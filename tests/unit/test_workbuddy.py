#!/usr/bin/env python3
"""Tests for WorkBuddy tool routing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.interfaces import ToolResult
from adapters.workbuddy import WorkBuddyTools


ADVANCED_CHINA_DOMESTIC_SOURCES = {
    "enterprise_tax_credit_public_records",
    "enterprise_judicial_asset_public_records",
    "enterprise_mofcom_overseas_investment_public_records",
    "enterprise_baidu_aiqicha_public_aggregation",
    "enterprise_shuidi_credit_public_aggregation",
}


class FakeMdsTool:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        self.calls.append({"query": query, "tool_type": tool_type, **kwargs})
        return ToolResult(ok=True, data={"query": query}, sources=["fake:mds"])


@pytest.mark.asyncio
async def test_web_search_is_delegated_to_host():
    tools = WorkBuddyTools()

    result = await tools.search("test company", "web")

    assert result.ok is True
    assert result.data["hint"] == "delegated_to_host"
    assert result.sources == ["wb:web"]


@pytest.mark.asyncio
async def test_host_mcp_is_delegated_to_host():
    tools = WorkBuddyTools()

    result = await tools.search("connector_catalog", "host_mcp")

    assert result.ok is True
    assert result.data["hint"] == "delegated_to_host"
    assert result.sources == ["wb:host_mcp"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_connector_catalog():
    tools = WorkBuddyTools()

    result = await tools.search("", "connector_catalog")
    connector_rows = {item["name"]: item for item in result.data["connectors"]}
    explicit_only_names = {item["name"] for item in result.data["groups"]["explicit_only"]}

    assert result.ok is True
    assert result.data["type"] == "connector_catalog"
    assert "default_public_intel" in result.data["summary"]["zero_config_ready"]
    assert result.data["summary"]["data_effectiveness"]["fact_capable_sources"] >= 4
    assert ADVANCED_CHINA_DOMESTIC_SOURCES <= explicit_only_names
    for source_name in ADVANCED_CHINA_DOMESTIC_SOURCES:
        assert connector_rows[source_name]["default_enabled"] is False
        assert connector_rows[source_name]["access"] == "user_authorized"
        assert (
            connector_rows[source_name]["data_effectiveness"]["admission_mode"]
            == "user_authorized_fact_source_when_entity_match_passes"
        )
        assert connector_rows[source_name]["data_effectiveness"]["can_feed_report_facts"] is True
    assert "administrative_credit_risk" in connector_rows["enterprise_tax_credit_public_records"]["data_effectiveness"]["analysis_outputs"]
    assert "legal_enforcement_risk" in connector_rows["enterprise_judicial_asset_public_records"]["data_effectiveness"]["analysis_outputs"]
    assert "official_origin_provenance_required" in connector_rows["enterprise_baidu_aiqicha_public_aggregation"]["risk_flags"]
    assert result.sources == ["workbuddy:connector_catalog"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_release_readiness():
    tools = WorkBuddyTools()

    result = await tools.search("", "release_readiness")

    assert result.ok is True
    assert result.data["type"] == "release_readiness_brief"
    assert result.data["persona_surface"]["role_count"] == 13
    assert result.data["contract"]["variants"]["workbuddy_expert_team"]["readiness"] == "alpha"
    assert result.sources == ["workbuddy:release_readiness"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_development_requirements():
    tools = WorkBuddyTools()

    result = await tools.search("", "development_requirements")

    assert result.ok is True
    assert result.data["type"] == "development_requirements_board"
    assert result.data["completion_percent"] == 94
    assert result.data["qyyjt_current_version"]["p0_queue_count"] == 20
    assert result.data["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"
    assert result.sources == ["workbuddy:development_requirements"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_agent_tool_adapters():
    tools = WorkBuddyTools()

    result = await tools.search("", "agent_tool_adapters")

    assert result.ok is True
    assert result.data["type"] == "agent_tool_adapter_manifest"
    assert result.data["primary_host_id"] == "codex"
    assert result.data["host_priority_order"][0] == "codex"
    assert "workbuddy_expert_team" in result.data["host_ids"]
    workbuddy = next(item for item in result.data["adapters"] if item["host_id"] == "workbuddy_expert_team")
    assert workbuddy["primary_mode"] == "workbuddy_adapter_plus_skill"
    assert workbuddy["delivery_priority"]["lane"] == "secondary"
    assert "codex" in workbuddy["delivery_priority"]["depends_on"]
    assert workbuddy["project_branch_contract"]["branch_id"] == "workbuddy_expert_team"
    assert workbuddy["project_branch_contract"]["branch_type"] == "expert_team_host_adapter"
    assert "core runtime architecture" in workbuddy["project_branch_contract"]["must_not_touch"]
    assert workbuddy["tool_sequence"] == [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
    ]
    shared_tools = {tool["name"]: tool for tool in result.data["shared_tools"]}
    assert shared_tools["delivery_audit"]["mcp_tool"] == "delivery_audit"
    assert shared_tools["delivery_audit"]["api"] == "GET /api/delivery-audit"
    assert "connector_catalog.groups.explicit_only" in workbuddy["required_packet_fields"]
    assert "connector_catalog.connectors[].data_effectiveness" in workbuddy["required_packet_fields"]
    assert "connector_catalog.source_strengthening_queue" in workbuddy["required_packet_fields"]
    assert "connector_catalog.source_strengthening_queue[].runtime_companion" in workbuddy["required_packet_fields"]
    assert "qyyjt_public_origin_handoff.agent_autorun" in workbuddy["required_packet_fields"]
    assert "report_exports.agent_decision_digest" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.verifier_output_fields" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun" in workbuddy["required_packet_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in workbuddy["required_packet_fields"]
    assert "enterprise_cognition.relationship_resolution_v1" in workbuddy["required_packet_fields"]
    assert (
        "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue"
        in workbuddy["required_packet_fields"]
    )
    assert (
        "report_exports.directory_bundle.agent_handoff.relationship_resolution"
        in workbuddy["required_packet_fields"]
    )
    assert result.sources == ["workbuddy:agent_tool_adapters"]


def test_workbuddy_available_tools_include_baseline_sequence():
    tools = WorkBuddyTools()

    assert {
        "release_readiness",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
        "due_diligence",
    } <= tools.available_tools()


@pytest.mark.asyncio
async def test_workbuddy_investigate_company_returns_packet(tmp_path):
    tools = WorkBuddyTools()

    result = await tools.search(
        "",
        "investigate_company",
        company_name="Demo WorkBuddy Runtime Co., Ltd.",
        offline_fixture=True,
        store=str(tmp_path / "risk-events.jsonl"),
    )

    assert result.ok is True
    assert result.data["type"] == "investigation_packet"
    assert result.data["input"] == "Demo WorkBuddy Runtime Co., Ltd."
    assert result.data["quality_gate"]
    assert result.data["evidence_ledger"]
    assert result.data["qyyjt_public_origin_handoff"]["type"] == "qyyjt_public_origin_handoff"
    assert "report_exports" in result.data
    assert result.data["report_exports"]["agent_decision_digest"]["type"] == "agent_decision_digest"
    relationship_resolution = result.data["enterprise_cognition"]["relationship_resolution_v1"]
    assert relationship_resolution["type"] == "relationship_resolution_v1"
    assert isinstance(relationship_resolution["resolution_summary"]["verification_queue"], list)
    directory_bundle = result.data["report_exports"]["directory_bundle"]
    assert "agent_handoff.relationship_resolution_present" in directory_bundle["verifier_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in directory_bundle["verifier_output_fields"]
    assert "relationship_resolution" in directory_bundle["agent_handoff"]["schema_fields"]
    assert directory_bundle["agent_handoff"]["source_strengthening"]["type"] == "source_strengthening_handoff"
    assert directory_bundle["agent_handoff"]["source_strengthening"]["status"] in {"ready", "complete"}
    assert directory_bundle["agent_handoff"]["source_resilience"]["type"] == "source_resilience_handoff"
    assert directory_bundle["agent_handoff"]["source_resilience"]["replay_routes"]
    assert directory_bundle["agent_handoff"]["source_resilience"]["agent_autorun"]["type"] == "source_resilience_agent_autorun"
    assert directory_bundle["agent_handoff"]["capital_risk_panel"]["type"] == "capital_risk_panel_handoff"
    assert directory_bundle["agent_handoff"]["capital_risk_panel"]["agent_autorun"]["type"] == "capital_risk_agent_autorun"
    assert directory_bundle["agent_handoff"]["relationship_graph_audit"]["type"] == "relationship_graph_audit_handoff"
    assert (
        directory_bundle["agent_handoff"]["relationship_graph_audit"]["agent_autorun"]["type"]
        == "relationship_graph_audit_agent_autorun"
    )
    assert (
        directory_bundle["agent_handoff"]["relationship_resolution"]["agent_autorun"]["type"]
        == "relationship_resolution_agent_autorun"
    )
    assert directory_bundle["agent_handoff"]["report_artifact_autorun"]["type"] == "report_artifact_agent_autorun"
    assert result.data["qyyjt_public_origin_handoff"]["section_work_orders"]
    assert result.data["qyyjt_public_origin_handoff"]["agent_autorun"]["type"] == "qyyjt_public_origin_agent_autorun"
    assert result.sources == ["workbuddy:investigate_company"]


@pytest.mark.asyncio
async def test_workbuddy_investigate_company_validates_source_modes():
    tools = WorkBuddyTools()

    result = await tools.search(
        "Demo WorkBuddy Runtime Co., Ltd.",
        "investigate_company",
        offline_fixture=True,
        fixture_pack=True,
    )

    assert result.ok is False
    assert "mutually exclusive" in result.error
    assert result.sources == ["workbuddy:investigate_company:validation"]


@pytest.mark.asyncio
async def test_mds_failure_returns_tool_result(monkeypatch):
    tools = WorkBuddyTools()
    monkeypatch.setattr(tools, "_get_mds_tool", lambda: None)

    result = await tools.search("test company", "multi_datasource")

    assert result.ok is False
    assert result.data["query"] == "test company"
    assert result.data["tool_type"] == "multi_datasource"
    assert result.error


@pytest.mark.asyncio
async def test_force_keyword_path_does_not_crash():
    tools = WorkBuddyTools()
    fake = FakeMdsTool()
    tools._mds_tool = fake

    result = await tools.search("测试公司 股东 信息", "mds", sources=["demo"], use_cache=False)

    assert result.ok is True
    assert fake.calls == [
        {
            "query": "测试公司 股东 信息",
            "tool_type": "mds",
            "sources": ["demo"],
            "use_cache": False,
        }
    ]


@pytest.mark.asyncio
async def test_default_public_intel_failure_is_standardized(monkeypatch):
    tools = WorkBuddyTools()
    monkeypatch.setattr(tools, "_get_default_public_tool", lambda: None)

    result = await tools.search("Demo Co.", "default_public_intel")

    assert result.ok is False
    assert result.data["tool_type"] == "default_public_intel"
    assert result.sources == ["workbuddy:default_public_intel:error"]


@pytest.mark.asyncio
async def test_unknown_tool_type_is_reported():
    tools = WorkBuddyTools()

    result = await tools.search("test company", "unknown")

    assert result.ok is False
    assert "unknown" in result.data["tool_type"]
