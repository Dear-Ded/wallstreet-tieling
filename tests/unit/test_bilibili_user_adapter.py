"""Tests for Bilibili public user search adapter (offline fixtures, 2026-10-21 API shapes)."""

import json as _json

from adapters.bilibili_user_adapter import BilibiliUserLookup

# Real API shape from 2026-10-21 survey (search_type=bili_user, keyword=人民日报)
FIXTURE_SEARCH = {
    "code": 0,
    "message": "OK",
    "data": {
        "result": [
            {
                "mid": 1131457022,
                "uname": "人民日报",
                "usign": "参与、沟通、记录时代。",
                "fans": 19082142,
                "level": 6,
                "gender": 0,
                "videos": 5741,
                "is_upuser": 0,
                "official_verify": {"type": 1, "desc": "人民日报官方账号"},
                "verify_info": "",
                "upic": "https://i0.hdslb.com/bfs/face/xxx.jpg",
                "type": "bili_user",
            },
            {
                "mid": 2,
                "uname": "测试用户",
                "usign": "",
                "fans": 10,
                "level": 3,
                "gender": 1,
                "videos": 5,
                "is_upuser": 1,
                "official_verify": {"type": -1, "desc": ""},
                "verify_info": "",
                "upic": "",
                "type": "bili_user",
            },
        ]
    },
}


def _adapter(body, **kw):
    raw = body if isinstance(body, str) else _json.dumps(body)
    return BilibiliUserLookup(
        execute_query=lambda url, headers: (200, raw, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
        **kw,
    )


def test_parse_user_flattens_fields():
    u = BilibiliUserLookup.parse_user(FIXTURE_SEARCH["data"]["result"][0])
    assert u["mid"] == 1131457022
    assert u["uname"] == "人民日报"
    assert u["bio"] == "参与、沟通、记录时代。"
    assert u["fans"] == 19082142
    assert u["level"] == 6
    assert u["official_type"] == 1
    assert u["official_desc"] == "人民日报官方账号"
    assert u["profile_url"] == "https://space.bilibili.com/1131457022"


def test_parse_user_empty_bio_ok():
    u = BilibiliUserLookup.parse_user(FIXTURE_SEARCH["data"]["result"][1])
    assert u["uname"] == "测试用户"
    assert u["bio"] == ""
    assert u["is_upuser"] is True


def test_query_extracts_users():
    a = _adapter(FIXTURE_SEARCH)
    result = a.query("人民日报")
    assert result["status"] == "ok"
    assert result["fields"]["user_count"] == 2
    assert result["fields"]["users"][0]["uname"] == "人民日报"
    assert result["response_status"] == 200
    assert a.audit.verify_integrity()


def test_query_invalid_input():
    a = _adapter(FIXTURE_SEARCH)
    result = a.query("   ")
    assert result["status"] == "invalid_input"
    assert result["users"] == []


def test_query_api_error_structured():
    a = _adapter({"code": -799, "message": "请求过于频繁，请稍后再试"})
    result = a.query("人民日报")
    assert result["status"] == "api_error"
    assert result["code"] == -799
    assert result["users"] == []


def test_query_waf_block_page():
    a = _adapter("<html><body>412 Precondition Failed</body></html>")
    result = a.query("人民日报")
    assert result["status"] == "rate_limited"
    assert result["users"] == []


def test_five_second_rate_limit_enforced():
    waits: list[float] = []
    a = BilibiliUserLookup(
        execute_query=lambda url, headers: (200, _json.dumps(FIXTURE_SEARCH), ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: waits.append(s),
    )
    assert a.min_request_interval == 5.0
    a._enforce_rate_limit()
    a._enforce_rate_limit()
    assert waits, "second call within 5s must sleep"
    assert waits[0] > 4.0


def test_data_boundary_and_no_credentials():
    a = _adapter(FIXTURE_SEARCH)
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.requires_interaction is False
