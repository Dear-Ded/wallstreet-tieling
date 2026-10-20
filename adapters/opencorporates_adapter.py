#!/usr/bin/env python3
"""OpenCorporates public API adapter for cross-border corporate registry lookup.

OpenCorporates (https://opencorporates.com) is the largest open database of
companies in the world (140M+ companies, 130+ jurisdictions). Its v0.4 API
requires a free API token (opencorporates.com registration), passed at
construction time and never persisted:

- ``GET /v0.4/companies/search?q={name}`` — company search by name
- ``GET /v0.4/companies/{jurisdiction_code}/{company_number}`` — company detail
- ``GET /v0.4/officers/search?q={name}`` — officer search

All data is fully public. The adapter stays default-off and is registered as
EXPERIMENTAL in the connector registry; enablement remains an explicit
operator decision per the project's source-admission policy.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class OpenCorporatesCompanyLookup(SafeResearchAdapter):
    """Search OpenCorporates for companies matching a name.

    MONEY线: 跨境主体注册信息 — 公司名、注册号、司法管辖区、公司类型、
    成立/注销日期、注册地址、登记机关链接、分支与活跃状态。

    NOTE (2026-10-20 实测): OpenCorporates v0.4 现要求 api_token（免费注册
    https://opencorporates.com 即可获取）。token 通过构造参数传入，
    不落盘、不进日志，符合项目"不暂存凭证"房规。
    """

    source_domain = "api.opencorporates.com"
    source_type = "enterprise_global_corporate_registry"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, api_token: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_token = (api_token or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_token)

    def _token_param(self) -> str:
        return f"&api_token={urllib.parse.quote(self._api_token)}"

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        per_page = max(1, min(int(params.get("per_page", 10)), 30))
        jurisdiction = str(params.get("jurisdiction_code") or "").strip()
        base = "https://api.opencorporates.com/v0.4/companies/search"
        url = f"{base}?q={query}&per_page={per_page}{self._token_param()}"
        if jurisdiction:
            url += f"&jurisdiction_code={urllib.parse.quote(jurisdiction)}"
        return url

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        results = (data or {}).get("results", {}) or {}
        companies = results.get("companies", []) or []
        samples: list[dict[str, Any]] = []
        for entry in companies[:10]:
            company = entry.get("company", {}) if isinstance(entry, dict) else {}
            if not isinstance(company, dict):
                continue
            samples.append({
                "name": company.get("name", ""),
                "company_number": company.get("company_number", ""),
                "jurisdiction_code": company.get("jurisdiction_code", ""),
                "company_type": company.get("company_type", ""),
                "incorporation_date": company.get("incorporation_date", ""),
                "dissolution_date": company.get("dissolution_date", ""),
                "registered_address": (company.get("registered_address_in_full")
                                       or company.get("registered_address", "")),
                "registry_url": company.get("registry_url", ""),
                "opencorporates_url": company.get("opencorporates_url", ""),
                "inactive": bool(company.get("inactive", False)),
                "branch": bool(company.get("branch", False)),
            })
        return {
            "companies_found": results.get("total_count", len(samples)),
            "per_page": results.get("per_page", len(samples)),
            "samples": samples,
            "data_note": "OpenCorporates 公开企业注册数据库 — 140M+ 公司，130+ 司法管辖区，免费公开层",
        }

    def query_by_jurisdiction_number(self, jurisdiction_code: str, company_number: str) -> dict[str, Any]:
        """Fetch a single company by jurisdiction code + company number."""
        keyword = f"{jurisdiction_code}/{company_number}"
        url = (
            "https://api.opencorporates.com/v0.4/companies/"
            f"{urllib.parse.quote(jurisdiction_code.strip())}/"
            f"{urllib.parse.quote(company_number.strip())}"
            f"?api_token={urllib.parse.quote(self._api_token)}"
        )
        return self._direct_get(keyword, url)

    def _direct_get(self, keyword: str, url: str) -> dict[str, Any]:
        import hashlib
        import time

        start = time.monotonic()
        if self.requires_credentials and not self._has_required_credentials():
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "credentials_required")
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=keyword, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(keyword, "robots_txt_disallowed")
        status, raw_data, error = self._execute_query(url, self._build_headers())
        fields = self._extract_company_detail_fields(raw_data) if raw_data else {}
        self._record_audit(keyword=keyword, url=url, status=status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "fields": fields,
            "field_count": len(fields),
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def _extract_company_detail_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        company = ((data or {}).get("results", {}) or {}).get("company", {}) or {}
        if not isinstance(company, dict):
            return {"not_found": True}
        officers = company.get("officers", []) or []
        officer_samples = [
            {
                "name": (o.get("officer", {}) or {}).get("name", ""),
                "position": (o.get("officer", {}) or {}).get("position", ""),
                "start_date": (o.get("officer", {}) or {}).get("start_date", ""),
            }
            for o in officers[:10] if isinstance(o, dict)
        ]
        filings = company.get("filings", []) or []
        return {
            "name": company.get("name", ""),
            "company_number": company.get("company_number", ""),
            "jurisdiction_code": company.get("jurisdiction_code", ""),
            "company_type": company.get("company_type", ""),
            "incorporation_date": company.get("incorporation_date", ""),
            "dissolution_date": company.get("dissolution_date", ""),
            "registered_address": company.get("registered_address_in_full", ""),
            "registry_url": company.get("registry_url", ""),
            "inactive": bool(company.get("inactive", False)),
            "officer_count": len(officers),
            "officer_samples": officer_samples,
            "filing_count": len(filings),
            "data_note": "OpenCorporates 公司详情 — 公开数据",
        }


class OpenCorporatesOfficerLookup(SafeResearchAdapter):
    """Search OpenCorporates for officers (directors) matching a person name.

    PEOPLE线: 关键人员任职 — 姓名、职位、任职公司、起止日期。
    注意：人名查询返回的是公开任职记录，用于交叉核验，不做身份断言。
    """

    source_domain = "api.opencorporates.com"
    source_type = "enterprise_officer_public_records"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, api_token: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_token = (api_token or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_token)

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        per_page = max(1, min(int(params.get("per_page", 10)), 30))
        token = f"&api_token={urllib.parse.quote(self._api_token)}"
        return f"https://api.opencorporates.com/v0.4/officers/search?q={query}&per_page={per_page}{token}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        results = (data or {}).get("results", {}) or {}
        officers = results.get("officers", []) or []
        samples: list[dict[str, Any]] = []
        for entry in officers[:10]:
            officer = entry.get("officer", {}) if isinstance(entry, dict) else {}
            if not isinstance(officer, dict):
                continue
            company = officer.get("company", {}) or {}
            samples.append({
                "name": officer.get("name", ""),
                "position": officer.get("position", ""),
                "start_date": officer.get("start_date", ""),
                "end_date": officer.get("end_date", ""),
                "company_name": company.get("name", ""),
                "jurisdiction_code": officer.get("jurisdiction_code", ""),
                "opencorporates_url": officer.get("opencorporates_url", ""),
            })
        return {
            "officers_found": results.get("total_count", len(samples)),
            "samples": samples,
            "data_note": "OpenCorporates 公开任职记录 — 仅用于交叉核验，不做身份断言",
        }
