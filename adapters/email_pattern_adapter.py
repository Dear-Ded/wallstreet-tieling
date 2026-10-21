#!/usr/bin/env python3
"""邮箱模式候选生成适配器（Hunter.io 的零注册替代）。

回答："已知某人姓名与公司域名，按常见命名模式，可能的邮箱地址有哪些？"

这不是"邮箱查找"，而是"模式候选生成"：
    输入 first_name + last_name + domain（或 keyword "First Last@domain"），
    输出 ~14 种常见企业邮箱命名模式的候选地址。

诚实边界（写死）：
    - 全部候选一律标注 confidence="low"，data_note 明确"未验证"。
    - 只做域名 MX 记录存在性检查（公开 DNS），证明该域名可收邮件；
      绝不做 SMTP 存活探测（VRFY/RCPT TO）——红线，不碰。
    - 不查泄露库、不做密码找回探测。
    - 候选用于"交叉验证线索"（如与 Gravatar/公开简历中的邮箱比对），
      不得作为"该邮箱属于此人"的断言。

Endpoint: 无外部 API（纯离线模式生成 + 一次 DoH MX 查询）。
data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter
from adapters.email_intel_adapter import EmailIntelLookup

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'.\- ]{0,60}$")


def _clean_token(s: str) -> str:
    """只保留 a-z0-9，供模式拼接。"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def generate_patterns(first: str, last: str) -> list[str]:
    """常见企业邮箱本地部分模式（去重保序）。"""
    f = _clean_token(first)
    l = _clean_token(last)
    if not f or not l:
        return []
    fi, li = f[0], l[0]
    cands = [
        f"{f}.{l}", f"{f}{l}", f"{f}_{l}", f"{f}-{l}",
        f"{fi}{l}", f"{f}{li}", f"{fi}.{l}", f"{f}.{li}",
        f"{l}.{f}", f"{l}{f}",
        f"{fi}{li}", f"{f}",
        f"{l}", f"{f}{l}1",
    ]
    seen: set[str] = set()
    uniq: list[str] = []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def parse_subject(keyword: str, params: dict) -> tuple[str, str, str]:
    """解析输入 → (first, last, domain)。支持 keyword 与 params 两种形态。"""
    first = str(params.get("first_name", "")).strip()
    last = str(params.get("last_name", "")).strip()
    domain = str(params.get("domain", "")).strip().lower()
    kw = keyword.strip()
    if "@" in kw:
        name_part, _, dom = kw.partition("@")
        domain = domain or dom.strip().lower()
        parts = name_part.strip().split()
        if len(parts) >= 2 and not first:
            first, last = parts[0], " ".join(parts[1:])
        elif len(parts) == 1 and not first:
            first = parts[0]
    return first, last, domain


class EmailPatternLookup(SafeResearchAdapter):
    """姓名+域名 → 常见邮箱命名模式候选（全部低置信度，未验证）。"""

    source_domain = "email_pattern_generator"
    source_type = "people_email_pattern_candidates"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        first, last, domain = parse_subject(keyword, params)
        return f"email-pattern://{urllib.parse.quote(first)}.{urllib.parse.quote(last)}@{urllib.parse.quote(domain)}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        return raw_data if isinstance(raw_data, dict) else {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        import time

        start = time.monotonic()
        first, last, domain = parse_subject(keyword, params)
        self._enforce_rate_limit()
        fields: dict[str, Any] = {
            "first_name": first,
            "last_name": last,
            "domain": domain,
            "confidence": "low",
        }
        if not (_NAME_RE.match(first) and _NAME_RE.match(last) and "." in domain):
            fields["candidates"] = []
            fields["data_note"] = "输入无效：需要拉丁字母姓名与有效域名（名 姓@域名）"
        else:
            locals_ = generate_patterns(first, last)
            mx_ok = EmailIntelLookup._check_mx(domain)
            fields["domain_has_mx"] = mx_ok
            fields["candidates"] = [
                {"email": f"{local}@{domain}", "pattern": local, "confidence": "low"}
                for local in locals_
            ]
            fields["candidate_count"] = len(fields["candidates"])
            fields["data_note"] = (
                "模式候选，未验证：SMTP 存活探测被红线禁止，不做。候选仅用于交叉验证线索"
                "（如与公开简历/Gravatar 中的邮箱比对），不得断言归属。"
            )
        self._record_audit(
            keyword=keyword, url=self._build_url(keyword, **params),
            status=200, fields=list(fields.keys()),
        )
        return {
            "query_subject_hash": "",
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 200,
            "fields": fields,
            "field_count": len(fields),
            "error": "",
            "duration_ms": (time.monotonic() - start) * 1000,
        }
