"""Tests for Analytics ID pivot adapter."""
import pytest
from adapters.analytics_pivot_adapter import AnalyticsPivotLookup


SAMPLE_HTML = """
<html><head>
<script src="https://hm.baidu.com/hm.js?abcdef1234567890abcdef1234567890"></script>
<script>
var _hmt = _hmt || [];
_hmt.push(['_setAccount', 'abcdef1234567890abcdef1234567890']);
</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABCDEF1234"></script>
<script>
gtag('config', 'UA-12345678-1');
</script>
<script src="https://s4.cnzz.com/z_stat.php?id=98765432&web_id=98765432"></script>
<script src="https://js.users.51.la/11223344.js"></script>
</head><body>hello</body></html>
"""

SAMPLE_URLSCAN_JSON = """{
  "total": 3,
  "results": [
    {"task": {"url": "https://shop-a.example.com/", "time": "2026-01-01T00:00:00Z"},
     "page": {"title": "Shop A", "country": "CN"}},
    {"task": {"url": "https://shop-b.example.com/item", "time": "2026-02-01T00:00:00Z"},
     "page": {"title": "Shop B", "country": "CN"}},
    {"task": {"url": "https://shop-a.example.com/about", "time": "2026-03-01T00:00:00Z"},
     "page": {"title": "Shop A About", "country": "CN"}}
  ]
}"""


def test_extract_baidu_tongji():
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert "baidu_tongji" in ids
    assert "abcdef1234567890abcdef1234567890" in ids["baidu_tongji"]


def test_extract_google_ua():
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert "google_ua" in ids
    assert "UA-12345678-1" in ids["google_ua"]


def test_extract_google_ga4():
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert "google_ga4" in ids
    assert "G-ABCDEF1234" in ids["google_ga4"]


def test_extract_cnzz():
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert "cnzz" in ids
    assert "98765432" in ids["cnzz"]


def test_extract_51la():
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert "la51" in ids
    assert "11223344" in ids["la51"]


def test_extract_dedupes():
    # hm.js 和 _hmt push 是同一个 ID，应去重
    ids = AnalyticsPivotLookup.extract_ids_from_html(SAMPLE_HTML)
    assert ids["baidu_tongji"].count("abcdef1234567890abcdef1234567890") == 1


def test_extract_empty_html():
    assert AnalyticsPivotLookup.extract_ids_from_html("") == {}
    assert AnalyticsPivotLookup.extract_ids_from_html("<html></html>") == {}


def test_parse_pivot_response_dedupes_domains():
    adapter = AnalyticsPivotLookup.__new__(AnalyticsPivotLookup)
    out = AnalyticsPivotLookup._parse_pivot_response(adapter, SAMPLE_URLSCAN_JSON)
    assert out["total_scans"] == 3
    # shop-a 出现两次，应去重为 2 个域名
    assert out["related_domain_count"] == 2
    hosts = {d["domain"] for d in out["related_domains"]}
    assert hosts == {"shop-a.example.com", "shop-b.example.com"}


def test_parse_pivot_response_bad_json():
    adapter = AnalyticsPivotLookup.__new__(AnalyticsPivotLookup)
    out = AnalyticsPivotLookup._parse_pivot_response(adapter, "not json")
    assert out.get("parse_error") is True
    assert out["related_domains"] == []


def test_build_url_extract_mode_adds_scheme():
    a = AnalyticsPivotLookup.__new__(AnalyticsPivotLookup)
    url = AnalyticsPivotLookup._build_url(a, "example.com", mode="extract")
    assert url == "https://example.com"


def test_build_url_pivot_mode():
    a = AnalyticsPivotLookup.__new__(AnalyticsPivotLookup)
    url = AnalyticsPivotLookup._build_url(a, "UA-12345678-1", mode="pivot", size=5)
    assert "urlscan.io/api/v1/search" in url
    assert "UA-12345678-1" in url
    assert "size=5" in url


def test_query_subject_hash_not_leak_id():
    # 审计只存 query 的 sha256，不存原始 ID
    import hashlib
    h = hashlib.sha256("UA-12345678-1".encode()).hexdigest()[:12]
    assert len(h) == 12
    assert "UA-12345678-1" not in h
