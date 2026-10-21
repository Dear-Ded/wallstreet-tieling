"""Hunter.io 企业域名邮箱检索适配器。数据边界: fully_public

Hunter.io (hunter.io) 查询企业域名 → 公开邮箱列表 + 人员（姓名/职位/部门）。
这些邮箱是 Hunter 从公开网页爬取的已公开发布邮箱（官网、新闻稿等），
免费 tier 25 次/月。key 只走构造参数（premium_keyed 模式），永不落盘/进日志。

关联价值：企业域名 → 邮箱 → 人员姓名/职位 → 人物-企业关联链条。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class _KeyedAdapter(SafeResearchAdapter):
    """需要构造时注入 API key 的基类（key 永不进审计日志）。"""

    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)


class HunterDomainLookup(_KeyedAdapter):
    """Hunter.io domain-search：企业域名 → 公开邮箱 + 人员信息。

    API: GET https://api.hunter.io/v2/domain-search
        ?domain=<domain>&api_key=<key>&limit=10
    Free tier: 25 requests/month. key 来自 hunter.io 免费注册。
    无 key 时 query() 返回 credentials_required，不静默失败。
    """

    source_domain = "api.hunter.io"
    source_type = "infra_hunter_email_intel"
    data_boundary = "fully_public"

    def _check_robots(self) -> bool:
        # api.hunter.io is a key-authenticated API host: it serves no
        # robots.txt (301 -> HTML landing page). This adapter only calls the
        # API with an operator-supplied key, i.e. under the Hunter.io API
        # terms of service, not as a web crawler. We still attempt to fetch
        # robots.txt and honor it when a valid one is served.
        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers={"User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    return True  # no robots.txt served -> API ToS governs
                ctype = resp.headers.get("Content-Type", "")
                if "text/plain" not in ctype and "text/html" not in ctype:
                    return True
                content = resp.read().decode("utf-8", errors="ignore")
            if "<html" in content[:500].lower():
                return True  # HTML landing page, not a robots.txt
            import urllib.robotparser
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"https://{self.source_domain}/robots.txt")
            rp.parse(content.split("\n"))
            return rp.can_fetch(
                "WallstreetTieling/0.6.0",
                f"https://{self.source_domain}/v2/domain-search",
            )
        except Exception:
            return True  # unreachable -> RFC 9309 default allow

    def query_domain(self, domain: str, limit: int = 10) -> dict[str, Any]:
        """按域名查公开邮箱。"""
        return self.query(domain.strip().lower(), limit=max(1, min(limit, 100)))

    def _build_url(self, keyword: str, **params) -> str:
        domain = urllib.parse.quote(keyword.strip().lower())
        limit = params.get("limit", 10)
        return (
            f"https://api.hunter.io/v2/domain-search"
            f"?domain={domain}&limit={limit}"
            f"&api_key={urllib.parse.quote(self._api_key or '')}"
        )

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        # Read HTTPError bodies so 401/402/429 payloads parse into fields
        # instead of collapsing into a bare transport error.
        import urllib.error
        import urllib.request
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = None
            return (e.code, body, f"HTTPError: {e.code}")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"lookup_failed": True}
        errors = data.get("errors") or []
        if errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            return {
                "lookup_failed": True,
                "reason": str(first.get("details", ""))[:120],
                "error_id": first.get("id", ""),
            }
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            return {"lookup_failed": True}
        emails: list[dict[str, Any]] = []
        for e in (payload.get("emails") or [])[:20]:
            if not isinstance(e, dict):
                continue
            emails.append({
                "value": e.get("value", ""),
                "type": e.get("type", ""),
                "confidence": e.get("confidence"),
                "first_name": e.get("first_name", ""),
                "last_name": e.get("last_name", ""),
                "position": e.get("position", ""),
                "seniority": e.get("seniority", ""),
                "department": e.get("department", ""),
                "linkedin": e.get("linkedin", ""),
                "phone_number": e.get("phone_number", ""),
                "source_count": len(e.get("sources") or []),
            })
        return {
            "domain": payload.get("domain", ""),
            "organization": payload.get("organization", ""),
            "country": payload.get("country", ""),
            "email_pattern": payload.get("pattern", ""),
            "accept_all": payload.get("accept_all"),
            "disposable": payload.get("disposable"),
            "emails": emails,
            "email_count": len(emails),
            "data_note": "Hunter.io 公开爬取邮箱 — 仅用于企业联系人/人员关联线索",
        }
