"""Tests for adapters.weibo_relation_adapter.WeiboRelationLookup."""

import json

import pytest

from adapters.weibo_relation_adapter import WeiboRelationLookup


@pytest.fixture()
def adapter() -> WeiboRelationLookup:
    return WeiboRelationLookup()


def _sample_response() -> dict:
    return {
        "ok": 1,
        "data": {
            "cards": [
                {
                    "card_type": 10,
                    "user": {
                        "id": 123456,
                        "screen_name": "王铁柱",
                        "description": "铁岭XX商贸有限公司总经理",
                        "profile_url": "https://m.weibo.cn/u/123456",
                        "verified": True,
                        "verified_type": 0,
                        "verified_reason": "铁岭XX商贸有限公司总经理",
                        "followers_count": 800,
                        "follow_count": 300,
                        "gender": "m",
                        "follow_me": True,
                        "following": True,
                    },
                },
                {
                    "card_type": 10,
                    "user": {
                        "id": 654321,
                        "screen_name": "李桂花",
                        "description": "全职妈妈，爱生活",
                        "profile_url": "",
                        "verified": False,
                        "verified_type": -1,
                        "verified_reason": "",
                        "followers_count": 50,
                        "follow_count": 120,
                        "gender": "f",
                    },
                },
                {"card_type": 7},  # "查看更多" 分页卡，无 user，应被跳过
                "not-a-dict",  # 脏数据，应被跳过
            ],
            "cardlistInfo": {
                "containerid": "231051_-_followers_-_999888",
                "since_id": "abc123",
                "total": 300,
            },
        },
    }


def test_query_returns_interaction_required(adapter: WeiboRelationLookup):
    r = adapter.query("999888", relation="followers")
    assert r["status"] == "interaction_required"
    assert r["user_id"] == "999888"
    assert r["relation"] == "followers"
    assert r["relation_cn"] == "关注"
    assert "231051_-_followers_-_999888" in r["api_url_hint"]
    assert len(r["instructions"]) >= 6


def test_query_fans_relation(adapter: WeiboRelationLookup):
    r = adapter.query("999888", relation="fans")
    assert r["relation"] == "fans"
    assert r["relation_cn"] == "粉丝"
    assert "231051_-_fans_-_999888" in r["api_url_hint"]


def test_query_empty_user_id(adapter: WeiboRelationLookup):
    r = adapter.query("")
    assert r["status"] == "interaction_required"
    assert r["reason"] == "empty user_id"


def test_query_invalid_relation(adapter: WeiboRelationLookup):
    r = adapter.query("999888", relation="bogus")
    assert r["status"] == "interaction_required"
    assert "invalid relation" in r["reason"]


def test_parse_browser_result_dict(adapter: WeiboRelationLookup):
    r = adapter.parse_browser_result(_sample_response(), relation="followers")
    assert r["status"] == "ok"
    assert r["relation"] == "followers"
    assert r["user_count"] == 2
    assert r["total"] == 300

    u0 = r["users"][0]
    assert u0["id"] == "123456"
    assert u0["screen_name"] == "王铁柱"
    assert u0["verified"] is True
    assert "总经理" in u0["verified_reason"]
    assert u0["followers_count"] == 800
    assert u0["follow_me"] is True
    assert u0["following"] is True

    u1 = r["users"][1]
    assert u1["id"] == "654321"
    assert u1["verified"] is False
    # 无 profile_url 时自动拼 m.weibo.cn/u/{id}
    assert u1["profile_url"] == "https://m.weibo.cn/u/654321"

    assert r["pagination"]["since_id"] == "abc123"
    assert "since_id" in r["pagination"]["next_page_hint"]


def test_parse_browser_result_json_string(adapter: WeiboRelationLookup):
    r = adapter.parse_browser_result(json.dumps(_sample_response()), relation="fans")
    assert r["status"] == "ok"
    assert r["relation_cn"] == "粉丝"
    assert r["user_count"] == 2


def test_parse_browser_result_invalid_json(adapter: WeiboRelationLookup):
    r = adapter.parse_browser_result("{not json", relation="followers")
    assert r["status"] == "parse_failed"
    assert r["reason"] == "invalid_json"
    assert r["user_count"] == 0


def test_parse_browser_result_invalid_input(adapter: WeiboRelationLookup):
    r = adapter.parse_browser_result(None)
    assert r["status"] == "parse_failed"
    assert r["reason"] == "invalid_input"


def test_parse_browser_result_missing_data(adapter: WeiboRelationLookup):
    r = adapter.parse_browser_result({"ok": 1}, relation="followers")
    assert r["status"] == "ok"
    assert r["user_count"] == 0
    assert r["users"] == []


def test_build_url(adapter: WeiboRelationLookup):
    url = adapter._build_url("999888", relation="fans", page=3)
    assert "231051_-_fans_-_999888" in url
    assert "page=3" in url


def test_default_off_metadata(adapter: WeiboRelationLookup):
    assert adapter.requires_interaction is True
    assert adapter.requires_credentials is False
    assert adapter.data_boundary == "fully_public"
    assert adapter.source_domain == "m.weibo.cn"


def test_audit_does_not_leak_raw(adapter: WeiboRelationLookup):
    # 审计只存 keyword 的 sha256 前 12 位，不存原文
    adapter.query("999888", relation="followers")
    trail = adapter.audit.get_trail()
    blob = json.dumps(trail, default=str, ensure_ascii=False)
    assert "999888" not in blob
