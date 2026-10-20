#!/usr/bin/env python3
"""Email intelligence adapter for people-focused due diligence.

Given an email address, this adapter answers only questions that are
answerable from public infrastructure and the subject's own public
choices:

- 格式与域名有效性：syntax check + MX record existence (does the domain
  actually receive mail?)
- Gravatar 注册检查：the subject chose to register a public avatar —
  ``https://www.gravatar.com/avatar/{md5}?d=404`` returns 200 iff registered.
- 一次性邮箱识别：offline list of known throwaway domains.
- 角色账号识别：admin@/support@/... are functional, not personal.

What this adapter deliberately does NOT do:
- No breach-data ("社工库") queries of any kind.
- No mailbox-existence probing (SMTP VRFY / RCPT TO fishing).
- No password-reset or account-recovery probing.

All checks are public, credential-free, and auditable. Default-off,
EXPERIMENTAL in the connector registry.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$"
)

_ROLE_PREFIXES = frozenset({
    "admin", "administrator", "support", "info", "contact", "hello",
    "sales", "marketing", "billing", "noreply", "no-reply", "postmaster",
    "webmaster", "abuse", "security", "hr", "careers", "press", "media",
})

# Curated offline list of well-known disposable-email domains.
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "throwawaymail.com", "yopmail.com", "temp-mail.org", "fakeinbox.com",
    "trashmail.com", "dispostable.com", "getnada.com", "mohmal.com",
    "emailondeck.com", "mytemp.email", "tempail.com", "sharklasers.com",
})


class EmailIntelLookup(SafeResearchAdapter):
    """Public-infrastructure email intelligence.

    PEOPLE线: 邮箱真实性核验 — 格式、MX 记录、Gravatar 注册、一次性邮箱、
    角色账号。全部基于公开基础设施与当事人主动公开的选择。
    """

    source_domain = "public_email_infrastructure"
    source_type = "people_email_intelligence"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        # Not a single-URL source; query() is overridden to fan out.
        return f"email-intel://{urllib.parse.quote(keyword.strip().lower())}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        return raw_data if isinstance(raw_data, dict) else {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        import time

        start = time.monotonic()
        email = keyword.strip().lower()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=email, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(email, "robots_txt_disallowed")
        fields = self._analyze(email)
        self._record_audit(
            keyword=email, url=self._build_url(email),
            status=200 if fields.get("syntax_valid") else 0,
            fields=list(fields.keys()),
        )
        return {
            "query_subject_hash": hashlib.sha256(email.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 200,
            "fields": fields,
            "field_count": len(fields),
            "error": "",
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def _analyze(self, email: str) -> dict[str, Any]:
        syntax_valid = bool(_EMAIL_RE.match(email))
        local, _, domain = email.partition("@") if syntax_valid else ("", "", "")
        fields: dict[str, Any] = {
            "syntax_valid": syntax_valid,
            "local_part": local,
            "domain": domain,
        }
        if not syntax_valid:
            fields["data_note"] = "邮箱格式无效 — 后续检查跳过"
            return fields
        fields["is_role_account"] = local.split("+")[0] in _ROLE_PREFIXES
        fields["is_disposable"] = domain in _DISPOSABLE_DOMAINS
        fields["has_mx_record"] = self._check_mx(domain)
        fields["gravatar_registered"] = self._check_gravatar(email)
        fields["data_note"] = (
            "公开基础设施核验：MX 记录存在性、Gravatar 主动注册、当事人可验证的选择；"
            "不做邮箱存活探测、不查泄露库"
        )
        return fields

    @staticmethod
    def _check_mx(domain: str) -> bool:
        """True if the domain publishes at least one MX record (via DNS-over-HTTPS).

        Uses Google's DoH JSON API instead of shelling out to nslookup:
        no binary dependency, no locale-dependent output parsing.
        """
        import json
        import urllib.request

        url = f"https://dns.google/resolve?name={urllib.parse.quote(domain)}&type=MX"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data.get("Status") == 0 and bool(data.get("Answer"))
        except Exception:
            return False

    @staticmethod
    def _check_gravatar(email: str) -> bool:
        """True if the email hash has a Gravatar registered (d=404 trick)."""
        import urllib.request

        digest = hashlib.md5(email.encode()).hexdigest()
        url = f"https://www.gravatar.com/avatar/{digest}?d=404"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception:
            return False
