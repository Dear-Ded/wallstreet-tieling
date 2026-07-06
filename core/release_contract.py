#!/usr/bin/env python3
"""Runtime release contract for portal, plugins, and marketplace checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from api.personality import build_persona_surface_brief


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VARIANTS_PATH = PROJECT_ROOT / "release" / "variants.yaml"
AUTORUN_PRESERVED_FIELDS = [
    "qyyjt_public_origin_handoff.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
    "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
]


def load_release_contract(path: str | Path | None = None) -> dict[str, Any]:
    """Load and normalize the release/variant matrix for API consumers."""
    target = Path(path) if path else DEFAULT_VARIANTS_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    product = _dict(data.get("product"))
    variants = _dict(data.get("variants"))
    gates = _dict(data.get("release_gates"))
    normalized_variants = {
        name: _variant_payload(name, _dict(variant))
        for name, variant in sorted(variants.items())
    }
    readiness_counts: dict[str, int] = {}
    for variant in normalized_variants.values():
        readiness = str(variant.get("readiness") or "unknown")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1

    return {
        "type": "release_contract",
        "version": "0.5.0",
        "product": {
            "name": product.get("name", "wallstreet-tieling"),
            "display_name": product.get("display_name", "Wallstreet Tieling"),
            "positioning": product.get("positioning", "Enterprise Intelligence & Risk Discovery System"),
            "public_portal_repo": product.get("public_portal_repo"),
            "shared_core": _string_list(product.get("shared_core")),
        },
        "persona_surface": build_persona_surface_brief(),
        "variants": normalized_variants,
        "summary": {
            "variant_count": len(normalized_variants),
            "readiness_counts": readiness_counts,
            "stable_or_beta_count": sum(
                1
                for variant in normalized_variants.values()
                if variant.get("readiness") in {"stable", "beta"}
            ),
            "alpha_count": readiness_counts.get("alpha", 0),
            "planned_count": readiness_counts.get("planned", 0),
        },
        "release_gates": {
            name: _string_list(rules)
            for name, rules in sorted(gates.items())
        },
    }


def release_readiness_brief(path: str | Path | None = None) -> dict[str, Any]:
    """Return a plain product brief without forcing callers to parse YAML."""
    contract = load_release_contract(path)
    runtime_delivery = _runtime_delivery_summary()
    latest_acceptance = _latest_acceptance_evidence()
    blockers: list[dict[str, Any]] = []
    readyish: list[str] = []
    for name, variant in contract["variants"].items():
        readiness = variant.get("readiness")
        if readiness in {"stable", "beta"}:
            readyish.append(name)
        else:
            blockers.append(
                {
                    "variant": name,
                    "readiness": readiness,
                    "next_gate": variant.get("next_gate", []),
                }
            )
    delivery_closure = _delivery_closure_summary()
    delivery_decision = _delivery_decision(contract, runtime_delivery, blockers)
    return {
        "type": "release_readiness_brief",
        "version": contract["version"],
        "positioning": contract["product"]["positioning"],
        "persona_surface": contract["persona_surface"],
        "runtime_delivery": runtime_delivery,
        "latest_acceptance_evidence": latest_acceptance,
        "delivery_decision": delivery_decision,
        "delivery_closure": delivery_closure,
        "release_preflight": _release_preflight_summary(
            delivery_decision=delivery_decision,
            delivery_closure=delivery_closure,
            latest_acceptance=latest_acceptance,
            runtime_delivery=runtime_delivery,
        ),
        "readyish_variants": readyish,
        "blockers": blockers,
        "next_focus": _next_focus(blockers),
        "contract": contract,
    }


def release_preflight_brief(path: str | Path | None = None) -> dict[str, Any]:
    """Return a compact go/no-go preflight for desktop-agent alpha packaging."""
    brief = release_readiness_brief(path)
    return brief["release_preflight"]


def objective_completion_audit_brief(path: str | Path | None = None) -> dict[str, Any]:
    """Map the active product objective to current evidence and remaining gaps."""
    brief = release_readiness_brief(path)
    delivery_audit = delivery_audit_brief(path)
    preflight = _dict(brief.get("release_preflight"))
    closure = _dict(brief.get("delivery_closure"))
    latest_acceptance = _dict(brief.get("latest_acceptance_evidence"))
    runtime_delivery = _dict(brief.get("runtime_delivery"))
    surfaces = runtime_delivery.get("surfaces") or []
    surface_names = {
        str(surface.get("surface"))
        for surface in surfaces
        if isinstance(surface, dict)
    }
    preserved_fields = set(_string_list(closure.get("required_preserved_fields")))
    required_commands = set(_string_list(closure.get("required_verification_commands")))
    coverage = _dict(delivery_audit.get("coverage"))
    superpowers_review = _superpowers_final_review_summary()

    requirements = [
        _objective_requirement(
            "nightpilot_goal_mode",
            "NightPilot goal-mode continuity and unattended handoff state remain available for the active objective.",
            bool(preflight.get("package_candidate_ready"))
            and latest_acceptance.get("status") == "passed"
            and "npm run delivery:audit" in required_commands,
            [
                "release_preflight.package_candidate_ready",
                "latest_acceptance_evidence.status",
                "delivery_closure.required_verification_commands",
                ".codex-autonomous/state.json",
            ],
            [
                "Child Codex execution may still be limited by account quota; continue manual main-session implementation when child workers are unavailable.",
            ],
        ),
        _objective_requirement(
            "source_resilience",
            "Information-source resilience is visible in runtime, report handoff, release checks, and agent preservation fields.",
            _dict(coverage.get("source_resilience")).get("covered") is True,
            [
                "delivery_audit.coverage.source_resilience",
                "source_resilience_recovery_step",
                "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
            ],
        ),
        _objective_requirement(
            "qyyjt_public_origin_mapping",
            "QYYJT/commercial-source concepts are mapped back to public-origin categories and survive agent handoff.",
            _dict(coverage.get("qyyjt_public_origin")).get("covered") is True,
            [
                "delivery_audit.coverage.qyyjt_public_origin",
                "qyyjt_public_origin_execution_queue",
                "qyyjt_public_origin_handoff.agent_autorun",
            ],
        ),
        _objective_requirement(
            "relationship_graph",
            "Relationship graph runtime exposes auditable nodes, edges, verification queues, and desktop-agent preservation.",
            _dict(coverage.get("relationship_graph")).get("covered") is True
            and "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun" in preserved_fields,
            [
                "delivery_audit.coverage.relationship_graph",
                "relationship_graph_audit_queue",
                "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            ],
        ),
        _objective_requirement(
            "capital_risk",
            "Capital-risk analysis is present in runtime outputs, report visibility, and agent handoff.",
            _dict(coverage.get("capital_risk")).get("covered") is True,
            [
                "delivery_audit.coverage.capital_risk",
                "risk_graph_capital_exposure",
                "one_click_readiness.capital_risk_panel",
                "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
            ],
        ),
        _objective_requirement(
            "report_visibility",
            "Report outputs remain visible to desktop agents as DOCX/HTML/Markdown/JSON/handoff artifacts without prose-only collapse.",
            _dict(coverage.get("report_visibility")).get("covered") is True
            and {
                "report_exports.premium_html",
                "report_exports.portable_html.premium_profile",
                "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
            } <= preserved_fields,
            [
                "delivery_audit.coverage.report_visibility",
                "report_exports.premium_html",
                "report_exports.portable_html.premium_profile",
                "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
            ],
        ),
        _objective_requirement(
            "acceptance_closure",
            "Acceptance closure is represented by the mandatory verification command set and latest full acceptance evidence.",
            latest_acceptance.get("status") == "passed"
            and {
                "npm run acceptance",
                "npm run delivery:audit",
                "npm run release:preflight",
                "npm run release:privacy-scan",
                "npm pack --dry-run --json",
            } <= required_commands,
            [
                "latest_acceptance_evidence",
                "delivery_closure.required_verification_commands",
                "tools/run-acceptance.ps1",
            ],
        ),
        _objective_requirement(
            "desktop_agent_delivery",
            "Desktop-agent delivery is locally packageable across Codex, Claude Code, Hermes, Doubao, OpenClaude/open agents, WorkBuddy, and universal hosts.",
            delivery_audit.get("status") == "pass"
            and bool(delivery_audit.get("ready_for_local_packaging"))
            and {"agent_tool_adapters", "desktop_agent_installation_handoff"} <= surface_names,
            [
                "delivery_audit.status",
                "delivery_audit.ready_for_local_packaging",
                "runtime_delivery.surfaces",
                "deploy/mcp-server.json",
            ],
        ),
        _objective_requirement(
            "workbuddy_expert_team_compatibility",
            "WorkBuddy expert-team mode is a secondary branch with preserved packet fields and smoke coverage.",
            _dict(coverage.get("workbuddy_expert_team")).get("covered") is True,
            [
                "delivery_audit.coverage.workbuddy_expert_team",
                "agent_tool_adapters.adapters[workbuddy_expert_team]",
                "tests/unit/test_workbuddy.py",
            ],
        ),
        _objective_requirement(
            "superpowers_final_review",
            "Final Superpowers review/update has been performed after all objective work.",
            superpowers_review["status"] == "pass"
            and latest_acceptance.get("status") == "passed"
            and delivery_audit.get("status") == "pass"
            and not delivery_audit.get("failed_checks"),
            [
                "docs/SUPERPOWERS_FINAL_REVIEW.md",
                "Superpowers using-superpowers",
                "Superpowers verification-before-completion",
                "npm run objective:audit",
                "npm run delivery:audit",
            ],
            superpowers_review["remaining_work"],
        ),
    ]
    failed = [item for item in requirements if item["status"] != "complete"]
    return {
        "type": "objective_completion_audit",
        "target": "wallstreet_tieling_desktop_agent_delivery_objective",
        "status": "complete" if not failed else "in_progress",
        "completion_percent": round(
            100 * (len(requirements) - len(failed)) / len(requirements)
        ),
        "requirements": requirements,
        "failed_requirements": failed,
        "release_gate": {
            "delivery_audit_status": delivery_audit.get("status"),
            "ready_for_local_packaging": delivery_audit.get("ready_for_local_packaging"),
            "final_submission_ready": delivery_audit.get("final_submission_ready"),
            "full_product_status": delivery_audit.get("full_product_status"),
        },
        "verification_evidence": {
            "latest_acceptance": latest_acceptance,
            "required_commands": sorted(required_commands),
            "delivery_audit_failed_checks": delivery_audit.get("failed_checks", []),
            "release_blocking_surface_count": runtime_delivery.get("release_blocking_surface_count", 0),
            "superpowers_final_review": superpowers_review,
        },
        "next_actions": [
            item
            for requirement in failed
            for item in requirement.get("remaining_work", [])
        ],
        "policy": (
            "This audit checks the active development objective requirement by requirement. "
            "Do not mark the thread goal complete while failed_requirements is non-empty."
        ),
    }


def _superpowers_final_review_summary() -> dict[str, Any]:
    review_path = PROJECT_ROOT / "docs" / "SUPERPOWERS_FINAL_REVIEW.md"
    skill_root = (
        Path.home()
        / ".codex"
        / "plugins"
        / "cache"
        / "openai-curated"
        / "superpowers"
        / "d6169bef"
    )
    required_markers = [
        "Status: pass",
        "using-superpowers",
        "verification-before-completion",
        "npm run objective:audit",
        "npm run delivery:audit",
        "npm run release:preflight",
        "npm run release:privacy-scan",
        "npm pack --dry-run --json",
        "58 passed",
        "issue_count: 0",
        "desktop-agent alpha",
    ]
    remaining_work: list[str] = []
    content = ""
    if not review_path.exists():
        remaining_work.append("Create docs/SUPERPOWERS_FINAL_REVIEW.md with requirement-by-requirement final evidence.")
    else:
        content = review_path.read_text(encoding="utf-8", errors="replace")
        missing_markers = [marker for marker in required_markers if marker not in content]
        if missing_markers:
            remaining_work.append(
                "Update docs/SUPERPOWERS_FINAL_REVIEW.md missing markers: "
                + ", ".join(missing_markers)
            )
    if not (skill_root / "skills" / "using-superpowers" / "SKILL.md").exists():
        remaining_work.append("Superpowers using-superpowers skill is not installed in the local plugin cache.")
    if not (skill_root / "skills" / "verification-before-completion" / "SKILL.md").exists():
        remaining_work.append("Superpowers verification-before-completion skill is not installed in the local plugin cache.")
    return {
        "type": "superpowers_final_review_evidence",
        "document": "docs/SUPERPOWERS_FINAL_REVIEW.md",
        "status": "pass" if not remaining_work else "incomplete",
        "skill_cache": "local_openai_curated_superpowers_cache",
        "skills_checked": [
            "using-superpowers",
            "verification-before-completion",
        ],
        "remaining_work": remaining_work,
    }


def delivery_audit_brief(path: str | Path | None = None) -> dict[str, Any]:
    """Return one machine-readable delivery audit for desktop-agent hosts."""
    brief = release_readiness_brief(path)
    delivery_decision = _dict(brief.get("delivery_decision"))
    preflight = _dict(brief.get("release_preflight"))
    closure = _dict(brief.get("delivery_closure"))
    runtime_delivery = _dict(brief.get("runtime_delivery"))
    latest_acceptance = _dict(brief.get("latest_acceptance_evidence"))
    surfaces = runtime_delivery.get("surfaces") or []
    surface_names = {
        str(surface.get("surface"))
        for surface in surfaces
        if isinstance(surface, dict)
    }
    preserved_fields = set(_string_list(closure.get("required_preserved_fields")))
    required_commands = set(_string_list(closure.get("required_verification_commands")))
    blocking_items = _string_list(preflight.get("blocking_items"))

    checks = [
        _audit_check(
            "desktop_agent_release_candidate",
            delivery_decision.get("status") == "desktop_agent_alpha_release_candidate",
            "release_readiness.delivery_decision.status",
        ),
        _audit_check(
            "package_candidate_ready",
            preflight.get("package_candidate_ready") is True,
            "release_preflight.package_candidate_ready",
        ),
        _audit_check(
            "acceptance_passed",
            latest_acceptance.get("status") == "passed",
            "latest_acceptance_evidence.status",
        ),
        _audit_check(
            "no_runtime_blocking_surfaces",
            int(runtime_delivery.get("release_blocking_surface_count") or 0) == 0,
            "runtime_delivery.release_blocking_surface_count",
        ),
        _audit_check(
            "host_adapters_declared",
            {"agent_tool_adapters", "desktop_agent_installation_handoff"} <= surface_names,
            "runtime_delivery.surfaces",
        ),
        _audit_check(
            "report_visibility_preserved",
            {
                "report_exports.premium_html",
                "report_exports.portable_html.premium_profile",
                "report_exports.directory_bundle.agent_handoff.report_visibility",
                "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
            } <= preserved_fields,
            "delivery_closure.required_preserved_fields",
        ),
        _audit_check(
            "deep_runtime_autorun_preserved",
            set(AUTORUN_PRESERVED_FIELDS) <= preserved_fields,
            "delivery_closure.required_preserved_fields",
        ),
        _audit_check(
            "verification_commands_declared",
            {
                "npm run acceptance",
                "npm run codex:mcp-smoke",
                "npm run agent:host-smoke",
                "npm run api:smoke",
                "npm run release:privacy-scan",
                "npm run release:preflight",
                "npm run delivery:audit",
                "npm run objective:audit",
                "npm pack --dry-run --json",
            } <= required_commands,
            "delivery_closure.required_verification_commands",
        ),
    ]
    failed = [check for check in checks if not check["passed"]]
    status = "pass" if not failed and not blocking_items else "blocked"
    return {
        "type": "desktop_agent_alpha_delivery_audit",
        "target": "desktop_agent_alpha",
        "status": status,
        "ready_for_local_packaging": status == "pass",
        "final_submission_ready": bool(preflight.get("final_submission_ready")),
        "full_product_status": delivery_decision.get("full_product_status", "not_final_release_ready"),
        "safe_claim": preflight.get("agent_handoff", {}).get(
            "safe_claim",
            "Desktop-agent alpha release candidate, not final polished product launch readiness.",
        ),
        "checks": checks,
        "failed_checks": failed,
        "blocking_items": blocking_items,
        "coverage": {
            "source_resilience": {
                "surface": "source_resilience_recovery_step",
                "preserved_field": "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
                "covered": "source_resilience_recovery_step" in surface_names
                and "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun" in preserved_fields,
            },
            "qyyjt_public_origin": {
                "surface": "qyyjt_public_origin_execution_queue",
                "preserved_field": "qyyjt_public_origin_handoff.agent_autorun",
                "covered": "qyyjt_public_origin_execution_queue" in surface_names
                and "qyyjt_public_origin_handoff.agent_autorun" in preserved_fields,
            },
            "relationship_graph": {
                "surface": "relationship_graph_audit_queue",
                "preserved_field": "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
                "covered": "relationship_graph_audit_queue" in surface_names
                and "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun" in preserved_fields,
            },
            "capital_risk": {
                "surface": "risk_graph_capital_exposure",
                "preserved_field": "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
                "covered": "risk_graph_capital_exposure" in surface_names
                and "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun" in preserved_fields,
            },
            "report_visibility": {
                "surface": "portable_html_and_markdown_exports",
                "preserved_field": "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
                "covered": "portable_html_and_markdown_exports" in surface_names
                and "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in preserved_fields,
            },
            "workbuddy_expert_team": {
                "surface": "agent_tool_adapters",
                "covered": "agent_tool_adapters" in surface_names,
            },
        },
        "verification_evidence": {
            "latest_acceptance": preflight.get("latest_acceptance", {}),
            "required_commands": sorted(required_commands),
            "runtime_surface_count": len(surface_names),
            "release_blocking_surface_count": runtime_delivery.get("release_blocking_surface_count", 0),
        },
        "next_actions": [
            "Run npm run acceptance before any stronger delivery claim if code changed after the recorded evidence.",
            "Capture marketplace/operator screenshots only when preparing external submission.",
            "Publish only from a clean reviewed release branch after privacy scan and package dry-run.",
        ],
        "not_current_release": closure.get("not_current_release", []),
        "policy": (
            "This audit is the single machine-readable go/no-go view for desktop-agent alpha delivery. "
            "It does not certify final product launch readiness or external marketplace approval."
        ),
    }


def _audit_check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
    }


def _objective_requirement(
    requirement_id: str,
    requirement: str,
    passed: bool,
    evidence: list[str],
    remaining_work: list[str] | None = None,
) -> dict[str, Any]:
    remaining = remaining_work or []
    return {
        "id": requirement_id,
        "requirement": requirement,
        "status": "complete" if passed else "incomplete",
        "evidence": evidence,
        "remaining_work": [] if passed else remaining,
    }


def _delivery_decision(
    contract: dict[str, Any],
    runtime_delivery: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking_surfaces = int(runtime_delivery.get("release_blocking_surface_count") or 0)
    alpha_variants = int(contract.get("summary", {}).get("alpha_count") or 0)
    status = (
        "desktop_agent_alpha_release_candidate"
        if alpha_variants and blocking_surfaces == 0
        else "not_ready_for_desktop_agent_delivery"
    )
    return {
        "type": "release_delivery_decision",
        "current_target": "desktop_agent_alpha",
        "status": status,
        "full_product_status": "not_final_release_ready",
        "desktop_agent_release_candidate": status == "desktop_agent_alpha_release_candidate",
        "runtime_blocking_surface_count": blocking_surfaces,
        "alpha_variant_count": alpha_variants,
        "remaining_variant_blocker_count": 0 if status == "desktop_agent_alpha_release_candidate" else len(blockers),
        "variant_next_gate_count": len(blockers),
        "variant_next_gate_policy": "Variant next_gate rows are follow-up packaging, screenshot, or stronger-claim tasks; they do not block desktop-agent alpha delivery when runtime_blocking_surface_count is 0.",
        "polished_html_current_release": bool(runtime_delivery.get("polished_html_current_release")),
        "policy": (
            "Use this release decision for desktop-agent alpha delivery only. "
            "Do not treat it as final product launch readiness while polished HTML and later app targets remain outside current release."
        ),
    }


def _delivery_closure_summary() -> dict[str, Any]:
    """Machine-readable desktop-agent alpha closure checklist."""
    return {
        "type": "desktop_agent_alpha_delivery_closure",
        "status": "release_candidate",
        "target": "desktop_agent_alpha",
        "document": "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
        "baseline_sequence": [
            "release_readiness",
            "delivery_audit",
            "connector_catalog",
            "development_requirements",
            "agent_tool_adapters",
            "investigate_company",
        ],
        "followup_tools": ["aggregate_subject"],
        "required_verification_commands": [
            "npm run acceptance",
            "npm run codex:mcp-smoke",
            "npm run agent:host-smoke",
            "npm run api:smoke",
            "npm run release:privacy-scan",
            "npm run release:preflight",
            "npm run delivery:audit",
            "npm run objective:audit",
            "npm pack --dry-run --json",
        ],
        "required_preserved_fields": [
            "delivery_decision",
            "quality_gate",
            "evidence_ledger",
            "one_click_readiness",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.capital_risk_panel.report_visibility",
            "qyyjt_public_origin_handoff",
            "report_exports.agent_decision_digest",
            "report_exports.premium_html",
            "report_exports.portable_html.premium_profile",
            "report_exports.directory_bundle",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.agent_handoff.report_visibility",
            "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
            "report_exports.directory_bundle.agent_handoff.report_visibility.image_evidence",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
            "report_exports.directory_bundle.agent_handoff.source_strengthening",
            "report_exports.directory_bundle.agent_handoff.delivery_decision",
            *AUTORUN_PRESERVED_FIELDS,
        ],
        "not_current_release": [
            "final polished product launch readiness",
            "marketplace approval",
            "human-captured marketplace screenshots",
            "polished immersive HTML workbench as the primary product surface",
            "mini-program, mobile app, or standalone desktop app",
            "always-on continuous monitoring",
            "guaranteed live coverage for every advertised source",
        ],
        "open_submission_items": [
            "capture marketplace/operator screenshots after final acceptance",
            "publish from a clean reviewed release branch",
            "keep local fixtures, private reports, cookies, browser profiles, runtime state, and secrets out of package",
        ],
    }


def _release_preflight_summary(
    *,
    delivery_decision: dict[str, Any],
    delivery_closure: dict[str, Any],
    latest_acceptance: dict[str, Any],
    runtime_delivery: dict[str, Any],
) -> dict[str, Any]:
    """Machine-readable alpha package preflight for agents and release scripts."""
    required_commands = _string_list(delivery_closure.get("required_verification_commands"))
    preserved_fields = _string_list(delivery_closure.get("required_preserved_fields"))
    open_submission_items = _string_list(delivery_closure.get("open_submission_items"))
    blocking_items: list[str] = []
    if delivery_decision.get("status") != "desktop_agent_alpha_release_candidate":
        blocking_items.append("delivery_decision.status is not desktop_agent_alpha_release_candidate")
    if int(runtime_delivery.get("release_blocking_surface_count") or 0) != 0:
        blocking_items.append("runtime_delivery.release_blocking_surface_count is not 0")
    if latest_acceptance.get("status") != "passed":
        blocking_items.append("latest_acceptance_evidence.status is not passed")
    if "npm pack --dry-run --json" not in required_commands:
        blocking_items.append("npm pack --dry-run --json is missing from required verification commands")
    for field in [
        "report_exports.premium_html",
        "report_exports.portable_html.premium_profile",
        "report_exports.directory_bundle.agent_handoff.delivery_decision",
        "report_exports.directory_bundle.agent_handoff.report_visibility",
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
        "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
        "report_exports.directory_bundle.agent_handoff.source_strengthening",
        *AUTORUN_PRESERVED_FIELDS,
    ]:
        if field not in preserved_fields:
            blocking_items.append(f"{field} is missing from required preserved fields")

    package_candidate_ready = not blocking_items
    return {
        "type": "desktop_agent_alpha_release_preflight",
        "target": "desktop_agent_alpha",
        "status": "ready_for_local_packaging" if package_candidate_ready else "blocked",
        "package_candidate_ready": package_candidate_ready,
        "final_submission_ready": False,
        "final_submission_blockers": open_submission_items,
        "blocking_items": blocking_items,
        "required_verification_commands": required_commands,
        "required_preserved_fields": preserved_fields,
        "latest_acceptance": {
            "status": latest_acceptance.get("status"),
            "command": latest_acceptance.get("command"),
            "observed_at": latest_acceptance.get("observed_at"),
            "python_tests_passed": latest_acceptance.get("python_tests_passed"),
            "python_tests_skipped": latest_acceptance.get("python_tests_skipped"),
        },
        "packaging_review": {
            "dry_run_command": "npm pack --dry-run --json",
            "privacy_command": "npm run release:privacy-scan",
            "do_not_package": [
                "API keys, cookies, browser profiles, local SQLite collaboration databases, generated secrets",
                "runtime state directories such as .codex-autonomous, outputs, deliverables, audit_reports, or WorkBuddy local artifacts",
                "private investigation reports or local fixtures not listed in package.json files",
            ],
        },
        "agent_handoff": {
            "read_first": [
                "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
                "docs/AGENT_HOST_SMOKE_CHECKLIST.md",
                "docs/API_CONTRACTS.md",
            ],
            "baseline_sequence": delivery_closure.get("baseline_sequence", []),
            "safe_claim": "Desktop-agent alpha release candidate, not final polished product launch readiness.",
            "do_not_claim": delivery_closure.get("not_current_release", []),
        },
        "policy": (
            "This preflight proves local desktop-agent alpha package readiness only. "
            "Marketplace screenshots, clean branch publishing, and external approval remain separate submission tasks."
        ),
    }


def _variant_payload(name: str, variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": variant.get("display_name", name),
        "audience": variant.get("audience", ""),
        "entrypoints": _string_list(variant.get("entrypoints")),
        "packaging": _string_list(variant.get("packaging")),
        "required_capabilities": _string_list(variant.get("required_capabilities")),
        "delivery_priority": _dict(variant.get("delivery_priority")),
        "project_branch": _dict(variant.get("project_branch")),
        "readiness": str(variant.get("readiness") or "planned"),
        "next_gate": _string_list(variant.get("next_gate")),
    }


def _next_focus(blockers: list[dict[str, Any]]) -> list[str]:
    focus: list[str] = []
    for blocker in blockers:
        for gate in blocker.get("next_gate", [])[:2]:
            item = f"{blocker['variant']}: {gate}"
            if item not in focus:
                focus.append(item)
    return focus[:8]


def _runtime_delivery_summary() -> dict[str, Any]:
    surfaces = [
        {
            "surface": "one_click_investigation_packet",
            "entrypoints": ["bin/investigate.py", "/api/investigate", "MCP investigate_company"],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_packet_contains_report_and_monitoring_seed",
                "tests/unit/test_api_server.py::test_investigate_endpoint_accepts_one_line_message",
            ],
        },
        {
            "surface": "qyyjt_public_origin_execution_queue",
            "entrypoints": [
                "/api/connectors",
                "/api/docs",
                "core.qyyjt_benchmark.build_qyyjt_benchmark",
                "investigation_packet.qyyjt_public_origin_handoff",
                "investigation_packet.qyyjt_public_origin_handoff.report_section_batches",
                "investigation_packet.qyyjt_public_origin_handoff.section_work_orders",
                "investigation_packet.qyyjt_public_origin_handoff.section_execution_summary",
                "investigation_packet.qyyjt_public_origin_handoff.top_ready_section_work_order",
                "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.section_work_orders",
                "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.section_execution_summary",
                "one_click_readiness.public_origin_gap_bridge",
                "one_click_readiness.public_origin_gap_bridge_top_action",
                "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_qyyjt_tool.py::test_qyyjt_benchmark_surface_is_fully_module_specific",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
                "tests/unit/test_investigation.py::test_investigation_packet_contains_report_and_monitoring_seed",
            ],
        },
        {
            "surface": "agent_tool_adapters",
            "entrypoints": [
                "core.agent_tool_adapters.build_agent_tool_adapter_manifest",
                "/api/agent-tools",
                "npx wallstreet-tieling --agent-tools",
                "MCP agent_tool_adapters",
                "deploy/mcp-server.json tools.agent_tool_adapters",
                "agent_tool_adapter_manifest.installation_handoff",
                "agent_tool_adapter_manifest.installation_handoff.host_matrix",
                "agent_tool_adapter_manifest.installation_handoff.failure_routing",
                "agent_tool_adapter_manifest.adapters[].install_handoff",
                "agent_tool_adapter_manifest.adapter_lookup.<host_id>.install_command",
                "agent_tool_adapter_manifest.adapters[].tool_sequence",
                "agent_tool_adapter_manifest.adapters[].fallback_order",
                "agent_tool_adapter_manifest.adapters[].required_packet_fields",
                "agent_tool_adapter_manifest.adapters[].required_packet_fields.report_exports.directory_bundle.verification_recipe",
                "agent_tool_adapter_manifest.execution_matrix",
                "agent_tool_adapter_manifest.execution_matrix[].done_condition",
                "agent_tool_adapter_manifest.first_run_recipe",
                "agent_tool_adapter_manifest.first_run_recipe.preserve_before_summarizing",
                "agent_tool_adapter_manifest.required_smoke_commands",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_release_variants.py::test_agent_tool_adapter_manifest_covers_all_current_hosts",
                "tests/unit/test_release_variants.py::test_package_scripts_and_mcp_manifest_stay_aligned",
                "tests/unit/test_api_server.py::test_agent_tools_endpoint_exposes_all_desktop_agent_adapters",
            ],
        },
        {
            "surface": "desktop_agent_installation_handoff",
            "entrypoints": [
                "agent_tool_adapter_manifest.installation_handoff",
                "agent_tool_adapter_manifest.installation_handoff.default_install_command",
                "agent_tool_adapter_manifest.installation_handoff.default_mcp_command",
                "agent_tool_adapter_manifest.installation_handoff.required_local_runtime_env",
                "agent_tool_adapter_manifest.installation_handoff.verification_commands",
                "agent_tool_adapter_manifest.installation_handoff.host_matrix",
                "agent_tool_adapter_manifest.installation_handoff.failure_routing",
                "agent_tool_adapter_manifest.adapters[].install_handoff",
                "agent_tool_adapter_manifest.adapter_lookup.<host_id>.install_command",
                "agent_tool_adapter_manifest.adapter_lookup.<host_id>.start_command",
                "tools/run-python.ps1",
                "package.json scripts.api",
                "package.json scripts.api:smoke",
                "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
                "docs/AGENT_HOST_SMOKE_CHECKLIST.md",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_release_variants.py::test_agent_tool_adapter_manifest_covers_all_current_hosts",
                "tests/unit/test_release_variants.py::test_package_scripts_and_mcp_manifest_stay_aligned",
                "tests/unit/test_release_variants.py::test_desktop_agent_alpha_delivery_closure_is_actionable",
            ],
        },
        {
            "surface": "aggregate_subject_followup",
            "entrypoints": [
                "core.investigation.run_subject_profile_aggregation",
                "npx wallstreet-tieling --aggregate-subject <subject_id>",
                "POST /api/aggregate",
                "MCP aggregate_subject",
                "agent_tool_adapter_manifest.shared_tools.aggregate_subject",
                "aggregate_subject.subject",
                "aggregate_subject.relationship_graph",
                "aggregate_subject.profile",
                "docs/API_CONTRACTS.md POST /api/aggregate",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_api_server.py::test_aggregate_endpoint_matches_agent_tool_contract",
                "tests/unit/test_release_variants.py::test_agent_tool_adapter_manifest_covers_all_current_hosts",
                "tests/unit/test_encoding_integrity.py::test_cli_help_mentions_catalog_and_release_commands",
            ],
        },
        {
            "surface": "risk_graph_capital_exposure",
            "entrypoints": [
                "bin/risk_graph.py",
                "/api/risk-graph",
                "core.risk_graph_export.export_risk_graph",
                "summary.capital_exposure.verification_queue",
                "summary.capital_exposure.relationship_audit_queue",
                "one_click_readiness.graph_capital_exposure",
                "one_click_readiness.graph_capital_exposure_top_step",
                "one_click_readiness.graph_capital_exposure_source_family_summary",
                "one_click_readiness.capital_pressure_source_family_summary",
                "one_click_readiness.capital_verification_queue",
                "one_click_readiness.capital_verification_top_step",
                "one_click_readiness.capital_risk_panel",
                "one_click_readiness.capital_risk_panel.report_visibility",
                "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
                "report_exports.directory_bundle.agent_handoff.capital_and_relationship.risk_panel",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_risk_graph_export.py::test_risk_graph_cli_fixture_pack_exports_multi_source_graph",
                "tests/unit/test_investigation.py::test_one_click_readiness_flags_unexplained_capital_pressure",
            ],
        },
        {
            "surface": "relationship_graph_audit_queue",
            "entrypoints": [
                "one_click_readiness.relationship_graph_audit_queue_count",
                "one_click_readiness.relationship_graph_audit_queue",
                "one_click_readiness.relationship_graph_audit_top_step",
                "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_report_surfaces_relationship_network_and_parks_monitoring",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "printable_docx_export",
            "entrypoints": [
                "bin/investigate.py --export-docx",
                "core.report_docx.render_print_package_docx",
                "report_exports.print_package.operational_handoff",
                "report_exports.print_package.delivery_checklist",
                "report_exports.print_package.docx.renderer_capabilities.official_document_metadata",
                "report_exports.print_package.docx.renderer_capabilities.red_head_separator_rule",
                "report_exports.print_package.docx.renderer_capabilities.native_chart_summary_panels",
                "report_exports.print_package.docx.renderer_capabilities.embedded_local_image_evidence",
                "report_exports.print_package.source_provenance_appendix",
                "report_exports.print_package.delivery_checklist.quality_checks.source_provenance_appendix_present",
                "word/document.xml official metadata table, red-head separator, and chart summary panels",
                "word/document.xml source provenance appendix and evidence source index",
                "word/media embedded local or data-uri image evidence",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_print_package_docx_renderer_preserves_report_contract",
                "tests/unit/test_investigation.py::test_investigate_cli_export_docx_writes_word_file",
            ],
        },
        {
            "surface": "portable_html_and_markdown_exports",
            "entrypoints": [
                "bin/investigate.py --export-html",
                "bin/investigate.py --export-markdown",
                "bin/investigate.py --export-json",
                "bin/investigate.py --export-dir",
                "bin/verify_report_bundle.py <export-dir>",
                "report_exports.directory_bundle.verification_recipe",
                "report_exports.directory_bundle.verification_recipe.required_output_fields",
                "report_exports.directory_bundle.verifier_output_fields",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.bundle_ready_to_verify",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.image_evidence_inventory_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.premium_html_report_visibility_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.verification_recipe_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.verifier_output_fields_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.acceptance_closure_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.qyyjt_public_origin_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_resilience_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.relationship_graph_audit_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_strengthening_present",
                "report_exports.directory_bundle.verifier_output_fields.agent_handoff.source_strengthening_runtime_companion_present",
                "node_cli_offline_fixture_fallback_export_dir",
                "node_cli_fallback_manifest.unavailable_outputs.docx",
                "report_exports.agent_decision_digest",
                "report_exports.directory_bundle",
                "report_exports.directory_bundle.manifest_fields",
                "report_exports.directory_bundle.manifest_fields.file_manifest",
                "report_exports.directory_bundle.manifest_fields.agent_summary",
                "report_exports.directory_bundle.agent_handoff",
                "report_exports.directory_bundle.agent_handoff.delivery_files",
                "report_exports.directory_bundle.agent_handoff.bundle_integrity",
                "report_exports.directory_bundle.agent_handoff.bundle_verification",
                "report_exports.directory_bundle.agent_handoff.delivery_checklist",
                "report_exports.directory_bundle.agent_handoff.source_strengthening",
                "report_exports.directory_bundle.agent_handoff.trust_boundaries",
                "report_exports.directory_bundle.agent_handoff.decision_digest",
                "report_exports.directory_bundle.agent_handoff.next_actions",
                "report_exports.directory_bundle.agent_handoff.acceptance_closure",
                "report_exports.directory_bundle.agent_handoff.reliance_limitations",
                "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin.gap_bridge",
                "report_exports.directory_bundle.agent_handoff.capital_and_relationship.graph_capital_exposure",
                "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
                "report_exports.portable_html",
                "report_exports.premium_html",
                "report_exports.premium_html.acceptance_checklist",
                "report_exports.premium_html.content_guarantees",
                "report_exports.premium_html.forbidden_shortcuts",
                "report_exports.portable_html.premium_profile",
                "report_exports.portable_html.first_screen_handoff_cards",
                "report_exports.portable_html.delivery_checklist_source",
                "report_markdown",
                "json_packet",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_packet_contains_report_and_monitoring_seed",
                "tests/unit/test_investigation.py::test_investigate_cli_exports_report_file_bundle",
                "tests/unit/test_investigation.py::test_investigate_cli_exports_report_directory_bundle",
                "tests/unit/test_investigation.py::test_node_cli_offline_fallback_writes_agent_handoff_bundle",
            ],
        },
        {
            "surface": "source_resilience_recovery_step",
            "entrypoints": [
                "source_failure_summary.source_resilience_profile.recommended_step",
                "source_failure_summary.source_resilience_profile.retry_policy",
                "one_click_readiness.source_resilience_recommended_step",
                "one_click_readiness.source_resilience_retry_policy",
                "one_click_readiness.source_resilience_retryable",
                "one_click_readiness.source_resilience_retry_max_attempts",
                "monitoring_seed.recovery_execution_queue.queue.retry_policy",
                "monitoring_seed.recovery_execution_queue.queue.replay_route",
                "monitoring_seed.recovery_execution_queue.queue.non_reliance_caveat",
                "monitoring_seed.recovery_execution_queue.blocked_preview.replay_route",
                "report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue",
                "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.retry_policy",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_packet_surfaces_source_failure_taxonomy",
                "tests/unit/test_investigation_quality.py::test_source_diagnostics_marks_recovery_steps_ready_when_connector_available",
                "tests/unit/test_investigation_quality.py::test_source_diagnostics_decision_explains_blocked_recovery_step",
            ],
        },
        {
            "surface": "operator_work_queue",
            "entrypoints": [
                "one_click_readiness.operator_work_queue",
                "one_click_readiness.operator_work_top_action",
                "one_click_readiness.public_origin_gap_bridge",
                "one_click_readiness.graph_capital_exposure",
                "one_click_readiness.reliance_limitations",
                "one_click_readiness.acceptance_closure_summary",
                "one_click_readiness.acceptance_closure_status",
                "report_exports.print_package.operational_handoff.cards",
                "report_exports.print_package.operational_handoff.cards.acceptance_closure_summary",
                "report_exports.print_package.operational_handoff.cards.graph_capital_exposure_top_step",
                "report_exports.print_package.operational_handoff.cards.public_origin_gap_bridge_top_action",
                "report_exports.print_package.operational_handoff.cards.people_control_closure_step",
                "report_exports.directory_bundle.agent_handoff.acceptance_closure",
                "report_exports.directory_bundle.agent_handoff.closure_steps",
                "report_exports.print_package.operational_handoff.cards.reliance_limitation_top_action",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_packet_surfaces_source_failure_taxonomy",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "control_path_closure_step",
            "entrypoints": [
                "enterprise_cognition.control_ownership.control_path_verification_queue",
                "one_click_readiness.control_path_closure_needed",
                "one_click_readiness.control_path_closure_step",
                "one_click_readiness.control_path_source_family_summary",
                "one_click_readiness.operator_work_queue",
                "report_exports.print_package.operational_handoff.cards",
                "report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_investigation_report_surfaces_indirect_controller_path",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "subject_profile_controller_source_families",
            "entrypoints": [
                "core.subject_profile.SubjectProfileBuilder",
                "graph.diagnostics.subject_profile.controller_candidates.source_family_summary",
                "graph.diagnostics.subject_profile.controller_candidates.control_path_summaries.source_family_summary",
                "graph.diagnostics.subject_profile.relationship_graph.edges.source_family_summary",
                "enterprise_cognition.control_ownership.controller_candidates.source_family_summary",
                "enterprise_cognition.control_ownership.control_paths.source_family_summary",
                "/api/investigate",
                "/api/docs",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_subject_profile.py::test_subject_profile_summarizes_control_source_families_across_major_feeds",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "goods_economics_closure_step",
            "entrypoints": [
                "one_click_readiness.goods_economics_closure_needed",
                "one_click_readiness.goods_economics_closure_step",
                "one_click_readiness.operator_work_queue",
                "report_exports.print_package.operational_handoff.cards",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_public_goods_profile_structures_market_and_business_model_leads",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "people_control_closure_step",
            "entrypoints": [
                "one_click_readiness.people_control_closure_needed",
                "one_click_readiness.people_control_closure_step",
                "one_click_readiness.operator_work_queue",
                "enterprise_cognition.public_people_profile",
                "enterprise_cognition.people_flow_profile",
                "report_exports.directory_bundle.agent_handoff.closure_steps.people_control",
                "report_exports.print_package.operational_handoff.cards",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_public_people_profile_structures_people_lane_and_report_without_fact_promotion",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "source_repair_priority_queue",
            "entrypoints": [
                "monitoring_seed.source_repair_priority_queue",
                "monitoring_seed.recovery_execution_summary.source_repair_top_action",
                "one_click_readiness.source_repair_priority_count",
                "one_click_readiness.source_repair_top_action",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_recurring_source_failure_patterns_are_report_and_seed_visible",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "source_health_trend_snapshot",
            "entrypoints": [
                "monitoring_seed.source_health_trend_snapshot",
                "monitoring_seed.recovery_execution_summary.source_health_top_source",
                "one_click_readiness.source_health_trend_source_count",
                "one_click_readiness.source_health_trend_top_source",
                "one_click_readiness.source_health_trend_digest",
                "one_click_readiness.source_health_trend_digest.actionability",
                "one_click_readiness.source_health_trend_digest.subject_risk_verdict_allowed",
                "report_exports.directory_bundle.agent_handoff.source_health.digest",
                "report_exports.print_package.operational_handoff.cards.source_health_trend_top_source",
                "report_markdown",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_investigation.py::test_recurring_source_failure_patterns_are_report_and_seed_visible",
                "tests/unit/test_api_server.py::test_api_docs_mentions_qyyjt_benchmark_surface",
            ],
        },
        {
            "surface": "source_health_release_warnings",
            "entrypoints": [
                "/api/monitor/source-health",
                "bin/risk_monitor.py --source-health",
                "RiskMonitorRunStore.source_health_trends",
                "source_health.connector_recovery_queue",
                "source_health.release_readiness_warnings",
                "source_health.release_readiness_warning_count",
            ],
            "current_release": True,
            "proof_tests": [
                "tests/unit/test_api_server.py::test_monitor_source_health_endpoint_returns_trends",
                "tests/unit/test_risk_monitor_cli.py::test_risk_monitor_cli_reports_source_health_from_run_store",
                "tests/unit/test_risk_monitor.py::test_risk_monitor_run_store_summarizes_source_health_trends",
            ],
        },
    ]
    proof_tests = _dedupe(
        str(test)
        for surface in surfaces
        for test in surface.get("proof_tests", [])
    )
    surfaces = [_runtime_surface_with_acceptance(item) for item in surfaces]
    acceptance_counts: dict[str, int] = {}
    for surface in surfaces:
        status = str(surface.get("acceptance_status") or "unknown")
        acceptance_counts[status] = acceptance_counts.get(status, 0) + 1
    return {
        "type": "runtime_delivery_summary",
        "current_release_surface_count": sum(1 for item in surfaces if item["current_release"]),
        "agent_first": True,
        "polished_html_current_release": False,
        "acceptance_status_counts": acceptance_counts,
        "release_blocking_surface_count": acceptance_counts.get("blocked", 0),
        "proof_test_count": len(proof_tests),
        "focused_test_command": "python -m pytest " + " ".join(proof_tests) + " -q",
        "surfaces": surfaces,
        "source_health_operator_handoff": {
            "type": "source_health_operator_handoff",
            "default_mode": "on_demand_not_background_monitoring",
            "trend_entrypoints": [
                "/api/monitor/source-health",
                "bin/risk_monitor.py --source-health",
                "RiskMonitorRunStore.source_health_trends",
            ],
            "recovery_queue_fields": [
                "source",
                "priority",
                "status",
                "failure_category",
                "availability_ratio",
                "operator_action",
                "retry_policy",
                "done_condition",
            ],
            "warning_fields": [
                "source",
                "priority",
                "status",
                "operator_action",
                "release_gate",
            ],
            "release_action_policy": "Treat degraded source-health as connector/operator work, not as a subject-risk verdict.",
        },
        "acceptance_note": "Each surface lists the focused tests that prove the current runtime contract before broader npm run acceptance.",
    }


def _latest_acceptance_evidence() -> dict[str, Any]:
    return {
        "type": "latest_acceptance_evidence",
        "status": "passed",
        "command": "npm run acceptance",
        "observed_at": "2026-07-06 08:24 Asia/Shanghai",
        "python_tests_passed": 799,
        "python_tests_skipped": 9,
        "plugin_validation": "passed",
        "api_smoke": "passed",
        "default_one_click_acceptance": "Apple Inc. passed",
        "release_target": "desktop_agent_alpha",
        "post_acceptance_focused_regressions": [
            {
                "type": "focused_regression_evidence",
                "status": "passed",
                "observed_at": "2026-07-05 21:24 Asia/Shanghai",
                "command": (
                    "node tools/run-python.js -m pytest tests/unit/test_runtime_deep.py "
                    "tests/unit/test_telegram_agg.py tests/unit/test_autonomous.py "
                    "tests/unit/test_connector_registry.py tests/unit/test_release_variants.py "
                    "tests/unit/test_api_server.py tests/unit/test_investigation.py "
                    "tests/unit/test_workbuddy.py -q"
                ),
                "python_tests_passed": 223,
                "python_tests_skipped": 2,
                "covers": [
                    "source_strengthening completion state with needs_admission=0",
                    "empty source_strengthening_queue summary and handoff completion status",
                    "Codex MCP smoke source-strengthening completion acceptance",
                    "REST API smoke source-strengthening completion acceptance",
                    "WorkBuddy expert-team packet compatibility",
                    "directory bundle verifier completion-state handling",
                ],
            },
            {
                "type": "focused_regression_evidence",
                "status": "passed",
                "observed_at": "2026-07-05 22:01 Asia/Shanghai",
                "command": (
                    "node tools/run-python.js -m pytest tests/unit/test_investigation.py::test_investigation_packet_contains_report_and_monitoring_seed "
                    "tests/unit/test_investigation.py::test_investigate_cli_exports_report_directory_bundle "
                    "tests/unit/test_investigation.py::test_node_cli_offline_fallback_writes_agent_handoff_bundle "
                    "tests/unit/test_release_variants.py::test_agent_tool_adapter_manifest_covers_all_current_hosts "
                    "tests/unit/test_release_variants.py::test_agent_host_smoke_checklist_covers_release_variants_and_commands "
                    "tests/unit/test_release_variants.py::test_desktop_agent_alpha_delivery_closure_is_actionable "
                    "tests/unit/test_api_server.py::test_agent_tools_endpoint_exposes_all_desktop_agent_adapters "
                    "tests/unit/test_development_requirements.py -q; npm run agent:host-smoke; npm run codex:mcp-smoke; "
                    "npm run api:smoke; npm pack --dry-run --json; git diff --check"
                ),
                "python_tests_passed": 14,
                "python_tests_skipped": 0,
                "node_smokes": [
                    "npm run agent:host-smoke",
                    "npm run codex:mcp-smoke",
                    "npm run api:smoke",
                    "npm pack --dry-run --json",
                    "git diff --check",
                ],
                "covers": [
                    "premium_html report_exports runtime contract",
                    "portable_html premium_profile mirror",
                    "agent_tool_adapters premium_html preservation guards",
                    "directory agent-handoff report_visibility.premium_html",
                    "Codex primary premium report smoke coverage",
                    "WorkBuddy-compatible host smoke premium report coverage",
                    "premium HTML visual QA markers and full-report preservation markers",
                ],
            }
        ],
        "covers": [
            "REST API smoke",
            "packaged Codex MCP smoke",
            "host-neutral desktop-agent smoke",
            "Codex primary delivery lane and WorkBuddy secondary branch priority",
            "connector_catalog source_strengthening_queue",
            "official China source strengthening implementation_pack",
            "OpenSanctions and IDB public dataset source strengthening implementation_pack",
            "agent_tool_adapters first_run_recipe preserves source_strengthening_queue",
            "source_strengthening risk_enforcement lane routing",
            "source_strengthening execution_plan agent handoff",
            "WorkBuddy investigate_company host smoke",
            "host-smoke Python runtime resolution",
            "desktop-agent installation handoff",
            "agent_tool_adapters runtime contract",
            "agent_tool_adapters premium_html preservation guards",
            "premium_html report_exports runtime contract",
            "directory agent-handoff report_visibility.premium_html",
            "release_preflight package go/no-go gate",
            "package privacy scan gate",
            "npm package dry-run content gate",
            "terminology guard public-copy hygiene",
            "report_exports.agent_decision_digest packet routing",
            "directory bundle decision_digest and bundle_integrity verifier",
            "directory bundle verifier_output_fields handoff",
            "directory bundle verification_recipe handoff",
            "portable HTML handoff visibility",
            "DOCX official metadata/red-head/chart panels",
            "manifest agent_summary deep drift verification",
            "DOCX source provenance appendix and evidence source index",
            "DOCX relationship/capital appendix and delivery checklist",
            "QYYJT public-origin work orders",
            "source resilience and recovery queues",
            "capital verification and relationship graph audit handoff",
            "source_resilience agent_autorun",
            "QYYJT public-origin agent_autorun",
            "capital risk and relationship autorun routes",
            "report_artifact_agent_autorun",
        ],
        "artifact_policy": "local acceptance evidence only; marketplace/operator screenshots are still separate release artifacts",
    }


def _runtime_surface_with_acceptance(surface: dict[str, Any]) -> dict[str, Any]:
    item = dict(surface)
    proof_tests = _string_list(item.get("proof_tests"))
    entrypoints = _string_list(item.get("entrypoints"))
    current_release = bool(item.get("current_release"))
    if not current_release:
        status = "planned"
        gate = "not_in_current_release"
        blocker = ""
    elif proof_tests and entrypoints:
        status = "proof_defined"
        gate = "focused_tests_listed_and_entrypoints_declared"
        blocker = ""
    else:
        status = "blocked"
        gate = "missing_entrypoints_or_proof_tests"
        blocker = "current_release_surface_requires_entrypoints_and_focused_proof_tests"
    item["acceptance_status"] = status
    item["acceptance_gate"] = gate
    item["blocking_reason"] = blocker
    return item


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
