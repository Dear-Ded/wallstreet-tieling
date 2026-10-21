"""Tests for CnipaTrademarkLookup adapter."""
import json
import pytest
from adapters.trademark_adapter import CnipaTrademarkLookup


@pytest.fixture
def adapter():
    return CnipaTrademarkLookup()


def test_query_returns_interaction(adapter):
    result = adapter.query("蜜雪冰城")
    assert result["status"] == "interaction_required"
    assert result["keyword"] == "蜜雪冰城"
    assert len(result["browser_steps"]) == 7
    assert "wcjs.sbj.cnipa.gov.cn" in result["source"]


def test_parse_browser_result_list_shape(adapter):
    raw = {
        "list": [{
            "tmName": "蜜雪冰城",
            "regNo": "12345678",
            "applicantName": "蜜雪冰城股份有限公司",
            "appDate": "2019-03-20",
            "intCls": "43",
            "tmStatus": "注册",
        }],
    }
    result = adapter.parse_browser_result(raw)
    assert result["status"] == "ok"
    assert result["total_found"] == 1
    r = result["records"][0]
    assert r["mark_name"] == "蜜雪冰城"
    assert r["reg_number"] == "12345678"
    assert r["applicant"] == "蜜雪冰城股份有限公司"
    assert r["intl_class"] == "43"


def test_parse_browser_result_json_string(adapter):
    raw = json.dumps({"rows": [{"markName": "测试", "申请号": "999"}]})
    result = adapter.parse_browser_result(raw)
    assert result["status"] == "ok"
    assert result["records"][0]["mark_name"] == "测试"


def test_parse_browser_result_invalid(adapter):
    result = adapter.parse_browser_result("not json {{{")
    assert result["status"] == "parse_failed"


def test_parse_browser_result_empty(adapter):
    result = adapter.parse_browser_result({})
    assert result["status"] == "ok"
    assert result["total_found"] == 0


def test_registered_default_off():
    from core.connector_registry import ConnectorRegistry
    reg = ConnectorRegistry()
    caps = {c.name: c for c in reg.list()}
    assert "public_cnipa_trademark_lookup" in caps
    assert caps["public_cnipa_trademark_lookup"].default_enabled is False
