#!/usr/bin/env python3
"""Optional intel-enrichment module for investigation packets.

Plugs the existing OSINT adapters into investigation packets through two
small, dependency-injected entry points:

- ``enrich_domain(domain, ...)`` — infrastructure intel for a domain
  (urlscan.io scan history, hackertarget DNS/reverse-IP/headers,
  ip-api geolocation/ASN/hosting).
- ``enrich_person(query, ...)`` — people intel via ``PeopleIntelOrchestrator``
  (email, GitHub deep, OpenCorporates officers, username footprint).

Design rules (per project house rules):
- Adapters are ALWAYS injected by the caller, never constructed here —
  credentialed adapters (e.g. OpenCorporates) stay default-off; this module
  cannot enable anything on its own.
- Every adapter failure degrades to a per-source error entry; one source
  never breaks the others.
- ``risk_notes`` / corroborations are leads only, never factual assertions.
- Public evidence only. No breach data, no mailbox probing, no intrusive
  scanning — the adapters exclude those by design; this module adds no new
  collection surface.
"""

from __future__ import annotations

import time
from typing import Any

from core.people_intel import PeopleIntelOrchestrator, PersonQuery

_ORCHESTRATOR_ADAPTER_FIELDS = frozenset({
    "email_adapter", "github_adapter", "officer_adapter", "username_adapter",
    "social_adapter", "dev_footprint_adapters",
})


def _safe_adapter_call(adapter: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run one adapter call; failures degrade to an error entry."""
    try:
        result = adapter.query(*args, **kwargs)
        if isinstance(result, dict):
            return result
        return {"error": "unexpected_result_shape"}
    except Exception as exc:  # noqa: BLE001 - per-source degradation
        return {"error": f"{type(exc).__name__}: {exc}"}


def _fields_of(source_result: Any) -> dict[str, Any]:
    fields = (source_result or {}).get("fields")
    return fields if isinstance(fields, dict) else {}


def enrich_domain(
    domain: str,
    *,
    urlscan: Any = None,
    hackertarget: Any = None,
    ipapi: Any = None,
) -> dict[str, Any]:
    """Enrich a domain with infrastructure intel from injected adapters.

    Cross-source step: the first A record from hackertarget's DNS lookup is
    fed into ip-api, so the enrichment can surface registered-vs-actual
    location mismatches as leads.
    """
    start = time.monotonic()
    target = (domain or "").strip().lower()
    sources: dict[str, Any] = {}
    risk_notes: list[str] = []

    if urlscan is not None:
        sources["urlscan"] = _safe_adapter_call(urlscan, target)
    if hackertarget is not None:
        sources["hackertarget"] = _safe_adapter_call(
            hackertarget, target, endpoints=["dnslookup", "reverseiplookup"])
    if ipapi is not None:
        ip = _first_a_record(_fields_of(sources.get("hackertarget")))
        if ip:
            sources["ipapi"] = _safe_adapter_call(ipapi, ip)
        else:
            sources["ipapi"] = {"error": "no_a_record_for_ip_lookup"}

    # Lead-only risk notes.
    urlscan_fields = _fields_of(sources.get("urlscan"))
    if "urlscan" in sources and urlscan_fields.get("total_scans") == 0:
        risk_notes.append("无公开扫描记录，互联网可见度低")
    hackertarget_fields = _fields_of(sources.get("hackertarget"))
    reverse = hackertarget_fields.get("reverseiplookup")
    neighbor_count = reverse.get("neighbor_count") if isinstance(reverse, dict) else None
    if isinstance(neighbor_count, int) and neighbor_count > 20:
        risk_notes.append(f"同 IP 存在 {neighbor_count} 个邻居域名，共享主机")
    ipapi_fields = _fields_of(sources.get("ipapi"))
    if ipapi_fields.get("is_hosting") is True:
        risk_notes.append("服务器位于托管机房")
    if ipapi_fields.get("is_proxy") is True:
        risk_notes.append("IP 疑似代理出口，地理归属仅供参考")

    return {
        "type": "domain_intel_enrichment",
        "domain": target,
        "sources": sources,
        "source_count": len(sources),
        "risk_notes": risk_notes,
        "policy": (
            "基础设施公开数据；risk_notes 仅为线索提示，不做归属或风险断言；"
            "域名所有权与风险结论需复核与准入测试。"
        ),
        "duration_ms": (time.monotonic() - start) * 1000,
    }


def _first_a_record(hackertarget_fields: dict[str, Any]) -> str:
    dns = hackertarget_fields.get("dnslookup")
    if not isinstance(dns, dict):
        return ""
    records = dns.get("records")
    if not isinstance(records, dict):
        return ""
    a_records = records.get("A") or []
    for entry in a_records:
        candidate = str(entry).strip()
        if candidate and not candidate.lower().startswith("error"):
            return candidate
    return ""


def enrich_person(
    query: PersonQuery | dict[str, Any],
    *,
    orchestrator: PeopleIntelOrchestrator | None = None,
    **adapters: Any,
) -> dict[str, Any]:
    """Enrich a person query via an injected PeopleIntelOrchestrator.

    Either pass a ready-made ``orchestrator`` or pass adapters as keyword
    arguments (``email_adapter=...``, ``github_adapter=...``,
    ``officer_adapter=...``, ``username_adapter=...``,
    ``social_adapter=...``) to build one.
    With neither, returns an empty lead graph — nothing runs by default.
    """
    if orchestrator is None:
        known = {k: v for k, v in adapters.items()
                 if k in _ORCHESTRATOR_ADAPTER_FIELDS}
        if not known:
            return {
                "type": "people_lead_graph",
                "subject_hash": "",
                "identifiers_provided": {},
                "sources": {},
                "source_count": 0,
                "corroborations": [],
                "note": "未提供任何人物情报适配器，未执行查询（默认关闭）",
                "policy": (
                    "人物公开情报；corroborations 仅为线索提示，不做身份断言；"
                    "人物级事实断言需 exact/strong 主体匹配与复核。"
                ),
            }
        orchestrator = PeopleIntelOrchestrator(**known)
    return orchestrator.investigate(query)
