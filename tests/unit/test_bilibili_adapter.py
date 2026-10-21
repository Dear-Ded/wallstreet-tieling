"""Tests for BilibiliVideoSearch adapter (stubbed, no network)."""
import json
from adapters.bilibili_adapter import BilibiliVideoSearch


SAMPLE_API_RESPONSE = {
    "code": 0,
    "message": "OK",
    "data": {
        "page": 1,
        "numResults": 2,
        "result": [
            {
                "type": "video",
                "author": "探店小王",
                "mid": 12345678,
                "bvid": "BV1xx411c7mD",
                "title": "【探店】海底捞中关村店实测",
                "play": 152000,
                "danmaku": 1200,
                "duration": "12:34",
                "pubdate": 1729000000,
                "description": "今天来探这家海底捞",
            },
            {
                "type": "video",
                "author": "美食侦探",
                "mid": 87654321,
                "bvid": "BV1yy411c7mE",
                "title": "人均50的宝藏小店",
                "play": 88000,
                "danmaku": 500,
                "duration": "8:20",
                "pubdate": 1728900000,
                "description": "",
            },
        ],
    },
}


def _stub_urlopen(monkeypatch, payload):
    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return payload.encode("utf-8")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=20: FakeResp())


def _no_side_effects(a):
    a._rate_limit = lambda: None
    a._check_robots = lambda: True
    # audit skipped
    return a


def test_search_extracts_videos(monkeypatch):
    _stub_urlopen(monkeypatch, json.dumps(SAMPLE_API_RESPONSE))
    a = _no_side_effects(BilibiliVideoSearch())
    out = a.query("海底捞 探店")
    assert out["status"] == "ok"
    assert out["video_count"] == 2
    v = out["videos"][0]
    assert v["bvid"] == "BV1xx411c7mD"
    assert v["author"] == "探店小王"
    assert v["play_count"] == 152000
    assert v["url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert "海底捞" in v["title"]


def test_waf_block_graceful(monkeypatch):
    _stub_urlopen(monkeypatch, "<!DOCTYPE html><html>WAF</html>")
    a = _no_side_effects(BilibiliVideoSearch())
    out = a.query("test")
    assert out["status"] == "rate_limited"
    assert out["videos"] == []


def test_api_error(monkeypatch):
    _stub_urlopen(monkeypatch, json.dumps({"code": -799, "message": "too frequent"}))
    a = _no_side_effects(BilibiliVideoSearch())
    out = a.query("test")
    assert out["status"] == "api_error"
    assert out["code"] == -799


def test_empty_keyword():
    a = BilibiliVideoSearch()
    out = a.query("   ")
    assert out["status"] == "invalid_input"


def test_no_credentials_required():
    a = BilibiliVideoSearch()
    assert a.requires_credentials is False
    assert a.data_boundary == "fully_public"
