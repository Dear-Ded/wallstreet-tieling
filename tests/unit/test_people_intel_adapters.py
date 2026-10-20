#!/usr/bin/env python3
"""Unit tests for people-intel adapters (email infrastructure, GitHub deep).

Network is stubbed: EmailIntelLookup overrides _check_mx/_check_gravatar;
GitHubDeepEnrichment uses SafeResearchAdapter's execute_query override.
"""

from __future__ import annotations

import json

from adapters.email_intel_adapter import EmailIntelLookup
from adapters.github_deep_adapter import GitHubDeepEnrichment
from core.connector_registry import ConnectorRegistry, ConnectorStatus


class _EmailStub(EmailIntelLookup):
    def __init__(self, mx=True, gravatar=False):
        super().__init__(
            robots_checker=lambda domain, url: True,
            sleeper=lambda seconds: None,
        )
        self._mx = mx
        self._gravatar = gravatar

    @staticmethod
    def _check_mx(domain: str) -> bool:
        return True

    def _check_gravatar(self, email: str) -> bool:  # noqa: ARG002
        return self._gravatar


def _github_stub(routes: dict):
    ordered = sorted(routes.items(), key=lambda kv: -len(kv[0]))

    def _exec(url, headers):
        for prefix, payload in ordered:
            if url.startswith(prefix):
                return (200, json.dumps(payload), "")
        return (404, json.dumps({"message": "not found"}), "")
    return GitHubDeepEnrichment(
        execute_query=_exec,
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )


def test_email_intel_rejects_bad_syntax():
    adapter = _EmailStub()
    result = adapter.query("not-an-email")
    assert result["fields"]["syntax_valid"] is False
    assert result["response_status"] == 200


def test_email_intel_detects_role_and_disposable():
    adapter = _EmailStub()
    role = adapter.query("support@example.com")["fields"]
    assert role["is_role_account"] is True
    assert role["is_disposable"] is False
    disp = adapter.query("user@mailinator.com")["fields"]
    assert disp["is_disposable"] is True
    assert disp["is_role_account"] is False


def test_email_intel_personal_address():
    adapter = _EmailStub(gravatar=True)
    fields = adapter.query("Jane.Doe@Example.COM")["fields"]
    assert fields["syntax_valid"] is True
    assert fields["domain"] == "example.com"
    assert fields["local_part"] == "jane.doe"
    assert fields["has_mx_record"] is True
    assert fields["gravatar_registered"] is True
    assert "不查泄露库" in fields["data_note"]


def test_email_intel_audit_integrity():
    adapter = _EmailStub()
    adapter.query("a@b.com")
    assert adapter.audit.verify_integrity() is True


def test_github_deep_enrichment_summarizes():
    routes = {
        "https://api.github.com/users/octocat": {
            "login": "octocat", "name": "The Octocat", "company": "GitHub",
            "public_repos": 8, "followers": 100, "hireable": None,
        },
        "https://api.github.com/users/octocat/repos": [
            {"name": "hello-world", "fork": False, "language": "Python",
             "stargazers_count": 50, "topics": ["demo"], "description": "d",
             "updated_at": "2024-01-01T00:00:00Z"},
            {"name": "forked", "fork": True, "language": "Go",
             "stargazers_count": 999, "topics": [], "description": "",
             "updated_at": "2024-01-01T00:00:00Z"},
        ],
        "https://api.github.com/users/octocat/orgs": [
            {"login": "github", "description": "GitHub org"},
        ],
        "https://api.github.com/users/octocat/events": [
            {"type": "PushEvent", "repo": {"name": "octocat/hello-world"},
             "created_at": "2024-06-01T00:00:00Z"},
        ],
    }
    adapter = _github_stub(routes)
    result = adapter.query("octocat")
    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["profile_found"] is True
    assert fields["profile"]["company"] == "GitHub"
    # fork excluded from own-repo footprint
    assert fields["repository_footprint"]["own_repo_count"] == 1
    assert fields["repository_footprint"]["languages"] == {"Python": 1}
    assert fields["affiliations"]["org_count"] == 1
    assert fields["affiliations"]["orgs"][0]["login"] == "github"
    assert fields["recent_activity"]["event_types"] == {"PushEvent": 1}


def test_github_deep_enrichment_missing_user():
    adapter = _github_stub({})
    result = adapter.query("no-such-user-xyz")
    assert result["fields"]["profile_found"] is False


def test_github_deep_enrichment_uses_public_api_headers():
    adapter = _github_stub({})
    headers = adapter._build_headers()
    assert "WallstreetTieling" in headers["User-Agent"]
    assert adapter.min_request_interval >= 3.0


def test_registry_lists_people_intel_default_off():
    registry = ConnectorRegistry()
    for name in ("public_email_infrastructure_intel", "public_github_deep_enrichment"):
        cap = registry.get(name)
        assert cap is not None, name
        assert cap.default_enabled is False, name
        assert cap.status == ConnectorStatus.EXPERIMENTAL, name


def test_orchestrator_fans_out_and_corroborates():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeEmail:
        def query(self, email):
            return {"fields": {"domain": "github.com", "is_disposable": False,
                               "is_role_account": False, "syntax_valid": True}}

    class FakeGitHub:
        def query(self, username):
            return {"fields": {"profile": {"company": "GitHub"},
                               "affiliations": {"orgs": [{"login": "github"}]}}}

    class FakeOfficer:
        def query(self, name):
            return {"fields": {"samples": [{"company_name": "GitHub Inc"}]}}

    orch = PeopleIntelOrchestrator(
        email_adapter=FakeEmail(), github_adapter=FakeGitHub(),
        officer_adapter=FakeOfficer())
    graph = orch.investigate(PersonQuery(
        name="The Octocat", email="octocat@github.com", github_username="octocat"))
    assert graph["type"] == "people_lead_graph"
    assert graph["source_count"] == 3
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "domain_company_consistent" in types
    assert "officer_org_consistent" in types


def test_orchestrator_degrades_per_source():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class Boom:
        def query(self, arg):
            raise RuntimeError("network down")

    orch = PeopleIntelOrchestrator(email_adapter=Boom())
    graph = orch.investigate(PersonQuery(email="a@b.com"))
    assert "network down" in graph["sources"]["email_intel"]["error"]
    assert graph["source_count"] == 1


def test_orchestrator_runs_nothing_by_default():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery
    graph = PeopleIntelOrchestrator().investigate(
        PersonQuery(name="X", email="x@y.com"))
    assert graph["source_count"] == 0
    assert graph["corroborations"] == []


def test_orchestrator_username_footprint_wiring():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeProfiler:
        def massive_cross_check(self, username):
            return {"fields": {"platforms_found": 3, "coverage_ratio": "3/29",
                               "by_category": {"code": ["GitHub", "GitLab"]}}}

    orch = PeopleIntelOrchestrator(username_adapter=FakeProfiler())
    graph = orch.investigate(PersonQuery(username="octocat", github_username="octocat"))
    assert graph["source_count"] == 1
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "username_github_consistent" in types
    assert "username_footprint_summary" in types


def test_orchestrator_username_adapter_without_massive_check():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class PlainQuery:
        def query(self, username):
            return {"fields": {"platforms_found": 1, "by_category": {}}}

    orch = PeopleIntelOrchestrator(username_adapter=PlainQuery())
    graph = orch.investigate(PersonQuery(username="someone"))
    assert graph["sources"]["username_footprint"]["fields"]["platforms_found"] == 1


def test_orchestrator_social_listening_runs_when_injected():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeSocial:
        def query(self, q):
            return {"fields": {"total_hits": 5, "stories": [
                {"title": "Jane Doe launches a startup"},
                {"title": "unrelated story"}]}}

    orch = PeopleIntelOrchestrator(social_adapter=FakeSocial())
    graph = orch.investigate(PersonQuery(name="Jane Doe"))
    assert graph["source_count"] == 1
    assert "social_listening" in graph["sources"]
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "social_mention_signal" in types
    lead = next(l for l in graph["corroborations"] if l["type"] == "social_mention_signal")
    assert "5" in lead["detail"] and "Jane Doe" in lead["detail"]


def test_orchestrator_social_no_lead_without_name_mention():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeSocial:
        def query(self, q):
            return {"fields": {"total_hits": 3, "stories": [
                {"title": "totally unrelated title"}]}}

    orch = PeopleIntelOrchestrator(social_adapter=FakeSocial())
    graph = orch.investigate(PersonQuery(name="Jane Doe"))
    assert graph["source_count"] == 1
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "social_mention_signal" not in types


def test_orchestrator_social_no_lead_on_zero_hits():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeSocial:
        def query(self, q):
            return {"fields": {"total_hits": 0, "stories": []}}

    orch = PeopleIntelOrchestrator(social_adapter=FakeSocial())
    graph = orch.investigate(PersonQuery(name="Jane Doe"))
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "social_mention_signal" not in types


def test_orchestrator_social_stackexchange_shape():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeSE:
        def query(self, q):
            return {"fields": {"total_questions": 2, "questions": [
                {"title": "How does Jane Doe scale databases?"}]}}

    orch = PeopleIntelOrchestrator(social_adapter=FakeSE())
    graph = orch.investigate(PersonQuery(name="Jane Doe"))
    types = {lead["type"] for lead in graph["corroborations"]}
    assert "social_mention_signal" in types


def test_orchestrator_social_degrades_on_exception():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class Boom:
        def query(self, q):
            raise RuntimeError("api down")

    orch = PeopleIntelOrchestrator(social_adapter=Boom())
    graph = orch.investigate(PersonQuery(name="Jane Doe"))
    assert "api down" in graph["sources"]["social_listening"]["error"]
    assert graph["source_count"] == 1


def test_orchestrator_social_not_run_without_name():
    from core.people_intel import PeopleIntelOrchestrator, PersonQuery

    class FakeSocial:
        def query(self, q):
            raise AssertionError("should not be called")

    orch = PeopleIntelOrchestrator(social_adapter=FakeSocial())
    graph = orch.investigate(PersonQuery(email="a@b.com"))
    assert graph["source_count"] == 0


def test_domain_intel_endpoint_missing_domain():
    from api.server import app
    client = app.test_client()
    r = client.post("/api/domain-intel", json={})
    assert r.status_code == 400
    assert "domain" in r.get_json().get("error", "")


def test_domain_intel_endpoint_empty_sources_runs_nothing():
    from api.server import app
    client = app.test_client()
    r = client.post("/api/domain-intel", json={"domain": "example.com"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["type"] == "domain_intel_enrichment"
    assert body["domain"] == "example.com"
    assert body["source_count"] == 0
    assert body["sources"] == {}
