#!/usr/bin/env python3
"""Unit tests for developer-footprint adapters (GitLab, DockerHub, npm, crates.io).

HTTP is stubbed via SafeResearchAdapter's execute_query override.
"""

from __future__ import annotations

import json

from adapters.dev_footprint_adapters import (
    CratesIoSearch,
    DockerHubUserLookup,
    GitLabUserLookup,
    NpmAuthorSearch,
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


def test_gitlab_extracts_user():
    payload = [{"id": 1, "username": "octocat", "name": "The Octocat",
                "bio": "hello", "location": "SF", "projects_count": 5,
                "followers": 10, "created_at": "2020-01-01",
                "web_url": "https://gitlab.com/octocat"}]
    adapter = _stub(GitLabUserLookup, payload)
    result = adapter.query("octocat")
    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["user_found"] is True
    assert fields["username"] == "octocat"
    assert fields["public_repos"] == 5


def test_gitlab_empty_list():
    adapter = _stub(GitLabUserLookup, [])
    result = adapter.query("no-such-user-xyz")
    assert result["fields"]["user_found"] is False


def test_gitlab_garbage():
    adapter = _stub(GitLabUserLookup, {"unexpected": True})
    result = adapter.query("x")
    assert result["fields"]["parse_error"] is True


def test_dockerhub_extracts_profile():
    payload = {"username": "torvalds", "full_name": "", "location": "Italy",
               "company": "DoLoop srls", "profile_url": "",
               "date_joined": "2020-01-01"}
    adapter = _stub(DockerHubUserLookup, payload)
    result = adapter.query("torvalds")
    fields = result["fields"]
    assert fields["user_found"] is True
    assert fields["location"] == "Italy"
    assert fields["company"] == "DoLoop srls"


def test_dockerhub_404_normalized():
    adapter = _stub(DockerHubUserLookup, {"message": "not found"}, status=404)
    result = adapter.query("no-such-user-xyz")
    assert result["response_status"] == 200
    assert result["fields"]["user_found"] is False
    assert result["error"] == ""


def test_npm_extracts_packages():
    payload = {"total": 2, "objects": [
        {"package": {"name": "@u/pkg-a", "version": "1.0.0",
                     "description": "aaa", "keywords": ["x"], "date": "2024-01-01"},
         "downloads": {"monthly": 100, "weekly": 20}},
        {"package": {"name": "@u/pkg-b", "version": "2.0.0",
                     "description": "bbb", "keywords": [], "date": "2024-02-01"},
         "downloads": {"monthly": 500, "weekly": 100}},
    ]}
    adapter = _stub(NpmAuthorSearch, payload)
    result = adapter.query("u")
    fields = result["fields"]
    assert fields["total_packages"] == 2
    # sorted by downloads desc
    assert fields["packages"][0]["name"] == "@u/pkg-b"
    assert fields["packages"][0]["monthly_downloads"] == 500


def test_npm_empty():
    adapter = _stub(NpmAuthorSearch, {"total": 0, "objects": []})
    result = adapter.query("nobody-here-xyz")
    assert result["fields"]["total_packages"] == 0
    assert result["fields"]["packages"] == []


def test_cratesio_extracts_crates():
    payload = {"meta": {"total": 1}, "crates": [
        {"name": "serde", "description": "Serialization",
         "downloads": 1000, "recent_downloads": 100,
         "created_at": "2014-01-01", "updated_at": "2024-01-01"}]}
    adapter = _stub(CratesIoSearch, payload)
    result = adapter.query("serde")
    fields = result["fields"]
    assert fields["total_crates"] == 1
    assert fields["crates"][0]["name"] == "serde"
    assert fields["crates"][0]["downloads"] == 1000


def test_cratesio_garbage():
    adapter = _stub(CratesIoSearch, "not json{{{")
    result = adapter.query("x")
    assert result["fields"]["parse_error"] is True


def test_dev_footprint_audit_integrity():
    for cls, payload in (
        (GitLabUserLookup, []),
        (DockerHubUserLookup, {"username": "u"}),
        (NpmAuthorSearch, {"total": 0, "objects": []}),
        (CratesIoSearch, {"meta": {"total": 0}, "crates": []}),
    ):
        adapter = _stub(cls, payload)
        adapter.query("testuser")
        assert adapter.audit.verify_integrity() is True, cls.__name__


def test_registry_lists_dev_footprint_default_off():
    registry = ConnectorRegistry()
    for name in ("public_gitlab_user_lookup", "public_dockerhub_user_lookup",
                 "public_npm_author_search", "public_cratesio_search"):
        cap = registry.get(name)
        assert cap is not None, name
        assert cap.default_enabled is False, name
        assert cap.status == ConnectorStatus.EXPERIMENTAL, name
