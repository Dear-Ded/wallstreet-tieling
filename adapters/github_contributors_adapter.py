#!/usr/bin/env python3
"""GitHub 仓库共同贡献者查询适配器（免 key 公开面）。

回答："这个仓库有哪些公开贡献者？→ 同一仓库的贡献者之间存在技术协作关联。"

Endpoint: GET https://api.github.com/repos/{owner}/{repo}/contributors?per_page=N
    文档化公开 REST API；未认证 60 req/h。实测（2026-10-21）：
    - 小仓库免 key 返回 200，字段 login / contributions / type / html_url；
    - 超大仓库（如 torvalds/linux）返回 403
      {"message": "The history or contributor list is too large ..."}，
      属文档化限制而非封禁，优雅降级为 repo_too_large。
    - 组织/机器人账号（type=Bot）在 contributors 列表中同样出现，
      关联时排除 Bot（context 标注）。

Association 价值：
    - 同一 repo 的 contributors → co_contributor（技术协作关联，review 级）；
    - 与兄弟 lane 的 public_github_deep_extra（commit 邮箱/star 画像）
      无字段重复：本 adapter 只做"同一仓库贡献者名单"。

红线：只读公开端点；不碰 /search/commits（需 token）；不登录；
限频 5s、per_page ≤ 100；匿名额度内使用。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API_BASE = "https://api.github.com/repos"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


class GithubContributorsLookup(SafeResearchAdapter):
    """GitHub 公开仓库贡献者名单：owner/repo → contributors（免 key）。"""

    source_domain = "api.github.com"
    source_type = "code_hosting_contributors"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # 匿名 60 req/h，保守

    def _build_url(self, keyword: str, **params) -> str:
        owner_repo = keyword.strip().strip("/")
        try:
            per_page = max(1, min(100, int(params.get("per_page", 30))))
        except (TypeError, ValueError):
            per_page = 30
        q = urllib.parse.urlencode({"per_page": per_page, "anon": "0"})
        return f"{_API_BASE}/{owner_repo}/contributors?{q}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.6 (research; public repo contributors query)",
            "Accept": "application/vnd.github+json",
        }

    def query(self, keyword: str, **params: Any) -> dict[str, Any]:
        """owner/repo 格式校验前置；非法输入直接返回 invalid_input。"""
        owner_repo = (keyword or "").strip().strip("/")
        if not _REPO_RE.match(owner_repo):
            return {
                "query_subject_hash": "",
                "source_domain": self.source_domain,
                "source_type": self.source_type,
                "data_boundary": self.data_boundary,
                "response_status": 0,
                "fields": {},
                "field_count": 0,
                "error": "invalid_input: want 'owner/repo'",
                "duration_ms": 0,
            }
        return super().query(owner_repo, **params)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if isinstance(data, dict):
            msg = str(data.get("message", "") or "")
            if "too large to list contributors" in msg:
                return {
                    "repo_too_large": True,
                    "data_note": "该仓库贡献者历史过大，GitHub API 拒绝列出（文档化限制）；"
                                 "未列出≠无贡献者",
                }
            if "API rate limit exceeded" in msg:
                return {"rate_limited": True,
                        "data_note": "GitHub 匿名额度用尽（60 req/h），稍后重试"}
            if data.get("message") == "Not Found":
                return {"not_found": True,
                        "data_note": "仓库不存在或为私有"}
            return {"lookup_failed": True, "api_message": msg[:200]}
        if not isinstance(data, list):
            return {"parse_error": True}

        contributors: list[dict[str, Any]] = []
        bots = 0
        for u in data:
            if not isinstance(u, dict) or not u.get("login"):
                continue
            login = str(u["login"])
            is_bot = str(u.get("type", "")).lower() == "bot"
            if is_bot:
                bots += 1
            contributors.append({
                "login": login,
                "contributions": u.get("contributions") or 0,
                "type": u.get("type") or "User",
                "is_bot": is_bot,
                "profile_url": u.get("html_url") or f"https://github.com/{login}",
            })
        contributors.sort(key=lambda c: c["contributions"], reverse=True)
        return {
            "contributor_count": len(contributors),
            "bots_excluded": bots,
            "contributors": contributors,
            "data_note": (
                "GitHub 公开贡献者名单（未认证公开 API）；"
                "contributors 是技术协作线索，按 leads 处理，Bot 账号已标注排除"
            ),
        }

    # -- 便捷方法 ------------------------------------------------------

    @staticmethod
    def parse_contributors(raw: Any) -> list[dict[str, Any]]:
        """纯解析入口（测试/离线用，不发起请求）。"""
        inst = GithubContributorsLookup.__new__(GithubContributorsLookup)
        fields = GithubContributorsLookup._extract_public_fields(inst, raw)
        return fields.get("contributors", [])
