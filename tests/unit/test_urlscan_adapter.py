"""Tests for urlscan.io public archive adapter (offline fixtures)."""

import json

from adapters.urlscan_adapter import UrlscanLookup

FIXTURE_SEARCH = json.dumps({
    "total": 2,
    "results": [
        {
            "task": {"uuid": "abc-123", "time": "2026-10-01T00:00:00.000Z",
                     "visibility": "public", "method": "api"},
            "page": {"url": "https://sub.example.com/login", "domain": "sub.example.com",
                     "apexDomain": "example.com", "ip": "93.184.216.34",
                     "country": "US", "city": "Norwell", "server": "ECS",
                     "mimeType": "text/html", "status": "200",
                     "technologies": ["nginx", "jQuery"]},
        },
        {
            "task": {"uuid": "def-456", "time": "2026-09-01T00:00:00.000Z",
                     "visibility": "public", "method": "manual"},
            "page": {"url": "http://example.com/", "domain": "example.com",
                     "apexDomain": "example.com", "ip": "93.184.216.34",
                     "country": "US", "server": "ECS",
                     "technologies": []},
        },
    ],
})

FIXTURE_ERROR = json.dumps({"message": "Search query invalid"})


def _adapter(body, status=200):
    return UrlscanLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_domain_query():
    a = _adapter("")
    url = a._build_url("example.com")
    assert "q=domain%3Aexample.com" in url and "size=10" in url


def test_build_url_ip_query():
    a = _adapter("")
    url = a._build_url("93.184.216.34")
    assert "q=ip%3A93.184.216.34" in url


def test_build_url_raw_and_size_clamp():
    a = _adapter("")
    assert "q=page.url%3A%22x%22" in a._build_url('page.url:"x"', search_type="raw", size=500)
    assert "size=100" in a._build_url("example.com", size=500)
    assert "size=10" in a._build_url("example.com", size="junk")


def test_extract_parses_scans_and_dedupes_ips():
    a = _adapter(FIXTURE_SEARCH)
    out = a.query("example.com")
    f = out["fields"]
    assert f["total"] == 2 and f["returned"] == 2
    assert f["scans"][0]["scan_url"] == "https://urlscan.io/result/abc-123/"
    assert f["scans"][0]["technologies"] == ["nginx", "jQuery"]
    assert f["observed_ips"] == ["93.184.216.34"]
    assert "未出现≠该资产不存在" in f["data_note"]


def test_extract_handles_api_error_message():
    a = _adapter(FIXTURE_ERROR)
    out = a.query("example.com")
    assert out["fields"]["lookup_failed"] is True


def test_extract_handles_garbage():
    a = _adapter("not json{{{")
    assert a.query("example.com")["fields"]["parse_error"] is True


def test_parse_search_results_static_entry():
    scans = UrlscanLookup.parse_search_results(FIXTURE_SEARCH)
    assert len(scans) == 2 and scans[1]["domain"] == "example.com"
