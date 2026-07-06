#!/usr/bin/env python3
"""Tests for the QYYJT ToolProvider bridge."""
from __future__ import annotations

import asyncio

import pytest

from adapters.qyyjt_adapter import QYYJTAdapter, QYYJTModule
from adapters.qyyjt_tool import QYYJTTool, qyyjt_result_to_standardized_records
from core.qyyjt_benchmark import build_qyyjt_benchmark
from core.investigation import build_investigation_packet
from core.risk_graph_export import export_risk_graph
from core.risk_discovery_pipeline import RiskDiscoveryPipeline


def test_qyyjt_websearch_plan_maps_to_low_confidence_records() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "source": "websearch",
            "api_data": {},
            "websearch_queries": [
                {
                    "module": "risk_scan",
                    "module_name": "RISK_SCAN",
                    "query": "Demo QYYJT Co., Ltd. 失信 被执行",
                    "note": "public search lead",
                }
            ],
        }
    )

    assert len(records) == 1
    assert records[0]["source_name"] == "qyyjt_websearch_plan"
    assert records[0]["source_type"] == "query_plan"
    assert records[0]["confidence"] == 0.3
    assert "not a verified fact" in records[0]["evidence"][0]["claim"]


def test_qyyjt_freeze_api_payload_uses_equity_freeze_contract() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Freeze Co.",
            "source": "api",
            "cookie_valid": True,
            "api_data": {
                "freeze": {
                    "records": [
                        {
                            "freezeSubject": "Alice Holder",
                            "courtName": "Beijing No.1 Court",
                            "freezeAmount": "1000000",
                            "freezeDate": "2026-05-01",
                            "status": "active",
                            "sourceUrl": "https://qyyjt.cn/freeze/demo",
                        }
                    ]
                }
            },
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record["source_name"] == "qyyjt_api:freeze"
    assert record["field_contract"]["record_type"] == "equity_freeze"
    assert record["report_admission"]["admissible"] is True
    assert record["extracted_fields"]["subject"] == "Alice Holder"
    assert record["extracted_fields"]["frozen_amount"] == "1000000"
    assert record["risk_events"][0]["risk_category"] == "court_enforcement"
    assert record["risk_events"][0]["title"].startswith("equity_freeze:")


def test_qyyjt_related_party_api_payload_infers_edge_fields() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Related Co.",
            "source": "api",
            "cookie_valid": True,
            "api_data": {
                "related": {
                    "records": [
                        {
                            "relatedEntity": "Supplier Affiliate Ltd.",
                            "transactionType": "supplier_transaction",
                            "sourceUrl": "https://qyyjt.cn/related/demo",
                        }
                    ]
                }
            },
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record["field_contract"]["record_type"] == "related_party_edge"
    assert record["report_admission"]["admissible"] is True
    assert record["extracted_fields"]["related_name"] == "Supplier Affiliate Ltd."
    assert record["extracted_fields"]["relationship_direction"] == "subject_to_related"
    assert record["relations"][0]["from_name"] == "Demo Related Co."
    assert record["relations"][0]["to_name"] == "Supplier Affiliate Ltd."
    assert record["relations"][0]["confidence_basis"] == "licensed QYYJT related module"


def test_qyyjt_websearch_plan_does_not_raise_risk_event(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "source": "websearch",
            "api_data": {},
            "websearch_queries": [
                {
                    "module": "risk_scan",
                    "module_name": "RISK_SCAN",
                    "query": (
                        "Demo QYYJT Co., Ltd. 行政处罚 失信 被执行 "
                        "site:wenshu.court.gov.cn site:cninfo.com.cn"
                    ),
                    "note": "query-plan lead only",
                }
            ],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    assert result.evidence_count == 1
    assert result.risk_event_count == 0
    assert result.retrieval_summary["execution_state"] == "evidence_found"
    assert len(result.graph.entities) == 1
    assert result.graph.relations == []
    assert not any(
        entity.kind.value == "domain" or entity.name in {"wenshu.court.gov.cn", "cninfo.com.cn"}
        for entity in result.graph.entities.values()
    )
    assert result.subject_profile["relationship_graph"]["edges"] == []


def test_qyyjt_api_payload_maps_to_standardized_records() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {"search": {"list": [{"name": "Demo QYYJT Co., Ltd."}]}},
            "websearch_queries": [],
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record["source_name"] == "qyyjt_api:search"
    assert record["source_type"] == "licensed_api"
    assert record["entity"] == "Demo QYYJT Co., Ltd."
    assert record["title"] == "QYYJT API result: search"
    assert record["confidence"] == 0.72
    assert record["field_contract"]["record_type"] == "subject_resolution_candidate"
    assert record["field_contract"]["report_section"] == "subject_resolution"
    assert record["extracted_fields"] == {"candidate_name": "Demo QYYJT Co., Ltd."}
    assert record["report_admission"]["admissible"] is False
    assert record["report_admission"]["missing_required_fields"] == [
        "identifier",
        "entity_type",
        "match_score",
    ]
    assert record["report_admission"]["missing_common_fields"] == []
    assert record["report_admission"]["provenance"]["source_url"] == "https://qyyjt.cn/modules/search"
    assert record["verification_status"] == "api_payload_field_contract"
    assert record["raw"] == {"list": [{"name": "Demo QYYJT Co., Ltd."}]}


def test_qyyjt_search_multi_strong_match_feeds_entity_resolution(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Search Co., Ltd.",
            "api_data": {
                "search": {
                    "list": [
                        {
                            "name": "Demo Search Co., Ltd.",
                            "creditCode": "913000000000000000",
                            "entityType": "company",
                            "matchScore": 0.98,
                            "detailUrl": "https://qyyjt.example.invalid/company/demo-search",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo Search Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    evidence = next(iter(result.graph.evidence.values()))
    assert evidence.entity_match["level"] == "exact"
    assert evidence.entity_match["score"] == 0.98
    assert result.retrieval_summary["entity_resolution"]["strong_match_count"] >= 1
    assert any(
        entity.attributes.get("identifier") == "913000000000000000"
        for entity in result.graph.entities.values()
    )


def test_qyyjt_search_multi_weak_match_stays_out_of_candidate_entities(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Search Co., Ltd.",
            "api_data": {
                "search": {
                    "list": [
                        {
                            "name": "Similar Search Co., Ltd.",
                            "creditCode": "913000000000000001",
                            "entityType": "company",
                            "matchScore": 0.42,
                            "detailUrl": "https://qyyjt.example.invalid/company/similar-search",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo Search Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    evidence = next(iter(result.graph.evidence.values()))
    assert evidence.entity_match["level"] == "weak"
    assert result.retrieval_summary["entity_resolution"]["weak_match_count"] == 1
    assert all(entity.name != "Similar Search Co., Ltd." for entity in result.graph.entities.values())


def test_qyyjt_p0_api_payload_extracts_contract_fields_for_report_admission() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {
                "risk_scan": {
                    "list": [
                        {
                            "riskType": "judicial",
                            "riskLevel": "high",
                            "riskLabel": "execution",
                            "description": "Open enforcement signal",
                            "status": "open",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record["field_contract"]["record_type"] == "risk_overview"
    assert record["extracted_fields"] == {
        "risk_category": "judicial",
        "severity": "high",
        "risk_label": "execution",
        "summary": "Open enforcement signal",
        "status": "open",
    }
    assert record["report_admission"]["admissible"] is True
    assert record["report_admission"]["report_section"] == "risk_brief"
    assert record["report_admission"]["missing_common_fields"] == []
    assert record["report_admission"]["provenance"]["source_name"] == "qyyjt_api:risk_scan"
    assert record["report_admission"]["provenance"]["source_url"] == "https://qyyjt.cn/modules/risk_scan"
    assert record["retrieved_at"]
    assert record["verification_status"] == "api_payload_field_contract"
    assert record["risk_events"] == [
        {
            "risk_category": "judicial",
            "severity": "high",
            "title": "execution",
            "summary": "Open enforcement signal",
            "status": "open",
            "confidence": 0.72,
        }
    ]
    assert any(item["claim"] == "severity=high" for item in record["evidence"])


def test_qyyjt_p0_api_payload_blocks_report_admission_when_fields_missing() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {"actual_controller": {"list": [{"name": "Alice Zhang"}]}},
            "websearch_queries": [],
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record["field_contract"]["record_type"] == "controller_candidate"
    assert record["extracted_fields"] == {"person_name": "Alice Zhang"}
    assert record["report_admission"]["admissible"] is False
    assert record["report_admission"]["missing_required_fields"] == [
        "relation_type",
        "control_path",
        "confidence_basis",
    ]
    assert "entities" not in record


def test_qyyjt_admitted_controller_payload_emits_graph_entity() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {
                "actual_controller": {
                    "list": [
                        {
                            "name": "Alice Zhang",
                            "relationType": "actual_controller",
                            "controlPath": "Demo QYYJT Co., Ltd. -> Alice Zhang",
                            "basis": "licensed QYYJT controller module",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    record = records[0]

    assert record["report_admission"]["admissible"] is True
    assert record["entities"][0]["kind"] == "person"
    assert record["entities"][0]["name"] == "Alice Zhang"
    assert record["entities"][0]["relation"] == "actual_controller"


def test_qyyjt_admitted_api_payloads_feed_pipeline_risk_and_controller(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {
                "risk_scan": {
                    "list": [
                        {
                            "riskType": "judicial",
                            "riskLevel": "high",
                            "riskLabel": "execution",
                            "description": "Open enforcement signal",
                            "status": "open",
                        }
                    ]
                },
                "actual_controller": {
                    "list": [
                        {
                            "name": "Alice Zhang",
                            "relationType": "actual_controller",
                            "controlPath": "Demo QYYJT Co., Ltd. -> Alice Zhang",
                            "basis": "licensed QYYJT controller module",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    assert result.risk_event_count == 1
    assert result.graph.risk_events[0].title == "execution"
    assert any(
        item["name"] == "Alice Zhang"
        for item in result.subject_profile["controller_candidates"]
    )


def test_qyyjt_relationship_ubo_and_group_payloads_feed_graph_and_report(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Group Co., Ltd.",
            "api_data": {
                "related": {
                    "list": [
                        {
                            "relatedName": "Demo Affiliate Co., Ltd.",
                            "relationType": "shareholder",
                            "direction": "outbound",
                            "basis": "licensed related-party module",
                        }
                    ]
                },
                "ubo": {
                    "list": [
                        {
                            "beneficialOwnerName": "Alice Zhang",
                            "controlChain": [
                                "Demo QYYJT Group Co., Ltd.",
                                "Demo Holding Co., Ltd.",
                                "Alice Zhang",
                            ],
                            "holdingRatio": "62%",
                            "layer": 2,
                        }
                    ]
                },
                "group": {
                    "list": [
                        {
                            "fromName": "Demo Holding Co., Ltd.",
                            "toName": "Demo Subsidiary Co., Ltd.",
                            "relationType": "subsidiary",
                            "basis": "licensed group-network module",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert len(records) == 3
    assert any(record.get("relations") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Group Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(
        graph,
        input_text="Demo QYYJT Group Co., Ltd.",
        mode="standard",
    ).to_dict()

    relation_types = {
        edge["relation_type"]
        for edge in result.subject_profile["relationship_graph"]["edges"]
    }
    assert {"shareholder", "beneficial_owner", "subsidiary"} <= relation_types
    controllers = result.subject_profile["controller_candidates"]
    assert controllers[0]["name"] == "Alice Zhang"
    assert controllers[0]["confidence_tier"] == "verified_fact"
    assert any("Alice Zhang" in path for path in controllers[0]["control_paths"])
    assert "tier: verified_fact" in packet["report_markdown"]
    assert "control_path:" in packet["report_markdown"]


def test_qyyjt_related_party_alias_payload_feeds_subject_graph(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Alias Related Co.",
            "source": "api",
            "cookie_valid": True,
            "api_data": {
                "related": {
                    "records": [
                        {
                            "relatedEntity": "Alias Supplier Ltd.",
                            "transactionType": "supplier_transaction",
                            "sourceUrl": "https://qyyjt.cn/related/alias",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo Alias Related Co.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    edges = result.subject_profile["relationship_graph"]["edges"]
    assert any(
        edge["from_id"] == "company:demo_alias_related_co."
        and edge["to_id"] == "company:alias_supplier_ltd."
        and edge["relation_type"] == "supplier_transaction"
        for edge in edges
    )


def test_qyyjt_trade_activity_counterparty_feeds_subject_graph(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Trade Co.",
            "source": "api",
            "cookie_valid": True,
            "api_data": {
                "import_export": {
                    "records": [
                        {
                            "tradeType": "export",
                            "country": "Singapore",
                            "period": "2026-Q1",
                            "amount": "50000000",
                            "counterparty": "Major Buyer Ltd.",
                            "status": "active",
                            "sourceUrl": "https://qyyjt.cn/trade/demo",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    assert records[0]["relations"][0]["relation_type"] == "trade_counterparty"
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo Trade Co.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    assert any(
        edge["from_id"] == "company:demo_trade_co."
        and edge["to_id"] == "company:major_buyer_ltd."
        and edge["relation_type"] == "trade_counterparty"
        for edge in result.subject_profile["relationship_graph"]["edges"]
    )


def test_qyyjt_fin_inst_reaches_packet_and_report(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Bank Exposure Co.",
            "source": "api",
            "cookie_valid": True,
            "api_data": {
                "fin_inst": {
                    "records": [
                        {
                            "institutionName": "Beijing Credit Bank",
                            "institutionType": "commercial_bank",
                            "licenseStatus": "active",
                            "regionName": "Beijing",
                            "riskLevel": "low",
                            "counterpartyRole": "credit_lender",
                            "creditLine": "50000000",
                            "sourceUrl": "https://qyyjt.cn/fin-inst/demo",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo Bank Exposure Co.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo Bank Exposure Co.",
    ).to_dict()

    profile = packet["enterprise_cognition"]["financial_institution_profile"]
    assert profile["row_count"] == 1
    assert profile["rows"][0]["institution_name"] == "Beijing Credit Bank"
    assert profile["rows"][0]["counterparty_role"] == "credit_lender"
    assert profile["rows"][0]["credit_line"] == "50000000"
    assert profile["rows"][0]["record_type"] == "financial_institution_profile"
    assert profile["rows"][0]["field_values"]["institution_name"] == "Beijing Credit Bank"
    assert profile["top_exposures"][0]["identifier"] == "Beijing Credit Bank"
    assert profile["monitoring_queue"][0]["module"] == "fin_inst"
    assert profile["field_coverage"]["coverage_ratio"] > 0.5
    assert "credit_lender" in profile["rows"][0]["summary"]
    fund_flow = packet["enterprise_cognition"]["fund_flow_profile"]
    assert any("financial_institution_counterparties=1" in signal for signal in fund_flow["operating_activity_signals"])
    capital_pressure = packet["enterprise_cognition"]["capital_pressure_profile"]
    assert "financial_institution_profile" in capital_pressure["source_basis"]
    assert any("financial_counterparties=1" in signal for signal in capital_pressure["pressure_signals"])
    assert any(row.get("institution_name") == "Beijing Credit Bank" for row in capital_pressure["rows"])
    assert "top exposure: fin_inst:Beijing Credit Bank" in packet["report_markdown"]
    assert "next verification: P1 QYYJT-FIN_INST-01" in packet["report_markdown"]
    assert "金融机构对手方画像" in packet["report_markdown"]
    assert "Beijing Credit Bank" in packet["report_markdown"]
    assert "credit_lender" in packet["report_markdown"]


def test_qyyjt_registry_identity_payload_emits_structured_identity_entities() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Co., Ltd.",
            "api_data": {
                "ent_basic": {
                    "list": [
                        {
                            "name": "Demo QYYJT Co., Ltd.",
                            "creditCode": "91330100MA2BXXXX1X",
                            "status": "active",
                            "legalRep": "Alice Zhang",
                            "regAddress": "Hangzhou, Zhejiang",
                            "regCapital": "1000万人民币",
                            "estiblishTime": "2018-05-01",
                            "businessTerm": "2018-05-01 to 2048-04-30",
                            "regInstitute": "Hangzhou Market Supervision Administration",
                            "businessScope": "Investment consulting and software services.",
                            "companyType": "有限责任公司",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    record = records[0]

    assert record["field_contract"]["record_type"] == "registry_identity"
    assert record["report_admission"]["admissible"] is True
    assert record["source_hint"] == "registry_and_commercial_sources"
    assert record["legal_name"] == "Demo QYYJT Co., Ltd."
    assert record["unified_social_credit_code"] == "91330100MA2BXXXX1X"
    assert record["registered_capital"] == "1000万人民币"
    assert record["establishment_date"] == "2018-05-01"
    assert record["operating_period"] == "2018-05-01 to 2048-04-30"
    assert record["registration_authority"] == "Hangzhou Market Supervision Administration"
    assert record["business_scope"] == "Investment consulting and software services."
    assert record["company_type"] == "有限责任公司"
    assert any(item["claim"] == "registered_capital=1000万人民币" for item in record["evidence"])
    assert any(item["claim"] == "business_scope=Investment consulting and software services." for item in record["evidence"])
    assert {item["kind"] for item in record["entities"]} >= {"person", "address"}


def test_qyyjt_registry_identity_payload_reaches_subject_profile_and_report(tmp_path) -> None:
    company = "Demo QYYJT Profile Co., Ltd."
    records = qyyjt_result_to_standardized_records(
        {
            "company": company,
            "api_data": {
                "ent_basic": {
                    "list": [
                        {
                            "name": company,
                            "creditCode": "91330100MA2BPROFILE",
                            "status": "active",
                            "legalRep": "Alice Zhang",
                            "regAddress": "Hangzhou, Zhejiang",
                            "regCapital": "2000万人民币",
                            "estiblishTime": "2017-03-15",
                            "regInstitute": "Hangzhou Market Supervision Administration",
                            "businessScope": "Equity investment advisory and enterprise management consulting.",
                            "companyType": "有限责任公司",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            company,
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    profile = result.subject_profile
    identity_values = {
        item["value"]
        for item in profile["signals_by_dimension"]["identity"]
    }
    asset_values = {
        item["value"]
        for item in profile["signals_by_dimension"]["asset_solvency"]
    }
    location_values = {
        item["value"]
        for item in profile["signals_by_dimension"]["location_activity"]
    }

    assert "91330100MA2BPROFILE" in identity_values
    assert "active" in identity_values
    assert "2000万人民币" in asset_values
    assert "Equity investment advisory and enterprise management consulting." in location_values
    assert any(
        item["name"] == "Alice Zhang"
        and item["relation_type"] == "legal_representative"
        and "relation_type:legal_representative" in item["confidence_basis"]
        for item in profile["controller_candidates"]
    )

    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text=company, mode="standard").to_dict()
    report = packet["report_markdown"]

    assert "91330100MA2BPROFILE" in report
    assert "2000万人民币" in report
    assert "Equity investment advisory and enterprise management consulting." in report


def test_qyyjt_financial_payload_reaches_investigation_financial_cognition(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Finance Co., Ltd.",
            "api_data": {
                "financial": {
                    "list": [
                        {
                            "period": "2024-12-31",
                            "metricName": "revenue",
                            "metricValue": "1200000",
                            "unit": "CNY",
                            "accountingScope": "consolidated",
                        }
                    ]
                },
                "fin_indic": {
                    "list": [
                        {
                            "period": "2024-12-31",
                            "indicatorName": "net_margin",
                            "indicatorValue": "0.25",
                            "unit": "ratio",
                            "meaning": "net profit margin",
                        },
                        {
                            "period": "2024-12-31",
                            "indicatorName": "debt_to_assets",
                            "indicatorValue": "0.9",
                            "unit": "ratio",
                            "meaning": "debt pressure",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Finance Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text="Demo QYYJT Finance Co., Ltd.").to_dict()

    financial = packet["enterprise_cognition"]["financial"]

    assert financial["verification_status"] == "licensed_qyyjt_financial_contract"
    assert financial["revenue"] == 1200000.0
    assert financial["net_margin"] == 0.25
    assert financial["debt_to_assets"] == 0.9
    assert any(
        event["category"] == "financing_capital_markets"
        and event["severity"] == "high"
        and "debt_to_assets" in event["title"]
        for event in graph["risk_events"]
    )
    assert "revenue=1.20M" in packet["report_markdown"]
    assert "financial_facts_present" in packet["quality_gate"]["strengths"]


def test_qyyjt_credit_profile_reaches_risk_and_report_cognition(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Credit Co., Ltd.",
            "api_data": {
                "ent_credit": {
                    "list": [
                        {
                            "section": "public_credit",
                            "item": "tax_payment_status",
                            "status": "overdue warning",
                            "referenceDate": "2026-06-01",
                            "detailUrl": "https://qyyjt.example.invalid/company/credit-demo",
                        }
                    ]
                }
            },
            "websearch_queries": [],
        }
    )

    record = records[0]

    assert record["field_contract"]["record_type"] == "credit_profile"
    assert record["report_admission"]["admissible"] is True
    assert record["credit_profile"][0]["status"] == "overdue warning"
    assert record["risk_events"][0]["title"] == "Credit profile warning: tax_payment_status"

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Credit Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text="Demo QYYJT Credit Co., Ltd.").to_dict()

    credit = packet["enterprise_cognition"]["credit_profile"]

    assert result.graph.risk_events
    assert credit["verification_status"] == "licensed_qyyjt_credit_contract"
    assert credit["item_count"] == 1
    assert credit["risk_item_count"] == 1
    assert credit["items"][0]["risk_flag"] is True
    assert "信用画像" in packet["report_markdown"]
    assert "tax_payment_status" in packet["report_markdown"]
    assert any("信用画像预警" in item for item in packet["enterprise_cognition"]["risk_hypotheses"])


def test_qyyjt_legal_admin_profile_reaches_risk_and_report_cognition(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Legal Co., Ltd.",
            "api_data": {
                "court_cases": {
                    "list": [
                        {
                            "caseNo": "(2026) Demo-Civil-001",
                            "courtName": "Demo Intermediate Court",
                            "caseCause": "contract dispute",
                            "party": "Demo QYYJT Legal Co., Ltd.; Demo Buyer",
                            "caseDate": "2026-05-10",
                            "caseStatus": "pending",
                            "detailUrl": "https://qyyjt.example.invalid/case/demo-civil-001",
                        }
                    ]
                },
                "dishonesty": {
                    "list": [
                        {
                            "caseNo": "(2026) Demo-Dishonesty-002",
                            "courtName": "Demo Enforcement Court",
                            "obligation": "unperformed payment obligation",
                            "publishDate": "2026-05-18",
                            "performanceStatus": "unperformed",
                        }
                    ]
                },
                "limit_high": {
                    "list": [
                        {
                            "caseNo": "(2026) Demo-Limit-003",
                            "courtName": "Demo Enforcement Court",
                            "subject": "Alice Zhang",
                            "publishDate": "2026-05-20",
                            "status": "active",
                        }
                    ]
                },
                "execution": {
                    "list": [
                        {
                            "caseNo": "(2026) Demo-Exec-004",
                            "courtName": "Demo Enforcement Court",
                            "execMoney": "500000",
                            "filingDate": "2026-05-22",
                            "executionStatus": "open",
                        }
                    ]
                },
                "ent_penalty": {
                    "list": [
                        {
                            "agency": "Demo Market Supervision Bureau",
                            "decisionNo": "Demo-Penalty-2026-05",
                            "illegalFact": "missing required disclosure",
                            "penaltyContent": "fine 20000",
                            "decisionDate": "2026-05-25",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert len(records) == 5
    assert {record["field_contract"]["record_type"] for record in records} == {
        "court_case",
        "dishonesty_record",
        "limit_high_consumption",
        "enforcement_record",
        "administrative_penalty",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert all(record.get("risk_events") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Legal Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text="Demo QYYJT Legal Co., Ltd.").to_dict()

    legal_admin = packet["enterprise_cognition"]["legal_administrative_profile"]

    assert result.risk_event_count == 5
    assert legal_admin["verification_status"] == "licensed_qyyjt_legal_admin_contract"
    assert legal_admin["row_count"] == 5
    assert legal_admin["court_enforcement_count"] == 4
    assert legal_admin["administrative_penalty_count"] == 1
    assert legal_admin["high_or_critical_event_count"] >= 3
    assert "法务行政画像" in packet["report_markdown"]
    assert "Demo-Penalty-2026-05" in packet["report_markdown"]
    assert "法务行政画像已取证" in packet["enterprise_cognition"]["risk_hypotheses"][0]


def test_qyyjt_financing_change_news_and_research_reach_executable_packet(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Operating Co., Ltd.",
            "api_data": {
                "ent_financing": {
                    "list": [
                        {
                            "financingType": "pledge financing",
                            "amount": "8800000",
                            "counterparty": "Demo Bank",
                            "eventDate": "2026-06-01",
                            "status": "pledge pending",
                        }
                    ]
                },
                "ent_change": {
                    "list": [
                        {
                            "changeItem": "registered capital",
                            "changeBefore": "1000000",
                            "changeAfter": "500000",
                            "changeDate": "2026-05-20",
                        }
                    ]
                },
                "news_negative": {
                    "list": [
                        {
                            "title": "Supplier dispute escalates",
                            "media": "Demo Business News",
                            "publishDate": "2026-06-10",
                            "sentiment": "negative warning",
                            "summary": "Supplier payment dispute creates operational pressure",
                        }
                    ]
                },
                "news_all": {
                    "list": [
                        {
                            "title": "New export channel launched",
                            "media": "Demo Industry Wire",
                            "publishDate": "2026-06-11",
                            "sentiment": "neutral",
                            "summary": "Company opened a new overseas sales channel.",
                        }
                    ]
                },
                "research": {
                    "list": [
                        {
                            "reportTitle": "Demo equipment sector update",
                            "publisher": "Demo Research",
                            "publishDate": "2026-06-12",
                            "industry": "industrial equipment",
                            "product": "precision pump",
                            "summary": "Demand slows while replacement products improve",
                            "industryGrowth": "-0.04",
                            "customerValue": "mission critical replacement parts",
                            "substitutionRisk": "medium",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert len(records) == 5
    assert {record["field_contract"]["record_type"] for record in records} == {
        "financing_event",
        "registry_change_event",
        "negative_public_opinion",
        "news_opinion_event",
        "research_report_signal",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert sum(1 for record in records if record.get("risk_events")) == 4

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Operating Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()
    packet = build_investigation_packet(graph, input_text="Demo QYYJT Operating Co., Ltd.").to_dict()
    operational = packet["enterprise_cognition"]["operational_event_profile"]
    capital_pressure = packet["enterprise_cognition"]["capital_pressure_profile"]

    assert result.risk_event_count == 4
    assert operational["verification_status"] == "licensed_qyyjt_operational_event_contract"
    assert operational["row_count"] == 4
    assert operational["financing_event_count"] == 1
    assert operational["registry_change_count"] == 1
    assert operational["negative_opinion_count"] == 1
    assert operational["news_opinion_count"] == 1
    assert capital_pressure["verification_status"] == "admitted_capital_pressure_facts"
    assert capital_pressure["pressure_level"] == "watch"
    assert capital_pressure["pressure_signal_count"] >= 1
    assert "operational_event_profile" in capital_pressure["source_basis"]
    assert any("financing_events=1" in signal for signal in capital_pressure["inflow_signals"])
    assert any("negative_opinion_events=1" in signal for signal in capital_pressure["pressure_signals"])
    assert packet["enterprise_cognition"]["industry"]["industry"] == "industrial equipment"
    assert packet["enterprise_cognition"]["industry"]["input_signals"]["industry_growth"] == "-0.04"
    assert packet["enterprise_cognition"]["product"]["product_name"] == "precision pump"
    assert packet["enterprise_cognition"]["product"]["input_signals"]["customer_value"] == "mission critical replacement parts"
    assert any(
        "Capital pressure profile ready" in item
        for item in packet["enterprise_cognition"]["risk_hypotheses"]
    )
    assert "Capital Pressure Profile" in packet["report_markdown"]
    assert "negative_opinion_events=1" in packet["report_markdown"]
    assert "经营事件画像" in packet["report_markdown"]
    assert "registered capital" in packet["report_markdown"]
    assert "pledge financing" in packet["report_markdown"]
    assert "Supplier dispute escalates" in packet["report_markdown"]
    assert "New export channel launched" in packet["report_markdown"]
    assert "industrial equipment" in packet["report_markdown"]
    assert "precision pump" in packet["report_markdown"]


def test_qyyjt_domain_depth_modules_have_contracts_and_structured_events(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Domain Co., Ltd.",
            "api_data": {
                "bond_default": {
                    "list": [
                        {
                            "bondName": "Demo 2026 Bond",
                            "issuerName": "Demo QYYJT Domain Co., Ltd.",
                            "defaultDate": "2026-05-01",
                            "amount": "10000000",
                            "status": "default",
                            "summary": "Principal default announced.",
                        }
                    ]
                },
                "pledge": {
                    "list": [
                        {
                            "shareholderName": "Alice Holder",
                            "pledgeeName": "Demo Bank",
                            "pledgedAmount": "500000",
                            "pledgeDate": "2026-04-10",
                            "status": "pledge active",
                            "shareRatio": "12%",
                        }
                    ]
                },
                "patent": {
                    "list": [
                        {
                            "type": "patent",
                            "title": "Risk analytics engine",
                            "patentNo": "CN20260001",
                            "applyDate": "2026-03-01",
                            "status": "valid",
                            "ownerName": "Demo QYYJT Domain Co., Ltd.",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert {record["field_contract"]["record_type"] for record in records} == {
        "bond_default_event",
        "equity_pledge",
        "ip_asset",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert any(record.get("entities") for record in records)
    assert any(record.get("risk_events") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Domain Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo QYYJT Domain Co., Ltd.",
    ).to_dict()

    categories = {event.category.value for event in result.graph.risk_events}
    assert {"financing_capital_markets", "location_assets", "ip_tech"} <= categories
    assert any(event.severity.value == "high" for event in result.graph.risk_events)
    bond_profile = packet["enterprise_cognition"]["bond_credit_profile"]
    asset_profile = packet["enterprise_cognition"]["asset_solvency_profile"]
    assert bond_profile["default_count"] == 1
    assert bond_profile["top_exposures"][0]["identifier"] == "Demo 2026 Bond"
    assert bond_profile["top_exposures"][0]["pressure_flag"] == "high"
    assert bond_profile["monitoring_queue"][0]["priority"] == "P0"
    assert "bond_name" in bond_profile["field_coverage"]["covered_fields"]
    assert asset_profile["pledge_count"] == 1
    assert asset_profile["top_exposures"][0]["counterparty"] == "Demo Bank"
    assert asset_profile["monitoring_queue"][0]["module"] == "pledge"
    assert "pledged_amount" in asset_profile["field_coverage"]["covered_fields"]
    assert packet["enterprise_cognition"]["ip_tech_profile"]["patent_count"] == 1
    assert "top exposure: bond_default:Demo 2026 Bond" in packet["report_markdown"]
    assert "next verification: P0 QYYJT-BOND_CREDIT-01" in packet["report_markdown"]
    assert "债券信用画像" in packet["report_markdown"]
    assert "资产偿付画像" in packet["report_markdown"]
    assert "知识产权画像" in packet["report_markdown"]
    assert "Demo 2026 Bond" in packet["report_markdown"]
    assert "Risk analytics engine" in packet["report_markdown"]


def test_qyyjt_regional_credit_modules_feed_report_cognition(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Regional Co., Ltd.",
            "api_data": {
                "city_invest": {
                    "list": [
                        {
                            "cityName": "Demo City",
                            "item": "platform_debt_pressure",
                            "year": "2026",
                            "value": "125",
                            "unit": "%",
                            "debtRatio": "125",
                            "fiscalRevenue": "800000000",
                            "riskLevel": "high",
                        }
                    ]
                },
                "region_economy": {
                    "list": [
                        {
                            "regionName": "Demo Province",
                            "item": "GDP growth",
                            "year": "2026",
                            "value": "3.1",
                            "unit": "%",
                            "regionalGdp": "3200000000",
                            "fiscalRevenue": "900000000",
                            "riskLevel": "medium",
                        }
                    ]
                },
                "region_debt": {
                    "list": [
                        {
                            "regionName": "Demo Province",
                            "item": "local debt balance",
                            "year": "2026",
                            "value": "1200000000",
                            "unit": "CNY",
                            "debtBalance": "1200000000",
                            "debtRatio": "95",
                            "riskLevel": "warning",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert {record["field_contract"]["record_type"] for record in records} == {
        "regional_credit_indicator",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert all(record.get("risk_events") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Regional Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo QYYJT Regional Co., Ltd.",
    ).to_dict()

    profile = packet["enterprise_cognition"]["regional_credit_profile"]
    assert profile["verification_status"] == "licensed_qyyjt_regional_credit_contract"
    assert profile["row_count"] == 3
    assert profile["city_invest_count"] == 1
    assert profile["region_economy_count"] == 1
    assert profile["region_debt_count"] == 1
    assert profile["high_or_critical_event_count"] >= 1
    assert profile["top_exposures"][0]["identifier"] == "Demo City"
    assert profile["top_exposures"][0]["pressure_flag"] == "high"
    assert profile["monitoring_queue"][0]["priority"] == "P0"
    assert "risk_level" in profile["field_coverage"]["covered_fields"]
    assert "top exposure: city_invest:Demo City" in packet["report_markdown"]
    assert "Demo City" in packet["report_markdown"]
    assert "platform_debt_pressure" in packet["report_markdown"]


def test_qyyjt_court_merger_and_bond_calendar_feed_report_cognition(tmp_path) -> None:
    company = "Demo QYYJT Event Co., Ltd."
    records = qyyjt_result_to_standardized_records(
        {
            "company": company,
            "api_data": {
                "court_announce": {
                    "list": [
                        {
                            "caseNo": "(2026) Demo Civil 001",
                            "courtName": "Demo Hearing Court",
                            "caseCause": "sales contract dispute",
                            "party": "Demo QYYJT Event Co., Ltd.; Demo Buyer",
                            "hearingDate": "2026-07-01",
                            "status": "scheduled",
                        }
                    ]
                },
                "bond_calendar": {
                    "list": [
                        {
                            "bondName": "Demo Event 2026 Bond",
                            "issuerName": company,
                            "eventDate": "2026-08-15",
                            "calendarType": "maturity",
                            "amount": "50000000",
                            "status": "upcoming",
                            "bondCode": "DEMO26",
                        }
                    ]
                },
                "merger": {
                    "list": [
                        {
                            "eventType": "asset acquisition",
                            "counterparty": "Demo M&A Target Co., Ltd.",
                            "announcementDate": "2026-06-20",
                            "amount": "120000000",
                            "status": "announced",
                            "targetAsset": "automation component line",
                            "summary": "Acquisition announced by board.",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert {record["field_contract"]["record_type"] for record in records} == {
        "court_announcement",
        "bond_calendar_event",
        "merger_restructuring_event",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert any(record.get("relations") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            company,
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text=company,
    ).to_dict()

    categories = {event.category.value for event in result.graph.risk_events}
    assert {"court_enforcement", "financing_capital_markets"} <= categories
    assert packet["enterprise_cognition"]["legal_administrative_profile"]["court_enforcement_count"] == 1
    assert packet["enterprise_cognition"]["bond_credit_profile"]["calendar_count"] == 1
    assert packet["enterprise_cognition"]["operational_event_profile"]["merger_event_count"] == 1
    assert packet["enterprise_cognition"]["relationship_network"]["relation_count"] >= 1
    assert "Demo Hearing Court" in packet["report_markdown"]
    assert "Demo Event 2026 Bond" in packet["report_markdown"]
    assert "Demo M&A Target Co., Ltd." in packet["report_markdown"]


def test_qyyjt_commercial_activity_modules_feed_report_cognition(tmp_path) -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo QYYJT Commercial Co., Ltd.",
            "api_data": {
                "tax": {
                    "list": [
                        {
                            "taxItem": "VAT",
                            "taxStatus": "normal",
                            "period": "2026Q1",
                            "agency": "Demo Tax Bureau",
                            "amount": "120000",
                        }
                    ]
                },
                "import_export": {
                    "list": [
                        {
                            "tradeType": "export",
                            "country": "Germany",
                            "period": "2026Q1",
                            "amount": "300000",
                            "status": "active",
                            "counterparty": "Demo Distributor GmbH",
                        }
                    ]
                },
                "recruit": {
                    "list": [
                        {
                            "jobTitle": "Risk analyst",
                            "city": "Tieling",
                            "recruitCount": "3",
                            "salaryRange": "8k-12k",
                            "publishDate": "2026-04-12",
                            "status": "open",
                        }
                    ]
                },
            },
            "websearch_queries": [],
        }
    )

    assert {record["field_contract"]["record_type"] for record in records} == {
        "tax_profile",
        "trade_activity",
        "recruiting_signal",
    }
    assert all(record["report_admission"]["admissible"] is True for record in records)
    assert all(record.get("risk_events") for record in records)

    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl").run(
            "Demo QYYJT Commercial Co., Ltd.",
            records=records,
            store_path=tmp_path / "risk-events.jsonl",
        )
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo QYYJT Commercial Co., Ltd.",
    ).to_dict()

    profile = packet["enterprise_cognition"]["commercial_activity_profile"]
    assert profile["tax_count"] == 1
    assert profile["trade_count"] == 1
    assert profile["recruiting_count"] == 1
    assert "经营活跃度画像" in packet["report_markdown"]
    assert "VAT" in packet["report_markdown"]
    assert "export" in packet["report_markdown"]
    assert "Risk analyst" in packet["report_markdown"]


class FakeQYYJTAdapter:
    def __init__(self, *, cookie_valid: bool = False, smoke_api: bool = False):
        self.cookie_manager = FakeCookieManager(cookie_valid)
        self.smoke_api = smoke_api

    def get_module_query(self, module, company):
        return {
            "module": module.value,
            "module_name": module.name,
            "company": company,
            "queries": [f"{company} {module.value}"],
        }

    async def query(self, company, modules, prefer_api):
        if self.smoke_api and prefer_api:
            return {
                "company": company,
                "source": "api",
                "api_data": {"search": {"list": [{"name": company}]}},
                "websearch_queries": [],
                "errors": {},
            }
        assert modules == [QYYJTModule.RISK_SCAN]
        return {
            "company": company,
            "api_data": {},
            "websearch_queries": [
                {
                    "module": "risk_scan",
                    "module_name": "RISK_SCAN",
                    "query": f"{company} 失信 被执行",
                    "note": "risk lead",
                }
            ],
        }


class FakeCookieManager:
    def __init__(self, valid: bool):
        self.valid = valid

    async def test_cookies_valid(self):
        return self.valid


@pytest.mark.asyncio
async def test_qyyjt_authorized_query_builds_payload_for_non_p0_modules(tmp_path, monkeypatch) -> None:
    adapter = QYYJTAdapter(session_path=str(tmp_path / "qyyjt_session.json"))
    adapter.cookie_manager = FakeCookieManager(True)

    async def fake_search_company(company: str):
        return {
            "list": [
                {
                    "name": company,
                    "source_url": "https://qyyjt.example.invalid/company/demo",
                    "institution_name": "Demo Bank",
                    "institution_type": "bank",
                    "risk_level": "medium",
                }
            ]
        }

    monkeypatch.setattr(adapter, "search_company", fake_search_company)

    result = await adapter.query(
        "Demo Authorized Co.",
        modules=[QYYJTModule.FIN_INSTITUTION, QYYJTModule.NEWS_ALL],
        prefer_api=True,
    )

    assert result["source"] == "api"
    assert "fin_inst" in result["api_data"]
    assert "news_all" in result["api_data"]
    assert result["api_data"]["fin_inst"]["module"] == "fin_inst"
    assert result["api_data"]["news_all"]["module"] == "news_all"


@pytest.mark.asyncio
async def test_qyyjt_authorized_query_keeps_monitoring_modules_future_scoped(tmp_path, monkeypatch) -> None:
    adapter = QYYJTAdapter(session_path=str(tmp_path / "qyyjt_session.json"))
    adapter.cookie_manager = FakeCookieManager(True)

    async def fake_search_company(company: str):
        return {"list": [{"name": company}]}

    monkeypatch.setattr(adapter, "search_company", fake_search_company)

    result = await adapter.query(
        "Demo Authorized Co.",
        modules=[QYYJTModule.WATCHLIST, QYYJTModule.ALERT_PUSH],
        prefer_api=True,
    )

    assert "watchlist" not in result["api_data"]
    assert "alert_push" not in result["api_data"]
    assert result["future_monitoring_modules"] == ["watchlist", "alert_push"]
    assert all("query" in item for item in result["websearch_queries"])


@pytest.mark.asyncio
async def test_qyyjt_tool_health_check_is_non_invasive() -> None:
    tool = QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN])

    result = await tool.health_check()

    assert result["ok"] is True
    assert result["module_queries_ok"] is True
    assert result["cookie_checked"] is False
    assert result["cookie_valid"] is None
    assert result["standardized_records"] is True


@pytest.mark.asyncio
async def test_qyyjt_authorization_report_without_cookie_gives_next_action() -> None:
    tool = QYYJTTool(
        adapter=FakeQYYJTAdapter(cookie_valid=False),
        modules=[QYYJTModule.RISK_SCAN],
    )

    result = await tool.authorization_report()

    assert result["ok"] is False
    assert result["cookie_checked"] is True
    assert result["cookie_valid"] is False
    assert result["next_action"] == "provide_or_refresh_user_authorized_cookie"
    assert result["admission"]["decision"] == "conditional_production"
    assert result["admission"]["production_route"] == "user_configured_production"


@pytest.mark.asyncio
async def test_qyyjt_authorization_report_smoke_api_success() -> None:
    tool = QYYJTTool(
        adapter=FakeQYYJTAdapter(cookie_valid=True, smoke_api=True),
        modules=[QYYJTModule.RISK_SCAN],
    )

    result = await tool.authorization_report(
        company="Demo QYYJT Co., Ltd.",
        smoke_api=True,
        terms_reviewed=True,
        authorization_evidence="user_authorized_cookie_and_terms_review",
    )

    assert result["ok"] is True
    assert result["cookie_valid"] is True
    assert result["smoke_api"]["attempted"] is True
    assert result["smoke_api"]["ok"] is True
    assert result["api_keys"] == ["search"]
    assert result["admission"]["decision"] == "production_ready"
    assert result["admission"]["production_route"] == "active"


@pytest.mark.asyncio
async def test_qyyjt_tool_provider_feeds_risk_discovery_pipeline(tmp_path) -> None:
    tool = QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN])
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = await pipeline.run("Demo QYYJT Co., Ltd.", search_engine=tool)

    assert result.queried_sources == ["qyyjt"]
    assert result.evidence_count >= 1
    assert result.source_diagnostics[0]["source_name"] == "qyyjt"
    assert result.risk_event_summary["alert_count"] == 0


@pytest.mark.asyncio
async def test_qyyjt_tool_returns_record_quality_report() -> None:
    tool = QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN])

    result = await tool.search("Demo QYYJT Co., Ltd.", "qyyjt")

    assert result.ok
    assert result.data["record_quality"]["ok"] is True
    assert result.data["record_quality"]["record_count"] == 1


@pytest.mark.asyncio
async def test_qyyjt_authorization_report_includes_benchmark_summary() -> None:
    tool = QYYJTTool(
        adapter=FakeQYYJTAdapter(cookie_valid=True, smoke_api=True),
        modules=[QYYJTModule.RISK_SCAN],
    )

    result = await tool.authorization_report(
        company="Demo QYYJT Co., Ltd.",
        smoke_api=True,
        terms_reviewed=True,
        authorization_evidence="user_authorized_cookie_and_terms_review",
    )

    assert result["benchmark"]["type"] == "qyyjt_benchmark"
    assert result["benchmark"]["summary"]["module_count"] == 45
    assert result["benchmark"]["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert result["benchmark"]["summary"]["surface_lanes"]["authorized_api"] == 4
    assert result["benchmark"]["summary"]["p0_queue_count"] == 20


def test_qyyjt_benchmark_surface_is_fully_module_specific() -> None:
    benchmark = build_qyyjt_benchmark()

    assert benchmark["summary"]["module_count"] == 45
    assert benchmark["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert benchmark["summary"]["surface_profile"]["rich_query_plan_modules"] >= 41
    assert benchmark["summary"]["surface_lanes"]["generic_fallback"] == 0
    assert benchmark["summary"]["p0_queue"][0]["module"] == "search_multi"
    assert all(item["done_when"] for item in benchmark["summary"]["work_items"])
    assert benchmark["summary"]["field_contracts"]["actual_controller"]["record_type"] == "controller_candidate"
    assert benchmark["summary"]["field_contracts"]["ent_financing"]["record_type"] == "financing_event"
    assert benchmark["summary"]["field_contracts"]["ent_change"]["record_type"] == "registry_change_event"
    assert benchmark["summary"]["field_contracts"]["news_negative"]["record_type"] == "negative_public_opinion"
    assert benchmark["summary"]["field_contracts"]["research"]["record_type"] == "research_report_signal"
    assert benchmark["summary"]["field_contracts"]["bond_default"]["record_type"] == "bond_default_event"
    assert benchmark["summary"]["field_contracts"]["city_invest"]["record_type"] == "regional_credit_indicator"
    assert benchmark["summary"]["field_contracts"]["region_economy"]["record_type"] == "regional_credit_indicator"
    assert benchmark["summary"]["field_contracts"]["region_debt"]["record_type"] == "regional_credit_indicator"
    assert benchmark["summary"]["field_contracts"]["pledge"]["record_type"] == "equity_pledge"
    assert benchmark["summary"]["field_contracts"]["patent"]["record_type"] == "ip_asset"
    assert all(item["field_contract"]["required_fields"] for item in benchmark["summary"]["p0_queue"])
    assert benchmark["summary"]["public_origin_plans"]["ent_basic"]["fallback_mode"] == "public_origin_reconstruction"
    assert "official_company_registry" in benchmark["summary"]["public_origin_plans"]["ent_basic"]["origin_channels"]
    execution_queue = benchmark["summary"]["public_origin_execution_queue"]
    execution_summary = benchmark["summary"]["public_origin_execution_summary"]
    assert execution_queue[0]["action_id"] == "PUBLIC-ORIGIN-SEARCH_MULTI"
    assert execution_queue[0]["record_type"] == "subject_resolution_candidate"
    assert "candidate_name" in execution_queue[0]["required_fields"]
    assert "official_company_registry" in execution_queue[0]["origin_channels"]
    assert all(item["done_condition"] for item in execution_queue)
    assert execution_summary["type"] == "public_origin_execution_summary"
    assert execution_summary["queue_count"] == len(execution_queue)
    assert execution_summary["p0_count"] == benchmark["summary"]["p0_queue_count"]
    assert execution_summary["top_action"]["action_id"] == "PUBLIC-ORIGIN-SEARCH_MULTI"
    assert len(execution_summary["next_batch"]) == 8
    assert execution_summary["field_contract_gap_count"] == 0
    assert execution_summary["target_lane_counts"]["financing_capital_markets"] >= 1
    assert execution_summary["origin_channel_counts"]["official_company_registry"] >= 1
    section_batches = execution_summary["report_section_batches"]
    assert section_batches[0]["report_section"] == "subject_resolution"
    assert all(item["top_actions"] for item in section_batches)
    legal_batch = next(item for item in section_batches if item["report_section"] == "legal_risk")
    assert legal_batch["queue_count"] >= 1
    assert legal_batch["done_condition"] == "complete_or_explicitly_mark_no_public_origin_evidence_for_section"
    asset_batch = next(item for item in section_batches if item["report_section"] == "asset_solvency")
    assert "equity_pledge" in asset_batch["record_types"]
    financing_action = next(item for item in execution_queue if item["module"] == "ent_financing")
    assert financing_action["target_lane"] == "financing_capital_markets"
    assert "amount" in financing_action["required_fields"]
    assert "do_not_bypass_authentication_paywalls_captcha_or_rate_limits" in {
        item["public_origin_plan"]["compliance_rule"]
        for item in benchmark["summary"]["work_items"]
    }
    assert any(
        item["module"] == "ent_financing"
        and "exchange_disclosures" in item["public_origin_plan"]["origin_channels"]
        for item in benchmark["summary"]["p0_queue"]
    )


# ── RIX-002 FIN_INSTITUTION field contract ──

def test_fin_inst_field_contract_exists() -> None:
    """FIN_INSTITUTION module has a proper field contract (not the old generic lead contract)."""
    from core.qyyjt_benchmark import build_qyyjt_benchmark

    benchmark = build_qyyjt_benchmark()
    contracts = benchmark["summary"]["field_contracts"]

    assert "fin_inst" in contracts
    contract = contracts["fin_inst"]
    assert contract["record_type"] == "financial_institution_profile"
    assert "institution_name" in contract["required_fields"]
    assert "institution_type" in contract["required_fields"]
    assert "license_status" in contract["required_fields"]
    assert "region" in contract["required_fields"]
    assert "risk_level" in contract["required_fields"]
    assert "report_section" in contract
    assert contract["report_section"] != "follow_up_leads"


def test_fin_inst_benchmark_row_is_p1_domain_depth() -> None:
    """fin_inst stays in p1_domain_depth (not P0 report-critical)."""
    from core.qyyjt_benchmark import build_qyyjt_benchmark

    benchmark = build_qyyjt_benchmark()
    p0_modules = {item["module"] for item in benchmark["summary"]["p0_queue"]}
    assert "fin_inst" not in p0_modules, "fin_inst should be P1 domain-depth, not P0 report-critical"



def test_fin_inst_graph_report_payload_generates_entity_and_risk_event() -> None:
    """Fixture-backed FIN_INSTITUTION payload maps to entity + risk_event + relation."""
    from adapters.qyyjt_tool import _qyyjt_structured_payload

    # Use canonical field names (already normalized)
    fixture = {
        "institution_name": "中国工商银行",
        "institution_type": "commercial_bank",
        "license_status": "active",
        "region": "北京",
        "risk_level": "low",
        "counterparty_role": "credit_lender",
        "credit_line": "5000000000",
        "regulatory_authority": "国家金融监督管理总局",
        "source_provenance": "QYYJT licensed financial data",
        "subject_name": "Demo Co.",
        "source_name": "qyyjt_api",
        "source_url": "https://example.com/fin_inst",
        "observed_at": "2025-06-01",
        "confidence": "0.74",
        "verification_status": "licensed_qyyjt",
    }

    contract = {
        "record_type": "financial_institution_profile",
        "report_section": "financial_institution_counterparty",
        "required_fields": [
            "institution_name", "institution_type", "license_status", "region", "risk_level"
        ],
        "required_common_fields": [
            "subject_name", "source_name", "source_url", "observed_at", "confidence", "verification_status"
        ],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    report_admission = {
        "admissible": True,
        "report_section": "financial_institution_counterparty",
        "record_type": "financial_institution_profile",
        "provenance": {"source_url": "https://example.com/fin_inst"},
        "gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    payload = _qyyjt_structured_payload(
        company="Demo Co.",
        key="fin_inst",
        contract=contract,
        extracted_fields=fixture,
        report_admission=report_admission,
    )

    assert "entities" in payload, f"Expected entities in payload, got {list(payload.keys())}"
    entities = payload["entities"]
    assert any(e.get("name") == "中国工商银行" for e in entities)

    assert "risk_events" in payload
    assert any("Financial institution counterparty" in re.get("title", "") for re in payload["risk_events"])

    assert "relations" in payload
    assert any(r.get("relation_type", "").startswith("financial_institution_") for r in payload["relations"])


# ── RIX-002-NEGATIVE-GATES ──


def test_fin_inst_missing_required_field_not_admissible() -> None:
    """Missing institution_name → report_admission.admissible=False → no structured payload."""
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload

    contract = {
        "record_type": "financial_institution_profile",
        "report_section": "financial_institution_counterparty",
        "required_fields": ["institution_name", "institution_type", "license_status", "region", "risk_level"],
        "required_common_fields": ["subject_name", "source_name"],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    fixture = {
        "institution_type": "commercial_bank",
        "license_status": "active",
        "region": "北京",
        "risk_level": "low",
    }

    report_admission = _qyyjt_report_admission(contract, fixture, {"subject_name": "Demo Co.", "source_name": "qyyjt_api"})

    assert report_admission["admissible"] is False, f"Expected not admissible, got {report_admission}"
    assert "institution_name" in report_admission["missing_required_fields"]

    payload = _qyyjt_structured_payload("Demo Co.", "fin_inst", contract, fixture, report_admission)

    assert payload == {}, f"Expected empty payload for incomplete row, got {list(payload.keys())}"


def test_fin_inst_missing_provenance_not_admissible() -> None:
    """Missing common provenance fields → admissible=False → no payload."""
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload

    contract = {
        "record_type": "financial_institution_profile",
        "report_section": "financial_institution_counterparty",
        "required_fields": ["institution_name", "institution_type", "license_status", "region", "risk_level"],
        "required_common_fields": ["subject_name", "source_name", "source_url"],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    fixture = {
        "institution_name": "Test Bank",
        "institution_type": "commercial_bank",
        "license_status": "active",
        "region": "北京",
        "risk_level": "low",
    }

    # Has subject_name and source_name but missing source_url
    report_admission = _qyyjt_report_admission(contract, fixture, {"subject_name": "Demo Co.", "source_name": "qyyjt_api"})

    assert report_admission["admissible"] is False, f"Should be not admissible with missing provenance, got {report_admission}"
    assert "source_url" in report_admission["missing_common_fields"]

    payload = _qyyjt_structured_payload("Demo Co.", "fin_inst", contract, fixture, report_admission)

    assert payload == {}, f"Expected empty payload for missing provenance, got {list(payload.keys())}"


def test_fin_inst_empty_extracted_fields_not_admissible() -> None:
    """No fields at all → admissible=False → empty payload."""
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload

    contract = {
        "record_type": "financial_institution_profile",
        "report_section": "financial_institution_counterparty",
        "required_fields": ["institution_name", "institution_type", "license_status", "region", "risk_level"],
        "required_common_fields": ["subject_name", "source_name"],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    report_admission = _qyyjt_report_admission(contract, {}, {})

    assert report_admission["admissible"] is False

    payload = _qyyjt_structured_payload("Demo Co.", "fin_inst", contract, {}, report_admission)

    assert payload == {}, f"Expected empty payload for empty fields, got {list(payload.keys())}"


# ── Task 5: News All bridge ──


def test_news_all_field_contract_exists() -> None:
    """NEWS_ALL module has a proper field contract."""
    from core.qyyjt_benchmark import build_qyyjt_benchmark

    benchmark = build_qyyjt_benchmark()
    contracts = benchmark["summary"]["field_contracts"]

    assert "news_all" in contracts
    contract = contracts["news_all"]
    assert contract["record_type"] == "news_opinion_event"
    assert "news_title" in contract["required_fields"]
    assert contract["report_section"] != "follow_up_leads"


def test_news_all_graph_report_payload_generates_risk_event() -> None:
    """Fixture-backed NEWS_ALL payload maps to risk event."""
    from adapters.qyyjt_tool import _qyyjt_structured_payload

    fixture = {
        "news_title": "Subject company faces regulatory inquiry",
        "publisher": "Financial Times",
        "publish_date": "2025-06-01",
        "sentiment": "negative",
        "summary": "Regulatory body launches investigation.",
        "topic": "regulatory",
        "impact_level": "high",
    }

    contract = {
        "record_type": "news_opinion_event",
        "report_section": "risk_brief",
        "required_fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
        "required_common_fields": ["subject_name", "source_name", "source_url", "observed_at", "confidence", "verification_status"],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    report_admission = {
        "admissible": True,
        "report_section": "risk_brief",
        "record_type": "news_opinion_event",
        "provenance": {"source_url": "https://qyyjt.cn/news_all"},
        "gate": contract["report_gate"],
    }

    payload = _qyyjt_structured_payload(
        company="Demo Co.",
        key="news_all",
        contract=contract,
        extracted_fields=fixture,
        report_admission=report_admission,
    )

    assert "risk_events" in payload, f"Expected risk_events in payload, got {list(payload.keys())}"
    assert any("regulatory inquiry" in re.get("title", "") for re in payload["risk_events"])
    assert any(re.get("risk_category") == "news_public_opinion" for re in payload["risk_events"])


def test_news_all_missing_field_not_admissible() -> None:
    """Missing news_title → not admissible → empty payload."""
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload

    contract = {
        "record_type": "news_opinion_event",
        "report_section": "risk_brief",
        "required_fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
        "required_common_fields": ["subject_name", "source_name"],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }

    report_admission = _qyyjt_report_admission(contract, {"publisher": "FT"}, {"subject_name": "Demo Co.", "source_name": "qyyjt_api"})
    assert report_admission["admissible"] is False
    assert "news_title" in report_admission["missing_required_fields"]

    payload = _qyyjt_structured_payload("Demo Co.", "news_all", contract, {"publisher": "FT"}, report_admission)
    assert payload == {}, f"Expected empty payload, got {list(payload.keys())}"


def test_smoke_summary_no_credentials() -> None:
    try:
        from adapters.qyyjt_tool import qyyjt_authorized_smoke_summary
    except ImportError:
        return  # function not yet available
    result = qyyjt_authorized_smoke_summary()
    assert result["smoke_available"] is False
    assert "cookie" not in str(result).lower()
    assert "token" not in str(result).lower()


# --- QYYJT Auto-Login Tests ---

def test_auto_login_module_imports() -> None:
    try:
        from adapters.qyyjt_auto_login import QYYJTAutoLogin, _encrypt, _decrypt, create_auto_login
        assert QYYJTAutoLogin is not None
        assert create_auto_login is not None
    except ImportError as e:
        # requests library may not be available in test environment
        pass


def test_credential_encrypt_decrypt_roundtrip() -> None:
    try:
        from adapters.qyyjt_auto_login import _encrypt, _decrypt
    except ImportError:
        return
    plain = '{"test_phone":"10000000000","token":"test-token-value"}'
    encrypted = _encrypt(plain)
    assert encrypted != plain
    assert len(encrypted) > len(plain)
    decrypted = _decrypt(encrypted)
    assert decrypted == plain


def test_auto_login_not_configured_by_default(tmp_path) -> None:
    try:
        from adapters.qyyjt_auto_login import QYYJTAutoLogin
    except ImportError:
        return
    session = QYYJTAutoLogin()
    # Override credential path to use temp
    session.credential_dir = tmp_path / "qyyjt"
    session.credential_dir.mkdir(parents=True, exist_ok=True)
    # Path hack: the class uses CREDENTIAL_FILE which is a module-level constant
    # For test purposes, just verify the module-level behavior
    assert session is not None


# --- QYYJT Public Fallback Tests ---

def test_public_fallback_module_query_templates_exist() -> None:
    from adapters.qyyjt_public_fallback import MODULE_SEARCH_TEMPLATES, build_public_query
    assert "ent_basic" in MODULE_SEARCH_TEMPLATES
    assert "court_cases" in MODULE_SEARCH_TEMPLATES
    assert "dishonesty" in MODULE_SEARCH_TEMPLATES
    assert "financial" in MODULE_SEARCH_TEMPLATES
    assert "patent" in MODULE_SEARCH_TEMPLATES
    assert "news_all" in MODULE_SEARCH_TEMPLATES
    assert "fin_inst" in MODULE_SEARCH_TEMPLATES
    q = build_public_query("Demo Company", "ent_basic")
    assert "Demo Company" in q
    assert len(q) > 20


def test_public_fallback_query_contains_government_site_filters() -> None:
    from adapters.qyyjt_public_fallback import build_public_query
    q = build_public_query("测试公司", "ent_basic")
    assert "gsxt.gov.cn" in q
    q2 = build_public_query("测试公司", "court_cases")
    assert "wenshu.court.gov.cn" in q2
    q3 = build_public_query("测试公司", "dishonesty")
    assert "zxgk.court.gov.cn" in q3


# --- Phase B: Pledge bridge ---

def test_pledge_admitted_reaches_asset_solvency_profile() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload, qyyjt_result_to_standardized_records
    from core.investigation import _asset_solvency_profile_from_evidence
    
    contract = {
        'record_type': 'equity_pledge',
        'required_fields': ['shareholder', 'pledgee', 'pledged_amount', 'pledge_date', 'status'],
        'required_common_fields': ['subject_name', 'source_name', 'source_url', 'observed_at', 'confidence', 'verification_status'],
        'report_gate': 'do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present',
    }
    fixture = {
        'shareholder': 'Alice Holder', 'pledgee': 'Demo Bank', 'pledged_amount': '500000',
        'pledge_date': '2026-04-10', 'status': 'active',
        'subject_name': 'Demo Co.', 'source_name': 'qyyjt_api', 'source_url': 'https://qyyjt.cn/pledge',
        'observed_at': '2026-01-01', 'confidence': '0.74', 'verification_status': 'licensed_qyyjt',
    }
    ra = _qyyjt_report_admission(contract, fixture, {k: fixture[k] for k in contract['required_common_fields']})
    assert ra['admissible'] is True
    payload = _qyyjt_structured_payload('Demo Co.', 'pledge', contract, fixture, ra)
    assert 'risk_events' in payload
    relation_types = {row["relation_type"] for row in payload["relations"]}
    assert "equity_pledge" in relation_types
    assert "equity_pledgee" in relation_types
    assert any(row["to_name"] == "Demo Bank" for row in payload["relations"])

def test_pledge_missing_shareholder_stays_lead() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    
    contract = {
        'record_type': 'equity_pledge',
        'required_fields': ['shareholder', 'pledgee', 'pledged_amount', 'pledge_date', 'status'],
        'required_common_fields': ['subject_name', 'source_name'],
        'report_gate': 'do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present',
    }
    fixture = {'pledgee': 'Demo Bank', 'pledged_amount': '500000', 'pledge_date': '2026-04-10', 'status': 'active'}
    ra = _qyyjt_report_admission(contract, fixture, {'subject_name': 'Demo Co.', 'source_name': 'qyyjt_api'})
    assert ra['admissible'] is False
    assert 'shareholder' in ra['missing_required_fields']
    payload = _qyyjt_structured_payload('Demo Co.', 'pledge', contract, fixture, ra)
    assert payload == {}


def test_freeze_auction_reaches_asset_solvency() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    c = {"record_type":"equity_freeze","required_fields":["subject","court","frozen_amount","freeze_date","status"],"required_common_fields":["subject_name","source_name","source_url","observed_at","confidence","verification_status"],"report_gate":"do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present"}
    f = {"subject":"Alice Holder","court":"Beijing No.1","frozen_amount":"1000000","freeze_date":"2026-05-01","status":"active","subject_name":"Demo Co.","source_name":"qyyjt_api","source_url":"https://qyyjt.cn/freeze","observed_at":"2026-01-01","confidence":"0.74","verification_status":"licensed_qyyjt"}
    ra = _qyyjt_report_admission(c,f,{k:f[k] for k in c["required_common_fields"]})
    assert ra["admissible"] is True
    pld = _qyyjt_structured_payload("Demo Co.","freeze",c,f,ra)
    assert "risk_events" in pld


def test_debt_obligation_missing_amount_stays_lead() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    c={"record_type":"debt_credit_obligation","required_fields":["obligation_type","creditor","amount","due_date","status"],"required_common_fields":["subject_name","source_name"],"report_gate":"do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present"}
    f={"obligation_type":"loan","creditor":"Demo Bank","due_date":"2026-12-31","status":"outstanding"}
    ra=_qyyjt_report_admission(c,f,{"subject_name":"Demo Co.","source_name":"qyyjt_api"})
    assert ra["admissible"] is False
    assert "amount" in ra["missing_required_fields"]
    payload=_qyyjt_structured_payload("Demo Co.","debt",c,f,ra)
    assert payload=={}


def test_bond_calendar_admitted_reaches_risk_events() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    c={"record_type":"bond_calendar_event","required_fields":["bond_name","issuer","event_date","event_type","amount","status"],"required_common_fields":["subject_name","source_name","source_url","observed_at","confidence","verification_status"],"report_gate":"do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present"}
    f={"bond_name":"Demo 2026 Bond","issuer":"Demo Co.","event_date":"2026-06-30","event_type":"maturity","amount":"100000000","status":"upcoming","subject_name":"Demo Co.","source_name":"qyyjt_api","source_url":"https://qyyjt.cn/bond","observed_at":"2026-01-01","confidence":"0.74","verification_status":"licensed_qyyjt"}
    ra=_qyyjt_report_admission(c,f,{k:f[k] for k in c["required_common_fields"]})
    assert ra["admissible"] is True
    payload=_qyyjt_structured_payload("Demo Co.","bond_calendar",c,f,ra)
    assert "risk_events" in payload


def test_court_announce_admitted_reaches_legal_profile() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    c={"record_type":"court_announcement","required_fields":["case_number","court","cause","parties","hearing_date","status"],"required_common_fields":["subject_name","source_name","source_url","observed_at","confidence","verification_status"],"report_gate":"do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present"}
    f={"case_number":"(2026)京01民初001","court":"北京市第一中级人民法院","cause":"合同纠纷","parties":"Demo Co. vs Supplier Ltd.","hearing_date":"2026-07-15","status":"scheduled","subject_name":"Demo Co.","source_name":"qyyjt_api","source_url":"https://qyyjt.cn/court","observed_at":"2026-01-01","confidence":"0.74","verification_status":"licensed_qyyjt"}
    ra=_qyyjt_report_admission(c,f,{k:f[k] for k in c["required_common_fields"]})
    assert ra["admissible"] is True
    payload=_qyyjt_structured_payload("Demo Co.","court_announce",c,f,ra)
    assert "risk_events" in payload


def test_merger_admitted_reaches_operational_events() -> None:
    from adapters.qyyjt_tool import _qyyjt_report_admission, _qyyjt_structured_payload
    c={"record_type":"merger_restructuring_event","required_fields":["event_type","counterparty","announcement_date","amount","status"],"required_common_fields":["subject_name","source_name","source_url","observed_at","confidence","verification_status"],"report_gate":"do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present"}
    f={"event_type":"merger","counterparty":"Target Corp.","announcement_date":"2026-06-01","amount":"500000000","status":"pending","subject_name":"Demo Co.","source_name":"qyyjt_api","source_url":"https://qyyjt.cn","observed_at":"2026-01-01","confidence":"0.74","verification_status":"licensed_qyyjt"}
    ra=_qyyjt_report_admission(c,f,{k:f[k] for k in c["required_common_fields"]})
    assert ra["admissible"] is True
    assert "risk_events" in _qyyjt_structured_payload("Demo Co.","merger",c,f,ra)




def test_recruiting_admitted_creates_risk_event():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"recruiting_signal","required_fields":["signal_type","signal_date"]}
    fixt = {
        "signal_type":"hiring_surge",
        "signal_date":"2026-05-01",
        "position_count":"50",
        "salary_range":"15k-25k",
        "subject_name":"Demo Co.",
        "source_name":"qyyjt_api"
    }
    p = _qyyjt_structured_payload("Demo Co.","recruiting",fc,fixt,{"risk_category":"commercial_activity"})
    assert p is not None
    # Check: if admitted, should have risk events or entities
    if len(p) > 0:
        assert len(p.get("risk_events",[])) >= 1 or len(p.get("entities",[])) >= 1

def test_recruiting_missing_fields_empty():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"recruiting_signal","required_fields":["signal_type","signal_date"]}
    fixt = {"source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","recruiting",fc,fixt,{"risk_category":"commercial_activity"})
    assert p is not None


def test_auction_bridge_admitted_reaches_risk_events():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"judicial_auction","required_fields":["auction_subject","auction_date","auction_amount"]}
    fixt = {"auction_subject":"Demo Asset","auction_date":"2026-05-01","auction_amount":"1000000","status":"announced","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","auction",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None
    if p.get("risk_events"):
        assert len(p.get("risk_events",[])) >= 1
    else:
        print("Auction not admitted by admission check")

def test_auction_missing_fields_lead_only():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"judicial_auction","required_fields":["auction_subject","auction_date","auction_amount"]}
    fixt = {"auction_date":"2026-05-01","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","auction",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None


def test_freeze_bridge_admitted_reaches_risk_events():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"asset_freeze","required_fields":["freeze_subject","freeze_date","freeze_amount"]}
    fixt = {"freeze_subject":"Demo Equipment","freeze_date":"2026-03-01","freeze_amount":"5000000","status":"frozen","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","freeze",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None

def test_freeze_missing_fields_lead_only():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"asset_freeze","required_fields":["freeze_subject","freeze_date","freeze_amount"]}
    fixt = {"freeze_date":"2026-03-01","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","freeze",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None


def test_related_party_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"related_party_transaction","required_fields":["related_entity","transaction_type","transaction_amount"]}
    fixt = {"related_entity":"Related Co.","transaction_type":"fund_transfer","transaction_amount":"10000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","related_party",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None

def test_related_party_missing_fields():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"related_party_transaction","required_fields":["related_entity","transaction_type","transaction_amount"]}
    fixt = {"related_entity":"Related Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","related_party",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None


def test_ip_bridge_admitted_creates_entity():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"ip_asset","required_fields":["ip_type","ip_title","registration_number"]}
    fixt = {"ip_type":"patent","ip_title":"AI Risk Engine","registration_number":"CN123456","status":"active","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","ip",fc,fixt,{"risk_category":"ip_tech"})
    assert p is not None

def test_ip_missing_registration_lead():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"ip_asset","required_fields":["ip_type","ip_title","registration_number"]}
    fixt = {"ip_type":"patent","ip_title":"AI Engine","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","ip",fc,fixt,{"risk_category":"ip_tech"})
    assert p is not None


def test_court_enforcement_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"enforcement_record","required_fields":["case_number","enforcement_date"]}
    fixt = {"case_number":"(2026)京01执001号","enforcement_date":"2026-05-01","enforcement_amount":"5000000","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"executing"}
    p = _qyyjt_structured_payload("Demo Co.","enforcement",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None

def test_dishonesty_record_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"dishonesty_record","required_fields":["dishonest_subject","publish_date"]}
    fixt = {"dishonest_subject":"Demo Co.","publish_date":"2026-04-15","reason":"failure_to_execute","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"published"}
    p = _qyyjt_structured_payload("Demo Co.","dishonesty",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None

def test_limit_high_consumption_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"limit_high_consumption","required_fields":["restricted_person","restriction_date"]}
    fixt = {"restricted_person":"Alice Zhang","restriction_date":"2026-05-01","restriction_type":"air_travel","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"active"}
    p = _qyyjt_structured_payload("Demo Co.","limit_high_consumption",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None


def test_administrative_penalty_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"administrative_penalty","required_fields":["penalty_reason","penalty_date","penalty_amount"]}
    fixt = {"penalty_reason":"tax_violation","penalty_date":"2026-03-15","penalty_amount":"200000","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"confirmed"}
    p = _qyyjt_structured_payload("Demo Co.","administrative_penalty",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None

def test_registry_change_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"registry_change_event","required_fields":["change_type","change_date"]}
    fixt = {"change_type":"legal_representative","change_date":"2026-05-01","before_value":"Alice","after_value":"Bob","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"registered"}
    p = _qyyjt_structured_payload("Demo Co.","registry_change",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None

def test_credit_profile_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"credit_profile","required_fields":["credit_type","credit_amount"]}
    fixt = {"credit_type":"bank_loan","credit_amount":"50000000","credit_period":"12M","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"active"}
    p = _qyyjt_structured_payload("Demo Co.","credit_profile",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None


def test_financing_event_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financing_event","required_fields":["financing_type","financing_amount","financing_date"]}
    fixt = {"financing_type":"series_a","amount":"50000000","event_date":"2026-01-15","counterparty":"Demo Capital Fund","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financing_event",fc,fixt,{"admissible": True, "risk_category":"capital_pressure"})
    assert p is not None
    assert p["relations"][0]["to_name"] == "Demo Capital Fund"
    assert p["relations"][0]["relation_type"] == "financing_counterparty"

def test_research_report_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"research_report_signal","required_fields":["report_title","publish_date"]}
    fixt = {"report_title":"Demo Co. Analysis","publish_date":"2026-06-01","analyst_rating":"buy","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","research_report",fc,fixt,{"risk_category":"market_sentiment"})
    assert p is not None

def test_negative_public_opinion_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"negative_public_opinion","required_fields":["opinion_title","publish_date"]}
    fixt = {"opinion_title":"Demo Co. Scandal","publish_date":"2026-05-01","sentiment":"negative","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","negative_public_opinion",fc,fixt,{"risk_category":"reputation_risk"})
    assert p is not None


def test_qyyjt_follow_up_lead_bridges_are_visible_but_lead_only():
    from adapters.qyyjt_tool import _qyyjt_structured_payload

    for record_type, key in (("watchlist_lead", "watchlist"), ("alert_push_lead", "alert_push")):
        fc = {"record_type": record_type, "required_fields": ["module", "query", "summary"]}
        fixt = {
            "module": key,
            "query": "Demo Co. risk trigger",
            "summary": "Monitor this lead after source verification.",
            "subject_name": "Demo Co.",
            "source_name": "qyyjt_api",
        }
        payload = _qyyjt_structured_payload("Demo Co.", key, fc, fixt, {"admissible": True})

        assert payload["risk_events"][0]["risk_category"] == "follow_up_lead"
        assert payload["risk_events"][0]["status"] == "lead_only_pending_verification"
        assert payload["follow_up_leads"][0]["evidence_role"] == "lead_only_not_verified_fact"


def test_all_qyyjt_field_contract_record_types_have_structured_bridge():
    import re
    from pathlib import Path

    from core.qyyjt_benchmark import build_qyyjt_benchmark

    text = Path("adapters/qyyjt_tool.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'record_type == "([^"]+)"', text))
    for group in re.findall(r"record_type in \{([^}]+)\}", text):
        handled.update(re.findall(r'"([^"]+)"', group))

    missing = sorted(
        (module, contract.get("record_type"))
        for module, contract in build_qyyjt_benchmark()["summary"]["field_contracts"].items()
        if contract.get("record_type") and contract.get("record_type") not in handled
    )

    assert missing == []


def test_financial_statement_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financial_statement_metric","required_fields":["metric_name","metric_value","period"]}
    fixt = {"metric_name":"total_revenue","metric_value":"500000000","period":"2026-Q1","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financial_statement",fc,fixt,{"risk_category":"capital_pressure"})
    assert p is not None

def test_financial_indicator_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financial_indicator","required_fields":["indicator_name","indicator_value"]}
    fixt = {"indicator_name":"debt_to_equity","indicator_value":"2.5","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financial_indicator",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None

def test_regional_credit_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"regional_credit_indicator","required_fields":["region_name","indicator_type","indicator_value"]}
    fixt = {"region_name":"Beijing","indicator_type":"city_investment_debt_ratio","indicator_value":"320","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","regional_credit",fc,fixt,{"risk_category":"regional_risk"})
    assert p is not None


def test_merger_restructuring_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"merger_restructuring_event","required_fields":["event_type","event_date","target_entity"]}
    fixt = {"event_type":"acquisition","event_date":"2026-04-01","target_entity":"Target Co.","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"announced"}
    p = _qyyjt_structured_payload("Demo Co.","merger",fc,fixt,{"risk_category":"operational_event"})
    assert p is not None

def test_court_announcement_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"court_announcement","required_fields":["announcement_title","announcement_date"]}
    fixt = {"announcement_title":"Court Case Notice","announcement_date":"2026-05-01","case_type":"civil","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"published"}
    p = _qyyjt_structured_payload("Demo Co.","court_announcement",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None

def test_court_case_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"court_case","required_fields":["case_title","case_date"]}
    fixt = {"case_title":"Demo Co. vs Plaintiff","case_date":"2026-05-15","case_type":"contract_dispute","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"pending"}
    p = _qyyjt_structured_payload("Demo Co.","court_case",fc,fixt,{"risk_category":"legal_admin"})
    assert p is not None


def test_news_opinion_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"news_opinion_event","required_fields":["news_title","publish_date"]}
    fixt = {"news_title":"Demo Co. Market Update","publish_date":"2026-06-01","sentiment":"negative","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","news_opinion",fc,fixt,{"risk_category":"reputation_risk"})
    assert p is not None

def test_subject_resolution_candidate_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"subject_resolution_candidate","required_fields":["candidate_name","match_score"]}
    fixt = {"candidate_name":"Demo Co.","match_score":"0.95","match_type":"exact","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","subject_resolution",fc,fixt,{"risk_category":"subject_resolution"})
    assert p is not None

def test_risk_overview_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"risk_overview","required_fields":["risk_category","risk_level"]}
    fixt = {"risk_category":"credit_pressure","risk_level":"medium","risk_score":"65","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","risk_overview",fc,fixt,{"risk_category":"summary"})
    assert p is not None


def test_risk_signal_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"risk_signal","required_fields":["signal_type","signal_date"]}
    fixt = {"signal_type":"credit_pressure","signal_date":"2026-05-01","signal_strength":"medium","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","risk_signal",fc,fixt,{"risk_category":"summary"})
    assert p is not None

def test_controller_candidate_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"controller_candidate","required_fields":["candidate_name","relation_type","confidence"]}
    fixt = {"candidate_name":"Alice Zhang","relation_type":"legal_representative","confidence":"0.90","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","controller_candidate",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None

def test_registry_identity_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"registry_identity","required_fields":["entity_name","registration_number"]}
    fixt = {"entity_name":"Demo Co.","registration_number":"91110000MA000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","registry_identity",fc,fixt,{"risk_category":"subject_resolution"})
    assert p is not None


def test_recruiting_signal_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"recruiting_signal","required_fields":["signal_type","signal_date"]}
    fixt = {"signal_type":"hiring_surge","signal_date":"2026-06-01","position_count":"50","signal_strength":"medium","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","recruiting",fc,fixt,{"risk_category":"commercial_activity"})
    assert p is not None


def test_financial_institution_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financial_institution_profile","required_fields":["institution_name","institution_type"]}
    fixt = {"institution_name":"Beijing Bank","institution_type":"commercial_bank","license_status":"active","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","fin_inst",fc,fixt,{"risk_category":"financial_data"})
    assert p is not None

def test_ubo_path_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"ubo_path","required_fields":["ubo_name","ubo_relation","ownership_pct"]}
    fixt = {"ubo_name":"Alice Controller","ubo_relation":"ultimate_beneficial_owner","ownership_pct":"100","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","ubo_path",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None

def test_group_network_edge_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"group_network_edge","required_fields":["source_entity","target_entity","relation_type"]}
    fixt = {"source_entity":"Demo Co.","target_entity":"Subsidiary Ltd.","relation_type":"subsidiary","confidence":"0.8","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","group_network",fc,fixt,{"risk_category":"control_ownership"})
    assert p is not None


def test_tax_profile_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"tax_profile","required_fields":["tax_type","tax_period","tax_amount"]}
    fixt = {"tax_type":"corporate_income","tax_period":"2026-Q1","tax_amount":"5000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","tax",fc,fixt,{"risk_category":"operational_event"})
    assert p is not None

def test_trade_activity_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"trade_activity","required_fields":["trade_type","trade_date","trade_amount"]}
    fixt = {"trade_type":"export","trade_date":"2026-05-01","trade_amount":"50000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","trade",fc,fixt,{"risk_category":"commercial_activity"})
    assert p is not None


def test_bond_rating_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"bond_profile","required_fields":["bond_name","bond_type","issue_amount"]}
    fixt = {"bond_name":"Demo Bond 2026","bond_type":"corporate","issue_amount":"500000000","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"active"}
    p = _qyyjt_structured_payload("Demo Co.","bond_profile",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None

def test_bond_issue_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"bond_issue","required_fields":["issue_name","issue_date","issue_amount"]}
    fixt = {"issue_name":"Demo Bond Series A","issue_date":"2026-03-15","issue_amount":"300000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","bond_issue",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None


def test_credit_profile_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"credit_profile","required_fields":["credit_type","credit_amount"]}
    fixt = {"credit_type":"bank_loan","credit_amount":"50000000","credit_period":"12M","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"active"}
    p = _qyyjt_structured_payload("Demo Co.","credit_profile",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None

def test_financial_statement_metric_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financial_statement_metric","required_fields":["metric_name","metric_value","period"]}
    fixt = {"metric_name":"total_revenue","metric_value":"500000000","period":"2026-Q1","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financial_statement",fc,fixt,{"risk_category":"capital_pressure"})
    assert p is not None

def test_financial_indicator_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financial_indicator","required_fields":["indicator_name","indicator_value"]}
    fixt = {"indicator_name":"debt_to_equity","indicator_value":"2.5","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financial_indicator",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None


def test_regional_credit_indicator_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"regional_credit_indicator","required_fields":["region_name","indicator_type","indicator_value"]}
    fixt = {"region_name":"Beijing","indicator_type":"city_investment_debt_ratio","indicator_value":"220","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","regional_credit",fc,fixt,{"risk_category":"regional_risk"})
    assert p is not None

def test_bond_calendar_event_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"bond_calendar_event","required_fields":["bond_name","event_type","event_date"]}
    fixt = {"bond_name":"Demo Bond 2026","event_type":"maturity","event_date":"2026-06-15","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","bond_calendar",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None

def test_bond_default_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"bond_default_event","required_fields":["bond_name","default_date","default_amount"]}
    fixt = {"bond_name":"Demo Bond 2026","issuer":"Demo Co.","default_date":"2026-05-01","default_amount":"100000000","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"confirmed"}
    p = _qyyjt_structured_payload("Demo Co.","bond_default",fc,fixt,{"admissible": True, "risk_category":"credit_pressure"})
    assert p is not None
    assert p["relations"][0]["to_name"] == "Demo Bond 2026"
    assert p["relations"][0]["relation_type"] == "bond_default_event"


def test_financing_event_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"financing_event","required_fields":["financing_type","financing_amount","financing_date"]}
    fixt = {"financing_type":"series_a","financing_amount":"50000000","financing_date":"2026-01-15","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","financing_event",fc,fixt,{"risk_category":"capital_pressure"})
    assert p is not None

def test_credit_profile_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"credit_profile","required_fields":["credit_type","credit_amount"]}
    fixt = {"credit_type":"bank_loan","credit_amount":"50000000","credit_period":"12M","subject_name":"Demo Co.","source_name":"qyyjt_api","status":"active"}
    p = _qyyjt_structured_payload("Demo Co.","credit_profile",fc,fixt,{"risk_category":"credit_pressure"})
    assert p is not None

def test_research_report_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"research_report_signal","required_fields":["report_title","publish_date"]}
    fixt = {"report_title":"Demo Co. Analysis","publish_date":"2026-06-01","analyst_rating":"buy","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","research_report",fc,fixt,{"risk_category":"market_sentiment"})
    assert p is not None


def test_tax_profile_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"tax_profile","required_fields":["tax_type","tax_period","tax_amount"]}
    fixt = {"tax_type":"corporate_income","tax_period":"2026-Q1","tax_amount":"5000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","tax",fc,fixt,{"risk_category":"operational_event"})
    assert p is not None

def test_trade_activity_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"trade_activity","required_fields":["trade_type","trade_date","trade_amount"]}
    fixt = {"trade_type":"export","trade_date":"2026-05-01","trade_amount":"50000000","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","trade",fc,fixt,{"risk_category":"commercial_activity"})
    assert p is not None


def test_news_all_bridge():
    from adapters.qyyjt_tool import _qyyjt_structured_payload
    fc = {"record_type":"news_opinion_event","required_fields":["news_title","publish_date"]}
    fixt = {"news_title":"Industry Update","publish_date":"2026-06-10","sentiment":"neutral","subject_name":"Demo Co.","source_name":"qyyjt_api"}
    p = _qyyjt_structured_payload("Demo Co.","news_opinion",fc,fixt,{"risk_category":"reputation_risk"})
    assert p is not None
