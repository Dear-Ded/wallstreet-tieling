#!/usr/bin/env python3
"""Tests for executable development requirement levels."""
from __future__ import annotations

from core.development_requirements import build_development_requirements_board


def test_development_requirements_board_classifies_current_release_work() -> None:
    board = build_development_requirements_board()

    assert board["type"] == "development_requirements_board"
    assert board["version"] == "0.5.0"
    assert board["completion_percent"] == 94
    assert board["summary"]["by_level"]["P0"] >= 6
    assert board["summary"]["p0_open_count"] >= 1
    assert board["summary"]["desktop_agent_delivery"] == "desktop_agent_alpha_release_candidate"
    assert board["delivery_decision"]["type"] == "development_delivery_decision"
    assert board["delivery_decision"]["current_target"] == "desktop_agent_alpha"
    assert board["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert board["delivery_decision"]["desktop_agent_release_candidate"] is True
    assert board["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert board["delivery_decision"]["p0_min_completion_percent"] >= 94
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
    assert requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["completion_percent"] == 98
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
        "public_origin_execution_summary" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "report_section_batches" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "qyyjt_public_origin_handoff" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "bridges coverage gap domains" in item
        for item in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["implemented"]
    )
    assert any(
        "execution summary" in gate
        for gate in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["acceptance_gates"]
    )
    assert any(
        "qyyjt_public_origin_handoff.report_section_batches" in gate
        for gate in requirements["P0.QYYJT_CURRENT_VERSION_PARITY"]["acceptance_gates"]
    )
    assert any(
        "public_origin_gap_bridge" in gate
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
    assert requirements["P1.PUBLIC_SOURCE_BREADTH"]["completion_percent"] == 95
    assert requirements["P1.INDUSTRY_PRODUCT_EXTRACTION"]["completion_percent"] == 95
    assert requirements["P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION"]["completion_percent"] == 98
    assert requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["completion_percent"] == 98
    assert requirements["P0.CONTROLLER_UBO_SUBJECT_PROFILE"]["completion_percent"] == 98
    assert requirements["P0.REPORT_VALUE_COGNITION"]["completion_percent"] == 98
    assert requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["completion_percent"] == 98
    assert requirements["P1.OPERATIONAL_OBSERVABILITY"]["completion_percent"] == 94
    assert requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["completion_percent"] == 94
    assert requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]["completion_percent"] == 44
    assert requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]["status"] == "in_progress"
    assert any(
        "blocked recovery execution preview" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "report-admission results" in item
        for item in requirements["P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION"]["implemented"]
    )
    assert any(
        "one_click_readiness" in item
        for item in requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["implemented"]
    )
    assert any(
        "goods_economics_closure_step" in item
        for item in requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["implemented"]
    )
    assert any(
        "people_control_closure_step" in item
        for item in requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["implemented"]
    )
    assert any(
        "public_origin_gap_bridge" in item
        for item in requirements["P0.ONE_CLICK_PRODUCT_LOOP"]["implemented"]
    )
    assert any(
        "Coverage-gap handling now links missing or empty domains" in item
        for item in requirements["P1.PUBLIC_SOURCE_BREADTH"]["implemented"]
    )
    assert any(
        "Public people profile now splits controller/UBO" in item
        for item in requirements["P1.PUBLIC_SOURCE_BREADTH"]["implemented"]
    )
    assert any(
        "Subject-profile controller candidates" in item
        for item in requirements["P0.CONTROLLER_UBO_SUBJECT_PROFILE"]["implemented"]
    )
    assert any(
        "people_control_closure_step" in item
        for item in requirements["P1.PUBLIC_SOURCE_BREADTH"]["implemented"]
    )
    assert any(
        "China-style fixture-pack" in item
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
        "control_path_closure_step" in item
        for item in requirements["P0.CONTROLLER_UBO_SUBJECT_PROFILE"]["implemented"]
    )
    assert any(
        "control_path_verification_queue" in item and "agent-handoff" in item
        for item in requirements["P0.CONTROLLER_UBO_SUBJECT_PROFILE"]["implemented"]
    )
    assert any(
        "control_path_source_family_summary" in item
        for item in requirements["P0.CONTROLLER_UBO_SUBJECT_PROFILE"]["implemented"]
    )
    assert any(
        "reliance_limitations" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "agent-handoff exports" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "capital_exposure is now mirrored" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "relationship_graph_audit summary" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "capital_verification_queue" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "source_family_summary" in item and "Capital pressure" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "recovery_execution_queue" in item
        for item in requirements["P0.REPORT_VALUE_COGNITION"]["implemented"]
    )
    assert any(
        "Package variant tests" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "relationship graph audit summary" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "source recovery execution queue" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "pytest-asyncio auto mode" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "2026-07-06 08:24" in item and "799 Python tests" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "2026-07-05 21:24" in item and "223 Python tests" in item and "needs_admission=0" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "OpenSanctions and IDB public dataset source strengthening implementation_pack" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "agent_tool_adapters first_run_recipe preserves source_strengthening_queue" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "source_strengthening risk_enforcement lane routing" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "source_strengthening execution_plan agent handoff" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "directory bundle verifier_output_fields handoff" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "delivery_decision" in item and "desktop-agent alpha" in item
        for item in requirements["P0.RELEASE_ACCEPTANCE_HYGIENE"]["implemented"]
    )
    assert any(
        "relationship graph audit summary" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "capital_verification_queue" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "capital-pressure and graph-capital source-family summaries" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "source_health.recovery_execution_queue" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "closure_steps.control_path_verification_queue" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "subject-profile controller candidate" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
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
        "control_path_closure_step" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.CONTROLLER_UBO_SUBJECT_PROFILE"
    )
    assert any(
        "closure_steps.control_path_verification_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.CONTROLLER_UBO_SUBJECT_PROFILE"
    )
    assert any(
        "source-family provenance" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.CONTROLLER_UBO_SUBJECT_PROFILE"
    )
    assert any(
        "reliance_limitations" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "Report export handoffs expose reliance limitation summaries" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "capital_exposure is mirrored into one-click" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "relationship_graph_audit" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "capital_verification_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "source-family provenance" in gate["gate"] and "Capital pressure" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "source_health.recovery_execution_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "relationship graph audit summary" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.RELEASE_ACCEPTANCE_HYGIENE"
    )
    assert any(
        "source recovery execution queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.RELEASE_ACCEPTANCE_HYGIENE"
    )
    assert any(
        "Node Python-spawn failures" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.RELEASE_ACCEPTANCE_HYGIENE"
    )
    assert any(
        "Cross-lane questions expose priority" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.REPORT_VALUE_COGNITION"
    )
    assert any(
        "goods_economics_closure_step" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.ONE_CLICK_PRODUCT_LOOP"
    )
    assert any(
        "people_control_closure_step" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.ONE_CLICK_PRODUCT_LOOP"
    )
    assert any(
        "public_origin_gap_bridge" in gate["gate"]
        for gate in board["acceptance_gates"]["P0"]
        if gate["requirement_id"] == "P0.ONE_CLICK_PRODUCT_LOOP"
    )
    assert any(
        "Coverage gaps are bridged to public-origin actions" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.PUBLIC_SOURCE_BREADTH"
    )
    assert any(
        "Public people/control leads remain corroboration-needed" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.PUBLIC_SOURCE_BREADTH"
    )
    assert any(
        "Public people/control closure is exposed" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.PUBLIC_SOURCE_BREADTH"
    )
    assert any(
        "Business-scope industry/product extraction" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.INDUSTRY_PRODUCT_EXTRACTION"
    )
    assert any(
        "unit-economics, bargaining-power, and competitive-landscape" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.INDUSTRY_PRODUCT_EXTRACTION"
    )
    assert any(
        "Source-specific public web page signals" in gate["gate"]
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
        "source_health_trends" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "connector_recovery_queue" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "source_health_trend_snapshot" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "source_health_trend_digest" in item
        for item in requirements["P1.OPERATIONAL_OBSERVABILITY"]["implemented"]
    )
    assert any(
        "recovery_execution_queue" in item
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
        "source_health_trend_snapshot" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "source_health_trend_digest" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "source_health.recovery_execution_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.OPERATIONAL_OBSERVABILITY"
    )
    assert any(
        "agent-handoff.json" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "source_health.recovery_execution_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "manifest_fields" in item and "delivery_checklist" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "bin/verify_report_bundle.py" in item and "bundle verification" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "verifier_output_fields" in item and "bundle_ready_to_verify" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "Node offline-fixture fallback export-dir" in item and "DOCX unavailable" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "Runtime MCP tool descriptions" in item and "trust_boundaries" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "report_exports.agent_decision_digest" in item and "--export-dir" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "API smoke, Codex MCP smoke, agent-host smoke, and acceptance" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "latest_acceptance_evidence" in item and "default one-click result" in item
        for item in requirements["P1.RUNTIME_SURFACE_CONTRACTS"]["implemented"]
    )
    assert any(
        "delivery_files, bundle_integrity, delivery_checklist, trust_boundaries, decision_digest, agent_summary, and next_actions" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "Node fallback export-dir writes agent-handoff.json" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "Runtime MCP server and deploy MCP manifest" in gate["gate"] and "decision_digest" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "report_exports.agent_decision_digest" in gate["gate"] and "first_action" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "latest_acceptance_evidence" in gate["gate"] and "timestamp/counts" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "agent-handoff schema_fields omit delivery_files, bundle_integrity" in gate["gate"] and "decision_digest" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "verifier_output_fields" in gate["gate"] and "bundle_ready_to_verify" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "capital_pressure_source_family_summary" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "closure_steps.control_path_verification_queue" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "subject-profile controller candidates" in gate["gate"]
        for gate in board["acceptance_gates"]["P1"]
        if gate["requirement_id"] == "P1.RUNTIME_SURFACE_CONTRACTS"
    )
    assert any(
        "Word output opens as a .docx" in gate["gate"]
        and "source provenance appendix" in gate["gate"]
        for gate in board["acceptance_gates"]["P2"]
        if gate["requirement_id"] == "P2.PRODUCTIZED_REPORT_OUTPUTS"
    )
    productized_report = requirements["P2.PRODUCTIZED_REPORT_OUTPUTS"]
    assert "three productized forms" in productized_report["user_goal"]
    assert any("native chart summary panels" in item for item in productized_report["implemented"])
    assert any("delivery_checklist" in item for item in productized_report["implemented"])
    assert any("file_manifest sha256 rows" in item and "bounded agent_summary" in item for item in productized_report["implemented"])
    assert any("verify_report_bundle.py" in item and "tampered" in item for item in productized_report["implemented"])
    assert any("decision_digest schema" in item and "broken handoff routing" in item for item in productized_report["implemented"])
    assert any("source_provenance_appendix" in item and "evidence source index" in item for item in productized_report["implemented"])
    assert any("premium_html profile" in item and "premium visual QA checklist" in item for item in productized_report["implemented"])
    assert any("runtime contract and full-fidelity markers" in item for item in productized_report["gaps"])
    assert any("polished screen-review package" in action for action in productized_report["next_actions"])
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
    assert any(
        gate["requirement_id"] == "P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION"
        and "weak/review entity_match remain leads" in gate["gate"]
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
