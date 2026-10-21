#!/usr/bin/env python3
"""百度地图地点检索适配器（线下商业 lane）。

回答："这家线下店真实存在吗？在哪？电话多少？口碑如何？"

Endpoint: GET https://api.map.baidu.com/place/v2/search
Params: query（店名，必填）, region（城市/行政区，必填）,
        ak（API key，必填）, output=json, scope=2（详细信息）,
        page_size（最大20）, page_num, city_limit

Key handling: 构造参数注入（api_key=<redacted> key 时返回
`credentials_required`。key 只出现在请求 URL 的 ak= 查询参数中；
审计日志只存 query 的 sha256 前 12 位，不存 URL，key 永不进日志。

免费 key: lbsyun.baidu.com 注册（Web 服务 API 地点检索，
个人开发者免费额度约 2 万次/天，具体以控制台为准；需实名认证）。

ToS 合规（百度地图开放平台服务条款）：
百度 ToS 同样禁止对 POI 数据做离线缓存、存储与二次分发。
本适配器只做实时查询、不做任何本地持久化；每次调用都是
fresh request，返回结果由调用方即时消费，不落盘。

与高德 POI 的差异：
- 百度 region 为必填（高德可选），默认 region="全国"
- 百度 scope=2 返回 detail_info（含 overall_rating / comment_num / tag）
- 百度坐标系为 bd09ll；如需国测局坐标可加 ret_coordtype=gcj02ll
- 百度 page_size 最大 20（高德 v5 为 25）

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class BaiduMapPoiLookup(SafeResearchAdapter):
    """百度地图地点检索：线下门店存在性 / 地址 / 电话 / 口碑核验。"""

    source_domain = "api.map.baidu.com"
    source_type = "offline_business_baidu_poi"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)

    def _build_url(self, keyword: str, **params) -> str:
        keyword = keyword.strip()
        region = str(params.get("region", "") or "").strip() or "全国"
        query = {
            "ak": self._api_key,
            "query": keyword,
            "region": region,
            "output": "json",
            "scope": "2",
        }
        page_size = params.get("page_size", 10)
        try:
            page_size = max(1, min(int(page_size), 20))
        except (TypeError, ValueError):
            page_size = 10
        query["page_size"] = str(page_size)
        page_num = params.get("page_num", 0)
        try:
            page_num = max(0, int(page_num))
        except (TypeError, ValueError):
            page_num = 0
        query["page_num"] = str(page_num)
        if str(params.get("city_limit", "")).lower() == "true":
            query["city_limit"] = "true"
        # key 必须放 URL query 参数（百度 API 要求）；审计日志不存 URL
        return "https://api.map.baidu.com/place/v2/search?" + urllib.parse.urlencode(query)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        status = data.get("status")
        if status != 0:
            return {
                "lookup_failed": True,
                "reason": str(data.get("message", ""))[:120],
                "status_code": status,
            }
        results = data.get("results") or []
        try:
            total = int(data.get("total", len(results)))
        except (TypeError, ValueError):
            total = len(results)
        pois: list[dict[str, Any]] = []
        for poi in results[:10]:
            if not isinstance(poi, dict):
                continue
            loc = poi.get("location") or {}
            if not isinstance(loc, dict):
                loc = {}
            detail = poi.get("detail_info") or {}
            if not isinstance(detail, dict):
                detail = {}
            pois.append({
                "uid": poi.get("uid", ""),
                "name": poi.get("name", ""),
                "address": poi.get("address", ""),
                "province": poi.get("province", ""),
                "city": poi.get("city", ""),
                "area": poi.get("area", ""),
                "lng": loc.get("lng", ""),
                "lat": loc.get("lat", ""),
                "tel": str(poi.get("telephone", "") or "")[:80],
                "tag": detail.get("tag", ""),
                "price": detail.get("price", ""),
                "overall_rating": detail.get("overall_rating", ""),
                "comment_num": detail.get("comment_num", ""),
                "shop_hours": detail.get("shop_hours", ""),
            })
        return {
            "poi_count": total,
            "pois": pois,
            "data_note": "百度地图 POI 实时查询 — 门店存在性/地址/电话/评分为平台收录数据，仅作线索；ToS：不缓存不存储",
        }
