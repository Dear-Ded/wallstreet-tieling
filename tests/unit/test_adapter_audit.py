#!/usr/bin/env python3
"""Tests for adapter readiness audit."""
from __future__ import annotations

from core.adapter_audit import AdapterAuditor


def test_adapter_audit_marks_ready_and_blocked_connectors() -> None:
    payload = AdapterAuditor(repo_root=".").audit()
    rows = {row["name"]: row for row in payload["rows"]}

    assert payload["total"] >= 4
    assert rows["multi_datasource_rest_api"]["production_ready"] is True
    assert rows["multi_datasource_rest_api"]["blockers"] == []
    assert rows["multi_datasource_rest_api"]["quality_gate"]["ok"] is True
    assert rows["multi_datasource_rest_api"]["readiness_score"] >= 90
    assert rows["multi_datasource_rest_api"]["priority"] == "P3"

    assert rows["default_public_intel"]["production_ready"] is True
    assert rows["default_public_intel"]["blockers"] == []
    assert rows["default_public_intel"]["admission"]["decision"] == "production_ready"
    assert rows["default_public_intel"]["quality_gate"]["ok"] is True
    assert rows["default_public_intel"]["readiness_score"] >= 90

    assert rows["qyyjt_tool"]["production_ready"] is True
    assert "missing_health_check" not in rows["qyyjt_tool"]["blockers"]
    assert "connector_status:experimental" not in rows["qyyjt_tool"]["blockers"]
    assert rows["qyyjt_tool"]["quality_gate"]["ok"] is True
    assert rows["qyyjt_tool"]["admission"]["decision"] == "conditional_production"
    assert rows["qyyjt_tool"]["priority"] == "P3"
    assert rows["qyyjt_tool"]["readiness_score"] < rows["multi_datasource_rest_api"]["readiness_score"]

    assert rows["telegram_bot_public_service"]["production_ready"] is True
    assert "missing_health_check" not in rows["telegram_bot_public_service"]["blockers"]
    assert "missing_standardized_records" not in rows["telegram_bot_public_service"]["blockers"]
    assert "connector_status:needs_review" not in rows["telegram_bot_public_service"]["blockers"]
    assert rows["telegram_bot_public_service"]["quality_gate"]["ok"] is True
    assert rows["telegram_bot_public_service"]["admission"]["decision"] == "conditional_production"
    assert rows["telegram_bot_public_service"]["priority"] == "P3"


def test_adapter_audit_next_actions_are_actionable() -> None:
    payload = AdapterAuditor(repo_root=".").audit()
    qyyjt = next(row for row in payload["rows"] if row["name"] == "qyyjt_tool")

    assert any("risk flags" in action for action in qyyjt["next_actions"])
    assert qyyjt["admission"]["production_route"] == "user_configured_production"


def test_adapter_audit_exposes_priority_for_next_work() -> None:
    payload = AdapterAuditor(repo_root=".").audit()
    rows = {row["name"]: row for row in payload["rows"]}

    assert rows["public_web_search"]["priority"] == "P3"
    assert rows["public_web_search"]["production_ready"] is True
    assert rows["public_web_search"]["readiness_score"] >= 90
    assert rows["public_web_search"]["capability"]["risk_flags"] == []


def test_adapter_audit_classifies_public_official_connector_tiers() -> None:
    payload = AdapterAuditor(repo_root=".").audit()
    rows = {row["name"]: row for row in payload["rows"]}

    for name in (
        "gleif_lei_public_api",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "world_bank_debarred_firms_public_list",
        "sec_edgar_public_api",
    ):
        assert rows[name]["admission"]["tier"] == "official_public"
        assert "unknown_source_tier" not in rows[name]["admission"]["blockers"]

    assert rows["authorized_opensanctions_api"]["admission"]["tier"] == "user_authorized_service"
    assert rows["authorized_opensanctions_api"]["production_ready"] is False
