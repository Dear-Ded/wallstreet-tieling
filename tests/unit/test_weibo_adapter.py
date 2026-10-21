"""Tests for adapters.weibo_adapter.WeiboSearchLookup."""

import json

import pytest

from adapters.weibo_adapter import WeiboSearchLookup


@pytest.fixture()
def adapter() -> WeiboSearchLookup:
    return WeiboSearchLookup()


def _sample_response() -> dict:
    return {
        "ok": 1,
        "data": {
            "cards": [
                {
                    "card_type": 9,
                    "mblog": {
                        "id": "1234567890",
                        "mid": "Nb123456",
                        "text": "我是<span>蜜雪冰城</span>创始人张红超，今天新店开业！",
                        "created_at": "2026-10-21",
                        "reposts_count": 100,
                        "comments_count": 50,
                        "attitudes_count": 1000,
                        "user": {
                            "id": 123456,
                            "screen_name": "张红超",
                            "description": "蜜雪冰城创始人",
                            "followers_count": 50000,
                            "verified": True,
                            "verified_reason": "蜜雪冰城创始人",
                        },
                    },
                },
                {
                    "card_type": 11,
                    "card_group": [
                        {
                            "mblog": {
                                "id": "0987654321",
                                "text": "探店：<a>蜜雪冰城</a>新品真好喝",
                                "created_at": "2小时前",
                                "reposts_count": 5,
                                "comments_count": 10,
                                "attitudes_count": 100,
                                "user": {
                                    "id": 654321,
                                    "screen_name": "吃货小王",
                                    "description": "美食博主",
                                    "followers_count": 1000,
                                    "verified": False,
                                    "verified_reason": "",
                                },
                            }
                        }
                    ],
                },
            ]
        },
    }


def test_query_returns_interaction_required(adapter: WeiboSearchLookup):
    result = adapter.query("蜜雪冰城")
    assert result["status"] == "interaction_required"
    assert result["keyword"] == "蜜雪冰城"
    assert "instructions" in result
    assert len(result["instructions"]) > 0


def test_query_empty_keyword(adapter: WeiboSearchLookup):
    result = adapter.query("")
    assert result["status"] == "interaction_required"
    assert result["reason"] == "empty keyword"


def test_parse_browser_result_extracts_posts(adapter: WeiboSearchLookup):
    parsed = adapter.parse_browser_result(_sample_response())
    assert parsed["status"] == "ok"
    assert parsed["post_count"] == 2

    first = parsed["posts"][0]
    assert "蜜雪冰城" in first["text"]
    assert "创始人张红超" in first["text"]
    # HTML 标签已去除
    assert "<span>" not in first["text"]
    assert first["author"]["screen_name"] == "张红超"
    assert first["author"]["description"] == "蜜雪冰城创始人"
    assert first["author"]["verified"] is True
    assert first["likes"] == 1000

    second = parsed["posts"][1]
    assert second["author"]["screen_name"] == "吃货小王"


def test_parse_browser_result_accepts_json_string(adapter: WeiboSearchLookup):
    raw = json.dumps(_sample_response())
    parsed = adapter.parse_browser_result(raw)
    assert parsed["status"] == "ok"
    assert parsed["post_count"] == 2


def test_parse_browser_result_invalid_json(adapter: WeiboSearchLookup):
    parsed = adapter.parse_browser_result("not json {{{")
    assert parsed["status"] == "parse_failed"
    assert parsed["post_count"] == 0


def test_parse_browser_result_garbage_input(adapter: WeiboSearchLookup):
    parsed = adapter.parse_browser_result(None)  # type: ignore[arg-type]
    assert parsed["status"] == "parse_failed"


def test_audit_does_not_leak_keyword(adapter: WeiboSearchLookup):
    adapter.query("敏感关键词测试")
    records = list(adapter.audit.records) if hasattr(adapter.audit, "records") else []
    # 审计中不应出现原文
    blob = json.dumps(records, default=str, ensure_ascii=False)
    assert "敏感关键词测试" not in blob
