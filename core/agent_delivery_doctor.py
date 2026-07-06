#!/usr/bin/env python3
"""Install-time desktop-agent delivery self-check."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_delivery_packet import build_agent_delivery_packet
from .agent_tool_adapters import build_agent_tool_adapter_manifest
from .release_contract import release_readiness_brief
from .source_preflight import build_source_preflight


PROJECT_ROOT = Path(__file__).resolve().parent.parent


REQUIRED_FILES = [
    "SKILL.md",
    "CLAUDE.md",
    "bin/cli.js",
    "lib/mcp-server.js",
    "api/server.py",
    "core/agent_delivery_packet.py",
    "core/agent_delivery_doctor.py",
    "core/report_delivery_targets.py",
    "core/agent_tool_adapters.py",
    "core/release_contract.py",
    "core/source_preflight.py",
    "docs/API_CONTRACTS.md",
    "docs/AGENT_HOST_SMOKE_CHECKLIST.md",
    "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
    "docs/DESKTOP_AGENT_HOSTS.md",
    "deploy/mcp-server.json",
    "release/variants.yaml",
    "tools/agent-host-smoke.js",
    "tools/agent-release-final-smoke.js",
    "tools/agent-package-install-smoke.js",
    "tools/codex-mcp-smoke.js",
    "tools/api-smoke.py",
]

FINAL_PRODUCT_REQUIREMENTS = [
    "complete due-diligence coverage without major functional omissions",
    "anthropomorphic 13-role interaction surface preserved across hosts",
    "print-ready DOCX report with official-document styling, tables, charts, and image evidence",
    "polished immersive HTML report without reducing investigation findings",
]


def build_agent_delivery_doctor(host_id: str | None = None) -> dict[str, Any]:
    """Return a machine-readable readiness self-check for installed agents."""
    release = release_readiness_brief()
    delivery = build_agent_delivery_packet(host_id)
    adapters = build_agent_tool_adapter_manifest()
    source_preflight = build_source_preflight()
    verifier_contract = release.get("delivery_closure", {}).get("report_bundle_verifier_contract", {})
    file_checks = _file_checks(REQUIRED_FILES)
    tool_names = {tool.get("name") for tool in adapters.get("shared_tools", [])}
    required_tools = {
        "agent_delivery_packet",
        "agent_delivery_doctor",
        "report_delivery_targets",
        "release_readiness",
        "delivery_closure",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "source_preflight",
        "investigate_company",
        "aggregate_subject",
        "verify_report_bundle",
    }
    missing_tools = sorted(required_tools - tool_names)
    required_commands = _dedupe(delivery.get("verification", {}).get("required_commands", []))
    command_checks = [
        _command_check(command)
        for command in required_commands
    ]
    blockers = []
    if not delivery.get("release_candidate"):
        blockers.append("agent_delivery_packet.release_candidate_not_true")
    if release.get("delivery_decision", {}).get("status") != "desktop_agent_alpha_release_candidate":
        blockers.append("release.delivery_decision_not_release_candidate")
    if int(release.get("runtime_delivery", {}).get("release_blocking_surface_count") or 0) != 0:
        blockers.append("runtime_delivery.release_blocking_surface_count_nonzero")
    if missing_tools:
        blockers.append("agent_tool_adapters.shared_tools_missing")
    if file_checks["missing"]:
        blockers.append("required_package_files_missing")

    return {
        "type": "agent_delivery_doctor",
        "version": release.get("version", "0.5.0"),
        "release_target": "desktop_agent_alpha",
        "host_filter": host_id or "all",
        "status": "pass" if not blockers else "fail",
        "release_candidate": bool(delivery.get("release_candidate")) and not blockers,
        "blockers": blockers,
        "summary": {
            "host_count": delivery.get("host_count", 0),
            "shared_tool_count": len(tool_names),
            "missing_tool_count": len(missing_tools),
            "required_file_count": file_checks["required_count"],
            "missing_file_count": len(file_checks["missing"]),
            "required_command_count": len(command_checks),
            "runtime_blocking_surface_count": release.get("runtime_delivery", {}).get("release_blocking_surface_count", 0),
            "full_product_status": release.get("delivery_decision", {}).get("full_product_status"),
            "source_preflight_status": source_preflight.get("status"),
            "source_preflight_deep_mode_status": source_preflight.get("deep_mode_status"),
            "source_preflight_ready_to_run": source_preflight.get("summary", {}).get("ready_to_run"),
            "report_bundle_verifier_required_check_count": len(
                verifier_contract.get("required_agent_handoff_checks", [])
                if isinstance(verifier_contract, dict)
                else []
            ),
        },
        "checks": {
            "release_decision": {
                "status": release.get("delivery_decision", {}).get("status"),
                "full_product_status": release.get("delivery_decision", {}).get("full_product_status"),
                "runtime_blocking_surface_count": release.get("delivery_decision", {}).get("runtime_blocking_surface_count"),
                "remaining_variant_blocker_count": release.get("delivery_decision", {}).get("remaining_variant_blocker_count"),
            },
            "agent_delivery_packet": {
                "status": delivery.get("status"),
                "host_count": delivery.get("host_count"),
                "first_command": (delivery.get("start_here", {}).get("first_commands") or [""])[0],
                "mcp_entrypoint_present": "agent_delivery_packet" in delivery.get("start_here", {}).get("mcp_sequence", []),
                "api_entrypoint_present": "GET /api/agent-delivery" in delivery.get("start_here", {}).get("api_sequence", []),
            },
            "shared_tools": {
                "required": sorted(required_tools),
                "missing": missing_tools,
            },
            "package_files": file_checks,
            "source_preflight": source_preflight,
            "report_bundle_verifier_contract": verifier_contract if isinstance(verifier_contract, dict) else {},
            "commands": command_checks,
        },
        "next_actions": _next_actions(blockers, file_checks["missing"], missing_tools),
        "scope_policy": {
            "current_delivery": "desktop_agent_alpha_install_readiness",
            "does_not_certify": [
                "final polished HTML launch",
                "mobile app, mini-program, or standalone desktop app launch",
                "marketplace approval",
                "live data coverage for every jurisdiction or licensed source",
            ],
            "must_not_shrink_final_product": FINAL_PRODUCT_REQUIREMENTS,
        },
    }


def _file_checks(paths: list[str]) -> dict[str, Any]:
    present = []
    missing = []
    for item in paths:
        if (PROJECT_ROOT / item).exists():
            present.append(item)
        else:
            missing.append(item)
    return {
        "required_count": len(paths),
        "present_count": len(present),
        "missing_count": len(missing),
        "present": present,
        "missing": missing,
    }


def _command_check(command: str) -> dict[str, Any]:
    return {
        "command": command,
        "required": True,
        "status": "listed",
        "execution_policy": "run_on_release_machine_before_stronger_delivery_claims",
    }


def _next_actions(blockers: list[str], missing_files: list[str], missing_tools: list[str]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if missing_files:
        actions.append({
            "id": "restore_required_package_files",
            "priority": "P0",
            "status": "blocked",
            "action": "Restore missing package/runtime files before publishing the agent package.",
            "items": missing_files,
        })
    if missing_tools:
        actions.append({
            "id": "restore_shared_agent_tools",
            "priority": "P0",
            "status": "blocked",
            "action": "Expose all required shared tools in the agent adapter manifest.",
            "items": missing_tools,
        })
    if blockers and not actions:
        actions.append({
            "id": "inspect_release_decision",
            "priority": "P0",
            "status": "blocked",
            "action": "Inspect /api/release and /api/agent-delivery; runtime blockers remain.",
            "items": blockers,
        })
    if not actions:
        actions.append({
            "id": "run_final_release_gates",
            "priority": "P0",
            "status": "ready",
            "action": "Run npm run acceptance, npm run release:agent-smoke, npm run agent:host-smoke, npm run api:smoke, and npm pack --dry-run --json before publishing.",
            "items": [],
        })
    return actions


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
