"""智联招聘企业信息 — 公开职位搜索页解析。数据边界: fully_public

Zhaopin (zhaopin.com) job search pages embed structured JSON:
- Search: /sou/?q={kw} → HTML with embedded job records
  (companyName, companyNumber, companySize, companyUrl, financingStage,
   industryName, firstPublishTime, displayPhoneNumber, jobDetailData)

Association value (实体关联):
- Company name → companyNumber (智联企业编码) = stable entity ID
- Company → financing stage / size / industry = business profile
- firstPublishTime = recruitment activity timeline
- displayPhoneNumber = contact signal

Philosophy: 招聘信息是企业主动公开的。只取公开的。
公开的就是公开的。

Rate limit: 3s between requests. No credentials. Default-off.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
from urllib.parse import quote


class ZhaopinCompanyLookup(SafeResearchAdapter):
    """智联招聘企业搜索：公司名 → 规模/融资/行业/联系方式。"""

    source_domain = "www.zhaopin.com"
    source_type = "recruitment_platform"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://www.zhaopin.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def _build_url(self, keyword: str, **params) -> str:
        return f"{self._BASE}/sou/?q={quote(keyword)}"

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    # Fields to extract per job record (company-centric)
    _FIELD_PATTERNS = [
        ("company_name", r'"companyName":"((?:[^"\\]|\\.)*)"'),
        ("company_number", r'"companyNumber":"((?:[^"\\]|\\.)*)"'),
        ("company_size", r'"companySize":"((?:[^"\\]|\\.)*)"'),
        ("company_url", r'"companyUrl":"((?:[^"\\]|\\.)*)"'),
        ("financing_stage", r'"financingStage":"((?:[^"\\]|\\.)*)"'),
        ("industry", r'"industryName":"((?:[^"\\]|\\.)*)"'),
        ("first_publish_time", r'"firstPublishTime":"((?:[^"\\]|\\.)*)"'),
        ("display_phone", r'"displayPhoneNumber":"((?:[^"\\]|\\.)*)"'),
        ("job_name", r'"jobName":"((?:[^"\\]|\\.)*)"'),
        ("salary", r'"salary":"((?:[^"\\]|\\.)*)"'),
        ("work_city", r'"workCity":"((?:[^"\\]|\\.)*)"'),
    ]

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse zhaopin search page embedded JSON."""
        if not raw_data:
            return {"company_found": False, "records": []}
        # Each job record contains "companyName":"..."
        # Split page into record windows at each companyName occurrence
        indices = [m.start() for m in re.finditer(r'"companyName":"', raw_data)]
        records = []
        seen_companies: dict[str, dict] = {}
        for idx in indices:
            # Take a window after this marker; fields for this record
            # appear within ~3000 chars (verified 2026-10-21)
            window = raw_data[idx:idx + 3000]
            rec: dict[str, Any] = {}
            for field, pat in self._FIELD_PATTERNS:
                m = re.search(pat, window)
                if m:
                    # Only decode \uXXXX escapes; page is already UTF-8.
                    # codecs.unicode_escape would mangle real CJK chars.
                    val = re.sub(
                        r"\\u([0-9a-fA-F]{4})",
                        lambda mm: chr(int(mm.group(1), 16)),
                        m.group(1),
                    )
                    val = val.replace('\\"', '"').replace("\\\\", "\\")
                    if val:
                        rec[field] = val
            if rec.get("company_name"):
                records.append(rec)
                cname = rec["company_name"]
                if cname not in seen_companies:
                    seen_companies[cname] = {
                        "company_name": cname,
                        "company_number": rec.get("company_number"),
                        "company_size": rec.get("company_size"),
                        "company_url": rec.get("company_url"),
                        "financing_stage": rec.get("financing_stage"),
                        "industry": rec.get("industry"),
                        "display_phone": rec.get("display_phone"),
                    }
        return {
            "company_found": bool(records),
            "record_count": len(records),
            "records": records[:50],
            "company_count": len(seen_companies),
            "companies": list(seen_companies.values())[:20],
        }
