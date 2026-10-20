#!/usr/bin/env python3
"""Unit tests for core.intel_enrichment (domain + person enrichment).

All adapters are stubbed with simple fake classes; no network access.
"""

from __future__ import annotations

from core.intel_enrichment import enrich_domain, enrich_person
from core.people_intel import PeopleIntelOrchestrator, PersonQuery


class _FakeUrlScan:
    def query(self, domain, **kwargs):
        assert domain == "example.com"
        return {"fields": {"total_scans": 5,
                           "recent_scans": [{"scanned_url": "https://example.com/"}]}}


class _FakeHackertarget:
    def __init__(self, neighbors=30):
        self._neighbors = neighbors

    def query(self, target, **kwargs):
        assert kwargs.get("endpoints") == ["dnslookup", "reverseiplookup"]
        return {"fields": {
            "dnslookup": {"record_types": ["A", "MX"],
                          "records": {"A": ["93.184.216.34"], "MX": ["0 mail.example.com."]}},
            "reverseiplookup": {"neighbor_count": self._neighbors,
                                "neighbors": [f"n{i}.example" for i in range(self._neighbors)]},
        }}


class _FakeIpApi:
    def __init__(self):
        self.seen_ips = []

    def query(self, ip, **kwargs):
        self.seen_ips.append(ip)
        return {"fields": {"ip": ip, "country": "United States",
                           "org": "Example Org", "asn": "AS1234",
                           "is_hosting": True, "is_proxy": False}}


class _Boom:
    def query(self, *args, **kwargs):
        raise RuntimeError("network down")


def test_enrich_domain_aggregates_three_sources():
    ipapi = _FakeIpApi()
    result = enrich_domain("Example.COM", urlscan=_FakeUrlScan(),
                           hackertarget=_FakeHackertarget(), ipapi=ipapi)
    assert result["type"] == "domain_intel_enrichment"
    assert result["domain"] == "example.com"  # normalized
    assert result["source_count"] == 3
    assert set(result["sources"]) == {"urlscan", "hackertarget", "ipapi"}
    # cross-source: A record fed into ip-api
    assert ipapi.seen_ips == ["93.184.216.34"]
    notes = result["risk_notes"]
    assert "服务器位于托管机房" in notes
    assert "同 IP 存在 30 个邻居域名，共享主机" in notes
    assert not any("无公开扫描记录" in n for n in notes)  # total_scans=5


def test_enrich_domain_zero_scans_note():
    class _EmptyScan:
        def query(self, domain, **kwargs):
            return {"fields": {"total_scans": 0, "recent_scans": []}}

    result = enrich_domain("new.example", urlscan=_EmptyScan())
    assert result["source_count"] == 1
    assert "无公开扫描记录，互联网可见度低" in result["risk_notes"]


def test_enrich_domain_failing_adapter_degrades():
    result = enrich_domain("example.com", urlscan=_Boom(),
                           hackertarget=_FakeHackertarget(),
                           ipapi=_FakeIpApi())
    assert result["source_count"] == 3
    assert "network down" in result["sources"]["urlscan"]["error"]
    # other sources still ran
    assert result["sources"]["hackertarget"]["fields"]["dnslookup"]["record_types"] == ["A", "MX"]
    assert result["sources"]["ipapi"]["fields"]["is_hosting"] is True


def test_enrich_domain_no_adapters():
    result = enrich_domain("example.com")
    assert result["type"] == "domain_intel_enrichment"
    assert result["source_count"] == 0
    assert result["sources"] == {}
    assert result["risk_notes"] == []


def test_enrich_person_delegates_to_orchestrator():
    class _FakeEmail:
        def query(self, email):
            return {"fields": {"domain": "example.com", "syntax_valid": True,
                               "is_disposable": False, "is_role_account": False}}

    orch = PeopleIntelOrchestrator(email_adapter=_FakeEmail())
    result = enrich_person(PersonQuery(email="a@example.com"), orchestrator=orch)
    assert result["type"] == "people_lead_graph"
    assert result["source_count"] == 1
    assert "email_intel" in result["sources"]


def test_enrich_person_builds_orchestrator_from_adapters():
    class _FakeEmail:
        def query(self, email):
            return {"fields": {"domain": "example.com", "syntax_valid": True}}

    result = enrich_person({"email": "a@example.com"},
                           email_adapter=_FakeEmail(),
                           unknown_adapter=object())  # unknown kwargs ignored
    assert result["type"] == "people_lead_graph"
    assert result["source_count"] == 1


def test_enrich_person_empty_adapters():
    result = enrich_person(PersonQuery(email="a@example.com"))
    assert result["type"] == "people_lead_graph"
    assert result["source_count"] == 0
    assert result["sources"] == {}
    assert "默认关闭" in result["note"]


def test_enrich_person_failing_adapter_degrades():
    orch = PeopleIntelOrchestrator(email_adapter=_Boom())
    result = enrich_person(PersonQuery(email="a@example.com"), orchestrator=orch)
    assert result["source_count"] == 1
    assert "network down" in result["sources"]["email_intel"]["error"]
