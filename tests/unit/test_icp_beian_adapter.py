"""Tests for IcpBeianLookup adapter."""
import json
import pytest
from adapters.icp_beian_adapter import IcpBeianLookup


@pytest.fixture
def adapter():
    return IcpBeianLookup()


def test_service_types(adapter):
    assert adapter.SERVICE_TYPES["web"] == 1
    assert adapter.SERVICE_TYPES["app"] == 6


def test_extract_records_full_fields(adapter):
    raw = {
        "params": {
            "total": 1,
            "list": [{
                "domain": "baidu.com",
                "unitName": "北京百度网讯科技有限公司",
                "natureName": "企业",
                "mainLicence": "京ICP证030173号",
                "serviceLicence": "京ICP备123456号-1",
                "serviceName": "百度",
                "homeUrl": "www.baidu.com",
                "updateRecordTime": "2024-01-15",
                "mainUnitAddress": "北京市海淀区",
            }],
        },
    }
    records = adapter._extract_records(raw)
    assert len(records) == 1
    r = records[0]
    # No masking: full values preserved
    assert r["unit_name"] == "北京百度网讯科技有限公司"
    assert r["main_licence"] == "京ICP证030173号"
    assert r["unit_address"] == "北京市海淀区"
    assert r["domain"] == "baidu.com"


def test_extract_records_empty(adapter):
    assert adapter._extract_records({}) == []
    assert adapter._extract_records({"params": {}}) == []


def test_extract_records_malformed(adapter):
    assert adapter._extract_records(None) == []
    assert adapter._extract_records("garbage") == []


def test_query_interaction_fallback(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_query_api",
                        lambda *a, **k: {"error": "captcha_failed", "need_interaction": True})
    result = adapter.query("example.com")
    assert result["status"] == "interaction_required"
    assert "beian.miit.gov.cn" in result["message"]


def test_query_token_failure(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_query_api",
                        lambda *a, **k: {"error": "token_failed"})
    result = adapter.query("example.com")
    assert result["status"] == "lookup_failed"


def test_query_success_shape(adapter, monkeypatch):
    fake_raw = {
        "success": True,
        "params": {
            "total": 2,
            "list": [
                {"domain": "a.com", "unitName": "甲公司", "mainLicence": "京ICP备1号"},
                {"domain": "b.com", "unitName": "甲公司", "mainLicence": "京ICP备1号"},
            ],
        },
    }
    monkeypatch.setattr(adapter, "_query_api", lambda *a, **k: fake_raw)
    result = adapter.query("甲公司")
    assert result["status"] == "ok"
    assert result["record_count"] == 2
    assert result["total"] == 2
    assert result["source"] == "hlwicpfwc.miit.gov.cn"


def test_solve_slider_no_pil(adapter, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "PIL", None)
    # Should return -1 gracefully when PIL unavailable
    result = adapter._solve_slider("x", "y")
    assert result == -1


def test_registered_default_off():
    from core.connector_registry import ConnectorRegistry
    reg = ConnectorRegistry()
    caps = {c.name: c for c in reg.list()}
    assert "public_icp_beian_lookup" in caps
    assert caps["public_icp_beian_lookup"].default_enabled is False
