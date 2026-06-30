#!/usr/bin/env python3
"""Quality gate for product-facing investigation packets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvestigationQualityGate:
    """Machine-readable delivery status for a one-click investigation packet."""

    ok: bool
    status: str
    score: int
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    dimension_scores: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "score": self.score,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "strengths": list(self.strengths),
            "next_actions": list(self.next_actions),
            "dimension_scores": list(self.dimension_scores),
        }


def evaluate_investigation_packet(
    *,
    summary: dict[str, Any],
    risk_brief: dict[str, Any],
    profile_brief: dict[str, Any],
    evidence_ledger: list[dict[str, Any]],
    enterprise_cognition: dict[str, Any],
    report_markdown: str,
    source_failure_summary: dict[str, Any] | None = None,
) -> InvestigationQualityGate:
    """Evaluate whether a packet is ready for user-facing reliance."""
    blockers: list[str] = []
    warnings: list[str] = []
    strengths: list[str] = []
    next_actions: list[str] = []

    evidence_count = int(summary.get("evidence_count") or len(evidence_ledger))
    execution_state = str(summary.get("execution_state") or "unknown")
    factual_evidence = [item for item in evidence_ledger if _is_fact_admission(item)]
    official_evidence = [
        item for item in factual_evidence
        if item.get("authority") == "official" or item.get("access") in {"licensed", "user_authorized"}
    ]
    financial = enterprise_cognition.get("financial") if isinstance(enterprise_cognition, dict) else None
    supply_chain = enterprise_cognition.get("supply_chain_profile") if isinstance(enterprise_cognition, dict) else None
    relationship_network = enterprise_cognition.get("relationship_network") if isinstance(enterprise_cognition, dict) else None
    claim_corroboration = enterprise_cognition.get("claim_corroboration") if isinstance(enterprise_cognition, dict) else None
    investigation_card = (
        enterprise_cognition.get("investigation_report_card")
        if isinstance(enterprise_cognition, dict)
        else None
    )
    dd_summary = investigation_card.get("dd_summary") if isinstance(investigation_card, dict) else {}
    people_lane = dd_summary.get("people_lane_summary") if isinstance(dd_summary, dict) else {}
    controller_conflicts = (
        people_lane.get("controller_conflict_summary")
        if isinstance(people_lane, dict)
        else None
    )
    public_lead_profiles = [
        enterprise_cognition.get("public_capital_profile"),
        enterprise_cognition.get("public_goods_profile"),
        enterprise_cognition.get("public_people_profile"),
    ] if isinstance(enterprise_cognition, dict) else []
    public_lead_count = sum(
        int(profile.get("row_count") or 0)
        for profile in public_lead_profiles
        if isinstance(profile, dict)
    )
    controller_count = int(profile_brief.get("controller_candidate_count") or 0)
    gaps = [str(item) for item in enterprise_cognition.get("evidence_gaps", []) if str(item).strip()]
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    subject_profile = summary.get("subject_profile") if isinstance(summary.get("subject_profile"), dict) else {}
    covered_dimensions = {
        str(item) for item in subject_profile.get("covered_dimensions", [])
        if str(item).strip()
    }
    evidence_is_substantive = evidence_count >= 4 and len(covered_dimensions) >= 4
    domains_without_evidence = [str(item) for item in coverage.get("domains_without_evidence", []) if str(item).strip()]
    missing_domains = [str(item) for item in coverage.get("missing_domains", []) if str(item).strip()]
    failed_sources = [str(item) for item in summary.get("failed_sources", []) if str(item).strip()]
    source_failure_summary = source_failure_summary or {}
    recovery_decision = (
        source_failure_summary.get("coverage_recovery_decision")
        if isinstance(source_failure_summary, dict)
        else None
    )
    source_resilience = (
        source_failure_summary.get("source_resilience_profile")
        if isinstance(source_failure_summary, dict)
        else None
    )

    if execution_state in {"not_executed", "no_available_sources", "all_sources_failed"}:
        blockers.append(f"retrieval_not_reliable:{execution_state}")
        next_actions.append("run a configured or official-public retrieval pass before relying on the report")
    if evidence_count <= 0 or not factual_evidence:
        blockers.append("no_factual_evidence")
        next_actions.append("collect at least one source-backed factual record")
    if public_lead_count and not factual_evidence:
        warnings.append("public_leads_need_corroboration")
        next_actions.append("upgrade public leads into official, licensed, or user-authorized facts before relying on this packet")
    if not official_evidence:
        warnings.append("no_official_or_licensed_evidence")
        next_actions.append("add at least one official, licensed, or high-authority public source")
    else:
        strengths.append("official_or_licensed_evidence_present")
    if financial:
        strengths.append("financial_facts_present")
        if "## 财务认知" not in report_markdown:
            blockers.append("financial_facts_not_rendered")
            next_actions.append("render financial facts in the report body")
        if any(_is_financial_gap(gap) for gap in gaps):
            blockers.append("financial_gap_conflicts_with_financial_facts")
            next_actions.append("remove finance evidence gaps once verified finance facts are present")
    elif evidence_count > 0:
        warnings.append("financial_facts_missing")
        next_actions.append("collect finance or capital-market facts when material to the subject")
    if isinstance(supply_chain, dict) and supply_chain:
        if supply_chain.get("corroboration_status") == "multi_source_supported":
            strengths.append("supply_chain_corroborated")
        elif supply_chain.get("corroboration_status") == "single_source_needs_corroboration":
            warnings.append("supply_chain_single_source_needs_corroboration")
            next_actions.append("corroborate customer, supplier, upstream/downstream, and concentration claims with another independent source")
    if isinstance(relationship_network, dict) and relationship_network:
        relationship_edges = [
            item for item in relationship_network.get("top_edges", [])
            if isinstance(item, dict)
        ]
        strong_edges = [item for item in relationship_edges if _is_strong_relationship_edge(item)]
        audited_edges = [item for item in strong_edges if _has_evidence_ids(item)]
        unaudited_edges = [item for item in relationship_edges if not _has_evidence_ids(item)]
        if audited_edges:
            strengths.append("relationship_edges_auditable")
        if relationship_edges and not strong_edges:
            warnings.append("relationship_edges_need_fact_admission")
            next_actions.append("verify relationship edges against fact-admitted registry, filing, announcement, or licensed evidence")
        if unaudited_edges:
            warnings.append("relationship_edges_missing_evidence_ids")
            next_actions.append("attach evidence_ids to relationship edges before relying on graph claims")
    if isinstance(claim_corroboration, dict):
        conflict_count = int(claim_corroboration.get("conflict_field_count") or 0)
        supported_count = int(claim_corroboration.get("multi_source_supported_count") or 0)
        if conflict_count:
            warnings.append("claim_conflicts_need_review")
            next_actions.append("review conflicting claim fields before relying on the packet")
        if supported_count:
            strengths.append("multi_source_claims_present")
    if isinstance(controller_conflicts, dict) and controller_conflicts.get("review_required"):
        status = str(controller_conflicts.get("status") or "controller_conflict")
        if status == "conflicting_verified_controller_claims":
            warnings.append("verified_controller_conflicts_need_review")
            next_actions.append("resolve competing verified controller or UBO claims before final reliance")
        else:
            warnings.append("controller_leads_need_review")
            next_actions.append("review competing controller leads against official, licensed, or user-authorized sources")
    if controller_count <= 0:
        warnings.append("controller_profile_missing")
        next_actions.append("collect controller, UBO, or key-person evidence before final reliance")
    if failed_sources:
        warnings.append("source_failures_present")
        next_actions.append("retry or replace failed sources before treating empty coverage as meaningful")
    if isinstance(source_resilience, dict) and source_resilience:
        resilience_status = str(source_resilience.get("status") or "").strip()
        resilience_failures = int(source_resilience.get("failure_count") or 0)
        if resilience_status == "needs_operator_recovery":
            warnings.append("source_resilience_needs_operator_recovery")
            recommended_action = str(source_resilience.get("recommended_action") or "").strip()
            if recommended_action:
                next_actions.append("resolve source resilience issue: " + recommended_action)
            else:
                next_actions.append("resolve source resilience issues before treating coverage as complete")
    if isinstance(recovery_decision, dict) and recovery_decision:
        decision = str(recovery_decision.get("decision") or "").strip()
        next_action = str(recovery_decision.get("next_action") or "").strip()
        recommended_step = recovery_decision.get("recommended_step")
        recommended_step = recommended_step if isinstance(recommended_step, dict) else {}
        source = str(recommended_step.get("source") or recommended_step.get("suggested_source") or "").strip()
        domain = str(recommended_step.get("domain") or "").strip()
        if decision == "run_ready_recovery_step":
            strengths.append("coverage_recovery_ready")
            next_actions.append(
                "run ready coverage recovery"
                + (f" for {domain}" if domain else "")
                + (f" via {source}" if source else "")
                + (f": {next_action}" if next_action else "")
            )
        elif decision:
            warnings.append("coverage_recovery_blocked")
            next_actions.append(
                "resolve blocked coverage recovery"
                + (f" for {domain}" if domain else "")
                + (f" via {source}" if source else "")
                + (f": {next_action}" if next_action else "")
            )
    if domains_without_evidence or (missing_domains and not evidence_is_substantive):
        warnings.append("coverage_gaps_present")
        if domains_without_evidence:
            next_actions.append("expand or retry evidence-poor domains: " + ", ".join(domains_without_evidence[:5]))
        elif missing_domains:
            next_actions.append("run retrieval for missing domains: " + ", ".join(missing_domains[:5]))
    md_lowered = report_markdown.lower()
    cleaned_gaps = [gap for gap in gaps if not _gap_is_covered_by_report(gap, md_lowered, enterprise_cognition)]
    material_gaps = [gap for gap in cleaned_gaps if _is_material_cognition_gap(gap)]
    if material_gaps:
        warnings.append("enterprise_cognition_gaps_present")
        next_actions.append("collect missing industry, product, legal, administrative, or event evidence before final reliance")
    if risk_brief.get("verdict") == "no_material_risk_found_from_available_evidence" and blockers:
        blockers.append("clean_verdict_with_blockers")
        next_actions.append("avoid clean-sounding conclusions when blocking quality issues remain")

    score = 100
    non_scoring_warnings = {
        "coverage_recovery_blocked",
        "coverage_recovery_ready",
        "source_resilience_needs_operator_recovery",
    }
    scoring_warnings = set(warnings) - non_scoring_warnings
    score -= 30 * len(set(blockers))
    score -= 8 * len(scoring_warnings)
    score = max(0, min(100, score))
    status = _status(bool(blockers), score)
    # Per-dimension quality assessment
    dims = {
        "evidence_coverage": min(100, sum(1 for e in evidence_ledger if _is_fact_admission(e)) * 20),
        "source_diversity": min(100, len({e.get("source","") for e in evidence_ledger}) * 25),
        "report_completeness": min(100, report_markdown.count("## ") * 4),
        "risk_detection": min(100, max(0, 50 + (risk_brief.get("risk_score", 0) - 2) * 10)),
        "data_quality": min(100, sum(1 for e in evidence_ledger if e.get("admission") == "fact") * 25),
    }
    dimension_scores = [
        {"dimension": k, "score": v, "max": 100, "status": "good" if v >= 75 else ("fair" if v >= 50 else "weak")}
        for k, v in dims.items()
    ]
    return InvestigationQualityGate(
        ok=not blockers,
        status=status,
        score=score,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
        strengths=tuple(sorted(set(strengths))),
        next_actions=tuple(_dedupe(next_actions)),
        dimension_scores=dimension_scores,
    )



def _negative_source_gate(source_statuses: list) -> dict:
    """Blocked/template-only sources must not reduce risk or imply clean coverage."""
    blocked = [s for s in source_statuses if s.get("status") in ("blocked","template_only","authorization_required","timeout")]
    empty = [s for s in source_statuses if s.get("status") in ("empty_result","not_searched")]
    warnings = []
    if blocked:
        warnings.append({"type":"coverage_gap_blocked","count":len(blocked),"sources":[s.get("source_name","?") for s in blocked]})
    if empty:
        warnings.append({"type":"coverage_gap_empty","count":len(empty),"sources":[s.get("source_name","?") for s in empty]})
    return {"source_blocked_count":len(blocked),"source_empty_count":len(empty),"warnings":warnings}


def _is_fact_admission(item: dict[str, Any]) -> bool:
    admission = item.get("admission")
    if admission is not None:
        return admission == "fact"
    return item.get("record_kind") == "evidence"


def _is_strong_relationship_edge(item: dict[str, Any]) -> bool:
    return str(item.get("admission") or "").strip().lower() in {"fact", "admitted", "evidence"}


def _has_evidence_ids(item: dict[str, Any]) -> bool:
    return any(str(evidence_id).strip() for evidence_id in item.get("evidence_ids", []))


def _gap_is_covered_by_report(gap: str, md_lowered: str, enterprise_cognition: dict[str, Any] | None = None) -> bool:
    """Return True only if enterprise_cognition has actual evidence objects for this gap domain.

    Report section headers alone are not sufficient — must have real data.
    """
    cognition = enterprise_cognition or {}
    gap_lowered = gap.lower()
    # Evidence-backed checks: must have corresponding profile dict, not just a section header
    evidence_checks = {
        "财务": lambda: bool(cognition.get("financial")),
        "现金流": lambda: bool(cognition.get("financial")),
        "行业": lambda: bool(cognition.get("industry")),
        "产品": lambda: bool(cognition.get("product")),
        "上下游": lambda: bool(cognition.get("supply_chain_profile")),
        "供应商": lambda: bool(cognition.get("supply_chain_profile")),
        "司法": lambda: bool(cognition.get("legal_administrative_profile")),
        "执行": lambda: bool(cognition.get("legal_administrative_profile")),
        "行政": lambda: bool(cognition.get("legal_administrative_profile")),
        "风险事件": lambda: bool(cognition.get("risk_event_summary")),
    }
    # Check evidence first
    for domain, check in evidence_checks.items():
        if domain in gap_lowered:
            try:
                if check():
                    return True
            except Exception:
                pass
    # Fallback: section headers as weak signal only if evidence check not applicable
    sections_present = {
        "财务": ["## 财务", "## financial"],
        "行业": ["## 行业", "## industry"],
        "产品": ["## 产品", "## product"],
        "上下游": ["## 供应链", "## supply chain"],
        "供应商": ["## 供应链"],
        "司法": ["## 法务", "## 司法"],
        "执行": ["## 法务"],
        "行政": ["## 法务", "## 行政"],
    }
    for domain, markers in sections_present.items():
        if domain in gap_lowered:
            for marker in markers:
                if marker in md_lowered:
                    return True
    return False

def _is_financial_gap(text: str) -> bool:
    return any(token in text for token in ("financial", "finance", "财务", "现金流", "璐㈠姟", "鐜伴噾"))


def _is_material_cognition_gap(text: str) -> bool:
    lowered = str(text or "").lower()
    material_tokens = (
        "industry",
        "product",
        "financial",
        "finance",
        "legal",
        "administrative",
        "court",
        "risk event",
        "行业",
        "产品",
        "财务",
        "现金流",
        "司法",
        "执行",
        "行政",
        "舆情",
        "风险事件",
    )
    if any(token in lowered for token in material_tokens):
        return True
    followup_tokens = (
        "relationship-network",
        "relationship network",
        "关联",
        "关系网络",
    )
    return not any(token in lowered for token in followup_tokens)


def _status(has_blockers: bool, score: int) -> str:
    if has_blockers:
        return "blocked"
    if score >= 85:
        return "ready_for_human_review"
    if score >= 65:
        return "usable_with_warnings"
    return "needs_more_evidence"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
