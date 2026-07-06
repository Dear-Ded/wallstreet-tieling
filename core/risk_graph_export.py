#!/usr/bin/env python3
"""Compact graph/timeline export for risk discovery results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context_budget import ContextBudgetManager
from .intelligence_retrieval import EvidenceGraph, RiskSeverity
from .risk_discovery_pipeline import RiskDiscoveryResult


SEVERITY_RANK = {
    RiskSeverity.CRITICAL.value: 4,
    RiskSeverity.HIGH.value: 3,
    RiskSeverity.MEDIUM.value: 2,
    RiskSeverity.LOW.value: 1,
}


@dataclass(frozen=True)
class RiskGraphExport:
    """Plugin/UI friendly graph view with compact references."""

    company: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    risk_events: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "summary": self.summary,
            "nodes": self.nodes,
            "edges": self.edges,
            "evidence": self.evidence,
            "risk_events": self.risk_events,
            "timeline": self.timeline,
            "diagnostics": self.diagnostics,
        }


def export_risk_graph(result: RiskDiscoveryResult) -> RiskGraphExport:
    """Build a compact graph/timeline payload from a discovery result."""

    graph = result.graph
    nodes = _nodes(graph)
    evidence = _evidence(graph)
    risk_events = _risk_events(graph)
    edges = _edges(graph, risk_events)
    timeline = _timeline(evidence, risk_events)
    capital_exposure = _capital_exposure_summary(evidence, risk_events, edges)
    context_capsule = _context_capsule(result, evidence, risk_events)
    subject_profile_summary = _subject_profile_summary(result.subject_profile)
    run_id = result.retrieval_summary.get("run_id") or getattr(result, "run_id", "")
    summary = {
        "run_id": run_id,
        "execution_state": result.retrieval_summary.get("execution_state"),
        "entity_count": len(nodes),
        "relation_count": len(graph.relations),
        "evidence_count": len(evidence),
        "risk_event_count": len(risk_events),
        "highest_severity": _highest_severity(risk_events),
        "queried_sources": result.queried_sources,
        "failed_sources": result.failed_sources,
        "alert_count": _current_alert_count(risk_events),
        "monitoring_alert_count": result.risk_event_summary.get("alert_count", 0),
        "coverage": result.retrieval_summary.get("coverage", {}),
        "next_actions": result.retrieval_summary.get("next_actions", []),
        "subject_profile": subject_profile_summary,
        "entity_resolution": result.retrieval_summary.get("entity_resolution", {}),
        "capital_exposure": capital_exposure,
    }
    diagnostics = {
        "run_id": run_id,
        "store_path": result.store_path,
        "retrieval_summary": result.retrieval_summary,
        "source_routing": result.retrieval_summary.get("source_routing", {}),
        "record_quality": result.retrieval_summary.get("record_quality", {}),
        "source_diagnostics": result.source_diagnostics,
        "subject_profile": result.subject_profile,
        "first_alert": result.to_dict().get("first_alert"),
        "monitoring_delta": result.risk_event_summary.get("delta", {}),
        "context_capsule": context_capsule,
    }
    return RiskGraphExport(
        company=result.company,
        nodes=nodes,
        edges=edges,
        evidence=evidence,
        risk_events=risk_events,
        timeline=timeline,
        summary=summary,
        diagnostics=diagnostics,
    )


def _nodes(graph: EvidenceGraph) -> list[dict[str, Any]]:
    return [
        {
            "id": entity_id,
            "kind": entity.kind.value,
            "name": entity.name,
            "confidence": entity.confidence,
            "evidence_ids": list(entity.evidence_ids),
            "attributes": entity.attributes,
        }
        for entity_id, entity in sorted(graph.entities.items())
    ]


def _subject_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    signals_by_dimension = profile.get("signals_by_dimension", {})
    if not isinstance(signals_by_dimension, dict):
        signals_by_dimension = {}
    dimension_counts = {
        str(dimension): len(signals)
        for dimension, signals in signals_by_dimension.items()
        if isinstance(signals, list)
    }
    return {
        "seed_subject_id": profile.get("seed_subject_id"),
        "seed_subject_name": profile.get("seed_subject_name"),
        "subject_count": len(profile.get("subjects", {})) if isinstance(profile.get("subjects"), dict) else 0,
        "controller_candidate_count": len(profile.get("controller_candidates", []))
        if isinstance(profile.get("controller_candidates"), list)
        else 0,
        "dimension_counts": dimension_counts,
        "covered_dimensions": sorted(
            dimension for dimension, count in dimension_counts.items()
            if count > 0
        ),
        "evidence_gap_count": len(profile.get("evidence_gaps", []))
        if isinstance(profile.get("evidence_gaps"), list)
        else 0,
        "recursion_policy": profile.get("recursion_policy", {}),
    }


def _edges(graph: EvidenceGraph, risk_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Build entity name lookup
    entity_names = {}
    for eid, entity in graph.entities.items():
        entity_names[eid] = entity.name

    # Build evidence source lookup
    evidence_sources = {}
    for eid, item in graph.evidence.items():
        evidence_sources[eid] = {"source": item.source, "title": item.title}

    edges = []
    for idx, relation in enumerate(graph.relations, start=1):
        from_name = entity_names.get(relation.from_id, relation.from_id)
        to_name = entity_names.get(relation.to_id, relation.to_id)
        edge_sources = []
        for ev_id in relation.evidence_ids:
            src_info = evidence_sources.get(ev_id, {})
            src_name = src_info.get("source", ev_id)
            if src_name not in edge_sources:
                edge_sources.append(src_name)
        edges.append({
            "id": f"relation:{idx}",
            "type": relation.relation_type,
            "from": relation.from_id,
            "to": relation.to_id,
            "from_name": from_name,
            "to_name": to_name,
            "confidence": relation.confidence,
            "evidence_ids": list(relation.evidence_ids),
            "source_names": edge_sources[:5],
            "rationale": f"Relation {relation.relation_type} from {from_name} to {to_name} based on {len(relation.evidence_ids)} evidence item(s)",
        })
    for event in risk_events:
        for entity_id in event["entity_ids"]:
            edges.append(
                {
                    "id": f"{event['id']}->{entity_id}",
                    "type": "has_risk_event",
                    "from": entity_id,
                    "to": event["id"],
                    "confidence": event["confidence"],
                    "evidence_ids": event["evidence_ids"],
                }
            )
    return edges


def _evidence(graph: EvidenceGraph) -> list[dict[str, Any]]:
    return [
        {
            "id": evidence_id,
            "type": item.evidence_type.value,
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "observed_at": item.observed_at,
            "confidence": item.confidence,
            "claim_count": len(item.claims),
            "claims": _trimmed_claims(item.claims),
            "omitted_claim_count": max(0, len(item.claims) - 12),
            "source_profile": item.source_profile.to_dict() if item.source_profile else None,
            "entity_match": item.entity_match,
        }
        for evidence_id, item in sorted(graph.evidence.items())
    ]


def _risk_events(graph: EvidenceGraph) -> list[dict[str, Any]]:
    entity_names = {entity_id: entity.name for entity_id, entity in graph.entities.items()}
    evidence_lookup = graph.evidence
    events = [
        {
            "id": event.id,
            "category": event.category.value,
            "title": event.title,
            "severity": event.severity.value,
            "entity_ids": list(event.entity_ids),
            "entity_names": [
                entity_names[entity_id]
                for entity_id in event.entity_ids
                if entity_id in entity_names
            ],
            "evidence_ids": list(event.evidence_ids),
            "evidence_refs": [
                {
                    "id": evidence_id,
                    "source": evidence_lookup[evidence_id].source,
                    "url": evidence_lookup[evidence_id].url,
                    "confidence": evidence_lookup[evidence_id].confidence,
                    "authority": (
                        evidence_lookup[evidence_id].source_profile.authority.value
                        if evidence_lookup[evidence_id].source_profile
                        else "unknown"
                    ),
                    "access": (
                        evidence_lookup[evidence_id].source_profile.access.value
                        if evidence_lookup[evidence_id].source_profile
                        else "unknown"
                    ),
                }
                for evidence_id in event.evidence_ids
                if evidence_id in evidence_lookup
            ],
            "confidence": event.confidence,
            "rationale": event.rationale,
            "status": event.status,
        }
        for event in graph.risk_events
    ]
    return sorted(
        events,
        key=lambda item: (
            -SEVERITY_RANK.get(str(item["severity"]), 0),
            str(item["category"]),
            str(item["id"]),
        ),
    )


def _timeline(
    evidence: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evidence_by_id = {item["id"]: item for item in evidence}
    for item in evidence:
        rows.append(
            {
                "id": f"timeline:{item['id']}",
                "kind": "evidence",
                "at": item.get("observed_at"),
                "title": item["title"],
                "source": item["source"],
                "severity": None,
                "evidence_ids": [item["id"]],
            }
        )
    for event in risk_events:
        event_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in event["evidence_ids"]
            if evidence_id in evidence_by_id
        ]
        rows.append(
            {
                "id": f"timeline:{event['id']}",
                "kind": "risk_event",
                "at": _first_observed_at(event_evidence),
                "title": event["title"],
                "source": ", ".join(sorted({item["source"] for item in event_evidence})),
                "severity": event["severity"],
                "evidence_ids": event["evidence_ids"],
            }
        )
    return sorted(rows, key=lambda item: (str(item.get("at") or ""), item["kind"], item["id"]))


def _first_observed_at(evidence: list[dict[str, Any]]) -> str | None:
    observed = sorted(str(item["observed_at"]) for item in evidence if item.get("observed_at"))
    return observed[0] if observed else None


def _highest_severity(risk_events: list[dict[str, Any]]) -> str | None:
    if not risk_events:
        return None
    return max(
        (str(item["severity"]) for item in risk_events),
        key=lambda severity: SEVERITY_RANK.get(severity, 0),
    )


def _capital_exposure_summary(
    evidence: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize capital pressure for graph consumers without promoting leads."""
    capital_evidence: list[dict[str, Any]] = []
    pressure_signals: list[str] = []
    inflow_signals: list[str] = []
    for item in evidence:
        text = _capital_text(item)
        if not _contains_any(text, CAPITAL_TOKENS):
            continue
        capital_evidence.append(item)
        pressure_signals.extend(token for token in CAPITAL_PRESSURE_TOKENS if token in text)
        inflow_signals.extend(token for token in CAPITAL_INFLOW_TOKENS if token in text)

    capital_event_categories = {"financing_capital_markets", "location_assets"}
    capital_risk_events = [
        item for item in risk_events
        if item.get("category") in capital_event_categories
        or _contains_any(_capital_text(item), CAPITAL_TOKENS)
    ]
    capital_edges = [
        item for item in edges
        if item.get("type") != "has_risk_event"
        and _contains_any(_capital_edge_text(item), CAPITAL_RELATIONSHIP_TOKENS)
    ]
    verification_queue = _capital_verification_queue(
        capital_evidence=capital_evidence,
        capital_risk_events=capital_risk_events,
        capital_edges=capital_edges,
    )
    relationship_audit_queue = _capital_relationship_audit_queue(
        capital_evidence=capital_evidence,
        capital_edges=capital_edges,
    )
    pressure_signals = sorted(set(pressure_signals))
    inflow_signals = sorted(set(inflow_signals))
    pressure_signal_count = len(pressure_signals) + len(capital_risk_events)
    inflow_signal_count = len(inflow_signals)
    if pressure_signal_count >= 3 or any(str(item.get("severity")) in {"high", "critical"} for item in capital_risk_events):
        pressure_level = "elevated"
    elif pressure_signal_count:
        pressure_level = "watch"
    elif inflow_signal_count:
        pressure_level = "capital_activity_only"
    else:
        pressure_level = "none"

    if pressure_level == "none":
        relationship_status = "not_applicable"
        next_action = ""
    elif capital_edges:
        relationship_status = "mapped"
        next_action = "Review capital-linked relationship edges and verify the highest-risk counterparty first."
    else:
        relationship_status = "needs_relationship_mapping"
        next_action = (
            "Map admitted lenders, pledgees, guarantors, bond parties, asset holders, or related controllers "
            "before treating capital pressure as explained."
        )

    return {
        "type": "capital_exposure_summary",
        "pressure_level": pressure_level,
        "pressure_signal_count": pressure_signal_count,
        "inflow_signal_count": inflow_signal_count,
        "pressure_signals": pressure_signals[:12],
        "inflow_signals": inflow_signals[:8],
        "capital_evidence_count": len(capital_evidence),
        "capital_risk_event_count": len(capital_risk_events),
        "capital_relationship_edge_count": len(capital_edges),
        "relationship_status": relationship_status,
        "evidence_ids": [str(item["id"]) for item in capital_evidence[:8]],
        "risk_event_ids": [str(item["id"]) for item in capital_risk_events[:8]],
        "relationship_edge_ids": [str(item["id"]) for item in capital_edges[:8]],
        "relationship_audit_queue": relationship_audit_queue,
        "relationship_audit_queue_count": len(relationship_audit_queue),
        "relationship_audit_top_step": relationship_audit_queue[0] if relationship_audit_queue else {},
        "verification_queue": verification_queue,
        "verification_queue_count": len(verification_queue),
        "next_action": next_action,
        "basis": "risk_graph_evidence_claims_events_and_explicit_capital_edges",
    }


def _capital_relationship_audit_queue(
    *,
    capital_evidence: list[dict[str, Any]],
    capital_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for edge in capital_edges[:10]:
        evidence_ids = [str(item) for item in edge.get("evidence_ids", []) if str(item).strip()]
        missing_evidence = not evidence_ids
        queue.append(
            {
                "step_id": f"CAP-REL-AUDIT-{len(queue) + 1:03d}",
                "priority": "P0" if missing_evidence else "P1",
                "kind": "capital_relationship_missing_evidence" if missing_evidence else "capital_relationship_evidence_review",
                "target_id": edge.get("id"),
                "target_title": f"{edge.get('from_name') or edge.get('from')} -> {edge.get('to_name') or edge.get('to')}",
                "relation_type": edge.get("type"),
                "evidence_ids": evidence_ids[:8],
                "source_names": list(edge.get("source_names") or [])[:5],
                "done_condition": (
                    "attach_evidence_ids_or_remove_capital_relationship_edge"
                    if missing_evidence
                    else "confirm_counterparty_role_subject_match_and_capital_claim_provenance"
                ),
            }
        )
    if capital_evidence and not capital_edges:
        queue.append(
            {
                "step_id": "CAP-REL-AUDIT-001",
                "priority": "P0",
                "kind": "capital_relationship_mapping_required",
                "target_id": "capital_counterparty_relationships",
                "target_title": "Map lenders, pledgees, guarantors, bond parties, asset holders, or related controllers",
                "relation_type": "capital_counterparty",
                "evidence_ids": [str(item.get("id")) for item in capital_evidence[:8] if item.get("id")],
                "source_names": sorted({str(item.get("source")) for item in capital_evidence if str(item.get("source") or "").strip()})[:5],
                "done_condition": "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason",
            }
        )
    return sorted(
        queue,
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority") or "P1"), 9),
            str(item.get("kind") or ""),
            str(item.get("target_id") or ""),
        ),
    )[:12]


def _capital_verification_queue(
    *,
    capital_evidence: list[dict[str, Any]],
    capital_risk_events: list[dict[str, Any]],
    capital_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for event in capital_risk_events[:6]:
        queue.append(
            {
                "step_id": f"CAP-RISK-{len(queue) + 1:03d}",
                "priority": "P0" if str(event.get("severity")) in {"critical", "high"} else "P1",
                "kind": "risk_event_verification",
                "target_id": event.get("id"),
                "target_title": event.get("title"),
                "severity": event.get("severity"),
                "evidence_ids": list(event.get("evidence_ids") or [])[:8],
                "done_condition": "risk_event_evidence_refs_reviewed_and_capital_claim_classified_as_fact_or_lead",
            }
        )
    if capital_evidence and not capital_edges:
        queue.append(
            {
                "step_id": f"CAP-REL-{len(queue) + 1:03d}",
                "priority": "P0",
                "kind": "relationship_mapping_required",
                "target_id": "capital_counterparty_relationships",
                "target_title": "Map lender, pledgee, guarantor, bond party, asset holder, or related controller edges",
                "evidence_ids": [str(item.get("id")) for item in capital_evidence[:8] if item.get("id")],
                "done_condition": "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason",
            }
        )
    for edge in capital_edges[:6]:
        queue.append(
            {
                "step_id": f"CAP-EDGE-{len(queue) + 1:03d}",
                "priority": "P1",
                "kind": "relationship_edge_review",
                "target_id": edge.get("id"),
                "target_title": f"{edge.get('from_name') or edge.get('from')} -> {edge.get('to_name') or edge.get('to')}",
                "relation_type": edge.get("type"),
                "evidence_ids": list(edge.get("evidence_ids") or [])[:8],
                "done_condition": "capital_relationship_edge_evidence_and_counterparty_role_confirmed",
            }
        )
    for evidence in capital_evidence[:6]:
        queue.append(
            {
                "step_id": f"CAP-EVID-{len(queue) + 1:03d}",
                "priority": "P2",
                "kind": "capital_evidence_review",
                "target_id": evidence.get("id"),
                "target_title": evidence.get("title"),
                "source": evidence.get("source"),
                "url": evidence.get("url"),
                "evidence_ids": [evidence.get("id")] if evidence.get("id") else [],
                "done_condition": "capital_evidence_claims_reviewed_for_amount_date_counterparty_and_subject_match",
            }
        )
    return queue[:18]


def _current_alert_count(risk_events: list[dict[str, Any]]) -> int:
    return sum(1 for item in risk_events if str(item.get("severity")) in {"critical", "high"})


def _trimmed_claims(claims: tuple[str, ...], *, limit: int = 12, max_chars: int = 260) -> list[str]:
    trimmed: list[str] = []
    for claim in claims[:limit]:
        value = " ".join(str(claim).split())
        if len(value) > max_chars:
            value = value[: max_chars - 14].rstrip() + "...[truncated]"
        trimmed.append(value)
    return trimmed


def _context_capsule(
    result: RiskDiscoveryResult,
    evidence: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> dict[str, Any]:
    lines: list[str] = []
    for event in risk_events:
        refs = event.get("evidence_refs", [])
        source = refs[0].get("source") if refs else "unknown"
        lines.append(
            f"{event['severity']} {event['category']}: {event['title']} [source: {source}]"
        )
    for item in evidence[:12]:
        source = item.get("source") or "unknown"
        title = item.get("title") or item.get("id")
        url = item.get("url") or "no-url"
        lines.append(f"Evidence: {title} [source: {source}, url: {url}]")
    for action in result.retrieval_summary.get("next_actions", [])[:5]:
        lines.append(f"Next action: {action}")

    capsule = ContextBudgetManager(
        max_summary_chars=900,
        max_line_chars=260,
        max_evidence_lines=10,
        max_risk_lines=10,
        max_recent_lines=4,
    ).build_capsule(
        [{"ok": True, "name": "risk_graph", "text": "\n".join(lines)}],
        target=result.company,
    )
    return capsule.to_dict()


CAPITAL_TOKENS = (
    "capital",
    "debt",
    "credit",
    "financing",
    "refinancing",
    "liquidity",
    "bond",
    "pledge",
    "pledged",
    "freeze",
    "frozen",
    "auction",
    "collateral",
    "guarantee",
    "guarantor",
    "lender",
    "bank",
    "equity_fundraising",
    "convertible",
    "maturity_wall",
)
CAPITAL_PRESSURE_TOKENS = (
    "debt",
    "credit",
    "refinancing",
    "liquidity",
    "bond",
    "default",
    "pledge",
    "freeze",
    "frozen",
    "auction",
    "collateral",
    "guarantee",
    "maturity_wall",
    "pressure",
)
CAPITAL_INFLOW_TOKENS = (
    "financing_event",
    "financing",
    "fundraising",
    "offering",
    "convertible",
    "atm_program",
)
CAPITAL_RELATIONSHIP_TOKENS = (
    "lender",
    "pledgee",
    "guarantor",
    "guarantee",
    "bank",
    "bond",
    "creditor",
    "debtor",
    "collateral",
    "capital_counterparty",
    "financial_counterparty",
)


def _capital_text(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "id",
        "type",
        "category",
        "title",
        "source",
        "from_name",
        "to_name",
        "rationale",
        "severity",
    ):
        values.append(str(item.get(key) or ""))
    claims = item.get("claims")
    if isinstance(claims, list):
        values.extend(str(claim) for claim in claims)
    evidence_refs = item.get("evidence_refs")
    if isinstance(evidence_refs, list):
        values.extend(str(ref.get("source") or "") for ref in evidence_refs if isinstance(ref, dict))
    return " ".join(values).lower()


def _capital_edge_text(item: dict[str, Any]) -> str:
    values = [
        str(item.get("id") or ""),
        str(item.get("type") or ""),
        " ".join(str(source) for source in item.get("source_names", []) if str(source).strip())
        if isinstance(item.get("source_names"), list)
        else "",
    ]
    return " ".join(values).lower()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)
