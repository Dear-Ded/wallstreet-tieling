#!/usr/bin/env python3
"""GitHub deep-enrichment adapter for technical-people due diligence.

Beyond the basic public profile (covered by GitHubPublicProfileLookup),
this adapter pulls the subject's *public activity graph* from GitHub's
unauthenticated REST API (60 req/hour/IP — comfortably within our
rate limits):

- ``/users/{u}/repos`` — public repositories: languages, stars, topics
  (technical footprint, what they actually build)
- ``/users/{u}/orgs`` — public organization memberships (affiliations —
  the strongest public employment signal on GitHub)
- ``/users/{u}/events/public`` — recent public events (activity recency,
  collaboration graph seeds)

Everything returned is data the subject chose to make public. No token,
no scraping of private state. Default-off, EXPERIMENTAL.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API = "https://api.github.com"


class GitHubDeepEnrichment(SafeResearchAdapter):
    """Deep public-activity enrichment for a GitHub username.

    PEOPLE线: 技术人员公开画像深化 — 仓库技术足迹、公开组织归属、
    近期公开动态。全部为当事人主动公开的数据。
    """

    source_domain = "api.github.com"
    source_type = "people_github_deep_enrichment"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _build_url(self, keyword: str, **params) -> str:
        user = urllib.parse.quote(keyword.strip())
        return f"{_API}/users/{user}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() is overridden; this satisfies the ABC.
        return raw_data if isinstance(raw_data, dict) else {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        import hashlib
        import time

        start = time.monotonic()
        username = keyword.strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=username, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(username, "robots_txt_disallowed")

        profile = self._get(f"{_API}/users/{urllib.parse.quote(username)}")
        fields: dict[str, Any] = {"profile_found": profile.get("_status") == 200}
        if fields["profile_found"]:
            fields["profile"] = self._summarize_profile(profile.get("_body", {}))
            repos = self._get(f"{_API}/users/{urllib.parse.quote(username)}/repos?per_page=100&sort=updated")
            fields["repository_footprint"] = self._summarize_repos(repos.get("_body", []))
            orgs = self._get(f"{_API}/users/{urllib.parse.quote(username)}/orgs?per_page=100")
            fields["affiliations"] = self._summarize_orgs(orgs.get("_body", []))
            events = self._get(f"{_API}/users/{urllib.parse.quote(username)}/events/public?per_page=30")
            fields["recent_activity"] = self._summarize_events(events.get("_body", []))
        fields["data_note"] = "GitHub 公开 API — 仅当事人主动公开的数据；组织归属是最强的公开雇佣信号"

        self._record_audit(
            keyword=username, url=self._build_url(username),
            status=profile.get("_status", 0), fields=list(fields.keys()),
        )
        return {
            "query_subject_hash": hashlib.sha256(username.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": profile.get("_status", 0),
            "fields": fields,
            "field_count": len(fields),
            "error": profile.get("_error", ""),
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def _get(self, url: str) -> dict[str, Any]:
        self._enforce_rate_limit()
        status, raw, error = self._execute_query(url, self._build_headers())
        body: Any = None
        if raw:
            try:
                body = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                body = None
        return {"_status": status, "_body": body, "_error": error}

    @staticmethod
    def _summarize_profile(body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        return {
            "login": body.get("login", ""),
            "name": body.get("name", ""),
            "company": body.get("company", ""),
            "blog": body.get("blog", ""),
            "location": body.get("location", ""),
            "email": body.get("email", ""),
            "bio": (body.get("bio") or "")[:300],
            "public_repos": body.get("public_repos", 0),
            "followers": body.get("followers", 0),
            "following": body.get("following", 0),
            "created_at": body.get("created_at", ""),
            "hireable": body.get("hireable"),
        }

    @staticmethod
    def _summarize_repos(body: Any) -> dict[str, Any]:
        if not isinstance(body, list):
            return {"repo_count": 0, "languages": {}, "top_repos": []}
        languages: dict[str, int] = {}
        top: list[dict[str, Any]] = []
        for repo in body:
            if not isinstance(repo, dict) or repo.get("fork"):
                continue
            lang = repo.get("language") or "unknown"
            languages[lang] = languages.get(lang, 0) + 1
            top.append({
                "name": repo.get("name", ""),
                "description": (repo.get("description") or "")[:120],
                "language": lang,
                "stars": repo.get("stargazers_count", 0),
                "topics": list(repo.get("topics") or [])[:8],
                "updated_at": repo.get("updated_at", ""),
            })
        top.sort(key=lambda r: r["stars"], reverse=True)
        return {
            "repo_count": len(body),
            "own_repo_count": len(top),
            "languages": dict(sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:10]),
            "top_repos": top[:10],
        }

    @staticmethod
    def _summarize_orgs(body: Any) -> dict[str, Any]:
        if not isinstance(body, list):
            return {"org_count": 0, "orgs": []}
        return {
            "org_count": len(body),
            "orgs": [
                {"login": o.get("login", ""), "description": (o.get("description") or "")[:120]}
                for o in body if isinstance(o, dict)
            ][:20],
        }

    @staticmethod
    def _summarize_events(body: Any) -> dict[str, Any]:
        if not isinstance(body, list):
            return {"event_count": 0, "event_types": {}, "latest": []}
        types: dict[str, int] = {}
        latest: list[dict[str, Any]] = []
        for event in body[:15]:
            if not isinstance(event, dict):
                continue
            etype = event.get("type", "")
            types[etype] = types.get(etype, 0) + 1
            repo = event.get("repo", {}) or {}
            latest.append({
                "type": etype,
                "repo": repo.get("name", ""),
                "created_at": event.get("created_at", ""),
            })
        return {"event_count": len(body), "event_types": types, "latest": latest}
