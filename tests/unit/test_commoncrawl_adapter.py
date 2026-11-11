"""Unit tests for CommonCrawlLookup (Common Crawl CDX index adapter)."""
import pytest
from adapters.commoncrawl_adapter import CommonCrawlLookup


SAMPLE_CDX = """\
{"urlkey": "com,example)/contact.html", "timestamp": "20240115120000", "url": "https://example.com/contact.html", "mime": "text/html", "mime-detected": "text/html", "status": "200", "digest": "ABC123", "length": "1234", "offset": "5678", "filename": "crawl-data/CC-MAIN-2024-10/segments/123/warc/file.warc.gz", "languages": "eng", "recordid": "rec-1", "encoding": "utf-8"}
{"urlkey": "com,example)/about", "timestamp": "20230601093000", "url": "https://example.com/about", "mime": "text/html", "status": "200", "digest": "DEF456", "length": "999", "offset": "111", "filename": "crawl-data/CC-MAIN-2023-14/segments/456/warc/f2.warc.gz", "languages": "zho,eng"}
{"urlkey": "com,example)/old.pdf", "timestamp": "20200101000000", "url": "http://example.com/old.pdf", "mime": "application/pdf", "status": "404", "digest": "GHI789", "length": "10", "offset": "20", "filename": "x.warc.gz"}
not-json-line
"""


def _adapter(**overrides):
    a = CommonCrawlLookup(**overrides)
    a._robots_checker = lambda *args: True
    return a


# ------------------------------------------------------------------
# Domain normalization
# ------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("example.com", "example.com"),
    ("https://example.com/", "example.com"),
    ("http://www.example.com/path?q=1", "example.com"),
    ("WWW.EXAMPLE.COM:8080/x", "example.com"),
    ("  sub.example.com  ", "sub.example.com"),
])
def test_normalize_domain(raw, expected):
    assert CommonCrawlLookup._normalize_domain(raw) == expected


# ------------------------------------------------------------------
# CDX parsing
# ------------------------------------------------------------------

def test_parse_cdx_lines_basic():
    records = CommonCrawlLookup.parse_cdx_lines(SAMPLE_CDX)
    assert len(records) == 3  # non-JSON line skipped
    first = records[0]
    assert first["url"] == "https://example.com/contact.html"
    assert first["captured_at"] == "2024-01-15T12:00:00Z"
    assert first["captured_at_raw"] == "20240115120000"
    assert first["status"] == "200"
    assert first["mime"] == "text/html"
    assert first["digest"] == "ABC123"
    assert first["warc_file"] == "crawl-data/CC-MAIN-2024-10/segments/123/warc/file.warc.gz"
    assert first["warc_offset"] == "5678"
    assert first["languages"] == "eng"


def test_parse_cdx_lines_mime_detected_fallback():
    records = CommonCrawlLookup.parse_cdx_lines(
        '{"url": "https://x.com/", "timestamp": "20220101000000", "status": "200", "mime-detected": "text/html"}'
    )
    assert records[0]["mime"] == "text/html"


def test_parse_cdx_lines_empty_and_garbage():
    assert CommonCrawlLookup.parse_cdx_lines("") == []
    assert CommonCrawlLookup.parse_cdx_lines("<html>504 Gateway</html>") == []


def test_format_timestamp():
    assert CommonCrawlLookup._format_timestamp("20260904131850") == "2026-09-04T13:18:50Z"
    assert CommonCrawlLookup._format_timestamp("bad") == "bad"
    assert CommonCrawlLookup._format_timestamp("") == ""


# ------------------------------------------------------------------
# URL building
# ------------------------------------------------------------------

def test_build_url_structure():
    a = _adapter()
    # stub index discovery to avoid network
    a._discover_latest_index = lambda: "CC-MAIN-2026-39"
    url = a._build_url("https://www.example.com/")
    assert "index.commoncrawl.org/CC-MAIN-2026-39-index?" in url
    assert "url=example.com" in url
    assert "matchType=domain" in url
    assert "output=json" in url
    assert "collapse=urlkey" in url
    assert "filter=status%3A200" in url or "filter=status:200" in url.replace("%3A", ":")


def test_build_url_respects_params():
    a = _adapter()
    url = a._build_url("example.com", index="CC-MAIN-2024-10", limit=50, **{"from": "2020", "to": "2024"})
    assert "CC-MAIN-2024-10-index" in url
    assert "limit=50" in url
    assert "from=2020" in url
    assert "to=2024" in url


# ------------------------------------------------------------------
# query() end-to-end with stubbed transport
# ------------------------------------------------------------------

def _stub_execute(url, headers):
    return (200, SAMPLE_CDX, "")


def test_query_success():
    a = _adapter(execute_query=_stub_execute)
    a._discover_latest_index = lambda: "CC-MAIN-2026-39"
    result = a.query("example.com")
    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["url_count"] == 3
    assert len(fields["urls"]) == 3
    assert fields["index_used"] == "CC-MAIN-2026-39"
    assert "query_subject_hash" in result
    # audit logged, no raw query in the clear beyond hash
    assert len(a.audit.get_trail()) == 1


def test_query_empty_domain_rejected_gracefully():
    a = _adapter(execute_query=lambda u, h: (200, "", ""))
    a._discover_latest_index = lambda: "CC-MAIN-2026-39"
    result = a.query("example.com")
    # base class returns empty fields dict when raw body is empty
    assert result["fields"] == {}
    assert result["response_status"] == 200


def test_retry_exhaustion_returns_service_unavailable():
    import urllib.request
    calls = {"n": 0}

    def always_fail(url_or_req, **kwargs):
        calls["n"] += 1
        url = url_or_req.full_url if hasattr(url_or_req, "full_url") else str(url_or_req)
        raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)

    # patch urlopen via override path: use real _execute_query with monkeypatched urlopen
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = always_fail
    try:
        a = _adapter()
        # avoid real index discovery network call
        a._discover_latest_index = lambda: "CC-MAIN-2026-39"
        # avoid real sleep in retries
        a._sleeper = lambda s: None
        import adapters.commoncrawl_adapter as mod
        real_sleep = mod.time.sleep
        mod.time.sleep = lambda s: None
        try:
            status, raw, err = a._execute_query("https://index.commoncrawl.org/x", {})
        finally:
            mod.time.sleep = real_sleep
    finally:
        urllib.request.urlopen = real_urlopen
    assert status == 0
    assert raw is None
    assert "cdx_unavailable_after_4_retries" in err
    assert calls["n"] == 4


def test_retry_succeeds_on_second_attempt():
    import urllib.request

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"url": "https://example.com/", "timestamp": "20240101000000", "status": "200"}'

    calls = {"n": 0}

    def flaky(url_or_req, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            url = url_or_req.full_url if hasattr(url_or_req, "full_url") else str(url_or_req)
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)
        return FakeResp()

    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = flaky
    import adapters.commoncrawl_adapter as mod
    real_sleep = mod.time.sleep
    mod.time.sleep = lambda s: None
    try:
        a = _adapter()
        status, raw, err = a._execute_query("https://index.commoncrawl.org/x", {})
    finally:
        urllib.request.urlopen = real_urlopen
        mod.time.sleep = real_sleep
    assert status == 200
    assert err == ""
    assert raw.startswith("{")
    assert calls["n"] == 2


def test_robots_disallowed_returns_empty():
    a = CommonCrawlLookup()
    a._robots_checker = lambda *args: False
    result = a.query("example.com")
    assert result["fields"] == {} or result.get("error")


def test_audit_record_has_no_raw_query():
    a = _adapter(execute_query=_stub_execute)
    a._discover_latest_index = lambda: "CC-MAIN-2026-39"
    a.query("example.com")
    trail = a.audit.get_trail()
    assert len(trail) == 1
    rec = trail[0]
    assert rec["source_domain"] == "index.commoncrawl.org"
    assert rec["data_boundary"] == "fully_public"
    assert "example.com" not in json_dumps(rec)


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)
