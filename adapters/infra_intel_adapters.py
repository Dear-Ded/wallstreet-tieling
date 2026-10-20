#!/usr/bin/env python3
"""Infrastructure intelligence adapters for asset/risk verification.

MONEY线 / 风控线: 用公开基础设施数据回答三个尽调问题 —
1. 这个域名在互联网上真实存在并被扫描过吗？(urlscan.io)
2. 它的 DNS / 同 IP 邻居 / HTTP 头暴露了什么？(hackertarget)
3. 它的 IP 实际归属哪、是不是托管机房？(ip-api.com)

All three are free, credential-free public APIs. Default-off,
EXPERIMENTAL in the connector registry. No breach data, no intrusive
scanning — only public lookup endpoints.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class UrlScanDomainLookup(SafeResearchAdapter):
    """urlscan.io public scan history for a domain.

    回答：该域名被公开扫描过多少次、最近扫描到的 URL、页面标题。
    扫描记录是提交者主动公开的；未被扫描过本身也是信号（新域名/低可见度）。
    """

    source_domain = "urlscan.io"
    source_type = "infra_domain_scan_history"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        domain = urllib.parse.quote(keyword.strip().lower())
        size = max(1, min(int(params.get("size", 10)), 100))
        return f"https://urlscan.io/api/v1/search/?q=domain:{domain}&size={size}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        results = data.get("results", []) or []
        scans: list[dict[str, Any]] = []
        for item in results[:10]:
            if not isinstance(item, dict):
                continue
            task = item.get("task", {}) or {}
            page = item.get("page", {}) or {}
            scans.append({
                "scanned_url": task.get("url", ""),
                "scan_date": task.get("time", ""),
                "page_title": (page.get("title") or "")[:120],
                "country": page.get("country", ""),
                "ip": page.get("ip", ""),
                "result_url": item.get("result", ""),
            })
        return {
            "total_scans": data.get("total", len(scans)),
            "recent_scans": scans,
            "data_note": "urlscan.io 公开扫描历史 — 提交者主动公开；无记录=低可见度或新域名",
        }


class HackertargetInfraLookup(SafeResearchAdapter):
    """hackertarget.com free infrastructure lookups.

    三个只读端点：
    - dnslookup: A/MX/NS/TXT 记录
    - reverseiplookup: 同 IP 上的其他域名（共享主机/关联资产线索）
    - httpheaders: HTTP 响应头（Server 技术栈披露）
    """

    source_domain = "api.hackertarget.com"
    source_type = "infra_dns_host_intel"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    _ENDPOINTS = ("dnslookup", "reverseiplookup", "httpheaders")

    def _build_url(self, keyword: str, **params) -> str:
        endpoint = str(params.get("endpoint", "dnslookup"))
        if endpoint not in self._ENDPOINTS:
            endpoint = "dnslookup"
        target = urllib.parse.quote(keyword.strip())
        return f"https://api.hackertarget.com/{endpoint}/?q={target}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() is overridden for multi-endpoint fan-out; ABC satisfied.
        return {"raw": raw_data} if raw_data else {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        import hashlib
        import time

        start = time.monotonic()
        target = keyword.strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=target, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(target, "robots_txt_disallowed")

        endpoints = params.get("endpoints") or ["dnslookup", "reverseiplookup"]
        fields: dict[str, Any] = {}
        worst_status, first_error = 0, ""
        for endpoint in endpoints:
            if endpoint not in self._ENDPOINTS:
                continue
            self._enforce_rate_limit()
            url = self._build_url(target, endpoint=endpoint)
            status, raw, error = self._execute_query(url, self._build_headers())
            worst_status = max(worst_status, status)
            if error and not first_error:
                first_error = error
            fields[endpoint] = self._parse_text_result(endpoint, raw) if raw else {"error": error}
        fields["data_note"] = "hackertarget 免费基础设施查询 — 公开 DNS/HTTP 信息，无侵入扫描"

        self._record_audit(keyword=target, url=self._build_url(target),
                           status=worst_status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(target.encode()).hexdigest()[:12],
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
    def _parse_text_result(endpoint: str, raw: Any) -> dict[str, Any]:
        text = raw if isinstance(raw, str) else ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if endpoint == "dnslookup":
            records: dict[str, list[str]] = {}
            for ln in lines:
                parts = ln.split(" : ", 1)
                if len(parts) == 2:
                    records.setdefault(parts[0].strip(), []).append(parts[1].strip())
            return {"record_types": sorted(records.keys()), "records": records}
        if endpoint == "reverseiplookup":
            neighbors = [ln for ln in lines if "." in ln and "error" not in ln.lower()]
            return {"neighbor_count": len(neighbors), "neighbors": neighbors[:50]}
        if endpoint == "httpheaders":
            headers = {}
            for ln in lines:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip()] = v.strip()[:200]
            interesting = {k: v for k, v in headers.items()
                           if k.lower() in ("server", "x-powered-by", "via", "x-server", "powered-by")}
            return {"server_disclosure": interesting, "header_count": len(headers)}
        return {"lines": lines[:20]}


class IpApiGeolocationLookup(SafeResearchAdapter):
    """ip-api.com free IP geolocation + ASN/org + hosting detection.

    回答：IP 归属国家/城市、运营商/AS、是否为托管机房（hosting 字段）。
    注册地址声称 vs 服务器实际位置不一致是经典风险信号。
    免费层 45 req/min；本适配器 2s 间隔远低于限额。
    """

    source_domain = "ip-api.com"
    source_type = "infra_ip_geolocation"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    _FIELDS = "status,country,regionName,city,org,as,hosting,proxy,query"

    def _build_url(self, keyword: str, **params) -> str:
        ip = urllib.parse.quote(keyword.strip())
        return f"http://ip-api.com/json/{ip}?fields={self._FIELDS}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict) or data.get("status") != "success":
            return {"lookup_failed": True, "raw_status": data.get("status") if isinstance(data, dict) else None}
        return {
            "ip": data.get("query", ""),
            "country": data.get("country", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "org": data.get("org", ""),
            "asn": data.get("as", ""),
            "is_hosting": bool(data.get("hosting", False)),
            "is_proxy": bool(data.get("proxy", False)),
            "data_note": "ip-api.com 公开 IP 地理/ASN 数据；hosting=机房托管",
        }
