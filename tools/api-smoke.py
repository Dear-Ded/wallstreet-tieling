#!/usr/bin/env python3
"""Host-neutral REST API smoke for desktop-agent release checks."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _json(response, label: str) -> dict:
    _assert(response.status_code == 200, f"{label} returned HTTP {response.status_code}: {response.get_data(as_text=True)}")
    payload = response.get_json()
    _assert(isinstance(payload, dict), f"{label} did not return JSON")
    return payload


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("WST_STATE_DIR", str(Path(tempfile.gettempdir()) / "wallstreet-tieling-api-smoke-state"))

    with redirect_stdout(sys.stderr):
        from api.server import app

    client = app.test_client()
    state_dir = Path(os.environ["WST_STATE_DIR"])
    state_dir.mkdir(parents=True, exist_ok=True)

    with redirect_stdout(sys.stderr):
        health = _json(client.get("/api/health"), "GET /api/health")
        _assert(health["version"] == "0.5.0", "health version mismatch")

        release = _json(client.get("/api/release"), "GET /api/release")["data"]
        _assert(release["type"] == "release_readiness_brief", "release type mismatch")
        _assert(release["runtime_delivery"]["release_blocking_surface_count"] == 0, "release runtime blockers present")
        _assert(
            release["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate",
            "desktop-agent delivery decision mismatch",
        )
        _assert(
            release["delivery_decision"]["full_product_status"] == "not_final_release_ready",
            "full product status boundary missing",
        )
        _assert(release["delivery_decision"]["runtime_blocking_surface_count"] == 0, "runtime blocking surfaces must be zero")
        _assert(release["delivery_decision"]["remaining_variant_blocker_count"] == 0, "variant next gates must not block alpha delivery")
        _assert(release["delivery_closure"]["type"] == "desktop_agent_alpha_delivery_closure", "delivery closure type mismatch")
        _assert(release["delivery_closure"]["document"] == "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md", "delivery closure document missing")
        _assert(
            "report_exports.directory_bundle.agent_handoff.delivery_decision"
            in release["delivery_closure"]["required_preserved_fields"],
            "delivery closure handoff field missing",
        )
        _assert(
            "qyyjt_public_origin_handoff.agent_autorun" in release["delivery_closure"]["required_preserved_fields"]
            and "report_exports.directory_bundle.agent_handoff.report_artifact_autorun"
            in release["delivery_closure"]["required_preserved_fields"],
            "delivery closure autorun preserved fields missing",
        )
        _assert("npm pack --dry-run --json" in release["delivery_closure"]["required_verification_commands"], "delivery closure package gate missing")
        _assert("npm run delivery:audit" in release["delivery_closure"]["required_verification_commands"], "delivery closure audit gate missing")
        _assert(release["latest_acceptance_evidence"]["status"] == "passed", "latest acceptance status missing")
        _assert(
            release["latest_acceptance_evidence"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai",
            "latest acceptance timestamp mismatch",
        )
        _assert(release["latest_acceptance_evidence"]["python_tests_passed"] == 799, "latest acceptance test count mismatch")
        _assert(
            "agent_tool_adapters runtime contract" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover agent tool adapters",
        )
        _assert(
            "WorkBuddy investigate_company host smoke" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover WorkBuddy investigation smoke",
        )
        _assert(
            "host-smoke Python runtime resolution" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover Python runtime resolution",
        )
        _assert(
            "release_preflight package go/no-go gate" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover release preflight",
        )
        _assert(
            "package privacy scan gate" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover package privacy scan",
        )
        _assert(
            "npm package dry-run content gate" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover package dry-run gate",
        )
        _assert(
            "terminology guard public-copy hygiene" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover public-copy terminology hygiene",
        )
        _assert(
            "report_exports.agent_decision_digest packet routing" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover packet decision digest",
        )
        _assert(
            "directory bundle verifier_output_fields handoff" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover verifier output fields",
        )
        _assert(
            "directory bundle verification_recipe handoff" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover verification recipe",
        )
        _assert(
            "DOCX source provenance appendix and evidence source index" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover source provenance appendix",
        )
        _assert(
            "DOCX relationship/capital appendix and delivery checklist" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover relationship/capital appendix",
        )
        _assert(
            "source_resilience agent_autorun" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover source_resilience agent_autorun",
        )
        _assert(
            "QYYJT public-origin agent_autorun" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover QYYJT public-origin agent_autorun",
        )
        _assert(
            "capital risk and relationship autorun routes" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover capital/relationship autorun routes",
        )
        _assert(
            "report_artifact_agent_autorun" in release["latest_acceptance_evidence"]["covers"],
            "latest acceptance does not cover report_artifact_agent_autorun",
        )
        _assert(release["release_preflight"]["type"] == "desktop_agent_alpha_release_preflight", "release preflight type missing")
        _assert(release["release_preflight"]["package_candidate_ready"] is True, "release preflight package candidate not ready")
        _assert(release["release_preflight"]["final_submission_ready"] is False, "release preflight final submission boundary missing")
        _assert(
            "npm pack --dry-run --json" in release["release_preflight"]["required_verification_commands"],
            "release preflight package gate missing",
        )
        _assert(
            "npm run release:privacy-scan" in release["release_preflight"]["required_verification_commands"],
            "release preflight privacy scan gate missing",
        )
        _assert(
            "npm run delivery:audit" in release["release_preflight"]["required_verification_commands"],
            "release preflight delivery audit gate missing",
        )
        _assert(
            "npm run objective:audit" in release["release_preflight"]["required_verification_commands"],
            "release preflight objective audit gate missing",
        )

        release_preflight = _json(client.get("/api/release-preflight"), "GET /api/release-preflight")["data"]
        _assert(release_preflight["type"] == "desktop_agent_alpha_release_preflight", "release-preflight endpoint type mismatch")
        _assert(release_preflight["status"] == "ready_for_local_packaging", "release-preflight status mismatch")
        _assert(release_preflight["package_candidate_ready"] is True, "release-preflight package candidate not ready")
        _assert(release_preflight["final_submission_ready"] is False, "release-preflight final submission boundary missing")
        _assert(
            "marketplace/operator screenshots" in " ".join(release_preflight["final_submission_blockers"]),
            "release-preflight submission blockers missing screenshots",
        )
        _assert(
            release_preflight["packaging_review"]["privacy_command"] == "npm run release:privacy-scan",
            "release-preflight privacy command mismatch",
        )

        delivery_audit = _json(client.get("/api/delivery-audit"), "GET /api/delivery-audit")["data"]
        _assert(delivery_audit["type"] == "desktop_agent_alpha_delivery_audit", "delivery-audit type mismatch")
        _assert(delivery_audit["status"] == "pass", "delivery-audit status mismatch")
        _assert(delivery_audit["ready_for_local_packaging"] is True, "delivery-audit package readiness mismatch")
        _assert(delivery_audit["failed_checks"] == [], "delivery-audit failed checks must be empty")
        _assert(delivery_audit["coverage"]["source_resilience"]["covered"] is True, "delivery-audit source resilience coverage missing")
        _assert(delivery_audit["coverage"]["qyyjt_public_origin"]["covered"] is True, "delivery-audit QYYJT coverage missing")
        _assert(delivery_audit["coverage"]["capital_risk"]["covered"] is True, "delivery-audit capital coverage missing")
        _assert(delivery_audit["coverage"]["relationship_graph"]["covered"] is True, "delivery-audit relationship coverage missing")
        _assert(delivery_audit["coverage"]["report_visibility"]["covered"] is True, "delivery-audit report visibility coverage missing")
        _assert(
            "not final polished product launch readiness" in delivery_audit["safe_claim"].lower(),
            "delivery-audit safe claim boundary missing",
        )

        objective_audit = _json(client.get("/api/objective-audit"), "GET /api/objective-audit")["data"]
        _assert(objective_audit["type"] == "objective_completion_audit", "objective-audit type mismatch")
        _assert(objective_audit["status"] == "complete", "objective-audit must be complete after release hygiene closure")
        _assert(objective_audit["completion_percent"] == 100, "objective-audit completion unexpectedly low")
        _assert(
            objective_audit["release_gate"]["delivery_audit_status"] == "pass",
            "objective-audit delivery gate status mismatch",
        )
        requirement_status = {item["id"]: item["status"] for item in objective_audit["requirements"]}
        _assert(requirement_status["source_resilience"] == "complete", "objective-audit source resilience incomplete")
        _assert(requirement_status["qyyjt_public_origin_mapping"] == "complete", "objective-audit QYYJT incomplete")
        _assert(requirement_status["desktop_agent_delivery"] == "complete", "objective-audit desktop agent delivery incomplete")
        _assert(
            requirement_status["public_release_hygiene"] == "complete",
            "objective-audit public release hygiene incomplete",
        )
        _assert(objective_audit["failed_requirements"] == [], "objective-audit failed requirements must be empty")

        connectors = _json(client.get("/api/connectors"), "GET /api/connectors")["data"]
        _assert(connectors["type"] == "connector_catalog", "connector catalog type mismatch")
        _assert("default_public_intel" in connectors["summary"]["zero_config_ready"], "default public connector missing")
        _assert(isinstance(connectors["source_strengthening_queue"], list), "source strengthening queue missing")
        _assert(
            connectors["summary"]["source_strengthening"]["candidate_count"] == len(connectors["source_strengthening_queue"]),
            "source strengthening summary must match queue state",
        )
        source_work = {
            item["connector"]: item
            for item in connectors["source_strengthening_queue"]
        }
        connector_rows = {
            item["name"]: item
            for item in connectors["connectors"]
        }
        if connectors["source_strengthening_queue"]:
            _assert(
                connectors["source_strengthening_queue"][0]["can_feed_report_facts_now"] is False,
                "source strengthening queue must not promote pending sources to facts",
            )
        else:
            _assert(
                connectors["summary"]["source_strengthening"]["top_connectors"] == []
                and connectors["summary"]["source_strengthening"]["by_priority"] == {},
                "empty source strengthening queue must expose empty completion summary",
            )
        _assert(
            "idb_sanctioned_firms_dataset_catalog" not in source_work
            and connector_rows["idb_sanctioned_firms_dataset_catalog"]["production_ready"] is True
            and connector_rows["idb_sanctioned_firms_dataset_catalog"]["default_enabled"] is False
            and connector_rows["idb_sanctioned_firms_dataset_catalog"]["data_effectiveness"]["can_feed_report_facts"] is False
            and connector_rows["idb_sanctioned_firms_dataset_catalog"]["data_effectiveness"]["admission_mode"] == "catalog_source_requires_local_subject_index"
            and connector_rows["idb_local_subject_index"]["production_ready"] is True,
            "IDB catalog should be conditionally production-ready with local subject index companion registered",
        )
        _assert(
            "opensanctions_public_dataset_catalog" not in source_work
            and connector_rows["opensanctions_public_dataset_catalog"]["production_ready"] is True
            and connector_rows["opensanctions_public_dataset_catalog"]["default_enabled"] is False
            and connector_rows["opensanctions_public_dataset_catalog"]["data_effectiveness"]["admission_mode"] == "lead_source_with_exact_match_promotion"
            and connector_rows["opensanctions_local_subject_index"]["production_ready"] is True,
            "OpenSanctions catalog should be conditionally production-ready with local index companion registered",
        )
        gleif_relationship = connector_rows["gleif_lei_relationship_traversal_public_api"]
        _assert(
            "gleif_lei_relationship_traversal_public_api" not in source_work
            and gleif_relationship["production_ready"] is True
            and gleif_relationship["default_enabled"] is False
            and gleif_relationship["data_effectiveness"]["admission_mode"] == "fact_source_when_subject_match_passes",
            "GLEIF relationship traversal should be production-ready default-off and absent from source strengthening queue",
        )
        _assert(
            "official_china_registry_portal_catalog" not in source_work
            and "official_china_credit_portal_catalog" not in source_work
            and "official_china_court_enforcement_catalog" not in source_work
            and connector_rows["official_china_registry_portal_catalog"]["production_ready"] is True
            and connector_rows["official_china_registry_portal_catalog"]["default_enabled"] is False
            and connector_rows["official_china_registry_portal_catalog"]["data_effectiveness"]["can_feed_report_facts"] is True
            and connector_rows["official_china_registry_portal_catalog"]["data_effectiveness"]["admission_mode"] == "fact_source_when_subject_match_passes"
            and connector_rows["official_china_credit_portal_catalog"]["production_ready"] is True
            and connector_rows["official_china_court_enforcement_catalog"]["production_ready"] is True,
            "official China registry source hardening state mismatch",
        )
        _assert(connectors["qyyjt_benchmark"]["summary"]["p0_queue_count"] >= 1, "QYYJT P0 queue missing")

        requirements = _json(client.get("/api/requirements"), "GET /api/requirements")["data"]
        _assert(requirements["type"] == "development_requirements_board", "requirements type mismatch")
        _assert(
            requirements["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate",
            "requirements desktop-agent delivery decision mismatch",
        )
        _assert(
            requirements["delivery_decision"]["full_product_status"] == "not_final_release_ready",
            "requirements full-product boundary missing",
        )
        _assert(requirements["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release", "monitoring boundary missing")

        agent_tools = _json(client.get("/api/agent-tools"), "GET /api/agent-tools")["data"]
        _assert(agent_tools["type"] == "agent_tool_adapter_manifest", "agent tools type mismatch")
        _assert(agent_tools["release_target"] == "desktop_agent_alpha", "agent tools release target mismatch")
        _assert(agent_tools["adapter_count"] == 7, "agent tools adapter count mismatch")
        _assert(agent_tools["all_current_release_ready"] is True, "agent tools readiness mismatch")
        _assert("codex" in agent_tools["host_ids"], "agent tools codex host missing")
        _assert("workbuddy_expert_team" in agent_tools["host_ids"], "agent tools workbuddy host missing")
        _assert(
            "agent_tool_adapters" in {item["name"] for item in agent_tools["shared_tools"]},
            "agent tool adapters shared tool missing",
        )
        _assert(
            "delivery_audit" in {item["name"] for item in agent_tools["shared_tools"]},
            "delivery audit shared tool missing",
        )
        _assert(
            [item["phase"] for item in agent_tools["execution_matrix"]]
            == [
                "release_gate",
                "delivery_audit",
                "source_catalog",
                "priority_board",
                "host_binding",
                "investigation_run",
                "followup_expansion",
            ],
            "agent tools execution matrix phase order mismatch",
        )
        _assert(
            any("operator_work_queue" in item.get("failure_routing", "") for item in agent_tools["execution_matrix"]),
            "agent tools execution matrix failure routing missing",
        )
        autorun = agent_tools.get("one_input_autorun_contract", {})
        _assert(autorun.get("type") == "one_input_autorun_contract", "agent tools one-input autorun contract missing")
        _assert(
            autorun.get("subject_input", {}).get("manual_intermediate_steps_required") is False,
            "agent tools autorun manual step flag mismatch",
        )
        _assert(
            "company_name" in autorun.get("subject_input", {}).get("accepted_fields", []),
            "agent tools autorun subject field missing",
        )
        _assert(
            autorun.get("autorun_sequence", [])[-1]["step"] == "investigate_company",
            "agent tools autorun terminal investigation step missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff" in autorun.get("required_packet_fields", [])
            and "one_click_readiness.capital_risk_panel" in autorun.get("required_packet_fields", []),
            "agent tools autorun packet preservation fields missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"],
            "agent tools first-run recipe preservation guard missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff.report_visibility"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"],
            "agent tools first-run recipe report visibility preservation guard missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"],
            "agent tools first-run recipe capital risk panel preservation guard missing",
        )
        _assert(
            "qyyjt_public_origin_handoff.agent_autorun" in agent_tools["first_run_recipe"]["preserve_before_summarizing"]
            and "report_exports.directory_bundle.agent_handoff.report_artifact_autorun"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"],
            "agent tools first-run recipe autorun preservation guard missing",
        )
        _assert(
            "enterprise_cognition.relationship_resolution_v1"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"]
            and "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue"
            in agent_tools["first_run_recipe"]["preserve_before_summarizing"],
            "agent tools first-run recipe relationship resolution guard missing",
        )
        _assert(
            any("prose-only" in item for item in agent_tools["first_run_recipe"]["do_not"]),
            "agent tools first-run recipe do-not guard missing",
        )
        _assert(agent_tools["default_host_id"] == "codex", "agent tools default host id mismatch")
        _assert(agent_tools["primary_host_id"] == "codex", "agent tools primary host id mismatch")
        _assert(agent_tools["host_priority_order"][0] == "codex", "agent tools priority order must start with codex")
        _assert("workbuddy_expert_team" in agent_tools["secondary_host_ids"], "agent tools workbuddy secondary host missing")
        _assert(set(agent_tools["adapter_lookup"]) == set(agent_tools["host_ids"]), "agent tools adapter lookup host coverage mismatch")
        _assert(
            agent_tools["adapter_lookup"]["codex"]["smoke_command"] == "npm run codex:mcp-smoke",
            "agent tools codex lookup smoke command mismatch",
        )
        _assert(
            agent_tools["adapter_lookup"]["codex"]["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix",
            "agent tools codex lookup execution matrix ref missing",
        )
        _assert(agent_tools["adapter_lookup"]["codex"]["delivery_priority"]["lane"] == "primary", "codex adapter priority mismatch")
        _assert(
            agent_tools["adapter_lookup"]["workbuddy_expert_team"]["delivery_priority"]["lane"] == "secondary",
            "workbuddy adapter priority mismatch",
        )
        codex_adapter = next(item for item in agent_tools["adapters"] if item["host_id"] == "codex")
        _assert(codex_adapter["primary_mode"] == "codex_plugin_mcp", "codex adapter primary mode mismatch")
        _assert(
            codex_adapter["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix",
            "codex adapter execution matrix ref missing",
        )
        _assert(
            codex_adapter["tool_sequence"]
            == [
                "release_readiness",
                "delivery_audit",
                "connector_catalog",
                "development_requirements",
                "agent_tool_adapters",
                "investigate_company",
            ],
            "codex adapter tool sequence mismatch",
        )
        _assert("report_exports.agent_decision_digest" in codex_adapter["required_packet_fields"], "codex adapter packet field missing")
        _assert(
            "enterprise_cognition.relationship_resolution_v1" in codex_adapter["required_packet_fields"]
            and "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue"
            in codex_adapter["required_packet_fields"],
            "codex adapter relationship resolution packet fields missing",
        )
        _assert(
            "report_exports.directory_bundle.verifier_output_fields" in codex_adapter["required_packet_fields"],
            "codex adapter verifier output field missing",
        )
        _assert(
            "report_exports.directory_bundle.verification_recipe" in codex_adapter["required_packet_fields"],
            "codex adapter verification recipe field missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff.report_visibility" in codex_adapter["required_packet_fields"],
            "codex adapter report visibility field missing",
        )
        _assert(
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel" in codex_adapter["required_packet_fields"],
            "codex adapter capital risk panel field missing",
        )
        _assert("npm run codex:mcp-smoke" in agent_tools["required_smoke_commands"], "codex smoke command missing")

        investigate = _json(
            client.post(
                "/api/investigate",
                json={
                    "company": "Demo REST Agent Smoke Co., Ltd.",
                    "offline_fixture": True,
                    "store": str(state_dir / "risk-events.jsonl"),
                },
            ),
            "POST /api/investigate",
        )["data"]
        _assert(investigate["type"] == "investigation_packet", "investigation packet type mismatch")
        _assert(investigate["qyyjt_public_origin_handoff"]["type"] == "qyyjt_public_origin_handoff", "QYYJT handoff missing")
        _assert(investigate["qyyjt_public_origin_handoff"]["section_work_orders"], "QYYJT section work orders missing")
        _assert(
            investigate["qyyjt_public_origin_handoff"]["section_execution_summary"]["type"]
            == "qyyjt_section_execution_summary",
            "QYYJT section execution summary missing",
        )
        _assert(
            investigate["qyyjt_public_origin_handoff"]["top_ready_section_work_order"],
            "QYYJT top ready section work order missing",
        )
        _assert(
            investigate["qyyjt_public_origin_handoff"]["agent_autorun"]["type"]
            == "qyyjt_public_origin_agent_autorun",
            "QYYJT autorun handoff missing",
        )
        _assert(
            investigate["qyyjt_public_origin_handoff"]["agent_autorun"]["manual_intermediate_steps_required"] is False,
            "QYYJT autorun should not require manual intermediate steps",
        )
        _assert(
            investigate["qyyjt_public_origin_handoff"]["agent_autorun"]["routes"][0]["mcp_tool"] == "investigate_company",
            "QYYJT autorun route missing investigate_company tool",
        )
        _assert("source_resilience_recommended_step" in investigate["one_click_readiness"], "source recovery step missing")
        _assert("source_resilience_retry_policy" in investigate["one_click_readiness"], "source recovery retry policy missing")
        _assert(
            isinstance(investigate["one_click_readiness"].get("source_resilience_retry_max_attempts"), int),
            "source recovery retry max attempts missing",
        )
        _assert("operator_work_queue_count" in investigate["one_click_readiness"], "operator work count missing")
        _assert("operator_work_queue" in investigate["one_click_readiness"], "operator work queue missing")
        _assert("reliance_limitations" in investigate["one_click_readiness"], "reliance limitations missing")
        _assert("can_make_clean_conclusion" in investigate["one_click_readiness"], "clean conclusion flag missing")
        _assert("capital_verification_queue_count" in investigate["one_click_readiness"], "capital queue missing")
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["capital_risk_panel"]["agent_autorun"]["type"]
            == "capital_risk_agent_autorun",
            "capital risk autorun missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["capital_risk_panel"]["agent_autorun"]["routes"][0]["mcp_tool"]
            == "investigate_company",
            "capital risk autorun route missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["relationship_graph_audit"]["agent_autorun"]["type"]
            == "relationship_graph_audit_agent_autorun",
            "relationship graph autorun missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["relationship_resolution"]["agent_autorun"]["type"]
            == "relationship_resolution_agent_autorun",
            "relationship resolution autorun missing",
        )
        _assert(isinstance(investigate["one_click_readiness"].get("capital_verification_queue"), list), "capital queue list missing")
        capital_panel = investigate["one_click_readiness"].get("capital_risk_panel", {})
        _assert(capital_panel.get("type") == "capital_risk_panel", "one-click capital risk panel missing")
        _assert(capital_panel.get("report_visibility"), "one-click capital risk panel report visibility missing")
        _assert(
            capital_panel.get("capital_verification_queue_count")
            == investigate["one_click_readiness"]["capital_verification_queue_count"],
            "one-click capital risk panel queue count mismatch",
        )
        _assert("relationship_graph_audit_queue_count" in investigate["one_click_readiness"], "relationship audit queue missing")
        _assert(isinstance(investigate["one_click_readiness"].get("relationship_graph_audit_queue"), list), "relationship audit queue list missing")
        _assert(
            investigate["report_exports"]["agent_decision_digest"]["type"] == "agent_decision_digest",
            "packet-level agent decision digest missing",
        )
        _assert(
            investigate["report_exports"]["agent_decision_digest"]["first_action"]["id"],
            "packet-level agent decision digest first action missing",
        )
        _assert(investigate["report_exports"]["portable_html"]["document"].startswith("<!doctype html>"), "portable HTML missing")
        _assert("Agent decision digest" in investigate["report_exports"]["portable_html"]["document"], "portable HTML decision digest missing")
        _assert("Visual evidence panels" in investigate["report_exports"]["portable_html"]["document"], "portable HTML visual panels missing")
        _assert("Source provenance appendix" in investigate["report_exports"]["portable_html"]["document"], "portable HTML source appendix missing")
        _assert("Relationship and capital appendix" in investigate["report_exports"]["portable_html"]["document"], "portable HTML relationship/capital appendix missing")
        _assert(
            "operational_handoff_tables"
            in investigate["report_exports"]["print_package"]["docx"]["renderer_capabilities"],
            "operational handoff DOCX capability missing",
        )
        _assert(
            "embedded_local_image_evidence"
            in investigate["report_exports"]["print_package"]["docx"]["renderer_capabilities"],
            "embedded image DOCX capability missing",
        )
        image_inventory = investigate["report_exports"]["print_package"].get("image_evidence_inventory", {})
        _assert(image_inventory.get("type") == "image_evidence_inventory", "image evidence inventory missing")
        _assert("count" in image_inventory and "embeddable_count" in image_inventory, "image evidence inventory counts missing")
        _assert(
            investigate["report_exports"]["portable_html"].get("image_evidence_source")
            == "report_exports.print_package.image_evidence_inventory",
            "portable HTML image evidence source missing",
        )
        _assert(
            "Image evidence summary" in investigate["report_exports"]["portable_html"]["document"],
            "portable HTML image evidence summary missing",
        )
        _assert(
            investigate["report_exports"]["print_package"]["operational_handoff"]["summary"]["status"]
            == investigate["one_click_readiness"]["status"],
            "operational handoff summary mismatch",
        )
        _assert(
            investigate["report_exports"]["print_package"]["relationship_capital_appendix"]["type"]
            == "relationship_capital_appendix",
            "relationship/capital print appendix missing",
        )
        _assert(
            "relationship_capital_appendix_present"
            in {
                row["id"]
                for row in investigate["report_exports"]["print_package"]["delivery_checklist"]["quality_checks"]
            },
            "relationship/capital appendix delivery check missing",
        )
        _assert(
            investigate["one_click_readiness"]["acceptance_closure_summary"]["type"] == "acceptance_closure_summary",
            "acceptance closure summary missing",
        )
        _assert(
            investigate["report_exports"]["print_package"]["operational_handoff"]["cards"][0]["id"]
            == "acceptance_closure_summary",
            "acceptance closure handoff card missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["runtime_entrypoint"] == "bin/investigate.py --export-dir",
            "directory bundle export contract missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["integrity_verifier_entrypoint"]
            == "bin/verify_report_bundle.py <export-dir>",
            "directory bundle integrity verifier missing",
        )
        verifier_fields = set(investigate["report_exports"]["directory_bundle"].get("verifier_output_fields", []))
        verification_recipe = investigate["report_exports"]["directory_bundle"].get("verification_recipe", {})
        _assert(verification_recipe.get("type") == "report_bundle_verification_recipe", "directory bundle verification recipe missing")
        _assert(
            "agent_handoff.bundle_ready_to_verify" in set(verification_recipe.get("required_output_fields", [])),
            "directory bundle verification recipe required output fields missing",
        )
        _assert(
            {
                "ok",
                "agent_handoff.schema_valid",
                "agent_handoff.delivery_checklist_present",
                "agent_handoff.bundle_integrity_present",
                "agent_handoff.bundle_verification_present",
                "agent_handoff.bundle_verification_ready_to_run",
                "agent_handoff.bundle_ready_to_verify",
                "agent_handoff.report_visibility_present",
                "agent_handoff.capital_risk_panel_present",
                "agent_handoff.source_strengthening_present",
                "agent_handoff.source_strengthening_runtime_companion_present",
                "agent_handoff.relationship_resolution_present",
            }
            <= verifier_fields,
            "directory bundle verifier output fields missing",
        )
        manifest_fields = set(investigate["report_exports"]["directory_bundle"].get("manifest_fields", []))
        _assert(
            {"file_manifest", "delivery_checklist", "agent_summary"} <= manifest_fields,
            "directory bundle manifest fields missing file manifest, delivery checklist, or agent summary",
        )
        _assert("agent_handoff" in investigate["report_exports"]["directory_bundle"]["writes"], "agent handoff export missing")
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["filename"] == "agent-handoff.json",
            "agent handoff filename missing",
        )
        handoff_fields = set(investigate["report_exports"]["directory_bundle"]["agent_handoff"].get("schema_fields", []))
        _assert(
            {"delivery_decision", "delivery_files", "bundle_integrity", "bundle_verification", "delivery_checklist", "report_visibility", "capital_risk_panel", "source_strengthening", "trust_boundaries", "decision_digest", "next_actions", "report_artifact_autorun"} <= handoff_fields,
            "agent handoff executable schema fields missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["report_artifact_autorun"]["type"]
            == "report_artifact_agent_autorun",
            "report artifact autorun missing",
        )
        _assert(
            investigate["report_exports"]["directory_bundle"]["agent_handoff"]["report_artifact_autorun"]["routes"][1]["cli_command"]
            == "python bin/verify_report_bundle.py <export-dir>",
            "report artifact verifier autorun route missing",
        )
        _assert(
            "delivery decision" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff delivery decision content missing",
        )
        _assert(
            "decision digest" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff decision digest content missing",
        )
        _assert(
            "report visibility" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff report visibility content missing",
        )
        _assert(
            "capital risk panel" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff capital risk panel content missing",
        )
        _assert(
            "source strengthening" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff source strengthening content missing",
        )
        _assert(
            "acceptance closure" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff acceptance closure content missing",
        )
        _assert(
            "control path verification queue" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff control path verification queue content missing",
        )
        _assert(
            "relationship graph audit summary" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff relationship graph audit content missing",
        )
        _assert(
            "source recovery execution queue" in investigate["report_exports"]["directory_bundle"]["agent_handoff"]["content"],
            "agent handoff source recovery execution queue content missing",
        )
        _assert(
            "source resilience retry policy" in investigate["report_markdown"],
            "report markdown source resilience retry policy missing",
        )
        _assert(
            investigate["report_exports"]["future_formats"]["docx_red_head"] == "runtime_cli_renderer_available_via_export_docx",
            "DOCX runtime flag missing",
        )

    print(
        json.dumps(
            {
                "ok": True,
                "checked": [
                    "GET /api/health",
                    "GET /api/release",
                    "GET /api/release-preflight",
                    "GET /api/delivery-audit",
                    "GET /api/objective-audit",
                    "GET /api/connectors",
                    "GET /api/requirements",
                    "GET /api/agent-tools",
                    "POST /api/investigate",
                ],
                "version": release["version"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
