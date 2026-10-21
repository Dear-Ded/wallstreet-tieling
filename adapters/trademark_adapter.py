"""中国商标查询 — 国家知识产权局商标局公开数据适配器。数据边界: fully_public

商标注册信息是法定公开信息。
官方查询：https://wcjs.sbj.cnipa.gov.cn/ (中国商标网网上查询)

BROWSER-ASSISTED: 官方站点对程序化访问实施地域限制 (403)，
query() 返回 interaction_required + 浏览器操作指引；
parse_browser_result() 将浏览器中复制的查询结果 JSON 结构化。

提取：商标名称、注册号/申请号、申请人名称、申请日期、
注册公告日期、国际分类、商标状态。
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import json


class CnipaTrademarkLookup(SafeResearchAdapter):
    """中国商标注册信息查询 (browser-assisted)。"""

    source_domain = "wcjs.sbj.cnipa.gov.cn"
    source_type = "government_mandatory_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True
    min_request_interval = 3.0

    BROWSER_STEPS = [
        "1. 浏览器访问 https://sbj.cnipa.gov.cn/trademark-query",
        "2. 勾选同意后点击「进入查询」，跳转到 wcjs.sbj.cnipa.gov.cn",
        "3. 选择「商标综合查询」，输入商标名称或申请人",
        "4. 完成验证后查看结果列表",
        "5. 打开浏览器开发者工具 (F12) → Network 面板",
        "6. 找到商标查询 API 请求，复制 Response JSON",
        "7. 将 JSON 传给 parse_browser_result() 解析",
    ]

    def _build_url(self, keyword: str, **params) -> str:
        return "https://wcjs.sbj.cnipa.gov.cn/"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        parsed = self.parse_browser_result(raw_data)
        return {
            "total_found": parsed.get("total_found", 0),
            "records": parsed.get("records", []),
        }

    def query(self, keyword: str, **kwargs) -> dict:
        """商标查询需浏览器辅助。keyword: 商标名称/申请人/注册号。"""
        return {
            "status": "interaction_required",
            "keyword": keyword,
            "source": "wcjs.sbj.cnipa.gov.cn",
            "disclosure": "mandatory_public_trademark_register",
            "browser_steps": self.BROWSER_STEPS,
            "note": "官方站点对境外 IP 限制访问，需在境内网络环境下用浏览器查询",
        }

    def parse_browser_result(self, response_json) -> dict:
        """解析从浏览器复制的商标查询响应。"""
        try:
            data = json.loads(response_json) if isinstance(response_json, str) else response_json
        except Exception:
            return {"status": "parse_failed", "error": "invalid_json"}

        records = []
        # 兼容多种可能的响应结构
        items = []
        if isinstance(data, dict):
            for key in ("list", "rows", "data", "records"):
                v = data.get(key)
                if isinstance(v, list):
                    items = v
                    break
                elif isinstance(v, dict) and isinstance(v.get("list"), list):
                    items = v["list"]
                    break
        elif isinstance(data, list):
            items = data

        for item in items:
            if not isinstance(item, dict):
                continue
            records.append({
                # 商标名称 (多字段兼容)
                "mark_name": item.get("tmName") or item.get("markName")
                             or item.get("商标名称") or "",
                # 注册号/申请号
                "reg_number": item.get("regNo") or item.get("regNumber")
                              or item.get("申请号") or item.get("注册号") or "",
                # 申请人名称
                "applicant": item.get("applicantName") or item.get("applicant")
                             or item.get("申请人") or "",
                # 申请日期
                "app_date": item.get("appDate") or item.get("申请日期") or "",
                # 注册公告日期
                "reg_pub_date": item.get("regPubDate") or item.get("注册公告日期") or "",
                # 国际分类
                "intl_class": item.get("intCls") or item.get("internationalClass")
                              or item.get("国际分类") or "",
                # 商标状态
                "status_text": item.get("tmStatus") or item.get("status")
                               or item.get("商标状态") or "",
            })

        result = {
            "status": "ok",
            "total_found": len(records),
            "records": records,
            "source": "wcjs.sbj.cnipa.gov.cn",
            "disclosure": "mandatory_public_trademark_register",
        }
        return result
