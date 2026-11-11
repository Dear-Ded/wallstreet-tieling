"""拉勾招聘企业信息 — 公开企业搜索与详情。数据边界: fully_public

Lagou (lagou.com) company search is fully accessible without login:
- Company search API: /gongsi/search.json?companyName={kw} → JSON
  (companyFullName, companyShortName, city, industryField, financeStage,
   companySize, positionNum, interviewRemarkNum, updateTime, companyId)
- Company detail page: /gongsi/{companyId}.html → HTML with embedded JSON
  (district, detailAddress, lat/lng, positions list with positionName)

Association value (实体关联):
- Company name → registered address (detailAddress) = address association
- Company → finance stage / size = business scale signal
- Position count trends = expansion/contraction signal
- Multiple companies at same address = shared address pattern

Philosophy: 招聘信息是企业主动公开的。只取公开的。
公开的就是公开的。

Rate limit: 3s between requests. No credentials. Default-off.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import json
import re
from urllib.parse import quote


class LagouCompanyLookup(SafeResearchAdapter):
    """拉勾企业搜索：公司名 → 规模/融资/地址/在招职位。"""

    source_domain = "www.lagou.com"
    source_type = "recruitment_platform"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://www.lagou.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def _build_url(self, keyword: str, **params) -> str:
        return (
            f"{self._BASE}/gongsi/search.json"
            f"?companyName={quote(keyword)}&first=false&pn=1"
        )

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self._BASE}/gongsi/",
        }

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse lagou company search JSON."""
        if not raw_data:
            return {"company_found": False, "companies": []}
        try:
            data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            return {"company_found": False, "companies": [], "parse_error": True}
        results = data.get("result") or []
        companies = []
        for r in results:
            companies.append({
                "company_id": r.get("companyId"),
                "company_full_name": r.get("companyFullName"),
                "company_short_name": r.get("companyShortName"),
                "city": r.get("city"),
                "industry": r.get("industryField"),
                "finance_stage": r.get("financeStage"),
                "company_size": r.get("companySize"),
                "position_count": r.get("positionNum"),
                "interview_remarks": r.get("interviewRemarkNum"),
                "update_time": r.get("updateTime"),
                "benefits": r.get("otherLabel"),
                "detail_url": (
                    f"{self._BASE}/gongsi/{r.get('companyId')}.html"
                    if r.get("companyId") else None
                ),
            })
        return {
            "company_found": bool(companies),
            "company_count": len(companies),
            "companies": companies,
        }

    def query_company_detail(self, company_id: int) -> dict[str, Any]:
        """Fetch company detail page: address, lat/lng, positions.

        Returns dict with detail fields. Uses same rate limiting.
        """
        self._enforce_rate_limit()
        url = f"{self._BASE}/gongsi/{company_id}.html"
        headers = {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self._BASE}/gongsi/",
        }
        status, raw, error = self._execute_query(url, headers)
        fields = self._parse_detail_page(raw) if raw else {}
        self._record_audit(
            keyword=f"company_id:{company_id}", url=url,
            status=status, fields=list(fields.keys()),
        )
        return {
            "source_domain": self.source_domain,
            "response_status": status,
            "fields": fields,
            "error": error,
        }

    def _parse_detail_page(self, html: str) -> dict[str, Any]:
        """Extract address, geo, positions from company detail HTML."""
        fields: dict[str, Any] = {}
        # Address block: "city":"北京","district":"海淀区","detailAddress":"..."
        m = re.search(
            r'"city":"([^"]*)","district":"([^"]*)","detailAddress":"([^"]*)"'
            r'(?:,"lat":"([^"]*)","lng":"([^"]*)")?',
            html,
        )
        if m:
            fields["city"] = m.group(1)
            fields["district"] = m.group(2)
            fields["detail_address"] = m.group(3)
            if m.group(4):
                fields["lat"] = m.group(4)
                fields["lng"] = m.group(5)
            fields["full_address"] = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        # Company meta
        for key, pat in [
            ("company_size", r'"companySize":"([^"]*)"'),
            ("finance_stage", r'"financeStage":"([^"]*)"'),
            ("industry", r'"industryField":"([^"]*)"'),
            ("company_full_name", r'"companyFullName":"([^"]*)"'),
        ]:
            mm = re.search(pat, html)
            if mm:
                fields[key] = mm.group(1)
        # Positions
        positions = re.findall(r'"positionName":"([^"]*)"', html)
        # Deduplicate preserving order
        seen = set()
        uniq = []
        for p in positions:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        fields["positions"] = uniq[:50]
        fields["position_count_on_page"] = len(uniq)
        return fields
