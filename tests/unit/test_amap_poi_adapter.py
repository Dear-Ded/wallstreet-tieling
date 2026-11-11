#!/usr/bin/env python3
"""Unit tests for AmapPoiLookup."""

from __future__ import annotations

import json

from adapters.amap_poi_adapter import AmapPoiLookup
from core.connector_registry import ConnectorRegistry


def _realistic_v5_response():
    return {
        "status": "1",
        "info": "OK",
        "count": "2",
        "pois": [
            {
                "id": "B0FFG12345",
                "name": "老王烩面馆",
                "type": "050301",
                "typecode": "050301",
                "pname": "河南省",
                "cityname": "郑州市",
                "adname": "金水区",
                "address": "花园路123号",
                "location": "113.631,34.747",
                "business": {
                    "opentime_today": "09:00-22:00",
                    "opentime_week": "周一至周日 09:00-22:00",
                    "rating": "4.5",
                    "cost": "25",
                    "tel": "0371-88889999",
                    "business_area": "花园路商圈",
                },
                "photos": [
                    {"title": "门头", "url": "https://example.com/p1.jpg"},
                    {"title": "内景", "url": "https://example.com/p2.jpg"},
                ],
            },
            {
                "id": "B0FFG67890",
                "name": "老王烩面馆（分店）",
                "type": "050301",
                "typecode": "050301",
                "pname": "河南省",
                "cityname": "郑州市",
                "adname": "二七区",
                "address": "解放路45号",
                "location": "113.625,34.730",
                "business": {},
                "photos": [],
            },
        ],
    }


def _stub(payload, **kwargs):
    body = json.dumps(payload, ensure_ascii=False)
    return AmapPoiLookup(
        api_key="test-amap-key",
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


def test_field_extraction():
    adapter = _stub(_realistic_v5_response())
    result = adapter.query("老王烩面馆", region="郑州")
    fields = result["fields"]
    assert fields["poi_count"] == 2
    first = fields["pois"][0]
    assert first["name"] == "老王烩面馆"
    assert first["id"] == "B0FFG12345"
    assert first["lng"] == "113.631" and first["lat"] == "34.747"
    assert first["city"] == "郑州市"
    assert first["tel"] == "0371-88889999"
    assert first["rating"] == "4.5"
    assert first["opentime_today"] == "09:00-22:00"
    assert len(first["photos"]) == 2
    # 缺 business 字段的 POI 不崩
    assert fields["pois"][1]["tel"] == ""
    assert result["source_domain"] == "restapi.amap.com"


def test_empty_results():
    adapter = _stub({"status": "1", "info": "OK", "count": "0", "pois": []})
    result = adapter.query("不存在的店xyz123")
    assert result["fields"]["poi_count"] == 0
    assert result["fields"]["pois"] == []
    assert result["error"] == ""


def test_api_error_status():
    adapter = _stub({"status": "0", "info": "INVALID_USER_KEY", "count": "0"})
    result = adapter.query("老王烩面馆")
    assert result["fields"]["lookup_failed"] is True
    assert "INVALID_USER_KEY" in result["fields"]["reason"]


def test_no_key_returns_credentials_required():
    adapter = AmapPoiLookup(
        execute_query=lambda url, headers: (200, "{}", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    result = adapter.query("老王烩面馆")
    assert "credentials_required" in result["error"]
    assert result["fields"] == {}


def test_key_not_in_audit_trail():
    adapter = _stub(_realistic_v5_response())
    adapter.query("老王烩面馆", region="郑州")
    trail = adapter.audit.get_trail()
    assert trail, "expected audit records"
    trail_json = json.dumps(trail, ensure_ascii=False)
    assert "test-amap-key" not in trail_json
    # audit 存的是 keyword hash，不是 URL
    assert adapter.audit.verify_integrity() is True


def test_key_in_url_query_param():
    adapter = _stub(_realistic_v5_response())
    url = adapter._build_url("老王烩面馆", region="郑州")
    assert "key=test-amap-key" in url
    assert "show_fields=business%2Cphotos" in url or "show_fields=business,photos" in url
    assert "region=" in url


def test_garbage_input():
    adapter = AmapPoiLookup(
        api_key="k",
        execute_query=lambda url, headers: (200, "not json {{{", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    result = adapter.query("老王烩面馆")
    assert result["fields"]["parse_error"] is True


def test_registered_default_off():
    names = {c.name: c for c in ConnectorRegistry().list()}
    assert "public_amap_poi_search" in names
    assert names["public_amap_poi_search"].default_enabled is False
