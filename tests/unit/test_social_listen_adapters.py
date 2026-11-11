#!/usr/bin/env python3
"""Unit tests for social/tech-listening adapters (HN Algolia, StackExchange).

HTTP is stubbed via SafeResearchAdapter's execute_query override.
"""

from __future__ import annotations

import json

from adapters.social_listen_adapters import (
    HackerNewsAlgoliaSearch,
    StackExchangeSearch,
)
from core.connector_registry import ConnectorRegistry, ConnectorStatus


def _stub(adapter_cls, payload, status=200, **kwargs):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return adapter_cls(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_hn_extracts_stories():
    payload = {"nbHits": 128, "hits": [
        {"title": "Example launches v2", "url": "https://example.com/v2",
         "points": 342, "num_comments": 87, "author": "janedoe",
         "created_at": "2026-10-01T12:00:00Z"},
        {"title": "Ask HN: Example?", "url": "",
         "points": 12, "num_comments": 5, "author": "anon",
         "created_at": "2026-09-01T00:00:00Z"},
    ]}
    adapter = _stub(HackerNewsAlgoliaSearch, payload)
    result = adapter.query("example")
    assert result["response_status"] == 200
    assert result["fields"]["total_hits"] == 128
    first = result["fields"]["stories"][0]
    assert first["title"] == "Example launches v2"
    assert first["points"] == 342
    assert first["num_comments"] == 87
    assert first["author"] == "janedoe"


def test_hn_url_shape():
    adapter = _stub(HackerNewsAlgoliaSearch, {"nbHits": 0, "hits": []})
    url = adapter._build_url("openai", hitsPerPage=25)
    assert "hn.algolia.com/api/v1/search" in url
    assert "tags=story" in url
    assert "hitsPerPage=25" in url


def test_hn_empty_results():
    adapter = _stub(HackerNewsAlgoliaSearch, {"nbHits": 0, "hits": []})
    result = adapter.query("zzz-no-such-topic-xyz")
    assert result["fields"]["total_hits"] == 0
    assert result["fields"]["stories"] == []


def test_hn_garbage_input():
    adapter = _stub(HackerNewsAlgoliaSearch, "not json at all")
    result = adapter.query("example")
    assert result["fields"]["parse_error"] is True


def test_stackexchange_extracts_questions():
    payload = {"has_more": True, "quota_remaining": 9876, "items": [
        {"title": "How to do X in kubernetes?",
         "link": "https://stackoverflow.com/questions/123",
         "score": 45, "answer_count": 3, "is_answered": True,
         "creation_date": 1700000000},
        {"title": "kubernetes error Y",
         "link": "https://stackoverflow.com/questions/124",
         "score": 2, "answer_count": 0, "is_answered": False,
         "creation_date": 1700001000},
    ]}
    adapter = _stub(StackExchangeSearch, payload)
    result = adapter.query("kubernetes")
    assert result["response_status"] == 200
    first = result["fields"]["questions"][0]
    assert first["score"] == 45
    assert first["is_answered"] is True
    assert first["answer_count"] == 3
    assert result["fields"]["has_more"] is True


def test_stackexchange_url_shape():
    adapter = _stub(StackExchangeSearch, {"items": []})
    url = adapter._build_url("kubernetes")
    assert "api.stackexchange.com/2.3/search" in url
    assert "site=stackoverflow" in url
    assert "intitle=kubernetes" in url


def test_stackexchange_empty_results():
    adapter = _stub(StackExchangeSearch, {"items": [], "has_more": False})
    result = adapter.query("zzz-no-such-topic-xyz")
    assert result["fields"]["total_questions"] == 0
    assert result["fields"]["questions"] == []


def test_stackexchange_garbage_input():
    adapter = _stub(StackExchangeSearch, {"unexpected": "shape"})
    result = adapter.query("kubernetes")
    assert result["fields"]["total_questions"] == 0
    assert result["fields"]["questions"] == []


def test_adapters_audit_integrity():
    adapter = _stub(HackerNewsAlgoliaSearch, {"nbHits": 1, "hits": []})
    adapter.query("example")
    assert adapter.audit.verify_integrity() is True
    trail = adapter.audit.get_trail()
    assert trail and trail[0]["source_domain"] == "hn.algolia.com"
    adapter2 = _stub(StackExchangeSearch, {"items": []})
    adapter2.query("example")
    assert adapter2.audit.verify_integrity() is True


def test_registry_lists_social_listen_default_off():
    registry = ConnectorRegistry()
    for name in ("public_hn_algolia_search", "public_stackexchange_search"):
        cap = registry.get(name)
        assert cap is not None, name
        assert cap.default_enabled is False, name
        assert cap.status == ConnectorStatus.EXPERIMENTAL, name
