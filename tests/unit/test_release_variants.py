#!/usr/bin/env python3
"""Release-portal contract tests for product variants."""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VARIANTS_PATH = PROJECT_ROOT / "release" / "variants.yaml"
PACKAGE_PATH = PROJECT_ROOT / "package.json"
MCP_MANIFEST_PATH = PROJECT_ROOT / "deploy" / "mcp-server.json"
AGENT_RELEASE_CI_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
AGENT_HOST_SMOKE_CHECKLIST_PATH = PROJECT_ROOT / "docs" / "AGENT_HOST_SMOKE_CHECKLIST.md"
MULTI_PLATFORM_GUIDE_PATH = PROJECT_ROOT / "deploy" / "multi-platform-guide.md"


def _load_variants() -> dict:
    return yaml.safe_load(VARIANTS_PATH.read_text(encoding="utf-8"))


def test_release_matrix_defines_desktop_agent_target_variants():
    data = _load_variants()

    assert set(data["variants"]) == {
        "universal",
        "codex",
        "claude_code",
        "hermes",
        "doubao_office_task_mode",
        "open_claude_agents",
        "workbuddy_expert_team",
    }


def test_release_variant_entrypoints_exist():
    data = _load_variants()

    for variant_name, variant in data["variants"].items():
        for entrypoint in variant["entrypoints"]:
            target = PROJECT_ROOT / entrypoint
            assert target.exists(), f"{variant_name} entrypoint missing: {entrypoint}"


def test_codex_is_primary_delivery_lane_and_workbuddy_is_secondary():
    data = _load_variants()
    codex = data["variants"]["codex"]
    workbuddy = data["variants"]["workbuddy_expert_team"]

    assert codex["delivery_priority"]["lane"] == "primary"
    assert codex["delivery_priority"]["rank"] == 1
    assert "mainline release target" in codex["delivery_priority"]["reason"]
    assert workbuddy["delivery_priority"]["lane"] == "secondary"
    assert workbuddy["delivery_priority"]["rank"] > codex["delivery_priority"]["rank"]
    assert "codex" in workbuddy["delivery_priority"]["depends_on"]


def test_release_matrix_keeps_product_claims_tied_to_core_capabilities():
    data = _load_variants()

    shared_core = set(data["product"]["shared_core"])
    assert "core.enterprise_cognition.EnterpriseCognitionEngine" in shared_core
    assert "core.intelligence_retrieval.InvestigativeRetrievalPlanner" in shared_core
    assert "core.risk_event_store.RiskEventStore" in shared_core

    for variant in data["variants"].values():
        assert variant["readiness"] in {"planned", "alpha", "beta", "stable"}
        assert variant["required_capabilities"]
        assert variant["next_gate"]


def test_release_gates_cover_claims_security_and_quality():
    data = _load_variants()

    gates = data["release_gates"]
    assert {"public_claims", "security", "quality"} <= set(gates)
    assert any("No API keys" in rule for rule in gates["security"])
    assert any("feature claim" in rule for rule in gates["public_claims"])
    assert any("evidence gaps" in rule for rule in gates["quality"])
    assert any("agent_tool_adapters" in rule for rule in gates["quality"])


def test_release_contract_can_be_loaded_by_runtime_api():
    from core.release_contract import (
        delivery_audit_brief,
        load_release_contract,
        objective_completion_audit_brief,
        release_preflight_brief,
        release_readiness_brief,
    )

    contract = load_release_contract()
    brief = release_readiness_brief()
    preflight = release_preflight_brief()
    audit = delivery_audit_brief()
    objective_audit = objective_completion_audit_brief()

    assert contract["type"] == "release_contract"
    assert contract["version"] == "0.5.0"
    assert contract["summary"]["variant_count"] == 7
    assert contract["persona_surface"]["type"] == "persona_surface_brief"
    assert contract["persona_surface"]["role_count"] == 13
    persona_lane_fields = {
        item["lane"]: set(item["packet_fields"])
        for item in contract["persona_surface"]["runtime_lane_bindings"]
    }
    assert "one_click_readiness.operator_work_queue" in persona_lane_fields["data_sources"]
    assert "qyyjt_public_origin_handoff" in persona_lane_fields["data_sources"]
    assert "one_click_readiness.reliance_limitations" in persona_lane_fields["verification"]
    assert "one_click_readiness.capital_verification_top_step" in persona_lane_fields["finance"]
    assert "one_click_readiness.relationship_graph_audit_top_step" in persona_lane_fields["people"]
    assert contract["variants"]["codex"]["entrypoints"]
    assert brief["type"] == "release_readiness_brief"
    assert brief["persona_surface"]["role_count"] == 13
    assert brief["delivery_decision"]["type"] == "release_delivery_decision"
    assert brief["delivery_decision"]["current_target"] == "desktop_agent_alpha"
    assert brief["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert brief["delivery_decision"]["desktop_agent_release_candidate"] is True
    assert brief["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert brief["delivery_decision"]["runtime_blocking_surface_count"] == 0
    assert brief["delivery_decision"]["remaining_variant_blocker_count"] == 0
    assert brief["delivery_decision"]["variant_next_gate_count"] == len(brief["blockers"])
    assert "do not block desktop-agent alpha delivery" in brief["delivery_decision"]["variant_next_gate_policy"]
    assert "desktop-agent alpha delivery only" in brief["delivery_decision"]["policy"]
    closure = brief["delivery_closure"]
    assert closure["type"] == "desktop_agent_alpha_delivery_closure"
    assert closure["status"] == "release_candidate"
    assert closure["target"] == "desktop_agent_alpha"
    assert closure["document"] == "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md"
    assert closure["baseline_sequence"] == [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
    ]
    assert "aggregate_subject" in closure["followup_tools"]
    assert "npm run acceptance" in closure["required_verification_commands"]
    assert "npm pack --dry-run --json" in closure["required_verification_commands"]
    assert "npm run delivery:audit" in closure["required_verification_commands"]
    assert "npm run objective:audit" in closure["required_verification_commands"]
    assert "one_click_readiness.capital_risk_panel" in closure["required_preserved_fields"]
    assert "one_click_readiness.capital_risk_panel.report_visibility" in closure["required_preserved_fields"]
    assert "report_exports.premium_html" in closure["required_preserved_fields"]
    assert "report_exports.portable_html.premium_profile" in closure["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in closure["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility" in closure["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in closure["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in closure["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.source_strengthening" in closure["required_preserved_fields"]
    for field in [
        "qyyjt_public_origin_handoff.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
    ]:
        assert field in closure["required_preserved_fields"]
    assert "always-on continuous monitoring" in closure["not_current_release"]
    assert any("marketplace/operator screenshots" in item for item in closure["open_submission_items"])
    assert brief["latest_acceptance_evidence"]["type"] == "latest_acceptance_evidence"
    assert brief["latest_acceptance_evidence"]["status"] == "passed"
    assert brief["latest_acceptance_evidence"]["command"] == "npm run acceptance"
    assert brief["latest_acceptance_evidence"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai"
    assert brief["latest_acceptance_evidence"]["python_tests_passed"] == 799
    focused_regression = brief["latest_acceptance_evidence"]["post_acceptance_focused_regressions"][0]
    assert focused_regression["observed_at"] == "2026-07-05 21:24 Asia/Shanghai"
    assert focused_regression["python_tests_passed"] == 223
    assert focused_regression["python_tests_skipped"] == 2
    assert "source_strengthening completion state with needs_admission=0" in focused_regression["covers"]
    premium_regression = brief["latest_acceptance_evidence"]["post_acceptance_focused_regressions"][1]
    assert premium_regression["observed_at"] == "2026-07-05 22:01 Asia/Shanghai"
    assert premium_regression["python_tests_passed"] == 14
    assert premium_regression["python_tests_skipped"] == 0
    assert "npm run agent:host-smoke" in premium_regression["node_smokes"]
    assert "npm run codex:mcp-smoke" in premium_regression["node_smokes"]
    assert "premium_html report_exports runtime contract" in premium_regression["covers"]
    assert "directory agent-handoff report_visibility.premium_html" in premium_regression["covers"]
    assert "Codex primary premium report smoke coverage" in premium_regression["covers"]
    assert "Codex primary delivery lane and WorkBuddy secondary branch priority" in brief["latest_acceptance_evidence"]["covers"]
    assert "connector_catalog source_strengthening_queue" in brief["latest_acceptance_evidence"]["covers"]
    assert "official China source strengthening implementation_pack" in brief["latest_acceptance_evidence"]["covers"]
    assert "OpenSanctions and IDB public dataset source strengthening implementation_pack" in brief["latest_acceptance_evidence"]["covers"]
    assert "agent_tool_adapters first_run_recipe preserves source_strengthening_queue" in brief["latest_acceptance_evidence"]["covers"]
    assert "source_strengthening risk_enforcement lane routing" in brief["latest_acceptance_evidence"]["covers"]
    assert "source_strengthening execution_plan agent handoff" in brief["latest_acceptance_evidence"]["covers"]
    assert "manifest agent_summary deep drift verification" in brief["latest_acceptance_evidence"]["covers"]
    assert brief["latest_acceptance_evidence"]["python_tests_skipped"] == 9
    assert "agent_tool_adapters runtime contract" in brief["latest_acceptance_evidence"]["covers"]
    assert "agent_tool_adapters premium_html preservation guards" in brief["latest_acceptance_evidence"]["covers"]
    assert "premium_html report_exports runtime contract" in brief["latest_acceptance_evidence"]["covers"]
    assert "directory agent-handoff report_visibility.premium_html" in brief["latest_acceptance_evidence"]["covers"]
    assert "WorkBuddy investigate_company host smoke" in brief["latest_acceptance_evidence"]["covers"]
    assert "host-smoke Python runtime resolution" in brief["latest_acceptance_evidence"]["covers"]
    assert "desktop-agent installation handoff" in brief["latest_acceptance_evidence"]["covers"]
    assert "release_preflight package go/no-go gate" in brief["latest_acceptance_evidence"]["covers"]
    assert "package privacy scan gate" in brief["latest_acceptance_evidence"]["covers"]
    assert "npm package dry-run content gate" in brief["latest_acceptance_evidence"]["covers"]
    assert "terminology guard public-copy hygiene" in brief["latest_acceptance_evidence"]["covers"]
    assert "report_exports.agent_decision_digest packet routing" in brief["latest_acceptance_evidence"]["covers"]
    assert "directory bundle verifier_output_fields handoff" in brief["latest_acceptance_evidence"]["covers"]
    assert "directory bundle verification_recipe handoff" in brief["latest_acceptance_evidence"]["covers"]
    assert "DOCX source provenance appendix and evidence source index" in brief["latest_acceptance_evidence"]["covers"]
    assert "DOCX relationship/capital appendix and delivery checklist" in brief["latest_acceptance_evidence"]["covers"]
    assert "source_resilience agent_autorun" in brief["latest_acceptance_evidence"]["covers"]
    assert "QYYJT public-origin agent_autorun" in brief["latest_acceptance_evidence"]["covers"]
    assert "capital risk and relationship autorun routes" in brief["latest_acceptance_evidence"]["covers"]
    assert "report_artifact_agent_autorun" in brief["latest_acceptance_evidence"]["covers"]
    assert brief["release_preflight"] == preflight
    assert preflight["type"] == "desktop_agent_alpha_release_preflight"
    assert preflight["status"] == "ready_for_local_packaging"
    assert preflight["package_candidate_ready"] is True
    assert preflight["final_submission_ready"] is False
    assert preflight["blocking_items"] == []
    assert "npm pack --dry-run --json" in preflight["required_verification_commands"]
    assert "npm run release:privacy-scan" in preflight["required_verification_commands"]
    assert "npm run delivery:audit" in preflight["required_verification_commands"]
    assert "npm run objective:audit" in preflight["required_verification_commands"]
    assert "marketplace/operator screenshots" in " ".join(preflight["final_submission_blockers"])
    assert preflight["latest_acceptance"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai"
    assert preflight["packaging_review"]["dry_run_command"] == "npm pack --dry-run --json"
    assert preflight["packaging_review"]["privacy_command"] == "npm run release:privacy-scan"
    assert "desktop-agent alpha release candidate" in preflight["agent_handoff"]["safe_claim"].lower()
    assert "not final polished product launch readiness" in preflight["agent_handoff"]["safe_claim"].lower()
    assert audit["type"] == "desktop_agent_alpha_delivery_audit"
    assert audit["target"] == "desktop_agent_alpha"
    assert audit["status"] == "pass"
    assert audit["ready_for_local_packaging"] is True
    assert audit["final_submission_ready"] is False
    assert audit["full_product_status"] == "not_final_release_ready"
    assert audit["failed_checks"] == []
    assert audit["coverage"]["source_resilience"]["covered"] is True
    assert audit["coverage"]["qyyjt_public_origin"]["covered"] is True
    assert audit["coverage"]["relationship_graph"]["covered"] is True
    assert audit["coverage"]["capital_risk"]["covered"] is True
    assert audit["coverage"]["report_visibility"]["covered"] is True
    assert audit["coverage"]["workbuddy_expert_team"]["covered"] is True
    assert audit["verification_evidence"]["latest_acceptance"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai"
    assert "not final polished product launch readiness" in audit["safe_claim"].lower()
    assert objective_audit["type"] == "objective_completion_audit"
    assert objective_audit["status"] == "complete"
    assert objective_audit["release_gate"]["delivery_audit_status"] == "pass"
    assert objective_audit["completion_percent"] == 100
    requirement_status = {item["id"]: item["status"] for item in objective_audit["requirements"]}
    assert requirement_status["source_resilience"] == "complete"
    assert requirement_status["qyyjt_public_origin_mapping"] == "complete"
    assert requirement_status["relationship_graph"] == "complete"
    assert requirement_status["capital_risk"] == "complete"
    assert requirement_status["report_visibility"] == "complete"
    assert requirement_status["desktop_agent_delivery"] == "complete"
    assert requirement_status["workbuddy_expert_team_compatibility"] == "complete"
    assert requirement_status["superpowers_final_review"] == "complete"
    assert objective_audit["failed_requirements"] == []
    assert brief["runtime_delivery"]["type"] == "runtime_delivery_summary"
    assert brief["runtime_delivery"]["agent_first"] is True
    assert brief["runtime_delivery"]["polished_html_current_release"] is False
    assert brief["runtime_delivery"]["acceptance_status_counts"]["proof_defined"] >= 7
    assert brief["runtime_delivery"]["release_blocking_surface_count"] == 0
    assert brief["runtime_delivery"]["proof_test_count"] >= 6
    assert brief["runtime_delivery"]["focused_test_command"].startswith("python -m pytest ")
    surfaces = {item["surface"] for item in brief["runtime_delivery"]["surfaces"]}
    assert "qyyjt_public_origin_execution_queue" in surfaces
    assert "agent_tool_adapters" in surfaces
    assert "desktop_agent_installation_handoff" in surfaces
    assert "risk_graph_capital_exposure" in surfaces
    assert "source_resilience_recovery_step" in surfaces
    assert "source_repair_priority_queue" in surfaces
    assert "source_health_trend_snapshot" in surfaces
    assert "source_health_release_warnings" in surfaces
    assert "operator_work_queue" in surfaces
    assert "control_path_closure_step" in surfaces
    assert "goods_economics_closure_step" in surfaces
    assert "people_control_closure_step" in surfaces
    assert "printable_docx_export" in surfaces
    assert "aggregate_subject_followup" in surfaces
    install_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "desktop_agent_installation_handoff")
    assert "agent_tool_adapter_manifest.installation_handoff.default_install_command" in install_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.installation_handoff.host_matrix" in install_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.installation_handoff.failure_routing" in install_surface["entrypoints"]
    assert "tools/run-python.ps1" in install_surface["entrypoints"]
    assert "package.json scripts.api:smoke" in install_surface["entrypoints"]
    aggregate_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "aggregate_subject_followup")
    assert "npx wallstreet-tieling --aggregate-subject <subject_id>" in aggregate_surface["entrypoints"]
    assert "POST /api/aggregate" in aggregate_surface["entrypoints"]
    assert "MCP aggregate_subject" in aggregate_surface["entrypoints"]
    assert "aggregate_subject.subject" in aggregate_surface["entrypoints"]
    assert "aggregate_subject.relationship_graph" in aggregate_surface["entrypoints"]
    assert "aggregate_subject.profile" in aggregate_surface["entrypoints"]
    qyyjt_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "qyyjt_public_origin_execution_queue")
    assert "investigation_packet.qyyjt_public_origin_handoff" in qyyjt_surface["entrypoints"]
    assert "investigation_packet.qyyjt_public_origin_handoff.report_section_batches" in qyyjt_surface["entrypoints"]
    assert "investigation_packet.qyyjt_public_origin_handoff.section_work_orders" in qyyjt_surface["entrypoints"]
    assert "investigation_packet.qyyjt_public_origin_handoff.section_execution_summary" in qyyjt_surface["entrypoints"]
    assert "investigation_packet.qyyjt_public_origin_handoff.top_ready_section_work_order" in qyyjt_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.section_work_orders" in qyyjt_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.section_execution_summary" in qyyjt_surface["entrypoints"]
    assert "one_click_readiness.public_origin_gap_bridge" in qyyjt_surface["entrypoints"]
    assert "one_click_readiness.public_origin_gap_bridge_top_action" in qyyjt_surface["entrypoints"]
    assert "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary" in qyyjt_surface["entrypoints"]
    agent_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "agent_tool_adapters")
    assert "agent_tool_adapter_manifest.installation_handoff" in agent_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.adapters[].install_handoff" in agent_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.execution_matrix" in agent_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.execution_matrix[].done_condition" in agent_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.first_run_recipe" in agent_surface["entrypoints"]
    assert "agent_tool_adapter_manifest.first_run_recipe.preserve_before_summarizing" in agent_surface["entrypoints"]
    capital_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "risk_graph_capital_exposure")
    assert "summary.capital_exposure.verification_queue" in capital_surface["entrypoints"]
    assert "summary.capital_exposure.relationship_audit_queue" in capital_surface["entrypoints"]
    assert "one_click_readiness.graph_capital_exposure" in capital_surface["entrypoints"]
    assert "one_click_readiness.graph_capital_exposure_top_step" in capital_surface["entrypoints"]
    assert "one_click_readiness.graph_capital_exposure_source_family_summary" in capital_surface["entrypoints"]
    assert "one_click_readiness.capital_pressure_source_family_summary" in capital_surface["entrypoints"]
    assert "one_click_readiness.capital_verification_queue" in capital_surface["entrypoints"]
    assert "one_click_readiness.capital_verification_top_step" in capital_surface["entrypoints"]
    assert "one_click_readiness.capital_risk_panel" in capital_surface["entrypoints"]
    assert "one_click_readiness.capital_risk_panel.report_visibility" in capital_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in capital_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.capital_and_relationship.risk_panel" in capital_surface["entrypoints"]
    relationship_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "relationship_graph_audit_queue")
    assert "one_click_readiness.relationship_graph_audit_queue" in relationship_surface["entrypoints"]
    assert "one_click_readiness.relationship_graph_audit_top_step" in relationship_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit" in relationship_surface["entrypoints"]
    source_repair_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "source_repair_priority_queue")
    assert "monitoring_seed.source_repair_priority_queue" in source_repair_surface["entrypoints"]
    assert "one_click_readiness.source_repair_top_action" in source_repair_surface["entrypoints"]
    source_health_snapshot_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "source_health_trend_snapshot")
    assert "monitoring_seed.source_health_trend_snapshot" in source_health_snapshot_surface["entrypoints"]
    assert "one_click_readiness.source_health_trend_top_source" in source_health_snapshot_surface["entrypoints"]
    assert "one_click_readiness.source_health_trend_digest" in source_health_snapshot_surface["entrypoints"]
    assert "one_click_readiness.source_health_trend_digest.actionability" in source_health_snapshot_surface["entrypoints"]
    assert "one_click_readiness.source_health_trend_digest.subject_risk_verdict_allowed" in source_health_snapshot_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.source_health.digest" in source_health_snapshot_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.source_health_trend_top_source" in source_health_snapshot_surface["entrypoints"]
    source_health_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "source_health_release_warnings")
    assert "/api/monitor/source-health" in source_health_surface["entrypoints"]
    assert "source_health.connector_recovery_queue" in source_health_surface["entrypoints"]
    assert "source_health.release_readiness_warnings" in source_health_surface["entrypoints"]
    source_health_handoff = brief["runtime_delivery"]["source_health_operator_handoff"]
    assert source_health_handoff["default_mode"] == "on_demand_not_background_monitoring"
    assert "connector_recovery_queue" not in source_health_handoff["warning_fields"]
    assert "operator_action" in source_health_handoff["recovery_queue_fields"]
    assert "retry_policy" in source_health_handoff["recovery_queue_fields"]
    assert "release_gate" in source_health_handoff["warning_fields"]
    source_resilience_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "source_resilience_recovery_step")
    assert "source_failure_summary.source_resilience_profile.retry_policy" in source_resilience_surface["entrypoints"]
    assert "one_click_readiness.source_resilience_retry_policy" in source_resilience_surface["entrypoints"]
    assert "monitoring_seed.recovery_execution_queue.queue.retry_policy" in source_resilience_surface["entrypoints"]
    assert "monitoring_seed.recovery_execution_queue.queue.replay_route" in source_resilience_surface["entrypoints"]
    assert "monitoring_seed.recovery_execution_queue.blocked_preview.replay_route" in source_resilience_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue" in source_resilience_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.retry_policy" in source_resilience_surface["entrypoints"]
    operator_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "operator_work_queue")
    assert "one_click_readiness.operator_work_queue" in operator_surface["entrypoints"]
    assert "one_click_readiness.public_origin_gap_bridge" in operator_surface["entrypoints"]
    assert "one_click_readiness.graph_capital_exposure" in operator_surface["entrypoints"]
    assert "one_click_readiness.reliance_limitations" in operator_surface["entrypoints"]
    assert "one_click_readiness.acceptance_closure_summary" in operator_surface["entrypoints"]
    assert "one_click_readiness.acceptance_closure_status" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.acceptance_closure_summary" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.graph_capital_exposure_top_step" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.public_origin_gap_bridge_top_action" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.people_control_closure_step" in operator_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.acceptance_closure" in operator_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.closure_steps" in operator_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards.reliance_limitation_top_action" in operator_surface["entrypoints"]
    control_path_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "control_path_closure_step")
    assert "enterprise_cognition.control_ownership.control_path_verification_queue" in control_path_surface["entrypoints"]
    assert "one_click_readiness.control_path_closure_needed" in control_path_surface["entrypoints"]
    assert "one_click_readiness.control_path_closure_step" in control_path_surface["entrypoints"]
    assert "one_click_readiness.control_path_source_family_summary" in control_path_surface["entrypoints"]
    assert "one_click_readiness.operator_work_queue" in control_path_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue" in control_path_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards" in control_path_surface["entrypoints"]
    subject_source_family_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "subject_profile_controller_source_families")
    assert "graph.diagnostics.subject_profile.controller_candidates.source_family_summary" in subject_source_family_surface["entrypoints"]
    assert "graph.diagnostics.subject_profile.controller_candidates.control_path_summaries.source_family_summary" in subject_source_family_surface["entrypoints"]
    assert "graph.diagnostics.subject_profile.relationship_graph.edges.source_family_summary" in subject_source_family_surface["entrypoints"]
    assert "enterprise_cognition.control_ownership.controller_candidates.source_family_summary" in subject_source_family_surface["entrypoints"]
    assert "enterprise_cognition.control_ownership.control_paths.source_family_summary" in subject_source_family_surface["entrypoints"]
    goods_economics_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "goods_economics_closure_step")
    assert "one_click_readiness.goods_economics_closure_needed" in goods_economics_surface["entrypoints"]
    assert "one_click_readiness.goods_economics_closure_step" in goods_economics_surface["entrypoints"]
    assert "one_click_readiness.operator_work_queue" in goods_economics_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards" in goods_economics_surface["entrypoints"]
    people_control_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "people_control_closure_step")
    assert "one_click_readiness.people_control_closure_needed" in people_control_surface["entrypoints"]
    assert "one_click_readiness.people_control_closure_step" in people_control_surface["entrypoints"]
    assert "enterprise_cognition.public_people_profile" in people_control_surface["entrypoints"]
    assert "enterprise_cognition.people_flow_profile" in people_control_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.closure_steps.people_control" in people_control_surface["entrypoints"]
    assert "report_exports.print_package.operational_handoff.cards" in people_control_surface["entrypoints"]
    docx_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "printable_docx_export")
    assert "report_exports.print_package.operational_handoff" in docx_surface["entrypoints"]
    assert "report_exports.print_package.delivery_checklist" in docx_surface["entrypoints"]
    assert "report_exports.print_package.docx.renderer_capabilities.official_document_metadata" in docx_surface["entrypoints"]
    assert "report_exports.print_package.docx.renderer_capabilities.red_head_separator_rule" in docx_surface["entrypoints"]
    assert "report_exports.print_package.docx.renderer_capabilities.native_chart_summary_panels" in docx_surface["entrypoints"]
    assert "report_exports.print_package.docx.renderer_capabilities.embedded_local_image_evidence" in docx_surface["entrypoints"]
    assert "report_exports.print_package.source_provenance_appendix" in docx_surface["entrypoints"]
    assert "report_exports.print_package.delivery_checklist.quality_checks.source_provenance_appendix_present" in docx_surface["entrypoints"]
    assert "word/document.xml official metadata table, red-head separator, and chart summary panels" in docx_surface["entrypoints"]
    assert "word/document.xml source provenance appendix and evidence source index" in docx_surface["entrypoints"]
    assert "word/media embedded local or data-uri image evidence" in docx_surface["entrypoints"]
    html_surface = next(item for item in brief["runtime_delivery"]["surfaces"] if item["surface"] == "portable_html_and_markdown_exports")
    assert "bin/investigate.py --export-html" in html_surface["entrypoints"]
    assert "bin/investigate.py --export-json" in html_surface["entrypoints"]
    assert "bin/investigate.py --export-dir" in html_surface["entrypoints"]
    assert "bin/verify_report_bundle.py <export-dir>" in html_surface["entrypoints"]
    assert "node_cli_offline_fixture_fallback_export_dir" in html_surface["entrypoints"]
    assert "node_cli_fallback_manifest.unavailable_outputs.docx" in html_surface["entrypoints"]
    assert "report_exports.agent_decision_digest" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verification_recipe" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verification_recipe.required_output_fields" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.bundle_ready_to_verify" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.acceptance_closure_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.premium_html_report_visibility_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.qyyjt_public_origin_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_resilience_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.relationship_graph_audit_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_strengthening_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_strengthening_runtime_companion_present" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.manifest_fields" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.manifest_fields.file_manifest" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.manifest_fields.agent_summary" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_files" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.bundle_integrity" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.bundle_verification" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_checklist" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.source_strengthening" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.trust_boundaries" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.decision_digest" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.next_actions" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.acceptance_closure" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.reliance_limitations" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.gap_bridge" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.capital_and_relationship.graph_capital_exposure" in html_surface["entrypoints"]
    assert "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit" in html_surface["entrypoints"]
    assert "report_exports.portable_html.first_screen_handoff_cards" in html_surface["entrypoints"]
    assert "report_exports.portable_html.delivery_checklist_source" in html_surface["entrypoints"]
    assert "report_exports.premium_html" in html_surface["entrypoints"]
    assert "report_exports.premium_html.acceptance_checklist" in html_surface["entrypoints"]
    assert "report_exports.premium_html.content_guarantees" in html_surface["entrypoints"]
    assert "report_exports.premium_html.forbidden_shortcuts" in html_surface["entrypoints"]
    assert "report_exports.portable_html.premium_profile" in html_surface["entrypoints"]
    assert "tests/unit/test_investigation.py::test_node_cli_offline_fallback_writes_agent_handoff_bundle" in html_surface["proof_tests"]
    assert all(item["acceptance_status"] == "proof_defined" for item in brief["runtime_delivery"]["surfaces"])
    assert all(item["acceptance_gate"] == "focused_tests_listed_and_entrypoints_declared" for item in brief["runtime_delivery"]["surfaces"])
    assert all(item["blocking_reason"] == "" for item in brief["runtime_delivery"]["surfaces"])
    proof_tests = {
        proof_test
        for item in brief["runtime_delivery"]["surfaces"]
        for proof_test in item["proof_tests"]
    }
    assert all(proof_test in brief["runtime_delivery"]["focused_test_command"] for proof_test in proof_tests)
    assert brief["blockers"]
    assert brief["contract"]["product"]["name"] == "wallstreet-tieling"


def test_claude_code_variant_is_alpha_with_adapter_doc():
    data = _load_variants()
    variant = data["variants"]["claude_code"]

    assert variant["readiness"] == "alpha"
    assert "CLAUDE.md" in variant["entrypoints"]
    assert "docs/CLAUDE_CODE_ADAPTER.md" in variant["entrypoints"]
    assert "docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md" in variant["entrypoints"]
    assert "deploy/mcp-server.json" in variant["entrypoints"]
    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in variant["entrypoints"]
    assert any("host smoke" in item for item in variant["next_gate"])
    assert any("knowledge-pack bundle" in item for item in variant["next_gate"])


def test_codex_variant_tracks_packaged_mcp_smoke_after_validator_pass():
    data = _load_variants()
    variant = data["variants"]["codex"]

    assert variant["readiness"] == "alpha"
    assert ".codex-plugin/plugin.json" in variant["entrypoints"]
    assert "docs/CODEX_MARKETPLACE_SUBMISSION_NOTES.md" in variant["entrypoints"]
    assert "docs/PLUGIN_MARKET_READINESS.md" in variant["entrypoints"]
    assert any("Codex CI workflow" in item for item in variant["next_gate"])
    assert any("host-neutral desktop-agent smoke" in item for item in variant["next_gate"])
    assert any("retrieval plan and cognition profile" in item for item in variant["next_gate"])
    assert any("marketplace submission screenshots" in item for item in variant["next_gate"])
    assert not any(item == "Run official plugin validator" for item in variant["next_gate"])
    assert not any(item.startswith("Add Codex smoke workflow") for item in variant["next_gate"])
    assert not any("final review notes" in item for item in variant["next_gate"])


def test_desktop_agent_variants_are_alpha_and_do_not_require_html_ui():
    data = _load_variants()

    for name in {"hermes", "doubao_office_task_mode", "open_claude_agents"}:
        variant = data["variants"][name]
        entrypoints = set(variant["entrypoints"])
        packaging = set(variant["packaging"])
        capabilities = " ".join(variant["required_capabilities"])

        assert variant["readiness"] == "alpha"
        assert "SKILL.md" in entrypoints
        assert {"bin/cli.js", "deploy/mcp-server.json", "docs/API_CONTRACTS.md"} & entrypoints
        assert {"CLI tool", "MCP server", "MCP deployment manifest", "REST API"} & packaging
        assert "HTML" not in capabilities or "No dependency on polished HTML UI" in capabilities

    hermes = data["variants"]["hermes"]
    assert "docs/HERMES_AGENT_SETUP.md" in hermes["entrypoints"]
    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in hermes["entrypoints"]
    assert any("timeout defaults" in item for item in hermes["next_gate"])

    open_agents = data["variants"]["open_claude_agents"]
    assert "docs/OPEN_AGENT_COMPATIBILITY.md" in open_agents["entrypoints"]
    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in open_agents["entrypoints"]
    assert any("environment variables" in item for item in open_agents["next_gate"])

    doubao = data["variants"]["doubao_office_task_mode"]
    assert "docs/OFFICE_TASK_MODE_HANDOFF.md" in doubao["entrypoints"]
    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in doubao["entrypoints"]
    assert any("Chinese operator handoff" in item for item in doubao["next_gate"])


def test_current_release_contract_is_agent_first_not_polished_html():
    data = _load_variants()
    universal = data["variants"]["universal"]

    assert "index.html" not in universal["entrypoints"]
    assert not any("static web workbench" in item for item in universal["packaging"])
    assert any("CLI, REST API, and MCP" in item for item in universal["next_gate"])
    assert any("portable HTML, and DOCX renderer metadata" in item for item in universal["next_gate"])
    assert not any(item.startswith("Add host-neutral agent packet acceptance") for item in universal["next_gate"])
    assert any("Desktop-agent first" in item for item in data["product"]["signature_features"])
    assert any("polished HTML" in item for item in data["product"]["signature_features"])
    assert any("Desktop-agent entrypoints" in item for item in data["release_gates"]["quality"])
    assert any("agent_tool_adapters" in item for item in data["release_gates"]["quality"])


def test_package_scripts_and_mcp_manifest_stay_aligned():
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MCP_MANIFEST_PATH.read_text(encoding="utf-8"))

    scripts = package["scripts"]
    assert scripts["mcp"] == "node lib/mcp-server.js"
    assert scripts["api"] == "powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 api/server.py"
    assert scripts["api:smoke"] == "powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 tools/api-smoke.py"
    assert scripts["codex:mcp-smoke"] == "node tools/codex-mcp-smoke.js"
    assert scripts["agent:host-smoke"] == "node tools/agent-host-smoke.js"
    assert scripts["release:preflight"] == "node bin/cli.js --release-preflight"
    assert scripts["delivery:audit"] == "node bin/cli.js --delivery-audit"
    assert scripts["objective:audit"] == "node bin/cli.js --objective-audit"
    assert scripts["release:privacy-scan"] == "powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 tools/package-privacy-scan.py --json"
    assert scripts["acceptance"] == "powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-acceptance.ps1"
    acceptance_text = (PROJECT_ROOT / "tools" / "run-acceptance.ps1").read_text(encoding="utf-8")
    assert "qyyjt_public_origin_handoff" in acceptance_text
    assert "source_resilience_recommended_step" in acceptance_text
    assert "acceptance_closure_summary" in acceptance_text
    assert "capital_verification_queue_count" in acceptance_text
    assert "relationship_graph_audit_queue_count" in acceptance_text
    assert "relationship graph audit summary" in acceptance_text
    assert "chart_manifest_data_rows" in acceptance_text
    assert "operational_handoff_tables" in acceptance_text
    assert "agent_handoff.bundle_ready_to_verify" in acceptance_text
    assert "verification_recipe" in acceptance_text
    assert "bundle_verification" in acceptance_text
    assert "tools\\api-smoke.py" in acceptance_text
    focused_text = (PROJECT_ROOT / "tools" / "run-focused-tests.ps1").read_text(encoding="utf-8")
    assert '$env:WST_PYTHON = $python' in focused_text
    cli_text = (PROJECT_ROOT / "bin" / "cli.js").read_text(encoding="utf-8")
    assert "writeOfflineFixtureFallback" in cli_text
    assert "python_child_process_unavailable_fallback_active" in cli_text
    assert "delivery_decision.remaining_variant_blocker_count" in cli_text
    assert "delivery_decision.variant_next_gate_count" in cli_text
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in cli_text
    assert "tools/codex-mcp-smoke.js" in package["files"]
    assert "tools/agent-host-smoke.js" in package["files"]
    assert "tools/run-python.js" in package["files"]
    assert "tools/run-python.ps1" in package["files"]
    assert "tools/api-smoke.py" in package["files"]
    assert "tools/package-privacy-scan.py" in package["files"]
    assert "tools/run-acceptance.ps1" in package["files"]
    assert "tools/run-focused-tests.ps1" in package["files"]
    assert "tools/run-terminology-check.ps1" in package["files"]
    assert "CLAUDE.md" in package["files"]
    assert "docs/API_CONTRACTS.md" in package["files"]
    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in package["files"]
    assert "docs/CLAUDE_CODE_ADAPTER.md" in package["files"]
    assert "docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md" in package["files"]
    assert "docs/CODEX_MARKETPLACE_SUBMISSION_NOTES.md" in package["files"]
    assert "docs/DESKTOP_AGENT_HOSTS.md" in package["files"]
    assert "docs/HERMES_AGENT_SETUP.md" in package["files"]
    assert "docs/OFFICE_TASK_MODE_HANDOFF.md" in package["files"]
    assert "docs/OPEN_AGENT_COMPATIBILITY.md" in package["files"]
    assert "docs/PLUGIN_MARKET_READINESS.md" in package["files"]
    assert "docs/RELEASE_PORTAL.md" in package["files"]

    server = manifest["mcpServers"]["wallstreet-tieling"]
    assert server["command"] == "npx"
    assert server["args"] == ["-y", package["name"], "--mcp"]
    assert package["bin"]["wallstreet-tieling"] == "./bin/cli.js"

    referenced_tools = {
        match.group(1).replace("\\", "/")
        for command in scripts.values()
        for match in re.finditer(r"(tools[/\\][^\s|&;]+)", str(command))
    }
    for tool in referenced_tools:
        assert (PROJECT_ROOT / tool).is_file(), tool
        assert tool in package["files"], tool

    manifest_tools = {tool["name"] for tool in manifest["tools"]}
    assert {
        "investigate_company",
        "connector_catalog",
        "release_readiness",
        "delivery_closure",
        "release_preflight",
        "delivery_audit",
        "objective_audit",
        "development_requirements",
        "agent_tool_adapters",
        "aggregate_subject",
    } <= manifest_tools
    investigate_tool = next(tool for tool in manifest["tools"] if tool["name"] == "investigate_company")
    aggregate_tool = next(tool for tool in manifest["tools"] if tool["name"] == "aggregate_subject")
    connector_tool = next(tool for tool in manifest["tools"] if tool["name"] == "connector_catalog")
    release_tool = next(tool for tool in manifest["tools"] if tool["name"] == "release_readiness")
    delivery_closure_tool = next(tool for tool in manifest["tools"] if tool["name"] == "delivery_closure")
    release_preflight_tool = next(tool for tool in manifest["tools"] if tool["name"] == "release_preflight")
    delivery_audit_tool = next(tool for tool in manifest["tools"] if tool["name"] == "delivery_audit")
    objective_audit_tool = next(tool for tool in manifest["tools"] if tool["name"] == "objective_audit")
    agent_tools_tool = next(tool for tool in manifest["tools"] if tool["name"] == "agent_tool_adapters")
    assert "quality gate" in investigate_tool["description"]
    assert "one_click_readiness" in investigate_tool["description"]
    assert "report_exports" in investigate_tool["description"]
    assert "directory_bundle.agent_handoff" in investigate_tool["description"]
    assert "manifest_fields" in investigate_tool["description"]
    assert "file_manifest" in investigate_tool["description"]
    assert "agent_summary" in investigate_tool["description"]
    assert "delivery_files" in investigate_tool["description"]
    assert "bundle_integrity" in investigate_tool["description"]
    assert "verification_recipe" in investigate_tool["description"]
    assert "bundle_verification" in investigate_tool["description"]
    assert "delivery_checklist" in investigate_tool["description"]
    assert "trust_boundaries" in investigate_tool["description"]
    assert "next_actions" in investigate_tool["description"]
    assert "qyyjt_public_origin_handoff" in investigate_tool["description"]
    assert "report_section_batches" in investigate_tool["description"]
    assert "section_work_orders" in investigate_tool["description"]
    assert "capital verification queue" in investigate_tool["description"]
    assert "relationship graph audit queue" in investigate_tool["description"]
    assert "relationship graph audit summary" in investigate_tool["description"]
    assert aggregate_tool["inputSchema"]["required"] == ["subject_id"]
    assert "max_depth" in aggregate_tool["inputSchema"]["properties"]
    assert "admission" in connector_tool["description"]
    assert "runtime_delivery" in release_tool["description"]
    assert "latest_acceptance_evidence" in release_tool["description"]
    assert "acceptance_status_counts" in release_tool["description"]
    assert "delivery closure checklist" in delivery_closure_tool["description"]
    assert "required verification commands" in delivery_closure_tool["description"]
    assert "go/no-go preflight" in release_preflight_tool["description"]
    assert "package_candidate_ready" in release_preflight_tool["description"]
    assert "machine-readable desktop-agent alpha delivery audit" in delivery_audit_tool["description"]
    assert "safe claim" in delivery_audit_tool["description"]
    assert "active objective" in objective_audit_tool["description"]
    assert "requirement-by-requirement" in objective_audit_tool["description"]
    assert "baseline tool sequence" in agent_tools_tool["description"]
    assert "execution_matrix done conditions" in agent_tools_tool["description"]
    assert "first_run_recipe preservation guards" in agent_tools_tool["description"]
    assert "fallback order" in agent_tools_tool["description"]
    assert "smoke commands" in agent_tools_tool["description"]
    runtime_mcp = (PROJECT_ROOT / "lib" / "mcp-server.js").read_text(encoding="utf-8")
    assert "report_exports including packet-level agent_decision_digest" in runtime_mcp
    assert "directory_bundle verifier_output_fields and verification_recipe for bundle verifier booleans" in runtime_mcp
    assert "directory_bundle manifest_fields with file_manifest, delivery_checklist, and agent_summary" in runtime_mcp
    assert "directory_bundle.agent_handoff with delivery_files, bundle_integrity, bundle_verification, delivery_checklist, report_visibility, capital_risk_panel, source_strengthening, trust_boundaries, decision_digest, next_actions" in runtime_mcp
    assert "focused_test_command" in release_tool["description"]
    assert "query_timeout_seconds" in investigate_tool["inputSchema"]["properties"]
    assert investigate_tool["inputSchema"]["properties"]["retrieval_concurrency"]["maximum"] == 20
    assert investigate_tool["inputSchema"]["properties"]["fanout_rounds"]["maximum"] == 3
    assert investigate_tool["inputSchema"]["properties"]["max_fanout_tasks"]["maximum"] == 80
    assert investigate_tool["inputSchema"]["properties"]["query_timeout_seconds"]["maximum"] == 120

    server_text = (PROJECT_ROOT / "lib" / "mcp-server.js").read_text(encoding="utf-8")
    server_tool_names = set(re.findall(r"name: '([^']+)'", server_text))
    assert manifest_tools <= server_tool_names


def test_agent_tool_adapter_manifest_covers_all_current_hosts():
    from core.agent_tool_adapters import build_agent_tool_adapter_manifest

    manifest = build_agent_tool_adapter_manifest()
    data = _load_variants()

    assert manifest["type"] == "agent_tool_adapter_manifest"
    assert manifest["release_target"] == "desktop_agent_alpha"
    assert manifest["adapter_count"] == len(data["variants"])
    assert set(manifest["host_ids"]) == set(data["variants"])
    assert manifest["all_current_release_ready"] is True
    assert {"npm run agent:host-smoke", "npm run codex:mcp-smoke", "npm run api:smoke"} <= set(manifest["required_smoke_commands"])
    install = manifest["installation_handoff"]
    assert install["type"] == "desktop_agent_installation_handoff"
    assert install["release_target"] == "desktop_agent_alpha"
    assert install["default_install_command"] == "npm install -g wallstreet-tieling"
    assert install["default_mcp_command"] == "npx -y wallstreet-tieling --mcp"
    assert "npm_config_cache" in " ".join(install["required_local_runtime_env"])
    assert "WST_PYTHON" in " ".join(install["required_local_runtime_env"])
    assert "npm run agent:host-smoke" in install["verification_commands"]
    assert "npm run release:privacy-scan" in install["verification_commands"]
    assert "npm run release:preflight" in install["verification_commands"]
    assert "npm run delivery:audit" in install["verification_commands"]
    assert "npm run objective:audit" in install["verification_commands"]
    assert "npm pack --dry-run --json" in install["verification_commands"]
    assert {row["host_id"] for row in install["host_matrix"]} == set(data["variants"])
    assert any(row["host_id"] == "codex" and "skills add" in row["install_command"] for row in install["host_matrix"])
    assert any("Python child process unavailable" in row["symptom"] for row in install["failure_routing"])
    assert "directory_bundle.agent_handoff" in install["done_condition"]

    shared_tools = {tool["name"]: tool for tool in manifest["shared_tools"]}
    for name in [
        "release_readiness",
        "delivery_closure",
        "release_preflight",
        "delivery_audit",
        "objective_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
        "aggregate_subject",
    ]:
        assert name in shared_tools
        assert shared_tools[name]["mcp_tool"]
        assert shared_tools[name]["cli"]
        assert shared_tools[name]["api"]
    assert shared_tools["aggregate_subject"]["cli"].startswith("npx wallstreet-tieling --aggregate-subject")
    assert shared_tools["aggregate_subject"]["api"] == "POST /api/aggregate"
    assert "delivery_decision.remaining_variant_blocker_count" in shared_tools["release_readiness"]["required_output_fields"]
    assert "delivery_decision.variant_next_gate_count" in shared_tools["release_readiness"]["required_output_fields"]
    assert "delivery_closure.status" in shared_tools["release_readiness"]["required_output_fields"]
    assert "delivery_closure.required_preserved_fields" in shared_tools["release_readiness"]["required_output_fields"]
    assert "delivery_closure.required_verification_commands" in shared_tools["release_readiness"]["required_output_fields"]
    assert "summary.data_effectiveness" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "groups.explicit_only" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "connectors[].data_effectiveness" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "source_strengthening_queue" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "source_strengthening_queue[].execution_plan" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "source_strengthening_queue[].runtime_companion" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "summary.source_strengthening" in shared_tools["connector_catalog"]["required_output_fields"]
    assert "delivery_decision.status" in shared_tools["development_requirements"]["required_output_fields"]
    assert shared_tools["agent_tool_adapters"]["cli"] == "npx wallstreet-tieling --agent-tools"
    assert shared_tools["agent_tool_adapters"]["api"] == "GET /api/agent-tools"
    assert "adapters[].tool_sequence" in shared_tools["agent_tool_adapters"]["required_output_fields"]
    assert "execution_matrix[].done_condition" in shared_tools["agent_tool_adapters"]["required_output_fields"]
    assert "one_input_autorun_contract.manual_intermediate_steps_required" in shared_tools["agent_tool_adapters"]["required_output_fields"]
    assert "one_input_autorun_contract.required_packet_fields" in shared_tools["agent_tool_adapters"]["required_output_fields"]
    assert shared_tools["delivery_closure"]["cli"] == "npx wallstreet-tieling --delivery-closure"
    assert shared_tools["delivery_closure"]["mcp_tool"] == "delivery_closure"
    assert "required_preserved_fields" in shared_tools["delivery_closure"]["required_output_fields"]
    assert shared_tools["release_preflight"]["cli"] == "npx wallstreet-tieling --release-preflight"
    assert shared_tools["release_preflight"]["api"] == "GET /api/release-preflight"
    assert "package_candidate_ready" in shared_tools["release_preflight"]["required_output_fields"]
    assert "final_submission_blockers" in shared_tools["release_preflight"]["required_output_fields"]
    assert "packaging_review.dry_run_command" in shared_tools["release_preflight"]["required_output_fields"]
    assert shared_tools["delivery_audit"]["cli"] == "npx wallstreet-tieling --delivery-audit"
    assert shared_tools["delivery_audit"]["api"] == "GET /api/delivery-audit"
    assert shared_tools["delivery_audit"]["mcp_tool"] == "delivery_audit"
    assert "coverage" in shared_tools["delivery_audit"]["required_output_fields"]
    assert "failed_checks" in shared_tools["delivery_audit"]["required_output_fields"]
    assert shared_tools["objective_audit"]["cli"] == "npx wallstreet-tieling --objective-audit"
    assert shared_tools["objective_audit"]["api"] == "GET /api/objective-audit"
    assert shared_tools["objective_audit"]["mcp_tool"] == "objective_audit"
    assert "failed_requirements" in shared_tools["objective_audit"]["required_output_fields"]
    assert manifest["completion_audit"]["tool"] == "objective_audit"
    assert "delivery_decision.full_product_status" in shared_tools["development_requirements"]["required_output_fields"]
    assert (
        "report_exports.directory_bundle.agent_handoff.delivery_decision"
        in shared_tools["investigate_company"]["required_output_fields"]
    )
    assert (
        "report_exports.directory_bundle.verifier_output_fields"
        in shared_tools["investigate_company"]["required_output_fields"]
    )
    assert (
        "report_exports.directory_bundle.verification_recipe"
        in shared_tools["investigate_company"]["required_output_fields"]
    )
    assert "one_click_readiness.capital_risk_panel" in shared_tools["investigate_company"]["required_output_fields"]
    assert (
        "one_click_readiness.capital_risk_panel.report_visibility"
        in shared_tools["investigate_company"]["required_output_fields"]
    )
    assert "report_exports.premium_html" in shared_tools["investigate_company"]["required_output_fields"]
    assert "report_exports.portable_html.premium_profile" in shared_tools["investigate_company"]["required_output_fields"]
    assert (
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html"
        in shared_tools["investigate_company"]["required_output_fields"]
    )

    matrix = {item["phase"]: item for item in manifest["execution_matrix"]}
    assert list(matrix) == [
        "release_gate",
        "delivery_audit",
        "source_catalog",
        "priority_board",
        "host_binding",
        "investigation_run",
        "followup_expansion",
    ]
    assert matrix["release_gate"]["tool"] == "release_readiness"
    assert "desktop_agent_alpha_release_candidate" in matrix["release_gate"]["done_condition"]
    assert matrix["delivery_audit"]["tool"] == "delivery_audit"
    assert "failed_checks" in matrix["delivery_audit"]["required_fields"]
    assert matrix["source_catalog"]["tool"] == "connector_catalog"
    assert "qyyjt_benchmark.summary.public_origin_execution_summary" in matrix["source_catalog"]["required_fields"]
    assert "summary.data_effectiveness" in matrix["source_catalog"]["required_fields"]
    assert "groups.explicit_only" in matrix["source_catalog"]["required_fields"]
    assert "connectors[].data_effectiveness" in matrix["source_catalog"]["required_fields"]
    assert "source_strengthening_queue" in matrix["source_catalog"]["required_fields"]
    assert "source_strengthening_queue[].execution_plan" in matrix["source_catalog"]["required_fields"]
    assert "source_strengthening_queue[].runtime_companion" in matrix["source_catalog"]["required_fields"]
    assert matrix["host_binding"]["tool"] == "agent_tool_adapters"
    assert any("required_packet_fields" in field for field in matrix["host_binding"]["required_fields"])
    assert matrix["investigation_run"]["tool"] == "investigate_company"
    assert "operator_work_queue" in matrix["investigation_run"]["failure_routing"]
    assert matrix["followup_expansion"]["tool"] == "aggregate_subject"
    assert matrix["followup_expansion"]["optional"] is True
    recipe = manifest["first_run_recipe"]
    assert recipe["sequence"] == [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
    ]
    assert "aggregate_subject" in recipe["optional_followup"]
    assert "report_exports.directory_bundle.agent_handoff" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.groups.explicit_only" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.connectors[].data_effectiveness" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.source_strengthening_queue" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.source_strengthening_queue[].implementation_pack" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.source_strengthening_queue[].execution_plan" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.source_strengthening_queue[].runtime_companion" in recipe["preserve_before_summarizing"]
    assert "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary" in recipe["preserve_before_summarizing"]
    assert "report_exports.premium_html" in recipe["preserve_before_summarizing"]
    assert "report_exports.portable_html.premium_profile" in recipe["preserve_before_summarizing"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility" in recipe["preserve_before_summarizing"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in recipe["preserve_before_summarizing"]
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in recipe["preserve_before_summarizing"]
    assert "report_exports.directory_bundle.agent_handoff.source_strengthening" in recipe["preserve_before_summarizing"]
    for field in [
        "qyyjt_public_origin_handoff.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
    ]:
        assert field in recipe["preserve_before_summarizing"]
    assert "npm run release:privacy-scan" in recipe["verification_commands"]
    assert "npm run release:preflight" in recipe["verification_commands"]
    assert "npm run delivery:audit" in recipe["verification_commands"]
    assert "npm run objective:audit" in recipe["verification_commands"]
    assert "npm pack --dry-run --json" in recipe["verification_commands"]
    assert any("prose-only" in item for item in recipe["do_not"])
    assert any("groups.explicit_only" in item for item in recipe["do_not"])
    assert any("source_strengthening_queue" in item for item in recipe["do_not"])
    autorun = manifest["one_input_autorun_contract"]
    assert autorun["type"] == "one_input_autorun_contract"
    assert autorun["subject_input"]["manual_intermediate_steps_required"] is False
    assert autorun["autorun_sequence"][-1]["step"] == "investigate_company"
    assert "company_name" in autorun["subject_input"]["accepted_fields"]
    assert "report_exports.directory_bundle.agent_handoff" in autorun["required_packet_fields"]
    assert "one_click_readiness.capital_risk_panel" in autorun["required_packet_fields"]
    assert any("extra clicks" in item for item in autorun["do_not"])
    assert manifest["default_host_id"] == "codex"
    assert manifest["primary_host_id"] == "codex"
    assert manifest["host_priority_order"][0] == "codex"
    assert "workbuddy_expert_team" in manifest["secondary_host_ids"]
    assert set(manifest["adapter_lookup"]) == set(data["variants"])
    codex_lookup = manifest["adapter_lookup"]["codex"]
    workbuddy_lookup = manifest["adapter_lookup"]["workbuddy_expert_team"]
    assert codex_lookup["delivery_priority"]["lane"] == "primary"
    assert workbuddy_lookup["delivery_priority"]["lane"] == "secondary"
    assert "codex" in workbuddy_lookup["delivery_priority"]["depends_on"]
    assert codex_lookup["primary_mode"] == "codex_plugin_mcp"
    assert "skills add" in codex_lookup["install_command"]
    assert ".codex-plugin/plugin.json" in codex_lookup["config_files"]
    assert codex_lookup["start_command"] == "npx -y wallstreet-tieling --mcp"
    assert "Codex plugin" in codex_lookup["fallback_order"]
    assert codex_lookup["smoke_command"] == "npm run codex:mcp-smoke"
    assert codex_lookup["tool_sequence"] == [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
    ]
    assert codex_lookup["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix"
    assert codex_lookup["required_packet_field_count"] >= 9
    assert "agent_handoff" in codex_lookup["report_outputs"]
    assert "premium_html" in codex_lookup["report_outputs"]

    for adapter in manifest["adapters"]:
        assert adapter["host_id"] in data["variants"]
        assert adapter["readiness"] == "alpha"
        assert adapter["current_release_supported"] is True
        assert adapter["project_branch_contract"]["type"] == "desktop_agent_project_branch"
        assert adapter["project_branch_contract"]["branch_id"] == adapter["host_id"]
        assert "investigate_company" in adapter["project_branch_contract"]["shared_runtime_contract"]
        assert adapter["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix"
        assert adapter["tool_sequence"] == [
            "release_readiness",
            "delivery_audit",
            "connector_catalog",
            "development_requirements",
            "agent_tool_adapters",
            "investigate_company",
        ]
        assert adapter["fallback_order"]
        assert adapter["operator_prompt"]
        assert adapter["install_handoff"]["type"] == "host_install_handoff"
        assert adapter["install_handoff"]["host_id"] == adapter["host_id"]
        assert adapter["install_handoff"]["config_files"]
        assert adapter["install_handoff"]["smoke_command"] == adapter["smoke_command"]
        assert "agent_handoff" in adapter["install_handoff"]["done_condition"]
        assert adapter["smoke_command"]
        assert "connector_catalog.groups.explicit_only" in adapter["required_packet_fields"]
        assert "connector_catalog.connectors[].data_effectiveness" in adapter["required_packet_fields"]
        assert "report_exports.agent_decision_digest" in adapter["required_packet_fields"]
        assert "report_exports.premium_html" in adapter["required_packet_fields"]
        assert "report_exports.portable_html.premium_profile" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.verification_recipe" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.verifier_output_fields" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.report_visibility" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.source_strengthening" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in adapter["required_packet_fields"]
        assert "agent_handoff" in adapter["report_outputs"]
        assert "premium_html" in adapter["report_outputs"]
        assert "polished immersive HTML is not required for desktop-agent alpha" in adapter["trust_boundaries"]


def test_agent_host_smoke_checklist_covers_release_variants_and_commands():
    data = _load_variants()
    text = AGENT_HOST_SMOKE_CHECKLIST_PATH.read_text(encoding="utf-8")

    for heading in [
        "Claude Code",
        "Hermes",
        "Doubao Office Task Mode",
        "OpenClaude And Open-Source Agents",
        "WorkBuddy Expert Team",
    ]:
        assert f"## {heading}" in text

    for command in [
        "npm run agent:host-smoke",
        "npm run api:smoke",
        "node tools/codex-mcp-smoke.js",
        "npx wallstreet-tieling --mcp",
        "python -m pytest tests/unit/test_workbuddy.py -q",
    ]:
        assert command in text
    for item in [
        "Call WorkBuddy tool routing for `investigate_company`",
        "offline_fixture=True",
        "source_strengthening_queue[].implementation_pack",
        "agent_tool_adapters.first_run_recipe.preserve_before_summarizing",
        "report_exports.premium_html",
        "report_exports.portable_html.premium_profile",
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
        "report_exports.agent_decision_digest",
        "report_exports.directory_bundle.agent_handoff.delivery_decision",
        "`delivery_decision`, `agent_handoff`, `report_visibility`, and",
    ]:
        assert item in text

    workbuddy = data["variants"]["workbuddy_expert_team"]
    assert workbuddy["project_branch"]["branch_id"] == "workbuddy_expert_team"
    assert "core runtime architecture" in workbuddy["project_branch"]["must_not_touch"]
    assert "WorkBuddy persona/tool routing" in workbuddy["project_branch"]["owns"]
    assert any("investigate_company" in item for item in workbuddy["next_gate"])
    assert any("investigation packet routing" in item for item in workbuddy["next_gate"])

    for variant in data["variants"].values():
        if variant["display_name"] == "Codex":
            continue
        assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in variant["entrypoints"]


def test_multi_platform_guide_is_agent_first_and_executable():
    data = _load_variants()
    text = MULTI_PLATFORM_GUIDE_PATH.read_text(encoding="utf-8")

    for variant in data["variants"].values():
        assert variant["display_name"] in text

    for item in [
        "npx wallstreet-tieling --release",
        "npx wallstreet-tieling --connectors",
        "npx wallstreet-tieling --requirements",
        "npx wallstreet-tieling --agent-tools",
        "GET /api/agent-tools",
        "agent_tool_adapters",
        "investigate_company",
        "aggregate_subject",
        "npm run agent:host-smoke",
        "npm run codex:mcp-smoke",
        "npm run api:smoke",
        "Polished immersive HTML, mini-program, mobile app, and standalone desktop app",
    ]:
        assert item in text

    assert "\u7d2b" not in text
    assert "\u6e10" not in text


def test_agent_release_ci_runs_packaged_and_host_smokes():
    workflow = yaml.safe_load(AGENT_RELEASE_CI_PATH.read_text(encoding="utf-8"))
    text = AGENT_RELEASE_CI_PATH.read_text(encoding="utf-8")
    host_smoke = (PROJECT_ROOT / "tools" / "agent-host-smoke.js").read_text(encoding="utf-8")

    assert workflow["name"] == "Agent Release CI"
    assert "codex/**" in workflow[True]["push"]["branches"]
    assert "npm run codex:mcp-smoke" in text
    assert "npm run api:smoke" in text
    assert "npm run agent:host-smoke" in text
    assert "node --check tools/codex-mcp-smoke.js" in text
    assert "node --check tools/agent-host-smoke.js" in text
    assert "tests/unit/test_release_variants.py" in text
    assert "tests/unit/test_release_hygiene.py" in text
    assert "workbuddy_investigate_company" in host_smoke
    assert "WorkBuddyTools().search" in host_smoke
    assert "workbuddy:investigate_company" in host_smoke


def test_codex_mcp_smoke_covers_retrieval_plan_and_cognition_profile():
    text = (PROJECT_ROOT / "tools" / "codex-mcp-smoke.js").read_text(encoding="utf-8")

    assert "bin', 'retrieval_plan.py'" in text
    assert "'retrieval_plan'" in text
    assert "retrievalPlan.tasks.length === 5" in text
    assert "investigation.enterprise_cognition.investigation_report_card" in text
    assert "investigation.enterprise_cognition.subject_due_diligence_profile" in text
    assert "hasOwnProperty.call(investigation.enterprise_cognition, 'control_ownership')" in text
    assert "investigation.enterprise_cognition.evidence_gaps" in text


def test_claude_adapter_points_to_shared_host_smoke_checklist():
    text = (PROJECT_ROOT / "docs" / "CLAUDE_CODE_ADAPTER.md").read_text(encoding="utf-8")

    assert "docs/AGENT_HOST_SMOKE_CHECKLIST.md" in text
    assert "covered by the shared desktop-agent host smoke" in text
    assert "still needs broader host-level smoke coverage" not in text


def test_codex_marketplace_notes_are_clean_and_bound_to_alpha_claims():
    readiness = (PROJECT_ROOT / "docs" / "PLUGIN_MARKET_READINESS.md").read_text(encoding="utf-8")
    notes = (PROJECT_ROOT / "docs" / "CODEX_MARKETPLACE_SUBMISSION_NOTES.md").read_text(encoding="utf-8")
    desktop_hosts = (PROJECT_ROOT / "docs" / "DESKTOP_AGENT_HOSTS.md").read_text(encoding="utf-8")

    for text in [readiness, notes]:
        assert "0.5.0 Alpha" in text
        assert "npm run acceptance" in text
        assert "npm pack --dry-run --json" in text
        assert "Fully automated live investigation" in text
        assert "marketplace approval" in text or "Approved by the marketplace" in text
        assert "\u937e" not in text
        assert "\u4e71\u7801" not in text

    assert "retrieval_plan" in readiness
    assert "Screenshot Capture List" in notes
    assert "npm run codex:mcp-smoke" in notes
    assert "0.5.0 Alpha" in desktop_hosts
    assert "npm run acceptance" in desktop_hosts
    assert "npm pack --dry-run --json" in desktop_hosts
    assert "development_requirements.delivery_decision" in desktop_hosts
    assert "continuous monitoring" in desktop_hosts


def test_office_task_mode_handoff_is_readable_and_release_bound():
    text = (PROJECT_ROOT / "docs" / "OFFICE_TASK_MODE_HANDOFF.md").read_text(encoding="utf-8")

    assert "Wallstreet Tieling 0.5.0 Alpha" in text
    assert "npx wallstreet-tieling --release" in text
    assert "POST /api/investigate" in text
    assert "npm pack --dry-run --json" in text
    assert "\u9886\u5bfc\u6458\u8981" in text
    assert "\u8bc1\u636e\u4e0e\u7f3a\u53e3" in text
    assert "\u4ea4\u4ed8\u6587\u4ef6" in text
    assert "\u4e0d\u5f97\u58f0\u79f0\u5df2\u7ecf\u5b8c\u6210\u751f\u4ea7\u7ea7\u5168\u81ea\u52a8\u5b9e\u65f6\u5c3d\u8c03" in text
    assert "\u6d63\u72b3" not in text
    assert "\u93b5\u0446" not in text
    assert "\u68f0" not in text


def test_npm_pack_dry_run_contains_agent_delivery_files_and_excludes_runtime_artifacts():
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    assert npm, "npm executable is required for package dry-run verification"
    result = subprocess.run(
        [npm, "pack", "--dry-run", "--json"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "npm_config_cache": str(Path(tempfile.gettempdir()) / "wallstreet-tieling-npm-cache")},
    )
    payload = json.loads(result.stdout)[0]
    packed_paths = {item["path"] for item in payload["files"]}

    required_paths = {
        "bin/cli.js",
        "bin/investigate.py",
        "bin/verify_report_bundle.py",
        "lib/mcp-server.js",
        "api/server.py",
        "core/agent_tool_adapters.py",
        "core/release_contract.py",
        "core/investigation.py",
        "core/report_docx.py",
        "tools/agent-host-smoke.js",
        "tools/codex-mcp-smoke.js",
        "tools/api-smoke.py",
        "tools/package-privacy-scan.py",
        "docs/API_CONTRACTS.md",
        "docs/AGENT_HOST_SMOKE_CHECKLIST.md",
        "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
        "docs/DESKTOP_AGENT_HOSTS.md",
        "docs/OFFICE_TASK_MODE_HANDOFF.md",
        "docs/OPEN_AGENT_COMPATIBILITY.md",
        "docs/RELEASE_PORTAL.md",
        "deploy/mcp-server.json",
        "release/variants.yaml",
        "skills/wallstreet-tieling/SKILL.md",
    }
    forbidden_paths = {
        "AGENT_COORDINATION_BOARD.md",
        "docs/COMPREHENSIVE_AUDIT_REPORT_2026-06-16.md",
        "docs/FINAL_DELIVERY_REPORT_2026-06-16.md",
        "gen_ci.py",
        "overview.md",
        "send_message_to_product_ai.py",
        "tmp-events.jsonl",
    }
    forbidden_prefixes = (
        ".tmp/",
        ".workbuddy/",
        "audit_reports/",
        "deliverables/",
        "output/",
        "outputs/",
        "docs/workbuddy/",
    )

    assert required_paths <= packed_paths
    assert not (packed_paths & forbidden_paths)
    assert all(not path.startswith(forbidden_prefixes) for path in packed_paths)


def test_desktop_agent_alpha_delivery_closure_is_actionable():
    text = (PROJECT_ROOT / "docs" / "DESKTOP_AGENT_ALPHA_DELIVERY.md").read_text(encoding="utf-8")
    portal = (PROJECT_ROOT / "docs" / "RELEASE_PORTAL.md").read_text(encoding="utf-8")

    for item in [
        "desktop_agent_alpha_release_candidate",
        "not_final_release_ready",
        "remaining_variant_blocker_count == 0",
        "execution_mode == node_metadata_fallback",
        "report_exports.premium_html",
        "report_exports.portable_html.premium_profile",
        "report_exports.directory_bundle.agent_handoff.delivery_decision",
        "report_exports.directory_bundle.agent_handoff.report_visibility",
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
        "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
        "Delivery Readiness Matrix",
        "source_resilience agent_autorun",
        "qyyjt_public_origin_handoff.agent_autorun",
        "capital_risk_agent_autorun",
        "relationship_graph_audit_agent_autorun",
        "relationship_resolution_agent_autorun",
        "report_artifact_agent_autorun",
        "npx wallstreet-tieling --delivery-closure",
        "release_readiness -> delivery_audit -> connector_catalog -> development_requirements -> agent_tool_adapters -> investigate_company",
        "799 passed, 9 skipped",
        "2026-07-06 08:24 Asia/Shanghai",
        "Final polished product launch readiness",
        "Marketplace approval",
    ]:
        assert item in text
    assert "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md" in portal


def test_node_cli_delivery_closure_entrypoint_returns_machine_readable_contract():
    result = subprocess.run(
        ["node", "bin/cli.js", "--delivery-closure"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "desktop_agent_alpha_delivery_closure"
    assert payload["target"] == "desktop_agent_alpha"
    assert payload["document"] == "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md"
    assert payload["status"] == "release_candidate"
    if payload.get("execution_mode") == "node_metadata_fallback":
        assert "full investigation packets" in payload["policy"]
        assert "DOCX export" in payload["policy"]
    assert payload["baseline_sequence"][-1] == "investigate_company"
    assert payload["baseline_sequence"][-2] == "agent_tool_adapters"
    assert "aggregate_subject" in payload["followup_tools"]
    assert "npm pack --dry-run --json" in payload["required_verification_commands"]
    assert "npm run release:privacy-scan" in payload["required_verification_commands"]
    assert "npm run delivery:audit" in payload["required_verification_commands"]
    assert "npm run objective:audit" in payload["required_verification_commands"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in payload["required_preserved_fields"]
    assert "report_exports.premium_html" in payload["required_preserved_fields"]
    assert "report_exports.portable_html.premium_profile" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.source_strengthening" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in payload["required_preserved_fields"]


def test_node_cli_release_preflight_entrypoint_returns_packaging_go_no_go():
    result = subprocess.run(
        ["node", "bin/cli.js", "--release-preflight"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "desktop_agent_alpha_release_preflight"
    assert payload["target"] == "desktop_agent_alpha"
    assert payload["status"] == "ready_for_local_packaging"
    assert payload["package_candidate_ready"] is True
    assert payload["final_submission_ready"] is False
    assert payload["blocking_items"] == []
    assert "npm pack --dry-run --json" in payload["required_verification_commands"]
    assert "npm run release:privacy-scan" in payload["required_verification_commands"]
    assert "npm run delivery:audit" in payload["required_verification_commands"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in payload["required_preserved_fields"]
    assert "report_exports.premium_html" in payload["required_preserved_fields"]
    assert "report_exports.portable_html.premium_profile" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in payload["required_preserved_fields"]
    assert "qyyjt_public_origin_handoff.agent_autorun" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in payload["required_preserved_fields"]
    assert payload["latest_acceptance"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai"
    assert payload["packaging_review"]["dry_run_command"] == "npm pack --dry-run --json"
    assert payload["packaging_review"]["privacy_command"] == "npm run release:privacy-scan"
    assert any("runtime state" in item for item in payload["packaging_review"]["do_not_package"])
    assert "desktop-agent alpha release candidate" in payload["agent_handoff"]["safe_claim"].lower()
    assert "marketplace/operator screenshots" in " ".join(payload["final_submission_blockers"])


def test_node_cli_delivery_audit_entrypoint_returns_single_go_no_go():
    result = subprocess.run(
        ["node", "bin/cli.js", "--delivery-audit"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "desktop_agent_alpha_delivery_audit"
    assert payload["target"] == "desktop_agent_alpha"
    assert payload["status"] == "pass"
    assert payload["ready_for_local_packaging"] is True
    assert payload["final_submission_ready"] is False
    assert payload["failed_checks"] == []
    assert payload["coverage"]["source_resilience"]["covered"] is True
    assert payload["coverage"]["qyyjt_public_origin"]["covered"] is True
    assert payload["coverage"]["relationship_graph"]["covered"] is True
    assert payload["coverage"]["capital_risk"]["covered"] is True
    assert payload["coverage"]["report_visibility"]["covered"] is True
    assert "npm run acceptance" in payload["verification_evidence"]["required_commands"]
    assert "not final polished product launch readiness" in payload["safe_claim"].lower()


def test_node_cli_objective_audit_entrypoint_maps_goal_to_evidence():
    result = subprocess.run(
        ["node", "bin/cli.js", "--objective-audit"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "objective_completion_audit"
    assert payload["target"] == "wallstreet_tieling_desktop_agent_delivery_objective"
    assert payload["status"] == "complete"
    assert payload["completion_percent"] == 100
    assert payload["release_gate"]["delivery_audit_status"] == "pass"
    assert payload["verification_evidence"]["superpowers_final_review"]["status"] == "pass"
    requirement_ids = {item["id"] for item in payload["requirements"]}
    assert {
        "source_resilience",
        "qyyjt_public_origin_mapping",
        "relationship_graph",
        "capital_risk",
        "report_visibility",
        "acceptance_closure",
        "desktop_agent_delivery",
        "workbuddy_expert_team_compatibility",
        "superpowers_final_review",
    } <= requirement_ids
    requirement_status = {item["id"]: item["status"] for item in payload["requirements"]}
    assert requirement_status["superpowers_final_review"] == "complete"
    assert payload["failed_requirements"] == []
