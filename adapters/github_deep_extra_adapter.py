#!/usr/bin/env python3
"""GitHub 深挖补充适配器（commit 作者邮箱 + star 技术口味画像）。

回答："这个 GitHub 用户在公开 commit 里留过哪些作者邮箱？/
他 star 了哪些仓库（技术口味）？"

Survey（2026-10-21 实测，未登录）：
    - GET /repos/{owner}/{repo}/commits?author=<login>&per_page=N → 200，
      commit.commit.author.email / committer.email 可见。
    - GET /users/<login>/starred?per_page=100 → 200，仓库语言/topics 可见。
    - /search/commits 需 token → 判死，不用。
    与现有 GitHubDeepEnrichment（profile/repos/orgs/events）无字段重复，
    是其补充：邮箱线索 + star 画像。

用量纪律（匿名 60 req/h）：
    - 单次 query 预算 ≤ 7 请求：repos 列表 1 + starred 1 + top5 仓库
      commits 5；min_request_interval=3.0。默认关闭、EXPERIMENTAL。

诚实边界：commit 作者邮箱是提交者自己写入 git config 的公开信息，
可伪造、可与账号邮箱不一致；star 列表是公开兴趣信号。均为 leads。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API = "https://api.github.com"
_MAX_COMMIT_REPOS = 5
_COMMITS_PER_REPO = 10


def _safe_str(v: Any, limit: int = 200) -> str:
    return str(v or "")[:limit]


class GitHubDeepExtra(SafeResearchAdapter):
    """GitHub 深挖补充：公开 commit 作者邮箱 + star 列表技术口味画像。"""

    source_domain = "api.github.com"
    source_type = "people_github_deep_extra"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_headers(self) -> dict[str, str]:
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

    def query(self, keyword: str, **params) -> dict[str, Any]:  # type: ignore[override]
        import hashlib

        start = time.monotonic()
        username = keyword.strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=username, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(username, "robots_txt_disallowed")

        fields: dict[str, Any] = {}
        status = 0
        error = ""
        try:
            repos = self._get(f"{_API}/users/{urllib.parse.quote(username)}/repos?per_page=100&sort=updated")
            status = repos.get("_status", 0)
            error = repos.get("_error", "")
            own_repos = [
                r for r in (repos.get("_body") or [])
                if isinstance(r, dict) and not r.get("fork")
            ][:_MAX_COMMIT_REPOS]
            emails = self._collect_commit_emails(username, own_repos)
            fields["commit_author_emails"] = emails
            starred = self._get(f"{_API}/users/{urllib.parse.quote(username)}/starred?per_page=100")
            fields["starred_profile"] = self._summarize_starred(starred.get("_body"))
            fields["scanned_repos"] = [
                {"owner": r.get("owner", {}).get("login", ""), "name": r.get("name", "")}
                for r in own_repos
            ]
        except Exception as exc:  # noqa: BLE001 - 网络错误归一化
            error = f"{type(exc).__name__}: {exc}"
        fields["data_note"] = (
            "commit 作者邮箱是提交者自填的公开 git 信息，可伪造、"
            "可与账号邮箱不一致；star 列表是公开技术兴趣信号。均为 leads。"
            f"单次查询 ≤ {2 + _MAX_COMMIT_REPOS} 请求，匿名额度 60 req/h。"
        )
        self._record_audit(
            keyword=username, url=self._build_url(username),
            status=status, fields=list(fields.keys()),
        )
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

    # -- 内部抓取 ------------------------------------------------------
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

    def _collect_commit_emails(self, username: str, repos: list[dict[str, Any]]) -> dict[str, Any]:
        """扫描 top 仓库中该用户署名的 commit，收集去重的作者/提交者邮箱。"""
        emails: dict[str, dict[str, Any]] = {}
        repos_scanned = 0
        commits_scanned = 0
        for repo in repos:
            owner = (repo.get("owner") or {}).get("login", "")
            name = repo.get("name", "")
            if not owner or not name:
                continue
            url = (
                f"{_API}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}"
                f"/commits?author={urllib.parse.quote(username)}&per_page={_COMMITS_PER_REPO}"
            )
            resp = self._get(url)
            body = resp.get("_body")
            if not isinstance(body, list):
                continue
            repos_scanned += 1
            for commit in body:
                if not isinstance(commit, dict):
                    continue
                commits_scanned += 1
                c = commit.get("commit") or {}
                for role in ("author", "committer"):
                    who = c.get(role) or {}
                    email = _safe_str(who.get("email"), 128)
                    cname = _safe_str(who.get("name"), 128)
                    if email and "@" in email and "noreply" not in email.lower():
                        ent = emails.setdefault(email, {"email": email, "names": [], "roles": [], "repos": []})
                        if cname and cname not in ent["names"]:
                            ent["names"].append(cname)
                        if role not in ent["roles"]:
                            ent["roles"].append(role)
                        repo_full = f"{owner}/{name}"
                        if repo_full not in ent["repos"]:
                            ent["repos"].append(repo_full)
        return {
            "repos_scanned": repos_scanned,
            "commits_scanned": commits_scanned,
            "emails": list(emails.values()),
            "email_count": len(emails),
        }

    @staticmethod
    def _summarize_starred(body: Any) -> dict[str, Any]:
        if not isinstance(body, list):
            return {"star_count": 0, "languages": {}, "topics": {}, "top_starred": []}
        languages: dict[str, int] = {}
        topics: dict[str, int] = {}
        top: list[dict[str, Any]] = []
        for repo in body:
            if not isinstance(repo, dict):
                continue
            lang = repo.get("language") or "unknown"
            languages[lang] = languages.get(lang, 0) + 1
            for t in (repo.get("topics") or [])[:8]:
                t = _safe_str(t, 64)
                topics[t] = topics.get(t, 0) + 1
            top.append({
                "full_name": _safe_str(repo.get("full_name"), 128),
                "description": _safe_str(repo.get("description"), 120),
                "language": lang,
                "stars": repo.get("stargazers_count", 0),
            })
        top.sort(key=lambda r: r["stars"], reverse=True)
        return {
            "star_count": len(body),
            "languages": dict(sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:10]),
            "topics": dict(sorted(topics.items(), key=lambda kv: kv[1], reverse=True)[:15]),
            "top_starred": top[:10],
        }

    @staticmethod
    def parse_starred_result(raw: Any) -> dict[str, Any]:
        """供测试的纯函数入口（离线可测）。"""
        inst = GitHubDeepExtra.__new__(GitHubDeepExtra)
        body = json.loads(raw) if isinstance(raw, str) else raw
        return GitHubDeepExtra._summarize_starred(body)
