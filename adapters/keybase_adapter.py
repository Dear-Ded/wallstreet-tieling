#!/usr/bin/env python3
"""Keybase identity-proofs adapter (PEOPLE lane).

Keybase (https://keybase.io) 让用户用加密签名把自己的各平台账号
(Twitter/X、GitHub、Reddit、HackerNews、DNS 域名、PGP 等）绑定到
同一个身份上，并全部公开可查。对尽调而言，它回答的是：

    "这个用户名声称拥有哪些平台身份？这些声称有密码学证明吗？"

lookup API: GET https://keybase.io/_/api/1.0/user/lookup.json?usernames={u}
免费、无需 key、公开数据。proofs 数组中每条含 proof_type 与 nametag，
即"该用户在某平台的账号名"——这是跨平台身份关联的强信号。

2026-10-21 deep-dive (people-unconventional p2): 同一公开端点实际返回
远超 proofs 的字段，全部纳入 extraction（同一请求，无新增调用/无鉴权）：
- profile.full_name / location / bio → person 实体解析的姓名/地点/简介；
- proofs 每条的 service_url / proof_url / sig_id（证明原文链接 + 签名链 ID）；
- stellar.primary.account_id（用户公开绑定的 Stellar 收款地址）；
- cryptocurrency_addresses（BTC 等地址 + 其 sig_id）；
- devices（设备名/类型/状态/数量，密钥 kid 保留、bundle 不落盘）；
- public_keys.primary（kid / key_type；PGP bundle 不完整存储）；
- sigs.last（sig_id / seqno / payload_hash，签名链最新锚点）。

PGP bundle 为公钥但体积大且非分析必需，仅记录 kid/key_type；
device key 的 kid 同理只保留标识，不展开。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


def _safe_str(v: Any, limit: int = 300) -> str:
    s = str(v or "")
    return s[:limit]


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
        # proofs_summary 是 {平台名: [proof, ...]} 的 dict；另有 by_sig_id /
        # by_presentation_group 两种索引视图（dict），只取 list 形态的条目。
        proof_items: list[Any] = []
        if isinstance(proofs_summary, dict):
            for plist in proofs_summary.values():
                if isinstance(plist, list):
                    proof_items.extend(plist)
        elif isinstance(proofs_summary, list):
            proof_items = proofs_summary
        seen_sig_ids: set[str] = set()
        for proof in proof_items:
            if not isinstance(proof, dict):
                continue
            ptype = str(proof.get("proof_type", ""))
            nametag = str(proof.get("nametag", ""))
            if not ptype:
                continue
            sig_id = str(proof.get("sig_id", ""))
            # by_sig_id 与按平台分组是同一批 proof 的两种视图，去重。
            if sig_id and sig_id in seen_sig_ids:
                continue
            if sig_id:
                seen_sig_ids.add(sig_id)
            proofs.append({
                "proof_type": ptype,
                "nametag": nametag,
                "state": proof.get("state"),  # 1 = ok
                "service_url": _safe_str(proof.get("service_url")),
                "proof_url": _safe_str(proof.get("proof_url")),
                "sig_id": sig_id[:64],
            })
            if nametag:
                by_platform.setdefault(ptype, []).append(nametag)

        # ---- deep fields: 同一公开响应的增量字段 ----
        profile = user.get("profile") or {}
        full_name = _safe_str(profile.get("full_name"), 128)
        location = _safe_str(profile.get("location"), 128)
        bio = _safe_str(profile.get("bio"), 1000)

        stellar = user.get("stellar") or {}
        stellar_primary = stellar.get("primary") or {}
        stellar_account = _safe_str(stellar_primary.get("account_id"), 128)

        crypto: dict[str, list[dict[str, str]]] = {}
        for currency, addrs in (user.get("cryptocurrency_addresses") or {}).items():
            if not isinstance(addrs, list):
                continue
            items = []
            for a in addrs:
                if not isinstance(a, dict):
                    continue
                addr = _safe_str(a.get("address"), 128)
                if addr:
                    items.append({
                        "address": addr,
                        "sig_id": _safe_str(a.get("sig_id"), 64),
                    })
            if items:
                crypto[_safe_str(currency, 32)] = items[:10]

        devices: list[dict[str, Any]] = []
        for dev_id, dev in (user.get("devices") or {}).items():
            if not isinstance(dev, dict):
                continue
            devices.append({
                "device_id": _safe_str(dev_id, 64),
                "name": _safe_str(dev.get("name"), 128),
                "type": _safe_str(dev.get("type"), 32),
                "status": dev.get("status"),
                "ctime": dev.get("ctime"),
            })
        devices = devices[:20]

        pk = (user.get("public_keys") or {}).get("primary") or {}
        primary_pgp = {
            "kid": _safe_str(pk.get("kid"), 128),
            "key_type": pk.get("key_type"),
            "has_bundle": bool(pk.get("bundle")),
        }

        sigs_last = (user.get("sigs") or {}).get("last") or {}
        sig_chain = {
            "last_sig_id": _safe_str(sigs_last.get("sig_id"), 64),
            "last_seqno": sigs_last.get("seqno"),
            "last_payload_hash": _safe_str(sigs_last.get("payload_hash"), 64),
        }

        return {
            "user_found": True,
            "username": basics.get("username", ""),
            "full_name": full_name or None,
            "location": location or None,
            "bio": bio or None,
            "proof_count": len(proofs),
            "proofs": proofs[:20],
            "linked_platforms": sorted(by_platform.keys()),
            "linked_identities": {k: v[:5] for k, v in by_platform.items()},
            "identity_deep": {
                "stellar_account": stellar_account or None,
                "stellar_hidden": bool(stellar.get("hidden", False)),
                "crypto_addresses": crypto,
                "devices": devices,
                "device_count": len(devices),
                "primary_pgp_key": primary_pgp,
                "sig_chain": sig_chain,
            },
            "data_note": "Keybase 公开身份证明 — 用户主动发布的跨平台绑定声明，"
                         "proof state=1 为有效证明；identity_deep 为同一公开"
                         "端点的增量字段（简介/地点/Stellar/加密币地址/设备/"
                         "PGP kid/签名链锚点）",
        }
