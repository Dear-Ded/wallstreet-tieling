#!/usr/bin/env python3
"""Unit tests for key-ready premium adapters (Shodan, OTX, VirusTotal)."""

from __future__ import annotations

import json

from adapters.premium_keyed_adapters import (
    OtxDomainLookup,
    ShodanHostLookup,
    VirusTotalDomainLookup,
)
from core.connector_registry import ConnectorRegistry


def _stub(cls, payload, **kwargs):
    body = json.dumps(payload)
    return cls(
        api_key="test-key",
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_key_gate_blocks_without_key():
    for cls in (ShodanHostLookup, OtxDomainLookup, VirusTotalDomainLookup):
        adapter = cls(
            execute_query=lambda u, h: (200, "{}", ""),
            robots_checker=lambda d, u: True,
            sleeper=lambda s: None,
        )
        result = adapter.query("example.com")
        assert "credentials_required" in result["error"]
        # key must not leak into the error or audit trail
        trail = adapter.audit.get_trail()
        assert trail and "test" not in trail[0].get("query_params_hash", "")


def test_shodan_extracts_host():
    payload = {"ip_str": "8.8.8.8", "org": "Google LLC", "asn": "AS15169",
               "country_name": "United States", "ports": [53, 443],
               "data": [{"port": 53, "product": "DNS", "version": ""}],
               "vulns": {"CVE-2020-1234": {}}, "last_update": "2026-01-01"}
    adapter = _stub(ShodanHostLookup, payload)
    result = adapter.query("8.8.8.8")
    assert result["fields"]["port_count"] == 2
    assert result["fields"]["vuln_hints"] == ["CVE-2020-1234"]


def test_otx_extracts_pulses():
    payload = {"pulse_info": {"count": 2, "pulses": [
        {"name": "Bad Stuff", "tags": ["malware"], "created": "2026-01-01"}]}}
    adapter = _stub(OtxDomainLookup, payload)
    result = adapter.query("evil.example", itype="domain")
    assert result["fields"]["pulse_count"] == 2
    assert result["fields"]["pulses"][0]["name"] == "Bad Stuff"
    # key goes in header, not URL
    assert "test-key" not in adapter._build_url("evil.example")


def test_virustotal_reputation():
    payload = {"data": {"attributes": {
        "last_analysis_stats": {"malicious": 3, "suspicious": 1, "harmless": 80},
        "reputation": -10}}}
    adapter = _stub(VirusTotalDomainLookup, payload)
    result = adapter.query("evil.example")
    assert result["fields"]["malicious_votes"] == 3
    assert result["fields"]["risk_flag"] is True
    assert "test-key" not in adapter._build_url("evil.example")


def test_keyed_adapters_audit_integrity():
    adapter = _stub(ShodanHostLookup, {"ip_str": "1.1.1.1"})
    adapter.query("1.1.1.1")
    assert adapter.audit.verify_integrity() is True
    # audit trail must not contain the raw key
    import json as _json
    assert "test-key" not in _json.dumps(adapter.audit.get_trail())
