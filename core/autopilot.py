#!/usr/bin/env python3
"""Execution profiles for one-click and deep-mode investigation autopilot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutopilotExecutionProfile:
    """Resolved runtime bounds and policy for an investigation run."""

    type: str
    mode: str
    level: str
    interaction_model: str
    source_strategy: str
    retrieval_concurrency: int
    fanout_rounds: int
    max_fanout_tasks: int
    query_timeout_seconds: float
    configured_source_available: bool
    fixture_mode: bool
    official_public_smoke: bool
    user_overrides: dict[str, bool]
    runtime_must: list[str]
    runtime_must_not: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "mode": self.mode,
            "level": self.level,
            "interaction_model": self.interaction_model,
            "source_strategy": self.source_strategy,
            "retrieval_concurrency": self.retrieval_concurrency,
            "fanout_rounds": self.fanout_rounds,
            "max_fanout_tasks": self.max_fanout_tasks,
            "query_timeout_seconds": self.query_timeout_seconds,
            "configured_source_available": self.configured_source_available,
            "fixture_mode": self.fixture_mode,
            "official_public_smoke": self.official_public_smoke,
            "user_overrides": self.user_overrides,
            "runtime_must": self.runtime_must,
            "runtime_must_not": self.runtime_must_not,
        }


_DEFAULTS = {
    "retrieval_concurrency": 4,
    "fanout_rounds": 1,
    "max_fanout_tasks": 24,
    "query_timeout_seconds": 20.0,
}

_BOUNDS = {
    "retrieval_concurrency": (1, 20),
    "fanout_rounds": (0, 3),
    "max_fanout_tasks": (0, 80),
    "query_timeout_seconds": (0.1, 120.0),
}

_DEEP_MINIMUMS = {
    "retrieval_concurrency": 8,
    "fanout_rounds": 2,
    "max_fanout_tasks": 48,
    "query_timeout_seconds": 45.0,
}

_QUICK_MAXIMUMS = {
    "retrieval_concurrency": 3,
    "fanout_rounds": 0,
    "max_fanout_tasks": 12,
    "query_timeout_seconds": 12.0,
}


def build_autopilot_execution_profile(
    *,
    mode: str,
    retrieval_concurrency: Any = _DEFAULTS["retrieval_concurrency"],
    fanout_rounds: Any = _DEFAULTS["fanout_rounds"],
    max_fanout_tasks: Any = _DEFAULTS["max_fanout_tasks"],
    query_timeout_seconds: Any = _DEFAULTS["query_timeout_seconds"],
    configured_source_available: bool = False,
    fixture_mode: bool = False,
    official_public_smoke: bool = False,
    explicit_overrides: set[str] | None = None,
) -> AutopilotExecutionProfile:
    """Return resolved execution bounds for product-facing investigation modes.

    Deep mode is deliberately not a label: unless a host explicitly supplies
    stronger limits, it raises the runtime floor so configured sources, graph
    expansion, capital checks, and fallback queues have enough budget to run.
    """
    normalized_mode = _mode(mode)
    overrides = set(explicit_overrides or set())
    raw = {
        "retrieval_concurrency": _coerce_number(retrieval_concurrency, _DEFAULTS["retrieval_concurrency"]),
        "fanout_rounds": _coerce_number(fanout_rounds, _DEFAULTS["fanout_rounds"]),
        "max_fanout_tasks": _coerce_number(max_fanout_tasks, _DEFAULTS["max_fanout_tasks"]),
        "query_timeout_seconds": _coerce_number(query_timeout_seconds, _DEFAULTS["query_timeout_seconds"]),
    }
    resolved = {key: _clamp(key, value) for key, value in raw.items()}

    if normalized_mode == "deep" and not official_public_smoke:
        for key, minimum in _DEEP_MINIMUMS.items():
            if key not in overrides:
                resolved[key] = _clamp(key, max(float(resolved[key]), float(minimum)))
    elif normalized_mode == "quick":
        for key, maximum in _QUICK_MAXIMUMS.items():
            if key not in overrides:
                resolved[key] = _clamp(key, min(float(resolved[key]), float(maximum)))

    if official_public_smoke:
        resolved["fanout_rounds"] = 1

    source_strategy = (
        "configured_sources_first_then_public_fallback"
        if configured_source_available
        else "default_public_autopilot_with_official_public_when_available"
    )
    if fixture_mode:
        source_strategy = "fixture_or_offline_smoke_no_live_source_claim"

    return AutopilotExecutionProfile(
        type="runtime_autopilot_profile",
        mode=normalized_mode,
        level="advanced_deep_autopilot" if normalized_mode == "deep" else f"{normalized_mode}_autopilot",
        interaction_model="subject_name_only_after_workspace_preconfiguration",
        source_strategy=source_strategy,
        retrieval_concurrency=int(resolved["retrieval_concurrency"]),
        fanout_rounds=int(resolved["fanout_rounds"]),
        max_fanout_tasks=int(resolved["max_fanout_tasks"]),
        query_timeout_seconds=float(resolved["query_timeout_seconds"]),
        configured_source_available=bool(configured_source_available),
        fixture_mode=bool(fixture_mode),
        official_public_smoke=bool(official_public_smoke),
        user_overrides={key: key in overrides for key in _DEFAULTS},
        runtime_must=[
            "run configured sources without mid-run user source selection",
            "use bounded retries and fallback routes for unavailable sources",
            "preserve source failures and evidence gaps in the final packet",
            "attempt relationship, capital, goods, people, and source-resilience closure in deep mode",
        ],
        runtime_must_not=[
            "ask the user to choose sources after subject submission",
            "stop solely because an advanced source is unavailable",
            "promote fallback leads into verified facts",
        ],
    )


def explicit_execution_overrides(data: dict[str, Any], keys: set[str] | None = None) -> set[str]:
    """Return execution-bound keys explicitly supplied by a host/API request."""
    requested = keys or set(_DEFAULTS)
    return {key for key in requested if key in data and data.get(key) not in (None, "")}


def build_deep_autopilot_execution_plan(
    *,
    runtime_autopilot: dict[str, Any],
    one_click_readiness: dict[str, Any],
    source_failure_summary: dict[str, Any],
    monitoring_seed: dict[str, Any],
    qyyjt_public_origin_handoff: dict[str, Any],
    subject_name: str = "",
) -> dict[str, Any]:
    """Build the machine-readable deep-mode plan used by desktop agents.

    The plan intentionally treats existing recovery queues as internal
    autopilot work, not a list of manual tasks for the end user.
    """
    runtime = runtime_autopilot if isinstance(runtime_autopilot, dict) else {}
    one_click = one_click_readiness if isinstance(one_click_readiness, dict) else {}
    failures = source_failure_summary if isinstance(source_failure_summary, dict) else {}
    monitoring = monitoring_seed if isinstance(monitoring_seed, dict) else {}
    qyyjt = qyyjt_public_origin_handoff if isinstance(qyyjt_public_origin_handoff, dict) else {}
    recovery_queue = monitoring.get("recovery_execution_queue") if isinstance(monitoring, dict) else {}
    if not isinstance(recovery_queue, dict):
        recovery_queue = {}
    source_resilience = one_click.get("source_resilience_recommended_step")
    if not isinstance(source_resilience, dict):
        source_resilience = {}
    retry_policy = one_click.get("source_resilience_retry_policy")
    if not isinstance(retry_policy, dict):
        retry_policy = {}

    operator_count = _int(one_click.get("operator_work_queue_count"))
    recovery_count = _int(recovery_queue.get("queued_count")) + _int(recovery_queue.get("blocked_count"))
    source_repair_count = _int(one_click.get("source_repair_priority_count"))
    public_origin_count = _int(one_click.get("public_origin_next_action_count"))
    capital_count = _int(one_click.get("capital_verification_queue_count"))
    relationship_count = _int(one_click.get("relationship_graph_audit_queue_count"))
    closure_count = sum(
        1
        for key in (
            "control_path_closure_needed",
            "goods_economics_closure_needed",
            "people_control_closure_needed",
            "capital_relationship_needed",
        )
        if bool(one_click.get(key))
    )
    queue_total = (
        operator_count
        + recovery_count
        + source_repair_count
        + public_origin_count
        + capital_count
        + relationship_count
        + closure_count
    )
    active = str(runtime.get("mode") or "").lower() == "deep"
    configured = bool(runtime.get("configured_source_available"))
    source_strategy = runtime.get("source_strategy") or (
        "configured_sources_first_then_public_fallback"
        if configured
        else "default_public_autopilot_with_official_public_when_available"
    )
    stop_conditions = [
        "configured_and_public_sources_exhausted_or_bounded_time_budget_reached",
        "all ready internal recovery queues completed or explicitly non-reliant",
        "capital_relationship_and_relationship_graph_closure_attempted",
        "report_exports_ready_with_evidence_gaps_and_failures_preserved",
    ]
    next_steps = _autopilot_next_steps(
        source_resilience=source_resilience,
        one_click=one_click,
        recovery_queue=recovery_queue,
        qyyjt=qyyjt,
    )
    continuation_entrypoints = _continuation_entrypoints(
        runtime=runtime,
        next_steps=next_steps,
        source_strategy=source_strategy,
        subject_name=subject_name,
    )
    return {
        "type": "deep_autopilot_execution_plan",
        "surface": "runtime_autopilot.execution_plan",
        "active": active,
        "mode": runtime.get("mode") or "standard",
        "subject_name": str(subject_name or "").strip(),
        "interaction_model": runtime.get("interaction_model")
        or "subject_name_only_after_workspace_preconfiguration",
        "automation_contract": {
            "user_input_after_subject_submission": "none_required_for_configured_sources",
            "user_confirmation_scope": "pre-run source credentials, licensed connectors, and export destinations only",
            "operator_work_queue_role": "internal_autopilot_recovery_queue_not_end_user_task_list",
            "fallback_behavior": "continue_with_available_sources_and_record_all_failures",
            "fact_admission_policy": "fallback leads stay lead-only until provenance and entity-match gates pass",
        },
        "execution_budget": {
            "retrieval_concurrency": _int(runtime.get("retrieval_concurrency")),
            "fanout_rounds": _int(runtime.get("fanout_rounds")),
            "max_fanout_tasks": _int(runtime.get("max_fanout_tasks")),
            "query_timeout_seconds": float(runtime.get("query_timeout_seconds") or 0.0),
        },
        "source_exhaustion": {
            "strategy": source_strategy,
            "configured_source_available": configured,
            "attempted_source_count": _int(failures.get("attempted_source_count")),
            "failed_source_count": _int(failures.get("failure_count")),
            "coverage_not_searched_count": _int(one_click.get("coverage_not_searched_count")),
            "coverage_no_evidence_count": _int(one_click.get("coverage_no_evidence_count")),
            "coverage_gap_severity": one_click.get("coverage_gap_severity") or "none",
            "done_condition": "every configured source is attempted, unavailable sources enter retry/fallback queues, and report caveats preserve gaps",
        },
        "source_recovery": {
            "retry_policy": retry_policy,
            "retryable": bool(one_click.get("source_resilience_retryable")),
            "max_attempts": _int(one_click.get("source_resilience_retry_max_attempts")),
            "recommended_step": source_resilience,
            "ready_to_run": bool(one_click.get("source_resilience_recommended_step_ready_to_run")),
            "blocked_reason": one_click.get("source_resilience_recommended_step_blocked_reason") or "",
            "repair_queue_count": source_repair_count,
            "recovery_queue_count": recovery_count,
            "packet_refs": [
                "one_click_readiness.source_resilience_recommended_step",
                "one_click_readiness.source_resilience_retry_policy",
                "monitoring_seed.recovery_execution_queue",
                "monitoring_seed.source_repair_priority_queue",
            ],
        },
        "public_origin_gap_bridge": {
            "bridge_count": _int(one_click.get("public_origin_gap_bridge_count")),
            "next_action_count": public_origin_count,
            "section_work_order_count": len(qyyjt.get("section_work_orders") or [])
            if isinstance(qyyjt.get("section_work_orders"), list)
            else 0,
            "top_action": one_click.get("public_origin_gap_bridge_top_action") or {},
            "policy": "Use public-origin rows as gap-closure leads, not facts, until provenance and entity-match gates pass.",
            "packet_refs": [
                "one_click_readiness.public_origin_gap_bridge",
                "qyyjt_public_origin_handoff.section_work_orders",
            ],
        },
        "closure": {
            "operator_work_internal_count": operator_count,
            "capital_verification_count": capital_count,
            "relationship_audit_count": relationship_count,
            "closure_step_count": closure_count,
            "can_make_clean_conclusion": bool(one_click.get("can_make_clean_conclusion")),
            "acceptance_status": one_click.get("acceptance_closure_status") or "unknown",
            "acceptance_blocking_count": _int(one_click.get("acceptance_closure_blocking_count")),
            "packet_refs": [
                "one_click_readiness.operator_work_queue",
                "one_click_readiness.capital_verification_queue",
                "one_click_readiness.relationship_graph_audit_queue",
                "one_click_readiness.acceptance_closure_summary",
            ],
        },
        "report_completion": {
            "required_outputs": ["docx_red_head", "portable_html", "markdown", "json_packet", "agent_handoff", "manifest"],
            "handoff_surface": "report_exports.directory_bundle.agent_handoff",
            "done_condition": "all report outputs are generated and agent-handoff preserves execution plan, evidence gaps, and delivery decision",
        },
        "queue_total": queue_total,
        "next_internal_steps": next_steps,
        "continuation_entrypoints": continuation_entrypoints,
        "continuation_policy": {
            "default": "rerun_deep_investigate_with_same_subject_and_configured_workspace",
            "no_user_prompt": True,
            "preserve_previous_packet": True,
            "merge_policy": "new admitted facts replace stale leads; unresolved prior gaps remain caveated until closed",
            "audit_policy": "append run id, source attempts, retry decisions, fallback use, and export verifier result",
        },
        "stop_conditions": stop_conditions,
        "must_not_stop_for": [
            "single_source_timeout",
            "empty_optional_source",
            "public_origin_gap_without_configured_credentials",
            "lead_only_relationship_edge",
        ],
        "policy": "Deep mode is an automatic execution contract for expert-configured workspaces; it should not ask users to choose sources after subject submission.",
    }


def build_deep_autopilot_source_runbook(
    *,
    runtime_autopilot: dict[str, Any],
    one_click_readiness: dict[str, Any],
    source_failure_summary: dict[str, Any],
    monitoring_seed: dict[str, Any],
    qyyjt_public_origin_handoff: dict[str, Any],
    execution_plan: dict[str, Any],
    subject_name: str = "",
) -> dict[str, Any]:
    """Build an agent-verifiable runbook for automatic deep-mode source work.

    This is intentionally more concrete than the execution plan: it names the
    lanes that a desktop agent must treat as automatic internal work after the
    subject is submitted, and exposes packet refs that prove each lane has a
    runtime surface.
    """
    runtime = runtime_autopilot if isinstance(runtime_autopilot, dict) else {}
    one_click = one_click_readiness if isinstance(one_click_readiness, dict) else {}
    failures = source_failure_summary if isinstance(source_failure_summary, dict) else {}
    monitoring = monitoring_seed if isinstance(monitoring_seed, dict) else {}
    qyyjt = qyyjt_public_origin_handoff if isinstance(qyyjt_public_origin_handoff, dict) else {}
    plan = execution_plan if isinstance(execution_plan, dict) else {}
    source_strategy = runtime.get("source_strategy") or plan.get("source_exhaustion", {}).get("strategy") or ""
    retry_policy = one_click.get("source_resilience_retry_policy")
    if not isinstance(retry_policy, dict):
        retry_policy = {}

    lanes = [
        _runbook_lane(
            lane_id="configured_sources",
            role="try preconfigured public, licensed, and user-authorized connectors",
            queue_count=_int(failures.get("attempted_source_count")),
            status="attempted_or_ready",
            packet_refs=[
                "runtime_autopilot",
                "source_failure_summary.attempted_source_count",
                "source_failure_summary.source_routing_summary",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="source_recovery",
            role="retry transient failures and downgrade unavailable sources to fallback lanes",
            queue_count=_int(one_click.get("source_repair_priority_count"))
            + _int(_dict(monitoring.get("recovery_execution_queue")).get("queued_count"))
            + _int(_dict(monitoring.get("recovery_execution_queue")).get("blocked_count")),
            status="internal_queue",
            packet_refs=[
                "one_click_readiness.source_resilience_recommended_step",
                "one_click_readiness.source_resilience_retry_policy",
                "monitoring_seed.recovery_execution_queue",
                "monitoring_seed.source_repair_priority_queue",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="official_public_sources",
            role="use zero-config official/public channels when configured sources are absent or fail",
            queue_count=_int(one_click.get("coverage_not_searched_count"))
            + _int(one_click.get("coverage_no_evidence_count")),
            status="fallback_ready",
            packet_refs=[
                "one_click_readiness.coverage_missing_domains",
                "one_click_readiness.coverage_domains_without_evidence",
                "source_failure_summary.coverage_recovery_actions",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="qyyjt_public_origin_bridge",
            role="translate commercial platform gaps into public-origin work orders",
            queue_count=_int(one_click.get("public_origin_gap_bridge_count"))
            + _int(one_click.get("public_origin_next_action_count"))
            + _int(qyyjt.get("section_work_order_count")),
            status="lead_only_gap_bridge",
            packet_refs=[
                "one_click_readiness.public_origin_gap_bridge",
                "one_click_readiness.public_origin_gap_bridge_top_action",
                "qyyjt_public_origin_handoff.section_work_orders",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="relationship_and_control_path",
            role="expand and audit related entities, controllers, and graph edges",
            queue_count=_int(one_click.get("relationship_graph_audit_queue_count"))
            + _int(one_click.get("control_path_signal_count")),
            status="closure_queue",
            packet_refs=[
                "one_click_readiness.relationship_graph_audit_queue",
                "one_click_readiness.relationship_graph_audit_top_step",
                "one_click_readiness.control_path_closure_step",
                "enterprise_cognition.control_ownership",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="capital_and_financing",
            role="verify capital pressure, financing signals, pledges, and related exposure",
            queue_count=_int(one_click.get("capital_verification_queue_count"))
            + (1 if one_click.get("capital_relationship_needed") else 0),
            status="closure_queue",
            packet_refs=[
                "one_click_readiness.graph_capital_exposure",
                "one_click_readiness.capital_verification_queue",
                "one_click_readiness.capital_verification_top_step",
                "one_click_readiness.capital_relationship_closure_step",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="goods_and_people_closure",
            role="close goods-flow, supply-chain, executive, and people-control gaps",
            queue_count=(1 if one_click.get("goods_economics_closure_needed") else 0)
            + (1 if one_click.get("people_control_closure_needed") else 0),
            status="closure_queue",
            packet_refs=[
                "one_click_readiness.goods_economics_closure_step",
                "one_click_readiness.people_control_closure_step",
                "enterprise_cognition.public_goods_profile",
                "enterprise_cognition.public_people_profile",
            ],
            retry_policy=retry_policy,
        ),
        _runbook_lane(
            lane_id="report_bundle_completion",
            role="generate and verify JSON, Markdown, DOCX, HTML, manifest, and agent handoff",
            queue_count=1,
            status="required_output",
            packet_refs=[
                "report_exports.print_package",
                "report_exports.portable_html",
                "report_exports.directory_bundle",
                "report_exports.directory_bundle.agent_handoff",
            ],
            retry_policy={"retryable": False, "max_attempts": 1},
        ),
    ]
    active = str(runtime.get("mode") or "").lower() == "deep"
    return {
        "type": "deep_autopilot_source_runbook",
        "surface": "runtime_autopilot.source_runbook",
        "active": active,
        "mode": runtime.get("mode") or "standard",
        "subject_name": str(subject_name or plan.get("subject_name") or "").strip(),
        "interaction_model": runtime.get("interaction_model")
        or "subject_name_only_after_workspace_preconfiguration",
        "source_strategy": source_strategy,
        "user_input_after_subject_submission": "none_required_for_configured_sources",
        "operator_queue_semantics": "internal_autopilot_recovery_queue_not_end_user_task_list",
        "lane_count": len(lanes),
        "automatic_lane_count": sum(1 for lane in lanes if lane.get("auto_execute")),
        "total_queue_count": sum(_int(lane.get("queue_count")) for lane in lanes),
        "execution_budget": plan.get("execution_budget") or {
            "retrieval_concurrency": _int(runtime.get("retrieval_concurrency")),
            "fanout_rounds": _int(runtime.get("fanout_rounds")),
            "max_fanout_tasks": _int(runtime.get("max_fanout_tasks")),
            "query_timeout_seconds": float(runtime.get("query_timeout_seconds") or 0.0),
        },
        "lanes": lanes,
        "fallback_order": [
            "configured_sources",
            "source_recovery",
            "official_public_sources",
            "qyyjt_public_origin_bridge",
            "relationship_and_control_path",
            "capital_and_financing",
            "goods_and_people_closure",
            "report_bundle_completion",
        ],
        "done_condition": (
            "all lanes have been attempted, exhausted, or caveated in the packet; "
            "report bundle verifier preserves runbook and execution plan"
        ),
        "must_not_prompt_user_for": [
            "source choice after subject submission",
            "whether to retry a transient connector failure",
            "whether to include configured deep-mode report outputs",
        ],
        "evidence_policy": "public/licensed/user-authorized only; fallback rows stay lead-only until admission gates pass",
    }


def _runbook_lane(
    *,
    lane_id: str,
    role: str,
    queue_count: Any,
    status: str,
    packet_refs: list[str],
    retry_policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "role": role,
        "status": status,
        "auto_execute": True,
        "queue_count": _int(queue_count),
        "retry_policy": retry_policy,
        "stop_on_failure": False,
        "user_prompt_required": False,
        "packet_refs": packet_refs,
        "done_condition": "lane attempted, exhausted, or explicitly caveated with provenance and admission policy",
    }


def _autopilot_next_steps(
    *,
    source_resilience: dict[str, Any],
    one_click: dict[str, Any],
    recovery_queue: dict[str, Any],
    qyyjt: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = [
        ("source_resilience", source_resilience, "run retry/fallback for the top failed or missing source"),
        ("source_recovery_execution", _first_dict(recovery_queue.get("ready")), "execute the first ready recovery task"),
        ("public_origin_gap_bridge", one_click.get("public_origin_gap_bridge_top_action"), "run the top public-origin gap bridge"),
        ("capital_verification", one_click.get("capital_verification_top_step"), "verify the top capital relationship lead"),
        ("relationship_graph_audit", one_click.get("relationship_graph_audit_top_step"), "audit the top relationship edge"),
        ("qyyjt_section_work_order", qyyjt.get("top_section_work_order"), "execute the top QYYJT public-origin section work order"),
    ]
    rows: list[dict[str, Any]] = []
    for index, (step_id, raw, fallback) in enumerate(candidates, start=1):
        item = raw if isinstance(raw, dict) else {}
        if not item and step_id != "source_resilience":
            continue
        rows.append(
            {
                "step_id": f"DEEP-AUTO-{index:02d}",
                "lane": step_id,
                "priority": item.get("priority") or ("P0" if index <= 2 else "P1"),
                "ready_to_run": bool(item.get("ready_to_run", True)),
                "action": item.get("action")
                or item.get("operator_action")
                or item.get("done_condition")
                or fallback,
                "done_condition": item.get("done_condition")
                or item.get("acceptance_gate")
                or "step_completed_or_marked_non_reliant_with_reason",
            }
        )
    return rows[:6]


def _continuation_entrypoints(
    *,
    runtime: dict[str, Any],
    next_steps: list[dict[str, Any]],
    source_strategy: str,
    subject_name: str = "",
) -> list[dict[str, Any]]:
    mode = str(runtime.get("mode") or "deep")
    command_mode = "deep" if mode == "deep" else mode
    subject = str(subject_name or "").strip() or "<same_subject>"
    subject_cli = _quote_cli_arg(subject)
    base = [
        {
            "id": "rerun_deep_investigate",
            "tool": "investigate_company",
            "mcp": {"tool": "investigate_company", "args": {"company_name": subject, "mode": command_mode}},
            "api": {"method": "POST", "path": "/api/investigate", "json": {"company": subject, "mode": command_mode}},
            "cli": f"npx wallstreet-tieling --investigate {subject_cli} --mode {command_mode}",
            "applies_to_lanes": ["source_resilience", "source_recovery_execution", "public_origin_gap_bridge", "qyyjt_section_work_order"],
            "source_strategy": source_strategy,
            "done_condition": "new packet has updated runtime_autopilot.execution_plan, source_failure_summary, one_click_readiness, and report_exports",
        },
        {
            "id": "expand_related_subject",
            "tool": "aggregate_subject",
            "mcp": {"tool": "aggregate_subject", "args": {"subject_id": "<related_subject_id>", "subject_name": "<related_subject_name>"}},
            "api": {"method": "POST", "path": "/api/aggregate", "json": {"subject_id": "<related_subject_id>", "subject_name": "<related_subject_name>"}},
            "cli": 'npx wallstreet-tieling --aggregate-subject "<related_subject_id>" --subject-name "<related_subject_name>"',
            "applies_to_lanes": ["relationship_graph_audit", "capital_verification"],
            "source_strategy": "relationship_or_capital_expansion_from_existing_packet",
            "done_condition": "related subject graph/profile is returned and linked back to the investigation packet as evidence or lead-only gap",
        },
        {
            "id": "verify_export_bundle",
            "tool": "verify_report_bundle",
            "mcp": {"tool": "verify_report_bundle", "args": {"path": "<export_dir>"}},
            "api": {"method": "POST", "path": "/api/verify-report-bundle", "json": {"path": "<export_dir>"}},
            "cli": 'npx wallstreet-tieling --verify-report-bundle "<export_dir>"',
            "applies_to_lanes": ["report_completion"],
            "source_strategy": "post_export_integrity_verification",
            "done_condition": "bundle verifier returns ok=true and agent_handoff.schema_valid=true",
        },
    ]
    lanes = {str(item.get("lane") or "") for item in next_steps if isinstance(item, dict)}
    rows = [
        {**item, "selected_for_current_plan": bool(lanes.intersection(set(item["applies_to_lanes"])))}
        for item in base
    ]
    if not any(item["selected_for_current_plan"] for item in rows):
        rows[0]["selected_for_current_plan"] = True
    return rows


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _quote_cli_arg(value: str) -> str:
    text = str(value or "").replace('"', '\\"')
    return f'"{text}"'


def _mode(value: Any) -> str:
    item = str(value or "standard").strip().lower()
    return item if item in {"quick", "standard", "deep"} else "standard"


def _coerce_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(key: str, value: float) -> float:
    low, high = _BOUNDS[key]
    return max(float(low), min(float(value), float(high)))
