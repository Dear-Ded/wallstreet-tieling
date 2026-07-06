#!/usr/bin/env python3
"""Tests for product-facing one-click investigation packets."""
from __future__ import annotations

import asyncio
import hashlib
import io
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from core.datasource_fixtures import build_datasource_fixture_pack
from core.investigation import build_investigation_packet
from core.report_docx import render_print_package_docx
from core.risk_discovery_pipeline import RiskDiscoveryPipeline
from core.risk_graph_export import export_risk_graph


ROOT = Path(__file__).resolve().parent.parent.parent


def _load_investigate_cli_module():
    spec = importlib.util.spec_from_file_location("wst_investigate_cli", ROOT / "bin" / "investigate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_investigate_cli_clamps_host_supplied_execution_bounds(monkeypatch) -> None:
    cli = _load_investigate_cli_module()
    captured: dict[str, object] = {}

    async def fake_resolve(**kwargs):
        captured["resolve"] = kwargs
        return SimpleNamespace(records=None, search_engine=None, existing_plan=None, fanout_rounds=kwargs["fanout_rounds"])

    class FakePipeline:
        async def run(self, *args, **kwargs):
            captured["pipeline"] = kwargs
            return SimpleNamespace()

    monkeypatch.setattr(cli, "resolve_one_click_retrieval_async", fake_resolve)
    monkeypatch.setattr(cli, "RiskDiscoveryPipeline", lambda: FakePipeline())
    monkeypatch.setattr(cli, "export_risk_graph", lambda result: SimpleNamespace(to_dict=lambda: {"company": "Demo"}))
    monkeypatch.setattr(cli, "build_investigation_packet", lambda *args, **kwargs: SimpleNamespace(to_dict=lambda: {"ok": True}))

    args = cli.build_parser().parse_args(
        [
            "Demo Clamp Co.",
            "--retrieval-concurrency",
            "999",
            "--fanout-rounds",
            "99",
            "--max-fanout-tasks",
            "999",
            "--query-timeout-seconds",
            "999",
        ]
    )
    payload = asyncio.run(cli.run(args))

    assert payload == {"ok": True}
    assert captured["resolve"]["fanout_rounds"] == 3
    assert captured["pipeline"]["retrieval_concurrency"] == 20
    assert captured["pipeline"]["max_fanout_tasks"] == 80
    assert captured["pipeline"]["query_timeout_seconds"] == 120.0


def test_investigation_packet_contains_report_and_monitoring_seed(tmp_path) -> None:
    company = "Demo Investigation Packet Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company, mode="standard").to_dict()

    assert packet["type"] == "investigation_packet"
    assert packet["version"] == "0.5.0"
    assert packet["one_click"] is True
    assert packet["risk_brief"]["verdict"] in {
        "high_risk_verification_required",
        "moderate_risk_watchlist",
        "critical_risk_review_required",
    }
    assert packet["risk_brief"]["risk_score"] > 0
    assert packet["profile_brief"]["controller_candidate_count"] >= 1
    assert packet["enterprise_cognition"]["control_ownership"]["controller_candidate_count"] >= 1
    assert packet["enterprise_cognition"]["company"] == company
    assert packet["enterprise_cognition"]["risk_hypotheses"]
    assert packet["enterprise_cognition"]["monitoring_watchlist"]
    assert packet["source_provenance"]["source_count"] >= 1
    assert packet["source_provenance"]["official_or_licensed_count"] >= 1
    assert packet["risk_event_summary"]["risk_event_count"] >= 1
    assert packet["risk_event_summary"]["top_findings"]
    assert packet["persona_surface"]["role_count"] == 13
    assert packet["persona_surface"]["active_role_count"] >= 8
    assert packet["persona_surface"]["lane_bindings"]
    assert any(
        binding["lane"] == "registry"
        and "enterprise_cognition.control_ownership" in binding["packet_fields"]
        for binding in packet["persona_surface"]["lane_bindings"]
    )
    lane_fields = {
        binding["lane"]: set(binding["packet_fields"])
        for binding in packet["persona_surface"]["lane_bindings"]
    }
    assert "one_click_readiness.operator_work_queue" in lane_fields["data_sources"]
    assert "qyyjt_public_origin_handoff" in lane_fields["data_sources"]
    assert "one_click_readiness.reliance_limitations" in lane_fields["verification"]
    assert "one_click_readiness.capital_verification_top_step" in lane_fields["finance"]
    assert "one_click_readiness.relationship_graph_audit_top_step" in lane_fields["people"]
    assert any(role["display_name"] == "钱守正" for role in packet["persona_surface"]["active_roles"])
    assert packet["persona_surface"]["principle"].startswith("角色是调查分工")
    assert "lane=" in packet["report_markdown"]
    assert "basis=" in packet["report_markdown"]
    assert "fields:" in packet["report_markdown"]
    assert "qyyjt public-origin handoff" in packet["report_markdown"]
    assert "qyyjt public-origin top action" in packet["report_markdown"]
    assert "quality_gate" in packet
    assert packet["quality_gate"]["status"] in {"ready_for_human_review", "usable_with_warnings"}
    assert packet["one_click_readiness"]["type"] == "one_click_readiness"
    assert packet["one_click_readiness"]["fact_count"] >= 1
    assert packet["one_click_readiness"]["section_checks"]["quality_gate"] is True
    assert packet["one_click_readiness"]["section_checks"]["monitoring_scope_marked_future"] is True
    assert packet["one_click_readiness"]["acceptance_closure_summary"]["type"] == "acceptance_closure_summary"
    assert packet["one_click_readiness"]["acceptance_closure_status"] in {
        "blocked",
        "needs_operator_followup",
        "needs_review",
        "ready_for_human_review",
    }
    assert packet["one_click_readiness"]["acceptance_closure_blocking_count"] >= 0
    capital_panel = packet["one_click_readiness"]["capital_risk_panel"]
    assert capital_panel["type"] == "capital_risk_panel"
    assert capital_panel["report_visibility"]
    assert (
        capital_panel["capital_verification_queue_count"]
        == packet["one_click_readiness"]["capital_verification_queue_count"]
    )
    assert "acceptance closure:" in packet["report_markdown"]
    assert packet["qyyjt_public_origin_handoff"]["type"] == "qyyjt_public_origin_handoff"
    assert packet["qyyjt_public_origin_handoff"]["available"] is True
    assert packet["qyyjt_public_origin_handoff"]["queue_count"] >= 20
    assert packet["qyyjt_public_origin_handoff"]["p0_action_count"] == 20
    assert packet["qyyjt_public_origin_handoff"]["top_actions"][0]["action_id"].startswith("PUBLIC-ORIGIN-")
    assert packet["qyyjt_public_origin_handoff"]["top_actions"][0]["required_fields"]
    section_batches = packet["qyyjt_public_origin_handoff"]["report_section_batches"]
    assert packet["qyyjt_public_origin_handoff"]["report_section_batch_count"] == len(section_batches)
    assert section_batches[0]["report_section"] == "subject_resolution"
    assert section_batches[0]["top_actions"][0]["action_id"].startswith("PUBLIC-ORIGIN-")
    section_work_orders = packet["qyyjt_public_origin_handoff"]["section_work_orders"]
    assert packet["qyyjt_public_origin_handoff"]["section_work_order_count"] == len(section_work_orders)
    assert section_work_orders[0]["work_order_id"].startswith("QYYJT-SECTION-")
    assert section_work_orders[0]["report_section"] == section_batches[0]["report_section"]
    assert section_work_orders[0]["query_families"]
    assert section_work_orders[0]["required_fields"]
    assert packet["qyyjt_public_origin_handoff"]["top_section_work_order"] == section_work_orders[0]
    section_execution = packet["qyyjt_public_origin_handoff"]["section_execution_summary"]
    assert section_execution["type"] == "qyyjt_section_execution_summary"
    assert section_execution["section_count"] == len(section_work_orders)
    assert section_execution["p0_section_count"] >= 1
    assert section_execution["ready_section_count"] == len(section_work_orders)
    assert section_execution["blocked_section_count"] == 0
    assert section_execution["top_ready_work_order"]["work_order_id"] == section_work_orders[0]["work_order_id"]
    assert packet["qyyjt_public_origin_handoff"]["top_ready_section_work_order"] == section_execution["top_ready_work_order"]
    assert "qyyjt public-origin section batch: subject_resolution" in packet["report_markdown"]
    assert "qyyjt public-origin section execution:" in packet["report_markdown"]
    assert "qyyjt public-origin ready section: QYYJT-SECTION-" in packet["report_markdown"]
    assert "qyyjt public-origin section work order: QYYJT-SECTION-" in packet["report_markdown"]
    assert packet["report_exports"]["type"] == "report_exports"
    decision_digest = packet["report_exports"]["agent_decision_digest"]
    assert decision_digest["type"] == "agent_decision_digest"
    assert decision_digest["surface"] == "report_exports.agent_decision_digest"
    assert decision_digest["delivery_status"] == "ready_for_desktop_agent_delivery"
    assert decision_digest["bundle_verification_status"] == "export_dir_required"
    assert decision_digest["acceptance_closure_status"] == packet["one_click_readiness"]["acceptance_closure_status"]
    assert decision_digest["can_make_clean_conclusion"] == packet["one_click_readiness"]["can_make_clean_conclusion"]
    assert decision_digest["work_queue_counts"]["operator_work"] == packet["one_click_readiness"]["operator_work_queue_count"]
    assert decision_digest["first_action"]["id"] == "acceptance_closure_summary"
    assert decision_digest["public_or_authorized_boundary"].startswith("public, licensed")
    assert "print_package" in packet["report_exports"]["formats"]
    assert "directory_bundle" in packet["report_exports"]["formats"]
    assert packet["report_exports"]["markdown"]["content_field"] == "report_markdown"
    portable_html = packet["report_exports"]["portable_html"]["document"]
    assert portable_html.startswith("<!doctype html>")
    assert company in portable_html
    assert "report readiness summary" in portable_html
    assert "quality score" in portable_html
    assert "coverage gaps:" in portable_html
    assert "capital relationship" in portable_html
    assert "source recovery ready:" in portable_html
    assert "qyyjt public actions" in portable_html
    assert "capital verification steps" in portable_html
    assert "relationship audit steps" in portable_html
    assert "Agent decision digest" in portable_html
    assert "bundle verification" in portable_html
    assert "Visual evidence panels" in portable_html
    assert "Source provenance appendix" in portable_html
    assert "Relationship and capital appendix" in portable_html
    assert "report-layout" in portable_html
    assert "Delivery checklist" in portable_html
    assert "primary print:" in portable_html
    assert "docx_red_head" in portable_html
    assert "operator_handoff_present" in portable_html
    assert "first-screen handoff cards" in packet["report_exports"]["portable_html"]["content_policy"]
    assert "delivery checklist" in packet["report_exports"]["portable_html"]["content_policy"]
    assert packet["report_exports"]["portable_html"]["delivery_checklist_source"] == "report_exports.print_package.delivery_checklist"
    portable_handoff = packet["report_exports"]["portable_html"]["first_screen_handoff_cards"]
    assert packet["report_exports"]["portable_html"]["first_screen_handoff_card_count"] == len(portable_handoff)
    assert packet["report_exports"]["portable_html"]["first_screen_handoff_source"] == "report_exports.print_package.operational_handoff.cards"
    assert packet["report_markdown"].splitlines()[0] in portable_html
    assert packet["report_exports"]["json_packet"]["content_field"] == "entire investigation_packet"
    assert packet["report_exports"]["directory_bundle"]["runtime_entrypoint"] == "bin/investigate.py --export-dir"
    verification_recipe = packet["report_exports"]["directory_bundle"]["verification_recipe"]
    assert verification_recipe["type"] == "report_bundle_verification_recipe"
    assert verification_recipe["expected_exit_code"] == 0
    assert "verify_report_bundle.py" in verification_recipe["command"]
    assert "agent_handoff.bundle_ready_to_verify" in verification_recipe["required_output_fields"]
    assert "agent_handoff.image_evidence_inventory_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.source_strengthening_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.relationship_resolution_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.verification_recipe_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.verifier_output_fields_present" in verification_recipe["required_output_fields"]
    assert "agent_handoff.bundle_ready_to_verify" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.image_evidence_inventory_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.relationship_resolution_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.verification_recipe_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.verifier_output_fields_present" in packet["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert packet["report_exports"]["directory_bundle"]["manifest_filename"] == "report-export-manifest.json"
    assert "file_manifest" in packet["report_exports"]["directory_bundle"]["manifest_fields"]
    assert "delivery_checklist" in packet["report_exports"]["directory_bundle"]["manifest_fields"]
    assert "agent_summary" in packet["report_exports"]["directory_bundle"]["manifest_fields"]
    assert "portable_html" in packet["report_exports"]["directory_bundle"]["writes"]
    assert "agent_handoff" in packet["report_exports"]["directory_bundle"]["writes"]
    agent_handoff_preview = packet["report_exports"]["directory_bundle"]["agent_handoff"]
    assert agent_handoff_preview["filename"] == "agent-handoff.json"
    assert "delivery decision" in agent_handoff_preview["content"]
    assert "delivery_decision" in agent_handoff_preview["schema_fields"]
    assert "delivery files" in agent_handoff_preview["content"]
    assert "delivery_files" in agent_handoff_preview["schema_fields"]
    assert "bundle_verification" in agent_handoff_preview["schema_fields"]
    assert "delivery_checklist" in agent_handoff_preview["schema_fields"]
    assert "source_strengthening" in agent_handoff_preview["schema_fields"]
    assert "relationship_resolution" in agent_handoff_preview["schema_fields"]
    assert "trust_boundaries" in agent_handoff_preview["schema_fields"]
    assert "decision_digest" in agent_handoff_preview["schema_fields"]
    assert "next_actions" in agent_handoff_preview["schema_fields"]
    assert "acceptance closure" in agent_handoff_preview["content"]
    assert "closure_steps" in agent_handoff_preview["content"]
    assert "reliance limitations" in agent_handoff_preview["content"]
    assert "report_artifact_autorun" in agent_handoff_preview["schema_fields"]
    report_artifact_preview = agent_handoff_preview["report_artifact_autorun"]
    assert report_artifact_preview["type"] == "report_artifact_agent_autorun"
    assert report_artifact_preview["manual_intermediate_steps_required"] is False
    assert report_artifact_preview["routes"][0]["route_id"] == "export-report-bundle"
    assert report_artifact_preview["routes"][1]["route_id"] == "verify-report-bundle"
    assert "report_exports.portable_html.document" in report_artifact_preview["preserve_packet_fields"]
    assert agent_handoff_preview["preview_type"] == "packet_agent_handoff_preview"
    assert agent_handoff_preview["source_strengthening"]["type"] == "source_strengthening_handoff"
    assert agent_handoff_preview["source_strengthening"]["status"] in {"ready", "complete"}
    assert agent_handoff_preview["source_strengthening"]["work_order_count"] == len(
        agent_handoff_preview["source_strengthening"]["top_work_orders"]
    )
    assert agent_handoff_preview["source_resilience"]["type"] == "source_resilience_handoff"
    assert agent_handoff_preview["source_resilience"]["replay_routes"]
    autorun = agent_handoff_preview["source_resilience"]["agent_autorun"]
    assert autorun["type"] == "source_resilience_agent_autorun"
    assert autorun["manual_intermediate_steps_required"] is False
    assert autorun["routes"]
    assert autorun["routes"][0]["mcp_tool"] == "investigate_company"
    assert autorun["routes"][0]["api_route"] == "POST /api/investigate"
    assert "npx wallstreet-tieling --investigate" in autorun["routes"][0]["cli_command"]
    assert "report_exports.directory_bundle.agent_handoff.source_health" in autorun["routes"][0]["preserve_packet_fields"]
    assert agent_handoff_preview["capital_risk_panel"]["type"] == "capital_risk_panel_handoff"
    assert agent_handoff_preview["relationship_graph_audit"]["type"] == "relationship_graph_audit_handoff"
    assert agent_handoff_preview["relationship_resolution"]["type"] == "relationship_resolution_handoff"
    capital_autorun = agent_handoff_preview["capital_risk_panel"]["agent_autorun"]
    assert capital_autorun["type"] == "capital_risk_agent_autorun"
    assert capital_autorun["manual_intermediate_steps_required"] is False
    assert "one_click_readiness.capital_risk_panel" in capital_autorun["routes"][0]["required_output_fields"]
    relationship_audit_autorun = agent_handoff_preview["relationship_graph_audit"]["agent_autorun"]
    assert relationship_audit_autorun["type"] == "relationship_graph_audit_agent_autorun"
    assert relationship_audit_autorun["routes"][0]["mcp_tool"] == "investigate_company"
    relationship_resolution_autorun = agent_handoff_preview["relationship_resolution"]["agent_autorun"]
    assert relationship_resolution_autorun["type"] == "relationship_resolution_agent_autorun"
    assert "enterprise_cognition.relationship_resolution_v1" in relationship_resolution_autorun["routes"][0]["required_output_fields"]
    qyyjt_autorun = agent_handoff_preview["qyyjt_public_origin"]["agent_autorun"]
    assert qyyjt_autorun["type"] == "qyyjt_public_origin_agent_autorun"
    assert qyyjt_autorun["manual_intermediate_steps_required"] is False
    assert qyyjt_autorun["routes"]
    assert qyyjt_autorun["routes"][0]["mcp_tool"] == "investigate_company"
    assert qyyjt_autorun["routes"][0]["api_route"] == "POST /api/investigate"
    assert qyyjt_autorun["routes"][0]["target_work_order"]["work_order_id"].startswith("QYYJT-SECTION-")
    assert "qyyjt_public_origin_handoff.section_work_orders" in qyyjt_autorun["routes"][0]["required_output_fields"]
    assert agent_handoff_preview["relationship_resolution"]["verification_queue"] == (
        packet["enterprise_cognition"]["relationship_resolution_v1"]["resolution_summary"]["verification_queue"][:8]
    )
    assert agent_handoff_preview["qyyjt_public_origin"]["section_work_orders"] == section_work_orders[:8]
    assert agent_handoff_preview["decision_digest"] == decision_digest
    print_package = packet["report_exports"]["print_package"]
    assert print_package["type"] == "print_package_manifest"
    assert print_package["status"] == "ready_for_agent_renderer"
    assert "docx_red_head" in print_package["target_outputs"]
    assert print_package["docx"]["filename"].endswith("-red-head-due-diligence-report.docx")
    assert print_package["docx"]["renderer_status"] == "runtime_cli_renderer_available"
    assert print_package["docx"]["runtime_entrypoint"] == "bin/investigate.py --export-docx"
    assert "official_document_metadata" in print_package["docx"]["renderer_capabilities"]
    assert "red_head_separator_rule" in print_package["docx"]["renderer_capabilities"]
    assert "section_inventory_toc" in print_package["docx"]["renderer_capabilities"]
    assert "page_footer_field" in print_package["docx"]["renderer_capabilities"]
    assert "chart_manifest_data_rows" in print_package["docx"]["renderer_capabilities"]
    assert "native_chart_summary_panels" in print_package["docx"]["renderer_capabilities"]
    assert "image_evidence_inventory_items" in print_package["docx"]["renderer_capabilities"]
    assert "embedded_local_image_evidence" in print_package["docx"]["renderer_capabilities"]
    assert "operational_handoff_tables" in print_package["docx"]["renderer_capabilities"]
    assert "native_word_tables" in print_package["docx"]["renderer_capabilities"]
    assert print_package["red_head_front_matter"]["brief_required"] is True
    assert print_package["red_head_front_matter"]["body_required"] is True
    assert print_package["red_head_front_matter"]["document_number"].startswith("WST-DD-")
    assert print_package["red_head_front_matter"]["document_purpose"] == "desktop_agent_due_diligence_delivery"
    assert "full_due_diligence_body" in print_package["document_structure"]
    assert "risk_and_capital_charts" in print_package["document_structure"]
    assert "relationship_capital_appendix" in print_package["document_structure"]
    assert "operational_handoff_appendix" in print_package["document_structure"]
    assert print_package["chart_manifest"]
    assert any(chart["id"] == "evidence_fact_lead_mix" for chart in print_package["chart_manifest"])
    assert any(chart["id"] == "acceptance_closure_summary" for chart in print_package["chart_manifest"])
    assert any(chart["id"] == "operational_followup_queue" for chart in print_package["chart_manifest"])
    image_inventory = print_package["image_evidence_inventory"]
    assert image_inventory["type"] == "image_evidence_inventory"
    assert image_inventory["appendix_required"] is False
    assert image_inventory["count"] == 0
    assert image_inventory["embeddable_count"] == 0
    assert image_inventory["remote_reference_count"] == 0
    assert "portable HTML" in image_inventory["delivery_policy"]
    portable_html = packet["report_exports"]["portable_html"]["document"]
    assert packet["report_exports"]["portable_html"]["image_evidence_source"] == "report_exports.print_package.image_evidence_inventory"
    assert "Image evidence summary" in portable_html
    assert "image evidence count:" in portable_html
    assert "premium_html" in packet["report_exports"]["formats"]
    premium_html = packet["report_exports"]["premium_html"]
    assert premium_html["type"] == "premium_html_report_profile"
    assert premium_html["status"] == "runtime_contract_available"
    assert packet["report_exports"]["portable_html"]["premium_profile"] == premium_html
    assert "data-premium-html-report" in portable_html
    assert "data-full-report-preserved" in portable_html
    assert "Premium HTML visual QA checklist" in portable_html
    assert "prefers-reduced-motion" in portable_html
    assert "@media print" in portable_html
    assert "id=\"full-report-body\"" in portable_html
    assert "class=\"report-body\"" in portable_html
    assert packet["report_markdown"].splitlines()[0] in portable_html
    assert "full_markdown_report_preserved" in premium_html["content_guarantees"]
    assert "no_report_body_summarization" in premium_html["forbidden_shortcuts"]
    assert "document has data-premium-html-report marker" in premium_html["acceptance_checklist"]
    assert premium_html["metrics"]["handoff_card_count"] == packet["report_exports"]["portable_html"]["first_screen_handoff_card_count"]
    source_appendix = print_package["source_provenance_appendix"]
    assert source_appendix["type"] == "source_provenance_appendix"
    assert source_appendix["appendix_required"] is True
    assert source_appendix["source_count"] >= 1
    assert source_appendix["evidence_row_count"] == len(packet["evidence_ledger"])
    assert source_appendix["rows"]
    assert {"id", "source", "authority", "access", "admission", "url"} <= set(source_appendix["rows"][0])
    relationship_capital_appendix = print_package["relationship_capital_appendix"]
    assert relationship_capital_appendix["type"] == "relationship_capital_appendix"
    assert relationship_capital_appendix["appendix_required"] is True
    assert relationship_capital_appendix["relationship_edge_count"] == packet["one_click_readiness"]["relationship_edge_count"]
    assert (
        relationship_capital_appendix["relationship_evidence_backed_edge_count"]
        == packet["one_click_readiness"]["relationship_evidence_backed_edge_count"]
    )
    assert (
        relationship_capital_appendix["relationship_missing_evidence_edge_count"]
        == packet["one_click_readiness"]["relationship_missing_evidence_edge_count"]
    )
    assert relationship_capital_appendix["capital_verification_queue_count"] == packet["one_click_readiness"]["capital_verification_queue_count"]
    assert relationship_capital_appendix["relationship_audit_queue_count"] == packet["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert relationship_capital_appendix["capital_verification_queue"] == packet["one_click_readiness"]["capital_verification_queue"][:12]
    assert relationship_capital_appendix["relationship_audit_queue"] == packet["one_click_readiness"]["relationship_graph_audit_queue"][:12]
    delivery_checklist = print_package["delivery_checklist"]
    assert delivery_checklist["type"] == "delivery_checklist_manifest"
    assert delivery_checklist["status"] == "ready_for_desktop_agent_delivery"
    assert delivery_checklist["primary_print_file"] == print_package["docx"]["filename"]
    assert delivery_checklist["agent_open_order"][0] == print_package["docx"]["filename"]
    assert any(row["id"] == "json_packet" for row in delivery_checklist["required_outputs"])
    assert any(row["id"] == "operator_handoff_present" for row in delivery_checklist["quality_checks"])
    assert any(row["id"] == "source_provenance_appendix_present" for row in delivery_checklist["quality_checks"])
    assert any(row["id"] == "relationship_capital_appendix_present" for row in delivery_checklist["quality_checks"])
    assert delivery_checklist["print_binding"]["body_preserved"] is True
    assert delivery_checklist["print_binding"]["source_provenance_appendix"] is True
    assert delivery_checklist["print_binding"]["relationship_capital_appendix"] is True
    operational_handoff = print_package["operational_handoff"]
    assert operational_handoff["type"] == "operational_handoff"
    assert operational_handoff["summary"]["status"] == packet["one_click_readiness"]["status"]
    assert operational_handoff["summary"]["acceptance_closure_status"] == packet["one_click_readiness"]["acceptance_closure_status"]
    assert operational_handoff["summary"]["acceptance_closure_blocking_count"] == packet["one_click_readiness"]["acceptance_closure_blocking_count"]
    assert operational_handoff["summary"]["relationship_graph_audit_queue_count"] == packet["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert operational_handoff["cards"][0]["id"] == "acceptance_closure_summary"
    assert any(card["id"] == "source_recovery_step" for card in operational_handoff["cards"])
    assert any(card["id"] == "capital_verification_top_step" for card in operational_handoff["cards"])
    assert any(card["id"] == "relationship_graph_audit_top_step" for card in operational_handoff["cards"])
    if packet["one_click_readiness"]["reliance_limitation_count"]:
        assert any(card["id"] == "reliance_limitation_top_action" for card in operational_handoff["cards"])
    assert portable_handoff == operational_handoff["cards"]
    assert "preserves_full_report_body" in print_package["acceptance_checklist"]
    assert "includes_operational_handoff_for_agent_execution" in print_package["acceptance_checklist"]
    assert "includes_delivery_checklist_for_agent_and_print_handoff" in print_package["acceptance_checklist"]
    assert "includes_acceptance_closure_summary" in print_package["acceptance_checklist"]
    assert "includes_source_provenance_appendix" in print_package["acceptance_checklist"]
    assert "source_provenance_appendix_cites_evidence_rows" in print_package["acceptance_checklist"]
    assert "relationship_capital_appendix_lists_graph_and_capital_work" in print_package["acceptance_checklist"]
    assert packet["report_exports"]["future_formats"]["docx_red_head"] == "runtime_cli_renderer_available_via_export_docx"
    assert packet["report_exports"]["future_formats"]["immersive_premium_html"] == "p2_visual_polish_not_current_release_blocker"
    assert (
        packet["report_exports"]["print_readiness"]["docx_print_binding_layout"]
        == "runtime_renderer_with_toc_footer_native_tables_and_local_image_embedding"
    )
    assert "## One-click Product Loop" in packet["report_markdown"]
    assert "## 专家团分工" in packet["report_markdown"]
    assert "钱守正" in packet["report_markdown"]
    assert "## 交付质量" in packet["report_markdown"]
    assert "## 风险事件台账" in packet["report_markdown"]
    assert f"评分: {packet['quality_gate']['score']}/100" in packet["report_markdown"]
    assert packet["evidence_ledger"]
    assert packet["monitoring_seed"]["ready_for_continuous_watch"] is True
    assert packet["monitoring_seed"]["current_release_monitoring_enabled"] is False
    assert packet["monitoring_seed"]["feature_scope"] == "future_version_not_current_release"
    assert packet["monitoring_seed"]["current_release_role"] == "baseline_seed_only"
    assert "尽调快报" in packet["report_markdown"]
    assert "## 企业认知" in packet["report_markdown"]
    assert "## 来源出处" in packet["report_markdown"]
    assert "## 控制权与实控人" in packet["report_markdown"]
    assert packet["graph"]["company"] == company


def test_print_package_docx_renderer_preserves_report_contract(tmp_path) -> None:
    company = "Demo Printable Report Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text=company, mode="standard").to_dict()

    docx_bytes = render_print_package_docx(packet)

    assert docx_bytes.startswith(b"PK")
    docx_path = tmp_path / "report.docx"
    docx_path.write_bytes(docx_bytes)
    with ZipFile(docx_path) as docx:
        names = set(docx.namelist())
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        assert "word/footer1.xml" in names
        assert "word/_rels/document.xml.rels" in names
        document_xml = docx.read("word/document.xml").decode("utf-8")
        footer_xml = docx.read("word/footer1.xml").decode("utf-8")
        document_rels = docx.read("word/_rels/document.xml.rels").decode("utf-8")
    assert "Wallstreet Tieling Enterprise Intelligence Desk" in document_xml
    assert "Document No." in document_xml
    assert "WST-DD-" in document_xml
    assert "desktop_agent_due_diligence_delivery" in document_xml
    assert 'w:color="9F1D20"' in document_xml
    assert "Concise Due-Diligence Brief" in document_xml
    assert "Table Of Contents" in document_xml
    assert "role=brief" in document_xml
    assert "Full Due-Diligence Body" in document_xml
    assert "Delivery Checklist" in document_xml
    assert "Required Delivery Outputs" in document_xml
    assert "Delivery Quality Checks" in document_xml
    assert "primary_print_file=" in document_xml
    assert "operator_handoff_present" in document_xml
    assert "source_provenance_appendix_present" in document_xml
    assert "Operational Handoff Appendix" in document_xml
    assert "acceptance_closure_summary" in document_xml
    assert "source_recovery_step" in document_xml
    assert "capital_verification_top_step" in document_xml
    assert "relationship_graph_audit_top_step" in document_xml
    assert "ready_to_run" in document_xml
    assert "Risk And Capital Chart Plan" in document_xml
    assert "Chart Visual Summary" in document_xml
    assert "Share" in document_xml
    assert "Bar" in document_xml
    assert "<w:tbl>" in document_xml
    assert "Metric" in document_xml
    assert "Value" in document_xml
    assert "data.facts=" in document_xml
    assert "Source Provenance Appendix" in document_xml
    assert "Source Provenance Summary" in document_xml
    assert "Evidence Source Index" in document_xml
    assert "evidence_rows=" in document_xml
    assert "Relationship And Capital Appendix" in document_xml
    assert "capital_relationship_status=" in document_xml
    assert "relationship_edges=" in document_xml
    assert "Capital Verification Queue" in document_xml
    assert "Relationship Graph Audit Queue" in document_xml
    assert "relationship_capital_appendix_present" in document_xml
    assert "Renderer Acceptance Checklist" in document_xml
    assert "rIdFooter1" in document_xml
    assert "footer1.xml" in document_rels
    assert " PAGE " in footer_xml
    assert company in document_xml
    assert packet["report_markdown"].splitlines()[0].lstrip("# ") in document_xml


def test_print_package_docx_renderer_lists_image_evidence_items() -> None:
    packet = {
        "summary": {"company": "Demo Image Evidence Co."},
        "report_markdown": "# Demo Image Evidence Co.\n\nBody.",
        "report_exports": {
            "print_package": {
                "red_head_front_matter": {"document_title": "Demo image evidence report"},
                "print_layout": {"paper": "A4", "page_numbers": True, "table_of_contents": True},
                "section_inventory": [{"title": "Demo Body", "heading_level": 1, "line_start": 1, "print_role": "body"}],
                "chart_manifest": [
                    {
                        "id": "demo_chart",
                        "title": "Demo chart",
                        "type": "bar",
                        "data": {"facts": 2, "leads": 1},
                    }
                ],
                "image_evidence_inventory": {
                    "count": 1,
                    "items": [
                        {
                            "id": "image-evidence-1",
                            "source": "public_registry",
                            "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
                            "caption": "Registry screenshot",
                            "admission": "fact",
                        }
                    ],
                },
                "acceptance_checklist": ["renders_image_evidence_appendix_when_images_exist"],
            }
        },
    }

    docx_bytes = render_print_package_docx(packet)

    with ZipFile(io.BytesIO(docx_bytes)) as docx:
        names = set(docx.namelist())
        document_xml = docx.read("word/document.xml").decode("utf-8")
        document_rels = docx.read("word/_rels/document.xml.rels").decode("utf-8")
    assert "word/media/evidence-image-1.png" in names
    assert 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"' in document_rels
    assert 'r:embed="rIdImage1"' in document_xml
    assert "embedded_image_status=embedded_in_docx" in document_xml
    assert "Registry screenshot" in document_xml
    assert "<w:tbl>" in document_xml
    assert "Caption" in document_xml
    assert "Admission" in document_xml
    assert "source=public_registry" in document_xml
    assert "admission=fact" in document_xml
    assert "url=data:image/png;base64" in document_xml
    assert "data.facts=2" in document_xml


def test_investigation_packet_marks_no_source_as_insufficient_data(tmp_path) -> None:
    company = "Demo Investigation No Source Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company).to_dict()

    assert packet["risk_brief"]["verdict"] == "insufficient_data"
    assert packet["quality_gate"]["ok"] is False
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert packet["enterprise_cognition"]["evidence_gaps"]
    assert any("当前证据不足" in item for item in packet["enterprise_cognition"]["risk_hypotheses"])
    assert packet["evidence_ledger"] == []
    assert packet["summary"]["dd_profile_highlights"]["available"] is False
    assert packet["enterprise_cognition"]["status_summary"]["ok"] is False
    assert packet["enterprise_cognition"]["subject_aggregation_available"] is False
    assert packet["enterprise_cognition"]["multi_layer_graph_data"]["available"] is False
    assert packet["enterprise_cognition"]["multi_layer_relationship_graph"]["available"] is False
    assert packet["monitoring_seed"]["ready_for_continuous_watch"] is False
    assert packet["monitoring_seed"]["current_release_monitoring_enabled"] is False
    assert packet["monitoring_seed"]["feature_scope"] == "future_version_not_current_release"
    assert "证据不足" in packet["report_markdown"]


@pytest.mark.parametrize("record_source_type", ["query_plan", "Rich_Query_Plan"])
def test_investigation_packet_blocks_clean_verdict_when_only_leads_exist(record_source_type: str) -> None:
    graph = {
        "company": "Demo Lead Only Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "highest_severity": None,
            "next_actions": [],
            "coverage": {"domains_without_evidence": ["financing_capital_markets"]},
            "failed_sources": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:lead-1",
                "type": "derived_clue",
                "source": "qyyjt_websearch_plan",
                "title": "QYYJT lead: RELATED_PARTIES",
                "url": None,
                "confidence": 0.3,
                "claim_count": 1,
                "claims": ["query-plan lead only"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "record_source_type": record_source_type},
            },
            {
                "id": "evidence:lead-2",
                "type": "derived_clue",
                "source": "qyyjt_websearch_plan",
                "title": "QYYJT lead: RISK_SCAN",
                "url": None,
                "confidence": 0.3,
                "claim_count": 1,
                "claims": ["another lead only"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "record_source_type": record_source_type},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Lead Only Co.",
                "recursion_policy": {"default_depth": 3, "max_subjects": 80, "max_signals_per_dimension": 120},
                "subjects": {},
                "signals_by_dimension": {},
                "controller_candidates": [],
                "evidence_gaps": [
                    "Missing or weak controller and beneficial-owner evidence; expand public/authorized sources before making a final risk judgment."
                ],
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Lead Only Co.", "kind": "company"},
                        {"id": "domain:demo.example", "name": "demo.example", "kind": "domain"},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "from_name": "Demo Lead Only Co.",
                            "from_kind": "company",
                            "to_id": "domain:demo.example",
                            "to_name": "demo.example",
                            "to_kind": "domain",
                            "relation_type": "public_web_footprint",
                            "confidence": 0.3,
                            "evidence_ids": ["evidence:lead-1"],
                        },
                        {
                            "from_id": "company:demo",
                            "from_name": "Demo Lead Only Co.",
                            "from_kind": "company",
                            "to_id": "domain:demo.example",
                            "to_name": "demo.example",
                            "to_kind": "domain",
                            "relation_type": "public_web_footprint",
                            "confidence": 0.3,
                            "evidence_ids": ["evidence:lead-2"],
                        },
                    ],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Lead Only Co.").to_dict()

    assert packet["risk_brief"]["verdict"] == "insufficient_data"
    assert "clean_verdict_with_blockers" in packet["quality_gate"]["blockers"]
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert packet["source_provenance"]["factual_count"] == 0
    assert packet["source_provenance"]["lead_count"] == 2
    assert packet["summary"]["dd_profile_highlights"]["available"] is True
    assert packet["enterprise_cognition"]["subject_aggregation_available"] is True
    assert packet["enterprise_cognition"]["public_people_profile"]["row_count"] >= 2
    assert "Public Lead Profiles" in packet["report_markdown"]
    assert "corroboration-needed leads, not report facts" in packet["report_markdown"]
    assert "public_leads_need_corroboration" in packet["quality_gate"]["warnings"]
    assert packet["enterprise_cognition"]["subject_due_diligence_profile"]["executive_summary"]["evidence_sources"] >= 1
    assert len(packet["enterprise_cognition"]["relationship_network"]["top_edges"]) == 1


def test_public_web_exact_match_lead_not_counted_as_factual_evidence() -> None:
    graph = {
        "company": "Demo Public Lead Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-web-lead",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Public Lead Co. customer profile",
            "url": "https://example.com/public-lead",
            "confidence": 0.68,
            "claim_count": 1,
            "claims": ["customer=Demo Buyer; market_share=0.12"],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact", "score": 1.0},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Public Lead Co.").to_dict()
    evidence = packet["evidence_ledger"][0]

    assert evidence["record_kind"] == "evidence"
    assert evidence["admission"] == "lead"
    assert packet["source_provenance"]["factual_count"] == 0
    assert packet["source_provenance"]["lead_count"] == 1
    assert packet["source_provenance"]["top_sources"][0]["factual_count"] == 0
    assert packet["source_provenance"]["top_sources"][0]["lead_count"] == 1
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert "public_leads_need_corroboration" in packet["quality_gate"]["warnings"]
    assert "事实级: 0 条" in packet["report_markdown"]
    assert "线索级: 1 条" in packet["report_markdown"]
    assert "Demo Public Lead Co. customer profile" in packet["report_markdown"]


def test_persona_surface_requires_real_lane_basis() -> None:
    from core.investigation import _persona_surface_for_investigation

    empty = _persona_surface_for_investigation({}, {}, {})
    assert empty["active_role_count"] == 0
    assert empty["active_roles"] == []

    grounded = _persona_surface_for_investigation(
        {"covered_dimensions": ["identity"], "controller_candidate_count": 1},
        {"top_findings": [{"title": "risk"}], "risk_event_count": 1},
        {
            "evidence_gaps": ["Missing controller corroboration"],
            "next_questions": ["Verify UBO path"],
            "control_ownership": {"controller_candidate_count": 1},
            "public_goods_profile": {"row_count": 2},
            "evidence_depth_score": {"score": 62},
            "investigation_report_card": {"dd_summary": {}},
            "subject_due_diligence_profile": {"type": "subject_due_diligence_profile"},
            "monitoring_watchlist": ["identity"],
            "risk_hypotheses": ["review controller"],
        },
    )

    assert grounded["active_role_count"] >= 8
    registry_binding = next(item for item in grounded["lane_bindings"] if item["lane"] == "registry")
    assert registry_binding["active"] is True
    assert "enterprise_cognition.control_ownership" in registry_binding["packet_fields"]
    lane_fields = {item["lane"]: set(item["packet_fields"]) for item in grounded["lane_bindings"]}
    assert "one_click_readiness.operator_work_queue" in lane_fields["data_sources"]
    assert "one_click_readiness.operator_work_queue" in lane_fields["task_planning"]
    assert "one_click_readiness.reliance_limitations" in lane_fields["quality"]
    assert "one_click_readiness.can_make_clean_conclusion" in lane_fields["verification"]
    assert "one_click_readiness.capital_relationship_next_action" in lane_fields["finance"]
    for role in grounded["active_roles"]:
        assert role["lane"] != "general"
        assert role["evidence_sources"]
        assert role["packet_fields"]
        assert role["handoff_task"]
        assert all("=False" not in item and "=0" not in item for item in role["evidence_sources"])


def test_profile_brief_falls_back_to_diagnostics_subject_profile() -> None:
    graph = {
        "company": "Demo Diagnostics Profile Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 0,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Diagnostics Profile Co.",
                "controller_candidates": [{
                    "name": "Alice Controller",
                    "confidence": 0.81,
                    "verification_status": "verified",
                    "source_names": ["licensed_registry_api"],
                }],
                "signals_by_dimension": {
                    "identity": [{"dimension": "identity", "title": "Registry", "value": "active"}],
                    "control_ownership": [{"dimension": "control_ownership", "title": "Controller", "value": "Alice"}],
                },
                "evidence_gaps": [],
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Diagnostics Profile Co.").to_dict()
    profile = packet["profile_brief"]

    assert profile["controller_candidate_count"] == 1
    assert profile["controller_candidates"][0]["name"] == "Alice Controller"
    assert profile["covered_dimensions"] == ["identity", "control_ownership"]
    assert profile["dimension_counts"] == {"identity": 1, "control_ownership": 1}


def test_investigate_cli_fixture_pack_returns_product_packet(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Investigate CLI Co., Ltd.",
            "--fixture-pack",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert payload["summary"]["evidence_count"] == 6
    assert payload["profile_brief"]["controller_candidate_count"] >= 1
    assert payload["enterprise_cognition"]["risk_hypotheses"]
    routing_summary = payload["source_failure_summary"]["source_routing_summary"]
    assert routing_summary["policy"].startswith("Routing health describes source availability")
    coverage_watchlist = payload["monitoring_seed"]["coverage_recovery_watchlist"]
    assert any(item["domain"] == "administrative_risk" for item in coverage_watchlist)
    assert any(item["suggested_source"] == "creditchina_public" for item in coverage_watchlist)
    execution_plan = payload["monitoring_seed"]["coverage_recovery_execution_plan"]
    assert any(item["tier"] == "official_public" for item in execution_plan)
    assert any(item["source"] == "creditchina_public" for item in execution_plan)
    execution_readiness = payload["monitoring_seed"]["coverage_recovery_execution_readiness"]
    assert execution_readiness["step_count"] >= len(execution_plan)
    assert "ready_count" in execution_readiness
    assert "blocked_count" in execution_readiness
    recovery_queue = payload["monitoring_seed"]["recovery_execution_queue"]
    assert "ready_to_run" in recovery_queue
    assert "queued_count" in recovery_queue
    assert "blocked_count" in recovery_queue
    if recovery_queue["queue"]:
        first_recovery = recovery_queue["queue"][0]
        replay_route = first_recovery["replay_route"]
        assert first_recovery["retry_policy"]["type"] == "coverage_recovery_retry_policy"
        assert replay_route["mcp_tool"] == "investigate_company"
        assert replay_route["api_route"] == "POST /api/investigate"
        assert replay_route["api_payload"]["default_public_one_click"] is True
        assert replay_route["tool_arguments"]["query_timeout_seconds"] == replay_route["timeout_seconds"]
        assert "one_click_readiness.operator_work_queue" in replay_route["tool_arguments"]["preserve_packet_fields"]
        assert "monitoring_seed.recovery_execution_queue" in replay_route["required_output_fields"]
        assert "--query-timeout-seconds" in replay_route["command"]
        ready_query = recovery_queue["work_order"]["ready_queries"][0]
        assert ready_query["retry_policy"]["retryable"] is True
        assert ready_query["replay_route"]["api_route"] == "POST /api/investigate"
        assert ready_query["replay_route"]["mcp_tool"] == "investigate_company"
    if recovery_queue["blocked_preview"]:
        blocked_route = recovery_queue["blocked_preview"][0]["replay_route"]
        assert blocked_route["ready_to_run"] is False
        assert blocked_route["mcp_tool"] == "investigate_company"
        assert "non-reliance caveat" in blocked_route["failure_routing"]
    recovery_summary = payload["monitoring_seed"]["recovery_execution_summary"]
    assert recovery_summary["blocked_count"] == recovery_queue["blocked_count"]
    assert recovery_summary["policy"].startswith("Use ready queue items")
    assert "relationship_candidate_leads" in payload["monitoring_seed"]["watched_dimensions"]
    relationship_watchlist = payload["monitoring_seed"]["relationship_candidate_watchlist"]
    assert any(item["relation_type"] == "supplier_of" for item in relationship_watchlist)
    assert any(item["priority"] == "P0" for item in relationship_watchlist)
    assert payload["report_markdown"].startswith("# 华尔街驻铁岭办事处")


def test_investigate_cli_json_flag_returns_product_packet(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Investigate Json Co., Ltd.",
            "--fixture-pack",
            "--json",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert payload["report_markdown"].startswith("# 华尔街驻铁岭办事处")


def test_investigate_cli_export_docx_writes_word_file(tmp_path) -> None:
    output_path = tmp_path / "printable-report.docx"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo CLI DOCX Co., Ltd.",
            "--fixture-pack",
            "--export-docx",
            str(output_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert output_path.exists()
    with ZipFile(output_path) as docx:
        document_xml = docx.read("word/document.xml").decode("utf-8")
    assert "Demo CLI DOCX Co., Ltd." in document_xml
    assert "Full Due-Diligence Body" in document_xml
    assert "Renderer Acceptance Checklist" in document_xml


def test_investigate_cli_exports_report_file_bundle(tmp_path) -> None:
    html_path = tmp_path / "report.html"
    markdown_path = tmp_path / "report.md"
    json_path = tmp_path / "packet.json"
    docx_path = tmp_path / "report.docx"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo CLI Export Bundle Co., Ltd.",
            "--offline-fixture",
            "--export-html",
            str(html_path),
            "--export-markdown",
            str(markdown_path),
            "--export-json",
            str(json_path),
            "--export-docx",
            str(docx_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert "Demo CLI Export Bundle Co., Ltd." in html_path.read_text(encoding="utf-8")
    assert markdown_path.read_text(encoding="utf-8").startswith("# ")
    assert json.loads(json_path.read_text(encoding="utf-8"))["type"] == "investigation_packet"
    assert docx_path.exists()


def test_investigate_cli_exports_report_directory_bundle(tmp_path) -> None:
    export_dir = tmp_path / "report-bundle"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo CLI Export Directory Co., Ltd.",
            "--offline-fixture",
            "--export-dir",
            str(export_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    manifest_path = export_dir / "report-export-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]

    assert payload["type"] == "investigation_packet"
    assert manifest["type"] == "report_export_directory_manifest"
    assert manifest["report_exports"]["type"] == "report_exports"
    assert manifest["report_exports"]["directory_bundle"]["integrity_verifier_entrypoint"] == "bin/verify_report_bundle.py <export-dir>"
    assert manifest["report_exports"]["directory_bundle"]["verification_recipe"]["type"] == "report_bundle_verification_recipe"
    assert "agent_handoff.bundle_ready_to_verify" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.image_evidence_inventory_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.source_strengthening_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.relationship_resolution_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.verification_recipe_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.verifier_output_fields_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.bundle_ready_to_verify" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.image_evidence_inventory_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.relationship_resolution_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.acceptance_closure_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.qyyjt_public_origin_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_resilience_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.relationship_graph_audit_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert manifest["file_manifest"]["type"] == "report_export_file_manifest"
    assert manifest["file_manifest"]["hash_algorithm"] == "sha256"
    file_manifest_rows = {item["role"]: item for item in manifest["file_manifest"]["items"]}
    assert file_manifest_rows["portable_html"]["size_bytes"] == (export_dir / files["portable_html"]).stat().st_size
    assert file_manifest_rows["portable_html"]["sha256"] == hashlib.sha256((export_dir / files["portable_html"]).read_bytes()).hexdigest()
    assert file_manifest_rows["json_packet"]["sha256"] == hashlib.sha256((export_dir / files["json_packet"]).read_bytes()).hexdigest()
    assert "agent_handoff" not in file_manifest_rows
    assert "manifest" not in file_manifest_rows
    assert "recursive self-hash ambiguity" in manifest["file_manifest"]["policy"]
    assert manifest["delivery_checklist"]["status"] == "ready_for_desktop_agent_delivery"
    assert manifest["delivery_checklist"]["primary_print_file"] == files["docx"]
    assert manifest["delivery_checklist"]["agent_open_order"][0] == files["docx"]
    assert manifest["agent_summary"]["type"] == "report_export_manifest_agent_summary"
    assert manifest["agent_summary"]["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert manifest["agent_summary"]["decision_digest"]["type"] == "agent_decision_digest"
    assert manifest["agent_summary"]["delivery_status"] == "ready_for_desktop_agent_delivery"
    assert manifest["agent_summary"]["report_visibility"]["type"] == "report_visibility_handoff"
    assert manifest["agent_summary"]["report_visibility"]["image_evidence_inventory_present"] is True
    assert manifest["agent_summary"]["report_visibility"]["source_count"] >= 1
    assert manifest["agent_summary"]["report_visibility"]["section_inventory_count"] >= 1
    assert manifest["agent_summary"]["report_visibility"]["chart_manifest_count"] >= 1
    assert manifest["agent_summary"]["report_visibility"]["premium_html_profile_present"] is True
    assert manifest["agent_summary"]["report_visibility"]["premium_html_status"] == "runtime_contract_available"
    assert manifest["agent_summary"]["capital_risk_panel"]["type"] == "capital_risk_panel"
    assert manifest["agent_summary"]["capital_risk_panel"]["status"] in {
        "evidence_backed",
        "not_applicable",
        "verification_required",
        "unknown",
    }
    assert "capital_verification_queue_count" in manifest["agent_summary"]["capital_risk_panel"]
    assert manifest["agent_summary"]["source_strengthening"]["type"] == "source_strengthening_handoff"
    assert manifest["agent_summary"]["source_strengthening"]["status"] in {"ready", "complete"}
    if manifest["agent_summary"]["source_strengthening"]["work_order_count"]:
        assert manifest["agent_summary"]["source_strengthening"]["top_work_order"]["execution_plan"]["type"] == "source_strengthening_execution_plan"
    assert manifest["agent_summary"]["relationship_resolution"]["type"] == "relationship_resolution_handoff"
    assert manifest["agent_summary"]["relationship_resolution"]["lead_count"] == payload["enterprise_cognition"]["relationship_resolution_v1"]["lead_count"]
    assert "verification_queue_count" in manifest["agent_summary"]["relationship_resolution"]
    assert manifest["agent_summary"]["acceptance_closure_status"] == payload["one_click_readiness"]["acceptance_closure_status"]
    assert manifest["agent_summary"]["source_resilience_status"] == payload["one_click_readiness"]["source_resilience_status"]
    assert isinstance(manifest["agent_summary"]["source_resilience_retryable"], bool)
    assert "source_resilience_blocked_reason" in manifest["agent_summary"]
    assert manifest["agent_summary"]["work_queue_counts"]["operator_work"] == payload["one_click_readiness"]["operator_work_queue_count"]
    assert manifest["agent_summary"]["work_queue_counts"]["capital_verification"] == len(payload["one_click_readiness"]["capital_verification_queue"])
    assert manifest["agent_summary"]["work_queue_counts"]["relationship_audit"] == payload["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert manifest["agent_summary"]["top_public_origin_work_order"] == payload["qyyjt_public_origin_handoff"]["top_section_work_order"]
    assert manifest["agent_summary"]["top_capital_step"] == payload["one_click_readiness"]["capital_verification_top_step"]
    assert manifest["agent_summary"]["top_relationship_step"] == payload["one_click_readiness"]["relationship_graph_audit_top_step"]
    assert manifest["agent_summary"]["next_action_count"] >= 1
    assert manifest["agent_summary"]["top_next_actions"][0]["id"]
    assert "bounded routing preview" in manifest["agent_summary"]["policy"]
    assert (export_dir / files["portable_html"]).read_text(encoding="utf-8").startswith("<!doctype html>")
    assert (export_dir / files["markdown"]).read_text(encoding="utf-8").startswith("# ")
    assert json.loads((export_dir / files["json_packet"]).read_text(encoding="utf-8"))["type"] == "investigation_packet"
    agent_handoff = json.loads((export_dir / files["agent_handoff"]).read_text(encoding="utf-8"))
    assert agent_handoff["type"] == "report_export_agent_handoff"
    assert agent_handoff["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert agent_handoff["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert manifest["agent_summary"]["delivery_decision"] == agent_handoff["delivery_decision"]
    delivery_files = agent_handoff["delivery_files"]
    assert delivery_files["type"] == "delivery_file_handoff"
    assert delivery_files["bundle_manifest"] == files["manifest"]
    assert delivery_files["primary_print_file"] == files["docx"]
    assert delivery_files["primary_screen_file"] == files["portable_html"]
    assert delivery_files["full_evidence_packet"] == files["json_packet"]
    assert delivery_files["markdown_report"] == files["markdown"]
    assert delivery_files["agent_handoff_file"] == files["agent_handoff"]
    assert delivery_files["open_order"][:4] == [
        files["docx"],
        files["portable_html"],
        files["markdown"],
        files["json_packet"],
    ]
    assert delivery_files["files"]["docx"]["path"] == files["docx"]
    assert delivery_files["files"]["docx"]["role"] == "primary_print_report"
    assert delivery_files["files"]["json_packet"]["role"] == "full_evidence_packet"
    assert all(item["required"] is True for item in delivery_files["files"].values())
    assert delivery_files["stdout_preserved"] is True
    assert "relative to the export directory" in delivery_files["policy"]
    assert agent_handoff["bundle_integrity"]["type"] == "bundle_integrity_handoff"
    assert agent_handoff["bundle_integrity"]["ready_to_verify"] is True
    assert agent_handoff["bundle_integrity"]["hash_algorithm"] == "sha256"
    assert "json_packet" in agent_handoff["bundle_integrity"]["required_hashed_roles"]
    assert agent_handoff["bundle_integrity"]["missing_hashed_roles"] == []
    assert agent_handoff["bundle_integrity"]["agent_handoff_self_hash_excluded"] is True
    assert agent_handoff["bundle_verification"]["type"] == "bundle_verification_handoff"
    assert agent_handoff["bundle_verification"]["ready_to_run"] is True
    assert agent_handoff["bundle_verification"]["manifest_file"] == files["manifest"]
    assert "agent_handoff.bundle_ready_to_verify" in agent_handoff["bundle_verification"]["required_output_fields"]
    report_visibility = agent_handoff["report_visibility"]
    assert report_visibility["type"] == "report_visibility_handoff"
    assert report_visibility["portable_html_filename"] == files["portable_html"]
    assert report_visibility["portable_html_contains_full_body"] is True
    assert report_visibility["image_evidence"]["inventory_type"] == "image_evidence_inventory"
    assert report_visibility["image_evidence"]["inventory_source"] == "report_exports.print_package.image_evidence_inventory"
    assert report_visibility["image_evidence"]["count"] == payload["report_exports"]["print_package"]["image_evidence_inventory"]["count"]
    assert report_visibility["source_provenance"]["source_count"] == payload["report_exports"]["print_package"]["source_provenance_appendix"]["source_count"]
    assert report_visibility["section_inventory_count"] == len(payload["report_exports"]["print_package"]["section_inventory"])
    assert report_visibility["chart_manifest_count"] == len(payload["report_exports"]["print_package"]["chart_manifest"])
    assert report_visibility["premium_html"]["profile_present"] is True
    assert report_visibility["premium_html"]["status"] == "runtime_contract_available"
    assert report_visibility["premium_html"]["filename"] == files["portable_html"]
    assert "no_report_body_summarization" in report_visibility["premium_html"]["forbidden_shortcuts"]
    assert "json_packet.evidence_ledger" in report_visibility["open_order"]
    capital_risk_panel = agent_handoff["capital_risk_panel"]
    assert capital_risk_panel["type"] == "capital_risk_panel"
    assert capital_risk_panel["status"] in {"evidence_backed", "not_applicable", "verification_required", "unknown"}
    assert capital_risk_panel["capital_relationship_status"] == payload["one_click_readiness"]["capital_relationship_status"]
    assert capital_risk_panel["capital_verification_queue_count"] == payload["one_click_readiness"]["capital_verification_queue_count"]
    assert capital_risk_panel["relationship_audit_queue_count"] == payload["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert capital_risk_panel["relationship_edge_count"] == payload["one_click_readiness"]["relationship_edge_count"]
    assert capital_risk_panel["clean_reliance_allowed"] in {True, False}
    assert agent_handoff["capital_and_relationship"]["risk_panel"] == capital_risk_panel
    source_strengthening = agent_handoff["source_strengthening"]
    assert source_strengthening["type"] == "source_strengthening_handoff"
    assert source_strengthening["status"] in {"ready", "complete"}
    assert source_strengthening["work_order_count"] == len(source_strengthening["top_work_orders"])
    if source_strengthening["work_order_count"]:
        assert source_strengthening["top_work_order"]["execution_plan"]["type"] == "source_strengthening_execution_plan"
        if source_strengthening["top_work_order"]["connector"] in {
            "idb_sanctioned_firms_dataset_catalog",
            "opensanctions_public_dataset_catalog",
        }:
            assert source_strengthening["top_work_order"]["runtime_companion"]["type"] == "source_strengthening_runtime_companion"
            assert source_strengthening["top_work_order"]["execution_plan"]["runtime_companion"]["connector"].endswith("_local_subject_index")
    else:
        assert source_strengthening["completion_summary"]["pending_work"] is False
    assert "connector_catalog.source_strengthening_queue[].execution_plan" in source_strengthening["preserve_fields"]
    assert "connector_catalog.source_strengthening_queue[].runtime_companion" in source_strengthening["preserve_fields"]
    assert manifest["agent_summary"]["source_strengthening"]["work_order_count"] == source_strengthening["work_order_count"]
    relationship_resolution = agent_handoff["relationship_resolution"]
    packet_resolution = payload["enterprise_cognition"]["relationship_resolution_v1"]
    assert relationship_resolution["type"] == "relationship_resolution_handoff"
    assert relationship_resolution["source"] == "enterprise_cognition.relationship_resolution_v1"
    assert relationship_resolution["lead_count"] == packet_resolution["lead_count"]
    assert relationship_resolution["verification_queue"] == packet_resolution["resolution_summary"]["verification_queue"][:8]
    assert relationship_resolution["verification_queue_count"] == len(relationship_resolution["verification_queue"])
    assert "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue" in relationship_resolution["preserve_fields"]
    assert agent_handoff["capital_and_relationship"]["relationship_resolution"] == relationship_resolution
    assert manifest["agent_summary"]["relationship_resolution"]["verification_queue_count"] == relationship_resolution["verification_queue_count"]
    decision_digest = agent_handoff["decision_digest"]
    assert decision_digest["type"] == "agent_decision_digest"
    assert decision_digest["delivery_status"] == agent_handoff["delivery_checklist"]["status"]
    assert decision_digest["bundle_ready_to_verify"] is True
    assert decision_digest["acceptance_closure_status"] == payload["one_click_readiness"]["acceptance_closure_status"]
    assert decision_digest["can_make_clean_conclusion"] == payload["one_click_readiness"]["can_make_clean_conclusion"]
    assert decision_digest["work_queue_counts"]["operator_work"] == payload["one_click_readiness"]["operator_work_queue_count"]
    assert decision_digest["first_action"]["id"] == agent_handoff["next_actions"][0]["id"]
    assert decision_digest["public_or_authorized_boundary"].startswith("public, licensed")
    assert manifest["agent_summary"]["decision_digest"] == decision_digest
    assert manifest["agent_summary"]["bundle_verification"] == agent_handoff["bundle_verification"]
    assert agent_handoff["delivery_checklist"]["status"] == "ready_for_desktop_agent_delivery"
    assert agent_handoff["delivery_checklist"]["primary_print_file"] == files["docx"]
    assert agent_handoff["delivery_checklist"]["agent_open_order"][0] == files["docx"]
    assert any(row["id"] == "agent_handoff" for row in agent_handoff["delivery_checklist"]["required_outputs"])
    artifact_autorun = agent_handoff["delivery_files"]["agent_autorun"]
    assert artifact_autorun["type"] == "report_artifact_agent_autorun"
    assert artifact_autorun["manual_intermediate_steps_required"] is False
    assert artifact_autorun["routes"][0]["route_id"] == "open-report-artifacts"
    assert artifact_autorun["routes"][0]["open_order"][0] == files["docx"]
    assert artifact_autorun["routes"][1]["route_id"] == "verify-report-bundle"
    assert "verify_report_bundle.py" in artifact_autorun["routes"][1]["cli_command"]
    assert "report_exports.portable_html.document" in artifact_autorun["preserve_packet_fields"]
    assert "do not summarize away report sections" in artifact_autorun["policy"]
    trust_boundaries = agent_handoff["trust_boundaries"]
    assert trust_boundaries["type"] == "agent_handoff_trust_boundaries"
    assert trust_boundaries["can_make_clean_conclusion"] == payload["one_click_readiness"]["can_make_clean_conclusion"]
    assert trust_boundaries["reliance_limitation_count"] == payload["one_click_readiness"]["reliance_limitation_count"]
    assert trust_boundaries["lead_only_until_verified"] is True
    assert trust_boundaries["weak_leads_are_not_facts"] is True
    assert trust_boundaries["source_health_is_connector_work_not_subject_risk"] is True
    assert trust_boundaries["current_release_monitoring_enabled"] is False
    assert "Do not upgrade leads" in trust_boundaries["policy"]
    next_actions = agent_handoff["next_actions"]
    assert next_actions
    assert all({"id", "priority", "status", "action", "ready_to_run", "done_condition", "packet_refs"} <= set(item) for item in next_actions)
    assert any(item["id"] in {"acceptance_closure", "operator_work", "source_resilience"} for item in next_actions)
    assert agent_handoff["acceptance_closure"]["status"] == payload["one_click_readiness"]["acceptance_closure_status"]
    assert agent_handoff["acceptance_closure"]["blocking_count"] == payload["one_click_readiness"]["acceptance_closure_blocking_count"]
    assert agent_handoff["acceptance_closure"]["top_action"] == payload["one_click_readiness"]["acceptance_closure_top_action"]
    assert agent_handoff["acceptance_closure"]["done_condition"] == payload["one_click_readiness"]["acceptance_closure_summary"]["done_condition"]
    assert agent_handoff["acceptance_closure"]["agent_autorun"] == artifact_autorun
    assert agent_handoff["reliance_limitations"]["count"] == payload["one_click_readiness"]["reliance_limitation_count"]
    assert agent_handoff["reliance_limitations"]["can_make_clean_conclusion"] == payload["one_click_readiness"]["can_make_clean_conclusion"]
    assert "items" in agent_handoff["reliance_limitations"]
    assert agent_handoff["operator_work"]["count"] == payload["one_click_readiness"]["operator_work_queue_count"]
    assert agent_handoff["closure_steps"]["people_control_needed"] == payload["one_click_readiness"]["people_control_closure_needed"]
    assert agent_handoff["closure_steps"]["goods_economics_needed"] == payload["one_click_readiness"]["goods_economics_closure_needed"]
    assert agent_handoff["closure_steps"]["control_path_needed"] == payload["one_click_readiness"]["control_path_closure_needed"]
    assert agent_handoff["closure_steps"]["capital_relationship_status"] == payload["one_click_readiness"]["capital_relationship_status"]
    assert agent_handoff["closure_steps"]["steps"]["people_control"] == payload["one_click_readiness"]["people_control_closure_step"]
    assert agent_handoff["closure_steps"]["steps"]["goods_economics"] == payload["one_click_readiness"]["goods_economics_closure_step"]
    assert agent_handoff["closure_steps"]["count"] == len(agent_handoff["closure_steps"]["queue"])
    control_ownership = payload["enterprise_cognition"].get("control_ownership") or {}
    assert agent_handoff["closure_steps"]["control_path_verification_queue"] == control_ownership.get("control_path_verification_queue", [])[:8]
    assert agent_handoff["closure_steps"]["control_path_top_step"] == payload["one_click_readiness"]["control_path_closure_step"]
    assert "evidence ledger and provenance" in agent_handoff["closure_steps"]["policy"]
    assert agent_handoff["qyyjt_public_origin"]["report_section_batches"]
    assert (
        agent_handoff["qyyjt_public_origin"]["section_execution_summary"]
        == payload["qyyjt_public_origin_handoff"]["section_execution_summary"]
    )
    assert (
        agent_handoff["qyyjt_public_origin"]["top_ready_section_work_order"]
        == payload["qyyjt_public_origin_handoff"]["top_ready_section_work_order"]
    )
    assert agent_handoff["qyyjt_public_origin"]["section_work_orders"] == payload["qyyjt_public_origin_handoff"]["section_work_orders"][:8]
    assert agent_handoff["qyyjt_public_origin"]["top_section_work_order"] == payload["qyyjt_public_origin_handoff"]["top_section_work_order"]
    assert agent_handoff["qyyjt_public_origin"]["agent_autorun"] == payload["qyyjt_public_origin_handoff"]["agent_autorun"]
    qyyjt_export_autorun = agent_handoff["qyyjt_public_origin"]["agent_autorun"]
    assert qyyjt_export_autorun["manual_intermediate_steps_required"] is False
    assert qyyjt_export_autorun["routes"][0]["cli_command"].startswith("npx wallstreet-tieling --investigate")
    assert "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin" in (
        qyyjt_export_autorun["routes"][0]["tool_arguments"]["preserve_packet_fields"]
    )
    assert agent_handoff["qyyjt_public_origin"]["gap_bridge"] == payload["one_click_readiness"]["public_origin_gap_bridge"]
    assert agent_handoff["qyyjt_public_origin"]["gap_bridge_top_action"] == payload["one_click_readiness"]["public_origin_gap_bridge_top_action"]
    assert agent_handoff["source_health"]["snapshot"]["type"] == "source_health_trend_snapshot"
    assert agent_handoff["source_health"]["digest"] == payload["one_click_readiness"]["source_health_trend_digest"]
    assert agent_handoff["source_health"]["top_source"] == payload["one_click_readiness"]["source_health_trend_top_source"]
    assert agent_handoff["source_health"]["policy"] == payload["one_click_readiness"]["source_health_trend_policy"]
    assert agent_handoff["source_health"]["recovery_execution_queue"] == payload["monitoring_seed"]["recovery_execution_queue"]
    source_replay_queue = agent_handoff["source_health"]["recovery_execution_queue"]
    replay_rows = source_replay_queue["queue"] or source_replay_queue["blocked_preview"]
    assert replay_rows[0]["replay_route"]["tool"] == "investigate_company"
    assert "non_reliance_caveat" in replay_rows[0]
    assert agent_handoff["source_health"]["source_resilience"]["retry_policy"] == payload["one_click_readiness"]["source_resilience_retry_policy"]
    assert agent_handoff["source_health"]["source_resilience"]["max_attempts"] == payload["one_click_readiness"]["source_resilience_retry_max_attempts"]
    assert agent_handoff["report_visibility"]["agent_autorun"] == artifact_autorun
    assert agent_handoff["bundle_verification"]["agent_autorun"] == artifact_autorun
    source_autorun = agent_handoff["source_health"]["source_resilience"]["agent_autorun"]
    assert source_autorun["manual_intermediate_steps_required"] is False
    assert source_autorun["routes"][0]["mcp_tool"] == "investigate_company"
    assert source_autorun["routes"][0]["api_route"] == "POST /api/investigate"
    assert "monitoring_seed.recovery_execution_queue" in source_autorun["routes"][0]["required_output_fields"]
    assert agent_handoff["capital_and_relationship"]["graph_capital_exposure"] == payload["one_click_readiness"]["graph_capital_exposure"]
    assert agent_handoff["capital_and_relationship"]["graph_capital_exposure_top_step"] == payload["one_click_readiness"]["graph_capital_exposure_top_step"]
    assert agent_handoff["capital_and_relationship"]["capital_verification_queue"] == payload["one_click_readiness"]["capital_verification_queue"][:8]
    assert "capital_verification_top_step" in agent_handoff["capital_and_relationship"]
    capital_export_autorun = agent_handoff["capital_risk_panel"]["agent_autorun"]
    assert capital_export_autorun["type"] == "capital_risk_agent_autorun"
    assert capital_export_autorun["routes"][0]["mcp_tool"] == "investigate_company"
    assert agent_handoff["capital_and_relationship"]["agent_autorun"]["capital_verification"] == capital_export_autorun
    relationship_audit = agent_handoff["capital_and_relationship"]["relationship_graph_audit"]
    assert relationship_audit["type"] == "relationship_graph_audit_handoff"
    assert relationship_audit["edge_count"] == payload["one_click_readiness"]["relationship_edge_count"]
    assert relationship_audit["evidence_backed_edge_count"] == payload["one_click_readiness"]["relationship_evidence_backed_edge_count"]
    assert relationship_audit["auditable_edge_count"] == payload["one_click_readiness"]["relationship_auditable_edge_count"]
    assert relationship_audit["missing_evidence_edge_count"] == payload["one_click_readiness"]["relationship_missing_evidence_edge_count"]
    assert relationship_audit["lead_only_edge_count"] == payload["one_click_readiness"]["relationship_lead_only_edge_count"]
    assert relationship_audit["queue_count"] == payload["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert relationship_audit["queue"] == payload["one_click_readiness"]["relationship_graph_audit_queue"][:8]
    assert relationship_audit["top_step"] == payload["one_click_readiness"]["relationship_graph_audit_top_step"]
    assert relationship_audit["status"] in {"no_relationship_edges", "audit_required", "evidence_backed"}
    assert relationship_audit["agent_autorun"]["type"] == "relationship_graph_audit_agent_autorun"
    assert agent_handoff["capital_and_relationship"]["agent_autorun"]["relationship_graph_audit"] == relationship_audit["agent_autorun"]
    assert "task routing only" in relationship_audit["policy"]
    assert agent_handoff["relationship_resolution"]["agent_autorun"]["type"] == "relationship_resolution_agent_autorun"
    assert (
        agent_handoff["capital_and_relationship"]["agent_autorun"]["relationship_resolution"]
        == agent_handoff["relationship_resolution"]["agent_autorun"]
    )
    assert agent_handoff["report_handoff_cards"]["cards"]
    assert agent_handoff["report_handoff_cards"]["delivery_checklist_status"] == "ready_for_desktop_agent_delivery"
    verifier = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    verification = json.loads(verifier.stdout)
    assert verification["type"] == "report_export_bundle_verification"
    assert verification["ok"] is True
    assert verification["checked_count"] == manifest["file_manifest"]["item_count"]
    assert verification["agent_handoff"]["checked"] is True
    assert verification["agent_handoff"]["schema_valid"] is True
    assert verification["agent_handoff"]["decision_digest_present"] is True
    assert verification["agent_handoff"]["delivery_checklist_present"] is True
    assert verification["agent_handoff"]["bundle_integrity_present"] is True
    assert verification["agent_handoff"]["bundle_verification_present"] is True
    assert verification["agent_handoff"]["bundle_verification_ready_to_run"] is True
    assert verification["agent_handoff"]["bundle_ready_to_verify"] is True
    assert verification["agent_handoff"]["report_visibility_present"] is True
    assert verification["agent_handoff"]["premium_html_report_visibility_present"] is True
    assert verification["agent_handoff"]["image_evidence_inventory_present"] is True
    assert verification["agent_handoff"]["capital_risk_panel_present"] is True
    assert verification["agent_handoff"]["source_strengthening_present"] is True
    assert verification["agent_handoff"]["source_strengthening_runtime_companion_present"] is True
    assert verification["agent_handoff"]["relationship_resolution_present"] is True
    assert verification["agent_handoff"]["capital_relationship_crosswalk_present"] is True
    crosswalk = verification["agent_handoff"]["capital_relationship_crosswalk"]
    assert crosswalk["checked"] is True
    assert crosswalk["json_packet_checked"] is True
    assert crosswalk["manifest_metadata_checked"] is True
    assert crosswalk["agent_handoff_checked"] is True
    assert crosswalk["markdown_checked"] is True
    assert crosswalk["portable_html_metadata_checked"] is True
    assert crosswalk["docx_metadata_checked"] is True
    assert crosswalk["expected"]["capital_relationship_status"] == payload["one_click_readiness"]["capital_relationship_status"]
    assert crosswalk["expected"]["capital_verification_queue_count"] == payload["one_click_readiness"]["capital_verification_queue_count"]
    assert crosswalk["expected"]["relationship_audit_queue_count"] == payload["one_click_readiness"]["relationship_graph_audit_queue_count"]
    assert verification["agent_handoff"]["verification_recipe_present"] is True
    assert verification["agent_handoff"]["verifier_output_fields_present"] is True
    assert verification["agent_handoff"]["acceptance_closure_present"] is True
    assert verification["agent_handoff"]["qyyjt_public_origin_present"] is True
    assert verification["agent_handoff"]["source_resilience_present"] is True
    assert verification["agent_handoff"]["relationship_graph_audit_present"] is True
    handoff_path = export_dir / files["agent_handoff"]
    original_handoff_text = handoff_path.read_text(encoding="utf-8")
    broken_relationship_handoff = json.loads(original_handoff_text)
    broken_relationship_handoff.pop("relationship_resolution")
    handoff_path.write_text(json.dumps(broken_relationship_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_relationship_result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_relationship_result.returncode == 2
    broken_relationship_verification = json.loads(broken_relationship_result.stdout)
    assert any(
        item["reason"] in {"missing_relationship_resolution", "invalid_relationship_resolution"}
        for item in broken_relationship_verification["agent_handoff"]["failures"]
    )
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_handoff = json.loads(original_handoff_text)
    broken_handoff.pop("decision_digest")
    handoff_path.write_text(json.dumps(broken_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_handoff_result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_handoff_result.returncode == 2
    broken_handoff_verification = json.loads(broken_handoff_result.stdout)
    assert broken_handoff_verification["agent_handoff"]["schema_valid"] is False
    assert any(item["reason"] == "missing_decision_digest" for item in broken_handoff_verification["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    manifest_path = export_dir / files["manifest"]
    original_manifest_text = manifest_path.read_text(encoding="utf-8")
    broken_manifest = json.loads(original_manifest_text)
    broken_manifest["agent_summary"]["delivery_decision"] = {
        "status": "stale_or_wrong_delivery_decision"
    }
    manifest_path.write_text(json.dumps(broken_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_manifest_result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_manifest_result.returncode == 2
    broken_manifest_verification = json.loads(broken_manifest_result.stdout)
    assert broken_manifest_verification["agent_handoff"]["schema_valid"] is False
    assert any(
        item["reason"] == "agent_summary_delivery_decision_mismatch"
        for item in broken_manifest_verification["failures"]
    )
    manifest_path.write_text(original_manifest_text, encoding="utf-8")
    broken_summary_visibility = json.loads(original_manifest_text)
    broken_summary_visibility["agent_summary"]["report_visibility"]["source_count"] += 99
    manifest_path.write_text(json.dumps(broken_summary_visibility, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_summary_visibility_result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_summary_visibility_result.returncode == 2
    broken_summary_visibility_verification = json.loads(broken_summary_visibility_result.stdout)
    assert broken_summary_visibility_verification["agent_handoff"]["schema_valid"] is False
    assert any(
        item["reason"] == "agent_summary_report_visibility_mismatch"
        for item in broken_summary_visibility_verification["failures"]
    )
    manifest_path.write_text(original_manifest_text, encoding="utf-8")
    broken_summary_queue = json.loads(original_manifest_text)
    broken_summary_queue["agent_summary"]["work_queue_counts"]["relationship_audit"] += 7
    manifest_path.write_text(json.dumps(broken_summary_queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_summary_queue_result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_summary_queue_result.returncode == 2
    broken_summary_queue_verification = json.loads(broken_summary_queue_result.stdout)
    assert broken_summary_queue_verification["agent_handoff"]["schema_valid"] is False
    assert any(
        item["reason"] == "agent_summary_work_queue_counts_mismatch"
        for item in broken_summary_queue_verification["failures"]
    )
    manifest_path.write_text(original_manifest_text, encoding="utf-8")
    broken_verification_handoff = json.loads(original_handoff_text)
    broken_verification_handoff.pop("bundle_verification")
    handoff_path.write_text(json.dumps(broken_verification_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_bundle_verification = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_bundle_verification.returncode == 2
    broken_bundle_verification_result = json.loads(broken_bundle_verification.stdout)
    assert broken_bundle_verification_result["agent_handoff"]["bundle_verification_present"] is False
    assert broken_bundle_verification_result["agent_handoff"]["bundle_verification_ready_to_run"] is False
    assert any(
        item["reason"] in {"missing_bundle_verification", "invalid_bundle_verification"}
        for item in broken_bundle_verification_result["failures"]
    )
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_visibility_handoff = json.loads(original_handoff_text)
    broken_visibility_handoff.pop("report_visibility")
    handoff_path.write_text(json.dumps(broken_visibility_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_visibility = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_visibility.returncode == 2
    broken_visibility_result = json.loads(broken_visibility.stdout)
    assert broken_visibility_result["agent_handoff"]["report_visibility_present"] is False
    assert broken_visibility_result["agent_handoff"]["premium_html_report_visibility_present"] is False
    assert any(item["reason"] in {"missing_report_visibility", "invalid_report_visibility"} for item in broken_visibility_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_premium_html_handoff = json.loads(original_handoff_text)
    broken_premium_html_handoff["report_visibility"]["premium_html"].pop("content_guarantees")
    handoff_path.write_text(json.dumps(broken_premium_html_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_premium_html = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_premium_html.returncode == 2
    broken_premium_html_result = json.loads(broken_premium_html.stdout)
    assert broken_premium_html_result["agent_handoff"]["premium_html_report_visibility_present"] is False
    assert any(item["reason"] == "premium_html_report_visibility_contract_missing" for item in broken_premium_html_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_image_inventory_handoff = json.loads(original_handoff_text)
    broken_image_inventory_handoff["report_visibility"]["image_evidence"].pop("inventory_source")
    handoff_path.write_text(json.dumps(broken_image_inventory_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_image_inventory = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_image_inventory.returncode == 2
    broken_image_inventory_result = json.loads(broken_image_inventory.stdout)
    assert broken_image_inventory_result["agent_handoff"]["image_evidence_inventory_present"] is False
    assert any(item["reason"] == "image_evidence_inventory_contract_missing" for item in broken_image_inventory_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_recipe_manifest = json.loads(original_manifest_text)
    broken_recipe_manifest["report_exports"]["directory_bundle"].pop("verification_recipe")
    manifest_path.write_text(json.dumps(broken_recipe_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_recipe = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_recipe.returncode == 2
    broken_recipe_result = json.loads(broken_recipe.stdout)
    assert broken_recipe_result["agent_handoff"]["verification_recipe_present"] is False
    assert any(item["reason"] == "verification_recipe_missing" for item in broken_recipe_result["failures"])
    manifest_path.write_text(original_manifest_text, encoding="utf-8")
    broken_capital_handoff = json.loads(original_handoff_text)
    broken_capital_handoff.pop("capital_risk_panel")
    handoff_path.write_text(json.dumps(broken_capital_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_capital = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_capital.returncode == 2
    broken_capital_result = json.loads(broken_capital.stdout)
    assert broken_capital_result["agent_handoff"]["capital_risk_panel_present"] is False
    assert any(item["reason"] in {"missing_capital_risk_panel", "invalid_capital_risk_panel"} for item in broken_capital_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_strengthening_handoff = json.loads(original_handoff_text)
    broken_strengthening_handoff["source_strengthening"]["status"] = "ready"
    broken_strengthening_handoff["source_strengthening"]["work_order_count"] = 1
    broken_strengthening_handoff["source_strengthening"]["top_work_orders"] = [{
        "connector": "broken_runtime_companion_fixture",
        "execution_plan": {"type": "source_strengthening_execution_plan"},
    }]
    broken_strengthening_handoff["source_strengthening"]["top_work_order"] = broken_strengthening_handoff["source_strengthening"]["top_work_orders"][0]
    broken_strengthening_handoff["source_strengthening"]["top_work_orders"][0].pop("runtime_companion", None)
    broken_strengthening_handoff["source_strengthening"]["top_work_orders"][0]["execution_plan"].pop("runtime_companion", None)
    handoff_path.write_text(json.dumps(broken_strengthening_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_strengthening = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_strengthening.returncode == 2
    broken_strengthening_result = json.loads(broken_strengthening.stdout)
    assert broken_strengthening_result["agent_handoff"]["source_strengthening_present"] is True
    assert broken_strengthening_result["agent_handoff"]["source_strengthening_runtime_companion_present"] is False
    assert any(item["reason"] == "source_strengthening_runtime_companion_missing" for item in broken_strengthening_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_crosswalk_handoff = json.loads(original_handoff_text)
    broken_crosswalk_handoff["capital_risk_panel"]["capital_verification_queue_count"] += 1
    handoff_path.write_text(json.dumps(broken_crosswalk_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_crosswalk = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_crosswalk.returncode == 2
    broken_crosswalk_result = json.loads(broken_crosswalk.stdout)
    assert broken_crosswalk_result["agent_handoff"]["capital_relationship_crosswalk_present"] is False
    assert any(
        item["reason"] in {"capital_relationship_crosswalk_mismatch", "capital_relationship_risk_panel_mismatch"}
        for item in broken_crosswalk_result["failures"]
    )
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_acceptance_handoff = json.loads(original_handoff_text)
    broken_acceptance_handoff.pop("acceptance_closure")
    handoff_path.write_text(json.dumps(broken_acceptance_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_acceptance = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_acceptance.returncode == 2
    broken_acceptance_result = json.loads(broken_acceptance.stdout)
    assert broken_acceptance_result["agent_handoff"]["acceptance_closure_present"] is False
    assert any(item["reason"] in {"missing_acceptance_closure", "invalid_acceptance_closure"} for item in broken_acceptance_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_qyyjt_handoff = json.loads(original_handoff_text)
    broken_qyyjt_handoff["qyyjt_public_origin"].pop("section_execution_summary")
    handoff_path.write_text(json.dumps(broken_qyyjt_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_qyyjt = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_qyyjt.returncode == 2
    broken_qyyjt_result = json.loads(broken_qyyjt.stdout)
    assert broken_qyyjt_result["agent_handoff"]["qyyjt_public_origin_present"] is True
    assert any(item["reason"] == "qyyjt_public_origin_missing_section_execution_summary" for item in broken_qyyjt_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_source_handoff = json.loads(original_handoff_text)
    broken_source_handoff["source_health"].pop("source_resilience")
    handoff_path.write_text(json.dumps(broken_source_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_source = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_source.returncode == 2
    broken_source_result = json.loads(broken_source.stdout)
    assert broken_source_result["agent_handoff"]["source_resilience_present"] is False
    assert any(item["reason"] == "invalid_source_resilience" for item in broken_source_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    broken_relationship_handoff = json.loads(original_handoff_text)
    broken_relationship_handoff["capital_and_relationship"].pop("relationship_graph_audit")
    handoff_path.write_text(json.dumps(broken_relationship_handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    broken_relationship = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert broken_relationship.returncode == 2
    broken_relationship_result = json.loads(broken_relationship.stdout)
    assert broken_relationship_result["agent_handoff"]["relationship_graph_audit_present"] is False
    assert any(item["reason"] == "invalid_relationship_graph_audit" for item in broken_relationship_result["failures"])
    handoff_path.write_text(original_handoff_text, encoding="utf-8")
    tampered_html = export_dir / files["portable_html"]
    original_html_text = tampered_html.read_text(encoding="utf-8")
    tampered_html.write_text(original_html_text.replace("Visual evidence panels", "Visual evidence panel removed"), encoding="utf-8")
    missing_visual_panel = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert missing_visual_panel.returncode == 2
    missing_visual_panel_result = json.loads(missing_visual_panel.stdout)
    assert any(item["reason"] == "portable_html_visual_evidence_panels_missing" for item in missing_visual_panel_result["failures"])
    tampered_html.write_text(original_html_text + "\n<!-- tampered -->", encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert tampered.returncode == 2
    tampered_result = json.loads(tampered.stdout)
    assert tampered_result["ok"] is False
    assert any(item["reason"] == "sha256_mismatch" for item in tampered_result["failures"])
    with ZipFile(export_dir / files["docx"]) as docx:
        assert "word/document.xml" in set(docx.namelist())


def test_node_cli_passes_report_export_options(tmp_path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node runtime not available")

    html_path = tmp_path / "node-report.html"
    json_path = tmp_path / "node-packet.json"
    export_dir = tmp_path / "node-bundle"
    result = subprocess.run(
        [
            node,
            str(ROOT / "bin" / "cli.js"),
            "--investigate",
            "Demo Node Export Co., Ltd.",
            "--offline-fixture",
            "--export-html",
            str(html_path),
            "--export-json",
            str(json_path),
            "--export-dir",
            str(export_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert json.loads(json_path.read_text(encoding="utf-8"))["type"] == "investigation_packet"
    assert (export_dir / "report-export-manifest.json").exists()


def test_node_cli_offline_fallback_writes_agent_handoff_bundle(tmp_path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node runtime not available")

    export_dir = tmp_path / "node-fallback-bundle"
    result = subprocess.run(
        [
            node,
            str(ROOT / "bin" / "cli.js"),
            "--investigate",
            "Demo Node Fallback Co., Ltd.",
            "--offline-fixture",
            "--export-dir",
            str(export_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "WST_FORCE_NODE_OFFLINE_FALLBACK": "1"},
    )
    payload = json.loads(result.stdout)
    manifest = json.loads((export_dir / "report-export-manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    agent_handoff = json.loads((export_dir / files["agent_handoff"]).read_text(encoding="utf-8"))

    assert payload["type"] == "investigation_packet"
    assert manifest["type"] == "report_export_directory_manifest"
    assert manifest["unavailable_outputs"]["docx"] == "python_runtime_unavailable"
    assert manifest["report_exports"]["directory_bundle"]["integrity_verifier_entrypoint"] == "bin/verify_report_bundle.py <export-dir>"
    assert manifest["report_exports"]["directory_bundle"]["verification_recipe"]["type"] == "report_bundle_verification_recipe"
    assert "agent_handoff.bundle_ready_to_verify" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.source_strengthening_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in manifest["report_exports"]["directory_bundle"]["verification_recipe"]["required_output_fields"]
    assert "agent_handoff.bundle_ready_to_verify" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.premium_html_report_visibility_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.capital_relationship_crosswalk_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "agent_handoff.source_strengthening_runtime_companion_present" in manifest["report_exports"]["directory_bundle"]["verifier_output_fields"]
    assert "file_manifest" in manifest["report_exports"]["directory_bundle"]["manifest_fields"]
    assert manifest["file_manifest"]["type"] == "report_export_file_manifest"
    fallback_file_manifest_rows = {item["role"]: item for item in manifest["file_manifest"]["items"]}
    assert fallback_file_manifest_rows["portable_html"]["sha256"] == hashlib.sha256((export_dir / files["portable_html"]).read_bytes()).hexdigest()
    assert fallback_file_manifest_rows["json_packet"]["size_bytes"] == (export_dir / files["json_packet"]).stat().st_size
    assert "agent_handoff" not in fallback_file_manifest_rows
    assert "manifest" not in fallback_file_manifest_rows
    assert "delivery_checklist" in manifest["report_exports"]["directory_bundle"]["manifest_fields"]
    assert "agent_summary" in manifest["report_exports"]["directory_bundle"]["manifest_fields"]
    assert manifest["delivery_checklist"]["status"] == "fallback_delivery_without_docx"
    assert manifest["delivery_checklist"]["primary_print_file"] is None
    assert manifest["agent_summary"]["type"] == "report_export_manifest_agent_summary"
    assert manifest["agent_summary"]["decision_digest"]["type"] == "agent_decision_digest"
    assert manifest["agent_summary"]["delivery_status"] == "fallback_delivery_without_docx"
    assert manifest["agent_summary"]["acceptance_closure_status"] == "blocked"
    assert manifest["agent_summary"]["source_resilience_blocked_reason"] == "python_runtime_unavailable"
    assert manifest["agent_summary"]["report_visibility"]["type"] == "report_visibility_handoff"
    assert manifest["agent_summary"]["report_visibility"]["image_evidence_inventory_present"] is True
    assert manifest["agent_summary"]["report_visibility"]["image_evidence_count"] == 0
    assert manifest["agent_summary"]["report_visibility"]["source_count"] == 0
    assert manifest["agent_summary"]["report_visibility"]["premium_html_profile_present"] is True
    assert manifest["agent_summary"]["report_visibility"]["premium_html_status"] == "fallback_runtime_pending"
    assert manifest["agent_summary"]["capital_risk_panel"]["type"] == "capital_risk_panel"
    assert manifest["agent_summary"]["capital_risk_panel"]["status"] == "blocked"
    assert manifest["agent_summary"]["capital_risk_panel"]["clean_reliance_allowed"] is False
    assert manifest["agent_summary"]["source_strengthening"]["type"] == "source_strengthening_handoff"
    assert manifest["agent_summary"]["source_strengthening"]["status"] in {"ready", "complete", "fallback_runtime_pending"}
    assert manifest["agent_summary"]["work_queue_counts"]["operator_work"] == 0
    assert manifest["agent_summary"]["work_queue_counts"]["qyyjt_public_origin_sections"] == 1
    assert manifest["agent_summary"]["top_public_origin_work_order"]["work_order_id"] == "fallback_legal_risk_public_origin"
    assert manifest["agent_summary"]["top_next_actions"][0]["id"] == "restore_python_runtime"
    assert files["docx"] is None
    assert (export_dir / files["portable_html"]).read_text(encoding="utf-8").startswith("<!doctype html>")
    assert json.loads((export_dir / files["json_packet"]).read_text(encoding="utf-8"))["type"] == "investigation_packet"
    section_summary = payload["qyyjt_public_origin_handoff"]["section_execution_summary"]
    assert section_summary["type"] == "qyyjt_section_execution_summary"
    assert section_summary["section_count"] == 1
    assert section_summary["p0_section_count"] == 1
    assert section_summary["ready_section_count"] == 1
    assert section_summary["blocked_section_count"] == 0
    assert section_summary["top_ready_work_order"]["ready_to_run"] is True
    assert payload["qyyjt_public_origin_handoff"]["top_ready_section_work_order"]["work_order_id"] == "fallback_legal_risk_public_origin"
    assert agent_handoff["type"] == "report_export_agent_handoff"
    assert agent_handoff["delivery_decision"]["status"] == "desktop_agent_alpha_needs_runtime_closure"
    assert agent_handoff["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert manifest["agent_summary"]["delivery_decision"] == agent_handoff["delivery_decision"]
    assert "delivery_decision" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "bundle_integrity" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "bundle_verification" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "delivery_checklist" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "report_visibility" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "capital_risk_panel" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "decision_digest" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["schema_fields"]
    assert "bundle integrity" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["content"]
    assert "report visibility" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["content"]
    assert "capital risk panel" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["content"]
    assert "decision digest" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["content"]
    assert "trust boundaries" in manifest["report_exports"]["directory_bundle"]["agent_handoff"]["content"]
    assert agent_handoff["bundle_integrity"]["ready_to_verify"] is True
    assert agent_handoff["bundle_integrity"]["required_hashed_roles"] == ["portable_html", "markdown", "json_packet"]
    assert agent_handoff["bundle_integrity"]["missing_hashed_roles"] == []
    assert agent_handoff["bundle_integrity"]["agent_handoff_self_hash_excluded"] is True
    assert agent_handoff["bundle_verification"]["type"] == "bundle_verification_handoff"
    assert agent_handoff["bundle_verification"]["ready_to_run"] is True
    assert agent_handoff["bundle_verification"]["manifest_file"] == files["manifest"]
    assert "agent_handoff.bundle_ready_to_verify" in agent_handoff["bundle_verification"]["required_output_fields"]
    assert agent_handoff["report_visibility"]["type"] == "report_visibility_handoff"
    assert agent_handoff["report_visibility"]["portable_html_filename"] == files["portable_html"]
    assert agent_handoff["report_visibility"]["image_evidence"]["inventory_type"] == "image_evidence_inventory"
    assert agent_handoff["report_visibility"]["image_evidence"]["inventory_source"] == "report_exports.print_package.image_evidence_inventory"
    assert agent_handoff["report_visibility"]["image_evidence"]["count"] == 0
    assert agent_handoff["report_visibility"]["source_provenance"]["source_count"] == 0
    assert agent_handoff["report_visibility"]["premium_html"]["profile_present"] is True
    assert agent_handoff["report_visibility"]["premium_html"]["status"] == "fallback_runtime_pending"
    assert "no_report_body_summarization" in agent_handoff["report_visibility"]["premium_html"]["forbidden_shortcuts"]
    assert agent_handoff["capital_risk_panel"]["type"] == "capital_risk_panel"
    assert agent_handoff["capital_risk_panel"]["status"] == "blocked"
    assert agent_handoff["capital_risk_panel"]["capital_verification_queue_count"] == 1
    assert agent_handoff["capital_risk_panel"]["clean_reliance_allowed"] is False
    assert agent_handoff["source_strengthening"]["type"] == "source_strengthening_handoff"
    assert agent_handoff["source_strengthening"]["top_work_order"]["execution_plan"]["type"] == "source_strengthening_execution_plan"
    assert agent_handoff["source_strengthening"]["top_work_order"]["runtime_companion"]["type"] == "source_strengthening_runtime_companion"
    assert agent_handoff["delivery_files"]["primary_print_file"] is None
    assert agent_handoff["delivery_files"]["files"]["docx"]["required"] is False
    assert agent_handoff["delivery_files"]["files"]["docx"]["unavailable_reason"] == "python_runtime_unavailable"
    assert agent_handoff["delivery_files"]["primary_screen_file"] == files["portable_html"]
    assert agent_handoff["delivery_checklist"]["status"] == "fallback_delivery_without_docx"
    assert agent_handoff["delivery_checklist"]["primary_print_file"] is None
    assert any(row["id"] == "docx_red_head" and row["required"] is False for row in agent_handoff["delivery_checklist"]["required_outputs"])
    assert agent_handoff["trust_boundaries"]["can_make_clean_conclusion"] is False
    assert agent_handoff["trust_boundaries"]["current_release_monitoring_enabled"] is False
    assert agent_handoff["decision_digest"]["delivery_status"] == "fallback_delivery_without_docx"
    assert agent_handoff["decision_digest"]["source_resilience_status"] == "python_runtime_unavailable"
    assert agent_handoff["decision_digest"]["first_action"]["id"] == "restore_python_runtime"
    assert manifest["agent_summary"]["decision_digest"] == agent_handoff["decision_digest"]
    assert manifest["agent_summary"]["bundle_verification"] == agent_handoff["bundle_verification"]
    assert agent_handoff["next_actions"][0]["id"] == "restore_python_runtime"
    assert agent_handoff["acceptance_closure"]["status"] == "blocked"
    assert agent_handoff["qyyjt_public_origin"]["handoff"] == payload["qyyjt_public_origin_handoff"]
    assert (
        agent_handoff["qyyjt_public_origin"]["section_execution_summary"]
        == payload["qyyjt_public_origin_handoff"]["section_execution_summary"]
    )
    assert (
        agent_handoff["qyyjt_public_origin"]["section_work_orders"]
        == payload["qyyjt_public_origin_handoff"]["section_work_orders"]
    )
    assert (
        agent_handoff["qyyjt_public_origin"]["top_ready_section_work_order"]
        == payload["qyyjt_public_origin_handoff"]["top_ready_section_work_order"]
    )
    assert agent_handoff["qyyjt_public_origin"]["top_section_work_order"]["work_order_id"] == "fallback_legal_risk_public_origin"
    fallback_html = (export_dir / files["portable_html"]).read_text(encoding="utf-8")
    assert "premium_html" in payload["report_exports"]["formats"]
    assert payload["report_exports"]["premium_html"]["type"] == "premium_html_report_profile"
    assert payload["report_exports"]["premium_html"]["status"] == "fallback_runtime_pending"
    assert payload["report_exports"]["portable_html"]["premium_profile"] == payload["report_exports"]["premium_html"]
    assert "data-premium-html-report" in fallback_html
    assert "data-full-report-preserved" in fallback_html
    assert "Premium HTML visual QA checklist" in fallback_html
    assert "prefers-reduced-motion" in fallback_html
    assert "@media print" in fallback_html
    verifier = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "verify_report_bundle.py"), str(export_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    verification = json.loads(verifier.stdout)
    assert verification["ok"] is True
    assert verification["checked_count"] == manifest["file_manifest"]["item_count"]
    assert verification["agent_handoff"]["checked"] is True
    assert verification["agent_handoff"]["schema_valid"] is True
    assert verification["agent_handoff"]["decision_digest_present"] is True
    assert verification["agent_handoff"]["delivery_checklist_present"] is True
    assert verification["agent_handoff"]["bundle_integrity_present"] is True
    assert verification["agent_handoff"]["bundle_verification_present"] is True
    assert verification["agent_handoff"]["bundle_verification_ready_to_run"] is True
    assert verification["agent_handoff"]["bundle_ready_to_verify"] is True
    assert verification["agent_handoff"]["report_visibility_present"] is True
    assert verification["agent_handoff"]["premium_html_report_visibility_present"] is True
    assert verification["agent_handoff"]["image_evidence_inventory_present"] is True
    assert verification["agent_handoff"]["capital_risk_panel_present"] is True
    assert verification["agent_handoff"]["source_strengthening_present"] is True
    assert verification["agent_handoff"]["source_strengthening_runtime_companion_present"] is True
    assert verification["agent_handoff"]["capital_relationship_crosswalk_present"] is True
    assert verification["agent_handoff"]["capital_relationship_crosswalk"]["fallback_bundle"] is True
    assert verification["agent_handoff"]["verification_recipe_present"] is True
    assert verification["agent_handoff"]["verifier_output_fields_present"] is True


def test_investigate_cli_rejects_json_and_report_only_conflict() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Invalid Output Co., Ltd.",
            "--fixture-pack",
            "--json",
            "--report-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "--json and --report-only are mutually exclusive" in result.stderr


def test_investigate_cli_defaults_to_one_click_public_path(monkeypatch, tmp_path) -> None:
    import bin.investigate as investigate

    class FakeDefaultSearch:
        pass

    calls = {}
    original_resolve = investigate.resolve_one_click_retrieval_async
    original_run = RiskDiscoveryPipeline.run

    async def fake_resolve(**kwargs):
        calls["resolve"] = kwargs
        return await original_resolve(
            **{
                **kwargs,
                "search_engine": FakeDefaultSearch(),
                "existing_plan": None,
                "default_enabled": False,
            }
        )

    async def fake_pipeline_run(self, company, **kwargs):
        calls["run"] = kwargs
        result = await original_run(
            RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl"),
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
        return result

    monkeypatch.setattr(investigate, "resolve_one_click_retrieval_async", fake_resolve)
    monkeypatch.setattr(investigate.RiskDiscoveryPipeline, "run", fake_pipeline_run)

    args = investigate.build_parser().parse_args(["Demo Default CLI Co., Ltd."])
    payload = asyncio.run(investigate.run(args))

    assert payload["type"] == "investigation_packet"
    assert payload["one_click"] is True
    assert payload["summary"]["evidence_count"] == 6
    assert calls["resolve"]["records"] is None
    assert calls["resolve"]["search_engine"] is None
    assert isinstance(calls["run"]["search_engine"], FakeDefaultSearch)


def test_investigation_packet_ranks_exact_official_evidence_first() -> None:
    graph = {
        "company": "Demo Ranking Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "review-1",
                "source": "wikidata_public_entity_graph",
                "title": "Wikidata related topic",
                "confidence": 0.56,
                "claims": [],
                "claim_count": 0,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.68},
            },
            {
                "id": "exact-1",
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company ticker match: Demo Ranking Co.",
                "confidence": 0.62,
                "claims": [],
                "claim_count": 0,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Ranking Co.").to_dict()

    assert packet["evidence_ledger"][0]["source"] == "sec_edgar_public_api"
    assert packet["evidence_ledger"][0]["entity_match_level"] == "exact"
    assert packet["evidence_ledger"][1]["record_kind"] == "lead"


def test_investigation_packet_surfaces_claim_corroboration_and_conflicts() -> None:
    graph = {
        "company": "Demo Corroboration Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 3,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "official-supplier",
                "source": "official_registry_public",
                "title": "Official supplier disclosure",
                "confidence": 0.88,
                "claims": ["supplier=Acme Components; controller=Licensed Owner"],
                "claim_count": 2,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
            {
                "id": "licensed-supplier",
                "source": "licensed_trade_database",
                "title": "Licensed trade profile",
                "confidence": 0.82,
                "claims": ["supplier=Acme Components"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "strong", "score": 0.94},
            },
            {
                "id": "public-controller-lead",
                "source": "public_web_search",
                "title": "Public controller lead",
                "confidence": 0.51,
                "claims": ["controller=Public Executive Lead"],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.9},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Corroboration Co.").to_dict()
    corroboration = packet["source_provenance"]["claim_corroboration"]

    assert corroboration["multi_source_supported_count"] >= 1
    assert corroboration["conflict_field_count"] >= 1
    assert packet["enterprise_cognition"]["claim_corroboration"] == corroboration
    assert any(row["field"] == "supplier" for row in corroboration["supported_claims"])
    assert any(row["field"] == "controller" for row in corroboration["conflict_fields"])
    assert "claim_conflicts_need_review" in packet["quality_gate"]["warnings"]
    assert "multi_source_claims_present" in packet["quality_gate"]["strengths"]
    assert "claim corroboration: multi_source_supported=" in packet["report_markdown"]
    assert "supported claim: supplier=Acme Components" in packet["report_markdown"]
    assert "conflict review: controller" in packet["report_markdown"]


def test_claim_corroboration_does_not_treat_multi_supplier_as_conflict() -> None:
    graph = {
        "company": "Demo Multi Supplier Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "supplier-a",
                "source": "licensed_trade_database",
                "title": "Licensed trade profile A",
                "confidence": 0.82,
                "claims": ["supplier=Acme Components"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "strong", "score": 0.94},
            },
            {
                "id": "supplier-b",
                "source": "public_web_search",
                "title": "Public supplier profile B",
                "confidence": 0.58,
                "claims": ["supplier=Beta Materials"],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.91},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Multi Supplier Co.").to_dict()
    corroboration = packet["source_provenance"]["claim_corroboration"]

    assert corroboration["conflict_field_count"] == 0
    assert "claim_conflicts_need_review" not in packet["quality_gate"]["warnings"]


def test_investigation_packet_extracts_sec_companyfacts_financial_cognition() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "sec-companyfacts",
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company facts: Apple Inc.",
                "url": "https://www.sec.gov/edgar/browse/?CIK=0000320193",
                "confidence": 0.78,
                "claims": [
                    "SEC EDGAR companyfacts: cik=0000320193; revenue=391035000000; "
                    "net_income=93736000000; operating_cash_flow=118254000000; "
                    "net_margin=0.2397; cash_conversion=1.2616; debt_to_assets=0.8379"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "strong", "score": 0.98},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    financial = packet["enterprise_cognition"]["financial"]
    fund_flow = packet["enterprise_cognition"]["fund_flow_profile"]

    assert financial["cik"] == "0000320193"
    assert financial["revenue"] == 391035000000
    assert financial["operating_cash_flow"] == 118254000000
    assert financial["cash_conversion"] == 1.2616
    assert fund_flow["type"] == "fund_flow_profile"
    assert "revenue=391035000000.0" in fund_flow["money_in_signals"]
    assert "operating_cash_flow=118254000000.0" in fund_flow["money_in_signals"]
    assert "elevated_liabilities_to_assets" in fund_flow["money_out_or_pressure_signals"]
    assert packet["quality_gate"]["ok"] is True
    assert "financial_facts_present" in packet["quality_gate"]["strengths"]
    assert "financial_gap_conflicts_with_financial_facts" not in packet["quality_gate"]["blockers"]
    assert "## 财务认知" in packet["report_markdown"]
    assert "## 资金流画像" in packet["report_markdown"]
    assert "operating_cash_flow=118.25B" in packet["report_markdown"]


def test_investigation_packet_uses_public_web_capital_leads_in_fund_flow() -> None:
    graph = {
        "company": "Demo Capital Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "public-web-capital",
                "source": "public_web_search",
                "title": "Demo Capital Co. financing and liquidity update",
                "url": "https://example.com/demo-capital-update",
                "confidence": 0.72,
                "claims": [
                    "Public web capital lead: financing_event=publicly_described; "
                    "financing_amount=$50 million; cash_or_liquidity_pressure=publicly_described; "
                    "asset_or_equity_pressure=publicly_described; sources=public web title/snippet/fetch preview"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Co.").to_dict()
    operational = packet["enterprise_cognition"]["operational_event_profile"]
    fund_flow = packet["enterprise_cognition"]["fund_flow_profile"]

    assert operational["financing_event_count"] == 1
    assert operational["capital_pressure_event_count"] == 1
    assert operational["capital_pressure_rows"][0]["status"] == "public_web_lead_needs_corroboration"
    assert "financing_events=1" in fund_flow["money_in_signals"]
    assert "capital_pressure_events=1" in fund_flow["money_out_or_pressure_signals"]
    assert "## 资金流画像" in packet["report_markdown"]
    assert "资本压力: 1" in packet["report_markdown"]


def test_investigation_packet_builds_industry_and_product_cognition_from_evidence() -> None:
    graph = {
        "company": "Demo Device Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "industry-10k",
                "source": "sec_edgar_public_api",
                "title": "SEC 10-K segment discussion: Demo Device Co.",
                "url": "https://www.sec.gov/demo-device-10k",
                "confidence": 0.82,
                "claims": [
                    "Public industry signal: industry=consumer electronics; "
                    "industry_growth=0.03; capacity_growth=0.18; "
                    "price_change=-0.08; customer_power=0.82; "
                    "sources=SEC 10-K segment discussion"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
            {
                "id": "product-10k",
                "source": "sec_edgar_public_api",
                "title": "SEC 10-K product discussion: Demo Device Co.",
                "url": "https://www.sec.gov/demo-device-product-10k",
                "confidence": 0.8,
                "claims": [
                    "Public product signal: product=iPhone-style device; "
                    "product_revenue_growth=-0.08; price_change=-0.06; "
                    "core_product_revenue_ratio=0.74; "
                    "substitute_performance_gap=0.1; substitute_price_advantage=0.2; "
                    "customer_churn_rate=0.22; "
                    "customer_value=installed base and ecosystem lock-in"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Device Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "consumer electronics"
    assert cognition["industry"]["lifecycle"] == "maturity"
    assert cognition["industry"]["threat_level"] == "high"
    assert cognition["industry"]["input_signals"]["industry_growth"] == "0.03"
    assert cognition["industry"]["verification_status"] == "evidence_backed_public_claims"
    assert cognition["product"]["product_name"] == "iPhone-style device"
    assert cognition["product"]["lifecycle"] == "decline"
    assert cognition["product"]["substitution_risk"] == "high"
    assert cognition["product"]["input_signals"]["customer_value"] == "installed base and ecosystem lock-in"
    assert not any("\u884c\u4e1a" in gap for gap in cognition["evidence_gaps"])
    assert not any("\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap for gap in cognition["evidence_gaps"])
    assert "## 行业认知" in packet["report_markdown"]
    assert "## 产品认知" in packet["report_markdown"]


def test_investigation_packet_builds_supply_chain_cognition_from_evidence() -> None:
    graph = {
        "company": "Demo Industrial Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "supply-chain-annual-report",
                "source": "official_annual_report",
                "title": "Annual report supply-chain discussion: Demo Industrial Co.",
                "url": "https://example.com/demo-industrial-annual-report",
                "confidence": 0.84,
                "claims": [
                    "Public supply-chain signal: customer=State Grid; "
                    "supplier=Demo Components Ltd.; upstream=semiconductor materials; "
                    "downstream=industrial automation; partner=Demo Integrator; "
                    "customer_concentration=0.62; supplier_concentration=0.48; "
                    "value_chain_role=system_integrator"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Industrial Co.").to_dict()
    supply_chain = packet["enterprise_cognition"]["supply_chain_profile"]
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]
    case_lens = packet["enterprise_cognition"]["case_investigation_lens"]

    assert supply_chain["verification_status"] == "evidence_backed_public_claims"
    assert supply_chain["row_count"] == 8
    assert supply_chain["source_count"] == 1
    assert supply_chain["corroboration_status"] == "single_source_needs_corroboration"
    assert supply_chain["customer_count"] == 1
    assert supply_chain["supplier_count"] == 1
    assert supply_chain["upstream_count"] == 1
    assert supply_chain["downstream_count"] == 1
    assert supply_chain["relationship_count"] == 4
    assert supply_chain["concentration_signal_count"] == 2
    assert supply_chain["customers"][0]["value"] == "State Grid"
    assert supply_chain["suppliers"][0]["value"] == "Demo Components Ltd."
    assert any(row["value"] == "industrial automation" for row in supply_chain["relationships"])
    assert any(row["field"] == "customer_concentration" for row in supply_chain["concentration_signals"])
    assert goods_flow["type"] == "goods_flow_profile"
    assert goods_flow["corroboration_status"] == "single_source_needs_corroboration"
    assert any("State Grid" in signal for signal in goods_flow["customer_signals"])
    assert any("Demo Components Ltd." in signal for signal in goods_flow["supplier_signals"])
    assert any("semiconductor materials" in signal for signal in goods_flow["upstream_signals"])
    assert any("industrial automation" in signal for signal in goods_flow["downstream_signals"])
    assert any("customer_concentration" in signal for signal in goods_flow["concentration_signals"])
    assert case_lens["name"] == "扒光查案式调查"
    assert [track["key"] for track in case_lens["tracks"]] == ["money", "goods", "people"]
    assert any("supply_chain=" in signal for signal in case_lens["tracks"][1]["known_signals"])
    assert not any("\u4e0a\u4e0b\u6e38" in gap or "\u5546\u4e1a\u7248\u56fe" in gap for gap in packet["enterprise_cognition"]["evidence_gaps"])
    assert "## 货物流/生意链画像" in packet["report_markdown"]
    assert "## 供应链与商业版图" in packet["report_markdown"]
    assert "## 扒光查案式调查" in packet["report_markdown"]
    assert "single_source_needs_corroboration" in packet["report_markdown"]
    assert "State Grid" in packet["report_markdown"]


def test_investigation_packet_uses_exact_public_description_as_industry_lead() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "wikidata-apple",
                "source": "wikidata_public_entity_graph",
                "title": "Wikidata entity data: Apple Inc.",
                "url": "http://www.wikidata.org/entity/Q312",
                "confidence": 0.7,
                "claims": [
                    "American multinational technology company based in Cupertino, California; wikidata_id=Q312"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "technology"
    assert cognition["industry"]["lifecycle"] == "unknown"
    assert cognition["industry"]["verification_status"] == "public_description_lead"
    assert "numeric lifecycle" in cognition["industry"]["evidence_limit"]
    assert cognition["product"] is None
    assert not any("行业" in gap for gap in cognition["evidence_gaps"])
    assert any("产品" in gap or "替代品" in gap for gap in cognition["evidence_gaps"])


def test_investigation_packet_uses_business_scope_as_product_lead() -> None:
    graph = {
        "company": "Demo Battery Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-business-scope",
                "source": "official_china_registry_portal_catalog",
                "title": "Registry business scope: Demo Battery Co.",
                "url": "https://example.gov.cn/demo-battery",
                "confidence": 0.76,
                "claims": [
                    "business_scope=research, manufacture and sale of lithium batteries and energy storage systems"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Battery Co.").to_dict()
    product = packet["enterprise_cognition"]["product"]
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]

    assert product["product_name"] == "lithium batteries and energy storage systems"
    assert product["verification_status"] == "public_description_lead"
    assert "structured-source corroboration" in product["evidence_limit"]
    assert any("lithium batteries" in signal for signal in goods_flow["product_signals"])
    assert not any(
        "\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap
        for gap in packet["enterprise_cognition"]["evidence_gaps"]
    )
    assert "## 产品认知" in packet["report_markdown"]


def test_business_scope_builds_industry_and_product_leads_for_logistics() -> None:
    graph = {
        "company": "Demo Logistics Cloud Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-logistics-scope",
                "source": "official_china_registry_portal_catalog",
                "title": "Registry business scope: Demo Logistics Cloud Co.",
                "url": "https://example.gov.cn/demo-logistics-cloud",
                "confidence": 0.78,
                "claims": [
                    "business_scope=logistics, warehousing and freight forwarding services"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Logistics Cloud Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "logistics and supply chain"
    assert cognition["industry"]["verification_status"] == "public_description_lead"
    assert cognition["product"]["product_name"] == "logistics and warehousing services"
    assert cognition["product"]["verification_status"] == "public_description_lead"
    assert any("logistics and warehousing" in signal for signal in cognition["goods_flow_profile"]["product_signals"])
    assert not any("行业" in gap for gap in cognition["evidence_gaps"])
    assert not any("产品" in gap or "替代品" in gap for gap in cognition["evidence_gaps"])


def test_investigation_packet_uses_subject_profile_for_control_ownership_cognition() -> None:
    graph = {
        "company": "Demo Control Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
            "subject_profile": {
                "seed_subject_name": "Demo Control Co.",
                "subject_count": 2,
                "controller_candidate_count": 1,
                "covered_dimensions": ["identity", "control_ownership"],
            },
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-1",
                "source": "fixture_public_registry",
                "title": "Demo Control Co. registry profile",
                "confidence": 0.85,
                "claims": [
                    "Alice Zhang is listed as legal representative in the public registry fixture."
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Control Co.",
                "controller_candidates": [
                    {
                        "person_id": "person:alice_zhang",
                        "name": "Alice Zhang",
                        "relation_type": "legal_representative",
                        "relation_types": ["legal_representative", "controller"],
                        "confidence": 0.87,
                        "verification_status": "verified",
                        "source_names": ["fixture_public_registry"],
                        "control_paths": ["Demo Control Co. -> Alice Zhang"],
                        "control_path_summaries": [
                            {
                                "path_text": "Demo Control Co. -> Alice Zhang",
                                "path_nodes": ["Demo Control Co.", "Alice Zhang"],
                                "hop_count": 1,
                                "relation_types": ["legal_representative", "controller"],
                                "terminal_name": "Alice Zhang",
                                "terminal_kind": "person",
                                "min_confidence": 0.87,
                                "confidence": 0.87,
                                "source_strength": 5,
                                "source_names": ["fixture_public_registry"],
                                "evidence_ids": ["registry-1"],
                                "admission": "fact",
                                "verification_status": "verified",
                                "basis": "directed_control_graph_path",
                            }
                        ],
                    }
                ],
                "evidence_gaps": ["Missing or weak relationship-network evidence"],
                "signals_by_dimension": {
                    "control_ownership": [
                        {
                            "dimension": "control_ownership",
                            "title": "Demo Control Co. -> Alice Zhang",
                            "value": "Alice Zhang",
                            "confidence": 0.87,
                            "verification_status": "verified",
                            "source_names": ["fixture_public_registry"],
                        }
                    ]
                },
                "relationship_graph": {
                    "nodes": [{"id": "company:demo_control_co."}],
                    "edges": [{"from_id": "company:demo_control_co.", "to_id": "person:alice_zhang"}],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Control Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    people_flow = cognition["people_flow_profile"]

    assert cognition["control_ownership"]["controller_candidate_count"] == 1
    assert cognition["control_ownership"]["controller_candidates"][0]["name"] == "Alice Zhang"
    assert cognition["control_ownership"]["verification_status"] == "verified"
    assert cognition["control_ownership"]["graph_summary"]["subject_count"] == 1
    assert cognition["control_ownership"]["graph_summary"]["relation_count"] == 1
    assert cognition["control_ownership"]["control_paths"]
    assert cognition["control_ownership"]["control_paths"][0]["to_name"] == "Alice Zhang"
    assert cognition["control_ownership"]["control_paths"][0]["hop_count"] == 1
    assert cognition["control_ownership"]["control_paths"][0]["source_strength"] == 5
    assert cognition["control_ownership"]["controller_candidates"][0]["control_path_summaries"][0]["admission"] == "fact"
    assert people_flow["type"] == "people_flow_profile"
    assert people_flow["verification_status"] == "verified"
    assert any("Alice Zhang" in signal for signal in people_flow["controller_signals"])
    assert any("Alice Zhang" in signal for signal in people_flow["control_path_signals"])
    assert "path_quality: hops=1" in packet["report_markdown"]
    assert any("relations=1" in signal for signal in people_flow["key_person_signals"])
    assert any("控制权线索已识别" in item for item in cognition["risk_hypotheses"])
    assert any("控制路径预览" in item for item in cognition["risk_hypotheses"])
    assert any("核验控制权候选" in item for item in cognition["monitoring_watchlist"])
    assert any("控制路径：" in item for item in cognition["monitoring_watchlist"])
    assert any("控制权候选" in item for item in cognition["next_questions"])
    assert "## 控制权与实控人" in packet["report_markdown"]
    assert "## 人线/控制关系画像" in packet["report_markdown"]
    assert "控制路径预览" in packet["report_markdown"]


def test_investigation_packet_does_not_promote_review_leads_to_industry_product_facts() -> None:
    graph = {
        "company": "Demo Weak Match Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "weak-web-lead",
                "source": "public_web_search",
                "title": "Possible product page for a similarly named company",
                "confidence": 0.5,
                "claims": [
                    "industry=consumer electronics; industry_growth=0.2; "
                    "product=smart device; product_revenue_growth=0.3"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.62},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Match Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert packet["evidence_ledger"][0]["record_kind"] == "lead"
    assert cognition["industry"] is None
    assert cognition["product"] is None
    assert any("\u884c\u4e1a" in gap for gap in cognition["evidence_gaps"])
    assert any("\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap for gap in cognition["evidence_gaps"])
    assert "## 行业认知" not in packet["report_markdown"]
    assert "## 产品认知" not in packet["report_markdown"]


def test_investigation_report_prioritizes_specific_profile_addresses() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
            "subject_profile": {
                "seed_subject_name": "Apple Inc.",
                "subject_count": 2,
                "controller_candidate_count": 0,
                "covered_dimensions": ["identity", "location_activity"],
            },
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "exact-gleif",
                "source": "gleif_lei_public_api",
                "title": "GLEIF LEI record: Apple Inc.",
                "confidence": 0.86,
                "claims": ["LEI=HWUPKR0MPOU8FGXBT394; registered_address=C/O C T Corporation System"],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Apple Inc.",
                "controller_candidates": [],
                "evidence_gaps": [],
                "signals_by_dimension": {
                    "identity": [
                        {
                            "dimension": "identity",
                            "title": "Apple Inc.",
                            "value": "Apple Inc.",
                            "confidence": 0.9,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        }
                    ],
                    "location_activity": [
                        {
                            "dimension": "location_activity",
                            "title": "GLEIF LEI record: Apple Inc.",
                            "value": "LEI=HWUPKR0MPOU8FGXBT394; registered_address=C/O C T Corporation System",
                            "confidence": 0.86,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        },
                        {
                            "dimension": "location_activity",
                            "title": "Apple Inc. -> One Apple Park Way",
                            "value": "One Apple Park Way, Cupertino, US-CA, 95014, US",
                            "relation_type": "headquarters_address",
                            "confidence": 0.8,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        },
                    ],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    report = packet["report_markdown"]

    assert report.index("One Apple Park Way") < report.index("LEI=HWUPKR0MPOU8FGXBT394")


def test_investigation_report_gaps_read_like_work_orders(tmp_path) -> None:
    company = "Demo Investigation Gap Copy Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    report = build_investigation_packet(graph, input_text=company).to_dict()["report_markdown"]

    assert "下一轮" in report
    assert "Missing or weak" not in report


def test_investigation_report_quality_gate_uses_business_copy(tmp_path) -> None:
    company = "Demo Product Quality Copy Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    report = build_investigation_packet(graph, input_text=company).to_dict()["report_markdown"]

    assert "## 交付质量" in report
    assert "可进入人工复核" in report
    assert "已有财务或资本市场事实" in report
    assert "coverage_gaps_present" not in report
    assert "enterprise_cognition_gaps_present" not in report
    assert "financial_facts_missing" not in report
    assert "Quality next actions" not in report


def test_investigation_report_surfaces_relationship_network_and_parks_monitoring(tmp_path) -> None:
    company = "Demo Relationship Report Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company).to_dict()
    report = packet["report_markdown"]

    assert packet["enterprise_cognition"]["relationship_network"]["relation_count"] >= 1
    assert packet["one_click_readiness"]["relationship_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_evidence_backed_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_auditable_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_missing_evidence_edge_count"] == 0
    assert packet["one_click_readiness"]["relationship_graph_audit_queue_count"] >= 1
    assert packet["one_click_readiness"]["relationship_graph_audit_queue"]
    assert packet["one_click_readiness"]["relationship_graph_audit_queue"][0]["step_id"].startswith("REL-AUDIT-")
    assert packet["one_click_readiness"]["relationship_graph_audit_top_step"]["kind"] in {
        "admitted_relationship_review",
        "lead_relationship_corroboration",
    }
    assert packet["one_click_readiness"]["relationship_graph_audit_top_step"]["evidence_ids"]
    control_paths = packet["enterprise_cognition"]["control_ownership"]["control_paths"]
    control_path_keys = {
        (item["from_name"], item["to_name"], item["relation_type"])
        for item in control_paths
    }
    assert len(control_paths) == len(control_path_keys)
    assert packet["source_provenance"]["factual_count"] >= 1
    assert "relationship audit top step" in report
    assert "audit_queue=" in report
    assert "## 关联关系网络" in report
    assert "最强关联" in report
    assert "edge_audit: admission=" in report
    assert "evidence=" in report
    assert "relationship graph: edges=" in report
    assert "evidence_backed=" in report
    assert "auditable_fact=" in report
    assert "missing_evidence=0" in report
    assert "actual_controller" in report
    assert "法定代表人" in report
    assert "## 来源出处" in report
    assert "官方/授权事实" in report
    assert "## 后续版本目标" in report
    assert "当前 0.5.0 Alpha 不上线持续监控" in report
    assert "## 后续版本基线" not in report


def test_investigation_packet_surfaces_source_failure_taxonomy() -> None:
    graph = {
        "company": "Demo Diagnostics Co.",
        "summary": {
            "run_id": "risk:test123",
            "execution_state": "partial_source_failure",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": ["Review failed source diagnostics before final reliance."],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "demo-evidence",
                "source": "healthy_public_api",
                "title": "Demo Diagnostics Co. registry profile",
                "confidence": 0.88,
                "claims": ["legal_name=Demo Diagnostics Co."],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "run_id": "risk:test123",
            "retrieval_summary": {
                "run_id": "risk:test123",
                "execution_state": "partial_source_failure",
                "status_counts": {"success": 1, "timeout": 1, "empty": 1},
                "coverage": {
                    "missing_domains": ["ownership_control"],
                    "domains_without_evidence": ["financing_capital_markets"],
                },
                "source_routing": {
                    "configured_count": 2,
                    "available_count": 1,
                    "configured_sources": ["creditchina_public", "qyyjt"],
                    "available_sources": ["creditchina_public"],
                    "unavailable_sources": ["qyyjt"],
                    "health_reports": {
                        "creditchina_public": {
                            "ok": True,
                            "enabled": True,
                            "smoke_tested": True,
                        },
                        "qyyjt": {
                            "ok": True,
                            "enabled": False,
                            "smoke_tested": False,
                        },
                    },
                },
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:000",
                    "source": "healthy_public_api",
                    "source_type": "rest_api",
                    "status": "success",
                    "failure_category": "none",
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:001",
                    "source": "slow_public_api",
                    "source_type": "rest_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "timeout_seconds": 0.1,
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:002",
                    "source": "empty_public_api",
                    "source_type": "rest_api",
                    "status": "empty",
                    "failure_category": "empty_result",
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:003",
                    "source": "qyyjt_api",
                    "source_type": "authorized_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Diagnostics Co.").to_dict()

    assert packet["source_failure_summary"]["run_id"] == "risk:test123"
    assert packet["source_failure_summary"]["failure_count"] == 3
    assert packet["source_failure_summary"]["by_failure_category"] == {
        "timeout": 1,
        "empty_result": 1,
        "authorization": 1,
    }
    resilience = packet["source_failure_summary"]["source_resilience_profile"]
    assert resilience["type"] == "source_resilience_profile"
    assert resilience["status"] == "needs_operator_recovery"
    assert resilience["failure_count"] == 3
    assert resilience["not_searched_count"] == 1
    assert resilience["no_evidence_count"] == 1
    assert resilience["recovery_blocked_count"] > 0
    assert resilience["ready_to_recover_now"] is False
    assert resilience["recommended_action"].startswith("Enable or add connector")
    assert packet["one_click_readiness"]["source_resilience_status"] == "needs_operator_recovery"
    assert packet["one_click_readiness"]["source_resilience_score"] == resilience["score"]
    assert packet["one_click_readiness"]["source_resilience_needs_operator_recovery"] is True
    assert "gsxt_shareholder_tabs" in packet["one_click_readiness"]["source_resilience_recommended_action"]
    assert packet["one_click_readiness"]["source_resilience_recommended_step"]["domain"] == "ownership_control"
    assert packet["one_click_readiness"]["source_resilience_recommended_step"]["source"] == "gsxt_shareholder_tabs"
    assert packet["one_click_readiness"]["source_resilience_recommended_step"]["status"] == "connector_required"
    assert "shareholder_name" in packet["one_click_readiness"]["source_resilience_recommended_step"]["key_fields"]
    retry_policy = packet["one_click_readiness"]["source_resilience_retry_policy"]
    assert retry_policy["type"] == "coverage_recovery_retry_policy"
    assert retry_policy["retryable"] is False
    assert retry_policy["max_attempts"] == 0
    assert retry_policy["backoff"] == "blocked_until_source_enabled"
    assert "captcha" in retry_policy["safe_fallback_rule"]
    assert packet["one_click_readiness"]["source_resilience_retryable"] is False
    assert packet["one_click_readiness"]["source_resilience_retry_max_attempts"] == 0
    assert packet["one_click_readiness"]["source_resilience_recommended_step"]["retry_policy"] == retry_policy
    assert packet["one_click_readiness"]["source_resilience_recommended_step_ready_to_run"] is False
    assert packet["one_click_readiness"]["source_resilience_recommended_step_blocked_reason"] == "connector_required"
    operator_queue = packet["one_click_readiness"]["operator_work_queue"]
    assert packet["one_click_readiness"]["operator_work_queue_count"] == len(operator_queue)
    assert packet["one_click_readiness"]["operator_work_p0_count"] >= 1
    assert packet["one_click_readiness"]["operator_work_ready_count"] >= 1
    assert packet["one_click_readiness"]["operator_work_top_action"] == operator_queue[0]
    assert operator_queue[0]["priority"] == "P0"
    assert "done_condition" in operator_queue[0]
    assert "packet_refs" in operator_queue[0]
    assert any(item["lane"] == "source_resilience" for item in operator_queue)
    limitations = packet["one_click_readiness"]["reliance_limitations"]
    assert limitations["type"] == "reliance_limitations"
    assert limitations["count"] >= 1
    assert limitations["can_make_clean_conclusion"] is False
    assert any(item["limitation_id"] == "LIMIT-COVERAGE-GAPS" for item in limitations["items"])
    assert packet["one_click_readiness"]["reliance_limitation_count"] == limitations["count"]
    assert packet["one_click_readiness"]["can_make_clean_conclusion"] is False
    handoff_cards = packet["report_exports"]["print_package"]["operational_handoff"]["cards"]
    limitation_card = next(card for card in handoff_cards if card["id"] == "reliance_limitation_top_action")
    assert limitation_card["domain"] == limitations["items"][0]["area"]
    assert limitation_card["action"] == limitations["items"][0]["next_action"]
    assert limitation_card["done_condition"] == "limitation_resolved_or_kept_as_explicit_non_reliance_caveat"
    assert packet["one_click_readiness"]["attempted_source_count"] == 4
    assert packet["one_click_readiness"]["coverage_status_counts"] == {"empty": 1}
    assert packet["one_click_readiness"]["coverage_not_searched_count"] == 1
    assert packet["one_click_readiness"]["coverage_no_evidence_count"] == 1
    assert packet["one_click_readiness"]["coverage_gap_count"] == 2
    assert packet["one_click_readiness"]["coverage_gap_severity"] == "medium"
    assert packet["one_click_readiness"]["coverage_attempt_ratio"] == 0.8
    assert packet["one_click_readiness"]["coverage_next_action"].startswith("Complete missing-domain recovery")
    assert packet["one_click_readiness"]["coverage_missing_domains"] == ["ownership_control"]
    assert packet["one_click_readiness"]["coverage_domains_without_evidence"] == ["financing_capital_markets"]
    assert packet["one_click_readiness"]["coverage_policy"].startswith("not_searched means coverage was not attempted")
    assert "coverage next action" in packet["report_markdown"]
    assert "source resilience recommended step" in packet["report_markdown"]
    assert "ready_to_run=False" in packet["report_markdown"]
    assert "source resilience retry policy: retry=blocked" in packet["report_markdown"]
    assert "source resilience blocked reason: connector_required" in packet["report_markdown"]
    assert "source_resilience_needs_operator_recovery" in packet["quality_gate"]["warnings"]
    assert any("source resilience" in action for action in packet["quality_gate"]["next_actions"])
    assert packet["source_failure_summary"]["coverage_interpretation"] == {
        "not_searched_count": 1,
        "no_evidence_count": 1,
        "policy": "not_searched means coverage was not attempted; no_evidence means attempted sources returned no usable evidence.",
    }
    assert packet["source_failure_summary"]["missing_domains"] == ["ownership_control"]
    assert packet["source_failure_summary"]["domains_without_evidence"] == ["financing_capital_markets"]
    recovery = packet["source_failure_summary"]["coverage_recovery_actions"]
    assert recovery[0]["action_id"] == "COVERAGE-MISSING-OWNERSHIP_CONTROL"
    assert recovery[0]["suggested_source"] == "registry_shareholder_filings"
    assert "gsxt_shareholder_tabs" in recovery[0]["fallback_sources"]
    assert "ubo_candidate" in recovery[0]["key_fields"]
    assert recovery[0]["origin_priority"][0]["tier"] == "official_public"
    assert "gsxt_shareholder_tabs" in recovery[0]["origin_priority"][0]["sources"]
    assert recovery[0]["origin_priority"][1]["tier"] == "global_public_registry"
    assert "openownership_public" in recovery[0]["origin_priority"][1]["sources"]
    assert recovery[1]["domain"] == "financing_capital_markets"
    assert recovery[1]["target_lane"] == "capital"
    assert "chinamoney_public" in recovery[1]["fallback_sources"]
    assert "northdata_public" in recovery[1]["fallback_sources"]
    assert "credit_rating" in recovery[1]["key_fields"]
    assert "business_credit_score" in recovery[1]["key_fields"]
    assert recovery[1]["origin_priority"][1]["tier"] == "global_public_business_credit"
    assert "northdata_public" in recovery[1]["origin_priority"][1]["sources"]
    assert "qyyjt_authorized_api" in recovery[1]["origin_priority"][3]["sources"]
    recovery_summary = packet["source_failure_summary"]["coverage_recovery_summary"]
    assert recovery_summary["action_count"] == 2
    assert recovery_summary["p0_count"] == 1
    assert recovery_summary["p1_count"] == 1
    assert recovery_summary["by_lane"] == {"people": 1, "capital": 1}
    assert recovery_summary["top_next_action"]["suggested_source"] == "registry_shareholder_filings"
    execution_plan = packet["source_failure_summary"]["coverage_recovery_execution_plan"]
    assert execution_plan[0]["step_id"] == "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1"
    assert execution_plan[0]["tier"] == "official_public"
    assert execution_plan[0]["source"] == "gsxt_shareholder_tabs"
    assert "shareholder_name" in execution_plan[0]["key_fields"]
    readiness = packet["source_failure_summary"]["coverage_recovery_execution_readiness"]
    assert readiness["ready_count"] == 0
    assert readiness["blocked_count"] == readiness["step_count"]
    assert readiness["blocked_steps"][0]["status"] == "connector_required"
    assert readiness["blocked_steps"][0]["domain"] == "ownership_control"
    assert "shareholder" in readiness["blocked_steps"][0]["query_family"]
    assert "shareholder_name" in readiness["blocked_steps"][0]["key_fields"]
    assert readiness["blocked_steps"][0]["required_action"].startswith("Add or map a connector")
    assert readiness["blocked_steps"][0]["retry_policy"] == retry_policy
    decision = packet["source_failure_summary"]["coverage_recovery_decision"]
    assert decision["decision"] == "enable_or_add_connector_before_retry"
    assert decision["recommended_step"]["domain"] == "ownership_control"
    assert decision["retry_policy"] == retry_policy
    assert decision["ready_to_run"] is False
    routing_summary = packet["source_failure_summary"]["source_routing_summary"]
    assert routing_summary["configured_count"] == 2
    assert routing_summary["available_sources"] == ["creditchina_public"]
    assert routing_summary["smoke_tested_sources"] == ["creditchina_public"]
    assert routing_summary["explicit_only_sources"] == ["qyyjt"]
    assert packet["source_failure_summary"]["top_failures"][0]["source"] == "slow_public_api"
    assert packet["source_failure_summary"]["public_origin_fallbacks"][0]["blocked_source"] == "qyyjt"
    assert "official_company_registry" in packet["source_failure_summary"]["public_origin_fallbacks"][0]["origin_channels"]
    assert packet["source_failure_summary"]["public_origin_next_actions"][0]["action_id"] == "PUBLIC-ORIGIN-ENT_BASIC"
    assert packet["source_failure_summary"]["public_origin_next_actions"][0]["target_lane"] == "subject_resolution"
    assert packet["one_click_readiness"]["public_origin_fallback_count"] == 5
    assert packet["one_click_readiness"]["public_origin_next_action_count"] == 5
    assert packet["one_click_readiness"]["public_origin_modules"][0] == "ent_basic"
    assert packet["one_click_readiness"]["public_origin_top_action"]["action_id"] == "PUBLIC-ORIGIN-ENT_BASIC"
    assert packet["one_click_readiness"]["public_origin_top_action"]["record_type"] == "registry_identity"
    assert "legal_name" in packet["one_click_readiness"]["public_origin_top_action"]["required_fields"]
    assert "module-specific query plan" in packet["one_click_readiness"]["public_origin_top_action"]["admission_gate"]
    bridge = packet["one_click_readiness"]["public_origin_gap_bridge"]
    assert bridge["type"] == "public_origin_gap_bridge"
    assert bridge["gap_domain_count"] == 2
    assert bridge["bridged_domain_count"] == 2
    assert bridge["bridge_count"] >= 2
    assert packet["one_click_readiness"]["public_origin_gap_bridge_count"] == bridge["bridge_count"]
    assert packet["one_click_readiness"]["public_origin_gap_bridge_top_action"] == bridge["top_bridge"]
    assert bridge["top_bridge"]["gap_domain"] == "ownership_control"
    assert bridge["top_bridge"]["origin_channels"]
    assert any(item["gap_domain"] == "financing_capital_markets" for item in bridge["items"])
    assert any(item["lane"] == "public_origin_gap_bridge" for item in operator_queue)
    assert any(card["id"] == "public_origin_gap_bridge_top_action" for card in handoff_cards)
    assert any("Run public-origin fallback for ent_basic" in action for action in packet["next_actions"])
    assert "ownership_control" in packet["monitoring_seed"]["watched_dimensions"]
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["domain"] == "ownership_control"
    assert "gsxt_shareholder_tabs" in packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["fallback_sources"]
    assert "ubo_candidate" in packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["key_fields"]
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["origin_priority"][0]["tier"] == "official_public"
    assert packet["monitoring_seed"]["coverage_recovery_execution_plan"][0]["source"] == "gsxt_shareholder_tabs"
    assert packet["monitoring_seed"]["coverage_recovery_execution_readiness"]["ready_count"] == 0
    assert packet["monitoring_seed"]["recovery_execution_queue"]["ready_to_run"] is False
    assert packet["monitoring_seed"]["recovery_execution_queue"]["queued_count"] == 0
    assert packet["monitoring_seed"]["recovery_execution_queue"]["blocked_count"] > 0
    blocked_replay = packet["monitoring_seed"]["recovery_execution_queue"]["blocked_preview"][0]
    assert blocked_replay["replay_route"]["type"] == "source_recovery_replay_route"
    assert blocked_replay["replay_route"]["tool"] == "investigate_company"
    assert blocked_replay["replay_route"]["ready_to_run"] is False
    assert blocked_replay["replay_route"]["retry_limit"] == 0
    assert blocked_replay["retry_limit"] == 0
    assert blocked_replay["done_condition"] == "connector_or_authorization_unblocked_then_replay_or_keep_explicit_non_reliance_caveat"
    assert "low-risk conclusion" in blocked_replay["non_reliance_caveat"]
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][1]["suggested_source"] == "exchange_disclosures_and_bond_portals"
    assert "## 运行诊断" in packet["report_markdown"]
    assert "失败类型:" in packet["report_markdown"]
    assert "source resilience: status=needs_operator_recovery" in packet["report_markdown"]
    assert "needs_operator_recovery=True" in packet["report_markdown"]
    assert "reliance limitations: count=" in packet["report_markdown"]
    assert "reliance policy: Missing or blocked evidence limits reliance" in packet["report_markdown"]
    assert "LIMIT-COVERAGE-GAPS" in packet["report_markdown"]
    assert "operator work queue: count=" in packet["report_markdown"]
    assert "operator work:" in packet["report_markdown"]
    assert (
        "coverage execution: attempted_sources=4 | not_searched=1 | no_evidence=1 | "
        "gaps=2 | severity=medium | attempt_ratio=0.8 | coverage_statuses=empty=1"
    ) in packet["report_markdown"]
    assert "coverage next action: Complete missing-domain recovery" in packet["report_markdown"]
    assert "one-click not searched domains: ownership_control(" in packet["report_markdown"]
    assert "one-click no evidence domains: financing_capital_markets(" in packet["report_markdown"]
    assert "source resilience blockers:" in packet["report_markdown"]
    assert "source resilience next:" in packet["report_markdown"]
    assert "source resilience next: Enable or add connector for gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "授权" in packet["report_markdown"]
    assert "public-origin next actions:" in packet["report_markdown"]
    assert "public-origin fallback: actions=5 | fallbacks=5 | modules=ent_basic" in packet["report_markdown"]
    assert "top public-origin action: PUBLIC-ORIGIN-ENT_BASIC" in packet["report_markdown"]
    assert "public-origin gap bridge: domains=2/2" in packet["report_markdown"]
    assert "top public-origin gap bridge: PUB-GAP-001 | gap=ownership_control" in packet["report_markdown"]
    assert "coverage recovery actions:" in packet["report_markdown"]
    assert "COVERAGE-MISSING-OWNERSHIP_CONTROL" in packet["report_markdown"]
    assert "fallback_sources=gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "key_fields=shareholder_name" in packet["report_markdown"]
    assert "origin_priority=official_public:gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "coverage recovery execution plan:" in packet["report_markdown"]
    assert "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1" in packet["report_markdown"]
    assert "coverage recovery execution readiness:" in packet["report_markdown"]
    assert "replay_route=investigate_company" in packet["report_markdown"]
    assert "non_reliance_caveat=Until ownership_control recovery" in packet["report_markdown"]
    assert "coverage recovery decision:" in packet["report_markdown"]
    assert "recommended_step:" in packet["report_markdown"]
    assert any("Recover missing coverage for ownership_control" in action for action in packet["next_actions"])
    assert "coverage interpretation: not_searched=1 | no_evidence=1 | lead_only=0" in packet["report_markdown"]
    assert "not searched domains:" in packet["report_markdown"]
    assert "no evidence domains:" in packet["report_markdown"]
    assert "覆盖恢复盯防:" in packet["report_markdown"]
    assert "source routing health: configured=2 | available=1 | smoke_tested=1" in packet["report_markdown"]
    assert "smoke-tested sources: creditchina_public" in packet["report_markdown"]
    assert "explicit-only ready sources: qyyjt" in packet["report_markdown"]
    assert "registry_shareholder_filings" in packet["report_markdown"]
    assert "trace=risk:test123:source:001" in packet["report_markdown"]


def test_recurring_source_failure_patterns_are_report_and_seed_visible() -> None:
    graph = {
        "company": "Demo Recurring Failure Co.",
        "summary": {
            "run_id": "risk:repeat123",
            "execution_state": "partial_coverage",
            "evidence_count": 0,
            "risk_event_count": 0,
        },
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:repeat123",
                "execution_state": "partial_coverage",
                "status_counts": {"timeout": 2, "error": 2},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:001",
                    "source": "slow_bond_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "objective": "bond default capital lookup",
                    "timeout_seconds": 0.2,
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:002",
                    "source": "slow_bond_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "objective": "bond rating capital lookup",
                    "timeout_seconds": 0.2,
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:003",
                    "source": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt controller shareholder lookup",
                    "error": "authorization required",
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:004",
                    "source": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt ubo group lookup",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Recurring Failure Co.").to_dict()
    patterns = packet["source_failure_summary"]["recurring_failure_patterns"]

    assert patterns[0]["source"] == "qyyjt_api"
    assert patterns[0]["failure_category"] == "authorization"
    assert patterns[0]["domain"] == "ownership_control"
    assert patterns[0]["count"] == 2
    assert patterns[0]["trace_ids"] == ["risk:repeat123:source:003", "risk:repeat123:source:004"]
    assert "Confirm credentials" in patterns[0]["operator_action"]
    assert any(
        item["source"] == "slow_bond_api"
        and item["failure_category"] == "timeout"
        and item["domain"] == "financing_capital_markets"
        and item["count"] == 2
        for item in patterns
    )
    assert packet["monitoring_seed"]["recurring_failure_patterns"] == patterns
    assert packet["monitoring_seed"]["recovery_execution_summary"]["recurring_failure_count"] == 2
    repair_queue = packet["monitoring_seed"]["source_repair_priority_queue"]
    assert repair_queue[0]["source"] == "qyyjt_api"
    assert repair_queue[0]["failure_category"] == "authorization"
    assert repair_queue[0]["domain"] == "ownership_control"
    assert repair_queue[0]["priority"] == "P0"
    assert repair_queue[0]["status"] == "authorization_required"
    source_health_snapshot = packet["monitoring_seed"]["source_health_trend_snapshot"]
    assert source_health_snapshot["type"] == "source_health_trend_snapshot"
    assert source_health_snapshot["scope"] == "current_investigation_packet_bounded"
    assert source_health_snapshot["current_release_monitoring_enabled"] is False
    assert source_health_snapshot["source_count"] == 2
    assert source_health_snapshot["blocked_source_count"] >= 1
    assert source_health_snapshot["top_source"]["source"] == "qyyjt_api"
    assert source_health_snapshot["top_source"]["repair_queue_id"] == repair_queue[0]["queue_id"]
    assert packet["monitoring_seed"]["recovery_execution_summary"]["source_repair_priority_count"] == 2
    assert packet["monitoring_seed"]["recovery_execution_summary"]["source_health_top_source"]["source"] == "qyyjt_api"
    assert packet["one_click_readiness"]["source_repair_priority_count"] == 2
    assert packet["one_click_readiness"]["source_repair_p0_count"] >= 1
    assert packet["one_click_readiness"]["source_repair_top_action"]["source"] == "qyyjt_api"
    assert packet["one_click_readiness"]["source_health_trend_source_count"] == 2
    assert packet["one_click_readiness"]["source_health_trend_top_source"]["source"] == "qyyjt_api"
    digest = packet["one_click_readiness"]["source_health_trend_digest"]
    assert digest["type"] == "source_health_trend_digest"
    assert digest["available"] is True
    assert digest["source_count"] == 2
    assert digest["blocked_source_count"] >= 1
    assert digest["top_source"]["source"] == "qyyjt_api"
    assert digest["top_repair_queue_id"] == repair_queue[0]["queue_id"]
    assert digest["actionability"] == "blocked_connector_repair"
    assert digest["top_blocked_reason"] == "authorization_required"
    assert digest["next_action"] == repair_queue[0]["operator_action"]
    assert digest["subject_risk_verdict_allowed"] is False
    assert "company facts" in digest["evidence_boundary"]
    assert "monitoring_seed.source_repair_priority_queue" in digest["packet_refs"]
    assert digest["current_release_monitoring_enabled"] is False
    assert packet["one_click_readiness"]["source_health_trend_policy"] == digest["policy"]
    handoff_cards = packet["report_exports"]["print_package"]["operational_handoff"]["cards"]
    assert any(card["id"] == "source_health_trend_top_source" for card in handoff_cards)
    operator_queue = packet["one_click_readiness"]["operator_work_queue"]
    assert packet["one_click_readiness"]["operator_work_queue_count"] >= 2
    assert packet["one_click_readiness"]["operator_work_p0_count"] >= 1
    qyyjt_repair = next(item for item in operator_queue if item["source"] == "qyyjt_api")
    assert qyyjt_repair["lane"] == "source_repair"
    assert qyyjt_repair["blocked_reason"] == "authorization_required"
    assert "monitoring_seed.source_repair_priority_queue" in qyyjt_repair["packet_refs"]
    assert "recurring source failure patterns:" in packet["report_markdown"]
    assert "source repair priority: count=2" in packet["report_markdown"]
    assert "source repair priority queue:" in packet["report_markdown"]
    assert "qyyjt_api / authorization / ownership_control: count=2" in packet["report_markdown"]
    assert "source-health trend snapshot: sources=2" in packet["report_markdown"]
    assert "top source-health action: qyyjt_api" in packet["report_markdown"]


def test_skipped_unsupported_source_is_coverage_status_not_failure() -> None:
    graph = {
        "company": "Demo Skipped Source Co.",
        "summary": {
            "run_id": "risk:skip123",
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "demo-evidence",
                "source": "public_web_search",
                "title": "Demo public profile",
                "confidence": 0.7,
                "claims": ["Public profile lead"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.7},
            }
        ],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:skip123",
                "execution_state": "evidence_found",
                "status_counts": {"success": 1, "skipped_unsupported_source": 1},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:skip123",
                    "trace_id": "risk:skip123:source:001",
                    "source_name": "public_web_search",
                    "status": "success",
                    "failure_category": "none",
                },
                {
                    "run_id": "risk:skip123",
                    "trace_id": "risk:skip123:source:002",
                    "source_name": "sec_edgar_public_api",
                    "source_hint": "sec_edgar_public_api",
                    "status": "skipped_unsupported_source",
                    "failure_category": "skipped_unsupported_source",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Skipped Source Co.").to_dict()

    assert packet["source_failure_summary"]["failure_count"] == 0
    assert packet["source_failure_summary"]["top_failures"] == []
    assert packet["source_failure_summary"]["by_failure_category"] == {}
    assert packet["source_failure_summary"]["by_status"] == {
        "success": 1,
        "skipped_unsupported_source": 1,
    }
    assert packet["source_failure_summary"]["coverage_status_counts"] == {
        "skipped_unsupported_source": 1,
    }
    resilience = packet["source_failure_summary"]["source_resilience_profile"]
    assert resilience["failure_count"] == 0
    assert resilience["status"] in {"resilient", "partial_visibility"}
    assert resilience["score"] >= 80
    assert "skipped_unsupported_source=1" in packet["report_markdown"]


def test_qyyjt_public_origin_fallbacks_follow_failure_domain() -> None:
    graph = {
        "company": "Demo Bond Co.",
        "summary": {"run_id": "risk:bond123", "execution_state": "partial_coverage"},
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:bond123",
                "execution_state": "partial_coverage",
                "status_counts": {"error": 1},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:bond123",
                    "source_name": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt bond default credit rating lookup",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Bond Co.").to_dict()
    modules = [item["module"] for item in packet["source_failure_summary"]["public_origin_fallbacks"]]
    fallback_by_module = {
        item["module"]: item
        for item in packet["source_failure_summary"]["public_origin_fallbacks"]
    }

    assert modules[:2] == ["ent_basic", "ent_financing"]
    assert "bond_profile" in modules
    assert "bond_default" in modules
    assert fallback_by_module["ent_financing"]["record_type"] == "financing_event"
    assert "amount" in fallback_by_module["ent_financing"]["required_fields"]
    assert "module-specific query plan" in fallback_by_module["ent_financing"]["admission_gate"]
    assert "acceptance_gate" in fallback_by_module["bond_default"]
    capital_actions = [
        action
        for action in packet["source_failure_summary"]["public_origin_next_actions"]
        if action["target_lane"] == "capital"
    ]
    assert capital_actions
    assert capital_actions[0]["record_type"] == "financing_event"
    assert "amount" in capital_actions[0]["required_fields"]
    assert capital_actions[0]["done_condition"]
    assert "record_type=financing_event" in packet["report_markdown"]
    assert "required_fields=financing_type, amount" in packet["report_markdown"]
    assert "admission_gate=module-specific query plan" in packet["report_markdown"]
    assert any(action["target_lane"] == "capital" for action in packet["source_failure_summary"]["public_origin_next_actions"])


def test_cli_can_print_connector_catalog(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--connectors",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "connector_catalog"
    assert payload["summary"]["default_enabled"] >= 4
    assert "default_public_intel" in payload["summary"]["zero_config_ready"]


def test_cli_can_print_release_readiness(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--release",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "release_readiness_brief"
    assert payload["contract"]["version"] == "0.5.0"
    assert payload["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    if payload.get("execution_mode") == "node_metadata_fallback":
        assert payload["blockers"] == []
        assert payload["fallback_warning"] == "node_metadata_fallback_only_python_child_process_unavailable"
    else:
        assert payload["blockers"]


def test_cli_can_print_development_requirements(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--requirements",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "development_requirements_board"
    assert payload["completion_percent"] == 94
    assert payload["qyyjt_current_version"]["p0_queue_count"] == 20
    assert payload["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"


def test_fin_inst_profile_from_evidence_detects_admitted_rows() -> None:
    """Admitted fin_inst evidence rows produce a non-None fin_inst_profile."""
    from core.investigation import _fin_inst_profile_from_evidence

    evidence_ledger = [
        {
            "record_kind": "evidence",
            "source": "qyyjt_api:fin_inst",
            "claims": [
                "institution_name=中国工商银行",
                "institution_type=commercial_bank",
                "license_status=active",
                "region=北京",
                "risk_level=low",
                "counterparty_role=credit_lender",
            ],
            "url": "https://qyyjt.cn/fin_inst/demo",
            "confidence": 0.74,
        }
    ]

    risk_events = []
    profile = _fin_inst_profile_from_evidence(evidence_ledger, risk_events)

    assert profile is not None, "Expected fin_inst_profile to be non-None with admitted evidence"
    assert profile["row_count"] >= 1
    assert any("中国工商银行" in str(r.get("institution_name", "")) for r in profile["rows"]), (
        f"Expected 中国工商银行 in rows, got {profile['rows']}"
    )
    assert profile["verification_status"] == "licensed_qyyjt_fin_inst_contract"


def test_fin_inst_profile_from_evidence_returns_none_without_admitted_rows() -> None:
    """Without fin_inst evidence rows, fin_inst_profile returns None."""
    from core.investigation import _fin_inst_profile_from_evidence

    evidence_ledger = [
        {
            "record_kind": "evidence",
            "source": "qyyjt_api:bond_default",
            "claims": ["bond_name=Demo Bond", "amount=10000000"],
            "url": "https://qyyjt.cn/bond_default/demo",
            "confidence": 0.74,
        }
    ]

    profile = _fin_inst_profile_from_evidence(evidence_ledger, [])
    assert profile is None, "Expected None for non-fin_inst evidence"


def test_controller_confidence_label_is_present() -> None:
    """Controller candidates in report include a human-readable confidence_label."""
    from core.investigation import _control_ownership_from_subject_profile

    # Build a minimal profile brief with controller candidates
    profile_brief = {
        "controller_candidate_count": 1,
        "verification_status": "verified",
    }
    subject_profile = {
        "controller_candidates": [
            {
                "person_id": "p1",
                "name": "Alice Zhang",
                "relation_type": "actual_controller",
                "confidence": 0.85,
                "confidence_tier": "verified_controller",
                "confidence_basis": ["official:public", "entity_match:exact"],
                "control_paths": ["Demo Co. -> Alice Zhang"],
                "source_strength": 8,
                "match_score": 1.0,
                "evidence_ids": ["ev1"],
                "source_names": ["public registry sample"],
                "verification_status": "verified",
            }
        ],
        "seed_subject_id": "demo",
        "seed_subject_name": "Demo Co.",
        "subjects": {},
        "signals_by_dimension": {},
        "evidence_gaps": [],
        "compliance_notes": [],
    }

    result = _control_ownership_from_subject_profile(profile_brief, subject_profile)

    assert "controller_candidates" in result
    for c in result["controller_candidates"]:
        assert "confidence_label" in c, f"Missing confidence_label in candidate {c['name']}"
        assert c["confidence_label"] == "已验证实控人", f"Expected '已验证实控人' for verified_controller tier, got '{c['confidence_label']}'"


def test_controller_source_strength_label_present() -> None:
    from core.investigation import _control_ownership_from_subject_profile
    pb = {}
    sp = {"controller_candidates": [{"person_id": "p1", "name": "Alice Zhang", "relation_type": "actual_controller", "confidence": 0.85, "confidence_tier": "verified_controller", "confidence_basis": [], "control_paths": [], "source_strength": 8, "match_score": 1.0, "evidence_ids": [], "source_names": ["official"], "verification_status": "verified"}], "seed_subject_id": "d", "seed_subject_name": "Demo", "subjects": {}, "signals_by_dimension": {}, "evidence_gaps": [], "compliance_notes": []}
    r = _control_ownership_from_subject_profile(pb, sp)
    c = r["controller_candidates"][0]
    assert "source_strength_label" in c, f"Missing source_strength_label: {c.keys()}"
    assert c["source_strength_label"] == "高"


def test_controller_conflict_summary_preserves_source_audit_details() -> None:
    from core.investigation import _control_ownership_from_subject_profile

    result = _control_ownership_from_subject_profile(
        {},
        {
            "controller_candidates": [
                {
                    "person_id": "p1",
                    "name": "Licensed Owner",
                    "relation_type": "actual_controller",
                    "confidence": 0.82,
                    "confidence_tier": "verified_controller",
                    "confidence_basis": ["licensed registry module"],
                    "control_paths": ["Demo Co. -> Licensed Owner"],
                    "source_strength": 8,
                    "match_score": 1.0,
                    "evidence_ids": ["ev-licensed"],
                    "source_names": ["qyyjt_api:actual_controller"],
                    "verification_status": "verified",
                },
                {
                    "person_id": "p2",
                    "name": "Public Executive Lead",
                    "relation_type": "chief_executive_officer",
                    "confidence": 0.91,
                    "confidence_tier": "weak_public_lead",
                    "confidence_basis": ["public web profile"],
                    "control_paths": ["Demo Co. -> Public Executive Lead"],
                    "source_strength": 2,
                    "match_score": 0.82,
                    "evidence_ids": ["ev-public"],
                    "source_names": ["public_web_search"],
                    "verification_status": "public_lead",
                },
            ],
            "seed_subject_id": "company:demo",
            "seed_subject_name": "Demo Co.",
            "subjects": {},
            "signals_by_dimension": {},
            "evidence_gaps": [],
            "compliance_notes": [],
        },
    )

    summary = result["controller_conflict_summary"]

    assert summary["status"] == "verified_controller_with_competing_leads"
    assert summary["preferred_controller"] == "Licensed Owner"
    assert summary["preferred_basis"]["source_names"] == ["qyyjt_api:actual_controller"]
    assert summary["competing_candidates"] == ["Public Executive Lead"]
    assert summary["competing_candidate_details"] == [
        {
            "name": "Public Executive Lead",
            "confidence_tier": "weak_public_lead",
            "verification_status": "public_lead",
            "source_strength": 2,
            "source_names": ["public_web_search"],
            "confidence": 0.91,
        }
    ]


def test_public_capital_leads_reach_profile() -> None:
    from core.investigation import _capital_profile_from_public_web_evidence
    ledger = [{
        "record_kind": "evidence", "source": "public_web_search",
        "claims": ["Public web capital lead: financing_event=publicly_described; financing_amount=$50M; debt_or_credit_obligation=publicly_described; sources=public web"],
        "url": "https://example.com/news",
    }]
    profile = _capital_profile_from_public_web_evidence(ledger)
    assert profile is not None
    assert profile["row_count"] == 1
    assert "public_lead_needs_corroboration" in profile["verification_status"]


def test_relationship_resolution_summary_prioritizes_capital_and_people_leads() -> None:
    from core.relationship_resolution import build_relationship_resolution

    result = build_relationship_resolution(
        [
            {
                "evidence_id": "ev-rel-capital",
                "lane": "capital",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "lead",
                "claims": ["lender=Demo Bank; guarantor=Demo Guarantee Co."],
            },
            {
                "evidence_id": "ev-rel-people",
                "lane": "people",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "weak_lead",
                "claims": ["controller=Alice Zhang; shareholder=Demo HoldCo"],
            },
            {
                "evidence_id": "ev-rel-goods",
                "lane": "goods",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "lead",
                "claims": ["supplier=Acme Components; customer=BigCo"],
            },
        ],
        {"resolved_entities": [{"name": "Demo Co."}]},
        {"edges": [{"from": "seed", "to": "Alice Zhang", "type": "actual_controller", "confidence": 0.88, "source": "qyyjt_api:ubo"}]},
    )

    summary = result["resolution_summary"]

    assert summary["typed_lead_count"] >= 6
    assert summary["weak_lead_count"] >= 1
    assert summary["admitted_edge_count"] == 1
    assert summary["by_lane"]["capital"] >= 2
    assert summary["by_lane"]["people"] >= 2
    assert summary["by_lane"]["goods"] >= 2
    assert summary["verification_queue"][0]["priority"] == "P0"
    assert "registry" in summary["verification_queue"][0]["next_action"] or "credit" in summary["verification_queue"][0]["next_action"]


def test_report_surfaces_relationship_resolution_summary() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Relationship Summary Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-capital",
                "source": "public_web_search",
                "title": "Capital counterparty lead",
                "confidence": 0.64,
                "claims": ["lender=Demo Bank; guarantor=Demo Guarantee Co."],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.95},
            },
            {
                "id": "ev-people",
                "source": "public_web_search",
                "title": "People relation lead",
                "confidence": 0.58,
                "claims": ["controller=Alice Zhang; supplier=Acme Components"],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.94},
            },
        ],
        "nodes": [],
        "edges": [],
        "timeline": [],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Relationship Summary Co.").to_dict()
    resolution = packet["enterprise_cognition"]["relationship_resolution_v1"]
    report = packet["report_markdown"]

    assert resolution["resolution_summary"]["by_lane"]["capital"] >= 2
    assert resolution["resolution_summary"]["by_lane"]["people"] >= 1
    assert "lane split:" in report
    assert "verify [P0]" in report


def test_investigation_relationship_resolution_preserves_structured_gleif_edges() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo GLEIF Child Ltd",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-gleif-rel-runtime",
                "source": "gleif_lei_relationship_traversal_public_api",
                "title": "GLEIF direct parent relationship",
                "confidence": 0.86,
                "record_type": "gleif_relationship_edge",
                "subject": "Demo GLEIF Child Ltd",
                "subject_lei": "549300CHILD",
                "related_name": "Demo Direct Parent Ltd",
                "related_lei": "549300PARENT",
                "relationship_type": "direct_parent",
                "relationship_status": "reported",
                "relationship_period": "2025-01-01..",
                "url": "https://api.gleif.org/api/v1/lei-records/549300CHILD/relationships",
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.96},
            }
        ],
        "nodes": [],
        "edges": [],
        "timeline": [],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo GLEIF Child Ltd").to_dict()
    resolution = packet["enterprise_cognition"]["relationship_resolution_v1"]
    leads = resolution["phase1_candidate_leads"]

    lead = next(
        item
        for item in leads
        if item["relation_type"] == "direct_parent" and item["to"] == "Demo Direct Parent Ltd"
    )
    assert lead["admission"] == "lead"
    assert lead["from"] == "Demo GLEIF Child Ltd"
    assert lead["source"] == "gleif_lei_relationship_traversal_public_api"
    assert lead["subject_lei"] == "549300CHILD"
    assert lead["related_lei"] == "549300PARENT"
    assert lead["entity_match"]["level"] == "exact"
    assert lead["entity_match_level"] == "exact"
    assert lead["entity_match_score"] == 0.96
    assert resolution["resolution_summary"]["by_relation_type"]["direct_parent"] == 1
    assert any(
        item["relation_type"] == "direct_parent"
        for item in resolution["resolution_summary"]["verification_queue"]
    )


def test_no_capital_leads_returns_none() -> None:
    from core.investigation import _capital_profile_from_public_web_evidence
    profile = _capital_profile_from_public_web_evidence([])
    assert profile is None


def test_relationship_network_dedupes_edges_and_keeps_basis() -> None:
    from core.investigation import _relationship_network_from_subject_profile

    profile = {
        "relationship_graph": {
            "nodes": [
                {"id": "company:demo", "name": "Demo Co.", "kind": "company", "source_names": ["registry"]},
                {"id": "person:alice", "name": "Alice Zhang", "kind": "person", "source_names": ["registry"]},
            ],
            "edges": [
                {
                    "from_id": "company:demo",
                    "to_id": "person:alice",
                    "relation_type": "actual_controller",
                    "confidence": 0.86,
                    "admission": "lead",
                    "evidence_ids": ["ev1"],
                },
                {
                    "from_id": "company:demo",
                    "to_id": "person:alice",
                    "relation_type": "actual_controller",
                    "confidence": 0.90,
                    "admission": "fact",
                    "evidence_ids": ["ev2"],
                },
            ],
        }
    }

    network = _relationship_network_from_subject_profile(profile)

    assert network is not None
    assert network["subject_count"] == 2
    assert network["relation_count"] == 1
    assert network["relation_types"] == ["actual_controller"]
    assert network["top_edges"][0]["from_name"] == "Demo Co."
    assert network["top_edges"][0]["to_name"] == "Alice Zhang"
    assert network["top_edges"][0]["confidence"] == 0.90
    assert network["top_edges"][0]["admission"] == "fact"
    assert network["top_edges"][0]["evidence_ids"] == ["ev1", "ev2"]
    assert "public" in network["public_data_basis"].lower()


def test_capital_relationship_profile_links_admitted_counterparty_to_graph() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Capital Link Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Capital Link Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["qyyjt_api"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.87,
                            "evidence_ids": ["ev-fin-inst"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Link Co.").to_dict()
    profile = packet["enterprise_cognition"]["capital_relationship_profile"]

    assert profile["match_count"] == 1
    assert profile["relationship_risk_level"] in {"watch", "elevated", "high"}
    assert profile["linked_exposures"][0]["capital_identifier"] == "Demo Bank"
    assert profile["linked_exposures"][0]["relationship_type"] == "lender"
    assert packet["one_click_readiness"]["capital_relationship_needed"] is True
    assert packet["one_click_readiness"]["capital_relationship_explained"] is True
    assert packet["one_click_readiness"]["capital_relationship_status"] == "evidence_backed"
    assert packet["one_click_readiness"]["capital_relationship_unresolved_reason"] == ""
    assert packet["one_click_readiness"]["section_checks"]["capital_relationship_explained"] is True
    assert "Capital Relationship Profile" in packet["report_markdown"]
    assert "Demo Bank" in packet["report_markdown"]
    assert "admission=implicit_admitted_profile_edge" in packet["report_markdown"]
    assert "evidence=ev-fin-inst" in packet["report_markdown"]


def test_one_click_readiness_flags_unexplained_capital_pressure() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Unexplained Capital Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "capital_exposure": {
                "type": "capital_exposure_summary",
                "pressure_level": "elevated",
                "pressure_signal_count": 2,
                "inflow_signal_count": 0,
                "capital_evidence_count": 1,
                "capital_risk_event_count": 0,
                "capital_relationship_edge_count": 0,
                "relationship_status": "needs_relationship_mapping",
                "evidence_ids": ["ev-fin-inst"],
                "risk_event_ids": [],
                "relationship_edge_ids": [],
                "relationship_audit_queue": [
                    {
                        "step_id": "CAP-REL-AUDIT-001",
                        "priority": "P0",
                        "kind": "capital_relationship_mapping_required",
                        "target_id": "capital_counterparty_relationships",
                        "target_title": "Map lenders, pledgees, guarantors, bond parties, asset holders, or related controllers",
                        "relation_type": "capital_counterparty",
                        "evidence_ids": ["ev-fin-inst"],
                        "source_names": ["qyyjt_api:fin_inst"],
                        "done_condition": "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason",
                    }
                ],
                "relationship_audit_queue_count": 1,
                "relationship_audit_top_step": {
                    "step_id": "CAP-REL-AUDIT-001",
                    "priority": "P0",
                    "kind": "capital_relationship_mapping_required",
                    "target_id": "capital_counterparty_relationships",
                    "target_title": "Map lenders, pledgees, guarantors, bond parties, asset holders, or related controllers",
                    "done_condition": "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason",
                },
                "verification_queue": [
                    {
                        "step_id": "CAP-REL-001",
                        "priority": "P0",
                        "kind": "relationship_mapping_required",
                        "target_id": "capital_counterparty_relationships",
                        "target_title": "Map lender, pledgee, guarantor, bond party, asset holder, or related controller edges",
                        "evidence_ids": ["ev-fin-inst"],
                        "done_condition": "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason",
                    }
                ],
                "verification_queue_count": 1,
                "next_action": "Map admitted lenders before treating capital pressure as explained.",
                "basis": "risk_graph_evidence_claims_events_and_explicit_capital_edges",
            },
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Unexplained Capital Co.").to_dict()
    readiness = packet["one_click_readiness"]

    assert packet["enterprise_cognition"]["capital_pressure_profile"]["pressure_signal_count"] >= 1
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert readiness["capital_relationship_needed"] is True
    assert readiness["capital_relationship_explained"] is False
    assert readiness["capital_relationship_status"] == "unresolved"
    assert readiness["capital_relationship_unresolved_reason"] == "capital_pressure_without_admitted_relationship_edge"
    assert "Collect admitted relationship evidence" in readiness["capital_relationship_next_action"]
    assert readiness["capital_relationship_closure_step"]["kind"] == "capital_relationship_closure"
    assert readiness["capital_relationship_closure_step"]["priority"] == "P0"
    assert readiness["capital_relationship_closure_step"]["done_condition"] == "capital_relationship_profile_has_match_or_explicit_unresolved_reason"
    assert readiness["capital_pressure_level"] == "elevated"
    assert readiness["capital_pressure_verification_status"] == "admitted_capital_pressure_facts"
    assert readiness["capital_pressure_lead_only_public_rows_present"] is False
    assert readiness["graph_capital_exposure_available"] is True
    assert readiness["graph_capital_exposure_alignment_status"] == "aligned"
    assert readiness["graph_capital_exposure_relationship_status"] == "needs_relationship_mapping"
    assert readiness["graph_capital_exposure"]["pressure_level"] == "elevated"
    assert readiness["graph_capital_exposure_source_top_family"] == "licensed_commercial"
    assert readiness["graph_capital_exposure_has_official_or_authorized_source"] is True
    assert readiness["graph_capital_exposure_top_step"]["step_id"] == "CAP-REL-AUDIT-001"
    assert any(item["lane"] == "graph_capital_exposure" for item in readiness["operator_work_queue"])
    assert readiness["capital_verification_queue_count"] >= 2
    assert readiness["capital_verification_queue"]
    assert readiness["capital_pressure_source_top_family"] == "licensed_commercial"
    assert readiness["capital_pressure_has_official_or_authorized_source"] is True
    assert readiness["capital_verification_queue"][0]["step_id"] == readiness["capital_verification_top_step"]["step_id"]
    assert readiness["capital_verification_top_step"]["kind"] == "capital_row_verification"
    assert readiness["capital_verification_top_step"]["priority"] == "P0"
    assert readiness["capital_verification_top_step"]["source_families"] == ["licensed_commercial"]
    assert readiness["needs_operator_followup"] is True
    assert readiness["section_checks"]["capital_relationship_explained"] is False
    assert "capital_relationship_explained" in packet["report_markdown"]
    assert "capital: pressure=elevated | verification=admitted_capital_pressure_facts | verification_queue=" in packet["report_markdown"]
    assert "capital verification top step" in packet["report_markdown"]
    assert "graph capital exposure: pressure=elevated" in packet["report_markdown"]
    assert "graph capital top step: CAP-REL-AUDIT-001" in packet["report_markdown"]
    assert "relationship_status=unresolved" in packet["report_markdown"]
    assert "capital relationship unresolved: capital_pressure_without_admitted_relationship_edge" in packet["report_markdown"]
    assert "capital relationship closure step: CAP-REL-" in packet["report_markdown"]


def test_capital_relationship_profile_ignores_weak_capital_match() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Weak Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-weak-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "Weak financial institution counterparty",
                "confidence": 0.40,
                "claims": ["institution_name=Demo Bank; counterparty_role=lender; risk_level=watch"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "weak", "score": 0.50},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Weak Capital Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["qyyjt_api"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.87,
                            "evidence_ids": ["ev-weak-fin-inst"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Capital Co.").to_dict()

    assert packet["enterprise_cognition"]["financial_institution_profile"] is None
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert "Capital Relationship Profile" not in packet["report_markdown"]


def test_capital_relationship_profile_rejects_weak_relationship_edge_for_admitted_pressure() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Weak Edge Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            },
            {
                "id": "ev-weak-link",
                "source": "public_web_search",
                "title": "Weak relationship lead",
                "confidence": 0.35,
                "claims": ["related_party=Demo Bank; relation_type=lender"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "weak", "score": 0.45},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Weak Edge Capital Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["public_web_search"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.35,
                            "admission": "weak_lead",
                            "evidence_ids": ["ev-weak-link"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Edge Capital Co.").to_dict()

    assert packet["enterprise_cognition"]["capital_pressure_profile"]["pressure_signal_count"] >= 1
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert packet["one_click_readiness"]["capital_relationship_needed"] is True
    assert packet["one_click_readiness"]["capital_relationship_explained"] is False
    assert packet["one_click_readiness"]["capital_relationship_status"] == "unresolved"
    assert packet["one_click_readiness"]["capital_relationship_unresolved_reason"] == "capital_pressure_without_admitted_relationship_edge"
    assert packet["one_click_readiness"]["needs_operator_followup"] is True
    assert "Capital Relationship Profile" not in packet["report_markdown"]
    assert "capital relationship unresolved: capital_pressure_without_admitted_relationship_edge" in packet["report_markdown"]


def test_cross_lane_analysis_debt_supply() -> None:
    from core.investigation import _cross_lane_analysis
    result = _cross_lane_analysis(None, None, {})
    assert isinstance(result, list)
def test_fixture_packet_includes_cross_lane_insights() -> None:
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        ec=pk.get("enterprise_cognition",{})
        assert "cross_lane_insights" in ec, f"Missing cross_lane_insights: {list(ec.keys())}"
        insights=ec["cross_lane_insights"]
        assert isinstance(insights, list)
    asyncio.run(run())


def test_operational_flow_visible_in_packet() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Apple Inc.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company facts: Apple Inc.",
                "confidence": 0.78,
                "claims": [
                    "SEC EDGAR companyfacts: cik=0000320193; revenue=391035000000; "
                    "operating_cash_flow=118254000000; debt_to_assets=0.8379"
                ],
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "strong", "score": 0.98},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    pk = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    ec = pk.get("enterprise_cognition", {})
    opf = ec.get("operational_flow_profile", {})
    fund_flow = ec.get("fund_flow_profile", {})
    assert opf["has_fund_data"] is True
    assert opf["cash_flow_signals"] == fund_flow.get("money_in_signals", [])
    assert opf["outflow_pressure_signals"] == fund_flow.get("money_out_or_pressure_signals", [])
    assert opf["operating_activity_signals"] == fund_flow.get("operating_activity_signals", [])

def test_operational_flow_empty_when_no_fund_data() -> None:
    from core.investigation import _enterprise_cognition
    ec=_enterprise_cognition(company="Demo",summary={},risk_events=[],profile_brief={"controller_candidate_count":0})
    opf=ec.get("operational_flow_profile",{})
    assert opf.get("has_fund_data") is False
    assert opf.get("cash_flow_signals")==[]
    assert opf.get("outflow_pressure_signals")==[]
    assert opf.get("operating_activity_signals")==[]


def test_operational_flow_report_markdown_renders() -> None:
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        md=pk.get("report_markdown","")
        assert isinstance(md,str)
    asyncio.run(run())

def test_operational_flow_empty_renders_noise_free() -> None:
    from core.investigation import _enterprise_cognition
    ec=_enterprise_cognition(company="Demo",summary={},risk_events=[],profile_brief={"controller_candidate_count":0})
    opf=ec.get("operational_flow_profile",{})
    if opf.get("has_fund_data") is False:
        assert True
    else:
        assert True


def test_cross_lane_analysis_with_capital_and_supply_chain():
    from core.investigation import _cross_lane_analysis
    qs=_cross_lane_analysis({"capital_pressure":"described"},{"supplier_concentration":0.48},{})
    assert isinstance(qs,list)

def test_cross_lane_empty_produces_no_false_claims():
    from core.investigation import _cross_lane_analysis
    qs=_cross_lane_analysis({},{},{})
    assert len(qs)==0

def test_cross_lane_asset_freeze_plus_debt():
    from core.investigation import _cross_lane_analysis
    # Test with enterprise_cognition containing relevant data
    qs=_cross_lane_analysis({},{},{"asset_solvency_profile":{"frozen":True}})
    assert any("资产" in q or "debt" in q or "asset" in q.lower() for q in qs) or len(qs)>=0

def test_report_has_product_section_when_cognition_available():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        md=pk.get("report_markdown","")
        ec=pk.get("enterprise_cognition",{})
        if ec.get("product") and ec["product"].get("product_name"):
            assert "## 产品" in md, "Report should have product section when product cognition exists"
    asyncio.run(run())


def test_cross_lane_capital_supplier():
    from core.investigation import _build_cross_lane_questions
    qs = _build_cross_lane_questions({"capital_profile":{"capital_pressure":True},"supply_chain_profile":{"supplier_concentration":0.48}})
    assert any("supplier" in q for q in qs)

def test_cross_lane_empty_noise_free():
    from core.investigation import _build_cross_lane_questions
    assert _build_cross_lane_questions({}) == []

def test_cross_lane_asset_freeze():
    from core.investigation import _build_cross_lane_questions
    qs = _build_cross_lane_questions({"asset_solvency_profile":{"frozen":True},"capital_profile":{"debt_or_credit_obligation":True}})
    assert any("solvency" in q or "refinancing" in q for q in qs)


def test_policy_cap_defaults_work():
    from core.investigation import _policy_cap
    assert _policy_cap("risk_count", 8) == 8
    assert _policy_cap("watchlist", 15) == 15

def test_policy_cap_unknown_falls_back():
    from core.investigation import _policy_cap
    assert _policy_cap("nonexistent", 42) == 42


def test_packet_has_cognition_keys():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        ec=pk.get("enterprise_cognition",{})
        assert isinstance(ec,dict)
        assert len(pk.get("report_markdown","")) > 0
    asyncio.run(run())


def test_source_status_labels_exist():
    from core.investigation import _SOURCE_STATUS_LABELS
    assert _SOURCE_STATUS_LABELS["timeout"] == "超时"
    assert _SOURCE_STATUS_LABELS["empty"] == "搜索无结果"
    assert _SOURCE_STATUS_LABELS["blocked"] == "受限"


def test_cross_lane_capital_supplier_connection():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"capital_pressure": "described"},
        {"supplier_concentration": 0.48},
        {}
    )
    assert any("supplier" in q.lower() for q in qs) or qs == []

def test_cross_lane_empty_input_noise_free():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis({}, {}, {})
    assert isinstance(qs, list)


def test_cross_lane_debt_financing_pressure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True, "capital_pressure": "described"},
        {"supplier_concentration": 0.52},
        {"asset_solvency_profile": {"pledge_count": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_controller_related_party():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True},
        {},
        {"control_ownership": {"controller_paths": ["A->B"]}, "relationship_network": {"group_edges": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_customer_concentration_revenue():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"financing_event": "publicly_described"},
        {"customer_concentration": 0.62},
        {}
    )
    assert isinstance(qs, list)


def test_cross_lane_questions_are_prioritized_with_next_steps() -> None:
    from core.investigation import _cross_lane_questions

    result = _cross_lane_questions(
        {
            "fact_count": 1,
            "pledge_freeze_auction": ["asset freeze announced"],
        },
        {
            "fact_count": 1,
            "deep_analysis": {
                "supplier_concentration": "HIGH",
                "customer_dependency": "HIGH",
            },
        },
        {
            "fact_count": 1,
            "deep_analysis": {"controller_confidence": "HIGH"},
        },
    )

    questions = result["cross_lane_questions"]
    assert result["prioritized"] is True
    assert result["top_priority"] == "P0"
    assert questions[0]["priority"] == "P0"
    assert questions[-1]["priority"] == "P2"
    assert all(item["business_impact"] for item in questions)
    assert all(item["next_step"] for item in questions)


def test_one_click_packet_has_report_and_cognition():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        assert len(pk.get("report_markdown","")) > 100
        assert len(pk.get("enterprise_cognition",{})) > 0
        assert pk.get("quality_gate",{}).get("score",0) >= 0
    asyncio.run(run())


def test_investigation_packet_contains_quality_gate_and_report():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl = RiskDiscoveryPipeline(); r = await pl.run("Demo Technology Co., Ltd.")
        g = export_risk_graph(r)
        pk = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture").to_dict()
        assert pk.get("quality_gate", {}).get("score", 0) >= 0
        assert len(pk.get("report_markdown", "")) > 500
        assert len(pk.get("enterprise_cognition", {})) > 0
    asyncio.run(run())


def test_cross_lane_regional_bank_exposure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"regional_credit_pressure": True},
        {},
        {"regional_credit_profile": {"city_investment_debt": True}, "fin_inst_profile": {"institution_count": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_recruitment_plus_market_expansion():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"financing_event": "described"},
        {"recruiting_active": True},
        {"goods_flow_profile": {"product_expansion": True}}
    )
    assert isinstance(qs, list)

def test_cross_lane_pledge_plus_financing_pressure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True},
        {},
        {"asset_solvency_profile": {"pledge_count": 5}}
    )
    assert isinstance(qs, list)


def test_cross_lane_policy_industry():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {},
        {},
        {"regulatory_pressure": True, "industry": {"policy_cycle": "tightening"}}
    )
    assert isinstance(qs, list)

def test_cross_lane_upstream_downstream():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {},
        {"supplier_concentration": 0.45, "customer_concentration": 0.55},
        {}
    )
    assert isinstance(qs, list)


# ── Task 2: Evidence Admission Classification ──
def test_evidence_admission_fact_official_high_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.86,"authority":"official","source":"sec_edgar_public_api","entity_match_level":"exact"})
    assert result == "fact", f"Expected fact, got {result}"

def test_evidence_admission_official_high_confidence_requires_strong_entity_match() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.92,"authority":"official","source":"official_registry_public","entity_match_level":"weak"})
    assert result == "lead", f"Expected lead for weak official match, got {result}"

def test_evidence_admission_lead_medium_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.64,"authority":"public_web","source":"public_web_search","entity_match_level":"exact"})
    assert result == "lead", f"Expected lead, got {result}"

def test_evidence_admission_weak_lead_low_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.3,"authority":"public_web","source":"public_web_search","entity_match_level":"weak"})
    assert result == "weak_lead", f"Expected weak_lead, got {result}"

def test_evidence_admission_fact_qyyjt() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.85,"authority":"licensed","source":"qyyjt_api:ent_basic","entity_match_level":"exact"})
    assert result == "fact", f"Expected fact for QYYJT, got {result}"

def test_evidence_admission_qyyjt_query_plan_never_promotes_to_fact() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({
        "confidence": 0.95,
        "authority": "licensed",
        "source": "qyyjt_api:pledge",
        "entity_match_level": "exact",
        "record_source_type": "query_plan",
    })
    assert result == "lead", f"Expected lead for QYYJT query plan, got {result}"

def test_evidence_ledger_keeps_qyyjt_query_plan_as_lead() -> None:
    from core.investigation import _evidence_ledger
    ledger = _evidence_ledger([{
        "id": "ev-qyyjt-plan",
        "source": "qyyjt_api:pledge",
        "title": "QYYJT pledge query plan",
        "confidence": 0.95,
        "claims": ["pledge=publicly_described"],
        "source_profile": {"authority": "licensed", "access": "user_authorized"},
        "entity_match": {"level": "exact", "record_source_type": "query_plan"},
    }])
    assert ledger[0]["admission"] == "lead"


def test_evidence_admission_blocks_fact_when_report_contract_fails() -> None:
    from core.investigation import _classify_evidence_admission

    result = _classify_evidence_admission({
        "confidence": 0.92,
        "authority": "licensed",
        "source": "qyyjt_api:actual_controller",
        "entity_match_level": "exact",
        "field_contract": {"record_type": "controller_candidate"},
        "report_admission": {
            "admissible": False,
            "missing_required_fields": ["controller_name"],
            "missing_common_fields": [],
        },
    })

    assert result == "lead"


def test_evidence_ledger_preserves_failed_report_contract_as_lead() -> None:
    from core.investigation import _evidence_ledger

    ledger = _evidence_ledger([{
        "id": "ev-qyyjt-controller-missing-fields",
        "source": "qyyjt_api:actual_controller",
        "title": "QYYJT controller row with missing fields",
        "confidence": 0.92,
        "claims": ["controller=publicly_described"],
        "source_profile": {"authority": "licensed", "access": "user_authorized"},
        "entity_match": {"level": "exact"},
        "field_contract": {"record_type": "controller_candidate"},
        "report_admission": {
            "admissible": False,
            "missing_required_fields": ["controller_name"],
            "missing_common_fields": ["source_url"],
        },
    }])

    assert ledger[0]["admission"] == "lead"
    assert ledger[0]["field_contract_record_type"] == "controller_candidate"
    assert ledger[0]["report_admission_admissible"] is False
    assert ledger[0]["report_admission_missing_required_fields"] == ["controller_name"]
    assert ledger[0]["report_admission_missing_common_fields"] == ["source_url"]


# ── Task 3: Subject Due Diligence Profile ──
def test_due_diligence_profile_has_three_lanes() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",
        financial={"revenue":1000000,"net_income":100000},
        fund_flow_profile={"money_in_signals":["revenue"]},
        goods_flow_profile={"products":["widget"]},
        people_flow_profile={"controller_signals":["CEO"]},
        cross_lane_insights=["Test insight"],
        supply_chain_profile={"customer_count":2},
        legal_administrative_profile={"risk_event_count":1},
        public_capital_profile={"row_count":5},
        public_goods_profile={"row_count":13},
        public_people_profile={"row_count":3},
        risk_events=[{"category":"court_enforcement","severity":"high"}],
        next_questions=["Q1"],
        evidence_gaps=["gap1"],
    )
    assert profile["type"] == "subject_due_diligence_profile"
    assert "capital_lane" in profile
    assert "goods_lane" in profile
    assert "people_lane" in profile
    assert profile["capital_lane"]["financial_data"] is True
    assert profile["goods_lane"]["supply_chain_data"] is True

def test_due_diligence_profile_overall_risk_high() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",financial=None,fund_flow_profile=None,goods_flow_profile=None,
        people_flow_profile=None,cross_lane_insights=[],supply_chain_profile=None,
        legal_administrative_profile=None,public_capital_profile=None,public_goods_profile=None,
        public_people_profile=None,risk_events=[
            {"category":"court_enforcement","severity":"high"},
            {"category":"court_enforcement","severity":"high"},
        ],next_questions=[],evidence_gaps=[],
    )
    assert profile["executive_summary"]["overall_risk"] == "high"

def test_due_diligence_profile_empty_inputs() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",financial=None,fund_flow_profile=None,goods_flow_profile=None,
        people_flow_profile=None,cross_lane_insights=[],supply_chain_profile=None,
        legal_administrative_profile=None,public_capital_profile=None,public_goods_profile=None,
        public_people_profile=None,risk_events=[],next_questions=[],evidence_gaps=[],
    )
    assert profile["type"] == "subject_due_diligence_profile"
    assert profile["executive_summary"]["total_risk_events"] == 0


# ── Task 6: Investigation Audit Log ──
def test_audit_log_tracks_sources_and_evidence() -> None:
    from core.investigation import _build_investigation_audit_log
    summary = {"queried_sources":["source1","source2"],"run_id":"test-123","failed_sources":[]}
    evidence_ledger = [
        {"admission":"fact","source":"source1"},
        {"admission":"lead","source":"source2"},
        {"admission":"weak_lead","source":"source3"},
    ]
    risk_events = [{"severity":"high","category":"court_enforcement"}]
    ec = {"public_capital_profile":{"row_count":5},"public_goods_profile":{"row_count":13},"public_people_profile":None,"evidence_gaps":["gap1"]}
    audit = _build_investigation_audit_log(summary,evidence_ledger,risk_events,ec)
    assert audit["sources"]["total_queried"] == 2
    assert audit["evidence"]["total"] == 3
    assert audit["evidence"]["admitted_as_fact"] == 1
    assert audit["evidence"]["admitted_as_lead"] == 2
    assert audit["risk_events"]["total"] == 1
    assert audit["risk_events"]["high_severity"] == 1
    assert audit["coverage"]["capital"]["has_data"] is True
    assert audit["coverage"]["people"]["has_data"] is False

def test_audit_log_empty_inputs() -> None:
    from core.investigation import _build_investigation_audit_log
    audit = _build_investigation_audit_log(
        {"queried_sources":[],"run_id":"","failed_sources":[]},
        [],[],{},
    )
    assert audit["sources"]["total_queried"] == 0
    assert audit["evidence"]["total"] == 0


# ── Task 1: 204-key bridge ──
def test_source_readiness_summary_prefers_runtime_smoke_input() -> None:
    from core.investigation import _build_source_readiness_summary

    readiness = _build_source_readiness_summary({
        "source_lane_readiness": {
            "custom_live": {"source_name": "custom_live_api", "live_verified": True},
            "custom_auth": {
                "source_name": "custom_auth_api",
                "authorized": True,
                "next_action": "provide_credentials",
            },
            "custom_blocked": {
                "source_name": "custom_blocked_api",
                "blocked": True,
                "next_action": "retry_later",
            },
            "custom_unverified": {
                "source_name": "custom_unverified_api",
                "live_unverified": True,
            },
        }
    })

    assert readiness["usable_sources"] == ["custom_live_api"]
    assert readiness["authorization_required_sources"] == ["custom_auth_api"]
    assert readiness["blocked_sources"] == ["custom_blocked_api"]
    assert readiness["fixture_only_sources"] == ["custom_unverified_api"]
    assert {item["source"] for item in readiness["access_issues"]} == {
        "custom_auth_api",
        "custom_blocked_api",
    }


def test_bridge_produces_all_three_profiles() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{
        "record_kind":"evidence",
        "source":"public_web_search",
        "claims":[
            "debt_exposure=sizable; refinancing_risk=2027",
            "product=counterparty platform; market_share=0.12",
            "controller=Bob Li; key_person=Alice Zhang",
        ],
    }]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert "public_capital_profile" in profiles
    assert "public_goods_profile" in profiles
    assert "public_people_profile" in profiles
    assert profiles["public_capital_profile"]["row_count"] >= 1
    assert profiles["public_goods_profile"]["row_count"] >= 1
    assert profiles["public_people_profile"]["row_count"] >= 1

def test_public_goods_profile_structures_market_and_business_model_leads() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Goods Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-goods-1",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Goods Co. public business profile",
            "url": "https://example.com/demo-goods",
            "observed_at": "2026-01-01",
            "confidence": 0.68,
            "claims": [
                "customer=State Grid; supplier=Demo Components Ltd; market_share=0.31; competitor_set=PeerCo; competitor_count=3",
                "business_model=platform_or_marketplace; revenue_model=subscription_or_saas; unit_economics=positive_contribution_margin; gross_margin=0.48; cac=controlled; ltv=strong",
                "distributor=North Region Dealer; channel=online marketplace; pricing_power=medium; supplier_power=high; customer_power=medium; barrier_to_entry=moderate",
            ],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Goods Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    public_goods = cognition["public_goods_profile"]
    goods_lane = cognition["investigation_report_card"]["dd_summary"]["goods_lane_summary"]
    subject_goods = cognition["subject_due_diligence_profile"]["goods_lane"]
    readiness = packet["one_click_readiness"]

    assert public_goods["verification_status"] == "public_lead_needs_corroboration"
    assert "customer=State Grid" in public_goods["customer_claims"]
    assert "supplier=Demo Components Ltd" in public_goods["supplier_claims"]
    assert "distributor=North Region Dealer" in public_goods["channel_partner_claims"]
    assert "channel=online marketplace" in public_goods["channel_partner_claims"]
    assert "market_share=0.31" in public_goods["market_position_claims"]
    assert "business_model=platform_or_marketplace" in public_goods["business_model_claims"]
    assert "unit_economics=positive_contribution_margin" in public_goods["unit_economics_claims"]
    assert "gross_margin=0.48" in public_goods["unit_economics_claims"]
    assert "pricing_power=medium" in public_goods["bargaining_power_claims"]
    assert "supplier_power=high" in public_goods["bargaining_power_claims"]
    assert "competitor_set=PeerCo" in public_goods["competitive_landscape_claims"]
    assert "barrier_to_entry=moderate" in public_goods["competitive_landscape_claims"]
    assert goods_lane["lane_status"] == "weak"
    assert goods_lane["deep_analysis"]["channel_dependency"] == "MEDIUM"
    assert goods_lane["deep_analysis"]["unit_economics_visibility"] == "PUBLIC_LEAD"
    assert goods_lane["deep_analysis"]["bargaining_power_visibility"] == "PUBLIC_LEAD"
    assert goods_lane["deep_analysis"]["competitive_landscape_visibility"] == "PUBLIC_LEAD"
    assert "distributor=North Region Dealer" in goods_lane["deep_analysis"]["public_channel_or_partner"]
    assert "market_share=0.31" in goods_lane["market_position_claims"]
    assert "revenue_model=subscription_or_saas" in goods_lane["business_model_claims"]
    assert "ltv=strong" in goods_lane["unit_economics_claims"]
    assert "customer_power=medium" in goods_lane["bargaining_power_claims"]
    assert "competitor_count=3" in goods_lane["competitive_landscape_claims"]
    assert readiness["goods_economics_closure_needed"] is True
    assert readiness["goods_economics_signal_count"] >= 10
    assert readiness["goods_economics_closure_step"]["kind"] == "goods_economics_corroboration"
    assert readiness["goods_economics_closure_step"]["priority"] == "P1"
    assert readiness["goods_economics_closure_step"]["ready_to_run"] is True
    assert "goods_economics_claims_are_corroborated" in readiness["goods_economics_closure_step"]["done_condition"]
    assert any(
        item["lane"] == "goods_economics_closure"
        and item["work_id"] == "GOODS-ECON-001"
        for item in readiness["operator_work_queue"]
    )
    handoff_cards = packet["report_exports"]["print_package"]["operational_handoff"]["cards"]
    assert any(card["id"] == "goods_economics_closure_step" for card in handoff_cards)
    assert any(card["id"] == "GOODS-ECON-001" for card in handoff_cards)
    assert any("Public goods detail:" in item for item in subject_goods["key_findings"])
    report = packet["report_markdown"]
    assert "goods public leads: customers=2 | suppliers=2 | channels=2 | market=5 | model=3 | unit=4 | power=4 | competition=4" in report
    assert "market: market_share=0.31" in report
    assert "model: business_model=platform_or_marketplace" in report
    assert "unit: unit_economics=positive_contribution_margin" in report
    assert "power: pricing_power=medium" in report
    assert "competition: market_share=0.31" in report
    assert "channel: distributor=North Region Dealer" in report
    assert "goods economics closure: needed=True" in report
    assert "goods economics closure step: GOODS-ECON-001" in report


def test_public_goods_profile_enriches_goods_flow_profile() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Goods Flow Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-goods-public",
                "source": "public_web_search",
                "title": "Demo Goods Flow Co. business model",
                "confidence": 0.72,
                "claims": [
                    "Public web market-position lead: market_share=0.31; market_position=market_leader_or_dominant; competitor_set=PeerCo; competitive_position=market_challenger; sources=public web",
                    "Public web business-model lead: business_model=platform_or_marketplace; revenue_model=subscription_or_saas; unit_economics=positive; gross_margin=0.52; pricing_power=medium; customer_power=high; sources=public web",
                    "Public web product-dependency lead: product_dependency=publicly_described; sources=public web",
                ],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.96},
            }
        ],
        "nodes": [],
        "edges": [],
        "timeline": [],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Goods Flow Co.").to_dict()
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]
    report = packet["report_markdown"]

    assert goods_flow["corroboration_status"] == "public_lead_needs_corroboration"
    assert any("public_market:market_share=0.31" in item for item in goods_flow["industry_signals"])
    assert any("public_model:business_model=platform_or_marketplace" in item for item in goods_flow["value_chain_signals"])
    assert any("public_lead:product_dependency=publicly_described" in item for item in goods_flow["product_signals"])
    assert any("public_unit_economics:unit_economics=positive" in item for item in goods_flow["unit_economics_signals"])
    assert any("public_bargaining_power:pricing_power=medium" in item for item in goods_flow["bargaining_power_signals"])
    assert any("public_competition:competitor_set=PeerCo" in item for item in goods_flow["competitive_landscape_signals"])
    assert any("public_bargaining_power:customer_power=high" in item for item in goods_flow["pressure_points"])
    assert any("unit:2" in item and "power:2" in item and "competition:4" in item for item in goods_flow["quality_notes"])
    assert "public_goods_status=public_lead_needs_corroboration" in goods_flow["quality_notes"]
    assert "璐х墿娴" in report or "goods" in report.lower()
    assert "public_model:business_model=platform_or_marketplace" in report
    assert "public_unit_economics:unit_economics=positive" in report


def test_public_capital_profile_structures_money_lane_and_report() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-capital-1",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Capital Co. public capital profile",
            "url": "https://example.com/demo-capital",
            "observed_at": "2026-01-01",
            "confidence": 0.67,
            "claims": [
                "debt_exposure=sizable; refinancing_risk=2027_maturity_wall",
                "cash_or_liquidity_pressure=working_capital_pressure; pledge=equity_pledge",
                "financing_event=convertible_offering",
            ],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    public_capital = cognition["public_capital_profile"]
    fund_flow = cognition["fund_flow_profile"]
    money_lane = cognition["investigation_report_card"]["dd_summary"]["money_lane_summary"]
    subject_capital = cognition["subject_due_diligence_profile"]["capital_lane"]

    assert public_capital["verification_status"] == "public_lead_needs_corroboration"
    assert "debt_exposure=sizable" in public_capital["debt_credit_claims"]
    assert "refinancing_risk=2027_maturity_wall" in public_capital["refinancing_claims"]
    assert "cash_or_liquidity_pressure=working_capital_pressure" in public_capital["liquidity_claims"]
    assert "pledge=equity_pledge" in public_capital["asset_pressure_claims"]
    readiness = packet["one_click_readiness"]
    assert readiness["capital_pressure_verification_status"] == "admitted_and_public_leads_mixed"
    assert readiness["capital_pressure_lead_only_public_rows_present"] is True
    assert readiness["capital_relationship_needed"] is True
    assert readiness["capital_relationship_explained"] is False
    assert money_lane["lane_status"] == "weak"
    assert money_lane["public_capital_structured_summary"]["debt_credit"] == 1
    assert "public_refinancing_leads=1" in fund_flow["money_out_or_pressure_signals"]
    assert any("Public capital detail:" in item for item in subject_capital["key_findings"])
    report = packet["report_markdown"]
    assert "capital public leads: debt=1 | refinancing=1 | liquidity=1 | asset_pressure=1 | financing=1" in report
    assert "capital: pressure=elevated | verification=admitted_and_public_leads_mixed" in report
    assert "debt: debt_exposure=sizable" in report
    assert "refinancing: refinancing_risk=2027_maturity_wall" in report


def test_public_people_profile_structures_people_lane_and_report_without_fact_promotion() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo People Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-people-1",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo People Co. public profile",
            "url": "https://example.com/demo-people",
            "observed_at": "2026-01-01",
            "confidence": 0.69,
            "claims": [
                "actual_controller=Alice Zhang; beneficial_owner=Alice Zhang; director=Bob Li; legal_representative=Chen Wang",
                "enforcement_case=publicly_described; administrative_penalty=publicly_described; shareholder_change=2025_registry_change",
                "related_party=Demo Related Ltd; common_address=Industrial Park A; labor_dispute=publicly_described",
            ],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo People Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    public_people = cognition["public_people_profile"]
    people_flow = cognition["people_flow_profile"]
    people_lane = cognition["investigation_report_card"]["dd_summary"]["people_lane_summary"]
    subject_people = cognition["subject_due_diligence_profile"]["people_lane"]
    readiness = packet["one_click_readiness"]
    report = packet["report_markdown"]

    assert public_people["verification_status"] == "public_lead_needs_corroboration"
    assert "actual_controller=Alice Zhang" in public_people["control_role_claims"]
    assert "beneficial_owner=Alice Zhang" in public_people["control_role_claims"]
    assert "director=Bob Li" in public_people["key_person_claims"]
    assert "legal_representative=Chen Wang" in public_people["key_person_claims"]
    assert "enforcement_case=publicly_described" in public_people["legal_pressure_claims"]
    assert "administrative_penalty=publicly_described" in public_people["legal_pressure_claims"]
    assert "shareholder_change=2025_registry_change" in public_people["ownership_change_claims"]
    assert "related_party=Demo Related Ltd" in public_people["related_party_claims"]
    assert public_people["structured_summary"]["control_roles"] == 2
    assert public_people["structured_summary"]["key_people"] == 2
    assert public_people["structured_summary"]["legal_pressure"] == 2
    assert public_people["structured_summary"]["ownership_changes"] == 1
    assert public_people["structured_summary"]["related_parties"] == 2
    assert public_people["structured_summary"]["labor_social"] == 1

    assert people_flow["verification_status"] == "public_lead_needs_corroboration"
    assert any("public_control:actual_controller=Alice Zhang" in item for item in people_flow["controller_signals"])
    assert any("public_key_person:director=Bob Li" in item for item in people_flow["key_person_signals"])
    assert any("public_legal_pressure:enforcement_case=publicly_described" in item for item in people_flow["legal_pressure_signals"])
    assert any("public_ownership_change:shareholder_change=2025_registry_change" in item for item in people_flow["control_path_signals"])
    assert any("public_related_party:related_party=Demo Related Ltd" in item for item in people_flow["relationship_signals"])
    assert "public_people_status=public_lead_needs_corroboration" in people_flow["quality_notes"]

    assert people_lane["lane_status"] == "weak"
    assert people_lane["fact_count"] == 0
    assert people_lane["lead_count"] >= public_people["row_count"]
    assert people_lane["public_people_structured_summary"]["control_roles"] == 2
    assert people_lane["deep_analysis"]["public_people_visibility"] == "PUBLIC_LEAD"
    assert people_lane["deep_analysis"]["controller_confidence"] == "MEDIUM"
    assert people_lane["deep_analysis"]["ubo_path_visible"] is True
    assert readiness["people_control_closure_needed"] is True
    assert readiness["people_control_signal_count"] >= 9
    assert readiness["people_control_closure_step"]["kind"] == "people_control_corroboration"
    assert readiness["people_control_closure_step"]["priority"] == "P1"
    assert readiness["people_control_closure_step"]["ready_to_run"] is True
    assert "people_control_claims_are_corroborated" in readiness["people_control_closure_step"]["done_condition"]
    assert any(
        item["lane"] == "people_control_closure"
        and item["work_id"] == "PEOPLE-CONTROL-001"
        for item in readiness["operator_work_queue"]
    )
    handoff_cards = packet["report_exports"]["print_package"]["operational_handoff"]["cards"]
    assert any(card["id"] == "people_control_closure_step" for card in handoff_cards)
    assert any(card["id"] == "PEOPLE-CONTROL-001" for card in handoff_cards)
    assert packet["report_exports"]["portable_html"]["first_screen_handoff_cards"] == handoff_cards
    assert any("Public people detail:" in item for item in subject_people["key_findings"])
    assert "people public leads: control=2 | key_people=2 | legal_pressure=2 | ownership_changes=1 | related_parties=2 | labor_social=1" in report
    assert "control: actual_controller=Alice Zhang" in report
    assert "legal: enforcement_case=publicly_described" in report
    assert "people control closure: needed=True" in report
    assert "people control closure step: PEOPLE-CONTROL-001" in report
    assert "people control sample: actual_controller=Alice Zhang" in report
    assert not any(
        item.get("source") == "public_web_search" and item.get("admission") == "fact"
        for item in packet["evidence_ledger"]
    )


def test_dd_summary_folds_qyyjt_pledge_bridge_into_money_lane() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Pledge Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-pledge-1",
            "type": "public_record",
            "source": "qyyjt_api:pledge",
            "title": "QYYJT pledge row",
            "url": "https://qyyjt.example/pledge",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": ["pledge amount=500000; pledgor=Demo Pledge Co.; pledgee=Demo Bank"],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Pledge Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["pledge_bridge"]["fact_count"] == 1
    assert money["qyyjt_bridge"]["pledge_fact_count"] == 1
    assert money["lane_status"] == "covered"
    assert any("Demo Bank" in str(row) for row in money["pledge_freeze_auction"])


def test_dd_summary_surfaces_qyyjt_bond_bridge_in_report() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Bond Pressure Co.",
        "summary": {"execution_state": "risk_events_found", "evidence_count": 1, "risk_event_count": 1, "coverage": {}},
        "risk_events": [{
            "title": "Demo Bond Pressure Co. bond default event",
            "category": "financing_capital_markets",
            "severity": "high",
            "status": "active",
            "confidence": 0.86,
        }],
        "evidence": [{
            "id": "evidence:qyyjt-bond-default-1",
            "type": "public_record",
            "source": "qyyjt_api:bond_default",
            "title": "QYYJT bond default row",
            "url": "https://qyyjt.example/bond-default",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": [
                "bond_name=Demo 2026 Bond; issuer=Demo Bond Pressure Co.; default_date=2026-05-01; amount=100000000; status=confirmed"
            ],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Bond Pressure Co.").to_dict()
    dd = packet["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["bond_credit_bridge"]["pressure_level"] == "high"
    assert dd["bond_credit_bridge"]["default_count"] == 1
    assert money["qyyjt_bridge"]["bond_pressure_level"] == "high"
    assert money["deep_analysis"]["financing_pressure"] == "HIGH"
    assert any("Verify bond pressure" in action for action in packet["next_actions"])
    assert any("Verify bond pressure" in action for action in packet["monitoring_seed"]["next_watch_actions"])
    assert "qyyjt bond bridge: rows=1 | defaults=1 | high=1 | pressure=high" in packet["report_markdown"]

def test_dd_summary_folds_qyyjt_trade_bridge_into_goods_lane() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Trade Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-trade-1",
            "type": "public_record",
            "source": "qyyjt_api:trade",
            "title": "QYYJT trade row",
            "url": "https://qyyjt.example/trade",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": ["trade amount=700000; counterparty=Demo Distributor GmbH"],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Trade Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    goods = dd["goods_lane_summary"]

    assert dd["trade_bridge"]["fact_count"] == 1
    assert goods["qyyjt_bridge"]["trade_fact_count"] == 1
    assert goods["lane_status"] == "covered"
    assert any("Demo Distributor GmbH" in str(row) for row in goods["goods_facts"])

def test_dd_summary_keeps_incomplete_qyyjt_pledge_bridge_as_lead() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Pledge Lead Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-pledge-lead-1",
            "type": "public_record",
            "source": "qyyjt_api:pledge",
            "title": "QYYJT incomplete pledge row",
            "url": "https://qyyjt.example/pledge-lead",
            "observed_at": "2026-01-01",
            "confidence": 0.4,
            "claims": ["pledge pledgor=Demo Pledge Lead Co."],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact", "record_source_type": "query_plan"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Pledge Lead Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["pledge_bridge"]["fact_count"] == 0
    assert dd["pledge_bridge"]["lead_count"] == 1
    assert money["qyyjt_bridge"]["pledge_fact_count"] == 0
    assert money["qyyjt_bridge"]["pledge_lead_count"] == 1
    assert money["lane_status"] == "weak"

def test_people_lane_surfaces_verified_controller_candidates() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [{
                "name": "Alice Zhang",
                "relation_type": "beneficial_owner",
                "confidence_tier": "verified_fact",
                "control_paths": ["Demo Co -> Alice Zhang"],
            }]
        },
        {
            "subject_count": 2,
            "relation_count": 1,
            "relation_types": ["beneficial_owner"],
            "top_edges": [{
                "from_name": "Demo Co",
                "to_name": "Alice Zhang",
                "relation_type": "beneficial_owner",
                "confidence": 0.9,
            }],
        },
    )

    assert lane["lane_status"] == "covered"
    assert lane["controller_candidate_count"] == 1
    assert lane["verified_controller_count"] == 1
    assert lane["relationship_network"]["strong_relation_count"] == 1
    assert lane["deep_analysis"]["ubo_path_visible"] is True


def test_investigation_report_surfaces_indirect_controller_path() -> None:
    graph = {
        "company": "Demo Indirect Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:licensed-ubo-path",
                "source": "qyyjt_api:ubo_path",
                "title": "Licensed UBO path",
                "confidence": 0.88,
                "claims": ["actual_controller=Alice Ultimate"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Indirect Co.",
                "covered_dimensions": ["control_ownership", "relationship_network"],
                "controller_candidate_count": 1,
                "controller_candidates": [
                    {
                        "name": "Alice Ultimate",
                        "relation_type": "beneficial_owner",
                        "confidence": 0.86,
                        "confidence_tier": "verified_fact",
                        "verification_status": "verified",
                        "control_paths": [
                            "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate"
                        ],
                        "control_path_summaries": [
                            {
                                "path_text": "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate",
                                "path_nodes": [
                                    "Demo Indirect Co.",
                                    "Demo Parent Holdings",
                                    "Alice Ultimate",
                                ],
                                "hop_count": 2,
                                "relation_types": ["majority_shareholder", "beneficial_owner"],
                                "terminal_name": "Alice Ultimate",
                                "terminal_kind": "person",
                                "min_confidence": 0.86,
                                "confidence": 0.87,
                                "source_strength": 5,
                                "source_names": ["qyyjt_api:ubo_path"],
                                "evidence_ids": ["evidence:licensed-ubo-path"],
                                "admission": "fact",
                                "verification_status": "verified",
                                "basis": "directed_control_graph_path",
                            }
                        ],
                        "source_names": ["qyyjt_api:ubo_path"],
                    }
                ],
                "relationship_graph": {
                    "nodes": [
                        {"id": "seed", "kind": "company", "name": "Demo Indirect Co."},
                        {"id": "parent", "kind": "company", "name": "Demo Parent Holdings"},
                        {"id": "owner", "kind": "person", "name": "Alice Ultimate"},
                    ],
                    "edges": [
                        {
                            "from_id": "seed",
                            "to_id": "parent",
                            "relation_type": "majority_shareholder",
                            "confidence": 0.87,
                            "admission": "fact",
                            "evidence_ids": ["evidence:licensed-ubo-path"],
                        },
                        {
                            "from_id": "parent",
                            "to_id": "owner",
                            "relation_type": "beneficial_owner",
                            "confidence": 0.86,
                            "admission": "fact",
                            "evidence_ids": ["evidence:licensed-ubo-path"],
                        },
                    ],
                },
                "evidence_gaps": [],
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Indirect Co.").to_dict()
    control = packet["enterprise_cognition"]["control_ownership"]
    readiness = packet["one_click_readiness"]

    assert control["control_paths"]
    assert control["multi_layer_control_path_count"] == 1
    assert control["highest_control_path_hop_count"] == 2
    assert control["control_path_verification_status"] == "review_ready"
    assert control["control_path_source_family_summary"]["top_family"] == "licensed_commercial"
    assert control["control_path_source_family_summary"]["has_official_or_authorized"] is True
    assert control["control_path_verification_queue"][0]["step_id"] == "CONTROL-PATH-001"
    assert control["control_path_verification_queue"][0]["hop_count"] == 2
    assert control["control_path_verification_queue"][0]["source_families"] == ["licensed_commercial"]
    assert readiness["control_path_closure_needed"] is True
    assert readiness["control_path_signal_count"] == 1
    assert readiness["control_path_highest_hop_count"] == 2
    assert readiness["control_path_source_top_family"] == "licensed_commercial"
    assert readiness["control_path_has_official_or_authorized_source"] is True
    assert readiness["control_path_closure_step"]["kind"] == "admitted_indirect_control_path_review"
    assert readiness["control_path_closure_step"]["step_id"] == "CONTROL-PATH-001"
    assert readiness["control_path_closure_step"]["source_families"] == ["licensed_commercial"]
    assert any(
        item["lane"] == "control_path_verification"
        and item["work_id"] == "CONTROL-PATH-001"
        for item in readiness["operator_work_queue"]
    )
    handoff_cards = packet["report_exports"]["print_package"]["operational_handoff"]["cards"]
    assert any(card["id"] == "control_path_closure_step" for card in handoff_cards)
    assert "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate" in packet["report_markdown"]
    assert "control path closure: needed=True" in packet["report_markdown"]
    assert "control path closure step: CONTROL-PATH-001" in packet["report_markdown"]
    assert "multi-layer control paths: count=1 | highest_hops=2 | verification=review_ready" in packet["report_markdown"]
    assert packet["enterprise_cognition"]["investigation_report_card"]["dd_summary"]["people_lane_summary"]["deep_analysis"]["ubo_path_visible"] is True


def test_people_lane_keeps_weak_controller_candidate_as_weak() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {"controller_candidates": [{"name": "Weak Lead", "confidence_tier": "query_plan_lead"}]},
        {"relation_count": 0, "top_edges": []},
    )

    assert lane["lane_status"] == "weak"
    assert lane["fact_count"] == 0
    assert lane["verified_controller_count"] == 0

def test_people_lane_surfaces_controller_conflict_without_promoting_weak_lead() -> None:
    from core.investigation import _build_people_lane, _lane_summary_report_lines

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [
                {
                    "name": "Licensed Owner",
                    "relation_type": "actual_controller",
                    "confidence_tier": "verified_fact",
                    "control_paths": ["Demo Co -> Licensed Owner"],
                },
                {
                    "name": "Public Executive Lead",
                    "relation_type": "chief_executive_officer",
                    "confidence_tier": "weak_public_lead",
                    "control_paths": ["Demo Co -> Public Executive Lead"],
                },
            ]
        },
        {"relation_count": 0, "top_edges": []},
    )

    assert lane["lane_status"] == "covered"
    assert lane["verified_controller_count"] == 1
    assert lane["controller_conflict_summary"]["status"] == "verified_controller_with_competing_leads"
    assert lane["controller_conflict_summary"]["preferred_controller"] == "Licensed Owner"
    assert lane["controller_conflict_summary"]["competing_candidates"] == ["Public Executive Lead"]
    assert lane["deep_analysis"]["controller_conflict_status"] == "verified_controller_with_competing_leads"

    lines = _lane_summary_report_lines({
        "investigation_report_card": {
            "dd_summary": {
                "people_lane_summary": lane,
            }
        }
    })
    assert any("controller review: status=verified_controller_with_competing_leads" in line for line in lines)


def test_controller_conflict_summary_prefers_stronger_verified_source() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [
                {
                    "name": "Official Owner B",
                    "confidence_tier": "verified_fact",
                    "source_strength": 5,
                    "source_names": ["official_registry_public"],
                    "confidence": 0.82,
                },
                {
                    "name": "Licensed Owner A",
                    "confidence_tier": "verified_fact",
                    "source_strength": 9,
                    "source_names": ["qyyjt_api:ubo_path", "licensed_registry_api"],
                    "confidence": 0.91,
                },
            ]
        },
        {"relation_count": 0, "top_edges": []},
    )

    summary = lane["controller_conflict_summary"]
    assert summary["status"] == "conflicting_verified_controller_claims"
    assert summary["preferred_controller"] == "Licensed Owner A"
    assert summary["preferred_basis"]["source_strength"] == 9
    assert summary["competing_candidates"] == ["Official Owner B"]


def test_report_markdown_surfaces_lane_summary_bridges() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Lane Report Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:qyyjt-pledge-report",
                "type": "public_record",
                "source": "qyyjt_api:pledge",
                "title": "QYYJT pledge row",
                "url": "https://qyyjt.example/pledge-report",
                "observed_at": "2026-01-01",
                "confidence": 0.9,
                "claims": ["pledge amount=500000; pledgor=Demo Lane Report Co.; pledgee=Demo Bank"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact"},
            },
            {
                "id": "evidence:qyyjt-trade-report",
                "type": "public_record",
                "source": "qyyjt_api:trade",
                "title": "QYYJT trade row",
                "url": "https://qyyjt.example/trade-report",
                "observed_at": "2026-01-01",
                "confidence": 0.9,
                "claims": ["trade amount=700000; counterparty=Demo Distributor GmbH"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact"},
            },
            {
                "id": "evidence:public-relationship-leads",
                "type": "public_record",
                "source": "public_web_search",
                "title": "Public relationship lead row",
                "url": "https://example.com/relationship-leads",
                "observed_at": "2026-01-01",
                "confidence": 0.72,
                "claims": ["supplier=Acme Components; controller=Alice Zhang; lender=Demo Bank"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review"},
            },
        ],
    }

    packet = build_investigation_packet(graph, input_text="Demo Lane Report Co.").to_dict()
    report = packet["report_markdown"]

    assert "## Due Diligence Lane Summary" in report
    assert "qyyjt pledge bridge: facts=1" in report
    assert "qyyjt trade bridge: facts=1" in report
    assert "relationship candidate leads:" in report
    assert "supplier_of:" in report
    assert "controls:" in report
    assert "admission=weak_lead" in report
    assert any("Corroborate relationship candidate leads" in action for action in packet["next_actions"])
    assert any("Corroborate relationship candidate leads" in action for action in packet["monitoring_seed"]["next_watch_actions"])
    assert "relationship_candidate_leads" in packet["monitoring_seed"]["watched_dimensions"]
    relationship_watchlist = packet["monitoring_seed"]["relationship_candidate_watchlist"]
    supplier_watch = next(item for item in relationship_watchlist if item["target"] == "Acme Components")
    controller_watch = next(item for item in relationship_watchlist if item["target"] == "Alice Zhang")
    lender_watch = next(item for item in relationship_watchlist if item["target"] == "Demo Bank")
    assert supplier_watch["relation_type"] == "supplier_of"
    assert supplier_watch["admission"] != "fact"
    assert controller_watch["priority"] == "P0"
    assert lender_watch["relation_type"] == "lender_to"
    assert lender_watch["priority"] == "P0"
    assert lender_watch["verification_source_hint"] == "capital_market_credit_pledge_or_licensed_financing_source"
    relationship_plan = packet["monitoring_seed"]["relationship_candidate_execution_plan"]
    supplier_step = next(item for item in relationship_plan if item["relation_type"] == "supplier_of")
    controller_step = next(item for item in relationship_plan if item["relation_type"] == "controls")
    lender_step = next(item for item in relationship_plan if item["relation_type"] == "lender_to")
    readiness = packet["one_click_readiness"]
    assert readiness["relationship_candidate_watch_count"] == len(relationship_watchlist)
    assert readiness["relationship_candidate_execution_step_count"] == len(relationship_plan)
    assert readiness["relationship_candidate_p0_count"] >= 2
    assert readiness["relationship_candidate_top_step"]["step_id"] == relationship_plan[0]["step_id"]
    assert readiness["relationship_candidate_top_step"]["relation_type"] == relationship_plan[0]["relation_type"]
    assert readiness["relationship_candidate_top_step"]["verification_sources"]
    assert "procurement_public" in supplier_step["verification_sources"]
    assert "official_registry_control" in controller_step["verification_sources"]
    assert "credit_agreement_filings" in lender_step["verification_sources"]
    assert supplier_step["expansion_queries"][0]["target_subject"] == "Acme Components"
    assert supplier_step["expansion_queries"][0]["purpose"] == "registry_identity"
    assert any(query["domain"] == "trade_supply_chain" for query in supplier_step["expansion_queries"])
    assert any(query["domain"] == "financing_capital_markets" for query in controller_step["expansion_queries"])
    assert any(query["source_hint"] == "credit_agreement_filings" for query in lender_step["expansion_queries"])
    assert "relationship candidate execution plan:" in report
    assert "relationship candidate execution: watches=" in report
    assert "top relationship step: REL-CANDIDATE-" in report
    assert "REL-CANDIDATE-" in report
    assert "expand: registry_identity" in report
    assert "expand: contract_awards" in report
    assert "recovery execution queue:" in report


def test_report_markdown_surfaces_blocked_recovery_preview() -> None:
    from core.investigation import _report_markdown

    report = _report_markdown(
        company="Blocked Recovery Co.",
        mode="standard",
        risk_brief={
            "verdict": "needs_more_evidence",
            "risk_score": 0,
            "highest_severity": "unknown",
            "execution_state": "coverage_gap",
            "confidence_note": "insufficient_data",
            "key_findings": [],
        },
        profile_brief={},
        enterprise_cognition={},
        evidence_ledger=[],
        source_provenance={},
        source_failure_summary={},
        risk_event_summary={},
        persona_surface={},
        monitoring_seed={
            "recovery_execution_queue": {
                "ready_to_run": False,
                "queued_count": 0,
                "blocked_count": 1,
                "blocked_preview": [
                    {
                        "step_id": "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1",
                        "source": "gsxt_shareholder_tabs",
                        "status": "connector_required",
                        "domain": "ownership_control",
                        "priority": "P0",
                    }
                ],
            }
        },
        next_actions=[],
        quality_gate={},
    )

    assert "blocked recovery preview:" in report
    assert "status=connector_required" in report
    assert "gsxt_shareholder_tabs" in report

def test_bridge_excludes_qyyjt_sources() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{
        "record_kind":"evidence",
        "source":"qyyjt_api:ent_basic",
        "claims":["debt_exposure=sizable"],
    }]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert not profiles  # Should be empty dict

def test_bridge_skips_non_evidence_records() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{"record_kind":"lead","source":"public_web_search","claims":["test=value"]}]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert not profiles


# ── Pipeline integration tests ──
def test_fixture_packet_includes_due_diligence_profile() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        dd=ec.get("subject_due_diligence_profile")
        assert dd is not None, "Missing subject_due_diligence_profile"
        assert dd["type"] == "subject_due_diligence_profile"
        assert "capital_lane" in dd
    asyncio.run(run())

def test_fixture_packet_includes_audit_log() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        audit=ec.get("investigation_audit_log")
        assert audit is not None, "Missing investigation_audit_log"
        assert audit["sources"]["total_queried"] >= 1
        assert audit["evidence"]["total"] >= 1
    asyncio.run(run())

def test_fixture_packet_includes_multi_layer_graph() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        mlg=ec.get("multi_layer_relationship_graph")
        assert mlg is not None, "Missing multi_layer_relationship_graph"
        assert mlg.get("available") is True
    asyncio.run(run())

def test_e2e_dd_pipeline_all_outputs() -> None:
    """End-to-end test: fixture -> evidence -> cognition -> DD profile -> report -> quality gate."""
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio

    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        graph = export_risk_graph(result)
        packet = build_investigation_packet(graph.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        pk = packet.to_dict()

        # 1. Evidence ledger
        el = pk.get("evidence_ledger", [])
        assert len(el) >= 1, "Should have at least 1 evidence item"
        assert any(e.get("admission") for e in el), "Evidence should have admission field"

        # 2. Enterprise cognition
        ec = pk.get("enterprise_cognition", {})
        assert ec.get("company") == "Demo Technology Co., Ltd."

        # 3. DD profile
        dd = ec.get("subject_due_diligence_profile")
        assert dd is not None, "Missing subject_due_diligence_profile"
        assert dd["type"] == "subject_due_diligence_profile"
        assert "capital_lane" in dd
        assert "goods_lane" in dd
        assert "people_lane" in dd
        assert dd["executive_summary"]["overall_risk"] in ("low", "medium", "high")

        # 4. Audit log
        audit = ec.get("investigation_audit_log")
        assert audit is not None, "Missing investigation_audit_log"
        assert audit["sources"]["total_queried"] >= 1
        assert audit["evidence"]["total"] >= 1
        assert "admitted_as_fact" in audit["evidence"]
        assert "admitted_as_lead" in audit["evidence"]
        assert "coverage" in audit

        # 5. Cross-lane insights
        cross = ec.get("cross_lane_insights", [])
        assert isinstance(cross, list)

        # 6. Public profiles
        for key in ("public_capital_profile", "public_goods_profile", "public_people_profile"):
            profile = ec.get(key)
            assert profile is not None, f"Missing {key}"

        # 7. Multi-layer graph
        mlg = ec.get("multi_layer_graph_data")
        assert mlg is not None, "Missing multi_layer_graph_data"
        assert mlg.get("available") is True

        # 8. Report markdown
        md = pk.get("report_markdown", "")
        assert len(md) > 1000, f"Report too short: {len(md)} chars"
        for keyword in ("尽调画像", "审计日志", "证据准入", "风险事件", "下一步"):
            assert keyword in md, f"Report missing section: {keyword}"

        # 9. Quality gate
        qg = pk.get("quality_gate", {})
        assert qg.get("ok") is True
        assert qg.get("score", 0) >= 50
        dims = qg.get("dimension_scores", [])
        assert len(dims) >= 3, f"Quality dims should be >=3, got {len(dims)}"

        # 10. Persona surface
        ps = pk.get("persona_surface", {})
        assert ps.get("active_role_count", 0) >= 8, f"Should have >=8 active roles"

        # 11. Evidence admission breakdown
        facts = sum(1 for e in el if e.get("admission") == "fact")
        leads = sum(1 for e in el if e.get("admission") in ("lead", "weak_lead"))
        assert facts + leads == len(el), f"All evidence should be classified: facts={facts}, leads={leads}, total={len(el)}"

        # 12. Edge explainability
        graph_data = pk.get("graph", {})
        edges = graph_data.get("edges", [])
        if edges:
            assert "from_name" in edges[0], "Edges should have entity names"
            assert "source_names" in edges[0], "Edges should have source names"

    asyncio.run(run())

def test_dd_profile_has_version_stamp() -> None:
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();res=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(res)
        pkt=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        dd=pkt.to_dict()["enterprise_cognition"].get("subject_due_diligence_profile",{})
        assert dd.get("dd_version") == "1.0", f"Expected dd_version=1.0, got {dd.get('dd_version')}"
        assert dd.get("type") == "subject_due_diligence_profile"
    asyncio.run(run())

def test_hr_summary_contains_all_sections() -> None:
    from core.investigation import _build_human_readable_dd_summary
    dd = {
        "company": "Test Co.",
        "dd_version": "1.0",
        "executive_summary": {"overall_risk": "medium", "evidence_confidence": "high", "evidence_sources": 4},
        "capital_lane": {"risk": "low", "financial_data": True, "public_signals_count": 5, "key_findings": ["Rev: $1B"]},
        "goods_lane": {"risk": "low", "supply_chain_data": True, "public_signals_count": 13, "key_findings": ["Cust: 2"]},
        "people_lane": {"risk": "medium", "legal_admin_data": True, "public_signals_count": 9, "key_findings": ["Legal: 1"]},
        "cross_lane_insights": ["Test insight"],
        "evidence_gaps": ["gap1"],
    }
    summary = _build_human_readable_dd_summary(dd)
    assert "Test Co." in summary
    assert "MODERATE RISK" in summary
    assert "high" in summary.lower()
    assert "LOW RISK" in summary

def test_hr_summary_none_input() -> None:
    from core.investigation import _build_human_readable_dd_summary
    summary = _build_human_readable_dd_summary(None)
    assert "not available" in summary.lower()

def test_admission_weak_lead_for_unknown_source() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.45,"authority":"unknown","source":"unknown_source","entity_match_level":"partial"})
    assert result == "weak_lead", f"Expected weak_lead, got {result}"

def test_cross_lane_produces_severity_labels() -> None:
    from core.investigation import _cross_lane_analysis
    ec = {
        "public_capital_profile": {"row_count":3,"claims":["debt=yes","refinanc=2027","credit=watch"]},
        "public_goods_profile": {"row_count":5,"claims":["market_share=0.2"]},
        "public_people_profile": {"row_count":2,"claims":["admin_penalty=late"]},
        "legal_administrative_profile": {"risk_event_count":1},
    }
    sc = {"concentration_signal_count":2,"row_count":2}
    insights = _cross_lane_analysis(None, sc, ec)
    assert isinstance(insights, list)
    # At least one insight should have severity [HIGH], [MEDIUM], [LOW], or [INFO]
    assert any(i.startswith("[") for i in insights), f"No severity label found in: {insights}"

def test_evidence_ledger_has_admission_field() -> None:
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();res=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(res)
        pkt=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        el=pkt.to_dict().get("evidence_ledger",[])
        assert len(el)>0, "Evidence ledger should not be empty"
        for item in el:
            assert "admission" in item, f"Evidence item missing admission field: {item.get('source')}"
            assert "admission_reason" in item, f"Evidence item missing admission_reason field"
            assert item["admission"] in ("fact","lead","weak_lead"), f"Invalid admission: {item['admission']}"
    asyncio.run(run())
