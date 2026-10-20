#!/usr/bin/env python3
"""Unit tests for infrastructure intel adapters (urlscan, hackertarget, ip-api).

HTTP is stubbed via SafeResearchAdapter's execute_query override.
"""

from __future__ import annotations

import json

from adapters.infra_intel_adapters import (
    HackertargetInfraLookup,
    IpApiGeolocationLookup,
    UrlScanDomainLookup,
)
from core.connector_registry import ConnectorRegistry, ConnectorStatus


def _stub(adapter_cls, payload, status=200, **kwargs):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return adapter_cls(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_urlscan_extracts_scans():
    payload = {"total": 42, "results": [
        {"task": {"url": "https://example.com/", "time": "2026-10-01T00:00:00Z"},
         "page": {"title": "Example", "country": "US", "ip": "93.184.216.34"},
         "result": "https://urlscan.io/result/abc/"}]}
    adapter = _stub(UrlScanDomainLookup, payload)
    result = adapter.query("example.com")
    assert result["response_status"] == 200
    assert result["fields"]["total_scans"] == 42
    scan = result["fields"]["recent_scans"][0]
    assert scan["page_title"] == "Example"
    assert scan["ip"] == "93.184.216.34"


def test_urlscan_empty_history():
    adapter = _stub(UrlScanDomainLookup, {"total": 0, "results": []})
    result = adapter.query("brand-new-domain-xyz.example")
    assert result["fields"]["total_scans"] == 0
    assert result["fields"]["recent_scans"] == []


def test_hackertarget_parses_dns():
    text = ("A : 93.184.216.34\nMX : 0 mail.example.com.\n"
            "NS : ns1.example.com.\nTXT : \"v=spf1 -all\"")
    adapter = _stub(HackertargetInfraLookup, text)
    result = adapter.query("example.com", endpoints=["dnslookup"])
    dns = result["fields"]["dnslookup"]
    assert "A" in dns["record_types"]
    assert dns["records"]["A"] == ["93.184.216.34"]
    assert dns["records"]["TXT"] == ['"v=spf1 -all"']


def test_hackertarget_reverse_ip():
    text = "example.com\nexample.org\nexample.net"
    adapter = _stub(HackertargetInfraLookup, text)
    result = adapter.query("93.184.216.34", endpoints=["reverseiplookup"])
    rev = result["fields"]["reverseiplookup"]
    assert rev["neighbor_count"] == 3
    assert "example.org" in rev["neighbors"]


def test_hackertarget_headers():
    text = "HTTP/1.1 200 OK\nServer: nginx/1.24\nX-Powered-By: PHP/8.2\nContent-Type: text/html"
    adapter = _stub(HackertargetInfraLookup, text)
    result = adapter.query("example.com", endpoints=["httpheaders"])
    disclosure = result["fields"]["httpheaders"]["server_disclosure"]
    assert disclosure["Server"] == "nginx/1.24"


def test_hackertarget_rejects_bad_endpoint():
    adapter = _stub(HackertargetInfraLookup, "ok")
    url = adapter._build_url("example.com", endpoint="nmap")
    assert "dnslookup" in url  # falls back to safe default


def test_ipapi_extracts_geo():
    payload = {"status": "success", "query": "8.8.8.8", "country": "United States",
               "regionName": "Virginia", "city": "Ashburn",
               "org": "Google Public DNS", "as": "AS15169 Google LLC",
               "hosting": True, "proxy": False}
    adapter = _stub(IpApiGeolocationLookup, payload)
    result = adapter.query("8.8.8.8")
    fields = result["fields"]
    assert fields["country"] == "United States"
    assert fields["asn"] == "AS15169 Google LLC"
    assert fields["is_hosting"] is True
    assert fields["is_proxy"] is False


def test_ipapi_failed_lookup():
    adapter = _stub(IpApiGeolocationLookup, {"status": "fail", "message": "reserved range"})
    result = adapter.query("127.0.0.1")
    assert result["fields"]["lookup_failed"] is True


def test_registry_lists_infra_intel_default_off():
    registry = ConnectorRegistry()
    for name in ("public_urlscan_domain_history",
                 "public_hackertarget_infra_lookup",
                 "public_ipapi_geolocation"):
        cap = registry.get(name)
        assert cap is not None, name
        assert cap.default_enabled is False, name
        assert cap.status == ConnectorStatus.EXPERIMENTAL, name
