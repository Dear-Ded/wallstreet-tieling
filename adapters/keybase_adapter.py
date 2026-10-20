#!/usr/bin/env python3
"""Keybase identity-proofs adapter (PEOPLE lane).

Keybase (https://keybase.io) 让用户用加密签名把自己的各平台账号
(Twitter/X、GitHub、Reddit、HackerNews、DNS 域名、PGP 等）绑定到
同一个身份上，并全部公开可查。对尽调而言，它回答的是：

    "这个用户名声称拥有哪些平台身份？这些声称有密码学证明吗？"

lookup API: GET https://keybase.io/_/api/1.0/user/lookup.json?usernames={u}
免费、无需 key、公开数据。proofs 数组中每条含 proof_type 与 nametag，
即"该用户在某平台的账号名"——这是跨平台身份关联的强信号。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class KeybaseIdentityLookup(SafeResearchAdapter):
    """Keybase public identity + cryptographic proofs for a username."""

    source_domain = "keybase.io"
    source_type = "people_keybase_identity_proofs"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        username = urllib.parse.quote(keyword.strip().lower())
        return f"https://keybase.io/_/api/1.0/user/lookup.json?usernames={username}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        them = data.get("them") or []
        if not them:
            return {"user_found": False}
        user = them[0] if isinstance(them[0], dict) else {}
        basics = user.get("basics") or {}
        proofs: list[dict[str, Any]] = []
        by_platform: dict[str, list[str]] = {}
        proofs_summary = user.get("proofs_summary") or {}
        # proofs_summary 是 {平台名: [proof, ...]} 的 dict
        proof_items: list[Any] = []
        if isinstance(proofs_summary, dict):
            for plist in proofs_summary.values():
                if isinstance(plist, list):
                    proof_items.extend(plist)
        elif isinstance(proofs_summary, list):
            proof_items = proofs_summary
        for proof in proof_items:
            if not isinstance(proof, dict):
                continue
            ptype = str(proof.get("proof_type", ""))
            nametag = str(proof.get("nametag", ""))
            if not ptype:
                continue
            proofs.append({
                "proof_type": ptype,
                "nametag": nametag,
                "state": proof.get("state"),  # 1 = ok
            })
            if nametag:
                by_platform.setdefault(ptype, []).append(nametag)
        return {
            "user_found": True,
            "username": basics.get("username", ""),
            "proof_count": len(proofs),
            "proofs": proofs[:20],
            "linked_platforms": sorted(by_platform.keys()),
            "linked_identities": {k: v[:5] for k, v in by_platform.items()},
            "data_note": "Keybase 公开身份证明 — 用户主动发布的跨平台绑定声明，proof state=1 为有效证明",
        }
