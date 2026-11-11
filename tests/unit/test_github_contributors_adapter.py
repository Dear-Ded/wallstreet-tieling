"""Tests for GitHub contributors adapter (offline fixtures)."""

import json

from adapters.github_contributors_adapter import GithubContributorsLookup

FIXTURE_OK = json.dumps([
    {"login": "alice", "contributions": 120, "type": "User",
     "html_url": "https://github.com/alice"},
    {"login": "bob", "contributions": 45, "type": "User",
     "html_url": "https://github.com/bob"},
    {"login": "dependabot[bot]", "contributions": 30, "type": "Bot",
     "html_url": "https://github.com/apps/dependabot"},
])

FIXTURE_TOO_LARGE = json.dumps({
    "message": "The history or contributor list is too large to list "
               "contributors for this repository via the API.",
    "documentation_url": "https://docs.github.com/rest/repos/repos",
    "status": "403",
})

FIXTURE_RATE_LIMIT = json.dumps({
    "message": "API rate limit exceeded for 1.2.3.4.",
    "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting",
})

FIXTURE_NOT_FOUND = json.dumps({
    "message": "Not Found",
    "documentation_url": "https://docs.github.com/rest",
    "status": "404",
})


def _adapter(body, status=200):
    return GithubContributorsLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_and_per_page_clamp():
    a = _adapter("")
    url = a._build_url("octocat/Hello-World")
    assert "repos/octocat/Hello-World/contributors" in url
    assert "per_page=30" in url
    assert "per_page=100" in a._build_url("o/r", per_page=500)
    assert "per_page=1" in a._build_url("o/r", per_page=0)


def test_invalid_repo_format_rejected():
    a = _adapter("")
    out = a.query("not-a-repo")
    assert out["error"].startswith("invalid_input")
    out2 = a.query("a/b/c")
    assert out2["error"].startswith("invalid_input")


def test_extract_contributors_sorted_and_bots_flagged():
    a = _adapter(FIXTURE_OK)
    f = a.query("o/r")["fields"]
    assert f["contributor_count"] == 3
    assert f["bots_excluded"] == 1
    assert f["contributors"][0]["login"] == "alice"
    assert f["contributors"][0]["contributions"] == 120
    assert f["contributors"][2]["is_bot"] is True
    assert f["contributors"][0]["profile_url"] == "https://github.com/alice"


def test_extract_repo_too_large_degrades():
    a = _adapter(FIXTURE_TOO_LARGE, status=403)
    f = a.query("torvalds/linux")["fields"]
    assert f["repo_too_large"] is True
    assert "contributors" not in f


def test_extract_rate_limited():
    a = _adapter(FIXTURE_RATE_LIMIT, status=403)
    assert a.query("o/r")["fields"]["rate_limited"] is True


def test_extract_not_found():
    a = _adapter(FIXTURE_NOT_FOUND, status=404)
    assert a.query("o/r")["fields"]["not_found"] is True


def test_extract_garbage():
    a = _adapter("not json{{{")
    assert a.query("o/r")["fields"]["parse_error"] is True


def test_parse_contributors_static_entry():
    cs = GithubContributorsLookup.parse_contributors(FIXTURE_OK)
    assert [c["login"] for c in cs] == ["alice", "bob", "dependabot[bot]"]


def test_adapter_is_experimental_and_conservative():
    assert GithubContributorsLookup.min_request_interval >= 5.0
    assert GithubContributorsLookup.requires_credentials is False
    assert GithubContributorsLookup.requires_interaction is False
    assert GithubContributorsLookup.data_boundary == "fully_public"
