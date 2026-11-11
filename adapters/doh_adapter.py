#!/usr/bin/env python3
"""DNS-over-HTTPS adapter (Google Public DNS) for DNS record verification.

`https://dns.google/resolve?name={domain}&type={TYPE}` — free, no key,
JSON API. Complements HackertargetInfraLookup with a second independent
DNS vantage point (cross-validating DNS answers is itself a due-diligence
signal: inconsistent answers across resolvers can indicate manipulation).

Supported types: A, AAAA, MX, NS, TXT, CNAME, SOA. Default-off, EXPERIMENTAL.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_SUPPORTED_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA")


class DnsOverHttpsLookup(SafeResearchAdapter):
    """Google DNS-over-HTTPS record lookup.

    MONEY线: DNS 记录独立交叉验证 — A/AAAA/MX/NS/TXT/CNAME/SOA。
    """

    source_domain = "dns.google"
    source_type = "infra_doh_dns_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 1.5

    def _build_url(self, keyword: str, **params) -> str:
        name = urllib.parse.quote(keyword.strip())
        rtype = str(params.get("rtype", "A")).upper()
        if rtype not in _SUPPORTED_TYPES:
            rtype = "A"
        return f"https://dns.google/resolve?name={name}&type={rtype}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() is overridden for multi-type fan-out; ABC satisfied.
        return {"raw": raw_data} if raw_data else {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        import hashlib
        import time

        start = time.monotonic()
        domain = keyword.strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=domain, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(domain, "robots_txt_disallowed")

        rtypes = params.get("rtypes") or ["A", "MX", "NS", "TXT"]
        fields: dict[str, Any] = {}
        worst_status, first_error = 0, ""
        for rtype in rtypes:
            if rtype not in _SUPPORTED_TYPES:
                continue
            self._enforce_rate_limit()
            url = self._build_url(domain, rtype=rtype)
            status, raw, error = self._execute_query(url, self._build_headers())
            worst_status = max(worst_status, status)
            if error and not first_error:
                first_error = error
            fields[rtype] = self._parse_answer(raw) if raw else {"error": error}
        fields["data_note"] = "Google DNS-over-HTTPS — 独立 DNS 视角，用于交叉验证"

        self._record_audit(keyword=domain, url=self._build_url(domain),
                           status=worst_status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(domain.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": worst_status,
            "fields": fields,
            "field_count": len(fields),
            "error": first_error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    @staticmethod
    def _parse_answer(raw: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        if data.get("Status") != 0:
            return {"dns_status": data.get("Status"), "answers": []}
        answers = []
        for ans in (data.get("Answer") or []):
            if isinstance(ans, dict):
                answers.append({"name": ans.get("name", ""), "type": ans.get("type"),
                                "ttl": ans.get("TTL"), "data": str(ans.get("data", ""))[:300]})
        return {"answer_count": len(answers), "answers": answers[:20]}
