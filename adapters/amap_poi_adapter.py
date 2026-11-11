#!/usr/bin/env python3
"""高德地图 POI 关键字搜索适配器（线下商业 lane）。

回答："这家线下店真实存在吗？在哪？营业中吗？口碑如何？"

Endpoint: GET https://restapi.amap.com/v5/place/text
Params: keywords（店名）, region（城市，可选）,
        show_fields=business,photos, key（API key）

Key handling: 构造参数注入（api_key=...），无 key 时返回
`credentials_required`。key 只出现在请求 URL 的 key= 查询参数中；
审计日志只存 keyword 的 sha256 前 12 位，不存 URL，key 永不进日志。

免费 key: lbs.amap.com 注册（个人 5,000 次/月）。

ToS 合规（高德地图 API 服务条款 3.5）：
高德 ToS 禁止对 POI 数据做缓存、存储、二次分发。本适配器只做
实时查询、不做任何本地持久化；每次调用都是 fresh request，
返回结果由调用方即时消费，不落盘。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class AmapPoiLookup(SafeResearchAdapter):
    """高德 POI 关键字搜索：线下门店存在性 / 地址 / 营业 / 口碑核验。"""

    source_domain = "restapi.amap.com"
    source_type = "offline_business_amap_poi"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = (api_key or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)

    def _build_url(self, keyword: str, **params) -> str:
        keywords = urllib.parse.quote(keyword.strip())
        query = {
            "key": self._api_key,
            "keywords": keywords,
            "show_fields": "business,photos",
        }
        region = str(params.get("region", "") or "").strip()
        if region:
            query["region"] = region
        page_size = params.get("page_size", 10)
        try:
            page_size = max(1, min(int(page_size), 25))
        except (TypeError, ValueError):
            page_size = 10
        query["page_size"] = str(page_size)
        # key 必须放 URL query 参数（高德 API 要求）；审计日志不存 URL
        return "https://restapi.amap.com/v5/place/text?" + urllib.parse.urlencode(query)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        if str(data.get("status")) != "1":
            return {
                "lookup_failed": True,
                "reason": str(data.get("info", ""))[:120],
            }
        pois = data.get("pois") or []
        try:
            total = int(data.get("count", len(pois)))
        except (TypeError, ValueError):
            total = len(pois)
        results: list[dict[str, Any]] = []
        for poi in pois[:10]:
            if not isinstance(poi, dict):
                continue
            business = poi.get("business") or {}
            if not isinstance(business, dict):
                business = {}
            photos = poi.get("photos") or []
            photo_list = [
                {"title": str(p.get("title", ""))[:60], "url": p.get("url", "")}
                for p in photos[:5] if isinstance(p, dict) and p.get("url")
            ]
            location = str(poi.get("location", "") or "")
            lng, lat = "", ""
            if "," in location:
                parts = location.split(",", 1)
                lng, lat = parts[0].strip(), parts[1].strip()
            results.append({
                "id": poi.get("id", ""),
                "name": poi.get("name", ""),
                "type": poi.get("type", ""),
                "typecode": poi.get("typecode", ""),
                "province": poi.get("pname", ""),
                "city": poi.get("cityname", ""),
                "district": poi.get("adname", ""),
                "address": poi.get("address", ""),
                "lng": lng,
                "lat": lat,
                "tel": str(business.get("tel", "") or "")[:60],
                "opentime_today": business.get("opentime_today", ""),
                "opentime_week": business.get("opentime_week", ""),
                "rating": business.get("rating", ""),
                "cost": business.get("cost", ""),
                "business_area": business.get("business_area", ""),
                "photos": photo_list,
            })
        return {
            "poi_count": total,
            "pois": results,
            "data_note": "高德 POI 实时查询 — 门店存在性/地址/营业信息为平台收录数据，仅作线索；ToS 3.5：不缓存不存储",
        }
