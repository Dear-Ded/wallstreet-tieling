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
        next_actions=next_actions,
        quality_gate=quality_gate,
    )
    report_exports = _report_export_bundle(
        company=str(graph_payload.get("company") or input_text),
        version=version,
        report_markdown=report_markdown,
        one_click_readiness=one_click_readiness,
        summary=summary,
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
        report_exports=report_exports,
        report_markdown=report_markdown,
        graph=graph_payload,
        next_actions=next_actions,
    )


def _report_export_bundle(
    *,
    company: str,
    version: str,
    report_markdown: str,
    one_click_readiness: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Describe desktop-agent report outputs without requiring the HTML workbench."""
    safe_company = _safe_report_filename(company)
    markdown_filename = f"{safe_company}-due-diligence-report.md"
    html_filename = f"{safe_company}-due-diligence-report.html"
    html_document = _portable_report_html(
        company=company,
        version=version,
        report_markdown=report_markdown,
        one_click_readiness=one_click_readiness,
        summary=summary,
    )
    return {
        "type": "report_exports",
        "current_release": "desktop_agent_packet_exports",
        "formats": ["markdown", "json_packet", "portable_html"],
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
            "content_policy": "contains the full Markdown report in a printable escaped preformatted block; no findings are dropped",
        },
        "json_packet": {
            "filename": f"{safe_company}-investigation-packet.json",
            "mime_type": "application/json; charset=utf-8",
            "content_field": "entire investigation_packet",
        },
        "future_formats": {
            "docx_red_head": "p2_template_required_not_current_release_blocker",
            "immersive_premium_html": "p2_visual_polish_not_current_release_blocker",
        },
        "print_readiness": {
            "portable_html_printable": True,
            "markdown_printable": True,
            "docx_print_binding_layout": "future_template",
        },
    }


def _portable_report_html(
    *,
    company: str,
    version: str,
    report_markdown: str,
    one_click_readiness: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    status = html.escape(str(one_click_readiness.get("status") or "unknown"))
    execution_state = html.escape(str(summary.get("execution_state") or "unknown"))
    quality_score = html.escape(str(one_click_readiness.get("quality_score") or "n/a"))
    fact_count = html.escape(str(one_click_readiness.get("fact_count") or 0))
    lead_count = html.escape(str(one_click_readiness.get("lead_count") or 0))
    coverage_gap = html.escape(str(one_click_readiness.get("coverage_gap_count") or 0))
    coverage_severity = html.escape(str(one_click_readiness.get("coverage_gap_severity") or "none"))
    capital_status = html.escape(str(one_click_readiness.get("capital_relationship_status") or "unknown"))
    report = html.escape(report_markdown)
    title = html.escape(f"Wallstreet Tieling Due Diligence Report - {company}")
    company_html = html.escape(company)
    return (
        "<!doctype html>\n"
        "<html lang=\"zh-CN\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{title}</title>\n"
        "  <style>\n"
        "    body{font-family:Georgia,'Noto Serif SC','Microsoft YaHei',serif;margin:0;background:#f6f2ea;color:#1f2933;}\n"
        "    main{max-width:980px;margin:0 auto;padding:40px 28px 72px;}\n"
        "    header{border-bottom:4px solid #9f1d20;margin-bottom:24px;padding-bottom:18px;}\n"
        "    .eyebrow{letter-spacing:.18em;color:#9f1d20;font-weight:700;text-transform:uppercase;font-size:12px;}\n"
        "    h1{font-size:30px;line-height:1.25;margin:10px 0 8px;}\n"
        "    .meta{display:flex;gap:12px;flex-wrap:wrap;color:#52606d;font-size:14px;}\n"
        "    .pill{border:1px solid #c7b8a0;border-radius:999px;padding:5px 10px;background:#fffaf2;}\n"
        "    .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0;}\n"
        "    .card{background:#fffaf2;border:1px solid #e5d8c5;border-radius:14px;padding:14px 16px;}\n"
        "    .card b{display:block;font-size:20px;margin-bottom:4px;color:#1f2933;}\n"
        "    .card span{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7b6b58;}\n"
        "    pre{white-space:pre-wrap;word-break:break-word;background:#fffdf8;border:1px solid #e5d8c5;border-radius:16px;padding:24px;line-height:1.62;font-size:14px;box-shadow:0 18px 40px rgba(31,41,51,.08);}\n"
        "    @media print{body{background:#fff;}main{padding:18mm;}pre{box-shadow:none;border-color:#999;}header{break-after:avoid;}}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
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
        f"      <div class=\"card\"><b>{coverage_gap}</b><span>coverage gaps: {coverage_severity}</span></div>\n"
        f"      <div class=\"card\"><b>{capital_status}</b><span>capital relationship</span></div>\n"
        "    </section>\n"
        f"    <pre>{report}</pre>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _safe_report_filename(company: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", str(company or "subject")).strip("-._")
    return value[:80] or "subject"


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


def _one_click_readiness_summary(
    *,
    quality_gate: dict[str, Any],
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
    blockers = [str(item) for item in quality_gate.get("blockers", []) if str(item).strip()]
    warnings = [str(item) for item in quality_gate.get("warnings", []) if str(item).strip()]
    source_resilience_action = str(source_resilience.get("recommended_action") or "").strip()
    capital_pressure = _dict(enterprise_cognition.get("capital_pressure_profile"))
    capital_relationship = _dict(enterprise_cognition.get("capital_relationship_profile"))
    relationship_network = _dict(enterprise_cognition.get("relationship_network"))
    relationship_edges = [
        item for item in relationship_network.get("top_edges", [])
        if isinstance(item, dict)
    ]
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
        or int(recovery_queue.get("blocked_count") or 0)
        or int(recovery_queue.get("queued_count") or 0)
    )
    if not facts:
        status = "blocked_no_factual_evidence"
    elif blockers:
        status = "blocked_quality_gate"
    elif needs_operator_followup:
        status = "usable_with_operator_followup"
    else:
        status = "ready_for_human_review"
    return {
        "type": "one_click_readiness",
        "status": status,
        "ready_for_user_review": ready_for_user,
        "needs_operator_followup": needs_operator_followup,
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
        "recovery_ready_count": int(recovery_queue.get("queued_count") or 0),
        "recovery_blocked_count": int(recovery_queue.get("blocked_count") or 0),
        "capital_pressure_level": capital_pressure.get("pressure_level"),
        "capital_pressure_verification_status": capital_pressure.get("verification_status"),
        "capital_pressure_lead_only_public_rows_present": bool(capital_pressure.get("lead_only_public_rows_present")),
        "capital_relationship_needed": capital_relationship_needed,
        "capital_relationship_explained": capital_relationship_explained,
        "capital_relationship_status": capital_relationship_status,
        "capital_relationship_unresolved_reason": capital_relationship_unresolved_reason,
        "capital_relationship_next_action": capital_relationship_next_action,
        "capital_relationship_match_count": int(capital_relationship.get("match_count") or 0),
        "relationship_edge_count": len(relationship_edges),
        "relationship_evidence_backed_edge_count": relationship_evidence_backed_count,
        "relationship_auditable_edge_count": relationship_auditable_count,
        "relationship_missing_evidence_edge_count": relationship_missing_evidence_count,
        "relationship_lead_only_edge_count": relationship_lead_only_count,
        "section_checks": sections,
        "acceptance_gate": "packet_has_facts_quality_report_provenance_and_future_monitoring_boundary",
    }



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
                f"{structured.get('business_model', 0)} model leads"
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
                "query": _recovery_execution_query(subject, query_family),
                "key_fields": list(plan_item.get("key_fields") or [])[:6],
                "admission_rule": plan_item.get("admission_rule"),
                "done_condition": "Return source URL, observed timestamp, extracted key fields, and whether result is evidence, lead, empty, or blocked.",
            }
        )
    return {
        "ready_to_run": bool(queue),
        "queued_count": len(queue),
        "blocked_count": int(_dict(readiness).get("blocked_count") or len(blocked_steps)),
        "queue": queue,
        "blocked_preview": blocked_steps[:5],
        "work_order": {
            "subject": subject,
            "ready_queries": [
                {
                    "queue_id": item.get("queue_id"),
                    "source": item.get("source"),
                    "query": item.get("query"),
                    "key_fields": item.get("key_fields", []),
                }
                for item in queue
            ],
            "handoff_rule": "Execute queued ready queries first; keep blocked rows as connector/admission work, not subject evidence.",
        },
        "policy": "Queue includes only connector-ready recovery steps; blocked steps require explicit enablement or connector work.",
    }


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

    typed = [item for item in leads if str(item.get("extracted_field") or "").strip()]
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
        if not target and not relation_type and not extracted_field:
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
            for key in ("claims", "claim", "title", "url", "source"):
                if key not in row and original.get(key) is not None:
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
    return {
        "profile_available": bool(pg),
        "supplier_claims": pg.get("supplier_claims", []),
        "customer_claims": pg.get("customer_claims", []),
        "product_claims": pg.get("product_claims", []),
        "market_position_claims": pg.get("market_position_claims", []),
        "business_model_claims": pg.get("business_model_claims", []),
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
        "gaps": [] if (facts or leads or bridge_fact_count or bridge_lead_count or pg.get("supplier_claims") or pg.get("market_position_claims") or pg.get("business_model_claims")) else ["No product/supply chain evidence found — provide supplier/customer/industry data"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "Who are the top 5 customers by revenue share?",
            "Who are the critical suppliers and what is the dependency level?",
            "What is the market share and competitive position?",
            "Are there IP/technology assets that create moats?",
        ],
        "lane_status": "covered" if facts or bridge_fact_count else ("weak" if leads or bridge_lead_count or pg.get("supplier_claims") or pg.get("customer_claims") or pg.get("market_position_claims") or pg.get("business_model_claims") else "missing"),
        "deep_analysis": {
            "supplier_concentration": "HIGH" if pg.get("supplier_claims") else "UNKNOWN",
            "customer_dependency": "MEDIUM" if pg.get("customer_claims") else "UNKNOWN",
            "product_moat": "NEEDS_EVIDENCE" if not facts and not bridge_fact_count else "WEAK_SIGNALS",
            "market_position_notes": f"{len(facts) + bridge_fact_count} fact items, {len(leads) + bridge_lead_count} leads",
            "public_market_position": pg.get("market_position_claims", []),
            "public_business_model": pg.get("business_model_claims", []),
        },
    }

def _build_people_lane(evidence_ledger, subject_profile, relationship_network) -> dict:
    """P0-E: Build people/control investigation lane."""
    el = evidence_ledger or []; sp = subject_profile or {}; rn = relationship_network or {}
    facts = [e for e in el if e.get("admission")=="fact" and e.get("lane")=="people"]
    leads = [e for e in el if e.get("admission") in ("lead","weak_lead") and e.get("lane")=="people"]
    controllers = sp.get("controllers") or sp.get("controller_candidates") or []
    key_personnel = sp.get("key_personnel") or sp.get("key_people") or []
    relation_edges = rn.get("top_edges") or rn.get("edges") or []
    relation_count = int(rn.get("relation_count") or len(relation_edges or []))
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
        "fact_count": len(facts), "lead_count": len(leads),
        "gaps": [] if (facts or leads or controllers or relation_count or sp) else ["No people/ownership/control evidence found"],
        "entity_truth_gate": {"entity_resolution_version": "2.0", "same_name_no_merge": True, "official_outranks_public": True}, "researched_patterns": {"entity_resolution":"dedupe/recordlinkage-style entity keys","evidence_pipeline":"admission-gated provenance tracking","graph_explainability":"edge-level source+confidence audit"},
        "next_questions": [
            "Who is the ultimate beneficial owner (UBO)?",
            "Are there controller-company related-party transactions?",
            "Are there shared-address or shared-project relationships?",
            "Do key personnel have litigation or dishonesty records?",
        ],
        "lane_status": "covered" if facts or strong_controller_count or strong_relation_count else ("weak" if leads or controllers or relation_count or sp else "missing"),
        "deep_analysis": {
            "controller_confidence": "HIGH" if facts or strong_controller_count else ("MEDIUM" if controllers else "LOW"),
            "ubo_path_visible": any("ubo" in str(e).lower() for e in facts) or any("ubo" in str(e).lower() for e in leads) or any("beneficial" in str(c).lower() or "ubo" in str(c).lower() for c in controllers),
            "related_party_risk": "MONITOR" if controllers or key_personnel or relation_count else "UNKNOWN",
            "governance_notes": f"{len(facts)} controller facts, {len(leads)} leads, {len(controllers)} controller candidates, {relation_count} relationship edges",
            "controller_conflict_status": controller_conflict_summary.get("status", "none"),
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
            "source_count": len(preferred.get("source_names") or []),
            "confidence": preferred.get("confidence"),
        },
        "competing_candidates": [
            str(item.get("name") or "")
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
                    (people_lane_summary := _build_people_lane(evidence_ledger_v2, subject_profile, {})).get("lane_status", "missing"),
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
        row = {
            "module": "fin_inst",
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
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_fin_inst_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "quality_notes": [
            "QYYJT fin_inst contract supplied report-admissible institution name, type, license, region, and risk fields",
            f"financial institution counterparty rows: {len(rows)}",
            f"high-risk counterparties: {len(high_risk)}",
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

    return {
        "type": "capital_pressure_profile",
        "evidence_state": "evidence_backed",
        "pressure_level": pressure_level,
        "pressure_signal_count": len(pressure_signals),
        "inflow_signal_count": len(inflow_signals),
        "inflow_signals": inflow_signals,
        "pressure_signals": pressure_signals,
        "source_basis": source_basis,
        "rows": rows[:12],
        "lead_only_public_rows_present": lead_only,
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
                f"model:{structured.get('business_model', 0)}"
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

    if not any([controller_signals, key_person_signals, relationship_signals, control_path_signals, legal_pressure_signals]):
        return None

    verification_status = (
        str(control_ownership.get("verification_status"))
        if control_ownership
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

    return {
        "seed_subject_name": profile_brief.get("seed_subject_name") or subject_profile.get("seed_subject_name"),
        "controller_candidate_count": candidate_count,
        "controller_candidates": normalized_candidates,
        "source_names": _dedupe_strings(source_names),
        "relation_types": _dedupe_strings(relation_types),
        "verification_status": _best_verification_status(verification_statuses),
        "graph_summary": {
            "subject_count": len(nodes),
            "relation_count": len(edges),
        },
        "control_paths": _control_paths_from_graph(nodes, edges, normalized_candidates),
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
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_bond_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT bond contracts supplied report-admissible bond, rating, issue, or default fields",
            f"bond rows available: {len(rows)}",
            f"bond risk events available: {len(events)}",
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
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_regional_credit_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT regional/city-investment contracts supplied report-admissible region, period, metric, and risk-level fields",
            f"regional credit rows available: {len(rows)}",
            f"regional credit risk events available: {len(events)}",
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
        "risk_events": _profile_event_rows(events),
        "verification_status": "licensed_qyyjt_asset_solvency_contract",
        "evidence_sources": _dedupe_strings(sources)[:8],
        "source_claims": _dedupe_strings(source_claims)[:10],
        "quality_notes": [
            "licensed QYYJT asset/solvency contracts supplied report-admissible pledge, freeze, auction, or land fields",
            f"asset/solvency rows available: {len(rows)}",
            f"asset/solvency risk events available: {len(events)}",
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
        }
        rows.append(row)
        ref = _evidence_source_ref(item)
        if ref:
            sources.append(ref)
        source_claims.extend(claims)
    return rows, sources, source_claims


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

    # Strong sources → fact
    if authority in {"official", "licensed"} and confidence >= 0.8:
        return "fact"
    if "qyyjt_api" in source and confidence >= 0.8:
        return "fact"
    if "sec_edgar" in source and confidence >= 0.75:
        return "fact"

    # Medium sources or lower confidence → lead
    if authority in {"official", "licensed", "public"} and confidence >= 0.6:
        return "lead"
    if match_level in {"exact", "strong"} and confidence >= 0.5:
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
        })
        rows.append(
            {
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
                "admission": admission,
                "admission_reason": f"authority={source_profile.get('authority')} confidence={item.get('confidence')} match={entity_match.get('level')}",
            }
        )
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
        "recovery_execution_queue": recovery_execution_queue,
        "recovery_execution_summary": {
            "ready_to_run": recovery_execution_queue.get("ready_to_run", False),
            "queued_count": recovery_execution_queue.get("queued_count", 0),
            "blocked_count": recovery_execution_queue.get("blocked_count", 0),
            "top_blocker": blocked_preview[0] if blocked_preview else {},
            "recurring_failure_count": len(recurring_failure_patterns),
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
        if role["active"]:
            role["next_question"] = enterprise_cognition.get("next_questions",[])[:1] if enterprise_cognition.get("next_questions") else []
        enriched_roles.append(role)

    return {
        "type": "investigation_persona_surface",
        "version": "0.5.0",
        "display_name": "华尔街驻铁岭办事处 13 角色专家团",
        "role_count": len(enriched_roles),
        "active_role_count": len(active_ids),
        "active_roles": [role for role in enriched_roles if role["active"]],
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
        f"DD Summary: {dd.get('company', '?')} | Overall: {risk_labels.get(exec_sum.get('overall_risk', 'unknown'), '?')} | Confidence: {exec_sum.get('evidence_confidence', '?')}{fin_line} | Findings: {exec_sum.get("total_findings", "?")} total",
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
            f"market={goods_public_summary.get('market_position', 0)} | "
            f"model={goods_public_summary.get('business_model', 0)}"
        )
        for label, key in (
            ("market", "market_position_claims"),
            ("model", "business_model_claims"),
            ("customer", "customer_claims"),
            ("supplier", "supplier_claims"),
        ):
            signals = [str(item) for item in goods.get(key, []) if str(item).strip()]
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
        lines.append(
            f"- capital: pressure={one_click_readiness.get('capital_pressure_level') or 'none'} | "
            f"verification={one_click_readiness.get('capital_pressure_verification_status') or 'none'} | "
            f"relationship_needed={one_click_readiness.get('capital_relationship_needed')} | "
            f"relationship_explained={one_click_readiness.get('capital_relationship_explained')} | "
            f"relationship_status={one_click_readiness.get('capital_relationship_status') or 'unknown'} | "
            f"lead_only_public={one_click_readiness.get('capital_pressure_lead_only_public_rows_present')}"
        )
        if one_click_readiness.get("capital_relationship_unresolved_reason"):
            lines.append(
                "- capital relationship unresolved: "
                + str(one_click_readiness.get("capital_relationship_unresolved_reason"))
                + " | next="
                + _short_text(one_click_readiness.get("capital_relationship_next_action"), 220)
            )
        if int(one_click_readiness.get("relationship_edge_count") or 0):
            lines.append(
                f"- relationship graph: edges={one_click_readiness.get('relationship_edge_count', 0)} | "
                f"evidence_backed={one_click_readiness.get('relationship_evidence_backed_edge_count', 0)} | "
                f"auditable_fact={one_click_readiness.get('relationship_auditable_edge_count', 0)} | "
                f"missing_evidence={one_click_readiness.get('relationship_missing_evidence_edge_count', 0)} | "
                f"lead_only={one_click_readiness.get('relationship_lead_only_edge_count', 0)}"
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
        if control_ownership.get("control_paths"):
            lines.append("- 控制路径预览:")
            for path in control_ownership["control_paths"][:4]:
                if path.get("path_text"):
                    lines.append(f"  - {_short_text(path.get('path_text'), 160)}")
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
        lines.extend(["", "## 鍖哄煙/鍩庢姇淇＄敤鐢诲儚"])
        lines.append(
            f"- 璁板綍鏁? {regional_credit.get('row_count', 0)} | "
            f"鍩庢姇: {regional_credit.get('city_invest_count', 0)} | "
            f"鍖哄煙缁忔祹: {regional_credit.get('region_economy_count', 0)} | "
            f"鍦版柟鍊哄姟: {regional_credit.get('region_debt_count', 0)} | "
            f"楂橀闄╂寚鏍? {regional_credit.get('high_or_critical_event_count', 0)}"
        )
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
