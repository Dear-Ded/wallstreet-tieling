"""信用中国 — 政府公开行政处罚信息查询适配器。数据边界: fully_public"""
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
