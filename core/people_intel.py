#!/usr/bin/env python3
"""People-intelligence fan-out orchestrator.

Ties the PEOPLE-lane adapters into a single investigation call:

    orchestrator = PeopleIntelOrchestrator(
        email_adapter=EmailIntelLookup(),          # optional
        github_adapter=GitHubDeepEnrichment(),    # optional
        officer_adapter=OpenCorporatesOfficerLookup(api_token=...),  # optional
    )
    lead_graph = orchestrator.investigate(
        name="Jane Doe", email="jane@example.com", github_username="janedoe",
    )

Design rules (per project house rules):
- Adapters are injected, never constructed here: the caller decides what is
  enabled. Nothing runs by default.
- Every adapter failure degrades to a per-source error entry; one source
  never breaks the whole investigation.
- Cross-source corroboration only produces *leads* ("A 与 B 一致"), never
  identity assertions.
- No breach data, no mailbox probing, no pretexting — the adapters themselves
  exclude those by design; the orchestrator adds no new collection surface.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class PersonQuery:
    name: str | None = None
    email: str | None = None
    username: str | None = None
    github_username: str | None = None


def _safe_int(value: Any) -> int:
    """int() that never raises — orchestrator corroboration must not crash."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


@dataclass
class PeopleIntelOrchestrator:
    email_adapter: Any = None
    github_adapter: Any = None
    officer_adapter: Any = None
    username_adapter: Any = None  # e.g. MassCrossPlatformProfiler (needs explicit enable())
    social_adapter: Any = None  # object with query(q); e.g. HackerNewsAlgoliaSearch

    def investigate(self, query: PersonQuery | dict[str, Any]) -> dict[str, Any]:
        if isinstance(query, dict):
            query = PersonQuery(**{k: query.get(k) for k in
                                   ("name", "email", "username", "github_username")})
        start = time.monotonic()
        sources: dict[str, Any] = {}

        if query.email and self.email_adapter is not None:
            sources["email_intel"] = self._safe_run(
                self.email_adapter, "query", query.email)
        if query.github_username and self.github_adapter is not None:
            sources["github_deep"] = self._safe_run(
                self.github_adapter, "query", query.github_username)
        if query.name and self.officer_adapter is not None:
            sources["officer_records"] = self._safe_run(
                self.officer_adapter, "query", query.name)
        if query.username and self.username_adapter is not None:
            sources["username_footprint"] = self._safe_run_username(
                self.username_adapter, query.username)
        if query.name and self.social_adapter is not None:
            sources["social_listening"] = self._safe_run(
                self.social_adapter, "query", query.name)

        corroborations = self._corroborate(query, sources)
        subject_hash = hashlib.sha256(
            "|".join(x or "" for x in
                     (query.name, query.email, query.username,
                      query.github_username)).encode()
        ).hexdigest()[:12]
        return {
            "type": "people_lead_graph",
            "subject_hash": subject_hash,
            "identifiers_provided": {
                k: bool(v) for k, v in {
                    "name": query.name, "email": query.email,
                    "username": query.username,
                    "github_username": query.github_username,
                }.items()
            },
            "sources": sources,
            "source_count": len(sources),
            "corroborations": corroborations,
            "policy": (
                "所有来源均为当事人主动公开或公开基础设施数据；"
                "corroborations 仅为线索提示，不做身份断言；"
                "人物级事实断言需 exact/strong 主体匹配与复核。"
            ),
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    @staticmethod
    def _safe_run(adapter: Any, method: str, arg: str) -> dict[str, Any]:
        try:
            result = getattr(adapter, method)(arg)
            if isinstance(result, dict):
                return result
            return {"error": "unexpected_result_shape"}
        except Exception as exc:  # noqa: BLE001 - per-source degradation
            return {"error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _safe_run_username(adapter: Any, username: str) -> dict[str, Any]:
        """Username adapters expose massive_cross_check(); plain query() is the fallback."""
        try:
            if hasattr(adapter, "massive_cross_check"):
                result = adapter.massive_cross_check(username)
            else:
                result = adapter.query(username)
            if isinstance(result, dict):
                return result
            return {"error": "unexpected_result_shape"}
        except Exception as exc:  # noqa: BLE001 - per-source degradation
            return {"error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _corroborate(query: PersonQuery, sources: dict[str, Any]) -> list[dict[str, str]]:
        leads: list[dict[str, str]] = []
        email_fields = (sources.get("email_intel") or {}).get("fields", {})
        github_fields = (sources.get("github_deep") or {}).get("fields", {})
        officer_fields = (sources.get("officer_records") or {}).get("fields", {})

        # 1) GitHub 公开公司域名 vs 邮箱域名
        email_domain = str(email_fields.get("domain") or "")
        company = str((github_fields.get("profile") or {}).get("company") or "")
        if email_domain and company and email_domain.split(".")[0] in company.lower().replace(" ", ""):
            leads.append({
                "type": "domain_company_consistent",
                "detail": f"邮箱域名 {email_domain} 与 GitHub 公开公司 {company} 指向同一组织（线索，非断言）",
            })

        # 2) 任职记录中的公司名 vs GitHub 公开组织
        officer_samples = officer_fields.get("samples") or []
        github_orgs = {(o.get("login") or "").lower()
                       for o in (github_fields.get("affiliations") or {}).get("orgs", [])}
        for sample in officer_samples[:5]:
            company_name = str(sample.get("company_name") or "")
            if company_name and any(
                    token in company_name.lower() for token in github_orgs if token):
                leads.append({
                    "type": "officer_org_consistent",
                    "detail": f"任职记录公司 {company_name} 与 GitHub 公开组织存在交集（线索，非断言）",
                })
                break

        # 3) 一次性邮箱 / 角色账号风险提示
        if email_fields.get("is_disposable"):
            leads.append({
                "type": "disposable_email_flag",
                "detail": "一次性邮箱 — 该身份标识可信度低，建议要求更强的主体证据",
            })
        if email_fields.get("is_role_account"):
            leads.append({
                "type": "role_account_note",
                "detail": "角色账号（非个人）— 不适合作为个人身份锚点",
            })
        # 4) 用户名跨平台足迹 vs GitHub 用户名
        footprint_fields = (sources.get("username_footprint") or {}).get("fields", {})
        by_category = footprint_fields.get("by_category") or {}
        hit_platforms = {p for plats in by_category.values() for p in plats}
        if "GitHub" in hit_platforms and query.github_username:
            if query.username and query.username.lower() == query.github_username.lower():
                leads.append({
                    "type": "username_github_consistent",
                    "detail": f"用户名 {query.username} 在 GitHub 公开存在，与提供的 GitHub 用户名一致（线索，非断言）",
                })
        if footprint_fields.get("platforms_found"):
            leads.append({
                "type": "username_footprint_summary",
                "detail": f"用户名 {query.username or ''} 在 {footprint_fields.get('platforms_found')} 个公开平台有档案（{footprint_fields.get('coverage_ratio', '')}）",
            })
        # 5) 社区讨论信号：公开技术社区中提及该姓名
        social_fields = (sources.get("social_listening") or {}).get("fields", {})
        social_hits = _safe_int(social_fields.get("total_hits")) or _safe_int(
            social_fields.get("total_questions"))
        if social_hits > 0 and PeopleIntelOrchestrator._name_mentioned(query.name, social_fields):
            leads.append({
                "type": "social_mention_signal",
                "detail": f"公开技术社区中有 {social_hits} 条提及 {query.name} 的讨论（线索，非断言）",
            })
        return leads

    @staticmethod
    def _name_mentioned(name: str | None, fields: dict[str, Any]) -> bool:
        """True if any returned story/question title mentions the name."""
        if not name:
            return False
        needle = name.strip().lower()
        if not needle:
            return False
        titles: list[str] = []
        for key in ("stories", "questions"):
            for item in fields.get(key) or []:
                if isinstance(item, dict):
                    titles.append(str(item.get("title") or ""))
        return any(needle in title.lower() for title in titles if title)
