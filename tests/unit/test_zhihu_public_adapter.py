"""Tests for Zhihu public adapter (offline fixtures, 2026-10-21 API shapes)."""

from adapters.zhihu_public_adapter import ZhihuPublic

FIXTURE_HOT = {
    "data": [
        {
            "card_id": "Q_2095115404402225389",
            "target": {
                "title_area": {"text": "测试问题标题"},
                "excerpt_area": {"text": "摘要内容" * 10},
                "metrics_area": {"text": "1596 万热度"},
                "link": {"url": "https://www.zhihu.com/question/2095115404402225389"},
            },
        },
        {"card_id": "Q_1", "target": {}},
    ]
}

FIXTURE_PROFILE = {
    "name": "测试用户",
    "url_token": "test-user",
    "headline": "某公司 CEO",
    "user_type": "people",
    "is_org": False,
    "is_realname": True,
    "org_verify_status": 0,
    "gender": 1,
    "avatar_url": "https://picx.zhimg.com/x.jpg",
    "ip_info": "IP属地北京",
    "url": "https://www.zhihu.com/people/test-user",
}

import json as _json


def _adapter(body, **kw):
    return ZhihuPublic(
        execute_query=lambda url, headers: (200, _json.dumps(body), ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_hot():
    a = _adapter({})
    assert a._build_url("kw") == (
        "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true"
    )


def test_build_url_profile():
    a = _adapter({})
    assert a._build_url("kw", mode="profile", url_token="test-user") == (
        "https://www.zhihu.com/api/v4/members/test-user"
    )


def test_parse_hot_list():
    items = ZhihuPublic.parse_hot_list(FIXTURE_HOT)
    assert len(items) == 1
    assert items[0]["title"] == "测试问题标题"
    assert items[0]["heat"] == "1596 万热度"
    assert items[0]["url"].endswith("2095115404402225389")


def test_parse_profile():
    p = ZhihuPublic.parse_profile(FIXTURE_PROFILE)
    assert p["name"] == "测试用户"
    assert p["is_realname"] is True
    assert p["ip_info"] == "IP属地北京"


def test_query_hot():
    a = _adapter(FIXTURE_HOT)
    result = a.query("今日热点")
    assert result["fields"]["hot_count"] == 1
    assert result["response_status"] == 200
    assert a.audit.verify_integrity()


def test_query_profile():
    a = _adapter(FIXTURE_PROFILE)
    result = a.query("kw", mode="profile", url_token="test-user")
    assert result["fields"]["profile_found"] is True
    assert result["fields"]["profile"]["headline"] == "某公司 CEO"


def test_invalid_token_structured_empty():
    a = _adapter({})
    result = a.query("not a token!!", mode="profile")
    assert result["fields"] == {}
    assert "url_token_invalid" in result["error"]


def test_robots_no_wildcard_group_allows():
    a = _adapter({})
    # zhihu robots.txt has no User-agent: * group -> no restriction on us
    assert a._check_robots() is True
