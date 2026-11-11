#!/usr/bin/env python3
"""Tests for adapters/threatbook_adapter.py."""
import json

from adapters.threatbook_adapter import ThreatBookLookup


def _make_adapter():
    return ThreatBookLookup(api_key="deadbeef")


def test_no_credentials_returns_credentials_required():
    t = ThreatBookLookup()
    r = t.query_ip("8.8.8.8")
    assert "credentials_required" in r["error"]


def test_no_credentials_domain_helper():
    t = ThreatBookLookup()
    r = t.query_domain("example.com")
    assert "credentials_required" in r["error"]


def test_ip_url_points_at_reputation_endpoint():
    t = _make_adapter()
    url = t._build_url("8.8.8.8", kind="ip")
    assert "api.threatbook.cn/v3/scene/ip_reputation" in url
    assert "resource=8.8.8.8" in url
    assert "lang=zh" in url


def test_domain_url_points_at_dns_endpoint():
    t = _make_adapter()
    url = t._build_url("example.com", kind="domain")
    assert "api.threatbook.cn/v3/scene/dns" in url
    assert "resource=example.com" in url


def test_query_auto_detects_ip_vs_domain(monkeypatch):
    t = _make_adapter()
    seen = {}

    def fake_exec(url, headers):
        seen["url"] = url
        return (200, json.dumps({"response_code": 0, "verbose_msg": "Success", "data": {}}), "")

    monkeypatch.setattr(t, "_execute_query", fake_exec)
    t.query("1.2.3.4")
    assert "ip_reputation" in seen["url"]
    t.query("example.com")
    assert "/dns?" in seen["url"]


def _fake_ip_reputation():
    return {
        "response_code": 0,
        "verbose_msg": "Success",
        "data": {
            "1.2.3.4": {
                "severity": "high",
                "judgments": ["C2", "僵尸网络"],
                "tags_classes": ["APT-团伙"],
                "basic": {
                    "carrier": "电信",
                    "location": {
                        "country": "中国", "province": "广东", "city": "深圳",
                        "lng": "114.05", "lat": "22.54", "country_code": "CN",
                    },
                },
                "asn": {"rank": "", "info": "CHINANET Guangdong", "number": "4134"},
                "scene": "IDC",
                "confidence_level": "高",
                "is_malicious": True,
                "update_time": "2026-10-21 10:00:00",
            }
        },
    }


def test_extract_ip_reputation_fields(monkeypatch):
    t = _make_adapter()
    monkeypatch.setattr(
        t, "_execute_query",
        lambda url, headers: (200, json.dumps(_fake_ip_reputation()), ""),
    )
    r = t.query_ip("1.2.3.4")
    f = r["fields"]
    assert f["severity"] == "high"
    assert f["is_malicious"] is True
    assert f["judgments"] == ["C2", "僵尸网络"]
    assert f["scene"] == "IDC"
    assert f["location"]["city"] == "深圳"
    assert f["asn"]["number"] == "4134"
    assert f["carrier"] == "电信"


def _fake_dns():
    return {
        "response_code": 0,
        "verbose_msg": "Success",
        "data": {
            "example.com": {
                "severity": "info",
                "judgments": [],
                "is_malicious": False,
                "scene": "",
                "confidence_level": "高",
                "cur_ips": [{"ip": "93.184.216.34"}, {"ip": "2606:2800:220:1:248:1893:25c8:1946"}],
                "cur_whois": {"registrar_name": "Example Registrar", "cdate": "1995-08-14"},
                "cas": [{"subject": "CN=example.com"}],
                "categories": ["企业官网"],
                "update_time": "2026-10-21 10:00:00",
            }
        },
    }


def test_extract_dns_fields(monkeypatch):
    t = _make_adapter()
    monkeypatch.setattr(
        t, "_execute_query",
        lambda url, headers: (200, json.dumps(_fake_dns()), ""),
    )
    r = t.query_domain("example.com")
    f = r["fields"]
    assert f["is_malicious"] is False
    assert f["current_ips"] == ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]
    assert f["current_ip_count"] == 2
    assert f["whois_registrar"] == "Example Registrar"
    assert f["whois_create"] == "1995-08-14"
    assert f["cert_subject"] == "CN=example.com"
    assert f["categories"] == ["企业官网"]


def test_invalid_api_key_response(monkeypatch):
    t = _make_adapter()
    monkeypatch.setattr(
        t, "_execute_query",
        lambda url, headers: (
            200, json.dumps({"response_code": -1, "verbose_msg": "无效的API key"}), ""),
    )
    r = t.query_ip("8.8.8.8")
    assert r["fields"]["lookup_failed"] is True
    assert "无效的API key" in r["fields"]["reason"]


def test_extract_parse_error(monkeypatch):
    t = _make_adapter()
    monkeypatch.setattr(
        t, "_execute_query",
        lambda url, headers: (200, "not-json{{{", ""),
    )
    r = t.query_ip("8.8.8.8")
    assert r["fields"]["parse_error"] is True


def test_empty_inputs():
    t = _make_adapter()
    assert "empty_ip" in json.dumps(t.query_ip(""), ensure_ascii=False)
    assert "empty_domain" in json.dumps(t.query_domain("  "), ensure_ascii=False)


def test_audit_does_not_contain_key(monkeypatch):
    t = _make_adapter()
    monkeypatch.setattr(
        t, "_execute_query",
        lambda url, headers: (200, json.dumps(_fake_ip_reputation()), ""),
    )
    t.query_ip("8.8.8.8")
    trail = json.dumps(t.audit.get_trail(), ensure_ascii=False)
    assert "deadbeef" not in trail
