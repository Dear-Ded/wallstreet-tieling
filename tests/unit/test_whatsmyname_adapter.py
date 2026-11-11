"""WhatsMyName adapter tests."""

import json
import os
import pytest

from adapters.whatsmyname_adapter import WhatsMyNameLookup, CHINESE_SITES


@pytest.fixture
def adapter():
    return WhatsMyNameLookup(
        execute_query=lambda url, headers: (200, "", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_load_sites_includes_wmn_data(adapter):
    sites = adapter._load_sites()
    assert len(sites) >= 692, f"Expected 692+ sites, got {len(sites)}"


def test_chinese_sites_added(adapter):
    sites = adapter._load_sites()
    names = {s["name"].lower() for s in sites}
    assert "douban" in names


def test_chinese_sites_have_required_fields():
    for cs in CHINESE_SITES:
        assert "name" in cs
        assert "uri_check" in cs
        assert "{account}" in cs["uri_check"]


def test_check_site_search_based_returns_none():
    a = WhatsMyNameLookup(
        robots_checker=lambda d, u: True, sleeper=lambda s: None
    )
    site = {
        "name": "TestSearch",
        "uri_check": "https://example.com/search/{account}",
        "search_based": True,
    }
    result = a.check_site(site, "testuser")
    assert result["found"] is None
    assert "testuser" in result["url"]


def test_check_site_detects_found_via_e_string():
    def fake_execute(url, headers):
        return (200, "<html>welcome testuser profile page</html>", "")

    a = WhatsMyNameLookup(
        execute_query=fake_execute,
        robots_checker=lambda d, u: True,
        sleeper=lambda s: None,
    )
    # check_site uses urllib directly, so we monkeypatch at a different level
    # Instead test the logic via a mock
    import adapters.whatsmyname_adapter as mod

    site = {
        "name": "TestSite",
        "uri_check": "https://example.com/{account}",
        "e_code": 200,
        "e_string": "welcome testuser",
        "m_code": 404,
        "m_string": "not found",
    }
    # Patch urllib in the adapter module's check_site by replacing _execute path
    # check_site uses urllib.request directly; simulate via monkeypatching
    import urllib.request

    class FakeResp:
        status = 200

        def read(self):
            return b"<html>welcome testuser profile page</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    orig = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=15: FakeResp()
    try:
        result = a.check_site(site, "testuser")
    finally:
        urllib.request.urlopen = orig
    assert result["found"] is True


def test_check_site_detects_missing_via_m_string():
    import urllib.request

    a = WhatsMyNameLookup(
        robots_checker=lambda d, u: True, sleeper=lambda s: None
    )
    site = {
        "name": "TestSite",
        "uri_check": "https://example.com/{account}",
        "e_code": 200,
        "e_string": "profile of",
        "m_code": 404,
        "m_string": "user not found",
    }

    class FakeResp:
        status = 404

        def read(self):
            return b"<html>user not found</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    orig = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=15: FakeResp()
    try:
        result = a.check_site(site, "nouser")
    finally:
        urllib.request.urlopen = orig
    assert result["found"] is False


def test_query_empty_username(adapter):
    result = adapter.query("")
    assert result["error"] == "empty_username"
    assert result["found_count"] == 0


def test_query_returns_structure():
    # Use a tiny site list to keep test fast
    a = WhatsMyNameLookup(
        robots_checker=lambda d, u: True, sleeper=lambda s: None
    )
    a._sites = [
        {
            "name": "TestSearchOnly",
            "uri_check": "https://example.com/s/{account}",
            "search_based": True,
            "cat": "social",
        }
    ]
    result = a.query("someuser", max_sites=5, workers=2)
    assert result["sites_checked"] == 1
    assert result["found_count"] == 0
    assert len(result["needs_review"]) == 1
    assert "query_subject_hash" in result
    # username itself is the query input, not PII to redact
    assert result["username"] == "someuser"


def test_audit_trail_no_plaintext_leak():
    a = WhatsMyNameLookup(
        robots_checker=lambda d, u: True, sleeper=lambda s: None
    )
    a._sites = []
    a.query("secretuser123", max_sites=0)
    trail = a.audit.get_trail()
    assert len(trail) >= 1
    for record in trail:
        assert "secretuser123" not in json.dumps(record), "Plaintext username leaked in audit"


def test_wmn_data_license_attribution():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "adapters", "_vendor",
        "whatsmyname", "wmn-data.json",
    )
    assert os.path.exists(path), "wmn-data.json must be bundled"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "license" in data
    license_text = " ".join(data["license"])
    assert "Creative Commons" in license_text or "CC" in license_text


def test_douban_entry_format():
    douban = next((s for s in CHINESE_SITES if s["name"] == "Douban"), None)
    assert douban is not None
    assert douban["m_code"] == 404
    assert "{account}" in douban["uri_check"]
