#!/usr/bin/env python3
"""Host-specific desktop-agent tool adapter manifest."""
from __future__ import annotations

from typing import Any

from .release_contract import load_release_contract


SHARED_TOOLS = [
    {
        "name": "release_readiness",
        "purpose": "Check desktop-agent alpha status, runtime delivery surfaces, and latest acceptance evidence.",
        "mcp_tool": "release_readiness",
        "cli": "npx wallstreet-tieling --release",
        "api": "GET /api/release",
        "required_output_fields": [
            "type",
            "delivery_decision.status",
            "delivery_decision.remaining_variant_blocker_count",
            "delivery_decision.variant_next_gate_count",
            "delivery_closure.status",
            "delivery_closure.required_preserved_fields",
            "delivery_closure.required_verification_commands",
            "latest_acceptance_evidence.status",
            "runtime_delivery.surfaces",
        ],
    },
    {
        "name": "delivery_closure",
        "purpose": "Read the concise desktop-agent alpha delivery closure checklist without parsing the full release payload.",
        "mcp_tool": "delivery_closure",
        "cli": "npx wallstreet-tieling --delivery-closure",
        "api": "GET /api/release delivery_closure",
        "required_output_fields": [
            "type",
            "status",
            "baseline_sequence",
            "required_verification_commands",
            "required_preserved_fields",
            "not_current_release",
        ],
    },
    {
        "name": "release_preflight",
        "purpose": "Read the desktop-agent alpha local packaging go/no-go preflight, final submission blockers, and package privacy review checklist.",
        "mcp_tool": "release_preflight",
        "cli": "npx wallstreet-tieling --release-preflight",
        "api": "GET /api/release-preflight",
        "required_output_fields": [
            "type",
            "status",
            "package_candidate_ready",
            "final_submission_ready",
            "final_submission_blockers",
            "blocking_items",
            "required_verification_commands",
            "packaging_review.dry_run_command",
            "agent_handoff.safe_claim",
        ],
    },
    {
        "name": "delivery_audit",
        "purpose": "Read the single go/no-go audit that combines release readiness, preflight, preserved fields, coverage, blockers, and safe claim.",
        "mcp_tool": "delivery_audit",
        "cli": "npx wallstreet-tieling --delivery-audit",
        "api": "GET /api/delivery-audit",
        "required_output_fields": [
            "type",
            "status",
            "ready_for_local_packaging",
            "checks",
            "failed_checks",
            "coverage",
            "verification_evidence.latest_acceptance",
            "safe_claim",
            "not_current_release",
        ],
    },
    {
        "name": "objective_audit",
        "purpose": "Read the active project objective completion audit before claiming the thread goal is finished.",
        "mcp_tool": "objective_audit",
        "cli": "npx wallstreet-tieling --objective-audit",
        "api": "GET /api/objective-audit",
        "required_output_fields": [
            "type",
            "status",
            "completion_percent",
            "requirements",
            "failed_requirements",
            "release_gate.delivery_audit_status",
            "verification_evidence.latest_acceptance",
            "next_actions",
        ],
    },
    {
        "name": "connector_catalog",
        "purpose": "Discover default public sources, source admission policy, and QYYJT/public-origin work.",
        "mcp_tool": "connector_catalog",
        "cli": "npx wallstreet-tieling --connectors",
        "api": "GET /api/connectors",
        "required_output_fields": [
            "type",
            "summary.zero_config_ready",
            "summary.data_effectiveness",
            "summary.source_strengthening",
            "groups.explicit_only",
            "connectors[].data_effectiveness",
            "source_strengthening_queue",
            "source_strengthening_queue[].execution_plan",
            "source_strengthening_queue[].runtime_companion",
            "qyyjt_benchmark.summary.public_origin_execution_summary",
        ],
    },
    {
        "name": "development_requirements",
        "purpose": "Read executable P0/P1/P2/Future priorities and current-release boundaries.",
        "mcp_tool": "development_requirements",
        "cli": "npx wallstreet-tieling --requirements",
        "api": "GET /api/requirements",
        "required_output_fields": [
            "type",
            "completion_percent",
            "next_focus",
            "delivery_decision.status",
            "delivery_decision.full_product_status",
            "scope_rules.continuous_monitoring",
        ],
    },
    {
        "name": "agent_tool_adapters",
        "purpose": "Read host-specific desktop-agent sequences, fallback order, smoke commands, and packet preservation fields.",
        "mcp_tool": "agent_tool_adapters",
        "cli": "npx wallstreet-tieling --agent-tools",
        "api": "GET /api/agent-tools",
        "required_output_fields": [
            "type",
            "release_target",
            "adapters[].tool_sequence",
            "adapters[].fallback_order",
            "adapters[].required_packet_fields",
            "execution_matrix[].done_condition",
            "one_input_autorun_contract.manual_intermediate_steps_required",
            "one_input_autorun_contract.required_packet_fields",
            "required_smoke_commands",
        ],
    },
    {
        "name": "investigate_company",
        "purpose": "Run a one-click enterprise due-diligence packet with report exports and agent handoff.",
        "mcp_tool": "investigate_company",
        "cli": "npx wallstreet-tieling --investigate \"<company>\"",
        "api": "POST /api/investigate",
        "required_output_fields": [
            "type",
            "summary",
            "quality_gate",
            "evidence_ledger",
            "one_click_readiness",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.capital_risk_panel.report_visibility",
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            "qyyjt_public_origin_handoff",
            "report_exports.agent_decision_digest",
            "report_exports.premium_html",
            "report_exports.portable_html.premium_profile",
            "report_exports.print_package.delivery_checklist",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.verifier_output_fields",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
            "report_exports.directory_bundle.agent_handoff.report_visibility",
            "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
            "report_exports.directory_bundle.agent_handoff.report_visibility.image_evidence",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
            "report_exports.directory_bundle.agent_handoff.source_strengthening",
            "report_exports.directory_bundle.agent_handoff.delivery_decision",
        ],
    },
    {
        "name": "aggregate_subject",
        "purpose": "Run bounded subject aggregation for related companies, controllers, or other entities.",
        "mcp_tool": "aggregate_subject",
        "cli": "npx wallstreet-tieling --aggregate-subject \"<subject_id>\" --subject-name \"<subject_name>\"",
        "api": "POST /api/aggregate",
        "required_output_fields": ["subject", "relationship_graph", "profile"],
    },
]


HOST_OVERRIDES: dict[str, dict[str, Any]] = {
    "universal": {
        "primary_mode": "mcp_then_cli_then_rest",
        "fallback_order": ["MCP", "CLI", "REST API", "copy/paste SKILL.md"],
        "smoke_command": "npm run agent:host-smoke",
        "operator_prompt": (
            "Run release_readiness, connector_catalog, development_requirements, agent_tool_adapters, then investigate_company. "
            "Preserve JSON packet fields and report_exports instead of returning prose only."
        ),
    },
    "codex": {
        "primary_mode": "codex_plugin_mcp",
        "fallback_order": ["Codex plugin", "MCP", "CLI", "skill prompt"],
        "smoke_command": "npm run codex:mcp-smoke",
        "operator_prompt": (
            "Use the Codex plugin/MCP tools first. Keep report_exports.agent_decision_digest, "
            "directory_bundle.agent_handoff, and QYYJT public-origin handoff visible."
        ),
    },
    "claude_code": {
        "primary_mode": "repo_instructions_plus_mcp",
        "fallback_order": ["CLAUDE.md", "MCP", "CLI", "Project knowledge pack"],
        "smoke_command": "npm run agent:host-smoke",
        "operator_prompt": (
            "Load CLAUDE.md and docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md, then call MCP tools. "
            "Do not collapse the investigation_packet into a prose-only answer."
        ),
    },
    "hermes": {
        "primary_mode": "skill_prompt_plus_mcp_or_cli",
        "fallback_order": ["SKILL.md", "MCP", "CLI", "REST API"],
        "smoke_command": "npm run agent:host-smoke",
        "operator_prompt": (
            "Use SKILL.md and docs/HERMES_AGENT_SETUP.md. Prefer MCP; fall back to CLI with bounded timeouts."
        ),
    },
    "doubao_office_task_mode": {
        "primary_mode": "office_prompt_plus_cli_or_rest",
        "fallback_order": ["OFFICE_TASK_MODE_HANDOFF.md", "CLI", "REST API", "Markdown report"],
        "smoke_command": "npm run api:smoke",
        "operator_prompt": (
            "Use the Chinese office-task handoff. Return Markdown, evidence_ledger, quality_gate, "
            "report_exports.print_package, and next actions for office document generation."
        ),
    },
    "open_claude_agents": {
        "primary_mode": "open_agent_mcp_cli_rest_fallback",
        "fallback_order": ["MCP", "CLI", "REST API", "repo instructions", "prompt-only"],
        "smoke_command": "npm run agent:host-smoke",
        "operator_prompt": (
            "Follow docs/OPEN_AGENT_COMPATIBILITY.md. Preserve the full packet and use CLI/API fallback if MCP is unavailable."
        ),
    },
    "workbuddy_expert_team": {
        "primary_mode": "workbuddy_adapter_plus_skill",
        "fallback_order": ["adapters/workbuddy.py", "SKILL.md", "CLI", "REST API"],
        "smoke_command": "python -m pytest tests/unit/test_workbuddy.py -q",
        "operator_prompt": (
            "Use WorkBuddy expert-team routing for connector_catalog, release_readiness, development_requirements, "
            "and investigate_company. Keep backend architecture unchanged."
        ),
    },
}


def build_agent_tool_adapter_manifest() -> dict[str, Any]:
    """Return one machine-readable adapter contract for all current agent hosts."""
    release = load_release_contract()
    variants = release["variants"]
    adapters = []
    for host_id, variant in variants.items():
        override = HOST_OVERRIDES.get(host_id, {})
        adapters.append(_adapter_row(host_id, variant, override))
    adapters.sort(key=lambda row: (row["delivery_priority"]["rank"], row["host_id"]))
    return {
        "type": "agent_tool_adapter_manifest",
        "version": release["version"],
        "release_target": "desktop_agent_alpha",
        "primary_host_id": "codex",
        "secondary_host_ids": [
            row["host_id"]
            for row in adapters
            if row["delivery_priority"]["lane"] == "secondary"
        ],
        "host_priority_order": [row["host_id"] for row in adapters],
        "adapter_count": len(adapters),
        "all_current_release_ready": all(row["current_release_supported"] for row in adapters),
        "shared_tool_count": len(SHARED_TOOLS),
        "shared_tools": SHARED_TOOLS,
        "execution_matrix": _execution_matrix(),
        "first_run_recipe": _first_run_recipe(),
        "one_input_autorun_contract": _one_input_autorun_contract(),
        "installation_handoff": _installation_handoff(adapters),
        "adapters": adapters,
        "adapter_lookup": {
            row["host_id"]: _adapter_lookup_row(row)
            for row in adapters
        },
        "default_host_id": "codex",
        "host_ids": [row["host_id"] for row in adapters],
        "required_smoke_commands": _dedupe(row["smoke_command"] for row in adapters if row["smoke_command"]),
        "minimum_pass_gates": [
            "release_readiness returns desktop_agent_alpha_release_candidate",
            "objective_audit has no failed_requirements before the thread goal is marked complete",
            "connector_catalog exposes default public/QYYJT source metadata plus source_strengthening_queue implementation packs",
            "development_requirements exposes current-release priorities",
            "agent_tool_adapters returns execution_matrix with done conditions and failure routing",
            "investigate_company returns investigation_packet with report_exports and one_click_readiness",
            "agent host preserves JSON/Markdown/DOCX/HTML handoff fields without replacing them with prose-only output",
        ],
        "policy": (
            "Desktop-agent adapters are current-release delivery surfaces. Polished HTML, mobile apps, "
            "mini-programs, and standalone desktop apps remain later-version targets."
        ),
        "completion_audit": {
            "tool": "objective_audit",
            "cli": "npx wallstreet-tieling --objective-audit",
            "api": "GET /api/objective-audit",
            "done_condition": "status is complete and failed_requirements is empty before marking the active project objective complete.",
        },
    }


def _adapter_row(host_id: str, variant: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    entrypoints = [str(item) for item in variant.get("entrypoints", [])]
    tool_sequence = [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
    ]
    return {
        "host_id": host_id,
        "display_name": variant.get("display_name") or host_id,
        "readiness": variant.get("readiness") or "planned",
        "delivery_priority": _delivery_priority(host_id, variant),
        "project_branch_contract": _project_branch_contract(host_id, variant),
        "current_release_supported": variant.get("readiness") == "alpha",
        "primary_mode": override.get("primary_mode") or "mcp_or_cli",
        "entrypoints": entrypoints,
        "packaging": list(variant.get("packaging") or []),
        "required_capabilities": list(variant.get("required_capabilities") or []),
        "tool_sequence": tool_sequence,
        "tool_sequence_done_condition": "All six baseline tools return machine-readable JSON before host-specific formatting.",
        "execution_matrix_ref": "agent_tool_adapter_manifest.execution_matrix",
        "shared_tools": [tool["name"] for tool in SHARED_TOOLS],
        "fallback_order": list(override.get("fallback_order") or ["MCP", "CLI", "REST API", "prompt-only"]),
        "smoke_command": override.get("smoke_command") or "npm run agent:host-smoke",
        "install_handoff": _host_install_handoff(
            host_id,
            entrypoints,
            override.get("smoke_command") or "npm run agent:host-smoke",
        ),
        "operator_prompt": override.get("operator_prompt") or "",
        "required_packet_fields": [
            "quality_gate",
            "evidence_ledger",
            "connector_catalog.groups.explicit_only",
            "connector_catalog.connectors[].data_effectiveness",
            "connector_catalog.source_strengthening_queue",
            "connector_catalog.source_strengthening_queue[].implementation_pack",
            "connector_catalog.source_strengthening_queue[].runtime_companion",
            "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary",
            "one_click_readiness",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.capital_risk_panel.report_visibility",
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            "qyyjt_public_origin_handoff",
            "qyyjt_public_origin_handoff.agent_autorun",
            "report_exports.agent_decision_digest",
            "report_exports.premium_html",
            "report_exports.portable_html.premium_profile",
            "report_exports.print_package",
            "report_exports.directory_bundle",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.directory_bundle.verifier_output_fields",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
            "report_exports.directory_bundle.agent_handoff.report_visibility",
            "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
            "report_exports.directory_bundle.agent_handoff.report_visibility.image_evidence",
            "report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
            "report_exports.directory_bundle.agent_handoff.source_strengthening",
            "report_exports.directory_bundle.agent_handoff.delivery_decision",
        ],
        "report_outputs": ["markdown", "json_packet", "portable_html", "premium_html", "docx_red_head", "agent_handoff"],
        "trust_boundaries": [
            "public, licensed, or user-authorized evidence only",
            "lead-only rows remain leads until admission gates pass",
            "continuous monitoring is not current-release delivery",
            "polished immersive HTML is not required for desktop-agent alpha",
        ],
        "next_gate": list(variant.get("next_gate") or []),
    }


def _adapter_lookup_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return compact host selection data for low-context agent hosts."""
    return {
        "display_name": row["display_name"],
        "current_release_supported": row["current_release_supported"],
        "primary_mode": row["primary_mode"],
        "delivery_priority": row["delivery_priority"],
        "project_branch_id": row["project_branch_contract"]["branch_id"],
        "project_branch_type": row["project_branch_contract"]["branch_type"],
        "install_command": row["install_handoff"]["install_command"],
        "config_files": row["install_handoff"]["config_files"],
        "start_command": row["install_handoff"]["start_command"],
        "fallback_order": row["fallback_order"],
        "smoke_command": row["smoke_command"],
        "tool_sequence": row["tool_sequence"],
        "execution_matrix_ref": row["execution_matrix_ref"],
        "required_packet_field_count": len(row["required_packet_fields"]),
        "report_outputs": row["report_outputs"],
    }


def _installation_handoff(adapters: list[dict[str, Any]]) -> dict[str, Any]:
    """Host-neutral install and first-run contract for desktop agents."""
    return {
        "type": "desktop_agent_installation_handoff",
        "release_target": "desktop_agent_alpha",
        "package_name": "wallstreet-tieling",
        "default_install_command": "npm install -g wallstreet-tieling",
        "default_mcp_command": "npx -y wallstreet-tieling --mcp",
        "default_cli_smoke": "npx wallstreet-tieling --release",
        "offline_fixture_smoke": (
            'npx wallstreet-tieling --investigate "Demo Install Smoke Co., Ltd." --offline-fixture'
        ),
        "required_local_runtime_env": [
            "WST_PYTHON optional: set when the host cannot find Python automatically",
            "WST_MCP_TIMEOUT_MS optional: increase MCP timeout for slow hosts",
            "WST_QUERY_TIMEOUT_SECONDS optional: bound retrieval tasks",
            "npm_config_cache optional: keep npm cache in a writable local directory",
        ],
        "verification_commands": [
            "npm run agent:host-smoke",
            "npm run codex:mcp-smoke",
            "npm run api:smoke",
            "npm run release:privacy-scan",
            "npm run release:preflight",
            "npm run delivery:audit",
            "npm run objective:audit",
            "npm pack --dry-run --json",
        ],
        "host_matrix": [
            {
                "host_id": adapter["host_id"],
                "display_name": adapter["display_name"],
                "install_command": adapter["install_handoff"]["install_command"],
                "config_files": adapter["install_handoff"]["config_files"],
                "start_command": adapter["install_handoff"]["start_command"],
                "smoke_command": adapter["install_handoff"]["smoke_command"],
                "done_condition": adapter["install_handoff"]["done_condition"],
            }
            for adapter in adapters
        ],
        "failure_routing": [
            {
                "symptom": "npx or npm cannot write cache",
                "action": "Set npm_config_cache to a writable local cache and retry the same command.",
            },
            {
                "symptom": "Python child process unavailable",
                "action": "Set WST_PYTHON to a known Python runtime; release metadata fallback is not enough for final investigation output.",
            },
            {
                "symptom": "MCP startup or tool call timeout",
                "action": "Increase WST_MCP_TIMEOUT_MS and fall back to CLI/API while preserving packet fields.",
            },
            {
                "symptom": "host returns prose-only answer",
                "action": "Rerun agent_tool_adapters, select the host adapter, and require the listed packet fields before summarizing.",
            },
        ],
        "done_condition": (
            "Host can run release_readiness, agent_tool_adapters, and one offline-fixture "
            "investigate_company path while preserving delivery_decision and directory_bundle.agent_handoff."
        ),
        "policy": (
            "Installation handoff is a local desktop-agent alpha contract. It does not imply marketplace approval, "
            "final polished HTML readiness, or live-source guarantees."
        ),
    }


def _project_branch_contract(host_id: str, variant: dict[str, Any]) -> dict[str, Any]:
    branch = dict(variant.get("project_branch") or {})
    return {
        "type": "desktop_agent_project_branch",
        "branch_id": branch.get("branch_id") or host_id,
        "branch_type": branch.get("branch_type") or "host_adapter",
        "owns": list(branch.get("owns") or ["host-specific adapter instructions"]),
        "must_not_touch": list(branch.get("must_not_touch") or ["shared release/runtime contracts"]),
        "shared_runtime_contract": list(
            branch.get("shared_runtime_contract")
            or [
                "release_readiness",
                "connector_catalog",
                "development_requirements",
                "agent_tool_adapters",
                "investigate_company",
            ]
        ),
        "done_condition": (
            "Branch-specific host behavior is exposed without forking the shared runtime truth source, "
            "and the baseline tool sequence still returns the full investigation packet."
        ),
    }


def _delivery_priority(host_id: str, variant: dict[str, Any]) -> dict[str, Any]:
    priority = dict(variant.get("delivery_priority") or {})
    lane = str(priority.get("lane") or ("primary" if host_id == "codex" else "supporting"))
    try:
        rank = int(priority.get("rank", 1 if host_id == "codex" else 50))
    except (TypeError, ValueError):
        rank = 50
    return {
        "type": "desktop_agent_delivery_priority",
        "lane": lane,
        "rank": rank,
        "reason": str(priority.get("reason") or "Supporting desktop-agent host adaptation."),
        "depends_on": _string_list(priority.get("depends_on")),
    }


def _host_install_handoff(host_id: str, entrypoints: list[str], smoke_command: str) -> dict[str, Any]:
    """Return install/start data that a host can execute without reading prose docs."""
    install_command = "npm install -g wallstreet-tieling"
    start_command = "npx -y wallstreet-tieling --mcp"
    if host_id == "codex":
        install_command = "npx skills add Dear-Ded/wallstreet-tieling -g -y"
        start_command = "npx -y wallstreet-tieling --mcp"
    elif host_id == "workbuddy_expert_team":
        install_command = "Install from the repo skill pack, then load adapters/workbuddy.py as the workbuddy_expert_team project branch"
        start_command = "Use WorkBuddy project-branch routing for connector_catalog, release_readiness, agent_tool_adapters, and investigate_company"
    elif host_id == "doubao_office_task_mode":
        install_command = "Use docs/OFFICE_TASK_MODE_HANDOFF.md plus npx wallstreet-tieling CLI/API fallback"
        start_command = 'npx wallstreet-tieling --investigate "Demo Office Task Smoke Co., Ltd." --offline-fixture'

    return {
        "type": "host_install_handoff",
        "host_id": host_id,
        "install_command": install_command,
        "config_files": entrypoints,
        "start_command": start_command,
        "smoke_command": smoke_command,
        "minimum_commands": [
            "npx wallstreet-tieling --release",
            "npx wallstreet-tieling --agent-tools",
            'npx wallstreet-tieling --investigate "Demo Install Smoke Co., Ltd." --offline-fixture',
        ],
        "done_condition": (
            "release_readiness returns desktop_agent_alpha_release_candidate, agent_tool_adapters exposes this host, "
            "and investigate_company returns an investigation_packet with report_exports.directory_bundle.agent_handoff."
        ),
        "fallback_policy": "If MCP is blocked, use CLI, then REST API, then prompt-only handoff without dropping packet fields.",
    }


def _execution_matrix() -> list[dict[str, Any]]:
    """Agent-run playbook with explicit done conditions and failure routing."""
    return [
        {
            "phase": "release_gate",
            "tool": "release_readiness",
            "purpose": "Confirm this is a desktop-agent alpha run and separate alpha readiness from final-product readiness.",
            "done_condition": "delivery_decision.status is desktop_agent_alpha_release_candidate and runtime_delivery.release_blocking_surface_count is 0.",
            "required_fields": [
                "delivery_decision.status",
                "delivery_decision.full_product_status",
                "runtime_delivery.release_blocking_surface_count",
                "latest_acceptance_evidence.status",
            ],
            "failure_routing": "Stop packaging claims; inspect delivery_closure.required_verification_commands before continuing.",
        },
        {
            "phase": "delivery_audit",
            "tool": "delivery_audit",
            "purpose": "Read the single combined go/no-go result before host-specific execution or report formatting.",
            "done_condition": "status is pass, ready_for_local_packaging is true, and failed_checks is empty.",
            "required_fields": [
                "status",
                "ready_for_local_packaging",
                "failed_checks",
                "coverage",
                "verification_evidence.latest_acceptance",
                "safe_claim",
            ],
            "failure_routing": "Use failed_checks and blocking_items as the next task list; do not claim delivery readiness from partial evidence.",
        },
        {
            "phase": "source_catalog",
            "tool": "connector_catalog",
            "purpose": "Load default public sources, admission policy, and QYYJT/public-origin reconstruction queues.",
            "done_condition": "summary.zero_config_ready includes default_public_intel and qyyjt_benchmark.summary.public_origin_execution_summary.p0_count is present.",
            "required_fields": [
                "summary.zero_config_ready",
                "summary.data_effectiveness",
                "summary.admission_gate_summary",
                "groups.explicit_only",
                "connectors[].data_effectiveness",
                "summary.source_strengthening",
                "source_strengthening_queue",
                "source_strengthening_queue[].execution_plan",
                "source_strengthening_queue[].runtime_companion",
                "qyyjt_benchmark.summary.public_origin_execution_summary",
            ],
            "failure_routing": "Use fixture mode for local validation and keep failed/blocked sources in operator work instead of treating missing data as clean.",
        },
        {
            "phase": "priority_board",
            "tool": "development_requirements",
            "purpose": "Read executable P0/P1/P2 boundaries so agent work stays on runtime delivery rather than decorative UI or future apps.",
            "done_condition": "delivery_decision.current_target is desktop_agent_alpha and next_focus contains current P0/P1 lanes.",
            "required_fields": [
                "completion_percent",
                "delivery_decision.current_target",
                "delivery_decision.full_product_status",
                "next_focus",
            ],
            "failure_routing": "Do not infer roadmap from prose; rerun the requirements tool or fall back to PROJECT_TASKBOARD.md.",
        },
        {
            "phase": "host_binding",
            "tool": "agent_tool_adapters",
            "purpose": "Select host-specific fallback order and packet-preservation contract before investigation output is formatted.",
            "done_condition": "The selected adapter has current_release_supported=true, a six-tool sequence, fallback_order, smoke_command, and required_packet_fields.",
            "required_fields": [
                "adapters[].host_id",
                "adapters[].current_release_supported",
                "adapters[].delivery_priority",
                "adapters[].fallback_order",
                "adapters[].required_packet_fields",
                "primary_host_id",
                "host_priority_order",
                "required_smoke_commands",
            ],
            "failure_routing": "Use universal adapter and CLI fallback; never return a prose-only investigation summary.",
        },
        {
            "phase": "investigation_run",
            "tool": "investigate_company",
            "purpose": "Generate the one-click packet and preserve report, graph, source, QYYJT, capital, relationship, and verifier handoff fields.",
            "done_condition": "Packet type is investigation_packet and report_exports.directory_bundle.agent_handoff plus one_click_readiness.acceptance_closure_summary are present.",
            "required_fields": [
                "type",
                "quality_gate",
                "evidence_ledger",
                "enterprise_cognition.relationship_resolution_v1",
                "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
                "one_click_readiness.acceptance_closure_summary",
                "qyyjt_public_origin_handoff.section_work_orders",
                "report_exports.directory_bundle.agent_handoff",
                "report_exports.directory_bundle.verifier_output_fields",
            ],
            "failure_routing": "Return the failed source diagnostics and operator_work_queue; do not hide gaps behind a polished narrative.",
        },
        {
            "phase": "followup_expansion",
            "tool": "aggregate_subject",
            "purpose": "Only after the main packet identifies a concrete related subject, expand a controller, counterparty, or relationship node.",
            "done_condition": "subject, relationship_graph, and profile are present for the requested subject_id.",
            "required_fields": ["subject", "relationship_graph", "profile"],
            "failure_routing": "Keep this as a follow-up task; do not block the main investigation packet on aggregate_subject.",
            "optional": True,
        },
    ]


def _first_run_recipe() -> dict[str, Any]:
    """Compact copyable recipe for agents that only consume one manifest field."""
    return {
        "type": "desktop_agent_first_run_recipe",
        "sequence": [
            "release_readiness",
            "delivery_audit",
            "connector_catalog",
            "development_requirements",
            "agent_tool_adapters",
            "investigate_company",
        ],
        "optional_followup": ["aggregate_subject"],
        "preserve_before_summarizing": [
            "quality_gate",
            "evidence_ledger",
            "connector_catalog.groups.explicit_only",
            "connector_catalog.connectors[].data_effectiveness",
            "connector_catalog.source_strengthening_queue",
            "connector_catalog.source_strengthening_queue[].implementation_pack",
            "connector_catalog.source_strengthening_queue[].execution_plan",
            "connector_catalog.source_strengthening_queue[].runtime_companion",
            "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary",
            "one_click_readiness",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.capital_risk_panel.report_visibility",
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            "qyyjt_public_origin_handoff",
            "qyyjt_public_origin_handoff.agent_autorun",
            "report_exports.agent_decision_digest",
            "report_exports.premium_html",
            "report_exports.portable_html.premium_profile",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
            "report_exports.directory_bundle.agent_handoff.report_visibility",
            "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
            "report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
            "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
            "report_exports.directory_bundle.agent_handoff.source_strengthening",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.directory_bundle.verifier_output_fields",
        ],
        "verification_commands": [
            "npm run api:smoke",
            "npm run codex:mcp-smoke",
            "npm run agent:host-smoke",
            "npm run release:privacy-scan",
            "npm run release:preflight",
            "npm run delivery:audit",
            "npm run objective:audit",
            "npm pack --dry-run --json",
        ],
        "do_not": [
            "Do not replace the packet with prose-only output.",
            "Do not treat source failures or coverage gaps as clean findings.",
            "Do not drop connector_catalog.groups.explicit_only; it is where advanced authorized sources are exposed.",
            "Do not drop connector_catalog.source_strengthening_queue before assigning source-hardening follow-up work.",
            "Do not promote lead-only QYYJT/public-origin rows into facts before admission gates pass.",
            "Do not claim final product launch readiness from desktop-agent alpha readiness.",
        ],
    }


def _one_input_autorun_contract() -> dict[str, Any]:
    """Contract proving hosts can run after one subject input."""
    return {
        "type": "one_input_autorun_contract",
        "subject_input": {
            "accepted_fields": ["company_name", "company", "message"],
            "minimum_user_input": "One subject name or unified social credit identifier.",
            "manual_intermediate_steps_required": False,
        },
        "autorun_sequence": [
            {
                "step": "release_readiness",
                "input_source": "none",
                "purpose": "Confirm desktop-agent alpha runtime readiness and current-release boundary.",
                "blocks_autorun_if_missing": True,
            },
            {
                "step": "delivery_audit",
                "input_source": "none",
                "purpose": "Read the combined go/no-go audit before spending work on host-specific formatting.",
                "blocks_autorun_if_missing": False,
            },
            {
                "step": "connector_catalog",
                "input_source": "none",
                "purpose": "Load default public-source plan, explicit-only advanced sources, and QYYJT/public-origin mapping metadata.",
                "blocks_autorun_if_missing": True,
            },
            {
                "step": "development_requirements",
                "input_source": "none",
                "purpose": "Keep the host on runtime delivery lanes instead of future HTML/app work.",
                "blocks_autorun_if_missing": False,
            },
            {
                "step": "agent_tool_adapters",
                "input_source": "host_id",
                "purpose": "Select host fallback order and packet-preservation requirements.",
                "blocks_autorun_if_missing": True,
            },
            {
                "step": "investigate_company",
                "input_source": "subject_input.company_name",
                "purpose": "Run the executable due-diligence packet and report-export pipeline.",
                "blocks_autorun_if_missing": True,
            },
        ],
        "default_runtime_options": {
            "depth": "standard",
            "query_timeout_seconds": 20,
            "retrieval_concurrency": 4,
            "fanout_rounds": 1,
            "max_fanout_tasks": 24,
            "offline_fixture_for_smoke": True,
        },
        "required_packet_fields": [
            "type",
            "summary",
            "quality_gate",
            "evidence_ledger",
            "one_click_readiness",
            "one_click_readiness.source_resilience_recommended_step",
            "one_click_readiness.capital_risk_panel",
            "enterprise_cognition.relationship_resolution_v1",
            "qyyjt_public_origin_handoff",
            "report_exports",
            "report_exports.agent_decision_digest",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.agent_handoff.report_visibility",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
            "report_exports.directory_bundle.agent_handoff.source_strengthening",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.directory_bundle.verifier_output_fields",
        ],
        "operator_intervention_only_when": [
            "The subject input is absent or ambiguous after host-side parsing.",
            "A required authorized source needs credentials, CAPTCHA, payment, or account consent.",
            "The output directory cannot be written by the host.",
            "The host cannot execute MCP, CLI, or REST fallback paths.",
        ],
        "host_done_condition": (
            "After one subject input, the host returns the full investigation_packet plus report_exports and "
            "directory_bundle.agent_handoff without asking the user to manually run intermediate source, graph, "
            "capital-risk, QYYJT, or report-generation steps."
        ),
        "do_not": [
            "Do not ask the user to manually run release_readiness, connector_catalog, or agent_tool_adapters.",
            "Do not ask for extra clicks after a valid subject input unless an operator_intervention_only_when condition applies.",
            "Do not reduce source failures, relationship graph queues, capital risk, QYYJT gaps, or report export paths to prose.",
            "Do not enable explicit-only advanced sources without user/deployment authorization.",
        ],
    }


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    item = str(value).strip()
    return [item] if item else []
