#!/usr/bin/env python3
"""Blockscout 链上交易对手查询适配器（免 key 公开面）。

回答："这个地址/EVM 钱包最近跟谁频繁交易？→ 链上关联信号（弱关联）。"

Endpoint: GET https://eth.blockscout.com/api/v2/addresses/{address}/transactions
    Blockscout 公开实例（以太坊主网），无 key、无认证。
    实测（2026-10-21）：免 key 返回 200，每页 50 笔交易（cursor 分页），
    字段 from.hash / to.hash / timestamp / value；robots.txt 对 /api 无
    Disallow（User-agent: * Allow: /，仅封 /auth/*、/account/* 等）。
    注意 v2 接口分页用 cursor（next_page_params），不支持 limit 参数。

ENS：输入 `xxx.eth` 时经 https://api.ensideas.com/ens/resolve/<name>
    做免 key 解析（兄弟 lane 的 public_ens_lookup 同源，200 实测通过）；
    解析失败则返回 ens_resolve_failed，不继续查交易。

Etherscan 官方 API 现需 API key（注册）→ 按红线判死，不用；
Blockscout 公开实例是合规替代。

Association 价值：
    - 同一地址的交易对手按出现次数排序 → onchain_counterparty（弱关联）；
    - 合约创建交易（to 为空）跳过；seed 自身跳过；
    - 只读第一页（50 笔），结论明确标注"近 50 笔扫描"，不做全量画像。

红线：只读公开端点；不登录；不碰需 key 的 Etherscan；
限频 5s；单次 query 最多 2 个 HTTP 请求（ENS 解析 + 交易页）。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
所有命中均为 leads：频繁交易对手≠现实关联人。
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API_BASE = "https://eth.blockscout.com/api/v2/addresses"
_ENS_RESOLVE = "https://api.ensideas.com/ens/resolve/{}"
_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ENS_RE = re.compile(r"^[a-z0-9\-]+\.eth$", re.IGNORECASE)
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"


def _norm_addr(a: Any) -> str:
    s = str(a or "").strip()
    return s.lower() if _ADDR_RE.match(s) else ""


class BlockscoutAddressLookup(SafeResearchAdapter):
    """EVM 地址 → 近期交易对手 Top-N（Blockscout 公开实例，免 key）。"""

    source_domain = "eth.blockscout.com"
    source_type = "blockchain_explorer"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def _build_url(self, keyword: str, **params) -> str:
        addr = _norm_addr(keyword)
        return f"{_API_BASE}/{addr}/transactions"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.6 (research; public blockscout query)",
            "Accept": "application/json",
        }

    def query(self, keyword: str, **params: Any) -> dict[str, Any]:
        """地址直查；xxx.eth 先做免 key ENS 解析。"""
        kw = (keyword or "").strip()
        ens_name = ""
        if _ENS_RE.match(kw):
            ens_name = kw.lower()
            resolved = self._resolve_ens(ens_name)
            if not resolved:
                self._record_audit(keyword=kw, url=_ENS_RESOLVE.format(
                    urllib.parse.quote(ens_name)), status=0,
                    fields=[], robots_allowed=True)
                return {
                    "query_subject_hash": "",
                    "source_domain": self.source_domain,
                    "source_type": self.source_type,
                    "data_boundary": self.data_boundary,
                    "response_status": 0,
                    "fields": {"ens_name": ens_name, "ens_resolve_failed": True},
                    "field_count": 2,
                    "error": "ens_resolve_failed",
                    "duration_ms": 0,
                }
            kw = resolved
        if not _ADDR_RE.match(kw):
            return {
                "query_subject_hash": "",
                "source_domain": self.source_domain,
                "source_type": self.source_type,
                "data_boundary": self.data_boundary,
                "response_status": 0,
                "fields": {},
                "field_count": 0,
                "error": "invalid_input: want 0x-address or xxx.eth",
                "duration_ms": 0,
            }
        # seed 透传给 _extract_public_fields（基类 query 只传 raw_data）。
        # 并发说明：同一 adapter 实例在引擎 fan-out 中每 attr 仅一 job，
        # depth2 不调用本 adapter；实例级暂存安全。
        self._seed_addr = kw.lower()
        out = super().query(kw, **params)
        fields = out.get("fields") or {}
        if ens_name and isinstance(fields, dict):
            fields["ens_name"] = ens_name
            out["field_count"] = len(fields)
        return out

    @staticmethod
    def _resolve_ens(name: str) -> str:
        """api.ensideas.com 免 key 解析，失败返回 ''。"""
        try:
            req = urllib.request.Request(
                _ENS_RESOLVE.format(urllib.parse.quote(name)),
                headers={"User-Agent": "wallstreet-tieling/0.6 (research; ens resolve)",
                         "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            addr = _norm_addr((data or {}).get("address"))
            return addr
        except Exception:
            return ""

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        items = data.get("items")
        if not isinstance(items, list):
            return {"lookup_failed": True,
                    "api_note": str(data.get("errors", ""))[:200]}

        seed = getattr(self, "_seed_addr", "") or ""
        return self.parse_transactions(items, seed_hint=seed)

    # -- 核心解析（纯函数，可独立测试/复用） -----------------------------

    @staticmethod
    def parse_transactions(items: list[dict[str, Any]],
                           seed_hint: str = "") -> dict[str, Any]:
        """交易列表 → 对手方计数。seed_hint 为查询地址（小写归一）。"""
        seed = (seed_hint or "").lower()
        counterparties: dict[str, dict[str, Any]] = {}
        scanned = 0
        for t in items:
            if not isinstance(t, dict):
                continue
            scanned += 1
            frm = _norm_addr((t.get("from") or {}).get("hash"))
            to = _norm_addr((t.get("to") or {}).get("hash"))
            ts = t.get("timestamp") or ""
            if not seed:
                continue  # 无 seed 无法定向对手方
            other, direction = "", ""
            if frm == seed and to and to != seed:
                other, direction = to, "sent"
            elif to == seed and frm and frm != seed:
                other, direction = frm, "received"
            else:
                continue  # 自转 / 合约创建(to 为空) / 与 seed 无关
            if not other or other == _ZERO_ADDR:
                continue
            cp = counterparties.setdefault(other, {
                "address": other, "tx_count": 0, "sent": 0, "received": 0,
                "first_seen": ts, "last_seen": ts,
            })
            cp["tx_count"] += 1
            if direction == "sent":
                cp["sent"] += 1
            else:
                cp["received"] += 1
            if ts:
                if not cp["first_seen"] or ts < cp["first_seen"]:
                    cp["first_seen"] = ts
                if not cp["last_seen"] or ts > cp["last_seen"]:
                    cp["last_seen"] = ts

        ranked = sorted(counterparties.values(),
                        key=lambda c: c["tx_count"], reverse=True)[:20]
        return {
            "chain": "ethereum",
            "explorer": "eth.blockscout.com",
            "explorer_url": ("https://eth.blockscout.com/address/" + seed) if seed else "",
            "transactions_scanned": scanned,
            "unique_counterparties": len(counterparties),
            "counterparties": ranked,
            "data_note": (
                "仅扫描第一页（近 50 笔交易）；频繁交易对手是弱关联 lead，"
                "≠现实关联人；交易所/路由合约等公共对手方需人工排除"
            ),
        }
