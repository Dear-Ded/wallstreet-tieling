"""Tests for Toutiao search adapter."""

import json

from adapters.toutiao_adapter import ToutiaoSearchLookup


def _adapter():
    return ToutiaoSearchLookup(
        execute_query=lambda url, headers: (200, "", ""),
    )


def test_build_url_encodes_keyword():
    a = _adapter()
    url = a._build_url("海底捞")
    assert "so.toutiao.com/search?format=json" in url
    assert "keyword=" in url


def test_empty_raw_data_returns_rate_limited():
    a = _adapter()
    fields = a._extract_public_fields("")
    assert fields["article_count"] == 0
    assert fields.get("rate_limited") is True


def test_invalid_json_returns_parse_error():
    a = _adapter()
    fields = a._extract_public_fields("not json {{{")
    assert fields["article_count"] == 0
    assert fields.get("parse_error") is True


def test_empty_dom_returns_empty_result():
    a = _adapter()
    fields = a._extract_public_fields(json.dumps({"count": 0, "dom": ""}))
    assert fields["article_count"] == 0
    assert fields.get("empty_result") is True


def test_parse_search_dom_extracts_articles():
    dom = (
        '<div><a href="/a1234567890123456789/">海底捞火锅好吃吗</a></div>'
        '<div><span>来源：美食达人</span><span>2024-01-15</span></div>'
        '<div><a href="https://www.toutiao.com/i9876543210987654321/">张三谈创业经验分享</a></div>'
    )
    articles = ToutiaoSearchLookup.parse_search_dom(dom)
    assert len(articles) >= 1
    titles = [a["title"] for a in articles]
    assert any("海底捞" in t for t in titles)


def test_parse_search_dom_skips_short_titles():
    dom = '<a href="/a123/">AB</a><a href="/a456/">首页</a>'
    articles = ToutiaoSearchLookup.parse_search_dom(dom)
    # "AB" too short, "首页" is nav -> both skipped
    assert len(articles) == 0


def test_parse_search_dom_empty():
    assert ToutiaoSearchLookup.parse_search_dom("") == []
    assert ToutiaoSearchLookup.parse_search_dom(None) == []


def test_query_by_author_delegates():
    a = ToutiaoSearchLookup(
        execute_query=lambda url, headers: (200, json.dumps({"count": 0, "dom": ""}), ""),
        robots_checker=lambda domain, url: True,
    )
    result = a.query_by_author("张三")
    assert result["response_status"] == 200


def test_default_off_metadata():
    a = ToutiaoSearchLookup()
    assert a.requires_credentials is False
    assert a.data_boundary == "fully_public"
    assert a.min_request_interval >= 10.0


def test_audit_trail_no_raw_keyword():
    a = ToutiaoSearchLookup(
        execute_query=lambda url, headers: (200, json.dumps({"count": 0, "dom": ""}), ""),
        robots_checker=lambda domain, url: True,
    )
    result = a.query("敏感关键词测试")
    trail = a.audit.get_trail()
    assert len(trail) >= 1
    # audit stores hash, not raw keyword
    for record in trail:
        assert "敏感关键词测试" not in record.get("query_params_hash", "")
    assert result["query_subject_hash"] != "敏感关键词测试"
