#!/usr/bin/env python3
"""Verify a report export directory against report-export-manifest.json."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify report-export-manifest.json file_manifest size and sha256 rows."
    )
    parser.add_argument(
        "path",
        help="Report export directory or report-export-manifest.json path.",
    )
    return parser


def verify_report_bundle(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    manifest_path = target / "report-export-manifest.json" if target.is_dir() else target
    failures: list[dict[str, str]] = []
    if not manifest_path.exists():
        return _result(False, manifest_path, [], [{"role": "manifest", "reason": "manifest_not_found"}])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exact parser message varies by Python version
        return _result(False, manifest_path, [], [{"role": "manifest", "reason": f"manifest_unreadable:{exc}"}])

    file_manifest = manifest.get("file_manifest", {}) if isinstance(manifest, dict) else {}
    items = file_manifest.get("items", []) if isinstance(file_manifest, dict) else []
    if not isinstance(items, list):
        items = []
    checked: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            failures.append({"role": "", "reason": "invalid_file_manifest_item"})
            continue
        role = str(item.get("role") or "")
        filename = str(item.get("filename") or "")
        expected_size = item.get("size_bytes")
        expected_sha256 = str(item.get("sha256") or "")
        file_path = manifest_path.parent / filename
        if not filename:
            failures.append({"role": role, "reason": "missing_filename"})
            continue
        if not file_path.exists() or not file_path.is_file():
            failures.append({"role": role, "filename": filename, "reason": "file_not_found"})
            continue
        content = file_path.read_bytes()
        actual_size = len(content)
        actual_sha256 = hashlib.sha256(content).hexdigest()
        row = {
            "role": role,
            "filename": filename,
            "size_bytes": actual_size,
            "sha256": actual_sha256,
        }
        checked.append(row)
        if expected_size != actual_size:
            failures.append(
                {
                    "role": role,
                    "filename": filename,
                    "reason": f"size_mismatch:{expected_size}!={actual_size}",
                }
            )
        if expected_sha256 != actual_sha256:
            failures.append(
                {
                    "role": role,
                    "filename": filename,
                    "reason": "sha256_mismatch",
                }
            )

    handoff = _verify_agent_handoff(manifest, manifest_path)
    failures.extend(handoff["failures"])
    return _result(not failures and bool(checked), manifest_path, checked, failures, handoff)


def _verify_agent_handoff(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    agent_handoff_name = files.get("agent_handoff") if isinstance(files, dict) else ""
    result: dict[str, Any] = {
        "type": "agent_handoff_verification",
        "filename": str(agent_handoff_name or ""),
        "checked": False,
        "schema_valid": False,
        "decision_digest_present": False,
        "delivery_checklist_present": False,
        "bundle_integrity_present": False,
        "bundle_verification_present": False,
        "bundle_verification_ready_to_run": False,
        "bundle_ready_to_verify": False,
        "report_visibility_present": False,
        "premium_html_report_visibility_present": False,
        "image_evidence_inventory_present": False,
        "capital_risk_panel_present": False,
        "source_strengthening_present": False,
        "source_strengthening_runtime_companion_present": False,
        "capital_relationship_crosswalk_present": False,
        "verification_recipe_present": False,
        "verifier_output_fields_present": False,
        "acceptance_closure_present": False,
        "source_preflight_present": False,
        "source_preflight_contract_valid": False,
        "manifest_summary_source_preflight_present": False,
        "manifest_summary_source_preflight_valid": False,
        "deep_autopilot_plan_present": False,
        "deep_autopilot_source_runbook_present": False,
        "continuation_entrypoints_valid": False,
        "source_runbook_valid": False,
        "qyyjt_public_origin_present": False,
        "source_resilience_present": False,
        "relationship_graph_audit_present": False,
        "failure_count": 0,
        "failures": [],
    }
    failures: list[dict[str, str]] = []
    if not agent_handoff_name:
        failures.append({"role": "agent_handoff", "reason": "agent_handoff_filename_missing"})
        result["failures"] = failures
        result["failure_count"] = len(failures)
        return result

    handoff_path = manifest_path.parent / str(agent_handoff_name)
    if not handoff_path.exists() or not handoff_path.is_file():
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "agent_handoff_not_found"})
        result["failures"] = failures
        result["failure_count"] = len(failures)
        return result

    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exact parser message varies by Python version
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"agent_handoff_unreadable:{exc}"})
        result["failures"] = failures
        result["failure_count"] = len(failures)
        return result

    result["checked"] = True
    required_fields = [
        "delivery_decision",
        "delivery_files",
        "bundle_integrity",
        "bundle_verification",
        "delivery_checklist",
        "report_visibility",
        "capital_risk_panel",
        "source_strengthening",
        "relationship_resolution",
        "acceptance_closure",
        "qyyjt_public_origin",
        "source_health",
        "capital_and_relationship",
        "trust_boundaries",
        "decision_digest",
        "next_actions",
    ]
    for field in required_fields:
        if field not in handoff:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"missing_{field}"})
    if handoff.get("type") != "report_export_agent_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_handoff_type"})

    decision_digest = handoff.get("decision_digest")
    result["decision_digest_present"] = isinstance(decision_digest, dict)
    if not isinstance(decision_digest, dict) or decision_digest.get("type") != "agent_decision_digest":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_decision_digest"})
        decision_digest = {}

    delivery_checklist = handoff.get("delivery_checklist")
    result["delivery_checklist_present"] = isinstance(delivery_checklist, dict)
    if isinstance(delivery_checklist, dict) and decision_digest:
        if decision_digest.get("delivery_status") != delivery_checklist.get("status"):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "decision_digest_delivery_status_mismatch"})

    bundle_integrity = handoff.get("bundle_integrity")
    result["bundle_integrity_present"] = isinstance(bundle_integrity, dict)
    result["bundle_ready_to_verify"] = bool(bundle_integrity.get("ready_to_verify")) if isinstance(bundle_integrity, dict) else False
    if isinstance(bundle_integrity, dict) and decision_digest:
        if bool(decision_digest.get("bundle_ready_to_verify")) != bool(bundle_integrity.get("ready_to_verify")):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "decision_digest_bundle_ready_mismatch"})

    agent_summary = manifest.get("agent_summary", {}) if isinstance(manifest, dict) else {}
    if not isinstance(agent_summary, dict) or agent_summary.get("type") != "report_export_manifest_agent_summary":
        failures.append({"role": "agent_summary", "reason": "missing_or_invalid_agent_summary"})
        agent_summary = {}
    if agent_summary:
        delivery_decision = handoff.get("delivery_decision", {})
        if agent_summary.get("delivery_decision") != delivery_decision:
            failures.append({"role": "agent_summary", "reason": "agent_summary_delivery_decision_mismatch"})
        if decision_digest and agent_summary.get("decision_digest") != decision_digest:
            failures.append({"role": "agent_summary", "reason": "agent_summary_decision_digest_mismatch"})
        if isinstance(delivery_checklist, dict) and agent_summary.get("delivery_status") != delivery_checklist.get("status"):
            failures.append({"role": "agent_summary", "reason": "agent_summary_delivery_status_mismatch"})
        acceptance_closure = handoff.get("acceptance_closure", {})
        if isinstance(acceptance_closure, dict):
            if agent_summary.get("acceptance_closure_status") != acceptance_closure.get("status"):
                failures.append({"role": "agent_summary", "reason": "agent_summary_acceptance_closure_status_mismatch"})
        _verify_agent_summary_preview(agent_summary, handoff, failures)

    source_preflight = handoff.get("source_preflight")
    result["source_preflight_present"] = isinstance(source_preflight, dict)
    source_preflight_contract = source_preflight.get("no_prompt_contract") if isinstance(source_preflight, dict) else None
    result["source_preflight_contract_valid"] = (
        isinstance(source_preflight, dict)
        and source_preflight.get("type") == "source_preflight"
        and isinstance(source_preflight_contract, dict)
        and source_preflight_contract.get("operator_prompt_required_during_run") is False
        and source_preflight_contract.get("stop_on_missing_advanced_source") is False
    )
    if not result["source_preflight_present"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "missing_source_preflight"})
    elif not result["source_preflight_contract_valid"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_source_preflight_contract"})
    manifest_source_preflight = agent_summary.get("source_preflight") if isinstance(agent_summary, dict) else None
    result["manifest_summary_source_preflight_present"] = isinstance(manifest_source_preflight, dict)
    result["manifest_summary_source_preflight_valid"] = manifest_source_preflight == source_preflight
    if not result["manifest_summary_source_preflight_present"]:
        failures.append({"role": "agent_summary", "reason": "missing_source_preflight"})
    elif not result["manifest_summary_source_preflight_valid"]:
        failures.append({"role": "agent_summary", "reason": "source_preflight_mismatch"})

    deep_plan = handoff.get("deep_autopilot_execution_plan")
    result["deep_autopilot_plan_present"] = isinstance(deep_plan, dict) and deep_plan.get("type") == "deep_autopilot_execution_plan"
    if not result["deep_autopilot_plan_present"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "missing_deep_autopilot_execution_plan"})
        deep_plan = {}
    continuation_entrypoints = deep_plan.get("continuation_entrypoints") if isinstance(deep_plan, dict) else None
    result["continuation_entrypoints_valid"] = (
        isinstance(continuation_entrypoints, list)
        and any(isinstance(item, dict) and item.get("tool") == "investigate_company" for item in continuation_entrypoints)
    )
    if not result["continuation_entrypoints_valid"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_deep_autopilot_continuation_entrypoints"})

    source_runbook = handoff.get("deep_autopilot_source_runbook")
    result["deep_autopilot_source_runbook_present"] = (
        isinstance(source_runbook, dict)
        and source_runbook.get("type") == "deep_autopilot_source_runbook"
    )
    if not result["deep_autopilot_source_runbook_present"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "missing_deep_autopilot_source_runbook"})
        source_runbook = {}
    lanes = source_runbook.get("lanes") if isinstance(source_runbook, dict) else None
    result["source_runbook_valid"] = (
        isinstance(lanes, list)
        and len(lanes) >= 8
        and int(source_runbook.get("automatic_lane_count") or 0) >= 8
        and all(
            isinstance(item, dict)
            and item.get("user_prompt_required") is False
            and item.get("stop_on_failure") is False
            for item in lanes
        )
    )
    if not result["source_runbook_valid"]:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_deep_autopilot_source_runbook"})

    report_visibility = handoff.get("report_visibility")
    result["report_visibility_present"] = isinstance(report_visibility, dict)
    if not isinstance(report_visibility, dict) or report_visibility.get("type") != "report_visibility_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_report_visibility"})
    else:
        image_evidence = report_visibility.get("image_evidence", {})
        source_provenance = report_visibility.get("source_provenance", {})
        premium_html = report_visibility.get("premium_html", {})
        result["image_evidence_inventory_present"] = (
            isinstance(image_evidence, dict)
            and image_evidence.get("inventory_type") == "image_evidence_inventory"
            and image_evidence.get("inventory_source") == "report_exports.print_package.image_evidence_inventory"
            and "count" in image_evidence
            and isinstance(image_evidence.get("items"), list)
        )
        result["premium_html_report_visibility_present"] = (
            isinstance(premium_html, dict)
            and premium_html.get("profile_present") is True
            and premium_html.get("status") in {"runtime_contract_available", "fallback_runtime_pending"}
            and bool(premium_html.get("filename"))
            and isinstance(premium_html.get("acceptance_checklist"), list)
            and isinstance(premium_html.get("content_guarantees"), list)
            and isinstance(premium_html.get("forbidden_shortcuts"), list)
            and isinstance(premium_html.get("metrics"), dict)
            and isinstance(premium_html.get("policy"), str)
        )
        if not isinstance(image_evidence, dict) or "count" not in image_evidence:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "report_visibility_image_evidence_missing"})
        elif not result["image_evidence_inventory_present"]:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "image_evidence_inventory_contract_missing"})
        if not isinstance(source_provenance, dict) or "source_count" not in source_provenance:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "report_visibility_source_provenance_missing"})
        if not result["premium_html_report_visibility_present"]:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "premium_html_report_visibility_contract_missing"})

    capital_risk_panel = handoff.get("capital_risk_panel")
    result["capital_risk_panel_present"] = isinstance(capital_risk_panel, dict)
    if not isinstance(capital_risk_panel, dict) or capital_risk_panel.get("type") != "capital_risk_panel":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_capital_risk_panel"})
    else:
        for field in ("status", "risk_level", "capital_verification_queue_count", "relationship_audit_queue_count", "clean_reliance_allowed"):
            if field not in capital_risk_panel:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"capital_risk_panel_missing_{field}"})

    source_strengthening = handoff.get("source_strengthening")
    result["source_strengthening_present"] = isinstance(source_strengthening, dict)
    if not isinstance(source_strengthening, dict) or source_strengthening.get("type") != "source_strengthening_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_source_strengthening"})
    else:
        for field in ("status", "work_order_count", "top_work_orders", "preserve_fields", "promotion_gate"):
            if field not in source_strengthening:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"source_strengthening_missing_{field}"})
        top_orders = source_strengthening.get("top_work_orders")
        if not isinstance(top_orders, list):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "source_strengthening_top_work_orders_not_list"})
        elif not top_orders:
            if int(source_strengthening.get("work_order_count") or 0) == 0 and source_strengthening.get("status") in {"complete", "empty"}:
                result["source_strengthening_runtime_companion_present"] = True
            else:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "source_strengthening_top_work_orders_missing"})
        elif top_orders:
            top = top_orders[0] if isinstance(top_orders[0], dict) else {}
            execution_plan = top.get("execution_plan") if isinstance(top, dict) else None
            if not isinstance(execution_plan, dict) or execution_plan.get("type") != "source_strengthening_execution_plan":
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "source_strengthening_execution_plan_missing"})
            runtime_companion = top.get("runtime_companion") if isinstance(top, dict) else None
            plan_companion = execution_plan.get("runtime_companion") if isinstance(execution_plan, dict) else None
            companion_ok = (
                isinstance(runtime_companion, dict)
                and runtime_companion.get("type") == "source_strengthening_runtime_companion"
                and bool(runtime_companion.get("connector"))
                and isinstance(plan_companion, dict)
                and plan_companion.get("type") == "source_strengthening_runtime_companion"
                and bool(plan_companion.get("connector"))
            )
            result["source_strengthening_runtime_companion_present"] = companion_ok
            if not companion_ok:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "source_strengthening_runtime_companion_missing"})

    relationship_resolution = handoff.get("relationship_resolution")
    result["relationship_resolution_present"] = isinstance(relationship_resolution, dict)
    if not isinstance(relationship_resolution, dict) or relationship_resolution.get("type") != "relationship_resolution_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_relationship_resolution"})
        relationship_resolution = {}
    else:
        for field in ("lead_count", "verification_queue_count", "verification_queue", "top_step", "preserve_fields", "policy"):
            if field not in relationship_resolution:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"relationship_resolution_missing_{field}"})
        queue = relationship_resolution.get("verification_queue", [])
        if not isinstance(queue, list):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "relationship_resolution_queue_not_list"})
        elif int(relationship_resolution.get("verification_queue_count") or 0) != len(queue):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "relationship_resolution_queue_count_mismatch"})

    acceptance_closure = handoff.get("acceptance_closure")
    result["acceptance_closure_present"] = isinstance(acceptance_closure, dict)
    if not isinstance(acceptance_closure, dict) or "status" not in acceptance_closure:
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_acceptance_closure"})

    qyyjt_public_origin = handoff.get("qyyjt_public_origin")
    result["qyyjt_public_origin_present"] = isinstance(qyyjt_public_origin, dict)
    if not isinstance(qyyjt_public_origin, dict):
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_qyyjt_public_origin"})
    else:
        for field in ("section_work_orders", "section_execution_summary", "gap_bridge"):
            if field not in qyyjt_public_origin:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"qyyjt_public_origin_missing_{field}"})

    source_health = handoff.get("source_health")
    source_resilience = source_health.get("source_resilience") if isinstance(source_health, dict) else None
    result["source_resilience_present"] = isinstance(source_resilience, dict)
    if not isinstance(source_resilience, dict):
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_source_resilience"})
    else:
        for field in ("status", "retry_policy", "retryable", "ready_to_run", "blocked_reason"):
            if field not in source_resilience:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"source_resilience_missing_{field}"})

    capital_and_relationship = handoff.get("capital_and_relationship")
    relationship_audit = (
        capital_and_relationship.get("relationship_graph_audit")
        if isinstance(capital_and_relationship, dict)
        else None
    )
    result["relationship_graph_audit_present"] = isinstance(relationship_audit, dict)
    if not isinstance(relationship_audit, dict) or relationship_audit.get("type") != "relationship_graph_audit_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_relationship_graph_audit"})
    else:
        for field in ("status", "queue_count", "top_step", "policy"):
            if field not in relationship_audit:
                failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": f"relationship_graph_audit_missing_{field}"})
    if isinstance(capital_and_relationship, dict) and isinstance(capital_risk_panel, dict):
        if capital_and_relationship.get("risk_panel") != capital_risk_panel:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "capital_relationship_risk_panel_mismatch"})

    crosswalk = _verify_capital_relationship_crosswalk(manifest, handoff, manifest_path)
    result["capital_relationship_crosswalk_present"] = bool(crosswalk.get("checked")) and not crosswalk.get("failures")
    result["capital_relationship_crosswalk"] = crosswalk
    failures.extend(crosswalk["failures"])

    bundle_verification = handoff.get("bundle_verification")
    result["bundle_verification_present"] = isinstance(bundle_verification, dict)
    result["bundle_verification_ready_to_run"] = bool(bundle_verification.get("ready_to_run")) if isinstance(bundle_verification, dict) else False
    report_exports = manifest.get("report_exports", {}) if isinstance(manifest, dict) else {}
    directory_bundle = report_exports.get("directory_bundle", {}) if isinstance(report_exports, dict) else {}
    if not isinstance(directory_bundle, dict):
        directory_bundle = {}
    verification_recipe = directory_bundle.get("verification_recipe")
    verifier_output_fields = directory_bundle.get("verifier_output_fields")
    result["verification_recipe_present"] = (
        isinstance(verification_recipe, dict)
        and verification_recipe.get("type") == "report_bundle_verification_recipe"
        and isinstance(verification_recipe.get("required_output_fields"), list)
    )
    result["verifier_output_fields_present"] = isinstance(verifier_output_fields, list) and bool(verifier_output_fields)
    if not isinstance(bundle_verification, dict) or bundle_verification.get("type") != "bundle_verification_handoff":
        failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "invalid_bundle_verification"})
    else:
        if not result["verification_recipe_present"]:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verification_recipe_missing"})
        elif bundle_verification.get("recipe") != verification_recipe:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "bundle_verification_recipe_mismatch"})
        if not result["verifier_output_fields_present"]:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verifier_output_fields_missing"})
        if bool(bundle_verification.get("ready_to_run")) != result["bundle_ready_to_verify"]:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "bundle_verification_ready_mismatch"})
        if str(bundle_verification.get("manifest_file") or "") != "report-export-manifest.json":
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "bundle_verification_manifest_mismatch"})
        required_output_fields = bundle_verification.get("required_output_fields", [])
        if not isinstance(required_output_fields, list) or "agent_handoff.bundle_ready_to_verify" not in required_output_fields:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "bundle_verification_required_fields_missing"})
        elif isinstance(verification_recipe, dict) and required_output_fields != verification_recipe.get("required_output_fields"):
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "bundle_verification_required_fields_mismatch"})
        if isinstance(verifier_output_fields, list) and "agent_handoff.image_evidence_inventory_present" not in verifier_output_fields:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verifier_output_fields_image_inventory_missing"})
        if isinstance(verifier_output_fields, list) and "agent_handoff.premium_html_report_visibility_present" not in verifier_output_fields:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verifier_output_fields_premium_html_missing"})
        if isinstance(verifier_output_fields, list) and "agent_handoff.capital_relationship_crosswalk_present" not in verifier_output_fields:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verifier_output_fields_capital_relationship_crosswalk_missing"})
        if isinstance(verifier_output_fields, list) and "agent_handoff.relationship_resolution_present" not in verifier_output_fields:
            failures.append({"role": "report_exports.directory_bundle", "reason": "verifier_output_fields_relationship_resolution_missing"})
        for field in (
            "agent_handoff.source_preflight_present",
            "agent_handoff.source_preflight_contract_valid",
            "agent_handoff.manifest_summary_source_preflight_present",
            "agent_handoff.manifest_summary_source_preflight_valid",
            "agent_handoff.deep_autopilot_plan_present",
            "agent_handoff.deep_autopilot_source_runbook_present",
            "agent_handoff.continuation_entrypoints_valid",
            "agent_handoff.source_runbook_valid",
        ):
            if isinstance(verifier_output_fields, list) and field not in verifier_output_fields:
                failures.append(
                    {
                        "role": "report_exports.directory_bundle",
                        "reason": f"verifier_output_fields_{field.split('.')[-1]}_missing",
                    }
                )

    next_actions = handoff.get("next_actions", [])
    first_action = decision_digest.get("first_action", {}) if isinstance(decision_digest, dict) else {}
    if isinstance(next_actions, list) and next_actions and isinstance(first_action, dict):
        first_id = str(first_action.get("id") or "")
        expected_id = str(next_actions[0].get("id") or "") if isinstance(next_actions[0], dict) else ""
        if first_id != expected_id:
            failures.append({"role": "agent_handoff", "filename": str(agent_handoff_name), "reason": "decision_digest_first_action_mismatch"})

    result["schema_valid"] = not failures
    result["failure_count"] = len(failures)
    result["failures"] = failures
    return result


def _verify_agent_summary_preview(
    agent_summary: dict[str, Any],
    handoff: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    """Reject stale bounded manifest summaries before desktop agents route from them."""
    expected = _expected_agent_summary_preview(handoff)
    for field, expected_value in expected.items():
        if agent_summary.get(field) != expected_value:
            failures.append(
                {
                    "role": "agent_summary",
                    "field": field,
                    "reason": f"agent_summary_{field}_mismatch",
                }
            )


def _expected_agent_summary_preview(handoff: dict[str, Any]) -> dict[str, Any]:
    delivery_checklist = _as_dict(handoff.get("delivery_checklist"))
    trust_boundaries = _as_dict(handoff.get("trust_boundaries"))
    acceptance_closure = _as_dict(handoff.get("acceptance_closure"))
    source_health = _as_dict(handoff.get("source_health"))
    source_resilience = _as_dict(source_health.get("source_resilience"))
    qyyjt_public_origin = _as_dict(handoff.get("qyyjt_public_origin"))
    capital_relationship = _as_dict(handoff.get("capital_and_relationship"))
    relationship_audit = _as_dict(capital_relationship.get("relationship_graph_audit"))
    relationship_resolution = _as_dict(handoff.get("relationship_resolution"))
    operator_work = _as_dict(handoff.get("operator_work"))
    report_visibility = _as_dict(handoff.get("report_visibility"))
    image_evidence = _as_dict(report_visibility.get("image_evidence"))
    source_provenance = _as_dict(report_visibility.get("source_provenance"))
    premium_html = _as_dict(report_visibility.get("premium_html"))
    capital_risk_panel = _as_dict(handoff.get("capital_risk_panel"))
    source_repair_queue = source_health.get("repair_queue", [])
    capital_queue = capital_relationship.get("capital_verification_queue", [])
    next_actions = handoff.get("next_actions", [])
    top_next_actions = [
        {
            "id": item.get("id") or "",
            "priority": item.get("priority") or "",
            "status": item.get("status") or "",
            "action": item.get("action") or "",
            "ready_to_run": bool(item.get("ready_to_run")),
            "done_condition": item.get("done_condition") or "",
        }
        for item in (next_actions[:5] if isinstance(next_actions, list) else [])
        if isinstance(item, dict)
    ]
    return {
        "bundle_verification": _as_dict(handoff.get("bundle_verification")),
        "report_visibility": {
            "type": report_visibility.get("type", "report_visibility_handoff"),
            "image_evidence_inventory_present": (
                image_evidence.get("inventory_type") == "image_evidence_inventory"
            ),
            "image_evidence_count": image_evidence.get("count", 0),
            "source_count": source_provenance.get("source_count", 0),
            "section_inventory_count": report_visibility.get("section_inventory_count", 0),
            "chart_manifest_count": report_visibility.get("chart_manifest_count", 0),
            "premium_html_profile_present": bool(premium_html.get("profile_present")),
            "premium_html_status": premium_html.get("status", ""),
        },
        "capital_risk_panel": {
            "type": capital_risk_panel.get("type", "capital_risk_panel"),
            "status": capital_risk_panel.get("status", "unknown"),
            "risk_level": capital_risk_panel.get("risk_level", "unknown"),
            "capital_verification_queue_count": capital_risk_panel.get("capital_verification_queue_count", 0),
            "relationship_audit_queue_count": capital_risk_panel.get("relationship_audit_queue_count", 0),
            "clean_reliance_allowed": bool(capital_risk_panel.get("clean_reliance_allowed")),
        },
        "can_make_clean_conclusion": bool(trust_boundaries.get("can_make_clean_conclusion")),
        "acceptance_closure_blocking_count": acceptance_closure.get("blocking_count", 0),
        "source_resilience_status": source_resilience.get("status", ""),
        "source_resilience_retryable": bool(source_resilience.get("retryable")),
        "source_resilience_blocked_reason": source_resilience.get("blocked_reason", ""),
        "relationship_audit_status": relationship_audit.get("status", ""),
        "relationship_resolution": {
            "type": relationship_resolution.get("type", "relationship_resolution_handoff"),
            "lead_count": relationship_resolution.get("lead_count", 0),
            "typed_lead_count": relationship_resolution.get("typed_lead_count", 0),
            "weak_lead_count": relationship_resolution.get("weak_lead_count", 0),
            "verification_queue_count": relationship_resolution.get("verification_queue_count", 0),
            "top_step": relationship_resolution.get("top_step", {}),
        },
        "work_queue_counts": {
            "operator_work": operator_work.get("count", 0),
            "operator_work_ready": operator_work.get("ready_count", 0),
            "source_repair": len(source_repair_queue) if isinstance(source_repair_queue, list) else 0,
            "qyyjt_public_origin_sections": len(qyyjt_public_origin.get("section_work_orders", []))
            if isinstance(qyyjt_public_origin.get("section_work_orders"), list)
            else 0,
            "capital_verification": len(capital_queue) if isinstance(capital_queue, list) else 0,
            "relationship_audit": relationship_audit.get("queue_count", 0),
        },
        "top_public_origin_work_order": qyyjt_public_origin.get("top_section_work_order", {}),
        "top_capital_step": capital_relationship.get("capital_verification_top_step", {}),
        "top_relationship_step": relationship_audit.get("top_step", {}),
        "next_action_count": len(next_actions) if isinstance(next_actions, list) else 0,
        "top_next_actions": top_next_actions,
    }


def _verify_capital_relationship_crosswalk(
    manifest: dict[str, Any],
    handoff: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    """Prove capital and relationship routing stays synchronized across bundle surfaces."""
    result: dict[str, Any] = {
        "type": "capital_relationship_crosswalk_verification",
        "checked": False,
        "json_packet_checked": False,
        "manifest_metadata_checked": False,
        "agent_handoff_checked": False,
        "markdown_checked": False,
        "portable_html_metadata_checked": False,
        "docx_metadata_checked": False,
        "docx_metadata_status": "not_checked",
        "expected": {},
        "failure_count": 0,
        "failures": [],
    }
    failures: list[dict[str, str]] = []
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    if not isinstance(files, dict):
        files = {}
    unavailable_outputs = manifest.get("unavailable_outputs", {}) if isinstance(manifest, dict) else {}
    fallback_bundle = (
        isinstance(unavailable_outputs, dict)
        and str(unavailable_outputs.get("docx") or "") == "python_runtime_unavailable"
    )
    result["fallback_bundle"] = fallback_bundle

    packet = _read_json_file(manifest_path, files.get("json_packet"))
    if not isinstance(packet, dict):
        failures.append({"role": "json_packet", "reason": "json_packet_unreadable_for_capital_relationship_crosswalk"})
        return _finish_crosswalk(result, failures)
    result["json_packet_checked"] = True

    one_click = _as_dict(packet.get("one_click_readiness"))
    report_exports = _as_dict(manifest.get("report_exports")) or _as_dict(packet.get("report_exports"))
    print_package = _as_dict(report_exports.get("print_package"))
    appendix = _as_dict(print_package.get("relationship_capital_appendix"))
    portable_html = _as_dict(report_exports.get("portable_html"))
    graph_capital = _as_dict(one_click.get("graph_capital_exposure"))
    relationship_audit = _as_dict(_as_dict(handoff.get("capital_and_relationship")).get("relationship_graph_audit"))
    capital_panel = _as_dict(handoff.get("capital_risk_panel"))
    expected_pressure = str(
        graph_capital.get("pressure_level")
        or one_click.get("capital_pressure_level")
        or capital_panel.get("pressure_level")
        or ""
    )
    expected = {
        "capital_relationship_status": str(one_click.get("capital_relationship_status") or ""),
        "pressure_level": expected_pressure,
        "graph_alignment_status": str(
            one_click.get("graph_capital_exposure_alignment_status")
            or graph_capital.get("alignment_status")
            or ""
        ),
        "graph_relationship_status": str(
            one_click.get("graph_capital_exposure_relationship_status")
            or graph_capital.get("relationship_status")
            or ""
        ),
        "capital_verification_queue_count": _int(one_click.get("capital_verification_queue_count")),
        "relationship_audit_queue_count": _int(one_click.get("relationship_graph_audit_queue_count")),
        "relationship_edge_count": _int(one_click.get("relationship_edge_count")),
        "relationship_evidence_backed_edge_count": _int(one_click.get("relationship_evidence_backed_edge_count")),
        "relationship_lead_only_edge_count": _int(one_click.get("relationship_lead_only_edge_count")),
        "relationship_missing_evidence_edge_count": _int(one_click.get("relationship_missing_evidence_edge_count")),
    }
    result["expected"] = expected

    if fallback_bundle:
        result["agent_handoff_checked"] = bool(capital_panel and _as_dict(handoff.get("capital_and_relationship")))
        result["manifest_metadata_checked"] = bool(appendix)
        result["markdown_checked"] = _read_text_file(manifest_path, files.get("markdown")) is not None
        result["portable_html_metadata_checked"] = _read_text_file(manifest_path, files.get("portable_html")) is not None
        result["docx_metadata_status"] = "not_emitted_python_runtime_unavailable"
        return _finish_crosswalk(result, failures)

    result["agent_handoff_checked"] = bool(capital_panel and relationship_audit)
    _expect_equal(failures, "agent_handoff.capital_risk_panel.capital_relationship_status", capital_panel.get("capital_relationship_status"), expected["capital_relationship_status"])
    _expect_equal(failures, "agent_handoff.capital_risk_panel.pressure_level", capital_panel.get("pressure_level"), expected["pressure_level"])
    _expect_equal(failures, "agent_handoff.capital_risk_panel.capital_verification_queue_count", _int(capital_panel.get("capital_verification_queue_count")), expected["capital_verification_queue_count"])
    _expect_equal(failures, "agent_handoff.capital_risk_panel.relationship_audit_queue_count", _int(capital_panel.get("relationship_audit_queue_count")), expected["relationship_audit_queue_count"])
    _expect_equal(failures, "agent_handoff.relationship_graph_audit.queue_count", _int(relationship_audit.get("queue_count")), expected["relationship_audit_queue_count"])
    _expect_equal(failures, "agent_handoff.relationship_graph_audit.edge_count", _int(relationship_audit.get("edge_count")), expected["relationship_edge_count"])
    if _as_dict(handoff.get("capital_and_relationship")).get("graph_capital_exposure") != graph_capital:
        failures.append({"role": "agent_handoff", "reason": "graph_capital_exposure_crosswalk_mismatch"})

    result["manifest_metadata_checked"] = bool(appendix)
    _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.capital_relationship_status", appendix.get("capital_relationship_status"), expected["capital_relationship_status"])
    _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.relationship_edge_count", _int(appendix.get("relationship_edge_count")), expected["relationship_edge_count"])
    _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.capital_verification_queue_count", _int(appendix.get("capital_verification_queue_count")), expected["capital_verification_queue_count"])
    _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.relationship_audit_queue_count", _int(appendix.get("relationship_audit_queue_count")), expected["relationship_audit_queue_count"])
    graph_summary = _as_dict(appendix.get("graph_capital_exposure_summary"))
    if expected["pressure_level"]:
        _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.graph_capital_exposure_summary.pressure_level", graph_summary.get("pressure_level"), expected["pressure_level"])
    if expected["graph_relationship_status"]:
        _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.graph_capital_exposure_summary.relationship_status", graph_summary.get("relationship_status"), expected["graph_relationship_status"])
    if expected["graph_alignment_status"]:
        _expect_equal(failures, "report_exports.print_package.relationship_capital_appendix.graph_capital_exposure_summary.alignment_status", graph_summary.get("alignment_status"), expected["graph_alignment_status"])

    agent_summary = _as_dict(manifest.get("agent_summary"))
    summary_panel = _as_dict(agent_summary.get("capital_risk_panel"))
    _expect_equal(failures, "agent_summary.capital_risk_panel.capital_verification_queue_count", _int(summary_panel.get("capital_verification_queue_count")), expected["capital_verification_queue_count"])
    _expect_equal(failures, "agent_summary.capital_risk_panel.relationship_audit_queue_count", _int(summary_panel.get("relationship_audit_queue_count")), expected["relationship_audit_queue_count"])

    markdown = _read_text_file(manifest_path, files.get("markdown"))
    if markdown is None:
        failures.append({"role": "markdown", "reason": "markdown_unreadable_for_capital_relationship_crosswalk"})
    else:
        result["markdown_checked"] = True
        _expect_text(failures, "markdown", markdown, f"relationship_status={expected['capital_relationship_status']}", "markdown_capital_relationship_status_missing")
        if expected["pressure_level"] not in {"", "unknown", "none"}:
            _expect_text(failures, "markdown", markdown, f"capital: pressure={expected['pressure_level']}", "markdown_capital_pressure_missing")

    html_text = _read_text_file(manifest_path, files.get("portable_html"))
    if html_text is None:
        failures.append({"role": "portable_html", "reason": "portable_html_unreadable_for_capital_relationship_crosswalk"})
    else:
        result["portable_html_metadata_checked"] = True
        _expect_text(failures, "portable_html", html_text, "Visual evidence panels", "portable_html_visual_evidence_panels_missing")
        _expect_text(failures, "portable_html", html_text, "Source provenance appendix", "portable_html_source_provenance_appendix_missing")
        _expect_text(failures, "portable_html", html_text, "Relationship and capital appendix", "portable_html_relationship_capital_appendix_missing")
        _expect_text(failures, "portable_html", html_text, f"<b>{expected['capital_relationship_status']}</b><span>capital relationship</span>", "portable_html_capital_relationship_card_missing")
        _expect_text(failures, "portable_html", html_text, f"<b>{expected['capital_verification_queue_count']}</b><span>capital verification steps</span>", "portable_html_capital_queue_card_missing")
        _expect_text(failures, "portable_html", html_text, f"<b>{expected['relationship_audit_queue_count']}</b><span>relationship audit steps</span>", "portable_html_relationship_queue_card_missing")
        if portable_html.get("first_screen_handoff_cards") != _as_dict(print_package.get("operational_handoff")).get("cards"):
            failures.append({"role": "portable_html", "reason": "portable_html_handoff_cards_crosswalk_mismatch"})

    docx_name = files.get("docx")
    if docx_name:
        docx_text = _read_docx_document_xml(manifest_path, docx_name)
        if docx_text is None:
            failures.append({"role": "docx", "filename": str(docx_name), "reason": "docx_unreadable_for_capital_relationship_crosswalk"})
            result["docx_metadata_status"] = "unreadable"
        else:
            result["docx_metadata_checked"] = True
            result["docx_metadata_status"] = "checked"
            _expect_text(failures, "docx", docx_text, f"capital_relationship_status={expected['capital_relationship_status']}", "docx_capital_relationship_status_missing")
            _expect_text(failures, "docx", docx_text, f"capital_verification_steps={expected['capital_verification_queue_count']}", "docx_capital_queue_missing")
            _expect_text(failures, "docx", docx_text, f"relationship_audit_steps={expected['relationship_audit_queue_count']}", "docx_relationship_queue_missing")
            if expected["pressure_level"] not in {"", "unknown", "none"}:
                _expect_text(failures, "docx", docx_text, expected["pressure_level"], "docx_capital_pressure_missing")
    else:
        result["docx_metadata_status"] = "not_emitted"

    return _finish_crosswalk(result, failures)


def _finish_crosswalk(result: dict[str, Any], failures: list[dict[str, str]]) -> dict[str, Any]:
    result["checked"] = bool(result.get("json_packet_checked")) and bool(result.get("agent_handoff_checked"))
    result["failure_count"] = len(failures)
    result["failures"] = failures
    return result


def _read_json_file(manifest_path: Path, filename: object) -> Any:
    text = _read_text_file(manifest_path, filename)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_text_file(manifest_path: Path, filename: object) -> str | None:
    if not filename:
        return None
    path = manifest_path.parent / str(filename)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_docx_document_xml(manifest_path: Path, filename: object) -> str | None:
    path = manifest_path.parent / str(filename)
    if not path.exists() or not path.is_file():
        return None
    try:
        with ZipFile(path) as docx:
            return docx.read("word/document.xml").decode("utf-8", errors="replace")
    except (BadZipFile, KeyError, OSError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _expect_equal(failures: list[dict[str, str]], field: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        failures.append(
            {
                "role": "capital_relationship_crosswalk",
                "field": field,
                "reason": "capital_relationship_crosswalk_mismatch",
                "expected": str(expected),
                "actual": str(actual),
            }
        )


def _expect_text(
    failures: list[dict[str, str]],
    role: str,
    content: str,
    needle: str,
    reason: str,
) -> None:
    if needle not in content:
        failures.append({"role": role, "reason": reason})


def _result(
    ok: bool,
    manifest_path: Path,
    checked: list[dict[str, Any]],
    failures: list[dict[str, str]],
    handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "report_export_bundle_verification",
        "ok": ok,
        "manifest": str(manifest_path),
        "checked_count": len(checked),
        "checked": checked,
        "agent_handoff": handoff or {
            "type": "agent_handoff_verification",
            "checked": False,
            "schema_valid": False,
            "decision_digest_present": False,
            "delivery_checklist_present": False,
            "bundle_integrity_present": False,
            "bundle_verification_present": False,
            "bundle_verification_ready_to_run": False,
            "bundle_ready_to_verify": False,
            "report_visibility_present": False,
            "premium_html_report_visibility_present": False,
            "image_evidence_inventory_present": False,
            "capital_risk_panel_present": False,
            "capital_relationship_crosswalk_present": False,
            "capital_relationship_crosswalk": {
                "type": "capital_relationship_crosswalk_verification",
                "checked": False,
                "failure_count": 0,
                "failures": [],
            },
            "verification_recipe_present": False,
            "verifier_output_fields_present": False,
            "acceptance_closure_present": False,
            "qyyjt_public_origin_present": False,
            "source_resilience_present": False,
            "relationship_graph_audit_present": False,
            "failure_count": 0,
            "failures": [],
        },
        "failure_count": len(failures),
        "failures": failures,
        "policy": "Verification covers file_manifest rows and agent-handoff routing schema; manifest and agent-handoff hashes may be intentionally excluded to avoid recursive self-hash ambiguity.",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_report_bundle(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
