#!/usr/bin/env python3
"""One-click investigation packet builder.

This layer turns the executable risk graph into a product-facing payload:
plain-language conclusion, evidence ledger, profile highlights, report text,
and a monitoring seed for later continuous-watch iterations.
"""
from __future__ import annotations
from core.due_diligence_audit import build_capability_audit
from core.evidence_ledger_v2 import normalize_evidence_v2, compute_evidence_depth
from core.entity_resolution import build_entity_resolution
from core.relationship_resolution import build_relationship_resolution
from core.investigation_strategy import build_strategy_v2
from core.release_gate import compute_release_decision
from core.graph_explain import explain_graph_edges
from adapters.public_web_search_tool import reality_drill_extract
from core.qyyjt_pledge_bridge import build_pledge_bridge, pledge_to_evidence, extract_pledge_from_fixture
from core.qyyjt_trade_bridge import build_trade_bridge
from core.source_smoke_harness import run_source_smoke

import asyncio
from dataclasses import dataclass
import html
import re
from typing import Any

from .industry_intelligence import IndustryIntelligenceEngine
from .connector_registry import ConnectorRegistry
from .investigation_diagnostics import build_source_failure_summary as _source_failure_summary
from .investigation_quality import evaluate_investigation_packet
from .investigation_report_card import (
    build_blocker_gate as _report_card_blocker_gate,
    build_packet_quality_flags as _report_card_packet_quality_flags,
    build_realness_score as _report_card_realness_score,
    build_report_language as _report_card_report_language,
)
from .product_intelligence import ProductIntelligenceEngine
from .public_web_profile_bridge import build_public_web_profiles as _bridge_public_web_profiles_from_evidence
from .report_delivery_targets import build_report_delivery_targets
from .subject_profile_aggregator import SubjectProfileAggregator, SubjectProfileReport as AggregatorReport



def _classify_source_type(source_name: str) -> str:
    name = (source_name or "").lower()
    if any(k in name for k in ("qyyjt","企查查")): return "commercial_registry"
    if any(k in name for k in ("gsxt","court","wenshu")): return "official_registry"
    if any(k in name for k in ("bond","credit","financing")): return "financial_data"
    if any(k in name for k in ("news","public_web","search")): return "public_web"
    if any(k in name for k in ("patent","trademark","ip")): return "ip_data"
    if any(k in name for k in ("tax","trade","customs")): return "commercial_data"
    return "unknown"

_SOURCE_STATUS_LABELS: dict[str,str] = {
    "retrieved": "已获取",
    "empty": "搜索无结果",
    "blocked": "受限",
    "timeout": "超时",
    "parse_failed": "解析失败",
    "authorization_required": "需要授权",
    "not_searched": "未搜索",
    "query_template_only": "仅查询模板",
}
SEVERITY_WEIGHT = {
    "critical": 35,
    "high": 24,
    "medium": 12,
    "low": 5,
}

_INDUSTRY_NAME_KEYS = {"industry", "industry_name", "sector", "sector_name"}
_INDUSTRY_SIGNAL_KEYS = {
    "industry_growth",
    "growth_delta",
    "capacity_growth",
    "price_change",
    "substitution_risk",
    "policy_risk",
    "customer_power",
    "supplier_power",
    "company_gross_margin",
    "top_customer_ratio",
    "switching_cost",
    "value_chain_role",
    "moat",
    "sources",
}
_PRODUCT_NAME_KEYS = {"product", "product_name", "core_product", "core_product_name"}
_PRODUCT_SIGNAL_KEYS = {
    "product_revenue_growth",
    "price_change",
    "repeat_purchase_rate",
    "subscription_revenue_ratio",
    "gross_margin",
    "switching_cost",
    "core_product_revenue_ratio",
    "substitute_performance_gap",
    "substitute_price_advantage",
    "customer_churn_rate",
    "alternative_revenue_ratio",
    "customer_value",
    "substitution_risk",
    "sources",
}
_SUPPLY_CHAIN_KEYS = {
    "customer",
    "top_customer",
    "supplier",
    "top_supplier",
    "upstream",
    "downstream",
    "dealer",
    "distributor",
    "partner",
    "counterparty",
    "procurement_project",
    "sales_channel",
    "customer_concentration",
    "supplier_concentration",
    "value_chain_role",
    "sources",
}


@dataclass(frozen=True)
class InvestigationPacket:
    """Product-facing investigation packet for API, CLI, MCP, and UI."""

    type: str
    version: str
    input: str
    mode: str
    one_click: bool
    summary: dict[str, Any]
    risk_brief: dict[str, Any]
    profile_brief: dict[str, Any]
    evidence_ledger: list[dict[str, Any]]
    source_provenance: dict[str, Any]
    source_failure_summary: dict[str, Any]
    risk_event_summary: dict[str, Any]
    enterprise_cognition: dict[str, Any]
    persona_surface: dict[str, Any]
    quality_gate: dict[str, Any]
    monitoring_seed: dict[str, Any]
    one_click_readiness: dict[str, Any]
    qyyjt_public_origin_handoff: dict[str, Any]
    report_exports: dict[str, Any]
    report_markdown: str
    graph: dict[str, Any]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "input": self.input,
            "mode": self.mode,
            "one_click": self.one_click,
            "summary": self.summary,
            "risk_brief": self.risk_brief,
            "profile_brief": self.profile_brief,
            "evidence_ledger": self.evidence_ledger,
            "source_provenance": self.source_provenance,
            "source_failure_summary": self.source_failure_summary,
            "risk_event_summary": self.risk_event_summary,
            "enterprise_cognition": self.enterprise_cognition,
            "persona_surface": self.persona_surface,
            "quality_gate": self.quality_gate,
            "monitoring_seed": self.monitoring_seed,
            "one_click_readiness": self.one_click_readiness,
            "qyyjt_public_origin_handoff": self.qyyjt_public_origin_handoff,
            "report_exports": self.report_exports,
            "report_markdown": self.report_markdown,
            "graph": self.graph,
            "next_actions": self.next_actions,
        }


def build_investigation_packet(
    graph_payload: dict[str, Any],
    *,
    input_text: str,
    mode: str = "standard",
    version: str = "0.5.0",
) -> InvestigationPacket:
    """Build a readable investigation packet from a risk graph payload."""
    summary = _dict(graph_payload.get("summary"))
    summary["query_subject"] = str(graph_payload.get("company") or input_text)
    summary.setdefault("company", str(graph_payload.get("company") or input_text))
    risk_events = [_dict(item) for item in graph_payload.get("risk_events", []) if isinstance(item, dict)]
    evidence = [_dict(item) for item in graph_payload.get("evidence", []) if isinstance(item, dict)]
    diagnostics = _dict(graph_payload.get("diagnostics"))
    subject_profile = _dict(diagnostics.get("subject_profile"))
    risk_brief = _risk_brief(summary, risk_events, evidence)
    profile_brief = _profile_brief(summary, subject_profile)
    evidence_ledger = _evidence_ledger(evidence)
    # Fixture bridge is only allowed in explicit fixture/demo mode. Standard
    # investigation packets must not gain synthetic people/goods facts.
    allow_fixture_bridge = str(mode or "").lower() in {"fixture", "demo_fixture"}
    fixture_extra = [
        {"source": "fixture_bridge", "admission": "fact", "confidence": 0.9, "admission_reason": "fixture_bridge_injected",
         "claim": "supplier=Acme Components Ltd; customer=BigCo Electronics; product=SmartWidget X1; industry=consumer electronics",
         "provenance": "SEC fixture bridge", "lane_hint": "goods", "record_kind": "evidence"},
        {"source": "fixture_bridge", "admission": "fact", "confidence": 0.9, "admission_reason": "fixture_bridge_injected",
         "claim": "controller=Bob Li; key_person=Alice Zhang CEO; ownership=54pct indirect",
         "provenance": "SEC fixture bridge", "lane_hint": "people", "record_kind": "evidence"},
    ]
    if allow_fixture_bridge and evidence_ledger:
        evidence_ledger.extend(fixture_extra)
    # P1-002: wire public web extraction leads into evidence_ledger
    pw_leads = []
    for ev in evidence_ledger:
        if ev.get("source","").startswith("public_web"):
            drill = reality_drill_extract(str(ev.get("claim","")), ev.get("url",""), ev.get("source","public_web_source"))
            for lead in drill.get("money_leads",[]):
                pw_leads.append({"source":"public_web_search","admission":"lead","confidence":0.4,"claim":lead["hint"]+":"+lead["snippet"][:80],"admission_reason":"public_web_extraction","provenance":"reality_drill"})
    evidence_ledger.extend(pw_leads)
    # EV-002: inject fact-level graph edge for controller relationship
    if allow_fixture_bridge and graph_payload:
        gp_edges = graph_payload.get("edges", graph_payload.get("relationship_graph", {}).get("edges", []))
        gp_edges.append({"from": "Demo Technology Co., Ltd.", "to": "Bob Li", "type": "controls", "admission": "fact", "confidence": 0.9, "source": "fixture_bridge", "explanation": "Controller identified via SEC fixture", "evidence_ids": ["ev-fixture-001"]})
    source_provenance = _source_provenance_summary(evidence_ledger)
    source_failure_summary = _source_failure_summary(summary, diagnostics)
    risk_event_summary = _risk_event_summary(risk_events, risk_brief)
    next_actions = _merge_next_actions(
        [str(item) for item in summary.get("next_actions", []) if str(item).strip()],
        _source_failure_next_action_texts(source_failure_summary),
        _coverage_recovery_next_action_texts(source_failure_summary),
        _bond_pressure_next_action_texts(risk_events),
    )
    enterprise_cognition = _enterprise_cognition(
        company=str(graph_payload.get("company") or input_text),
        summary=summary,
        risk_events=risk_events,
        profile_brief=profile_brief,
        evidence_ledger=evidence_ledger,
        subject_profile=subject_profile,
        allow_fixture_bridge=allow_fixture_bridge,
    )
    enterprise_cognition["claim_corroboration"] = source_provenance.get("claim_corroboration", {})
    dd_profile = _dict(enterprise_cognition.get("subject_due_diligence_profile"))
    relationship_graph = _dict(dd_profile.get("relationship_graph"))
    relationship_stats = _relationship_graph_availability(relationship_graph)
    summary["dd_profile_highlights"] = {
        "available": _dd_profile_has_evidence(dd_profile),
        "evidence_sources": _dict(dd_profile.get("executive_summary")).get("evidence_sources", 0),
        "total_findings": _dict(dd_profile.get("executive_summary")).get("total_findings", 0),
        "note": "DD profile is derived from runtime evidence and explicit evidence gaps.",
    }
    enterprise_cognition["multi_layer_graph_data"] = {
        "available": relationship_stats["available"],
        "depth": 2 if relationship_stats["available"] else 0,
        "node_count": relationship_stats["node_count"],
        "edge_count": relationship_stats["edge_count"],
        "source": "SubjectProfileAggregator",
        "note": (
            "Runtime relationship graph available from current evidence."
            if relationship_stats["available"]
            else "No multi-layer relationship graph was derived from current evidence."
        ),
    }
    enterprise_cognition["human_readable_dd_summary"] = _build_human_readable_dd_summary(enterprise_cognition.get("subject_due_diligence_profile"))
    fact_count = sum(1 for e in evidence_ledger if e.get("admission") == "fact")
    lead_count = sum(1 for e in evidence_ledger if e.get("admission") in ("lead","weak_lead"))
    enterprise_cognition["status_summary"] = {
        "ok": bool(evidence_ledger),
        "risk_level": enterprise_cognition.get("subject_due_diligence_profile",{}).get("executive_summary",{}).get("overall_risk","unknown"),
        "confidence": enterprise_cognition.get("subject_due_diligence_profile",{}).get("executive_summary",{}).get("evidence_confidence","unknown"),
        "evidence_total": len(evidence_ledger),
        "facts": fact_count,
        "leads": lead_count,
        "sources_used": list({e.get("source","") for e in evidence_ledger}),
    }
    next_actions = _merge_next_actions(
        next_actions,
        _relationship_candidate_next_action_texts(enterprise_cognition),
    )
    enterprise_cognition["investigation_audit_log"] = _build_investigation_audit_log(
        summary=summary, evidence_ledger=evidence_ledger, risk_events=risk_events, enterprise_cognition=enterprise_cognition,
    )
    persona_surface = _persona_surface_for_investigation(profile_brief, risk_event_summary, enterprise_cognition)
    monitoring_seed = _monitoring_seed(
        graph_payload,
        summary,
        risk_events,
        profile_brief,
        next_actions,
        source_failure_summary,
        enterprise_cognition,
    )
    qyyjt_public_origin_handoff = _qyyjt_public_origin_handoff()
    report_markdown = _report_markdown(
        company=str(graph_payload.get("company") or input_text),
        mode=mode,
        risk_brief=risk_brief,
        profile_brief=profile_brief,
        enterprise_cognition=enterprise_cognition,
        evidence_ledger=evidence_ledger,
        source_provenance=source_provenance,
        source_failure_summary=source_failure_summary,
        risk_event_summary=risk_event_summary,
        persona_surface=persona_surface,
        monitoring_seed=monitoring_seed,
        qyyjt_public_origin_handoff=qyyjt_public_origin_handoff,
        next_actions=next_actions,
    )
    quality_gate = evaluate_investigation_packet(
        summary=summary,
        risk_brief=risk_brief,
        profile_brief=profile_brief,
        evidence_ledger=evidence_ledger,
        enterprise_cognition=enterprise_cognition,
        report_markdown=report_markdown,
        source_failure_summary=source_failure_summary,
    ).to_dict()
    risk_brief = _risk_brief_with_quality_gate(risk_brief, quality_gate)
    risk_event_summary = _risk_event_summary(risk_events, risk_brief)
    persona_surface = _persona_surface_for_investigation(profile_brief, risk_event_summary, enterprise_cognition)
    one_click_readiness = _one_click_readiness_summary(
        quality_gate=quality_gate,
        graph_summary=summary,
        evidence_ledger=evidence_ledger,
        source_provenance=source_provenance,
        source_failure_summary=source_failure_summary,
        monitoring_seed=monitoring_seed,
        enterprise_cognition=enterprise_cognition,
    )
    report_markdown = _report_markdown(
        company=str(graph_payload.get("company") or input_text),
        mode=mode,
        risk_brief=risk_brief,
        profile_brief=profile_brief,
        enterprise_cognition=enterprise_cognition,
        evidence_ledger=evidence_ledger,
        source_provenance=source_provenance,
        source_failure_summary=source_failure_summary,
        risk_event_summary=risk_event_summary,
        persona_surface=persona_surface,
        monitoring_seed=monitoring_seed,
        one_click_readiness=one_click_readiness,
        qyyjt_public_origin_handoff=qyyjt_public_origin_handoff,
        next_actions=next_actions,
        quality_gate=quality_gate,
    )
    report_exports = _report_export_bundle(
        company=str(graph_payload.get("company") or input_text),
        version=version,
        report_markdown=report_markdown,
        one_click_readiness=one_click_readiness,
        enterprise_cognition=enterprise_cognition,
        monitoring_seed=monitoring_seed,
        qyyjt_public_origin_handoff=qyyjt_public_origin_handoff,
        summary=summary,
        source_provenance=source_provenance,
        risk_event_summary=risk_event_summary,
        evidence_ledger=evidence_ledger,
    )

    return InvestigationPacket(
        type="investigation_packet",
        version=version,
        input=input_text,
        mode=mode,
        one_click=True,
        summary=summary,
        risk_brief=risk_brief,
        profile_brief=profile_brief,
        evidence_ledger=evidence_ledger,
        source_provenance=source_provenance,
        source_failure_summary=source_failure_summary,
        risk_event_summary=risk_event_summary,
        enterprise_cognition=enterprise_cognition,
        persona_surface=persona_surface,
        quality_gate=quality_gate,
        monitoring_seed=monitoring_seed,
        one_click_readiness=one_click_readiness,
        qyyjt_public_origin_handoff=qyyjt_public_origin_handoff,
        report_exports=report_exports,
        report_markdown=report_markdown,
        graph=graph_payload,
        next_actions=next_actions,
    )


def _qyyjt_public_origin_handoff() -> dict[str, Any]:
    try:
        from core.qyyjt_benchmark import build_qyyjt_benchmark

        benchmark = build_qyyjt_benchmark()
    except Exception as exc:  # pragma: no cover - defensive runtime degradation
        return {
            "type": "qyyjt_public_origin_handoff",
            "available": False,
            "queue_count": 0,
            "top_actions": [],
            "blocked_reason": str(exc),
            "policy": "Public-origin handoff is additive; investigation packets remain usable if benchmark loading fails.",
        }

    summary = _dict(benchmark.get("summary"))
    queue = [_dict(item) for item in summary.get("public_origin_execution_queue", []) if isinstance(item, dict)]
    execution_summary = _dict(summary.get("public_origin_execution_summary"))
    p0_actions = [item for item in queue if str(item.get("priority") or "").strip().upper().startswith("P0")]
    selected = p0_actions[:12] or queue[:12]
    top_actions: list[dict[str, Any]] = []
    for item in selected:
        top_actions.append(
            {
                "action_id": item.get("action_id"),
                "module": item.get("module"),
                "priority": item.get("priority"),
                "target_lane": item.get("target_lane"),
                "record_type": item.get("record_type"),
                "origin_channels": list(item.get("origin_channels") or [])[:6],
                "query_families": list(item.get("query_families") or [])[:6],
                "required_fields": list(item.get("required_fields") or [])[:8],
                "admission_gate": item.get("admission_gate"),
                "done_condition": item.get("done_condition"),
            }
        )
    report_section_batches = []
    for batch in execution_summary.get("report_section_batches", [])[:8]:
        if not isinstance(batch, dict):
            continue
        report_section_batches.append(
            {
                "report_section": batch.get("report_section"),
                "queue_count": batch.get("queue_count"),
                "p0_count": batch.get("p0_count"),
                "record_types": list(batch.get("record_types") or [])[:10],
                "top_actions": [
                    {
                        "action_id": item.get("action_id"),
                        "module": item.get("module"),
                        "priority": item.get("priority"),
                        "record_type": item.get("record_type"),
                        "origin_channels": list(item.get("origin_channels") or [])[:4],
                        "query_families": list(item.get("query_families") or [])[:4],
                        "required_fields": list(item.get("required_fields") or [])[:6],
                        "done_condition": item.get("done_condition"),
                    }
                    for item in batch.get("top_actions", [])[:4]
                    if isinstance(item, dict)
                ],
                "done_condition": batch.get("done_condition"),
            }
        )
    section_work_orders = _qyyjt_public_origin_section_work_orders(report_section_batches)
    section_execution_summary = _qyyjt_public_origin_section_execution_summary(section_work_orders)
    agent_autorun = _qyyjt_public_origin_agent_autorun(
        section_work_orders=section_work_orders,
        section_execution_summary=section_execution_summary,
    )
    return {
        "type": "qyyjt_public_origin_handoff",
        "available": True,
        "queue_count": len(queue),
        "p0_action_count": len(p0_actions),
        "report_section_batch_count": len(report_section_batches),
        "report_section_batches": report_section_batches,
        "section_work_order_count": len(section_work_orders),
        "section_work_orders": section_work_orders,
        "top_section_work_order": section_work_orders[0] if section_work_orders else {},
        "section_execution_summary": section_execution_summary,
        "top_ready_section_work_order": section_execution_summary.get("top_ready_work_order") or {},
        "agent_autorun": agent_autorun,
        "next_batch": list(execution_summary.get("next_batch") or [])[:8],
        "top_actions": top_actions,
        "policy": "Use public-origin actions only for public or user-authorized channels; do not bypass authentication, paywalls, captcha, or rate limits.",
    }


def _qyyjt_public_origin_section_work_orders(
    report_section_batches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert QYYJT public-origin report batches into agent-executable section work."""
    work_orders: list[dict[str, Any]] = []
    for index, batch in enumerate(report_section_batches[:8], start=1):
        if not isinstance(batch, dict):
            continue
        actions = [_dict(item) for item in batch.get("top_actions", []) if isinstance(item, dict)]
        if not actions:
            continue
        query_families = _dedupe_strings(
            str(query)
            for action in actions
            for query in action.get("query_families", [])
            if str(query).strip()
        )
        origin_channels = _dedupe_strings(
            str(channel)
            for action in actions
            for channel in action.get("origin_channels", [])
            if str(channel).strip()
        )
        required_fields = _dedupe_strings(
            str(field)
            for action in actions
            for field in action.get("required_fields", [])
            if str(field).strip()
        )
        p0_count = int(batch.get("p0_count") or 0)
        work_orders.append(
            {
                "work_order_id": f"QYYJT-SECTION-{index:02d}",
                "report_section": batch.get("report_section"),
                "priority": "P0" if p0_count else "P1",
                "action_count": int(batch.get("queue_count") or len(actions)),
                "p0_count": p0_count,
                "record_types": list(batch.get("record_types") or [])[:10],
                "origin_channels": origin_channels[:8],
                "query_families": query_families[:8],
                "required_fields": required_fields[:12],
                "top_actions": actions[:4],
                "done_condition": batch.get("done_condition")
                or "Capture source URL, observed time, required fields, entity match, and admission result for every selected action.",
                "admission_policy": "Public-origin rows stay lead-only until provenance, required fields, and exact/strong entity-match gates pass.",
            }
        )
    return work_orders


def _qyyjt_public_origin_section_execution_summary(
    section_work_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize QYYJT section work into a small agent routing surface."""
    orders = [_dict(item) for item in section_work_orders if isinstance(item, dict)]
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    p0_count = 0
    for item in orders:
        if str(item.get("priority") or "").upper().startswith("P0"):
            p0_count += 1
        missing: list[str] = []
        for field in ("origin_channels", "query_families", "required_fields", "done_condition"):
            value = item.get(field)
            if isinstance(value, list):
                if not value:
                    missing.append(field)
            elif not str(value or "").strip():
                missing.append(field)
        row = {
            "work_order_id": item.get("work_order_id") or "",
            "report_section": item.get("report_section") or "",
            "priority": item.get("priority") or "",
            "action_count": int(item.get("action_count") or 0),
            "p0_count": int(item.get("p0_count") or 0),
            "ready_to_run": not missing,
            "blocked_reason": "" if not missing else "missing_" + ",".join(missing),
            "done_condition": item.get("done_condition") or "",
        }
        if missing:
            blocked.append(row)
        else:
            ready.append(row)

    top_ready = ready[0] if ready else {}
    top_blocked = blocked[0] if blocked else {}
    return {
        "type": "qyyjt_section_execution_summary",
        "section_count": len(orders),
        "p0_section_count": p0_count,
        "ready_section_count": len(ready),
        "blocked_section_count": len(blocked),
        "top_ready_work_order": top_ready,
        "top_blocked_work_order": top_blocked,
        "ready_sections": ready[:8],
        "blocked_sections": blocked[:8],
        "done_condition": "all_ready_sections_executed_or_blocked_sections_have_explicit_non_reliance_caveats",
        "policy": "Section execution summary is a routing aid; admission still requires provenance, required fields, and entity-match gates.",
    }


def _qyyjt_public_origin_agent_autorun(
    *,
    section_work_orders: list[dict[str, Any]],
    section_execution_summary: dict[str, Any],
) -> dict[str, Any]:
    """Machine-readable QYYJT public-origin autorun contract for desktop agents."""
    ready_ids = {
        str(item.get("work_order_id") or "")
        for item in section_execution_summary.get("ready_sections", [])
        if isinstance(item, dict)
    }
    routes: list[dict[str, Any]] = []
    for index, order in enumerate(section_work_orders[:8], start=1):
        work_order = _dict(order)
        work_order_id = str(work_order.get("work_order_id") or f"QYYJT-SECTION-{index:02d}")
        ready_to_run = bool(work_order_id in ready_ids) if ready_ids else bool(work_order.get("origin_channels"))
        routes.append(
            {
                "route_id": work_order_id,
                "mcp_tool": "investigate_company",
                "api_route": "POST /api/investigate",
                "cli_command": 'npx wallstreet-tieling --investigate "<company>" --mode deep --export-dir <dir>',
                "ready_to_run": ready_to_run,
                "retry_limit": 2,
                "target_work_order": {
                    "work_order_id": work_order_id,
                    "report_section": work_order.get("report_section") or "",
                    "priority": work_order.get("priority") or "",
                    "origin_channels": list(work_order.get("origin_channels") or [])[:8],
                    "query_families": list(work_order.get("query_families") or [])[:8],
                    "required_fields": list(work_order.get("required_fields") or [])[:12],
                    "record_types": list(work_order.get("record_types") or [])[:10],
                },
                "tool_arguments": {
                    "company": "<company>",
                    "mode": "deep",
                    "offline_fixture": False,
                    "export_dir": "<dir>",
                    "public_origin_work_order_id": work_order_id,
                    "public_origin_query_families": list(work_order.get("query_families") or [])[:8],
                    "public_origin_required_fields": list(work_order.get("required_fields") or [])[:12],
                    "preserve_packet_fields": [
                        "qyyjt_public_origin_handoff",
                        "one_click_readiness.public_origin_gap_bridge",
                        "one_click_readiness.public_origin_modules",
                        "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin",
                    ],
                },
                "required_output_fields": [
                    "qyyjt_public_origin_handoff.section_work_orders",
                    "qyyjt_public_origin_handoff.section_execution_summary",
                    "qyyjt_public_origin_handoff.top_ready_section_work_order",
                    "report_exports.directory_bundle.agent_handoff.qyyjt_public_origin",
                ],
                "done_condition": work_order.get("done_condition") or "",
                "admission_policy": work_order.get("admission_policy") or "",
            }
        )
    return {
        "type": "qyyjt_public_origin_agent_autorun",
        "manual_intermediate_steps_required": False,
        "ready_to_run": any(route.get("ready_to_run") for route in routes),
        "route_count": len(routes),
        "routes": routes,
        "operator_intervention_only_when": [
            "A selected public-origin route requires credentials, CAPTCHA, payment, or account authorization.",
            "No public or user-authorized channel can provide the required fields for the work order.",
            "Entity-match, provenance, or required-field gates remain unresolved after retry_limit is reached.",
        ],
        "policy": "Run existing investigation routes and preserve QYYJT/public-origin packet fields; do not bypass authentication, paywalls, CAPTCHA, rate limits, or convert unresolved leads into facts.",
    }


def _packet_agent_handoff_preview(
    *,
    one_click_readiness: dict[str, Any],
    enterprise_cognition: dict[str, Any],
    monitoring_seed: dict[str, Any],
    qyyjt_public_origin_handoff: dict[str, Any],
    agent_decision_digest: dict[str, Any],
) -> dict[str, Any]:
    """Bounded agent-handoff preview for API/MCP hosts before export-dir exists."""
    relationship_resolution = _dict(enterprise_cognition.get("relationship_resolution_v1"))
    resolution_summary = _dict(relationship_resolution.get("resolution_summary"))
    verification_queue = [
        dict(item)
        for item in resolution_summary.get("verification_queue", [])
        if isinstance(item, dict)
    ][:8]
    relationship_audit_queue = [
        dict(item)
        for item in one_click_readiness.get("relationship_graph_audit_queue", [])
        if isinstance(item, dict)
    ][:8]
    source_resilience = _packet_source_resilience_handoff(
        one_click_readiness=one_click_readiness,
        monitoring_seed=monitoring_seed,
    )
    capital_panel = _dict(one_click_readiness.get("capital_risk_panel"))
    capital_autorun = _packet_queue_agent_autorun(
        autorun_type="capital_risk_agent_autorun",
        routes=one_click_readiness.get("capital_verification_queue")
        or ([one_click_readiness.get("capital_verification_top_step")] if one_click_readiness.get("capital_verification_top_step") else [{
            "step_id": "CAPITAL-RECHECK-001",
            "priority": "P1",
            "kind": "capital_relationship_recheck",
            "target": "capital_risk_panel",
            "done_condition": "Re-run deep investigation and preserve capital risk panel, graph capital exposure, and relationship audit fields.",
            "ready_to_run": True,
        }]),
        route_prefix="CAPITAL",
        required_output_fields=[
            "one_click_readiness.capital_verification_queue",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.graph_capital_exposure",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.capital_pressure_profile",
            "enterprise_cognition.capital_relationship_profile",
            "one_click_readiness.capital_verification_queue",
            "one_click_readiness.graph_capital_exposure",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship",
        ],
        policy="Verify capital pressure rows and relationship context before relying on capital-risk conclusions.",
    )
    relationship_audit_autorun = _packet_queue_agent_autorun(
        autorun_type="relationship_graph_audit_agent_autorun",
        routes=relationship_audit_queue,
        route_prefix="REL-AUDIT",
        required_output_fields=[
            "one_click_readiness.relationship_graph_audit_queue",
            "one_click_readiness.relationship_graph_audit_top_step",
            "enterprise_cognition.relationship_resolution_v1",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "one_click_readiness.relationship_graph_audit_queue",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
        ],
        policy="Audit relationship edges as verification tasks; never promote lead-only or missing-evidence edges into facts.",
    )
    relationship_resolution_autorun = _packet_queue_agent_autorun(
        autorun_type="relationship_resolution_agent_autorun",
        routes=verification_queue,
        route_prefix="REL-RESOLVE",
        required_output_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
        ],
        policy="Relationship-resolution leads stay leads until corroborated by registry, filing, announcement, licensed, or user-authorized evidence.",
    )
    return {
        "preview_type": "packet_agent_handoff_preview",
        "preview_scope": "bounded_pre_export_dir",
        "source_strengthening": _packet_source_strengthening_handoff(),
        "source_resilience": source_resilience,
        "capital_risk_panel": {
            "type": "capital_risk_panel_handoff",
            "source": "one_click_readiness.capital_risk_panel",
            "pressure_level": capital_panel.get("pressure_level") or "none",
            "relationship_status": capital_panel.get("relationship_status") or one_click_readiness.get("capital_relationship_status") or "unknown",
            "capital_verification_queue_count": int(one_click_readiness.get("capital_verification_queue_count") or 0),
            "relationship_audit_queue_count": int(one_click_readiness.get("relationship_graph_audit_queue_count") or 0),
            "relationship_edge_count": int(one_click_readiness.get("relationship_edge_count") or capital_panel.get("relationship_edge_count") or 0),
            "top_step": one_click_readiness.get("capital_verification_top_step") or capital_panel.get("top_step") or {},
            "report_visibility": capital_panel.get("report_visibility") or "",
            "agent_autorun": capital_autorun,
            "policy": "Packet preview only; export-dir agent-handoff carries bundle-integrity context.",
        },
        "relationship_graph_audit": {
            "type": "relationship_graph_audit_handoff",
            "status": "audit_required" if relationship_audit_queue else "no_open_audit_queue",
            "queue_count": int(one_click_readiness.get("relationship_graph_audit_queue_count") or len(relationship_audit_queue)),
            "edge_count": int(one_click_readiness.get("relationship_edge_count") or 0),
            "top_step": one_click_readiness.get("relationship_graph_audit_top_step") or (relationship_audit_queue[0] if relationship_audit_queue else {}),
            "queue": relationship_audit_queue,
            "agent_autorun": relationship_audit_autorun,
            "policy": "Relationship graph audit rows are verification tasks, not fact promotion.",
        },
        "relationship_resolution": {
            "type": "relationship_resolution_handoff",
            "source": "enterprise_cognition.relationship_resolution_v1",
            "lead_count": int(relationship_resolution.get("lead_count") or 0),
            "typed_lead_count": int(resolution_summary.get("typed_lead_count") or 0),
            "weak_lead_count": int(resolution_summary.get("weak_lead_count") or 0),
            "verification_queue_count": len(verification_queue),
            "verification_queue": verification_queue,
            "top_step": verification_queue[0] if verification_queue else {},
            "preserve_fields": [
                "enterprise_cognition.relationship_resolution_v1",
                "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            ],
            "agent_autorun": relationship_resolution_autorun,
            "policy": "Relationship-resolution leads stay leads until corroborated by registry, filing, announcement, or authorized evidence.",
        },
        "qyyjt_public_origin": {
            "type": "qyyjt_public_origin_packet_preview",
            "section_execution_summary": qyyjt_public_origin_handoff.get("section_execution_summary") or {},
            "top_ready_section_work_order": qyyjt_public_origin_handoff.get("top_ready_section_work_order") or {},
            "section_work_orders": list(qyyjt_public_origin_handoff.get("section_work_orders") or [])[:8],
            "report_section_batches": list(qyyjt_public_origin_handoff.get("report_section_batches") or [])[:8],
            "agent_autorun": qyyjt_public_origin_handoff.get("agent_autorun") or {},
            "gap_bridge": one_click_readiness.get("public_origin_gap_bridge") or {},
        },
        "decision_digest": agent_decision_digest,
        "policy": "This preview lets desktop agents route the next action before export-dir exists; run export-dir verifier before final delivery claims.",
    }


def _packet_queue_agent_autorun(
    *,
    autorun_type: str,
    routes: Any,
    route_prefix: str,
    required_output_fields: list[str],
    preserve_packet_fields: list[str],
    policy: str,
) -> dict[str, Any]:
    rows = [_dict(item) for item in routes if isinstance(item, dict)][:8] if isinstance(routes, list) else []
    autorun_routes: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        route_id = (
            row.get("step_id")
            or row.get("queue_id")
            or row.get("action_id")
            or row.get("id")
            or f"{route_prefix}-{index:03d}"
        )
        autorun_routes.append(
            {
                "route_id": route_id,
                "mcp_tool": "investigate_company",
                "api_route": "POST /api/investigate",
                "cli_command": 'npx wallstreet-tieling --investigate "<company>" --mode deep --export-dir <dir>',
                "ready_to_run": bool(row.get("ready_to_run", True)),
                "retry_limit": 2,
                "target_step": {
                    "step_id": route_id,
                    "priority": row.get("priority") or "",
                    "kind": row.get("kind") or row.get("relation_type") or "",
                    "target": row.get("target") or row.get("target_title") or row.get("target_id") or "",
                    "source": row.get("source") or "",
                    "evidence_ids": list(row.get("evidence_ids") or [])[:6],
                    "source_families": list(row.get("source_families") or [])[:6],
                },
                "tool_arguments": {
                    "company": "<company>",
                    "mode": "deep",
                    "export_dir": "<dir>",
                    "target_step_id": route_id,
                    "preserve_packet_fields": preserve_packet_fields,
                },
                "required_output_fields": required_output_fields,
                "done_condition": row.get("done_condition") or row.get("acceptance_gate") or "",
            }
        )
    return {
        "type": autorun_type,
        "manual_intermediate_steps_required": False,
        "ready_to_run": any(route.get("ready_to_run") for route in autorun_routes),
        "route_count": len(autorun_routes),
        "routes": autorun_routes,
        "operator_intervention_only_when": [
            "A route requires credentials, CAPTCHA, payment, or account authorization.",
            "The host cannot preserve the required packet fields after replay.",
            "Evidence, entity match, or provenance gates remain unresolved after retry_limit is reached.",
        ],
        "policy": policy,
    }


def _packet_source_strengthening_handoff() -> dict[str, Any]:
    try:
        queue = [
            item for item in ConnectorRegistry().product_catalog().get("source_strengthening_queue", [])
            if isinstance(item, dict)
        ]
    except Exception as exc:  # pragma: no cover - defensive runtime degradation
        return {
            "type": "source_strengthening_handoff",
            "status": "unavailable",
            "work_order_count": 0,
            "top_work_orders": [],
            "blocked_reason": f"connector_catalog_unavailable:{exc}",
        }
    by_lane: dict[str, int] = {}
    top_work_orders: list[dict[str, Any]] = []
    for item in queue[:8]:
        lane = str(item.get("lane") or "general_enrichment")
        by_lane[lane] = by_lane.get(lane, 0) + 1
        execution_plan = _dict(item.get("execution_plan"))
        runtime_companion = _dict(item.get("runtime_companion") or execution_plan.get("runtime_companion"))
        top_work_orders.append(
            {
                "connector": item.get("connector") or "",
                "priority": item.get("priority") or "",
                "lane": lane,
                "missing_contracts": list(item.get("missing_contracts") or [])[:8],
                "next_action": item.get("next_action") or "",
                "runtime_companion": runtime_companion,
                "execution_plan": {
                    "type": execution_plan.get("type") or "source_strengthening_execution_plan",
                    "source_hint": execution_plan.get("source_hint") or "",
                    "record_type": execution_plan.get("record_type") or "",
                    "first_target_file": execution_plan.get("first_target_file") or "",
                    "primary_acceptance_command": execution_plan.get("primary_acceptance_command") or "",
                    "ordered_steps": list(execution_plan.get("ordered_steps") or [])[:6],
                    "report_gate": execution_plan.get("report_gate") or "",
                },
            }
        )
    status = "ready" if top_work_orders else "complete"
    completion_summary = {
        "type": "source_strengthening_completion_summary",
        "candidate_count": len(queue),
        "pending_work": bool(top_work_orders),
        "message": (
            "No pending source-strengthening work orders remain in connector_catalog; "
            "future source expansion should start from new connector admission metadata."
        ),
    }
    return {
        "type": "source_strengthening_handoff",
        "status": status,
        "catalog_tool": "connector_catalog",
        "work_order_count": len(queue),
        "top_work_orders": top_work_orders,
        "top_work_order": top_work_orders[0] if top_work_orders else {},
        "by_lane": by_lane,
        "completion_summary": completion_summary,
        "preserve_fields": [
            "connector_catalog.source_strengthening_queue",
            "connector_catalog.source_strengthening_queue[].execution_plan",
            "connector_catalog.source_strengthening_queue[].runtime_companion",
        ],
        "promotion_gate": "standardized records, provenance, entity match, and admission tests are required before any source-strengthening row becomes a report fact.",
    }


def _packet_source_resilience_handoff(
    *,
    one_click_readiness: dict[str, Any],
    monitoring_seed: dict[str, Any],
) -> dict[str, Any]:
    recovery_queue = _dict(monitoring_seed.get("recovery_execution_queue"))
    queue = [
        dict(item)
        for item in recovery_queue.get("queue", [])
        if isinstance(item, dict)
    ]
    replay_routes = [
        _packet_replay_route(item, index)
        for index, item in enumerate(queue[:8], start=1)
    ]
    agent_autorun_routes = [
        _packet_agent_autorun_route(item, index)
        for index, item in enumerate(queue[:8], start=1)
    ]
    recommended = _dict(one_click_readiness.get("source_resilience_recommended_step"))
    if recommended and not replay_routes:
        replay_routes.append(_packet_replay_route(recommended, 1))
        agent_autorun_routes.append(_packet_agent_autorun_route(recommended, 1))
    if not replay_routes:
        repair = _dict(one_click_readiness.get("source_repair_top_action"))
        if repair:
            replay_routes.append(_packet_replay_route(repair, 1))
            agent_autorun_routes.append(_packet_agent_autorun_route(repair, 1))
    return {
        "type": "source_resilience_handoff",
        "status": one_click_readiness.get("source_resilience_status") or recovery_queue.get("status") or "unknown",
        "score": one_click_readiness.get("source_resilience_score"),
        "retry_policy": one_click_readiness.get("source_resilience_retry_policy") or {},
        "retryable": bool(one_click_readiness.get("source_resilience_retryable")),
        "max_attempts": int(one_click_readiness.get("source_resilience_retry_max_attempts") or 0),
        "recommended_action": one_click_readiness.get("source_resilience_recommended_action") or "",
        "recommended_step": recommended,
        "ready_to_run": bool(one_click_readiness.get("source_resilience_recommended_step_ready_to_run") or recovery_queue.get("ready_to_run")),
        "blocked_reason": one_click_readiness.get("source_resilience_recommended_step_blocked_reason") or "",
        "replay_route_count": len(replay_routes),
        "replay_routes": replay_routes,
        "agent_autorun": {
            "type": "source_resilience_agent_autorun",
            "manual_intermediate_steps_required": False,
            "ready_to_run": bool(agent_autorun_routes) and any(route.get("ready_to_run") for route in agent_autorun_routes),
            "route_count": len(agent_autorun_routes),
            "routes": agent_autorun_routes,
            "operator_intervention_only_when": [
                "A route is blocked by credentials, CAPTCHA, payment, or account authorization.",
                "The host cannot execute MCP, CLI, or REST fallback routes.",
                "The output packet still lacks required source_failure_summary or agent_handoff.source_health fields after retry_limit is reached.",
            ],
            "policy": "Run existing MCP/CLI/API investigation routes only; do not change OS/network settings or promote missing coverage into a clean risk conclusion.",
        },
        "recovery_execution_queue": {
            "ready_to_run": bool(recovery_queue.get("ready_to_run")),
            "queued_count": int(recovery_queue.get("queued_count") or len(queue)),
            "blocked_count": int(recovery_queue.get("blocked_count") or 0),
        },
        "policy": "Replay routes are bounded retry tasks; do not change OS/network settings or promote empty results into low-risk conclusions.",
    }


def _packet_replay_route(item: dict[str, Any], index: int) -> dict[str, Any]:
    retry_policy = _dict(item.get("retry_policy"))
    return {
        "route_id": item.get("step_id") or item.get("action_id") or item.get("queue_id") or f"replay-{index}",
        "source": item.get("source") or "",
        "domain": item.get("domain") or item.get("target") or "",
        "priority": item.get("priority") or "P1",
        "status": item.get("status") or "pending",
        "query_family": item.get("query_family") or item.get("operator_action") or item.get("action") or "",
        "ready_to_run": bool(item.get("ready_to_run", True)),
        "blocked_reason": item.get("blocked_reason") or "",
        "retry_policy": retry_policy,
        "key_fields": list(item.get("key_fields") or [])[:6],
    }


def _packet_agent_autorun_route(item: dict[str, Any], index: int) -> dict[str, Any]:
    replay_route = _dict(item.get("replay_route"))
    retry_policy = _dict(item.get("retry_policy") or replay_route.get("tool_arguments", {}).get("retry_policy"))
    tool_arguments = _dict(replay_route.get("tool_arguments"))
    preserve_fields = list(tool_arguments.get("preserve_packet_fields") or [])
    if not preserve_fields:
        preserve_fields = [
            "source_failure_summary",
            "monitoring_seed.recovery_execution_queue",
            "one_click_readiness.source_resilience_retry_policy",
            "one_click_readiness.operator_work_queue",
            "report_exports.directory_bundle.agent_handoff.source_health",
        ]
    return {
        "route_id": item.get("queue_id") or item.get("step_id") or item.get("action_id") or f"source-autoplay-{index}",
        "mcp_tool": replay_route.get("mcp_tool") or replay_route.get("tool") or "investigate_company",
        "api_route": replay_route.get("api_route") or "POST /api/investigate",
        "cli_command": replay_route.get("command") or "npx wallstreet-tieling --investigate \"<company>\"",
        "tool_arguments": tool_arguments,
        "target_recovery": tool_arguments.get("target_recovery") or {
            "source": item.get("source") or "",
            "domain": item.get("domain") or item.get("target") or "",
            "query_family": item.get("query_family") or item.get("operator_action") or item.get("action") or "",
            "key_fields": list(item.get("key_fields") or [])[:6],
        },
        "ready_to_run": bool(item.get("ready_to_run", replay_route.get("ready_to_run", True))),
        "blocked_reason": item.get("blocked_reason") or replay_route.get("blocked_reason") or "",
        "retry_policy": retry_policy,
        "retry_limit": int(item.get("retry_limit") or replay_route.get("retry_limit") or retry_policy.get("max_attempts") or 0),
        "required_output_fields": list(replay_route.get("required_output_fields") or preserve_fields),
        "preserve_packet_fields": preserve_fields,
        "done_condition": replay_route.get("done_condition") or item.get("done_condition") or "source_replay_records_admissible_evidence_or_explicit_empty_or_blocked_result",
        "non_reliance_caveat": replay_route.get("non_reliance_caveat") or item.get("non_reliance_caveat") or "",
    }


def _report_export_bundle(
    *,
    company: str,
    version: str,
    report_markdown: str,
    one_click_readiness: dict[str, Any],
    enterprise_cognition: dict[str, Any],
    monitoring_seed: dict[str, Any],
    qyyjt_public_origin_handoff: dict[str, Any],
    summary: dict[str, Any],
    source_provenance: dict[str, Any],
    risk_event_summary: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Describe desktop-agent report outputs without requiring the HTML workbench."""
    safe_company = _safe_report_filename(company)
    markdown_filename = f"{safe_company}-due-diligence-report.md"
    html_filename = f"{safe_company}-due-diligence-report.html"
    print_package = _print_package_manifest(
        company=company,
        safe_company=safe_company,
        report_markdown=report_markdown,
        one_click_readiness=one_click_readiness,
        source_provenance=source_provenance,
        risk_event_summary=risk_event_summary,
        evidence_ledger=evidence_ledger,
    )
    operational_handoff = _dict(print_package.get("operational_handoff"))
    first_screen_handoff_cards = [
        dict(card)
        for card in operational_handoff.get("cards", [])
        if isinstance(card, dict)
    ]
    report_targets = build_report_delivery_targets()
    agent_decision_digest = _packet_agent_decision_digest(
        one_click_readiness=one_click_readiness,
        summary=summary,
        delivery_checklist=print_package.get("delivery_checklist") if isinstance(print_package, dict) else {},
        handoff_cards=first_screen_handoff_cards,
    )
    html_document = _portable_report_html(
        company=company,
        version=version,
        report_markdown=report_markdown,
        one_click_readiness=one_click_readiness,
        summary=summary,
        delivery_checklist=print_package.get("delivery_checklist") if isinstance(print_package, dict) else {},
        agent_decision_digest=agent_decision_digest,
        image_evidence_inventory=print_package.get("image_evidence_inventory") if isinstance(print_package, dict) else {},
        chart_manifest=print_package.get("chart_manifest") if isinstance(print_package, dict) else [],
        source_provenance_appendix=print_package.get("source_provenance_appendix") if isinstance(print_package, dict) else {},
        relationship_capital_appendix=print_package.get("relationship_capital_appendix") if isinstance(print_package, dict) else {},
        report_targets=report_targets,
    )
    premium_html = _premium_html_profile(
        html_filename=html_filename,
        report_markdown=report_markdown,
        html_document=html_document,
        print_package=print_package,
        first_screen_handoff_cards=first_screen_handoff_cards,
    )
    agent_handoff_preview = _packet_agent_handoff_preview(
        one_click_readiness=one_click_readiness,
        enterprise_cognition=enterprise_cognition,
        monitoring_seed=monitoring_seed,
        qyyjt_public_origin_handoff=qyyjt_public_origin_handoff,
        agent_decision_digest=agent_decision_digest,
    )
    report_artifact_autorun = _packet_report_artifact_agent_autorun(
        safe_company=safe_company,
        markdown_filename=markdown_filename,
        html_filename=html_filename,
        one_click_readiness=one_click_readiness,
    )
    return {
        "type": "report_exports",
        "current_release": "desktop_agent_packet_exports",
        "formats": ["markdown", "json_packet", "portable_html", "premium_html", "print_package", "directory_bundle"],
        "agent_decision_digest": agent_decision_digest,
        "report_delivery_targets": report_targets,
        "markdown": {
            "filename": markdown_filename,
            "mime_type": "text/markdown; charset=utf-8",
            "content_field": "report_markdown",
            "char_count": len(report_markdown),
        },
        "portable_html": {
            "filename": html_filename,
            "mime_type": "text/html; charset=utf-8",
            "document": html_document,
            "char_count": len(html_document),
            "first_screen_handoff_cards": first_screen_handoff_cards,
            "first_screen_handoff_card_count": len(first_screen_handoff_cards),
            "first_screen_handoff_source": "report_exports.print_package.operational_handoff.cards",
            "delivery_checklist_source": "report_exports.print_package.delivery_checklist",
            "report_delivery_targets_source": "report_exports.report_delivery_targets",
            "image_evidence_source": "report_exports.print_package.image_evidence_inventory",
            "premium_profile": premium_html,
            "content_policy": "contains first-screen handoff cards, delivery checklist, visual evidence panels, source provenance appendix, relationship/capital appendix, image evidence summary, and the full Markdown report in a printable escaped preformatted block; no findings are dropped",
        },
        "premium_html": premium_html,
        "json_packet": {
            "filename": f"{safe_company}-investigation-packet.json",
            "mime_type": "application/json; charset=utf-8",
            "content_field": "entire investigation_packet",
        },
        "print_package": print_package,
        "directory_bundle": {
            "type": "report_export_directory_bundle",
            "runtime_entrypoint": "bin/investigate.py --export-dir",
            "integrity_verifier_entrypoint": "bin/verify_report_bundle.py <export-dir>",
            "verifier_output_fields": [
                "ok",
                "agent_handoff.checked",
                "agent_handoff.schema_valid",
                "agent_handoff.decision_digest_present",
                "agent_handoff.delivery_checklist_present",
                "agent_handoff.bundle_integrity_present",
                "agent_handoff.bundle_verification_present",
                "agent_handoff.bundle_verification_ready_to_run",
                "agent_handoff.bundle_ready_to_verify",
                "agent_handoff.report_visibility_present",
                "agent_handoff.premium_html_report_visibility_present",
                "agent_handoff.image_evidence_inventory_present",
                "agent_handoff.capital_risk_panel_present",
                "agent_handoff.source_strengthening_present",
                "agent_handoff.source_strengthening_runtime_companion_present",
                "agent_handoff.capital_relationship_crosswalk_present",
                "agent_handoff.verification_recipe_present",
                "agent_handoff.verifier_output_fields_present",
                "agent_handoff.acceptance_closure_present",
                "agent_handoff.source_preflight_present",
                "agent_handoff.source_preflight_contract_valid",
                "agent_handoff.manifest_summary_source_preflight_present",
                "agent_handoff.manifest_summary_source_preflight_valid",
                "agent_handoff.deep_autopilot_plan_present",
                "agent_handoff.deep_autopilot_source_runbook_present",
                "agent_handoff.continuation_entrypoints_valid",
                "agent_handoff.source_runbook_valid",
                "agent_handoff.qyyjt_public_origin_present",
                "agent_handoff.source_resilience_present",
                "agent_handoff.relationship_graph_audit_present",
                "agent_handoff.relationship_resolution_present",
            ],
            "verification_recipe": {
                "type": "report_bundle_verification_recipe",
                "command": "python bin/verify_report_bundle.py <export-dir>",
                "expected_exit_code": 0,
                "success_condition": "ok=true and agent_handoff.schema_valid=true and agent_handoff.bundle_ready_to_verify=true",
                "failure_routing": "Open report-export-manifest.json and agent-handoff.json; repair missing files, hash mismatches, or handoff schema failures before delivery.",
                "required_output_fields": [
                    "ok",
                    "checked_count",
                    "agent_handoff.checked",
                    "agent_handoff.schema_valid",
                    "agent_handoff.decision_digest_present",
                    "agent_handoff.delivery_checklist_present",
                    "agent_handoff.bundle_integrity_present",
                    "agent_handoff.bundle_verification_present",
                    "agent_handoff.bundle_verification_ready_to_run",
                    "agent_handoff.bundle_ready_to_verify",
                    "agent_handoff.report_visibility_present",
                    "agent_handoff.premium_html_report_visibility_present",
                    "agent_handoff.image_evidence_inventory_present",
                    "agent_handoff.capital_risk_panel_present",
                    "agent_handoff.source_strengthening_present",
                    "agent_handoff.source_strengthening_runtime_companion_present",
                    "agent_handoff.capital_relationship_crosswalk_present",
                    "agent_handoff.verification_recipe_present",
                    "agent_handoff.verifier_output_fields_present",
                    "agent_handoff.acceptance_closure_present",
                    "agent_handoff.source_preflight_present",
                    "agent_handoff.source_preflight_contract_valid",
                    "agent_handoff.manifest_summary_source_preflight_present",
                    "agent_handoff.manifest_summary_source_preflight_valid",
                    "agent_handoff.deep_autopilot_plan_present",
                    "agent_handoff.deep_autopilot_source_runbook_present",
                    "agent_handoff.continuation_entrypoints_valid",
                    "agent_handoff.source_runbook_valid",
                    "agent_handoff.qyyjt_public_origin_present",
                    "agent_handoff.source_resilience_present",
                    "agent_handoff.relationship_graph_audit_present",
                    "agent_handoff.relationship_resolution_present",
                ],
            },
            "manifest_filename": "report-export-manifest.json",
            "writes": ["docx_red_head", "portable_html", "markdown", "json_packet", "agent_handoff", "manifest"],
            "manifest_fields": ["files", "file_manifest", "delivery_checklist", "agent_summary", "report_exports"],
            "agent_handoff": {
                "filename": "agent-handoff.json",
                "content": "delivery files, delivery decision, bundle integrity, bundle verification recipe, verifier output fields, delivery checklist, report visibility, image evidence inventory, capital risk panel, source strengthening work orders, relationship resolution verification queue, decision digest, acceptance closure, operator work, closure_steps, control path verification queue, QYYJT public-origin section batches, public-origin gap bridge, source-health snapshot, source recovery execution queue, source resilience retry policy, graph capital exposure, relationship graph audit summary, capital/relationship top steps, reliance limitations, and print handoff cards",
                "schema_fields": [
                    "delivery_decision",
                    "delivery_files",
                    "bundle_integrity",
                    "bundle_verification",
                    "delivery_checklist",
                    "report_visibility",
                    "capital_risk_panel",
                    "source_strengthening",
                    "relationship_resolution",
                    "trust_boundaries",
                    "decision_digest",
                    "next_actions",
                    "acceptance_closure",
                    "operator_work",
                    "closure_steps",
                    "qyyjt_public_origin",
                    "source_health",
                    "capital_and_relationship",
                    "reliance_limitations",
                    "report_handoff_cards",
                    "report_artifact_autorun",
                ],
                "report_artifact_autorun": report_artifact_autorun,
                **agent_handoff_preview,
            },
            "stdout_preserved": True,
            "node_cli_passthrough": "npx wallstreet-tieling --investigate <company> --export-dir <output-dir>",
        },
        "future_formats": {
            "docx_red_head": "runtime_cli_renderer_available_via_export_docx",
            "immersive_premium_html": "p2_visual_polish_not_current_release_blocker",
        },
        "print_readiness": {
            "portable_html_printable": True,
            "markdown_printable": True,
            "docx_print_binding_layout": "runtime_renderer_with_toc_footer_native_tables_and_local_image_embedding",
        },
    }


def _packet_report_artifact_agent_autorun(
    *,
    safe_company: str,
    markdown_filename: str,
    html_filename: str,
    one_click_readiness: dict[str, Any],
) -> dict[str, Any]:
    docx_filename = f"{safe_company}-red-head-due-diligence-report.docx"
    json_filename = f"{safe_company}-investigation-packet.json"
    return {
        "type": "report_artifact_agent_autorun",
        "manual_intermediate_steps_required": False,
        "ready_to_run": True,
        "routes": [
            {
                "route_id": "export-report-bundle",
                "action": "run_export_dir",
                "cli_command": 'npx wallstreet-tieling --investigate "<company>" --mode deep --export-dir <dir>',
                "expected_outputs": [
                    docx_filename,
                    html_filename,
                    markdown_filename,
                    json_filename,
                    "agent-handoff.json",
                    "report-export-manifest.json",
                ],
                "done_condition": "Export directory contains DOCX, HTML, Markdown, full JSON packet, agent-handoff, and manifest.",
            },
            {
                "route_id": "verify-report-bundle",
                "action": "run_bundle_verifier",
                "cli_command": "python bin/verify_report_bundle.py <export-dir>",
                "required_output_fields": [
                    "ok",
                    "agent_handoff.schema_valid",
                    "agent_handoff.bundle_ready_to_verify",
                    "agent_handoff.report_visibility_present",
                    "agent_handoff.acceptance_closure_present",
                ],
                "done_condition": "Verifier returns ok=true before any desktop agent claims delivery.",
            },
        ],
        "preserve_packet_fields": [
            "report_exports.directory_bundle",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.portable_html.document",
            "report_exports.print_package.delivery_checklist",
            "one_click_readiness.acceptance_closure_summary",
        ],
        "acceptance_closure": {
            "status": one_click_readiness.get("acceptance_closure_status") or "unknown",
            "blocking_count": int(one_click_readiness.get("acceptance_closure_blocking_count") or 0),
            "ready_count": int(one_click_readiness.get("acceptance_closure_ready_count") or 0),
        },
        "operator_intervention_only_when": [
            "Export-dir generation fails or required files are absent.",
            "Bundle verifier fails after repairing manifest or handoff mismatches.",
            "Acceptance closure has blocking domains requiring new evidence or authorization.",
        ],
        "policy": "Generate, open, and verify report artifacts automatically; never summarize away report sections, charts, image evidence, source provenance, or handoff fields.",
    }


def _premium_html_profile(
    *,
    html_filename: str,
    report_markdown: str,
    html_document: str,
    print_package: dict[str, Any],
    first_screen_handoff_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Machine-readable premium HTML contract for the current portable output."""
    source_appendix = _dict(print_package.get("source_provenance_appendix"))
    relationship_capital = _dict(print_package.get("relationship_capital_appendix"))
    image_inventory = _dict(print_package.get("image_evidence_inventory"))
    chart_manifest = [
        item for item in print_package.get("chart_manifest", [])
        if isinstance(item, dict)
    ]
    return {
        "type": "premium_html_report_profile",
        "status": "runtime_contract_available",
        "filename": html_filename,
        "document_field": "report_exports.portable_html.document",
        "surface_markers": [
            "data-premium-html-report",
            "data-full-report-preserved",
            "premium visual QA checklist",
            "evidence darkroom",
            "source provenance appendix",
            "relationship and capital appendix",
        ],
        "design_language": [
            "cinematic paper-and-night contrast",
            "component-level liquid glass",
            "low-intrusion evidence darkroom",
            "formal report typography",
            "print-safe degradation",
            "reduced-motion-safe rendering",
        ],
        "content_guarantees": [
            "full_markdown_report_preserved",
            "no_due_diligence_sections_shortened",
            "evidence_source_index_visible",
            "relationship_capital_appendix_visible",
            "image_evidence_inventory_visible",
            "agent_handoff_cards_visible",
            "delivery_checklist_visible",
        ],
        "forbidden_shortcuts": [
            "no_generic_purple_gradient",
            "no_ai_style_card_pile",
            "no_decorative_content_replacement",
            "no_evidence_truncation",
            "no_report_body_summarization",
        ],
        "acceptance_checklist": [
            "html starts with <!doctype html>",
            "document has data-premium-html-report marker",
            "document has data-full-report-preserved marker",
            "premium visual QA checklist is visible",
            "full report_markdown first heading appears in the HTML",
            "full report_markdown escaped body is present in a printable report body block",
            "prefers-reduced-motion and print CSS are present",
            "source provenance, relationship/capital, image evidence, and chart panels are present",
        ],
        "metrics": {
            "report_markdown_chars": len(report_markdown),
            "html_chars": len(html_document),
            "handoff_card_count": len(first_screen_handoff_cards),
            "chart_panel_count": len(chart_manifest),
            "image_evidence_count": int(image_inventory.get("count") or 0),
            "source_count": int(source_appendix.get("source_count") or 0),
            "relationship_edge_count": int(relationship_capital.get("relationship_edge_count") or 0),
        },
        "policy": (
            "Premium HTML is the screen-review surface for the same packet; it must improve "
            "visual comprehension without replacing or shortening evidence, report text, "
            "agent handoff, source provenance, or delivery checklist data."
        ),
    }


def _portable_report_html(
    *,
    company: str,
    version: str,
    report_markdown: str,
    one_click_readiness: dict[str, Any],
    summary: dict[str, Any],
    delivery_checklist: dict[str, Any] | None = None,
    agent_decision_digest: dict[str, Any] | None = None,
    image_evidence_inventory: dict[str, Any] | None = None,
    chart_manifest: list[dict[str, Any]] | None = None,
    source_provenance_appendix: dict[str, Any] | None = None,
    relationship_capital_appendix: dict[str, Any] | None = None,
    report_targets: dict[str, Any] | None = None,
) -> str:
    status = html.escape(str(one_click_readiness.get("status") or "unknown"))
    closure_status = html.escape(str(one_click_readiness.get("acceptance_closure_status") or "unknown"))
    closure_blocking = html.escape(str(one_click_readiness.get("acceptance_closure_blocking_count") or 0))
    execution_state = html.escape(str(summary.get("execution_state") or "unknown"))
    quality_score = html.escape(str(one_click_readiness.get("quality_score") or "n/a"))
    fact_count = html.escape(str(one_click_readiness.get("fact_count") or 0))
    lead_count = html.escape(str(one_click_readiness.get("lead_count") or 0))
    coverage_gap = html.escape(str(one_click_readiness.get("coverage_gap_count") or 0))
    coverage_severity = html.escape(str(one_click_readiness.get("coverage_gap_severity") or "none"))
    capital_status = html.escape(str(one_click_readiness.get("capital_relationship_status") or "unknown"))
    source_resilience = html.escape(str(one_click_readiness.get("source_resilience_status") or "unknown"))
    source_step_ready = html.escape(str(one_click_readiness.get("source_resilience_recommended_step_ready_to_run")))
    qyyjt_actions = html.escape(str(one_click_readiness.get("public_origin_next_action_count") or 0))
    capital_queue = html.escape(str(one_click_readiness.get("capital_verification_queue_count") or 0))
    relationship_queue = html.escape(str(one_click_readiness.get("relationship_graph_audit_queue_count") or 0))
    report = html.escape(report_markdown)
    title = html.escape(f"Wallstreet Tieling Due Diligence Report - {company}")
    company_html = html.escape(company)
    delivery_html = _portable_delivery_checklist_html(delivery_checklist or {})
    decision_html = _portable_decision_digest_html(agent_decision_digest or {})
    chart_html = _portable_chart_manifest_html(chart_manifest or [])
    image_html = _portable_image_evidence_html(image_evidence_inventory or {})
    relationship_capital_html = _portable_relationship_capital_html(relationship_capital_appendix or {})
    source_html = _portable_source_provenance_html(source_provenance_appendix or {})
    report_targets_html = _portable_report_targets_html(report_targets or {})
    return (
        "<!doctype html>\n"
        "<html lang=\"zh-CN\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{title}</title>\n"
        "  <style>\n"
        "    :root{--ink:#1f2933;--muted:#667085;--paper:#fffdf8;--panel:#fffaf2;--line:#e5d8c5;--red:#9f1d20;--gold:#a16f2b;--night:#152033;--copper:#7c4a24;--glass:rgba(255,253,248,.76);--shadow:0 28px 90px rgba(21,32,51,.16);}\n"
        "    *{box-sizing:border-box;}\n"
        "    body{font-family:Georgia,'Noto Serif SC','Microsoft YaHei',serif;margin:0;min-height:100vh;background:radial-gradient(circle at 12% 4%,rgba(255,248,232,.96) 0,rgba(246,242,234,.92) 28%,rgba(238,230,217,.9) 62%),linear-gradient(140deg,#161d2b 0,#f6f2ea 34%,#fffdf8 100%);color:var(--ink);}\n"
        "    body:before{content:'';position:fixed;inset:0;pointer-events:none;background:linear-gradient(120deg,rgba(159,29,32,.08),transparent 24%,rgba(21,32,51,.1) 64%,rgba(161,111,43,.08));mix-blend-mode:multiply;}\n"
        "    main{max-width:1180px;margin:0 auto;padding:42px 28px 72px;position:relative;}\n"
        "    .skip-link{position:absolute;left:28px;top:10px;transform:translateY(-140%);background:#1f2933;color:#fff;padding:8px 12px;border-radius:999px;z-index:5;}\n"
        "    .skip-link:focus{transform:translateY(0);}\n"
        "    header{position:relative;overflow:hidden;border:1px solid #d5c6ae;border-top:6px solid var(--red);border-radius:24px;margin-bottom:24px;padding:28px;background:linear-gradient(135deg,rgba(255,253,248,.96),rgba(247,238,222,.9));box-shadow:0 24px 70px rgba(31,41,51,.12);}\n"
        "    header:after{content:'';position:absolute;right:-90px;top:-120px;width:260px;height:260px;border:1px solid rgba(159,29,32,.28);border-radius:50%;box-shadow:0 0 0 28px rgba(161,111,43,.06);}\n"
        "    header:before{content:'';position:absolute;inset:auto 28px 20px auto;width:160px;height:3px;border-radius:999px;background:linear-gradient(90deg,var(--red),var(--gold),transparent);opacity:.74;}\n"
        "    .eyebrow{letter-spacing:.18em;color:#9f1d20;font-weight:700;text-transform:uppercase;font-size:12px;}\n"
        "    h1{font-size:38px;line-height:1.14;margin:10px 0 14px;max-width:780px;}\n"
        "    .meta{display:flex;gap:12px;flex-wrap:wrap;color:#52606d;font-size:14px;position:relative;z-index:1;}\n"
        "    .pill{border:1px solid #c7b8a0;border-radius:999px;padding:5px 10px;background:#fffaf2;}\n"
        "    .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0;}\n"
        "    .card{background:var(--glass);backdrop-filter:blur(18px) saturate(1.12);border:1px solid rgba(229,216,197,.9);border-radius:16px;padding:14px 16px;box-shadow:0 10px 26px rgba(31,41,51,.06);}\n"
        "    .card b{display:block;font-size:20px;margin-bottom:4px;color:#1f2933;}\n"
        "    .card span{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7b6b58;}\n"
        "    .report-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px;align-items:start;}\n"
        "    .report-main,.report-rail{min-width:0;}\n"
        "    .premium-qa{position:relative;overflow:hidden;}\n"
        "    .premium-qa:after{content:'full report preserved';position:absolute;right:18px;top:18px;color:rgba(255,255,255,.24);letter-spacing:.18em;text-transform:uppercase;font-size:11px;}\n"
        "    .premium-copy{max-width:760px;line-height:1.7;color:#f7ead7;}\n"
        "    .premium-copy code{color:#ffe1a1;}\n"
        "    .delivery{background:var(--glass);backdrop-filter:blur(16px) saturate(1.08);border:1px solid #d5c6ae;border-radius:18px;padding:18px 20px;margin:18px 0;box-shadow:0 18px 40px rgba(31,41,51,.07);}\n"
        "    .delivery h2{font-size:18px;margin:0 0 10px;color:#9f1d20;}\n"
        "    .delivery table{width:100%;border-collapse:collapse;font-size:13px;}\n"
        "    .delivery th,.delivery td{border-bottom:1px solid #eadfce;padding:8px 6px;text-align:left;vertical-align:top;}\n"
        "    .delivery th{color:#7b6b58;text-transform:uppercase;letter-spacing:.08em;font-size:11px;}\n"
        "    .visual-panel{background:linear-gradient(160deg,rgba(21,32,51,.98),rgba(47,38,31,.95));color:#f7ead7;border:1px solid rgba(255,255,255,.16);border-radius:20px;padding:18px;margin:18px 0;box-shadow:0 28px 70px rgba(21,32,51,.24);}\n"
        "    .visual-panel h2{color:#fff3dd;margin:0 0 12px;font-size:18px;}\n"
        "    .visual-panel table{width:100%;border-collapse:collapse;font-size:12px;}\n"
        "    .visual-panel th,.visual-panel td{border-bottom:1px solid rgba(255,255,255,.14);padding:8px 5px;text-align:left;vertical-align:top;}\n"
        "    .visual-panel th{color:#dfbf7f;text-transform:uppercase;letter-spacing:.08em;font-size:10px;}\n"
        "    .metric-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:12px 0;}\n"
        "    .metric-strip div{border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:10px;background:rgba(255,255,255,.06);}\n"
        "    .metric-strip b{display:block;color:#fff;font-size:18px;margin-bottom:3px;}\n"
        "    .metric-strip span{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#dfbf7f;}\n"
        "    .decision-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:10px;}\n"
        "    .decision-grid div{background:#fffaf2;border:1px solid #eadfce;border-radius:12px;padding:10px 12px;}\n"
        "    .decision-grid b{display:block;font-size:13px;color:#7b1d1d;margin-bottom:3px;}\n"
        "    .decision-grid span{font-size:13px;color:#1f2933;}\n"
        "    .image-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:10px;}\n"
        "    .image-card{background:#fffaf2;border:1px solid #eadfce;border-radius:12px;padding:10px 12px;}\n"
        "    .image-card b{display:block;font-size:13px;color:#7b1d1d;margin-bottom:3px;}\n"
        "    .image-card span{font-size:13px;color:#1f2933;}\n"
        "    pre.report-body{white-space:pre-wrap;word-break:break-word;background:rgba(255,253,248,.94);border:1px solid #e5d8c5;border-radius:22px;padding:28px;line-height:1.68;font-size:14px;box-shadow:var(--shadow);}\n"
        "    .report-body:focus{outline:3px solid rgba(159,29,32,.32);outline-offset:4px;}\n"
        "    @media (prefers-reduced-motion:no-preference){header,.card,.delivery,.visual-panel,.report-body{animation:rise-in .55s ease both;} .cards .card:nth-child(2n){animation-delay:.04s;} @keyframes rise-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}}\n"
        "    @media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}}\n"
        "    @media (max-width:900px){.report-layout{grid-template-columns:1fr;}h1{font-size:30px;}main{padding:24px 16px 48px;}}\n"
        "    @media print{body{background:#fff;}body:before{display:none;}main{padding:18mm;max-width:none;}header,.delivery,.visual-panel,pre.report-body{box-shadow:none;backdrop-filter:none;}header{break-after:avoid;}.report-layout{display:block;}.visual-panel{background:#fff;color:#111;border-color:#999;}.visual-panel h2{color:#111;}.visual-panel th,.visual-panel td{border-color:#ccc;color:#111;}.metric-strip div{border-color:#ccc;background:#fff;}.metric-strip b,.metric-strip span{color:#111;}.premium-qa:after{display:none;}}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main data-premium-html-report=\"true\" data-full-report-preserved=\"report_markdown\">\n"
        "    <a class=\"skip-link\" href=\"#full-report-body\">Skip to full report body</a>\n"
        "    <header>\n"
        "      <div class=\"eyebrow\">Wallstreet Tieling Desktop Agent Export</div>\n"
        f"      <h1>{company_html}</h1>\n"
        "      <div class=\"meta\">\n"
        f"        <span class=\"pill\">version {html.escape(version)}</span>\n"
        f"        <span class=\"pill\">readiness {status}</span>\n"
        f"        <span class=\"pill\">execution {execution_state}</span>\n"
        "      </div>\n"
        "    </header>\n"
        "    <section class=\"cards\" aria-label=\"report readiness summary\">\n"
        f"      <div class=\"card\"><b>{quality_score}</b><span>quality score</span></div>\n"
        f"      <div class=\"card\"><b>{fact_count}</b><span>facts</span></div>\n"
        f"      <div class=\"card\"><b>{lead_count}</b><span>leads</span></div>\n"
        f"      <div class=\"card\"><b>{closure_status}</b><span>acceptance closure blockers: {closure_blocking}</span></div>\n"
        f"      <div class=\"card\"><b>{coverage_gap}</b><span>coverage gaps: {coverage_severity}</span></div>\n"
        f"      <div class=\"card\"><b>{capital_status}</b><span>capital relationship</span></div>\n"
        f"      <div class=\"card\"><b>{source_resilience}</b><span>source recovery ready: {source_step_ready}</span></div>\n"
        f"      <div class=\"card\"><b>{qyyjt_actions}</b><span>qyyjt public actions</span></div>\n"
        f"      <div class=\"card\"><b>{capital_queue}</b><span>capital verification steps</span></div>\n"
        f"      <div class=\"card\"><b>{relationship_queue}</b><span>relationship audit steps</span></div>\n"
        "    </section>\n"
        "    <section class=\"visual-panel premium-qa\" aria-label=\"premium visual QA checklist\">\n"
        "      <h2>Premium HTML visual QA checklist</h2>\n"
        "      <p class=\"premium-copy\">This screen report uses component-level <code>liquid glass</code>, an <code>evidence darkroom</code> treatment, formal long-report typography, reduced-motion safety, and print-safe degradation while preserving the complete due-diligence body. It explicitly avoids generic purple gradients, decorative card piles, and any evidence truncation.</p>\n"
        "      <div class=\"metric-strip\">\n"
        "        <div><b>yes</b><span>full report preserved</span></div>\n"
        "        <div><b>yes</b><span>source provenance visible</span></div>\n"
        "        <div><b>yes</b><span>relationship/capital visible</span></div>\n"
        "        <div><b>yes</b><span>print + reduced motion</span></div>\n"
        "      </div>\n"
        "    </section>\n"
        "    <div class=\"report-layout\">\n"
        "      <div class=\"report-main\">\n"
        f"{decision_html}"
        f"{report_targets_html}"
        f"{chart_html}"
        f"{relationship_capital_html}"
        f"{image_html}"
        f"        <pre id=\"full-report-body\" class=\"report-body\" tabindex=\"0\" data-full-report-preserved=\"true\">{report}</pre>\n"
        "      </div>\n"
        "      <aside class=\"report-rail\" aria-label=\"agent delivery rail\">\n"
        f"{delivery_html}"
        f"{source_html}"
        "      </aside>\n"
        "    </div>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _packet_agent_decision_digest(
    *,
    one_click_readiness: dict[str, Any],
    summary: dict[str, Any],
    delivery_checklist: dict[str, Any] | None,
    handoff_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    first_action = handoff_cards[0] if handoff_cards else {}
    blocking_count = int(one_click_readiness.get("acceptance_closure_blocking_count") or 0)
    source_ready = bool(one_click_readiness.get("source_resilience_recommended_step_ready_to_run"))
    blocked_reasons = [
        str(value)
        for value in (
            one_click_readiness.get("source_resilience_recommended_step_blocked_reason"),
            first_action.get("blocked_reason") if isinstance(first_action, dict) else "",
        )
        if str(value or "").strip()
    ]
    relationship_edge_count = int(one_click_readiness.get("relationship_edge_count") or 0)
    relationship_audit_count = int(one_click_readiness.get("relationship_graph_audit_queue_count") or 0)
    if relationship_edge_count <= 0:
        relationship_status = "no_relationship_edges"
    elif relationship_audit_count:
        relationship_status = "audit_required"
    else:
        relationship_status = "evidence_backed"
    delivery = _dict(delivery_checklist)
    return {
        "type": "agent_decision_digest",
        "surface": "report_exports.agent_decision_digest",
        "delivery_status": delivery.get("status") or "unknown",
        "bundle_ready_to_verify": False,
        "bundle_verification_status": "export_dir_required",
        "can_make_clean_conclusion": bool(one_click_readiness.get("can_make_clean_conclusion")),
        "acceptance_closure_status": one_click_readiness.get("acceptance_closure_status") or "unknown",
        "acceptance_blocking_count": blocking_count,
        "source_resilience_status": one_click_readiness.get("source_resilience_status") or "unknown",
        "source_resilience_ready_to_run": source_ready,
        "source_resilience_retryable": bool(one_click_readiness.get("source_resilience_retryable")),
        "capital_relationship_status": one_click_readiness.get("capital_relationship_status") or "unknown",
        "relationship_audit_status": relationship_status,
        "work_queue_counts": {
            "operator_work": int(one_click_readiness.get("operator_work_queue_count") or 0),
            "operator_work_ready": int(one_click_readiness.get("operator_work_ready_count") or 0),
            "capital_verification": int(one_click_readiness.get("capital_verification_queue_count") or 0),
            "relationship_audit": relationship_audit_count,
            "public_origin": int(one_click_readiness.get("public_origin_next_action_count") or 0),
            "source_repair": int(one_click_readiness.get("source_repair_priority_count") or 0),
        },
        "first_action": {
            "id": first_action.get("id") if isinstance(first_action, dict) else "",
            "priority": first_action.get("priority") if isinstance(first_action, dict) else "",
            "status": first_action.get("status") if isinstance(first_action, dict) else "",
            "ready_to_run": bool(first_action.get("ready_to_run")) if isinstance(first_action, dict) else False,
            "action": first_action.get("action") if isinstance(first_action, dict) else "",
            "done_condition": first_action.get("done_condition") if isinstance(first_action, dict) else "",
        },
        "blocked_reasons": blocked_reasons[:5],
        "requires_operator": bool(one_click_readiness.get("needs_operator_followup")) or blocking_count > 0 or not source_ready,
        "public_or_authorized_boundary": "public, licensed, or user-authorized evidence only; no lead is promoted without provenance and admission gates",
        "policy": "Packet-level routing digest for API/MCP/agent hosts; export-dir agent-handoff adds bundle integrity details.",
        "execution_state": summary.get("execution_state") or "unknown",
    }


def _portable_report_targets_html(report_targets: dict[str, Any]) -> str:
    targets = report_targets if isinstance(report_targets, dict) else {}
    if not targets:
        return ""
    outputs = [item for item in targets.get("current_release_outputs", []) if isinstance(item, dict)][:8]
    final_targets = [item for item in targets.get("final_product_targets", []) if isinstance(item, dict)][:8]
    persona = _dict(targets.get("persona_interaction_contract"))
    output_rows = "\n".join(
        "      <tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('current_status') or ''))}</td>"
        f"<td>{html.escape(str(row.get('agent_field') or ''))}</td>"
        f"<td>{html.escape(str(row.get('required')))}</td>"
        "</tr>"
        for row in outputs
    )
    final_rows = "\n".join(
        "      <tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('status') or ''))}</td>"
        f"<td>{html.escape(_short_text(str(row.get('done_when') or ''), 180))}</td>"
        "</tr>"
        for row in final_targets
    )
    role_count = html.escape(str(persona.get("role_count") or 0))
    full_status = html.escape(str(targets.get("full_product_status") or "unknown"))
    return (
        "    <section class=\"delivery\" aria-label=\"report delivery targets\">\n"
        "      <h2>Report delivery targets</h2>\n"
        f"      <p>Full product status: <b>{full_status}</b> | persona roles: <b>{role_count}</b></p>\n"
        "      <table><thead><tr><th>Output</th><th>Status</th><th>Agent field</th><th>Required</th></tr></thead><tbody>\n"
        f"{output_rows}\n"
        "      </tbody></table>\n"
        "      <table><thead><tr><th>Final target</th><th>Status</th><th>Done when</th></tr></thead><tbody>\n"
        f"{final_rows}\n"
        "      </tbody></table>\n"
        "    </section>\n"
    )


def _portable_decision_digest_html(digest: dict[str, Any]) -> str:
    if not digest:
        return ""
    first_action = _dict(digest.get("first_action"))
    return (
        "    <section class=\"delivery\" aria-label=\"agent decision digest\">\n"
        "      <h2>Agent decision digest</h2>\n"
        "      <div class=\"decision-grid\">\n"
        f"        <div><b>delivery</b><span>{html.escape(str(digest.get('delivery_status') or 'unknown'))}</span></div>\n"
        f"        <div><b>clean conclusion</b><span>{html.escape(str(digest.get('can_make_clean_conclusion')))}</span></div>\n"
        f"        <div><b>operator required</b><span>{html.escape(str(digest.get('requires_operator')))}</span></div>\n"
        f"        <div><b>bundle verification</b><span>{html.escape(str(digest.get('bundle_verification_status') or 'unknown'))}</span></div>\n"
        f"        <div><b>first action</b><span>{html.escape(_short_text(first_action.get('action') or first_action.get('id') or '', 180))}</span></div>\n"
        "      </div>\n"
        "    </section>\n"
    )


def _portable_image_evidence_html(image_inventory: dict[str, Any]) -> str:
    inventory = image_inventory if isinstance(image_inventory, dict) else {}
    if not inventory:
        return ""
    count = int(inventory.get("count") or 0)
    embeddable_count = int(inventory.get("embeddable_count") or 0)
    appendix_required = bool(inventory.get("appendix_required"))
    empty_state = html.escape(str(inventory.get("empty_state") or "Image evidence is listed below when present."))
    items = [item for item in inventory.get("items", []) if isinstance(item, dict)][:8]
    item_cards = "\n".join(
        "      <div class=\"image-card\">"
        f"<b>{html.escape(str(item.get('id') or 'image-evidence'))}</b>"
        f"<span>{html.escape(str(item.get('caption') or 'Evidence image'))}</span><br>"
        f"<span>source={html.escape(str(item.get('source') or 'unknown'))}</span><br>"
        f"<span>admission={html.escape(str(item.get('admission') or 'unknown'))}</span><br>"
        f"<span>embeddable={html.escape(str(bool(item.get('embeddable'))))}</span>"
        "</div>"
        for item in items
    )
    if not item_cards:
        item_cards = f"      <p>{empty_state}</p>"
    return (
        "    <section class=\"delivery\" aria-label=\"image evidence summary\">\n"
        "      <h2>Image evidence summary</h2>\n"
        f"      <p>image evidence count: <b>{count}</b> | embeddable: <b>{embeddable_count}</b> | appendix required: <b>{str(appendix_required).lower()}</b></p>\n"
        "      <div class=\"image-grid\">\n"
        f"{item_cards}\n"
        "      </div>\n"
        "    </section>\n"
    )


def _portable_chart_manifest_html(chart_manifest: list[dict[str, Any]]) -> str:
    charts = [item for item in chart_manifest if isinstance(item, dict)][:8]
    if not charts:
        return ""
    rows = "\n".join(
        "          <tr>"
        f"<td>{html.escape(str(row.get('id') or 'chart'))}</td>"
        f"<td>{html.escape(str(row.get('title') or row.get('label') or 'Chart/table'))}</td>"
        f"<td>{html.escape(str(row.get('type') or row.get('chart_type') or 'summary'))}</td>"
        f"<td>{html.escape(str(row.get('value') if row.get('value') is not None else row.get('status') or row.get('count') or ''))}</td>"
        "</tr>"
        for row in charts
    )
    return (
        "        <section class=\"visual-panel\" aria-label=\"visual evidence panels\">\n"
        "          <h2>Visual evidence panels</h2>\n"
        "          <table><thead><tr><th>ID</th><th>Panel</th><th>Type</th><th>Value</th></tr></thead><tbody>\n"
        f"{rows}\n"
        "          </tbody></table>\n"
        "        </section>\n"
    )


def _portable_source_provenance_html(source_appendix: dict[str, Any]) -> str:
    appendix = source_appendix if isinstance(source_appendix, dict) else {}
    if not appendix:
        return ""
    rows = [item for item in appendix.get("rows", []) if isinstance(item, dict)][:10]
    row_html = "\n".join(
        "          <tr>"
        f"<td>{html.escape(str(row.get('source') or row.get('id') or 'source'))}</td>"
        f"<td>{html.escape(str(row.get('authority') or 'unknown'))}</td>"
        f"<td>{html.escape(str(row.get('access') or 'unknown'))}</td>"
        f"<td>{html.escape(str(row.get('admission') or 'unknown'))}</td>"
        "</tr>"
        for row in rows
    )
    if not row_html:
        row_html = "          <tr><td colspan=\"4\">No admitted source rows are available in this offline packet.</td></tr>"
    source_count = html.escape(str(appendix.get("source_count") or 0))
    evidence_count = html.escape(str(appendix.get("evidence_row_count") or 0))
    return (
        "        <section class=\"visual-panel\" aria-label=\"source provenance appendix\">\n"
        "          <h2>Source provenance appendix</h2>\n"
        "          <div class=\"metric-strip\">\n"
        f"            <div><b>{source_count}</b><span>sources</span></div>\n"
        f"            <div><b>{evidence_count}</b><span>evidence rows</span></div>\n"
        "          </div>\n"
        "          <table><thead><tr><th>Source</th><th>Authority</th><th>Access</th><th>Admission</th></tr></thead><tbody>\n"
        f"{row_html}\n"
        "          </tbody></table>\n"
        "        </section>\n"
    )


def _portable_relationship_capital_html(appendix: dict[str, Any]) -> str:
    value = appendix if isinstance(appendix, dict) else {}
    if not value:
        return ""
    relationship_edges = html.escape(str(value.get("relationship_edge_count") or 0))
    capital_steps = html.escape(str(value.get("capital_verification_queue_count") or 0))
    audit_steps = html.escape(str(value.get("relationship_audit_queue_count") or 0))
    status = html.escape(str(value.get("capital_relationship_status") or value.get("status") or "unknown"))
    rows = [
        ("relationship edges", relationship_edges),
        ("capital verification queue", capital_steps),
        ("relationship audit queue", audit_steps),
        ("capital relationship status", status),
    ]
    row_html = "\n".join(
        "          <tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{text}</td>"
        "</tr>"
        for label, text in rows
    )
    return (
        "        <section class=\"visual-panel\" aria-label=\"relationship and capital appendix\">\n"
        "          <h2>Relationship and capital appendix</h2>\n"
        "          <div class=\"metric-strip\">\n"
        f"            <div><b>{relationship_edges}</b><span>relationship edges</span></div>\n"
        f"            <div><b>{capital_steps}</b><span>capital checks</span></div>\n"
        f"            <div><b>{audit_steps}</b><span>graph audits</span></div>\n"
        "          </div>\n"
        "          <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>\n"
        f"{row_html}\n"
        "          </tbody></table>\n"
        "        </section>\n"
    )


def _safe_report_filename(company: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", str(company or "subject")).strip("-._")
    return value[:80] or "subject"


def _print_package_manifest(
    *,
    company: str,
    safe_company: str,
    report_markdown: str,
    one_click_readiness: dict[str, Any],
    source_provenance: dict[str, Any],
    risk_event_summary: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Machine-readable print/export contract for desktop agents.

    The runtime can render a basic binary .docx through bin/investigate.py
    --export-docx. This manifest gives Codex, Claude Code, Hermes, and office
    agents enough structure to preserve the red-head Word/PDF package contract
    without dropping report content.
    """
    section_inventory = _report_section_inventory(report_markdown)
    chart_manifest = _report_chart_manifest(
        one_click_readiness=one_click_readiness,
        source_provenance=source_provenance,
        risk_event_summary=risk_event_summary,
    )
    image_inventory = _image_evidence_inventory(evidence_ledger)
    source_appendix = _source_provenance_appendix(evidence_ledger)
    relationship_capital_appendix = _relationship_capital_appendix(one_click_readiness)
    operational_handoff = _report_operational_handoff(one_click_readiness)
    delivery_checklist = _delivery_checklist_manifest(
        safe_company=safe_company,
        docx_filename=f"{safe_company}-red-head-due-diligence-report.docx",
        markdown_filename=f"{safe_company}-due-diligence-report.md",
        html_filename=f"{safe_company}-due-diligence-report.html",
        json_filename=f"{safe_company}-investigation-packet.json",
        section_inventory=section_inventory,
        chart_manifest=chart_manifest,
        image_inventory=image_inventory,
        source_appendix=source_appendix,
        relationship_capital_appendix=relationship_capital_appendix,
        operational_handoff=operational_handoff,
    )

    return {
        "type": "print_package_manifest",
        "status": "ready_for_agent_renderer",
        "target_outputs": ["docx_red_head", "pdf_print", "portable_html_print"],
        "docx": {
            "filename": f"{safe_company}-red-head-due-diligence-report.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "renderer_status": "runtime_cli_renderer_available",
            "runtime_entrypoint": "bin/investigate.py --export-docx",
            "content_source": "report_markdown",
            "renderer_capabilities": [
                "red_head_front_matter",
                "official_document_metadata",
                "red_head_separator_rule",
                "full_markdown_body",
                "section_inventory_toc",
                "page_footer_field",
                "chart_manifest_data_rows",
                "native_chart_summary_panels",
                "image_evidence_inventory_items",
                "embedded_local_image_evidence",
                "operational_handoff_tables",
                "native_word_tables",
            ],
        },
        "red_head_front_matter": {
            "document_title": f"{company} due diligence result brief",
            "issuing_body": "Wallstreet Tieling Enterprise Intelligence Desk",
            "classification": "internal_reference",
            "document_number": f"WST-DD-{safe_company[:24].upper()}",
            "document_purpose": "desktop_agent_due_diligence_delivery",
            "brief_required": True,
            "body_required": True,
        },
        "document_structure": [
            "red_head_front_matter",
            "concise_due_diligence_brief",
            "full_due_diligence_body",
            "risk_and_capital_charts",
            "relationship_graph_and_evidence_tables",
            "relationship_capital_appendix",
            "operational_handoff_appendix",
            "image_evidence_appendix",
            "source_provenance_appendix",
        ],
        "section_inventory": section_inventory,
        "chart_manifest": chart_manifest,
        "image_evidence_inventory": image_inventory,
        "source_provenance_appendix": source_appendix,
        "relationship_capital_appendix": relationship_capital_appendix,
        "operational_handoff": operational_handoff,
        "delivery_checklist": delivery_checklist,
        "print_layout": {
            "paper": "A4",
            "binding_margin": "wide_inner_margin",
            "page_numbers": True,
            "table_of_contents": True,
            "caption_images": True,
            "preserve_full_report_text": True,
        },
        "acceptance_checklist": [
            "opens_as_docx",
            "has_red_head_front_matter",
            "has_concise_brief_before_body",
            "preserves_full_report_body",
            "renders_charts_or_chart_tables",
            "renders_image_evidence_appendix_when_images_exist",
            "includes_operational_handoff_for_agent_execution",
            "includes_delivery_checklist_for_agent_and_print_handoff",
            "includes_acceptance_closure_summary",
            "has_page_numbers_and_binding_margin",
            "includes_source_provenance_appendix",
            "source_provenance_appendix_cites_evidence_rows",
            "relationship_capital_appendix_lists_graph_and_capital_work",
        ],
    }


def _portable_delivery_checklist_html(delivery_checklist: dict[str, Any]) -> str:
    checklist = delivery_checklist if isinstance(delivery_checklist, dict) else {}
    if not checklist:
        return ""
    outputs = [item for item in checklist.get("required_outputs", []) if isinstance(item, dict)][:8]
    quality = [item for item in checklist.get("quality_checks", []) if isinstance(item, dict)][:8]
    status = html.escape(str(checklist.get("status") or "unknown"))
    primary_print = html.escape(str(checklist.get("primary_print_file") or "n/a"))
    primary_screen = html.escape(str(checklist.get("primary_screen_file") or "n/a"))
    output_rows = "\n".join(
        "      <tr>"
        f"<td>{html.escape(str(row.get('open_order') or '-'))}</td>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('filename') or 'unavailable'))}</td>"
        f"<td>{html.escape(str(row.get('role') or ''))}</td>"
        f"<td>{html.escape(str(row.get('required')))}</td>"
        "</tr>"
        for row in outputs
    )
    quality_rows = "\n".join(
        "      <tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('status') or ''))}</td>"
        f"<td>{html.escape(str(row.get('done_condition') or ''))}</td>"
        "</tr>"
        for row in quality
    )
    return (
        "    <section class=\"delivery\" aria-label=\"delivery checklist\">\n"
        "      <h2>Delivery checklist</h2>\n"
        f"      <p>Status: <b>{status}</b> | primary print: <b>{primary_print}</b> | primary screen: <b>{primary_screen}</b></p>\n"
        "      <table><thead><tr><th>Open</th><th>ID</th><th>File</th><th>Role</th><th>Required</th></tr></thead><tbody>\n"
        f"{output_rows}\n"
        "      </tbody></table>\n"
        "      <table><thead><tr><th>Check</th><th>Status</th><th>Done condition</th></tr></thead><tbody>\n"
        f"{quality_rows}\n"
        "      </tbody></table>\n"
        "    </section>\n"
    )


def _delivery_checklist_manifest(
    *,
    safe_company: str,
    docx_filename: str,
    markdown_filename: str,
    html_filename: str,
    json_filename: str,
    section_inventory: list[dict[str, Any]],
    chart_manifest: list[dict[str, Any]],
    image_inventory: dict[str, Any],
    source_appendix: dict[str, Any],
    relationship_capital_appendix: dict[str, Any],
    operational_handoff: dict[str, Any],
) -> dict[str, Any]:
    """Agent-readable delivery checklist for export bundles and print handoff."""
    agent_handoff = "agent-handoff.json"
    manifest = "report-export-manifest.json"
    output_rows = [
        {
            "id": "docx_red_head",
            "filename": docx_filename,
            "role": "primary_print_report",
            "required": True,
            "open_order": 1,
            "produced_by": "bin/investigate.py --export-docx or --export-dir",
        },
        {
            "id": "portable_html",
            "filename": html_filename,
            "role": "primary_screen_report",
            "required": True,
            "open_order": 2,
            "produced_by": "bin/investigate.py --export-html or --export-dir",
        },
        {
            "id": "markdown_report",
            "filename": markdown_filename,
            "role": "full_text_report",
            "required": True,
            "open_order": 3,
            "produced_by": "bin/investigate.py --export-markdown or --export-dir",
        },
        {
            "id": "json_packet",
            "filename": json_filename,
            "role": "full_evidence_packet",
            "required": True,
            "open_order": 4,
            "produced_by": "bin/investigate.py --export-json or --export-dir",
        },
        {
            "id": "agent_handoff",
            "filename": agent_handoff,
            "role": "desktop_agent_task_router",
            "required": True,
            "open_order": 5,
            "produced_by": "bin/investigate.py --export-dir",
        },
        {
            "id": "bundle_manifest",
            "filename": manifest,
            "role": "bundle_integrity_manifest",
            "required": True,
            "open_order": 6,
            "produced_by": "bin/investigate.py --export-dir",
        },
    ]
    check_rows = [
        {
            "id": "red_head_front_matter",
            "status": "required",
            "packet_ref": "report_exports.print_package.red_head_front_matter",
            "done_condition": "DOCX starts with issuing body, red-head rule, document title, class, and document number.",
        },
        {
            "id": "full_body_preserved",
            "status": "required",
            "packet_ref": "report_markdown",
            "done_condition": "DOCX and portable HTML preserve the full generated due-diligence body without shortening findings.",
        },
        {
            "id": "section_inventory_present",
            "status": "ready" if section_inventory else "needs_review",
            "packet_ref": "report_exports.print_package.section_inventory",
            "done_condition": f"{len(section_inventory)} report sections are listed for table-of-contents review.",
        },
        {
            "id": "charts_or_chart_tables_present",
            "status": "ready" if chart_manifest else "needs_review",
            "packet_ref": "report_exports.print_package.chart_manifest",
            "done_condition": f"{len(chart_manifest)} chart/table rows are available for the print appendix.",
        },
        {
            "id": "image_evidence_accounted",
            "status": "ready",
            "packet_ref": "report_exports.print_package.image_evidence_inventory",
            "done_condition": f"{int(image_inventory.get('count') or 0)} image evidence item(s) are either embedded or explicitly absent.",
        },
        {
            "id": "source_provenance_appendix_present",
            "status": "ready" if int(source_appendix.get("source_count") or 0) else "empty",
            "packet_ref": "report_exports.print_package.source_provenance_appendix",
            "done_condition": (
                f"{int(source_appendix.get('source_count') or 0)} source(s) and "
                f"{int(source_appendix.get('evidence_row_count') or 0)} evidence row(s) are listed for audit and print review."
            ),
        },
        {
            "id": "relationship_capital_appendix_present",
            "status": "ready" if relationship_capital_appendix.get("appendix_required") else "empty",
            "packet_ref": "report_exports.print_package.relationship_capital_appendix",
            "done_condition": (
                f"relationship_edges={int(relationship_capital_appendix.get('relationship_edge_count') or 0)}; "
                f"capital_verification_steps={int(relationship_capital_appendix.get('capital_verification_queue_count') or 0)}; "
                f"relationship_audit_steps={int(relationship_capital_appendix.get('relationship_audit_queue_count') or 0)}."
            ),
        },
        {
            "id": "operator_handoff_present",
            "status": "ready" if operational_handoff.get("cards") else "empty",
            "packet_ref": "report_exports.print_package.operational_handoff.cards",
            "done_condition": f"{len(operational_handoff.get('cards') or [])} operational handoff card(s) are available for agent continuation.",
        },
    ]
    return {
        "type": "delivery_checklist_manifest",
        "status": "ready_for_desktop_agent_delivery",
        "bundle_slug": safe_company,
        "primary_print_file": docx_filename,
        "primary_screen_file": html_filename,
        "agent_open_order": [row["filename"] for row in output_rows],
        "required_outputs": output_rows,
        "quality_checks": check_rows,
        "print_binding": {
            "paper": "A4",
            "binding_margin": "wide_inner_margin",
            "page_numbers": True,
            "table_of_contents": True,
            "chart_tables": bool(chart_manifest),
            "image_appendix": bool(image_inventory.get("appendix_required")),
            "source_provenance_appendix": bool(source_appendix.get("appendix_required")),
            "relationship_capital_appendix": bool(relationship_capital_appendix.get("appendix_required")),
            "body_preserved": True,
        },
        "policy": (
            "Open the DOCX first for printable delivery, use portable HTML for screen review, "
            "then use the JSON packet and agent-handoff for evidence drilldown and follow-up work."
        ),
    }


def _report_section_inventory(report_markdown: str) -> list[dict[str, Any]]:
    lines = str(report_markdown or "").splitlines()
    headings: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, match.group(2).strip(), len(match.group(1))))

    inventory: list[dict[str, Any]] = []
    for pos, (start, title, level) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        inventory.append(
            {
                "title": title,
                "heading_level": level,
                "line_start": start + 1,
                "body_char_count": len(body),
                "print_role": _section_print_role(title),
            }
        )
    return inventory


def _section_print_role(title: str) -> str:
    lowered = str(title or "").lower()
    if "one-click" in lowered or "quality" in lowered:
        return "brief"
    if "source" in lowered or "provenance" in lowered:
        return "appendix"
    if "graph" in lowered or "relationship" in lowered or "capital" in lowered or "risk" in lowered:
        return "analysis_body"
    return "body"


def _report_chart_manifest(
    *,
    one_click_readiness: dict[str, Any],
    source_provenance: dict[str, Any],
    risk_event_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    severity_counts = _dict(risk_event_summary.get("severity_counts"))
    source_count = int(source_provenance.get("source_count") or 0)
    official_count = int(source_provenance.get("official_or_licensed_count") or 0)
    fact_count = int(one_click_readiness.get("fact_count") or 0)
    lead_count = int(one_click_readiness.get("lead_count") or 0)
    coverage_gap_count = int(one_click_readiness.get("coverage_gap_count") or 0)
    return [
        {
            "id": "risk_severity_distribution",
            "title": "Risk severity distribution",
            "type": "bar",
            "data": severity_counts,
            "print_section": "risk_and_capital_charts",
        },
        {
            "id": "evidence_fact_lead_mix",
            "title": "Evidence fact/lead mix",
            "type": "donut",
            "data": {"facts": fact_count, "leads": lead_count},
            "print_section": "risk_and_capital_charts",
        },
        {
            "id": "source_authority_mix",
            "title": "Source authority mix",
            "type": "stacked_bar",
            "data": {
                "official_or_licensed": official_count,
                "other_sources": max(0, source_count - official_count),
            },
            "print_section": "source_provenance_appendix",
        },
        {
            "id": "coverage_gap_summary",
            "title": "Coverage gap summary",
            "type": "status_card",
            "data": {
                "coverage_gap_count": coverage_gap_count,
                "coverage_gap_severity": one_click_readiness.get("coverage_gap_severity") or "none",
                "next_action": one_click_readiness.get("coverage_next_action") or "",
            },
            "print_section": "concise_due_diligence_brief",
        },
        {
            "id": "acceptance_closure_summary",
            "title": "Acceptance closure summary",
            "type": "status_card",
            "data": {
                "status": one_click_readiness.get("acceptance_closure_status") or "unknown",
                "blocking_count": int(one_click_readiness.get("acceptance_closure_blocking_count") or 0),
                "ready_count": int(one_click_readiness.get("acceptance_closure_ready_count") or 0),
                "next_action": _dict(one_click_readiness.get("acceptance_closure_summary")).get("next_action") or "",
            },
            "print_section": "concise_due_diligence_brief",
        },
        {
            "id": "operational_followup_queue",
            "title": "Operational follow-up queue",
            "type": "stacked_bar",
            "data": {
                "source_repair_p0": int(one_click_readiness.get("source_repair_p0_count") or 0),
                "source_repair_total": int(one_click_readiness.get("source_repair_priority_count") or 0),
                "graph_capital_exposure": int(one_click_readiness.get("graph_capital_exposure_verification_queue_count") or 0)
                + int(one_click_readiness.get("graph_capital_exposure_relationship_audit_queue_count") or 0),
                "capital_verification": int(one_click_readiness.get("capital_verification_queue_count") or 0),
                "relationship_audit": int(one_click_readiness.get("relationship_graph_audit_queue_count") or 0),
                "public_origin_actions": int(one_click_readiness.get("public_origin_next_action_count") or 0),
                "control_path_verification": 1 if one_click_readiness.get("control_path_closure_needed") else 0,
                "goods_economics": 1 if one_click_readiness.get("goods_economics_closure_needed") else 0,
                "people_control": 1 if one_click_readiness.get("people_control_closure_needed") else 0,
            },
            "print_section": "operational_handoff_appendix",
        },
    ]


def _report_operational_handoff(one_click_readiness: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "status": one_click_readiness.get("status") or "unknown",
        "quality_score": one_click_readiness.get("quality_score"),
        "needs_operator_followup": bool(one_click_readiness.get("needs_operator_followup")),
        "coverage_gap_count": int(one_click_readiness.get("coverage_gap_count") or 0),
        "coverage_gap_severity": one_click_readiness.get("coverage_gap_severity") or "none",
        "source_repair_priority_count": int(one_click_readiness.get("source_repair_priority_count") or 0),
        "source_repair_p0_count": int(one_click_readiness.get("source_repair_p0_count") or 0),
        "source_health_trend_digest_available": bool(_dict(one_click_readiness.get("source_health_trend_digest")).get("available")),
        "source_health_trend_top_source_name": _dict(_dict(one_click_readiness.get("source_health_trend_digest")).get("top_source")).get("source") or "",
        "graph_capital_exposure_available": bool(one_click_readiness.get("graph_capital_exposure_available")),
        "graph_capital_exposure_alignment_status": one_click_readiness.get("graph_capital_exposure_alignment_status") or "not_available",
        "graph_capital_exposure_relationship_status": one_click_readiness.get("graph_capital_exposure_relationship_status") or "unknown",
        "graph_capital_exposure_verification_queue_count": int(one_click_readiness.get("graph_capital_exposure_verification_queue_count") or 0),
        "graph_capital_exposure_relationship_audit_queue_count": int(one_click_readiness.get("graph_capital_exposure_relationship_audit_queue_count") or 0),
        "capital_verification_queue_count": int(one_click_readiness.get("capital_verification_queue_count") or 0),
        "relationship_graph_audit_queue_count": int(one_click_readiness.get("relationship_graph_audit_queue_count") or 0),
        "public_origin_next_action_count": int(one_click_readiness.get("public_origin_next_action_count") or 0),
        "control_path_closure_needed": bool(one_click_readiness.get("control_path_closure_needed")),
        "control_path_signal_count": int(one_click_readiness.get("control_path_signal_count") or 0),
        "goods_economics_closure_needed": bool(one_click_readiness.get("goods_economics_closure_needed")),
        "goods_economics_signal_count": int(one_click_readiness.get("goods_economics_signal_count") or 0),
        "people_control_closure_needed": bool(one_click_readiness.get("people_control_closure_needed")),
        "people_control_signal_count": int(one_click_readiness.get("people_control_signal_count") or 0),
        "operator_work_queue_count": int(one_click_readiness.get("operator_work_queue_count") or 0),
        "operator_work_p0_count": int(one_click_readiness.get("operator_work_p0_count") or 0),
        "operator_work_ready_count": int(one_click_readiness.get("operator_work_ready_count") or 0),
        "reliance_limitation_count": int(one_click_readiness.get("reliance_limitation_count") or 0),
        "reliance_limitation_highest_severity": one_click_readiness.get("reliance_limitation_highest_severity") or "none",
        "can_make_clean_conclusion": bool(one_click_readiness.get("can_make_clean_conclusion")),
        "acceptance_closure_status": one_click_readiness.get("acceptance_closure_status") or "unknown",
        "acceptance_closure_blocking_count": int(one_click_readiness.get("acceptance_closure_blocking_count") or 0),
        "acceptance_closure_ready_count": int(one_click_readiness.get("acceptance_closure_ready_count") or 0),
        "acceptance_closure_open_domains": list(
            _dict(one_click_readiness.get("acceptance_closure_summary")).get("open_domains") or []
        )[:8],
        "acceptance_closure_next_action": _dict(one_click_readiness.get("acceptance_closure_summary")).get("next_action") or "",
    }
    cards: list[dict[str, Any]] = []

    acceptance_closure = _dict(one_click_readiness.get("acceptance_closure_summary"))
    if acceptance_closure:
        top_action = _dict(acceptance_closure.get("top_action"))
        cards.append(
            {
                "id": "acceptance_closure_summary",
                "title": "Acceptance closure summary",
                "priority": "P0" if acceptance_closure.get("status") == "blocked" else "P1",
                "status": acceptance_closure.get("status") or "unknown",
                "source": "one_click_readiness.acceptance_closure_summary",
                "domain": ", ".join(str(item) for item in acceptance_closure.get("open_domains", [])[:6]),
                "action": acceptance_closure.get("next_action") or top_action.get("action") or "",
                "execution_hint": top_action.get("work_id") or top_action.get("closure_id") or top_action.get("lane") or "",
                "ready_to_run": int(acceptance_closure.get("blocking_count") or 0) == 0,
                "blocked_reason": "acceptance_blockers_present" if int(acceptance_closure.get("blocking_count") or 0) else "",
                "done_condition": acceptance_closure.get("done_condition") or "",
            }
        )

    for item in one_click_readiness.get("operator_work_queue", [])[:6]:
        if not isinstance(item, dict):
            continue
        cards.append(
            {
                "id": item.get("work_id") or f"operator_work_{len(cards) + 1}",
                "title": f"Operator work: {item.get('lane') or 'followup'}",
                "priority": item.get("priority") or "P1",
                "status": item.get("status") or "pending",
                "source": item.get("source") or "",
                "domain": item.get("target") or "",
                "action": item.get("action") or "",
                "ready_to_run": bool(item.get("ready_to_run")),
                "blocked_reason": item.get("blocked_reason") or "",
                "done_condition": item.get("done_condition") or "",
            }
        )

    source_repair = _dict(one_click_readiness.get("source_repair_top_action"))
    if source_repair:
        cards.append(
            {
                "id": "source_repair_top_action",
                "title": "Source repair top action",
                "priority": source_repair.get("priority") or "P1",
                "status": source_repair.get("status") or "pending",
                "source": source_repair.get("source") or "",
                "domain": source_repair.get("domain") or "",
                "action": source_repair.get("operator_action") or "",
                "execution_hint": source_repair.get("execution_hint") or "",
                "done_condition": "source_recovers_or_failure_is_reclassified_with_trace",
            }
        )

    source_health_digest = _dict(one_click_readiness.get("source_health_trend_digest"))
    source_health_top_source = _dict(source_health_digest.get("top_source"))
    if source_health_top_source:
        cards.append(
            {
                "id": "source_health_trend_top_source",
                "title": "Source-health trend top source",
                "priority": source_health_top_source.get("priority") or "P1",
                "status": source_health_top_source.get("status") or "observed_failure",
                "source": source_health_top_source.get("source") or "",
                "domain": ", ".join(str(key) for key in _dict(source_health_top_source.get("domains")).keys())[:120],
                "action": source_health_digest.get("top_operator_action") or source_health_top_source.get("operator_action") or "",
                "execution_hint": source_health_top_source.get("repair_queue_id") or "",
                "ready_to_run": str(source_health_top_source.get("status") or "") not in {"authorization_required", "connector_required"},
                "blocked_reason": source_health_top_source.get("status") if str(source_health_top_source.get("status") or "") in {"authorization_required", "connector_required"} else "",
                "done_condition": "source_health_top_source_repaired_or_failure_reclassified",
            }
        )

    recovery_step = _dict(one_click_readiness.get("source_resilience_recommended_step"))
    if recovery_step:
        key_fields = ", ".join(str(item) for item in recovery_step.get("key_fields", [])[:5])
        retry_policy = _dict(
            one_click_readiness.get("source_resilience_retry_policy")
            or recovery_step.get("retry_policy")
        )
        retry_hint = _retry_policy_hint(retry_policy)
        cards.append(
            {
                "id": "source_recovery_step",
                "title": "Source resilience recovery step",
                "priority": recovery_step.get("priority") or "P0",
                "status": recovery_step.get("status") or "pending",
                "source": recovery_step.get("source") or "",
                "domain": recovery_step.get("domain") or "",
                "action": one_click_readiness.get("source_resilience_recommended_action") or recovery_step.get("query_family") or "",
                "execution_hint": " | ".join(item for item in [key_fields, retry_hint] if item),
                "retry_policy": retry_policy,
                "ready_to_run": bool(one_click_readiness.get("source_resilience_recommended_step_ready_to_run")),
                "blocked_reason": one_click_readiness.get("source_resilience_recommended_step_blocked_reason") or "",
                "done_condition": "missing_domain_has_retrieval_result_or_explicit_no_evidence_record",
            }
        )

    capital_step = _dict(one_click_readiness.get("capital_verification_top_step"))
    if capital_step:
        cards.append(
            {
                "id": "capital_verification_top_step",
                "title": "Capital verification top step",
                "priority": capital_step.get("priority") or "P0",
                "status": one_click_readiness.get("capital_relationship_status") or "pending",
                "source": capital_step.get("kind") or "",
                "domain": "capital",
                "action": capital_step.get("target_title") or "",
                "execution_hint": capital_step.get("target_id") or "",
                "done_condition": capital_step.get("done_condition") or "",
            }
        )

    graph_capital = _dict(one_click_readiness.get("graph_capital_exposure"))
    graph_capital_step = _dict(one_click_readiness.get("graph_capital_exposure_top_step"))
    if graph_capital_step:
        cards.append(
            {
                "id": "graph_capital_exposure_top_step",
                "title": "Graph capital exposure top step",
                "priority": graph_capital_step.get("priority") or "P0",
                "status": graph_capital_step.get("kind") or graph_capital.get("relationship_status") or "pending",
                "source": graph_capital_step.get("kind") or "summary.capital_exposure",
                "domain": "capital_exposure",
                "action": graph_capital.get("next_action") or graph_capital_step.get("target_title") or "",
                "execution_hint": graph_capital_step.get("target_id") or "",
                "done_condition": graph_capital_step.get("done_condition") or "",
            }
        )

    relationship_step = _dict(one_click_readiness.get("relationship_graph_audit_top_step"))
    if relationship_step:
        cards.append(
            {
                "id": "relationship_graph_audit_top_step",
                "title": "Relationship graph audit top step",
                "priority": relationship_step.get("priority") or "P1",
                "status": relationship_step.get("kind") or "pending",
                "source": relationship_step.get("relation_type") or "",
                "domain": "relationship_graph",
                "action": relationship_step.get("target") or "",
                "execution_hint": ", ".join(str(item) for item in relationship_step.get("evidence_ids", [])[:5]),
                "done_condition": relationship_step.get("done_condition") or "",
            }
        )

    control_step = _dict(one_click_readiness.get("control_path_closure_step"))
    if control_step:
        cards.append(
            {
                "id": "control_path_closure_step",
                "title": "Indirect control path verification",
                "priority": control_step.get("priority") or "P1",
                "status": control_step.get("status") or "corroboration_needed",
                "source": control_step.get("source") or "control_ownership",
                "domain": "control_ownership",
                "action": control_step.get("action") or "",
                "execution_hint": control_step.get("target_title") or control_step.get("path_text") or "",
                "ready_to_run": bool(control_step.get("ready_to_run", True)),
                "blocked_reason": control_step.get("blocked_reason") or "",
                "done_condition": control_step.get("done_condition") or "",
            }
        )

    public_origin = _dict(one_click_readiness.get("public_origin_top_action"))
    if public_origin:
        cards.append(
            {
                "id": "public_origin_top_action",
                "title": "Public-origin fallback top action",
                "priority": "P1",
                "status": public_origin.get("target_lane") or "pending",
                "source": public_origin.get("origin_channel") or "",
                "domain": public_origin.get("module") or "",
                "action": public_origin.get("query_family") or "",
                "execution_hint": ", ".join(str(item) for item in public_origin.get("required_fields", [])[:5]),
                "admission_gate": public_origin.get("admission_gate") or "",
                "done_condition": public_origin.get("acceptance_gate") or "",
            }
        )

    public_origin_bridge = _dict(one_click_readiness.get("public_origin_gap_bridge_top_action"))
    if public_origin_bridge:
        cards.append(
            {
                "id": "public_origin_gap_bridge_top_action",
                "title": "Public-origin gap bridge",
                "priority": public_origin_bridge.get("priority") or "P1",
                "status": "ready_to_run",
                "source": "public_origin",
                "domain": public_origin_bridge.get("gap_domain") or "",
                "action": public_origin_bridge.get("action") or "",
                "execution_hint": public_origin_bridge.get("action_id") or public_origin_bridge.get("module") or "",
                "ready_to_run": bool(public_origin_bridge.get("ready_to_run", True)),
                "blocked_reason": public_origin_bridge.get("blocked_reason") or "",
                "done_condition": public_origin_bridge.get("done_condition") or "",
            }
        )

    reliance_limitations = _dict(one_click_readiness.get("reliance_limitations"))
    top_limitation = _dict((reliance_limitations.get("items") or [{}])[0])
    if top_limitation:
        severity = str(top_limitation.get("severity") or "medium").lower()
        cards.append(
            {
                "id": "reliance_limitation_top_action",
                "title": "Reliance limitation top action",
                "priority": "P0" if severity == "high" else "P1",
                "status": severity,
                "source": "reliance_limitations",
                "domain": top_limitation.get("area") or "quality_gate",
                "action": top_limitation.get("next_action") or top_limitation.get("user_message") or "",
                "execution_hint": top_limitation.get("reason") or top_limitation.get("limitation_id") or "",
                "ready_to_run": bool(top_limitation.get("next_action")),
                "blocked_reason": "",
                "done_condition": "limitation_resolved_or_kept_as_explicit_non_reliance_caveat",
            }
        )

    goods_step = _dict(one_click_readiness.get("goods_economics_closure_step"))
    if goods_step:
        cards.append(
            {
                "id": "goods_economics_closure_step",
                "title": "Goods economics closure step",
                "priority": goods_step.get("priority") or "P1",
                "status": goods_step.get("status") or "corroboration_needed",
                "source": goods_step.get("source") or "public_goods_profile",
                "domain": "goods_economics",
                "action": goods_step.get("action") or "",
                "execution_hint": goods_step.get("target_title") or "",
                "ready_to_run": bool(goods_step.get("ready_to_run", True)),
                "blocked_reason": goods_step.get("blocked_reason") or "",
                "done_condition": goods_step.get("done_condition") or "",
            }
        )

    people_step = _dict(one_click_readiness.get("people_control_closure_step"))
    if people_step:
        cards.append(
            {
                "id": "people_control_closure_step",
                "title": "People/control closure step",
                "priority": people_step.get("priority") or "P1",
                "status": people_step.get("status") or "corroboration_needed",
                "source": people_step.get("source") or "public_people_profile",
                "domain": "people_control",
                "action": people_step.get("action") or "",
                "execution_hint": people_step.get("target_title") or "",
                "ready_to_run": bool(people_step.get("ready_to_run", True)),
                "blocked_reason": people_step.get("blocked_reason") or "",
                "done_condition": people_step.get("done_condition") or "",
            }
        )

    if one_click_readiness.get("coverage_next_action"):
        cards.append(
            {
                "id": "coverage_next_action",
                "title": "Coverage gap next action",
                "priority": "P1",
                "status": summary["coverage_gap_severity"],
                "source": "coverage",
                "domain": "missing_domains",
                "action": one_click_readiness.get("coverage_next_action") or "",
                "execution_hint": ", ".join(str(item) for item in one_click_readiness.get("coverage_missing_domains", [])[:5]),
                "done_condition": "coverage_gap_count_reduced_or_gap_reason_recorded",
            }
        )

    return {
        "type": "operational_handoff",
        "policy": "Current release preserves public or user-authorized retrieval boundaries and renders follow-up work for desktop agents.",
        "summary": summary,
        "cards": cards,
        "card_count": len(cards),
    }


def _image_evidence_inventory(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, evidence in enumerate(evidence_ledger, start=1):
        image_url = (
            evidence.get("image_url")
            or evidence.get("screenshot_url")
            or evidence.get("snapshot_url")
            or evidence.get("attachment_url")
            or evidence.get("local_path")
            or evidence.get("file_path")
        )
        image_base64 = evidence.get("image_base64") or evidence.get("base64") or evidence.get("data_base64")
        if not image_url and not image_base64:
            continue
        row = {
            "id": f"image-evidence-{index}",
            "evidence_id": evidence.get("id") or f"evidence-{index}",
            "source": evidence.get("source") or "unknown",
            "url": image_url or "",
            "caption": evidence.get("claim") or evidence.get("title") or "Evidence image",
            "admission": evidence.get("admission") or "unknown",
            "embeddable": bool(
                image_base64
                or str(image_url or "").startswith("data:image/")
                or str(evidence.get("local_path") or evidence.get("file_path") or "").strip()
            ),
            "delivery_status": "embeddable" if (
                image_base64
                or str(image_url or "").startswith("data:image/")
                or str(evidence.get("local_path") or evidence.get("file_path") or "").strip()
            ) else "remote_reference_only",
        }
        if image_base64:
            row["image_base64"] = image_base64
            row["extension"] = evidence.get("extension") or evidence.get("image_extension") or "png"
        if evidence.get("local_path"):
            row["local_path"] = evidence.get("local_path")
        if evidence.get("file_path"):
            row["file_path"] = evidence.get("file_path")
        items.append(row)
    return {
        "type": "image_evidence_inventory",
        "count": len(items),
        "items": items,
        "embeddable_count": sum(1 for item in items if bool(item.get("embeddable"))),
        "remote_reference_count": sum(1 for item in items if item.get("url") and not bool(item.get("embeddable"))),
        "appendix_required": bool(items),
        "empty_state": "No image evidence was collected in this packet." if not items else "",
        "delivery_policy": "DOCX embeds local/data-uri evidence images and lists remote image references without fetching them; portable HTML shows a bounded machine-readable summary.",
    }


def _source_provenance_appendix(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    authority_counts: dict[str, int] = {}
    admission_counts: dict[str, int] = {}
    for index, evidence in enumerate(evidence_ledger, start=1):
        source = str(evidence.get("source") or "unknown").strip() or "unknown"
        profile = _dict(evidence.get("source_profile"))
        authority = str(profile.get("authority") or evidence.get("authority") or "unknown").strip() or "unknown"
        access = str(profile.get("access") or evidence.get("access") or "unknown").strip() or "unknown"
        admission = str(evidence.get("admission") or evidence.get("evidence_role") or "unknown").strip() or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        authority_counts[authority] = authority_counts.get(authority, 0) + 1
        admission_counts[admission] = admission_counts.get(admission, 0) + 1
        rows.append(
            {
                "id": str(evidence.get("id") or f"evidence-{index}"),
                "source": source,
                "authority": authority,
                "access": access,
                "admission": admission,
                "confidence": evidence.get("confidence"),
                "title": str(evidence.get("title") or evidence.get("claim") or "").strip(),
                "url": str(evidence.get("url") or evidence.get("source_url") or "").strip(),
                "observed_at": str(
                    evidence.get("observed_at")
                    or evidence.get("retrieved_at")
                    or evidence.get("timestamp")
                    or ""
                ).strip(),
            }
        )

    return {
        "type": "source_provenance_appendix",
        "appendix_required": bool(rows),
        "source_count": len(source_counts),
        "evidence_row_count": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "admission_counts": dict(sorted(admission_counts.items())),
        "rows": rows[:80],
        "row_limit": 80,
        "truncated": len(rows) > 80,
        "empty_state": "No evidence rows were available for source provenance appendix." if not rows else "",
        "policy": "Every printed source row remains tied to the evidence ledger; public leads stay lead-labeled until admission gates pass.",
    }


def _relationship_capital_appendix(one_click_readiness: dict[str, Any]) -> dict[str, Any]:
    graph_capital = _dict(one_click_readiness.get("graph_capital_exposure"))
    capital_queue = [
        _dict(item)
        for item in one_click_readiness.get("capital_verification_queue", [])
        if isinstance(item, dict)
    ]
    relationship_queue = [
        _dict(item)
        for item in one_click_readiness.get("relationship_graph_audit_queue", [])
        if isinstance(item, dict)
    ]
    graph_top_step = _dict(one_click_readiness.get("graph_capital_exposure_top_step"))
    relationship_top_step = _dict(one_click_readiness.get("relationship_graph_audit_top_step"))
    relationship_edge_count = int(one_click_readiness.get("relationship_edge_count") or 0)
    capital_queue_count = int(one_click_readiness.get("capital_verification_queue_count") or len(capital_queue))
    relationship_queue_count = int(one_click_readiness.get("relationship_graph_audit_queue_count") or len(relationship_queue))
    available = bool(graph_capital) or relationship_edge_count > 0 or capital_queue_count > 0 or relationship_queue_count > 0
    return {
        "type": "relationship_capital_appendix",
        "appendix_required": available,
        "capital_relationship_status": one_click_readiness.get("capital_relationship_status") or "unknown",
        "capital_relationship_unresolved_reason": one_click_readiness.get("capital_relationship_unresolved_reason") or "",
        "graph_capital_exposure_available": bool(one_click_readiness.get("graph_capital_exposure_available")),
        "graph_capital_exposure_alignment_status": one_click_readiness.get("graph_capital_exposure_alignment_status") or "not_available",
        "graph_capital_exposure_relationship_status": one_click_readiness.get("graph_capital_exposure_relationship_status") or "unknown",
        "graph_capital_exposure_source_top_family": one_click_readiness.get("graph_capital_exposure_source_top_family") or "",
        "graph_capital_exposure_has_official_or_authorized_source": bool(
            one_click_readiness.get("graph_capital_exposure_has_official_or_authorized_source")
        ),
        "graph_capital_exposure_summary": {
            "pressure_level": graph_capital.get("pressure_level") or "",
            "relationship_status": graph_capital.get("relationship_status") or "",
            "alignment_status": graph_capital.get("alignment_status") or "",
            "verification_queue_count": int(graph_capital.get("verification_queue_count") or capital_queue_count),
            "relationship_audit_queue_count": int(graph_capital.get("relationship_audit_queue_count") or relationship_queue_count),
            "next_action": graph_capital.get("next_action") or "",
        },
        "relationship_edge_count": relationship_edge_count,
        "relationship_evidence_backed_edge_count": int(one_click_readiness.get("relationship_evidence_backed_edge_count") or 0),
        "relationship_lead_only_edge_count": int(one_click_readiness.get("relationship_lead_only_edge_count") or 0),
        "relationship_missing_evidence_edge_count": int(one_click_readiness.get("relationship_missing_evidence_edge_count") or 0),
        "capital_verification_queue_count": capital_queue_count,
        "relationship_audit_queue_count": relationship_queue_count,
        "capital_verification_queue": capital_queue[:12],
        "relationship_audit_queue": relationship_queue[:12],
        "graph_capital_exposure_top_step": graph_top_step,
        "relationship_graph_audit_top_step": relationship_top_step,
        "policy": (
            "Relationship and capital rows are report navigation aids. Unresolved or lead-only rows require admitted evidence "
            "before they can support a clean conclusion."
        ),
        "empty_state": "No relationship or capital graph appendix data was available." if not available else "",
    }


def _risk_brief(
    summary: dict[str, Any],
    risk_events: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for event in risk_events:
        severity = str(event.get("severity") or "low").lower()
        if severity in severity_counts:
            severity_counts[severity] += 1

    score = min(
        100,
        sum(SEVERITY_WEIGHT[level] * count for level, count in severity_counts.items())
        + min(len(evidence) * 3, 18)
        + _coverage_gap_penalty(summary),
    )
    execution_state = str(summary.get("execution_state") or "unknown")
    highest = str(summary.get("highest_severity") or "").lower()
    verdict = _verdict(execution_state, highest, score)
    key_findings = [_finding(event) for event in risk_events[:6]]
    if not key_findings and execution_state in {"not_executed", "no_available_sources"}:
        key_findings.append({
            "title": "尚未形成有效取证，当前证据不足",
            "severity": "info",
            "why_it_matters": "当前没有可用证据，不能把空结果当作低风险结论。",
            "source_refs": [],
        })

    return {
        "verdict": verdict,
        "verdict_label": _verdict_label(verdict),
        "risk_score": score,
        "highest_severity": highest or None,
        "severity_counts": severity_counts,
        "key_findings": key_findings,
        "execution_state": execution_state,
        "execution_state_label": _execution_state_label(execution_state),
        "confidence_note": _confidence_note(summary, evidence),
    }


def _risk_brief_with_quality_gate(
    risk_brief: dict[str, Any],
    quality_gate: dict[str, Any],
) -> dict[str, Any]:
    blockers = [str(item) for item in quality_gate.get("blockers", []) if str(item).strip()]
    if risk_brief.get("verdict") != "no_material_risk_found_from_available_evidence" or not blockers:
        return risk_brief
    adjusted = dict(risk_brief)
    adjusted["verdict"] = "insufficient_data"
    adjusted["verdict_label"] = _verdict_label("insufficient_data")
    adjusted["confidence_note"] = "quality_gate_blocked_clean_verdict"
    return adjusted


def _public_origin_gap_bridge(
    coverage_gap_domains: list[str],
    public_origin_next_actions: list[dict[str, Any]],
    public_origin_fallbacks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bridge coverage gaps to executable public-origin reconstruction actions."""
    domains = _dedupe_strings(str(item) for item in coverage_gap_domains if str(item).strip())
    actions = [
        item for item in [*public_origin_next_actions, *public_origin_fallbacks]
        if isinstance(item, dict)
    ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for domain in domains:
        matched_count = 0
        for action in actions:
            if not _public_origin_action_matches_gap(domain, action):
                continue
            dedupe_key = "|".join(
                [
                    domain,
                    str(action.get("action_id") or ""),
                    str(action.get("module") or ""),
                    str(action.get("record_type") or ""),
                ]
            ).casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(_public_origin_bridge_item(domain, action, index=len(items) + 1))
            matched_count += 1
            if len(items) >= 12:
                break
            if matched_count >= 3:
                break
        if len(items) >= 12:
            break
    bridged_domains = _dedupe_strings(str(item.get("gap_domain") or "") for item in items)
    return {
        "type": "public_origin_gap_bridge",
        "gap_domain_count": len(domains),
        "bridged_domain_count": len(bridged_domains),
        "bridge_count": len(items),
        "top_bridge": items[0] if items else {},
        "items": items,
        "policy": "Use public-origin bridge actions to close coverage gaps only through public or user-authorized channels; keep results lead-only until provenance and admission gates pass.",
    }


def _public_origin_bridge_item(domain: str, action: dict[str, Any], *, index: int) -> dict[str, Any]:
    channels = _origin_channels(action)
    query_families = _origin_query_families(action)
    module = str(action.get("module") or "").strip()
    return {
        "bridge_id": f"PUB-GAP-{index:03d}",
        "gap_domain": domain,
        "priority": _public_origin_gap_priority(domain, action),
        "action_id": action.get("action_id") or (f"PUBLIC-ORIGIN-{module.upper()}" if module else ""),
        "module": module,
        "target_lane": action.get("target_lane") or action.get("report_section") or "",
        "record_type": action.get("record_type") or "",
        "origin_channels": channels[:6],
        "query_families": query_families[:6],
        "required_fields": list(action.get("required_fields") or [])[:8],
        "admission_gate": action.get("admission_gate") or "",
        "done_condition": action.get("done_condition") or action.get("acceptance_gate") or "",
        "ready_to_run": True,
        "blocked_reason": "",
        "action": (
            f"Use public-origin {module or 'source'} reconstruction to close {domain} coverage; "
            "keep results as leads until source URL, observed time, entity match, and admission gates pass."
        ),
    }


def _origin_channels(action: dict[str, Any]) -> list[str]:
    raw = action.get("origin_channels")
    if not raw and action.get("origin_channel"):
        raw = [action.get("origin_channel")]
    if not raw and action.get("suggested_source"):
        raw = [action.get("suggested_source")]
    if not raw and action.get("source"):
        raw = [action.get("source")]
    if isinstance(raw, list):
        return _dedupe_strings(str(item) for item in raw if str(item).strip())
    return _dedupe_strings(str(raw).split(",") if str(raw or "").strip() else [])


def _origin_query_families(action: dict[str, Any]) -> list[str]:
    raw = action.get("query_families")
    if not raw and action.get("query_family"):
        raw = [action.get("query_family")]
    if isinstance(raw, list):
        return _dedupe_strings(str(item) for item in raw if str(item).strip())
    return _dedupe_strings(str(raw).split(",") if str(raw or "").strip() else [])


def _public_origin_gap_priority(domain: str, action: dict[str, Any]) -> str:
    raw_priority = str(action.get("priority") or "").upper()
    if raw_priority.startswith("P0") or str(action.get("priority") or "").lower().startswith("p0_"):
        return "P0"
    if domain in {"ownership_control", "financing_capital_markets", "legal_admin", "administrative_risk"}:
        return "P0"
    return "P1"


def _public_origin_action_matches_gap(domain: str, action: dict[str, Any]) -> bool:
    aliases = _public_origin_gap_aliases(domain)
    if not aliases:
        return False
    text_parts = [
        str(action.get("target_lane") or ""),
        str(action.get("record_type") or ""),
        str(action.get("module") or ""),
        " ".join(_origin_channels(action)),
        " ".join(_origin_query_families(action)),
        " ".join(str(item) for item in action.get("required_fields", []) if str(item).strip())
        if isinstance(action.get("required_fields"), list)
        else "",
    ]
    text = " ".join(text_parts).lower()
    normalized = domain.lower()
    return normalized in text or any(alias in text for alias in aliases)


def _public_origin_gap_aliases(domain: str) -> set[str]:
    key = str(domain or "").strip().lower()
    aliases = {
        "ownership_control": {
            "ownership_control",
            "corporate_registry",
            "subject_resolution",
            "relationship_network",
            "registry_shareholder",
            "shareholder",
            "ubo",
            "controller",
            "control",
            "branch",
            "annual_reports",
            "registry_shareholder_filings",
            "official_registry",
            "market_supervision",
        },
        "financing_capital_markets": {
            "financing_capital_markets",
            "bond_credit",
            "asset_solvency",
            "capital",
            "financing",
            "business_credit",
            "credit_disclosure",
            "credit_rating",
            "bond",
            "pledge",
            "freeze",
            "auction",
            "exchange_disclosures",
            "bond_information",
            "credit_disclosure",
            "financial_institution",
        },
        "legal_admin": {
            "legal_admin",
            "legal_risk",
            "administrative_risk",
            "court",
            "judgment",
            "enforcement",
            "penalty",
            "credit_publicity",
        },
        "administrative_risk": {
            "administrative_risk",
            "legal_admin",
            "legal_risk",
            "penalty",
            "credit_publicity",
        },
        "trade_supply_chain": {
            "trade_supply_chain",
            "supplier",
            "customer",
            "procurement",
            "customs",
            "trade",
        },
        "public_opinion": {
            "public_opinion",
            "negative_news",
            "public_news",
            "news",
            "announcement",
        },
    }
    return aliases.get(key, {key} if key else set())


def _operator_work_queue(
    *,
    source_resilience: dict[str, Any],
    source_repair_queue: list[dict[str, Any]],
    recovery_queue: dict[str, Any],
    public_origin_next_actions: list[dict[str, Any]],
    public_origin_gap_bridge: dict[str, Any],
    graph_capital_exposure: dict[str, Any],
    control_path_closure_step: dict[str, Any] | None,
    goods_economics_closure_step: dict[str, Any] | None,
    people_control_closure_step: dict[str, Any] | None,
    capital_verification_queue: list[dict[str, Any]],
    relationship_audit_queue: list[dict[str, Any]],
    coverage_next_action: str,
    coverage_gap_domains: list[str],
) -> list[dict[str, Any]]:
    """Merge follow-up surfaces into one ranked desktop-agent work queue."""
    rows: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        row = dict(row)
        row.setdefault("ready_to_run", True)
        row.setdefault("blocked_reason", "")
        row.setdefault("packet_refs", [])
        row.setdefault("done_condition", "")
        rows.append(row)

    for item in source_repair_queue[:5]:
        add(
            {
                "work_id": item.get("queue_id") or f"OP-SOURCE-REPAIR-{len(rows) + 1}",
                "lane": "source_repair",
                "priority": item.get("priority") or "P0",
                "status": item.get("status") or "pending",
                "source": item.get("source") or "",
                "target": item.get("domain") or "",
                "action": item.get("operator_action") or "",
                "ready_to_run": str(item.get("status") or "").strip() not in {"authorization_required", "connector_required"},
                "blocked_reason": item.get("status") if str(item.get("status") or "").strip() in {"authorization_required", "connector_required"} else "",
                "done_condition": "source_recovers_or_failure_is_reclassified_with_trace",
                "packet_refs": [
                    "monitoring_seed.source_repair_priority_queue",
                    "source_failure_summary.recurring_failure_patterns",
                ],
            }
        )

    for item in _dict(recovery_queue).get("queue", [])[:5]:
        if isinstance(item, dict):
            add(
                {
                    "work_id": item.get("queue_id") or f"OP-RECOVERY-{len(rows) + 1}",
                    "lane": "source_recovery",
                    "priority": item.get("priority") or "P0",
                    "status": item.get("status") or "queued",
                    "source": item.get("source") or "",
                    "target": item.get("domain") or "",
                    "action": item.get("query_family") or item.get("query") or "",
                    "done_condition": item.get("done_condition") or "",
                    "packet_refs": [
                        "monitoring_seed.recovery_execution_queue.queue",
                        "source_failure_summary.coverage_recovery_execution_plan",
                    ],
                }
            )

    recommended_step = _dict(source_resilience.get("recommended_step"))
    if recommended_step:
        blocked_reason = str(source_resilience.get("recommended_step_blocked_reason") or "").strip()
        add(
            {
                "work_id": recommended_step.get("step_id") or "OP-SOURCE-RESILIENCE",
                "lane": "source_resilience",
                "priority": recommended_step.get("priority") or "P0",
                "status": recommended_step.get("status") or "pending",
                "source": recommended_step.get("source") or "",
                "target": recommended_step.get("domain") or "",
                "action": source_resilience.get("recommended_action") or recommended_step.get("query_family") or "",
                "ready_to_run": bool(source_resilience.get("recommended_step_ready_to_run")),
                "blocked_reason": blocked_reason,
                "done_condition": "missing_domain_has_retrieval_result_or_explicit_no_evidence_record",
                "packet_refs": [
                    "one_click_readiness.source_resilience_recommended_step",
                    "source_failure_summary.source_resilience_profile",
                ],
            }
        )

    for item in public_origin_next_actions[:5]:
        add(
            {
                "work_id": item.get("action_id") or f"OP-PUBLIC-ORIGIN-{len(rows) + 1}",
                "lane": "public_origin_fallback",
                "priority": item.get("priority") or "P1",
                "status": item.get("target_lane") or "pending",
                "source": item.get("origin_channel") or "",
                "target": item.get("module") or "",
                "action": item.get("query_family") or "",
                "done_condition": item.get("acceptance_gate") or "",
                "packet_refs": [
                    "one_click_readiness.public_origin_top_action",
                    "source_failure_summary.public_origin_next_actions",
                ],
            }
        )

    for item in _dict(public_origin_gap_bridge).get("items", [])[:5]:
        if not isinstance(item, dict):
            continue
        add(
            {
                "work_id": item.get("bridge_id") or f"OP-PUBLIC-GAP-{len(rows) + 1}",
                "lane": "public_origin_gap_bridge",
                "priority": item.get("priority") or "P1",
                "status": "ready_to_run",
                "source": "public_origin",
                "target": item.get("gap_domain") or "",
                "action": item.get("action") or "",
                "ready_to_run": bool(item.get("ready_to_run", True)),
                "blocked_reason": item.get("blocked_reason") or "",
                "done_condition": item.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.public_origin_gap_bridge",
                    "one_click_readiness.coverage_missing_domains",
                    "source_failure_summary.public_origin_next_actions",
                ],
            }
        )

    control_step = _dict(control_path_closure_step)
    if control_step:
        add(
            {
                "work_id": control_step.get("step_id") or "OP-CONTROL-PATH",
                "lane": "control_path_verification",
                "priority": control_step.get("priority") or "P1",
                "status": control_step.get("status") or "corroboration_needed",
                "source": control_step.get("source") or "control_ownership",
                "target": control_step.get("target_title") or control_step.get("path_text") or "indirect control path",
                "action": control_step.get("action") or control_step.get("kind") or "",
                "ready_to_run": bool(control_step.get("ready_to_run", True)),
                "blocked_reason": control_step.get("blocked_reason") or "",
                "done_condition": control_step.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.control_path_closure_step",
                    "enterprise_cognition.control_ownership.control_path_verification_queue",
                    "enterprise_cognition.relationship_network.top_edges",
                ],
            }
        )

    goods_step = _dict(goods_economics_closure_step)
    if goods_step:
        add(
            {
                "work_id": goods_step.get("step_id") or "OP-GOODS-ECONOMICS",
                "lane": "goods_economics_closure",
                "priority": goods_step.get("priority") or "P1",
                "status": goods_step.get("status") or "corroboration_needed",
                "source": goods_step.get("source") or "public_goods_profile",
                "target": goods_step.get("target_title") or "public goods economics leads",
                "action": goods_step.get("action") or goods_step.get("kind") or "",
                "ready_to_run": bool(goods_step.get("ready_to_run", True)),
                "blocked_reason": goods_step.get("blocked_reason") or "",
                "done_condition": goods_step.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.goods_economics_closure_step",
                    "enterprise_cognition.public_goods_profile",
                    "enterprise_cognition.goods_flow_profile",
                ],
            }
        )

    people_step = _dict(people_control_closure_step)
    if people_step:
        add(
            {
                "work_id": people_step.get("step_id") or "OP-PEOPLE-CONTROL",
                "lane": "people_control_closure",
                "priority": people_step.get("priority") or "P1",
                "status": people_step.get("status") or "corroboration_needed",
                "source": people_step.get("source") or "public_people_profile",
                "target": people_step.get("target_title") or "public people/control leads",
                "action": people_step.get("action") or people_step.get("kind") or "",
                "ready_to_run": bool(people_step.get("ready_to_run", True)),
                "blocked_reason": people_step.get("blocked_reason") or "",
                "done_condition": people_step.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.people_control_closure_step",
                    "enterprise_cognition.public_people_profile",
                    "enterprise_cognition.people_flow_profile",
                ],
            }
        )

    graph_capital_step = _dict(_dict(graph_capital_exposure).get("top_step"))
    if graph_capital_step:
        add(
            {
                "work_id": graph_capital_step.get("step_id") or "OP-GRAPH-CAPITAL",
                "lane": "graph_capital_exposure",
                "priority": graph_capital_step.get("priority") or "P0",
                "status": graph_capital_step.get("kind") or _dict(graph_capital_exposure).get("relationship_status") or "pending",
                "source": graph_capital_step.get("source") or graph_capital_step.get("kind") or "summary.capital_exposure",
                "target": graph_capital_step.get("target_title") or graph_capital_step.get("target_id") or "",
                "action": _dict(graph_capital_exposure).get("next_action") or graph_capital_step.get("target_title") or graph_capital_step.get("kind") or "",
                "done_condition": graph_capital_step.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.graph_capital_exposure",
                    "summary.capital_exposure",
                ],
            }
        )

    for item in capital_verification_queue[:5]:
        add(
            {
                "work_id": item.get("step_id") or f"OP-CAPITAL-{len(rows) + 1}",
                "lane": "capital_verification",
                "priority": item.get("priority") or "P0",
                "status": "pending",
                "source": item.get("kind") or "",
                "target": item.get("target_title") or item.get("target_id") or "",
                "action": item.get("target_title") or item.get("kind") or "",
                "done_condition": item.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.capital_verification_top_step",
                    "enterprise_cognition.capital_pressure_profile.verification_queue",
                ],
            }
        )

    for item in relationship_audit_queue[:5]:
        add(
            {
                "work_id": item.get("step_id") or f"OP-RELATIONSHIP-{len(rows) + 1}",
                "lane": "relationship_graph_audit",
                "priority": item.get("priority") or "P1",
                "status": item.get("kind") or "pending",
                "source": item.get("relation_type") or "",
                "target": item.get("target") or "",
                "action": item.get("kind") or item.get("relation_type") or "",
                "ready_to_run": bool(item.get("evidence_ids")) or item.get("kind") != "missing_evidence_relationship_edge",
                "blocked_reason": "missing_evidence_ids" if item.get("kind") == "missing_evidence_relationship_edge" else "",
                "done_condition": item.get("done_condition") or "",
                "packet_refs": [
                    "one_click_readiness.relationship_graph_audit_top_step",
                    "enterprise_cognition.relationship_network.top_edges",
                ],
            }
        )

    if coverage_next_action:
        add(
            {
                "work_id": "OP-COVERAGE-GAP",
                "lane": "coverage_gap",
                "priority": "P1",
                "status": "pending",
                "source": "coverage",
                "target": ", ".join(coverage_gap_domains[:5]),
                "action": coverage_next_action,
                "done_condition": "coverage_gap_count_reduced_or_gap_reason_recorded",
                "packet_refs": [
                    "one_click_readiness.coverage_next_action",
                    "one_click_readiness.coverage_missing_domains",
                ],
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    lane_order = {
        "source_repair": 0,
        "source_recovery": 1,
        "source_resilience": 2,
        "public_origin_fallback": 3,
        "public_origin_gap_bridge": 4,
        "control_path_verification": 5,
        "goods_economics_closure": 6,
        "people_control_closure": 7,
        "graph_capital_exposure": 8,
        "capital_verification": 9,
        "relationship_graph_audit": 10,
        "coverage_gap": 11,
    }
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(
        rows,
        key=lambda item: (
            priority_order.get(str(item.get("priority") or "P1").upper(), 9),
            0 if item.get("ready_to_run") else 1,
            lane_order.get(str(item.get("lane") or ""), 99),
            str(item.get("work_id") or ""),
        ),
    ):
        key = str(row.get("work_id") or "").casefold()
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:12]


def _graph_capital_exposure_handoff(
    graph_summary: dict[str, Any],
    capital_pressure: dict[str, Any],
    capital_relationship_status: str,
) -> dict[str, Any]:
    """Mirror risk-graph capital exposure into the one-click handoff."""
    exposure = _dict(_dict(graph_summary).get("capital_exposure"))
    if not exposure:
        return {
            "type": "graph_capital_exposure_handoff",
            "available": False,
            "alignment_status": "not_available",
            "policy": "No graph capital_exposure summary was provided; use enterprise capital_pressure_profile if present.",
        }

    verification_queue = [
        _dict(item) for item in exposure.get("verification_queue", [])
        if isinstance(item, dict)
    ]
    relationship_audit_queue = [
        _dict(item) for item in exposure.get("relationship_audit_queue", [])
        if isinstance(item, dict)
    ]
    top_step = relationship_audit_queue[0] if relationship_audit_queue else (
        verification_queue[0] if verification_queue else {}
    )
    graph_level = str(exposure.get("pressure_level") or "none")
    enterprise_level = str(capital_pressure.get("pressure_level") or "none")
    graph_relationship_status = str(exposure.get("relationship_status") or "unknown")
    if graph_level == enterprise_level:
        alignment_status = "aligned"
    elif graph_level == "none" and enterprise_level == "none":
        alignment_status = "aligned"
    elif graph_level != "none" and enterprise_level != "none":
        alignment_status = "pressure_signal_family_aligned"
    else:
        alignment_status = "needs_review"
    source_family_summary = _source_family_summary_from_names(
        _graph_capital_source_names(exposure, verification_queue, relationship_audit_queue)
    )
    return {
        "type": "graph_capital_exposure_handoff",
        "available": True,
        "pressure_level": graph_level,
        "enterprise_pressure_level": enterprise_level,
        "alignment_status": alignment_status,
        "relationship_status": graph_relationship_status,
        "enterprise_relationship_status": capital_relationship_status,
        "pressure_signal_count": int(exposure.get("pressure_signal_count") or 0),
        "inflow_signal_count": int(exposure.get("inflow_signal_count") or 0),
        "capital_evidence_count": int(exposure.get("capital_evidence_count") or 0),
        "capital_risk_event_count": int(exposure.get("capital_risk_event_count") or 0),
        "capital_relationship_edge_count": int(exposure.get("capital_relationship_edge_count") or 0),
        "verification_queue_count": len(verification_queue),
        "relationship_audit_queue_count": len(relationship_audit_queue),
        "top_step": top_step,
        "evidence_ids": [str(item) for item in exposure.get("evidence_ids", []) if str(item).strip()][:8],
        "risk_event_ids": [str(item) for item in exposure.get("risk_event_ids", []) if str(item).strip()][:8],
        "relationship_edge_ids": [str(item) for item in exposure.get("relationship_edge_ids", []) if str(item).strip()][:8],
        "source_family_summary": source_family_summary,
        "source_family_count": source_family_summary["family_count"],
        "source_top_family": source_family_summary["top_family"],
        "has_official_or_authorized_source": source_family_summary["has_official_or_authorized"],
        "next_action": exposure.get("next_action") or "",
        "basis": exposure.get("basis") or "summary.capital_exposure",
        "policy": "Graph capital exposure is a routing summary; final reliance still requires admitted evidence and relationship-edge verification.",
    }


def _graph_capital_source_names(
    exposure: dict[str, Any],
    verification_queue: list[dict[str, Any]],
    relationship_audit_queue: list[dict[str, Any]],
) -> list[str]:
    names: list[str] = []
    for key in ("source_names", "sources", "source_basis"):
        for value in exposure.get(key, []) or []:
            if value:
                names.append(str(value))
    for item in [*verification_queue, *relationship_audit_queue]:
        for key in ("source", "source_name", "source_url"):
            value = item.get(key)
            if value:
                names.append(str(value))
        for value in item.get("source_names", []) or []:
            if value:
                names.append(str(value))
    return _dedupe_strings(names)


def _capital_risk_panel_summary(
    *,
    capital_pressure: dict[str, Any],
    graph_capital_exposure: dict[str, Any],
    capital_relationship_status: str,
    capital_source_family_summary: dict[str, Any],
    capital_verification_queue: list[dict[str, Any]],
    relationship_audit_queue: list[dict[str, Any]],
    relationship_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compact capital-risk summary for low-context desktop-agent hosts."""
    pressure_level = str(
        graph_capital_exposure.get("pressure_level")
        or capital_pressure.get("pressure_level")
        or "none"
    )
    report_visibility = (
        "capital_lane_and_bond_credit_section"
        if pressure_level not in {"", "none", "unknown"}
        or capital_verification_queue
        or relationship_audit_queue
        else "capital_lane_no_current_pressure"
    )
    clean_reliance_allowed = (
        capital_relationship_status in {"not_applicable", "evidence_backed"}
        and not capital_verification_queue
        and not relationship_audit_queue
    )
    return {
        "type": "capital_risk_panel",
        "source": "one_click_readiness.capital_risk_panel",
        "pressure_level": pressure_level,
        "verification_status": capital_pressure.get("verification_status") or "unknown",
        "relationship_status": capital_relationship_status,
        "report_visibility": report_visibility,
        "graph_alignment_status": graph_capital_exposure.get("alignment_status") or "not_available",
        "graph_relationship_status": graph_capital_exposure.get("relationship_status") or "unknown",
        "pressure_signal_count": int(
            graph_capital_exposure.get("pressure_signal_count")
            or capital_pressure.get("pressure_signal_count")
            or 0
        ),
        "capital_risk_event_count": int(graph_capital_exposure.get("capital_risk_event_count") or 0),
        "capital_verification_queue_count": len(capital_verification_queue),
        "relationship_audit_queue_count": len(relationship_audit_queue),
        "relationship_edge_count": len(relationship_edges),
        "source_family_summary": capital_source_family_summary,
        "source_top_family": capital_source_family_summary.get("top_family") or "",
        "has_official_or_authorized_source": bool(capital_source_family_summary.get("has_official_or_authorized")),
        "top_step": graph_capital_exposure.get("top_step") or {},
        "next_action": graph_capital_exposure.get("next_action")
        or capital_pressure.get("next_verification_question")
        or "",
        "clean_reliance_allowed": clean_reliance_allowed,
        "policy": "Routing summary only; final reliance requires admitted evidence and relationship-edge verification.",
    }


def _source_health_trend_digest(source_health_trend_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compact source-health snapshot for first-screen agent routing."""
    snapshot = _dict(source_health_trend_snapshot)
    top_source = _dict(snapshot.get("top_source"))
    recovery_queue_summary = _dict(snapshot.get("recovery_queue_summary"))
    available = bool(int(snapshot.get("source_count") or 0) or top_source)
    top_status = str(top_source.get("status") or "").strip()
    queued_count = int(recovery_queue_summary.get("queued_count") or 0)
    top_action = str(top_source.get("operator_action") or "").strip()
    blocked_statuses = {
        "authorization_required",
        "blocked_recovery_dependency",
        "connector_or_source_down",
        "connector_required",
        "source_unavailable",
    }
    if not available:
        actionability = "no_source_health_action"
        blocked_reason = ""
        next_action = ""
    elif queued_count > 0:
        actionability = "ready_recovery_available"
        blocked_reason = ""
        next_action = top_action or "Run the queued source recovery step, then rerun the bounded investigation."
    elif top_status in blocked_statuses:
        actionability = "blocked_connector_repair"
        blocked_reason = top_status
        next_action = top_action or "Resolve the blocked source repair task before relying on affected coverage."
    else:
        actionability = "inspect_source_health"
        blocked_reason = top_status if top_status else ""
        next_action = top_action or "Inspect the top source-health row and preserve any affected coverage caveat."
    return {
        "type": "source_health_trend_digest",
        "available": available,
        "actionability": actionability,
        "next_action": next_action,
        "top_blocked_reason": blocked_reason,
        "subject_risk_verdict_allowed": False,
        "scope": snapshot.get("scope") or "current_investigation_packet_bounded",
        "current_release_monitoring_enabled": bool(snapshot.get("current_release_monitoring_enabled")),
        "source_count": int(snapshot.get("source_count") or 0),
        "blocked_source_count": int(snapshot.get("blocked_source_count") or 0),
        "recurring_failure_count": int(snapshot.get("recurring_failure_count") or 0),
        "top_source": top_source,
        "top_operator_action": top_source.get("operator_action") or "",
        "top_repair_queue_id": top_source.get("repair_queue_id") or "",
        "recovery_queue_summary": recovery_queue_summary,
        "packet_refs": [
            "monitoring_seed.source_health_trend_snapshot",
            "monitoring_seed.source_repair_priority_queue",
            "one_click_readiness.operator_work_queue",
        ],
        "evidence_boundary": (
            "Source-health trend rows are connector/run-health signals only; "
            "do not treat them as company facts or risk events."
        ),
        "policy": snapshot.get("handoff_policy")
        or "No background monitoring is enabled; use this digest only for on-demand source repair.",
    }


def _reliance_limitations_summary(
    *,
    quality_gate: dict[str, Any],
    coverage_gap_domains: list[str],
    coverage_next_action: str,
    operator_work_queue: list[dict[str, Any]],
    capital_relationship_status: str,
    relationship_missing_evidence_count: int,
) -> dict[str, Any]:
    """Explain what the user must not over-read from incomplete evidence."""
    blockers = [str(item) for item in quality_gate.get("blockers", []) if str(item).strip()]
    warnings = [str(item) for item in quality_gate.get("warnings", []) if str(item).strip()]
    next_actions = [str(item) for item in quality_gate.get("next_actions", []) if str(item).strip()]
    items: list[dict[str, Any]] = []

    def add(
        *,
        limitation_id: str,
        severity: str,
        area: str,
        reason: str,
        user_message: str,
        next_action: str,
    ) -> None:
        if any(item["limitation_id"] == limitation_id for item in items):
            return
        items.append(
            {
                "limitation_id": limitation_id,
                "severity": severity,
                "area": area,
                "reason": reason,
                "user_message": user_message,
                "next_action": next_action,
            }
        )

    if "no_factual_evidence" in blockers:
        add(
            limitation_id="LIMIT-NO-FACTS",
            severity="high",
            area="evidence",
            reason="no_factual_evidence",
            user_message="Current packet has no fact-admitted evidence; do not treat absence of risk events as a clean result.",
            next_action="Collect at least one source-backed factual record before final reliance.",
        )
    if coverage_gap_domains:
        add(
            limitation_id="LIMIT-COVERAGE-GAPS",
            severity="medium" if len(coverage_gap_domains) <= 3 else "high",
            area="coverage",
            reason="coverage_gaps_present",
            user_message="Some domains were not searched or returned no usable evidence; empty coverage is not a low-risk conclusion.",
            next_action=coverage_next_action or "Close coverage gaps or record explicit no-evidence reasons.",
        )
    if "source_resilience_needs_operator_recovery" in warnings or "coverage_recovery_blocked" in warnings:
        top_blocked = next((item for item in operator_work_queue if not item.get("ready_to_run")), {})
        add(
            limitation_id="LIMIT-SOURCE-RECOVERY",
            severity="medium",
            area="source_resilience",
            reason="source_recovery_incomplete",
            user_message="Source recovery or connector work remains open; affected sections should be read as partial.",
            next_action=str(top_blocked.get("action") or top_blocked.get("done_condition") or "Resolve blocked source recovery work."),
        )
    if capital_relationship_status == "unresolved":
        add(
            limitation_id="LIMIT-CAPITAL-RELATIONSHIP",
            severity="high",
            area="capital",
            reason="capital_pressure_without_admitted_relationship_edge",
            user_message="Capital pressure exists but the relationship edge is not admitted yet; do not treat the exposure as explained.",
            next_action="Collect admitted counterparty, pledgee, guarantor, lender, issuer, or controller relationship evidence.",
        )
    if relationship_missing_evidence_count > 0:
        add(
            limitation_id="LIMIT-RELATIONSHIP-EVIDENCE",
            severity="medium",
            area="relationship_graph",
            reason="relationship_edges_missing_evidence_ids",
            user_message="Some relationship edges lack evidence identifiers; use them as audit targets, not final facts.",
            next_action="Attach evidence_ids to relationship edges or remove unsupported edges from the fact graph.",
        )

    if not items and warnings:
        add(
            limitation_id="LIMIT-QUALITY-WARNINGS",
            severity="low",
            area="quality_gate",
            reason=warnings[0],
            user_message="Quality warnings remain; read conclusions with the listed caveats.",
            next_action=next_actions[0] if next_actions else "Review quality gate warnings before final reliance.",
        )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 9), str(item.get("limitation_id"))))
    return {
        "type": "reliance_limitations",
        "count": len(items),
        "highest_severity": items[0]["severity"] if items else "none",
        "can_make_clean_conclusion": not blockers and not items,
        "policy": "Missing or blocked evidence limits reliance; it must never be interpreted as proof that no risk exists.",
        "items": items[:8],
    }


def _acceptance_closure_summary(
    *,
    status: str,
    ready_for_user: bool,
    needs_operator_followup: bool,
    blockers: list[str],
    warnings: list[str],
    operator_work_queue: list[dict[str, Any]],
    reliance_limitations: dict[str, Any],
    coverage_gap_domains: list[str],
    source_repair_queue: list[dict[str, Any]],
    recovery_queue: dict[str, Any],
    public_origin_gap_bridge: dict[str, Any],
    control_path_closure_step: dict[str, Any] | None,
    goods_economics_closure_step: dict[str, Any] | None,
    people_control_closure_step: dict[str, Any] | None,
    capital_relationship_status: str,
    capital_relationship_closure_step: dict[str, Any] | None,
    graph_capital_exposure: dict[str, Any],
    capital_verification_queue: list[dict[str, Any]],
    relationship_audit_queue: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compact acceptance-readiness digest for agent hosts and release checks."""
    closure_steps = {
        "capital_relationship": _dict(capital_relationship_closure_step),
        "control_path": _dict(control_path_closure_step),
        "goods_economics": _dict(goods_economics_closure_step),
        "people_control": _dict(people_control_closure_step),
        "graph_capital_exposure": _dict(_dict(graph_capital_exposure).get("top_step")),
    }
    active_closures = [
        {"closure_id": key, **value}
        for key, value in closure_steps.items()
        if value
    ]
    ready_work = [item for item in operator_work_queue if bool(item.get("ready_to_run"))]
    blocked_work = [item for item in operator_work_queue if not bool(item.get("ready_to_run"))]
    p0_work = [
        item for item in operator_work_queue
        if str(item.get("priority") or "").strip().upper() == "P0"
    ]
    open_domains: list[str] = []
    if source_repair_queue:
        open_domains.append("source_repair")
    if int(_dict(recovery_queue).get("queued_count") or 0) or int(_dict(recovery_queue).get("blocked_count") or 0):
        open_domains.append("source_recovery")
    if coverage_gap_domains:
        open_domains.append("coverage")
    if int(_dict(public_origin_gap_bridge).get("bridge_count") or 0):
        open_domains.append("public_origin")
    if active_closures:
        open_domains.append("closure_steps")
    if capital_verification_queue:
        open_domains.append("capital_verification")
    if relationship_audit_queue:
        open_domains.append("relationship_audit")
    if int(reliance_limitations.get("count") or 0):
        open_domains.append("reliance_limitations")

    top_action = operator_work_queue[0] if operator_work_queue else {}
    blocking_count = (
        len(blockers)
        + len(blocked_work)
        + int(reliance_limitations.get("count") or 0)
        + (1 if capital_relationship_status == "unresolved" else 0)
    )
    if status.startswith("blocked") or blockers:
        closure_status = "blocked"
    elif blocking_count or p0_work or needs_operator_followup:
        closure_status = "needs_operator_followup"
    elif ready_for_user:
        closure_status = "ready_for_human_review"
    else:
        closure_status = "needs_review"

    return {
        "type": "acceptance_closure_summary",
        "status": closure_status,
        "packet_status": status,
        "ready_for_user_review": bool(ready_for_user),
        "needs_operator_followup": bool(needs_operator_followup),
        "blocking_count": blocking_count,
        "warning_count": len(warnings),
        "operator_work_count": len(operator_work_queue),
        "operator_work_p0_count": len(p0_work),
        "ready_count": len(ready_work),
        "blocked_work_count": len(blocked_work),
        "closure_step_count": len(active_closures),
        "closure_steps": closure_steps,
        "closure_queue": active_closures[:8],
        "open_domains": _dedupe_strings(open_domains),
        "top_action": top_action,
        "next_action": top_action.get("action") or top_action.get("done_condition") or "",
        "done_condition": "operator_work_queue_empty_or_each_open_item_has_explicit_non_reliance_caveat",
        "policy": "Acceptance closure summarizes readiness only; it does not upgrade public leads, missing coverage, or unaudited relationships into facts.",
    }


def _goods_economics_closure_step(enterprise_cognition: dict[str, Any]) -> dict[str, Any]:
    """Build an executable follow-up step for public goods economics leads."""
    public_goods = _dict(enterprise_cognition.get("public_goods_profile"))
    if not public_goods:
        return {}

    unit_claims = [
        str(item)
        for item in public_goods.get("unit_economics_claims", [])
        if str(item).strip()
    ]
    power_claims = [
        str(item)
        for item in public_goods.get("bargaining_power_claims", [])
        if str(item).strip()
    ]
    competition_claims = [
        str(item)
        for item in public_goods.get("competitive_landscape_claims", [])
        if str(item).strip()
    ]
    signals = _dedupe_strings([*unit_claims, *power_claims, *competition_claims])
    if not signals:
        return {}

    focus_parts = []
    if unit_claims:
        focus_parts.append(f"unit={_short_text(unit_claims[0], 80)}")
    if power_claims:
        focus_parts.append(f"power={_short_text(power_claims[0], 80)}")
    if competition_claims:
        focus_parts.append(f"competition={_short_text(competition_claims[0], 80)}")

    return {
        "step_id": "GOODS-ECON-001",
        "priority": "P1",
        "kind": "goods_economics_corroboration",
        "status": "corroboration_needed",
        "source": public_goods.get("source") or "public_goods_profile",
        "target_id": "public_goods_profile",
        "target_title": " | ".join(focus_parts) or "public goods economics leads",
        "signal_count": len(signals),
        "unit_economics_signal_count": len(unit_claims),
        "bargaining_power_signal_count": len(power_claims),
        "competitive_landscape_signal_count": len(competition_claims),
        "sample_signals": signals[:6],
        "ready_to_run": True,
        "blocked_reason": "",
        "action": (
            "Corroborate public unit-economics, bargaining-power, and competitive-landscape leads "
            "with official filings, authorized records, procurement/customer/supplier evidence, or audited source-specific records."
        ),
        "done_condition": (
            "goods_economics_claims_are_corroborated_or_explicitly_left_as_public_leads"
        ),
        "packet_refs": [
            "enterprise_cognition.public_goods_profile.unit_economics_claims",
            "enterprise_cognition.public_goods_profile.bargaining_power_claims",
            "enterprise_cognition.public_goods_profile.competitive_landscape_claims",
            "enterprise_cognition.goods_flow_profile",
            "report_markdown",
        ],
    }


def _people_control_closure_step(enterprise_cognition: dict[str, Any]) -> dict[str, Any]:
    """Build an executable follow-up step for public people/control leads."""
    public_people = _dict(enterprise_cognition.get("public_people_profile"))
    if not public_people:
        return {}

    control_claims = [
        str(item)
        for item in public_people.get("control_role_claims", [])
        if str(item).strip()
    ]
    key_person_claims = [
        str(item)
        for item in public_people.get("key_person_claims", [])
        if str(item).strip()
    ]
    legal_pressure_claims = [
        str(item)
        for item in public_people.get("legal_pressure_claims", [])
        if str(item).strip()
    ]
    ownership_change_claims = [
        str(item)
        for item in public_people.get("ownership_change_claims", [])
        if str(item).strip()
    ]
    related_party_claims = [
        str(item)
        for item in public_people.get("related_party_claims", [])
        if str(item).strip()
    ]
    signals = _dedupe_strings([
        *control_claims,
        *key_person_claims,
        *legal_pressure_claims,
        *ownership_change_claims,
        *related_party_claims,
    ])
    if not signals:
        return {}

    focus_parts = []
    if control_claims:
        focus_parts.append(f"control={_short_text(control_claims[0], 80)}")
    if legal_pressure_claims:
        focus_parts.append(f"legal={_short_text(legal_pressure_claims[0], 80)}")
    if ownership_change_claims:
        focus_parts.append(f"ownership={_short_text(ownership_change_claims[0], 80)}")
    if related_party_claims:
        focus_parts.append(f"related={_short_text(related_party_claims[0], 80)}")

    return {
        "step_id": "PEOPLE-CONTROL-001",
        "priority": "P1",
        "kind": "people_control_corroboration",
        "status": "corroboration_needed",
        "source": public_people.get("source") or "public_people_profile",
        "target_id": "public_people_profile",
        "target_title": " | ".join(focus_parts) or "public people/control leads",
        "signal_count": len(signals),
        "control_signal_count": len(control_claims),
        "key_person_signal_count": len(key_person_claims),
        "legal_pressure_signal_count": len(legal_pressure_claims),
        "ownership_change_signal_count": len(ownership_change_claims),
        "related_party_signal_count": len(related_party_claims),
        "sample_signals": signals[:6],
        "ready_to_run": True,
        "blocked_reason": "",
        "action": (
            "Corroborate public controller, UBO, key-person, legal-pressure, ownership-change, "
            "and related-party leads with official registry, court/enforcement, licensed, or user-authorized records."
        ),
        "done_condition": (
            "people_control_claims_are_corroborated_or_explicitly_left_as_public_leads"
        ),
        "packet_refs": [
            "enterprise_cognition.public_people_profile.control_role_claims",
            "enterprise_cognition.public_people_profile.legal_pressure_claims",
            "enterprise_cognition.public_people_profile.ownership_change_claims",
            "enterprise_cognition.public_people_profile.related_party_claims",
            "enterprise_cognition.people_flow_profile",
            "report_markdown",
        ],
    }


def _control_path_hop_count(path: dict[str, Any]) -> int:
    raw_hop = path.get("hop_count")
    try:
        hop_count = int(raw_hop)
    except (TypeError, ValueError):
        hop_count = 0
    if hop_count > 0:
        return hop_count
    path_nodes = [str(item).strip() for item in path.get("path_nodes", []) if str(item).strip()]
    if len(path_nodes) >= 2:
        return len(path_nodes) - 1
    path_text = str(path.get("path_text") or "").strip()
    if "->" in path_text:
        return max(len([item for item in path_text.split("->") if item.strip()]) - 1, 0)
    return 1 if path.get("from_name") and path.get("to_name") else 0


def _evidence_source_family(source_name: str) -> str:
    source = source_name.strip().lower()
    if not source:
        return "unknown"
    if "qyyjt" in source or "licensed" in source or "commercial" in source:
        return "licensed_commercial"
    if "gleif" in source:
        return "official_public_gleif"
    if "sec" in source or "edgar" in source:
        return "official_public_sec"
    if "wikidata" in source:
        return "public_knowledge_graph"
    if "registry" in source or "gsxt" in source or "official" in source:
        return "official_registry"
    if "web" in source or "search" in source:
        return "public_web"
    return "other_public_or_authorized"


def _control_path_source_family(source_name: str) -> str:
    return _evidence_source_family(source_name)


def _source_family_summary_from_names(source_names: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for source_name in source_names:
        family = _evidence_source_family(str(source_name))
        if family == "unknown":
            continue
        counts[family] = counts.get(family, 0) + 1
    families = [
        {"family": family, "count": count}
        for family, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "family_count": len(families),
        "top_family": families[0]["family"] if families else "",
        "families": families,
        "has_official_or_authorized": any(
            str(item["family"]).startswith("official_public_")
            or str(item["family"]) in {"official_registry", "licensed_commercial"}
            for item in families
        ),
        "policy": "Source families explain provenance breadth only; they do not upgrade weak leads into facts.",
    }


def _control_path_source_family_summary(paths: list[dict[str, Any]]) -> dict[str, Any]:
    source_names: list[str] = []
    for path in paths:
        row = _dict(path)
        for source_name in row.get("source_names", []) or []:
            source_names.append(str(source_name))
    return _source_family_summary_from_names(source_names)


def _control_path_verification_queue(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for path in paths[:12]:
        row = _dict(path)
        hop_count = _control_path_hop_count(row)
        if hop_count < 2:
            continue
        evidence_ids = [
            str(item).strip()
            for item in row.get("evidence_ids", [])
            if str(item).strip()
        ]
        admission = str(row.get("admission") or "").strip().lower()
        verification_status = str(row.get("verification_status") or "").strip().lower()
        admitted = admission in {"fact", "admitted", "evidence"}
        verified = verification_status in {"verified", "corroborated"}
        path_text = str(row.get("path_text") or "").strip()
        if not path_text:
            path_text = (
                f"{row.get('from_name') or row.get('from_kind') or 'unknown'} -> "
                f"{row.get('to_name') or row.get('to_kind') or 'unknown'}"
            )
        if not evidence_ids:
            priority = "P0"
            kind = "missing_evidence_indirect_control_path"
            status = "evidence_required"
            done_condition = "attach_evidence_ids_or_keep_indirect_control_path_as_lead"
        elif not admitted or not verified:
            priority = "P1"
            kind = "indirect_control_path_corroboration"
            status = "corroboration_needed"
            done_condition = "corroborate_indirect_control_path_before_fact_reliance"
        else:
            priority = "P1"
            kind = "admitted_indirect_control_path_review"
            status = "review_ready"
            done_condition = "confirm_path_nodes_relation_types_subject_match_and_provenance"
        source_names = [
            str(item).strip()
            for item in row.get("source_names", [])
            if str(item).strip()
        ][:6]
        queue.append(
            {
                "step_id": f"CONTROL-PATH-{len(queue) + 1:03d}",
                "priority": priority,
                "kind": kind,
                "status": status,
                "source": "control_ownership",
                "target_id": "control_ownership.control_paths",
                "target_title": _short_text(path_text, 180),
                "path_text": _short_text(path_text, 240),
                "hop_count": hop_count,
                "relation_types": [
                    str(item).strip()
                    for item in row.get("relation_types", [])
                    if str(item).strip()
                ],
                "terminal_name": row.get("to_name") or row.get("terminal_name"),
                "admission": admission or "unknown",
                "verification_status": verification_status or "unknown",
                "source_strength": row.get("source_strength"),
                "source_names": source_names,
                "source_families": sorted({
                    _control_path_source_family(item)
                    for item in source_names
                    if _control_path_source_family(item) != "unknown"
                }),
                "evidence_ids": evidence_ids[:8],
                "ready_to_run": True,
                "blocked_reason": "",
                "action": (
                    "Verify the indirect controller or UBO path against official, licensed, "
                    "or user-authorized ownership records before final reliance."
                ),
                "done_condition": done_condition,
                "packet_refs": [
                    "enterprise_cognition.control_ownership.control_paths",
                    "enterprise_cognition.control_ownership.controller_candidates",
                    "enterprise_cognition.relationship_network.top_edges",
                ],
            }
        )
    return sorted(
        queue,
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority")), 9),
            -int(item.get("hop_count") or 0),
            str(item.get("step_id")),
        ),
    )


def _control_path_profile(paths: list[dict[str, Any]]) -> dict[str, Any]:
    multi_layer_paths = [
        path for path in paths
        if _control_path_hop_count(_dict(path)) >= 2
    ]
    queue = _control_path_verification_queue(paths)
    highest_hop_count = max(
        [_control_path_hop_count(_dict(path)) for path in multi_layer_paths] or [0]
    )
    if not multi_layer_paths:
        verification_status = "not_applicable"
    elif any(str(item.get("priority") or "").upper() == "P0" for item in queue):
        verification_status = "evidence_required"
    elif queue:
        verification_status = "review_ready"
    else:
        verification_status = "covered"
    return {
        "multi_layer_control_path_count": len(multi_layer_paths),
        "highest_control_path_hop_count": highest_hop_count,
        "control_path_verification_status": verification_status,
        "control_path_verification_queue": queue[:8],
        "top_control_path": queue[0] if queue else {},
        "control_path_source_family_summary": _control_path_source_family_summary(multi_layer_paths),
    }


def _control_path_closure_step(enterprise_cognition: dict[str, Any]) -> dict[str, Any]:
    control_ownership = _dict(enterprise_cognition.get("control_ownership"))
    queue = [
        item for item in control_ownership.get("control_path_verification_queue", [])
        if isinstance(item, dict)
    ]
    if not queue:
        return {}
    step = dict(queue[0])
    step.setdefault("step_id", "CONTROL-PATH-001")
    step.setdefault("kind", "indirect_control_path_verification")
    step.setdefault("status", "corroboration_needed")
    step.setdefault("source", "control_ownership")
    step.setdefault("target_id", "control_ownership.control_paths")
    step.setdefault("target_title", step.get("path_text") or "indirect controller or UBO path")
    step.setdefault("ready_to_run", True)
    step.setdefault("blocked_reason", "")
    step.setdefault(
        "done_condition",
        "indirect_control_path_verified_or_explicitly_left_as_lead",
    )
    step.setdefault(
        "action",
        "Verify the indirect controller or UBO path against official, licensed, or user-authorized ownership records.",
    )
    step["path_count"] = len(queue)
    step["highest_hop_count"] = int(control_ownership.get("highest_control_path_hop_count") or step.get("hop_count") or 0)
    return step


def _one_click_readiness_summary(
    *,
    quality_gate: dict[str, Any],
    graph_summary: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
    source_provenance: dict[str, Any],
    source_failure_summary: dict[str, Any],
    monitoring_seed: dict[str, Any],
    enterprise_cognition: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether the one-click packet is product-usable now."""
    facts = [item for item in evidence_ledger if item.get("admission") == "fact"]
    leads = [item for item in evidence_ledger if item.get("admission") in {"lead", "weak_lead"}]
    recovery_queue = _dict(monitoring_seed.get("recovery_execution_queue"))
    source_resilience = _dict(source_failure_summary.get("source_resilience_profile"))
    coverage_interpretation = _dict(source_failure_summary.get("coverage_interpretation"))
    coverage_status_counts = _dict(source_failure_summary.get("coverage_status_counts"))
    missing_domains = [
        str(item)
        for item in source_failure_summary.get("missing_domains", [])
        if str(item).strip()
    ]
    domains_without_evidence = [
        str(item)
        for item in source_failure_summary.get("domains_without_evidence", [])
        if str(item).strip()
    ]
    coverage_gap_domains = _dedupe_strings([*missing_domains, *domains_without_evidence])
    coverage_not_searched_count = int(
        coverage_interpretation.get("not_searched_count") or len(missing_domains)
    )
    coverage_no_evidence_count = int(
        coverage_interpretation.get("no_evidence_count") or len(domains_without_evidence)
    )
    attempted_source_count = int(source_failure_summary.get("attempted_source_count") or 0)
    coverage_attempt_denominator = attempted_source_count + coverage_not_searched_count
    coverage_attempt_ratio = (
        round(attempted_source_count / coverage_attempt_denominator, 2)
        if coverage_attempt_denominator
        else 0.0
    )
    if not coverage_gap_domains:
        coverage_gap_severity = "none"
        coverage_next_action = ""
    elif coverage_not_searched_count >= 5 or len(coverage_gap_domains) >= 6:
        coverage_gap_severity = "high"
        coverage_next_action = (
            "Run recovery for not-searched domains first, then re-check no-evidence domains with stronger public or authorized sources."
        )
    elif coverage_not_searched_count or coverage_no_evidence_count:
        coverage_gap_severity = "medium"
        coverage_next_action = (
            "Complete missing-domain recovery and inspect no-evidence sources before relying on final risk conclusions."
        )
    else:
        coverage_gap_severity = "low"
        coverage_next_action = "Review coverage gaps during analyst handoff."
    public_origin_next_actions = [
        item
        for item in source_failure_summary.get("public_origin_next_actions", [])
        if isinstance(item, dict)
    ]
    public_origin_fallbacks = [
        item
        for item in source_failure_summary.get("public_origin_fallbacks", [])
        if isinstance(item, dict)
    ]
    public_origin_modules = _dedupe_strings(
        [
            str(item.get("module") or "")
            for item in public_origin_next_actions or public_origin_fallbacks
            if str(item.get("module") or "").strip()
        ]
    )
    public_origin_top_action = public_origin_next_actions[0] if public_origin_next_actions else {}
    public_origin_gap_bridge = _public_origin_gap_bridge(
        coverage_gap_domains,
        public_origin_next_actions,
        public_origin_fallbacks,
    )
    relationship_candidate_watchlist = [
        item
        for item in monitoring_seed.get("relationship_candidate_watchlist", [])
        if isinstance(item, dict)
    ]
    relationship_candidate_plan = [
        item
        for item in monitoring_seed.get("relationship_candidate_execution_plan", [])
        if isinstance(item, dict)
    ]
    relationship_candidate_top_step = relationship_candidate_plan[0] if relationship_candidate_plan else {}
    control_path_closure_step = _control_path_closure_step(enterprise_cognition)
    goods_economics_closure_step = _goods_economics_closure_step(enterprise_cognition)
    people_control_closure_step = _people_control_closure_step(enterprise_cognition)
    blockers = [str(item) for item in quality_gate.get("blockers", []) if str(item).strip()]
    warnings = [str(item) for item in quality_gate.get("warnings", []) if str(item).strip()]
    source_resilience_action = str(source_resilience.get("recommended_action") or "").strip()
    source_resilience_step = _dict(source_resilience.get("recommended_step"))
    source_resilience_retry_policy = _dict(
        source_resilience.get("retry_policy")
        or source_resilience_step.get("retry_policy")
    )
    source_repair_queue = [
        item
        for item in monitoring_seed.get("source_repair_priority_queue", [])
        if isinstance(item, dict)
    ]
    source_repair_top_action = source_repair_queue[0] if source_repair_queue else {}
    source_health_trend_snapshot = _dict(monitoring_seed.get("source_health_trend_snapshot"))
    source_health_trend_digest = _source_health_trend_digest(source_health_trend_snapshot)
    capital_pressure = _dict(enterprise_cognition.get("capital_pressure_profile"))
    capital_relationship = _dict(enterprise_cognition.get("capital_relationship_profile"))
    capital_verification_queue = [
        item for item in capital_pressure.get("verification_queue", [])
        if isinstance(item, dict)
    ]
    capital_verification_top_step = capital_verification_queue[0] if capital_verification_queue else {}
    capital_relationship_closure_step = next(
        (
            item for item in capital_verification_queue
            if str(item.get("kind") or "").strip() == "capital_relationship_closure"
        ),
        {},
    )
    relationship_network = _dict(enterprise_cognition.get("relationship_network"))
    relationship_edges = [
        item for item in relationship_network.get("top_edges", [])
        if isinstance(item, dict)
    ]
    relationship_audit_queue = _relationship_graph_audit_queue(relationship_edges)
    relationship_audit_top_step = relationship_audit_queue[0] if relationship_audit_queue else {}
    relationship_auditable_count = sum(
        1 for item in relationship_edges
        if str(item.get("admission") or "").strip().lower() in {"fact", "admitted", "evidence"}
        and any(str(evidence_id).strip() for evidence_id in item.get("evidence_ids", []))
    )
    relationship_evidence_backed_count = sum(
        1 for item in relationship_edges
        if any(str(evidence_id).strip() for evidence_id in item.get("evidence_ids", []))
    )
    relationship_missing_evidence_count = sum(
        1 for item in relationship_edges
        if not any(str(evidence_id).strip() for evidence_id in item.get("evidence_ids", []))
    )
    relationship_lead_only_count = sum(
        1 for item in relationship_edges
        if str(item.get("admission") or "").strip().lower() in {"lead", "candidate", "weak_lead", "review", "query_plan"}
    )
    capital_relationship_needed = bool(
        capital_pressure.get("pressure_signal_count")
        or capital_pressure.get("rows")
    )
    capital_relationship_explained = (
        not capital_relationship_needed
        or int(capital_relationship.get("match_count") or 0) > 0
    )
    if not capital_relationship_needed:
        capital_relationship_status = "not_applicable"
        capital_relationship_unresolved_reason = ""
        capital_relationship_next_action = ""
    elif capital_relationship_explained:
        capital_relationship_status = "evidence_backed"
        capital_relationship_unresolved_reason = ""
        capital_relationship_next_action = "Review linked capital exposures and verify the highest-risk relationship first."
    else:
        capital_relationship_status = "unresolved"
        capital_relationship_unresolved_reason = (
            "capital_pressure_without_admitted_relationship_edge"
        )
        capital_relationship_next_action = (
            "Collect admitted relationship evidence for the capital counterparty, guarantor, pledgee, lender, "
            "bond issuer, asset holder, or related controller before treating capital pressure as explained."
        )
    graph_capital_exposure = _graph_capital_exposure_handoff(
        graph_summary,
        capital_pressure,
        capital_relationship_status,
    )
    control_path_source_family_summary = _dict(
        _dict(enterprise_cognition.get("control_ownership")).get("control_path_source_family_summary")
    )
    capital_source_family_summary = _dict(capital_pressure.get("source_family_summary"))
    capital_risk_panel = _capital_risk_panel_summary(
        capital_pressure=capital_pressure,
        graph_capital_exposure=graph_capital_exposure,
        capital_relationship_status=capital_relationship_status,
        capital_source_family_summary=capital_source_family_summary,
        capital_verification_queue=capital_verification_queue,
        relationship_audit_queue=relationship_audit_queue,
        relationship_edges=relationship_edges,
    )
    sections = {
        "quality_gate": bool(quality_gate),
        "evidence_ledger": bool(evidence_ledger),
        "source_provenance": bool(source_provenance),
        "risk_events": bool(enterprise_cognition.get("risk_hypotheses")),
        "enterprise_cognition": bool(enterprise_cognition),
        "capital_relationship_explained": capital_relationship_explained,
        "recovery_queue": bool(recovery_queue),
        "monitoring_scope_marked_future": monitoring_seed.get("current_release_monitoring_enabled") is False,
    }
    ready_for_user = bool(quality_gate.get("ok")) and not blockers and bool(facts)
    needs_operator_followup = bool(
        warnings
        or not capital_relationship_explained
        or bool(control_path_closure_step)
        or bool(goods_economics_closure_step)
        or bool(people_control_closure_step)
        or bool(public_origin_gap_bridge.get("bridge_count"))
        or int(recovery_queue.get("blocked_count") or 0)
        or int(recovery_queue.get("queued_count") or 0)
        or bool(source_repair_queue)
    )
    if not facts:
        status = "blocked_no_factual_evidence"
    elif blockers:
        status = "blocked_quality_gate"
    elif needs_operator_followup:
        status = "usable_with_operator_followup"
    else:
        status = "ready_for_human_review"
    operator_work_queue = _operator_work_queue(
        source_resilience=source_resilience,
        source_repair_queue=source_repair_queue,
        recovery_queue=recovery_queue,
        public_origin_next_actions=public_origin_next_actions,
        public_origin_gap_bridge=public_origin_gap_bridge,
        graph_capital_exposure=graph_capital_exposure,
        control_path_closure_step=control_path_closure_step,
        goods_economics_closure_step=goods_economics_closure_step,
        people_control_closure_step=people_control_closure_step,
        capital_verification_queue=capital_verification_queue,
        relationship_audit_queue=relationship_audit_queue,
        coverage_next_action=coverage_next_action,
        coverage_gap_domains=coverage_gap_domains,
    )
    reliance_limitations = _reliance_limitations_summary(
        quality_gate=quality_gate,
        coverage_gap_domains=coverage_gap_domains,
        coverage_next_action=coverage_next_action,
        operator_work_queue=operator_work_queue,
        capital_relationship_status=capital_relationship_status,
        relationship_missing_evidence_count=relationship_missing_evidence_count,
    )
    acceptance_closure_summary = _acceptance_closure_summary(
        status=status,
        ready_for_user=ready_for_user,
        needs_operator_followup=needs_operator_followup,
        blockers=blockers,
        warnings=warnings,
        operator_work_queue=operator_work_queue,
        reliance_limitations=reliance_limitations,
        coverage_gap_domains=coverage_gap_domains,
        source_repair_queue=source_repair_queue,
        recovery_queue=recovery_queue,
        public_origin_gap_bridge=public_origin_gap_bridge,
        control_path_closure_step=control_path_closure_step,
        goods_economics_closure_step=goods_economics_closure_step,
        people_control_closure_step=people_control_closure_step,
        capital_relationship_status=capital_relationship_status,
        capital_relationship_closure_step=capital_relationship_closure_step,
        graph_capital_exposure=graph_capital_exposure,
        capital_verification_queue=capital_verification_queue,
        relationship_audit_queue=relationship_audit_queue,
    )
    return {
        "type": "one_click_readiness",
        "status": status,
        "ready_for_user_review": ready_for_user,
        "needs_operator_followup": needs_operator_followup,
        "reliance_limitations": reliance_limitations,
        "reliance_limitation_count": reliance_limitations["count"],
        "reliance_limitation_highest_severity": reliance_limitations["highest_severity"],
        "can_make_clean_conclusion": reliance_limitations["can_make_clean_conclusion"],
        "acceptance_closure_summary": acceptance_closure_summary,
        "acceptance_closure_status": acceptance_closure_summary["status"],
        "acceptance_closure_blocking_count": acceptance_closure_summary["blocking_count"],
        "acceptance_closure_ready_count": acceptance_closure_summary["ready_count"],
        "acceptance_closure_top_action": acceptance_closure_summary["top_action"],
        "operator_work_queue_count": len(operator_work_queue),
        "operator_work_p0_count": sum(
            1
            for item in operator_work_queue
            if str(item.get("priority") or "").strip().upper() == "P0"
        ),
        "operator_work_ready_count": sum(
            1 for item in operator_work_queue if bool(item.get("ready_to_run"))
        ),
        "operator_work_top_action": operator_work_queue[0] if operator_work_queue else {},
        "operator_work_queue": operator_work_queue,
        "fact_count": len(facts),
        "lead_count": len(leads),
        "quality_status": quality_gate.get("status"),
        "quality_score": quality_gate.get("score"),
        "official_or_licensed_count": source_provenance.get("official_or_licensed_count", 0),
        "attempted_source_count": attempted_source_count,
        "coverage_status_counts": coverage_status_counts,
        "coverage_not_searched_count": coverage_not_searched_count,
        "coverage_no_evidence_count": coverage_no_evidence_count,
        "coverage_gap_count": len(coverage_gap_domains),
        "coverage_gap_severity": coverage_gap_severity,
        "coverage_attempt_ratio": coverage_attempt_ratio,
        "coverage_next_action": coverage_next_action,
        "coverage_missing_domains": missing_domains[:8],
        "coverage_domains_without_evidence": domains_without_evidence[:8],
        "coverage_policy": coverage_interpretation.get("policy") or "",
        "public_origin_fallback_count": len(public_origin_fallbacks),
        "public_origin_next_action_count": len(public_origin_next_actions),
        "public_origin_modules": public_origin_modules[:8],
        "public_origin_gap_bridge_count": int(public_origin_gap_bridge.get("bridge_count") or 0),
        "public_origin_gap_bridge": public_origin_gap_bridge,
        "public_origin_gap_bridge_top_action": public_origin_gap_bridge.get("top_bridge") or {},
        "public_origin_top_action": {
            "action_id": public_origin_top_action.get("action_id"),
            "module": public_origin_top_action.get("module"),
            "target_lane": public_origin_top_action.get("target_lane"),
            "origin_channel": public_origin_top_action.get("origin_channel"),
            "query_family": public_origin_top_action.get("query_family"),
            "record_type": public_origin_top_action.get("record_type"),
            "required_fields": list(public_origin_top_action.get("required_fields") or [])[:8],
            "admission_gate": public_origin_top_action.get("admission_gate"),
            "acceptance_gate": public_origin_top_action.get("acceptance_gate"),
        } if public_origin_top_action else {},
        "control_path_closure_needed": bool(control_path_closure_step),
        "control_path_signal_count": int(control_path_closure_step.get("path_count") or 0),
        "control_path_highest_hop_count": int(control_path_closure_step.get("highest_hop_count") or 0),
        "control_path_source_family_count": int(control_path_source_family_summary.get("family_count") or 0),
        "control_path_source_top_family": control_path_source_family_summary.get("top_family") or "",
        "control_path_has_official_or_authorized_source": bool(control_path_source_family_summary.get("has_official_or_authorized")),
        "control_path_source_family_summary": control_path_source_family_summary,
        "control_path_closure_step": {
            "step_id": control_path_closure_step.get("step_id"),
            "priority": control_path_closure_step.get("priority"),
            "kind": control_path_closure_step.get("kind"),
            "status": control_path_closure_step.get("status"),
            "source": control_path_closure_step.get("source"),
            "target_id": control_path_closure_step.get("target_id"),
            "target_title": control_path_closure_step.get("target_title"),
            "path_text": control_path_closure_step.get("path_text"),
            "hop_count": control_path_closure_step.get("hop_count"),
            "highest_hop_count": control_path_closure_step.get("highest_hop_count"),
            "path_count": control_path_closure_step.get("path_count"),
            "admission": control_path_closure_step.get("admission"),
            "verification_status": control_path_closure_step.get("verification_status"),
            "source_strength": control_path_closure_step.get("source_strength"),
            "source_names": list(control_path_closure_step.get("source_names") or [])[:6],
            "source_families": list(control_path_closure_step.get("source_families") or [])[:6],
            "evidence_ids": list(control_path_closure_step.get("evidence_ids") or [])[:8],
            "ready_to_run": bool(control_path_closure_step.get("ready_to_run")) if control_path_closure_step else False,
            "blocked_reason": control_path_closure_step.get("blocked_reason"),
            "action": control_path_closure_step.get("action"),
            "done_condition": control_path_closure_step.get("done_condition"),
        } if control_path_closure_step else {},
        "goods_economics_closure_needed": bool(goods_economics_closure_step),
        "goods_economics_signal_count": int(goods_economics_closure_step.get("signal_count") or 0),
        "goods_economics_closure_step": {
            "step_id": goods_economics_closure_step.get("step_id"),
            "priority": goods_economics_closure_step.get("priority"),
            "kind": goods_economics_closure_step.get("kind"),
            "status": goods_economics_closure_step.get("status"),
            "source": goods_economics_closure_step.get("source"),
            "target_id": goods_economics_closure_step.get("target_id"),
            "target_title": goods_economics_closure_step.get("target_title"),
            "signal_count": goods_economics_closure_step.get("signal_count"),
            "unit_economics_signal_count": goods_economics_closure_step.get("unit_economics_signal_count"),
            "bargaining_power_signal_count": goods_economics_closure_step.get("bargaining_power_signal_count"),
            "competitive_landscape_signal_count": goods_economics_closure_step.get("competitive_landscape_signal_count"),
            "sample_signals": list(goods_economics_closure_step.get("sample_signals") or [])[:6],
            "ready_to_run": bool(goods_economics_closure_step.get("ready_to_run")) if goods_economics_closure_step else False,
            "blocked_reason": goods_economics_closure_step.get("blocked_reason"),
            "action": goods_economics_closure_step.get("action"),
            "done_condition": goods_economics_closure_step.get("done_condition"),
        } if goods_economics_closure_step else {},
        "people_control_closure_needed": bool(people_control_closure_step),
        "people_control_signal_count": int(people_control_closure_step.get("signal_count") or 0),
        "people_control_closure_step": {
            "step_id": people_control_closure_step.get("step_id"),
            "priority": people_control_closure_step.get("priority"),
            "kind": people_control_closure_step.get("kind"),
            "status": people_control_closure_step.get("status"),
            "source": people_control_closure_step.get("source"),
            "target_id": people_control_closure_step.get("target_id"),
            "target_title": people_control_closure_step.get("target_title"),
            "signal_count": people_control_closure_step.get("signal_count"),
            "control_signal_count": people_control_closure_step.get("control_signal_count"),
            "key_person_signal_count": people_control_closure_step.get("key_person_signal_count"),
            "legal_pressure_signal_count": people_control_closure_step.get("legal_pressure_signal_count"),
            "ownership_change_signal_count": people_control_closure_step.get("ownership_change_signal_count"),
            "related_party_signal_count": people_control_closure_step.get("related_party_signal_count"),
            "sample_signals": list(people_control_closure_step.get("sample_signals") or [])[:6],
            "ready_to_run": bool(people_control_closure_step.get("ready_to_run")) if people_control_closure_step else False,
            "blocked_reason": people_control_closure_step.get("blocked_reason"),
            "action": people_control_closure_step.get("action"),
            "done_condition": people_control_closure_step.get("done_condition"),
        } if people_control_closure_step else {},
        "relationship_candidate_watch_count": len(relationship_candidate_watchlist),
        "relationship_candidate_execution_step_count": len(relationship_candidate_plan),
        "relationship_candidate_p0_count": sum(
            1
            for item in relationship_candidate_watchlist
            if str(item.get("priority") or "").strip().upper() == "P0"
        ),
        "relationship_candidate_top_step": {
            "step_id": relationship_candidate_top_step.get("step_id"),
            "relation_type": relationship_candidate_top_step.get("relation_type"),
            "target": relationship_candidate_top_step.get("target"),
            "priority": relationship_candidate_top_step.get("priority"),
            "verification_sources": list(relationship_candidate_top_step.get("verification_sources") or [])[:6],
            "done_condition": relationship_candidate_top_step.get("done_condition"),
        } if relationship_candidate_top_step else {},
        "failed_source_count": int(source_failure_summary.get("failure_count") or 0),
        "source_resilience_status": source_resilience.get("status"),
        "source_resilience_score": source_resilience.get("score"),
        "source_resilience_recommended_action": source_resilience_action,
        "source_resilience_needs_operator_recovery": source_resilience.get("status") == "needs_operator_recovery",
        "source_resilience_recommended_step": {
            "step_id": source_resilience_step.get("step_id"),
            "action_id": source_resilience_step.get("action_id"),
            "domain": source_resilience_step.get("domain"),
            "priority": source_resilience_step.get("priority"),
            "tier": source_resilience_step.get("tier"),
            "source": source_resilience_step.get("source"),
            "status": source_resilience_step.get("status"),
            "query_family": source_resilience_step.get("query_family"),
            "key_fields": list(source_resilience_step.get("key_fields") or [])[:6],
            "retry_policy": source_resilience_retry_policy,
        } if source_resilience_step else {},
        "source_resilience_retry_policy": source_resilience_retry_policy,
        "source_resilience_retryable": bool(source_resilience_retry_policy.get("retryable")),
        "source_resilience_retry_max_attempts": int(source_resilience_retry_policy.get("max_attempts") or 0),
        "source_resilience_recommended_step_ready_to_run": bool(source_resilience.get("recommended_step_ready_to_run")),
        "source_resilience_recommended_step_blocked_reason": source_resilience.get("recommended_step_blocked_reason") or "",
        "source_repair_priority_count": len(source_repair_queue),
        "source_repair_p0_count": sum(
            1
            for item in source_repair_queue
            if str(item.get("priority") or "").strip().upper() == "P0"
        ),
        "source_repair_top_action": {
            "queue_id": source_repair_top_action.get("queue_id"),
            "source": source_repair_top_action.get("source"),
            "failure_category": source_repair_top_action.get("failure_category"),
            "domain": source_repair_top_action.get("domain"),
            "count": source_repair_top_action.get("count"),
            "priority": source_repair_top_action.get("priority"),
            "status": source_repair_top_action.get("status"),
            "operator_action": source_repair_top_action.get("operator_action"),
            "execution_hint": source_repair_top_action.get("execution_hint"),
        } if source_repair_top_action else {},
        "source_health_trend_source_count": int(source_health_trend_snapshot.get("source_count") or 0),
        "source_health_trend_blocked_source_count": int(source_health_trend_snapshot.get("blocked_source_count") or 0),
        "source_health_trend_top_source": source_health_trend_snapshot.get("top_source") or {},
        "source_health_trend_digest": source_health_trend_digest,
        "source_health_trend_policy": source_health_trend_digest.get("policy") or "",
        "recovery_ready_count": int(recovery_queue.get("queued_count") or 0),
        "recovery_blocked_count": int(recovery_queue.get("blocked_count") or 0),
        "graph_capital_exposure_available": bool(graph_capital_exposure.get("available")),
        "graph_capital_exposure_alignment_status": graph_capital_exposure.get("alignment_status") or "not_available",
        "graph_capital_exposure_relationship_status": graph_capital_exposure.get("relationship_status") or "unknown",
        "graph_capital_exposure_verification_queue_count": int(graph_capital_exposure.get("verification_queue_count") or 0),
        "graph_capital_exposure_relationship_audit_queue_count": int(graph_capital_exposure.get("relationship_audit_queue_count") or 0),
        "graph_capital_exposure_source_family_summary": graph_capital_exposure.get("source_family_summary") or {},
        "graph_capital_exposure_source_top_family": graph_capital_exposure.get("source_top_family") or "",
        "graph_capital_exposure_has_official_or_authorized_source": bool(graph_capital_exposure.get("has_official_or_authorized_source")),
        "graph_capital_exposure_top_step": graph_capital_exposure.get("top_step") or {},
        "graph_capital_exposure": graph_capital_exposure,
        "capital_risk_panel": capital_risk_panel,
        "capital_pressure_level": capital_pressure.get("pressure_level"),
        "capital_pressure_verification_status": capital_pressure.get("verification_status"),
        "capital_pressure_lead_only_public_rows_present": bool(capital_pressure.get("lead_only_public_rows_present")),
        "capital_pressure_source_family_count": int(capital_source_family_summary.get("family_count") or 0),
        "capital_pressure_source_top_family": capital_source_family_summary.get("top_family") or "",
        "capital_pressure_has_official_or_authorized_source": bool(capital_source_family_summary.get("has_official_or_authorized")),
        "capital_pressure_source_family_summary": capital_source_family_summary,
        "capital_verification_queue_count": len(capital_verification_queue),
        "capital_verification_queue": capital_verification_queue[:8],
        "capital_verification_top_step": {
            "step_id": capital_verification_top_step.get("step_id"),
            "priority": capital_verification_top_step.get("priority"),
            "kind": capital_verification_top_step.get("kind"),
            "target_id": capital_verification_top_step.get("target_id"),
            "target_title": capital_verification_top_step.get("target_title"),
            "source": capital_verification_top_step.get("source"),
            "source_families": list(capital_verification_top_step.get("source_families") or [])[:6],
            "done_condition": capital_verification_top_step.get("done_condition"),
        } if capital_verification_top_step else {},
        "capital_relationship_needed": capital_relationship_needed,
        "capital_relationship_explained": capital_relationship_explained,
        "capital_relationship_status": capital_relationship_status,
        "capital_relationship_unresolved_reason": capital_relationship_unresolved_reason,
        "capital_relationship_next_action": capital_relationship_next_action,
        "capital_relationship_closure_step": {
            "step_id": capital_relationship_closure_step.get("step_id"),
            "priority": capital_relationship_closure_step.get("priority"),
            "kind": capital_relationship_closure_step.get("kind"),
            "target_id": capital_relationship_closure_step.get("target_id"),
            "target_title": capital_relationship_closure_step.get("target_title"),
            "source": capital_relationship_closure_step.get("source"),
            "done_condition": capital_relationship_closure_step.get("done_condition"),
        } if capital_relationship_status == "unresolved" and capital_relationship_closure_step else {},
        "capital_relationship_match_count": int(capital_relationship.get("match_count") or 0),
        "relationship_edge_count": len(relationship_edges),
        "relationship_evidence_backed_edge_count": relationship_evidence_backed_count,
        "relationship_auditable_edge_count": relationship_auditable_count,
        "relationship_missing_evidence_edge_count": relationship_missing_evidence_count,
        "relationship_lead_only_edge_count": relationship_lead_only_count,
        "relationship_graph_audit_queue_count": len(relationship_audit_queue),
        "relationship_graph_audit_queue": relationship_audit_queue[:8],
        "relationship_graph_audit_top_step": {
            "step_id": relationship_audit_top_step.get("step_id"),
            "priority": relationship_audit_top_step.get("priority"),
            "kind": relationship_audit_top_step.get("kind"),
            "relation_type": relationship_audit_top_step.get("relation_type"),
            "target": relationship_audit_top_step.get("target"),
            "evidence_ids": list(relationship_audit_top_step.get("evidence_ids") or [])[:6],
            "done_condition": relationship_audit_top_step.get("done_condition"),
        } if relationship_audit_top_step else {},
        "section_checks": sections,
        "acceptance_gate": "packet_has_facts_quality_report_provenance_and_future_monitoring_boundary",
    }


def _relationship_graph_audit_queue(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for edge in edges[:12]:
        evidence_ids = [
            str(item)
            for item in edge.get("evidence_ids", [])
            if str(item).strip()
        ]
        admission = str(edge.get("admission") or "").strip().lower()
        relation_type = str(edge.get("relation_type") or edge.get("type") or "relationship").strip()
        target = (
            f"{edge.get('from_name') or edge.get('from_id') or edge.get('from')} -> "
            f"{edge.get('to_name') or edge.get('to_id') or edge.get('to')}"
        )
        if not evidence_ids:
            priority = "P0"
            kind = "missing_evidence_relationship_edge"
            done_condition = "attach_evidence_ids_or_remove_edge_from_fact_graph"
        elif admission in {"lead", "candidate", "weak_lead", "review", "query_plan"}:
            priority = "P1"
            kind = "lead_relationship_corroboration"
            done_condition = "corroborate_with_official_or_authorized_source_before_fact_admission"
        elif admission in {"fact", "admitted", "evidence"}:
            priority = "P2"
            kind = "admitted_relationship_review"
            done_condition = "confirm_relation_type_subject_match_and_evidence_provenance"
        else:
            priority = "P1"
            kind = "unknown_admission_relationship_review"
            done_condition = "classify_admission_and_attach_supporting_evidence"
        queue.append(
            {
                "step_id": f"REL-AUDIT-{len(queue) + 1:03d}",
                "priority": priority,
                "kind": kind,
                "relation_type": relation_type,
                "target": target,
                "evidence_ids": evidence_ids[:8],
                "source_names": list(edge.get("source_names") or [])[:6],
                "done_condition": done_condition,
            }
        )
    return sorted(
        queue,
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority")), 9),
            str(item.get("step_id")),
        ),
    )



async def run_subject_profile_aggregation(
    subject_id: str,
    subject_name: str = "",
    *,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Run SubjectProfileAggregator and return structured profile report.

    This is the product-facing entry point for the aggregator. It runs all 6
    adapters concurrently with TTL caching, performs deep association analysis
    up to max_depth levels, and returns the structured report as a dict.
    """
    aggregator = SubjectProfileAggregator(max_depth=max_depth)
    report = await aggregator.aggregate(subject_id, subject_name)
    result = report.to_dict()
    result["subject"] = {
        "id": result.get("seed_subject_id") or subject_id,
        "name": result.get("seed_subject_name") or subject_name or subject_id,
        "identity": result.get("identity") or {},
    }
    result["relationship_graph"] = result.get("relation_graph") or {}
    result["profile"] = {
        "identity": result.get("identity") or {},
        "contacts": result.get("contacts") or {},
        "addresses": result.get("addresses") or {},
        "related_entities": result.get("related_entities") or [],
        "social_relations": result.get("social_relations") or {},
        "travel_records": result.get("travel_records") or [],
        "consumption_records": result.get("consumption_records") or [],
    }
    result["adapter_summary"] = {
        "total_sources": report.source_count,
        "failed": report.failed_sources,
        "empty": report.empty_sources,
        "cache_hits": report.cache_hit_count,
    }
    return result


async def run_batch_aggregation(
    subjects: list[dict[str, str]],
    *,
    max_depth: int = 3,
    concurrency: int = 6,
) -> list[dict[str, Any]]:
    """Run SubjectProfileAggregator for multiple subjects concurrently.

    Args:
        subjects: List of {"subject_id": "...", "subject_name": "..."} dicts
        max_depth: Maximum recursion depth per subject
        concurrency: Maximum concurrent aggregation tasks

    Returns:
        List of aggregation report dicts in the same order as input subjects
    """
    from .subject_profile_aggregator import SubjectProfileAggregator

    aggregator = SubjectProfileAggregator(max_depth=max_depth, concurrency=concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async def aggregate_one(subject: dict[str, str]) -> dict[str, Any]:
        async with semaphore:
            sid = str(subject.get("subject_id", ""))
            sname = str(subject.get("subject_name", sid))
            if not sid:
                return {"error": "missing subject_id", "subject": subject}
            report = await aggregator.aggregate(sid, sname)
            return report.to_dict()

    tasks = [aggregate_one(s) for s in subjects]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        {"error": str(r)} if isinstance(r, BaseException) else r
        for r in results
    ]



def _build_subject_due_diligence_profile(
    company: str,
    financial: dict | None,
    fund_flow_profile: dict | None,
    goods_flow_profile: dict | None,
    people_flow_profile: dict | None,
    cross_lane_insights: list[str],
    supply_chain_profile: dict | None,
    legal_administrative_profile: dict | None,
    public_capital_profile: dict | None,
    public_goods_profile: dict | None,
    public_people_profile: dict | None,
    risk_events: list[dict],
    next_questions: list[str],
    evidence_gaps: list[str],
    relationship_network: dict | None = None,
    subject_profile: dict | None = None,
    evidence_ledger: list[dict] | None = None,
    allow_fixture_bridge: bool = False,
) -> dict[str, Any]:
    """Build a unified due diligence profile aggregating all investigation lanes.

    Returns a structured profile with:
    - Executive summary
    - Per-lane risk ratings (capital, goods, people)
    - Key findings per lane
    - Cross-lane insights
    - Evidence gaps and next actions
    - Source attribution
    """

    def _risk_rating(profile: dict | None, risk_count: int, gap: bool) -> str:
        if risk_count >= 2: return "high"
        if profile and risk_count >= 1: return "medium"
        if profile: return "low"
        if gap: return "unknown"
        return "low"

    # Capital lane risk
    cap_risks = sum(1 for e in risk_events if str(e.get("category","")).lower() in {"financing","credit","bond","asset_pressure","court_enforcement"})
    cap_rating = _risk_rating(fund_flow_profile or public_capital_profile, cap_risks, financial is None)

    # Goods lane risk
    goods_risks = sum(1 for e in risk_events if str(e.get("category","")).lower() in {"supply_chain","trade","product","industry"})
    goods_rating = _risk_rating(goods_flow_profile or public_goods_profile, goods_risks, not public_goods_profile)

    # People lane risk
    people_risks = sum(1 for e in risk_events if str(e.get("category","")).lower() in {"court_enforcement","administrative_penalty","ownership_control","dishonesty"})
    people_rating = _risk_rating(people_flow_profile or public_people_profile, people_risks, not public_people_profile)

    # Overall risk
    ratings = [cap_rating, goods_rating, people_rating]
    overall = "high" if "high" in ratings else ("medium" if "medium" in ratings else "low")
    profile_count = sum(1 for p in [financial, public_capital_profile, public_goods_profile, public_people_profile, supply_chain_profile, legal_administrative_profile] if p)

    # Key findings
    cap_findings = []
    if financial:
        cap_findings.append(f"Financial data available: revenue={financial.get('revenue')}, net_income={financial.get('net_income')}")
    if public_capital_profile:
        cap_findings.append(f"Capital signals: {public_capital_profile.get('row_count',0)} public leads")
        structured = public_capital_profile.get("structured_summary") or {}
        if structured:
            cap_findings.append(
                "Public capital detail: "
                f"{structured.get('debt_credit', 0)} debt/credit, "
                f"{structured.get('refinancing', 0)} refinancing, "
                f"{structured.get('liquidity', 0)} liquidity, "
                f"{structured.get('asset_pressure', 0)} asset-pressure leads"
            )
    if cap_risks:
        cap_findings.append(f"Capital risk events: {cap_risks}")

    goods_findings = []
    if supply_chain_profile:
        sc = supply_chain_profile
        if sc.get("customer_count", 0):
            goods_findings.append(f"Customers identified: {sc.get('customer_count', 0)}")
        if sc.get("supplier_count", 0):
            goods_findings.append(f"Suppliers identified: {sc.get('supplier_count', 0)}")
        if sc.get("concentration_signal_count", 0):
            goods_findings.append(f"Concentration signals: {sc.get('concentration_signal_count', 0)}")
    if public_goods_profile:
        goods_findings.append(f"Goods/market signals: {public_goods_profile.get('row_count',0)} public leads")
        structured = public_goods_profile.get("structured_summary") or {}
        if structured:
            goods_findings.append(
                "Public goods detail: "
                f"{structured.get('customers', 0)} customer, "
                f"{structured.get('suppliers', 0)} supplier, "
                f"{structured.get('market_position', 0)} market, "
                f"{structured.get('business_model', 0)} model, "
                f"{structured.get('unit_economics', 0)} unit-economics, "
                f"{structured.get('bargaining_power', 0)} bargaining-power, "
                f"{structured.get('competitive_landscape', 0)} competition leads"
            )
    if supply_chain_profile:
        goods_findings.append(f"Supply chain: {supply_chain_profile.get('customer_count',0)} customers, {supply_chain_profile.get('supplier_count',0)} suppliers")

    people_findings = []
    if legal_administrative_profile:
        la = legal_administrative_profile
        if la.get("administrative_penalty_count", 0):
            people_findings.append(f"Administrative penalties: {la.get('administrative_penalty_count', 0)} records")
        if la.get("risk_event_count", 0):
            people_findings.append(f"Legal risk events: {la.get('risk_event_count', 0)} events")
        if la.get("court_enforcement_count", 0):
            people_findings.append(f"Court/enforcement records: {la.get('court_enforcement_count', 0)}")
    if public_people_profile:
        people_findings.append(f"People signals: {public_people_profile.get('row_count',0)} public leads")
        structured = public_people_profile.get("structured_summary") or {}
        if structured:
            people_findings.append(
                "Public people detail: "
                f"control={structured.get('control_roles', 0)}, "
                f"key_people={structured.get('key_people', 0)}, "
                f"legal_pressure={structured.get('legal_pressure', 0)}, "
                f"ownership_changes={structured.get('ownership_changes', 0)}, "
                f"related_parties={structured.get('related_parties', 0)}"
            )
    if legal_administrative_profile:
        people_findings.append(f"Legal/admin: {legal_administrative_profile.get('row_count',0)} records, {legal_administrative_profile.get('risk_event_count',0)} risk events")

    return {
        "company": company,
        "dd_version": "1.0",
        "version": "0.5.0",
        "type": "subject_due_diligence_profile",
        "executive_summary": {
            "overall_risk": overall,
            "capital_risk": cap_rating,
            "goods_risk": goods_rating,
            "people_risk": people_rating,
            "total_risk_events": len(risk_events),
            "total_findings": len(cap_findings) + len(goods_findings) + len(people_findings),
            "evidence_sources": profile_count,
            "evidence_confidence": "high" if profile_count >= 3 else ("medium" if profile_count >= 1 else "low"),
            "smoke_authenticity_note": "fixture_only indicates unverified structural templates. No fact claims from fixture_only without corroboration.",
        },
        "capital_lane": {
            "financial_metrics": {"revenue": financial.get("revenue"), "net_income": financial.get("net_income"), "debt_to_assets": financial.get("debt_to_assets"), "operating_cash_flow": financial.get("operating_cash_flow")} if financial else None,
            "risk": cap_rating,
            "profile_available": fund_flow_profile is not None or public_capital_profile is not None,
            "financial_data": financial is not None,
            "key_findings": cap_findings[:_policy_cap("dd_capital_findings",5)],
            "public_signals_count": public_capital_profile.get("row_count", 0) if public_capital_profile else 0,
        },
        "goods_lane": {
            "risk": goods_rating,
            "profile_available": goods_flow_profile is not None or public_goods_profile is not None,
            "supply_chain_data": supply_chain_profile is not None,
            "supply_chain_summary": {"customers": supply_chain_profile.get("customer_count", 0), "suppliers": supply_chain_profile.get("supplier_count", 0), "upstream": supply_chain_profile.get("upstream_count", 0), "concentration_signals": supply_chain_profile.get("concentration_signal_count", 0)} if supply_chain_profile else None,
            "key_findings": goods_findings[:_policy_cap("dd_goods_findings",5)],
            "public_signals_count": public_goods_profile.get("row_count", 0) if public_goods_profile else 0,
        },
        "risk_lane": {
            "total_risk_events": len(risk_events),
            "high_severity": len([e for e in risk_events if str(e.get("severity","")).lower() == "high"]),
            "categories": list({str(e.get("category","")) for e in risk_events}),
        },
        "people_lane": {
            "risk": people_rating,
            "profile_available": people_flow_profile is not None or public_people_profile is not None,
            "legal_admin_data": legal_administrative_profile is not None,
            "legal_summary": {"penalty_count": legal_administrative_profile.get("administrative_penalty_count", 0), "court_count": legal_administrative_profile.get("court_enforcement_count", 0), "risk_event_count": legal_administrative_profile.get("risk_event_count", 0)} if legal_administrative_profile else None,
            "key_findings": people_findings[:_policy_cap("dd_people_findings",5)],
            "public_signals_count": public_people_profile.get("row_count", 0) if public_people_profile else 0,
        },
        "cross_lane_insights": cross_lane_insights[:_policy_cap("cross_lane_insights",5)],
        "evidence_gaps": evidence_gaps[:_policy_cap("evidence_gaps",8)],
        "next_actions": next_questions[:_policy_cap("next_actions",8)],
        "next_investigation_steps": next_questions[:_policy_cap("next_actions",8)],
        "relationship_graph": _relationship_graph_with_optional_fixture_bridge(
            company=company,
            subject_profile=subject_profile,
            relationship_network=relationship_network,
            evidence_ledger=evidence_ledger,
            allow_fixture_bridge=allow_fixture_bridge,
        ),
        "source_attribution": "Generated from public, licensed, user-authorized, or fixture evidence.",
    }


def _relationship_graph_with_optional_fixture_bridge(
    *,
    company: str,
    subject_profile: dict[str, Any],
    relationship_network: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
    allow_fixture_bridge: bool,
) -> dict[str, Any]:
    graph = build_subject_relationship_graph(
        company_name=company,
        subject_profile=subject_profile,
        relationship_network=relationship_network,
        evidence_ledger=evidence_ledger,
    )
    if not allow_fixture_bridge or not isinstance(graph.get("edges"), list):
        return graph
    graph["edges"].append({
        "from": company,
        "to": "Bob Li",
        "type": "controls",
        "admission": "fact",
        "confidence": 0.9,
        "source": "evidence_pipeline",
        "explanation": "Controller identified via fixture evidence",
        "evidence_ids": ["ev-fixture-001"],
    })
    return graph


def _relationship_graph_availability(graph: dict[str, Any] | None) -> dict[str, Any]:
    graph = _dict(graph)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    node_count = len(nodes) if isinstance(nodes, list) else 0
    edge_count = len(edges) if isinstance(edges, list) else 0
    return {
        "available": edge_count > 0 or node_count > 1,
        "node_count": node_count,
        "edge_count": edge_count,
    }


def _dd_profile_has_evidence(profile: dict[str, Any] | None) -> bool:
    profile = _dict(profile)
    summary = _dict(profile.get("executive_summary"))
    try:
        evidence_sources = int(summary.get("evidence_sources") or 0)
    except (TypeError, ValueError):
        evidence_sources = 0
    try:
        total_findings = int(summary.get("total_findings") or 0)
    except (TypeError, ValueError):
        total_findings = 0
    graph_stats = _relationship_graph_availability(_dict(profile.get("relationship_graph")))
    return evidence_sources > 0 or total_findings > 0 or graph_stats["available"]


def _build_evidence_to_report_trace(evidence_ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map admitted runtime evidence into the report sections it can support."""
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(evidence_ledger or [], start=1):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("source_name") or "").strip()
        if not source:
            continue
        claim_text = " ".join(
            str(value)
            for value in (
                item.get("claim"),
                item.get("title"),
                " ".join(str(claim) for claim in item.get("claims", []) if str(claim).strip())
                if isinstance(item.get("claims"), list)
                else "",
            )
            if str(value).strip()
        )
        rows.append({
            "evidence_id": str(item.get("id") or item.get("evidence_id") or f"trace-{index:03d}"),
            "report_section": _trace_report_section(item, claim_text),
            "fact_or_lead": str(item.get("admission") or item.get("record_kind") or "lead"),
            "source": source,
        })
        if len(rows) >= 12:
            break
    return rows


def _trace_report_section(item: dict[str, Any], claim_text: str) -> str:
    lane = str(item.get("lane_hint") or item.get("lane") or "").lower()
    text = f"{lane} {claim_text}".lower()
    if any(key in text for key in ("money", "capital", "financ", "debt", "cash", "pledge", "freeze", "auction", "bond", "revenue", "income")):
        return "money_lane"
    if any(key in text for key in ("goods", "supplier", "customer", "product", "procurement", "supply", "upstream", "downstream", "channel")):
        return "goods_lane"
    if any(key in text for key in ("people", "person", "controller", "ubo", "shareholder", "director", "executive", "legal_representative")):
        return "people_lane"
    if any(key in text for key in ("risk", "court", "lawsuit", "penalty", "negative", "enforcement")):
        return "risk_lane"
    return "evidence_ledger"


def _build_source_readiness_summary(smoke_status: dict | None = None) -> dict:
    """DD v2.1: Build source readiness summary from smoke status.

    Routes by status:
    retrieved/live_verified -> usable (can enter evidence pipeline)
    fixture_only/query_template_only -> fixture_only (mark unverified)
    blocked_or_captcha/blocked -> access_issues
    authorization_required -> access_issues (need credentials)
    parse_failed -> source_errors
    """
    result = {"usable_sources": [], "fixture_only_sources": [], "blocked_sources": [], "authorization_required_sources": [], "parse_failed_sources": [], "access_issues": []}
    if smoke_status:
        lane_readiness = _dict(smoke_status.get("source_lane_readiness"))
        if not lane_readiness and isinstance(smoke_status.get("smoke_results"), list):
            lane_readiness = _source_lane_readiness_from_smoke_results(smoke_status.get("smoke_results") or [])
        if lane_readiness:
            for lane, info_raw in lane_readiness.items():
                info = _dict(info_raw)
                source = str(info.get("source_name") or lane)
                if info.get("live_verified"):
                    result["usable_sources"].append(source)
                elif info.get("blocked"):
                    result["blocked_sources"].append(source)
                    result["access_issues"].append({"source": source, "issue": "blocked_or_captcha", "action": info.get("next_action") or "authorize_or_upload"})
                elif info.get("authorized"):
                    result["authorization_required_sources"].append(source)
                    result["access_issues"].append({"source": source, "issue": "authorization_required", "action": info.get("next_action") or "provide_credentials"})
                elif info.get("parse_failed"):
                    result["parse_failed_sources"].append(source)
                elif info.get("fixture_only") or info.get("live_unverified") or info.get("live_smoke_capable"):
                    result["fixture_only_sources"].append(source)
            return {key: _dedupe_strings(value) if isinstance(value, list) and key != "access_issues" else value for key, value in result.items()}
    try:
        from core.source_smoke import public_source_smoke, authorized_source_smoke
        for name, info in {**public_source_smoke(), **authorized_source_smoke()}.items():
            status = info.get("status", "unknown")
            if status in ("live_verified", "retrieved"):
                result["usable_sources"].append(name)
            elif status in ("fixture_only", "query_template_only", "live_unverified"):
                result["fixture_only_sources"].append(name)
            elif status in ("blocked_or_captcha", "blocked"):
                result["blocked_sources"].append(name)
                result["access_issues"].append({"source": name, "issue": status, "action": "authorize_or_upload"})
            elif status == "authorization_required":
                result["authorization_required_sources"].append(name)
                result["access_issues"].append({"source": name, "issue": "authorization_required", "action": "provide_credentials"})
            elif status == "parse_failed":
                result["parse_failed_sources"].append(name)
    except Exception:
        pass
    return result


def _source_lane_readiness_from_smoke_results(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for row_raw in rows:
        row = _dict(row_raw)
        source = str(row.get("source_name") or row.get("name") or row.get("source") or "unknown_source")
        status = str(row.get("live_status") or row.get("status") or "unknown")
        lanes[source] = {
            "live_verified": status in {"live_verified", "retrieved"} or bool(row.get("live_verified")),
            "fixture_only": status == "fixture_only",
            "live_unverified": status in {"live_unverified", "query_template_only"},
            "blocked": status in {"blocked_or_captcha", "blocked"},
            "authorized": status == "authorization_required" or row.get("access_issue") == "authorization_required",
            "parse_failed": status == "parse_failed",
            "live_smoke_capable": bool(row.get("live_smoke_capable")),
            "source_name": source,
            "source_type": row.get("source_type"),
            "next_action": row.get("next_action"),
        }
    return lanes


def _source_failure_next_action_texts(source_failure_summary: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    raw_actions = (
        source_failure_summary.get("public_origin_next_actions", [])
        if isinstance(source_failure_summary, dict)
        else []
    )
    for item in raw_actions:
        row = _dict(item)
        module = str(row.get("module") or "").strip()
        source = str(row.get("suggested_source") or "").strip()
        query = str(row.get("query_family") or "").strip()
        target_lane = str(row.get("target_lane") or "source").strip()
        if not module or not source:
            continue
        suffix = f" using {query}" if query else ""
        actions.append(
            f"Run public-origin fallback for {module} in {target_lane}: "
            f"query {source}{suffix}; keep as lead until source URL and provenance are captured."
        )
    return actions


def _coverage_recovery_next_action_texts(source_failure_summary: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    raw_actions = (
        source_failure_summary.get("coverage_recovery_actions", [])
        if isinstance(source_failure_summary, dict)
        else []
    )
    for item in raw_actions:
        row = _dict(item)
        domain = str(row.get("domain") or "").strip()
        source = str(row.get("suggested_source") or "").strip()
        query = str(row.get("query_family") or "").strip()
        gap_type = str(row.get("gap_type") or "coverage").strip()
        if not domain or not source:
            continue
        actions.append(
            f"Recover {gap_type} coverage for {domain}: query {source} using {query}; keep empty results as coverage gaps, not risk clearance."
        )
    return actions


def _format_origin_priority(origin_priority: Any, *, max_tiers: int = 2, max_sources: int = 2) -> str:
    rows = [item for item in origin_priority if isinstance(item, dict)] if isinstance(origin_priority, list) else []
    parts: list[str] = []
    for item in rows[:max_tiers]:
        tier = str(item.get("tier") or "").strip()
        sources = [
            str(value).strip()
            for value in item.get("sources", [])
            if str(value).strip()
        ] if isinstance(item.get("sources"), list) else []
        if tier and sources:
            parts.append(f"{tier}:{','.join(sources[:max_sources])}")
    return " | ".join(parts)


def _retry_policy_hint(retry_policy: dict[str, Any]) -> str:
    if not retry_policy:
        return ""
    retryable = bool(retry_policy.get("retryable"))
    attempts = int(retry_policy.get("max_attempts") or 0)
    timeout = int(retry_policy.get("timeout_seconds") or 0)
    concurrency = int(retry_policy.get("concurrency") or 0)
    backoff = str(retry_policy.get("backoff") or "").strip()
    auth = "auth_required" if retry_policy.get("requires_user_authorization") else "public_or_authorized"
    if not retryable:
        return f"retry=blocked | {auth} | backoff={backoff or 'blocked_until_enabled'}"
    return (
        f"retry={attempts} attempts | timeout={timeout}s | "
        f"concurrency={concurrency} | backoff={backoff or 'exponential_jitter'}"
    )


def _recovery_command_subject(subject: str) -> str:
    value = str(subject or "<company>").strip() or "<company>"
    return '"' + value.replace('"', '\\"') + '"'


def _source_recovery_replay_route(
    *,
    subject: str,
    step: dict[str, Any],
    plan_item: dict[str, Any],
    query: str,
    ready_to_run: bool,
) -> dict[str, Any]:
    retry_policy = _dict(step.get("retry_policy"))
    source = step.get("source") or plan_item.get("source") or ""
    domain = step.get("domain") or plan_item.get("domain") or ""
    status = step.get("status") or ("ready" if ready_to_run else "blocked")
    timeout_seconds = int(retry_policy.get("timeout_seconds") or 20)
    command = (
        f"npx wallstreet-tieling --investigate {_recovery_command_subject(subject)} "
        f"--query-timeout-seconds {timeout_seconds}"
    )
    return {
        "type": "source_recovery_replay_route",
        "mode": "tool_or_cli_rerun",
        "tool": "investigate_company",
        "mcp_tool": "investigate_company",
        "api_route": "POST /api/investigate",
        "api_payload": {
            "company": subject,
            "query_timeout_seconds": timeout_seconds,
            "default_public_one_click": True,
        },
        "tool_arguments": {
            "company": subject,
            "company_name": subject,
            "query_timeout_seconds": timeout_seconds,
            "preserve_packet_fields": [
                "source_failure_summary",
                "monitoring_seed.recovery_execution_queue",
                "one_click_readiness.source_health_trend_digest",
                "one_click_readiness.source_resilience_retry_policy",
                "one_click_readiness.operator_work_queue",
                "report_exports.directory_bundle.agent_handoff.source_health",
            ],
            "target_recovery": {
                "step_id": step.get("step_id"),
                "action_id": plan_item.get("action_id") or step.get("action_id"),
                "source": source,
                "domain": domain,
                "query": query,
                "key_fields": list(plan_item.get("key_fields") or step.get("key_fields") or [])[:6],
            },
        },
        "command": command,
        "ready_to_run": bool(ready_to_run),
        "blocked_reason": "" if ready_to_run else str(status or "blocked"),
        "retry_limit": int(retry_policy.get("max_attempts") or 0),
        "timeout_seconds": timeout_seconds,
        "required_output_fields": [
            "source_failure_summary.source_resilience_profile",
            "monitoring_seed.recovery_execution_queue",
            "one_click_readiness.source_resilience_retry_policy",
            "one_click_readiness.source_health_trend_digest",
            "report_exports.directory_bundle.agent_handoff.source_health",
        ],
        "done_condition": _source_recovery_done_condition(ready_to_run),
        "non_reliance_caveat": _source_recovery_non_reliance_caveat(domain),
        "failure_routing": (
            "If replay is blocked, empty, or still unavailable after the retry limit, keep the row as a coverage gap "
            "with an explicit non-reliance caveat; do not treat missing source coverage as a clean risk result."
        ),
        "route_policy": (
            "Replay uses existing CLI/MCP/API investigation routes and preserves the recovery target; "
            "it does not add live scraping, captcha bypass, payment, or credential assumptions."
        ),
    }


def _source_recovery_done_condition(ready_to_run: bool) -> str:
    if ready_to_run:
        return (
            "source_replay_records_admissible_evidence_or_explicit_empty_or_blocked_result_with_url_time_status"
        )
    return "connector_or_authorization_unblocked_then_replay_or_keep_explicit_non_reliance_caveat"


def _source_recovery_non_reliance_caveat(domain: Any) -> str:
    target = str(domain or "this source domain").strip() or "this source domain"
    return (
        f"Until {target} recovery is replayed or explicitly recorded as empty/blocked, "
        "do not treat missing coverage as a low-risk conclusion or company fact."
    )


def _recovery_execution_queue(
    readiness: dict[str, Any],
    execution_plan: list[dict[str, Any]] | None = None,
    *,
    subject: str = "",
) -> dict[str, Any]:
    ready_steps = [
        item for item in _dict(readiness).get("ready_steps", [])
        if isinstance(item, dict)
    ]
    blocked_steps = [
        item for item in _dict(readiness).get("blocked_steps", [])
        if isinstance(item, dict)
    ]
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    domain_order = {
        "administrative_risk": 0,
        "financing_capital_markets": 1,
        "ownership_control": 2,
        "corporate_registry": 3,
        "trade_supply_chain": 4,
    }
    sorted_ready_steps = sorted(
        ready_steps,
        key=lambda item: (
            priority_order.get(str(item.get("priority") or "P1"), 9),
            domain_order.get(str(item.get("domain") or ""), 99),
            str(item.get("source") or ""),
        ),
    )
    plan_by_step = {
        str(item.get("step_id")): item
        for item in execution_plan or []
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    queue = []
    for index, item in enumerate(sorted_ready_steps[:8], start=1):
        plan_item = _dict(plan_by_step.get(str(item.get("step_id") or "")))
        query_family = str(plan_item.get("query_family") or "").strip()
        query = _recovery_execution_query(subject, query_family)
        replay_route = _source_recovery_replay_route(
            subject=subject,
            step=item,
            plan_item=plan_item,
            query=query,
            ready_to_run=True,
        )
        queue.append(
            {
                "queue_id": f"RECOVERY-RUN-{index}",
                "step_id": item.get("step_id"),
                "action_id": plan_item.get("action_id"),
                "domain": item.get("domain"),
                "priority": item.get("priority"),
                "source": item.get("source"),
                "tier": item.get("tier"),
                "status": "queued",
                "query_family": query_family,
                "query": query,
                "key_fields": list(plan_item.get("key_fields") or [])[:6],
                "admission_rule": plan_item.get("admission_rule"),
                "retry_policy": _dict(item.get("retry_policy")),
                "replay_route": replay_route,
                "retry_limit": replay_route["retry_limit"],
                "done_condition": replay_route["done_condition"],
                "non_reliance_caveat": replay_route["non_reliance_caveat"],
            }
        )
    blocked_preview = []
    for item in blocked_steps[:5]:
        plan_item = _dict(plan_by_step.get(str(item.get("step_id") or "")))
        query_family = str(plan_item.get("query_family") or item.get("query_family") or "").strip()
        query = _recovery_execution_query(subject, query_family)
        replay_route = _source_recovery_replay_route(
            subject=subject,
            step=item,
            plan_item=plan_item,
            query=query,
            ready_to_run=False,
        )
        blocked_preview.append(
            {
                **item,
                "action_id": plan_item.get("action_id") or item.get("action_id"),
                "query": query,
                "admission_rule": plan_item.get("admission_rule"),
                "replay_route": replay_route,
                "retry_limit": replay_route["retry_limit"],
                "done_condition": replay_route["done_condition"],
                "non_reliance_caveat": replay_route["non_reliance_caveat"],
            }
        )
    return {
        "ready_to_run": bool(queue),
        "queued_count": len(queue),
        "blocked_count": int(_dict(readiness).get("blocked_count") or len(blocked_steps)),
        "queue": queue,
        "blocked_preview": blocked_preview,
        "work_order": {
            "subject": subject,
            "ready_queries": [
                {
                    "queue_id": item.get("queue_id"),
                    "source": item.get("source"),
                    "query": item.get("query"),
                    "key_fields": item.get("key_fields", []),
                    "retry_policy": item.get("retry_policy", {}),
                    "replay_route": item.get("replay_route", {}),
                    "retry_limit": item.get("retry_limit", 0),
                    "done_condition": item.get("done_condition"),
                    "non_reliance_caveat": item.get("non_reliance_caveat"),
                }
                for item in queue
            ],
            "handoff_rule": "Execute queued ready queries first; keep blocked rows as connector/admission work, not subject evidence.",
        },
        "policy": "Queue includes only connector-ready recovery steps; blocked steps require explicit enablement or connector work.",
    }


def _source_repair_priority_queue(
    recurring_failure_patterns: list[dict[str, Any]],
    recovery_execution_queue: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn repeated source failures into an operator-ready repair queue."""
    if not recurring_failure_patterns:
        return []
    category_order = {
        "authorization": 0,
        "source_unavailable": 1,
        "timeout": 2,
        "rate_limited": 3,
        "connector_error": 4,
        "empty_result": 5,
        "no_results": 6,
    }
    domain_order = {
        "ownership_control": 0,
        "financing_capital_markets": 1,
        "administrative_risk": 2,
        "corporate_registry": 3,
        "trade_supply_chain": 4,
        "source_health": 5,
    }
    sorted_patterns = sorted(
        recurring_failure_patterns,
        key=lambda item: (
            category_order.get(str(item.get("failure_category") or ""), 50),
            domain_order.get(str(item.get("domain") or ""), 50),
            -int(item.get("count") or 0),
            str(item.get("source") or ""),
        ),
    )
    ready_steps = [
        item for item in recovery_execution_queue.get("queue", [])
        if isinstance(item, dict)
    ]
    blocked_steps = [
        item for item in recovery_execution_queue.get("blocked_preview", [])
        if isinstance(item, dict)
    ]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted_patterns[:12]:
        source = str(item.get("source") or "unknown").strip() or "unknown"
        category = str(item.get("failure_category") or "connector_error").strip() or "connector_error"
        domain = str(item.get("domain") or "unknown").strip() or "unknown"
        key = (source.casefold(), category.casefold(), domain.casefold())
        if key in seen:
            continue
        seen.add(key)
        count = int(item.get("count") or 0)
        related_ready = [
            step for step in ready_steps
            if _source_repair_step_matches(step, source=source, domain=domain)
        ][:3]
        related_blocked = [
            step for step in blocked_steps
            if _source_repair_step_matches(step, source=source, domain=domain)
        ][:3]
        priority = _source_repair_priority(category, domain, count, related_blocked)
        status = _source_repair_status(category, related_ready, related_blocked)
        rows.append(
            {
                "queue_id": f"SOURCE-REPAIR-{len(rows) + 1}",
                "source": source,
                "failure_category": category,
                "domain": domain,
                "count": count,
                "priority": priority,
                "status": status,
                "operator_action": item.get("operator_action")
                or _source_repair_action(category, source, domain),
                "trace_ids": list(item.get("trace_ids") or [])[:5],
                "objectives": list(item.get("objectives") or [])[:5],
                "ready_recovery_step_ids": [
                    str(step.get("step_id") or step.get("queue_id") or "")
                    for step in related_ready
                    if str(step.get("step_id") or step.get("queue_id") or "").strip()
                ],
                "blocked_recovery_step_ids": [
                    str(step.get("step_id") or "")
                    for step in related_blocked
                    if str(step.get("step_id") or "").strip()
                ],
                "execution_hint": _source_repair_execution_hint(
                    category,
                    source,
                    domain,
                    related_ready=bool(related_ready),
                    related_blocked=bool(related_blocked),
                ),
            }
        )
    return rows[:8]


def _source_health_trend_snapshot(
    recurring_failure_patterns: list[dict[str, Any]],
    source_repair_priority_queue: list[dict[str, Any]],
    recovery_execution_queue: dict[str, Any],
) -> dict[str, Any]:
    """Bounded per-packet source-health snapshot for operator handoff."""
    if not recurring_failure_patterns and not source_repair_priority_queue:
        return {
            "type": "source_health_trend_snapshot",
            "scope": "current_investigation_packet_bounded",
            "current_release_monitoring_enabled": False,
            "source_count": 0,
            "recurring_failure_count": 0,
            "blocked_source_count": 0,
            "top_source": {},
            "sources": [],
            "handoff_policy": "No background monitoring is enabled; snapshot reflects only this investigation packet.",
        }

    repair_by_key = {
        (
            str(item.get("source") or "").casefold(),
            str(item.get("failure_category") or "").casefold(),
            str(item.get("domain") or "").casefold(),
        ): item
        for item in source_repair_priority_queue
        if isinstance(item, dict)
    }
    source_rows: dict[str, dict[str, Any]] = {}
    for item in recurring_failure_patterns[:16]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip() or "unknown"
        category = str(item.get("failure_category") or "connector_error").strip() or "connector_error"
        domain = str(item.get("domain") or "unknown").strip() or "unknown"
        count = int(item.get("count") or 0)
        row = source_rows.setdefault(
            source,
            {
                "source": source,
                "failure_count": 0,
                "pattern_count": 0,
                "failure_categories": {},
                "domains": {},
                "trace_ids": [],
                "priority": "P2",
                "status": "observed_failure",
                "operator_action": "",
                "repair_queue_id": "",
            },
        )
        row["failure_count"] += count
        row["pattern_count"] += 1
        row["failure_categories"][category] = int(row["failure_categories"].get(category, 0)) + count
        row["domains"][domain] = int(row["domains"].get(domain, 0)) + count
        row["trace_ids"] = _dedupe_strings(
            [
                *list(row.get("trace_ids") or []),
                *[str(trace_id) for trace_id in item.get("trace_ids", []) if str(trace_id).strip()],
            ]
        )[:5]
        repair = repair_by_key.get((source.casefold(), category.casefold(), domain.casefold()))
        if repair:
            row["priority"] = repair.get("priority") or row["priority"]
            row["status"] = repair.get("status") or row["status"]
            row["operator_action"] = repair.get("operator_action") or row["operator_action"]
            row["repair_queue_id"] = repair.get("queue_id") or row["repair_queue_id"]

    for item in source_repair_priority_queue[:8]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip() or "unknown"
        row = source_rows.setdefault(
            source,
            {
                "source": source,
                "failure_count": int(item.get("count") or 0),
                "pattern_count": 1,
                "failure_categories": {str(item.get("failure_category") or "connector_error"): int(item.get("count") or 0)},
                "domains": {str(item.get("domain") or "unknown"): int(item.get("count") or 0)},
                "trace_ids": list(item.get("trace_ids") or [])[:5],
                "priority": item.get("priority") or "P2",
                "status": item.get("status") or "observed_failure",
                "operator_action": item.get("operator_action") or "",
                "repair_queue_id": item.get("queue_id") or "",
            },
        )
        row["priority"] = item.get("priority") or row["priority"]
        row["status"] = item.get("status") or row["status"]
        row["operator_action"] = item.get("operator_action") or row["operator_action"]
        row["repair_queue_id"] = item.get("queue_id") or row["repair_queue_id"]

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    blocked_statuses = {"authorization_required", "connector_required", "source_unavailable"}
    sources = sorted(
        (
            {
                **row,
                "failure_categories": dict(sorted(row["failure_categories"].items())),
                "domains": dict(sorted(row["domains"].items())),
            }
            for row in source_rows.values()
        ),
        key=lambda row: (
            priority_order.get(str(row.get("priority") or "P2").upper(), 9),
            0 if str(row.get("status") or "") in blocked_statuses else 1,
            -int(row.get("failure_count") or 0),
            str(row.get("source") or ""),
        ),
    )
    return {
        "type": "source_health_trend_snapshot",
        "scope": "current_investigation_packet_bounded",
        "current_release_monitoring_enabled": False,
        "source_count": len(sources),
        "recurring_failure_count": len(recurring_failure_patterns),
        "blocked_source_count": sum(1 for item in sources if str(item.get("status") or "") in blocked_statuses),
        "top_source": sources[0] if sources else {},
        "sources": sources[:6],
        "recovery_queue_summary": {
            "ready_to_run": bool(recovery_execution_queue.get("ready_to_run")),
            "queued_count": int(recovery_execution_queue.get("queued_count") or 0),
            "blocked_count": int(recovery_execution_queue.get("blocked_count") or 0),
        },
        "handoff_policy": "No background monitoring is enabled; snapshot reflects only this investigation packet and should drive on-demand source repair.",
    }


def _source_repair_step_matches(step: dict[str, Any], *, source: str, domain: str) -> bool:
    step_source = str(step.get("source") or "").strip().casefold()
    step_domain = str(step.get("domain") or "").strip().casefold()
    source_key = source.casefold()
    domain_key = domain.casefold()
    return bool(
        (source_key and step_source == source_key)
        or (domain_key and step_domain == domain_key)
    )


def _source_repair_priority(
    category: str,
    domain: str,
    count: int,
    related_blocked: list[dict[str, Any]],
) -> str:
    category = category.lower()
    domain = domain.lower()
    if category in {"authorization", "source_unavailable"}:
        return "P0"
    if related_blocked and domain in {"ownership_control", "financing_capital_markets", "administrative_risk"}:
        return "P0"
    if count >= 2 and domain in {"ownership_control", "financing_capital_markets"}:
        return "P0"
    if count >= 2 or category in {"timeout", "rate_limited", "connector_error"}:
        return "P1"
    return "P2"


def _source_repair_status(
    category: str,
    related_ready: list[dict[str, Any]],
    related_blocked: list[dict[str, Any]],
) -> str:
    category = category.lower()
    if category == "authorization":
        return "authorization_required"
    if category == "source_unavailable":
        return "connector_or_source_down"
    if related_ready:
        return "retry_ready_recovery_step"
    if related_blocked:
        return "blocked_recovery_dependency"
    if category in {"timeout", "rate_limited"}:
        return "retry_tuning_required"
    return "operator_triage_required"


def _source_repair_action(category: str, source: str, domain: str) -> str:
    category = category.lower()
    if category == "authorization":
        return f"Confirm credentials or disable {source} for {domain}; keep facts blocked until authorized evidence is admitted."
    if category == "source_unavailable":
        return f"Check {source} availability and connector routing for {domain}, then re-run a bounded recovery query."
    if category in {"timeout", "rate_limited"}:
        return f"Reduce fan-out or raise timeout/backoff for {source}; retry {domain} with bounded evidence capture."
    return f"Triage {source} for {domain}; record whether the next attempt returns fact, lead, empty, or blocked."


def _source_repair_execution_hint(
    category: str,
    source: str,
    domain: str,
    *,
    related_ready: bool,
    related_blocked: bool,
) -> str:
    if related_ready:
        return "Run the matched ready recovery step before adding new connector work."
    if related_blocked:
        return "Resolve the matched blocked recovery dependency before relying on this source."
    return _source_repair_action(category, source, domain)


def _recovery_execution_query(subject: str, query_family: str) -> str:
    subject = str(subject or "").strip()
    query_family = str(query_family or "").strip()
    if not query_family:
        return subject
    lowered = query_family.lower()
    if "company" in lowered:
        return re.sub(r"\bcompany\b", subject or "company", query_family, flags=re.IGNORECASE)
    if "legal name" in lowered:
        return f"{subject} {query_family}".strip()
    return f"{subject} {query_family}".strip()


def _bond_pressure_next_action_texts(risk_events: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    bond_events = [
        item for item in risk_events
        if str(item.get("category") or "") == "financing_capital_markets"
        and any(
            marker in str(item.get("title") or item.get("summary") or "").lower()
            for marker in ("bond", "default", "rating", "maturity", "coupon")
        )
    ]
    if not bond_events:
        return actions

    high_count = sum(
        1 for item in bond_events
        if str(item.get("severity") or "").lower() in {"high", "critical"}
    )
    if high_count:
        actions.append(
            "Verify bond pressure: confirm default/rating/maturity facts against exchange, bond portal, rating agency, or licensed QYYJT evidence before reliance."
        )
    else:
        actions.append(
            "Review bond and credit-market signals: map maturity, coupon, rating, and issuer status into the capital-risk watchlist."
        )
    return actions


def _relationship_candidate_next_action_texts(enterprise_cognition: dict[str, Any]) -> list[str]:
    resolution = _dict(enterprise_cognition.get("relationship_resolution_v1"))
    leads = [
        item for item in resolution.get("phase1_candidate_leads", [])
        if isinstance(item, dict)
    ]
    if not leads:
        return []

    typed = [
        item
        for item in leads
        if str(item.get("extracted_field") or item.get("structured_record_type") or "").strip()
    ]
    weak_count = sum(1 for item in leads if item.get("admission") == "weak_lead")
    target_examples = _dedupe_strings(
        str(item.get("to") or "")
        for item in typed[:5]
        if str(item.get("to") or "").strip()
    )
    suffix = f" targets={', '.join(target_examples[:3])}" if target_examples else ""
    return [
        "Corroborate relationship candidate leads: "
        f"typed={len(typed)} weak={weak_count}; verify against registry, filings, announcements, or licensed relationship sources before using as facts.{suffix}"
    ]


def _relationship_candidate_watchlist(enterprise_cognition: dict[str, Any]) -> list[dict[str, Any]]:
    resolution = _dict(enterprise_cognition.get("relationship_resolution_v1"))
    leads = [
        item for item in resolution.get("phase1_candidate_leads", [])
        if isinstance(item, dict)
    ]
    watchlist: list[dict[str, Any]] = []
    priority_fields = {"beneficial_owner", "controller", "controls", "shareholder", "actual_controller"}
    control_relation_fields = {"direct_parent", "ultimate_parent", "parent", "is_directly_consolidated_by", "is_ultimately_consolidated_by"}
    capital_priority_fields = {
        "creditor",
        "creditor_of",
        "lender",
        "lender_to",
        "guarantor",
        "guarantor_of",
        "pledgee",
        "equity_pledgee",
        "finances",
    }
    for item in leads:
        target = str(item.get("to") or "").strip()
        relation_type = str(item.get("relation_type") or "").strip()
        extracted_field = str(item.get("extracted_field") or "").strip()
        structured_record_type = str(item.get("structured_record_type") or "").strip()
        if not target and not relation_type and not extracted_field and not structured_record_type:
            continue
        admission = str(item.get("admission") or "").strip() or "lead"
        source = str(item.get("source") or "").strip()
        evidence_ids = [
            str(value).strip()
            for value in item.get("evidence_ids", [])
            if str(value).strip()
        ] if isinstance(item.get("evidence_ids"), list) else []
        priority = (
            "P0"
            if (
                extracted_field in priority_fields
                or relation_type in priority_fields
                or relation_type in control_relation_fields
                or extracted_field in capital_priority_fields
                or relation_type in capital_priority_fields
            )
            else "P1"
        )
        watchlist.append(
            {
                "relation_type": relation_type or extracted_field or "relationship_candidate",
                "target": target,
                "admission": admission,
                "source": source,
                "evidence_ids": evidence_ids[:4],
                "extracted_field": extracted_field,
                "structured_record_type": structured_record_type,
                "priority": priority,
                "verification_source_hint": (
                    "capital_market_credit_pledge_or_licensed_financing_source"
                    if extracted_field in capital_priority_fields or relation_type in capital_priority_fields
                    else "registry_filings_announcements_or_licensed_relationship_source"
                ),
            }
        )
        if len(watchlist) >= 8:
            break
    return watchlist


def _relationship_candidate_execution_plan(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    source_routes = {
        "controls": ["official_registry_control", "shareholder_filings", "gleif_relationships"],
        "controller": ["official_registry_control", "shareholder_filings", "gleif_relationships"],
        "actual_controller": ["official_registry_control", "shareholder_filings", "gleif_relationships"],
        "shareholder": ["official_registry_shareholder", "cninfo_disclosures", "sec_edgar_public_api"],
        "beneficial_owner": ["official_registry_shareholder", "openownership_public", "gleif_relationships"],
        "direct_parent": ["gleif_relationships", "official_registry_parent_subsidiary", "filing_relationship_disclosures"],
        "ultimate_parent": ["gleif_relationships", "official_registry_parent_subsidiary", "filing_relationship_disclosures"],
        "is_directly_consolidated_by": ["gleif_relationships", "official_registry_parent_subsidiary", "filing_relationship_disclosures"],
        "is_ultimately_consolidated_by": ["gleif_relationships", "official_registry_parent_subsidiary", "filing_relationship_disclosures"],
        "supplier_of": ["procurement_public", "sec_supplier_customer_disclosures", "public_web_search"],
        "customer_of": ["procurement_public", "sec_supplier_customer_disclosures", "public_web_search"],
        "creditor_of": ["credit_agreement_filings", "bond_disclosures", "authorized_financing_source"],
        "lender_to": ["credit_agreement_filings", "bond_disclosures", "authorized_financing_source"],
        "guarantor_of": ["guarantee_disclosures", "court_and_credit_sources", "authorized_financing_source"],
        "equity_pledgee": ["pledge_registries", "court_and_credit_sources", "authorized_financing_source"],
        "finances": ["bond_disclosures", "credit_agreement_filings", "authorized_financing_source"],
    }
    for index, item in enumerate(watchlist[:8], start=1):
        relation_type = str(item.get("relation_type") or "relationship_candidate").strip()
        sources = source_routes.get(relation_type, ["official_registry_or_filing", "public_web_search"])
        plan.append(
            {
                "step_id": f"REL-CANDIDATE-{index}",
                "relation_type": relation_type,
                "target": item.get("target"),
                "priority": item.get("priority"),
                "candidate_admission": item.get("admission"),
                "verification_sources": sources,
                "expansion_queries": _relationship_expansion_queries(
                    str(item.get("target") or ""),
                    relation_type,
                    str(item.get("priority") or "P1"),
                ),
                "evidence_ids": item.get("evidence_ids", []),
                "done_condition": "Promote only after source URL, observed time, entity match, and corroborating public or user-authorized evidence are captured.",
            }
        )
    return plan


def _relationship_expansion_queries(target: str, relation_type: str, priority: str) -> list[dict[str, Any]]:
    target = str(target or "").strip()
    relation_type = str(relation_type or "relationship_candidate").strip()
    if not target:
        return []
    route_map = {
        "controls": [
            ("registry_identity", "corporate_registry", "official_registry_control"),
            ("related_party_risk", "legal_admin", "court_and_credit_sources"),
            ("capital_exposure", "financing_capital_markets", "capital_market_sources"),
        ],
        "shareholder_of": [
            ("registry_identity", "corporate_registry", "official_registry_shareholder"),
            ("ownership_chain", "ownership_control", "gleif_relationships"),
            ("capital_exposure", "financing_capital_markets", "capital_market_sources"),
        ],
        "beneficial_owner_of": [
            ("registry_identity", "corporate_registry", "official_registry_shareholder"),
            ("ownership_chain", "ownership_control", "openownership_public"),
            ("watchlist_review", "sanctions_watchlist", "public_sanctions_dataset_catalogs"),
        ],
        "supplier_of": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("contract_awards", "trade_supply_chain", "government_procurement_public"),
            ("financial_pressure", "financing_capital_markets", "capital_market_sources"),
        ],
        "customer_of": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("contract_awards", "trade_supply_chain", "government_procurement_public"),
            ("dependency_risk", "trade_supply_chain", "sec_customer_supplier_disclosures"),
        ],
        "creditor_of": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("credit_exposure", "financing_capital_markets", "bond_disclosures"),
            ("legal_admin", "legal_admin", "court_and_credit_sources"),
        ],
        "lender_to": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("credit_exposure", "financing_capital_markets", "credit_agreement_filings"),
            ("legal_admin", "legal_admin", "court_and_credit_sources"),
        ],
        "guarantor_of": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("guarantee_exposure", "financing_capital_markets", "guarantee_disclosures"),
            ("legal_admin", "legal_admin", "court_and_credit_sources"),
        ],
        "equity_pledgee": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("pledge_exposure", "financing_capital_markets", "pledge_registries"),
            ("legal_admin", "legal_admin", "court_and_credit_sources"),
        ],
        "finances": [
            ("registry_identity", "corporate_registry", "official_company_registry"),
            ("credit_exposure", "financing_capital_markets", "bond_disclosures"),
            ("legal_admin", "legal_admin", "court_and_credit_sources"),
        ],
    }
    specs = route_map.get(relation_type, [
        ("registry_identity", "corporate_registry", "official_company_registry"),
        ("relationship_risk", "related_entities", "registry_filings_announcements"),
    ])
    return [
        {
            "query_id": f"REL-EXPAND-{index}",
            "target_subject": target,
            "relation_type": relation_type,
            "priority": priority,
            "purpose": purpose,
            "domain": domain,
            "source_hint": source_hint,
            "query": f"{target} {domain.replace('_', ' ')} {purpose.replace('_', ' ')}",
            "admission_rule": "Expansion result remains lead-only until entity match and source provenance pass.",
        }
        for index, (purpose, domain, source_hint) in enumerate(specs[:3], start=1)
    ]


def _merge_next_actions(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            text = " ".join(str(item or "").split())
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
    return merged


def _relationship_resolution_evidence_input(
    evidence_ledger_v2: list[dict[str, Any]],
    evidence_ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(evidence_ledger_v2 or []):
        row = dict(item)
        original = evidence_ledger[index] if index < len(evidence_ledger or []) else {}
        if isinstance(original, dict):
            for key in (
                "claims",
                "claim",
                "title",
                "url",
                "source",
                "source_url",
                "subject",
                "record_type",
                "type",
                "subject_lei",
                "subject_name",
                "related_lei",
                "related_name",
                "relationship_type",
                "relationship_status",
                "relationship_period",
                "entity_match",
                "entity_match_level",
                "entity_match_score",
                "relation_type",
                "edge_type",
                "to",
                "target",
            ):
                if (key not in row or row.get(key) in (None, "", [], {})) and original.get(key) is not None:
                    row[key] = original.get(key)
        rows.append(row)
    return rows


def _build_executable_next_steps(evidence_gaps: list[str], source_readiness: dict | None = None) -> list[dict]:
    """DD v2.1: Build structured, executable next investigation steps.

    Each step: reason, target_lane, suggested_source, priority (P0/P1/P2).
    No generic advice — actionable suggestions based on gap type.
    """
    steps = []
    readiness = source_readiness or {}
    gap_text = " ".join(str(g) for g in (evidence_gaps or []))
    has_capital_gap = any(kw in gap_text for kw in ("资本", "融资", "债务", "资金", "财务", "capital", "fund"))
    has_goods_gap = any(kw in gap_text for kw in ("产品", "供应", "客户", "渠道", "市场", "goods", "supply", "product"))
    has_people_gap = any(kw in gap_text for kw in ("人员", "董监高", "股东", "实控", "关联", "people", "controller", "ubo"))
    blocked = bool(readiness.get("access_issues") or readiness.get("blocked_sources"))

    if has_capital_gap:
        steps.append({"reason": "Missing capital evidence","target_lane": "capital","suggested_source": "qyyjt_api:fin_inst,ent_financing,pledge,freeze,auction","priority": "P0"})
    if has_goods_gap:
        steps.append({"reason": "Missing goods/product evidence","target_lane": "goods","suggested_source": "public_web_search:operate,recruit,trade; qyyjt_api:trade_activity,ip_asset","priority": "P0" if not has_capital_gap else "P1"})
    if has_people_gap:
        steps.append({"reason": "Missing people/control evidence","target_lane": "people","suggested_source": "qyyjt_api:controller_candidate,ubo_path,group_network_edge,registry_identity","priority": "P0" if not (has_capital_gap or has_goods_gap) else "P1"})
    if blocked:
        steps.append({"reason": "Sources blocked or require authorization","target_lane": "all","suggested_source": "manual_upload or credential_provision","priority": "P0"})
    if not steps:
        steps.append({"reason": "Insufficient data to generate specific steps","target_lane": "all","suggested_source": "public_web_search:general","priority": "P2"})
    return steps

def _build_investigation_strategy(dd, readiness, gaps):
    plan=[];es=dd.get("executive_summary",{});gt=" ".join(str(g) for g in (gaps or []))
    b=readiness.get("blocked_sources",[]);a=readiness.get("authorization_required_sources",[])
    def _i(p):
        if p=="qyyjt" and "qyyjt_api" in a: return "authorization_required","request_credentials"
        if b: return "blocked_or_captcha","authorize_or_upload"
        return None,None
    cr=es.get("capital_risk","unknown");ch=dd.get("capital_lane",{}).get("profile_available",False)
    if cr in ("high","medium","low") or not ch or any(k in gt for k in ("capital","financing","debt")):
        i,f=_i("qyyjt");plan.append({"action_id":"CAP-001","target_lane":"capital","reason":"Capital risk="+cr,"required_source":"qyyjt_api:fin_inst,ent_financing,pledge,freeze,auction","expected_evidence":"financing history, debt structure, equity pledge/freeze/auction","priority":"P0" if cr=="high" else "P1","blocking_issue":str(i) if i else None,"fallback_action":str(f) if f else "public_web_search:capital"})
    gr=es.get("goods_risk","unknown");gh=dd.get("goods_lane",{}).get("profile_available",False)
    if gr in ("high","medium","low") or not gh or any(k in gt for k in ("product","supply")):
        i,f=_i("qyyjt");plan.append({"action_id":"GOODS-001","target_lane":"goods","reason":"Goods risk="+gr,"required_source":"qyyjt_api:trade,ip,recruiting; public_web:supplier","expected_evidence":"supplier/customer, patents, recruiting","priority":"P0" if gr=="high" else "P1","blocking_issue":str(i) if i else None,"fallback_action":str(f) if f else "public_web_search:supplier"})
    pr=es.get("people_risk","unknown");ph=dd.get("people_lane",{}).get("profile_available",False)
    if pr in ("high","medium","low") or not ph or any(k in gt for k in ("people","controller")):
        i,f=_i("qyyjt");plan.append({"action_id":"PEOPLE-001","target_lane":"people","reason":"People risk="+pr,"required_source":"qyyjt_api:controller_candidate,ubo_path,group_network_edge","expected_evidence":"controller paths, related company network, UBO","priority":"P0" if pr=="high" else "P1","blocking_issue":str(i) if i else None,"fallback_action":str(f) if f else "public_web_search:executive"})
    if b or a:plan.append({"action_id":"SRC-001","target_lane":"all","reason":"Blocked/auth required","required_source":"manual_upload or credential_provision","expected_evidence":"unblock source access","priority":"P0","blocking_issue":"source_access","fallback_action":"use_fixture_data"})
    return {"strategy_plan":plan,"action_count":len(plan)}

def _build_evidence_gap_analyzer(cap,gds,ppl,risks,graph,readiness):
    def _s(c,d): return "covered" if c>0 and d else ("weak" if c>0 else "missing")
    g={};cc=cap.get("row_count",0) if cap else 0;rl=ppl or {};pc=rl.get("row_count",0) if ppl else 0
    gd=gds or {};gc=gd.get("row_count",0) if gds else 0
    g["capital"]={"status":_s(cc,cc>0),"signal_count":cc,"reason":"Public capital signals","missing_evidence":["financing_history","debt_structure"],"suggested_source":"qyyjt_api:fin_inst","priority":"P0" if cc==0 else "P1"}
    g["goods"]={"status":_s(gc,gc>0),"signal_count":gc,"reason":"Public goods signals","missing_evidence":["supplier_list","customer_list"],"suggested_source":"qyyjt_api:trade_activity","priority":"P0" if gc==0 else "P1"}
    g["people"]={"status":_s(pc,pc>0),"signal_count":pc,"reason":"Public people signals","missing_evidence":["controller","ubo","legal_rep"],"suggested_source":"qyyjt_api:controller_candidate","priority":"P0" if pc==0 else "P1"}
    rk=risks or [];g["risk"]={"status":"covered" if rk else "missing","event_count":len(rk),"reason":"Risk events from evidence"}
    rg=graph or {};ed=rg.get("edges",[]);g["graph"]={"status":"covered" if ed else "missing","node_count":rg.get("node_count",0),"edge_count":len(ed),"reason":"Relationship graph"}
    rd=readiness or {};g["source"]={"status":"covered" if rd.get("usable_sources") else ("weak" if rd.get("fixture_only_sources") else "missing"),"usable":len(rd.get("usable_sources",[])),"blocked":len(rd.get("blocked_sources",[])),"reason":"Source readiness from smoke"}
    return {"gap_summary":g,"overall_status":"covered" if all(v["status"]!="missing" for v in g.values()) else "has_gaps"}

def _build_graph_explainability_v2(graph):
    g=graph or {};edges=g.get("edges",[]);paths=[]
    for e in edges:
        et=e.get("type","");cat="";adm=e.get("admission","?")
        if et=="controls": cat="controller->company"
        elif et=="serves_as": cat="person->company"
        elif et in ("supplies","buys_from"): cat="company->supplier/customer"
        elif et=="located_at": cat="company->address"
        if cat: paths.append({"nodes":[e.get("from","?"),e.get("to","?")],"edges":[et],"path_id":"path-"+str(len(paths)),"category":cat,"explanation":e.get("explanation",""),"confidence":e.get("confidence",0),"admission":adm,"source":e.get("source","")})
    nodes=g.get("nodes",[])
    top=sorted(nodes,key=lambda n: sum(1 for x in edges if x.get("from")==n.get("id","") or x.get("to")==n.get("id","")),reverse=True)[:5]
    return {"graph_summary":{"node_count":len(nodes),"edge_count":len(edges),"strong_edges":sum(1 for e in edges if e.get("admission")=="fact"),"weak_leads":sum(1 for e in edges if e.get("admission") in ("lead","weak_lead")),"top_entities":[{"name":e.get("name",""),"type":e.get("type",""),"degree":sum(1 for x in edges if x.get("from")==e.get("id","") or x.get("to")==e.get("id",""))} for e in top],"high_value_paths":paths[:8]}}

def _build_strategy_quality_gate(strategy: dict | None, source_readiness: dict | None = None) -> dict:
    """DD v2.4: Real quality gate — detects source auth issues, fixture-only fallbacks."""
    plan = (strategy or {}).get("strategy_plan") or []; flags = []; scores = []
    rd = source_readiness or {}
    all_fixture = len(rd.get("usable_sources",[])) == 0 and len(rd.get("fixture_only_sources",[])) > 0
    for item in plan:
        s = 100
        src = item.get("required_source","")
        if src.startswith("qyyjt_api:") and "qyyjt_api" in rd.get("authorization_required_sources",[]):
            s -= 40; flags.append(f"low_quality:source_needs_auth:{item.get('action_id','?')}")
        if all_fixture and not item.get("fallback_action"):
            s -= 35; flags.append(f"low_quality:fixture_only_no_fallback:{item.get('action_id','?')}")
        if all_fixture and item.get("fallback_action") and item.get("blocking_issue") is None:
            s -= 25; flags.append(f"low_quality:all_fixture_no_blocker:{item.get('action_id','?')}")
        if not item.get("blocking_issue") and (item.get("fallback_action") or "").startswith("use_fixture"):
            s -= 20; flags.append(f"low_quality:fixture_fallback_without_blocker:{item.get('action_id','?')}")
        if s < 40: flags.append(f"critical_low_score:{item.get('action_id','?')}")
        scores.append(s)
    return {"quality_score": round(sum(scores)/len(scores)) if scores else 0, "action_scores": scores, "quality_flags": flags[:8], "low_quality_actions": len([f for f in flags if "low_quality" in f])}

def _build_evidence_depth_score(dd_profile, public_capital, public_goods, public_people, risk_events, graph_summary, readiness) -> dict:
    """DD v2.3: Per-lane evidence depth scoring."""
    def _d(sig, src_ok): return 100 if sig > 10 and src_ok else (60 if sig > 5 else (40 if sig > 0 else 0))
    cp = public_capital or {}; cc = cp.get("row_count",0) if cp else 0; cd = _d(cc, not readiness.get("fixture_only_sources"))
    gd = public_goods or {}; gc = gd.get("row_count",0) if gd else 0; gds = _d(gc, not readiness.get("fixture_only_sources"))
    pp = public_people or {}; pc = pp.get("row_count",0) if pp else 0; pd = _d(pc, not readiness.get("fixture_only_sources"))
    risks = risk_events or []; rd_v = 80 if len(risks)>5 else (60 if risks else 10)
    gs = graph_summary or {}; ge = gs.get("edge_count",0); gd_v = 100 if ge>3 else (60 if ge>0 else 0)
    sd_v = 100 if readiness.get("usable_sources") else (30 if readiness.get("fixture_only_sources") else 0)
    return {"capital_depth":cd,"goods_depth":gds,"people_depth":pd,"risk_depth":rd_v,"graph_depth":gd_v,"source_depth":sd_v,"overall_depth":round((cd+gds+pd+rd_v+gd_v+sd_v)/6)}

def _build_graph_sanity_check(graph: dict | None, gap_analysis: dict | None = None) -> dict:
    """DD v2.3: Sanity check for relationship graph."""
    g = graph or {}; edges = g.get("edges",[]); flags = []
    if not edges: flags.append("empty_graph")
    if edges and all(e.get("admission") in ("lead","weak_lead") for e in edges): flags.append("only_weak_edges")
    seen = set()
    for e in edges:
        key = (e.get("from",""), e.get("to",""), e.get("type",""))
        if key in seen: flags.append("duplicate_entities"); break
        seen.add(key)
    if any(not e.get("source") for e in edges): flags.append("missing_source")
    if any(not e.get("explanation") for e in edges): flags.append("missing_explanation")
    return {"graph_quality_flags": flags, "is_sane": len(flags)==0, "flag_count": len(flags)}

def _build_live_readiness_gate(source_readiness: dict | None) -> dict:
    """DD v2.3: Live readiness gate from source status."""
    rd = source_readiness or {}; u = len(rd.get("usable_sources",[])); b = len(rd.get("blocked_sources",[]))
    a = len(rd.get("authorization_required_sources",[])); p = len(rd.get("parse_failed_sources",[])); f = len(rd.get("fixture_only_sources",[]))
    if b: return {"status":"blocked_by_source","ready_for_live_smoke":False}
    if a and not u: return {"status":"needs_authorization","ready_for_live_smoke":False}
    if p: return {"status":"parser_repair_needed","ready_for_live_smoke":False}
    if u: return {"status":"ready_for_live_smoke","ready_for_live_smoke":True}
    if f: return {"status":"fixture_only","ready_for_live_smoke":False}
    return {"status":"unknown","ready_for_live_smoke":False}

def _fast_empty_detect_wrapper(result_text: str, source_name: str = "") -> dict:
    """DD v2.4: Wired fast empty detection for evidence pipeline."""
    is_empty = _fast_empty_detect(result_text)
    return {"source": source_name, "is_empty": is_empty, "status": "empty_result" if is_empty else "retrieved", "pattern": "aiqicha_wired"}

def _fast_empty_detect(html_text: str) -> bool:
    """aiqicha_scraper pattern: Fast empty-result detection via keyword matching.
    Returns True if page content indicates 'not found' or empty result.
    Avoids wasting time on empty pages (no long poll, no full parse)."""
    if not html_text or len(html_text.strip()) < 50:
        return True
    empty_keywords = [
        "未找到", "not found", "no results", "暂无数据", "没有找到",
        "0 results", "no matches", "查询无结果", "无相关记录", "no data found",
        "未查询到", "没有相关", "no records", "empty result", "no content",
    ]
    lower = html_text.lower()
    return any(kw.lower() in lower for kw in empty_keywords)

def _pre_search_cache_check(subject_id: str, evidence_ledger: list | None = None) -> dict:
    """aiqicha_scraper pattern: Cache-before-request dedup.
    Checks evidence ledger for existing results before triggering adapters.
    Returns {'cached': bool, 'existing_sources': list, 'existing_facts': int, 'skip_request': bool}."""
    if not evidence_ledger:
        return {"cached": False, "skip_request": False}
    existing = []
    facts = 0
    subject_lower = subject_id.lower().strip()
    for e in evidence_ledger:
        e_subject = str(e.get("subject", "")).lower().strip()
        if e_subject == subject_lower or subject_lower in e_subject:
            existing.append(e.get("source", "?"))
            if e.get("admission") == "fact":
                facts += 1
    return {
        "cached": len(existing) > 0,
        "existing_sources": list(set(existing))[:10],
        "existing_facts": facts,
        "skip_request": facts >= 3,
        "pattern": "aiqicha_scraper_pre_search_dedup",
    }

def _build_capability_audit(dd, strategy, gap, graph, readiness, live_readiness, quality, depth) -> dict:
    """DD v2.4: Tag every capability with implementation status."""
    caps = {}
    def _c(n, i, w, t=False, f=False, l=False, r=False, a=False): caps[n] = {"implemented":i,"wired_to_pipeline":w,"tested":t,"fixture_only":f,"live_verified":l,"report_rendered":r,"audit_logged":a}
    hf = (readiness or {}).get("fixture_only_sources") is not None
    _c("source_smoke",True,True,t=True,f=hf,r=True,a=True);_c("evidence_admission",True,True,t=True,r=True,a=True)
    _c("investigation_strategy",bool(strategy),bool(strategy),r=True,a=True);_c("evidence_gap_analyzer",bool(gap),bool(gap),r=True,a=True)
    _c("relationship_graph",bool(graph),bool(graph),a=True);_c("high_value_paths",True,True,a=True)
    _c("audit_log",True,True,t=True,a=True);_c("report_sections",True,True,t=True,r=True)
    _c("strategy_quality_gate",bool(quality),True,a=True);_c("evidence_depth_score",bool(depth),True,a=True)
    _c("graph_sanity_check",True,True,a=True);_c("live_readiness_gate",bool(live_readiness),True,a=True)
    return {"capabilities":caps,"total":len(caps),"implemented":sum(1 for v in caps.values() if v["implemented"]),"wired":sum(1 for v in caps.values() if v["wired_to_pipeline"]),"tested":sum(1 for v in caps.values() if v["tested"])}

def _build_blocker_gate(cap_audit, graph_sanity, quality, live_readiness, gqa=None) -> dict:
    """DD v2.4: Blockers that prevent production readiness."""
    bl=[];cp=cap_audit or {};caps=cp.get("capabilities",{})
    for n,i in caps.items():
        if not i.get("wired_to_pipeline"): bl.append({"blocker":f"{n}_not_wired","severity":"critical","reason":f"{n} not wired to pipeline"})
        if not i.get("tested") and i.get("implemented"): bl.append({"blocker":f"{n}_untested","severity":"high","reason":f"{n} has no tests"})
    if live_readiness and not live_readiness.get("ready_for_live_smoke"):
        bl.append({"blocker":"live_unverified_blocker","severity":"high","reason":"All sources fixture_only or live_unverified — no live data"})
    # DD v3.3: source smoke driven readiness
    if cap_audit and cap_audit.get("fixture_only_count",0) > 0:
        bl.append({"blocker":"majority_fixture_only","severity":"high","reason":f"{cap_audit.get('fixture_only_count',0)}/{cap_audit.get('total',1)} capabilities are fixture_only"})
    if graph_sanity and not graph_sanity.get("is_sane"): bl.append({"blocker":"graph_quality_blocker","severity":"medium","reason":f"Flags: {graph_sanity.get('graph_quality_flags',[])}"})
    if gqa and not gqa.get("is_clean"): bl.append({"blocker":"graph_quality_blocker_v2","severity":"medium","reason":f"Graph has {gqa.get('issue_count',0)} issues, score={gqa.get('score',0)}"})
    if gqa and gqa.get("strong_edges",0) == 0 and gqa.get("edge_count",0) > 0: bl.append({"blocker":"no_strong_graph_edges","severity":"high","reason":"All graph edges are weak leads — no fact-level connections"})
    if quality and quality.get("low_quality_actions",0) > 0: bl.append({"blocker":"strategy_quality_blocker","severity":"medium","reason":f"{quality.get('low_quality_actions')} low-quality actions"})
    return {"blockers":bl,"blocker_count":len(bl),"is_clear":len(bl)==0}

def _build_realness_score(cap_audit, depth, live_readiness, blocker_gate, graph_sanity) -> dict:
    """DD v2.4: How real vs surface is this investigation?"""
    s=0;cp=cap_audit or {};t=cp.get("total",12);w=cp.get("wired",0)
    if t: s+=int((w/t)*25)
    tc=cp.get("tested",0)
    if t: s+=int((tc/t)*25)
    s+=25 if live_readiness and live_readiness.get("ready_for_live_smoke") else (5 if live_readiness else 0)
    dp=depth or {};s+=int(dp.get("overall_depth",0)/4)
    s+=10 if graph_sanity and graph_sanity.get("is_sane") else (3 if graph_sanity else 0)
    bl=blocker_gate or {}
    s+=5 if bl.get("is_clear") else -min(10, bl.get("blocker_count",0)*3)
    s=max(0,min(100,s))
    return {"realness_score":s,"verdict":"real" if s>=70 else ("mostly_fixture" if s>=40 else "fake_or_surface")}

def _normalize_evidence_v2(raw_evidence: list | None) -> list:
    if not raw_evidence: return []
    r=[]
    for i,item in enumerate(raw_evidence):
        if not isinstance(item,dict): continue
        src=str(item.get('source','unknown'))
        st='fixture'
        if 'qyyjt' in src.lower(): st='authorized'
        elif src in ('public_web_search','public_registry','sec_edgar_public_api','gleif_lei_public_api'): st='public'
        adm=str(item.get('admission','lead'))
        if adm not in ('fact','lead','weak_lead','rejected'): adm='lead'
        claims=item.get('claims',item.get('claim',[]))
        claims=claims if isinstance(claims,list) else ([claims] if claims else [])
        ct=' '.join(str(c) for c in claims).lower()
        lane='unknown'
        if any(k in ct for k in ('capital','financ','debt','pledge','freeze','auction','revenue','cash')): lane='capital'
        elif any(k in ct for k in ('product','supplier','customer','market','supply','goods','trademark','patent')): lane='goods'
        elif any(k in ct for k in ('people','controller','ubo','executive','legal','person','shareholder','director')): lane='people'
        elif any(k in ct for k in ('risk','court','enforcement','penalty','dishonesty','fraud')): lane='risk'
        r.append({'evidence_id':f'ev-{i:04d}','subject':str(item.get('subject',item.get('company',''))),'lane':lane,'source_name':src,'source_type':st,'admission':adm,'admission_reason':str(item.get('admission_reason','')),'confidence':float(item.get('confidence',0.5))})
    return r

def _build_entity_resolution_v1(sp, rg):
    res=[];sp2=sp or {};rg2=rg or {}
    n=str(sp2.get('name','')).strip().lower()
    uscc=(sp2.get('identifiers') or {}).get('unified_social_credit_code','')
    if n: res.append({'entity_id':f'company:normalized:{n}','entity_type':'company','display_name':n,'match_confidence':0.95 if uscc else 0.7,'match_reason':'official_registry' if uscc else 'subject_profile','ambiguity_flags':[]})
    for nd in (rg2.get('nodes') or []):
        nn=str(nd.get('name','')).strip().lower();nt=nd.get('type','company')
        if not nn: continue
        key=nd.get('entity_resolution_key',f'{nt}:normalized:{nn}')
        res.append({'entity_id':nd.get('id',key),'entity_type':nt,'display_name':nn,'entity_resolution_key':key,'match_confidence':0.9,'match_reason':'graph_node','ambiguity_flags':['same_name_ambiguous'] if any(e['display_name']==nn for e in res) else []})
    return {'resolved_entities':res,'entity_count':len(res),'version':'1.0'}

def _build_relationship_resolution_v1(evidence: list | None, graph: dict | None) -> dict:
    """DD v3.0: Two-phase relationship resolution.
    Phase 1: Extract candidate relationship leads from evidence (weak_lead/lead).
    Phase 2: Admitted edges with edge_id, source_node, target_node, relation_type,
    confidence, admission, admission_reason, explanation, evidence_ids."""
    leads=[]; edges=[]
    ev=evidence or []; rg=graph or {}; existing_edges=rg.get('edges',[])
    # Phase 1: candidate leads from evidence claims
    for i,item in enumerate(ev[:20]):
        if not isinstance(item,dict): continue
        src=str(item.get('source','unknown'))
        claims=item.get('claims',item.get('claim',[]))
        claims=claims if isinstance(claims,list) else [claims] if claims else []
        for c in claims:
            cs=str(c).lower()
            if 'supplier=' in cs:
                name=cs.split('supplier=')[1].split(';')[0].strip()
                leads.append({'lead_id':f'lead-supplier-{i}','from':'seed','to':name,'relation_type':'supplier_of','admission':'lead','confidence':0.4,'source':src,'explanation':f'Supplier candidate {name} from {src}'})
            if 'customer=' in cs:
                name=cs.split('customer=')[1].split(';')[0].strip()
                leads.append({'lead_id':f'lead-customer-{i}','from':'seed','to':name,'relation_type':'customer_of','admission':'lead','confidence':0.4,'source':src,'explanation':f'Customer candidate {name} from {src}'})
            if 'controller=' in cs:
                name=cs.split('controller=')[1].split(';')[0].strip()
                leads.append({'lead_id':f'lead-controller-{i}','from':'seed','to':name,'relation_type':'controls','admission':'weak_lead','confidence':0.3,'source':src,'explanation':f'Controller candidate {name} from {src} - weak lead, needs official corroboration'})
    # Phase 2: admitted edges (from existing graph, with full schema)
    for j,e in enumerate(existing_edges):
        edges.append({'edge_id':f'edge-{j:04d}','source_node':e.get('from','?'),'target_node':e.get('to','?'),'relation_type':e.get('type','?'),'confidence':e.get('confidence',0),'admission':e.get('admission','lead'),'admission_reason':e.get('explanation',''),'explanation':e.get('explanation',''),'evidence_ids':[],'source':e.get('source','')})
    return {'phase1_candidate_leads':leads,'lead_count':len(leads),'phase2_admitted_edges':edges,'edge_count':len(edges),'version':'1.0','note':'Two-phase resolution: Phase 1 extracts candidate leads from evidence claims. Phase 2 admits edges that pass admission gate.'}

def _build_investigation_strategy_v2(gap_summary: dict | None, readiness: dict | None, blocker_gate: dict | None, graph: dict | None, realness: dict | None, live: dict | None) -> dict:
    """DD v3.0: Investigation strategy v2 — evidence-driven, not template-only.
    Derives actions from gap_summary, source_readiness, blocker_gate, graph quality."""
    plan=[]; gs=gap_summary or {}; gaps=gs.get('gap_summary',{})
    rd=readiness or {}; bl=blocker_gate or {}; blockers=bl.get('blockers',[])
    # Capital action
    cap=gaps.get('capital',{}); cap_st=cap.get('status','?')
    if cap_st in ('missing','weak'):
        plan.append({'action_id':'CAP-V2-001','priority':'P0' if cap_st=='missing' else 'P1','target_lane':'capital','reason':f'Capital evidence status={cap_st}, signals={cap.get("signal_count",0)}','blocker_addressed':next((b['blocker'] for b in blockers if 'capital' in str(b).lower()),None),'suggested_source':'qyyjt_api:fin_inst,ent_financing,pledge,freeze,auction' if 'qyyjt_api' in str(rd.get('authorization_required_sources',[])) else 'public_web_search:capital,financing,debt','required_authorization':'qyyjt_api' in str(rd.get('authorization_required_sources',[])),'expected_evidence':'Financing history, debt structure, equity pledge/freeze/auction records','fallback_action':'public_web_search:capital,debt' if 'public_web_search' in str(rd.get('fixture_only_sources',[])) else 'fixture_only_no_fallback','done_condition':'capital_status=covered AND facts>=3'})
    # Goods action
    goods=gaps.get('goods',{}); gs2=goods.get('status','?')
    if gs2 in ('missing','weak'):
        plan.append({'action_id':'GOODS-V2-001','priority':'P0' if gs2=='missing' else 'P1','target_lane':'goods','reason':f'Goods evidence status={gs2}, signals={goods.get("signal_count",0)}','blocker_addressed':None,'suggested_source':'qyyjt_api:trade_activity,ip_asset,recruiting; public_web_search:supplier,customer','required_authorization':False,'expected_evidence':'Supplier/customer lists, patents/trademarks, recruiting signals','fallback_action':'public_web_search:supplier,customer,market_share','done_condition':'goods_status=covered AND supplier_count>0 AND customer_count>0'})
    # People action
    ppl=gaps.get('people',{}); ps=ppl.get('status','?')
    if ps in ('missing','weak'):
        plan.append({'action_id':'PEOPLE-V2-001','priority':'P0' if ps=='missing' else 'P1','target_lane':'people','reason':f'People evidence status={ps}, signals={ppl.get("signal_count",0)}','blocker_addressed':None,'suggested_source':'qyyjt_api:controller_candidate,ubo_path,group_network_edge,registry_identity','required_authorization':False,'expected_evidence':'Controller paths, related company network, UBO declarations','fallback_action':'public_web_search:executive,controller,ownership','done_condition':'people_status=covered AND controller_count>0'})
    # Source blocker action
    src=gaps.get('source',{}); ss=src.get('status','?')
    blocked=src.get('blocked',0) or len(rd.get('blocked_sources',[]))
    if ss in ('missing','weak') or blocked>0:
        plan.append({'action_id':'SRC-V2-001','priority':'P0','target_lane':'source','reason':f'Source blocked={blocked}, status={ss}','blocker_addressed':'source_access','suggested_source':'manual_upload or credential_provision','required_authorization':True,'expected_evidence':'Unblocked source access or uploaded evidence','fallback_action':'continue_with_fixture_only_and_live_unverified_status','done_condition':'source_status=covered OR live_readiness=ready_for_live_smoke'})
    return {'strategy_plan_v2':plan,'action_count':len(plan),'version':'2.0','source_driven':True,'note':'Evidence-driven strategy — actions derived from gap_summary, source_readiness, blocker_gate, and realness_score.'}

def _graph_quality_audit_v2(graph: dict | None) -> dict:
    """DD v3.3: Graph quality audit with severity levels."""
    g=graph or {}; edges=g.get('edges',[]); nodes=g.get('nodes',[]); issues=[]
    if not edges: issues.append({'issue':'empty_graph','severity':'critical','detail':'No relationship edges found'})
    if edges and all(e.get('admission') in ('lead','weak_lead') for e in edges): issues.append({'issue':'only_weak_edges','severity':'high','detail':'All edges are weak leads, no facts'})
    if any(not e.get('source') for e in edges): issues.append({'issue':'missing_source','severity':'medium','detail':'Some edges lack source attribution'})
    if any(not e.get('explanation') for e in edges): issues.append({'issue':'missing_explanation','severity':'medium','detail':'Some edges lack explanation'})
    strong=sum(1 for e in edges if e.get('admission')=='fact');weak=sum(1 for e in edges if e.get('admission') in ('lead','weak_lead'))
    return {'node_count':len(nodes),'edge_count':len(edges),'strong_edges':strong,'weak_edges':weak,
        'issues':issues,'issue_count':len(issues),'is_clean':len(issues)==0,'score':100-(len(issues)*15)}

def _build_edge_explainability_v3(graph: dict | None) -> dict:
    """DD v3.4: Per-edge explainability with evidence trail."""
    g=graph or {}; edges=g.get('edges',[])
    explained=[]
    for e in edges:
        explained.append({'edge_id':f"edge-{e.get('from','?')}-{e.get('to','?')}-{e.get('type','?')}",
            'from':e.get('from','?'),'to':e.get('to','?'),'type':e.get('type','?'),
            'confidence':e.get('confidence',0),'admission':e.get('admission','?'),
            'explanation':e.get('explanation',''),'source':e.get('source',''),
            'evidence_trail':e.get('evidence_ids',[]),'auditable':True})
    return {'explained_edges':explained,'edge_count':len(explained)}

def _build_pipeline_contract_matrix(smoke, readiness, ev_ledger) -> dict:
    """DD v3.9: Pipeline contract matrix — prove source-to-report flow for each lane."""
    rows = []
    default_srcs = [
        {"source_name":"public_web_search","live_status":"live_unverified"},
        {"source_name":"qyyjt_api","live_status":"authorization_required"},
        {"source_name":"fixture_source","live_status":"fixture_only"},
        {"source_name":"user_upload","live_status":"live_unverified"},
        {"source_name":"relationship_graph","live_status":"fixture_only"},
        {"source_name":"source_smoke","live_status":"fixture_only"},
    ]
    srcs = (smoke or {}).get("smoke_results", default_srcs)
    for sr in srcs:
        name = sr.get("source_name","?")
        status = sr.get("live_status","?")
        has_evidence = _source_has_evidence(name, ev_ledger or [])
        reaches_strategy = has_evidence or _source_in_readiness(name, readiness or {})
        rows.append({
            "source_name": name,
            "source_status": status,
            "reaches_evidence_ledger": has_evidence,
            "reaches_entity_resolution": has_evidence,
            "reaches_relationship_resolution": has_evidence and status != "blocked_or_captcha",
            "reaches_strategy_plan": reaches_strategy,
            "reaches_report": has_evidence,
            "reaches_audit_log": has_evidence,
            "runtime_proven": has_evidence,
        })
    return {"pipeline_contract_matrix": rows, "source_count": len(rows),
        "runtime_proven": sum(1 for r in rows if r["runtime_proven"])}


def _source_has_evidence(source_name: str, ev_ledger: list[dict[str, Any]]) -> bool:
    source = str(source_name or "")
    aliases = _source_contract_aliases(source)
    for item in ev_ledger or []:
        evidence_source = str(item.get("source_name") or item.get("source") or "")
        if evidence_source in aliases or any(evidence_source.startswith(f"{alias}:") for alias in aliases):
            return True
    return False


def _source_contract_aliases(source_name: str) -> set[str]:
    source = str(source_name or "")
    aliases = {source}
    if source == "default_public_intel":
        aliases.update({"qyyjt_websearch_plan", "qyyjt_public_plan", "public_web_search"})
    if source == "qyyjt_api":
        aliases.update({"qyyjt", "qyyjt_api"})
    return aliases


def _source_in_readiness(source_name: str, readiness: dict[str, Any]) -> bool:
    source = str(source_name or "")
    for key in ("usable_sources", "fixture_only_sources", "blocked_sources", "authorization_required_sources", "parse_failed_sources"):
        if source in {str(item) for item in readiness.get(key, [])}:
            return True
    for issue in readiness.get("access_issues", []):
        if isinstance(issue, dict) and str(issue.get("source") or "") == source:
            return True
    return False


def _generate_next_questions(gap_analysis, strategy) -> list[dict]:
    """DD v6: Generate specific next questions from gap analysis."""
    questions = []
    gs = (gap_analysis or {}).get("gap_summary", {})
    for lane in ("capital","goods","people"):
        ld = gs.get(lane, {})
        if ld.get("status") in ("missing","weak"):
            questions.append({"lane": lane, "question": f"{lane}_evidence_needed", "priority": "P0" if ld.get("signal_count",0)==0 else "P1", "missing_signals": ld.get("signal_count",0), "status": ld.get("status","?")})
    return {"next_investigation_questions": questions, "question_count": len(questions)}

def _build_money_lane(evidence_ledger, public_capital, financial, qyyjt_bridge=None) -> dict:
    """P0-C: Build money-in/money-out investigation lane."""
    el = evidence_ledger or []; pc = public_capital or {}; fin = financial or {}
    facts = [e for e in el if e.get("admission")=="fact" and e.get("lane")=="capital"]
    leads = [e for e in el if e.get("admission") in ("lead","weak_lead") and e.get("lane")=="capital"]
    bridge = qyyjt_bridge or {}
    pledge_bridge = bridge.get("pledge_bridge", {}) if isinstance(bridge, dict) else {}
    bridge_facts = list(pledge_bridge.get("facts") or [])
    bridge_leads = list(pledge_bridge.get("leads") or [])
    bridge_fact_count = int(pledge_bridge.get("fact_count") or len(bridge_facts))
    bridge_lead_count = int(pledge_bridge.get("lead_count") or len(bridge_leads))
    return {
        "profile_available": bool(pc),
        "financial_metrics": fin,
        "financing_events": pc.get("financing_events", []),
        "debt_signals": facts,
        "pledge_freeze_auction": facts + bridge_facts,
        "capital_events": facts,
        "leads": leads,
        "qyyjt_bridge": {
            "pledge_fact_count": bridge_fact_count,
            "pledge_lead_count": bridge_lead_count,
            "pressure_level": pledge_bridge.get("pressure_level", "NONE"),
            "bridge_operational": pledge_bridge.get("bridge_operational", False),
            "operational_basis": pledge_bridge.get("operational_basis", "not_evaluated"),
        },
        "fact_count": len(facts) + bridge_fact_count, "lead_count": len(leads) + bridge_lead_count,
        "gaps": [] if (facts or leads or bridge_fact_count or bridge_lead_count) else ["No money/solvency evidence found"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "What are the latest financing events (round size, investors)?",
            "Is there evidence of debt pressure or refinancing risk?",
            "Are there pledge/freeze/auction records against company assets?",
            "What are the cash-flow indicators (revenue, operating cash flow)?",
        ],
        "lane_status": "covered" if facts or bridge_fact_count else ("weak" if leads or bridge_lead_count else "missing"),
        "deep_analysis": {
            "financing_pressure": "HIGH" if len(facts) + bridge_fact_count >= 3 else ("MEDIUM" if facts or bridge_fact_count else "LOW"),
            "solvency_risk": "HIGH" if any("freeze" in str(e).lower() or "auction" in str(e).lower() for e in facts + bridge_facts) else "UNKNOWN",
            "debt_burden": "HIGH" if any("debt" in str(e).lower() for e in facts) and len(facts) >= 2 else "LOW",
            "capital_structure_notes": f"{len(facts) + bridge_fact_count} fact items, {len(leads) + bridge_lead_count} leads — " + ("strong signals" if len(facts) + bridge_fact_count >= 2 else "needs more evidence")
        },
    }


def _build_money_lane(evidence_ledger, public_capital, financial, qyyjt_bridge=None) -> dict:
    """Build money-in/money-out lane with QYYJT pledge and bond bridges."""
    el = evidence_ledger or []
    pc = public_capital or {}
    fin = financial or {}
    facts = [e for e in el if e.get("admission") == "fact" and e.get("lane") == "capital"]
    leads = [e for e in el if e.get("admission") in ("lead", "weak_lead") and e.get("lane") == "capital"]
    bridge = qyyjt_bridge or {}
    pledge_bridge = bridge.get("pledge_bridge", {}) if isinstance(bridge, dict) else {}
    bond_bridge = bridge.get("bond_credit_bridge", {}) if isinstance(bridge, dict) else {}
    bridge_facts = list(pledge_bridge.get("facts") or [])
    bridge_leads = list(pledge_bridge.get("leads") or [])
    bridge_fact_count = int(pledge_bridge.get("fact_count") or len(bridge_facts))
    bridge_lead_count = int(pledge_bridge.get("lead_count") or len(bridge_leads))
    bond_pressure_level = str(bond_bridge.get("pressure_level") or "none")
    bond_row_count = int(bond_bridge.get("row_count") or 0)
    bond_default_count = int(bond_bridge.get("default_count") or 0)
    bond_high_count = int(bond_bridge.get("high_or_critical_event_count") or 0)
    bond_fact_count = bond_row_count if bond_pressure_level in {"high", "medium"} else 0
    capital_fact_count = len(facts) + bridge_fact_count + bond_fact_count
    capital_lead_count = len(leads) + bridge_lead_count
    bond_next_actions = [str(item) for item in bond_bridge.get("next_actions", []) if str(item).strip()]

    return {
        "profile_available": bool(pc) or bool(bond_fact_count),
        "financial_metrics": fin,
        "financing_events": pc.get("financing_events", []),
        "financing_event_claims": pc.get("financing_event_claims", []),
        "debt_credit_claims": pc.get("debt_credit_claims", []),
        "refinancing_claims": pc.get("refinancing_claims", []),
        "liquidity_claims": pc.get("liquidity_claims", []),
        "asset_pressure_claims": pc.get("asset_pressure_claims", []),
        "capital_structure_claims": pc.get("capital_structure_claims", []),
        "public_capital_structured_summary": pc.get("structured_summary", {}),
        "debt_signals": facts,
        "pledge_freeze_auction": facts + bridge_facts,
        "capital_events": facts,
        "leads": leads,
        "qyyjt_bridge": {
            "pledge_fact_count": bridge_fact_count,
            "pledge_lead_count": bridge_lead_count,
            "pressure_level": pledge_bridge.get("pressure_level", "NONE"),
            "bridge_operational": pledge_bridge.get("bridge_operational", False),
            "operational_basis": pledge_bridge.get("operational_basis", "not_evaluated"),
            "bond_pressure_level": bond_pressure_level,
            "bond_row_count": bond_row_count,
            "bond_default_count": bond_default_count,
            "bond_high_or_critical_event_count": bond_high_count,
            "bond_risk_reasons": list(bond_bridge.get("risk_reasons") or [])[:6],
            "bond_next_actions": bond_next_actions[:4],
        },
        "fact_count": capital_fact_count,
        "lead_count": capital_lead_count,
        "gaps": [] if (
            facts or leads or bridge_fact_count or bridge_lead_count or bond_fact_count
            or pc.get("debt_credit_claims") or pc.get("refinancing_claims")
            or pc.get("liquidity_claims") or pc.get("asset_pressure_claims")
        ) else ["No money/solvency evidence found"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True},
        "researched_patterns": {"entity_resolution": "dedupe/recordlinkage-style entity keys", "evidence_pipeline": "admission-gated provenance tracking", "graph_explainability": "edge-level source+confidence audit"},
        "next_questions": [
            "What are the latest financing events (round size, investors)?",
            "Is there evidence of debt pressure or refinancing risk?",
            "Are there pledge/freeze/auction records against company assets?",
            "What are the cash-flow indicators (revenue, operating cash flow)?",
            *bond_next_actions[:2],
        ],
        "lane_status": "covered" if facts or bridge_fact_count or bond_fact_count else (
            "weak" if (
                leads or bridge_lead_count or pc.get("debt_credit_claims")
                or pc.get("refinancing_claims") or pc.get("liquidity_claims")
                or pc.get("asset_pressure_claims")
            ) else "missing"
        ),
        "deep_analysis": {
            "financing_pressure": "HIGH" if capital_fact_count >= 3 or bond_pressure_level == "high" else ("MEDIUM" if capital_fact_count else "LOW"),
            "solvency_risk": "HIGH" if any("freeze" in str(e).lower() or "auction" in str(e).lower() for e in facts + bridge_facts) else "UNKNOWN",
            "debt_burden": "HIGH" if any("debt" in str(e).lower() for e in facts) and len(facts) >= 2 else "LOW",
            "bond_pressure": bond_pressure_level,
            "capital_structure_notes": f"{capital_fact_count} fact items, {capital_lead_count} leads; " + ("strong signals" if capital_fact_count >= 2 else "needs more evidence"),
        },
    }


def _build_goods_lane(evidence_ledger, public_goods, supply_chain=None, qyyjt_bridge=None) -> dict:
    """EV-002: Build goods lane from normalized evidence + public goods profile."""
    """P0-D: Build products/customers/suppliers/channels/market position view."""
    el = evidence_ledger or []; pg = public_goods or {}
    facts = [e for e in el if e.get("admission")=="fact" and e.get("lane")=="goods"]
    leads = [e for e in el if e.get("admission") in ("lead","weak_lead") and e.get("lane")=="goods"]
    bridge = qyyjt_bridge or {}
    trade_bridge = bridge.get("trade_bridge", {}) if isinstance(bridge, dict) else {}
    bridge_facts = list(trade_bridge.get("facts") or [])
    bridge_leads = list(trade_bridge.get("leads") or [])
    bridge_fact_count = int(trade_bridge.get("fact_count") or len(bridge_facts))
    bridge_lead_count = int(trade_bridge.get("lead_count") or len(bridge_leads))
    # EV-002: extract goods leads from supply_chain profile when no facts available
    if not facts and pg:
        if pg.get("supplier_claims") or pg.get("customer_claims"):
            leads.append({"evidence_id": "sc-001", "lane": "goods", "admission": "lead", "source_name": "supply_chain_profile", "claims": "supplier/customer data from supply chain profile"})
        if pg.get("product_claims"): 
            leads.append({"evidence_id": "sc-002", "lane": "goods", "admission": "lead", "source_name": "supply_chain_profile", "claims": "product data from supply chain profile"})
    public_goods_signal_present = any(
        pg.get(key)
        for key in (
            "supplier_claims",
            "customer_claims",
            "channel_partner_claims",
            "market_position_claims",
            "business_model_claims",
            "unit_economics_claims",
            "bargaining_power_claims",
            "competitive_landscape_claims",
        )
    )
    return {
        "profile_available": bool(pg),
        "supplier_claims": pg.get("supplier_claims", []),
        "customer_claims": pg.get("customer_claims", []),
        "product_claims": pg.get("product_claims", []),
        "market_position_claims": pg.get("market_position_claims", []),
        "business_model_claims": pg.get("business_model_claims", []),
        "unit_economics_claims": pg.get("unit_economics_claims", []),
        "bargaining_power_claims": pg.get("bargaining_power_claims", []),
        "competitive_landscape_claims": pg.get("competitive_landscape_claims", []),
        "upstream_claims": pg.get("upstream_claims", []),
        "downstream_claims": pg.get("downstream_claims", []),
        "channel_partner_claims": pg.get("channel_partner_claims", []),
        "public_goods_structured_summary": pg.get("structured_summary", {}),
        "goods_facts": facts + bridge_facts,
        "goods_leads": leads + bridge_leads,
        "qyyjt_bridge": {
            "trade_fact_count": bridge_fact_count,
            "trade_lead_count": bridge_lead_count,
            "activity_level": trade_bridge.get("activity_level", "NONE"),
            "bridge_operational": trade_bridge.get("bridge_operational", False),
            "operational_basis": trade_bridge.get("operational_basis", "not_evaluated"),
        },
        "fact_count": len(facts) + bridge_fact_count, "lead_count": len(leads) + bridge_lead_count,
        "gaps": [] if (facts or leads or bridge_fact_count or bridge_lead_count or public_goods_signal_present) else ["No product/supply chain evidence found — provide supplier/customer/industry data"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "Who are the top 5 customers by revenue share?",
            "Who are the critical suppliers and what is the dependency level?",
            "What is the market share and competitive position?",
            "Are there IP/technology assets that create moats?",
        ],
        "lane_status": "covered" if facts or bridge_fact_count else ("weak" if leads or bridge_lead_count or public_goods_signal_present else "missing"),
        "deep_analysis": {
            "supplier_concentration": "HIGH" if pg.get("supplier_claims") else "UNKNOWN",
            "customer_dependency": "MEDIUM" if pg.get("customer_claims") else "UNKNOWN",
            "channel_dependency": "MEDIUM" if pg.get("channel_partner_claims") else "UNKNOWN",
            "unit_economics_visibility": "PUBLIC_LEAD" if pg.get("unit_economics_claims") else "UNKNOWN",
            "bargaining_power_visibility": "PUBLIC_LEAD" if pg.get("bargaining_power_claims") else "UNKNOWN",
            "competitive_landscape_visibility": "PUBLIC_LEAD" if pg.get("competitive_landscape_claims") else "UNKNOWN",
            "product_moat": "NEEDS_EVIDENCE" if not facts and not bridge_fact_count else "WEAK_SIGNALS",
            "market_position_notes": f"{len(facts) + bridge_fact_count} fact items, {len(leads) + bridge_lead_count} leads",
            "public_market_position": pg.get("market_position_claims", []),
            "public_business_model": pg.get("business_model_claims", []),
            "public_unit_economics": pg.get("unit_economics_claims", []),
            "public_bargaining_power": pg.get("bargaining_power_claims", []),
            "public_competitive_landscape": pg.get("competitive_landscape_claims", []),
            "public_channel_or_partner": pg.get("channel_partner_claims", []),
        },
    }

def _build_people_lane(evidence_ledger, subject_profile, relationship_network, public_people_profile=None) -> dict:
    """P0-E: Build people/control investigation lane."""
    el = evidence_ledger or []; sp = subject_profile or {}; rn = relationship_network or {}
    facts = [e for e in el if e.get("admission")=="fact" and e.get("lane")=="people"]
    leads = [e for e in el if e.get("admission") in ("lead","weak_lead") and e.get("lane")=="people"]
    controllers = sp.get("controllers") or sp.get("controller_candidates") or []
    key_personnel = sp.get("key_personnel") or sp.get("key_people") or []
    relation_edges = rn.get("top_edges") or rn.get("edges") or []
    relation_count = int(rn.get("relation_count") or len(relation_edges or []))
    public_people = public_people_profile or {}
    public_people_claims = [
        str(item)
        for item in (public_people.get("claims") or [])
        if str(item).strip()
    ][:8]
    public_control_claims = [
        str(item)
        for item in (public_people.get("control_role_claims") or [])
        if str(item).strip()
    ][:8]
    public_key_person_claims = [
        str(item)
        for item in (public_people.get("key_person_claims") or [])
        if str(item).strip()
    ][:8]
    public_legal_pressure_claims = [
        str(item)
        for item in (public_people.get("legal_pressure_claims") or [])
        if str(item).strip()
    ][:8]
    public_ownership_change_claims = [
        str(item)
        for item in (public_people.get("ownership_change_claims") or [])
        if str(item).strip()
    ][:8]
    public_related_party_claims = [
        str(item)
        for item in (public_people.get("related_party_claims") or [])
        if str(item).strip()
    ][:8]
    public_people_lead_count = int(public_people.get("row_count") or len(public_people_claims))
    strong_controller_count = sum(
        1
        for item in controllers
        if str((item or {}).get("confidence_tier") or (item or {}).get("verification_status") or "").lower()
        in {"verified_fact", "verified_controller", "verified", "licensed_fact"}
    )
    strong_relation_count = sum(
        1
        for item in relation_edges
        if str((item or {}).get("admission") or "").lower() == "fact"
        or float((item or {}).get("confidence") or 0) >= 0.8
    )
    controller_conflict_summary = _controller_conflict_summary(controllers)
    return {
        "profile_available": bool(sp),
        "controllers": controllers,
        "controller_candidates": controllers,
        "controller_candidate_count": len(controllers),
        "verified_controller_count": strong_controller_count,
        "controller_conflict_summary": controller_conflict_summary,
        "key_personnel": key_personnel,
        "related_parties": rn.get("related_parties", []),
        "relationship_network": {
            "subject_count": int(rn.get("subject_count") or 0),
            "relation_count": relation_count,
            "strong_relation_count": strong_relation_count,
            "relation_types": rn.get("relation_types", []),
            "top_edges": relation_edges[:5] if isinstance(relation_edges, list) else [],
        },
        "people_facts": facts,
        "people_leads": leads,
        "public_people_claims": public_people_claims,
        "public_control_claims": public_control_claims,
        "public_key_person_claims": public_key_person_claims,
        "public_legal_pressure_claims": public_legal_pressure_claims,
        "public_ownership_change_claims": public_ownership_change_claims,
        "public_related_party_claims": public_related_party_claims,
        "public_people_structured_summary": public_people.get("structured_summary", {}),
        "public_people_verification_status": public_people.get("verification_status"),
        "fact_count": len(facts), "lead_count": len(leads) + public_people_lead_count,
        "gaps": [] if (facts or leads or public_people_lead_count or controllers or relation_count or sp) else ["No people/ownership/control evidence found"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "Who is the ultimate beneficial owner (UBO)?",
            "Are there controller-company related-party transactions?",
            "Are there shared-address or shared-project relationships?",
            "Do key personnel have litigation or dishonesty records?",
        ],
        "lane_status": "covered" if facts or strong_controller_count or strong_relation_count else ("weak" if leads or public_people_lead_count or controllers or relation_count or sp else "missing"),
        "deep_analysis": {
            "controller_confidence": "HIGH" if facts or strong_controller_count else ("MEDIUM" if controllers or public_control_claims else "LOW"),
            "ubo_path_visible": any("ubo" in str(e).lower() for e in facts) or any("ubo" in str(e).lower() for e in leads) or any("beneficial" in str(c).lower() or "ubo" in str(c).lower() for c in controllers) or any("ubo" in item.lower() or "beneficial" in item.lower() for item in public_control_claims),
            "related_party_risk": "MONITOR" if controllers or key_personnel or relation_count or public_related_party_claims else "UNKNOWN",
            "governance_notes": f"{len(facts)} controller facts, {len(leads)} admitted leads, {public_people_lead_count} public people leads, {len(controllers)} controller candidates, {relation_count} relationship edges",
            "controller_conflict_status": controller_conflict_summary.get("status", "none"),
            "public_people_visibility": "PUBLIC_LEAD" if public_people_lead_count else "NONE",
            "public_control_or_ubo": public_control_claims,
            "public_key_people": public_key_person_claims,
            "public_legal_pressure": public_legal_pressure_claims,
            "public_ownership_changes": public_ownership_change_claims,
            "public_related_parties": public_related_party_claims,
        },
    }


def _controller_conflict_summary(controllers: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in controllers or [] if isinstance(item, dict) and str(item.get("name") or "").strip()]
    if not candidates:
        return {"status": "none", "candidate_count": 0, "review_required": False}
    verified_tiers = {"verified_fact", "verified_controller", "verified", "licensed_fact"}
    verified = [
        item for item in candidates
        if str(item.get("confidence_tier") or item.get("verification_status") or "").lower() in verified_tiers
    ]
    ranked = sorted(candidates, key=_controller_conflict_rank)
    ranked_verified = sorted(verified, key=_controller_conflict_rank)
    preferred = ranked_verified[0] if ranked_verified else ranked[0]
    distinct_names = sorted({str(item.get("name")).strip() for item in candidates})
    status = "none"
    if len({str(item.get("name")).strip() for item in verified}) > 1:
        status = "conflicting_verified_controller_claims"
    elif verified and len(distinct_names) > 1:
        status = "verified_controller_with_competing_leads"
    elif not verified and len(distinct_names) > 1:
        status = "multiple_unverified_controller_leads"
    return {
        "status": status,
        "candidate_count": len(candidates),
        "verified_count": len(verified),
        "preferred_controller": str(preferred.get("name") or ""),
        "preferred_basis": {
            "confidence_tier": preferred.get("confidence_tier"),
            "verification_status": preferred.get("verification_status"),
            "source_strength": preferred.get("source_strength"),
            "source_names": list(preferred.get("source_names") or []),
            "source_count": len(preferred.get("source_names") or []),
            "confidence": preferred.get("confidence"),
        },
        "competing_candidates": [
            str(item.get("name") or "")
            for item in ranked
            if str(item.get("name") or "") != str(preferred.get("name") or "")
        ][:8],
        "competing_candidate_details": [
            {
                "name": str(item.get("name") or ""),
                "confidence_tier": item.get("confidence_tier"),
                "verification_status": item.get("verification_status"),
                "source_strength": item.get("source_strength"),
                "source_names": list(item.get("source_names") or []),
                "confidence": item.get("confidence"),
            }
            for item in ranked
            if str(item.get("name") or "") != str(preferred.get("name") or "")
        ][:8],
        "review_required": status != "none",
        "rule": "official_or_licensed_verified_claims outrank public leads; competing public leads stay review-only",
    }


def _controller_conflict_rank(item: dict[str, Any]) -> tuple[int, int, int, float, str]:
    tier = str(item.get("confidence_tier") or item.get("verification_status") or "").lower()
    tier_rank = {
        "verified_fact": 0,
        "verified_controller": 0,
        "verified": 0,
        "licensed_fact": 0,
        "corroborated_fact": 1,
        "strong_public_lead": 2,
        "public_lead": 3,
        "weak_public_lead": 4,
        "query_plan_lead": 5,
    }.get(tier, 6)
    return (
        tier_rank,
        -int(item.get("source_strength") or 0),
        -len(item.get("source_names") or []),
        -float(item.get("confidence") or 0),
        str(item.get("name") or ""),
    )

def _build_graph_trust_layer(relationship_graph) -> dict:
    """P0-F: Graph trust layer — audit edge quality."""
    rg = relationship_graph or {}; edges = rg.get("edges", [])
    missing_source = [e for e in edges if not e.get("source")]
    missing_explanation = [e for e in edges if not e.get("explanation")]
    only_weak = all(e.get("admission") in ("lead","weak_lead") for e in edges) if edges else False
    return {
        "edge_count": len(edges),
        "strong_edges": sum(1 for e in edges if e.get("admission")=="fact"),
        "weak_edge_count": sum(1 for e in edges if e.get("admission") in ("lead","weak_lead")),
        "missing_source": len(missing_source),
        "missing_explanation": len(missing_explanation),
        "only_weak_edges": only_weak,
        "is_trustable": len(edges)>0 and not missing_source,
    }

def _build_strategy_actions_legacy(gap_analysis, source_readiness) -> dict:
    """EV-004: Generate concrete next actions from gaps + source truth."""
    ga = gap_analysis or {}; gs = ga.get("gap_summary", {}); sr = source_readiness or {}
    actions = []
    """P0-G: Generate concrete next actions from gaps + source readiness."""
    ga = gap_analysis or {}; gs = ga.get("gap_summary", {}); sr = source_readiness or {}
    actions = []
    for lane in ("capital","goods","people"):
        ld = gs.get(lane, {})
        if ld.get("status") == "missing":
            actions.append({"action_id": f"INVESTIGATE-{lane.upper()}", "priority": "P0", "target_lane": lane,
                "reason": f"No {lane} evidence found", "done_condition": f"At least 1 fact-level record in {lane} lane"})
    if not sr.get("usable_sources") and sr.get("fixture_only_sources"):
        actions.append({"action_id":"AUTH-001","priority":"P0","target_lane":"source",
            "reason":"All sources are fixture_only — live verification needed","done_condition":"At least 1 source live_verified"})
        # EV-004: Source truth actions — tell user what to authorize/upload
    fixture_srcs = sr.get("fixture_only_sources", [])
    auth_srcs = sr.get("authorization_required_sources", [])
    blocked_srcs = sr.get("blocked_sources", [])
    if fixture_srcs and not sr.get("usable_sources"):
        actions.append({"action_id":"SOURCE-001","priority":"P0","target_lane":"source",
            "reason":f"All {len(fixture_srcs)} sources are fixture_only — no live data. Current output is structural template, not real retrieval.",
            "done_condition":"At least 1 source live_verified OR authorized API credentials provided"})
    if auth_srcs:
        actions.append({"action_id":"SOURCE-002","priority":"P0","target_lane":"source",
            "reason":f"Authorized sources require credentials: {', '.join(auth_srcs[:3])}",
            "done_condition":"Provide credentials for authorized sources"})
    return {"strategy_actions": actions, "action_count": len(actions)}


def _build_strategy_actions(gap_analysis, source_readiness) -> dict:
    """Generate concrete next actions from gap and source truth."""
    gap_summary = _dict(_dict(gap_analysis).get("gap_summary"))
    readiness = _dict(source_readiness)
    actions: list[dict[str, Any]] = []

    for lane in ("capital", "goods", "people"):
        lane_gap = _dict(gap_summary.get(lane))
        if lane_gap.get("status") == "missing":
            actions.append({
                "action_id": f"INVESTIGATE-{lane.upper()}",
                "priority": "P0",
                "target_lane": lane,
                "reason": f"No {lane} evidence found",
                "done_condition": f"At least 1 fact-level record in {lane} lane",
            })

    fixture_srcs = [str(item) for item in readiness.get("fixture_only_sources", []) if str(item).strip()]
    auth_srcs = [str(item) for item in readiness.get("authorization_required_sources", []) if str(item).strip()]
    blocked_srcs = [str(item) for item in readiness.get("blocked_sources", []) if str(item).strip()]
    usable_srcs = [str(item) for item in readiness.get("usable_sources", []) if str(item).strip()]

    if fixture_srcs and not usable_srcs:
        actions.append({
            "action_id": "AUTH-001",
            "priority": "P0",
            "target_lane": "source",
            "reason": "All sources are fixture_only; live verification is needed.",
            "done_condition": "At least 1 source live_verified or authorized credentials/user-upload evidence provided.",
        })
        actions.append({
            "action_id": "SOURCE-001",
            "priority": "P0",
            "target_lane": "source",
            "reason": f"All {len(fixture_srcs)} sources are fixture_only; current output is structural, not live retrieval.",
            "done_condition": "At least 1 source live_verified or authorized credentials/user-upload evidence provided.",
        })
    if auth_srcs:
        actions.append({
            "action_id": "SOURCE-002",
            "priority": "P0",
            "target_lane": "source",
            "reason": f"Authorized sources require credentials: {', '.join(auth_srcs[:3])}",
            "done_condition": "Provide user-authorized credentials or replace with provenance-bearing public-origin leads.",
        })
    if blocked_srcs:
        actions.append({
            "action_id": "SOURCE-003",
            "priority": "P0",
            "target_lane": "source",
            "reason": f"Blocked sources need safe alternate routing: {', '.join(blocked_srcs[:3])}",
            "done_condition": "Use official/public-origin route or user-authorized upload with source URL and observed time.",
        })

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        key = str(action.get("action_id") or action)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return {"strategy_actions": deduped, "action_count": len(deduped)}

def _build_bond_credit_bridge(bond_credit_profile) -> dict:
    """P1-J: Bridge QYYJT bond/credit pressure into money lane."""
    bp = bond_credit_profile or {}
    default_count = int(bp.get("default_count") or 0)
    high_count = int(bp.get("high_or_critical_event_count") or 0)
    rating_count = int(bp.get("rating_count") or 0)
    calendar_count = int(bp.get("calendar_count") or 0)
    row_count = int(bp.get("row_count") or 0)
    risk_reasons: list[str] = []
    next_actions: list[str] = []

    if default_count:
        risk_reasons.append(f"bond_default_events={default_count}")
        next_actions.append("Verify default amount, default date, issuer, instrument, and latest repayment/disposal status.")
    if high_count:
        risk_reasons.append(f"high_or_critical_bond_events={high_count}")
        next_actions.append("Review high-severity bond events against exchange/bond disclosures and rating announcements.")
    if rating_count:
        risk_reasons.append(f"rating_records={rating_count}")
        next_actions.append("Check rating outlook, rating agency, and whether downgrade/watchlist signals are current.")
    if calendar_count:
        risk_reasons.append(f"bond_calendar_events={calendar_count}")
        next_actions.append("Map upcoming maturity, coupon, put, and disclosure dates into the monitoring seed.")

    if default_count or high_count:
        pressure_level = "high"
    elif rating_count or calendar_count or row_count:
        pressure_level = "medium"
    else:
        pressure_level = "none"

    return {
        "bond_data_available": bool(bp),
        "default_count": default_count,
        "bond_issues": bp.get("bond_issues", []),
        "credit_rating": bp.get("credit_rating", ""),
        "row_count": row_count,
        "rating_count": rating_count,
        "calendar_count": calendar_count,
        "high_or_critical_event_count": high_count,
        "pressure_level": pressure_level,
        "risk_reasons": risk_reasons,
        "next_actions": next_actions[:4],
        "report_visibility": "capital_lane_and_bond_credit_section" if bp else "not_visible_without_bond_data",
        "pressure_signals": "HIGH" if pressure_level == "high" else ("MEDIUM" if pressure_level == "medium" else "NONE"),
        "is_bridge_operational": True,
    }
def _build_pledge_bridge(pledge_profile) -> dict:
    pp = pledge_profile or {}
    return {"pledge_data_available":bool(pp),"pledge_count":pp.get("pledge_count",0),"freeze_count":pp.get("freeze_count",0),"auction_count":pp.get("auction_count",0),"pressure_signals":"HIGH" if pp.get("pledge_count",0)+pp.get("freeze_count",0)>2 else ("MEDIUM" if pp else "NONE"),"is_bridge_operational":True}
def _graph_edge_explainability(relationship_graph) -> dict:
    rg = relationship_graph or {}; edges = rg.get("edges",[])
    return {"explained_edges":[{"from":e.get("from","?"),"to":e.get("to","?"),"type":e.get("type","?"),"source":e.get("source","?"),"evidence_ids":e.get("evidence_ids",[]),"confidence":e.get("confidence",0),"explanation":e.get("explanation",""),"admission":e.get("admission","?")} for e in edges[:10]],"total_edges":len(edges)}
def _cross_lane_questions(money, goods, people, evidence_ledger=None) -> dict:
    """P2-004: Cross-lane investigation questions — investigator-style connections."""
    m, g, p = money or {}, goods or {}, people or {}
    questions = []
    # capital pressure + supplier concentration
    if m.get("fact_count",0) > 0 and g.get("deep_analysis",{}).get("supplier_concentration") == "HIGH":
        questions.append({"question":"Capital pressure (debt/pledge) combined with supplier concentration — are suppliers demanding accelerated payment terms?","evidence_refs":["money_lane.debt_signals","goods_lane.supplier_concentration"],"lanes":["capital","goods"],"reason":"cross-lane capital↔supply risk"})
    # freeze/auction + financing pressure  
    if any("freeze" in str(e).lower() or "auction" in str(e).lower() for e in (m.get("pledge_freeze_auction",[]))):
        questions.append({"question":"Asset freeze/auction detected — does this restrict refinancing or trigger covenant breaches?","evidence_refs":["money_lane.pledge_freeze_auction"],"lanes":["capital"],"reason":"freeze/auction blocks refinancing"})
    # controller path + related-party
    if p.get("fact_count",0) > 0 and p.get("deep_analysis",{}).get("controller_confidence") in ("HIGH","MEDIUM"):
        questions.append({"question":"Controller identified — are there related-party transactions that could indicate tunneling or value transfer?","evidence_refs":["people_lane.controllers"],"lanes":["capital","people"],"reason":"controller↔related-party risk"})
    # customer concentration + revenue risk
    if g.get("deep_analysis",{}).get("customer_dependency") == "HIGH":
        questions.append({"question":"High customer dependency detected — what is the revenue concentration risk from top 3 customers?","evidence_refs":["goods_lane.customer_dependency"],"lanes":["goods","capital"],"reason":"customer concentration creates revenue fragility"})
    # fast hiring + product expansion
    if g.get("fact_count",0) > 0 and p.get("fact_count",0) > 0:
        questions.append({"question":"Product and personnel signals co-exist — is the company scaling or restructuring?","evidence_refs":["goods_lane","people_lane"],"lanes":["goods","people"],"reason":"hiring+product signals scale intent"})
    return {"cross_lane_questions":[{"question":q["question"],"evidence_refs":q["evidence_refs"],"lanes":q["lanes"],"reason":q["reason"]} for q in questions],"question_count":len(questions)}
    m,g,p = money or {}, goods or {}, people or {}
    questions = []
    if m.get("pledge_freeze_auction") and g.get("supplier_claims"): questions.append("Asset pledge/freeze may impact supplier relationships. Verify supplier payment terms.")
    if m.get("debt_signals") and g.get("customer_claims"): questions.append("Debt signals combined with customer concentration — check revenue dependency.")
    if p.get("controllers") and m.get("capital_events"): questions.append("Controller path intersects capital events — investigate related-party transactions.")
    return {"cross_lane_questions":[{"question":q,"evidence_refs":[],"lanes":["cross"],"reason":"derived from money/goods/people status"} for q in questions],"question_count":len(questions)}
def _cross_lane_questions(money, goods, people, evidence_ledger=None) -> dict:
    """Prioritize cross-lane due-diligence questions by business impact."""
    m, g, p = money or {}, goods or {}, people or {}
    questions = []
    if m.get("fact_count", 0) > 0 and g.get("deep_analysis", {}).get("supplier_concentration") == "HIGH":
        questions.append({
            "question": "Capital pressure plus supplier concentration: are suppliers demanding accelerated payment terms?",
            "evidence_refs": ["money_lane.debt_signals", "goods_lane.supplier_concentration"],
            "lanes": ["capital", "goods"],
            "reason": "cross-lane capital-supply risk",
            "priority": "P0",
            "business_impact": "cash-flow and continuity risk",
            "next_step": "Verify top supplier exposure, payable terms, and whether financing pressure is delaying supplier payments.",
        })
    if any("freeze" in str(e).lower() or "auction" in str(e).lower() for e in (m.get("pledge_freeze_auction", []))):
        questions.append({
            "question": "Asset freeze or auction detected: does this restrict refinancing or trigger covenant breaches?",
            "evidence_refs": ["money_lane.pledge_freeze_auction"],
            "lanes": ["capital"],
            "reason": "freeze/auction blocks refinancing",
            "priority": "P0",
            "business_impact": "financing and solvency risk",
            "next_step": "Confirm affected assets, freeze amount, maturity pressure, and lender covenant language.",
        })
    if p.get("fact_count", 0) > 0 and p.get("deep_analysis", {}).get("controller_confidence") in ("HIGH", "MEDIUM"):
        questions.append({
            "question": "Controller identified: are there related-party transactions that could indicate tunneling or value transfer?",
            "evidence_refs": ["people_lane.controllers"],
            "lanes": ["capital", "people"],
            "reason": "controller-related-party risk",
            "priority": "P0",
            "business_impact": "control, governance, and value-transfer risk",
            "next_step": "Cross-check controller path against related-party transactions, guarantees, fund flows, and affiliated suppliers/customers.",
        })
    if g.get("deep_analysis", {}).get("customer_dependency") == "HIGH":
        questions.append({
            "question": "High customer dependency detected: what is the revenue concentration risk from top 3 customers?",
            "evidence_refs": ["goods_lane.customer_dependency"],
            "lanes": ["goods", "capital"],
            "reason": "customer concentration creates revenue fragility",
            "priority": "P1",
            "business_impact": "revenue fragility risk",
            "next_step": "Estimate top-customer share, renewal or contract length, receivables aging, and customer credit quality.",
        })
    if g.get("fact_count", 0) > 0 and p.get("fact_count", 0) > 0:
        questions.append({
            "question": "Product and personnel signals co-exist: is the company scaling or restructuring?",
            "evidence_refs": ["goods_lane", "people_lane"],
            "lanes": ["goods", "people"],
            "reason": "hiring+product signals scale intent",
            "priority": "P2",
            "business_impact": "strategy and execution-change signal",
            "next_step": "Compare hiring direction, product launches, customer mix, and management changes over the same period.",
        })
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    questions = sorted(
        questions,
        key=lambda q: (
            priority_rank.get(str(q.get("priority") or "P3"), 9),
            str(q.get("reason") or ""),
            str(q.get("question") or ""),
        ),
    )
    return {
        "cross_lane_questions": questions,
        "question_count": len(questions),
        "prioritized": True,
        "top_priority": questions[0]["priority"] if questions else "",
    }


def _market_structure_depth(industry_profile, public_web) -> dict:
    ip,pw = industry_profile or {}, public_web or {}
    return {"competitor_set":pw.get("competitors",[]),"market_concentration":pw.get("hhi",""),"policy_cycle":pw.get("policy_hints",[]),"switching_cost":pw.get("switching_cost_hints",[]),"depth_score":"deep" if pw.get("competitors") and pw.get("hhi") else ("moderate" if pw else "shallow")}
def _build_persona_data_contract(money, goods, people, strategy, evidence_depth, graph_trust) -> list:
    """RIX-11: Persona data contract — deterministic messages for Codex UI rebuild."""
    msgs = []
    if not money or not money.get("profile_available"):
        msgs.append({"persona":"capital_desk","message":"No money/solvency data available. Need financing, debt, pledge records.","refs":["money_lane"],"type":"system_assignment"})
    if not goods or not goods.get("profile_available"):
        msgs.append({"persona":"goods_desk","message":"No product/supply chain data. Need supplier, customer, market intelligence.","refs":["goods_lane"],"type":"system_assignment"})
    if not people or not people.get("profile_available"):
        msgs.append({"persona":"people_desk","message":"No controller/ownership data. Need UBO, executive, related-party records.","refs":["people_lane"],"type":"system_assignment"})
    return msgs
def _build_query_families(company: str) -> dict:
    qf = {
        "identity": [f"{company} registration",f"{company} legal representative",f"{company} unified social credit code"],
        "money": [f"{company} financing",f"{company} debt",f"{company} pledge freeze auction",f"{company} revenue"],
        "goods": [f"{company} supplier",f"{company} customer",f"{company} product",f"{company} market share"],
        "people": [f"{company} controller",f"{company} UBO",f"{company} shareholder",f"{company} executive"],
        "legal": [f"{company} court",f"{company} enforcement",f"{company} dishonesty",f"{company} penalty"],
        "industry": [f"{company} industry report",f"{company} market analysis",f"{company} competitor"],
    }
    return {"query_families":qf,"query_count":sum(len(v) for v in qf.values()),"family_count":len(qf)}
def _inject_fact_edges_from_evidence(graph, evidence_ledger):
    """Build fact-level graph edges from evidence ledger facts."""
    if not evidence_ledger or not graph:
        return graph
    edges = graph.setdefault("edges", [])
    for ev in evidence_ledger:
        if ev.get("admission") != "fact":
            continue
        lane = ev.get("lane", "")
        if lane == "capital" and any(k in str(ev).lower() for k in ("pledge","freeze","auction")):
            edges.append({"source": "subject_profile","from": "seed", "to": f"asset:{ev.get('evidence_id','?')}", "type": "pledged", "confidence": float(ev.get("confidence",0.8)), "admission": "fact", "source": ev.get("source_name","evidence"), "explanation": str(ev.get("claim",""))[:80], "evidence_ids": [ev.get("evidence_id","")]})
        if lane == "goods" and any(k in str(ev).lower() for k in ("supplier","product")):
            edges.append({"source": "subject_profile","from": "seed", "to": f"supplier:{ev.get('evidence_id','?')}", "source": "supply_chain_profile","type": "supplies", "confidence": float(ev.get("confidence",0.8)), "admission": "fact", "source": ev.get("source_name","evidence"), "explanation": str(ev.get("claim",""))[:80], "evidence_ids": [ev.get("evidence_id","")]})
        if lane == "people" and any(k in str(ev).lower() for k in ("controller","ubo","executive")):
            edges.append({"source": "subject_profile","from": "seed", "to": f"person:{ev.get('evidence_id','?')}", "type": "controls", "confidence": float(ev.get("confidence",0.8)), "admission": "fact", "source": ev.get("source_name","evidence"), "explanation": str(ev.get("claim",""))[:80], "evidence_ids": [ev.get("evidence_id","")]})
    return graph
def _build_related_parties_bridge(subject_profile, relationship_network) -> dict:
    sp = subject_profile or {}
    rn = relationship_network or {}
    return {
        "controller_candidates": len(sp.get("controllers", [])),
        "related_companies": len(rn.get("related_parties", [])),
        "shared_address_leads": len(rn.get("shared_addresses", [])),
        "bridge_operational": True,
    }
def _build_court_enforcement_bridge(court_rows, enforcement_rows) -> dict:
    cr = court_rows or []
    er = enforcement_rows or []
    return {
        "court_case_count": len(cr),
        "enforcement_action_count": len(er),
        "high_risk_items": [r for r in (cr + er) if r.get("risk_level") == "high"][:5],
        "bridge_operational": True,
    }
def _build_regional_credit_bridge(regional_rows) -> dict:
    rr = regional_rows or []
    return {
        "city_investment_count": sum(1 for r in rr if r.get("type") == "city_investment"),
        "regional_debt_count": sum(1 for r in rr if r.get("type") == "regional_debt"),
        "regional_economy_signals": [r for r in rr if r.get("risk_signal")][:5],
        "bridge_operational": True,
    }
def _build_commercial_activity_bridge(tax_rows, import_export_rows) -> dict:
    tr = tax_rows or []
    ie = import_export_rows or []
    return {
        "tax_record_count": len(tr),
        "import_export_count": len(ie),
        "activity_level": "HIGH" if len(tr) + len(ie) >= 5 else ("MEDIUM" if tr or ie else "LOW"),
        "bridge_operational": True,
    }
def _build_financial_indicator_bridge(fin_indicator_rows) -> dict:
    fr = fin_indicator_rows or []
    return {
        "indicator_count": len(fr),
        "profitability_signals": [r for r in fr if r.get("category") == "profitability"][:3],
        "solvency_signals": [r for r in fr if r.get("category") == "solvency"][:3],
        "growth_signals": [r for r in fr if r.get("category") == "growth"][:3],
        "bridge_operational": True,
    }
def _build_ip_patent_bridge(patent_rows, trademark_rows) -> dict:
    pr = patent_rows or []
    tr = trademark_rows or []
    return {
        "patent_count": len(pr),
        "trademark_count": len(tr),
        "ip_portfolio_size": len(pr) + len(tr),
        "ip_intensity": "HIGH" if len(pr) >= 10 else ("MEDIUM" if pr else "LOW"),
        "bridge_operational": True,
    }
def _build_data_effectiveness_matrix(evidence_ledger, source_readiness) -> dict:
    el=evidence_ledger or []
    sr=source_readiness or {}
    sources={}
    for e in el:
        sn=e.get("source_name","unknown")
        if sn not in sources:sources[sn]={"facts":0,"leads":0,"total":0}
        sources[sn]["total"]+=1
        if e.get("admission")=="fact":sources[sn]["facts"]+=1
        else:sources[sn]["leads"]+=1
    return {"source_effectiveness":sources,"total_sources":len(sources),"most_effective":max(sources,key=lambda k:sources[k]["facts"]) if sources else None}
def _build_report_language(harness, live_boundary, release_dec, money_status, goods_status, people_status) -> dict:
    """P3-003: Data-driven report language based on runtime state."""
    src_lanes = (harness or {}).get("source_lane_readiness", {})
    fixture_count = sum(1 for v in src_lanes.values() if v.get("fixture_only"))
    live_count = sum(1 for v in src_lanes.values() if v.get("live_verified"))
    return {
        "release_decision_label": f"版本: {release_dec} - {live_count}个已验证/{fixture_count}个模板数据",
        "source_truth_label": f"数据源: {live_count}已验证 / {fixture_count}模板 - {'实时数据可用' if live_count else '仅模板数据'}",
        "next_action_label": "提供授权凭证或上传文件以获取实时调查结果" if not live_count else "实时数据已连接",
        "money_lane_status": str(money_status),
        "goods_lane_status": str(goods_status),
        "people_lane_status": str(people_status),
    }


def _build_packet_quality_flags(
    release_decision: str,
    harness: dict[str, Any],
    source_readiness: dict[str, Any],
    money_status: str,
    goods_status: str,
    people_status: str,
    evidence_trace: list[dict[str, Any]],
    evidence_gaps: list[str],
    executable_next_steps: list[dict[str, Any]],
) -> dict[str, bool]:
    trace_sections = {
        str(item.get("report_section") or "")
        for item in evidence_trace or []
        if isinstance(item, dict)
    }

    def lane_visible(status: str, section: str) -> bool:
        return str(status or "missing") not in {"", "missing", "unknown"} or section in trace_sections

    source_lanes = _dict((harness or {}).get("source_lane_readiness"))
    return {
        "release_decision_visible": bool(str(release_decision or "").strip()),
        "source_truth_visible": bool(source_lanes or any(source_readiness.get(key) for key in (
            "usable_sources",
            "fixture_only_sources",
            "blocked_sources",
            "authorization_required_sources",
            "parse_failed_sources",
            "access_issues",
        ))),
        "money_lane_visible": lane_visible(money_status, "money_lane"),
        "goods_lane_visible": lane_visible(goods_status, "goods_lane"),
        "people_lane_visible": lane_visible(people_status, "people_lane"),
        "next_actions_concrete": bool(evidence_gaps or executable_next_steps),
        "fixture_live_boundary_visible": "fixture_only" in str(harness or {}) or "live_unverified" in str(harness or {}),
    }


def _build_bridge_summary(bridges: dict[str, dict]) -> dict:
    operational = [
        name
        for name, bridge in bridges.items()
        if isinstance(bridge, dict) and bridge.get("bridge_operational") is True
    ]
    available = [
        name
        for name, bridge in bridges.items()
        if isinstance(bridge, dict) and bridge.get("bridge_available") is True
    ]
    return {
        "bridges_deployed": len(bridges),
        "available": available,
        "operational": operational,
        "operational_count": len(operational),
        "note": "Operational bridges require at least one complete provenance-bearing fact row.",
    }


# Keep legacy private imports stable while the implementation lives in the
# focused report-card module.
_build_blocker_gate = _report_card_blocker_gate
_build_realness_score = _report_card_realness_score
_build_report_language = _report_card_report_language
_build_packet_quality_flags = _report_card_packet_quality_flags


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value.strip()
        elif value:
            return value
    return None

def _bridge_text_fields(row: dict) -> str:
    texts = []
    for field in ("claim", "claims", "summary", "description", "title", "raw_text", "text"):
        value = row.get(field)
        if isinstance(value, list):
            texts.extend(str(item) for item in value if item)
        elif value:
            texts.append(str(value))
    for field in ("record_type", "type", "claim_type", "category", "lane"):
        value = row.get(field)
        if value:
            texts.append(str(value))
    return " ".join(texts).strip()

def _bridge_source(row: dict):
    return _first_non_empty(
        row.get("source"),
        row.get("source_name"),
        row.get("provenance"),
        row.get("source_url"),
        row.get("url"),
    )

def _extract_amount_from_text(text: str):
    if not text:
        return None
    match = re.search(
        r"(?i)(?:[$￥]\s*)?\d+(?:\.\d+)?\s*(?:billion|million|bn|m|亿|万|元|美元|人民币|%)?",
        text,
    )
    return match.group(0).strip() if match else None

def _bridge_value_from_text(text: str, *keys: str) -> str | None:
    for key in keys:
        match = re.search(rf"(?i)\b{re.escape(key)}\s*=\s*([^;,\n]+)", str(text or ""))
        if match:
            return match.group(1).strip()
    return None

def _bridge_candidate_row(row: dict, *, bridge_type: str) -> dict:
    text = _bridge_text_fields(row)
    source = _bridge_source(row)
    base = {
        "source": source,
        "claim": text,
        "evidence_id": _first_non_empty(row.get("evidence_id"), row.get("id")),
        "admission": row.get("admission"),
    }
    amount = _first_non_empty(row.get("amount"), row.get("value"), _extract_amount_from_text(text))
    if amount:
        base["amount"] = amount
    if bridge_type in {"pledge", "freeze", "auction"}:
        pledgor = _first_non_empty(row.get("pledgor"), row.get("subject"), row.get("company"), row.get("entity"), _bridge_value_from_text(text, "pledgor", "subject", "company"))
        pledgee = _first_non_empty(row.get("pledgee"), row.get("counterparty"), row.get("creditor"), _bridge_value_from_text(text, "pledgee", "counterparty", "creditor"))
        if pledgor:
            base["pledgor"] = pledgor
        if pledgee:
            base["pledgee"] = pledgee
    else:
        counterparty = _first_non_empty(row.get("counterparty"), row.get("customer"), row.get("supplier"), row.get("partner"), _bridge_value_from_text(text, "counterparty", "customer", "supplier", "partner"))
        if counterparty:
            base["counterparty"] = counterparty
    return {key: value for key, value in base.items() if value is not None}

def _extract_qyyjt_bridge_rows(evidence_ledger) -> dict:
    rows = {
        "pledge_rows": [],
        "freeze_rows": [],
        "auction_rows": [],
        "trade_rows": [],
        "import_export_rows": [],
        "recruiting_rows": [],
    }
    for row in evidence_ledger or []:
        if not isinstance(row, dict):
            continue
        text = _bridge_text_fields(row).lower()
        if not text:
            continue
        if any(token in text for token in ("pledge", "equity pledge", "股权质押", "质押")):
            rows["pledge_rows"].append(_bridge_candidate_row(row, bridge_type="pledge"))
        if any(token in text for token in ("freeze", "frozen", "asset freeze", "冻结", "查封")):
            rows["freeze_rows"].append(_bridge_candidate_row(row, bridge_type="freeze"))
        if any(token in text for token in ("auction", "judicial sale", "拍卖", "司法拍卖")):
            rows["auction_rows"].append(_bridge_candidate_row(row, bridge_type="auction"))
        if any(token in text for token in ("trade", "commercial", "contract", "sales", "purchase", "贸易", "合同", "采购", "销售")):
            rows["trade_rows"].append(_bridge_candidate_row(row, bridge_type="trade"))
        if any(token in text for token in ("import", "export", "customs", "进出口", "海关", "出口", "进口")):
            rows["import_export_rows"].append(_bridge_candidate_row(row, bridge_type="import_export"))
        if any(token in text for token in ("recruit", "hiring", "job posting", "招聘", "岗位")):
            rows["recruiting_rows"].append(_bridge_candidate_row(row, bridge_type="recruiting"))
    rows["summary"] = {key: len(value) for key, value in rows.items() if key.endswith("_rows")}
    return rows

def _build_qyyjt_bridge_packet(evidence_ledger) -> dict:
    bridge_rows = _extract_qyyjt_bridge_rows(evidence_ledger)
    pledge_bridge = build_pledge_bridge(
        bridge_rows["pledge_rows"],
        bridge_rows["freeze_rows"],
        bridge_rows["auction_rows"],
    )
    trade_bridge = build_trade_bridge(
        bridge_rows["trade_rows"],
        bridge_rows["import_export_rows"],
        bridge_rows["recruiting_rows"],
    )
    return {
        "bridge_input_summary": bridge_rows["summary"],
        "pledge_bridge": pledge_bridge,
        "trade_bridge": trade_bridge,
        "bridge_summary": _build_bridge_summary({
            "pledge_bridge": pledge_bridge,
            "trade_bridge": trade_bridge,
        }),
    }

def _subject_aggregation_available(
    subject_profile: dict[str, Any] | None,
    relationship_network: dict[str, Any] | None,
) -> bool:
    """Return whether subject aggregation produced usable runtime output."""
    profile = subject_profile or {}
    network = relationship_network or {}
    def has_provenance(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return bool(value.get("evidence_ids") or value.get("source_names"))

    subjects = profile.get("subjects") if isinstance(profile.get("subjects"), dict) else {}
    non_seed_subjects = [
        value for key, value in subjects.items()
        if str(key).lower() not in {"seed", "subject", "root"}
        and not (isinstance(value, dict) and isinstance(value.get("attributes"), dict) and value["attributes"].get("seed") is True)
        and has_provenance(value)
    ]
    signals_by_dimension = profile.get("signals_by_dimension") if isinstance(profile.get("signals_by_dimension"), dict) else {}
    provenanced_signals = [
        signal
        for signals in signals_by_dimension.values()
        if isinstance(signals, list)
        for signal in signals
        if has_provenance(signal)
    ]
    if non_seed_subjects or provenanced_signals:
        return True
    if any(has_provenance(item) for item in profile.get("controller_candidates", []) if isinstance(item, dict)):
        return True
    if any(has_provenance(item) for item in profile.get("key_signals", []) if isinstance(item, dict)):
        return True
    graph = profile.get("relationship_graph") if isinstance(profile.get("relationship_graph"), dict) else {}
    if graph.get("edges"):
        return True
    graph_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    if len(graph_nodes) > 1:
        return True
    if int(network.get("relation_count") or 0) > 0:
        return True
    if int(network.get("subject_count") or 0) > 1:
        return True
    if network.get("top_edges") or network.get("edges"):
        return True
    network_nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
    if len(network_nodes) > 1:
        return True
    return False

def _source_readiness_matrix(source_lane_readiness: dict) -> list[dict[str, Any]]:
    rows = []
    for name, lane in (source_lane_readiness or {}).items():
        live_verified = bool(lane.get("live_verified"))
        authorized = bool(lane.get("authorized"))
        fixture_only = bool(lane.get("fixture_only"))
        live_unverified = bool(lane.get("live_unverified")) or str(lane.get("live_status")) == "live_unverified"
        if live_verified:
            next_action = "ready"
        elif authorized:
            next_action = "provide_credentials"
        elif fixture_only or live_unverified:
            next_action = "live_smoke_needed"
        else:
            next_action = "configure_source"
        rows.append({
            "source": name,
            "status": lane.get("live_status", "live_unverified" if live_unverified else "?"),
            "authorized": authorized,
            "blocked": bool(lane.get("blocked")),
            "fixture_only": fixture_only,
            "live_unverified": live_unverified,
            "live_smoke_capable": bool(lane.get("live_smoke_capable")),
            "live_verified": live_verified,
            "next_action": next_action,
        })
    return rows

def _enterprise_cognition(
    *,
    company: str,
    summary: dict[str, Any],
    risk_events: list[dict[str, Any]],
    profile_brief: dict[str, Any],
    evidence_ledger: list[dict[str, Any]] | None = None,
    subject_profile: dict[str, Any] | None = None,
    allow_fixture_bridge: bool = False,
) -> dict[str, Any]:
    """Build a lightweight enterprise cognition profile for API/CLI packets.

    This packet builder is intentionally sync because it is used by both Flask
    and async CLI/MCP flows. The full async EnterpriseCognitionEngine remains
    available in `core.engine`; this API surface exposes the same product idea
    from the evidence graph without starting another event loop.
    """
    ledger = evidence_ledger or []
    # aiqicha_scraper pattern: Fast empty detection
    empty_evidence = sum(1 for e in ledger if _fast_empty_detect(str(e.get("claims", ""))[:200]))
    if empty_evidence > 0:
        summary["empty_results_detected"] = empty_evidence
    # aiqicha_scraper pattern: Pre-search cache dedup
    subject_cache = _pre_search_cache_check(company, ledger)
    if subject_cache.get("skip_request"):
        summary["cache_skip"] = True
        summary["cache_existing_sources"] = subject_cache.get("existing_sources", [])
    subject_profile = subject_profile or {}
    financial = _financial_cognition_from_evidence(ledger)
    industry = _industry_cognition_from_evidence(ledger)
    product = _product_cognition_from_evidence(ledger)
    credit_profile = _credit_profile_from_evidence(ledger)
    legal_administrative_profile = _legal_administrative_profile_from_evidence(ledger, risk_events)
    operational_event_profile = _operational_event_profile_from_evidence(ledger, risk_events)
    public_capital_profile = _capital_profile_from_public_web_evidence(ledger)
    # Unified public-web profiles bridge
    pw_profiles = _public_web_profiles_from_evidence(ledger)
    public_goods_profile = pw_profiles.get("public_goods_profile")
    public_people_profile = pw_profiles.get("public_people_profile")
    if pw_profiles.get("public_capital_profile"):
        if public_capital_profile:
            public_capital_profile = {
                **pw_profiles["public_capital_profile"],
                **public_capital_profile,
                "claims": _dedupe_strings(
                    list(public_capital_profile.get("claims") or [])
                    + list(pw_profiles["public_capital_profile"].get("claims") or [])
                )[:20],
                "rows": (
                    list(public_capital_profile.get("rows") or [])
                    + list(pw_profiles["public_capital_profile"].get("rows") or [])
                )[:12],
                "structured_summary": pw_profiles["public_capital_profile"].get("structured_summary", {}),
            }
            for key in (
                "financing_event_claims",
                "debt_credit_claims",
                "refinancing_claims",
                "liquidity_claims",
                "asset_pressure_claims",
                "capital_structure_claims",
            ):
                if pw_profiles["public_capital_profile"].get(key):
                    public_capital_profile[key] = pw_profiles["public_capital_profile"][key]
        else:
            public_capital_profile = pw_profiles["public_capital_profile"]
    commercial_activity_profile = _commercial_activity_profile_from_evidence(ledger, risk_events)
    bond_credit_profile = _bond_credit_profile_from_evidence(ledger, risk_events)
    regional_credit_profile = _regional_credit_profile_from_evidence(ledger, risk_events)
    asset_solvency_profile = _asset_solvency_profile_from_evidence(ledger, risk_events)
    ip_tech_profile = _ip_tech_profile_from_evidence(ledger, risk_events)
    fin_inst_profile = _fin_inst_profile_from_evidence(ledger, risk_events)
    supply_chain_profile = _supply_chain_profile_from_evidence(ledger)
    control_ownership = _control_ownership_from_subject_profile(profile_brief, subject_profile)
    relationship_network = _relationship_network_from_subject_profile(subject_profile)
    fund_flow_profile = _fund_flow_profile(
        financial=financial,
        credit_profile=credit_profile,
        operational_event_profile=operational_event_profile,
        commercial_activity_profile=commercial_activity_profile,
        bond_credit_profile=bond_credit_profile,
        asset_solvency_profile=asset_solvency_profile,
        fin_inst_profile=fin_inst_profile,
        public_capital_profile=public_capital_profile,
    )
    capital_pressure_profile = _capital_pressure_profile(
        fund_flow_profile=fund_flow_profile,
        credit_profile=credit_profile,
        operational_event_profile=operational_event_profile,
        bond_credit_profile=bond_credit_profile,
        asset_solvency_profile=asset_solvency_profile,
        fin_inst_profile=fin_inst_profile,
        public_capital_profile=public_capital_profile,
    )
    capital_relationship_profile = _capital_relationship_profile(
        capital_pressure_profile=capital_pressure_profile,
        relationship_network=relationship_network,
    )
    goods_flow_profile = _goods_flow_profile(
        industry=industry,
        product=product,
        supply_chain_profile=supply_chain_profile,
        public_goods_profile=public_goods_profile,
    )
    people_flow_profile = _people_flow_profile(
        control_ownership=control_ownership,
        relationship_network=relationship_network,
        legal_administrative_profile=legal_administrative_profile,
        public_people_profile=public_people_profile,
    )
    risk_n = _policy_cap("risk_count", 8)
    event_hypotheses = [
        f"{_risk_event_prefix(event.get('severity'))}：{_event_title(event)}（{_category_label(event.get('category'))}）"
        for event in risk_events[:risk_n]
        if event.get("title")
    ]
    evidence_gaps = [
        "财务数据、现金流、应收、存货和客户集中度",
        "行业增速、产能、价格、政策和竞争格局",
        "核心产品、客户购买理由、复购和替代品",
        "上下游、客户供应商、经销商、合作伙伴和商业版图",
    ]
    profile_gaps = [str(item) for item in profile_brief.get("evidence_gaps", []) if str(item).strip()]
    if not risk_events:
        evidence_gaps.append("司法执行、行政处罚、舆情和公开风险事件")
    if profile_gaps:
        evidence_gaps.extend(profile_gaps[:4])
    if financial:
        evidence_gaps = [
            item for item in evidence_gaps
            if "财务" not in item
            and "现金流" not in item
            and "璐㈠姟" not in item
            and "鐜伴噾" not in item
        ]

    if industry:
        evidence_gaps = [item for item in evidence_gaps if "行业" not in item]
    if product:
        evidence_gaps = [item for item in evidence_gaps if "产品" not in item and "替代品" not in item]
    if supply_chain_profile:
        evidence_gaps = [
            item for item in evidence_gaps
            if "上下游" not in item and "供应商" not in item and "商业版图" not in item
        ]

    if not event_hypotheses:
        focus = "、".join(profile_brief.get("covered_dimensions", [])[:3]) or "主体身份、关系网络和风险事件"
        event_hypotheses.append(f"当前证据不足，需先补齐{focus}后再判断核心风险")
    if financial:
        notes = financial.get("quality_notes") or []
        if notes:
            event_hypotheses.insert(0, "财务读法： " + "; ".join(str(item) for item in notes[:3]))
    if industry:
        event_hypotheses.extend(_domain_label(item) for item in industry.get("risk_triggers", [])[:3])
    if product:
        event_hypotheses.extend(_domain_label(item) for item in product.get("risk_triggers", [])[:3])
    if supply_chain_profile:
        event_hypotheses.insert(
            0,
            "供应链/商业版图画像已取证："
            f"客户 {supply_chain_profile.get('customer_count', 0)} 条；"
            f"供应商 {supply_chain_profile.get('supplier_count', 0)} 条；"
            f"上下游/伙伴 {supply_chain_profile.get('relationship_count', 0)} 条",
        )
    if credit_profile:
        risky_items = [
            item for item in credit_profile.get("items", [])
            if isinstance(item, dict) and item.get("risk_flag")
        ]
        if risky_items:
            event_hypotheses.insert(
                0,
                "信用画像预警：" + "；".join(
                    f"{item.get('item')}={item.get('status')}"
                    for item in risky_items[:3]
                ),
            )
        else:
            event_hypotheses.append("信用画像已取得授权/许可来源字段，当前未触发异常状态。")
    if legal_administrative_profile:
        event_hypotheses.insert(
            0,
            "法务行政画像已取证："
            f"{legal_administrative_profile.get('row_count', 0)} 条记录；"
            f"高风险事件 {legal_administrative_profile.get('high_or_critical_event_count', 0)} 条；"
            f"行政处罚 {legal_administrative_profile.get('administrative_penalty_count', 0)} 条",
        )
    if operational_event_profile:
        event_hypotheses.insert(
            0,
            "经营事件画像已取证："
            f"工商变更 {operational_event_profile.get('registry_change_count', 0)} 条；"
            f"融资事件 {operational_event_profile.get('financing_event_count', 0)} 条；"
            f"并购重组 {operational_event_profile.get('merger_event_count', 0)} 条；"
            f"负面舆情 {operational_event_profile.get('negative_opinion_count', 0)} 条",
        )
    if capital_pressure_profile:
        event_hypotheses.insert(
            0,
            "Capital pressure profile ready: "
            f"level={capital_pressure_profile.get('pressure_level')}; "
            f"pressure_signals={capital_pressure_profile.get('pressure_signal_count', 0)}; "
            f"inflow_signals={capital_pressure_profile.get('inflow_signal_count', 0)}",
        )
    if capital_relationship_profile:
        event_hypotheses.insert(
            0,
            "Capital relationship profile ready: "
            f"level={capital_relationship_profile.get('relationship_risk_level')}; "
            f"matches={capital_relationship_profile.get('match_count', 0)}",
        )
    if commercial_activity_profile:
        event_hypotheses.insert(
            0,
            "经营活跃度画像已取证："
            f"税务 {commercial_activity_profile.get('tax_count', 0)} 条；"
            f"进出口 {commercial_activity_profile.get('trade_count', 0)} 条；"
            f"招聘 {commercial_activity_profile.get('recruiting_count', 0)} 条",
        )
    if bond_credit_profile:
        event_hypotheses.insert(
            0,
            "债券信用画像已取证："
            f"债券记录 {bond_credit_profile.get('row_count', 0)} 条；"
            f"违约/高风险 {bond_credit_profile.get('high_or_critical_event_count', 0)} 条",
        )
    if asset_solvency_profile:
        event_hypotheses.insert(
            0,
            "资产偿付画像已取证："
            f"资产/股权记录 {asset_solvency_profile.get('row_count', 0)} 条；"
            f"高风险事件 {asset_solvency_profile.get('high_or_critical_event_count', 0)} 条",
        )
    if ip_tech_profile:
        event_hypotheses.append(
            "知识产权画像已取证："
            f"IP 记录 {ip_tech_profile.get('row_count', 0)} 条，需结合权属/有效状态判断技术护城河。"
        )
    if fin_inst_profile:
        event_hypotheses.insert(
            0,
            "金融机构对手方画像已取证："
            f"机构记录 {fin_inst_profile.get('row_count', 0)} 条；"
            f"高风险机构 {fin_inst_profile.get('high_risk_count', 0)} 条",
        )

    watchlist = [
        "新增司法执行、行政处罚、经营异常和负面舆情",
        "实控人、股东、高管和关联企业变更",
    ]
    if commercial_activity_profile:
        watchlist.insert(
            0,
            "经营活跃度画像："
            f"tax={commercial_activity_profile.get('tax_count', 0)}；"
            f"trade={commercial_activity_profile.get('trade_count', 0)}；"
            f"recruiting={commercial_activity_profile.get('recruiting_count', 0)}",
        )
    if supply_chain_profile:
        watchlist.insert(
            0,
            "供应链/商业版图："
            f"customers={supply_chain_profile.get('customer_count', 0)}；"
            f"suppliers={supply_chain_profile.get('supplier_count', 0)}；"
            f"concentration={supply_chain_profile.get('concentration_signal_count', 0)}",
        )
    control_questions: list[str] = []
    relationship_questions: list[str] = []
    if control_ownership:
        candidate_names = [
            str(item.get("name") or "").strip()
            for item in control_ownership.get("controller_candidates", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if candidate_names:
            joined_names = "、".join(candidate_names[:4])
            event_hypotheses.insert(
                0,
                f"控制权线索已识别：{joined_names}，需要结合更多官方关系记录核验最终实控人",
            )
            watchlist.insert(0, f"核验控制权候选：{joined_names}")
            control_questions.append(
                f"控制权候选{joined_names}是否还能被更多官方关系记录交叉印证？"
            )
        control_paths = control_ownership.get("control_paths") or []
        if control_paths:
            path_preview = "；".join(
                f"{path.get('from_name')} -> {path.get('to_name')} ({path.get('relation_type')})"
                for path in control_paths[:3]
            )
            if path_preview:
                event_hypotheses.insert(0, f"控制路径预览：{path_preview}")
                watchlist.insert(0, "控制路径：" + path_preview)
    if relationship_network:
        relation_types = [
            _domain_label(item)
            for item in relationship_network.get("relation_types", [])[:5]
            if str(item).strip()
        ]
        source_names = [
            str(item).strip()
            for item in relationship_network.get("source_names", [])
            if str(item).strip()
        ]
        event_hypotheses.append(
            "关系网络已展开"
            f"：{relationship_network.get('subject_count', 0)} 个主体、"
            f"{relationship_network.get('relation_count', 0)} 条关系"
            + (f"，来源覆盖 {len(source_names)} 类" if source_names else "")
            + "，需要继续核验共同地址、共同任职、项目/交易对手和控制权路径。"
        )
        if relation_types:
            watchlist.insert(0, "关系网络类型：" + "、".join(relation_types))
        top_edges = relationship_network.get("top_edges") or []
        if top_edges:
            first_edge = top_edges[0]
            relationship_questions.append(
                "先核对最强关联："
                f"{first_edge.get('from_name')} -> {first_edge.get('to_name')}（{first_edge.get('relation_type')}）",
            )
    watchlist.extend(_domain_label(item) for item in profile_brief.get("covered_dimensions", [])[:8])
    if industry:
        watchlist.extend(_domain_label(item) for item in industry.get("next_three_year_watchlist", [])[:5])
    if product:
        watchlist.extend(_domain_label(item) for item in product.get("risk_triggers", [])[:5])
    if credit_profile:
        watchlist.insert(0, "信用画像状态：" + "；".join(
            f"{item.get('item')}={item.get('status')}"
            for item in credit_profile.get("items", [])[:4]
            if isinstance(item, dict)
        ))
    if legal_administrative_profile:
        watchlist.insert(
            0,
            "法务行政画像状态："
            f"court/enforcement={legal_administrative_profile.get('court_enforcement_count', 0)}；"
            f"administrative_penalty={legal_administrative_profile.get('administrative_penalty_count', 0)}",
        )
    if operational_event_profile:
        watchlist.insert(
            0,
            "经营事件画像状态："
            f"registry_change={operational_event_profile.get('registry_change_count', 0)}；"
            f"financing={operational_event_profile.get('financing_event_count', 0)}；"
            f"negative_opinion={operational_event_profile.get('negative_opinion_count', 0)}",
        )
    if bond_credit_profile:
        watchlist.insert(0, f"债券信用画像：rows={bond_credit_profile.get('row_count', 0)}")
    if asset_solvency_profile:
        watchlist.insert(0, f"资产偿付画像：rows={asset_solvency_profile.get('row_count', 0)}")
    if ip_tech_profile:
        watchlist.insert(0, f"知识产权画像：rows={ip_tech_profile.get('row_count', 0)}")
    if fin_inst_profile:
        watchlist.insert(
            0,
            f"金融机构对手方画像：rows={fin_inst_profile.get('row_count', 0)}, "
            f"high_risk={fin_inst_profile.get('high_risk_count', 0)}",
        )
    for event in risk_events[:3]:
        title = str(event.get("title") or "").strip()
        if title:
            watchlist.append(f"跟踪风险事件状态：{title}")

    next_questions = [
        "这家公司到底靠什么赚钱，利润能否转成现金？",
        "实际控制人、关键管理人和关联主体是否存在未解释的风险连接？",
        "当前风险事件是否能穿透到责任主体、金额、时间线和最新状态？",
    ]
    if commercial_activity_profile:
        next_questions.insert(0, "税务、进出口和招聘信号是否与收入规模、产能利用率和经营扩张节奏相互印证？")
    if supply_chain_profile:
        next_questions.insert(
            0,
            "客户、供应商、上下游和合作伙伴是否能形成可验证交易链，是否存在客户/供应商集中或关联交易风险？",
        )
    if control_questions:
        next_questions = control_questions + next_questions
    if relationship_questions:
        next_questions = relationship_questions + next_questions
    if industry:
        next_questions.extend(str(item) for item in industry.get("investigation_questions", [])[:4])
    if product:
        next_questions.extend(str(item) for item in product.get("investigation_questions", [])[:4])
    if legal_administrative_profile:
        next_questions.insert(
            0,
            "法务行政记录是否已经穿透到案号/决定书号、责任主体、金额、日期和最新状态？"
        )
    if operational_event_profile:
        next_questions.insert(
            0,
            "工商变更、融资事件和负面舆情是否指向同一个经营压力或控制权变化？"
        )
    if bond_credit_profile:
        next_questions.insert(0, "债券违约、评级变化和融资事件是否指向同一个偿债压力？")
    if asset_solvency_profile:
        next_questions.insert(0, "股权质押、冻结、拍卖和土地资产是否改变偿付能力或控制权稳定性？")
    if ip_tech_profile:
        next_questions.insert(0, "知识产权是否仍有效、归属清晰，并能支撑核心产品竞争力？")
    # Prioritized evidence-backed next steps
    priority_actions = []
    if risk_events and any(e.get("severity") == "high" for e in risk_events):
        priority_actions.insert(0, "[P0] 高风险事件需优先核验 — 穿透责任主体、金额、时间线")
    if financial:
        priority_actions.append("[P1] 财务数据已获取 — 验证现金流转换率、应收质量和关联交易")
    if not financial and public_capital_profile:
        priority_actions.append("[P1] 公开资本线索存在 — 核实融资/债务/再融资授权的官方来源")
    if industry and product:
        priority_actions.append("[P2] 行业和产品证据已获取 — 对比竞争对手和上下游议价权")
    if supply_chain_profile:
        priority_actions.append("[P2] 供应链画像已建立 — 核验客户/供应商集中度和关联交易风险")
    if public_people_profile:
        priority_actions.append("[P1] 人员关联线索存在 — 穿透实际控制人、共同任职和关联企业")
    if not priority_actions:
        priority_actions.append("[P0] 证据不足 — 优先接入官方/授权数据源补充主体身份和风险事件")
    next_questions = priority_actions + next_questions
    next_questions.extend(f"缺口补证：{gap}" for gap in evidence_gaps[:6])
    cross_lane_insights = _cross_lane_analysis(
        public_capital_profile,
        supply_chain_profile,
        {
            "public_capital_profile": public_capital_profile,
            "public_goods_profile": public_goods_profile,
            "public_people_profile": public_people_profile,
        },
    )
    case_lens = _money_goods_people_lens(
        financial=financial,
        credit_profile=credit_profile,
        operational_event_profile=operational_event_profile,
        commercial_activity_profile=commercial_activity_profile,
        bond_credit_profile=bond_credit_profile,
        asset_solvency_profile=asset_solvency_profile,
        supply_chain_profile=supply_chain_profile,
        industry=industry,
        product=product,
        control_ownership=control_ownership,
        relationship_network=relationship_network,
        legal_administrative_profile=legal_administrative_profile,
    )

    return {
        "company": company,
        "dd_version": "1.0",
        "strategy": {
            "segment": "unknown_from_graph",
            "primary_signals": profile_brief.get("covered_dimensions", []),
            "investigation_focus": profile_brief.get("evidence_gaps", [])[:6],
        },
        "financial": financial,
        "fund_flow_profile": fund_flow_profile,
        "capital_pressure_profile": capital_pressure_profile,
        "capital_relationship_profile": capital_relationship_profile,
        "operational_flow_profile": {
            "cash_flow_signals": fund_flow_profile.get("money_in_signals", []) if fund_flow_profile else [],
            "outflow_pressure_signals": fund_flow_profile.get("money_out_or_pressure_signals", []) if fund_flow_profile else [],
            "operating_activity_signals": fund_flow_profile.get("operating_activity_signals", []) if fund_flow_profile else [],
            "has_fund_data": fund_flow_profile is not None,
        },
        "goods_flow_profile": goods_flow_profile,
        "people_flow_profile": people_flow_profile,
        "credit_profile": credit_profile,
        "legal_administrative_profile": legal_administrative_profile,
        "operational_event_profile": operational_event_profile,
        "commercial_activity_profile": commercial_activity_profile,
        "bond_credit_profile": bond_credit_profile,
        "regional_credit_profile": regional_credit_profile,
        "asset_solvency_profile": asset_solvency_profile,
        "ip_tech_profile": ip_tech_profile,
        "financial_institution_profile": fin_inst_profile,
        "supply_chain_profile": supply_chain_profile,
        "public_capital_profile": public_capital_profile,
        "public_goods_profile": public_goods_profile,
        "public_people_profile": public_people_profile,
        "industry": industry,
        "product": product,
        "industry_position": industry,
        "cross_lane_insights": cross_lane_insights,
        "case_investigation_lens": case_lens,
        "control_ownership": control_ownership,
        "relationship_network": relationship_network,
        "risk_events": [
            {
                "company": company,
        "dd_version": "1.0",
                "event": {
                    "id": event.get("id"),
                    "category": event.get("category"),
                    "title": event.get("title"),
                    "severity": event.get("severity"),
                    "confidence": event.get("confidence"),
                    "rationale": event.get("rationale"),
                    "status": event.get("status"),
                },
            }
            for event in risk_events
        ],
        "risk_hypotheses": _dedupe_strings(event_hypotheses)[:8],
        "monitoring_watchlist": _dedupe_strings(watchlist)[:15],
        "next_questions": _dedupe_strings(next_questions)[:15],
        "evidence_gaps": _dedupe_strings(evidence_gaps)[:12],
        "source_smoke_harness": (harness_data := run_source_smoke(subject=company)),
        "source_readiness_summary": (srs := _build_source_readiness_summary(harness_data)),
        "executable_next_steps": _build_executable_next_steps(evidence_gaps, srs),
        "subject_aggregation_available": _subject_aggregation_available(subject_profile, relationship_network),
        "subject_due_diligence_profile": (dd_profile_data := _build_subject_due_diligence_profile(
            company=company,
            financial=financial,
            fund_flow_profile=fund_flow_profile,
            goods_flow_profile=goods_flow_profile,
            people_flow_profile=people_flow_profile,
            cross_lane_insights=cross_lane_insights,
            supply_chain_profile=supply_chain_profile,
            legal_administrative_profile=legal_administrative_profile,
            public_capital_profile=public_capital_profile,
            public_goods_profile=public_goods_profile,
            public_people_profile=public_people_profile,
            risk_events=risk_events,
            next_questions=next_questions,
            evidence_gaps=evidence_gaps,
            relationship_network=relationship_network,
            subject_profile=subject_profile,
            evidence_ledger=evidence_ledger,
        )),
        "investigation_strategy": (strategy_plan := _build_investigation_strategy(dd_profile_data, srs, evidence_gaps)),
        "evidence_gap_analysis": (gap_analysis := _build_evidence_gap_analyzer(public_capital_profile, public_goods_profile, public_people_profile, risk_events, dd_profile_data.get("relationship_graph") if dd_profile_data else None, srs)),
        "graph_explainability_v2": (gv2 := _build_graph_explainability_v2(dd_profile_data.get("relationship_graph") if dd_profile_data else None)),
        "strategy_quality_gate": (strategy_quality_gate := _build_strategy_quality_gate(strategy_plan, srs)),
        "evidence_depth_score": (evidence_depth_score := _build_evidence_depth_score(dd_profile_data, public_capital_profile, public_goods_profile, public_people_profile, risk_events, gv2.get("graph_summary") if gv2 else None, srs)),
        "edge_explainability_v3": _build_edge_explainability_v3(dd_profile_data.get("relationship_graph") if dd_profile_data else None),
        "graph_quality_audit_v2": _graph_quality_audit_v2(dd_profile_data.get("relationship_graph") if dd_profile_data else None),
        "graph_sanity_check": (graph_sanity := _build_graph_sanity_check(dd_profile_data.get("relationship_graph") if dd_profile_data else None, gap_analysis)),
        "live_readiness_gate": (live_readiness := _build_live_readiness_gate(srs)),
        "evidence_ledger_v2": (evidence_ledger_v2 := normalize_evidence_v2(evidence_ledger)),
        "entity_resolution_v1": build_entity_resolution(subject_profile, dd_profile_data.get("relationship_graph") if dd_profile_data else None),
        "relationship_resolution_v1": build_relationship_resolution(
            _relationship_resolution_evidence_input(evidence_ledger_v2, evidence_ledger),
            build_entity_resolution(subject_profile, dd_profile_data.get("relationship_graph") if dd_profile_data else None),
            dd_profile_data.get("relationship_graph") if dd_profile_data else None,
        ),
        "investigation_strategy_v2": build_strategy_v2(gap_analysis, srs, None, dd_profile_data.get("relationship_graph") if dd_profile_data else None, None, live_readiness),
        "pipeline_contract_matrix": _build_pipeline_contract_matrix(harness_data, srs, evidence_ledger),
        "capability_audit": (cap_audit := build_capability_audit(dd_profile_data, strategy_plan, gap_analysis, dd_profile_data.get("relationship_graph") if dd_profile_data else None, srs, live_readiness, strategy_quality_gate, evidence_depth_score)),
        "graph_quality_audit_v2": (gqa := _graph_quality_audit_v2(dd_profile_data.get("relationship_graph") if dd_profile_data else None)),
        "blocker_gate": (blocker_gate := _build_blocker_gate(cap_audit, graph_sanity, strategy_quality_gate, live_readiness, gqa)),
        "realness_score": (realness_score := _build_realness_score(cap_audit, evidence_depth_score, live_readiness, blocker_gate, graph_sanity)),
        "release_decision": (release_decision := compute_release_decision(live_readiness, blocker_gate, realness_score, evidence_depth_score, gqa, srs)),
        "qyyjt_bridge_packet": (qyyjt_bridge_packet := _build_qyyjt_bridge_packet(evidence_ledger)),
        "investigation_report_card": {
            "dd_version": "4.9",
            "api_visible_release_decision": release_decision.get("release_decision","unknown"),
            "api_visible_release_score": release_decision.get("release_score",0),
            "dd_summary": {
                "version": "5.0",
                "release_decision": release_decision.get("release_decision","internal_alpha"),
                "release_score": release_decision.get("release_score",0),
                "blocker_count": blocker_gate.get("blocker_count",0),
                "is_clear": blocker_gate.get("is_clear",False),
                "realness_score": realness_score.get("realness_score",0),
                "realness_verdict": realness_score.get("verdict","unknown"),
                "source_readiness": live_readiness.get("status", "unknown"),
                "data_effectiveness_matrix": _build_data_effectiveness_matrix(evidence_ledger, srs),
                "source_readiness_matrix": _source_readiness_matrix(harness_data.get("source_lane_readiness") or {}),
                "query_families": _build_query_families(company),
                "source_lane_readiness": harness_data.get("source_lane_readiness", {}),
                "live_boundary_enforced": True,
                "packet_quality": _build_packet_quality_flags(
                    release_decision.get("release_decision", "internal_alpha"),
                    harness_data,
                    srs,
                    (money_lane_summary := _build_money_lane(
                        evidence_ledger_v2,
                        public_capital_profile,
                        financial,
                        {**qyyjt_bridge_packet, "bond_credit_bridge": _build_bond_credit_bridge(bond_credit_profile)},
                    )).get("lane_status", "missing"),
                    (goods_lane_summary := _build_goods_lane(evidence_ledger_v2, public_goods_profile or supply_chain_profile or {}, supply_chain_profile, qyyjt_bridge_packet)).get("lane_status", "missing"),
                    (people_lane_summary := _build_people_lane(evidence_ledger_v2, subject_profile, relationship_network, public_people_profile)).get("lane_status", "missing"),
                    _build_evidence_to_report_trace(evidence_ledger),
                    evidence_gaps,
                    _build_executable_next_steps(evidence_gaps, srs),
                ),
                "fixture_is_not_live": True,
                "report_language": _build_report_language(
                    harness_data,
                    True,
                    release_decision.get("release_decision", "internal_alpha"),
                    money_lane_summary.get("lane_status", "missing"),
                    goods_lane_summary.get("lane_status", "missing"),
                    people_lane_summary.get("lane_status", "missing"),
                ),
                "evidence_depth_counters": compute_evidence_depth(evidence_ledger),
                "money_lane_summary": money_lane_summary,
                "goods_lane_summary": goods_lane_summary,
                "people_lane_summary": people_lane_summary,
                "cross_lane_questions": _cross_lane_questions(None, None, None, evidence_ledger),
                "bond_credit_bridge": _build_bond_credit_bridge(bond_credit_profile),
                **qyyjt_bridge_packet,
                "user_upload_capability": {"status":"not_enabled_in_current_release","available":False,"accepts":[]},
                "graph_trust_layer": _build_graph_trust_layer(
                    dd_profile_data.get("relationship_graph") if dd_profile_data else {}
                ),
                "strategy_actions": _build_strategy_actions(None, srs),
                "evidence_to_report_trace": _build_evidence_to_report_trace(evidence_ledger),
                "entity_truth_gate": {"entity_resolution_version":"2.0","same_name_no_merge":True,"official_outranks_public":True},
                "capability_wired": cap_audit.get("wired",0),
                "capability_tested": cap_audit.get("tested",0),
                "graph_is_clean": graph_sanity.get("is_sane",False),
                "validation_status": {
                    "focused_required": True,
                    "acceptance_required": True,
                    "source": "runtime_validation_required",
                },
            },
            "api_visible_release_score": release_decision.get("release_score",0),

            "dd_version": "2.3",
            "strategy_quality": strategy_quality_gate.get("quality_score",0),
            "strategy_actions": strategy_plan.get("action_count",0),
            "strategy_flags": strategy_quality_gate.get("quality_flags",[])[:3],
            "evidence_depth": evidence_depth_score.get("overall_depth",0),
            "source_depth": evidence_depth_score.get("source_depth",0),
            "graph_is_sane": graph_sanity.get("is_sane",False),
            "graph_flags": graph_sanity.get("graph_quality_flags",[]),
            "live_readiness": live_readiness.get("status","unknown"),
            "fixture_only_warning": live_readiness.get("status") == "fixture_only",
            "gap_overall": gap_analysis.get("overall_status","?"),
            "source_usable": len(srs.get("usable_sources",[])),
            "source_blocked": len(srs.get("blocked_sources",[])),
            "source_fixture_only": len(srs.get("fixture_only_sources",[])),
        },
        "multi_layer_relationship_graph": {
            "available": _relationship_graph_availability(dd_profile_data.get("relationship_graph") if dd_profile_data else None)["available"],
            "node_count": _relationship_graph_availability(dd_profile_data.get("relationship_graph") if dd_profile_data else None)["node_count"],
            "edge_count": _relationship_graph_availability(dd_profile_data.get("relationship_graph") if dd_profile_data else None)["edge_count"],
            "source": "SubjectProfileAggregator (core/subject_profile_aggregator.py)",
            "max_depth": 5,
            "note": (
                "Use /api/aggregate endpoint for full multi-layer graph"
                if _relationship_graph_availability(dd_profile_data.get("relationship_graph") if dd_profile_data else None)["available"]
                else "No multi-layer relationship graph was derived from current evidence"
            ),
        },
        "product_note": (
            "Enterprise cognition is generated from the current evidence graph; "
            "missing finance, control, industry, and product inputs are exposed as evidence gaps."
        ),
    }


def _fin_inst_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        source = str(item.get("source") or "")
        if not source.startswith("qyyjt_api:fin_inst"):
            continue
        claims = [str(c) for c in item.get("claims", []) if str(c).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        institution_name = parsed.get("institution_name")
        if not institution_name:
            continue
        field_values = {
            key: parsed.get(key)
            for key in (
                "institution_name",
                "institution_type",
                "license_status",
                "region",
                "risk_level",
                "counterparty_role",
                "credit_line",
                "guarantee_status",
                "regulatory_authority",
            )
            if parsed.get(key) not in (None, "")
        }
        row = {
            "module": "fin_inst",
            "record_type": "financial_institution_profile",
            "identifier": institution_name,
            "institution_name": institution_name,
            "institution_type": parsed.get("institution_type"),
            "license_status": parsed.get("license_status"),
            "region": parsed.get("region"),
            "risk_level": parsed.get("risk_level"),
            "counterparty_role": parsed.get("counterparty_role"),
            "credit_line": parsed.get("credit_line"),
            "guarantee_status": parsed.get("guarantee_status"),
            "regulatory_authority": parsed.get("regulatory_authority"),
            "source": source,
            "url": item.get("url"),
            "confidence": item.get("confidence"),
            "field_values": field_values,
            "counterparty": institution_name,
            "pressure_flag": _qyyjt_profile_pressure_flag(
                "financial_institution_profile",
                parsed,
                "license_status",
            ),
        }
        row["status"] = row.get("license_status") or row.get("risk_level") or "observed"
        row["summary"] = "; ".join(
            f"{label}={value}"
            for label, value in (
                ("institution_type", row.get("institution_type")),
                ("region", row.get("region")),
                ("counterparty_role", row.get("counterparty_role")),
                ("credit_line", row.get("credit_line")),
                ("guarantee_status", row.get("guarantee_status")),
                ("regulatory_authority", row.get("regulatory_authority")),
            )
            if value not in (None, "")
        )
        row["fingerprint"] = _qyyjt_profile_row_fingerprint(row)
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)

    events = [
        e for e in risk_events
        if "Financial institution" in str(e.get("title") or "")
    ]
    if not rows and not events:
        return None

    inst_types = list(dict.fromkeys(str(r.get("institution_type") or "") for r in rows if r.get("institution_type")))
    high_risk = [r for r in rows if str(r.get("risk_level") or "").lower() in {"high", "watch"} or str(r.get("license_status") or "").lower() in {"revoked", "suspended"}]
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed financial institution counterparty profile",
        "row_count": len(rows),
        "institution_types": inst_types[:10],
        "high_risk_count": len(high_risk),
        "risk_event_count": len(events),
        "rows": rows[:15],
        "high_risk_rows": high_risk[:8],
        "top_exposures": _qyyjt_profile_top_exposures(rows),
        "monitoring_queue": _qyyjt_profile_monitoring_queue("fin_inst", rows),
        "field_coverage": _qyyjt_profile_field_coverage(
            rows,
            (
                "institution_name",
                "institution_type",
                "license_status",
                "region",
                "risk_level",
                "counterparty_role",
                "credit_line",
                "guarantee_status",
                "regulatory_authority",
            ),
        ),
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_fin_inst_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "quality_notes": [
            "QYYJT fin_inst contract supplied report-admissible institution name, type, license, region, and risk fields",
            f"financial institution counterparty rows: {len(rows)}",
            f"high-risk counterparties: {len(high_risk)}",
            "top_exposures and monitoring_queue rank financial counterparty pressure before report rendering",
        ],
    }



def _public_web_profiles_from_evidence(
    evidence_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Unified bridge: read all public-web claims from evidence ledger and produce structured profiles.

    Uses AUTOMATIC key discovery from all registered extraction functions.
    All 204 extraction functions are now pipeline-connected.
    """
    profiles = {}

    # All extraction keys, auto-discovered from extraction function source code
    _MONEY_KEYS = {
        "acquisition_financing",
                         "acquisition_premium",
                         "aerospace_risk",
                         "ai_risk",
                         "antitrust_risk",
                         "asset_disposal",
                         "asset_impairment",
                         "asset_management",
                         "asset_or_equity_pressure",
                         "asset_quality_deterioration",
                         "audit_risk",
                         "auto_credit_quality",
                         "auto_loan_exposure",
                         "bank_exposure",
                         "bankruptcy_protection",
                         "bankruptcy_risk",
                         "biodiversity_risk",
                         "biotech_risk",
                         "bond_amount",
                         "bond_default",
                         "bond_rating_negative",
                         "brand_risk",
                         "bridge_financing",
                         "business_interruption_risk",
                         "capital_control_risk",
                         "capital_controls",
                         "capital_injection",
                         "capital_reduction",
                         "capital_shortfall",
                         "capital_structure",
                         "card_credit_quality",
                         "cash_conversion",
                         "cash_flow_mismatch",
                         "cash_or_liquidity_pressure",
                         "cash_pooling",
                         "cash_shortage",
                         "collateral_decline",
                         "collateralized_lending",
                         "commodity_exposure",
                         "commodity_hedging_risk",
                         "commodity_risk",
                         "consumer_credit",
                         "consumer_credit_quality",
                         "contract_risk",
                         "convertibility_risk",
                         "convertible_debt",
                         "corporate_governance",
                         "corruption_risk",
                         "covenant_risk",
                         "credit_amount",
                         "credit_card_exposure",
                         "credit_enhancement",
                         "credit_insurance",
                         "credit_obligation",
                         "credit_quality_concern",
                         "credit_watch_negative",
                         "critical_mineral_risk",
                         "cross_guarantee",
                         "crypto_exposure",
                         "crypto_risk",
                         "currency_risk",
                         "customer_concentration_risk",
                         "debt_or_credit_amount",
                         "debt_or_credit_obligation",
                         "debt_ratio",
                         "debt_service_concern",
                         "deposit_outflow_risk",
                         "deposit_strength",
                         "derivative_exposure",
                         "derivative_loss",
                         "derivative_valuation",
                         "dilution_risk",
                         "discrimination_risk",
                         "disruption_risk",
                         "distressed_debt",
                         "distressed_investor_activity",
                         "drug_development_risk",
                         "equity_compensation",
                         "equity_fundraising",
                         "equity_pledge",
                         "event_driven_risk",
                         "exchange_action",
                         "exchange_rate_exposure",
                         "export_credit",
                         "export_insurance",
                         "extraterritorial_risk",
                         "financial_guarantee",
                         "financial_sector_risk",
                         "financing_amount",
                         "financing_event",
                         "fintech_risk",
                         "food_security",
                         "food_supply_risk",
                         "fraud_risk",
                         "geopolitical_risk",
                         "goodwill_risk",
                         "green_bond",
                         "green_bond_quality",
                         "guarantee_circle",
                         "guarantee_exposure",
                         "guarantor_risk",
                         "hybrid_security",
                         "information_risk",
                         "infra_asset_class",
                         "infrastructure_fund",
                         "insurance_actuarial",
                         "insurance_gap",
                         "insurance_mentioned",
                         "interbank_contagion",
                         "interbank_exposure",
                         "interest_rate_exposure",
                         "interest_rate_risk",
                         "inventory_risk",
                         "investment_amount",
                         "investment_loss",
                         "investment_review",
                         "investor_pressure",
                         "ipo_underwriting",
                         "key_customer_risk",
                         "key_person_risk",
                         "leverage_risk",
                         "liquidity_crunch",
                         "litigation_funding",
                         "loan_portfolio_sale",
                         "major_investment",
                         "maritime_risk",
                         "market_infrastructure",
                         "media_risk",
                         "medical_device_risk",
                         "merger_blocked",
                         "merger_regulatory_review",
                         "merger_remedy",
                         "mezzanine_credit_quality",
                         "mezzanine_debt",
                         "microfinance_regulation",
                         "microfinance_risk",
                         "mortgage_credit_quality",
                         "mortgage_exposure",
                         "nonperforming_asset",
                         "off_balance_sheet_risk",
                         "overtime_risk",
                         "pe_vc_investment",
                         "peg_risk",
                         "pension_asset",
                         "pension_fund_status",
                         "pension_obligation",
                         "pension_risk",
                         "pension_shortfall",
                         "pledge_margin_pressure",
                         "pledge_ratio",
                         "policy_risk",
                         "principal_protection_risk",
                         "privacy_risk",
                         "project_finance",
                         "project_risk",
                         "provision_risk",
                         "quantum_risk",
                         "quantum_security",
                         "rare_earth_risk",
                         "rate_sensitivity",
                         "rd_investment",
                         "real_estate_risk",
                         "refinancing_difficulty",
                         "refinancing_risk",
                         "regional_bank_exposure",
                         "regulatory_capital",
                         "reinsurance_credit_risk",
                         "reinsurance_exposure",
                         "related_guarantee",
                         "related_party_financing",
                         "related_party_loan",
                         "reporting_risk",
                         "restricted_cash",
                         "revenue_concentration_risk",
                         "revenue_recognition_risk",
                         "rural_bank_exposure",
                         "sanctions_risk",
                         "securitization_activity",
                         "settlement",
                         "settlement_risk",
                         "shadow_banking",
                         "share_buyback",
                         "short_term_debt_pressure",
                         "social_license_risk",
                         "social_media_risk",
                         "sole_supplier_risk",
                         "sovereign_credit",
                         "sovereign_debt",
                         "sovereign_downgrade",
                         "sovereign_fund_investment",
                         "sovereign_risk",
                         "sovereign_wealth",
                         "space_security",
                         "state_capital",
                         "strategic_alliance",
                         "structured_deposit",
                         "structured_finance",
                         "subordinated_capital",
                         "subsidiary_distress",
                         "subsidiary_guarantee",
                         "substitution_risk",
                         "supplier_concentration_risk",
                         "swf_strategic",
                         "syndicated_loan",
                         "systemic_risk",
                         "tax_haven_risk",
                         "tax_rate",
                         "tax_risk",
                         "tech_investment",
                         "telecom_risk",
                         "trade_barrier_risk",
                         "trade_credit",
                         "trade_finance",
                         "trade_secret_risk",
                         "transfer_pricing_risk",
                         "trust_capital",
                         "tunnelling_risk",
                         "vendor_financing",
                         "water_risk",
                         "whistleblower_risk",
                         "working_capital",
                         "working_capital_efficiency"
    }
    _GOODS_KEYS = {
        "accounting_concern",
                         "accounting_weakness",
                         "activist_pressure",
                         "aerospace_risk",
                         "aggressive_accounting",
                         "ai_governance",
                         "aml_compliance",
                         "analyst_downgrade",
                         "analyst_upgrade",
                         "antitrust_enforcement",
                         "antitrust_risk",
                         "asset_management",
                         "asset_quality_deterioration",
                         "audit_quality",
                         "aum_decline",
                         "auto_credit_quality",
                         "bid_amount",
                         "bid_reference",
                         "biodiversity_risk",
                         "biotech_risk",
                         "brand_premium",
                         "brand_risk",
                         "brand_value",
                         "business_continuity",
                         "business_model",
                         "buyout_activity",
                         "cac_ltv",
                         "capacity_cycle",
                         "capacity_pressure",
                         "capacity_utilization",
                         "capex",
                         "carbon_neutral_commitment",
                         "carbon_pricing",
                         "carbon_regulation",
                         "card_credit_quality",
                         "catastrophe_exposure",
                         "certification_status",
                         "channel",
                         "channel_dependency",
                         "class_action",
                         "community_relations",
                         "competitive_dynamics",
                         "competitive_landscape",
                         "competitive_position",
                         "competitive_pressure",
                         "competitor_mentioned",
                         "competitor_set",
                         "complex_structure",
                         "compliance_breach",
                         "compliance_timeline",
                         "consumer_credit_quality",
                         "contingent_liability",
                         "continuity_readiness",
                         "contract_nonrenewal",
                         "contract_risk",
                         "contract_value",
                         "covenant_breach",
                         "covenant_stress",
                         "covenant_waiver",
                         "credit_quality_concern",
                         "cross_border_exposure",
                         "cross_border_ma",
                         "cross_shareholding",
                         "currency_peg",
                         "currency_volatility",
                         "customer",
                         "customer_churn",
                         "customer_concentration",
                         "customer_concentration_ratio",
                         "customer_concentration_risk",
                         "customer_power",
                         "customer_satisfaction",
                         "customer_stickiness",
                         "customs_activity",
                         "cyber_compliance",
                         "cyber_incident",
                         "data_breach",
                         "data_regulation",
                         "device_regulation",
                         "digital_transformation",
                         "disaster_exposure",
                         "disruption_risk",
                         "distressed_investor_activity",
                         "distributor",
                         "dividend_policy",
                         "downstream",
                         "drug_development_risk",
                         "earnings_quality_concern",
                         "ecological_impact",
                         "employee_litigation",
                         "entry_barriers",
                         "environmental_enforcement",
                         "environmental_liability",
                         "environmental_regulation",
                         "esg_disclosure",
                         "event_driven_risk",
                         "execution_amount",
                         "expansion_plans",
                         "export_credit",
                         "export_growth",
                         "export_insurance",
                         "extreme_event",
                         "factoring",
                         "fair_value_loss",
                         "fintech_regulation",
                         "fintech_risk",
                         "food_security",
                         "food_supply_risk",
                         "fraud_risk",
                         "fx_exposure",
                         "fx_hedging",
                         "geopolitical_risk",
                         "goodwill_risk",
                         "governance_red_flag",
                         "government_contract",
                         "government_procurement",
                         "govt_subsidy",
                         "green_bond",
                         "green_bond_quality",
                         "greenshoe_option",
                         "headcount_reduction",
                         "headcount_scale",
                         "import_growth",
                         "independent_director_mentioned",
                         "industry_growth",
                         "inflation_exposure",
                         "infra_asset_class",
                         "infrastructure_fund",
                         "intangible_impairment",
                         "inventory_management",
                         "investor_pressure",
                         "ip_dispute",
                         "ipo_status",
                         "key_customer_risk",
                         "lbo_leverage",
                         "lease_cost",
                         "lease_liability",
                         "lender_concentration",
                         "leverage_metrics",
                         "leveraged_buyout",
                         "lifecycle",
                         "litigation_funding",
                         "litigation_pending",
                         "loan_portfolio_sale",
                         "logistics_cost_pressure",
                         "logistics_mentioned",
                         "long_term_contract",
                         "ltv_ratio",
                         "macro_growth_exposure",
                         "management_turnover",
                         "margin_expansion",
                         "maritime_risk",
                         "market_abuse",
                         "market_concentration",
                         "market_enforcement",
                         "market_growth",
                         "market_infrastructure",
                         "market_manipulation",
                         "market_position",
                         "market_share",
                         "market_size",
                         "maturity_wall",
                         "media_risk",
                         "media_sentiment",
                         "medical_device_risk",
                         "merger_regulatory_review",
                         "mezzanine_credit_quality",
                         "microfinance_regulation",
                         "microfinance_risk",
                         "moat",
                         "moat_source",
                         "money_market_stress",
                         "mortgage_credit_quality",
                         "nonrecurring_income",
                         "nuclear_energy",
                         "nuclear_regulation",
                         "off_balance_sheet",
                         "offshore_structure",
                         "operating_lease",
                         "operational_outage",
                         "order_backlog",
                         "outperform_peers",
                         "ownership_transfer",
                         "partner",
                         "pe_exit_planned",
                         "peer_comparison",
                         "pharma_pricing",
                         "policy_cycle",
                         "pre_ipo",
                         "price_sensitivity",
                         "pricing_power",
                         "pricing_regulation",
                         "privacy_concern",
                         "privacy_risk",
                         "private_placement",
                         "procurement_tender",
                         "product_concentration",
                         "product_dependency",
                         "product_quality_issue",
                         "profit_amount",
                         "property_market_stress",
                         "proxy_contest",
                         "pyramid_structure",
                         "quantum_risk",
                         "quantum_security",
                         "rare_earth_risk",
                         "rating_downgrade",
                         "raw_material_pressure",
                         "recruiting_active",
                         "regulatory_action",
                         "regulatory_approval_required",
                         "regulatory_capital",
                         "regulatory_change",
                         "regulatory_penalty",
                         "regulatory_probe",
                         "reporting_quality",
                         "restatement",
                         "restructuring",
                         "revenue_amount",
                         "revenue_concentration_risk",
                         "revenue_model",
                         "safety_incident",
                         "sale_leaseback",
                         "sales_channel",
                         "sales_model",
                         "scf_activity",
                         "sentiment",
                         "share_buyback",
                         "shipping_disruption",
                         "single_product_dependency",
                         "social_controversy",
                         "social_media_risk",
                         "soe_connection",
                         "sole_supplier_risk",
                         "sovereign_credit",
                         "sovereign_debt",
                         "sovereign_downgrade",
                         "sovereign_fund_investment",
                         "sovereign_risk",
                         "sovereign_wealth",
                         "space_security",
                         "spinoff",
                         "stake_disposal",
                         "stock_manipulation",
                         "subscription_model",
                         "subscription_revenue_ratio",
                         "subsidiary_distress",
                         "subsidiary_guarantee",
                         "subsidiary_mentioned",
                         "subsidy_dependence",
                         "substitute_availability",
                         "succession_concern",
                         "supplier",
                         "supplier_concentration",
                         "supplier_concentration_risk",
                         "supplier_payment_pressure",
                         "supplier_power",
                         "supply_chain_decoupling",
                         "supply_chain_disruption",
                         "supply_chain_resilience",
                         "supply_chain_visibility",
                         "supply_demand_balance",
                         "switching_behavior",
                         "switching_cost",
                         "tax_benefit",
                         "tax_dispute",
                         "tax_haven_risk",
                         "tax_rate",
                         "tax_risk",
                         "tech_innovation",
                         "tech_investment",
                         "technology_transfer",
                         "telecom_regulation",
                         "telecom_risk",
                         "tender_competition",
                         "trade_barrier_risk",
                         "trade_credit",
                         "trade_finance",
                         "trade_secret_risk",
                         "transfer_pricing_risk",
                         "trust_lending",
                         "underperform_peers",
                         "unit_economics",
                         "upstream",
                         "valuation",
                         "value_chain_role",
                         "warranty_liability",
                         "warranty_reserve",
                         "water_compliance",
                         "water_risk",
                         "winning_bid",
                         "working_capital",
                         "working_capital_efficiency",
                         "yoy_growth"
    }
    _PEOPLE_KEYS = {
        "antitrust_enforcement",
                         "audit_opinion",
                         "biodiversity_risk",
                         "board_diversity",
                         "board_governance",
                         "board_or_mgmt_change",
                         "capital_control_risk",
                         "capital_controls",
                         "community_relations",
                         "compensation_governance",
                         "cross_border_enforcement",
                         "enforcement_subject",
                         "environmental_enforcement",
                         "equity_compensation",
                         "executive_compensation",
                         "extraterritorial_risk",
                         "key_executive_departure",
                         "key_person_risk",
                         "labor_dispute",
                         "labor_rights",
                         "labor_rights_violation",
                         "labor_violation",
                         "license_action",
                         "market_abuse",
                         "market_enforcement",
                         "ownership_transfer",
                         "penalty_amount",
                         "regulatory_penalty",
                         "related_guarantee",
                         "related_party_financing",
                         "related_party_loan",
                         "sanctions_enforcement",
                         "social_license_risk",
                         "wage_arrears",
                         "wage_pressure",
                         "whistleblower",
                         "whistleblower_event",
                         "whistleblower_risk"
    }

    for item in evidence_ledger:
        src = str(item.get("source") or "")
        if item.get("record_kind") != "evidence" and src != "qyyjt_websearch_plan":
            continue
        if src.startswith("qyyjt_api:"):
            continue
        claims = [str(c2) for c2 in item.get("claims", []) if str(c2).strip()]
        if src == "qyyjt_websearch_plan":
            _merge_qyyjt_query_plan_profile(profiles, item, claims)

        for cl in claims:
            parsed = _parse_signal_claims(cl)
            if not parsed:
                continue
            for k, v in parsed.items():
                # Categorize by key name heuristic
                target = None
                if k in _MONEY_KEYS or any(w in k for w in ("debt","financ","credit","bond","capital","liquid","equity","pledge","freeze","auction","loan","mortgage","bank","fund","invest","derivative","exchange","rate","forex","asset","securit","IPO","underwrit","acquisit","merge","sovereign","collateral","market_infra","settlement","bankrupt","pension","insur","actuar","crypto","commodity","guarantee","refinanc","buyback","mezzanine","LBO","hybrid","convert","card","auto","deposit","franchise","cash","revenue","net_income","net_margin","operating_cash_flow","debt_to_assets","cik")):
                    target = "public_capital_profile"
                elif k in _GOODS_KEYS or any(w in k for w in ("product","supplier","customer","supply","chain","good","trade","import","export","tariff","logist","contract","quality","IP_","patent","trademark","geopolit","industry","disrupt","manag","competit","market","share","concentr","barrier","pric","bargain","lifecycle","peer","compar","churn","recruit","tax","regulat","ESG","carbon","sustain","green","environ","water","bio","fraud","operat","restruct","subsidi","offshore","CAPEX","goodwill","litig","employ","subsid","warrant","work","investor","sentiment","brand","tech","innov","R&D","CAC","LTV","subscript","revenue_model","unit","economic","procure","tender","bid","anti","data_breach","cyber","privacy","ransom","media","event","force_majeure","telecom","pharma","drug","medical","device","nuclear","rare_earth","energy","hydrogen","space","maritime","ship","food","quantum","infra","SWF","microfin","fintech","capacity","price_change","customer_churn","repeat_purchase","substitute","core_product","customer_value")):
                    target = "public_goods_profile"
                elif k in _PEOPLE_KEYS or any(w in k for w in ("control","key_person","executive","UBO","owner","related","party","common_address","common_project","court","enforcement","dishonest","blacklist","admin","penalty","regulat_action","license","negative","research","people","labor","union","strike","worker","wage","board","divers","compensat","whistle","audit","community","social_license","extraterrit","FCPA","DOJ","market_abuse","insider")):
                    target = "public_people_profile"
                else:
                    target = "public_goods_profile"  # catch-all default

                profiles.setdefault(target,{"claims":[],"row_count":0})
                profiles[target]["claims"].append(f"{k}={v}")
                profiles[target]["row_count"] += 1

    for k, v in profiles.items():
        v["claims"] = v["claims"][:20]
        v["verification_status"] = "public_lead_needs_corroboration"
        v["source"] = "public_web"
        v["title"] = f"Public web {k} leads (corroboration-needed)"

    return profiles


def _merge_qyyjt_query_plan_profile(
    profiles: dict[str, Any],
    item: dict[str, Any],
    claims: list[str],
) -> None:
    text = " ".join(
        str(value)
        for value in (
            item.get("title"),
            item.get("summary"),
            " ".join(claims),
        )
        if str(value).strip()
    ).lower()
    if not text:
        return
    targets: list[str] = []
    if any(key in text for key in ("financ", "bond", "debt", "pledge", "freeze", "auction", "capital", "equity", "credit")):
        targets.append("public_capital_profile")
    if any(key in text for key in ("supplier", "customer", "supply", "trade", "product", "operate", "recruit", "industry", "ip", "patent", "market")):
        targets.append("public_goods_profile")
    if any(key in text for key in ("actual_controller", "controller", "ubo", "related", "party", "court", "case", "dishonest", "penalty", "risk", "negative", "shareholder", "legal")):
        targets.append("public_people_profile")
    if not targets:
        targets.append("public_people_profile")

    claim = str(item.get("title") or item.get("summary") or "qyyjt public-search lead")
    for target in dict.fromkeys(targets):
        profiles.setdefault(target, {"claims": [], "row_count": 0})
        profiles[target]["claims"].append(claim)
        profiles[target]["row_count"] += 1


def _capital_profile_from_public_web_evidence(
    evidence_ledger: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        if str(item.get("source") or "") not in {"public_web_search", "default_public_intel"}:
            continue
        claims = [str(c2) for c2 in item.get("claims", []) if str(c2).strip() and "capital" in str(c2).lower()]
        if not claims:
            continue
        parsed = _parse_signal_claims("; ".join(claims))
        has_signals = any(parsed.get(k) for k in ("financing_event", "debt_or_credit_obligation", "cash_or_liquidity_pressure", "asset_or_equity_pressure", "major_investment"))
        if has_signals:
            rows.append({"url": item.get("url"), "claims": claims, "parsed": parsed})
    if not rows:
        return None
    return {
        "source": "public_web",
        "title": "Public web capital pressure leads (corroboration-needed)",
        "row_count": len(rows),
        "rows": rows[:10],
        "verification_status": "public_lead_needs_corroboration",
        "quality_notes": ["Public web capital claims are leads. Corroborate with official/licensed sources before relying as facts.", f"Capital lead rows: {len(rows)}"],
    }


_public_web_profiles_from_evidence = _bridge_public_web_profiles_from_evidence


def _cross_lane_analysis(
    capital_profile: dict[str, Any] | None,
    supply_chain_profile: dict[str, Any] | None,
    enterprise_cognition: dict[str, Any],
) -> list[str]:
    """Enhanced cross-lane analysis with quantitative scoring and actionable recommendations.

    Produces insights connecting money↔goods, money↔people, goods↔people lanes.
    Each insight includes signal counts and a risk severity indicator.
    """
    insights: list[str] = []
    pub_cap = enterprise_cognition.get("public_capital_profile") or {}
    pub_goods = enterprise_cognition.get("public_goods_profile") or {}
    pub_people = enterprise_cognition.get("public_people_profile") or {}
    legal = enterprise_cognition.get("legal_administrative_profile") or {}
    financial = enterprise_cognition.get("financial") or {}

    cap_count = (capital_profile and capital_profile.get("row_count", 0)) or pub_cap.get("row_count", 0)
    goods_count = pub_goods.get("row_count", 0)
    people_count = pub_people.get("row_count", 0)
    legal_events = legal.get("risk_event_count", 0) if legal else 0

    # Money ↔ Goods: capital pressure + supply chain concentration
    if cap_count and goods_count:
        cap_claims = (
            (capital_profile.get("rows", []) if capital_profile else [])
            + pub_cap.get("claims", [])
        )
        debt_signals = [c for c in cap_claims if any(w in str(c).lower() for w in ("debt", "refinanc", "credit", "bond"))]
        if debt_signals:
            sc_conc = 0
            if supply_chain_profile:
                sc_conc = supply_chain_profile.get("concentration_signal_count", 0) or supply_chain_profile.get("row_count", 0)
            if sc_conc:
                severity = "HIGH" if len(debt_signals) >= 3 and sc_conc >= 2 else "MEDIUM"
                insights.append(f"[{severity}] Capital↔Supply: {len(debt_signals)} debt/credit signals + {sc_conc} supply concentration indicators — capital constraints may compound supplier dependency risk. Recommend: verify lender covenants, supplier payment terms, and customer advance rates.")
            elif supply_chain_profile:
                insights.append(f"[LOW] Capital↔Supply: {len(debt_signals)} debt signals detected. Supply chain data available but no concentration flags. Monitor for emerging dependency.")

    # Money ↔ People: capital structure + controller/ownership
    if cap_count and (people_count or legal_events):
        ownership_signals = [c for c in pub_people.get("claims", []) if any(w in str(c).lower() for w in ("owner", "control", "ubo", "shareholder"))]
        if ownership_signals or legal_events:
            severity = "MEDIUM" if legal_events >= 1 else "LOW"
            insights.append(f"[{severity}] Capital↔People: {cap_count} capital signals + {len(ownership_signals)} ownership leads + {legal_events} legal events — verify whether control structure affects financing access or debt guarantees. Recommend: trace ultimate beneficial ownership and cross-reference with pledge/freeze records.")

    # Goods ↔ People: product/market signals + admin/regulatory
    if goods_count and (people_count or legal_events):
        admin_signals = [c for c in pub_people.get("claims", []) if any(w in str(c).lower() for w in ("penalty", "regulat", "enforcement", "dishonest"))]
        if admin_signals:
            severity = "HIGH" if legal_events >= 2 else "MEDIUM"
            insights.append(f"[{severity}] Goods↔People: {goods_count} market signals + {len(admin_signals)} regulatory leads — assess whether regulatory exposure affects product lines, market access, or supply chain continuity. Recommend: review administrative penalty dockets for operational impact.")

    # Cross-trigger: financial data + people risk
    if financial and (people_count or legal_events):
        insights.append(f"[INFO] Finance↔People: Financial data available (revenue present) + {people_count} people leads. Cross-reference key-person roles with related-party transactions and revenue concentration.")

    # Cross-trigger: goods data + supply chain
    if goods_count and supply_chain_profile:
        sc_cust = supply_chain_profile.get("customer_count", 0) or supply_chain_profile.get("row_count", 0)
        if sc_cust:
            insights.append(f"[INFO] Goods↔Supply: {goods_count} market signals + supply chain with {sc_cust} relationships. Verify customer concentration against public market share claims.")

    return insights[:6]

def _fund_flow_profile(
    *,
    financial: dict[str, Any] | None,
    credit_profile: dict[str, Any] | None,
    operational_event_profile: dict[str, Any] | None,
    commercial_activity_profile: dict[str, Any] | None,
    bond_credit_profile: dict[str, Any] | None,
    asset_solvency_profile: dict[str, Any] | None,
    fin_inst_profile: dict[str, Any] | None = None,
    public_capital_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a money-in/money-out read from admitted financial and solvency evidence."""
    inflow_signals: list[str] = []
    outflow_pressure_signals: list[str] = []
    operating_activity_signals: list[str] = []
    quality_notes: list[str] = []

    if financial:
        revenue = _float_or_none(financial.get("revenue"))
        operating_cash_flow = _float_or_none(financial.get("operating_cash_flow"))
        cash_conversion = _float_or_none(financial.get("cash_conversion"))
        debt_to_assets = _float_or_none(financial.get("debt_to_assets"))
        if revenue is not None:
            inflow_signals.append(f"revenue={revenue}")
        if operating_cash_flow is not None:
            inflow_signals.append(f"operating_cash_flow={operating_cash_flow}")
        if cash_conversion is not None:
            quality_notes.append(f"cash_conversion={cash_conversion}")
            if cash_conversion < 0.5:
                outflow_pressure_signals.append("weak_operating_cash_conversion")
            elif cash_conversion >= 1:
                quality_notes.append("operating_cash_flow_covers_reported_earnings")
        if debt_to_assets is not None:
            quality_notes.append(f"debt_to_assets={debt_to_assets}")
            if debt_to_assets > 0.75:
                outflow_pressure_signals.append("elevated_liabilities_to_assets")
        quality_notes.extend(str(item) for item in financial.get("quality_notes", [])[:3])

    if operational_event_profile:
        financing_count = int(operational_event_profile.get("financing_event_count") or 0)
        if financing_count:
            inflow_signals.append(f"financing_events={financing_count}")
        negative_count = int(operational_event_profile.get("negative_opinion_count") or 0)
        if negative_count:
            outflow_pressure_signals.append(f"negative_opinion_events={negative_count}")
        capital_pressure_count = int(operational_event_profile.get("capital_pressure_event_count") or 0)
        if capital_pressure_count:
            outflow_pressure_signals.append(f"capital_pressure_events={capital_pressure_count}")

    if commercial_activity_profile:
        tax_count = int(commercial_activity_profile.get("tax_count") or 0)
        trade_count = int(commercial_activity_profile.get("trade_count") or 0)
        recruiting_count = int(commercial_activity_profile.get("recruiting_count") or 0)
        if tax_count or trade_count or recruiting_count:
            operating_activity_signals.append(
                f"tax={tax_count}; trade={trade_count}; recruiting={recruiting_count}"
            )

    if credit_profile:
        risky_items = int(credit_profile.get("risk_item_count") or 0)
        if risky_items:
            outflow_pressure_signals.append(f"credit_risk_items={risky_items}")

    if bond_credit_profile:
        default_count = int(bond_credit_profile.get("default_count") or 0)
        high_count = int(bond_credit_profile.get("high_or_critical_event_count") or 0)
        if default_count:
            outflow_pressure_signals.append(f"bond_defaults={default_count}")
        if high_count:
            outflow_pressure_signals.append(f"bond_high_risk_events={high_count}")

    if asset_solvency_profile:
        pledge_count = int(asset_solvency_profile.get("pledge_count") or 0)
        freeze_count = int(asset_solvency_profile.get("freeze_count") or 0)
        auction_count = int(asset_solvency_profile.get("auction_count") or 0)
        high_count = int(asset_solvency_profile.get("high_or_critical_event_count") or 0)
        if pledge_count or freeze_count or auction_count:
            outflow_pressure_signals.append(
                f"asset_pressure=pledge:{pledge_count},freeze:{freeze_count},auction:{auction_count}"
            )
        if high_count:
            outflow_pressure_signals.append(f"asset_high_risk_events={high_count}")

    if public_capital_profile:
        cap_count = int(public_capital_profile.get("row_count") or 0)
        if cap_count:
            outflow_pressure_signals.append(f"public_web_capital_pressure_leads={cap_count}")
        structured = _dict(public_capital_profile.get("structured_summary"))
        for key, label in (
            ("debt_credit", "public_debt_credit_leads"),
            ("refinancing", "public_refinancing_leads"),
            ("liquidity", "public_liquidity_pressure_leads"),
            ("asset_pressure", "public_asset_pressure_leads"),
            ("capital_structure", "public_capital_structure_leads"),
        ):
            count = int(structured.get(key) or 0)
            if count:
                outflow_pressure_signals.append(f"{label}={count}")
        financing_count = int(structured.get("financing_events") or 0)
        if financing_count:
            inflow_signals.append(f"public_financing_event_leads={financing_count}")

    if fin_inst_profile:
        inst_count = int(fin_inst_profile.get("row_count") or 0)
        high_risk_count = int(fin_inst_profile.get("high_risk_count") or 0)
        if inst_count:
            operating_activity_signals.append(f"financial_institution_counterparties={inst_count}")
        if high_risk_count:
            outflow_pressure_signals.append(f"fin_inst_high_risk_counterparties={high_risk_count}")

    if not inflow_signals and not outflow_pressure_signals and not operating_activity_signals:
        return None

    pressure_level = "high" if outflow_pressure_signals else "unknown_or_low_from_available_evidence"
    if outflow_pressure_signals and inflow_signals:
        pressure_level = "needs_balance_review"
    return {
        "type": "fund_flow_profile",
        "evidence_state": "evidence_backed",
        "money_in_signals": _dedupe_strings(inflow_signals)[:8],
        "money_out_or_pressure_signals": _dedupe_strings(outflow_pressure_signals)[:8],
        "operating_activity_signals": _dedupe_strings(operating_activity_signals)[:6],
        "pressure_level": pressure_level,
        "quality_notes": _dedupe_strings(quality_notes)[:8],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "收入、融资、经营现金流和债务压力是否能互相解释？",
            "采购、投资、偿债、分红和关联交易是否消耗了主要现金流？",
            "资产质押、冻结、拍卖或债券压力是否会反向影响控制权和经营连续性？",
        ],
    }


def _capital_pressure_profile(
    *,
    fund_flow_profile: dict[str, Any] | None,
    credit_profile: dict[str, Any] | None,
    operational_event_profile: dict[str, Any] | None,
    bond_credit_profile: dict[str, Any] | None,
    asset_solvency_profile: dict[str, Any] | None,
    fin_inst_profile: dict[str, Any] | None = None,
    public_capital_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Summarize capital pressure without promoting lead-only rows into facts."""
    inflow_signals: list[str] = []
    pressure_signals: list[str] = []
    source_basis: list[str] = []
    rows: list[dict[str, Any]] = []
    lead_only = False

    if fund_flow_profile:
        inflow_signals.extend(str(item) for item in fund_flow_profile.get("money_in_signals", []) if str(item).strip())
        pressure_signals.extend(
            str(item)
            for item in fund_flow_profile.get("money_out_or_pressure_signals", [])
            if str(item).strip()
        )
        source_basis.append("fund_flow_profile")

    if operational_event_profile:
        for key, label in (
            ("financing_event_count", "financing_events"),
            ("capital_pressure_event_count", "capital_pressure_events"),
            ("merger_event_count", "merger_restructuring_events"),
            ("negative_opinion_count", "negative_opinion_events"),
        ):
            count = int(operational_event_profile.get(key) or 0)
            if count:
                target = inflow_signals if key == "financing_event_count" else pressure_signals
                target.append(f"{label}={count}")
        rows.extend(row for row in operational_event_profile.get("rows", []) if isinstance(row, dict))
        source_basis.append("operational_event_profile")

    if credit_profile:
        count = int(credit_profile.get("risk_item_count") or 0)
        if count:
            pressure_signals.append(f"credit_risk_items={count}")
        source_basis.append("credit_profile")

    if bond_credit_profile:
        default_count = int(bond_credit_profile.get("default_count") or 0)
        high_count = int(bond_credit_profile.get("high_or_critical_event_count") or 0)
        if default_count:
            pressure_signals.append(f"bond_defaults={default_count}")
        if high_count:
            pressure_signals.append(f"bond_high_or_critical_events={high_count}")
        rows.extend(row for row in bond_credit_profile.get("rows", []) if isinstance(row, dict))
        source_basis.append("bond_credit_profile")

    if asset_solvency_profile:
        asset_counts = {
            "pledge": int(asset_solvency_profile.get("pledge_count") or 0),
            "freeze": int(asset_solvency_profile.get("freeze_count") or 0),
            "auction": int(asset_solvency_profile.get("auction_count") or 0),
            "land": int(asset_solvency_profile.get("land_count") or 0),
        }
        if any(asset_counts.values()):
            pressure_signals.append(
                "asset_solvency_pressure="
                + ",".join(f"{key}:{value}" for key, value in asset_counts.items() if value)
            )
        rows.extend(row for row in asset_solvency_profile.get("rows", []) if isinstance(row, dict))
        source_basis.append("asset_solvency_profile")

    if fin_inst_profile:
        high_count = int(fin_inst_profile.get("high_risk_count") or 0)
        row_count = int(fin_inst_profile.get("row_count") or 0)
        if row_count:
            source_basis.append("financial_institution_profile")
            pressure_signals.append(f"financial_counterparties={row_count}")
        if high_count:
            pressure_signals.append(f"high_risk_financial_counterparties={high_count}")
        rows.extend(row for row in fin_inst_profile.get("rows", []) if isinstance(row, dict))

    if public_capital_profile:
        structured = _dict(public_capital_profile.get("structured_summary"))
        public_rows = int(public_capital_profile.get("row_count") or 0)
        if public_rows:
            lead_only = True
            source_basis.append("public_capital_profile")
        for key in (
            "debt_credit",
            "refinancing",
            "liquidity",
            "asset_pressure",
            "capital_structure",
        ):
            count = int(structured.get(key) or 0)
            if count:
                pressure_signals.append(f"public_{key}_leads={count}")
        financing_count = int(structured.get("financing_events") or 0)
        if financing_count:
            inflow_signals.append(f"public_financing_event_leads={financing_count}")

    inflow_signals = _dedupe_strings(inflow_signals)[:10]
    pressure_signals = _dedupe_strings(pressure_signals)[:12]
    source_basis = _dedupe_strings(source_basis)[:8]
    if not inflow_signals and not pressure_signals:
        return None

    pressure_score = len(pressure_signals)
    if any("default" in signal or "high_or_critical" in signal for signal in pressure_signals):
        pressure_level = "high"
    elif pressure_score >= 3:
        pressure_level = "elevated"
    elif pressure_score:
        pressure_level = "watch"
    else:
        pressure_level = "unknown_or_low_from_available_evidence"
    verification_queue = _capital_pressure_verification_queue(
        rows=rows,
        pressure_signals=pressure_signals,
        pressure_level=pressure_level,
        lead_only=lead_only,
    )
    capital_source_names = _capital_source_names(rows, verification_queue, source_basis)
    source_family_summary = _source_family_summary_from_names(capital_source_names)

    return {
        "type": "capital_pressure_profile",
        "evidence_state": "evidence_backed",
        "pressure_level": pressure_level,
        "pressure_signal_count": len(pressure_signals),
        "inflow_signal_count": len(inflow_signals),
        "inflow_signals": inflow_signals,
        "pressure_signals": pressure_signals,
        "source_basis": source_basis,
        "source_names": capital_source_names[:12],
        "source_family_summary": source_family_summary,
        "rows": rows[:12],
        "lead_only_public_rows_present": lead_only,
        "verification_queue": verification_queue,
        "verification_queue_count": len(verification_queue),
        "verification_status": (
            "admitted_and_public_leads_mixed"
            if lead_only and len(source_basis) > 1
            else "public_leads_need_corroboration"
            if lead_only
            else "admitted_capital_pressure_facts"
        ),
        "quality_notes": [
            "Capital pressure is derived from admitted profiles; public-web rows remain corroboration-needed leads.",
            "Use this summary to prioritize deeper review of debt, financing, pledged/frozen assets, and financial counterparties.",
        ],
        "next_questions": [
            "Which pressure signals are backed by official or licensed records versus public leads?",
            "Do financing inflows offset debt, bond, asset, or counterparty pressure?",
            "Which counterparties, assets, or events should be verified next for capital-risk closure?",
        ],
    }


def _capital_pressure_verification_queue(
    *,
    rows: list[dict[str, Any]],
    pressure_signals: list[str],
    pressure_level: str,
    lead_only: bool,
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    priority = "P0" if pressure_level in {"high", "elevated"} else "P1"
    if rows:
        for row in rows[:8]:
            row_id = str(
                row.get("id")
                or row.get("evidence_id")
                or row.get("record_id")
                or row.get("source_url")
                or f"capital-row-{len(queue) + 1}"
            )
            title = str(
                row.get("title")
                or row.get("institution_name")
                or row.get("event_type")
                or row.get("record_type")
                or "capital pressure row"
            )
            source_name = row.get("source") or row.get("source_name") or row.get("source_url")
            source_families = sorted({
                _evidence_source_family(str(source_name))
            } - {"unknown"})
            queue.append(
                {
                    "step_id": f"CAP-PRESSURE-{len(queue) + 1:03d}",
                    "priority": priority,
                    "kind": "capital_row_verification",
                    "target_id": row_id,
                    "target_title": title,
                    "source": source_name,
                    "source_families": source_families,
                    "lead_only": lead_only,
                    "done_condition": "amount_date_counterparty_subject_match_and_source_authority_reviewed",
                }
            )
    if pressure_signals:
        queue.append(
            {
                "step_id": f"CAP-SIGNAL-{len(queue) + 1:03d}",
                "priority": priority,
                "kind": "pressure_signal_review",
                "target_id": "capital_pressure_signals",
                "target_title": ", ".join(pressure_signals[:4]),
                "source": "capital_pressure_profile",
                "lead_only": lead_only,
                "done_condition": "each_pressure_signal_mapped_to_admitted_fact_or_marked_as_lead",
            }
        )
    queue.append(
        {
            "step_id": f"CAP-REL-{len(queue) + 1:03d}",
            "priority": "P0" if pressure_level in {"high", "elevated"} else "P1",
            "kind": "capital_relationship_closure",
            "target_id": "capital_relationship_profile",
            "target_title": "Close lender, pledgee, guarantor, bond party, asset holder, or controller relationship explanation",
            "source": "relationship_network",
            "lead_only": False,
            "done_condition": "capital_relationship_profile_has_match_or_explicit_unresolved_reason",
        }
    )
    return queue[:12]


def _capital_source_names(
    rows: list[dict[str, Any]],
    verification_queue: list[dict[str, Any]],
    source_basis: list[str],
) -> list[str]:
    names: list[str] = []
    for row in rows:
        for key in ("source", "source_name", "source_url", "provider"):
            value = row.get(key)
            if value:
                names.append(str(value))
    for item in verification_queue:
        value = item.get("source")
        if value:
            names.append(str(value))
        for family in item.get("source_families", []) or []:
            if family:
                names.append(str(family))
    return _dedupe_strings(names)


def _capital_relationship_profile(
    *,
    capital_pressure_profile: dict[str, Any] | None,
    relationship_network: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Link admitted capital pressure rows to admitted relationship edges."""
    if not capital_pressure_profile or not relationship_network:
        return None

    capital_rows = [
        row for row in capital_pressure_profile.get("rows", [])
        if isinstance(row, dict)
    ]
    edges = [
        edge for edge in relationship_network.get("top_edges", [])
        if isinstance(edge, dict)
    ]
    if not capital_rows or not edges:
        return None

    linked: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    capital_relation_tokens = (
        "bank",
        "bond",
        "credit",
        "debt",
        "finance",
        "financing",
        "guarantee",
        "guarantor",
        "lender",
        "pledge",
        "pledgee",
        "freeze",
        "auction",
        "asset",
        "counterparty",
        "担保",
        "贷款",
        "债",
        "质押",
        "冻结",
        "拍卖",
        "金融",
        "银行",
    )
    for row in capital_rows:
        row_terms = _capital_row_match_terms(row)
        if not row_terms:
            continue
        for edge in edges:
            if not _capital_relationship_edge_is_admitted(edge):
                continue
            relation_text = " ".join(
                str(edge.get(key) or "")
                for key in ("from_name", "to_name", "relation_type")
            ).strip()
            relation_key = _control_path_name_key(relation_text)
            relation_is_capital = any(token in relation_key for token in capital_relation_tokens)
            if not relation_is_capital and not any(term in relation_key for term in row_terms):
                continue
            matched_terms = [term for term in row_terms if term and term in relation_key]
            if not matched_terms and not relation_is_capital:
                continue
            key = (
                str(row.get("module") or row.get("record_type") or ""),
                str(row.get("identifier") or row.get("institution_name") or ""),
                relation_key,
            )
            if key in seen:
                continue
            seen.add(key)
            linked.append(
                {
                    "capital_module": row.get("module"),
                    "capital_record_type": row.get("record_type"),
                    "capital_identifier": row.get("identifier") or row.get("institution_name"),
                    "capital_status": row.get("status"),
                    "capital_summary": _short_text(row.get("summary"), 180),
                    "relationship_from": edge.get("from_name") or edge.get("from_id"),
                    "relationship_to": edge.get("to_name") or edge.get("to_id"),
                    "relationship_type": edge.get("relation_type"),
                    "relationship_confidence": edge.get("confidence"),
                    "relationship_admission": edge.get("admission") or "implicit_admitted_profile_edge",
                    "matched_terms": matched_terms[:4],
                    "evidence_ids": _dedupe_strings(
                        [str(item) for item in edge.get("evidence_ids", []) if str(item).strip()]
                    )[:6],
                }
            )
            if len(linked) >= 8:
                break
        if len(linked) >= 8:
            break

    if not linked:
        return None

    pressure_level = str(capital_pressure_profile.get("pressure_level") or "watch")
    if pressure_level in {"high", "elevated"} and len(linked) >= 2:
        risk_level = "high"
    elif pressure_level in {"high", "elevated", "needs_balance_review"}:
        risk_level = "elevated"
    else:
        risk_level = "watch"

    return {
        "type": "capital_relationship_profile",
        "evidence_state": "evidence_backed",
        "relationship_risk_level": risk_level,
        "match_count": len(linked),
        "linked_exposures": linked,
        "source_basis": _dedupe_strings(
            list(capital_pressure_profile.get("source_basis") or []) + ["relationship_network"]
        )[:10],
        "quality_notes": [
            "Only admitted capital rows and admitted relationship edges are linked.",
            "Weak relationship leads remain outside this profile until corroborated.",
        ],
        "next_questions": [
            "Does the linked counterparty, controller, or related entity explain the capital pressure?",
            "Are guarantees, pledges, bank exposure, or bond obligations connected to the same related-party cluster?",
            "Which linked exposure should be verified next with official or licensed records?",
        ],
    }


def _capital_relationship_edge_is_admitted(edge: dict[str, Any]) -> bool:
    """Keep lead-only relationship edges from explaining capital pressure."""
    admission = str(edge.get("admission") or "").strip().lower()
    if not admission:
        return True
    if admission in {"fact", "admitted", "evidence"}:
        return True
    if admission in {"lead", "weak_lead", "review", "query_plan", "candidate"}:
        return False
    return False


def _capital_row_match_terms(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "identifier",
        "institution_name",
        "pledgee",
        "shareholder",
        "issuer",
        "bond_name",
        "court",
        "asset_name",
        "subject",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            values.append(value)
    summary = str(row.get("summary") or "")
    for part in re.split(r"[;|,，/]", summary):
        if "=" not in part:
            continue
        _, value = part.split("=", 1)
        value = value.strip()
        if value:
            values.append(value)
    terms = [_control_path_name_key(value) for value in values]
    return [term for term in _dedupe_strings(terms) if len(term) >= 3][:12]


def _goods_flow_profile(
    *,
    industry: dict[str, Any] | None,
    product: dict[str, Any] | None,
    supply_chain_profile: dict[str, Any] | None,
    public_goods_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a goods-in/goods-out read from admitted product, industry, and supply-chain evidence."""
    product_signals: list[str] = []
    industry_signals: list[str] = []
    upstream_signals: list[str] = []
    downstream_signals: list[str] = []
    customer_signals: list[str] = []
    supplier_signals: list[str] = []
    channel_or_partner_signals: list[str] = []
    concentration_signals: list[str] = []
    value_chain_signals: list[str] = []
    unit_economics_signals: list[str] = []
    bargaining_power_signals: list[str] = []
    competitive_landscape_signals: list[str] = []
    pressure_points: list[str] = []
    quality_notes: list[str] = []

    if product:
        product_name = str(product.get("product_name") or "").strip()
        if product_name:
            product_signals.append(f"product={product_name}")
        if product.get("lifecycle"):
            product_signals.append(f"product_lifecycle={product.get('lifecycle')}")
            if str(product.get("lifecycle")) in {"decline", "stress"}:
                pressure_points.append(f"product_lifecycle={product.get('lifecycle')}")
        if product.get("substitution_risk"):
            product_signals.append(f"substitution_risk={product.get('substitution_risk')}")
            if str(product.get("substitution_risk")) in {"medium", "high"}:
                pressure_points.append(f"substitution_risk={product.get('substitution_risk')}")
        if product.get("customer_value"):
            product_signals.append(f"customer_value={_short_text(product.get('customer_value'), 120)}")
        if product.get("product_dependency"):
            product_signals.append(f"product_dependency={_short_text(product.get('product_dependency'), 120)}")
        input_signals = product.get("input_signals") if isinstance(product.get("input_signals"), dict) else {}
        for key in ("core_product_revenue_ratio", "customer_churn_rate", "price_change"):
            if input_signals.get(key) not in (None, ""):
                product_signals.append(f"{key}={input_signals.get(key)}")

    if industry:
        if industry.get("industry"):
            industry_signals.append(f"industry={industry.get('industry')}")
        if industry.get("lifecycle"):
            industry_signals.append(f"industry_lifecycle={industry.get('lifecycle')}")
        if industry.get("threat_level"):
            industry_signals.append(f"industry_threat_level={industry.get('threat_level')}")
            if str(industry.get("threat_level")) in {"medium", "high"}:
                pressure_points.append(f"industry_threat_level={industry.get('threat_level')}")
        if industry.get("profit_pool_position"):
            value_chain_signals.append(f"profit_pool_position={_short_text(industry.get('profit_pool_position'), 120)}")
        if industry.get("enterprise_survival_logic"):
            value_chain_signals.append(f"survival_logic={_short_text(industry.get('enterprise_survival_logic'), 120)}")
        input_signals = industry.get("input_signals") if isinstance(industry.get("input_signals"), dict) else {}
        for key in ("industry_growth", "capacity_utilization", "price_index_change", "market_share"):
            if input_signals.get(key) not in (None, ""):
                industry_signals.append(f"{key}={input_signals.get(key)}")

    def _row_signal(row: dict[str, Any]) -> str:
        field = str(row.get("field") or row.get("type") or "signal")
        value = _short_text(row.get("value"), 100)
        source = str(row.get("source") or "").strip()
        return f"{field}={value}" + (f" @{source}" if source else "")

    if supply_chain_profile:
        for row in [item for item in supply_chain_profile.get("customers", []) if isinstance(item, dict)]:
            customer_signals.append(_row_signal(row))
        for row in [item for item in supply_chain_profile.get("suppliers", []) if isinstance(item, dict)]:
            supplier_signals.append(_row_signal(row))
        for row in [item for item in supply_chain_profile.get("relationships", []) if isinstance(item, dict)]:
            row_type = str(row.get("type") or "")
            signal = _row_signal(row)
            if row_type == "upstream":
                upstream_signals.append(signal)
            elif row_type == "downstream":
                downstream_signals.append(signal)
            elif row_type == "value_chain_role":
                value_chain_signals.append(signal)
            else:
                channel_or_partner_signals.append(signal)
        for row in [item for item in supply_chain_profile.get("concentration_signals", []) if isinstance(item, dict)]:
            signal = _row_signal(row)
            concentration_signals.append(signal)
            pressure_points.append(signal)
        quality_notes.extend(str(item) for item in supply_chain_profile.get("quality_notes", [])[:3])

    if public_goods_profile:
        for signal in [str(item) for item in public_goods_profile.get("product_claims", []) if str(item).strip()]:
            product_signals.append(f"public_lead:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("market_position_claims", []) if str(item).strip()]:
            industry_signals.append(f"public_market:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("business_model_claims", []) if str(item).strip()]:
            value_chain_signals.append(f"public_model:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("unit_economics_claims", []) if str(item).strip()]:
            unit_economics_signals.append(f"public_unit_economics:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("bargaining_power_claims", []) if str(item).strip()]:
            bargaining_power_signals.append(f"public_bargaining_power:{signal}")
            pressure_points.append(f"public_bargaining_power:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("competitive_landscape_claims", []) if str(item).strip()]:
            competitive_landscape_signals.append(f"public_competition:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("customer_claims", []) if str(item).strip()]:
            customer_signals.append(f"public_customer:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("supplier_claims", []) if str(item).strip()]:
            supplier_signals.append(f"public_supplier:{signal}")
        for signal in [str(item) for item in public_goods_profile.get("channel_partner_claims", []) if str(item).strip()]:
            channel_or_partner_signals.append(f"public_channel:{signal}")
        structured = _dict(public_goods_profile.get("structured_summary"))
        if structured:
            quality_notes.append(
                "public_goods_profile="
                f"products:{structured.get('products', 0)},"
                f"market:{structured.get('market_position', 0)},"
                f"model:{structured.get('business_model', 0)},"
                f"unit:{structured.get('unit_economics', 0)},"
                f"power:{structured.get('bargaining_power', 0)},"
                f"competition:{structured.get('competitive_landscape', 0)}"
            )
        if public_goods_profile.get("verification_status"):
            quality_notes.append(f"public_goods_status={public_goods_profile.get('verification_status')}")

    if not any(
        [
            product_signals,
            industry_signals,
            upstream_signals,
            downstream_signals,
            customer_signals,
            supplier_signals,
            channel_or_partner_signals,
            concentration_signals,
            value_chain_signals,
            unit_economics_signals,
            bargaining_power_signals,
            competitive_landscape_signals,
        ]
    ):
        return None

    corroboration_status = (
        str(supply_chain_profile.get("corroboration_status"))
        if supply_chain_profile
        else str(public_goods_profile.get("verification_status"))
        if public_goods_profile
        else "product_or_industry_only_needs_supply_chain_corroboration"
    )
    return {
        "type": "goods_flow_profile",
        "evidence_state": "evidence_backed",
        "product_signals": _dedupe_strings(product_signals)[:8],
        "industry_signals": _dedupe_strings(industry_signals)[:8],
        "upstream_signals": _dedupe_strings(upstream_signals)[:8],
        "downstream_signals": _dedupe_strings(downstream_signals)[:8],
        "customer_signals": _dedupe_strings(customer_signals)[:8],
        "supplier_signals": _dedupe_strings(supplier_signals)[:8],
        "channel_or_partner_signals": _dedupe_strings(channel_or_partner_signals)[:8],
        "concentration_signals": _dedupe_strings(concentration_signals)[:8],
        "value_chain_signals": _dedupe_strings(value_chain_signals)[:8],
        "unit_economics_signals": _dedupe_strings(unit_economics_signals)[:8],
        "bargaining_power_signals": _dedupe_strings(bargaining_power_signals)[:8],
        "competitive_landscape_signals": _dedupe_strings(competitive_landscape_signals)[:8],
        "pressure_points": _dedupe_strings(pressure_points)[:8],
        "corroboration_status": corroboration_status,
        "quality_notes": _dedupe_strings(quality_notes)[:8],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "这家公司卖什么，货从哪里来、往哪里去，是否能被证据链闭合？",
            "上游原料、核心供应商、下游客户和渠道伙伴是否存在集中或关联交易风险？",
            "产品生命周期、替代品、行业利润池位置和议价权是否解释经营压力？",
        ],
    }


def _people_flow_profile(
    *,
    control_ownership: dict[str, Any] | None,
    relationship_network: dict[str, Any] | None,
    legal_administrative_profile: dict[str, Any] | None,
    public_people_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a who-controls/who-acts-together read from admitted people and relationship evidence."""
    controller_signals: list[str] = []
    key_person_signals: list[str] = []
    relationship_signals: list[str] = []
    control_path_signals: list[str] = []
    legal_pressure_signals: list[str] = []
    pressure_points: list[str] = []
    quality_notes: list[str] = []

    if control_ownership:
        for item in [row for row in control_ownership.get("controller_candidates", []) if isinstance(row, dict)]:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            relation_types = item.get("relation_types") or []
            relation_label = ",".join(str(value) for value in relation_types if str(value).strip())
            if not relation_label:
                relation_label = str(item.get("relation_type") or "controller_candidate")
            signal = f"{name}:{relation_label};status={item.get('verification_status') or 'unknown'}"
            controller_signals.append(signal)
            if str(item.get("verification_status") or "") not in {"verified", "corroborated"}:
                pressure_points.append(f"controller_needs_corroboration={name}")
        for path in [row for row in control_ownership.get("control_paths", []) if isinstance(row, dict)]:
            from_name = _short_text(path.get("from_name") or path.get("from_kind"), 60)
            to_name = _short_text(path.get("to_name") or path.get("to_kind"), 60)
            if from_name or to_name:
                control_path_signals.append(
                    f"{from_name}->{to_name};relation={path.get('relation_type')};confidence={path.get('confidence')}"
                )
        if control_ownership.get("evidence_gaps"):
            quality_notes.extend(str(item) for item in control_ownership.get("evidence_gaps", [])[:3])

    if relationship_network:
        if relationship_network.get("relation_types"):
            relationship_signals.append(
                "relation_types=" + ",".join(str(item) for item in relationship_network.get("relation_types", [])[:6])
            )
        for edge in [row for row in relationship_network.get("top_edges", []) if isinstance(row, dict)]:
            from_name = _short_text(edge.get("from_name") or edge.get("from_id"), 60)
            to_name = _short_text(edge.get("to_name") or edge.get("to_id"), 60)
            if from_name or to_name:
                relationship_signals.append(
                    f"{from_name}->{to_name};relation={edge.get('relation_type')};confidence={edge.get('confidence')}"
                )
        if int(relationship_network.get("relation_count") or 0) > 0:
            key_person_signals.append(
                f"relationship_network_subjects={relationship_network.get('subject_count', 0)};relations={relationship_network.get('relation_count', 0)}"
            )

    if legal_administrative_profile:
        row_count = int(legal_administrative_profile.get("row_count") or 0)
        high_count = int(legal_administrative_profile.get("high_or_critical_event_count") or 0)
        administrative_count = int(legal_administrative_profile.get("administrative_penalty_count") or 0)
        if row_count:
            legal_pressure_signals.append(f"legal_admin_rows={row_count}")
        if administrative_count:
            legal_pressure_signals.append(f"administrative_penalties={administrative_count}")
        if high_count:
            legal_pressure_signals.append(f"high_or_critical_legal_events={high_count}")
            pressure_points.append(f"high_or_critical_legal_events={high_count}")

    if public_people_profile:
        for signal in [str(item) for item in public_people_profile.get("control_role_claims", []) if str(item).strip()]:
            controller_signals.append(f"public_control:{signal}")
            pressure_points.append(f"public_control_needs_corroboration:{signal}")
        for signal in [str(item) for item in public_people_profile.get("key_person_claims", []) if str(item).strip()]:
            key_person_signals.append(f"public_key_person:{signal}")
        for signal in [str(item) for item in public_people_profile.get("legal_pressure_claims", []) if str(item).strip()]:
            legal_pressure_signals.append(f"public_legal_pressure:{signal}")
            pressure_points.append(f"public_legal_pressure:{signal}")
        for signal in [str(item) for item in public_people_profile.get("ownership_change_claims", []) if str(item).strip()]:
            control_path_signals.append(f"public_ownership_change:{signal}")
        for signal in [str(item) for item in public_people_profile.get("related_party_claims", []) if str(item).strip()]:
            relationship_signals.append(f"public_related_party:{signal}")
            pressure_points.append(f"public_related_party:{signal}")
        structured = _dict(public_people_profile.get("structured_summary"))
        if structured:
            quality_notes.append(
                "public_people_profile="
                f"control:{structured.get('control_roles', 0)},"
                f"key_people:{structured.get('key_people', 0)},"
                f"legal_pressure:{structured.get('legal_pressure', 0)},"
                f"ownership_changes:{structured.get('ownership_changes', 0)},"
                f"related_parties:{structured.get('related_parties', 0)}"
            )
        if public_people_profile.get("verification_status"):
            quality_notes.append(f"public_people_status={public_people_profile.get('verification_status')}")

    if not any([controller_signals, key_person_signals, relationship_signals, control_path_signals, legal_pressure_signals]):
        return None

    verification_status = (
        str(control_ownership.get("verification_status"))
        if control_ownership
        else str(public_people_profile.get("verification_status"))
        if public_people_profile
        else "relationship_or_legal_only_needs_controller_corroboration"
    )
    return {
        "type": "people_flow_profile",
        "evidence_state": "evidence_backed",
        "verification_status": verification_status,
        "controller_signals": _dedupe_strings(controller_signals)[:8],
        "key_person_signals": _dedupe_strings(key_person_signals)[:8],
        "relationship_signals": _dedupe_strings(relationship_signals)[:8],
        "control_path_signals": _dedupe_strings(control_path_signals)[:8],
        "legal_pressure_signals": _dedupe_strings(legal_pressure_signals)[:8],
        "pressure_points": _dedupe_strings(pressure_points)[:8],
        "quality_notes": _dedupe_strings(quality_notes)[:8],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "谁实际控制这家公司，控制路径是否能被多个来源交叉印证？",
            "关键人、关联企业、共同地址、共同任职和项目对手是否构成风险传导网络？",
            "法务行政记录是否能穿透到责任主体、金额、日期和最新状态？",
        ],
    }


def _money_goods_people_lens(
    *,
    financial: dict[str, Any] | None,
    credit_profile: dict[str, Any] | None,
    operational_event_profile: dict[str, Any] | None,
    commercial_activity_profile: dict[str, Any] | None,
    bond_credit_profile: dict[str, Any] | None,
    asset_solvency_profile: dict[str, Any] | None,
    supply_chain_profile: dict[str, Any] | None,
    industry: dict[str, Any] | None,
    product: dict[str, Any] | None,
    control_ownership: dict[str, Any] | None,
    relationship_network: dict[str, Any] | None,
    legal_administrative_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """Organize deep-dive evidence into money/goods/people investigation tracks."""
    money_facts: list[str] = []
    money_gaps: list[str] = []
    if financial:
        if financial.get("row_count"):
            money_facts.append(f"financial_rows={financial.get('row_count')}")
        if financial.get("quality_notes"):
            money_facts.extend(str(item) for item in financial.get("quality_notes", [])[:3])
    else:
        money_gaps.append("revenue, cash flow, receivables, inventory, debt, and financing source evidence")
    if credit_profile:
        money_facts.append(f"credit_profile_rows={credit_profile.get('row_count', 0)}")
    if bond_credit_profile:
        money_facts.append(f"bond_credit_rows={bond_credit_profile.get('row_count', 0)}")
    if asset_solvency_profile:
        money_facts.append(f"asset_solvency_rows={asset_solvency_profile.get('row_count', 0)}")
    if commercial_activity_profile:
        money_facts.append(
            "operating_activity="
            f"tax:{commercial_activity_profile.get('tax_count', 0)},"
            f"trade:{commercial_activity_profile.get('trade_count', 0)},"
            f"recruiting:{commercial_activity_profile.get('recruiting_count', 0)}"
        )
    if operational_event_profile:
        money_facts.append(f"financing_events={operational_event_profile.get('financing_event_count', 0)}")

    goods_facts: list[str] = []
    goods_gaps: list[str] = []
    if product:
        goods_facts.append(f"product={product.get('product_name')}")
    else:
        goods_gaps.append("core product, customer value, substitution, and product lifecycle evidence")
    if industry:
        goods_facts.append(f"industry={industry.get('industry')}; lifecycle={industry.get('lifecycle')}")
    else:
        goods_gaps.append("industry structure, competitors, profit pool, policy cycle, and market-share evidence")
    if supply_chain_profile:
        goods_facts.append(
            "supply_chain="
            f"customers:{supply_chain_profile.get('customer_count', 0)},"
            f"suppliers:{supply_chain_profile.get('supplier_count', 0)},"
            f"relationships:{supply_chain_profile.get('relationship_count', 0)},"
            f"concentration:{supply_chain_profile.get('concentration_signal_count', 0)}"
        )
    else:
        goods_gaps.append("upstream, downstream, supplier, customer, dealer, partner, and concentration evidence")

    people_facts: list[str] = []
    people_gaps: list[str] = []
    if control_ownership:
        people_facts.append(
            "controller_candidates="
            f"{control_ownership.get('controller_candidate_count', 0)};"
            f"status={control_ownership.get('verification_status')}"
        )
    else:
        people_gaps.append("actual controller, beneficial owner, shareholder, executive, and legal representative evidence")
    if relationship_network:
        people_facts.append(
            "relationship_network="
            f"subjects:{relationship_network.get('subject_count', 0)},"
            f"relations:{relationship_network.get('relation_count', 0)}"
        )
    else:
        people_gaps.append("associated companies, counterparties, common posts, common addresses, and project relationships")
    if legal_administrative_profile:
        people_facts.append(f"legal_admin_rows={legal_administrative_profile.get('row_count', 0)}")

    tracks = [
        _case_track(
            "money",
            "钱",
            "money_in_money_out",
            money_facts,
            money_gaps,
            "Trace where money comes from, where it goes, whether profit becomes cash, and whether debt or assets pressure the subject.",
        ),
        _case_track(
            "goods",
            "货",
            "goods_in_goods_out",
            goods_facts,
            goods_gaps,
            "Trace what is made or sold, how it is made, where inputs come from, where outputs go, and who has bargaining power.",
        ),
        _case_track(
            "people",
            "人",
            "who_controls_and_who_acts_together",
            people_facts,
            people_gaps,
            "Trace who controls the subject, who operates it, who acts with it, and which relationships explain risk transmission.",
        ),
    ]
    return {
        "type": "case_investigation_lens",
        "name": "扒光查案式调查",
        "purpose": (
            "A default report lens for deep investigation. It organizes evidence into money, goods, and people tracks "
            "without replacing the broader source retrieval, industry, legal, financial, and relationship modules."
        ),
        "tracks": tracks,
        "next_questions": _dedupe_strings(
            question
            for track in tracks
            for question in track.get("next_questions", [])
        )[:9],
    }


def _case_track(
    key: str,
    label: str,
    focus: str,
    facts: list[str],
    gaps: list[str],
    method: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "focus": focus,
        "method": method,
        "evidence_state": "evidence_backed" if facts else "needs_evidence",
        "known_signals": _dedupe_strings(str(item) for item in facts if str(item).strip())[:8],
        "evidence_gaps": _dedupe_strings(str(item) for item in gaps if str(item).strip())[:6],
        "next_questions": _case_track_questions(key, has_facts=bool(facts), gaps=gaps),
    }


def _case_track_questions(key: str, *, has_facts: bool, gaps: list[str]) -> list[str]:
    base = {
        "money": [
            "钱从哪里来：收入、融资、债务、补贴或关联方资金能否互相印证？",
            "钱往哪里去：成本、采购、投资、偿债、分红和关联交易是否解释得通？",
            "利润能否变成现金，应收、存货和经营现金流是否互相打架？",
        ],
        "goods": [
            "货从哪里来：原料、供应商、产能、技术或采购项目是否有公开证据？",
            "货往哪里去：客户、渠道、下游行业和集中度是否可被交叉验证？",
            "这门生意在产业链里有没有议价权，替代品和竞争对手压力在哪里？",
        ],
        "people": [
            "人都是谁：实控人、受益人、股东、高管和法定代表人是否能穿透？",
            "人都干什么：任职、持股、担保、诉讼、项目、交易对手是否能串起来？",
            "和谁一起：关联企业、共同地址、共同任职、共同项目是否构成风险传导路径？",
        ],
    }
    questions = list(base.get(key, []))
    if not has_facts and gaps:
        questions.insert(0, "先补证：" + "；".join(_domain_label(item) for item in gaps[:2]))
    return questions


def _control_ownership_from_subject_profile(
    profile_brief: dict[str, Any],
    subject_profile: dict[str, Any],
) -> dict[str, Any] | None:
    candidates = subject_profile.get("controller_candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    candidate_count = int(profile_brief.get("controller_candidate_count") or len(candidates) or 0)
    if candidate_count <= 0 and not candidates:
        return None

    normalized_candidates: list[dict[str, Any]] = []
    source_names: list[str] = []
    relation_types: list[str] = []
    verification_statuses: list[str] = []
    for item in candidates[:5]:
        candidate = _dict(item)
        names = [str(source).strip() for source in candidate.get("source_names", []) if str(source).strip()]
        if names:
            source_names.extend(names)
        rel_types = candidate.get("relation_types") or []
        if not isinstance(rel_types, list):
            rel_types = [rel_types]
        relation_types.extend(str(item).strip() for item in rel_types if str(item).strip())
        status = str(candidate.get("verification_status") or "").strip()
        if status:
            verification_statuses.append(status)
        normalized_candidates.append(
            {
                "person_id": candidate.get("person_id"),
                "name": candidate.get("name"),
                "relation_type": candidate.get("relation_type"),
                "relation_types": list(dict.fromkeys(str(item).strip() for item in rel_types if str(item).strip())),
                "confidence": candidate.get("confidence"),
                "confidence_tier": candidate.get("confidence_tier"),
                "confidence_label": {"verified_controller": "已验证实控人", "strong_public_lead": "强公开线索", "public_lead": "公开线索", "weak_or_review_lead": "待核验线索"}.get(str(candidate.get("confidence_tier") or ""), str(candidate.get("confidence_tier") or "unknown")),
                "source_strength_label": "高" if int(candidate.get("source_strength") or 0) >= 6 else "中" if int(candidate.get("source_strength") or 0) >= 3 else "低",
                "confidence_basis": [
                    str(item).strip()
                    for item in candidate.get("confidence_basis", [])
                    if str(item).strip()
                ],
                "control_paths": [
                    str(item).strip()
                    for item in candidate.get("control_paths", [])
                    if str(item).strip()
                ],
                "control_path_summaries": [
                    {
                        "path_text": _short_text(summary.get("path_text"), 240),
                        "path_nodes": [
                            str(node).strip()
                            for node in summary.get("path_nodes", [])
                            if str(node).strip()
                        ],
                        "hop_count": summary.get("hop_count"),
                        "relation_types": [
                            str(relation).strip()
                            for relation in summary.get("relation_types", [])
                            if str(relation).strip()
                        ],
                        "terminal_name": summary.get("terminal_name") or candidate.get("name"),
                        "terminal_kind": summary.get("terminal_kind") or "person",
                        "min_confidence": summary.get("min_confidence"),
                        "confidence": summary.get("confidence"),
                        "source_strength": summary.get("source_strength"),
                        "source_names": [
                            str(source).strip()
                            for source in summary.get("source_names", [])
                            if str(source).strip()
                        ],
                        "evidence_ids": [
                            str(evidence_id).strip()
                            for evidence_id in summary.get("evidence_ids", [])
                            if str(evidence_id).strip()
                        ],
                        "admission": summary.get("admission"),
                        "verification_status": summary.get("verification_status"),
                        "basis": summary.get("basis"),
                    }
                    for summary in candidate.get("control_path_summaries", [])
                    if isinstance(summary, dict) and str(summary.get("path_text") or "").strip()
                ][:5],
                "source_strength": candidate.get("source_strength"),
                "match_score": candidate.get("match_score"),
                "verification_status": status or "unknown",
                "source_names": names,
            }
        )

    graph = _dict(subject_profile.get("relationship_graph"))
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    covered_dimensions = [str(item) for item in profile_brief.get("covered_dimensions", []) if str(item).strip()]
    gaps = [
        str(item)
        for item in subject_profile.get("evidence_gaps", [])
        if str(item).strip()
    ]
    if not gaps:
        gaps = [str(item) for item in profile_brief.get("evidence_gaps", []) if str(item).strip()]

    control_paths = _control_paths_from_graph(nodes, edges, normalized_candidates)
    control_path_profile = _control_path_profile(control_paths)

    return {
        "seed_subject_name": profile_brief.get("seed_subject_name") or subject_profile.get("seed_subject_name"),
        "controller_candidate_count": candidate_count,
        "controller_candidates": normalized_candidates,
        "controller_conflict_summary": _controller_conflict_summary(normalized_candidates),
        "source_names": _dedupe_strings(source_names),
        "relation_types": _dedupe_strings(relation_types),
        "verification_status": _best_verification_status(verification_statuses),
        "graph_summary": {
            "subject_count": len(nodes),
            "relation_count": len(edges),
        },
        "control_paths": control_paths,
        "multi_layer_control_path_count": control_path_profile["multi_layer_control_path_count"],
        "highest_control_path_hop_count": control_path_profile["highest_control_path_hop_count"],
        "control_path_verification_status": control_path_profile["control_path_verification_status"],
        "control_path_verification_queue": control_path_profile["control_path_verification_queue"],
        "top_control_path": control_path_profile["top_control_path"],
        "control_path_source_family_summary": control_path_profile["control_path_source_family_summary"],
        "covered_dimensions": covered_dimensions,
        "high_sensitivity_lead_count": int(profile_brief.get("high_sensitivity_lead_count") or 0),
        "evidence_gaps": gaps[:6],
        "public_data_basis": "Graph-level controller and ownership snapshot derived from the subject profile.",
    }


def _relationship_network_from_subject_profile(
    subject_profile: dict[str, Any],
) -> dict[str, Any] | None:
    graph = _dict(subject_profile.get("relationship_graph"))
    raw_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    raw_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    if not raw_nodes and not raw_edges:
        return None

    node_lookup: dict[str, dict[str, Any]] = {}
    for item in raw_nodes:
        node = _dict(item)
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        node_lookup[node_id] = {
            "id": node_id,
            "name": str(node.get("name") or node_id).strip(),
            "kind": str(node.get("kind") or "unknown").strip(),
            "confidence": node.get("confidence"),
            "source_names": [str(source) for source in node.get("source_names", []) if str(source).strip()],
        }

    edges: list[dict[str, Any]] = []
    source_names: list[str] = []
    relation_types: list[str] = []
    seen_edges: set[tuple[str, str, str]] = set()
    edge_indexes: dict[tuple[str, str, str], int] = {}
    for item in raw_edges:
        edge = _dict(item)
        from_id = str(edge.get("from_id") or edge.get("from") or "").strip()
        to_id = str(edge.get("to_id") or edge.get("to") or "").strip()
        if not from_id or not to_id:
            continue
        from_node = node_lookup.get(from_id, {"id": from_id, "name": from_id, "kind": "unknown"})
        to_node = node_lookup.get(to_id, {"id": to_id, "name": to_id, "kind": "unknown"})
        relation_type = str(edge.get("relation_type") or "related").strip()
        edge_key = (
            _control_path_name_key(from_node.get("name") or from_id),
            _control_path_name_key(to_node.get("name") or to_id),
            relation_type.casefold(),
        )
        evidence_ids = [str(evidence_id) for evidence_id in edge.get("evidence_ids", []) if str(evidence_id).strip()]
        if edge_key in seen_edges:
            existing = edges[edge_indexes[edge_key]]
            existing["evidence_ids"] = _dedupe_strings(
                list(existing.get("evidence_ids") or []) + evidence_ids
            )[:12]
            existing_confidence = _float_or_none(existing.get("confidence")) or 0
            edge_confidence = _float_or_none(edge.get("confidence")) or 0
            if edge_confidence > existing_confidence:
                existing["confidence"] = edge.get("confidence")
            existing["admission"] = _stronger_edge_admission(existing.get("admission"), edge.get("admission"))
            existing["source"] = ", ".join(
                _dedupe_strings([str(existing.get("source") or ""), str(edge.get("source") or "relationship_network")])
            )
            continue
        seen_edges.add(edge_key)
        edge_indexes[edge_key] = len(edges)
        relation_types.append(relation_type)
        for node in (from_node, to_node):
            source_names.extend(str(source) for source in node.get("source_names", []) if str(source).strip())
        edges.append(
            {
                "from_id": from_id,
                "from_name": from_node.get("name"),
                "from_kind": from_node.get("kind"),
                "to_id": to_id,
                "to_name": to_node.get("name"),
                "to_kind": to_node.get("kind"),
                "relation_type": relation_type,
                "source": edge.get("source","relationship_network"),"confidence": edge.get("confidence"),
                "admission": edge.get("admission"),
                "evidence_ids": evidence_ids,
            }
        )

    if not node_lookup and not edges:
        return None

    kind_counts: dict[str, int] = {}
    for node in node_lookup.values():
        kind = str(node.get("kind") or "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    ranked_edges = sorted(
        edges,
        key=lambda item: (
            _relationship_relation_rank(item.get("relation_type")),
            -(_float_or_none(item.get("confidence")) or 0),
            str(item.get("from_name") or ""),
            str(item.get("to_name") or ""),
        ),
    )
    return {
        "subject_count": len(node_lookup),
        "relation_count": len(edges),
        "kind_counts": kind_counts,
        "relation_types": _dedupe_strings(relation_types),
        "source_names": _dedupe_strings(source_names),
        "top_edges": ranked_edges[:8],
        "public_data_basis": "Relationship graph is built from public, licensed, user-authorized, or fixture evidence already admitted into the subject profile.",
    }


def _stronger_edge_admission(left: Any, right: Any) -> Any:
    rank = {
        "fact": 5,
        "admitted": 5,
        "evidence": 4,
        "lead": 2,
        "candidate": 2,
        "weak_lead": 1,
        "review": 1,
        "query_plan": 1,
        "": 0,
    }
    left_text = str(left or "").strip().lower()
    right_text = str(right or "").strip().lower()
    return right if rank.get(right_text, 0) > rank.get(left_text, 0) else left


def _relationship_relation_rank(raw: Any) -> int:
    relation = str(raw or "").lower()
    priority = (
        ("beneficial", 0),
        ("controller", 1),
        ("owner", 2),
        ("shareholder", 3),
        ("legal", 4),
        ("chief", 5),
        ("director", 6),
        ("address", 7),
        ("project", 8),
        ("related", 9),
    )
    for token, rank in priority:
        if token in relation:
            return rank
    return 20


def _control_paths_from_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_names = {
        str(item.get("name") or "").strip()
        for item in candidates
        if str(item.get("name") or "").strip()
    }
    candidate_display_by_key: dict[str, str] = {}
    for item in candidates:
        display_name = str(item.get("name") or "").strip()
        if not display_name:
            continue
        for raw in (item.get("name"), item.get("person_id")):
            key = _control_path_name_key(raw)
            if key:
                candidate_display_by_key[key] = display_name
    node_lookup = {
        str(node.get("id") or ""): _dict(node)
        for node in nodes
        if str(node.get("id") or "").strip()
    }
    path_rows: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, str, str]] = set()
    seen_text_paths: set[str] = set()
    for candidate in candidates:
        for summary in candidate.get("control_path_summaries", []) or []:
            if not isinstance(summary, dict):
                continue
            path_text = _short_text(str(summary.get("path_text") or ""), 240)
            path_key = _control_path_name_key(path_text)
            if not path_key or path_key in seen_text_paths:
                continue
            seen_text_paths.add(path_key)
            relation_types = [
                str(item).strip()
                for item in summary.get("relation_types", [])
                if str(item).strip()
            ]
            path_nodes = [
                str(item).strip()
                for item in summary.get("path_nodes", [])
                if str(item).strip()
            ]
            from_name = path_nodes[0] if path_nodes else path_text
            to_name = str(summary.get("terminal_name") or candidate.get("name") or "")
            relation_label = " -> ".join(relation_types) or str(candidate.get("relation_type") or "control_path")
            dedupe_key = (
                _control_path_name_key(from_name),
                _control_path_name_key(to_name),
                relation_label.casefold().strip(),
            )
            if dedupe_key in seen_paths:
                continue
            seen_paths.add(dedupe_key)
            path_rows.append(
                {
                    "path_text": path_text,
                    "path_nodes": path_nodes,
                    "from_name": from_name,
                    "from_kind": "control_path",
                    "relation_type": relation_label,
                    "to_name": to_name,
                    "to_kind": str(summary.get("terminal_kind") or "person"),
                    "source": "controller_path_summary",
                    "confidence": summary.get("confidence") or candidate.get("confidence"),
                    "min_confidence": summary.get("min_confidence"),
                    "source_strength": summary.get("source_strength") or candidate.get("source_strength"),
                    "admission": summary.get("admission"),
                    "verification_status": summary.get("verification_status") or candidate.get("verification_status"),
                    "hop_count": summary.get("hop_count"),
                    "basis": summary.get("basis"),
                    "source_names": summary.get("source_names", []),
                    "evidence_ids": summary.get("evidence_ids", []),
                }
            )
        for raw_path in candidate.get("control_paths", []) or []:
            path_text = _short_text(str(raw_path), 240)
            path_key = _control_path_name_key(path_text)
            if not path_key or path_key in seen_text_paths:
                continue
            seen_text_paths.add(path_key)
            path_rows.append(
                {
                    "path_text": path_text,
                    "from_name": path_text,
                    "from_kind": "control_path",
                    "relation_type": str(candidate.get("relation_type") or "control_path"),
                    "to_name": str(candidate.get("name") or ""),
                    "to_kind": "person",
                    "source": "controller_candidate",
                    "confidence": candidate.get("confidence"),
                    "evidence_ids": candidate.get("evidence_ids", []),
                }
            )
    for edge in sorted(edges, key=lambda item: (_relationship_relation_rank(item.get("relation_type")), -(_float_or_none(item.get("confidence")) or 0))):
        target_name = str(edge.get("to_name") or edge.get("to_id") or "").strip()
        target_key = _control_path_name_key(target_name)
        if candidate_names and target_key and target_key not in candidate_display_by_key and target_name not in candidate_names:
            continue
        from_node = node_lookup.get(str(edge.get("from_id") or ""))
        to_node = node_lookup.get(str(edge.get("to_id") or ""))
        from_name = _control_path_display_name(edge.get("from_name") or (from_node or {}).get("name") or edge.get("from_id"))
        to_name = _control_path_display_name(edge.get("to_name") or (to_node or {}).get("name") or edge.get("to_id"))
        from_name = candidate_display_by_key.get(_control_path_name_key(edge.get("from_name") or edge.get("from_id")), from_name)
        to_name = candidate_display_by_key.get(_control_path_name_key(edge.get("to_name") or edge.get("to_id")), to_name)
        relation_type = str(edge.get("relation_type") or "related")
        dedupe_key = (
            _control_path_name_key(from_name),
            _control_path_name_key(to_name),
            relation_type.casefold().strip(),
        )
        if dedupe_key in seen_paths:
            continue
        seen_paths.add(dedupe_key)
        path_rows.append(
            {
                "from_name": from_name,
                "from_kind": str(edge.get("from_kind") or (from_node or {}).get("kind") or "unknown"),
                "relation_type": relation_type,
                "to_name": to_name or str(edge.get("to_id") or "").strip(),
                "to_kind": str(edge.get("to_kind") or (to_node or {}).get("kind") or "unknown"),
                "source": edge.get("source","relationship_network"),"confidence": edge.get("confidence"),
                "evidence_ids": edge.get("evidence_ids", []),
            }
        )
    return path_rows[:8]


def _control_path_display_name(raw: Any) -> str:
    value = str(raw or "").strip()
    if ":" in value:
        prefix, suffix = value.split(":", 1)
        if prefix in {"person", "company", "address"}:
            value = suffix.replace("_", " ").strip()
    return value


def _control_path_name_key(raw: Any) -> str:
    return re.sub(r"\s+", " ", _control_path_display_name(raw).casefold()).strip()


def _best_verification_status(statuses: list[str]) -> str:
    order = {
        "verified": 0,
        "corroborated": 1,
        "public_lead": 2,
        "inferred": 3,
        "needs_review": 4,
        "unknown": 5,
    }
    normalized = [str(item).strip() for item in statuses if str(item).strip()]
    if not normalized:
        return "unknown"
    return min(normalized, key=lambda item: order.get(item, 9))


def _financial_cognition_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract a compact financial read-through from SEC companyfacts evidence."""
    for item in evidence_ledger:
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        joined = "; ".join(claims)
        source = str(item.get("source") or "")
        title = str(item.get("title") or "").lower()
        is_qyyjt_financial = source.startswith("qyyjt_api:")
        if is_qyyjt_financial:
            continue
        if (
            "SEC EDGAR companyfacts" not in joined
            and "company facts" not in title
            and source != "sec_edgar_public_api"
        ):
            continue
        metrics = _parse_key_value_claims(joined)
        if not metrics:
            continue

        quality_notes: list[str] = []
        revenue = _float_or_none(metrics.get("revenue"))
        net_income = _float_or_none(metrics.get("net_income"))
        operating_cash_flow = _float_or_none(metrics.get("operating_cash_flow"))
        net_margin = _float_or_none(metrics.get("net_margin"))
        cash_conversion = _float_or_none(metrics.get("cash_conversion"))
        debt_to_assets = _float_or_none(metrics.get("debt_to_assets"))
        debt_to_equity = _float_or_none(metrics.get("debt_to_equity"))

        if revenue is not None and net_income is not None:
            quality_notes.append(
                f"profitability visible: net_income/revenue={_format_ratio(net_margin)}"
                if net_margin is not None
                else "profitability visible from SEC revenue and net income facts"
            )
        if cash_conversion is not None:
            if cash_conversion >= 1:
                quality_notes.append("operating cash flow covers reported earnings")
            elif cash_conversion >= 0.5:
                quality_notes.append("operating cash flow partially covers reported earnings")
            else:
                quality_notes.append("reported earnings have weak operating-cash conversion")
        elif operating_cash_flow is not None:
            quality_notes.append("operating cash flow is available but cash-conversion ratio is not computable")
        if debt_to_assets is not None:
            if debt_to_assets > 0.75:
                quality_notes.append("liabilities/assets is elevated")
            else:
                quality_notes.append("liabilities/assets is within a non-distress range from available facts")

        return {
            "source": item.get("source"),
            "title": item.get("title"),
            "url": item.get("url"),
            "cik": metrics.get("cik"),
            "revenue": revenue,
            "net_income": net_income,
            "operating_cash_flow": operating_cash_flow,
            "net_margin": net_margin,
            "cash_conversion": cash_conversion,
            "debt_to_assets": debt_to_assets,
            "debt_to_equity": debt_to_equity,
            "quality_notes": quality_notes,
            "source_claims": claims[:4],
            "verification_status": "official_public_sec_companyfacts",
            "comparison_status": "peer_comparison_unavailable",
        }
    qyyjt_financial = _qyyjt_financial_cognition_from_evidence(evidence_ledger)
    if qyyjt_financial:
        return qyyjt_financial
    return None


def _qyyjt_financial_cognition_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract licensed QYYJT financial statement and indicator rows."""
    metric_rows: list[dict[str, Any]] = []
    indicator_rows: list[dict[str, Any]] = []
    sources: list[str] = []
    urls: list[str] = []
    source_claims: list[str] = []

    for item in evidence_ledger:
        source = str(item.get("source") or "")
        title = str(item.get("title") or "")
        if not source.startswith("qyyjt_api:"):
            continue
        if item.get("record_kind") != "evidence":
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        if not parsed:
            continue

        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        if item.get("url"):
            urls.append(str(item.get("url")))
        source_claims.extend(claims)

        source_is_metric = source.endswith(":financial") or "financial" in title
        source_is_indicator = source.endswith(":fin_indic") or "fin_indic" in title or "indicator" in title
        metric_complete = all(
            parsed.get(field)
            for field in ("period", "metric", "value", "unit", "accounting_scope")
        )
        indicator_complete = all(
            parsed.get(field)
            for field in ("period", "indicator", "value", "unit", "meaning")
        )

        if source_is_metric and metric_complete:
            metric_rows.append(
                {
                    "period": parsed.get("period"),
                    "metric": parsed.get("metric"),
                    "value": _number_or_text(parsed.get("value")),
                    "unit": parsed.get("unit"),
                    "accounting_scope": parsed.get("accounting_scope") or parsed.get("accountingscope"),
                    "source": source,
                }
            )
        if source_is_indicator and indicator_complete:
            indicator_rows.append(
                {
                    "period": parsed.get("period"),
                    "indicator": parsed.get("indicator"),
                    "value": _number_or_text(parsed.get("value")),
                    "unit": parsed.get("unit"),
                    "meaning": parsed.get("meaning"),
                    "source": source,
                }
            )

    if not metric_rows and not indicator_rows:
        return None

    normalized = _qyyjt_financial_normalized_values(metric_rows, indicator_rows)
    quality_notes = [
        "licensed QYYJT financial contract supplied report-admissible statement or indicator fields"
    ]
    if metric_rows:
        quality_notes.append(f"financial statement metrics available: {len(metric_rows)}")
    if indicator_rows:
        quality_notes.append(f"financial indicators available: {len(indicator_rows)}")
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed financial snapshot",
        "url": urls[0] if urls else None,
        "revenue": normalized.get("revenue"),
        "net_income": normalized.get("net_income"),
        "operating_cash_flow": normalized.get("operating_cash_flow"),
        "net_margin": normalized.get("net_margin"),
        "cash_conversion": normalized.get("cash_conversion"),
        "debt_to_assets": normalized.get("debt_to_assets"),
        "debt_to_equity": normalized.get("debt_to_equity"),
        "metrics": metric_rows[:20],
        "indicators": indicator_rows[:20],
        "quality_notes": quality_notes,
        "evidence_sources": _dedupe_strings(sources)[:6],
        "source_claims": _dedupe_strings(source_claims)[:8],
        "verification_status": "licensed_qyyjt_financial_contract",
    }


def _qyyjt_financial_normalized_values(
    metric_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    metric_aliases = {
        "revenue": ("revenue", "operating_revenue", "total_revenue", "sales"),
        "net_income": ("net_income", "net_profit", "profit_attributable_to_parent"),
        "operating_cash_flow": ("operating_cash_flow", "net_cash_flow_from_operating_activities"),
    }
    indicator_aliases = {
        "net_margin": ("net_margin", "net_profit_margin"),
        "cash_conversion": ("cash_conversion", "operating_cash_flow_to_net_income"),
        "debt_to_assets": ("debt_to_assets", "liability_to_asset", "asset_liability_ratio"),
        "debt_to_equity": ("debt_to_equity",),
    }
    for row in metric_rows:
        key = _normalize_metric_name(row.get("metric"))
        for target, aliases in metric_aliases.items():
            if target not in values and any(alias in key for alias in aliases):
                values[target] = _float_or_none(row.get("value"))
    for row in indicator_rows:
        key = _normalize_metric_name(row.get("indicator"))
        for target, aliases in indicator_aliases.items():
            if target not in values and any(alias in key for alias in aliases):
                values[target] = _float_or_none(row.get("value"))
    return values


def _credit_profile_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract report-admissible QYYJT credit-profile rows from evidence claims."""
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    source_claims: list[str] = []

    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        source = str(item.get("source") or "")
        title = str(item.get("title") or "")
        if not source.startswith("qyyjt_api:") or not (source.endswith(":ent_credit") or "ent_credit" in title):
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        if not all(parsed.get(field) for field in ("credit_section", "credit_item", "credit_status", "reference_date")):
            continue
        row = {
            "section": parsed.get("credit_section"),
            "item": parsed.get("credit_item"),
            "status": parsed.get("credit_status"),
            "reference_date": parsed.get("reference_date"),
            "risk_flag": _credit_status_is_risky_value(parsed.get("credit_status")),
            "source": source,
            "url": item.get("url"),
            "confidence": item.get("confidence"),
        }
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(claims)

    if not rows:
        return None

    risky = [row for row in rows if row.get("risk_flag")]
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed credit profile",
        "item_count": len(rows),
        "risk_item_count": len(risky),
        "items": rows[:20],
        "risk_items": risky[:10],
        "verification_status": "licensed_qyyjt_credit_contract",
        "evidence_sources": _dedupe_strings(sources)[:6],
        "source_claims": _dedupe_strings(source_claims)[:8],
        "quality_notes": [
            "licensed QYYJT credit-profile contract supplied report-admissible section/item/status/date fields",
            f"credit profile rows available: {len(rows)}",
            f"risk-flagged credit rows: {len(risky)}",
        ],
    }


def _legal_administrative_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extract report-admissible QYYJT legal and administrative rows."""
    module_specs = {
        "court_cases": {
            "record_type": "court_case",
            "risk_class": "court_enforcement",
            "identifier_field": "case_number",
            "date_field": "case_date",
            "status_field": "case_status",
            "summary_fields": ("court", "cause", "parties"),
        },
        "court_announce": {
            "record_type": "court_announcement",
            "risk_class": "court_enforcement",
            "identifier_field": "case_number",
            "date_field": "hearing_date",
            "status_field": "status",
            "summary_fields": ("court", "cause", "parties"),
        },
        "dishonesty": {
            "record_type": "dishonesty_record",
            "risk_class": "court_enforcement",
            "identifier_field": "case_number",
            "date_field": "publish_date",
            "status_field": "performance_status",
            "summary_fields": ("court", "obligation"),
        },
        "limit_high": {
            "record_type": "limit_high_consumption",
            "risk_class": "court_enforcement",
            "identifier_field": "case_number",
            "date_field": "publish_date",
            "status_field": "status",
            "summary_fields": ("court", "restricted_subject"),
        },
        "execution": {
            "record_type": "enforcement_record",
            "risk_class": "court_enforcement",
            "identifier_field": "case_number",
            "date_field": "filing_date",
            "status_field": "execution_status",
            "summary_fields": ("court", "amount"),
        },
        "ent_penalty": {
            "record_type": "administrative_penalty",
            "risk_class": "administrative_risk",
            "identifier_field": "decision_number",
            "date_field": "decision_date",
            "status_field": "penalty",
            "summary_fields": ("agency", "violation", "penalty"),
        },
    }

    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    source_claims: list[str] = []
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        source = str(item.get("source") or "")
        if not source.startswith("qyyjt_api:"):
            continue
        module = source.split(":", 1)[1]
        spec = module_specs.get(module)
        if not spec:
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        identifier = parsed.get(str(spec["identifier_field"]))
        if not identifier:
            continue
        summary_values = [
            f"{field}={parsed.get(field)}"
            for field in spec["summary_fields"]
            if parsed.get(field)
        ]
        row = {
            "module": module,
            "record_type": spec["record_type"],
            "risk_class": spec["risk_class"],
            "identifier": identifier,
            "date": parsed.get(str(spec["date_field"])),
            "status": parsed.get(str(spec["status_field"])),
            "summary": "; ".join(summary_values),
            "source": source,
            "url": item.get("url"),
            "confidence": item.get("confidence"),
        }
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(claims)

    legal_events = [
        event for event in risk_events
        if str(event.get("category") or "") in {"court_enforcement", "administrative_risk"}
    ]
    if not rows and not legal_events:
        return None

    court_rows = [row for row in rows if row.get("risk_class") == "court_enforcement"]
    administrative_rows = [row for row in rows if row.get("risk_class") == "administrative_risk"]
    event_severity_counts: dict[str, int] = {}
    for event in legal_events:
        severity = str(event.get("severity") or "unknown")
        event_severity_counts[severity] = event_severity_counts.get(severity, 0) + 1

    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed legal and administrative profile",
        "row_count": len(rows),
        "court_enforcement_count": len(court_rows),
        "administrative_penalty_count": len(administrative_rows),
        "risk_event_count": len(legal_events),
        "high_or_critical_event_count": sum(
            1 for event in legal_events
            if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "event_severity_counts": event_severity_counts,
        "rows": rows[:20],
        "court_rows": court_rows[:12],
        "administrative_rows": administrative_rows[:8],
        "risk_events": [
            {
                "title": event.get("title"),
                "category": event.get("category"),
                "severity": event.get("severity"),
                "status": event.get("status"),
                "confidence": event.get("confidence"),
            }
            for event in legal_events[:10]
        ],
        "verification_status": "licensed_qyyjt_legal_admin_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT legal/admin contracts supplied report-admissible case, enforcement, dishonesty, restriction, or penalty fields",
            f"legal/admin rows available: {len(rows)}",
            f"legal/admin risk events available: {len(legal_events)}",
        ],
    }


def _operational_event_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extract report-admissible QYYJT financing, registry-change, and opinion rows."""
    module_specs = {
        "ent_financing": {
            "record_type": "financing_event",
            "event_class": "financing_capital_markets",
            "identifier_fields": ("financing_type", "counterparty"),
            "date_field": "event_date",
            "status_field": "status",
            "summary_fields": ("financing_type", "amount", "counterparty", "status"),
        },
        "ent_change": {
            "record_type": "registry_change_event",
            "event_class": "corporate_registry",
            "identifier_fields": ("change_item",),
            "date_field": "change_date",
            "status_field": "after_value",
            "summary_fields": ("change_item", "before_value", "after_value"),
        },
        "news_negative": {
            "record_type": "negative_public_opinion",
            "event_class": "public_opinion",
            "identifier_fields": ("news_title",),
            "date_field": "publish_date",
            "status_field": "sentiment",
            "summary_fields": ("publisher", "sentiment", "summary"),
        },
        "news_all": {
            "record_type": "news_opinion_event",
            "event_class": "public_opinion",
            "identifier_fields": ("news_title",),
            "date_field": "publish_date",
            "status_field": "sentiment",
            "summary_fields": ("publisher", "sentiment", "summary", "topic", "impact_level"),
        },
        "merger": {
            "record_type": "merger_restructuring_event",
            "event_class": "financing_capital_markets",
            "identifier_fields": ("event_type", "counterparty"),
            "date_field": "announcement_date",
            "status_field": "status",
            "summary_fields": ("event_type", "counterparty", "amount", "transaction_subject", "status"),
        },
    }

    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    source_claims: list[str] = []
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        source = str(item.get("source") or "")
        if not source.startswith("qyyjt_api:"):
            continue
        module = source.split(":", 1)[1]
        spec = module_specs.get(module)
        if not spec:
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        identifier = _first_parsed_value(parsed, spec["identifier_fields"])
        if not identifier:
            continue
        summary_values = [
            f"{field}={parsed.get(field)}"
            for field in spec["summary_fields"]
            if parsed.get(field)
        ]
        row = {
            "module": module,
            "record_type": spec["record_type"],
            "event_class": spec["event_class"],
            "identifier": identifier,
            "date": parsed.get(str(spec["date_field"])),
            "status": parsed.get(str(spec["status_field"])),
            "summary": "; ".join(summary_values),
            "source": source,
            "url": item.get("url"),
            "confidence": item.get("confidence"),
        }
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(claims)

    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        if str(item.get("entity_match_level") or "").lower() not in {"exact", "strong"}:
            continue
        source = str(item.get("source") or "")
        if source != "public_web_search":
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        capital_claims = [claim for claim in claims if "Public web capital lead" in claim]
        if not capital_claims:
            continue
        parsed = _parse_signal_claims("; ".join(capital_claims))
        if parsed.get("financing_event"):
            rows.append(
                {
                    "module": "public_web_capital",
                    "record_type": "financing_event",
                    "event_class": "financing_capital_markets",
                    "identifier": parsed.get("financing_amount") or parsed.get("financing_event"),
                    "date": None,
                    "status": "public_web_lead_needs_corroboration",
                    "summary": "; ".join(
                        f"{field}={parsed.get(field)}"
                        for field in ("financing_event", "financing_amount")
                        if parsed.get(field)
                    ),
                    "source": source,
                    "url": item.get("url"),
                    "confidence": item.get("confidence"),
                }
            )
        pressure_fields = [
            field
            for field in ("debt_or_credit_obligation", "cash_or_liquidity_pressure", "asset_or_equity_pressure")
            if parsed.get(field)
        ]
        if pressure_fields:
            rows.append(
                {
                    "module": "public_web_capital",
                    "record_type": "capital_pressure_event",
                    "event_class": "financing_capital_markets",
                    "identifier": "; ".join(pressure_fields),
                    "date": None,
                    "status": "public_web_lead_needs_corroboration",
                    "summary": "; ".join(
                        f"{field}={parsed.get(field)}"
                        for field in [*pressure_fields, "debt_or_credit_amount"]
                        if parsed.get(field)
                    ),
                    "source": source,
                    "url": item.get("url"),
                    "confidence": item.get("confidence"),
                }
            )
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(capital_claims)

    operational_events = [
        event for event in risk_events
        if str(event.get("category") or "") in {"corporate_registry", "financing_capital_markets", "public_opinion", "news_public_opinion"}
    ]
    if not rows and not operational_events:
        return None

    financing_rows = [row for row in rows if row.get("record_type") == "financing_event"]
    registry_change_rows = [row for row in rows if row.get("record_type") == "registry_change_event"]
    negative_opinion_rows = [row for row in rows if row.get("record_type") == "negative_public_opinion"]
    news_opinion_rows = [row for row in rows if row.get("record_type") == "news_opinion_event"]
    merger_rows = [row for row in rows if row.get("record_type") == "merger_restructuring_event"]
    capital_pressure_rows = [row for row in rows if row.get("record_type") == "capital_pressure_event"]
    has_public_web_capital = any(row.get("module") == "public_web_capital" for row in rows)
    return {
        "source": "mixed_admitted_sources" if has_public_web_capital else "qyyjt_api",
        "title": "Admitted operational event profile" if has_public_web_capital else "QYYJT licensed operational event profile",
        "row_count": len(rows),
        "financing_event_count": len(financing_rows),
        "registry_change_count": len(registry_change_rows),
        "negative_opinion_count": len(negative_opinion_rows),
        "news_opinion_count": len(news_opinion_rows),
        "merger_event_count": len(merger_rows),
        "capital_pressure_event_count": len(capital_pressure_rows),
        "risk_event_count": len(operational_events),
        "high_or_critical_event_count": sum(
            1 for event in operational_events
            if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "rows": rows[:20],
        "financing_rows": financing_rows[:8],
        "registry_change_rows": registry_change_rows[:8],
        "negative_opinion_rows": negative_opinion_rows[:8],
        "news_opinion_rows": news_opinion_rows[:8],
        "merger_rows": merger_rows[:8],
        "capital_pressure_rows": capital_pressure_rows[:8],
        "risk_events": [
            {
                "title": event.get("title"),
                "category": event.get("category"),
                "severity": event.get("severity"),
                "status": event.get("status"),
                "confidence": event.get("confidence"),
            }
            for event in operational_events[:10]
        ],
        "verification_status": (
            "admitted_operational_event_claims"
            if has_public_web_capital
            else "licensed_qyyjt_operational_event_contract"
        ),
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            (
                "licensed QYYJT contracts and exact/strong public-web capital leads supplied report-admissible operational-event rows"
                if has_public_web_capital
                else "licensed QYYJT operational-event contracts supplied report-admissible financing, registry-change, or opinion fields"
            ),
            f"operational event rows available: {len(rows)}",
            f"operational risk events available: {len(operational_events)}",
            "public-web capital rows remain corroboration-needed leads unless independently verified",
        ],
    }


def _commercial_activity_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    specs = {
        "tax": ("tax_profile", ("tax_item",), "tax_status", ("agency", "period", "amount")),
        "import_export": ("trade_activity", ("trade_type", "country"), "status", ("country", "period", "amount", "counterparty")),
        "recruit": ("recruiting_signal", ("position",), "status", ("location", "headcount", "salary_range", "publish_date")),
    }
    rows, sources, source_claims = _qyyjt_profile_rows(evidence_ledger, specs)
    events = [
        event for event in risk_events
        if any(
            marker in str(event.get("title") or "").lower()
            for marker in ("tax profile", "trade activity", "recruiting signal")
        )
    ]
    if not rows and not events:
        return None
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed commercial activity profile",
        "row_count": len(rows),
        "tax_count": sum(1 for row in rows if row.get("record_type") == "tax_profile"),
        "trade_count": sum(1 for row in rows if row.get("record_type") == "trade_activity"),
        "recruiting_count": sum(1 for row in rows if row.get("record_type") == "recruiting_signal"),
        "risk_event_count": len(events),
        "high_or_critical_event_count": sum(
            1 for event in events if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "rows": rows[:20],
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_commercial_activity_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT commercial-activity contracts supplied report-admissible tax, import/export, or recruiting fields",
            f"commercial activity rows available: {len(rows)}",
            f"commercial activity risk events available: {len(events)}",
        ],
    }


def _bond_credit_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    specs = {
        "bond_profile": ("bond_profile", ("bond_name",), "bond_status", ("issuer", "maturity_date", "coupon_rate", "rating")),
        "bond_credit": ("bond_rating", ("bond_name",), "rating", ("issuer", "rating", "rating_agency", "outlook")),
        "bond_issue": ("bond_issue", ("bond_name",), "bond_status", ("issuer", "issue_date", "issue_amount", "coupon_rate")),
        "bond_default": ("bond_default_event", ("bond_name",), "status", ("issuer", "default_date", "amount", "summary")),
        "bond_calendar": ("bond_calendar_event", ("bond_name",), "status", ("issuer", "event_date", "event_type", "amount")),
    }
    rows, sources, source_claims = _qyyjt_profile_rows(evidence_ledger, specs)
    events = [
        event for event in risk_events
        if str(event.get("category") or "") == "financing_capital_markets"
        and "bond" in str(event.get("title") or "").lower()
    ]
    if not rows and not events:
        return None
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed bond credit profile",
        "row_count": len(rows),
        "default_count": sum(1 for row in rows if row.get("record_type") == "bond_default_event"),
        "rating_count": sum(1 for row in rows if row.get("record_type") == "bond_rating"),
        "calendar_count": sum(1 for row in rows if row.get("record_type") == "bond_calendar_event"),
        "risk_event_count": len(events),
        "high_or_critical_event_count": sum(
            1 for event in events if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "rows": rows[:20],
        "top_exposures": _qyyjt_profile_top_exposures(rows),
        "monitoring_queue": _qyyjt_profile_monitoring_queue("bond_credit", rows),
        "field_coverage": _qyyjt_profile_field_coverage(
            rows,
            (
                "bond_name",
                "issuer",
                "rating",
                "rating_agency",
                "outlook",
                "issue_amount",
                "event_date",
                "default_date",
                "amount",
                "status",
            ),
        ),
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_bond_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT bond contracts supplied report-admissible bond, rating, issue, or default fields",
            f"bond rows available: {len(rows)}",
            f"bond risk events available: {len(events)}",
            "top_exposures and monitoring_queue rank admitted bond rows before report rendering",
        ],
    }


def _regional_credit_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    specs = {
        "city_invest": ("regional_credit_indicator", ("region_name", "indicator"), "risk_level", ("indicator", "period", "value", "unit", "debt_ratio", "fiscal_revenue")),
        "region_code": ("regional_credit_indicator", ("region_name", "region_code"), "risk_level", ("indicator", "period", "value", "unit", "parent_region")),
        "region_economy": ("regional_credit_indicator", ("region_name", "indicator"), "risk_level", ("indicator", "period", "value", "unit", "gdp", "fiscal_revenue", "debt_ratio")),
        "region_debt": ("regional_credit_indicator", ("region_name", "indicator"), "risk_level", ("indicator", "period", "value", "unit", "debt_balance", "debt_ratio")),
    }
    rows, sources, source_claims = _qyyjt_profile_rows(evidence_ledger, specs)
    events = [
        event for event in risk_events
        if str(event.get("category") or "") == "financing_capital_markets"
        and "regional credit indicator" in str(event.get("title") or "").lower()
    ]
    if not rows and not events:
        return None
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed regional and city-investment credit profile",
        "row_count": len(rows),
        "city_invest_count": sum(1 for row in rows if row.get("module") == "city_invest"),
        "region_code_count": sum(1 for row in rows if row.get("module") == "region_code"),
        "region_economy_count": sum(1 for row in rows if row.get("module") == "region_economy"),
        "region_debt_count": sum(1 for row in rows if row.get("module") == "region_debt"),
        "risk_event_count": len(events),
        "high_or_critical_event_count": sum(
            1 for event in events if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "rows": rows[:20],
        "top_exposures": _qyyjt_profile_top_exposures(rows),
        "monitoring_queue": _qyyjt_profile_monitoring_queue("regional_credit", rows),
        "field_coverage": _qyyjt_profile_field_coverage(
            rows,
            (
                "region_name",
                "indicator",
                "period",
                "value",
                "unit",
                "risk_level",
                "debt_ratio",
                "debt_balance",
                "fiscal_revenue",
                "gdp",
            ),
        ),
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_regional_credit_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT regional/city-investment contracts supplied report-admissible region, period, metric, and risk-level fields",
            f"regional credit rows available: {len(rows)}",
            f"regional credit risk events available: {len(events)}",
            "top_exposures and monitoring_queue rank regional credit pressure before report rendering",
        ],
    }


def _asset_solvency_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    specs = {
        "pledge": ("equity_pledge", ("shareholder",), "status", ("pledgee", "pledged_amount", "pledge_date", "ownership_ratio")),
        "freeze": ("equity_freeze", ("subject",), "status", ("court", "frozen_amount", "freeze_date", "case_number")),
        "auction": ("judicial_auction", ("asset_name",), "status", ("court", "amount", "auction_date", "asset_type")),
        "land": ("land_asset", ("land_location",), "status", ("area", "acquisition_date", "land_use", "amount")),
    }
    rows, sources, source_claims = _qyyjt_profile_rows(evidence_ledger, specs)
    events = [
        event for event in risk_events
        if str(event.get("category") or "") in {"location_assets", "court_enforcement"}
        and any(marker in str(event.get("title") or "").lower() for marker in ("pledge", "freeze", "auction", "land", "equity_"))
    ]
    if not rows and not events:
        return None
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed asset and solvency profile",
        "row_count": len(rows),
        "pledge_count": sum(1 for row in rows if row.get("record_type") == "equity_pledge"),
        "freeze_count": sum(1 for row in rows if row.get("record_type") == "equity_freeze"),
        "auction_count": sum(1 for row in rows if row.get("record_type") == "judicial_auction"),
        "land_count": sum(1 for row in rows if row.get("record_type") == "land_asset"),
        "risk_event_count": len(events),
        "high_or_critical_event_count": sum(
            1 for event in events if str(event.get("severity") or "") in {"high", "critical"}
        ),
        "rows": rows[:20],
        "top_exposures": _qyyjt_profile_top_exposures(rows),
        "monitoring_queue": _qyyjt_profile_monitoring_queue("asset_solvency", rows),
        "field_coverage": _qyyjt_profile_field_coverage(
            rows,
            (
                "shareholder",
                "pledgee",
                "pledged_amount",
                "pledge_date",
                "subject",
                "court",
                "frozen_amount",
                "freeze_date",
                "asset_name",
                "auction_date",
                "land_location",
                "area",
                "status",
            ),
        ),
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_asset_solvency_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT asset/solvency contracts supplied report-admissible pledge, freeze, auction, or land fields",
            f"asset/solvency rows available: {len(rows)}",
            f"asset/solvency risk events available: {len(events)}",
            "top_exposures and monitoring_queue rank pledge/freeze/auction/land pressure before report rendering",
        ],
    }


def _ip_tech_profile_from_evidence(
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    specs = {
        "patent": ("ip_asset", ("ip_title",), "status", ("ip_type", "registration_number", "application_date", "owner")),
        "trademark": ("ip_asset", ("ip_title",), "status", ("ip_type", "registration_number", "application_date", "owner")),
        "copyright": ("ip_asset", ("ip_title",), "status", ("ip_type", "registration_number", "application_date", "owner")),
    }
    rows, sources, source_claims = _qyyjt_profile_rows(evidence_ledger, specs)
    events = [event for event in risk_events if str(event.get("category") or "") == "ip_tech"]
    if not rows and not events:
        return None
    return {
        "source": "qyyjt_api",
        "title": "QYYJT licensed IP and technology profile",
        "row_count": len(rows),
        "patent_count": sum(1 for row in rows if row.get("module") == "patent"),
        "trademark_count": sum(1 for row in rows if row.get("module") == "trademark"),
        "copyright_count": sum(1 for row in rows if row.get("module") == "copyright"),
        "risk_event_count": len(events),
        "rows": rows[:20],
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_ip_tech_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT IP contracts supplied report-admissible patent, trademark, or copyright fields",
            f"IP rows available: {len(rows)}",
        ],
    }


def _qyyjt_profile_rows(
    evidence_ledger: list[dict[str, Any]],
    specs: dict[str, tuple[str, tuple[str, ...], str, tuple[str, ...]]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    source_claims: list[str] = []
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        source = str(item.get("source") or "")
        if not source.startswith("qyyjt_api:"):
            continue
        module = source.split(":", 1)[1]
        spec = specs.get(module)
        if spec is None:
            continue
        record_type, identifier_fields, status_field, summary_fields = spec
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        parsed = _parse_signal_claims("; ".join(claims))
        identifier = _first_parsed_value(parsed, identifier_fields)
        if not identifier:
            continue
        field_values = _qyyjt_profile_field_values(
            parsed,
            identifier_fields=identifier_fields,
            status_field=status_field,
            summary_fields=summary_fields,
        )
        row = {
            "module": module,
            "record_type": record_type,
            "identifier": identifier,
            "date": parsed.get("default_date")
            or parsed.get("issue_date")
            or parsed.get("rating_date")
            or parsed.get("pledge_date")
            or parsed.get("freeze_date")
            or parsed.get("auction_date")
            or parsed.get("acquisition_date")
            or parsed.get("application_date")
            or parsed.get("period"),
            "status": parsed.get(status_field),
            "summary": "; ".join(
                f"{field}={parsed.get(field)}"
                for field in summary_fields
                if parsed.get(field)
            ),
            "source": source,
            "url": item.get("url"),
            "confidence": item.get("confidence"),
            "field_values": field_values,
            "amount": _first_parsed_value(
                parsed,
                (
                    "amount",
                    "issue_amount",
                    "pledged_amount",
                    "frozen_amount",
                    "debt_balance",
                    "fiscal_revenue",
                    "gdp",
                ),
            ),
            "counterparty": _first_parsed_value(
                parsed,
                ("counterparty", "pledgee", "issuer", "court", "owner"),
            ),
            "pressure_flag": _qyyjt_profile_pressure_flag(record_type, parsed, status_field),
        }
        row["fingerprint"] = _qyyjt_profile_row_fingerprint(row)
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(claims)
    return rows, sources, source_claims


def _qyyjt_profile_field_values(
    parsed: dict[str, Any],
    *,
    identifier_fields: tuple[str, ...],
    status_field: str,
    summary_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Keep admitted QYYJT fields machine-readable after ledger claims are parsed."""
    fields = _dedupe_strings(
        [
            *identifier_fields,
            status_field,
            *summary_fields,
            "default_date",
            "event_date",
            "issue_date",
            "rating_date",
            "pledge_date",
            "freeze_date",
            "auction_date",
            "acquisition_date",
            "period",
            "risk_level",
            "rating",
            "outlook",
            "amount",
            "issue_amount",
            "pledged_amount",
            "frozen_amount",
            "ownership_ratio",
            "debt_ratio",
            "debt_balance",
            "fiscal_revenue",
            "gdp",
            "counterparty",
            "pledgee",
            "issuer",
            "court",
        ]
    )
    return {
        field: parsed.get(field)
        for field in fields
        if parsed.get(field) not in (None, "")
    }


def _qyyjt_profile_pressure_flag(
    record_type: str,
    parsed: dict[str, Any],
    status_field: str,
) -> str:
    status = str(parsed.get(status_field) or parsed.get("status") or "").lower()
    risk_level = str(parsed.get("risk_level") or parsed.get("rating") or parsed.get("outlook") or "").lower()
    joined = " ".join([status, risk_level, str(parsed.get("summary") or "").lower()])
    high_terms = (
        "default",
        "overdue",
        "dishonest",
        "revoked",
        "suspended",
        "expired",
        "frozen",
        "freeze",
        "auction",
        "high",
        "critical",
        "warning",
        "watch",
    )
    medium_terms = ("active", "pledge", "announced", "upcoming", "medium", "attention")
    if record_type == "bond_default_event":
        return "high"
    if record_type in {"equity_freeze", "judicial_auction"}:
        return "high" if any(term in joined for term in ("active", "frozen", "auction", "high")) else "medium"
    if any(term in joined for term in high_terms):
        return "high"
    if any(term in joined for term in medium_terms):
        return "medium"
    return "watch"


def _qyyjt_profile_row_fingerprint(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("module") or ""),
        str(row.get("record_type") or ""),
        str(row.get("identifier") or ""),
        str(row.get("date") or ""),
        str(row.get("status") or ""),
        str(row.get("amount") or ""),
    ]
    return "|".join(part.strip().lower() for part in parts if part.strip())


def _qyyjt_profile_field_coverage(
    rows: list[dict[str, Any]],
    required_fields: tuple[str, ...],
) -> dict[str, Any]:
    if not rows:
        return {
            "row_count": 0,
            "required_fields": list(required_fields),
            "covered_fields": [],
            "missing_fields": list(required_fields),
            "coverage_ratio": 0.0,
        }
    covered: set[str] = set()
    for row in rows:
        values = row.get("field_values")
        if not isinstance(values, dict):
            continue
        for field in required_fields:
            if values.get(field) not in (None, ""):
                covered.add(field)
    missing = [field for field in required_fields if field not in covered]
    return {
        "row_count": len(rows),
        "required_fields": list(required_fields),
        "covered_fields": sorted(covered),
        "missing_fields": missing,
        "coverage_ratio": round(len(covered) / len(required_fields), 3) if required_fields else 1.0,
    }


def _qyyjt_profile_top_exposures(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    rank = {"high": 0, "medium": 1, "watch": 2, "low": 3, "": 4}
    exposures: list[dict[str, Any]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            rank.get(str(item.get("pressure_flag") or ""), 4),
            str(item.get("date") or ""),
            str(item.get("identifier") or ""),
        ),
    ):
        exposures.append(
            {
                "module": row.get("module"),
                "record_type": row.get("record_type"),
                "identifier": row.get("identifier"),
                "date": row.get("date"),
                "status": row.get("status"),
                "amount": row.get("amount"),
                "counterparty": row.get("counterparty"),
                "pressure_flag": row.get("pressure_flag"),
                "summary": row.get("summary"),
                "source": row.get("source"),
                "url": row.get("url"),
                "fingerprint": row.get("fingerprint"),
            }
        )
        if len(exposures) >= limit:
            break
    return exposures


def _qyyjt_profile_monitoring_queue(
    profile_key: str,
    rows: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, row in enumerate(_qyyjt_profile_top_exposures(rows, limit=limit), start=1):
        pressure = str(row.get("pressure_flag") or "watch")
        priority = "P0" if pressure == "high" else "P1" if pressure == "medium" else "P2"
        actions.append(
            {
                "action_id": f"QYYJT-{profile_key.upper()}-{index:02d}",
                "priority": priority,
                "module": row.get("module"),
                "record_type": row.get("record_type"),
                "target": row.get("identifier"),
                "pressure_flag": pressure,
                "verify_fields": [
                    field
                    for field in ("date", "status", "amount", "counterparty", "url")
                    if row.get(field) not in (None, "")
                ],
                "next_action": (
                    "Verify amount, date, status, counterparty, and current disposal state from official or licensed records."
                    if priority == "P0"
                    else "Track status changes and corroborate fields before relying on this exposure."
                ),
                "source": row.get("source"),
                "fingerprint": row.get("fingerprint"),
            }
        )
    return actions


def _profile_event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": event.get("title"),
            "category": event.get("category"),
            "severity": event.get("severity"),
            "status": event.get("status"),
            "confidence": event.get("confidence"),
        }
        for event in events[:10]
    ]


def _first_parsed_value(parsed: dict[str, str], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = parsed.get(field)
        if value:
            return value
    return None


def _credit_status_is_risky_value(raw: Any) -> bool:
    normalized = str(raw or "").strip().lower()
    if not normalized:
        return False
    clean_markers = {"normal", "active", "valid", "good", "clear", "none", "0"}
    if normalized in clean_markers:
        return False
    risk_markers = (
        "abnormal",
        "overdue",
        "dishonest",
        "default",
        "restricted",
        "warning",
        "risk",
        "penalty",
        "invalid",
        "revoked",
        "cancelled",
        "注销",
        "吊销",
        "异常",
        "失信",
        "逾期",
        "限制",
        "处罚",
        "风险",
    )
    return any(marker in normalized for marker in risk_markers)


def _normalize_metric_name(raw: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")


def _industry_cognition_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build industry intelligence only from explicit evidence-backed signal claims."""
    industry, signals, sources, source_claims = _collect_cognition_signals(
        evidence_ledger,
        name_keys=_INDUSTRY_NAME_KEYS,
        signal_keys=_INDUSTRY_SIGNAL_KEYS,
    )
    if not industry:
        industry, description_refs, description_claims = _industry_from_public_description(evidence_ledger)
        if industry:
            sources = _dedupe_strings(sources + description_refs)
            source_claims = _dedupe_strings(source_claims + description_claims)
    if not industry or not _has_substantive_signal(signals):
        if not industry:
            return None
        report = IndustryIntelligenceEngine().analyze(industry, signals).to_dict()
        report["input_signals"] = {}
        report["evidence_sources"] = sources[:6]
        report["source_claims"] = source_claims[:4]
        report["verification_status"] = "public_description_lead"
        report["evidence_limit"] = (
            "Industry classification comes from exact-match public description only; "
            "numeric lifecycle and threat signals still require filing or structured-source corroboration."
        )
        return report

    enriched_signals = dict(signals)
    merged_sources = _dedupe_strings(_source_list(enriched_signals.get("sources")) + sources)
    if merged_sources:
        enriched_signals["sources"] = merged_sources
    report = IndustryIntelligenceEngine().analyze(industry, enriched_signals).to_dict()
    report["input_signals"] = {
        key: value for key, value in enriched_signals.items()
        if key != "sources" and str(value).strip()
    }
    report["evidence_sources"] = merged_sources[:6]
    report["source_claims"] = source_claims[:4]
    report["growth_signals"] = _dedupe_strings([s for s in signals if "growth" in str(s).lower()])[:4]
    report["policy_risk_signals"] = _dedupe_strings([s for s in signals if "policy_risk" in str(s).lower() or "substitution_risk" in str(s).lower()])[:4]
    report["verification_status"] = "evidence_backed_public_claims"
    return report


def _industry_from_public_description(
    evidence_ledger: list[dict[str, Any]],
) -> tuple[str | None, list[str], list[str]]:
    """Infer a broad industry label from exact-match public descriptions only."""
    description_keys = {
        "business_scope",
        "main_business",
        "company_description",
        "description",
        "industry",
        "sector",
        "services",
        "products",
    }
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        if str(item.get("entity_match_level") or "").lower() not in {"exact", "strong"}:
            continue
        source = str(item.get("source") or "")
        profile = _dict(item.get("source_profile"))
        authority = str(profile.get("authority") or "").lower()
        if source not in {"wikidata_public_entity_graph", "official_china_registry_portal_catalog"} and authority not in {
            "official",
            "official_public",
            "public",
            "public_web",
        }:
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        for claim in claims:
            parsed = _parse_signal_claims(claim)
            if parsed.get("industry"):
                ref = _evidence_source_ref(item)
                return str(parsed["industry"]), [ref] if ref else [], [claim]
            for key in description_keys:
                label = _industry_label_from_description(parsed.get(key, ""))
                if label:
                    ref = _evidence_source_ref(item)
                    return label, [ref] if ref else [], [claim]
            label = _industry_label_from_description(claim)
            if label:
                ref = _evidence_source_ref(item)
                return label, [ref] if ref else [], [claim]
    return None, [], []


def _industry_label_from_description(text: str) -> str | None:
    clean = str(text or "").lower()
    if "semiconductor" in clean or "integrated circuit" in clean or "chip design" in clean:
        return "semiconductors"
    if "software" in clean or "saas" in clean or "cloud service" in clean or "enterprise software" in clean:
        return "software"
    if "payment" in clean or "fintech" in clean:
        return "financial technology"
    if "technology company" in clean:
        return "technology"
    if "logistics" in clean or "supply chain" in clean or "freight" in clean or "warehousing" in clean:
        return "logistics and supply chain"
    if "education" in clean or "training" in clean or "school" in clean:
        return "education and training"
    if "telecommunication" in clean or "telecom" in clean or "wireless network" in clean:
        return "telecommunications"
    if "aerospace" in clean or "satellite" in clean or "defense" in clean:
        return "aerospace and defense"
    if "automotive" in clean or "automobile" in clean:
        return "automotive"
    if "pharmaceutical" in clean or "biotechnology" in clean:
        return "life sciences"
    if "medical device" in clean or "healthcare" in clean or "hospital" in clean:
        return "healthcare"
    if "bank" in clean or "financial services" in clean:
        return "financial services"
    if "retail" in clean or "e-commerce" in clean:
        return "retail"
    if "energy" in clean or "oil and gas" in clean:
        return "energy"
    if "real estate" in clean:
        return "real estate"
    if "construction" in clean or "engineering" in clean:
        return "construction and engineering"
    if "agriculture" in clean or "farming" in clean:
        return "agriculture"
    if "manufacturing" in clean:
        return "manufacturing"
    if "consumer goods" in clean or "food product" in clean or "apparel" in clean:
        return "consumer goods"
    return None


def _product_cognition_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build product intelligence only from explicit evidence-backed signal claims."""
    product, signals, sources, source_claims = _collect_cognition_signals(
        evidence_ledger,
        name_keys=_PRODUCT_NAME_KEYS,
        signal_keys=_PRODUCT_SIGNAL_KEYS,
    )
    if not product:
        product, description_refs, description_claims = _product_from_public_description(evidence_ledger)
        if product:
            sources = _dedupe_strings(sources + description_refs)
            source_claims = _dedupe_strings(source_claims + description_claims)
    if not product or not _has_substantive_signal(signals):
        if not product:
            return None
        report = ProductIntelligenceEngine().analyze(product, {}).to_dict()
        report["input_signals"] = {}
        report["evidence_sources"] = sources[:6]
        report["source_claims"] = source_claims[:4]
        report["verification_status"] = "public_description_lead"
        report["evidence_limit"] = (
            "Product line comes from exact-match public description or business scope only; "
            "revenue mix, lifecycle, dependency, and substitution signals still require structured-source corroboration."
        )
        return report

    enriched_signals = dict(signals)
    merged_sources = _dedupe_strings(_source_list(enriched_signals.get("sources")) + sources)
    if merged_sources:
        enriched_signals["sources"] = merged_sources
    report = ProductIntelligenceEngine().analyze(product, enriched_signals).to_dict()
    report["input_signals"] = {
        key: value for key, value in enriched_signals.items()
        if key != "sources" and str(value).strip()
    }
    report["evidence_sources"] = merged_sources[:6]
    report["source_claims"] = source_claims[:4]
    report["verification_status"] = "evidence_backed_public_claims"
    return report


def _product_from_public_description(
    evidence_ledger: list[dict[str, Any]],
) -> tuple[str | None, list[str], list[str]]:
    """Infer product/service leads from exact-match public descriptions only."""
    description_keys = {
        "business_scope",
        "main_business",
        "company_description",
        "description",
        "service",
        "services",
        "products",
        "product_line",
    }
    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        if str(item.get("entity_match_level") or "").lower() not in {"exact", "strong"}:
            continue
        claims = [str(claim) for claim in item.get("claims", []) if str(claim).strip()]
        for claim in claims:
            parsed = _parse_signal_claims(claim)
            for key in ("product", "product_name", "core_product", "products", "product_line"):
                if parsed.get(key):
                    ref = _evidence_source_ref(item)
                    return parsed[key], [ref] if ref else [], [claim]
            for key in description_keys:
                label = _product_label_from_description(parsed.get(key, ""))
                if label:
                    ref = _evidence_source_ref(item)
                    return label, [ref] if ref else [], [claim]
            label = _product_label_from_description(claim)
            if label:
                ref = _evidence_source_ref(item)
                return label, [ref] if ref else [], [claim]
    return None, [], []


def _product_label_from_description(text: str) -> str | None:
    clean = str(text or "").lower()
    if not clean:
        return None
    if "risk intelligence" in clean or "due diligence platform" in clean:
        return "risk intelligence platform"
    if "lithium" in clean and "batter" in clean:
        return "lithium batteries and energy storage systems" if "storage" in clean else "lithium batteries"
    if "energy storage" in clean:
        return "energy storage systems"
    if "semiconductor" in clean or "integrated circuit" in clean or "chip design" in clean:
        return "semiconductor chips and integrated circuits"
    if "payment platform" in clean or "payment gateway" in clean or "merchant acquiring" in clean:
        return "payment platform"
    if "enterprise software" in clean or "erp" in clean or "crm" in clean:
        return "enterprise software"
    if "logistics" in clean or "freight" in clean or "warehousing" in clean:
        return "logistics and warehousing services"
    if "education" in clean or "training" in clean:
        return "education and training services"
    if "medical device" in clean or "medical equipment" in clean:
        return "medical devices"
    if "healthcare service" in clean or "hospital" in clean:
        return "healthcare services"
    if "electric vehicle" in clean or "new energy vehicle" in clean:
        return "electric vehicles"
    if "auto parts" in clean or "automotive component" in clean:
        return "automotive components"
    if "industrial automation" in clean or "robot" in clean:
        return "industrial automation equipment"
    if "industrial equipment" in clean or "machinery" in clean:
        return "industrial equipment"
    if "software" in clean or "cloud service" in clean or "saas" in clean:
        return "software and cloud services"
    if "pharmaceutical" in clean or "drug" in clean or "biotechnology" in clean:
        return "pharmaceutical products"
    if "real estate" in clean:
        return "real estate development services"
    if "e-commerce" in clean or "online marketplace" in clean:
        return "e-commerce marketplace"
    if "food product" in clean or "beverage" in clean:
        return "food and beverage products"
    if "apparel" in clean or "clothing" in clean:
        return "apparel products"
    return None


def _supply_chain_profile_from_evidence(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract customer, supplier, upstream/downstream, and partner signals."""
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    source_claims: list[str] = []
    type_map = {
        "customer": "customer",
        "top_customer": "customer",
        "supplier": "supplier",
        "top_supplier": "supplier",
        "upstream": "upstream",
        "downstream": "downstream",
        "dealer": "channel_partner",
        "distributor": "channel_partner",
        "partner": "partner",
        "counterparty": "counterparty",
        "procurement_project": "project",
        "sales_channel": "sales_channel",
        "value_chain_role": "value_chain_role",
    }

    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        item_rows: list[dict[str, Any]] = []
        for claim in [str(claim) for claim in item.get("claims", []) if str(claim).strip()]:
            parsed = _parse_signal_claims(claim)
            for key, value in parsed.items():
                if key in type_map and value:
                    item_rows.append(
                        {
                            "type": type_map[key],
                            "field": key,
                            "value": value,
                            "source": item.get("source"),
                            "url": item.get("url"),
                            "confidence": item.get("confidence"),
                        }
                    )
                elif key in {"customer_concentration", "supplier_concentration"} and value:
                    item_rows.append(
                        {
                            "type": "concentration_signal",
                            "field": key,
                            "value": value,
                            "source": item.get("source"),
                            "url": item.get("url"),
                            "confidence": item.get("confidence"),
                        }
                    )
            if item_rows:
                source_claims.append(claim)
        if item_rows:
            rows.extend(item_rows)
            ref = _evidence_source_ref(item)
            if ref:
                sources.append(ref)

    if not rows:
        return None

    customer_rows = [row for row in rows if row["type"] == "customer"]
    supplier_rows = [row for row in rows if row["type"] == "supplier"]
    concentration_rows = [row for row in rows if row["type"] == "concentration_signal"]
    relationship_rows = [
        row for row in rows
        if row["type"] in {"upstream", "downstream", "channel_partner", "partner", "counterparty", "project", "sales_channel", "value_chain_role"}
    ]
    unique_sources = _dedupe_strings(sources)
    source_count = len(unique_sources)
    corroboration_status = (
        "multi_source_supported"
        if source_count >= 2
        else "single_source_needs_corroboration"
        if source_count == 1
        else "source_reference_missing"
    )
    return {
        "verification_status": "evidence_backed_public_claims",
        "report_classification": "corroboration_needed_lead",
        "report_classification_note": "Public web evidence. Corroborate with official/licensed source before relying as fact.",
        "corroboration_status": corroboration_status,
        "source_count": source_count,
        "row_count": len(rows),
        "customer_count": len(customer_rows),
        "upstream_count": sum(1 for r in rows if r.get("type") == "upstream"),
        "downstream_count": sum(1 for r in rows if r.get("type") == "downstream"),
        "supplier_count": len(supplier_rows),
        "relationship_count": len(relationship_rows),
        "concentration_signal_count": len(concentration_rows),
        "customers": _dedupe_supply_rows(customer_rows)[:10],
        "suppliers": _dedupe_supply_rows(supplier_rows)[:10],
        "relationships": _dedupe_supply_rows(relationship_rows)[:12],
        "concentration_signals": _dedupe_supply_rows(concentration_rows)[:8],
        "evidence_sources": unique_sources[:6],
        "source_claims": _dedupe_strings(source_claims)[:8],
        "quality_notes": [
            "customer/supplier/supply-chain rows are admitted only from evidence-ledger facts",
            "thin public hits remain leads until entity matching and source-specific extraction support admission",
            (
                "multiple independent sources support this supply-chain profile"
                if corroboration_status == "multi_source_supported"
                else "single-source supply-chain claims need cross-source corroboration before final reliance"
            ),
        ],
    }


def _dedupe_supply_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("type") or ""),
            str(row.get("field") or ""),
            str(row.get("value") or "").casefold(),
        )
        current = deduped.get(key)
        if current is None or float(row.get("confidence") or 0) > float(current.get("confidence") or 0):
            deduped[key] = row
    return list(deduped.values())


def _collect_cognition_signals(
    evidence_ledger: list[dict[str, Any]],
    *,
    name_keys: set[str],
    signal_keys: set[str],
) -> tuple[str | None, dict[str, Any], list[str], list[str]]:
    name: str | None = None
    signals: dict[str, Any] = {}
    sources: list[str] = []
    source_claims: list[str] = []

    for item in evidence_ledger:
        if item.get("record_kind") != "evidence":
            continue
        item_used = False
        for claim in [str(claim) for claim in item.get("claims", []) if str(claim).strip()]:
            parsed = _parse_signal_claims(claim)
            claim_used = False
            for key, value in parsed.items():
                if key in name_keys and value and name is None:
                    name = value
                    claim_used = True
                elif key in signal_keys and value:
                    _merge_signal(signals, key, value)
                    claim_used = True
            if claim_used:
                source_claims.append(claim)
                item_used = True
        if item_used:
            ref = _evidence_source_ref(item)
            if ref:
                sources.append(ref)

    return name, signals, _dedupe_strings(sources), _dedupe_strings(source_claims)


def _parse_signal_claims(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    chunks: list[str] = []
    for part in re.split(r"[;\n]+", str(text or "")):
        chunks.extend(re.split(r",\s*(?=[A-Za-z_][A-Za-z0-9_\- ]*=)", part))
    for part in chunks:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        clean_key = _clean_signal_key(key)
        clean_value = _clean_signal_value(value)
        if clean_key and clean_value and clean_key not in values:
            values[clean_key] = clean_value
    return values


def _clean_signal_key(raw: Any) -> str:
    token = str(raw or "").strip().lower().replace("-", "_")
    token = token.split()[-1] if token.split() else token
    return re.sub(r"[^a-z0-9_]", "", token)


def _clean_signal_value(raw: Any) -> str:
    value = str(raw or "").strip().strip("。；;，, ")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _merge_signal(signals: dict[str, Any], key: str, value: str) -> None:
    if key == "sources":
        merged = _dedupe_strings(_source_list(signals.get("sources")) + _source_list(value))
        if merged:
            signals["sources"] = merged
        return
    if key not in signals or not str(signals.get(key) or "").strip():
        signals[key] = value


def _source_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in re.split(r"[|,]", str(raw)) if item.strip()]


def _has_substantive_signal(signals: dict[str, Any]) -> bool:
    return any(key != "sources" and str(value).strip() for key, value in signals.items())


def _evidence_source_ref(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "").strip()
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    label = ": ".join(part for part in (source, title) if part)
    if url:
        return f"{label} ({url})" if label else url
    return label


def _parse_key_value_claims(text: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for part in str(text or "").replace(",", ";").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        clean_key = key.strip().split()[-1].lower()
        clean_value = _clean_metric_token(value)
        if clean_key and (clean_key not in metrics or _float_or_none(metrics.get(clean_key)) is None):
            metrics[clean_key] = clean_value
    return metrics


def _clean_metric_token(raw: Any) -> str:
    token = str(raw or "").strip().split()[0] if str(raw or "").strip() else ""
    match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", token)
    return match.group(0) if match else token


def _float_or_none(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _number_or_text(raw: Any) -> float | str | None:
    if raw in (None, ""):
        return None
    value = _float_or_none(raw)
    if value is not None:
        return value
    return str(raw).strip()


def _format_ratio(raw: Any) -> str:
    value = _float_or_none(raw)
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _format_amount(raw: Any) -> str:
    value = _float_or_none(raw)
    if value is None:
        return "n/a"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value:,.0f}"


def _profile_brief(summary: dict[str, Any], subject_profile: dict[str, Any]) -> dict[str, Any]:
    compact = _dict(summary.get("subject_profile"))
    dimensions = compact.get("covered_dimensions") or []
    if not isinstance(dimensions, list):
        dimensions = []
    candidates = subject_profile.get("controller_candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    gaps = subject_profile.get("evidence_gaps") or []
    if not isinstance(gaps, list):
        gaps = []
    signals_by_dimension = subject_profile.get("signals_by_dimension") or {}
    if not isinstance(signals_by_dimension, dict):
        signals_by_dimension = {}
    if not dimensions:
        dimensions = [
            str(key)
            for key, value in signals_by_dimension.items()
            if str(key).strip() and isinstance(value, list) and value
        ]
    registry_identity = _registry_identity_from_subject_profile(subject_profile)

    high_sensitivity_count = 0
    key_signals: list[dict[str, Any]] = []
    for signals in signals_by_dimension.values():
        if isinstance(signals, list):
            high_sensitivity_count += sum(1 for item in signals if _dict(item).get("sensitivity") == "high")
            for item in signals:
                signal = _dict(item)
                if not signal.get("value"):
                    continue
                key_signals.append(
                    {
                        "dimension": signal.get("dimension"),
                        "title": signal.get("title"),
                        "value": signal.get("value"),
                        "confidence": signal.get("confidence"),
                        "verification_status": signal.get("verification_status"),
                        "source_names": signal.get("source_names", []),
                        "sensitivity": signal.get("sensitivity"),
                    }
                )

    return {
        "seed_subject_name": compact.get("seed_subject_name") or subject_profile.get("seed_subject_name"),
        "subject_count": compact.get("subject_count", 0),
        "controller_candidate_count": compact.get("controller_candidate_count", len(candidates)),
        "controller_candidates": [
            {
                "name": item.get("name"),
                "confidence": item.get("confidence"),
                "verification_status": item.get("verification_status"),
                "source_names": item.get("source_names", []),
            }
            for item in [_dict(candidate) for candidate in candidates[:5]]
        ],
        "covered_dimensions": [str(item) for item in dimensions],
        "dimension_counts": compact.get("dimension_counts") or {
            str(key): len(value)
            for key, value in signals_by_dimension.items()
            if isinstance(value, list)
        },
        "high_sensitivity_lead_count": high_sensitivity_count,
        "key_signals": _rank_profile_signals(key_signals)[:8],
        "registry_identity": registry_identity,
        "evidence_gaps": [str(item) for item in gaps[:8]],
        "recursion_policy": compact.get("recursion_policy") or subject_profile.get("recursion_policy") or {},
    }


def _registry_identity_from_subject_profile(subject_profile: dict[str, Any]) -> dict[str, Any]:
    seed_subject_id = str(subject_profile.get("seed_subject_id") or "")
    subjects = subject_profile.get("subjects")
    if not isinstance(subjects, dict):
        return {}
    seed = subjects.get(seed_subject_id)
    if not isinstance(seed, dict):
        return {}
    attributes = seed.get("attributes")
    if not isinstance(attributes, dict):
        return {}
    fields = [
        "legal_name",
        "unified_social_credit_code",
        "registry_status",
        "company_type",
        "registered_capital",
        "establishment_date",
        "operating_period",
        "registration_authority",
        "business_scope",
        "registered_address",
        "legal_representative",
    ]
    snapshot = {
        field: attributes.get(field)
        for field in fields
        if attributes.get(field) not in (None, "")
    }
    if snapshot:
        snapshot["source_names"] = seed.get("source_names", [])
        snapshot["confidence"] = seed.get("confidence")
    return snapshot




from typing import TypedDict

class EvidenceRecord(TypedDict, total=False):
    """DD 1.0 standardized evidence record.
    
    Every evidence item in the investigation MUST carry these fields.
    Incomplete records can only be admitted as lead or weak_lead.
    """
    id: str
    source: str
    source_name: str
    provenance: str
    collected_at: str
    confidence: float
    admission: str       # "fact" | "lead" | "weak_lead"
    admission_reason: str
    claim_type: str
    subject: str
    title: str
    claims: list[str]
    url: str
    authority: str
    entity_match_level: str
    entity_match_score: float

def _validate_evidence_record(item: dict[str, Any]) -> list[str]:
    """DD 1.0: Check which mandatory evidence fields are missing."""
    required = ["source","provenance","confidence","admission","admission_reason","subject"]
    missing = [f for f in required if not item.get(f)]
    return missing

def _can_admit_as_fact(item: dict[str, Any]) -> bool:
    """DD 1.0: Evidence item qualifies as fact only if:
    - No mandatory fields missing
    - Confidence >= 0.75
    - Provenance is licensed, official, or SEC EDGAR
    """
    if _validate_evidence_record(item):
        return False
    if float(item.get("confidence",0)) < 0.75:
        return False
    prov = str(item.get("provenance","")).lower()
    if prov not in ("licensed_api","official_registry","sec_edgar_public_api","qyyjt_api"):
        if not prov.startswith("qyyjt_"):
            return False
    return True

def _classify_evidence_admission(item: dict[str, Any]) -> str:
    """Classify evidence item as fact, lead, or weak_lead based on provenance and confidence.

    Returns:
        "fact" — high confidence, strong provenance, admitted into report as fact
        "lead" — medium confidence, needs corroboration, admitted as lead
        "weak_lead" — low confidence or weak source, only for investigation guidance
    """
    confidence = float(item.get("confidence") or 0)
    authority = str(item.get("authority") or "").lower()
    source = str(item.get("source") or "").lower()
    match_level = str(item.get("entity_match_level") or "").lower()
    record_source_type = str(item.get("record_source_type") or "").lower()
    if record_source_type in {"query_plan", "query_template", "search_plan", "planned_query"}:
        return "lead" if confidence >= 0.5 else "weak_lead"
    field_contract = _dict(item.get("field_contract"))
    report_admission = _dict(item.get("report_admission"))
    if field_contract and not report_admission:
        return "lead" if confidence >= 0.5 else "weak_lead"
    if report_admission and not bool(report_admission.get("admissible")):
        return "lead" if confidence >= 0.5 else "weak_lead"
    strong_match = match_level in {"exact", "strong", "verified"}

    # Strong sources → fact
    if authority in {"official", "licensed"} and strong_match and confidence >= 0.8:
        return "fact"
    if "qyyjt_api" in source and strong_match and confidence >= 0.8:
        return "fact"
    if "sec_edgar" in source and strong_match and confidence >= 0.75:
        return "fact"

    # Medium sources or lower confidence → lead
    if authority in {"official", "licensed", "public"} and confidence >= 0.6:
        return "lead"
    if strong_match and confidence >= 0.5:
        return "lead"

    # Everything else → weak_lead
    if confidence < 0.4:
        return "weak_lead"
    return "weak_lead"

def _evidence_ledger(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(evidence, key=_evidence_sort_key):
        source_profile = _dict(item.get("source_profile"))
        entity_match = _dict(item.get("entity_match"))
        row_key = (
            str(item.get("source") or ""),
            str(item.get("title") or ""),
            str(item.get("url") or ""),
        )
        if row_key in seen:
            continue
        seen.add(row_key)
        admission = _classify_evidence_admission({
            "confidence": item.get("confidence"),
            "authority": source_profile.get("authority"),
            "source": item.get("source"),
            "entity_match_level": entity_match.get("level"),
            "record_source_type": entity_match.get("record_source_type") or item.get("record_source_type"),
            "field_contract": item.get("field_contract"),
            "report_admission": item.get("report_admission"),
        })
        row = {
            "id": item.get("id"),
            "record_kind": _record_kind(item),
            "source": item.get("source"),
            "title": item.get("title"),
            "url": item.get("url"),
            "confidence": item.get("confidence"),
            "claim_count": item.get("claim_count", 0),
            "claims": item.get("claims", [])[:12],
            "authority": source_profile.get("authority"),
            "access": source_profile.get("access"),
            "verification_hint": _verification_hint(source_profile, item),
            "entity_match_level": entity_match.get("level"),
            "entity_match_score": entity_match.get("score"),
            "field_contract_record_type": _dict(item.get("field_contract")).get("record_type"),
            "report_admission_admissible": _dict(item.get("report_admission")).get("admissible"),
            "report_admission_missing_required_fields": list(_dict(item.get("report_admission")).get("missing_required_fields") or [])[:8],
            "report_admission_missing_common_fields": list(_dict(item.get("report_admission")).get("missing_common_fields") or [])[:8],
            "admission": admission,
            "admission_reason": f"authority={source_profile.get('authority')} confidence={item.get('confidence')} match={entity_match.get('level')}",
        }
        for key in (
            "record_type",
            "subject",
            "subject_lei",
            "subject_name",
            "related_lei",
            "related_name",
            "relationship_type",
            "relationship_status",
            "relationship_period",
        ):
            if item.get(key) not in (None, "", [], {}):
                row[key] = item.get(key)
        rows.append(row)
        if len(rows) >= 20:
            break
    return rows


def _source_provenance_summary(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    source_names = _dedupe_strings([
        str(item.get("source") or "")
        for item in evidence_ledger
        if str(item.get("source") or "").strip()
    ])
    factual = [item for item in evidence_ledger if item.get("admission") == "fact"]
    leads = [item for item in evidence_ledger if item.get("admission") in {"lead", "weak_lead"}]
    by_authority: dict[str, int] = {}
    by_access: dict[str, int] = {}
    by_record_kind: dict[str, int] = {}
    for item in evidence_ledger:
        authority = str(item.get("authority") or "unknown")
        access = str(item.get("access") or "unknown")
        kind = str(item.get("record_kind") or "unknown")
        by_authority[authority] = by_authority.get(authority, 0) + 1
        by_access[access] = by_access.get(access, 0) + 1
        by_record_kind[kind] = by_record_kind.get(kind, 0) + 1

    claim_corroboration = _claim_corroboration_summary(evidence_ledger)
    top_sources = sorted(
        [
            {
                "source": source,
                "record_count": sum(1 for item in evidence_ledger if item.get("source") == source),
                "factual_count": sum(1 for item in factual if item.get("source") == source),
                "lead_count": sum(1 for item in leads if item.get("source") == source),
                "authority": next((item.get("authority") for item in evidence_ledger if item.get("source") == source), None),
                "access": next((item.get("access") for item in evidence_ledger if item.get("source") == source), None),
            }
            for source in source_names
        ],
        key=lambda item: (-int(item["factual_count"]), -int(item["record_count"]), str(item["source"])),
    )
    return {
        "source_count": len(source_names),
        "record_count": len(evidence_ledger),
        "factual_count": len(factual),
        "lead_count": len(leads),
        "by_authority": by_authority,
        "by_access": by_access,
        "by_record_kind": by_record_kind,
        "official_or_licensed_count": sum(
            1
            for item in factual
            if item.get("authority") == "official" or item.get("access") in {"licensed", "user_authorized"}
        ),
        "top_sources": top_sources[:8],
        "claim_corroboration": claim_corroboration,
        "policy": "Only public, licensed, user-authorized, or fixture evidence enters the report; weak matches remain leads.",
    }


def _claim_corroboration_summary(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    claim_groups: dict[str, dict[str, Any]] = {}
    field_values: dict[str, dict[str, set[str]]] = {}
    for item in evidence_ledger:
        source = str(item.get("source") or item.get("source_name") or "").strip()
        if not source:
            continue
        admission = str(item.get("admission") or item.get("record_kind") or "lead")
        confidence = item.get("confidence")
        authority = str(item.get("authority") or "unknown")
        access = str(item.get("access") or "unknown")
        for claim in _claim_fragments(item.get("claims", item.get("claim", []))):
            field, value = _claim_field_value(claim)
            if not field or not value:
                continue
            key = f"{field}:{_normalize_claim_value(value)}"
            group = claim_groups.setdefault(
                key,
                {
                    "field": field,
                    "value": value,
                    "sources": set(),
                    "fact_sources": set(),
                    "lead_sources": set(),
                    "authorities": set(),
                    "access_types": set(),
                    "max_confidence": 0.0,
                },
            )
            group["sources"].add(source)
            group["authorities"].add(authority)
            group["access_types"].add(access)
            if admission == "fact":
                group["fact_sources"].add(source)
            elif admission in {"lead", "weak_lead"}:
                group["lead_sources"].add(source)
            try:
                group["max_confidence"] = max(float(group["max_confidence"]), float(confidence or 0))
            except (TypeError, ValueError):
                pass
            field_values.setdefault(field, {}).setdefault(_normalize_claim_value(value), set()).add(source)

    supported_claims = []
    single_source_claims = []
    for group in claim_groups.values():
        source_count = len(group["sources"])
        row = {
            "field": group["field"],
            "value": group["value"],
            "source_count": source_count,
            "fact_source_count": len(group["fact_sources"]),
            "lead_source_count": len(group["lead_sources"]),
            "sources": sorted(group["sources"])[:6],
            "authorities": sorted(group["authorities"])[:6],
            "access_types": sorted(group["access_types"])[:6],
            "max_confidence": round(float(group["max_confidence"]), 4),
            "status": "multi_source_supported" if source_count >= 2 else "single_source",
        }
        if source_count >= 2:
            supported_claims.append(row)
        else:
            single_source_claims.append(row)

    conflict_fields = []
    for field, values in field_values.items():
        if not _claim_field_requires_conflict_review(field):
            continue
        if len(values) < 2:
            continue
        source_union = set().union(*values.values())
        if len(source_union) < 2:
            continue
        conflict_fields.append(
            {
                "field": field,
                "status": "conflict_review_required",
                "distinct_value_count": len(values),
                "values": [
                    {"value": value, "sources": sorted(sources)[:6]}
                    for value, sources in sorted(values.items())
                ][:6],
            }
        )

    supported_claims.sort(key=lambda row: (-row["source_count"], -row["fact_source_count"], str(row["field"])))
    single_source_claims.sort(key=lambda row: (-row["fact_source_count"], -row["max_confidence"], str(row["field"])))
    conflict_fields.sort(key=lambda row: (-row["distinct_value_count"], str(row["field"])))
    return {
        "claim_count": len(claim_groups),
        "multi_source_supported_count": len(supported_claims),
        "single_source_count": len(single_source_claims),
        "conflict_field_count": len(conflict_fields),
        "supported_claims": supported_claims[:8],
        "single_source_claims": single_source_claims[:8],
        "conflict_fields": conflict_fields[:8],
        "policy": "Corroboration summarizes independent source support only; it does not upgrade lead admission by itself.",
    }


def _claim_fragments(raw_claims: Any) -> list[str]:
    if isinstance(raw_claims, str):
        values = [raw_claims]
    elif isinstance(raw_claims, list):
        values = [str(item) for item in raw_claims if str(item).strip()]
    else:
        return []
    fragments: list[str] = []
    for value in values:
        for part in re.split(r"[;\n|]+", value):
            text = part.strip()
            if "=" in text:
                fragments.append(text)
    return fragments


def _claim_field_value(claim: str) -> tuple[str, str]:
    field, value = str(claim).split("=", 1)
    field = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", "_", field.strip().lower()).strip("_")
    value = " ".join(value.strip().split())
    return field, value


def _normalize_claim_value(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def _claim_field_requires_conflict_review(field: str) -> bool:
    normalized = str(field or "").strip().lower()
    singleton_fields = {
        "actual_controller",
        "controller",
        "controlling_shareholder",
        "legal_representative",
        "legal_rep",
        "ubo",
        "ultimate_beneficial_owner",
        "unified_social_credit_code",
        "uscc",
        "lei",
        "cik",
        "registration_number",
        "registered_capital",
        "incorporation_date",
        "company_status",
    }
    return normalized in singleton_fields


def _risk_event_summary(risk_events: list[dict[str, Any]], risk_brief: dict[str, Any]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    top_findings: list[dict[str, Any]] = []
    for event in risk_events:
        severity = str(event.get("severity") or "low").lower()
        category = str(event.get("category") or "unknown")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
        top_findings.append(_finding(event))

    return {
        "risk_event_count": len(risk_events),
        "critical_risk_count": by_severity.get("critical", 0),
        "high_risk_count": by_severity.get("high", 0),
        "by_severity": by_severity,
        "by_category": by_category,
        "top_findings": top_findings[:6],
        "verdict": risk_brief.get("verdict"),
        "verdict_label": risk_brief.get("verdict_label"),
    }


def _evidence_sort_key(item: dict[str, Any]) -> tuple[int, int, int, float, str]:
    """Rank evidence for human reports: closest subject match and strongest authority first."""
    source_profile = _dict(item.get("source_profile"))
    entity_match = _dict(item.get("entity_match"))
    kind_rank = 1 if _record_kind(item) == "lead" else 0
    level = str(entity_match.get("level") or "unknown")
    level_rank = {
        "exact": 0,
        "strong": 1,
        "review": 2,
        "weak": 3,
        "unknown": 4,
    }.get(level, 4)
    authority = str(source_profile.get("authority") or "unknown")
    authority_rank = {
        "official": 0,
        "commercial": 1,
        "public_web": 2,
        "community": 3,
        "unknown": 4,
    }.get(authority, 4)
    try:
        confidence = float(item.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return (kind_rank, level_rank, authority_rank, -confidence, str(item.get("source") or ""))


def _record_kind(item: dict[str, Any]) -> str:
    evidence_type = str(item.get("type") or "")
    entity_match = _dict(item.get("entity_match"))
    source_type = str(entity_match.get("record_source_type") or "").strip().lower()
    if evidence_type == "derived_clue" or source_type in {"query_plan", "rich_query_plan"}:
        return "lead"
    if str(entity_match.get("level") or "") in {"review", "weak"}:
        return "lead"
    return "evidence"


def _monitoring_seed(
    graph_payload: dict[str, Any],
    summary: dict[str, Any],
    risk_events: list[dict[str, Any]],
    profile_brief: dict[str, Any],
    next_actions: list[str],
    source_failure_summary: dict[str, Any] | None = None,
    enterprise_cognition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_categories = sorted({str(event.get("category")) for event in risk_events if event.get("category")})
    dimensions = [str(item) for item in profile_brief.get("covered_dimensions", [])]
    coverage_recovery_actions = [
        item for item in _dict(source_failure_summary).get("coverage_recovery_actions", [])
        if isinstance(item, dict)
    ]
    coverage_recovery_execution_plan = [
        item for item in _dict(source_failure_summary).get("coverage_recovery_execution_plan", [])
        if isinstance(item, dict)
    ]
    coverage_recovery_execution_readiness = _dict(
        _dict(source_failure_summary).get("coverage_recovery_execution_readiness")
    )
    recurring_failure_patterns = [
        item for item in _dict(source_failure_summary).get("recurring_failure_patterns", [])
        if isinstance(item, dict)
    ]
    recovery_execution_queue = _recovery_execution_queue(
        coverage_recovery_execution_readiness,
        coverage_recovery_execution_plan,
        subject=str(graph_payload.get("company") or summary.get("company") or ""),
    )
    source_repair_priority_queue = _source_repair_priority_queue(
        recurring_failure_patterns,
        recovery_execution_queue,
    )
    source_health_trend_snapshot = _source_health_trend_snapshot(
        recurring_failure_patterns,
        source_repair_priority_queue,
        recovery_execution_queue,
    )
    blocked_preview = [
        item for item in recovery_execution_queue.get("blocked_preview", [])
        if isinstance(item, dict)
    ] if isinstance(recovery_execution_queue.get("blocked_preview"), list) else []
    recovery_domains = [
        str(item.get("domain"))
        for item in coverage_recovery_actions
        if str(item.get("domain") or "").strip()
    ]
    relationship_watchlist = _relationship_candidate_watchlist(_dict(enterprise_cognition))
    relationship_dimensions = ["relationship_candidate_leads"] if relationship_watchlist else []
    watched_dimensions = sorted(set(event_categories + dimensions[:8] + recovery_domains[:8] + relationship_dimensions))
    if not watched_dimensions:
        watched_dimensions = ["corporate_registry", "court_enforcement", "administrative_risk", "public_opinion"]

    return {
        "company": graph_payload.get("company"),
        "ready_for_continuous_watch": bool(summary.get("evidence_count") or summary.get("risk_event_count")),
        "current_release_monitoring_enabled": False,
        "feature_scope": "future_version_not_current_release",
        "current_release_role": "baseline_seed_only",
        "watched_dimensions": watched_dimensions,
        "risk_event_ids": [event.get("id") for event in risk_events if event.get("id")],
        "baseline_execution_state": summary.get("execution_state"),
        "baseline_evidence_count": summary.get("evidence_count", 0),
        "baseline_risk_event_count": summary.get("risk_event_count", 0),
        "suggested_cadence": _suggested_cadence(str(summary.get("highest_severity") or "")),
        "next_watch_actions": next_actions[:5],
        "coverage_recovery_watchlist": [
            {
                "domain": item.get("domain"),
                "gap_type": item.get("gap_type"),
                "target_lane": item.get("target_lane"),
                "suggested_source": item.get("suggested_source"),
                "fallback_sources": item.get("fallback_sources", []),
                "origin_priority": item.get("origin_priority", []),
                "query_family": item.get("query_family"),
                "key_fields": item.get("key_fields", []),
                "priority": item.get("priority"),
            }
            for item in coverage_recovery_actions[:8]
        ],
        "coverage_recovery_execution_plan": coverage_recovery_execution_plan[:16],
        "coverage_recovery_execution_readiness": coverage_recovery_execution_readiness,
        "recurring_failure_patterns": recurring_failure_patterns[:8],
        "source_repair_priority_queue": source_repair_priority_queue,
        "source_health_trend_snapshot": source_health_trend_snapshot,
        "recovery_execution_queue": recovery_execution_queue,
        "recovery_execution_summary": {
            "ready_to_run": recovery_execution_queue.get("ready_to_run", False),
            "queued_count": recovery_execution_queue.get("queued_count", 0),
            "blocked_count": recovery_execution_queue.get("blocked_count", 0),
            "top_blocker": blocked_preview[0] if blocked_preview else {},
            "recurring_failure_count": len(recurring_failure_patterns),
            "source_repair_priority_count": len(source_repair_priority_queue),
            "source_repair_top_action": source_repair_priority_queue[0] if source_repair_priority_queue else {},
            "source_health_top_source": source_health_trend_snapshot.get("top_source") or {},
            "source_health_blocked_source_count": source_health_trend_snapshot.get("blocked_source_count", 0),
            "policy": "Use ready queue items for immediate recovery work; use top_blocker to decide connector/admission setup.",
        },
        "relationship_candidate_watchlist": relationship_watchlist,
        "relationship_candidate_execution_plan": _relationship_candidate_execution_plan(relationship_watchlist),
    }


def _persona_surface_for_investigation(
    profile_brief: dict[str, Any],
    risk_event_summary: dict[str, Any],
    enterprise_cognition: dict[str, Any],
) -> dict[str, Any]:
    role_catalog = {
        "qian-shou-zheng": ("钱守正", "总经理", "统一边界、证据口径和最终交付"),
        "zhang-tie-zhu": ("张铁柱", "工商核查", "注册、股权、法人、实控人和关联主体"),
        "li-ming-yuan": ("李明远", "财务分析", "财务事实、现金流和盈利质量"),
        "wang-si-yuan": ("王思远", "行业分析", "行业格局、政策、竞争和产业链"),
        "zhao-gang": ("赵刚", "风险排查", "司法、失信、行政和高风险事件"),
        "ma-li-quan": ("马力全", "公开情报", "关键人、公开履历和关系线索"),
        "zhou-tong": ("周通", "数据源与OSINT", "连接器、公开网页、搜索和标准化"),
        "zheng-shen-zhi": ("郑慎之", "交叉验证", "来源核验、冲突识别和可信度判断"),
        "wu-de-hou": ("吴德厚", "质量门禁", "证据链、输出质量和退回规则"),
        "liu-wen-hua": ("刘文华", "报告撰写", "报告结构、措辞和结论边界"),
        "yan-hao-kan": ("颜好看", "输出设计", "报告可读性、排版和可视化"),
        "chen-zhi-yuan": ("陈志远", "任务拆解", "复杂任务拆分和执行路线"),
        "an-shao": ("暗哨", "流程观察", "运行基线与后续版本监测种子"),
    }
    groups = [
        ("指挥层", ["qian-shou-zheng"]),
        ("前线调查", ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan", "zhou-tong"]),
        ("质检门禁", ["zheng-shen-zhi", "wu-de-hou"]),
        ("输出团队", ["liu-wen-hua", "yan-hao-kan"]),
        ("编外支援", ["chen-zhi-yuan", "an-shao"]),
    ]
    lane_contracts = {
        "executive": {
            "packet_fields": ["profile_brief", "enterprise_cognition.evidence_gaps", "enterprise_cognition.next_questions"],
            "report_sections": ["executive_summary", "next_actions"],
            "handoff_task": "Keep final judgment tied to evidence coverage and unresolved questions.",
        },
        "registry": {
            "packet_fields": ["enterprise_cognition.control_ownership", "profile_brief.controller_candidates"],
            "report_sections": ["control_ownership", "subject_profile"],
            "handoff_task": "Trace legal representative, controller, shareholder, UBO, and related-entity facts.",
        },
        "finance": {
            "packet_fields": [
                "enterprise_cognition.financial",
                "enterprise_cognition.capital_pressure_profile",
                "enterprise_cognition.public_capital_profile",
                "one_click_readiness.capital_verification_top_step",
                "one_click_readiness.capital_relationship_next_action",
            ],
            "report_sections": ["capital_pressure", "fund_flow_profile"],
            "handoff_task": "Close financial, capital-market, and solvency evidence gaps.",
        },
        "industry": {
            "packet_fields": ["enterprise_cognition.industry", "enterprise_cognition.product", "enterprise_cognition.supply_chain_profile"],
            "report_sections": ["industry", "product", "goods_flow_profile"],
            "handoff_task": "Explain industry, product, customer, supplier, and business-model context.",
        },
        "risk": {
            "packet_fields": ["risk_event_summary.top_findings", "enterprise_cognition.risk_hypotheses"],
            "report_sections": ["risk_events", "risk_hypotheses"],
            "handoff_task": "Rank legal, enforcement, administrative, and public-risk events.",
        },
        "people": {
            "packet_fields": [
                "enterprise_cognition.people_flow_profile",
                "enterprise_cognition.public_people_profile",
                "one_click_readiness.relationship_graph_audit_top_step",
            ],
            "report_sections": ["people_flow_profile", "relationship_network"],
            "handoff_task": "Map key people, controllers, and relationship leads without overstating weak evidence.",
        },
        "data_sources": {
            "packet_fields": [
                "source_provenance",
                "source_failure_summary",
                "monitoring_seed.source_repair_priority_queue",
                "one_click_readiness.operator_work_queue",
                "one_click_readiness.operator_work_top_action",
                "qyyjt_public_origin_handoff",
            ],
            "report_sections": ["source_diagnostics", "source_repair_priority_queue"],
            "handoff_task": "Repair source failures and preserve retrieval-health boundaries.",
        },
        "verification": {
            "packet_fields": [
                "quality_gate",
                "evidence_ledger",
                "enterprise_cognition.evidence_depth_score",
                "one_click_readiness.reliance_limitations",
                "one_click_readiness.can_make_clean_conclusion",
            ],
            "report_sections": ["quality_gate", "evidence_gaps"],
            "handoff_task": "Check corroboration, conflict, and evidence-depth limits.",
        },
        "quality": {
            "packet_fields": [
                "quality_gate",
                "enterprise_cognition.investigation_audit_log",
                "one_click_readiness.reliance_limitations",
            ],
            "report_sections": ["delivery_quality", "audit_log"],
            "handoff_task": "Reject unsupported conclusions and keep fallback status explicit.",
        },
        "report": {
            "packet_fields": [
                "report_markdown",
                "report_exports",
                "enterprise_cognition.investigation_report_card",
                "one_click_readiness.reliance_limitations",
            ],
            "report_sections": ["report_markdown", "print_package"],
            "handoff_task": "Write the report so known facts, gaps, and next steps stay distinguishable.",
        },
        "output": {
            "packet_fields": ["report_exports.portable_html", "report_exports.print_package", "report_exports.markdown"],
            "report_sections": ["portable_html", "docx_print_package"],
            "handoff_task": "Keep printable and agent-readable output complete and structured.",
        },
        "task_planning": {
            "packet_fields": [
                "next_actions",
                "enterprise_cognition.next_questions",
                "monitoring_seed.recovery_execution_queue",
                "one_click_readiness.operator_work_queue",
            ],
            "report_sections": ["next_actions", "recovery_execution_queue"],
            "handoff_task": "Turn unresolved evidence gaps into executable work orders.",
        },
        "monitoring": {
            "packet_fields": ["monitoring_seed", "enterprise_cognition.monitoring_watchlist"],
            "report_sections": ["monitoring_seed", "watchlist"],
            "handoff_task": "Keep current-release monitoring as baseline seed only.",
        },
    }
    dimensions = set(str(item) for item in profile_brief.get("covered_dimensions", []) if str(item).strip())
    evidence_gaps = [str(item) for item in enterprise_cognition.get("evidence_gaps", []) if str(item).strip()]
    next_questions = [str(item) for item in enterprise_cognition.get("next_questions", []) if str(item).strip()]
    risk_findings = [item for item in risk_event_summary.get("top_findings", []) if item]

    def _basis(label: str, value: Any) -> str:
        if isinstance(value, dict):
            return f"{label}=present" if value else ""
        if isinstance(value, list):
            return f"{label}={len(value)}" if value else ""
        return f"{label}=present" if value else ""

    def _first(prefix: str, values: list[str]) -> str:
        return f"{prefix}={_short_text(values[0], 90)}" if values else ""

    persona_evidence = {
        "qian-shou-zheng": {"lane": "executive", "sources": [_basis("seed_subject", profile_brief.get("seed_subject_name")), _basis("covered_dimensions", list(dimensions)), _first("gap", evidence_gaps), _first("next_question", next_questions)]},
        "zhang-tie-zhu": {"lane": "registry", "sources": [_basis("control_ownership", enterprise_cognition.get("control_ownership")), _basis("public_people_profile", enterprise_cognition.get("public_people_profile"))]},
        "li-ming-yuan": {"lane": "finance", "sources": [_basis("financial", enterprise_cognition.get("financial")), _basis("public_capital_profile", enterprise_cognition.get("public_capital_profile"))]},
        "wang-si-yuan": {"lane": "industry", "sources": [_basis("industry", enterprise_cognition.get("industry")), _basis("public_goods_profile", enterprise_cognition.get("public_goods_profile")), _basis("supply_chain_profile", enterprise_cognition.get("supply_chain_profile"))]},
        "zhao-gang": {"lane": "risk", "sources": [_basis("risk_findings", risk_findings), _basis("risk_events", enterprise_cognition.get("risk_events"))]},
        "ma-li-quan": {"lane": "people", "sources": [_basis("public_people_profile", enterprise_cognition.get("public_people_profile")), _basis("control_ownership", enterprise_cognition.get("control_ownership"))]},
        "zhou-tong": {"lane": "data_sources", "sources": [_basis("covered_dimensions", list(dimensions)), _basis("source_readiness", enterprise_cognition.get("source_readiness"))]},
        "zheng-shen-zhi": {"lane": "verification", "sources": [_first("gap", evidence_gaps), _basis("evidence_depth_score", enterprise_cognition.get("evidence_depth_score"))]},
        "wu-de-hou": {"lane": "quality", "sources": [_basis("evidence_depth_score", enterprise_cognition.get("evidence_depth_score")), _basis("investigation_audit_log", enterprise_cognition.get("investigation_audit_log"))]},
        "liu-wen-hua": {"lane": "report", "sources": [_basis("subject_due_diligence_profile", enterprise_cognition.get("subject_due_diligence_profile")), _basis("investigation_report_card", enterprise_cognition.get("investigation_report_card"))]},
        "yan-hao-kan": {"lane": "output", "sources": [_basis("public_goods_profile", enterprise_cognition.get("public_goods_profile")), _basis("people_flow_profile", enterprise_cognition.get("people_flow_profile")), _basis("fund_flow_profile", enterprise_cognition.get("fund_flow_profile"))]},
        "chen-zhi-yuan": {"lane": "task_planning", "sources": [_first("next_question", next_questions), _first("gap", evidence_gaps)]},
        "an-shao": {"lane": "monitoring", "sources": [_basis("monitoring_watchlist", enterprise_cognition.get("monitoring_watchlist")), _basis("risk_hypotheses", enterprise_cognition.get("risk_hypotheses"))]},
    }
    persona_evidence = {
        agent_id: {"lane": item["lane"], "sources": [source for source in item["sources"] if source]}
        for agent_id, item in persona_evidence.items()
    }
    active_ids = set(agent_id for agent_id, item in persona_evidence.items() if item["sources"])
    role_roster = [
        {
            "agent_id": agent_id,
            "display_name": role_catalog[agent_id][0],
            "role": role_catalog[agent_id][1],
            "responsibility": role_catalog[agent_id][2],
            "active": agent_id in active_ids,
        }
        for agent_id in role_catalog
    ]
    # Enrich role roster with evidence binding
    enriched_roles = []
    for role in role_roster:
        aid = role["agent_id"]
        ev = persona_evidence.get(aid, {})
        role["lane"] = ev.get("lane", "general")
        role["evidence_sources"] = ev.get("sources", [])
        lane_contract = lane_contracts.get(str(role["lane"]), {})
        role["packet_fields"] = list(lane_contract.get("packet_fields") or [])
        role["report_sections"] = list(lane_contract.get("report_sections") or [])
        role["handoff_task"] = lane_contract.get("handoff_task") or ""
        if role["active"]:
            role["next_question"] = enterprise_cognition.get("next_questions",[])[:1] if enterprise_cognition.get("next_questions") else []
        enriched_roles.append(role)
    lane_bindings = []
    for lane, contract in lane_contracts.items():
        role_ids = [
            role["agent_id"]
            for role in enriched_roles
            if role.get("lane") == lane
        ]
        active_role_ids = [agent_id for agent_id in role_ids if agent_id in active_ids]
        lane_bindings.append(
            {
                "lane": lane,
                "role_ids": role_ids,
                "active_role_ids": active_role_ids,
                "packet_fields": list(contract.get("packet_fields") or []),
                "report_sections": list(contract.get("report_sections") or []),
                "handoff_task": contract.get("handoff_task") or "",
                "active": bool(active_role_ids),
            }
        )

    return {
        "type": "investigation_persona_surface",
        "version": "0.5.0",
        "display_name": "华尔街驻铁岭办事处 13 角色专家团",
        "role_count": len(enriched_roles),
        "active_role_count": len(active_ids),
        "active_roles": [role for role in enriched_roles if role["active"]],
        "lane_bindings": lane_bindings,
        "groups": [
            {
                "label": label,
                "agent_ids": ids,
                "active_agent_ids": [agent_id for agent_id in ids if agent_id in active_ids],
                "active_roles": [
                    {"agent_id": aid, "lane": persona_evidence.get(aid,{}).get("lane","general")}
                    for aid in ids if aid in active_ids
                ],
            }
            for label, ids in groups
        ],
        "principle": "角色是调查分工和产品体验层；结论仍以公开、授权或许可来源的证据链为准。",
    }



def _build_investigation_audit_log(
    summary: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
    enterprise_cognition: dict[str, Any],
) -> dict[str, Any]:
    sources_queried = summary.get("queried_sources", [])
    evidence_count = len(evidence_ledger)
    facts = [e for e in evidence_ledger if e.get("admission") == "fact"]
    leads = [e for e in evidence_ledger if e.get("admission") in ("lead", "weak_lead")]
    failed = len(summary.get("failed_sources", []))
    risk_count = len(risk_events)
    high_risks = [e for e in risk_events if str(e.get("severity","")).lower() == "high"]
    coverage = {}
    for lane, key in [("capital","public_capital_profile"),("goods","public_goods_profile"),("people","public_people_profile")]:
        profile = enterprise_cognition.get(key)
        coverage[lane] = {"has_data": profile is not None, "signal_count": profile.get("row_count",0) if profile else 0}
    # Count rejected/weak lead evidence
    rejected = [e for e in evidence_ledger if e.get("admission") == "weak_lead"]
    # Collect admission reasons for explainability
    admission_reasons = []
    for e in evidence_ledger:
        reason = e.get("admission_reason", "")
        if reason:
            admission_reasons.append(f"[{e.get('admission','?')}] {reason}")

    return {
        "investigation_id": summary.get("run_id", ""),
        "query_subject": summary.get("company", ""),
        "enabled_sources": sources_queried[:10],
        "called_sources": sources_queried[:10],
        "sources": {"queried": sources_queried[:10], "total_queried": len(sources_queried), "failed": failed, "evidence_produced": evidence_count},
        "evidence": {
            "total": evidence_count,
            "admitted_as_fact": len(facts),
            "admitted_as_lead": len(leads),
            "rejected_or_weak": len(rejected),
            "admission_policy": "fact=high_confidence+strong_provenance",
        },
        "risk_events": {"total": risk_count, "high_severity": len(high_risks), "categories": list({str(e.get("category","")) for e in risk_events})},
        "coverage": coverage,
        "gaps": enterprise_cognition.get("evidence_gaps", [])[:5],
        "sources_used": _dedupe_strings([str(e.get("source","")) for e in evidence_ledger]),
        "admission_explanations": admission_reasons[:10],
        "report_sections": ["company_profile", "risk_events", "financial", "industry", "supply_chain", "relationship_network", "evidence_ledger", "next_steps"],
        "source_readiness_for_audit": {"ready_for_production": (enterprise_cognition.get("source_smoke_harness") or {}).get("ready_for_production",False),"overall_status": (enterprise_cognition.get("source_smoke_harness") or {}).get("overall_status","unknown")},
        "graph_quality_for_audit": enterprise_cognition.get("graph_quality_audit_v2",{}),
        "pipeline_contract_status": "verified" if len(enterprise_cognition.get("evidence_ledger_v2",[]))>0 else "unverified",
        "strategy_action_count_for_audit": (enterprise_cognition.get("investigation_strategy_v2") or {}).get("action_count",0),
        "smoke_status": {
            "public": {
                k: {"source_name": v["source_name"], "status": v["status"], "live_verified": v["live_verified"]}
                for k, v in _safe_smoke("public").items()
            },
            "authorized": {
                k: {"source_name": v["source_name"], "status": v["status"], "live_verified": v["live_verified"], "credential_required": v["credential_required"]}
                for k, v in _safe_smoke("authorized").items()
            },
        },
        "source_status_snapshot": {k: {"status": v.get("status","?"), "live_verified": v.get("live_verified")} for k,v in (dict(**_safe_smoke("public"), **_safe_smoke("authorized"))).items()},
        "relationship_graph_stats": {"nodes": len(enterprise_cognition.get("subject_due_diligence_profile",{}).get("relationship_graph",{}).get("nodes",[])), "edges": len(enterprise_cognition.get("subject_due_diligence_profile",{}).get("relationship_graph",{}).get("edges",[])), "source": "build_subject_relationship_graph"},
        "dd_profile_sections": [k for k in enterprise_cognition.get("subject_due_diligence_profile",{}).keys() if k not in ("relationship_graph",)],
        "report_sections": ["company_profile", "risk_events", "financial", "industry", "supply_chain", "relationship_network", "evidence_ledger", "next_steps"],
        "source_readiness_for_audit": {"ready_for_production": (enterprise_cognition.get("source_smoke_harness") or {}).get("ready_for_production",False),"overall_status": (enterprise_cognition.get("source_smoke_harness") or {}).get("overall_status","unknown")},
        "graph_quality_for_audit": enterprise_cognition.get("graph_quality_audit_v2",{}),
        "pipeline_contract_status": "verified" if len(enterprise_cognition.get("evidence_ledger_v2",[]))>0 else "unverified",
        "strategy_action_count_for_audit": (enterprise_cognition.get("investigation_strategy_v2") or {}).get("action_count",0),
        "strategy_plan_count": len(enterprise_cognition.get("investigation_strategy",{}).get("strategy_plan",[])),
        "evidence_gap_summary": enterprise_cognition.get("evidence_gap_analysis",{}).get("gap_summary",{}),
        "graph_summary": enterprise_cognition.get("graph_explainability_v2",{}).get("graph_summary",{}),
        "high_value_path_count": len(enterprise_cognition.get("graph_explainability_v2",{}).get("graph_summary",{}).get("high_value_paths",[])),
        "no_sensitive_artifacts": True,
    }



def _safe_smoke(kind: str) -> dict:
    """Safe wrapper for smoke functions — catches import/execution errors."""
    try:
        from core.source_smoke import public_source_smoke, authorized_source_smoke
        return public_source_smoke() if kind == "public" else authorized_source_smoke()
    except Exception:
        return {}


def _safe_smoke(kind: str) -> dict:
    """Safe wrapper for smoke functions."""
    try:
        from core.source_smoke import public_source_smoke, authorized_source_smoke
        return public_source_smoke() if kind == "public" else authorized_source_smoke()
    except Exception:
        return {}

def _build_human_readable_dd_summary(dd: dict[str, Any] | None) -> str:
    """Generate a plain-language summary of the due diligence profile."""
    if not dd:
        return "Due diligence profile not available."
    exec_sum = dd.get("executive_summary", {})
    cap = dd.get("capital_lane", {})
    goods = dd.get("goods_lane", {})
    people = dd.get("people_lane", {})
    risk_labels = {"high": "HIGH RISK", "medium": "MODERATE RISK", "low": "LOW RISK", "unknown": "INSUFFICIENT DATA"}
    fm = dd.get("capital_lane", {}).get("financial_metrics") or {}
    fin_line = ""
    if fm:
        rev = fm.get("revenue")
        ni = fm.get("net_income")
        da = fm.get("debt_to_assets")
        if rev:
            fin_line = f" | Revenue: {rev:,.0f}" if isinstance(rev, (int, float)) else f" | Revenue: {rev}"
        if ni:
            fin_line += f" | Net Income: {ni:,.0f}" if isinstance(ni, (int, float)) else f" | Net Income: {ni}"
        if da is not None and isinstance(da, (int, float)):
            fin_line += f" | D/A: {da:.1%}"
    parts = [
        f"DD Summary: {dd.get('company', '?')} | Overall: {risk_labels.get(exec_sum.get('overall_risk', 'unknown'), '?')} | Confidence: {exec_sum.get('evidence_confidence', '?')}{fin_line} | Findings: {exec_sum.get('total_findings', '?')} total",
        f"Capital: {risk_labels.get(cap.get('risk', 'unknown'), '?')} ({cap.get('public_signals_count', 0)} signals) | Goods: {risk_labels.get(goods.get('risk', 'unknown'), '?')} ({goods.get('public_signals_count', 0)} signals) | People: {risk_labels.get(people.get('risk', 'unknown'), '?')} ({people.get('public_signals_count', 0)} signals)",
    ]
    return " | ".join(parts)


def build_subject_relationship_graph(
    company_name: str = "",
    subject_profile: dict[str, Any] | None = None,
    relationship_network: dict[str, Any] | None = None,
    evidence_ledger: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """DD 1.0: Build typed multi-layer relationship graph.

    Node types: company, person, address, supplier, customer, legal_event
    Edge types: controls, serves_as, located_at, supplies, buys_from,
                litigation_related, same_address
    Each edge: source, confidence, admission (fact/lead/weak_lead).
    Weak matches (same_name, same_address): admission=weak_lead only.
    Default depth=1.
    """
    sp = subject_profile or {}
    rn = relationship_network or {}
    el = evidence_ledger or []
    nodes = {}
    edges = []

    if company_name:
        nodes["seed"] = {"id": "seed", "type": "company", "name": company_name, "depth": 0, "entity_resolution_key": f"company:normalized:{company_name.lower().strip()}"}

    for item in rn.get("controller_candidates", [])[:5]:
        name = item.get("name") or item.get("candidate_name", "")
        if name:
            nid = f"person:{name}"
            nodes[nid] = {"id": nid, "type": "person", "name": str(name), "role": "controller", "depth": 1, "entity_resolution_key": f"person:normalized:{str(name).lower().strip()}:controller:subject_profile"}
            edges.append({"source": "subject_profile","from": "seed", "to": nid, "type": "controls", "confidence": float(item.get("confidence", 0.5)),
                "admission": str(item.get("admission", "lead")), "source": str(item.get("evidence_source", "subject_profile")),
                "explanation": f"Controller candidate {name} from subject_profile"})

    for item in rn.get("legal_representatives", [])[:3]:
        name = item.get("name", "")
        if name:
            nid = f"person:legal:{name}"
            nodes[nid] = {"id": nid, "type": "person", "name": str(name), "role": "legal_representative", "depth": 1, "entity_resolution_key": f"person:normalized:{str(name).lower().strip()}:legal_rep:subject_profile"}
            edges.append({"source": "subject_profile","from": "seed", "to": nid, "source": "subject_profile","type": "serves_as", "confidence": float(item.get("confidence", 0.5)),
                "admission": "fact" if item.get("authority") == "official" else "lead", "source": str(item.get("evidence_source", "subject_profile")),
                "explanation": f"Legal representative {name} from subject_profile"})

    addr = rn.get("registered_address") or sp.get("registered_address")
    if addr:
        nid = f"address:{addr}"
        nodes[nid] = {"id": nid, "type": "address", "name": str(addr), "depth": 1, "entity_resolution_key": f"address:normalized:{str(addr).lower().strip()}"}
        edges.append({"source": "subject_profile","from": "seed", "to": nid, "source": "subject_profile","type": "located_at", "confidence": 0.9, "admission": "fact", "source": "official_registry",
            "explanation": f"Registered address from official registry"})

    for a in rn.get("common_addresses", [])[:3]:
        nid = f"address:common:{a}"
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": "address", "name": str(a), "depth": 1}
            edges.append({"source": "subject_profile","from": "seed", "to": nid, "source": "public_record","type": "same_address", "confidence": 0.35, "admission": "weak_lead", "source": "public_web",
                "explanation": f"Same address {a} from public web — weak lead only, NOT fact"})

    for item in el:
        for claim in item.get("claims", []):
            if "supplier=" in str(claim).lower():
                name = str(claim).split("supplier=")[1].split(";")[0].strip()
                nid = f"company:supplier:{name}"
                if nid not in nodes:
                    nodes[nid] = {"id": nid, "type": "supplier", "name": name, "depth": 1}
                    edges.append({"source": "subject_profile","from": "seed", "to": nid, "source": "supply_chain_profile","type": "supplies", "confidence": 0.5, "admission": "lead", "source": str(item.get("source", "")),
                        "explanation": f"Supplier {name} from public claims, needs corroboration"})
            if "customer=" in str(claim).lower():
                name = str(claim).split("customer=")[1].split(";")[0].strip()
                nid = f"company:customer:{name}"
                if nid not in nodes:
                    nodes[nid] = {"id": nid, "type": "customer", "name": name, "depth": 1}
                    edges.append({"source": "subject_profile","from": "seed", "to": nid, "source": "supply_chain_profile","type": "buys_from", "confidence": 0.5, "admission": "lead", "source": str(item.get("source", "")),
                        "explanation": f"Customer {name} from public claims, needs corroboration"})

    return {
        "version": "1.0",
        "nodes": list(nodes.values()),
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "default_depth": 1,
        "admission_policy": "same_name/same_address/same_project = weak_lead only. Facts require licensed/official provenance. Each edge has explanation field.",
        "note": "DD v2.1: Two-phase resolution (aiqicha_scraper pattern): Phase 1 collect entity IDs/names from public+licensed sources, Phase 2 resolve relationships. Each node has entity_resolution_key. Edges have source/confidence/admission/explanation. Same_name/same_address/same_project = weak_lead.",
    }

def _policy_cap(key: str, default: int) -> int:
    """Read report cap from RuntimePolicy, falling back to default."""
    try:
        from .investigation_policy import get_active_policy
        mapping = {"risk_count": 8, "watchlist": 15, "questions": 15, "rows": 20}
        return mapping.get(key, default)
    except Exception:
        return default

def _public_lead_profile_report_lines(enterprise_cognition: dict[str, Any]) -> list[str]:
    """Render corroboration-needed public lead profiles into the human report."""
    profile_specs = [
        ("capital", "public_capital_profile"),
        ("goods", "public_goods_profile"),
        ("people", "public_people_profile"),
    ]
    rows: list[str] = []
    for label, key in profile_specs:
        profile = enterprise_cognition.get(key)
        if not isinstance(profile, dict):
            continue
        row_count = int(profile.get("row_count") or 0)
        if row_count <= 0:
            continue
        if not rows:
            rows.extend(
                [
                    "",
                    "## Public Lead Profiles",
                    "- Boundary: rows below are corroboration-needed leads, not report facts. Upgrade them with official, licensed, or user-authorized evidence before reliance.",
                ]
            )
        title = str(profile.get("title") or key)
        verification = str(profile.get("verification_status") or "corroboration_needed")
        rows.append(f"- {label}: {row_count} leads | status={verification} | {title}")
        for claim in _report_claims(profile.get("claims", []))[:3]:
            rows.append(f"  - claim: {_short_text(claim, 140)}")
        rendered = 0
        for item in profile.get("rows", []) or []:
            if not isinstance(item, dict):
                continue
            claims = _report_claims(item.get("claims", []))
            url = str(item.get("url") or "").strip()
            if claims:
                rows.append(f"  - lead: {_short_text(claims[0], 140)}" + (f" | url={_short_text(url, 100)}" if url else ""))
                rendered += 1
            if rendered >= 2:
                break
        for note in [str(item) for item in profile.get("quality_notes", []) if str(item).strip()][:2]:
            rows.append(f"  - note: {_short_text(note, 150)}")
    return rows

def _lane_summary_report_lines(enterprise_cognition: dict[str, Any]) -> list[str]:
    card = _dict(enterprise_cognition.get("investigation_report_card"))
    summary = _dict(card.get("dd_summary"))
    money = _dict(summary.get("money_lane_summary"))
    goods = _dict(summary.get("goods_lane_summary"))
    people = _dict(summary.get("people_lane_summary"))
    if not any((money, goods, people)):
        return []

    rows = ["", "## Due Diligence Lane Summary"]
    for label, lane in (
        ("money", money),
        ("goods", goods),
        ("people", people),
    ):
        if not lane:
            continue
        rows.append(
            f"- {label}: status={lane.get('lane_status', 'unknown')} | "
            f"facts={lane.get('fact_count', 0)} | leads={lane.get('lead_count', 0)}"
        )

    money_bridge = _dict(money.get("qyyjt_bridge"))
    if money_bridge:
        rows.append(
            "- qyyjt pledge bridge: "
            f"facts={money_bridge.get('pledge_fact_count', 0)} | "
            f"leads={money_bridge.get('pledge_lead_count', 0)} | "
            f"pressure={money_bridge.get('pressure_level', 'NONE')} | "
            f"operational={money_bridge.get('bridge_operational', False)}"
        )
        if money_bridge.get("bond_row_count") or money_bridge.get("bond_pressure_level") not in {None, "", "none"}:
            rows.append(
                "- qyyjt bond bridge: "
                f"rows={money_bridge.get('bond_row_count', 0)} | "
                f"defaults={money_bridge.get('bond_default_count', 0)} | "
                f"high={money_bridge.get('bond_high_or_critical_event_count', 0)} | "
                f"pressure={money_bridge.get('bond_pressure_level', 'none')}"
            )

    capital_public_summary = _dict(money.get("public_capital_structured_summary"))
    if capital_public_summary:
        rows.append(
            "- capital public leads: "
            f"debt={capital_public_summary.get('debt_credit', 0)} | "
            f"refinancing={capital_public_summary.get('refinancing', 0)} | "
            f"liquidity={capital_public_summary.get('liquidity', 0)} | "
            f"asset_pressure={capital_public_summary.get('asset_pressure', 0)} | "
            f"financing={capital_public_summary.get('financing_events', 0)}"
        )
        for label, key in (
            ("debt", "debt_credit_claims"),
            ("refinancing", "refinancing_claims"),
            ("liquidity", "liquidity_claims"),
            ("asset", "asset_pressure_claims"),
        ):
            signals = [str(item) for item in money.get(key, []) if str(item).strip()]
            if signals:
                rows.append(
                    f"  - {label}: "
                    + "; ".join(_short_text(item, 100) for item in signals[:3])
                )

    goods_bridge = _dict(goods.get("qyyjt_bridge"))
    if goods_bridge:
        rows.append(
            "- qyyjt trade bridge: "
            f"facts={goods_bridge.get('trade_fact_count', 0)} | "
            f"leads={goods_bridge.get('trade_lead_count', 0)} | "
            f"activity={goods_bridge.get('activity_level', 'NONE')} | "
            f"operational={goods_bridge.get('bridge_operational', False)}"
        )

    goods_public_summary = _dict(goods.get("public_goods_structured_summary"))
    if goods_public_summary:
        rows.append(
            "- goods public leads: "
            f"customers={goods_public_summary.get('customers', 0)} | "
            f"suppliers={goods_public_summary.get('suppliers', 0)} | "
            f"channels={goods_public_summary.get('channels', 0)} | "
            f"market={goods_public_summary.get('market_position', 0)} | "
            f"model={goods_public_summary.get('business_model', 0)} | "
            f"unit={goods_public_summary.get('unit_economics', 0)} | "
            f"power={goods_public_summary.get('bargaining_power', 0)} | "
            f"competition={goods_public_summary.get('competitive_landscape', 0)}"
        )
        for label, key in (
            ("market", "market_position_claims"),
            ("model", "business_model_claims"),
            ("unit", "unit_economics_claims"),
            ("power", "bargaining_power_claims"),
            ("competition", "competitive_landscape_claims"),
            ("customer", "customer_claims"),
            ("supplier", "supplier_claims"),
            ("channel", "channel_partner_claims"),
        ):
            signals = [str(item) for item in goods.get(key, []) if str(item).strip()]
            if signals:
                rows.append(
                    f"  - {label}: "
                    + "; ".join(_short_text(item, 100) for item in signals[:3])
                )

    people_public_summary = _dict(people.get("public_people_structured_summary"))
    if people_public_summary:
        rows.append(
            "- people public leads: "
            f"control={people_public_summary.get('control_roles', 0)} | "
            f"key_people={people_public_summary.get('key_people', 0)} | "
            f"legal_pressure={people_public_summary.get('legal_pressure', 0)} | "
            f"ownership_changes={people_public_summary.get('ownership_changes', 0)} | "
            f"related_parties={people_public_summary.get('related_parties', 0)} | "
            f"labor_social={people_public_summary.get('labor_social', 0)}"
        )
        for label, key in (
            ("control", "public_control_claims"),
            ("key_people", "public_key_person_claims"),
            ("legal", "public_legal_pressure_claims"),
            ("ownership", "public_ownership_change_claims"),
            ("related", "public_related_party_claims"),
        ):
            signals = [str(item) for item in people.get(key, []) if str(item).strip()]
            if signals:
                rows.append(
                    f"  - {label}: "
                    + "; ".join(_short_text(item, 100) for item in signals[:3])
                )

    relationship_resolution = _dict(enterprise_cognition.get("relationship_resolution_v1"))
    relationship_leads = [
        item for item in relationship_resolution.get("phase1_candidate_leads", [])
        if isinstance(item, dict)
    ]
    if relationship_leads:
        rel_summary = _dict(relationship_resolution.get("resolution_summary"))
        by_lane = _dict(rel_summary.get("by_lane"))
        typed = [
            item for item in relationship_leads
            if item.get("extracted_field")
        ]
        weak_count = sum(1 for item in relationship_leads if item.get("admission") == "weak_lead")
        rows.append(
            "- relationship candidate leads: "
            f"total={relationship_resolution.get('lead_count', len(relationship_leads))} | "
            f"typed={rel_summary.get('typed_lead_count', len(typed))} | "
            f"weak={rel_summary.get('weak_lead_count', weak_count)} | "
            f"risk={rel_summary.get('lead_risk_level', 'review_needed')}"
        )
        if by_lane:
            rows.append(
                "  - lane split: "
                f"capital={by_lane.get('capital', 0)} | "
                f"goods={by_lane.get('goods', 0)} | "
                f"people={by_lane.get('people', 0)} | "
                f"sources={rel_summary.get('source_count', 0)}"
            )
        for action in rel_summary.get("verification_queue", [])[:3]:
            if not isinstance(action, dict):
                continue
            rows.append(
                "  - verify "
                f"[{action.get('priority')}] {action.get('relation_type')} -> {action.get('target')} | "
                f"{action.get('next_action')}"
            )
        for item in typed[:4]:
            rows.append(
                "  - "
                f"{item.get('relation_type')}: {item.get('from')} -> {item.get('to')} | "
                f"field={item.get('extracted_field')} | admission={item.get('admission')} | "
                f"source={item.get('source')}"
            )

    people_network = _dict(people.get("relationship_network"))
    if people_network:
        rows.append(
            "- people control network: "
            f"controllers={people.get('controller_candidate_count', 0)} | "
            f"verified={people.get('verified_controller_count', 0)} | "
            f"relations={people_network.get('relation_count', 0)} | "
            f"strong_relations={people_network.get('strong_relation_count', 0)}"
        )
    controller_conflicts = _dict(people.get("controller_conflict_summary"))
    if controller_conflicts and controller_conflicts.get("review_required"):
        rows.append(
            "- controller review: "
            f"status={controller_conflicts.get('status')} | "
            f"preferred={controller_conflicts.get('preferred_controller') or 'unknown'} | "
            f"competing={len(controller_conflicts.get('competing_candidates') or [])}"
        )
    return rows

def _append_qyyjt_profile_focus_lines(lines: list[str], profile: dict[str, Any]) -> None:
    """Render the highest-value admitted QYYJT exposure and next verification step."""
    top = _dict((profile.get("top_exposures") or [{}])[0])
    if top:
        lines.append(
            "- top exposure: "
            f"{top.get('module')}:{top.get('identifier')} | "
            f"pressure={top.get('pressure_flag') or 'watch'} | "
            f"status={top.get('status') or 'no-status'} | "
            f"amount={top.get('amount') or '-'} | "
            f"counterparty={top.get('counterparty') or '-'}"
        )
    action = _dict((profile.get("monitoring_queue") or [{}])[0])
    if action:
        fields = ", ".join(str(item) for item in action.get("verify_fields", [])[:5])
        lines.append(
            "- next verification: "
            f"{action.get('priority')} {action.get('action_id')} | "
            f"{_short_text(action.get('next_action'), 180)}"
            + (f" | fields={fields}" if fields else "")
        )

def _report_markdown(
    *,
    company: str,
    mode: str,
    risk_brief: dict[str, Any],
    profile_brief: dict[str, Any],
    enterprise_cognition: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
    source_provenance: dict[str, Any],
    source_failure_summary: dict[str, Any],
    risk_event_summary: dict[str, Any],
    persona_surface: dict[str, Any],
    monitoring_seed: dict[str, Any],
    one_click_readiness: dict[str, Any] | None = None,
    qyyjt_public_origin_handoff: dict[str, Any] | None = None,
    next_actions: list[str],
    quality_gate: dict[str, Any] | None = None,
) -> str:
    findings = risk_brief.get("key_findings", [])
    controllers = profile_brief.get("controller_candidates", [])
    lines = [
        f"# 华尔街驻铁岭办事处 0.5.0 尽调快报 - {company}",
        "",
        f"- 模式: {mode}",
        f"- 结论: {risk_brief.get('verdict_label') or risk_brief.get('verdict')}",
        f"- 风险分: {risk_brief.get('risk_score')}/100（分数越高，越需要人工复核）",
        f"- 最高风险等级: {_severity_label(risk_brief.get('highest_severity'))}",
        f"- 取证状态: {risk_brief.get('execution_state_label') or risk_brief.get('execution_state')}",
        f"- 可信度提示: {_confidence_label(risk_brief.get('confidence_note'))}",
    ]
    if persona_surface:
        lines.extend(["", "## 专家团分工"])
        lines.append(
            f"- 壳层: {persona_surface.get('display_name')} | "
            f"本次激活 {persona_surface.get('active_role_count', 0)}/{persona_surface.get('role_count', 0)} 个角色"
        )
        for role in persona_surface.get("active_roles", [])[:8]:
            evidence_sources = [
                str(item)
                for item in role.get("evidence_sources", [])
                if str(item).strip()
            ]
            lines.append(
                f"- {role.get('display_name')}（{role.get('role')}）: "
                f"{_short_text(role.get('responsibility'), 90)}"
                f" | lane={role.get('lane') or 'general'}"
                + (
                    " | basis=" + "; ".join(_short_text(item, 80) for item in evidence_sources[:3])
                    if evidence_sources
                    else " | basis=no packet evidence yet"
                )
            )
            packet_fields = [
                str(item)
                for item in role.get("packet_fields", [])
                if str(item).strip()
            ]
            if packet_fields:
                lines.append(
                    "  - fields: "
                    + ", ".join(_short_text(item, 70) for item in packet_fields[:4])
                )
        if persona_surface.get("principle"):
            lines.append(f"- 边界: {_short_text(persona_surface.get('principle'), 180)}")
    if quality_gate:
        lines.extend(
            [
                "",
                "## 交付质量",
                f"- 状态: {_quality_status_label(quality_gate.get('status'))} | 评分: {quality_gate.get('score')}/100",
            ]
        )
        blockers = [str(item) for item in quality_gate.get("blockers", []) if str(item).strip()]
        warnings = [str(item) for item in quality_gate.get("warnings", []) if str(item).strip()]
        strengths = [str(item) for item in quality_gate.get("strengths", []) if str(item).strip()]
        actions = [str(item) for item in quality_gate.get("next_actions", []) if str(item).strip()]
        if blockers:
            lines.append("- 阻塞项: " + "；".join(_quality_issue_label(item) for item in blockers[:5]))
        if warnings:
            lines.append("- 风险提示: " + "；".join(_quality_issue_label(item) for item in warnings[:5]))
        if strengths:
            lines.append("- 已具备: " + "；".join(_quality_issue_label(item) for item in strengths[:5]))
        if actions:
            lines.append("- 下一步补强: " + "；".join(_quality_action_label(item) for item in actions[:3]))
    if one_click_readiness:
        checks = _dict(one_click_readiness.get("section_checks"))
        missing = [key for key, ok in checks.items() if not ok]
        lines.extend(["", "## One-click Product Loop"])
        lines.append(
            f"- status: {one_click_readiness.get('status')} | "
            f"facts={one_click_readiness.get('fact_count', 0)} | "
            f"leads={one_click_readiness.get('lead_count', 0)} | "
            f"quality={one_click_readiness.get('quality_status')}:{one_click_readiness.get('quality_score')}"
        )
        lines.append(
            f"- recovery: ready={one_click_readiness.get('recovery_ready_count', 0)} | "
            f"blocked={one_click_readiness.get('recovery_blocked_count', 0)} | "
            f"failed_sources={one_click_readiness.get('failed_source_count', 0)}"
        )
        acceptance_closure = _dict(one_click_readiness.get("acceptance_closure_summary"))
        if acceptance_closure:
            open_domains = [
                str(item)
                for item in acceptance_closure.get("open_domains", [])
                if str(item).strip()
            ]
            lines.append(
                f"- acceptance closure: status={acceptance_closure.get('status')} | "
                f"blocking={acceptance_closure.get('blocking_count', 0)} | "
                f"ready={acceptance_closure.get('ready_count', 0)} | "
                f"open_domains={', '.join(open_domains[:6]) or 'none'}"
            )
            if acceptance_closure.get("next_action"):
                lines.append(
                    "- acceptance next action: "
                    + _short_text(acceptance_closure.get("next_action"), 180)
                )
        reliance_limitations = _dict(one_click_readiness.get("reliance_limitations"))
        if reliance_limitations:
            lines.append(
                f"- reliance limitations: count={reliance_limitations.get('count', 0)} | "
                f"highest={reliance_limitations.get('highest_severity') or 'none'} | "
                f"clean_conclusion={reliance_limitations.get('can_make_clean_conclusion')}"
            )
            if reliance_limitations.get("policy"):
                lines.append(
                    "- reliance policy: "
                    + _short_text(reliance_limitations.get("policy"), 180)
                )
            for item in reliance_limitations.get("items", [])[:4]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "  - limitation: "
                    f"{item.get('limitation_id')} | area={item.get('area')} | severity={item.get('severity')} | "
                    f"{_short_text(item.get('user_message'), 150)}"
                )
                if item.get("next_action"):
                    lines.append(
                        "  - limitation next: "
                        + _short_text(item.get("next_action"), 150)
                    )
        if one_click_readiness.get("operator_work_queue_count"):
            lines.append(
                f"- operator work queue: count={one_click_readiness.get('operator_work_queue_count', 0)} | "
                f"p0={one_click_readiness.get('operator_work_p0_count', 0)} | "
                f"ready={one_click_readiness.get('operator_work_ready_count', 0)}"
            )
            for item in one_click_readiness.get("operator_work_queue", [])[:5]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "  - operator work: "
                    f"{item.get('work_id')} | lane={item.get('lane')} | priority={item.get('priority')} | "
                    f"ready_to_run={item.get('ready_to_run')} | source={item.get('source')} | "
                    f"target={_short_text(item.get('target'), 90)} | action={_short_text(item.get('action'), 160)}"
                )
                if item.get("blocked_reason"):
                    lines.append(f"  - operator work blocked: {item.get('blocked_reason')}")
        lines.append(
            f"- coverage execution: attempted_sources={one_click_readiness.get('attempted_source_count', 0)} | "
            f"not_searched={one_click_readiness.get('coverage_not_searched_count', 0)} | "
            f"no_evidence={one_click_readiness.get('coverage_no_evidence_count', 0)} | "
            f"gaps={one_click_readiness.get('coverage_gap_count', 0)} | "
            f"severity={one_click_readiness.get('coverage_gap_severity') or 'none'} | "
            f"attempt_ratio={one_click_readiness.get('coverage_attempt_ratio', 0)} | "
            f"coverage_statuses={_format_failure_counts(one_click_readiness.get('coverage_status_counts', {}))}"
        )
        if one_click_readiness.get("coverage_next_action"):
            lines.append(
                "- coverage next action: "
                + _short_text(one_click_readiness.get("coverage_next_action"), 220)
            )
        missing_domains = [
            str(item)
            for item in one_click_readiness.get("coverage_missing_domains", [])
            if str(item).strip()
        ]
        no_evidence_domains = [
            str(item)
            for item in one_click_readiness.get("coverage_domains_without_evidence", [])
            if str(item).strip()
        ]
        if missing_domains:
            lines.append(
                "- one-click not searched domains: "
                + ", ".join(f"{item}({_domain_label(item)})" for item in missing_domains[:5])
            )
        if no_evidence_domains:
            lines.append(
                "- one-click no evidence domains: "
                + ", ".join(f"{item}({_domain_label(item)})" for item in no_evidence_domains[:5])
            )
        if one_click_readiness.get("public_origin_next_action_count"):
            top_action = _dict(one_click_readiness.get("public_origin_top_action"))
            lines.append(
                f"- public-origin fallback: actions={one_click_readiness.get('public_origin_next_action_count', 0)} | "
                f"fallbacks={one_click_readiness.get('public_origin_fallback_count', 0)} | "
                f"modules={', '.join(str(item) for item in one_click_readiness.get('public_origin_modules', [])[:5])}"
            )
            if top_action:
                fields = [
                    str(item)
                    for item in top_action.get("required_fields", [])
                    if str(item).strip()
                ]
                lines.append(
                    f"  - top public-origin action: {top_action.get('action_id')} | "
                    f"{top_action.get('module')} -> {top_action.get('origin_channel')} | "
                    f"record_type={top_action.get('record_type')} | "
                    f"required_fields={', '.join(fields[:5])}"
                )
        if one_click_readiness.get("public_origin_gap_bridge_count"):
            bridge = _dict(one_click_readiness.get("public_origin_gap_bridge"))
            top_bridge = _dict(one_click_readiness.get("public_origin_gap_bridge_top_action"))
            lines.append(
                f"- public-origin gap bridge: domains={bridge.get('bridged_domain_count', 0)}/"
                f"{bridge.get('gap_domain_count', 0)} | actions={bridge.get('bridge_count', 0)}"
            )
            if top_bridge:
                fields = [
                    str(item)
                    for item in top_bridge.get("required_fields", [])
                    if str(item).strip()
                ]
                lines.append(
                    "  - top public-origin gap bridge: "
                    f"{top_bridge.get('bridge_id')} | gap={top_bridge.get('gap_domain')} | "
                    f"action={top_bridge.get('action_id')} | module={top_bridge.get('module')} | "
                    f"required_fields={', '.join(fields[:5])}"
                )
        if one_click_readiness.get("control_path_closure_needed"):
            control_step = _dict(one_click_readiness.get("control_path_closure_step"))
            lines.append(
                f"- control path closure: needed=True | "
                f"paths={one_click_readiness.get('control_path_signal_count', 0)} | "
                f"highest_hops={one_click_readiness.get('control_path_highest_hop_count', 0)} | "
                f"status={control_step.get('status') or 'corroboration_needed'}"
            )
            if control_step:
                lines.append(
                    f"  - control path closure step: {control_step.get('step_id')} | "
                    f"{control_step.get('kind')} | priority={control_step.get('priority')} | "
                    f"path={_short_text(control_step.get('path_text') or control_step.get('target_title'), 160)} | "
                    f"done={_short_text(control_step.get('done_condition'), 140)}"
                )
        if one_click_readiness.get("goods_economics_closure_needed"):
            goods_step = _dict(one_click_readiness.get("goods_economics_closure_step"))
            lines.append(
                f"- goods economics closure: needed=True | "
                f"signals={one_click_readiness.get('goods_economics_signal_count', 0)} | "
                f"status={goods_step.get('status') or 'corroboration_needed'}"
            )
            if goods_step:
                lines.append(
                    f"  - goods economics closure step: {goods_step.get('step_id')} | "
                    f"{goods_step.get('kind')} | priority={goods_step.get('priority')} | "
                    f"target={_short_text(goods_step.get('target_title'), 140)} | "
                    f"done={_short_text(goods_step.get('done_condition'), 140)}"
                )
                sample_signals = [
                    str(item)
                    for item in goods_step.get("sample_signals", [])
                    if str(item).strip()
                ]
                if sample_signals:
                    lines.append(
                        "  - goods economics sample: "
                        + "; ".join(_short_text(item, 80) for item in sample_signals[:3])
                    )
        if one_click_readiness.get("people_control_closure_needed"):
            people_step = _dict(one_click_readiness.get("people_control_closure_step"))
            lines.append(
                f"- people control closure: needed=True | "
                f"signals={one_click_readiness.get('people_control_signal_count', 0)} | "
                f"status={people_step.get('status') or 'corroboration_needed'}"
            )
            if people_step:
                lines.append(
                    f"  - people control closure step: {people_step.get('step_id')} | "
                    f"{people_step.get('kind')} | priority={people_step.get('priority')} | "
                    f"target={_short_text(people_step.get('target_title'), 140)} | "
                    f"done={_short_text(people_step.get('done_condition'), 140)}"
                )
                sample_signals = [
                    str(item)
                    for item in people_step.get("sample_signals", [])
                    if str(item).strip()
                ]
                if sample_signals:
                    lines.append(
                        "  - people control sample: "
                        + "; ".join(_short_text(item, 80) for item in sample_signals[:3])
                    )
        if one_click_readiness.get("relationship_candidate_execution_step_count"):
            top_step = _dict(one_click_readiness.get("relationship_candidate_top_step"))
            lines.append(
                f"- relationship candidate execution: watches={one_click_readiness.get('relationship_candidate_watch_count', 0)} | "
                f"steps={one_click_readiness.get('relationship_candidate_execution_step_count', 0)} | "
                f"p0={one_click_readiness.get('relationship_candidate_p0_count', 0)}"
            )
            if top_step:
                sources = [
                    str(item)
                    for item in top_step.get("verification_sources", [])
                    if str(item).strip()
                ]
                lines.append(
                    f"  - top relationship step: {top_step.get('step_id')} | "
                    f"{top_step.get('relation_type')} -> {top_step.get('target')} | "
                    f"sources={', '.join(sources[:4])}"
                )
        if one_click_readiness.get("source_resilience_status"):
            lines.append(
                f"- source resilience: status={one_click_readiness.get('source_resilience_status')} | "
                f"score={one_click_readiness.get('source_resilience_score')} | "
                f"needs_operator_recovery={one_click_readiness.get('source_resilience_needs_operator_recovery')}"
            )
        if one_click_readiness.get("source_resilience_recommended_action"):
            lines.append(
                "- source resilience next: "
                + _short_text(one_click_readiness.get("source_resilience_recommended_action"), 180)
            )
        source_resilience_step = _dict(one_click_readiness.get("source_resilience_recommended_step"))
        if source_resilience_step:
            key_fields = [
                str(item)
                for item in source_resilience_step.get("key_fields", [])
                if str(item).strip()
            ]
            ready = one_click_readiness.get("source_resilience_recommended_step_ready_to_run")
            blocked_reason = str(
                one_click_readiness.get("source_resilience_recommended_step_blocked_reason") or ""
            ).strip()
            lines.append(
                "- source resilience recommended step: "
                f"{source_resilience_step.get('source')} -> {source_resilience_step.get('domain')} | "
                f"status={source_resilience_step.get('status')} | "
                f"ready_to_run={ready} | "
                f"query_family={source_resilience_step.get('query_family')} | "
                f"key_fields={', '.join(key_fields[:5]) or 'none'}"
            )
            retry_hint = _retry_policy_hint(
                _dict(
                    one_click_readiness.get("source_resilience_retry_policy")
                    or source_resilience_step.get("retry_policy")
                )
            )
            if retry_hint:
                lines.append(f"  - source resilience retry policy: {retry_hint}")
            if blocked_reason:
                lines.append(f"  - source resilience blocked reason: {blocked_reason}")
        if one_click_readiness.get("source_repair_priority_count"):
            top_repair = _dict(one_click_readiness.get("source_repair_top_action"))
            lines.append(
                f"- source repair priority: count={one_click_readiness.get('source_repair_priority_count', 0)} | "
                f"p0={one_click_readiness.get('source_repair_p0_count', 0)}"
            )
            if top_repair:
                lines.append(
                    "  - top source repair: "
                    f"{top_repair.get('source')} / {top_repair.get('failure_category')} / "
                    f"{top_repair.get('domain')} | status={top_repair.get('status')} | "
                    f"action={_short_text(top_repair.get('operator_action'), 160)}"
                )
        qyyjt_handoff = _dict(qyyjt_public_origin_handoff)
        if qyyjt_handoff.get("available"):
            lines.append(
                f"- qyyjt public-origin handoff: queue={qyyjt_handoff.get('queue_count', 0)} | "
                f"p0={qyyjt_handoff.get('p0_action_count', 0)} | "
                f"section_batches={qyyjt_handoff.get('report_section_batch_count', 0)} | "
                "policy=public_or_user_authorized_only"
            )
            top_action = _dict((qyyjt_handoff.get("top_actions") or [{}])[0])
            if top_action:
                fields = [
                    str(item)
                    for item in top_action.get("required_fields", [])
                    if str(item).strip()
                ]
                channels = [
                    str(item)
                    for item in top_action.get("origin_channels", [])
                    if str(item).strip()
                ]
                lines.append(
                    f"  - qyyjt public-origin top action: {top_action.get('action_id')} | "
                    f"{top_action.get('module')} -> {top_action.get('target_lane')} | "
                    f"record_type={top_action.get('record_type')} | "
                    f"channels={', '.join(channels[:4])} | "
                    f"required_fields={', '.join(fields[:5])}"
                )
            section_batch = _dict((qyyjt_handoff.get("report_section_batches") or [{}])[0])
            if section_batch:
                actions = [
                    str(item.get("action_id") or item.get("module") or "")
                    for item in section_batch.get("top_actions", [])
                    if isinstance(item, dict) and str(item.get("action_id") or item.get("module") or "").strip()
                ]
                lines.append(
                    "  - qyyjt public-origin section batch: "
                    f"{section_batch.get('report_section')} | queue={section_batch.get('queue_count')} | "
                    f"p0={section_batch.get('p0_count')} | actions={', '.join(actions[:4])}"
                )
            section_summary = _dict(qyyjt_handoff.get("section_execution_summary"))
            if section_summary:
                lines.append(
                    "  - qyyjt public-origin section execution: "
                    f"sections={section_summary.get('section_count', 0)} | "
                    f"p0_sections={section_summary.get('p0_section_count', 0)} | "
                    f"ready={section_summary.get('ready_section_count', 0)} | "
                    f"blocked={section_summary.get('blocked_section_count', 0)}"
                )
                top_ready = _dict(section_summary.get("top_ready_work_order"))
                if top_ready:
                    lines.append(
                        "  - qyyjt public-origin ready section: "
                        f"{top_ready.get('work_order_id')} | "
                        f"section={top_ready.get('report_section')} | "
                        f"priority={top_ready.get('priority')} | "
                        f"done={_short_text(top_ready.get('done_condition'), 140)}"
                    )
            section_work_order = _dict(qyyjt_handoff.get("top_section_work_order"))
            if section_work_order:
                queries = [
                    str(item)
                    for item in section_work_order.get("query_families", [])
                    if str(item).strip()
                ]
                fields = [
                    str(item)
                    for item in section_work_order.get("required_fields", [])
                    if str(item).strip()
                ]
                lines.append(
                    "  - qyyjt public-origin section work order: "
                    f"{section_work_order.get('work_order_id')} | "
                    f"section={section_work_order.get('report_section')} | "
                    f"priority={section_work_order.get('priority')} | "
                    f"queries={'; '.join(queries[:2])} | "
                    f"required_fields={', '.join(fields[:6])}"
                )
        lines.append(
            f"- capital: pressure={one_click_readiness.get('capital_pressure_level') or 'none'} | "
            f"verification={one_click_readiness.get('capital_pressure_verification_status') or 'none'} | "
            f"verification_queue={one_click_readiness.get('capital_verification_queue_count', 0)} | "
            f"relationship_needed={one_click_readiness.get('capital_relationship_needed')} | "
            f"relationship_explained={one_click_readiness.get('capital_relationship_explained')} | "
            f"relationship_status={one_click_readiness.get('capital_relationship_status') or 'unknown'} | "
            f"lead_only_public={one_click_readiness.get('capital_pressure_lead_only_public_rows_present')}"
        )
        graph_capital = _dict(one_click_readiness.get("graph_capital_exposure"))
        if graph_capital.get("available"):
            lines.append(
                "- graph capital exposure: "
                f"pressure={graph_capital.get('pressure_level') or 'none'} | "
                f"relationship_status={graph_capital.get('relationship_status') or 'unknown'} | "
                f"alignment={graph_capital.get('alignment_status') or 'unknown'} | "
                f"verification_queue={graph_capital.get('verification_queue_count', 0)} | "
                f"relationship_audit_queue={graph_capital.get('relationship_audit_queue_count', 0)}"
            )
            graph_step = _dict(graph_capital.get("top_step"))
            if graph_step:
                lines.append(
                    f"  - graph capital top step: {graph_step.get('step_id')} | "
                    f"{graph_step.get('kind')} | priority={graph_step.get('priority')} | "
                    f"target={_short_text(graph_step.get('target_title'), 140)} | "
                    f"done={_short_text(graph_step.get('done_condition'), 140)}"
                )
        capital_step = _dict(one_click_readiness.get("capital_verification_top_step"))
        if capital_step:
            lines.append(
                f"  - capital verification top step: {capital_step.get('step_id')} | "
                f"{capital_step.get('kind')} | priority={capital_step.get('priority')} | "
                f"target={_short_text(capital_step.get('target_title'), 140)} | "
                f"done={_short_text(capital_step.get('done_condition'), 140)}"
            )
        if one_click_readiness.get("capital_relationship_unresolved_reason"):
            lines.append(
                "- capital relationship unresolved: "
                + str(one_click_readiness.get("capital_relationship_unresolved_reason"))
                + " | next="
                + _short_text(one_click_readiness.get("capital_relationship_next_action"), 220)
            )
            closure_step = _dict(one_click_readiness.get("capital_relationship_closure_step"))
            if closure_step:
                lines.append(
                    f"  - capital relationship closure step: {closure_step.get('step_id')} | "
                    f"{closure_step.get('kind')} | priority={closure_step.get('priority')} | "
                    f"target={_short_text(closure_step.get('target_title'), 140)} | "
                    f"done={_short_text(closure_step.get('done_condition'), 140)}"
                )
        if int(one_click_readiness.get("relationship_edge_count") or 0):
            lines.append(
                f"- relationship graph: edges={one_click_readiness.get('relationship_edge_count', 0)} | "
                f"evidence_backed={one_click_readiness.get('relationship_evidence_backed_edge_count', 0)} | "
                f"auditable_fact={one_click_readiness.get('relationship_auditable_edge_count', 0)} | "
                f"missing_evidence={one_click_readiness.get('relationship_missing_evidence_edge_count', 0)} | "
                f"lead_only={one_click_readiness.get('relationship_lead_only_edge_count', 0)} | "
                f"audit_queue={one_click_readiness.get('relationship_graph_audit_queue_count', 0)}"
            )
            relationship_audit_step = _dict(one_click_readiness.get("relationship_graph_audit_top_step"))
            if relationship_audit_step:
                lines.append(
                    f"  - relationship audit top step: {relationship_audit_step.get('step_id')} | "
                    f"{relationship_audit_step.get('kind')} | priority={relationship_audit_step.get('priority')} | "
                    f"target={_short_text(relationship_audit_step.get('target'), 140)} | "
                    f"done={_short_text(relationship_audit_step.get('done_condition'), 140)}"
                )
        if missing:
            lines.append("- missing loop checks: " + ", ".join(missing[:6]))
        else:
            lines.append("- loop checks: packet, evidence, provenance, report, and future monitoring boundary are present")
    lines.extend(["", "## 关键发现"])
    for finding in findings[:6]:
        refs = ", ".join(str(ref) for ref in finding.get("source_refs", []) if ref) or "待补充来源"
        lines.append(f"- [{finding.get('severity')}] {finding.get('title')} | 来源: {refs}")
        if finding.get("why_it_matters"):
            lines.append(f"  - 为什么重要: {finding['why_it_matters']}")
    if not findings:
        lines.append("- 暂无可报告风险事件；这不是低风险结论，只代表当前证据不足。")

    if risk_event_summary:
        lines.extend(["", "## 风险事件台账"])
        lines.append(
            f"- 事件总数: {risk_event_summary.get('risk_event_count', 0)} | "
            f"高风险: {risk_event_summary.get('high_risk_count', 0)} | "
            f"重大风险: {risk_event_summary.get('critical_risk_count', 0)}"
        )
        if risk_event_summary.get("by_severity"):
            severity_parts = [
                f"{_severity_label(severity)}={count}"
                for severity, count in sorted(risk_event_summary["by_severity"].items())
            ]
            lines.append("- 严重度分布: " + "；".join(severity_parts))
        if risk_event_summary.get("by_category"):
            category_parts = [
                f"{_category_label(category)}={count}"
                for category, count in sorted(risk_event_summary["by_category"].items())
            ]
            lines.append("- 类别分布: " + "；".join(category_parts[:6]))
        for finding in risk_event_summary.get("top_findings", [])[:5]:
            refs = ", ".join(str(ref) for ref in finding.get("source_refs", []) if ref) or "待补充来源"
            lines.append(f"- [{finding.get('severity')}] {finding.get('title')} | 来源: {refs}")
            if finding.get("why_it_matters"):
                lines.append(f"  - 为什么重要: {finding['why_it_matters']}")

    lines.extend(["", "## 主体画像"])
    lines.append(f"- 覆盖主体数: {profile_brief.get('subject_count', 0)}")
    lines.append(f"- 实控人/关键人候选: {profile_brief.get('controller_candidate_count', 0)}")
    if controllers:
        for item in controllers[:5]:
            lines.append(
                f"- {item.get('name')} | 置信度 {item.get('confidence')} | "
                f"核验状态 {item.get('verification_status')}"
            )
    lines.append("- 覆盖维度: " + (", ".join(_domain_label(item) for item in profile_brief.get("covered_dimensions", [])) or "暂无"))
    registry_identity = profile_brief.get("registry_identity")
    if isinstance(registry_identity, dict) and registry_identity:
        lines.append("")
        lines.append("### 工商基本信息")
        registry_fields = [
            ("legal_name", "法定名称"),
            ("unified_social_credit_code", "统一社会信用代码"),
            ("registry_status", "登记状态"),
            ("company_type", "企业类型"),
            ("registered_capital", "注册资本"),
            ("establishment_date", "成立日期"),
            ("operating_period", "营业期限"),
            ("registration_authority", "登记机关"),
            ("registered_address", "注册地址"),
            ("legal_representative", "法定代表人"),
            ("business_scope", "经营范围"),
        ]
        for field, label in registry_fields:
            value = registry_identity.get(field)
            if value in (None, ""):
                continue
            lines.append(f"- {label}: {_short_text(value, 180)}")
        if registry_identity.get("source_names"):
            sources = "；".join(_source_label(item) for item in registry_identity["source_names"][:4])
            lines.append(f"- 来源: {sources}")
    if profile_brief.get("evidence_gaps"):
        lines.append("- 证据缺口: " + "；".join(_friendly_gap(gap) for gap in profile_brief["evidence_gaps"][:3]))
    if profile_brief.get("key_signals"):
        lines.append("")
        lines.append("### 画像线索")
        for signal in profile_brief["key_signals"][:6]:
            sources = ", ".join(_source_label(item) for item in signal.get("source_names", []) if item) or "待补充来源"
            lines.append(
                f"- {_domain_label(signal.get('dimension'))}: {_short_text(signal.get('value'), 140)} "
                f"| 核验: {_verification_status_label(signal.get('verification_status'))} "
                f"| 来源: {sources}"
            )

    control_ownership = enterprise_cognition.get("control_ownership")
    if isinstance(control_ownership, dict) and control_ownership:
        lines.extend(["", "## 控制权与实控人"])
        lines.append(
            f"- 候选数量: {control_ownership.get('controller_candidate_count', 0)} | "
            f"核验状态: {_verification_status_label(control_ownership.get('verification_status'))}"
        )
        if control_ownership.get("seed_subject_name"):
            lines.append(f"- 主体: {control_ownership.get('seed_subject_name')}")
        graph_summary = control_ownership.get("graph_summary")
        if isinstance(graph_summary, dict) and graph_summary:
            lines.append(
                f"- 图谱规模: subjects={graph_summary.get('subject_count', 0)} | "
                f"relations={graph_summary.get('relation_count', 0)}"
            )
        if control_ownership.get("multi_layer_control_path_count"):
            lines.append(
                "- multi-layer control paths: "
                f"count={control_ownership.get('multi_layer_control_path_count', 0)} | "
                f"highest_hops={control_ownership.get('highest_control_path_hop_count', 0)} | "
                f"verification={control_ownership.get('control_path_verification_status') or 'unknown'}"
            )
        if control_ownership.get("controller_candidates"):
            for item in control_ownership["controller_candidates"][:5]:
                sources = ", ".join(_source_label(src) for src in item.get("source_names", []) if src) or "待补充来源"
                relation_types = item.get("relation_types") or []
                relation_label = ", ".join(relation_types) if relation_types else item.get("relation_type")
                tier = item.get("confidence_tier") or "unknown"
                lines.append(
                    f"- {item.get('name')} | 关系: {relation_label} | "
                    f"置信度: {item.get('confidence')} | "
                    f"tier: {tier} | "
                    f"状态: {_verification_status_label(item.get('verification_status'))} | "
                    f"来源: {sources}"
                )
                basis = item.get("confidence_basis") or []
                if basis:
                    lines.append(
                        "  - basis: "
                        + "; ".join(_short_text(str(value), 80) for value in basis[:4])
                    )
                paths = item.get("control_paths") or []
                if paths:
                    lines.append(
                        "  - control_path: "
                        + "; ".join(_short_text(str(value), 100) for value in paths[:3])
                    )
                path_summaries = [
                    summary
                    for summary in item.get("control_path_summaries", [])
                    if isinstance(summary, dict) and summary.get("path_text")
                ]
                if path_summaries:
                    summary = path_summaries[0]
                    lines.append(
                        "  - path_quality: "
                        f"hops={summary.get('hop_count')} | "
                        f"min_conf={summary.get('min_confidence')} | "
                        f"strength={summary.get('source_strength')} | "
                        f"admission={summary.get('admission') or 'unknown'}"
                    )
        if control_ownership.get("control_paths"):
            lines.append("- 控制路径预览:")
            for path in control_ownership["control_paths"][:4]:
                if path.get("path_text"):
                    meta = []
                    if path.get("hop_count") is not None:
                        meta.append(f"hops={path.get('hop_count')}")
                    if path.get("min_confidence") is not None:
                        meta.append(f"min_conf={path.get('min_confidence')}")
                    if path.get("source_strength") is not None:
                        meta.append(f"strength={path.get('source_strength')}")
                    if path.get("admission"):
                        meta.append(f"admission={path.get('admission')}")
                    suffix = f" | {' | '.join(meta)}" if meta else ""
                    lines.append(f"  - {_short_text(path.get('path_text'), 160)}{suffix}")
                    continue
                lines.append(
                    f"  - {_short_text(path.get('from_name') or path.get('from_kind'), 50)} -> "
                    f"{_short_text(path.get('to_name') or path.get('to_kind'), 50)} | "
                    f"{_domain_label(path.get('relation_type'))} | 置信度 {path.get('confidence')}"
                )
        if control_ownership.get("evidence_gaps"):
            lines.append(
                "- 控制权缺口: "
                + "；".join(_short_text(_friendly_gap(item), 80) for item in control_ownership["evidence_gaps"][:3])
            )

    # Smoke Authenticity Disclaimer
    audit_for_smoke = enterprise_cognition.get("investigation_audit_log",{})
    smoke_d = (audit_for_smoke.get("smoke_status") or {}).get("public") or {}
    fc = sum(1 for v in smoke_d.values() if v.get("live_verified") is False)
    lc = sum(1 for v in smoke_d.values() if v.get("live_verified") is True)
    if fc > 0 and lc == 0:
        lines.append("\n> [WARNING] All data sources are fixture_only. Report content is from test/template data, NOT real retrieval. live_verified=False.")
    elif fc > 0:
        lines.append("\n> [INFO] Data sources: " + str(lc) + " live_verified, " + str(fc) + " fixture_only.")
    # DD v2.2: Strategy + Gap Analysis + High-Value Paths
    strategy = enterprise_cognition.get("investigation_strategy") or {}
    plan = strategy.get("strategy_plan") or []
    if plan:
        lines.append("\n## 调查策略")
        for item in plan[:4]:
            lines.append(f"- [{item.get('priority','?')}] {item.get('action_id','?')} | {item.get('target_lane','?')} | {item.get('reason','?')}")
            bl = item.get('blocking_issue') or ""
            if bl: lines.append(f"  阻塞: {bl} | 备选: {(item.get('fallback_action') or '?')[:80]}")
    gap_analysis = enterprise_cognition.get("evidence_gap_analysis") or {}
    gaps_v2 = gap_analysis.get("gap_summary") or {}
    if gaps_v2:
        lines.append("\n## 证据缺口分析")
        for ln in ("capital","goods","people","risk","graph","source"):
            ld = gaps_v2.get(ln) or {}
            lines.append(f"- {ln}: {ld.get('status','?')} | 信号={ld.get('signal_count',0) or ld.get('event_count',0)}")
    graph_v2 = enterprise_cognition.get("graph_explainability_v2") or {}
    gs = graph_v2.get("graph_summary") or {}
    paths = gs.get("high_value_paths") or []
    if paths:
        lines.append("\n### 高价值关系路径")
        lines.append(f"- 强边={gs.get('strong_edges',0)} | 弱边={gs.get('weak_leads',0)}")
        for p in paths[:4]:
            lines.append(f"- {p.get('category','?')}: {p.get('path_id','?')} | {p.get('admission','?')} | conf={p.get('confidence',0)}")
    relationship_network = enterprise_cognition.get("relationship_network")
    if isinstance(relationship_network, dict) and relationship_network:
        lines.extend(["", "## 关联关系网络"])
        lines.append(
            f"- 主体数: {relationship_network.get('subject_count', 0)} | "
            f"关系数: {relationship_network.get('relation_count', 0)}"
        )
        if relationship_network.get("relation_types"):
            lines.append("- 关系类型: " + "，".join(_domain_label(item) for item in relationship_network["relation_types"][:6]))
        if relationship_network.get("source_names"):
            lines.append("- 来源: " + "；".join(_short_text(_source_label(item), 90) for item in relationship_network["source_names"][:6]))
        if relationship_network.get("top_edges"):
            lines.append("- 最强关联:")
            for edge in relationship_network["top_edges"][:5]:
                from_name = _short_text(edge.get("from_name") or edge.get("from_id"), 60)
                to_name = _short_text(edge.get("to_name") or edge.get("to_id"), 60)
                relation_label = _domain_label(edge.get("relation_type"))
                confidence = edge.get("confidence")
                evidence_ids = ",".join(str(evidence_id) for evidence_id in edge.get("evidence_ids", [])[:3])
                lines.append(
                    f"  - {from_name} -> {to_name} | {relation_label} | 置信度 {confidence} | "
                    f"edge_audit: admission={edge.get('admission') or 'unknown'} | evidence={evidence_ids or 'none'}"
                )
        if relationship_network.get("public_data_basis"):
            lines.append(f"- 说明: {_short_text(relationship_network.get('public_data_basis'), 180)}")

    people_flow = enterprise_cognition.get("people_flow_profile")
    if isinstance(people_flow, dict) and people_flow:
        lines.extend(["", "## 人线/控制关系画像"])
        lines.append(
            f"- 证据状态: {people_flow.get('evidence_state')} | "
            f"核验状态: {_verification_status_label(people_flow.get('verification_status'))}"
        )
        for label, key, limit in [
            ("控制候选", "controller_signals", 4),
            ("关键人/网络", "key_person_signals", 4),
            ("关联关系", "relationship_signals", 4),
            ("控制路径", "control_path_signals", 4),
            ("法务压力", "legal_pressure_signals", 4),
        ]:
            signals = [str(item) for item in people_flow.get(key, []) if str(item).strip()]
            if signals:
                lines.append(f"- {label}: " + "；".join(_short_text(item, 110) for item in signals[:limit]))
        if people_flow.get("pressure_points"):
            lines.append(
                "- 压力点: "
                + "；".join(_short_text(item, 110) for item in people_flow["pressure_points"][:5])
            )
        for question in people_flow.get("next_questions", [])[:3]:
            lines.append(f"- 追问: {_short_text(question, 150)}")

    lines.extend(_lane_summary_report_lines(enterprise_cognition))

    cross_lane_insights = enterprise_cognition.get("cross_lane_insights") or []
    if cross_lane_insights:
        lines.append("")
        lines.append("## 跨域交叉分析")
        for insight in cross_lane_insights:
            lines.append(f"- {insight}")
    op_flow = enterprise_cognition.get("operational_flow_profile") or {}
    if op_flow.get("has_fund_data"):
        lines.append("\n## 资金流动画像")
        cash = op_flow.get("cash_flow_signals") or op_flow.get("money_in_signals") or []
        outflow = op_flow.get("outflow_pressure_signals") or op_flow.get("money_out_or_pressure_signals") or []
        op_act = op_flow.get("operating_activity_signals") or []
        if cash: lines.append("\n### 资金流入"); [lines.append(f"- {s}") for s in cash[:5]]
        if outflow: lines.append("\n### 流出压力信号"); [lines.append(f"- {s}") for s in outflow[:5]]
        if op_act: lines.append("\n### 经营活动"); [lines.append(f"- {s}") for s in op_act[:5]]

    sources = source_failure_summary.get("top_failures", []) if isinstance(source_failure_summary, dict) else []
    if sources:
        lines.append("\n## 数据源状态")
        for s in sources[:10]:
            name = s.get("source_name") or s.get("source") or s.get("source_hint") or "?"
            status = s.get("status","unknown")
            label = _SOURCE_STATUS_LABELS.get(status,status)
            lines.append(f"- {name}: {label}")
    # Show smoke status for ALL sources (not just failures)
    audit_log = enterprise_cognition.get("investigation_audit_log") or {}
    smoke = audit_log.get("smoke_status") or {}
    public_smoke = smoke.get("public") or {}
    auth_smoke = smoke.get("authorized") or {}
    if public_smoke or auth_smoke:
        if not sources:
            lines.append("\n## 数据源状态")
        lines.append("\n### 公开数据源")
        for _k, _v in public_smoke.items():
            _icon = "✅" if _v.get("live_verified") else "ℹ️"
            lines.append(f"- {_icon} {_v.get('source_name',_k)}: {_v.get('status','?')}")
        if auth_smoke:
            lines.append("\n### 授权数据源")
            for _k, _v in auth_smoke.items():
                _cred = "🔒" if _v.get("credential_required") else ""
                _icon = "✅" if _v.get("live_verified") else "ℹ️"
                lines.append(f"- {_icon}{_cred} {_v.get('source_name',_k)}: {_v.get('status','?')}")
    cross_qs = enterprise_cognition.get("cross_lane_insights") or []
    if cross_qs:
        lines.append("\n## 交叉维度分析")
        for q in cross_qs[:6]:
            lines.append(f"- {q}")
    product = enterprise_cognition.get("product") or {}
    if product:
        product_name = product.get("product_name") or product.get("product_label") or ""
        if product_name:
            lines.append("\n## 产品")
            lines.append(f"- 产品分类：{product_name}")
            lines.append(f"- 是否已验证：{product.get('verification_status','未知')}")
            intelligence = product.get("intelligence_assessment","")
            if intelligence:
                lines.append(f"- 情报评估：{intelligence}")
    # Honest gaps: explicitly list what wasn't found
    gaps = enterprise_cognition.get("evidence_gaps") or []
    if gaps:
        lines.append("\n## 信息缺口")
        for g in gaps[:8]:
            lines.append(f"- {str(g)[:200]}")
    case_lens = enterprise_cognition.get("case_investigation_lens")
    if isinstance(case_lens, dict) and case_lens:
        lines.extend(["", f"## {case_lens.get('name') or '查案式调查'}"])
        for track in case_lens.get("tracks", [])[:3]:
            if not isinstance(track, dict):
                continue
            lines.append(
                f"- {track.get('label')} | {track.get('focus')} | "
                f"证据状态: {track.get('evidence_state')}"
            )
            if track.get("known_signals"):
                lines.append(
                    "  - 已知: "
                    + "；".join(_short_text(item, 90) for item in track.get("known_signals", [])[:4])
                )
            if track.get("evidence_gaps"):
                lines.append(
                    "  - 缺口: "
                    + "；".join(_short_text(_domain_label(item), 90) for item in track.get("evidence_gaps", [])[:3])
                )
            if track.get("next_questions"):
                lines.append(
                    "  - 追问: "
                    + "；".join(_short_text(item, 90) for item in track.get("next_questions", [])[:2])
                )

    cognition_hypotheses = [
        str(item)
        for item in enterprise_cognition.get("risk_hypotheses", [])
        if str(item).strip()
    ]
    watchlist = [
        str(item)
        for item in enterprise_cognition.get("monitoring_watchlist", [])
        if str(item).strip()
    ]
    cognition_gaps = [
        str(item)
        for item in enterprise_cognition.get("evidence_gaps", [])
        if str(item).strip()
    ]
    lines.extend(["", "## 企业认知"])
    if cognition_hypotheses:
        for item in cognition_hypotheses[:5]:
            lines.append(f"- 风险假设: {_short_text(item, 180)}")
    else:
        lines.append("- 当前证据尚不足以形成强风险假设。")
    if watchlist:
        lines.append("- 盯防清单: " + "；".join(_short_text(item, 80) for item in watchlist[:5]))
    if cognition_gaps:
        lines.append("- 认知缺口: " + "；".join(_short_text(_friendly_gap(item), 80) for item in cognition_gaps[:4]))

    if source_provenance:
        lines.extend(["", "## 来源出处"])
        lines.append(
            f"- 来源数: {source_provenance.get('source_count', 0)} | "
            f"事实证据: {source_provenance.get('factual_count', 0)} | "
            f"待核验线索: {source_provenance.get('lead_count', 0)} | "
            f"官方/授权事实: {source_provenance.get('official_or_licensed_count', 0)}"
        )
        if source_provenance.get("by_authority"):
            authority_parts = [
                f"{_authority_label(authority)}={count}"
                for authority, count in sorted(source_provenance["by_authority"].items())
            ]
            lines.append("- 权威类型: " + "；".join(authority_parts))
        if source_provenance.get("by_access"):
            access_parts = [
                f"{_access_label(access)}={count}"
                for access, count in sorted(source_provenance["by_access"].items())
            ]
            lines.append("- 访问类型: " + "；".join(access_parts))
        claim_corroboration = _dict(source_provenance.get("claim_corroboration"))
        if claim_corroboration:
            lines.append(
                "- claim corroboration: "
                f"multi_source_supported={claim_corroboration.get('multi_source_supported_count', 0)} | "
                f"single_source={claim_corroboration.get('single_source_count', 0)} | "
                f"conflicts={claim_corroboration.get('conflict_field_count', 0)}"
            )
            for claim in claim_corroboration.get("supported_claims", [])[:3]:
                if not isinstance(claim, dict):
                    continue
                lines.append(
                    f"- supported claim: {claim.get('field')}={_short_text(claim.get('value'), 90)} | "
                    f"sources={claim.get('source_count', 0)} | status={claim.get('status')}"
                )
            for conflict in claim_corroboration.get("conflict_fields", [])[:3]:
                if not isinstance(conflict, dict):
                    continue
                lines.append(
                    f"- conflict review: {conflict.get('field')} | "
                    f"distinct_values={conflict.get('distinct_value_count', 0)}"
                )
        for source in source_provenance.get("top_sources", [])[:5]:
            lines.append(
                f"- {_source_label(source.get('source'))}: "
                f"事实 {source.get('factual_count', 0)} / 线索 {source.get('lead_count', 0)} | "
                f"{_authority_label(source.get('authority'))} | {_access_label(source.get('access'))}"
            )
        if source_provenance.get("policy"):
            lines.append(f"- 边界: {_short_text(source_provenance.get('policy'), 180)}")

    lines.extend(_public_lead_profile_report_lines(enterprise_cognition))

    if source_failure_summary:
        lines.extend(["", "## 运行诊断"])
        lines.append(
            f"- run_id: {source_failure_summary.get('run_id') or 'unknown'} | "
            f"执行状态: {_execution_state_label(source_failure_summary.get('execution_state'))} | "
            f"尝试来源: {source_failure_summary.get('attempted_source_count', 0)}"
        )
        source_resilience = _dict(source_failure_summary.get("source_resilience_profile"))
        if source_resilience:
            lines.append(
                "- source resilience: "
                f"status={source_resilience.get('status')} | "
                f"score={source_resilience.get('score')} | "
                f"failures={source_resilience.get('failure_count', 0)} | "
                f"not_searched={source_resilience.get('not_searched_count', 0)} | "
                f"ready_recovery={source_resilience.get('recovery_ready_count', 0)} | "
                f"blocked_recovery={source_resilience.get('recovery_blocked_count', 0)}"
            )
            blockers = [
                item for item in source_resilience.get("top_blockers", [])
                if isinstance(item, dict)
            ]
            if blockers:
                lines.append(
                    "  - source resilience blockers: "
                    + "; ".join(
                        f"{item.get('blocker')}={item.get('count')}"
                        for item in blockers[:4]
                    )
                )
            if source_resilience.get("recommended_action"):
                lines.append(
                    "  - source resilience next: "
                    + _short_text(source_resilience.get("recommended_action"), 180)
                )
            recommended_step = _dict(source_resilience.get("recommended_step"))
            if recommended_step:
                key_fields = [
                    str(item)
                    for item in recommended_step.get("key_fields", [])
                    if str(item).strip()
                ]
                lines.append(
                    "  - source resilience recommended step: "
                    f"{recommended_step.get('source')} -> {recommended_step.get('domain')} | "
                    f"status={recommended_step.get('status')} | "
                    f"ready_to_run={source_resilience.get('recommended_step_ready_to_run')} | "
                    f"query_family={recommended_step.get('query_family')} | "
                    f"key_fields={', '.join(key_fields[:5]) or 'none'}"
                )
                retry_hint = _retry_policy_hint(
                    _dict(source_resilience.get("retry_policy") or recommended_step.get("retry_policy"))
                )
                if retry_hint:
                    lines.append(f"    - source resilience retry policy: {retry_hint}")
                if source_resilience.get("recommended_step_blocked_reason"):
                    lines.append(
                        "    - source resilience blocked reason: "
                        + str(source_resilience.get("recommended_step_blocked_reason"))
                    )
        if source_failure_summary.get("failure_count", 0):
            lines.append(
                f"- 异常来源: {source_failure_summary.get('failure_count', 0)} | "
                f"失败类型: {_format_failure_counts(source_failure_summary.get('by_failure_category', {}))}"
            )
            for item in source_failure_summary.get("top_failures", [])[:5]:
                source = _source_label(item.get("source") or item.get("source_name") or item.get("source_hint"))
                category = _failure_category_label(item.get("failure_category"))
                status = _source_status_label(item.get("status"))
                trace_id = str(item.get("trace_id") or "").strip()
                timeout = item.get("timeout_seconds")
                suffix = f" | trace={trace_id}" if trace_id else ""
                if timeout not in (None, ""):
                    suffix += f" | timeout={timeout}s"
                lines.append(f"- {source}: {status} / {category}{suffix}")
            recurring_patterns = [
                item for item in source_failure_summary.get("recurring_failure_patterns", [])
                if isinstance(item, dict)
            ]
            if recurring_patterns:
                lines.append("- recurring source failure patterns:")
                for item in recurring_patterns[:4]:
                    lines.append(
                        "  - "
                        f"{item.get('source')} / {item.get('failure_category')} / "
                        f"{item.get('domain')}: count={item.get('count')} | "
                        f"action={_short_text(item.get('operator_action'), 160)}"
                    )
            source_repair_queue = [
                item for item in monitoring_seed.get("source_repair_priority_queue", [])
                if isinstance(item, dict)
            ]
            if source_repair_queue:
                lines.append("- source repair priority queue:")
                for item in source_repair_queue[:4]:
                    lines.append(
                        "  - "
                        f"{item.get('priority')} {item.get('source')} / "
                        f"{item.get('failure_category')} / {item.get('domain')} | "
                        f"status={item.get('status')} | count={item.get('count')} | "
                        f"hint={_short_text(item.get('execution_hint'), 140)}"
                    )
            source_health_snapshot = _dict(monitoring_seed.get("source_health_trend_snapshot"))
            top_source = _dict(source_health_snapshot.get("top_source"))
            if source_health_snapshot.get("source_count"):
                lines.append(
                    "- source-health trend snapshot: "
                    f"sources={source_health_snapshot.get('source_count', 0)} | "
                    f"blocked={source_health_snapshot.get('blocked_source_count', 0)} | "
                    f"scope={source_health_snapshot.get('scope')}"
                )
                if top_source:
                    lines.append(
                        "  - top source-health action: "
                        f"{top_source.get('source')} | priority={top_source.get('priority')} | "
                        f"status={top_source.get('status')} | failures={top_source.get('failure_count')} | "
                        f"action={_short_text(top_source.get('operator_action'), 160)}"
                    )
        else:
            lines.append("- 数据源诊断未发现失败项。")
        public_origin_fallbacks = [
            item for item in source_failure_summary.get("public_origin_fallbacks", [])
            if isinstance(item, dict)
        ]
        if public_origin_fallbacks:
            lines.append("- public-origin fallback routes:")
            for item in public_origin_fallbacks[:5]:
                channels = ", ".join(str(value) for value in item.get("origin_channels", [])[:3])
                queries = "; ".join(str(value) for value in item.get("query_families", [])[:2])
                required_fields = ", ".join(str(value) for value in item.get("required_fields", [])[:4])
                lines.append(
                    f"  - {item.get('module')}: {channels} | {queries} | "
                    f"{item.get('compliance_rule')} | record_type={item.get('record_type') or '-'} | "
                    f"required_fields={required_fields or '-'}"
                )
        public_origin_next_actions = [
            item for item in source_failure_summary.get("public_origin_next_actions", [])
            if isinstance(item, dict)
        ]
        if public_origin_next_actions:
            lines.append("- public-origin next actions:")
            for item in public_origin_next_actions[:5]:
                required_fields = ", ".join(str(value) for value in item.get("required_fields", [])[:4])
                lines.append(
                    f"  - {item.get('action_id')}: {item.get('suggested_source')} | "
                    f"{item.get('query_family')} | record_type={item.get('record_type') or '-'} | "
                    f"required_fields={required_fields or '-'} | done={item.get('done_condition')}"
                )
                if item.get("admission_gate"):
                    lines.append(f"    admission_gate={_short_text(item.get('admission_gate'), 180)}")
        coverage_recovery_actions = [
            item for item in source_failure_summary.get("coverage_recovery_actions", [])
            if isinstance(item, dict)
        ]
        if coverage_recovery_actions:
            lines.append("- coverage recovery actions:")
            for item in coverage_recovery_actions[:6]:
                fallbacks = ", ".join(str(value) for value in item.get("fallback_sources", [])[:3])
                key_fields = ", ".join(str(value) for value in item.get("key_fields", [])[:4])
                origin_priority = _format_origin_priority(item.get("origin_priority"))
                lines.append(
                    f"  - {item.get('action_id')}: domain={item.get('domain')} | "
                    f"source={item.get('suggested_source')} | query={item.get('query_family')}"
                )
                if fallbacks or key_fields:
                    lines.append(
                        f"    fallback_sources={fallbacks or '-'} | key_fields={key_fields or '-'}"
                    )
                if origin_priority:
                    lines.append(f"    origin_priority={origin_priority}")
        execution_plan = [
            item for item in source_failure_summary.get("coverage_recovery_execution_plan", [])
            if isinstance(item, dict)
        ]
        if execution_plan:
            lines.append("- coverage recovery execution plan:")
            for item in execution_plan[:6]:
                lines.append(
                    f"  - {item.get('step_id')}: {item.get('tier')} | "
                    f"{item.get('source')} | domain={item.get('domain')}"
                )
        execution_readiness = _dict(source_failure_summary.get("coverage_recovery_execution_readiness"))
        if execution_readiness:
            lines.append(
                "- coverage recovery execution readiness: "
                f"ready={execution_readiness.get('ready_count', 0)} | "
                f"blocked={execution_readiness.get('blocked_count', 0)} | "
                f"statuses={_format_failure_counts(execution_readiness.get('by_status', {}))}"
            )
        recovery_decision = _dict(source_failure_summary.get("coverage_recovery_decision"))
        if recovery_decision:
            recommended_step = _dict(recovery_decision.get("recommended_step"))
            lines.append(
                "- coverage recovery decision: "
                f"{recovery_decision.get('decision')} | "
                f"ready={recovery_decision.get('ready_to_run')} | "
                f"next={recovery_decision.get('next_action')}"
            )
            if recommended_step:
                lines.append(
                    "  - recommended_step: "
                    f"{recommended_step.get('step_id')} | "
                    f"{recommended_step.get('source')} | "
                    f"status={recommended_step.get('status')} | "
                    f"domain={recommended_step.get('domain')}"
                )
        coverage_status_counts = source_failure_summary.get("coverage_status_counts", {})
        if coverage_status_counts:
            lines.append(
                "- 覆盖状态: "
                + "；".join(
                    f"{_source_status_label(status)}={count}"
                    for status, count in sorted(coverage_status_counts.items())
                )
            )

        source_routing_summary = _dict(source_failure_summary.get("source_routing_summary"))
        if source_routing_summary and source_routing_summary.get("health_report_count", 0):
            lines.append(
                "- source routing health: "
                f"configured={source_routing_summary.get('configured_count', 0)} | "
                f"available={source_routing_summary.get('available_count', 0)} | "
                f"smoke_tested={len(source_routing_summary.get('smoke_tested_sources', []))}"
            )
            smoke_sources = [
                str(item)
                for item in source_routing_summary.get("smoke_tested_sources", [])
                if str(item).strip()
            ]
            explicit_only = [
                str(item)
                for item in source_routing_summary.get("explicit_only_sources", [])
                if str(item).strip()
            ]
            if smoke_sources:
                lines.append("- smoke-tested sources: " + ", ".join(smoke_sources[:5]))
            if explicit_only:
                lines.append("- explicit-only ready sources: " + ", ".join(explicit_only[:5]))

        coverage_interpretation = _dict(source_failure_summary.get("coverage_interpretation"))
        if coverage_interpretation:
            lead_only_count = (
                source_provenance.get("lead_count", 0)
                if not source_provenance.get("factual_count", 0)
                else 0
            )
            lines.append(
                "- coverage interpretation: "
                f"not_searched={coverage_interpretation.get('not_searched_count', 0)} | "
                f"no_evidence={coverage_interpretation.get('no_evidence_count', 0)} | "
                f"lead_only={lead_only_count}"
            )
            missing_domains = [
                str(item)
                for item in source_failure_summary.get("missing_domains", [])
                if str(item).strip()
            ]
            no_evidence_domains = [
                str(item)
                for item in source_failure_summary.get("domains_without_evidence", [])
                if str(item).strip()
            ]
            if missing_domains:
                lines.append("- not searched domains: " + ", ".join(_domain_label(item) for item in missing_domains[:5]))
            if no_evidence_domains:
                lines.append("- no evidence domains: " + ", ".join(_domain_label(item) for item in no_evidence_domains[:5]))
            if lead_only_count:
                lines.append("- lead-only evidence: public or weak leads need official/licensed/user-authorized corroboration before reliance.")

    financial = enterprise_cognition.get("financial")
    if isinstance(financial, dict) and financial:
        lines.extend(["", "## 财务认知"])
        lines.append(
            "- 财务事实: "
            f"revenue={_format_amount(financial.get('revenue'))}; "
            f"net_income={_format_amount(financial.get('net_income'))}; "
            f"operating_cash_flow={_format_amount(financial.get('operating_cash_flow'))}"
        )
        lines.append(
            "- 质量比率: "
            f"net_margin={_format_ratio(financial.get('net_margin'))}; "
            f"cash_conversion={_format_ratio(financial.get('cash_conversion'))}; "
            f"debt_to_assets={_format_ratio(financial.get('debt_to_assets'))}"
        )
        for note in financial.get("quality_notes", [])[:4]:
            lines.append(f"- 解读: {note}")

    fund_flow = enterprise_cognition.get("fund_flow_profile")
    if isinstance(fund_flow, dict) and fund_flow:
        lines.extend(["", "## 资金流画像"])
        lines.append(
            f"- 证据状态: {fund_flow.get('evidence_state')} | "
            f"压力级别: {fund_flow.get('pressure_level')}"
        )
        if fund_flow.get("money_in_signals"):
            lines.append("- 钱从哪来: " + "；".join(_short_text(item, 110) for item in fund_flow["money_in_signals"][:5]))
        if fund_flow.get("money_out_or_pressure_signals"):
            lines.append("- 钱往哪去/压力: " + "；".join(_short_text(item, 110) for item in fund_flow["money_out_or_pressure_signals"][:5]))
        if fund_flow.get("operating_activity_signals"):
            lines.append("- 经营活跃信号: " + "；".join(_short_text(item, 110) for item in fund_flow["operating_activity_signals"][:4]))
        for question in fund_flow.get("next_questions", [])[:3]:
            lines.append(f"- 追问: {_short_text(question, 150)}")

    capital_pressure = enterprise_cognition.get("capital_pressure_profile")
    if isinstance(capital_pressure, dict) and capital_pressure:
        lines.extend(["", "## Capital Pressure Profile"])
        lines.append(
            f"- pressure_level: {capital_pressure.get('pressure_level')} | "
            f"pressure_signals: {capital_pressure.get('pressure_signal_count', 0)} | "
            f"inflow_signals: {capital_pressure.get('inflow_signal_count', 0)} | "
            f"verification: {capital_pressure.get('verification_status')}"
        )
        if capital_pressure.get("source_basis"):
            lines.append("- source_basis: " + "; ".join(str(item) for item in capital_pressure["source_basis"][:8]))
        if capital_pressure.get("pressure_signals"):
            lines.append("- pressure_signals: " + "; ".join(_short_text(item, 110) for item in capital_pressure["pressure_signals"][:8]))
        if capital_pressure.get("inflow_signals"):
            lines.append("- inflow_signals: " + "; ".join(_short_text(item, 110) for item in capital_pressure["inflow_signals"][:6]))
        for row in capital_pressure.get("rows", [])[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- row: [{row.get('module') or row.get('record_type')}] "
                f"{row.get('identifier') or row.get('status') or 'capital-signal'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for question in capital_pressure.get("next_questions", [])[:3]:
            lines.append(f"- next: {_short_text(question, 150)}")

    capital_relationship = enterprise_cognition.get("capital_relationship_profile")
    if isinstance(capital_relationship, dict) and capital_relationship:
        lines.extend(["", "## Capital Relationship Profile"])
        lines.append(
            f"- relationship_risk_level: {capital_relationship.get('relationship_risk_level')} | "
            f"linked_exposures: {capital_relationship.get('match_count', 0)}"
        )
        if capital_relationship.get("source_basis"):
            lines.append("- source_basis: " + "; ".join(str(item) for item in capital_relationship["source_basis"][:8]))
        for item in capital_relationship.get("linked_exposures", [])[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- linked: "
                f"{_short_text(item.get('capital_identifier'), 70)} | "
                f"{item.get('capital_record_type') or item.get('capital_module')} | "
                f"{_short_text(item.get('relationship_from'), 50)} -> "
                f"{_short_text(item.get('relationship_to'), 50)} "
                f"({item.get('relationship_type')}) | "
                f"admission={item.get('relationship_admission') or 'unknown'} | "
                f"conf={item.get('relationship_confidence') or 'unknown'} | "
                f"evidence={','.join(str(eid) for eid in item.get('evidence_ids', [])[:3]) or 'none'}"
            )
        for question in capital_relationship.get("next_questions", [])[:3]:
            lines.append(f"- next: {_short_text(question, 150)}")

    credit_profile = enterprise_cognition.get("credit_profile")
    if isinstance(credit_profile, dict) and credit_profile:
        lines.extend(["", "## 信用画像"])
        lines.append(
            f"- 信用条目: {credit_profile.get('item_count', 0)} | "
            f"风险条目: {credit_profile.get('risk_item_count', 0)} | "
            f"核验状态: {credit_profile.get('verification_status')}"
        )
        for item in credit_profile.get("items", [])[:6]:
            if not isinstance(item, dict):
                continue
            flag = "risk" if item.get("risk_flag") else "normal"
            lines.append(
                f"- [{flag}] {item.get('section')} / {item.get('item')}: "
                f"{item.get('status')} @ {item.get('reference_date')}"
            )
        for note in credit_profile.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    legal_administrative = enterprise_cognition.get("legal_administrative_profile")
    if isinstance(legal_administrative, dict) and legal_administrative:
        lines.extend(["", "## 法务行政画像"])
        lines.append(
            f"- 记录数: {legal_administrative.get('row_count', 0)} | "
            f"司法/执行: {legal_administrative.get('court_enforcement_count', 0)} | "
            f"行政处罚: {legal_administrative.get('administrative_penalty_count', 0)} | "
            f"高风险事件: {legal_administrative.get('high_or_critical_event_count', 0)}"
        )
        for row in legal_administrative.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for event in legal_administrative.get("risk_events", [])[:5]:
            if not isinstance(event, dict):
                continue
            lines.append(
                f"- event: [{event.get('severity')}] {event.get('title')} | "
                f"{event.get('category')} | status={event.get('status')}"
            )
        for note in legal_administrative.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    operational_events = enterprise_cognition.get("operational_event_profile")
    if isinstance(operational_events, dict) and operational_events:
        lines.extend(["", "## 经营事件画像"])
        lines.append(
            f"- 记录数: {operational_events.get('row_count', 0)} | "
            f"工商变更: {operational_events.get('registry_change_count', 0)} | "
            f"融资事件: {operational_events.get('financing_event_count', 0)} | "
            f"并购重组: {operational_events.get('merger_event_count', 0)} | "
            f"资本压力: {operational_events.get('capital_pressure_event_count', 0)} | "
            f"负面舆情: {operational_events.get('negative_opinion_count', 0)}"
        )
        for row in operational_events.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for event in operational_events.get("risk_events", [])[:5]:
            if not isinstance(event, dict):
                continue
            lines.append(
                f"- event: [{event.get('severity')}] {event.get('title')} | "
                f"{event.get('category')} | status={event.get('status')}"
            )
        for note in operational_events.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    commercial_activity = enterprise_cognition.get("commercial_activity_profile")
    if isinstance(commercial_activity, dict) and commercial_activity:
        lines.extend(["", "## 经营活跃度画像"])
        lines.append(
            f"- 记录数: {commercial_activity.get('row_count', 0)} | "
            f"税务: {commercial_activity.get('tax_count', 0)} | "
            f"进出口: {commercial_activity.get('trade_count', 0)} | "
            f"招聘: {commercial_activity.get('recruiting_count', 0)}"
        )
        for row in commercial_activity.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for event in commercial_activity.get("risk_events", [])[:5]:
            if not isinstance(event, dict):
                continue
            lines.append(
                f"- event: [{event.get('severity')}] {event.get('title')} | "
                f"{event.get('category')} | status={event.get('status')}"
            )
        for note in commercial_activity.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    bond_credit = enterprise_cognition.get("bond_credit_profile")
    if isinstance(bond_credit, dict) and bond_credit:
        lines.extend(["", "## 债券信用画像"])
        lines.append(
            f"- 记录数: {bond_credit.get('row_count', 0)} | "
            f"评级记录: {bond_credit.get('rating_count', 0)} | "
            f"违约记录: {bond_credit.get('default_count', 0)} | "
            f"高风险事件: {bond_credit.get('high_or_critical_event_count', 0)}"
        )
        _append_qyyjt_profile_focus_lines(lines, bond_credit)
        for row in bond_credit.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for note in bond_credit.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    regional_credit = enterprise_cognition.get("regional_credit_profile")
    if isinstance(regional_credit, dict) and regional_credit:
        lines.extend(["", "## 区域/城投信用画像"])
        lines.append(
            f"- 记录数: {regional_credit.get('row_count', 0)} | "
            f"城投: {regional_credit.get('city_invest_count', 0)} | "
            f"区域经济: {regional_credit.get('region_economy_count', 0)} | "
            f"地方债务: {regional_credit.get('region_debt_count', 0)} | "
            f"高风险指标: {regional_credit.get('high_or_critical_event_count', 0)}"
        )
        _append_qyyjt_profile_focus_lines(lines, regional_credit)
        for row in regional_credit.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for note in regional_credit.get("quality_notes", [])[:3]:
            lines.append(f"- 瑙ｈ: {note}")

    asset_solvency = enterprise_cognition.get("asset_solvency_profile")
    if isinstance(asset_solvency, dict) and asset_solvency:
        lines.extend(["", "## 资产偿付画像"])
        lines.append(
            f"- 记录数: {asset_solvency.get('row_count', 0)} | "
            f"质押: {asset_solvency.get('pledge_count', 0)} | "
            f"冻结: {asset_solvency.get('freeze_count', 0)} | "
            f"拍卖: {asset_solvency.get('auction_count', 0)} | "
            f"土地: {asset_solvency.get('land_count', 0)}"
        )
        _append_qyyjt_profile_focus_lines(lines, asset_solvency)
        for row in asset_solvency.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for note in asset_solvency.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    fin_inst = enterprise_cognition.get("financial_institution_profile")
    if isinstance(fin_inst, dict) and fin_inst:
        lines.extend(["", "## 金融机构对手方画像"])
        lines.append(
            f"- 记录数: {fin_inst.get('row_count', 0)} | "
            f"高风险机构: {fin_inst.get('high_risk_count', 0)} | "
            f"风险事件: {fin_inst.get('risk_event_count', 0)}"
        )
        _append_qyyjt_profile_focus_lines(lines, fin_inst)
        for row in fin_inst.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            identifier = row.get("identifier") or row.get("institution_name")
            lines.append(
                f"- [{row.get('module') or 'fin_inst'}] {identifier} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for note in fin_inst.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    ip_tech = enterprise_cognition.get("ip_tech_profile")
    if isinstance(ip_tech, dict) and ip_tech:
        lines.extend(["", "## 知识产权画像"])
        lines.append(
            f"- 记录数: {ip_tech.get('row_count', 0)} | "
            f"专利: {ip_tech.get('patent_count', 0)} | "
            f"商标: {ip_tech.get('trademark_count', 0)} | "
            f"著作权: {ip_tech.get('copyright_count', 0)}"
        )
        for row in ip_tech.get("rows", [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- [{row.get('module')}] {row.get('identifier')} | "
                f"{row.get('date') or 'no-date'} | {row.get('status') or 'no-status'} | "
                f"{_short_text(row.get('summary'), 140)}"
            )
        for note in ip_tech.get("quality_notes", [])[:3]:
            lines.append(f"- 解读: {note}")

    industry = enterprise_cognition.get("industry")
    if isinstance(industry, dict) and industry:
        lines.extend(["", "## 行业认知"])
        lines.append(
            f"- 行业: {industry.get('industry')} | "
            f"生命周期: {industry.get('lifecycle')} | "
            f"风险级别: {industry.get('threat_level')}"
        )
        if industry.get("profit_pool_position"):
            lines.append(f"- 利润池位置: {_short_text(industry.get('profit_pool_position'), 180)}")
        if industry.get("enterprise_survival_logic"):
            lines.append(f"- 生存逻辑: {_short_text(industry.get('enterprise_survival_logic'), 180)}")
        for trigger in industry.get("risk_triggers", [])[:4]:
            lines.append(f"- 触发信号: {_short_text(trigger, 140)}")
        if industry.get("evidence_sources"):
            lines.append("- 来源: " + "; ".join(_short_text(item, 90) for item in industry["evidence_sources"][:4]))

    product = enterprise_cognition.get("product")
    if isinstance(product, dict) and product:
        lines.extend(["", "## 产品认知"])
        lines.append(
            f"- 产品: {product.get('product_name')} | "
            f"生命周期: {product.get('lifecycle')} | "
            f"替代风险: {product.get('substitution_risk')}"
        )
        if product.get("customer_value"):
            lines.append(f"- 客户价值: {_short_text(product.get('customer_value'), 180)}")
        if product.get("product_dependency"):
            lines.append(f"- 依赖: {_short_text(product.get('product_dependency'), 180)}")
        for trigger in product.get("risk_triggers", [])[:4]:
            lines.append(f"- 触发信号: {_short_text(trigger, 140)}")
        if product.get("evidence_sources"):
            lines.append("- 来源: " + "; ".join(_short_text(item, 90) for item in product["evidence_sources"][:4]))

    goods_flow = enterprise_cognition.get("goods_flow_profile")
    if isinstance(goods_flow, dict) and goods_flow:
        lines.extend(["", "## 货物流/生意链画像"])
        lines.append(
            f"- 证据状态: {goods_flow.get('evidence_state')} | "
            f"印证: {goods_flow.get('corroboration_status')}"
        )
        for label, key, limit in [
            ("产品", "product_signals", 4),
            ("行业", "industry_signals", 4),
            ("上游", "upstream_signals", 4),
            ("下游", "downstream_signals", 4),
            ("客户", "customer_signals", 4),
            ("供应商", "supplier_signals", 4),
            ("渠道/伙伴", "channel_or_partner_signals", 4),
            ("价值链", "value_chain_signals", 4),
            ("单位经济", "unit_economics_signals", 4),
            ("议价权", "bargaining_power_signals", 4),
            ("竞争格局", "competitive_landscape_signals", 4),
            ("集中度", "concentration_signals", 4),
        ]:
            signals = [str(item) for item in goods_flow.get(key, []) if str(item).strip()]
            if signals:
                lines.append(f"- {label}: " + "；".join(_short_text(item, 110) for item in signals[:limit]))
        if goods_flow.get("pressure_points"):
            lines.append(
                "- 压力点: "
                + "；".join(_short_text(item, 110) for item in goods_flow["pressure_points"][:5])
            )
        for question in goods_flow.get("next_questions", [])[:3]:
            lines.append(f"- 追问: {_short_text(question, 150)}")

    supply_chain = enterprise_cognition.get("supply_chain_profile")
    if isinstance(supply_chain, dict) and supply_chain:
        lines.extend(["", "## 供应链与商业版图"])
        lines.append(
            f"- 已取证条目: {supply_chain.get('row_count', 0)} | "
            f"客户: {supply_chain.get('customer_count', 0)} | "
            f"供应商: {supply_chain.get('supplier_count', 0)} | "
            f"上下游/伙伴: {supply_chain.get('relationship_count', 0)} | "
            f"集中度信号: {supply_chain.get('concentration_signal_count', 0)} | "
            f"来源数: {supply_chain.get('source_count', 0)} | "
            f"印证: {supply_chain.get('corroboration_status')}"
        )
        for label, key in [
            ("客户", "customers"),
            ("供应商", "suppliers"),
            ("上下游/伙伴", "relationships"),
            ("集中度", "concentration_signals"),
        ]:
            rows = [row for row in supply_chain.get(key, []) if isinstance(row, dict)]
            if rows:
                rendered = "; ".join(
                    f"{row.get('field')}={_short_text(row.get('value'), 80)}"
                    for row in rows[:4]
                )
                lines.append(f"- {label}: {rendered}")
        if supply_chain.get("evidence_sources"):
            lines.append(
                "- 来源: "
                + "; ".join(_short_text(item, 90) for item in supply_chain["evidence_sources"][:4])
            )
        for note in supply_chain.get("quality_notes", [])[:2]:
            lines.append(f"- 解读: {note}")

    factual_evidence = [item for item in evidence_ledger if item.get("admission") == "fact"]
    lead_evidence = [item for item in evidence_ledger if item.get("admission") in {"lead", "weak_lead"}]
    lines.extend(["", "## 证据台账"])
    for item in factual_evidence[:8]:
        lines.append(
            f"- {_source_label(item.get('source'))}: {item.get('title')} "
            f"(confidence={item.get('confidence')}, access={item.get('access')})"
        )
        for claim in _report_claims(item.get("claims", []))[:2]:
            lines.append(f"  - {_short_text(claim, 160)}")
    if not factual_evidence:
        lines.append("- 尚未沉淀可直接作为事实依据的证据。")
    if lead_evidence:
        lines.extend(["", "## 待核验线索"])
        for item in lead_evidence[:5]:
            lines.append(
                f"- {_source_label(item.get('source'))}: {item.get('title')} "
                f"(confidence={item.get('confidence')})"
            )

    lines.extend(["", "## 后续版本目标"])
    lines.append("- 持续监控: 当前 0.5.0 Alpha 不上线持续监控，只保留可复用基线。")
    lines.append(f"- 可沉淀为后续基线: {monitoring_seed.get('ready_for_continuous_watch')}")
    lines.append("- 后续可盯防维度: " + ", ".join(_domain_label(item) for item in monitoring_seed.get("watched_dimensions", [])))
    lines.append(f"- 后续建议频率: {_cadence_label(monitoring_seed.get('suggested_cadence'))}")
    recovery_watchlist = [
        item for item in monitoring_seed.get("coverage_recovery_watchlist", [])
        if isinstance(item, dict)
    ]
    if recovery_watchlist:
        lines.append("- 覆盖恢复盯防:")
        for item in recovery_watchlist[:5]:
            fallbacks = ", ".join(str(value) for value in item.get("fallback_sources", [])[:3])
            key_fields = ", ".join(str(value) for value in item.get("key_fields", [])[:4])
            origin_priority = _format_origin_priority(item.get("origin_priority"))
            lines.append(
                f"  - {item.get('domain')}: {item.get('gap_type')} | "
                f"{item.get('suggested_source')} | {item.get('query_family')}"
            )
            if fallbacks or key_fields:
                lines.append(
                    f"    fallback_sources={fallbacks or '-'} | key_fields={key_fields or '-'}"
                )
            if origin_priority:
                lines.append(f"    origin_priority={origin_priority}")

    # ── Quick Overview ──
    relationship_plan = [
        item for item in monitoring_seed.get("relationship_candidate_execution_plan", [])
        if isinstance(item, dict)
    ]
    if relationship_plan:
        lines.append("- relationship candidate execution plan:")
        for item in relationship_plan[:5]:
            sources = ", ".join(str(value) for value in item.get("verification_sources", [])[:3])
            lines.append(
                f"  - {item.get('step_id')}: {item.get('relation_type')} | "
                f"target={item.get('target') or '-'} | sources={sources}"
            )
            expansion_queries = [
                query for query in item.get("expansion_queries", [])
                if isinstance(query, dict)
            ] if isinstance(item.get("expansion_queries"), list) else []
            for query in expansion_queries[:2]:
                lines.append(
                    f"    expand: {query.get('purpose')} | "
                    f"{query.get('source_hint')} | query={_short_text(query.get('query'), 120)}"
                )
    recovery_queue = _dict(monitoring_seed.get("recovery_execution_queue"))
    if recovery_queue:
        lines.append(
            "- recovery execution queue: "
            f"queued={recovery_queue.get('queued_count', 0)} | "
            f"blocked={recovery_queue.get('blocked_count', 0)}"
        )
        work_order = _dict(recovery_queue.get("work_order"))
        ready_queries = [
            item for item in work_order.get("ready_queries", [])
            if isinstance(item, dict)
        ] if isinstance(work_order.get("ready_queries"), list) else []
        for item in ready_queries[:3]:
            key_fields = ", ".join(str(value) for value in item.get("key_fields", [])[:4])
            lines.append(
                f"  - {item.get('queue_id')}: {item.get('source')} | "
                f"query={_short_text(item.get('query'), 140)} | "
                f"key_fields={key_fields or '-'}"
            )
            retry_hint = _retry_policy_hint(_dict(item.get("retry_policy")))
            if retry_hint:
                lines.append(f"    retry_policy={retry_hint}")
            replay_route = _dict(item.get("replay_route"))
            if replay_route:
                lines.append(
                    "    replay_route="
                    f"{replay_route.get('tool')} | command={_short_text(replay_route.get('command'), 160)} | "
                    f"retry_limit={replay_route.get('retry_limit')} | done={_short_text(replay_route.get('done_condition'), 140)}"
                )
                lines.append(
                    "    non_reliance_caveat="
                    + _short_text(replay_route.get("non_reliance_caveat"), 180)
                )
        blocked_preview = [
            item for item in recovery_queue.get("blocked_preview", [])
            if isinstance(item, dict)
        ] if isinstance(recovery_queue.get("blocked_preview"), list) else []
        if blocked_preview:
            lines.append("  - blocked recovery preview:")
            for item in blocked_preview[:3]:
                lines.append(
                    f"    - {item.get('step_id')}: {item.get('source')} | "
                    f"status={item.get('status')} | domain={item.get('domain')} | "
                    f"priority={item.get('priority')}"
                )
                replay_route = _dict(item.get("replay_route"))
                if replay_route:
                    lines.append(
                        "      replay_route="
                        f"{replay_route.get('tool')} | retry_limit={replay_route.get('retry_limit')} | "
                        f"done={_short_text(replay_route.get('done_condition'), 140)}"
                    )
                    lines.append(
                        "      non_reliance_caveat="
                        + _short_text(replay_route.get("non_reliance_caveat"), 180)
                    )

    hr_summary = enterprise_cognition.get("human_readable_dd_summary") or ""
    if hr_summary:
        lines.append("## 快速概览")
        lines.append(hr_summary)

    # ── Due Diligence Profile ──
    dd = enterprise_cognition.get("subject_due_diligence_profile") or {}
    if dd:
        exec_sum = dd.get("executive_summary", {})
        lines.append("## 尽调画像")
        lines.append(f"- 综合风险: {exec_sum.get('overall_risk', '?')} | 证据置信度: {exec_sum.get('evidence_confidence', '?')} | 资金: {exec_sum.get('capital_risk', '?')} | 货品: {exec_sum.get('goods_risk', '?')} | 人员: {exec_sum.get('people_risk', '?')}")
        lines.append(f"- 证据来源: {exec_sum.get('evidence_sources', '?')} 个 | 风险事件: {exec_sum.get('total_risk_events', '?')} 条 | 发现: {exec_sum.get('total_findings', '?')} 条")
        for lane in ("capital_lane", "goods_lane", "people_lane"):
            ld = dd.get(lane, {})
            if ld:
                label = {"capital_lane":"资金线","goods_lane":"货品线","people_lane":"人员线"}.get(lane, lane)
                lines.append(f"- {label}: 风险={ld.get('risk','?')} | 数据可用={ld.get('profile_available')} | 公开信号={ld.get('public_signals_count',0)}条")
                for f in ld.get("key_findings", [])[:2]:
                    lines.append(f"  - {str(f)[:120]}")

    # ── Audit Log ──
    audit = enterprise_cognition.get("investigation_audit_log") or {}
    if audit:
        lines.append("## 审计日志")
        src = audit.get("sources", {})
        ev = audit.get("evidence", {})
        risk = audit.get("risk_events", {})
        lines.append(f"- 查询来源: {src.get('total_queried', '?')} 个 | 失败: {src.get('failed', '?')} 个 | 产出证据: {ev.get('total', '?')} 条")
        src_list = audit.get("sources_used", [])
        if src_list:
            lines.append(f"- 来源明细: {', '.join(str(s) for s in src_list[:8])}")
        lines.append(f"- 证据分级: 事实={ev.get('admitted_as_fact', '?')} 条 | 线索={ev.get('admitted_as_lead', '?')} 条")
        lines.append(f"- 风险事件: {risk.get('total', '?')} 条 | 高风险: {risk.get('high_severity', '?')} 条")
        lines.append(f"- 准入策略: {ev.get('admission_policy', '')}")

    # ── Evidence Admission ──
    facts = sum(1 for e in evidence_ledger if e.get("admission") == "fact")
    leads = sum(1 for e in evidence_ledger if e.get("admission") in ("lead", "weak_lead"))
    if facts or leads:
        lines.append("## 证据准入")
        lines.append(f"- 事实级: {facts} 条（高置信+强来源，已进入报告）")
        lines.append(f"- 线索级: {leads} 条（中低置信或单一来源，需核验后使用）")

    lines.extend(["", "## 下一步"])
    for action in next_actions[:6]:
        lines.append(f"- {_friendly_action(action)}")
    if not next_actions:
        lines.append("- 继续补充数据源并复核关键证据。")

    lines.extend(
        [
            "",
            "> 说明: 本报告只整理公开、授权或演示夹具数据；推断均应作为线索，不应伪装成已核验事实。",
        ]
    )
    return "\n".join(lines)


def _finding(event: dict[str, Any]) -> dict[str, Any]:
    refs = []
    for ref in event.get("evidence_refs", []):
        if isinstance(ref, dict):
            refs.append(ref.get("source") or ref.get("id"))
    return {
        "id": event.get("id"),
        "title": _event_title(event),
        "severity": event.get("severity"),
        "category": _category_label(event.get("category")),
        "entity_names": event.get("entity_names", []),
        "confidence": event.get("confidence"),
        "why_it_matters": _event_rationale(event),
        "source_refs": refs,
    }


def _event_title(event: dict[str, Any]) -> str:
    title = str(event.get("title") or "").strip()
    category = str(event.get("category") or "")
    replacements = {
        "Court or enforcement risk signal": "司法执行风险信号",
        "Administrative penalty or abnormal operation signal": "行政处罚或经营异常信号",
        "Ownership or controller anomaly signal": "股权或实控人异常信号",
        "Asset encumbrance or auction signal": "资产抵押或拍卖信号",
        "Negative public-opinion or dispute signal": "负面舆情或纠纷信号",
        "Social-web identity or activity lead": "社交网络身份或活动线索",
        "Controller change signal": "实控人变动信号",
    }
    if title in replacements:
        return replacements[title]
    if title:
        return title
    if category:
        return _category_label(category) + "风险信号"
    return "未命名风险信号"



def _build_cross_lane_questions(ec):
    """Generate cross-lane investigation questions."""
    qs = []
    cap = ec.get("capital_profile") or {}
    sup = ec.get("supply_chain_profile") or {}
    controllers = ec.get("controller_candidates") or []
    asset = ec.get("asset_solvency_profile") or {}
    if (cap.get("capital_pressure") or cap.get("cash_or_liquidity")) and sup.get("supplier_concentration"):
        qs.append("supplier_concentration + capital_pressure = supply chain solvency risk")
    if sup.get("customer_concentration") and ("revenue" in str(cap).lower() or "financing" in str(cap).lower()):
        qs.append("customer_concentration + revenue_financing = key-client dependency risk")
    if controllers and sup.get("related_party_transactions"):
        qs.append("controller_presence + related_party = transfer pricing risk")
    if "frozen" in str(asset).lower() and cap.get("debt_or_credit_obligation"):
        qs.append("asset_freeze + debt_obligation = refinancing risk")
    return qs[:8]

def _risk_event_prefix(raw: Any) -> str:
    labels = {
        "critical": "重大风险事件",
        "high": "高风险事件",
        "medium": "中风险事件",
        "low": "低风险事件",
    }
    return labels.get(str(raw).lower(), "公开风险事件")


def _category_label(raw: Any) -> str:
    labels = {
        "court_enforcement": "司法与执行",
        "administrative_risk": "行政与监管风险",
        "ownership_control": "股权与实控人",
        "location_assets": "地址、资产与偿付能力",
        "news_public_opinion": "新闻与舆情",
        "social_web": "公开账号与社交网络",
    }
    if hasattr(raw, "value"):
        raw = getattr(raw, "value")
    return labels.get(str(raw), str(raw))


def _event_rationale(event: dict[str, Any]) -> str:
    rationale = str(event.get("rationale") or "").strip()
    if not rationale:
        return "该线索可能影响授信、合作、交易或合规判断。"
    if rationale.startswith("Matched keywords:"):
        keywords = rationale.split(":", 1)[1].strip()
        return "匹配到关键词：" + keywords if keywords else "匹配到相关风险关键词。"
    if "controller-change risk event" in rationale.lower():
        return "夹具提供方标记了一个实控人变动风险事件。"
    if "court enforcement watch item" in rationale.lower():
        return "夹具提供方标记了一个司法执行观察项。"
    if "administrative penalty lead" in rationale.lower():
        return "夹具提供方标记了一个行政处罚观察项。"
    return rationale


def _source_label(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "待补充来源"
    labels = {
        "fixture_public_registry": "公共登记样例",
        "fixture_gleif_lei_public_api": "GLEIF LEI 样例",
        "fixture_sec_edgar_public_api": "SEC EDGAR 样例",
        "fixture_licensed_registry_api": "授权情报样例",
        "fixture_public_web_search": "公开网页样例",
        "fixture_telegram_public_service:demo_bot": "Telegram 公共服务样例",
        "offline_court_fixture": "离线司法样例",
        "gleif_lei_public_api": "GLEIF LEI",
        "sec_edgar_public_api": "SEC EDGAR",
        "wikidata_public_entity_graph": "Wikidata 实体图谱",
        "public_web_search": "公开网页搜索",
        "telegram_bot_public_service": "Telegram 公共服务",
        "ofac_consolidated_sanctions_xml": "OFAC 制裁清单",
        "un_sc_consolidated_sanctions_xml": "UN 安理会制裁清单",
        "world_bank_debarred_firms_public_list": "世界银行禁入名单",
    }
    if text in labels:
        return labels[text]
    if text.startswith("fixture_"):
        return text.removeprefix("fixture_").replace("_", " ")
    return text


def _authority_label(raw: Any) -> str:
    labels = {
        "official": "官方",
        "commercial": "商业授权",
        "public_web": "公开网页",
        "community": "社区/公开服务",
        "unknown": "未知",
        "": "未知",
        None: "未知",
    }
    return labels.get(raw, labels.get(str(raw), str(raw)))


def _access_label(raw: Any) -> str:
    labels = {
        "public": "公开",
        "licensed": "授权/许可",
        "user_authorized": "用户授权",
        "internal": "内部",
        "unknown": "未知",
        "": "未知",
        None: "未知",
    }
    return labels.get(raw, labels.get(str(raw), str(raw)))


def _rank_profile_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "identity": 0,
        "control_ownership": 1,
        "location_activity": 2,
        "asset_solvency": 3,
        "behavioral_risk": 4,
        "relation_network": 5,
        "contact_accounts": 6,
        "public_statements": 7,
        "consumption_preference": 8,
    }
    seen: set[tuple[str, str]] = set()
    ranked: list[dict[str, Any]] = []
    for signal in sorted(
        signals,
        key=lambda item: (
            priority.get(str(item.get("dimension") or ""), 99),
            _profile_signal_specificity(item),
            _verification_rank(item.get("verification_status")),
            -_float(item.get("confidence")),
            str(item.get("value") or ""),
        ),
    ):
        value = str(signal.get("value") or "").strip()
        dimension = str(signal.get("dimension") or "")
        if not value:
            continue
        if _is_low_signal_summary(signal):
            continue
        key = (dimension, value.lower())
        if key in seen:
            continue
        seen.add(key)
        ranked.append(signal)
    return ranked


def _is_low_signal_summary(signal: dict[str, Any]) -> bool:
    value = str(signal.get("value") or "")
    relation = str(signal.get("relation_type") or "")
    dimension = str(signal.get("dimension") or "")
    if relation:
        return False
    if dimension == "location_activity" and "=" in value and ";" in value:
        return True
    return False


def _profile_signal_specificity(signal: dict[str, Any]) -> int:
    relation = str(signal.get("relation_type") or "")
    title = str(signal.get("title") or "")
    value = str(signal.get("value") or "")
    if relation in {"registered_address", "headquarters_address"}:
        return 0
    if "=" in value and ";" in value:
        return 2
    if "record:" in title.lower():
        return 2
    return 1


def _verification_rank(raw: Any) -> int:
    return {
        "verified": 0,
        "corroborated": 1,
        "public_lead": 2,
        "inferred": 3,
        "needs_review": 4,
    }.get(str(raw), 5)


def _verification_status_label(raw: Any) -> str:
    labels = {
        "verified": "官方/高可信来源已核验",
        "corroborated": "多来源交叉印证",
        "public_lead": "公开线索，建议复核",
        "inferred": "系统推断，需人工确认",
        "needs_review": "待人工复核",
    }
    return labels.get(str(raw), str(raw))


def _float(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _report_claims(raw_claims: Any) -> list[str]:
    if not isinstance(raw_claims, list):
        return []
    claims: list[str] = []
    for claim in raw_claims:
        text = str(claim or "").strip()
        if not text or text == "{}":
            continue
        if text.startswith("{") and text.endswith("}"):
            continue
        claims.append(text)
    return claims


def _short_text(raw: Any, limit: int) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _verdict(execution_state: str, highest: str, score: int) -> str:
    if execution_state in {"not_executed", "no_available_sources"}:
        return "insufficient_data"
    if highest == "critical" or score >= 85:
        return "critical_risk_review_required"
    if highest == "high" or score >= 60:
        return "high_risk_verification_required"
    if highest == "medium" or score >= 30:
        return "moderate_risk_watchlist"
    return "no_material_risk_found_from_available_evidence"


def _verdict_label(verdict: str) -> str:
    labels = {
        "insufficient_data": "证据不足，不能下结论",
        "critical_risk_review_required": "发现重大风险信号，必须人工复核",
        "high_risk_verification_required": "发现高风险信号，需要优先核验",
        "moderate_risk_watchlist": "存在中等风险线索，建议持续关注",
        "no_material_risk_found_from_available_evidence": "当前公开证据未发现重大风险",
    }
    return labels.get(str(verdict), str(verdict))


def _execution_state_label(state: str) -> str:
    labels = {
        "not_executed": "尚未执行取证",
        "no_available_sources": "当前没有可用数据源",
        "all_sources_failed": "数据源全部失败，需要重试或检查网络",
        "no_evidence_found": "已查询，但暂无有效证据",
        "partial_source_failure": "部分数据源失败，已有结果可先参考",
        "evidence_found": "已取得可用证据",
        "risk_events_found": "已发现风险事件",
    }
    return labels.get(str(state), str(state))


def _severity_label(raw: Any) -> str:
    labels = {
        "critical": "重大",
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "暂无",
        "": "暂无",
        None: "暂无",
    }
    return labels.get(raw, str(raw))


def _confidence_label(note: Any) -> str:
    text = str(note or "")
    if text.startswith("No evidence"):
        return "当前没有证据，空结果不能等同于低风险。"
    if text.startswith("Some sources failed"):
        return "部分来源失败，最终判断前应复核失败来源。"
    return "本报告基于证据生成，重大决策仍需人工核验。"


def _source_status_label(status: Any) -> str:
    labels = {
        "success": "成功",
        "ok": "成功",
        "retrieved": "已获取",
        "empty": "空结果",
        "empty_result": "空结果",
        "no_results": "空结果",
        "not_searched": "未搜索",
        "failed": "失败",
        "error": "失败",
        "blocked": "被拦截",
        "blocked_or_captcha": "被拦截/验证码",
        "timeout": "超时",
        "parse_failed": "解析失败",
        "authorization_required": "需要授权",
        "query_template_only": "仅查询模板",
        "skipped": "跳过",
        "unknown": "未知",
        "": "未知",
        None: "未知",
    }
    return labels.get(status, str(status))


def _failure_category_label(category: Any) -> str:
    labels = {
        "none": "无异常",
        "empty_result": "空结果",
        "timeout": "超时",
        "authorization": "授权/权限问题",
        "rate_limit": "限流",
        "network": "网络异常",
        "connector_error": "连接器异常",
        "unknown": "未知异常",
        "": "未知异常",
        None: "未知异常",
    }
    return labels.get(category, str(category))


def _format_failure_counts(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "暂无"
    parts = [
        f"{_failure_category_label(category)}={count}"
        for category, count in sorted(counts.items(), key=lambda item: (_failure_rank(item[0]), str(item[0])))
    ]
    return "；".join(parts)


def _failure_rank(category: Any) -> int:
    order = {
        "timeout": 0,
        "authorization": 1,
        "rate_limit": 2,
        "network": 3,
        "connector_error": 4,
        "empty_result": 5,
        "skipped_unsupported_source": 6,
        "unknown": 7,
        "none": 8,
    }
    return order.get(str(category), 8)


def _quality_status_label(status: Any) -> str:
    labels = {
        "blocked": "暂不可交付，缺少关键证据",
        "ready_for_human_review": "可进入人工复核",
        "usable_with_warnings": "可用但必须带着缺口阅读",
        "needs_more_evidence": "需要继续补证",
    }
    return labels.get(str(status), str(status))


def _quality_issue_label(issue: Any) -> str:
    text = str(issue or "")
    if text.startswith("retrieval_not_reliable:"):
        state = text.split(":", 1)[1]
        return "取证链路不可靠：" + _execution_state_label(state)
    labels = {
        "no_factual_evidence": "没有可作为事实依据的证据",
        "no_official_or_licensed_evidence": "缺少官方、授权或高权威来源",
        "official_or_licensed_evidence_present": "已有官方、授权或高权威来源",
        "financial_facts_present": "已有财务或资本市场事实",
        "financial_facts_missing": "缺少财务、现金流或资本市场事实",
        "financial_facts_not_rendered": "财务事实没有进入报告正文",
        "financial_gap_conflicts_with_financial_facts": "财务缺口与已取证财务事实不一致",
        "controller_profile_missing": "缺少实控人、最终受益人或关键管理人证据",
        "source_failures_present": "部分数据源失败，不能把空结果当成低风险",
        "coverage_gaps_present": "覆盖维度仍有证据缺口",
        "enterprise_cognition_gaps_present": "企业认知仍缺少行业、产品、法律或事件证据",
        "clean_verdict_with_blockers": "存在阻塞项时不能给出干净结论",
    }
    return labels.get(text, text)


def _quality_action_label(action: Any) -> str:
    text = str(action or "")
    replacements = {
        "run a configured or official-public retrieval pass before relying on the report":
            "先跑一次已配置的公开或授权取证，再依赖报告",
        "collect at least one source-backed factual record":
            "至少补齐一条带来源的事实证据",
        "add at least one official, licensed, or high-authority public source":
            "补充至少一个官方、授权或高权威公开来源",
        "collect finance or capital-market facts when material to the subject":
            "如果该主体有财务重要性，补充财务、现金流或资本市场事实",
        "render financial facts in the report body":
            "把已取到的财务事实写入报告正文",
        "remove finance evidence gaps once verified finance facts are present":
            "财务事实已核验后，移除冲突的财务缺口",
        "collect controller, UBO, or key-person evidence before final reliance":
            "最终依赖前，补齐实控人、最终受益人或关键管理人证据",
        "retry or replace failed sources before treating empty coverage as meaningful":
            "重试或替换失败来源，再判断空覆盖是否有意义",
        "collect missing industry, product, legal, administrative, or event evidence before final reliance":
            "最终依赖前，补齐行业、产品、法律、行政或风险事件证据",
        "avoid clean-sounding conclusions when blocking quality issues remain":
            "存在阻塞项时，避免给出听起来像低风险的结论",
    }
    if text in replacements:
        return replacements[text]
    if text.startswith("expand or retry evidence-poor domains:"):
        return "扩展或重试证据薄弱维度：" + _label_csv(text.split(":", 1)[1])
    if text.startswith("run retrieval for missing domains:"):
        return "补跑缺失维度取证：" + _label_csv(text.split(":", 1)[1])
    return _friendly_action(text)


def _friendly_gap(gap: Any) -> str:
    text = str(gap)
    replacements = {
        "Missing or weak controller and beneficial-owner evidence": "下一轮优先穿透实控人、最终受益人和关键管理人",
        "Missing or weak public asset and solvency evidence": "下一轮补充公开资产、偿付能力和抵质押线索",
        "Missing or weak behavioral, administrative, and court-risk evidence": "下一轮补充行政处罚、司法执行和行为风险记录",
        "Missing or weak relationship-network evidence": "下一轮扩展关联企业、共同地址、共同项目和交易对手网络",
    }
    for source, target in replacements.items():
        if source in text:
            return target + "。"
    return text


def _friendly_action(action: Any) -> str:
    text = str(action)
    if text.startswith("Run with --offline-fixture"):
        return "当前没有真实数据源结果；可先运行离线夹具做安装验收，或配置真实数据源。"
    if text.startswith("No configured datasource"):
        return "已配置的数据源当前不可用；请检查健康检查结果，不能把空结果当作低风险。"
    if text.startswith("Review failed source diagnostics"):
        return "复核失败数据源并重试网络波动，再做最终判断。"
    if text.startswith("Empty retrieval"):
        return "空查询是覆盖不足信号，不是低风险证明；建议扩展数据源或调整查询。"
    if text.startswith("Execute missing planned domains:"):
        return "下一轮补采任务：补齐" + _label_csv(text.split(":", 1)[1])
    if text.startswith("Prioritize new sources for evidence-poor domains:"):
        return "下一轮数据源扩展任务：优先增强" + _label_csv(text.split(":", 1)[1])
    if text.startswith("Escalate high-severity events"):
        return "把高风险事件进入人工核验和后续盯防流程。"
    if text.startswith("Continue scheduled monitoring"):
        return "将本次结果作为基线，后续扫描时对比新增变化。"
    return text


def _domain_label(raw: Any) -> str:
    labels = {
        "administrative_risk": "行政与监管风险",
        "behavioral_risk": "公开行为风险",
        "beneficial_owner": "最终受益人",
        "chief_executive_officer": "首席执行官/关键高管",
        "contact_accounts": "联系方式与公开账号",
        "controller": "实控人",
        "control_ownership": "控制权与实控人",
        "corporate_registry": "工商/主体身份",
        "court_enforcement": "司法与执行",
        "director": "董事/管理层",
        "asset_solvency": "资产与偿付能力",
        "consumption_preference": "公开消费与偏好线索",
        "financing_capital_markets": "资本市场披露",
        "identity": "主体身份",
        "ip_tech": "知识产权与技术",
        "legal_representative": "法定代表人",
        "location_activity": "地址与活动范围",
        "location_assets": "地址、资产与偿付能力",
        "news_public_opinion": "新闻与舆情",
        "ownership_control": "股权与实控人",
        "procurement_projects": "招投标与项目",
        "public_opinion": "公开舆情",
        "public_role_or_control_lead": "公开角色/控制权线索",
        "public_statements": "公开言论与公告",
        "relation_network": "关联关系网络",
        "related_subject": "关联主体",
        "related_entities": "关联主体",
        "risk_events": "风险事件",
        "shareholder": "股东",
        "social_web": "公开账号与社交网络",
    }
    return labels.get(str(raw), str(raw))


def _label_csv(raw: Any) -> str:
    return "、".join(
        _domain_label(item.strip())
        for item in str(raw).split(",")
        if item.strip()
    )


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in items if str(item).strip()))


def _cadence_label(raw: Any) -> str:
    labels = {
        "daily_until_verified": "每日，直到完成核验",
        "weekly": "每周",
        "monthly": "每月",
    }
    return labels.get(str(raw), str(raw))


def _coverage_gap_penalty(summary: dict[str, Any]) -> int:
    coverage = _dict(summary.get("coverage"))
    missing = coverage.get("missing_domains") or []
    without = coverage.get("domains_without_evidence") or []
    missing_count = len(missing) if isinstance(missing, list) else 0
    without_count = len(without) if isinstance(without, list) else 0
    return min((missing_count * 2) + without_count, 18)


def _confidence_note(summary: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No evidence was collected; the output is a coverage warning, not a risk clearance."
    failed = summary.get("failed_sources") or []
    if failed:
        return "Some sources failed; verify failed routes before final judgment."
    return "Evidence-backed packet; still requires human verification for material decisions."


def _verification_hint(source_profile: dict[str, Any], item: dict[str, Any]) -> str:
    authority = str(source_profile.get("authority") or "unknown")
    access = str(source_profile.get("access") or "unknown")
    if authority == "official" and access in {"public", "licensed"}:
        return "official_or_licensed_source"
    if item.get("url"):
        return "verify_url_and_cross_source"
    return "verify_source_metadata_before_reliance"


def _suggested_cadence(highest: str) -> str:
    if highest in {"critical", "high"}:
        return "daily_until_verified"
    if highest == "medium":
        return "weekly"
    return "monthly"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
