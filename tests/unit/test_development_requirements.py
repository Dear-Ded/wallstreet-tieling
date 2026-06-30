#!/usr/bin/env python3
"""Tests for executable development requirement levels."""
from __future__ import annotations

from core.development_requirements import build_development_requirements_board


def test_development_requirements_board_classifies_current_release_work() -> None:
    board = build_development_requirements_board()

    assert board["type"] == "development_requirements_board"
    assert board["version"] == "0.5.0"
    assert board["completion_percent"] == 88
    assert board["summary"]["by_level"]["P0"] >= 6
    assert board["summary"]["p0_open_count"] >= 1
    assert board["level_policy"]["P0"].startswith("Current-release blocker")
    assert board["scope_rules"]["ui_work_rule"].startswith("UI work is P2")


def test_qyyjt_is_current_release_requirement_with_module_snapshot() -> None:
    board = build_development_requirements_board()
    qyyjt = board["qyyjt_current_version"]
    requirements = {item["id"]: item for item in board["requirements"]}

    assert qyyjt["current_release_requirement_id"] == "P0.QYYJT_CURRENT_VERSION_PARITY"
    assert qyyjt["module_count"] == 45
    assert qyyjt["p0_queue_count"] == 20
    assert qyyjt["surface_profile"]["generic_fallback_modules"] == 0
    assert requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["current_version_scope"] is True
    assert requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["level"] == "P0"
    assert requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["completion_percent"] == 94
    assert any(
        "regional-credit cognition profile" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "court-announcement, merger/restructuring, and bond-calendar payloads" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert "QYYJT" in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["title"]
    assert any(
        "legal/admin cognition profile" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "operational-event profile" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "All 45 QYYJT field-contract record types" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "public-origin fallback diagnostics" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "public-origin fallback rows expose required fields" in gate
        for gate in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["acceptance_gates"]
    )


def test_continuous_monitoring_is_parked_outside_current_release() -> None:
    board = build_development_requirements_board()
    requirements = {item["id"]: item for item in board["requirements"]}
    monitoring = requirements["FUTURE.CONTINUOUS_MONITORING"]

    assert board["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"
    assert monitoring["level"] == "Future"
    assert monitoring["status"] == "parked"
    assert monitoring["current_version_scope"] is False
    assert all(item["id"] != "FUTURE.CONTINUOUS_MONITORING" for item in board["next_focus"])


def test_acceptance_gates_are_machine_readable_by_priority() -> None:
    board = build_development_requirements_board()
    requirements = {item["id"]: item for item in board["requirements"]}

    assert board["acceptance_gates"]["P0"]
    assert board["acceptance_gates"]["P1"]
    assert requirements["P1.PUBLIC_SOURCE_BREADTH"]["completion_percent"] == 89
    assert requirements["P1.INDUSTRY_PRODUCT_EXTRACTION"]["completion_percent"] == 90
    assert requirements["P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION"]["completion_percent"] == 92
    assert requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["completion_percent"] == 92
    assert requirements["P0.REPORT_VALUE_COGNITION"]["completion_percent"] == 95
    assert requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["completion_percent"] == 95
    assert requirements["P1.OPERATIONAL_OBSERVABILITY"]["completion_percent"] == 78
    assert requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]["completion_percent"] == 12
    assert requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]["status"] == "planned"
    assert any(
        "blocked recovery execution preview" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "one_click_readiness" in item
        for item in requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["implemented"]
    )
    assert any(
        "Relationship-network report rows" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "capital pressure level" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "Package variant tests" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "NPM script references" in gate
        for gate in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["acceptance_gates"]
    )
    assert any(
        "blocked preview rows" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "Relationship-network report rows include admission state" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "capital pressure verification state" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "Cross-lane questions expose priority" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "Business-scope industry/product extraction" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.INDUSTRY_PRODUCT_EXTRACTION"
    )
    assert any(
        "source_resilience_profile" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "recurring_failure_patterns" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "source_resilience_profile directly" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "One-click readiness now surfaces source_resilience_profile" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "source_resilience_needs_operator_recovery" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "One-click readiness exposes source resilience recovery status" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "Word output opens as a .docx" in gate["gate"]
        for gate in board["acceptance_gates"]["P2"]
        if gate["requirement_id"] == "P2.PRODUCTIZED_REPORT_OUTPUTS"
    )
    productized_report = requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]
    assert "three productized forms" in productized_report["user_goal"]
    assert any("no data reduction" in action for action in productized_report["next_actions"])
    assert any(
        "Third output form has an owner-confirmed specification" in gate["gate"]
        for gate in board["acceptance_gates"]["P2"]
        if gate["requirement_id"] == "P2.PRODUCTIZED_REPORT_OUTPUTS"
    )
    assert any(
        gate["requirement_id"] == "P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION"
        and "Weak entity_match" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
    )


def test_office_chat_packet_builder() -> None:
    from core.office_chat import build_office_chat_packet
    packet = build_office_chat_packet("Demo Company", {}, {})
    assert len(packet.messages) > 0
    assert packet.company == "Demo Company"
    assert "qian-shou-zheng" in packet.active_roles


def test_office_chat_data_contract_rules() -> None:
    from core.office_chat import build_office_chat_packet
    packet=build_office_chat_packet("Demo Company",{},{"controller_candidate_count":1})
    sentinel_msgs=[m for m in packet.messages if m.role_id=="an-shao"]
    assert all(m.msg_type=="sentinel_dm" for m in sentinel_msgs)
    assert packet.company=="Demo Company"
    assert len(packet.active_roles)>0


def test_persona_roles_exist_in_investigation():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        pd = pk.get("profile_brief",{}) or pk.get("persona_surface",{}) or {}
        assert pd is not None
    asyncio.run(run())
