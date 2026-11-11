#!/usr/bin/env python3
"""Tests for adapters/fofa_adapter.py."""
import base64
import json

from adapters.fofa_adapter import FofaLookup


def _make_adapter():
    return FofaLookup(email="test@example.com", api_key="deadbeef")


def test_no_credentials_returns_credentials_required():
    a = FofaLookup()
    r = a.query('domain="example.com"')
    assert "credentials_required" in r["error"]


def test_no_credentials_domain_helper():
    a = FofaLookup()
    r = a.query_domain("example.com")
    assert "credentials_required" in r["error"]


def test_qbase64_encoding():
    a = _make_adapter()
    q = 'domain="example.com"'
    assert a._encode_query(q) == base64.b64encode(q.encode()).decode()


def test_build_url_contains_params():
    a = _make_adapter()
    url = a._build_url('domain="example.com"')
    assert "fofa.info/api/v1/search/all" in url
    assert "qbase64=" in url
    assert "fields=" in url


def _decode_qbase64(url: str) -> str:
    import urllib.parse
    part = url.split("qbase64=")[1].split("&")[0]
    return base64.b64decode(urllib.parse.unquote(part)).decode()


def _fake_results():
    # fields: host,ip,port,protocol,title,icp,domain,cert,country,city,server
    return {
        "error": False,
        "size": 2,
        "results": [
            ["www.example.com", "93.184.216.34", 443, "https",
             "Example Domain", "京ICP备12345678号-1", "example.com",
             "example.com", "US", "", "nginx"],
            ["blog.example.com", "93.184.216.34", 80, "http",
             "Blog", "京ICP备12345678号-1", "example.com",
             "", "US", "", "nginx"],
        ],
    }


def test_extract_public_fields(monkeypatch):
    a = _make_adapter()
    monkeypatch.setattr(
        a, "_execute_query",
        lambda url, headers: (200, json.dumps(_fake_results()), ""),
    )
    r = a.query('domain="example.com"')
    f = r["fields"]
    assert f["asset_count"] == 2
    assert f["unique_ips"] == ["93.184.216.34"]
    assert "example.com" in f["unique_domains"]
    assert f["icp_numbers"] == ["京ICP备12345678号-1"]
    assert f["assets"][0]["title"] == "Example Domain"


def test_extract_error_response(monkeypatch):
    a = _make_adapter()
    monkeypatch.setattr(
        a, "_execute_query",
        lambda url, headers: (200, json.dumps({"error": True, "errmsg": "[-700] 账号无效"}), ""),
    )
    r = a.query('domain="example.com"')
    assert r["fields"]["lookup_failed"] is True
    assert "账号无效" in r["fields"]["reason"]


def test_extract_parse_error(monkeypatch):
    a = _make_adapter()
    monkeypatch.setattr(
        a, "_execute_query",
        lambda url, headers: (200, "not-json{{{", ""),
    )
    r = a.query('domain="example.com"')
    assert r["fields"]["parse_error"] is True


def test_query_ip_builds_ip_query(monkeypatch):
    a = _make_adapter()
    seen = {}

    def fake_exec(url, headers):
        seen["url"] = url
        return (200, json.dumps({"error": False, "size": 0, "results": []}), "")

    monkeypatch.setattr(a, "_execute_query", fake_exec)
    a.query_ip("1.2.3.4")
    assert _decode_qbase64(seen["url"]) == 'ip="1.2.3.4"'


def test_query_icp_builds_icp_query(monkeypatch):
    a = _make_adapter()
    seen = {}

    def fake_exec(url, headers):
        seen["url"] = url
        return (200, json.dumps({"error": False, "size": 0, "results": []}), "")

    monkeypatch.setattr(a, "_execute_query", fake_exec)
    a.query_icp("京ICP备12345678号-1")
    assert _decode_qbase64(seen["url"]) == 'icp="京ICP备12345678号-1"'


def test_empty_inputs():
    a = _make_adapter()
    assert "empty_domain" in json.dumps(a.query_domain(""), ensure_ascii=False)
    assert "empty_ip" in json.dumps(a.query_ip("  "), ensure_ascii=False)
    assert "empty_icp" in json.dumps(a.query_icp(None), ensure_ascii=False)


def test_audit_does_not_contain_key(monkeypatch):
    a = _make_adapter()
    monkeypatch.setattr(
        a, "_execute_query",
        lambda url, headers: (200, json.dumps({"error": False, "size": 0, "results": []}), ""),
    )
    a.query('domain="example.com"')
    trail = json.dumps(a.audit.get_trail(), ensure_ascii=False)
    assert "deadbeef" not in trail
