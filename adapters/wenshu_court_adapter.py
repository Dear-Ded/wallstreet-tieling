#!/usr/bin/env python3
"""裁判文书网 (wenshu.court.gov.cn) 查询适配器 — 线下商业 lane.

中国裁判文书网是最高人民法院的官方文书公开平台,收录全国法院的裁判文书。
对线下个体工商户尽调的价值:查询经营者/商户名称是否涉及诉讼、被执行等司法风险。

**重要:Browser-assisted 模式**
本站搜索 API (/website/parse/rest.q4w) 要求请求参数经 DES 加密
(反爬措施),直接 HTTP 调用返回 {"code":9,"success":false}。
本适配器不尝试绕过加密,而是:
1. query() 返回 interaction_required,附带浏览器操作指引
2. 操作员在浏览器中完成搜索后,将结果 JSON 传入 parse_browser_result()
   进行结构化提取

公开数据,无需登录,无需凭证。3 秒间隔。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class WenshuCaseLookup(SafeResearchAdapter):
    """裁判文书网案件查询 (browser-assisted).

    查询维度:当事人名称 (支持企业/个体工商户/个人姓名)
    提取字段:文书标题、案号、法院、裁判日期、案件类型、文书 ID
    """

    source_domain = "wenshu.court.gov.cn"
    source_type = "judicial_case_records"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True  # 需要浏览器辅助完成搜索
    min_request_interval = 3.0

    SEARCH_URL = "https://wenshu.court.gov.cn/website/wenshu/181029CR4M5A62CH/index.html"
    API_ENDPOINT = "https://wenshu.court.gov.cn/website/parse/rest.q4w"

    BROWSER_INSTRUCTIONS = (
        "1. 在浏览器中打开 https://wenshu.court.gov.cn/\n"
        "2. 在搜索框输入当事人名称 (如商户字号或经营者姓名)\n"
        "3. 完成页面验证码 (如出现)\n"
        "4. 在搜索结果页,打开浏览器开发者工具 (F12) > Network\n"
        "5. 找到对 /website/parse/rest.q4w 的 POST 请求,复制 Response JSON\n"
        "6. 调用 parse_browser_result(response_json) 解析"
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
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def parse_browser_result(self, response_json: str | dict) -> dict[str, Any]:
        """解析从浏览器复制的搜索结果 JSON。

        Args:
            response_json: 浏览器 Network 面板中 rest.q4w 响应的 JSON
                (字符串或已解析的 dict)

        Returns:
            结构化的案件列表
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

        # rest.q4w 返回结构: {"result": {"resultList": [...], "count": N}}
        result = data.get("result") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {}

        result_list = result.get("resultList") or []
        cases = []
        for item in result_list[:20]:
            if not isinstance(item, dict):
                continue
            cases.append({
                "title": item.get("s1", ""),           # 案件名称
                "court": item.get("s2", ""),           # 法院名称
                "doc_id": item.get("s5", ""),          # 文书 ID
                "doc_type": item.get("s6", ""),        # 文书类型
                "case_number": item.get("s7", ""),     # 案号
                "case_type": item.get("s8", ""),       # 案件类型
                "cause": item.get("s11", ""),          # 案由
                "parties": item.get("s17", ""),        # 当事人
                "judgment_date": item.get("s31", ""),  # 裁判日期
                "doc_url": (
                    f"https://wenshu.court.gov.cn/website/wenshu/"
                    f"181029CR4M5A62CH/doc.html?docId={item.get('s5', '')}"
                    if item.get("s5") else ""
                ),
            })

        return {
            "total_count": result.get("count", len(cases)),
            "cases": cases,
            "data_note": "中国裁判文书网公开数据,案件信息仅供参考",
        }
