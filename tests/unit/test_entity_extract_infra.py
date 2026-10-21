"""Tests for entity-association _extract handlers (infra lane).

Covers: dnsdumpster / commoncrawl / threatbook / hunter.
All fixtures are offline; adapters are never called.
"""

from core.entity_association import EntityAssociationEngine


def _eng():
    return EntityAssociationEngine()


# ---------------------------------------------------------------------------
# dnsdumpster
# ---------------------------------------------------------------------------

def test_dnsdumpster_extract_subdomains_and_ips():
    result = {
        "fields": {
            "subdomains": ["hr.example.com", "www.example.com"],
            "interesting_subdomains": [{"host": "hr.example.com", "label": "hr"}],
            "distinct_ips": ["93.184.216.34"],
            "subdomain_count": 2,
        }
    }
    ents = _eng()._extract("dnsdumpster", result)
    by_val = {e["value"]: e for e in ents}
    assert set(by_val) == {"hr.example.com", "www.example.com", "93.184.216.34"}
    hr = by_val["hr.example.com"]
    assert hr["type"] == "domain"
    assert hr["sources"] == ["dnsdumpster"]
    assert hr["context"]["from"] == "interesting_subdomain"
    assert hr["context"]["label"] == "hr"
    assert by_val["www.example.com"]["context"]["from"] == "dnsdumpster_subdomain"
    ip_e = by_val["93.184.216.34"]
    assert ip_e["type"] == "ip"
    assert ip_e["context"]["from"] == "dnsdumpster_ip"


def test_dnsdumpster_extract_missing_fields():
    assert _eng()._extract("dnsdumpster", {"fields": {}}) == []
    assert _eng()._extract("dnsdumpster", {}) == []
    assert _eng()._extract("dnsdumpster", {"fields": {"subdomains": None}}) == []


# ---------------------------------------------------------------------------
# commoncrawl
# ---------------------------------------------------------------------------

def test_commoncrawl_extract_dedup_hosts():
    result = {
        "fields": {
            "urls": [
                {"url": "https://hr.example.com/contact.html", "captured_at": "2024-01-02T00:00:00Z"},
                {"url": "http://hr.example.com/about.html", "captured_at": "2024-02-03T00:00:00Z"},
                {"url": "https://blog.example.com/post", "captured_at": "2024-03-04T00:00:00Z"},
            ],
            "url_count": 3,
        }
    }
    ents = _eng()._extract("commoncrawl", result)
    by_val = {e["value"]: e for e in ents}
    assert set(by_val) == {"hr.example.com", "blog.example.com"}
    hr = by_val["hr.example.com"]
    assert hr["type"] == "domain"
    assert hr["sources"] == ["commoncrawl"]
    assert hr["context"]["from"] == "cc_url"
    assert hr["context"]["captured_at"] == "2024-01-02T00:00:00Z"


def test_commoncrawl_extract_missing_fields():
    assert _eng()._extract("commoncrawl", {"fields": {}}) == []
    assert _eng()._extract("commoncrawl", {}) == []
    # malformed records skipped, not fatal
    ents = _eng()._extract(
        "commoncrawl",
        {"fields": {"urls": [{"url": "not-a-url"}, None, {"url": ""}]}},
    )
    assert ents == []


# ---------------------------------------------------------------------------
# threatbook
# ---------------------------------------------------------------------------

def test_threatbook_extract_current_ips():
    result = {
        "fields": {
            "severity": "info",
            "is_malicious": False,
            "scene": "IDC",
            "asn": {"number": "4134", "info": "CHINANET Guangdong"},
            "current_ips": ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"],
        }
    }
    ents = _eng()._extract("threatbook", result)
    assert len(ents) == 2
    for e in ents:
        assert e["type"] == "ip"
        assert e["sources"] == ["threatbook"]
        assert e["context"]["from"] == "threatbook_current_ip"
        assert e["context"]["asn_number"] == "4134"
        assert e["context"]["asn_info"] == "CHINANET Guangdong"
        assert e["context"]["severity"] == "info"
        assert e["context"]["is_malicious"] is False


def test_threatbook_extract_failure_paths():
    assert _eng()._extract("threatbook", {"fields": {"lookup_failed": True}}) == []
    assert _eng()._extract("threatbook", {"fields": {"no_data": True}}) == []
    assert _eng()._extract("threatbook", {"fields": {}}) == []
    assert _eng()._extract("threatbook", {}) == []
    # no ASN in payload: ips still extracted without asn context
    ents = _eng()._extract(
        "threatbook", {"fields": {"current_ips": ["1.2.3.4"]}}
    )
    assert len(ents) == 1
    assert "asn_number" not in ents[0]["context"]


# ---------------------------------------------------------------------------
# hunter
# ---------------------------------------------------------------------------

def test_hunter_extract_emails():
    result = {
        "fields": {
            "domain": "example.com",
            "emails": [
                {
                    "value": "John.Doe@Example.COM",
                    "first_name": "John",
                    "last_name": "Doe",
                    "position": "CTO",
                    "seniority": "executive",
                    "department": "engineering",
                },
                {"value": "info@example.com"},
            ],
            "email_count": 2,
        }
    }
    ents = _eng()._extract("hunter", result)
    by_val = {e["value"]: e for e in ents}
    assert set(by_val) == {"john.doe@example.com", "info@example.com"}
    lead = by_val["john.doe@example.com"]
    assert lead["type"] == "email"
    assert lead["sources"] == ["hunter"]
    assert lead["context"]["from"] == "hunter_email"
    assert lead["context"]["first_name"] == "John"
    assert lead["context"]["last_name"] == "Doe"
    assert lead["context"]["position"] == "CTO"
    # empty names/positions are not added to context
    info_ctx = by_val["info@example.com"]["context"]
    assert info_ctx == {"from": "hunter_email"}


def test_hunter_extract_missing_fields():
    assert _eng()._extract("hunter", {"fields": {"lookup_failed": True}}) == []
    assert _eng()._extract("hunter", {"fields": {}}) == []
    assert _eng()._extract("hunter", {}) == []
    # junk values skipped
    ents = _eng()._extract(
        "hunter", {"fields": {"emails": [{"value": "not-an-email"}, None]}}
    )
    assert ents == []


# ---------------------------------------------------------------------------
# end-to-end through associate() with stub adapters (no network)
# ---------------------------------------------------------------------------

class _StubAdapter:
    def __init__(self, fields):
        self._fields = fields

    def query(self, keyword, **params):
        return {"fields": self._fields}


def test_associate_domain_seed_uses_infra_extractors():
    eng = EntityAssociationEngine(
        dnsdumpster=_StubAdapter({
            "subdomains": ["hr.example.com"],
            "interesting_subdomains": [{"host": "hr.example.com", "label": "hr"}],
            "distinct_ips": ["93.184.216.34"],
        }),
        hunter=_StubAdapter({
            "emails": [{"value": "a@example.com", "first_name": "A",
                        "last_name": "B", "position": "CEO"}],
        }),
    )
    pkt = eng.associate({"type": "domain", "value": "example.com"}, max_depth=1)
    vals = {e["value"] for e in pkt["entities"]}
    assert "hr.example.com" in vals
    assert "93.184.216.34" in vals
    assert "a@example.com" in vals
