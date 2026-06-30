#!/usr/bin/env python3
"""Tests for broad investigative retrieval planning."""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from core.intelligence_retrieval import (
    EvidenceIngestor,
    EvidenceType,
    EntityKind,
    EntityResolutionScorer,
    InvestigativeRetrievalPlanner,
    InvestigationEntity,
    RetrievalDomain,
    RetrievalLayer,
    SourceAccess,
    SourceCatalog,
    ConnectorShape,
)


def test_company_plan_covers_broad_osint_domains() -> None:
    planner = InvestigativeRetrievalPlanner()

    plan = planner.build_company_plan("测试科技有限公司")

    assert plan.seed_company == "测试科技有限公司"
    assert len(plan.tasks) >= 10
    assert InvestigativeRetrievalPlanner.REQUIRED_DOMAINS <= plan.coverage_domains
    assert plan.graph.entities["company:测试科技有限公司"].attributes["seed"] is True
    assert plan.graph.evidence == {}
    assert any("实际控制人" in task.query for task in plan.tasks)
    assert any("微博" in task.query and "LinkedIn" in task.query for task in plan.tasks)
    assert any("不动产抵押" in task.query or "司法拍卖" in task.query for task in plan.tasks)
    assert any("上游" in task.query and "供应商" in task.query and "客户" in task.query for task in plan.tasks)
    assert any("行业" in task.query and "竞争格局" in task.query and "商业模式" in task.query for task in plan.tasks)


def test_plan_serializes_without_fabricated_evidence() -> None:
    planner = InvestigativeRetrievalPlanner()

    payload = planner.build_company_plan("  测试科技有限公司  ").to_dict()

    assert payload["seed_company"] == "测试科技有限公司"
    assert payload["graph"]["evidence"] == {}
    assert payload["graph"]["relations"] == []
    assert "social_web" in payload["coverage_domains"]
    assert all(task["expected_evidence"] for task in payload["tasks"])
    assert all(task["source_profile"]["provenance_required"] for task in payload["tasks"])
    assert any("public" in note.lower() for note in payload["compliance_notes"])
    assert any("bots are allowed" in note for note in payload["compliance_notes"])


def test_source_catalog_is_connector_shape_neutral_but_policy_aware() -> None:
    bot_profile = SourceCatalog.profile_for("telegram_bot_public_service")
    registry_profile = SourceCatalog.profile_for("registry_sources")
    gleif_profile = SourceCatalog.profile_for("gleif_lei_public_api")
    sec_profile = SourceCatalog.profile_for("sec_edgar_public_api")
    opensanctions_profile = SourceCatalog.profile_for("opensanctions_public_dataset_catalog")
    ofac_profile = SourceCatalog.profile_for("ofac_consolidated_sanctions_xml")
    un_sc_profile = SourceCatalog.profile_for("un_sc_consolidated_sanctions_xml")
    wikidata_profile = SourceCatalog.profile_for("wikidata_public_entity_graph")
    behavior_profile = SourceCatalog.profile_for("public_behavior_sources")
    relation_profile = SourceCatalog.profile_for("relationship_network_sources")
    unknown_profile = SourceCatalog.profile_for("unreviewed_source")

    assert bot_profile.shape is ConnectorShape.TELEGRAM_BOT
    assert bot_profile.access is SourceAccess.PUBLIC
    assert bot_profile.allowed is True
    assert any("public" in note for note in bot_profile.notes)

    assert registry_profile.access is SourceAccess.PUBLIC
    assert registry_profile.allowed is True
    assert gleif_profile.shape is ConnectorShape.REST_API
    assert gleif_profile.access is SourceAccess.PUBLIC
    assert gleif_profile.allowed is True
    assert sec_profile.shape is ConnectorShape.REST_API
    assert sec_profile.access is SourceAccess.PUBLIC
    assert sec_profile.allowed is True
    assert opensanctions_profile.shape is ConnectorShape.REST_API
    assert opensanctions_profile.access is SourceAccess.PUBLIC
    assert opensanctions_profile.allowed is True
    assert ofac_profile.shape is ConnectorShape.REST_API
    assert ofac_profile.access is SourceAccess.PUBLIC
    assert ofac_profile.allowed is True
    assert un_sc_profile.shape is ConnectorShape.REST_API
    assert un_sc_profile.access is SourceAccess.PUBLIC
    assert un_sc_profile.allowed is True
    assert wikidata_profile.shape is ConnectorShape.REST_API
    assert wikidata_profile.access is SourceAccess.PUBLIC
    assert wikidata_profile.allowed is True
    assert behavior_profile.access is SourceAccess.PUBLIC
    assert behavior_profile.allowed is True
    assert relation_profile.access is SourceAccess.PUBLIC
    assert relation_profile.allowed is True

    assert unknown_profile.allowed is False
    assert unknown_profile.access is SourceAccess.UNKNOWN


def test_company_plan_explicitly_targets_deep_subject_profile_dimensions() -> None:
    planner = InvestigativeRetrievalPlanner()

    plan = planner.build_company_plan("Demo Profile Co.")
    hints = {task.source_hint for task in plan.tasks}
    objectives = " ".join(task.objective for task in plan.tasks)

    assert {
        "public_contact_sources",
        "public_account_sources",
        "public_asset_sources",
        "public_behavior_sources",
        "relationship_network_sources",
        "supply_chain_sources",
        "industry_research_sources",
        "opensanctions_public_dataset_catalog",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "wikidata_public_entity_graph",
    } <= hints
    assert "recursive public-intelligence expansion" in objectives
    assert "solvency signals" in objectives
    assert "behavior-risk leads" in objectives


def test_company_plan_tags_money_goods_people_case_tracks() -> None:
    planner = InvestigativeRetrievalPlanner()

    payload = planner.build_company_plan("Demo Case Co.").to_dict()
    tasks = payload["tasks"]
    tracks = {
        task["params"].get("investigation_track")
        for task in tasks
        if task["params"].get("investigation_lens") == "扒光查案式调查"
    }

    assert {"money", "goods", "people"} <= tracks
    assert any(
        task["params"].get("investigation_track") == "money"
        and any("钱从哪里来" in question for question in task["params"].get("case_questions", []))
        for task in tasks
    )
    assert any(
        task["params"].get("investigation_track") == "goods"
        and any("货从哪里来" in question for question in task["params"].get("case_questions", []))
        for task in tasks
    )
    assert any(
        task["params"].get("investigation_track") == "people"
        and any("关键人" in question or "谁实际控制" in question for question in task["params"].get("case_questions", []))
        for task in tasks
    )


def test_company_plan_exposes_progressive_retrieval_layers() -> None:
    planner = InvestigativeRetrievalPlanner()

    plan = planner.build_company_plan("Demo Layered Co.")
    layers = {task.effective_retrieval_layer() for task in plan.tasks}
    exported_layers = {
        task["retrieval_layer"]
        for task in plan.to_dict()["tasks"]
    }

    assert RetrievalLayer.ENTITY_ANCHOR in layers
    assert RetrievalLayer.OVERVIEW in layers
    assert RetrievalLayer.PRIORITIZED_DRILLDOWN in layers
    assert RetrievalLayer.SPECIALIST in layers
    assert exported_layers >= {
        "entity_anchor",
        "overview",
        "prioritized_drilldown",
        "specialist",
    }
    assert next(
        task for task in plan.tasks if task.source_hint == "registry_sources"
    ).effective_retrieval_layer() is RetrievalLayer.ENTITY_ANCHOR


def test_person_address_and_account_fanout_tasks_are_associative() -> None:
    planner = InvestigativeRetrievalPlanner()

    person_tasks = planner.expand_from_entity(
        InvestigationEntity(id="person:张三", kind=EntityKind.PERSON, name="张三")
    )
    address_tasks = planner.expand_from_entity(
        InvestigationEntity(id="address:demo", kind=EntityKind.ADDRESS, name="北京市朝阳区某地址")
    )
    account_tasks = planner.expand_from_entity(
        InvestigationEntity(id="account:demo", kind=EntityKind.ACCOUNT, name="@demo_account")
    )

    assert {task.domain for task in person_tasks} >= {
        RetrievalDomain.PEOPLE,
        RetrievalDomain.OWNERSHIP_CONTROL,
        RetrievalDomain.SOCIAL_WEB,
        RetrievalDomain.COURT_ENFORCEMENT,
        RetrievalDomain.ADMINISTRATIVE_RISK,
        RetrievalDomain.LOCATION_ASSETS,
        RetrievalDomain.RELATED_ENTITIES,
    }
    assert {task.source_hint for task in person_tasks} >= {
        "public_asset_sources",
        "public_behavior_sources",
        "relationship_network_sources",
    }
    assert address_tasks[0].fanout_entities == (EntityKind.COMPANY, EntityKind.PERSON)
    assert account_tasks[0].domain is RetrievalDomain.SOCIAL_WEB


def test_empty_company_name_is_rejected() -> None:
    planner = InvestigativeRetrievalPlanner()

    with pytest.raises(ValueError):
        planner.build_company_plan("  ")


def test_evidence_ingestor_populates_graph_entities_and_relations() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.OWNERSHIP_CONTROL)[0]

    evidence = EvidenceIngestor.ingest_search_result(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        result={
            "source": "registry_fixture",
            "title": "股权穿透结果",
            "url": "https://example.com/report",
            "evidence_type": "registry_record",
            "confidence": 0.91,
            "claims": ["张三持股60%", "张三疑似实际控制人"],
            "entities": [
                {
                    "kind": "person",
                    "name": "张三",
                    "relation": "actual_controller_candidate",
                    "confidence": 0.86,
                }
            ],
        },
    )

    assert evidence.evidence_type is EvidenceType.REGISTRY_RECORD
    assert evidence.source == "registry_fixture"
    assert "张三持股60%" in evidence.claims
    assert evidence.source_profile is not None
    assert evidence.source_profile.access is SourceAccess.LICENSED
    assert evidence.id in plan.graph.entities[seed_id].evidence_ids
    assert "person:张三" in plan.graph.entities
    assert plan.graph.entities["person:张三"].evidence_ids == [evidence.id]
    assert plan.graph.relations[-1].relation_type == "actual_controller_candidate"
    assert plan.graph.relations[-1].evidence_ids == (evidence.id,)
    assert any(event.category is RetrievalDomain.OWNERSHIP_CONTROL for event in plan.graph.risk_events)


def test_evidence_from_unknown_source_is_flagged_for_manual_review() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.NEWS_PUBLIC_OPINION)[0]

    evidence = EvidenceIngestor.ingest_search_result(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        result={
            "source": "mystery_bot",
            "source_hint": "mystery_bot",
            "title": "未审查来源样例",
            "evidence_type": "webpage",
            "confidence": 0.4,
            "claims": ["样例线索"],
        },
    )

    payload = plan.to_dict()
    serialized = payload["graph"]["evidence"][evidence.id]["source_profile"]

    assert evidence.source_profile is not None
    assert evidence.source_profile.allowed is False
    assert serialized["access"] == "unknown"
    assert serialized["allowed"] is False


def test_risk_events_are_serialized_from_matching_evidence() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)[0]

    EvidenceIngestor.ingest_search_result(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        result={
            "source": "court_fixture",
            "title": "失信与限制高消费公告",
            "url": "https://example.com/court",
            "evidence_type": "court_record",
            "confidence": 0.77,
            "claims": ["该公司被执行", "存在限制高消费"],
        },
    )

    payload = plan.to_dict()

    assert payload["graph"]["risk_events"]
    assert payload["graph"]["risk_events"][0]["severity"] in {"high", "critical"}
    assert payload["graph"]["risk_events"][0]["category"] == "court_enforcement"


def test_non_matching_evidence_does_not_create_risk_event() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    EvidenceIngestor.ingest_search_result(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        result={
            "source": "registry_fixture",
            "title": "工商登记信息",
            "evidence_type": "registry_record",
            "confidence": 0.9,
            "claims": ["注册资本1000万元", "成立时间2020年"],
        },
    )

    assert len(plan.graph.risk_events) == 0


def test_standardized_records_ingest_into_evidence_graph_and_risk_events() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "court_public_api",
                "source_type": "rest_api",
                "entity": "测试科技有限公司",
                "title": "测试科技有限公司被执行公告",
                "summary": "该公司存在被执行风险。",
                "url": "https://example.com/court/1",
                "published_at": "2026-06-18",
                "confidence": 0.82,
                "evidence": [{"claim": "被执行案号公开记录"}],
            }
        ],
    )

    assert len(evidence_items) == 1
    evidence = evidence_items[0]
    assert evidence.source == "court_public_api"
    assert evidence.evidence_type is EvidenceType.COURT_RECORD
    assert "该公司存在被执行风险。" in evidence.claims
    assert evidence.id in plan.graph.entities[seed_id].evidence_ids
    assert plan.graph.risk_events
    assert plan.graph.risk_events[0].category is RetrievalDomain.COURT_ENFORCEMENT


def test_query_result_metadata_can_be_ingested_directly() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("测试科技有限公司")
    seed_id = "company:测试科技有限公司"
    task = plan.by_domain(RetrievalDomain.NEWS_PUBLIC_OPINION)[0]
    query_result = SimpleNamespace(
        metadata={
            "standardized_records": [
                {
                    "source_name": "news_search",
                    "source_type": "rest_api",
                    "entity": "测试科技有限公司",
                    "title": "公开新闻线索",
                    "summary": "媒体报道存在纠纷线索。",
                    "url": "https://example.com/news/1",
                    "confidence": 0.7,
                }
            ]
        }
    )

    evidence_items = EvidenceIngestor.ingest_query_result(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        query_result=query_result,
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].source == "news_search"
    assert evidence_items[0].evidence_type is EvidenceType.NEWS_ARTICLE


def test_standardized_record_extracts_business_entities_from_fields_and_text() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Intelligence Ltd")
    seed_id = "company:demo_intelligence_ltd"
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "registry_public_api",
                "source_type": "rest_api",
                "entity": "Demo Intelligence Ltd",
                "title": "Demo Intelligence Ltd registry profile",
                "summary": "Public registry profile. Contact: compliance@demo-intel.com, 010-88889999.",
                "url": "https://demo-intel.com/profile",
                "confidence": 0.88,
                "raw": {
                    "creditCode": "91330100MA2BINTEL1",
                    "regNo": "330100000000002",
                    "legal_representative": "Alice Zhang",
                    "actual_controller": {"name": "Bob Li"},
                    "shareholders": [{"name": "Carol Holding"}],
                    "director": "Diane Chen",
                    "registered_address": "No. 1 Finance Road, Tieling",
                    "website": "www.demo-intel.com",
                    "case_no": "辽0101执2026号",
                    "project_name": "North Market Intelligence Platform",
                },
            }
        ],
    )

    assert len(evidence_items) == 1
    expected_entities = {
        ("person", "Alice Zhang"),
        ("person", "Bob Li"),
        ("person", "Carol Holding"),
        ("person", "Diane Chen"),
        ("address", "No. 1 Finance Road, Tieling"),
        ("domain", "www.demo-intel.com"),
        ("domain", "demo-intel.com"),
        ("email", "compliance@demo-intel.com"),
        ("phone", "010-88889999"),
        ("case", "辽0101执2026号"),
        ("project", "North Market Intelligence Platform"),
    }
    actual_entities = {
        (entity.kind.value, entity.name)
        for entity in plan.graph.entities.values()
    }

    assert expected_entities <= actual_entities
    company = plan.graph.entities[seed_id]
    assert company.attributes["unified_social_credit_code"] == "91330100MA2BINTEL1"
    assert company.attributes["registration_number"] == "330100000000002"
    assert any(
        relation.relation_type == "legal_representative"
        and relation.to_id == "person:alice_zhang"
        and evidence_items[0].id in relation.evidence_ids
        for relation in plan.graph.relations
    )
    assert any(
        relation.relation_type == "actual_controller"
        and relation.to_id == "person:bob_li"
        for relation in plan.graph.relations
    )
    assert any(
        relation.relation_type == "shareholder"
        and relation.to_id == "person:carol_holding"
        for relation in plan.graph.relations
    )
    assert any(
        relation.relation_type == "director"
        and relation.to_id == "person:diane_chen"
        for relation in plan.graph.relations
    )
    assert any(
        relation.relation_type == "public_contact_lead"
        and relation.to_id == "email:compliance@demo-intel.com"
        for relation in plan.graph.relations
    )


def test_standardized_record_extracts_controller_aliases_and_control_metadata() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Alias Control Ltd")
    seed_id = "company:demo_alias_control_ltd"
    task = plan.by_domain(RetrievalDomain.OWNERSHIP_CONTROL)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "licensed_registry_api",
                "source_type": "rest_api",
                "entity": "Demo Alias Control Ltd",
                "title": "Demo Alias Control Ltd ownership profile",
                "confidence": 0.86,
                "raw": {
                    "actualControllerName": "Alice Controller",
                    "ultimateBeneficialOwner": {
                        "beneficialOwnerName": "Bob UBO",
                        "shareRatio": "61%",
                        "pathNodes": [
                            "Demo Alias Control Ltd",
                            "Demo Holding Ltd",
                            "Bob UBO",
                        ],
                        "basis": "licensed ownership profile",
                    },
                    "shareholders": [
                        {"shareholderName": "Carol Investor", "holdingRatio": "20%"}
                    ],
                },
            }
        ],
    )

    entities = plan.graph.entities
    assert "person:alice_controller" in entities
    assert "person:bob_ubo" in entities
    assert "person:carol_investor" in entities
    assert entities["person:bob_ubo"].attributes["ownership_ratio"] == "61%"
    assert entities["person:bob_ubo"].attributes["path_nodes"] == [
        "Demo Alias Control Ltd",
        "Demo Holding Ltd",
        "Bob UBO",
    ]
    assert entities["person:bob_ubo"].attributes["confidence_basis"] == "licensed ownership profile"
    assert entities["person:carol_investor"].attributes["ownership_ratio"] == "20%"
    assert any(
        relation.relation_type == "beneficial_owner"
        and relation.to_id == "person:bob_ubo"
        for relation in plan.graph.relations
    )
    assert any(
        relation.relation_type == "actual_controller"
        and relation.to_id == "person:alice_controller"
        for relation in plan.graph.relations
    )


def test_standardized_record_does_not_treat_filing_ids_as_public_contact_leads() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.FINANCING_CAPITAL_MARKETS)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "sec_edgar_public_api",
                "source_type": "rest_api",
                "entity": "Apple Inc.",
                "title": "SEC EDGAR company ticker match: Apple Inc.",
                "summary": "ticker=AAPL; cik=0000320193",
                "url": "https://www.sec.gov/edgar/browse/?CIK=0000320193",
                "confidence": 0.62,
            }
        ],
    )

    assert not any(
        entity.kind is EntityKind.PHONE and entity.name == "0000320193"
        for entity in plan.graph.entities.values()
    )


def test_standardized_record_does_not_treat_topic_years_as_public_contact_leads() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.RELATED_ENTITIES)[0]

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "wikidata_public_entity_graph",
                "source_type": "rest_api",
                "source_hint": "wikidata_public_entity_graph",
                "entity": "Apple Inc. v. Samsung Electronics Co.",
                "title": "Wikidata entity graph match: Apple Inc. v. Samsung Electronics Co.",
                "summary": "United States Supreme Court case, 580 U.S. 53, docket 2016",
                "url": "http://www.wikidata.org/entity/Q487819",
                "confidence": 0.56,
                "raw": {"id": "Q487819", "label": "Apple Inc. v. Samsung Electronics Co."},
            }
        ],
    )

    assert not any(entity.kind is EntityKind.PHONE for entity in plan.graph.entities.values())
    assert "company:apple_inc._v._samsung_electronics_co." not in plan.graph.entities


def test_standardized_record_ingests_structured_risk_events_without_keyword_match() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Structured Risk Ltd")
    seed_id = "company:demo_structured_risk_ltd"
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "licensed_registry_api",
                "source_type": "rest_api",
                "source_hint": "registry_and_commercial_sources",
                "entity": "Demo Structured Risk Ltd",
                "title": "Demo Structured Risk Ltd profile",
                "summary": "Connector returned structured event metadata.",
                "url": "https://example.invalid/profile",
                "confidence": 0.73,
                "risk_events": [
                    {
                        "risk_category": "ownership",
                        "severity": "high",
                        "title": "Controller change signal",
                        "summary": "The provider marked a controller-change risk event.",
                        "confidence": 0.81,
                    }
                ],
            }
        ],
    )

    assert len(evidence_items) == 1
    assert len(plan.graph.risk_events) == 1
    event = plan.graph.risk_events[0]
    assert event.category is RetrievalDomain.OWNERSHIP_CONTROL
    assert event.severity.value == "high"
    assert event.title == "Controller change signal"
    assert event.evidence_ids == (evidence_items[0].id,)
    assert event.entity_ids == (seed_id,)


def test_query_plan_records_stay_as_leads_without_graph_facts() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "qyyjt_websearch_plan",
                "source_type": "query_plan",
                "source_hint": "web_search",
                "entity": "Apple Inc.",
                "title": "QYYJT lead: RISK_SCAN",
                "summary": "Check site:wenshu.court.gov.cn and cninfo.com.cn for Apple Inc.",
                "confidence": 0.3,
                "entities": [
                    {
                        "kind": "person",
                        "name": "Lead Only",
                        "relation": "actual_controller",
                        "confidence": 0.3,
                    }
                ],
                "relations": [
                    {
                        "from_name": "Apple Inc.",
                        "to_name": "Lead Only",
                        "to_kind": "person",
                        "relation": "actual_controller",
                        "confidence": 0.3,
                    }
                ],
                "risk_events": [
                    {
                        "risk_category": "court",
                        "severity": "high",
                        "title": "Lead-only court query",
                    }
                ],
                "evidence": [
                    {"claim": "QYYJT fallback generated a public-search lead, not a verified fact."}
                ],
            }
        ],
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].evidence_type is EvidenceType.DERIVED_CLUE
    assert evidence_items[0].claims
    assert set(plan.graph.entities) == {seed_id}
    assert plan.graph.relations == []
    assert plan.graph.risk_events == []


def test_rich_query_plan_records_stay_lead_only_even_with_structured_payload() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.OWNERSHIP_CONTROL)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "QYYJT_WEBSEARCH_PLAN",
                "source_type": "Rich_Query_Plan",
                "entity": "Apple Inc.",
                "title": "QYYJT rich public-origin plan",
                "summary": "A rich query plan with structured-looking rows must stay lead-only.",
                "confidence": 0.91,
                "entity_match": {"level": "exact", "record_source_type": "Rich_Query_Plan"},
                "entities": [
                    {"kind": "person", "name": "Plan Controller", "relation": "actual_controller", "confidence": 0.9}
                ],
                "relations": [
                    {
                        "from_name": "Apple Inc.",
                        "to_name": "Plan Controller",
                        "to_kind": "person",
                        "relation": "actual_controller",
                        "confidence": 0.9,
                    }
                ],
                "risk_events": [
                    {"risk_category": "ownership", "severity": "high", "title": "Plan-only control event"}
                ],
                "evidence": [{"claim": "module-specific query plan, not verified evidence"}],
            }
        ],
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].evidence_type is EvidenceType.DERIVED_CLUE
    assert evidence_items[0].entity_match["record_source_type"] == "Rich_Query_Plan"
    assert set(plan.graph.entities) == {seed_id}
    assert plan.graph.relations == []
    assert plan.graph.risk_events == []


def test_entity_resolution_scorer_explains_strong_and_review_matches() -> None:
    strong = EntityResolutionScorer.score(
        "Demo Intelligence Co., Ltd.",
        "Demo Intelligence Ltd",
        {"lei": "5493001KJTIIGC8Y1R12"},
    )
    review = EntityResolutionScorer.score(
        "Demo Intelligence Co., Ltd.",
        "Demo Data Services Ltd",
    )
    with_registry_identifiers = EntityResolutionScorer.score(
        "Demo Registry Co., Ltd.",
        "Demo Registry Co., Ltd.",
        {"creditCode": "91330100MA2BIDENT1", "regNo": "330100000000001"},
    )

    assert strong["level"] in {"exact", "strong"}
    assert strong["score"] >= 0.82
    assert strong["identifiers"]["lei"] == "5493001KJTIIGC8Y1R12"
    assert any("official identifier" in reason for reason in strong["reasons"])
    assert review["level"] in {"review", "weak"}
    assert review["score"] < strong["score"]
    assert with_registry_identifiers["identifiers"]["unified_social_credit_code"] == "91330100MA2BIDENT1"
    assert with_registry_identifiers["identifiers"]["registration_number"] == "330100000000001"


def test_entity_resolution_identifier_does_not_promote_low_similarity_candidate() -> None:
    match = EntityResolutionScorer.score(
        "Apple Inc.",
        "APPLE QUEST, INC.",
        {"lei": "example-lei"},
    )

    assert match["level"] in {"review", "weak"}
    assert match["score"] < 0.82
    assert "lei" in match["identifiers"]


def test_standardized_record_does_not_promote_review_level_registry_candidate() -> None:
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
                "summary": "LEI=549300OFQZDF71H5ZN34",
                "confidence": 0.86,
                "raw": {"lei": "549300OFQZDF71H5ZN34"},
            }
        ],
    )

    assert "company:apple_quest,_inc." not in plan.graph.entities


def test_review_level_registry_candidate_does_not_attach_related_entities_to_subject() -> None:
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
                "summary": "LEI=549300OFQZDF71H5ZN34",
                "confidence": 0.86,
                "entities": [
                    {
                        "kind": "address",
                        "name": "1380 COOLIDGE STREET, CONKLIN, US-MI, 49403, US",
                        "relation": "registered_address",
                        "confidence": 0.82,
                    }
                ],
                "raw": {"lei": "549300OFQZDF71H5ZN34"},
            }
        ],
    )

    assert "address:1380_coolidge_street,_conklin,_us-mi,_49403,_us" not in plan.graph.entities


def test_source_url_domain_is_not_promoted_as_public_account_entity() -> None:
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
                "entity": "Apple Inc.",
                "title": "GLEIF LEI record: Apple Inc.",
                "summary": "LEI=HWUPKR0MPOU8FGXBT394",
                "url": "https://search.gleif.org/#/record/HWUPKR0MPOU8FGXBT394",
                "confidence": 0.86,
                "raw": {"lei": "HWUPKR0MPOU8FGXBT394"},
            }
        ],
    )

    assert "domain:search.gleif.org" not in plan.graph.entities


def test_evidence_dict_claims_are_rendered_as_readable_public_fields() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Apple Inc.")
    seed_id = "company:apple_inc."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "gleif_lei_public_api",
                "source_type": "rest_api",
                "source_hint": "gleif_lei_public_api",
                "entity": "Apple Inc.",
                "title": "GLEIF LEI record: Apple Inc.",
                "summary": "Official identity fixture.",
                "confidence": 0.86,
                "evidence": [
                    {
                        "type": "official_public_api",
                        "provider": "GLEIF",
                        "lei": "HWUPKR0MPOU8FGXBT394",
                        "registration_authority": "RA000598",
                        "jurisdiction": "US-CA",
                    }
                ],
                "raw": {"lei": "HWUPKR0MPOU8FGXBT394"},
            }
        ],
    )

    claims = evidence_items[0].claims

    assert "GLEIF: lei=HWUPKR0MPOU8FGXBT394; registration_authority=RA000598; jurisdiction=US-CA" in claims
    assert not any(claim.startswith("{") for claim in claims)


def test_standardized_record_carries_entity_match_assessment_into_exports() -> None:
    planner = InvestigativeRetrievalPlanner()
    plan = planner.build_company_plan("Demo Intelligence Co., Ltd.")
    seed_id = "company:demo_intelligence_co.,_ltd."
    task = plan.by_domain(RetrievalDomain.CORPORATE_REGISTRY)[0]

    evidence_items = EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id=seed_id,
        task=task,
        records=[
            {
                "source_name": "fixture_gleif_lei_public_api",
                "source_type": "rest_api",
                "source_hint": "gleif_lei_public_api",
                "entity": "Demo Intelligence Ltd",
                "title": "GLEIF LEI record: Demo Intelligence Ltd",
                "summary": "Official identity fixture.",
                "confidence": 0.86,
                "raw": {"lei": "5493001KJTIIGC8Y1R12"},
            }
        ],
    )

    match = evidence_items[0].entity_match
    serialized = plan.to_dict()["graph"]["evidence"][evidence_items[0].id]["entity_match"]

    assert match is not None
    assert match["level"] in {"exact", "strong"}
    assert match["identifiers"]["lei"] == "5493001KJTIIGC8Y1R12"
    assert serialized == match
