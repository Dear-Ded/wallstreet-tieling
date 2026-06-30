#!/usr/bin/env python3
"""Offline contracts for the QYYJT adapter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.qyyjt_adapter import CookieManager, QYYJTAdapter, QYYJTModule


def test_cookie_manager_round_trips_local_cookie_file(tmp_path):
    manager = CookieManager(data_dir=tmp_path)
    cookies = [
        {
            "name": "sessionid",
            "value": "local-test-cookie",
            "domain": "www.qyyjt.cn",
            "path": "/",
        }
    ]

    manager.save_cookies(cookies)

    loaded = CookieManager(data_dir=tmp_path).load_cookies()
    assert loaded == cookies
    assert "local-test-cookie" not in manager.cookie_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_query_without_api_returns_websearch_plan():
    adapter = QYYJTAdapter()

    result = await adapter.query(
        "测试公司",
        modules=[
            QYYJTModule.RISK_SCAN,
            QYYJTModule.COURT_CASES,
            QYYJTModule.NEWS_NEGATIVE,
        ],
        prefer_api=False,
    )

    assert result["source"] == "websearch"
    assert result["cookie_valid"] is False
    assert result["api_data"] == {}
    assert len(result["websearch_queries"]) >= 3
    assert {item["module"] for item in result["websearch_queries"]} >= {
        "risk_scan",
        "court_cases",
        "news_negative",
    }


@pytest.mark.asyncio
async def test_report_critical_api_modules_emit_module_level_payloads(monkeypatch):
    adapter = QYYJTAdapter()

    async def cookie_valid() -> bool:
        return True

    async def search_company(company: str):
        return {
            "data": {
                "search": {
                    "list": [
                        {"code": "BOND001", "name": company},
                        {"code": "BOND002", "name": f"{company} Holdings"},
                    ]
                }
            }
        }

    monkeypatch.setattr(adapter.cookie_manager, "test_cookies_valid", cookie_valid)
    monkeypatch.setattr(adapter, "search_company", search_company)

    result = await adapter.query(
        "测试公司",
        modules=[
            QYYJTModule.ENTERPRISE_BASIC,
            QYYJTModule.RISK_SCAN,
            QYYJTModule.ACTUAL_CONTROLLER,
            QYYJTModule.COURT_CASES,
            QYYJTModule.FINANCIAL_STATEMENT,
        ],
        prefer_api=True,
    )

    assert result["source"] == "api"
    assert result["api_data"]["ent_basic"]["module"] == "ent_basic"
    assert result["api_data"]["risk_scan"]["module"] == "risk_scan"
    assert result["api_data"]["actual_controller"]["module"] == "actual_controller"
    assert result["api_data"]["court_cases"]["module"] == "court_cases"
    assert result["api_data"]["financial"].get("module") == "financial"
    assert result["api_data"]["ent_basic"]["list"]
    assert result["api_data"]["risk_scan"]["list"][0]["name"] == "测试公司"


@pytest.mark.asyncio
async def test_bond_profile_api_branch_uses_existing_enum(monkeypatch):
    adapter = QYYJTAdapter()

    async def cookie_valid() -> bool:
        return True

    async def search_company(company: str):
        return {"data": {"search": {"list": [{"code": "BOND001"}]}}}

    async def get_bond_notices(code: str):
        return {"code": code, "list": []}

    monkeypatch.setattr(adapter.cookie_manager, "test_cookies_valid", cookie_valid)
    monkeypatch.setattr(adapter, "search_company", search_company)
    monkeypatch.setattr(adapter, "get_bond_notices", get_bond_notices)

    result = await adapter.query(
        "测试公司",
        modules=[QYYJTModule.BOND_PROFILE],
        prefer_api=True,
    )

    assert result["source"] == "api"
    assert result["api_data"]["bond_notices"] == {"code": "BOND001", "list": []}
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_region_code_api_branch_uses_existing_enum(monkeypatch):
    adapter = QYYJTAdapter()

    async def cookie_valid() -> bool:
        return True

    async def search_company(company: str):
        return {"data": {"search": {"list": []}}}

    async def get_region_codes():
        return {"rows": [{"code": "310000", "name": "上海市"}]}

    monkeypatch.setattr(adapter.cookie_manager, "test_cookies_valid", cookie_valid)
    monkeypatch.setattr(adapter, "search_company", search_company)
    monkeypatch.setattr(adapter, "get_region_codes", get_region_codes)

    result = await adapter.query(
        "娴嬭瘯鍏徃",
        modules=[QYYJTModule.REGION_CODE],
        prefer_api=True,
    )

    assert result["source"] == "api"
    assert result["api_data"]["region_codes"] == {"rows": [{"code": "310000", "name": "上海市"}]}
    assert result["errors"] == {}


def test_module_query_for_unimplemented_module_is_explicit_websearch_plan():
    adapter = QYYJTAdapter()

    query = adapter.get_module_query(QYYJTModule.BOND_CREDIT, "测试公司")

    assert query["source"] == "qyyjt_module"
    assert query["module"] == "bond_credit"
    assert len(query["queries"]) >= 3
    assert any("评级" in item or "债券" in item for item in query["queries"])
    assert any("chinabond" in item for item in query["queries"])


def test_module_query_for_monitoring_module_has_real_plan():
    adapter = QYYJTAdapter()

    query = adapter.get_module_query(QYYJTModule.WATCHLIST, "测试公司")

    assert query["source"] == "qyyjt_module"
    assert query["module"] == "watchlist"
    assert len(query["queries"]) >= 2
    assert any("监控" in item or "预警" in item for item in query["queries"])
    assert "未来持续监控版本" in query["note"]


def test_module_queries_are_readable_for_all_qyyjt_modules():
    adapter = QYYJTAdapter()
    mojibake_markers = ("鈥", "鑲", "鍊", "璐", "椋", "瑁", "澶", "�")

    for module in QYYJTModule:
        query = adapter.get_module_query(module, "测试公司")
        text = " ".join(query["queries"] + [query.get("note", "")])
        assert query["source"] == "qyyjt_module"
        assert query.get("source_role") == "public_search_plan"
        assert "测试公司" in text or module == QYYJTModule.REGION_CODE
        assert not any(marker in text for marker in mojibake_markers), f"{module.value}: {text}"


def test_default_qyyjt_public_plan_covers_deep_due_diligence_lanes():
    adapter = QYYJTAdapter()
    modules = [
        QYYJTModule.ACTUAL_CONTROLLER,
        QYYJTModule.RELATED_PARTIES,
        QYYJTModule.FIN_INSTITUTION,
        QYYJTModule.PLEDGE,
        QYYJTModule.IMPORT_EXPORT,
        QYYJTModule.RECRUIT,
    ]
    text = "\n".join(
        " ".join(adapter.get_module_query(module, "测试公司")["queries"])
        for module in modules
    )
    for keyword in ("实际控制人", "关联方", "金融机构", "股权质押", "进出口", "招聘"):
        assert keyword in text
