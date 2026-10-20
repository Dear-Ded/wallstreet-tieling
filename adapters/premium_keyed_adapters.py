#!/usr/bin/env python3
"""Key-ready adapters for premium threat/infrastructure intelligence sources.

These adapters cover the sources that require a (free-tier) API key:
- Shodan (https://www.shodan.io): internet-exposed asset intelligence
- AlienVault OTX (https://otx.alienvault.com): threat intel pulses/IOCs
- VirusTotal (https://www.virustotal.com): domain/URL reputation (v3 API)

Design: the key is injected at construction time ONLY — never read from
disk, env, or config by the adapter; never logged (audit records hash the
query subject, never the key). Without a key, query() returns
`credentials_required` instead of failing. This keeps the project's
"no staged credentials" rule while making the project ready the moment
the operator provides keys.

Default-off, EXPERIMENTAL, SourceAccess.PUBLIC (free-tier public APIs).
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class _KeyedAdapter(SafeResearchAdapter):
    """Base for adapters that need a user-supplied API key at construction."""

    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = (api_key or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)


class ShodanHostLookup(_KeyedAdapter):
    """Shodan host intelligence for an IP.

    回答：该 IP 暴露了哪些端口/服务、banner、组织、ASN、漏洞提示。
    Free tier: 100 查询/月。key 来自 shodan.io 注册。
    """

    source_domain = "api.shodan.io"
    source_type = "infra_shodan_host_intel"
    data_boundary = "fully_public"

    def _build_url(self, keyword: str, **params) -> str:
        ip = urllib.parse.quote(keyword.strip())
        return f"https://api.shodan.io/shodan/host/{ip}?key={urllib.parse.quote(self._api_key)}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict) or data.get("error"):
            return {"lookup_failed": True, "reason": str(data.get("error", ""))[:120] if isinstance(data, dict) else ""}
        ports = data.get("ports", []) or []
        services = []
        for item in (data.get("data") or [])[:15]:
            if isinstance(item, dict):
                services.append({
                    "port": item.get("port"), "product": item.get("product", ""),
                    "version": str(item.get("version", ""))[:40],
                })
        return {
            "ip": data.get("ip_str", ""),
            "org": data.get("org", ""),
            "asn": data.get("asn", ""),
            "country": data.get("country_name", ""),
            "open_ports": ports[:30],
            "port_count": len(ports),
            "services": services,
            "vuln_hints": list((data.get("vulns") or {}).keys())[:10] if isinstance(data.get("vulns"), dict) else [],
            "last_update": data.get("last_update", ""),
            "data_note": "Shodan 公开暴露面数据 — 仅用于资产风险核验",
        }


class OtxDomainLookup(_KeyedAdapter):
    """AlienVault OTX general info for a domain/IPv4.

    回答：该指标被多少威胁情报 pulse 引用、pulse 名称与标签。
    Free tier: 注册即得 key。端点: /api/v1/indicators/domain/{d}/general
    """

    source_domain = "otx.alienvault.com"
    source_type = "threat_intel_otx_indicator"
    data_boundary = "fully_public"

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
            "X-OTX-API-KEY": self._api_key,
        }

    def _build_url(self, keyword: str, **params) -> str:
        indicator = urllib.parse.quote(keyword.strip())
        itype = str(params.get("itype", "domain")).lower()
        if itype not in ("domain", "IPv4", "hostname", "URL"):
            itype = "domain"
        return f"https://otx.alienvault.com/api/v1/indicators/{itype}/{indicator}/general"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        pulses = data.get("pulse_info", {}) or {}
        pulse_list = pulses.get("pulses", []) or []
        return {
            "pulse_count": pulses.get("count", len(pulse_list)),
            "pulses": [
                {"name": p.get("name", ""), "tags": list(p.get("tags") or [])[:10],
                 "created": p.get("created", "")}
                for p in pulse_list[:10] if isinstance(p, dict)
            ],
            "data_note": "OTX 威胁情报 — pulse 引用是负面风险信号，需结合上下文研判",
        }


class VirusTotalDomainLookup(_KeyedAdapter):
    """VirusTotal v3 domain reputation.

    回答：多少安全厂商标记该域名恶意、总检出数、注册信息摘要。
    Free tier: 500 req/day。key 来自 virustotal.com 注册。
    """

    source_domain = "www.virustotal.com"
    source_type = "threat_intel_vt_reputation"
    data_boundary = "fully_public"

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
            "x-apikey": self._api_key,
            "Accept": "application/json",
        }

    def _build_url(self, keyword: str, **params) -> str:
        domain = urllib.parse.quote(keyword.strip().lower())
        return f"https://www.virustotal.com/api/v3/domains/{domain}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        attrs = ((data or {}).get("data", {}) or {}).get("attributes", {}) or {}
        if not attrs:
            return {"lookup_failed": True}
        stats = attrs.get("last_analysis_stats", {}) or {}
        malicious = int(stats.get("malicious", 0) or 0)
        return {
            "malicious_votes": malicious,
            "suspicious_votes": int(stats.get("suspicious", 0) or 0),
            "harmless_votes": int(stats.get("harmless", 0) or 0),
            "total_engines": sum(int(v or 0) for v in stats.values()),
            "reputation": attrs.get("reputation", 0),
            "risk_flag": malicious > 0,
            "data_note": "VirusTotal 多引擎检出 — malicious>0 即负面风险信号",
        }
