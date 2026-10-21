#!/usr/bin/env python3
"""人民法院公告网 (rmfygg.court.gov.cn) 查询适配器 — 线下商业/关联深挖 lane.

人民法院公告网是最高人民法院的官方公告平台,发布全国法院的司法公告:
送达公告、开庭公告、执行公告、拍卖公告等。与裁判文书网互补
(公告是程序性公开,文书是实体裁判)。

对尽调的价值:查询当事人/企业名称是否涉及诉讼程序、被执行、
破产等司法风险信号。公告中的当事人关联是实控人深挖的线索。

**重要:Browser-assisted 模式**
本站搜索走 Liferay portlet API,经腾讯云 WAF 防护,直接程序化
POST 返回 403 WAF 拦截页。本适配器不尝试绕过 WAF,而是:
1. query() 返回 interaction_required,附带浏览器操作指引
2. 操作员在浏览器中完成搜索后,将结果 JSON 传入 parse_browser_result()
   进行结构化提取

技术细节 (2026-10-21 实测):
- 旧域名 ggzx.court.gov.cn 已 GeoIP 封锁境外 IP
- 新域名 rmfygg.court.gov.cn 可达 (HTTP 200),但搜索 API 被 WAF 拦
- 搜索端点: /web/rmfyportal/noticeinfo (Liferay portlet)
- resource_id: initNoticeList (主搜索)
- 参数前缀: _noticelist_WAR_rmfynoticeListportlet_
- 关键参数: searchContent (搜索关键词), noticeType (公告类型),
  courtParam (法院), aoData (DataTables 分页,JSON)

公开数据,无需登录,无需凭证。3 秒间隔。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class CourtNoticeLookup(SafeResearchAdapter):
    """人民法院公告网查询 (browser-assisted).

    查询维度:当事人名称 (支持企业/个体工商户/个人姓名)
    提取字段:公告标题、公告类型、法院、当事人、公告日期、案号
    """

    source_domain = "rmfygg.court.gov.cn"
    source_type = "judicial_notice_records"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True  # 需要浏览器辅助完成搜索
    min_request_interval = 3.0

    SEARCH_URL = "https://rmfygg.court.gov.cn/web/rmfyportal/noticeinfo"
    API_RESOURCE = "initNoticeList"

    # 公告类型代码 (noticeTypeCode,来自页面)
    NOTICE_TYPES = {
        "62": "开庭公告",
        "66": "送达公告",
        "998": "执行公告",
        "999": "其他公告",
    }

    BROWSER_INSTRUCTIONS = (
        "1. 在浏览器中打开 https://rmfygg.court.gov.cn/web/rmfyportal/noticeinfo\n"
        "2. 在搜索框输入当事人名称 (如企业全称、商户字号或经营者姓名)\n"
        "3. 点击搜索,等待结果加载\n"
        "4. 打开浏览器开发者工具 (F12) > Network 标签\n"
        "5. 找到 p_p_resource_id=initNoticeList 的 POST 请求,复制 Response JSON\n"
        "6. 调用 parse_browser_result(response_json) 解析\n"
        "\n"
        "提示:如需按公告类型筛选,先在页面选择类型再搜索\n"
        "(开庭公告/送达公告/执行公告)"
    )

    def _build_url(self, keyword: str, **params) -> str:
        return self.SEARCH_URL

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """返回 interaction_required,不直接发起搜索请求。"""
        start = time.monotonic()
        self._enforce_rate_limit()
        self._record_audit(
            keyword=keyword,
            url=self.SEARCH_URL,
            status=0,
            fields=[],
        )
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "fields": {},
            "field_count": 0,
            "error": "interaction_required",
            "interaction_instructions": self.BROWSER_INSTRUCTIONS,
            "notice_types": self.NOTICE_TYPES,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def parse_browser_result(self, response_json: str | dict) -> dict[str, Any]:
        """解析从浏览器复制的搜索结果 JSON.

        Args:
            response_json: 浏览器 Network 面板中 initNoticeList 响应的 JSON
                (字符串或已解析的 dict)

        Returns:
            结构化的公告列表
        """
        return {
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "fields": self._extract_public_fields(response_json),
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}

        if not isinstance(data, dict):
            return {"parse_error": True}

        # Liferay DataTables 响应格式:
        # {"iTotalRecords": N, "iTotalDisplayRecords": N, "aaData": [[...], ...]}
        # 也兼容 {"total": N, "data": [...]} / {"rows": [...]} 变体
        total = (
            data.get("iTotalRecords")
            or data.get("iTotalDisplayRecords")
            or data.get("total")
            or data.get("count")
            or 0
        )

        rows = (
            data.get("aaData")
            or data.get("data")
            or data.get("rows")
            or data.get("resultList")
            or []
        )

        notices = []
        for item in rows[:20]:
            if isinstance(item, dict):
                notices.append(self._parse_dict_row(item))
            elif isinstance(item, (list, tuple)):
                notices.append(self._parse_list_row(item))

        return {
            "total_count": total if isinstance(total, int) else len(notices),
            "notices": [n for n in notices if n],
            "data_note": "人民法院公告网公开数据,公告信息仅供参考",
        }

    def _parse_dict_row(self, item: dict) -> dict[str, str]:
        """解析 dict 格式的行数据."""
        # 字段名可能因版本而异,做多键兼容
        return {
            "title": (
                item.get("title") or item.get("noticeTitle")
                or item.get("bt") or ""
            ),
            "notice_type": (
                item.get("noticeType") or item.get("type")
                or item.get("gglx") or ""
            ),
            "court": (
                item.get("court") or item.get("courtName")
                or item.get("fy") or ""
            ),
            "parties": (
                item.get("parties") or item.get("partyName")
                or item.get("dsr") or ""
            ),
            "case_number": (
                item.get("caseNumber") or item.get("caseNo")
                or item.get("ah") or ""
            ),
            "publish_date": (
                item.get("publishDate") or item.get("date")
                or item.get("fbrq") or ""
            ),
            "notice_code": (
                item.get("noticeCode") or item.get("code")
                or item.get("ggbh") or ""
            ),
        }

    def _parse_list_row(self, item: list | tuple) -> dict[str, str]:
        """解析数组格式的行数据 (DataTables aaData 典型格式).

        列顺序按页面表格推测: [序号, 公告标题, 公告类型, 法院, 当事人, 发布日期]
        """
        cols = [str(c) if c is not None else "" for c in item]
        # 去掉 HTML 标签
        import re
        cols = [re.sub(r"<[^>]+>", "", c).strip() for c in cols]

        result = {
            "title": "",
            "notice_type": "",
            "court": "",
            "parties": "",
            "case_number": "",
            "publish_date": "",
            "notice_code": "",
        }
        # 启发式:通常第 2 列是标题,最后一列是日期
        if len(cols) >= 2:
            # 跳过纯数字序号列
            data_cols = [c for c in cols if c and not c.isdigit()]
            if data_cols:
                result["title"] = data_cols[0]
            if len(data_cols) >= 2:
                # 最后一列通常是日期 (YYYY-MM-DD 格式)
                last = data_cols[-1]
                if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", last):
                    result["publish_date"] = last
                    data_cols = data_cols[:-1]
            # 中间列:类型、法院、当事人
            if len(data_cols) >= 4:
                result["notice_type"] = data_cols[1]
                result["court"] = data_cols[2]
                result["parties"] = " | ".join(data_cols[3:])
            elif len(data_cols) >= 3:
                result["court"] = data_cols[1]
                result["parties"] = " | ".join(data_cols[2:])
            elif len(data_cols) >= 2:
                result["parties"] = data_cols[1]

        return result
