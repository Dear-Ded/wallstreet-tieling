"""Tests for KuaishouVideoLookup adapter (stubbed, no network)."""
from adapters.kuaishou_adapter import KuaishouVideoLookup


SAMPLE_HTML = '''
<html><head><title>test</title></head><body>
<script>window.__APOLLO_STATE__ = {
"photoId":"3xabc123",
"caption":"\\u6d4b\\u8bd5\\u5e97\\u94fa\\u63a2\\u5e97",
"userName":"TestUser",
"userId":987654321,
"likeCount":15200,
"commentCount":340,
"viewCount":89000,
"location":"\\u90d1\\u5dde\\u5e02"
};</script>
</body></html>
'''


def test_parse_share_page():
    a = KuaishouVideoLookup()
    out = a.parse_share_page(SAMPLE_HTML)
    assert out["photo_id"] == "3xabc123"
    assert out["author"] == "TestUser"
    assert out["author_id"] == "987654321"
    assert out["like_count"] == 15200
    assert out["view_count"] == 89000


def test_parse_empty():
    a = KuaishouVideoLookup()
    assert a.parse_share_page("<html></html>") == {}


def test_query_share_url_dispatch(monkeypatch):
    a = KuaishouVideoLookup()
    a._rate_limit = lambda: None
    a._check_robots = lambda: True
    # audit skipped

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return SAMPLE_HTML.encode()
        def geturl(self): return "https://www.kuaishou.com/short-video/3xabc123"
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=20: FakeResp())
    out = a.query("https://v.kuaishou.com/abc123")
    assert out["status"] == "ok"
    assert out["video"]["photo_id"] == "3xabc123"


def test_query_name_search_interaction_required():
    a = KuaishouVideoLookup()
    out = a.query("沙县小吃")
    assert out["status"] == "interaction_required"


def test_invalid_input():
    a = KuaishouVideoLookup()
    out = a.query_by_share_url("https://example.com/notvideo")
    assert out["status"] == "invalid_input"


def test_no_credentials():
    a = KuaishouVideoLookup()
    assert a.requires_credentials is False
    assert a.data_boundary == "fully_public"
