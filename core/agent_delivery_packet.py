#!/usr/bin/env python3
"""Single desktop-agent delivery packet for runtime handoff."""
from __future__ import annotations

from typing import Any

from .agent_tool_adapters import build_agent_tool_adapter_manifest
from .release_contract import release_readiness_brief


def build_agent_delivery_packet(host_id: str | None = None) -> dict[str, Any]:
    """Return a compact, executable package that a desktop agent can start from."""
    release = release_readiness_brief()
    adapters = build_agent_tool_adapter_manifest()
    closure = release.get("delivery_closure", {})
    decision = release.get("delivery_decision", {})
    latest_acceptance = release.get("latest_acceptance_evidence", {})
    selected_adapters = _select_adapters(adapters.get("adapters", []), host_id)
    runtime_delivery = release.get("runtime_delivery", {})
    smoke_commands = _dedupe(
        list(adapters.get("required_smoke_commands", []))
        + list(closure.get("required_verification_commands", []))
    )
    release_candidate = (
        decision.get("status") == "desktop_agent_alpha_release_candidate"
        and bool(adapters.get("all_current_release_ready"))
        and int(runtime_delivery.get("release_blocking_surface_count") or 0) == 0
    )

    return {
        "type": "agent_delivery_packet",
        "version": release.get("version", "0.5.0"),
        "release_target": "desktop_agent_alpha",
        "status": "ready_for_desktop_agent_alpha" if release_candidate else "needs_runtime_closure",
        "host_filter": host_id or "all",
        "release_candidate": release_candidate,
        "delivery_decision": decision,
        "latest_acceptance_evidence": {
            "status": latest_acceptance.get("status"),
            "command": latest_acceptance.get("command"),
            "observed_at": latest_acceptance.get("observed_at"),
            "python_tests_passed": latest_acceptance.get("python_tests_passed"),
            "python_tests_skipped": latest_acceptance.get("python_tests_skipped"),
            "supporting_commands": latest_acceptance.get("supporting_commands", []),
        },
        "start_here": {
            "operator_sequence": closure.get("baseline_sequence", []),
            "first_commands": [
                "npx wallstreet-tieling --agent-delivery",
                "npx wallstreet-tieling --release",
                "npx wallstreet-tieling --agent-tools",
                "npx wallstreet-tieling --report-targets",
                "npx wallstreet-tieling --investigate \"<company>\" --offline-fixture",
            ],
            "mcp_sequence": [
                "agent_delivery_packet",
                "release_readiness",
                "report_delivery_targets",
                "connector_catalog",
                "source_preflight",
                "development_requirements",
                "agent_tool_adapters",
                "investigate_company",
            ],
            "api_sequence": [
                "GET /api/agent-delivery",
                "GET /api/release",
                "GET /api/report-targets",
                "GET /api/connectors",
                "GET /api/source-preflight",
                "GET /api/requirements",
                "GET /api/agent-tools",
                "POST /api/investigate",
            ],
            "followup_tools": closure.get("followup_tools", []),
        },
        "host_count": len(selected_adapters),
        "hosts": [_host_delivery_row(adapter) for adapter in selected_adapters],
        "shared_tools": adapters.get("shared_tools", []),
        "field_preservation_contract": {
            "required_preserved_fields": closure.get("required_preserved_fields", []),
            "minimum_pass_gates": adapters.get("minimum_pass_gates", []),
            "advanced_autopilot_contract": closure.get("advanced_autopilot_contract", {}),
            "do_not_collapse_to_prose_only": [
                "delivery_decision",
                "quality_gate",
                "evidence_ledger",
                "one_click_readiness",
                "runtime_autopilot",
                "runtime_autopilot.source_runbook",
                "source_preflight",
                "source_preflight.no_prompt_contract",
                "qyyjt_public_origin_handoff",
                "report_exports",
                "report_exports.directory_bundle.agent_handoff",
                "report_exports.directory_bundle.agent_handoff.deep_autopilot_execution_plan",
                "report_exports.directory_bundle.agent_handoff.deep_autopilot_source_runbook",
            ],
        },
        "verification": {
            "required_commands": smoke_commands,
            "advanced_autopilot_contract": closure.get("advanced_autopilot_contract", {}),
            "submission_evidence_contract": closure.get("submission_evidence_contract", {}),
            "report_bundle_verifier_contract": closure.get("report_bundle_verifier_contract", {}),
            "package_gate": "npm pack --dry-run --json",
            "full_acceptance_gate": "npm run acceptance",
            "focused_runtime_gate": runtime_delivery.get("focused_test_command", ""),
            "runtime_blocking_surface_count": runtime_delivery.get("release_blocking_surface_count", 0),
        },
        "boundaries": {
            "not_current_release": closure.get("not_current_release", []),
            "public_or_authorized_data_only": True,
            "continuous_monitoring_current_release": False,
            "full_product_status": decision.get("full_product_status", "not_final_release_ready"),
        },
        "submission_open_items": closure.get("open_submission_items", []),
        "policy": (
            "This packet is the agent-first handoff surface. Desktop agents should read it before "
            "formatting outputs, preserve machine-readable fields, and use investigate_company for work."
        ),
    }


def _select_adapters(adapters: list[dict[str, Any]], host_id: str | None) -> list[dict[str, Any]]:
    if not host_id:
        return adapters
    selected = [adapter for adapter in adapters if adapter.get("host_id") == host_id]
    return selected or adapters


def _host_delivery_row(adapter: dict[str, Any]) -> dict[str, Any]:
    return {
        "host_id": adapter.get("host_id", ""),
        "display_name": adapter.get("display_name", ""),
        "primary_mode": adapter.get("primary_mode", ""),
        "current_release_supported": bool(adapter.get("current_release_supported")),
        "tool_sequence": adapter.get("tool_sequence", []),
        "fallback_order": adapter.get("fallback_order", []),
        "smoke_command": adapter.get("smoke_command", ""),
        "operator_prompt": adapter.get("operator_prompt", ""),
        "required_packet_fields": adapter.get("required_packet_fields", []),
        "report_outputs": adapter.get("report_outputs", []),
    }


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
