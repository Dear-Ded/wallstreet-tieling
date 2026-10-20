#!/usr/bin/env python3
"""Unit tests for the DNS-over-HTTPS adapter."""

from __future__ import annotations

import json

from adapters.doh_adapter import DnsOverHttpsLookup
from core.connector_registry import ConnectorRegistry


def _stub(payload, **kwargs):
    body = json.dumps(payload)
    return DnsOverHttpsLookup(
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_doh_parses_answers():
    payload = {"Status": 0, "Answer": [
        {"name": "example.com.", "type": 1, "TTL": 300, "data": "93.184.216.34"},
        {"name": "example.com.", "type": 1, "TTL": 300, "data": "93.184.216.35"},
    ]}
    adapter = _stub(payload)
    result = adapter.query("example.com", rtypes=["A"])
    assert result["response_status"] == 200
    assert result["fields"]["A"]["answer_count"] == 2


def test_doh_nxdomain():
    adapter = _stub({"Status": 3})
    result = adapter.query("nope.invalid", rtypes=["A"])
    assert result["fields"]["A"]["dns_status"] == 3
    assert result["fields"]["A"]["answers"] == []


def test_doh_rejects_bad_rtype():
    adapter = _stub({"Status": 0, "Answer": []})
    url = adapter._build_url("example.com", rtype="AXFR")
    assert "type=A" in url
    assert adapter.min_request_interval >= 1.0


def test_doh_audit_integrity():
    adapter = _stub({"Status": 0, "Answer": []})
    adapter.query("example.com", rtypes=["A", "MX"])
    assert adapter.audit.verify_integrity() is True
