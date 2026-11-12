#!/usr/bin/env python3
"""Completions for default one-click official sources, Wikidata, and fan-out."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from adapters.eastmoney_f10_adapter import EASTMONEY_F10_SOURCE
from adapters.multi_datasource import DataSourceConfig, RestApiDataSource
from core.intelligence_retrieval import (
    EntityKind,
    EvidenceGraph,
    EvidenceIngestor,
    InvestigationEntity,
    RetrievalDomain,
    SearchTask,
)
from core.one_click_defaults import DefaultOneClickSearchEngine, build_default_one_click_plan
from core.risk_discovery_pipeline import RiskDiscoveryPipeline


def _wikidata_source() -> RestApiDataSource:
    source = RestApiDataSource(
        DataSourceConfig(
            name="wikidata_public_entity_graph",
            type="rest_api",
            base_url="https://www.wikidata.org/w",
            headers={"Accept": "application/json"},
            custom={"provider_type": "wikidata_entity_search"},
            rate_limit={"enabled": False},
        )
    )
    source._current_query_hint = "贵州茅台"
    return source


def test_wikidata_prefers_moutai_company_over_football_club() -> None:
    source = _wikidata_source()
    payload = {
        "search": [
            {
                "id": "Q631695",
                "label": "贵州茅台",
                "description": "中国足球俱乐部",
                "concepturi": "http://www.wikidata.org/entity/Q631695",
            },
            {
                "id": "Q1518607",
                "label": "贵州茅台",
                "description": "中国白酒上市公司",
                "concepturi": "http://www.wikidata.org/entity/Q1518607",
            },
        ]
    }
    records = source._format_wikidata_entity_search_result(payload)["standardized_records"]
    by_id = {record["wikidata_id"]: record for record in records}
    assert by_id["Q1518607"]["entity_match"]["level"] == "exact"
    assert by_id["Q1518607"]["entity_match"]["wikidata_kind"] in {"company", "listed_company"}
    assert by_id["Q631695"]["entity_match"]["level"] == "weak"
    assert by_id["Q631695"]["entity_match"]["wikidata_kind"] == "namesake"


def test_wikidata_ambiguous_companies_stay_leads() -> None:
    source = _wikidata_source()
    source._current_query_hint = "Demo Name"
    payload = {
        "search": [
            {
                "id": "Q1",
                "label": "Demo Name",
                "description": "Chinese beverage company",
                "concepturi": "http://www.wikidata.org/entity/Q1",
            },
            {
                "id": "Q2",
                "label": "Demo Name",
                "description": "Chinese manufacturing enterprise",
                "concepturi": "http://www.wikidata.org/entity/Q2",
            },
        ]
    }
    records = source._format_wikidata_entity_search_result(payload)["standardized_records"]
    assert all(record["entity_match"]["level"] == "review" for record in records)
    assert all("not promoted" in " ".join(record["entity_match"]["reasons"]) for record in records)


def test_wikidata_ended_ceo_claim_is_former_not_current() -> None:
    source = _wikidata_source()
    payload = {
        "entities": {
            "Q312": {
                "id": "Q312",
                "labels": {"en": {"value": "Apple Inc."}},
                "descriptions": {"en": {"value": "American technology company"}},
                "_linked_entities": {
                    "Q19837": {"labels": {"en": {"value": "Tim Cook"}}},
                    "Q19848": {"labels": {"en": {"value": "Steve Jobs"}}},
                },
                "claims": {
                    "P169": [
                        {
                            "mainsnak": {
                                "datavalue": {"value": {"id": "Q19837", "numeric-id": 19837}}
                            }
                        },
                        {
                            "mainsnak": {
                                "datavalue": {"value": {"id": "Q19848", "numeric-id": 19848}}
                            },
                            "qualifiers": {
                                "P582": [
                                    {"datavalue": {"value": {"time": "+2011-08-24T00:00:00Z"}}}
                                ]
                            },
                        },
                    ],
                    "P249": [
                        {"mainsnak": {"datavalue": {"value": "AAPL"}}},
                        {"mainsnak": {"datavalue": {"value": "600519"}}},
                    ],
                },
            }
        }
    }
    records = source._format_wikidata_entitydata_result(payload)["standardized_records"]
    relations = {(item["name"], item["relation"], item.get("current")) for item in records[0]["entities"]}
    assert ("Tim Cook", "chief_executive_officer", True) in relations
    assert ("Steve Jobs", "former_chief_executive_officer", False) in relations
    assert ("Steve Jobs", "chief_executive_officer", True) not in relations
    assert records[0]["ticker"] == "AAPL"
    assert "600519" in records[0]["tickers"]


def test_identifier_fanout_emits_lei_and_ashare_tasks() -> None:
    entity = InvestigationEntity(
        id="company:kweichow_moutai",
        kind=EntityKind.COMPANY,
        name="贵州茅台酒股份有限公司",
        attributes={"lei": "HWUPKR0MPOU8FGXBT394", "ticker": "600519", "cik": ""},
    )
    tasks = RiskDiscoveryPipeline._identifier_fanout_tasks(entity, set(), 1)
    by_hint = {task.source_hint: task for task in tasks}
    assert "gleif_lei_public_api" in by_hint
    assert by_hint["gleif_lei_public_api"].params["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert EASTMONEY_F10_SOURCE in by_hint
    assert by_hint[EASTMONEY_F10_SOURCE].params["stock_code"] == "SH600519"
    assert "sec_edgar_public_api" not in by_hint


def test_default_engine_formats_eastmoney_records_from_lookup() -> None:
    from tests.unit.test_eastmoney_f10_adapter import FIXTURE_HOLDERS, _adapter

    engine = DefaultOneClickSearchEngine(
        public_tool=SimpleNamespace(),
        eastmoney_lookup=_adapter(FIXTURE_HOLDERS),
    )

    async def run():
        return await engine.search(EASTMONEY_F10_SOURCE, "600519")

    result = asyncio.run(run())
    records = result.metadata["standardized_records"]
    assert result.is_success is True
    assert records[0]["entity"] == "贵州茅台酒股份有限公司"
    assert records[0]["stock_code"] == "SH600519"


def test_default_engine_eastmoney_name_without_code_is_a_gap() -> None:
    engine = DefaultOneClickSearchEngine(public_tool=SimpleNamespace())

    async def run():
        return await engine.search(EASTMONEY_F10_SOURCE, "贵州茅台")

    result = asyncio.run(run())
    assert result.metadata["standardized_records"] == []
    assert result.error == "stock_code_unresolved"
    assert "evidence gap" in result.data["gap"]


def test_default_plan_for_stock_code_seed_includes_eastmoney() -> None:
    plan = build_default_one_click_plan("SH600519")
    assert any(task.source_hint == EASTMONEY_F10_SOURCE for task in plan.tasks)



def test_wikidata_prefers_listed_company_when_labels_differ() -> None:
    source = _wikidata_source()
    payload = {
        "search": [
            {
                "id": "Q631695",
                "label": "北京橙丰足球俱乐部",
                "description": "中国足球俱乐部",
                "concepturi": "http://www.wikidata.org/entity/Q631695",
                "aliases": ["贵州茅台"],
            },
            {
                "id": "Q1518607",
                "label": "贵州茅台酒股份有限公司",
                "description": "中国白酒上市公司",
                "concepturi": "http://www.wikidata.org/entity/Q1518607",
                "aliases": ["贵州茅台"],
            },
            {
                "id": "Q15914704",
                "label": "贵州茅台集团",
                "description": "中国酒业集团",
                "concepturi": "http://www.wikidata.org/entity/Q15914704",
            },
        ]
    }
    records = source._format_wikidata_entity_search_result(payload)["standardized_records"]
    by_id = {record["wikidata_id"]: record for record in records}
    assert by_id["Q1518607"]["entity_match"]["level"] == "exact"
    assert by_id["Q1518607"]["entity_match"]["wikidata_kind"] == "listed_company"
    assert by_id["Q631695"]["entity_match"]["level"] == "weak"
    assert by_id["Q15914704"]["entity_match"]["level"] in {"strong", "review", "weak"}
    assert by_id["Q15914704"]["entity_match"]["level"] != "exact" or by_id["Q15914704"]["wikidata_id"] == "Q1518607"



def test_wikidata_entitydata_prefers_seed_language_label_and_extracts_ticker() -> None:
    source = _wikidata_source()
    source._current_query_hint = "贵州茅台酒股份有限公司"
    payload = {
        "entities": {
            "Q1518607": {
                "id": "Q1518607",
                "labels": {
                    "en": {"value": "Kweichow Moutai Company"},
                    "zh": {"value": "贵州茅台酒股份有限公司"},
                },
                "descriptions": {
                    "en": {"value": "company in Renhuai"},
                    "zh": {"value": "中国白酒上市公司"},
                },
                "claims": {
                    "P249": [{"mainsnak": {"datavalue": {"value": "600519"}}}]
                },
            }
        }
    }
    records = source._format_wikidata_entitydata_result(payload)["standardized_records"]
    assert records[0]["entity"] == "贵州茅台酒股份有限公司"
    assert records[0]["ticker"] == "600519"
    assert records[0]["entity_match"]["level"] in {"exact", "strong"}



def test_wikidata_tickers_from_exchange_qualifiers() -> None:
    source = _wikidata_source()
    payload = {
        "entities": {
            "Q1518607": {
                "id": "Q1518607",
                "labels": {"zh": {"value": "贵州茅台酒股份有限公司"}},
                "claims": {
                    "P414": [
                        {
                            "mainsnak": {"datavalue": {"value": {"id": "Q739514"}}},
                            "qualifiers": {
                                "P249": [{"datavalue": {"value": "600519", "type": "string"}}]
                            },
                        }
                    ]
                },
            }
        }
    }
    records = source._format_wikidata_entitydata_result(payload)["standardized_records"]
    assert records[0]["ticker"] == "600519"
    assert "600519" in records[0]["tickers"]


def _moutai_entitydata_payload() -> dict:
    return {
        "entities": {
            "Q1518607": {
                "id": "Q1518607",
                "type": "item",
                "labels": {"zh": {"value": "贵州茅台酒股份有限公司"}},
                "descriptions": {"en": {"value": "company in Renhuai"}},
                "claims": {
                    "P414": [
                        {
                            "mainsnak": {"datavalue": {"value": {"id": "Q739514"}}},
                            "qualifiers": {
                                "P249": [{"datavalue": {"value": "600519", "type": "string"}}]
                            },
                        }
                    ]
                },
            }
        }
    }


def test_wikidata_entitydata_ticker_survives_ingest_and_fans_out_eastmoney() -> None:
    """Name -> QID search, then entitydata, must attach ticker for Eastmoney F10."""
    source = _wikidata_source()
    source._current_query_hint = "贵州茅台酒股份有限公司"
    records = source._format_wikidata_entitydata_result(_moutai_entitydata_payload())["standardized_records"]
    assert records[0]["ticker"] == "600519"

    graph = EvidenceGraph()
    seed = InvestigationEntity(
        id="company:贵州茅台",
        kind=EntityKind.COMPANY,
        name="贵州茅台",
        attributes={"seed": True},
    )
    graph.add_entity(seed)
    search_record = {
        "source_name": "wikidata_public_entity_graph",
        "source_hint": "wikidata_public_entity_graph",
        "source_type": "rest_api",
        "entity": "贵州茅台酒股份有限公司",
        "title": "Wikidata entity graph match: 贵州茅台酒股份有限公司",
        "summary": "wikidata_id=Q1518607",
        "confidence": 0.72,
        "wikidata_id": "Q1518607",
        "entity_match": {
            "level": "strong",
            "score": 0.86,
            "seed_name": "贵州茅台",
            "candidate_name": "贵州茅台酒股份有限公司",
            "wikidata_kind": "company",
        },
    }
    EvidenceIngestor.ingest_standardized_records(
        graph,
        seed_entity_id=seed.id,
        task=SearchTask(
            RetrievalDomain.OWNERSHIP_CONTROL,
            "贵州茅台",
            "wikidata_public_entity_graph",
            "search",
            8,
            (),
            (),
        ),
        records=[search_record],
    )
    EvidenceIngestor.ingest_standardized_records(
        graph,
        seed_entity_id=seed.id,
        task=SearchTask(
            RetrievalDomain.OWNERSHIP_CONTROL,
            "贵州茅台酒股份有限公司",
            "wikidata_public_entity_graph",
            "fanout",
            17,
            (),
            (),
            params={"wikidata_endpoint": "entitydata", "wikidata_id": "Q1518607"},
        ),
        records=records,
    )
    company = graph.entities["company:贵州茅台酒股份有限公司"]
    assert company.attributes.get("ticker") == "600519"
    assert RiskDiscoveryPipeline._company_stock_code(company) == "SH600519"
    tasks = RiskDiscoveryPipeline._identifier_fanout_tasks(company, set(), 2)
    by_hint = {task.source_hint: task for task in tasks}
    assert EASTMONEY_F10_SOURCE in by_hint
    assert by_hint[EASTMONEY_F10_SOURCE].params["stock_code"] == "SH600519"


def test_stock_code_fanout_reads_ticker_from_wikidata_raw_claims() -> None:
    entity = InvestigationEntity(
        id="company:贵州茅台酒股份有限公司",
        kind=EntityKind.COMPANY,
        name="贵州茅台酒股份有限公司",
        attributes={
            "wikidata_id": "Q1518607",
            "raw": _moutai_entitydata_payload()["entities"]["Q1518607"],
        },
    )
    assert entity.attributes.get("ticker") is None
    assert RiskDiscoveryPipeline._company_stock_code(entity) == "SH600519"
    tasks = RiskDiscoveryPipeline._identifier_fanout_tasks(entity, set(), 2)
    by_hint = {task.source_hint: task for task in tasks}
    assert by_hint[EASTMONEY_F10_SOURCE].params["stock_code"] == "SH600519"


def test_eastmoney_source_catalog_is_public_web() -> None:
    from core.intelligence_retrieval import SourceAuthority, SourceCatalog

    profile = SourceCatalog.profile_for(EASTMONEY_F10_SOURCE)
    assert profile.authority is SourceAuthority.PUBLIC_WEB
    assert profile.access.value == "public"
    assert profile.allowed is True


def test_eastmoney_f10_profile_matches_legal_name_against_short_seed() -> None:
    from adapters.eastmoney_f10_adapter import format_eastmoney_f10_standardized_records
    from core.intelligence_retrieval import EvidenceIngestor
    from tests.unit.test_eastmoney_f10_adapter import FIXTURE_HOLDERS, _adapter

    result = _adapter(FIXTURE_HOLDERS).query("SH600519")
    records = format_eastmoney_f10_standardized_records(
        "贵州茅台酒股份有限公司",
        result,
        stock_code="SH600519",
    )
    assert records[0]["unified_social_credit_code"] == "9152000071430580XT"
    graph = EvidenceGraph()
    seed = InvestigationEntity(
        id="company:贵州茅台",
        kind=EntityKind.COMPANY,
        name="贵州茅台",
        attributes={"seed": True},
    )
    graph.add_entity(seed)
    EvidenceIngestor.ingest_standardized_records(
        graph,
        seed_entity_id=seed.id,
        task=SearchTask(
            RetrievalDomain.CORPORATE_REGISTRY,
            "贵州茅台酒股份有限公司",
            EASTMONEY_F10_SOURCE,
            "fanout",
            18,
            (),
            (),
            params={"stock_code": "SH600519"},
        ),
        records=records,
    )
    evidence = [item for item in graph.evidence.values() if item.source == EASTMONEY_F10_SOURCE]
    assert evidence, "expected Eastmoney F10 evidence"
    match = evidence[0].entity_match or {}
    assert match.get("level") in {"exact", "strong"}
    assert "600519" in str(match.get("identifiers") or {}) or "SH600519" in str(match.get("identifiers") or {})
    assert evidence[0].source_profile is not None
    assert evidence[0].source_profile.authority.value == "public_web"
    assert evidence[0].source_profile.allowed is True
    company = graph.entities["company:贵州茅台酒股份有限公司"]
    assert company.attributes.get("unified_social_credit_code") == "9152000071430580XT"
    assert company.attributes.get("ticker") in {"600519", "SH600519"}
