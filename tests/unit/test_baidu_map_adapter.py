#!/usr/bin/env python3
"""Unit tests for BaiduMapPoiLookup."""

from __future__ import annotations

import json

from adapters.baidu_map_adapter import BaiduMapPoiLookup
from core.connector_registry import ConnectorRegistry


def _realistic_v2_response():
    return {
        "status": 0,
        "message": "ok",
        "total": 2,
        "results": [
            {
                "name": "老王烩面馆",
                "location": {"lat": 34.747, "lng": 113.631},
                "address": "郑州市金水区花园路123号",
                "province": "河南省",
                "city": "郑州市",
                "area": "金水区",
                "telephone": "0371-88889999",
                "uid": "abc123def456",
                "detail_info": {
                    "tag": "小吃快餐;烩面",
                    "price": "25",
                    "overall_rating": "4.5",
                    "comment_num": "128",
                    "shop_hours": "09:00-22:00",
                },
            },
            {
                "name": "老王烩面馆（分店）",
                "location": {"lat": 34.730, "lng": 113.625},
                "address": "郑州市二七区解放路45号",
                "province": "河南省",
                "city": "郑州市",
                "area": "二七区",
                "telephone": "",
                "uid": "xyz789uvw012",
                "detail_info": {},
            },
        ],
    }


def _stub(payload, **kwargs):
    body = json.dumps(payload, ensure_ascii=False)
    return BaiduMapPoiLookup(
        api_key="test-baidu-key",
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_field_extraction():
    adapter = _stub(_realistic_v2_response())
    result = adapter.query("老王烩面馆", region="郑州")
    fields = result["fields"]
    assert fields["poi_count"] == 2
    first = fields["pois"][0]
    assert first["name"] == "老王烩面馆"
    assert first["uid"] == "abc123def456"
    assert first["lng"] == 113.631 and first["lat"] == 34.747
    assert first["city"] == "郑州市"
    assert first["tel"] == "0371-88889999"
    assert first["overall_rating"] == "4.5"
    assert first["comment_num"] == "128"
    assert first["shop_hours"] == "09:00-22:00"
    assert first["tag"] == "小吃快餐;烩面"
    # 缺 detail_info 字段的 POI 不崩
    assert fields["pois"][1]["tel"] == ""
    assert fields["pois"][1]["overall_rating"] == ""
    assert result["source_domain"] == "api.map.baidu.com"


def test_empty_results():
    adapter = _stub({"status": 0, "message": "ok", "total": 0, "results": []})
    result = adapter.query("不存在的店xyz123", region="郑州")
    assert result["fields"]["poi_count"] == 0
    assert result["fields"]["pois"] == []
    assert result["error"] == ""


def test_api_error_status():
    adapter = _stub({"status": 200, "message": "APP不存在，AK有误请检查再重试"})
    result = adapter.query("老王烩面馆", region="郑州")
    assert result["fields"]["lookup_failed"] is True
    assert "AK有误" in result["fields"]["reason"]
    assert result["fields"]["status_code"] == 200


def test_no_key_returns_credentials_required():
    adapter = BaiduMapPoiLookup(
        execute_query=lambda url, headers: (200, "{}", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    result = adapter.query("老王烩面馆", region="郑州")
    assert "credentials_required" in result["error"]
    assert result["fields"] == {}


def test_key_not_in_audit_trail():
    adapter = _stub(_realistic_v2_response())
    adapter.query("老王烩面馆", region="郑州")
    trail = adapter.audit.get_trail()
    assert trail, "expected audit records"
    trail_json = json.dumps(trail, ensure_ascii=False)
    assert "test-baidu-key" not in trail_json
    assert adapter.audit.verify_integrity() is True


def test_key_in_url_query_param():
    adapter = _stub(_realistic_v2_response())
    url = adapter._build_url("老王烩面馆", region="郑州")
    assert "ak=test-baidu-key" in url
    assert "scope=2" in url
    assert "output=json" in url
    # region 必填，默认"全国"
    url_default = adapter._build_url("老王烩面馆")
    assert "region=" in url_default


def test_garbage_input():
    adapter = BaiduMapPoiLookup(
        api_key="test-baidu-key",
        execute_query=lambda url, headers: (200, "not json {{{", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    result = adapter.query("老王烩面馆", region="郑州")
    assert result["fields"]["parse_error"] is True


def test_registered_default_off():
    names = {c.name: c for c in ConnectorRegistry().list()}
    assert "public_baidu_map_poi_search" in names
    assert names["public_baidu_map_poi_search"].default_enabled is False
