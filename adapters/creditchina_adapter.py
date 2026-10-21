"""信用中国 — 政府公开行政处罚信息查询适配器。数据边界: fully_public

⚠️ STATUS: BROKEN (2026-10-21 实测, 见 docs/research/creditchina-feasibility-20261021.md)
creditchina.gov.cn 对程序化访问启用知道创宇 WAF JS 防, /、/search?keyword=、候选
/api/creditinfo/search 全部返回 HTTP 412, 前端 JS bundle 拿不到, 真实 XHR 端点无法确认。
此 adapter 在服务端直调场景下失效, 保留仅作结构参考。如需使用, 改走 browser-assisted
(真实浏览器可自动通过 JS 防), 抓到真实 XHR 端点后再重建。
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
from urllib.parse import urlencode

class CreditchinaAdapter(SafeResearchAdapter):
    source_domain = "www.creditchina.gov.cn"
    source_type = "government_public_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        page = params.get("page", 1)
        query = urlencode({"keyword": keyword, "page": page})
        return f"https://www.creditchina.gov.cn/search?{query}"

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        if not raw_data:
            return {}
        return {
            "penalty_count": len(re.findall(r"处罚决定书文号", raw_data)),
            "source": "creditchina.gov.cn",
            "disclosure_type": "government_administrative_penalty",
            "access_level": "fully_public_no_login_required",
        }
