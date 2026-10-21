#!/usr/bin/env python3
"""CertTransparencyLookup 单元测试（全部 stub，不依赖 crt.sh 实时可用性）。"""
from __future__ import annotations

import json

from adapters.cert_transparency_adapter import CertTransparencyLookup, _parse_san_field


def _stub_executor(payload: object, status: int = 200):
    def _exec(url: str, headers: dict):
        body = json.dumps(payload) if not isinstance(payload, str) else payload
        return status, body, ""
    return _exec


def _make_adapter(payload: object, status: int = 200) -> CertTransparencyLookup:
    return CertTransparencyLookup(
        execute_query=_stub_executor(payload, status),
        robots_checker=lambda domain, url: True,
    )


SAMPLE_CRT_JSON = [
    {
        "id": 123456,
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "example.com",
        "name_value": "example.com\nwww.example.com\napi.example.com",
        "not_before": "2026-01-01T00:00:00",
        "not_after": "2026-04-01T00:00:00",
        "serial_number": "abc123",
    },
    {
        "id": 123457,
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "*.example.org",
        "name_value": "*.example.org\nexample.org",
        "not_before": "2026-02-01T00:00:00",
        "not_after": "2026-05-01T00:00:00",
        "serial_number": "def456",
    },
]


def test_parse_san_field_dedup_and_normalize():
    sans = _parse_san_field("Example.COM\nwww.example.com\n\nexample.com\n")
    assert sans == ["example.com", "www.example.com"]


def test_field_extraction():
    a = _make_adapter(SAMPLE_CRT_JSON)
    r = a.query("example.com")
    f = r["fields"]
    assert f["cert_count"] == 2
    assert f["associated_domain_count"] == 5
    assert "www.example.com" in f["associated_domains"]
    assert "*.example.org" in f["associated_domains"]
    assert f["certs"][0]["san_count"] == 3
    assert "关联线索" in f["data_note"]


def test_wildcard_param_builds_percent_query():
    seen: list[str] = []
    def _exec(url: str, headers: dict):
        seen.append(url)
        return 200, "[]", ""
    a = CertTransparencyLookup(execute_query=_exec, robots_checker=lambda d, u: True)
    a.query("example.com", wildcard=True)
    assert seen, "expected query to execute (robots blocked?)"
    assert "%25" in seen[0]


def test_empty_result():
    a = _make_adapter([])
    r = a.query("nonexistent-xyz123.com")
    assert r["fields"]["cert_count"] == 0
    assert r["fields"]["associated_domains"] == []


def test_service_unavailable_on_502():
    a = _make_adapter("<html>502</html>", status=502)
    r = a.query("example.com")
    assert r["response_status"] == 502
    assert r["fields"].get("service_unavailable") is True


def test_garbage_input():
    a = _make_adapter("not json{{{")
    r = a.query("example.com")
    assert r["fields"].get("parse_error") is True


def test_query_live_cert_unreachable():
    a = CertTransparencyLookup()
    r = a.query_live_cert("nonexistent-domain-xyz123456789.com", timeout=3)
    assert r.get("lookup_failed") is True


def test_audit_trail_no_secrets():
    a = _make_adapter(SAMPLE_CRT_JSON)
    a.query("example.com")
    trail = a.audit.get_trail()
    assert trail, "expected audit records"
    assert a.audit.verify_integrity()
    blob = json.dumps(trail)
    assert "query_params_hash" in blob  # query 明文不进审计日志，只有哈希
