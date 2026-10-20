#!/usr/bin/env python3
"""Developer-footprint OSINT adapters (PEOPLE / IP_TECH lane).

Four free, no-credential public APIs answering: *what does this person
publish as a developer?*

- GitLab: public user profile by username (id, name, bio, public project count)
- DockerHub: public user profile (full name, location, company, profile URL)
- npm: packages authored by a username (names, versions, descriptions, downloads)
- crates.io: Rust crates matching a query (names, descriptions, download counts;
  crates.io API policy requires a User-Agent — base _build_headers provides one)

All data is published by the subject. Default-off, EXPERIMENTAL.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class GitLabUserLookup(SafeResearchAdapter):
    """GitLab public user lookup by username.

    PEOPLE线: `GET /api/v4/users?username={u}` returns a list; the entry
    whose username matches (case-insensitive) is taken.
    """

    source_domain = "gitlab.com"
    source_type = "people_gitlab_public_profile"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        username = urllib.parse.quote(keyword.strip())
        return f"https://gitlab.com/api/v4/users?username={username}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, list):
            return {"parse_error": True}
        user = data[0] if data and isinstance(data[0], dict) else None
        if not user:
            return {"user_found": False, "data_note": "GitLab 无此用户名"}
        return {
            "user_found": True,
            "id": user.get("id"),
            "username": user.get("username", ""),
            "name": user.get("name", ""),
            "bio": (user.get("bio") or "")[:300],
            "location": user.get("location", ""),
            "public_repos": user.get("projects_count", user.get("public_repos", 0)),
            "followers": user.get("followers", 0),
            "created_at": user.get("created_at", ""),
            "web_url": user.get("web_url", ""),
            "data_note": "GitLab 公开用户档案 — 当事人主动公开",
        }


class DockerHubUserLookup(SafeResearchAdapter):
    """DockerHub public user profile.

    PEOPLE线: `GET /v2/users/{u}/` → full name, location, company.
    404 (user not found) surfaces as user_found=False, not an error.
    """

    source_domain = "hub.docker.com"
    source_type = "people_dockerhub_public_profile"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _check_robots(self) -> bool:
        """Evaluate robots.txt with the identifying User-Agent.

        Rationale (documented, auditable): the base-class check uses the
        default Python-urllib UA, which hub.docker.com answers with HTTP 403;
        Python's robotparser treats 403 as disallow-all, producing a false
        block. With the identifying User-Agent, robots.txt fetches fine and
        is fully permissive (`User-agent: *` / empty `Disallow:`).
        """
        import urllib.request

        try:
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers=self._build_headers(),
            )
            body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
            parser = __import__("urllib.robotparser", fromlist=["RobotFileParser"]).RobotFileParser()
            parser.parse(body.splitlines())
            return parser.can_fetch(
                "WallstreetTieling/0.6", f"https://{self.source_domain}/"
            )
        except Exception:
            return True

    def _build_url(self, keyword: str, **params) -> str:
        username = urllib.parse.quote(keyword.strip())
        return f"https://hub.docker.com/v2/users/{username}/"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict) or not data.get("username"):
            return {"user_found": False, "data_note": "DockerHub 无此用户名"}
        return {
            "user_found": True,
            "username": data.get("username", ""),
            "full_name": data.get("full_name", ""),
            "location": data.get("location", ""),
            "company": data.get("company", ""),
            "profile_url": data.get("profile_url", ""),
            "date_joined": data.get("date_joined", ""),
            "data_note": "DockerHub 公开用户档案 — 当事人主动公开",
        }

    def query(self, keyword: str, **params) -> dict[str, Any]:
        # DockerHub returns 404 for unknown users; normalize to user_found=False.
        import hashlib
        import time

        start = time.monotonic()
        username = keyword.strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=username, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(username, "robots_txt_disallowed")
        url = self._build_url(username, **params)
        status, raw_data, error = self._execute_query(url, self._build_headers())
        if status == 404:
            fields: dict[str, Any] = {"user_found": False, "data_note": "DockerHub 无此用户名"}
            status, error = 200, ""
        else:
            fields = self._extract_public_fields(raw_data) if raw_data else {}
        self._record_audit(keyword=username, url=url, status=status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(username.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "fields": fields,
            "field_count": len(fields),
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }


class NpmAuthorSearch(SafeResearchAdapter):
    """npm registry: packages authored by a username.

    IP_TECH线: `/-/v1/search?text=author:{u}&size=N` → package names,
    versions, descriptions, monthly downloads. Publishing footprint.
    """

    source_domain = "registry.npmjs.org"
    source_type = "people_npm_publish_footprint"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        author = urllib.parse.quote(keyword.strip())
        size = max(1, min(int(params.get("size", 10)), 50))
        return f"https://registry.npmjs.org/-/v1/search?text=author:{author}&size={size}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        objects = data.get("objects", []) or []
        packages: list[dict[str, Any]] = []
        for obj in objects[:10]:
            if not isinstance(obj, dict):
                continue
            pkg = obj.get("package", {}) if isinstance(obj.get("package"), dict) else {}
            downloads = obj.get("downloads", {}) if isinstance(obj.get("downloads"), dict) else {}
            packages.append({
                "name": pkg.get("name", ""),
                "version": pkg.get("version", ""),
                "description": (pkg.get("description") or "")[:150],
                "keywords": list(pkg.get("keywords") or [])[:8],
                "monthly_downloads": downloads.get("monthly", 0),
                "date": pkg.get("date", ""),
            })
        packages.sort(key=lambda p: p["monthly_downloads"], reverse=True)
        return {
            "total_packages": data.get("total", len(packages)),
            "packages": packages,
            "data_note": "npm 公开包作者记录 — 当事人主动发布",
        }


class CratesIoSearch(SafeResearchAdapter):
    """crates.io: Rust crates matching a query.

    IP_TECH线: `/api/v1/crates?q={q}&per_page=N` → names, descriptions,
    total/recent downloads. crates.io API policy requires a User-Agent
    header (base _build_headers supplies an identifying one).
    """

    source_domain = "crates.io"
    source_type = "people_cratesio_publish_footprint"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        per_page = max(1, min(int(params.get("per_page", 10)), 50))
        return f"https://crates.io/api/v1/crates?q={query}&per_page={per_page}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        crates = data.get("crates", []) or []
        items: list[dict[str, Any]] = []
        for crate in crates[:10]:
            if not isinstance(crate, dict):
                continue
            items.append({
                "name": crate.get("name", ""),
                "description": (crate.get("description") or "")[:150],
                "downloads": crate.get("downloads", 0),
                "recent_downloads": crate.get("recent_downloads", 0),
                "created_at": crate.get("created_at", ""),
                "updated_at": crate.get("updated_at", ""),
            })
        items.sort(key=lambda c: c["downloads"], reverse=True)
        return {
            "total_crates": (data.get("meta", {}) or {}).get("total", len(items)),
            "crates": items,
            "data_note": "crates.io 公开包记录 — 当事人主动发布",
        }
