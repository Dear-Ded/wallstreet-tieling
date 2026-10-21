#!/usr/bin/env python3
"""ENS（Ethereum Name Service）双向身份反查适配器。

回答："这个 .eth 名字绑定了哪个以太坊地址？/ 这个地址反向解析出什么名字？"

Survey（2026-10-21 实测）：
    - https://api.ensideas.com/ens/resolve/<name|address> → 双向 200，
      无 key、无认证、无注册。vitalik.eth ↔
      0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 双向验证通过。
    - 公共 RPC eth_call 路径（ethereum.publicnode.com / cloudflare-eth.com）
      实测不稳定（参数解析报错 / Internal error），弃用为主路径，
      仅在 docstring 记录为备选。
    - api.ensideas.com 历史上有不稳定记录：adapter 对非 200 / 解析失败
      做优雅降级（resolved=False），不硬崩。

Association 价值与诚实边界：
    - 能覆盖：链上身份别名（人可读名字 ↔ 地址），是"链上身份"lane 的
      主键，可 pivot 到 POAP/NFT/链上交易等其他链上数据源。
    - 不能替代：地址的真实世界归属——ENS 名字是用户自选的公开别名，
      名字≠实名；一个地址可有多个名字、一个名字历史上可换过主人。
      所有命中均为 leads，按"用户自声明链上别名"证据等级处理。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API_BASE = "https://api.ensideas.com/ens/resolve/"


def _safe_str(v: Any, limit: int = 200) -> str:
    return str(v or "")[:limit]


def _looks_like_address(s: str) -> bool:
    s = s.strip()
    if not s.startswith("0x") or len(s) != 42:
        return False
    try:
        int(s[2:], 16)
        return True
    except ValueError:
        return False


class ENSLookup(SafeResearchAdapter):
    """ENS 双向反查：.eth 名字 ↔ 以太坊地址（公开绑定，用户自声明别名）。"""

    source_domain = "api.ensideas.com"
    source_type = "identity_ens_lookup"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        q = keyword.strip()
        return _API_BASE + urllib.parse.quote(q, safe="")

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public ENS reverse lookup)",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"resolved": False, "parse_error": True}
        if not isinstance(data, dict):
            return {"resolved": False, "parse_error": True, "data_note": "unexpected response shape"}
        name = _safe_str(data.get("name"), 128)
        address = _safe_str(data.get("address"), 64)
        resolved = bool(name and _looks_like_address(address))
        return {
            "resolved": resolved,
            "name": name,
            "address": address,
            "display_name": _safe_str(data.get("displayName"), 128),
            "avatar": _safe_str(data.get("avatar"), 300),
            "data_note": (
                "ENS 名字是地址持有人的公开自选别名（链上身份主键），"
                "名字≠实名归属；未解析出≠该主体无链上身份。"
                "第三方解析服务（ensideas），结果以链上为准复核。"
            ),
        }

    @staticmethod
    def parse_lookup_result(raw: Any) -> dict[str, Any]:
        """供测试与外部调用的纯函数解析入口（离线可测）。"""
        inst = ENSLookup.__new__(ENSLookup)
        return ENSLookup._extract_public_fields(inst, raw)
