"""Relationship resolution: turn evidence lanes into candidate relationship leads.

Phase 1 emits candidate leads only. It never upgrades evidence-derived
relationships to fact, even when the source evidence itself is fact-admitted.
Phase 2 preserves graph edges that were already admitted upstream.
"""

from __future__ import annotations

import re
from typing import Any


def build_relationship_resolution(evidence_v2=None, entities=None, graph=None):
    leads: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    ev = evidence_v2 or []
    ents = (entities or {}).get("resolved_entities", [])
    rg = graph or {}
    existing = rg.get("edges", [])
    seed = _seed_entity(ents)

    for item in ev:
        if not isinstance(item, dict):
            continue
        eid = item.get("evidence_id", "?")
        src = item.get("source_name") or item.get("source") or "?"
        lane = item.get("lane", "?")
        subj = item.get("subject", "")
        adm = item.get("admission", "lead")
        if adm == "fact":
            adm = "lead"

        leads.extend(_field_relationship_leads(item, seed=seed, evidence_id=eid, source_name=src, lane=lane))

        if lane == "goods":
            leads.append(_lead(f"lead-goods-{eid}", "seed", subj, "supplier_of", adm, 0.35, src, f"Goods lane evidence from {src}: {subj}", eid))
        elif lane == "people":
            leads.append(_lead(f"lead-people-{eid}", "seed", subj, "controls", "weak_lead", 0.25, src, f"People lane evidence from {src}: {subj} -- weak lead, needs corroboration", eid))
        elif lane == "capital":
            leads.append(_lead(f"lead-capital-{eid}", "seed", subj, "finances", "lead", 0.4, src, f"Capital lane evidence from {src}: {subj}", eid))

    for j, edge in enumerate(existing):
        if not isinstance(edge, dict):
            continue
        edges.append({
            "edge_id": f"edge-{j:04d}",
            "source_node": edge.get("from", "?"),
            "target_node": edge.get("to", "?"),
            "relation_type": edge.get("type", "?"),
            "confidence": edge.get("confidence", 0),
            "admission": edge.get("admission", "lead"),
            "admission_reason": edge.get("explanation", ""),
            "explanation": edge.get("explanation", ""),
            "evidence_ids": list(edge.get("evidence_ids") or []),
            "source": edge.get("source", ""),
        })

    for lead in leads:
        if lead["admission"] == "fact":
            lead["admission"] = "lead"
        if "address" in lead.get("relation_type", "") or "project" in lead.get("relation_type", ""):
            lead["admission"] = "weak_lead"

    leads = _dedupe_leads(leads)
    summary = _resolution_summary(leads, edges)
    return {
        "phase1_candidate_leads": leads,
        "lead_count": len(leads),
        "phase2_admitted_edges": edges,
        "edge_count": len(edges),
        "resolution_summary": summary,
        "version": "2.2",
        "trust_layer": {
            "dedup": True,
            "source_required": True,
            "explanation_required": True,
            "weak_lead_limit": 3,
            "field_extraction": True,
        },
        "rules": {
            "no_fact_in_leads": True,
            "same_name_no_id": "weak_lead",
            "edge_requires_source": True,
            "edge_requires_explanation": True,
            "same_address": "weak_lead",
            "from_evidence_lanes": True,
            "field_claims_to_candidate_edges": True,
        },
    }


def _field_relationship_leads(item: dict[str, Any], *, seed: str, evidence_id: Any, source_name: str, lane: str) -> list[dict[str, Any]]:
    pairs = _parse_claim_pairs(item.get("claims") or item.get("claim") or "")
    field_relations = {
        "supplier": ("supplier_of", "goods", 0.45),
        "customer": ("customer_of", "goods", 0.45),
        "counterparty": ("counterparty_of", "goods", 0.4),
        "partner": ("partner_of", "goods", 0.4),
        "controller": ("controls", "people", 0.35),
        "actual_controller": ("controls", "people", 0.35),
        "ubo": ("beneficial_owner_of", "people", 0.35),
        "beneficial_owner": ("beneficial_owner_of", "people", 0.35),
        "shareholder": ("shareholder_of", "people", 0.35),
        "creditor": ("creditor_of", "capital", 0.4),
        "lender": ("lender_to", "capital", 0.4),
        "guarantor": ("guarantor_of", "capital", 0.4),
    }
    leads: list[dict[str, Any]] = []
    for field, value in pairs.items():
        spec = field_relations.get(field)
        if not spec:
            continue
        relation_type, target_lane, confidence = spec
        # A single source row can contain cross-lane fields, e.g. supplier and
        # controller in one public-web claim. Keep the relationship as a lead
        # instead of dropping it because the normalized row picked one lane.
        if lane == "source":
            continue
        admission = "weak_lead" if target_lane == "people" and "public" in str(source_name).lower() else "lead"
        leads.append(_lead(
            f"lead-{field}-{evidence_id}",
            seed,
            value,
            relation_type,
            admission,
            confidence,
            source_name,
            f"Extracted {field} relationship from {source_name}: {value}",
            evidence_id,
            extracted_field=field,
        ))
    return leads


def _parse_claim_pairs(raw: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    claims = raw if isinstance(raw, list) else [raw]
    for claim in claims:
        for part in re.split(r"[;\n]+", str(claim or "")):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            clean_key = re.sub(r"[^a-z0-9_]", "", key.strip().lower().replace("-", "_").split()[-1])
            clean_value = value.strip().strip(" ,.;")
            if clean_key and clean_value and clean_key not in values:
                values[clean_key] = clean_value
    return values


def _seed_entity(entities: list[Any]) -> str:
    if entities and isinstance(entities[0], dict):
        return str(entities[0].get("name") or entities[0].get("entity_name") or "seed")
    return "seed"


def _lead(
    lead_id: str,
    source: str,
    target: Any,
    relation_type: str,
    admission: str,
    confidence: float,
    source_name: str,
    explanation: str,
    evidence_id: Any,
    *,
    extracted_field: str | None = None,
) -> dict[str, Any]:
    row = {
        "lead_id": lead_id,
        "from": source or "seed",
        "to": target,
        "relation_type": relation_type,
        "admission": "lead" if admission == "fact" else admission,
        "confidence": confidence,
        "source": source_name,
        "explanation": explanation,
        "evidence_ids": [evidence_id],
    }
    if extracted_field:
        row["extracted_field"] = extracted_field
    return row


def _dedupe_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for lead in leads:
        key = (
            str(lead.get("from") or "").casefold(),
            str(lead.get("to") or "").casefold(),
            str(lead.get("relation_type") or "").casefold(),
            str(lead.get("source") or "").casefold(),
        )
        current = deduped.get(key)
        if current is None or float(lead.get("confidence") or 0) > float(current.get("confidence") or 0):
            deduped[key] = lead
    return list(deduped.values())


def _resolution_summary(leads: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    by_admission: dict[str, int] = {}
    by_relation_type: dict[str, int] = {}
    by_lane: dict[str, int] = {"capital": 0, "goods": 0, "people": 0, "unknown": 0}
    source_names: list[str] = []
    verification_queue: list[dict[str, Any]] = []

    for lead in leads:
        admission = str(lead.get("admission") or "lead")
        relation_type = str(lead.get("relation_type") or "unknown")
        by_admission[admission] = by_admission.get(admission, 0) + 1
        by_relation_type[relation_type] = by_relation_type.get(relation_type, 0) + 1
        source = str(lead.get("source") or "").strip()
        if source:
            source_names.append(source)
        lane = _relationship_lane(relation_type, str(lead.get("extracted_field") or ""))
        by_lane[lane] = by_lane.get(lane, 0) + 1
        priority = _verification_priority(lead, lane)
        verification_queue.append(
            {
                "priority": priority,
                "relation_type": relation_type,
                "target": lead.get("to"),
                "admission": admission,
                "source": source,
                "evidence_ids": list(lead.get("evidence_ids") or []),
                "next_action": _verification_next_action(relation_type, lane, admission),
            }
        )

    edge_relation_types: dict[str, int] = {}
    edge_sources: list[str] = []
    for edge in edges:
        relation_type = str(edge.get("relation_type") or "unknown")
        edge_relation_types[relation_type] = edge_relation_types.get(relation_type, 0) + 1
        source = str(edge.get("source") or "").strip()
        if source:
            edge_sources.append(source)

    weak_count = by_admission.get("weak_lead", 0)
    typed_count = sum(1 for lead in leads if str(lead.get("extracted_field") or "").strip())
    lead_risk_level = "high_review_need" if weak_count >= 3 else "review_needed" if leads else "no_candidate_leads"
    verification_queue = sorted(
        verification_queue,
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority")), 9),
            str(item.get("relation_type") or ""),
            str(item.get("target") or ""),
        ),
    )
    return {
        "lead_count": len(leads),
        "typed_lead_count": typed_count,
        "weak_lead_count": weak_count,
        "admitted_edge_count": len(edges),
        "lead_risk_level": lead_risk_level,
        "by_admission": by_admission,
        "by_relation_type": by_relation_type,
        "by_lane": by_lane,
        "source_count": len(_dedupe_strings(source_names + edge_sources)),
        "source_names": _dedupe_strings(source_names + edge_sources)[:8],
        "admitted_edge_relation_types": edge_relation_types,
        "verification_queue": verification_queue[:8],
        "quality_notes": [
            "Relationship leads are not facts until corroborated by registry, filing, announcement, or licensed relationship evidence.",
            "Admitted graph edges are preserved separately from candidate leads.",
        ],
    }


def _relationship_lane(relation_type: str, extracted_field: str) -> str:
    value = f"{relation_type} {extracted_field}".lower()
    if any(marker in value for marker in ("creditor", "lender", "guarantor", "finance", "finances")):
        return "capital"
    if any(marker in value for marker in ("supplier", "customer", "counterparty", "partner")):
        return "goods"
    if any(marker in value for marker in ("control", "owner", "shareholder", "ubo", "beneficial")):
        return "people"
    return "unknown"


def _verification_priority(lead: dict[str, Any], lane: str) -> str:
    relation_type = str(lead.get("relation_type") or "").lower()
    extracted = str(lead.get("extracted_field") or "").lower()
    if lane in {"people", "capital"} or any(
        marker in f"{relation_type} {extracted}"
        for marker in ("control", "owner", "shareholder", "creditor", "lender", "guarantor")
    ):
        return "P0"
    if lane == "goods":
        return "P1"
    return "P2"


def _verification_next_action(relation_type: str, lane: str, admission: str) -> str:
    if lane == "people":
        return "verify controller/shareholder/UBO relation against registry, filings, or licensed relationship source"
    if lane == "capital":
        return "verify financing/counterparty relation against credit, bond, pledge, guarantee, or licensed capital source"
    if lane == "goods":
        return "verify supplier/customer/partner relation against public announcements, filings, contracts, or credible business sources"
    if admission == "weak_lead":
        return "corroborate weak relationship lead before report reliance"
    return "collect a second source before promoting relationship candidate"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        rows.append(cleaned)
    return rows
