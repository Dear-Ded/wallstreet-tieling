#!/usr/bin/env python3
"""POAP（Proof of Attendance Protocol）徽章持有查询适配器。

回答："这个以太坊地址持有过哪些 POAP？→ 线下活动/兴趣图谱。"

Survey（2026-10-21 实测）：
    - 官方文档化接口 https://api.poap.tech/actions/scan/<address>
      无 key 返回 403 → 需要 API key 的路径一律判死（不注册、不绕）。
    - https://frontend.poap.tech/actions/scan/<address> 无 key 返回 200，
      与 poap.xyz/scan/<address> 公开页面渲染的是同一数据（事件名、
      城市、国家、起止日期、图片）。走通。
    - 诚实备注：frontend.poap.tech 是 POAP 官方前端的数据面，非文档化
      公开 API，结构可能随时变；adapter 只做只读查询、限频 3s、默认关闭。

Association 价值与诚实边界：
    - 能覆盖：地址持有人的线下活动出席记录（会议/聚会/城市），构成
      兴趣与社交图谱线索，可与其他链上身份（ENS）交叉。
    - 不能替代：真实身份——POAP 可转赠/代领，出席≠组织者；事件描述
      是发行方自填。所有命中均为 leads，按"公开出席徽章"证据等级处理。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API_BASE = "https://frontend.poap.tech/actions/scan/"


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


class POAPBadgeLookup(SafeResearchAdapter):
    """POAP 持有查询：以太坊地址 → 出席徽章（事件/城市/日期）→ 兴趣图谱。"""

    source_domain = "frontend.poap.tech"
    source_type = "identity_poap_badges"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        addr = keyword.strip()
        return _API_BASE + urllib.parse.quote(addr, safe="")

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public POAP holdings query)",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True, "badges": []}
        if not isinstance(data, list):
            if isinstance(data, dict) and data.get("message"):
                return {"lookup_failed": True, "reason": _safe_str(data.get("message"), 160), "badges": []}
            return {"parse_error": True, "data_note": "unexpected response shape", "badges": []}
        badges: list[dict[str, Any]] = []
        cities: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            event = item.get("event") or {}
            if not isinstance(event, dict):
                continue
            city = _safe_str(event.get("city"), 64)
            country = _safe_str(event.get("country"), 64)
            if city and city not in cities:
                cities.append(city)
            badges.append({
                "event_id": event.get("id"),
                "event_name": _safe_str(event.get("name"), 160),
                "city": city,
                "country": country,
                "start_date": _safe_str(event.get("start_date"), 32),
                "end_date": _safe_str(event.get("end_date"), 32),
                "event_url": _safe_str(event.get("event_url"), 300),
                "image_url": _safe_str(event.get("image_url"), 300),
            })
        return {
            "badge_count": len(badges),
            "badges": badges[:50],
            "cities_seen": cities[:20],
            "data_note": (
                "POAP 是地址持有人的公开出席徽章（可转赠/代领，出席≠实名）；"
                "数据面为 POAP 官方前端（非文档化 API），结构可能变化，"
                "仅作兴趣/社交图谱线索。"
            ),
        }

    def query(self, keyword: str, **params) -> dict[str, Any]:  # type: ignore[override]
        if not _looks_like_address(keyword):
            result = self._build_empty_result(keyword, "invalid_ethereum_address")
            result["error"] = "invalid_ethereum_address"
            return result
        return super().query(keyword, **params)

    @staticmethod
    def parse_scan_result(raw: Any) -> list[dict[str, Any]]:
        """供测试与外部调用的纯函数解析入口（离线可测）。"""
        inst = POAPBadgeLookup.__new__(POAPBadgeLookup)
        return POAPBadgeLookup._extract_public_fields(inst, raw).get("badges", [])
