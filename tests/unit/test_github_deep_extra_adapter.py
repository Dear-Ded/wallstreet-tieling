"""Tests for GitHub deep-extra adapter (commit emails + starred taste, offline)."""

import json

from adapters.github_deep_extra_adapter import GitHubDeepExtra

FIXTURE_REPOS = json.dumps([
    {"name": "demo", "fork": False,
     "owner": {"login": "octocat"}},
    {"name": "forked-thing", "fork": True,
     "owner": {"login": "octocat"}},
])
FIXTURE_COMMITS = json.dumps([
    {"commit": {"author": {"name": "Mona", "email": "mona@example.com"},
                "committer": {"name": "Mona", "email": "mona@example.com"}}},
    {"commit": {"author": {"name": "Mona", "email": "mona@noreply.github.com"},
                "committer": {"name": "Mona", "email": "mona@example.com"}}},
])
FIXTURE_STARRED = json.dumps([
    {"full_name": "rust-lang/rust", "description": "Rust language",
     "language": "Rust", "stargazers_count": 90000, "topics": ["language", "systems"]},
    {"full_name": "pallets/flask", "description": "web framework",
     "language": "Python", "stargazers_count": 60000, "topics": ["web"]},
])


def _router(url, headers):
    if "/starred" in url:
        return (200, FIXTURE_STARRED, "")
    if "/commits" in url:
        return (200, FIXTURE_COMMITS, "")
    if "/repos?" in url or url.rstrip("/").endswith("/repos"):
        return (200, FIXTURE_REPOS, "")
    return (404, "{}", "")


def _adapter():
    return GitHubDeepExtra(
        execute_query=_router,
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_query_collects_commit_emails_and_starred():
    result = _adapter().query("octocat")
    fields = result["fields"]
    emails = fields["commit_author_emails"]
    assert emails["repos_scanned"] == 1  # fork skipped
    found = {e["email"] for e in emails["emails"]}
    assert "mona@example.com" in found
    assert not any("noreply" in e for e in found)
    starred = fields["starred_profile"]
    assert starred["star_count"] == 2
    assert starred["languages"]["Rust"] == 1
    assert "language" in starred["topics"]


def test_parse_starred_offline():
    summary = GitHubDeepExtra.parse_starred_result(FIXTURE_STARRED)
    assert summary["star_count"] == 2
    assert summary["top_starred"][0]["full_name"] == "rust-lang/rust"


def test_build_url():
    assert _adapter()._build_url("octocat") == "https://api.github.com/users/octocat"
