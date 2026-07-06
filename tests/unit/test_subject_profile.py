#!/usr/bin/env python3
"""Tests for deep public subject profile construction."""
from __future__ import annotations

import pytest

from core.intelligence_retrieval import (
    EntityKind,
    EvidenceGraph,
    EvidenceIngestor,
    EvidenceItem,
    EvidenceType,
    InvestigationEntity,
    InvestigativeRetrievalPlanner,
    InvestigationRelation,
    RetrievalDomain,
    SourceCatalog,
)
from core.subject_profile import (
    RecursionPolicy,
    SubjectProfileBuilder,
    SubjectProfileDimension,
)


def test_subject_profile_surfaces_controller_and_high_sensitivity_public_leads() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Credit Co., Ltd.")
    seed_id = "company:demo_credit_co.,_ltd."
    task = plan.by_domain(RetrievalDomain.OWNERSHIP_CONTROL)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "registry_public_api",
                "source_type": "official_platform",
                "source_hint": "registry_sources",
                "entity": "Demo Credit Co., Ltd.",
                "title": "Demo Credit Co., Ltd. registry profile",
                "summary": (
                    "Public registry profile. Controller Bob Li. "
                    "Registered address No. 1 Finance Road."
                ),
                "url": "https://example.invalid/registry/demo",
                "published_at": "2026-06-18",
                "confidence": 0.87,
                "raw": {
                    "actual_controller": {"name": "Bob Li"},
                    "registered_address": "No. 1 Finance Road",
                    "asset": "Public real estate mortgage notice",
                },
                "evidence": [
                    {"claim": "Bob Li is listed as actual controller candidate."},
                    {"claim": "Public real estate mortgage notice indicates solvency lead."},
                    {"claim": "Traffic violation and administrative penalty leads require verification."},
                    {"claim": "Public delivery address and activity city require corroboration."},
                    {"claim": "Public social post statement requires business relevance review."},
                ],
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert profile["recursion_policy"]["default_depth"] == 3
    assert profile["controller_candidates"]
    assert profile["controller_candidates"][0]["name"] == "Bob Li"
    assert profile["signals_by_dimension"][SubjectProfileDimension.CONTROL_OWNERSHIP.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.ASSET_SOLVENCY.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.BEHAVIORAL_RISK.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.LOCATION_ACTIVITY.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.PUBLIC_STATEMENTS.value]

    high_sensitivity = [
        signal
        for signals in profile["signals_by_dimension"].values()
        for signal in signals
        if signal["sensitivity"] == "high"
    ]
    assert high_sensitivity
    assert all(signal["evidence_ids"] for signal in high_sensitivity)
    assert all(signal["verification_status"] for signal in high_sensitivity)
    assert all(signal["business_relevance"] for signal in high_sensitivity)


def test_subject_profile_deduplicates_controller_candidates_and_keeps_sources() -> None:
    graph = EvidenceGraph()
    root = "company:demo_controller_co."
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Demo Controller Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity("person:tim_cook_a", EntityKind.PERSON, "Tim Cook", 0.8, [])
    )
    evidence_a = EvidenceItem(
        id="evidence:wikidata",
        evidence_type=EvidenceType.DATABASE_RESULT,
        source="wikidata_public_entity_graph",
        title="Wikidata key people",
        confidence=0.7,
        source_profile=SourceCatalog.profile_for("wikidata_public_entity_graph"),
    )
    evidence_b = EvidenceItem(
        id="evidence:registry",
        evidence_type=EvidenceType.REGISTRY_RECORD,
        source="registry_public_api",
        title="Registry controller",
        confidence=0.9,
        source_profile=SourceCatalog.profile_for("registry_sources"),
    )
    graph.add_evidence(evidence_a)
    graph.add_evidence(evidence_b)
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:tim_cook_a",
            relation_type="chief_executive_officer",
            confidence=0.7,
            evidence_ids=(evidence_a.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:tim_cook_a",
            relation_type="beneficial_owner",
            confidence=0.9,
            evidence_ids=(evidence_b.id,),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()

    candidates = [item for item in profile["controller_candidates"] if item["name"] == "Tim Cook"]
    assert len(candidates) == 1
    assert candidates[0]["relation_type"] == "beneficial_owner"
    assert candidates[0]["relation_types"] == ["beneficial_owner", "chief_executive_officer"]
    assert candidates[0]["confidence"] == 0.9
    assert candidates[0]["evidence_ids"] == ["evidence:registry", "evidence:wikidata"]
    relationship_edges = profile["relationship_graph"]["edges"]
    registry_edge = next(item for item in relationship_edges if item["relation_type"] == "beneficial_owner")
    wikidata_edge = next(item for item in relationship_edges if item["relation_type"] == "chief_executive_officer")
    assert registry_edge["admission"] == "fact"
    assert registry_edge["source_strength"] >= 5
    assert registry_edge["source_names"] == ["registry_public_api"]
    assert wikidata_edge["admission"] == "lead"
    assert candidates[0]["source_names"] == ["registry_public_api", "wikidata_public_entity_graph"]
    assert candidates[0]["confidence_basis"]
    assert candidates[0]["confidence_tier"] in {"verified_fact", "corroborated_fact"}


def test_subject_profile_ranks_licensed_controller_fact_above_weak_public_lead() -> None:
    graph = EvidenceGraph()
    root = "company:demo_ubo_co."
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Demo UBO Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity("person:weak_public_lead", EntityKind.PERSON, "Weak Public Lead", 0.9, [])
    )
    graph.add_entity(
        InvestigationEntity(
            "person:licensed_owner",
            EntityKind.PERSON,
            "Licensed Owner",
            0.78,
            [],
            {"control_path": "Demo UBO Co. -> Licensed Owner", "confidence_basis": "licensed registry module"},
        )
    )
    public_evidence = EvidenceItem(
        id="evidence:public-web",
        evidence_type=EvidenceType.WEBPAGE,
        source="public_web_search",
        title="Public executive lead",
        confidence=0.82,
        source_profile=SourceCatalog.profile_for("web_search"),
        entity_match={"level": "strong", "score": 0.84},
    )
    licensed_evidence = EvidenceItem(
        id="evidence:qyyjt-licensed",
        evidence_type=EvidenceType.DATABASE_RESULT,
        source="qyyjt_api:actual_controller",
        title="Licensed controller record",
        confidence=0.78,
        source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
        entity_match={"level": "exact", "score": 1.0},
    )
    graph.add_evidence(public_evidence)
    graph.add_evidence(licensed_evidence)
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:weak_public_lead",
            relation_type="chief_executive_officer",
            confidence=0.9,
            evidence_ids=(public_evidence.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:licensed_owner",
            relation_type="actual_controller",
            confidence=0.78,
            evidence_ids=(licensed_evidence.id,),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()
    candidates = profile["controller_candidates"]

    assert candidates[0]["name"] == "Licensed Owner"
    assert candidates[0]["confidence_tier"] == "verified_fact"
    assert candidates[0]["match_score"] == 1.0
    assert "Demo UBO Co. -> Licensed Owner" in candidates[0]["control_paths"]
    assert candidates[1]["name"] == "Weak Public Lead"
    assert candidates[1]["confidence_tier"] == "weak_public_lead"


def test_subject_profile_formats_controller_alias_path_nodes_from_ingested_records() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Alias UBO Co.")
    seed_id = "company:demo_alias_ubo_co."
    task = plan.by_domain(RetrievalDomain.OWNERSHIP_CONTROL)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "licensed_registry_api",
                "source_type": "rest_api",
                "entity": "Demo Alias UBO Co.",
                "title": "Demo Alias UBO Co. UBO record",
                "confidence": 0.9,
                "raw": {
                    "ultimateBeneficialOwner": {
                        "beneficialOwnerName": "Alice Ultimate",
                        "shareRatio": "72%",
                        "pathNodes": [
                            "Demo Alias UBO Co.",
                            {"name": "Demo Parent Co."},
                            "Alice Ultimate",
                        ],
                        "basis": "licensed UBO profile",
                    }
                },
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()
    candidate = profile["controller_candidates"][0]

    assert candidate["name"] == "Alice Ultimate"
    assert candidate["relation_type"] == "beneficial_owner"
    assert "ownership_ratio:72%" in candidate["confidence_basis"]
    assert "licensed UBO profile" in candidate["confidence_basis"]
    assert "Demo Alias UBO Co. -> Demo Parent Co. -> Alice Ultimate" in candidate["control_paths"]


def test_subject_profile_derives_indirect_controller_path_from_relationship_graph() -> None:
    graph = EvidenceGraph()
    root = "company:demo_indirect_co."
    parent = "company:demo_parent_holdings"
    owner = "person:ultimate_owner"
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Demo Indirect Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity(parent, EntityKind.COMPANY, "Demo Parent Holdings", 0.92, [])
    )
    graph.add_entity(
        InvestigationEntity(owner, EntityKind.PERSON, "Alice Ultimate", 0.86, [])
    )
    evidence = EvidenceItem(
        id="evidence:licensed-ubo-path",
        evidence_type=EvidenceType.DATABASE_RESULT,
        source="qyyjt_api:ubo_path",
        title="Licensed UBO path",
        confidence=0.88,
        source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
        entity_match={"level": "exact", "score": 1.0},
    )
    graph.add_evidence(evidence)
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id=parent,
            relation_type="majority_shareholder",
            confidence=0.87,
            evidence_ids=(evidence.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id=parent,
            to_id=owner,
            relation_type="beneficial_owner",
            confidence=0.86,
            evidence_ids=(evidence.id,),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()
    candidate = profile["controller_candidates"][0]

    assert candidate["name"] == "Alice Ultimate"
    assert candidate["relation_type"] == "beneficial_owner"
    assert candidate["confidence_tier"] == "verified_fact"
    assert "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate" in candidate["control_paths"]
    assert not any("controller and beneficial-owner evidence" in gap for gap in profile["evidence_gaps"])


def test_subject_profile_exposes_structured_multi_layer_control_path_summary() -> None:
    graph = EvidenceGraph()
    root = "company:demo_nested_co."
    holding = "company:demo_holding_ltd"
    vehicle = "company:demo_family_vehicle"
    owner = "person:alice_ultimate"
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Demo Nested Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity(holding, EntityKind.COMPANY, "Demo Holding Ltd", 0.91, [])
    )
    graph.add_entity(
        InvestigationEntity(vehicle, EntityKind.COMPANY, "Demo Family Vehicle", 0.9, [])
    )
    graph.add_entity(
        InvestigationEntity(owner, EntityKind.PERSON, "Alice Ultimate", 0.89, [])
    )
    evidence = [
        EvidenceItem(
            id="evidence:shareholder",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="qyyjt_api:shareholder",
            title="Licensed shareholder layer",
            confidence=0.89,
            source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
            entity_match={"level": "exact", "score": 1.0},
        ),
        EvidenceItem(
            id="evidence:group",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="qyyjt_api:group_network",
            title="Licensed group layer",
            confidence=0.87,
            source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
            entity_match={"level": "exact", "score": 0.97},
        ),
        EvidenceItem(
            id="evidence:ubo",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="qyyjt_api:ubo_path",
            title="Licensed UBO layer",
            confidence=0.86,
            source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
            entity_match={"level": "exact", "score": 0.96},
        ),
    ]
    for item in evidence:
        graph.add_evidence(item)
    graph.add_relation(
        InvestigationRelation(root, holding, "majority_shareholder", 0.89, ("evidence:shareholder",))
    )
    graph.add_relation(
        InvestigationRelation(holding, vehicle, "controlling_shareholder", 0.87, ("evidence:group",))
    )
    graph.add_relation(
        InvestigationRelation(vehicle, owner, "beneficial_owner", 0.86, ("evidence:ubo",))
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()
    candidate = profile["controller_candidates"][0]
    summary = candidate["control_path_summaries"][0]

    assert candidate["name"] == "Alice Ultimate"
    assert "Demo Nested Co. -> Demo Holding Ltd -> Demo Family Vehicle -> Alice Ultimate" in candidate["control_paths"]
    assert summary["path_text"] == "Demo Nested Co. -> Demo Holding Ltd -> Demo Family Vehicle -> Alice Ultimate"
    assert summary["hop_count"] == 3
    assert summary["relation_types"] == [
        "majority_shareholder",
        "controlling_shareholder",
        "beneficial_owner",
    ]
    assert summary["source_names"] == [
        "qyyjt_api:group_network",
        "qyyjt_api:shareholder",
        "qyyjt_api:ubo_path",
    ]
    assert summary["source_families"] == ["licensed_commercial"]
    assert summary["source_family_summary"]["top_family"] == "licensed_commercial"
    assert summary["source_family_summary"]["has_official_or_authorized"] is True
    assert candidate["source_families"] == ["licensed_commercial"]
    assert summary["evidence_ids"] == ["evidence:group", "evidence:shareholder", "evidence:ubo"]
    assert summary["admission"] == "fact"
    assert summary["source_strength"] >= 4
    assert summary["min_confidence"] == 0.86


def test_subject_profile_summarizes_control_source_families_across_major_feeds() -> None:
    graph = EvidenceGraph()
    root = "company:demo_cross_source_co."
    parent = "company:demo_registry_parent"
    holding = "company:demo_gleif_holding"
    owner = "person:alice_cross_source"
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Demo Cross Source Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity(parent, EntityKind.COMPANY, "Demo Registry Parent", 0.92, [])
    )
    graph.add_entity(
        InvestigationEntity(holding, EntityKind.COMPANY, "Demo GLEIF Holding", 0.9, [])
    )
    graph.add_entity(
        InvestigationEntity(owner, EntityKind.PERSON, "Alice Cross Source", 0.88, [])
    )
    evidence = [
        EvidenceItem(
            id="evidence:registry-parent",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="official_registry",
            title="Official registry shareholder layer",
            confidence=0.9,
            source_profile=SourceCatalog.profile_for("registry_sources"),
            entity_match={"level": "exact", "score": 1.0},
        ),
        EvidenceItem(
            id="evidence:gleif-parent",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="gleif_lei_public_api",
            title="GLEIF parent layer",
            confidence=0.86,
            source_profile=SourceCatalog.profile_for("gleif_lei_public_api"),
            entity_match={"level": "exact", "score": 0.98},
        ),
        EvidenceItem(
            id="evidence:qyyjt-ubo",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="qyyjt_api:ubo_path",
            title="QYYJT UBO terminal layer",
            confidence=0.87,
            source_profile=SourceCatalog.profile_for("registry_and_commercial_sources"),
            entity_match={"level": "exact", "score": 0.99},
        ),
        EvidenceItem(
            id="evidence:sec-officer",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="sec_edgar_public_api",
            title="SEC officer corroboration",
            confidence=0.82,
            source_profile=SourceCatalog.profile_for("sec_edgar_public_api"),
            entity_match={"level": "exact", "score": 0.97},
        ),
        EvidenceItem(
            id="evidence:wikidata-board",
            evidence_type=EvidenceType.DATABASE_RESULT,
            source="wikidata_public_entity_graph",
            title="Wikidata board corroboration",
            confidence=0.68,
            source_profile=SourceCatalog.profile_for("wikidata_public_entity_graph"),
            entity_match={"level": "exact", "score": 0.95},
        ),
    ]
    for item in evidence:
        graph.add_evidence(item)
    graph.add_relation(InvestigationRelation(root, parent, "majority_shareholder", 0.9, ("evidence:registry-parent",)))
    graph.add_relation(InvestigationRelation(parent, holding, "ultimate_parent", 0.86, ("evidence:gleif-parent",)))
    graph.add_relation(
        InvestigationRelation(
            holding,
            owner,
            "beneficial_owner",
            0.87,
            ("evidence:qyyjt-ubo", "evidence:sec-officer", "evidence:wikidata-board"),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()
    candidate = next(item for item in profile["controller_candidates"] if item["name"] == "Alice Cross Source")
    family_names = {item["family"] for item in candidate["source_family_summary"]["families"]}
    multi_layer = next(
        summary for summary in candidate["control_path_summaries"]
        if summary["path_text"] == "Demo Cross Source Co. -> Demo Registry Parent -> Demo GLEIF Holding -> Alice Cross Source"
    )
    edge = next(
        item for item in profile["relationship_graph"]["edges"]
        if item["relation_type"] == "ultimate_parent"
    )

    assert candidate["confidence_tier"] == "corroborated_fact"
    assert family_names == {
        "official_registry",
        "official_public_gleif",
        "licensed_commercial",
        "official_public_sec",
        "public_knowledge_graph",
    }
    assert candidate["source_family_summary"]["has_official_or_authorized"] is True
    assert multi_layer["hop_count"] == 3
    assert multi_layer["source_families"] == [
        "licensed_commercial",
        "official_public_gleif",
        "official_public_sec",
        "official_registry",
        "public_knowledge_graph",
    ]
    assert multi_layer["source_family_summary"]["policy"].startswith("Source families explain")
    assert edge["source_families"] == ["official_public_gleif"]


def test_subject_profile_uses_gleif_parent_relationship_entities() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo GLEIF Child Ltd")
    seed_id = "company:demo_gleif_child_ltd"
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "gleif_lei_public_api",
                "source_type": "rest_api",
                "source_hint": "gleif_lei_public_api",
                "entity": "Demo GLEIF Child Ltd",
                "title": "GLEIF LEI record: Demo GLEIF Child Ltd",
                "summary": "LEI=549300CHILD; relationships=ultimate_parent:Demo Ultimate Parent Ltd",
                "confidence": 0.86,
                "lei": "549300CHILD",
                "entities": [
                    {
                        "kind": "company",
                        "name": "Demo Ultimate Parent Ltd",
                        "relation": "ultimate_parent",
                        "confidence": 0.76,
                        "source": "GLEIF",
                        "lei": "549300PARENT",
                    }
                ],
                "raw": {"lei": "549300CHILD"},
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert any(
        edge["relation_type"] == "ultimate_parent"
        and edge["to_id"] == "company:demo_ultimate_parent_ltd"
        for edge in profile["relationship_graph"]["edges"]
    )
    assert not any("relationship-network evidence" in gap for gap in profile["evidence_gaps"])


def test_subject_profile_uses_gleif_relationship_edge_records() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo GLEIF Child Ltd")
    seed_id = "company:demo_gleif_child_ltd"
    task = plan.by_domain(RetrievalDomain.RELATED_ENTITIES)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "gleif_lei_relationship_traversal_public_api",
                "source_type": "rest_api",
                "source_hint": "gleif_lei_relationship_traversal_public_api",
                "record_type": "gleif_relationship_edge",
                "entity": "Demo GLEIF Child Ltd",
                "title": "GLEIF relationship edge: Demo GLEIF Child Ltd -> Demo Direct Parent Ltd",
                "summary": "subject_lei=549300CHILD; related_lei=549300PARENT; relationship_type=direct_parent",
                "confidence": 0.78,
                "subject_lei": "549300CHILD",
                "related_lei": "549300PARENT",
                "relationship_type": "direct_parent",
                "relationship_status": "reported",
                "entities": [
                    {
                        "kind": "company",
                        "name": "Demo Direct Parent Ltd",
                        "relation": "direct_parent",
                        "confidence": 0.76,
                        "source": "GLEIF",
                        "lei": "549300PARENT",
                    }
                ],
                "evidence": [
                    {
                        "type": "official_public_api_relation",
                        "provider": "GLEIF",
                        "subject_lei": "549300CHILD",
                        "related_lei": "549300PARENT",
                        "relationship_type": "direct_parent",
                        "source_url": "https://api.gleif.org/api/v1/lei-records/549300CHILD/relationships",
                    }
                ],
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert any(
        edge["relation_type"] == "direct_parent"
        and edge["to_id"] == "company:demo_direct_parent_ltd"
        and "official_public_gleif" in edge["source_families"]
        for edge in profile["relationship_graph"]["edges"]
    )


def test_subject_profile_uses_sec_structured_key_people_as_controller_candidates() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "sec",
                "source_type": "rest_api",
                "source_hint": "sec_edgar_public_api",
                "entity": "Apple Inc.",
                "title": "SEC EDGAR submissions: Apple Inc.",
                "summary": "CIK=0000320193; key_people=chief_executive_officer:Tim Cook",
                "confidence": 0.84,
                "cik": "0000320193",
                "entity_match": {
                    "seed_name": "Apple Inc.",
                    "candidate_name": "Apple Inc.",
                    "score": 0.98,
                    "level": "exact",
                    "reasons": ["SEC CIK endpoint returned a single official company record"],
                    "identifiers": {"cik": "0000320193"},
                },
                "entities": [
                    {
                        "kind": "person",
                        "name": "Tim Cook",
                        "relation": "chief_executive_officer",
                        "confidence": 0.7,
                        "source": "SEC EDGAR",
                        "position": "Chief Executive Officer",
                        "confidence_basis": "structured SEC public submission field",
                    }
                ],
                "evidence": [
                    {
                        "type": "official_public_api",
                        "provider": "SEC EDGAR",
                        "cik": "0000320193",
                        "key_people_count": 1,
                    }
                ],
                "raw": {"cik": "0000320193", "name": "Apple Inc."},
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()
    candidate = next(item for item in profile["controller_candidates"] if item["name"] == "Tim Cook")

    assert candidate["relation_type"] == "chief_executive_officer"
    assert candidate["confidence_tier"] == "verified_fact"
    assert "structured SEC public submission field" in candidate["confidence_basis"]
    assert not any("controller and beneficial-owner evidence" in gap for gap in profile["evidence_gaps"])


def test_subject_profile_uses_wikidata_board_members_and_owner_of_relationships() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "wikidata_public_entity_graph",
                "source_type": "rest_api",
                "source_hint": "wikidata_public_entity_graph",
                "entity": "Apple Inc.",
                "title": "Wikidata entity data: Apple Inc.",
                "summary": "wikidata_id=Q312; relationships=board_member:Andrea Jung, owner_of:Google LLC",
                "confidence": 0.7,
                "wikidata_id": "Q312",
                "entity_match": {
                    "seed_name": "Apple Inc.",
                    "candidate_name": "Apple Inc.",
                    "score": 0.96,
                    "level": "exact",
                    "identifiers": {"wikidata_id": "Q312"},
                },
                "entities": [
                    {
                        "kind": "person",
                        "name": "Andrea Jung",
                        "relation": "board_member",
                        "confidence": 0.68,
                        "source": "Wikidata",
                        "wikidata_id": "Q209225",
                    },
                    {
                        "kind": "company",
                        "name": "Google LLC",
                        "relation": "owner_of",
                        "confidence": 0.66,
                        "source": "Wikidata",
                        "wikidata_id": "Q95",
                    },
                ],
                "evidence": [
                    {
                        "type": "public_knowledge_graph_relation",
                        "provider": "Wikidata",
                        "relation": "board_member",
                        "name": "Andrea Jung",
                        "wikidata_id": "Q209225",
                    },
                    {
                        "type": "public_knowledge_graph_relation",
                        "provider": "Wikidata",
                        "relation": "owner_of",
                        "name": "Google LLC",
                        "wikidata_id": "Q95",
                    },
                ],
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()
    candidate = next(item for item in profile["controller_candidates"] if item["name"] == "Andrea Jung")

    assert candidate["relation_type"] == "board_member"
    assert candidate["confidence_tier"] in {"strong_public_lead", "weak_public_lead"}
    assert "relation_type:board_member" in candidate["confidence_basis"]
    assert any(
        edge["relation_type"] == "owner_of" and edge["to_id"] == "company:google_llc"
        for edge in profile["relationship_graph"]["edges"]
    )


@pytest.mark.parametrize("record_source_type", ["query_plan", "Rich_Query_Plan"])
def test_subject_profile_excludes_query_plan_controller_relation_from_candidates(record_source_type: str) -> None:
    graph = EvidenceGraph()
    root = "company:query_plan_controller_co."
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Query Plan Controller Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity("person:lead_only", EntityKind.PERSON, "Lead Only", 0.7, [])
    )
    evidence = EvidenceItem(
        id="evidence:qyyjt-plan",
        evidence_type=EvidenceType.DERIVED_CLUE,
        source="qyyjt_websearch_plan",
        title="Generated controller search query",
        confidence=0.3,
        source_profile=SourceCatalog.profile_for("web_search"),
        entity_match={"record_source_type": record_source_type, "score": 0.0},
    )
    graph.add_evidence(evidence)
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:lead_only",
            relation_type="actual_controller",
            confidence=0.3,
            evidence_ids=(evidence.id,),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()

    assert profile["controller_candidates"] == []


@pytest.mark.parametrize("match_level", ["weak", "review"])
def test_subject_profile_keeps_official_weak_match_relationship_as_lead(match_level: str) -> None:
    graph = EvidenceGraph()
    root = "company:weak_official_match_co."
    related = "company:lookalike_related_co."
    graph.add_entity(
        InvestigationEntity(root, EntityKind.COMPANY, "Weak Official Match Co.", 1.0, [], {"seed": True})
    )
    graph.add_entity(
        InvestigationEntity(related, EntityKind.COMPANY, "Lookalike Related Co.", 0.86, [])
    )
    evidence = EvidenceItem(
        id="evidence:official-weak-match",
        evidence_type=EvidenceType.DATABASE_RESULT,
        source="official_registry",
        title="Official registry relation with weak subject match",
        confidence=0.91,
        source_profile=SourceCatalog.profile_for("registry_sources"),
        entity_match={"level": match_level, "score": 0.54},
    )
    graph.add_evidence(evidence)
    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id=related,
            relation_type="shareholder",
            confidence=0.88,
            evidence_ids=(evidence.id,),
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=root).to_dict()
    edge = profile["relationship_graph"]["edges"][0]

    assert edge["admission"] == "lead"
    assert edge["evidence_ids"] == ["evidence:official-weak-match"]


def test_subject_profile_recursion_depth_is_configurable_and_capped() -> None:
    graph = EvidenceGraph()
    root = "company:root_co."
    evidence = EvidenceItem(
        id="evidence:relationship_fixture",
        evidence_type=EvidenceType.WEBPAGE,
        source="relationship_fixture",
        title="Public relationship fixture",
        confidence=0.7,
        source_profile=SourceCatalog.profile_for("web_search"),
    )
    graph.add_evidence(evidence)
    for entity in [
        InvestigationEntity(root, EntityKind.COMPANY, "Root Co.", 1.0, [evidence.id], {"seed": True}),
        InvestigationEntity("person:person_a", EntityKind.PERSON, "Person A", 0.7, [evidence.id]),
        InvestigationEntity("company:company_b", EntityKind.COMPANY, "Company B", 0.7, [evidence.id]),
        InvestigationEntity("person:person_c", EntityKind.PERSON, "Person C", 0.7, [evidence.id]),
        InvestigationEntity("company:company_d", EntityKind.COMPANY, "Company D", 0.7, [evidence.id]),
    ]:
        graph.add_entity(entity)

    graph.add_relation(
        InvestigationRelation(
            from_id=root,
            to_id="person:person_a",
            relation_type="related_subject",
            confidence=0.7,
            evidence_ids=(evidence.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id="person:person_a",
            to_id="company:company_b",
            relation_type="related_subject",
            confidence=0.7,
            evidence_ids=(evidence.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id="company:company_b",
            to_id="person:person_c",
            relation_type="related_subject",
            confidence=0.7,
            evidence_ids=(evidence.id,),
        )
    )
    graph.add_relation(
        InvestigationRelation(
            from_id="person:person_c",
            to_id="company:company_d",
            relation_type="related_subject",
            confidence=0.7,
            evidence_ids=(evidence.id,),
        )
    )

    depth_two_profile = SubjectProfileBuilder(
        RecursionPolicy(default_depth=2, max_subjects=10)
    ).build(graph, seed_subject_id=root)
    depth_three_profile = SubjectProfileBuilder(
        RecursionPolicy(default_depth=3, max_subjects=10)
    ).build(graph, seed_subject_id=root)

    assert "company:company_b" in depth_two_profile.subjects
    assert "person:person_c" not in depth_two_profile.subjects
    assert "person:person_c" in depth_three_profile.subjects
    assert "company:company_d" not in depth_three_profile.subjects


def test_subject_profile_can_hide_high_sensitivity_leads_by_policy() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Sensitive Demo Co.")
    seed_id = "company:sensitive_demo_co."
    task = plan.by_domain(RetrievalDomain.LOCATION_ASSETS)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "public_asset_fixture",
                "source_type": "web_page",
                "source_hint": "asset_and_location_sources",
                "entity": "Sensitive Demo Co.",
                "title": "Public asset and delivery address notice",
                "summary": "Public delivery address and vehicle asset lead.",
                "url": "https://example.invalid/assets/demo",
                "confidence": 0.7,
                "raw": {
                    "registered_address": "No. 9 Public Road",
                    "asset": "Vehicle collateral public notice",
                },
                "evidence": [{"claim": "Vehicle collateral public notice."}],
            }
        ],
    )

    profile = SubjectProfileBuilder(
        RecursionPolicy(include_high_sensitivity_leads=False)
    ).build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert profile["signals_by_dimension"][SubjectProfileDimension.ASSET_SOLVENCY.value] == []
    assert profile["signals_by_dimension"][SubjectProfileDimension.LOCATION_ACTIVITY.value] == []


def test_subject_profile_excludes_review_level_candidate_evidence_from_profile_dimensions() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "gleif_lei_public_api",
                "source_type": "rest_api",
                "source_hint": "gleif_lei_public_api",
                "entity": "APPLE QUEST, INC.",
                "title": "GLEIF LEI record: APPLE QUEST, INC.",
                "summary": (
                    "LEI=549300OFQZDF71H5ZN34; registered_address="
                    "1380 COOLIDGE STREET, CONKLIN, US-MI, 49403, US"
                ),
                "confidence": 0.86,
                "raw": {"lei": "549300OFQZDF71H5ZN34"},
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert profile["signals_by_dimension"][SubjectProfileDimension.LOCATION_ACTIVITY.value] == []


@pytest.mark.parametrize("source_type", ["query_plan", "Rich_Query_Plan"])
def test_subject_profile_excludes_query_plan_entities_from_profile_signals(source_type: str) -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "qyyjt_websearch_plan",
                "source_type": source_type,
                "source_hint": "qyyjt_websearch_plan",
                "entity": "Apple Inc.",
                "title": "QYYJT lead: RISK_SCAN",
                "summary": "Review public court portal wenshu.court.gov.cn for follow-up.",
                "confidence": 0.3,
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    all_values = [
        signal["value"]
        for signals in profile["signals_by_dimension"].values()
        for signal in signals
    ]
    assert "wenshu.court.gov.cn" not in all_values
    assert not any(entity.kind is EntityKind.DOMAIN for entity in plan.graph.entities.values())
    assert not any(
        edge["relation_type"] == "public_web_footprint"
        for edge in profile["relationship_graph"]["edges"]
    )


def test_subject_profile_classifies_chinese_public_profile_dimensions() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("中文线索样例公司")
    seed_id = "company:中文线索样例公司"
    task = plan.by_domain(RetrievalDomain.LOCATION_ASSETS)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "public_chinese_fixture",
                "source_type": "web_page",
                "source_hint": "asset_and_location_sources",
                "entity": "中文线索样例公司",
                "title": "公开不动产、车辆、处罚、地址和发文线索",
                "summary": "公开资料提到不动产抵押、车辆、行政处罚、公开联系地址线索、公开场景评价和公众号发文。",
                "url": "https://example.invalid/chinese-profile",
                "confidence": 0.72,
                "evidence": [
                    {"claim": "公开不动产抵押和车辆线索。"},
                    {"claim": "行政处罚和违章线索需要核验。"},
                    {"claim": "公开联系地址线索、公开场景评价和公众号发文均来自公开页面。"},
                ],
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert profile["signals_by_dimension"][SubjectProfileDimension.ASSET_SOLVENCY.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.BEHAVIORAL_RISK.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.LOCATION_ACTIVITY.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.CONSUMPTION_PREFERENCE.value]
    assert profile["signals_by_dimension"][SubjectProfileDimension.PUBLIC_STATEMENTS.value]


def test_subject_profile_merges_duplicate_signals_without_losing_evidence() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Duplicate Signal Co.")
    seed_id = "company:duplicate_signal_co."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "official_public_api_a",
                "source_type": "rest_api",
                "entity": "Duplicate Signal Co.",
                "title": "Registry record A",
                "summary": "Website: https://duplicate.example.com/profile",
                "url": "https://duplicate.example.com/a",
                "confidence": 0.70,
            },
            {
                "source_name": "official_public_api_b",
                "source_type": "rest_api",
                "entity": "Duplicate Signal Co.",
                "title": "Registry record B",
                "summary": "Website: https://duplicate.example.com/profile",
                "url": "https://duplicate.example.com/b",
                "confidence": 0.80,
            },
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()
    matches = [
        signal
        for signal in profile["signals_by_dimension"][SubjectProfileDimension.CONTACT_ACCOUNTS.value]
        if signal["value"] == "duplicate.example.com"
        and signal["subject_id"] == seed_id
        and signal["relation_type"] == "public_web_footprint"
    ]

    assert len(matches) == 1
    assert len(matches[0]["evidence_ids"]) == 2
    assert matches[0]["source_names"] == ["official_public_api_a", "official_public_api_b"]


def test_subject_profile_does_not_report_relationship_gap_when_graph_has_edges() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Relationship Gap Co.")
    seed_id = "company:relationship_gap_co."
    task = plan.by_domain(RetrievalDomain.RELATED_ENTITIES)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "public_relationship_fixture",
                "source_type": "web_page",
                "entity": "Relationship Gap Co.",
                "title": "Public relationship network lead",
                "summary": "Shared address and related person lead.",
                "confidence": 0.8,
                "raw": {
                    "related_person": "Jane Doe",
                    "shared_address": "No. 1 Test Street",
                },
                "evidence": [{"claim": "Jane Doe is a related public lead."}],
            }
        ],
    )

    profile = SubjectProfileBuilder().build(plan.graph, seed_subject_id=seed_id).to_dict()

    assert profile["relationship_graph"]["edges"]
    assert not any("relationship-network evidence" in gap for gap in profile["evidence_gaps"])


def test_extract_company_brand_parser() -> None:
    from core.subject_profile import _extract_company_brand
    assert "百度" in _extract_company_brand("百度在线网络技术（北京）有限公司")
    assert "华为" in _extract_company_brand("华为技术有限公司")
    assert "腾讯" in _extract_company_brand("腾讯控股有限公司")
    assert "阿里巴巴" in _extract_company_brand("阿里巴巴（中国）有限公司")
    assert len(_extract_company_brand("普通小店"))<=10


def test_subject_profile_exposes_company_brand_identity_signal() -> None:
    graph = EvidenceGraph()
    entity_id = "company:baidu_online"
    graph.add_entity(
        InvestigationEntity(
            id=entity_id,
            kind=EntityKind.COMPANY,
            name="百度在线网络技术（北京）有限公司",
            confidence=0.86,
        )
    )

    profile = SubjectProfileBuilder().build(graph, seed_subject_id=entity_id).to_dict()
    identity_values = {
        signal["title"]: signal["value"]
        for signal in profile["signals_by_dimension"][SubjectProfileDimension.IDENTITY.value]
    }

    assert identity_values["Company brand"] == "百度在线网络技术"

def test_relationship_edge_explainability():
    from core.subject_profile import SubjectProfileBuilder
    sb=SubjectProfileBuilder()
    class FakeRel:
        from_name="Alice";to_name="Demo Co.";relation_type="controller"
        confidence=0.85;source_name="qyyjt_api";evidence_ids=["e1","e2"]
        basis="工商登记实控人";description=""
    class FakeGraph:
        relations=[FakeRel()];entities={}
    profile={}
    result=sb._explain_relationship_edges(FakeGraph(),profile)
    edges=result.get("relationship_edges",[])
    assert len(edges)==1
    assert edges[0]["relation_type"]=="controller"
    assert edges[0]["source_name"]=="qyyjt_api"
    assert "e1" in edges[0]["evidence_ids"]

def test_relationship_edge_dedup():
    from core.subject_profile import SubjectProfileBuilder
    sb=SubjectProfileBuilder()
    class FakeRel:
        def __init__(self,f,t,r,c):
            self.from_name=f;self.to_name=t;self.relation_type=r
            self.confidence=c;self.source_name="";self.evidence_ids=[]
            self.basis="";self.description=""
    rels=[FakeRel("A","B","owns",0.5),FakeRel("A","B","owns",0.9)]
    class FakeGraph:
        relations=rels;entities={}
    profile={}
    result=sb._explain_relationship_edges(FakeGraph(),profile)
    edges=result.get("relationship_edges",[])
    assert len(edges)==1
    assert edges[0]["confidence"]==0.9


def test_graph_edge_explainability():
    from core.subject_profile import _explain_relationship_edges
    class R:
        def __init__(self,f,t,rt,c,sn,eid,b):
            self.from_name=f;self.to_name=t;self.relation_type=rt
            self.confidence=c;self.source_name=sn;self.evidence_ids=eid
            self.basis=b;self.description="";self.from_id="";self.to_id=""
    class G:
        def __init__(self):self.relations=[R("A","B","controller",0.85,"qyyjt_api",["e1"],"工商实控")]
    r = _explain_relationship_edges(G(), {})
    es = r.get("relationship_edges", [])
    assert len(es) == 1 and es[0]["source_name"] == "qyyjt_api" and "e1" in es[0]["evidence_ids"]

def test_graph_edge_dedup():
    from core.subject_profile import _explain_relationship_edges
    class R:
        def __init__(self,f,t,rt,c):self.from_name=f;self.to_name=t;self.relation_type=rt;self.confidence=c;self.source_name="";self.evidence_ids=[];self.basis="";self.description="";self.from_id="";self.to_id=""
    class G:
        def __init__(self):self.relations=[R("A","B","owns",0.5),R("A","B","owns",0.9)]
    r = _explain_relationship_edges(G(), {})
    es = r.get("relationship_edges", [])
    assert len(es) == 1 and es[0]["confidence"] == 0.9


def test_entity_conflict_different_id_prevents_merge():
    from core.subject_profile import _check_entity_conflict
    c = _check_entity_conflict({"name":"A","identifier":"ID1"},{"name":"A","identifier":"ID2"})
    assert c is not None and "identifier_mismatch" in str(c.get("conflicts",[]))

def test_entity_no_conflict_same_id():
    from core.subject_profile import _check_entity_conflict
    c = _check_entity_conflict({"name":"A","identifier":"ID1"},{"name":"A","identifier":"ID1"})
    assert c is None

def test_entity_address_conflict():
    from core.subject_profile import _check_entity_conflict
    c = _check_entity_conflict({"name":"A","address":"Beijing"},{"name":"A","address":"Shanghai"})
    if c:
        assert "address_mismatch" in str(c.get("conflicts",[]))


def test_explain_relationship_edges():
    from core.subject_profile import _explain_relationship_edges
    class R:
        def __init__(self,f,t,rt,c,s,e):
            self.from_name=f;self.to_name=t;self.relation_type=rt
            self.confidence=c;self.source_name=s;self.evidence_ids=e
            self.basis="";self.description="";self.from_id="";self.to_id=""
    class G:
        def __init__(self):self.relations=[R("A","B","controller",0.85,"qyyjt_api",["e1"])];self.entities={}
    r = _explain_relationship_edges(G(), {})
    edges = r.get("relationship_edges", [])
    assert len(edges) == 1
    assert edges[0]["source_name"] == "qyyjt_api"
    assert "e1" in edges[0]["evidence_ids"]


def test_entity_conflict_integration():
    from core.subject_profile import _check_entity_conflict, _explain_relationship_edges
    c = _check_entity_conflict(
        {"name":"Demo Co.","identifier":"91110000MA"},
        {"name":"Demo Co.","identifier":"91110000MB"}
    )
    assert c is not None
    # Graph edges should work alongside conflict detection
    class R:
        def __init__(self):self.from_name="A";self.to_name="B";self.relation_type="owns"
        confidence=0.9;source_name="qyyjt";evidence_ids=["e1"];basis="";description=""
        from_id="";to_id=""
    class G:
        def __init__(self):self.relations=[R()];self.entities={}
    r = _explain_relationship_edges(G(), {})
    assert len(r.get("relationship_edges", [])) == 1


def test_entity_conflict_prevent_merge():
    from core.subject_profile import _check_entity_conflict
    c = _check_entity_conflict({"name":"Demo Co.","identifier":"91110000MA"},{"name":"Demo Co.","identifier":"91110000MB"})
    assert c is not None
    assert "identifier_mismatch" in str(c.get("conflicts",[]))

def test_entity_conflict_official_outranks_weak():
    from core.subject_profile import _check_entity_conflict
    # Same entity, different identifier sources — official should outrank
    c = _check_entity_conflict(
        {"name":"Demo Co.","identifier":"91110000MA","source_type":"official"},
        {"name":"Demo Co.","identifier":"91110000MB","source_type":"public_web"}
    )
    if c:
        assert "identifier_mismatch" in str(c.get("conflicts",[]))

def test_graph_edges_expose_confidence():
    from core.subject_profile import _explain_relationship_edges
    class R:
        def __init__(self,f,t,rt,c,src,eids):
            self.from_name=f;self.to_name=t;self.relation_type=rt
            self.confidence=c;self.source_name=src;self.evidence_ids=eids
            self.basis="";self.description="";self.from_id="";self.to_id=""
    class G:
        def __init__(self):self.relations=[R("A","B","controller",0.85,"qyyjt",["e1"])];self.entities={}
    r = _explain_relationship_edges(G(), {})
    edges = r.get("relationship_edges",[])
    assert len(edges) == 1
    assert edges[0]["confidence"] == 0.85
    assert edges[0]["source_name"] == "qyyjt"
    assert "e1" in edges[0]["evidence_ids"]
