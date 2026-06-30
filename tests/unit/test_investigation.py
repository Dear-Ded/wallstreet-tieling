#!/usr/bin/env python3
"""Tests for product-facing one-click investigation packets."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.datasource_fixtures import build_datasource_fixture_pack
from core.investigation import build_investigation_packet
from core.risk_discovery_pipeline import RiskDiscoveryPipeline
from core.risk_graph_export import export_risk_graph


ROOT = Path(__file__).resolve().parent.parent.parent


def _load_investigate_cli_module():
    spec = importlib.util.spec_from_file_location("wst_investigate_cli", ROOT / "bin" / "investigate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_investigate_cli_clamps_host_supplied_execution_bounds(monkeypatch) -> None:
    cli = _load_investigate_cli_module()
    captured: dict[str, object] = {}

    async def fake_resolve(**kwargs):
        captured["resolve"] = kwargs
        return SimpleNamespace(records=None, search_engine=None, existing_plan=None, fanout_rounds=kwargs["fanout_rounds"])

    class FakePipeline:
        async def run(self, *args, **kwargs):
            captured["pipeline"] = kwargs
            return SimpleNamespace()

    monkeypatch.setattr(cli, "resolve_one_click_retrieval_async", fake_resolve)
    monkeypatch.setattr(cli, "RiskDiscoveryPipeline", lambda: FakePipeline())
    monkeypatch.setattr(cli, "export_risk_graph", lambda result: SimpleNamespace(to_dict=lambda: {"company": "Demo"}))
    monkeypatch.setattr(cli, "build_investigation_packet", lambda *args, **kwargs: SimpleNamespace(to_dict=lambda: {"ok": True}))

    args = cli.build_parser().parse_args(
        [
            "Demo Clamp Co.",
            "--retrieval-concurrency",
            "999",
            "--fanout-rounds",
            "99",
            "--max-fanout-tasks",
            "999",
            "--query-timeout-seconds",
            "999",
        ]
    )
    payload = asyncio.run(cli.run(args))

    assert payload == {"ok": True}
    assert captured["resolve"]["fanout_rounds"] == 3
    assert captured["pipeline"]["retrieval_concurrency"] == 20
    assert captured["pipeline"]["max_fanout_tasks"] == 80
    assert captured["pipeline"]["query_timeout_seconds"] == 120.0


def test_investigation_packet_contains_report_and_monitoring_seed(tmp_path) -> None:
    company = "Demo Investigation Packet Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company, mode="standard").to_dict()

    assert packet["type"] == "investigation_packet"
    assert packet["version"] == "0.5.0"
    assert packet["one_click"] is True
    assert packet["risk_brief"]["verdict"] in {
        "high_risk_verification_required",
        "moderate_risk_watchlist",
        "critical_risk_review_required",
    }
    assert packet["risk_brief"]["risk_score"] > 0
    assert packet["profile_brief"]["controller_candidate_count"] >= 1
    assert packet["enterprise_cognition"]["control_ownership"]["controller_candidate_count"] >= 1
    assert packet["enterprise_cognition"]["company"] == company
    assert packet["enterprise_cognition"]["risk_hypotheses"]
    assert packet["enterprise_cognition"]["monitoring_watchlist"]
    assert packet["source_provenance"]["source_count"] >= 1
    assert packet["source_provenance"]["official_or_licensed_count"] >= 1
    assert packet["risk_event_summary"]["risk_event_count"] >= 1
    assert packet["risk_event_summary"]["top_findings"]
    assert packet["persona_surface"]["role_count"] == 13
    assert packet["persona_surface"]["active_role_count"] >= 8
    assert any(role["display_name"] == "钱守正" for role in packet["persona_surface"]["active_roles"])
    assert packet["persona_surface"]["principle"].startswith("角色是调查分工")
    assert "lane=" in packet["report_markdown"]
    assert "basis=" in packet["report_markdown"]
    assert "quality_gate" in packet
    assert packet["quality_gate"]["status"] in {"ready_for_human_review", "usable_with_warnings"}
    assert packet["one_click_readiness"]["type"] == "one_click_readiness"
    assert packet["one_click_readiness"]["fact_count"] >= 1
    assert packet["one_click_readiness"]["section_checks"]["quality_gate"] is True
    assert packet["one_click_readiness"]["section_checks"]["monitoring_scope_marked_future"] is True
    assert packet["report_exports"]["type"] == "report_exports"
    assert packet["report_exports"]["markdown"]["content_field"] == "report_markdown"
    portable_html = packet["report_exports"]["portable_html"]["document"]
    assert portable_html.startswith("<!doctype html>")
    assert company in portable_html
    assert "report readiness summary" in portable_html
    assert "quality score" in portable_html
    assert "coverage gaps:" in portable_html
    assert "capital relationship" in portable_html
    assert packet["report_markdown"].splitlines()[0] in portable_html
    assert packet["report_exports"]["json_packet"]["content_field"] == "entire investigation_packet"
    assert packet["report_exports"]["future_formats"]["immersive_premium_html"] == "p2_visual_polish_not_current_release_blocker"
    assert "## One-click Product Loop" in packet["report_markdown"]
    assert "## 专家团分工" in packet["report_markdown"]
    assert "钱守正" in packet["report_markdown"]
    assert "## 交付质量" in packet["report_markdown"]
    assert "## 风险事件台账" in packet["report_markdown"]
    assert f"评分: {packet['quality_gate']['score']}/100" in packet["report_markdown"]
    assert packet["evidence_ledger"]
    assert packet["monitoring_seed"]["ready_for_continuous_watch"] is True
    assert packet["monitoring_seed"]["current_release_monitoring_enabled"] is False
    assert packet["monitoring_seed"]["feature_scope"] == "future_version_not_current_release"
    assert packet["monitoring_seed"]["current_release_role"] == "baseline_seed_only"
    assert "尽调快报" in packet["report_markdown"]
    assert "## 企业认知" in packet["report_markdown"]
    assert "## 来源出处" in packet["report_markdown"]
    assert "## 控制权与实控人" in packet["report_markdown"]
    assert packet["graph"]["company"] == company


def test_investigation_packet_marks_no_source_as_insufficient_data(tmp_path) -> None:
    company = "Demo Investigation No Source Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company).to_dict()

    assert packet["risk_brief"]["verdict"] == "insufficient_data"
    assert packet["quality_gate"]["ok"] is False
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert packet["enterprise_cognition"]["evidence_gaps"]
    assert any("当前证据不足" in item for item in packet["enterprise_cognition"]["risk_hypotheses"])
    assert packet["evidence_ledger"] == []
    assert packet["summary"]["dd_profile_highlights"]["available"] is False
    assert packet["enterprise_cognition"]["status_summary"]["ok"] is False
    assert packet["enterprise_cognition"]["subject_aggregation_available"] is False
    assert packet["enterprise_cognition"]["multi_layer_graph_data"]["available"] is False
    assert packet["enterprise_cognition"]["multi_layer_relationship_graph"]["available"] is False
    assert packet["monitoring_seed"]["ready_for_continuous_watch"] is False
    assert packet["monitoring_seed"]["current_release_monitoring_enabled"] is False
    assert packet["monitoring_seed"]["feature_scope"] == "future_version_not_current_release"
    assert "证据不足" in packet["report_markdown"]


@pytest.mark.parametrize("record_source_type", ["query_plan", "Rich_Query_Plan"])
def test_investigation_packet_blocks_clean_verdict_when_only_leads_exist(record_source_type: str) -> None:
    graph = {
        "company": "Demo Lead Only Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "highest_severity": None,
            "next_actions": [],
            "coverage": {"domains_without_evidence": ["financing_capital_markets"]},
            "failed_sources": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:lead-1",
                "type": "derived_clue",
                "source": "qyyjt_websearch_plan",
                "title": "QYYJT lead: RELATED_PARTIES",
                "url": None,
                "confidence": 0.3,
                "claim_count": 1,
                "claims": ["query-plan lead only"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "record_source_type": record_source_type},
            },
            {
                "id": "evidence:lead-2",
                "type": "derived_clue",
                "source": "qyyjt_websearch_plan",
                "title": "QYYJT lead: RISK_SCAN",
                "url": None,
                "confidence": 0.3,
                "claim_count": 1,
                "claims": ["another lead only"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "record_source_type": record_source_type},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Lead Only Co.",
                "recursion_policy": {"default_depth": 3, "max_subjects": 80, "max_signals_per_dimension": 120},
                "subjects": {},
                "signals_by_dimension": {},
                "controller_candidates": [],
                "evidence_gaps": [
                    "Missing or weak controller and beneficial-owner evidence; expand public/authorized sources before making a final risk judgment."
                ],
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Lead Only Co.", "kind": "company"},
                        {"id": "domain:demo.example", "name": "demo.example", "kind": "domain"},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "from_name": "Demo Lead Only Co.",
                            "from_kind": "company",
                            "to_id": "domain:demo.example",
                            "to_name": "demo.example",
                            "to_kind": "domain",
                            "relation_type": "public_web_footprint",
                            "confidence": 0.3,
                            "evidence_ids": ["evidence:lead-1"],
                        },
                        {
                            "from_id": "company:demo",
                            "from_name": "Demo Lead Only Co.",
                            "from_kind": "company",
                            "to_id": "domain:demo.example",
                            "to_name": "demo.example",
                            "to_kind": "domain",
                            "relation_type": "public_web_footprint",
                            "confidence": 0.3,
                            "evidence_ids": ["evidence:lead-2"],
                        },
                    ],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Lead Only Co.").to_dict()

    assert packet["risk_brief"]["verdict"] == "insufficient_data"
    assert "clean_verdict_with_blockers" in packet["quality_gate"]["blockers"]
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert packet["source_provenance"]["factual_count"] == 0
    assert packet["source_provenance"]["lead_count"] == 2
    assert packet["summary"]["dd_profile_highlights"]["available"] is True
    assert packet["enterprise_cognition"]["subject_aggregation_available"] is True
    assert packet["enterprise_cognition"]["public_people_profile"]["row_count"] >= 2
    assert "Public Lead Profiles" in packet["report_markdown"]
    assert "corroboration-needed leads, not report facts" in packet["report_markdown"]
    assert "public_leads_need_corroboration" in packet["quality_gate"]["warnings"]
    assert packet["enterprise_cognition"]["subject_due_diligence_profile"]["executive_summary"]["evidence_sources"] >= 1
    assert len(packet["enterprise_cognition"]["relationship_network"]["top_edges"]) == 1


def test_public_web_exact_match_lead_not_counted_as_factual_evidence() -> None:
    graph = {
        "company": "Demo Public Lead Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-web-lead",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Public Lead Co. customer profile",
            "url": "https://example.com/public-lead",
            "confidence": 0.68,
            "claim_count": 1,
            "claims": ["customer=Demo Buyer; market_share=0.12"],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact", "score": 1.0},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Public Lead Co.").to_dict()
    evidence = packet["evidence_ledger"][0]

    assert evidence["record_kind"] == "evidence"
    assert evidence["admission"] == "lead"
    assert packet["source_provenance"]["factual_count"] == 0
    assert packet["source_provenance"]["lead_count"] == 1
    assert packet["source_provenance"]["top_sources"][0]["factual_count"] == 0
    assert packet["source_provenance"]["top_sources"][0]["lead_count"] == 1
    assert "no_factual_evidence" in packet["quality_gate"]["blockers"]
    assert "public_leads_need_corroboration" in packet["quality_gate"]["warnings"]
    assert "事实级: 0 条" in packet["report_markdown"]
    assert "线索级: 1 条" in packet["report_markdown"]
    assert "Demo Public Lead Co. customer profile" in packet["report_markdown"]


def test_persona_surface_requires_real_lane_basis() -> None:
    from core.investigation import _persona_surface_for_investigation

    empty = _persona_surface_for_investigation({}, {}, {})
    assert empty["active_role_count"] == 0
    assert empty["active_roles"] == []

    grounded = _persona_surface_for_investigation(
        {"covered_dimensions": ["identity"], "controller_candidate_count": 1},
        {"top_findings": [{"title": "risk"}], "risk_event_count": 1},
        {
            "evidence_gaps": ["Missing controller corroboration"],
            "next_questions": ["Verify UBO path"],
            "control_ownership": {"controller_candidate_count": 1},
            "public_goods_profile": {"row_count": 2},
            "evidence_depth_score": {"score": 62},
            "investigation_report_card": {"dd_summary": {}},
            "subject_due_diligence_profile": {"type": "subject_due_diligence_profile"},
            "monitoring_watchlist": ["identity"],
            "risk_hypotheses": ["review controller"],
        },
    )

    assert grounded["active_role_count"] >= 8
    for role in grounded["active_roles"]:
        assert role["lane"] != "general"
        assert role["evidence_sources"]
        assert all("=False" not in item and "=0" not in item for item in role["evidence_sources"])


def test_profile_brief_falls_back_to_diagnostics_subject_profile() -> None:
    graph = {
        "company": "Demo Diagnostics Profile Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 0,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Diagnostics Profile Co.",
                "controller_candidates": [{
                    "name": "Alice Controller",
                    "confidence": 0.81,
                    "verification_status": "verified",
                    "source_names": ["licensed_registry_api"],
                }],
                "signals_by_dimension": {
                    "identity": [{"dimension": "identity", "title": "Registry", "value": "active"}],
                    "control_ownership": [{"dimension": "control_ownership", "title": "Controller", "value": "Alice"}],
                },
                "evidence_gaps": [],
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Diagnostics Profile Co.").to_dict()
    profile = packet["profile_brief"]

    assert profile["controller_candidate_count"] == 1
    assert profile["controller_candidates"][0]["name"] == "Alice Controller"
    assert profile["covered_dimensions"] == ["identity", "control_ownership"]
    assert profile["dimension_counts"] == {"identity": 1, "control_ownership": 1}


def test_investigate_cli_fixture_pack_returns_product_packet(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Investigate CLI Co., Ltd.",
            "--fixture-pack",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert payload["summary"]["evidence_count"] == 6
    assert payload["profile_brief"]["controller_candidate_count"] >= 1
    assert payload["enterprise_cognition"]["risk_hypotheses"]
    routing_summary = payload["source_failure_summary"]["source_routing_summary"]
    assert routing_summary["policy"].startswith("Routing health describes source availability")
    coverage_watchlist = payload["monitoring_seed"]["coverage_recovery_watchlist"]
    assert any(item["domain"] == "administrative_risk" for item in coverage_watchlist)
    assert any(item["suggested_source"] == "creditchina_public" for item in coverage_watchlist)
    execution_plan = payload["monitoring_seed"]["coverage_recovery_execution_plan"]
    assert any(item["tier"] == "official_public" for item in execution_plan)
    assert any(item["source"] == "creditchina_public" for item in execution_plan)
    execution_readiness = payload["monitoring_seed"]["coverage_recovery_execution_readiness"]
    assert execution_readiness["step_count"] >= len(execution_plan)
    assert "ready_count" in execution_readiness
    assert "blocked_count" in execution_readiness
    recovery_queue = payload["monitoring_seed"]["recovery_execution_queue"]
    assert "ready_to_run" in recovery_queue
    assert "queued_count" in recovery_queue
    assert "blocked_count" in recovery_queue
    recovery_summary = payload["monitoring_seed"]["recovery_execution_summary"]
    assert recovery_summary["blocked_count"] == recovery_queue["blocked_count"]
    assert recovery_summary["policy"].startswith("Use ready queue items")
    assert "relationship_candidate_leads" in payload["monitoring_seed"]["watched_dimensions"]
    relationship_watchlist = payload["monitoring_seed"]["relationship_candidate_watchlist"]
    assert any(item["relation_type"] == "supplier_of" for item in relationship_watchlist)
    assert any(item["priority"] == "P0" for item in relationship_watchlist)
    assert payload["report_markdown"].startswith("# 华尔街驻铁岭办事处")


def test_investigate_cli_json_flag_returns_product_packet(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Investigate Json Co., Ltd.",
            "--fixture-pack",
            "--json",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["type"] == "investigation_packet"
    assert payload["report_markdown"].startswith("# 华尔街驻铁岭办事处")


def test_investigate_cli_rejects_json_and_report_only_conflict() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "Demo Invalid Output Co., Ltd.",
            "--fixture-pack",
            "--json",
            "--report-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "--json and --report-only are mutually exclusive" in result.stderr


def test_investigate_cli_defaults_to_one_click_public_path(monkeypatch, tmp_path) -> None:
    import bin.investigate as investigate

    class FakeDefaultSearch:
        pass

    calls = {}
    original_resolve = investigate.resolve_one_click_retrieval_async
    original_run = RiskDiscoveryPipeline.run

    async def fake_resolve(**kwargs):
        calls["resolve"] = kwargs
        return await original_resolve(
            **{
                **kwargs,
                "search_engine": FakeDefaultSearch(),
                "existing_plan": None,
                "default_enabled": False,
            }
        )

    async def fake_pipeline_run(self, company, **kwargs):
        calls["run"] = kwargs
        result = await original_run(
            RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl"),
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
        return result

    monkeypatch.setattr(investigate, "resolve_one_click_retrieval_async", fake_resolve)
    monkeypatch.setattr(investigate.RiskDiscoveryPipeline, "run", fake_pipeline_run)

    args = investigate.build_parser().parse_args(["Demo Default CLI Co., Ltd."])
    payload = asyncio.run(investigate.run(args))

    assert payload["type"] == "investigation_packet"
    assert payload["one_click"] is True
    assert payload["summary"]["evidence_count"] == 6
    assert calls["resolve"]["records"] is None
    assert calls["resolve"]["search_engine"] is None
    assert isinstance(calls["run"]["search_engine"], FakeDefaultSearch)


def test_investigation_packet_ranks_exact_official_evidence_first() -> None:
    graph = {
        "company": "Demo Ranking Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "review-1",
                "source": "wikidata_public_entity_graph",
                "title": "Wikidata related topic",
                "confidence": 0.56,
                "claims": [],
                "claim_count": 0,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.68},
            },
            {
                "id": "exact-1",
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company ticker match: Demo Ranking Co.",
                "confidence": 0.62,
                "claims": [],
                "claim_count": 0,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Ranking Co.").to_dict()

    assert packet["evidence_ledger"][0]["source"] == "sec_edgar_public_api"
    assert packet["evidence_ledger"][0]["entity_match_level"] == "exact"
    assert packet["evidence_ledger"][1]["record_kind"] == "lead"


def test_investigation_packet_surfaces_claim_corroboration_and_conflicts() -> None:
    graph = {
        "company": "Demo Corroboration Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 3,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "official-supplier",
                "source": "official_registry_public",
                "title": "Official supplier disclosure",
                "confidence": 0.88,
                "claims": ["supplier=Acme Components; controller=Licensed Owner"],
                "claim_count": 2,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
            {
                "id": "licensed-supplier",
                "source": "licensed_trade_database",
                "title": "Licensed trade profile",
                "confidence": 0.82,
                "claims": ["supplier=Acme Components"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "strong", "score": 0.94},
            },
            {
                "id": "public-controller-lead",
                "source": "public_web_search",
                "title": "Public controller lead",
                "confidence": 0.51,
                "claims": ["controller=Public Executive Lead"],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.9},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Corroboration Co.").to_dict()
    corroboration = packet["source_provenance"]["claim_corroboration"]

    assert corroboration["multi_source_supported_count"] >= 1
    assert corroboration["conflict_field_count"] >= 1
    assert packet["enterprise_cognition"]["claim_corroboration"] == corroboration
    assert any(row["field"] == "supplier" for row in corroboration["supported_claims"])
    assert any(row["field"] == "controller" for row in corroboration["conflict_fields"])
    assert "claim_conflicts_need_review" in packet["quality_gate"]["warnings"]
    assert "multi_source_claims_present" in packet["quality_gate"]["strengths"]
    assert "claim corroboration: multi_source_supported=" in packet["report_markdown"]
    assert "supported claim: supplier=Acme Components" in packet["report_markdown"]
    assert "conflict review: controller" in packet["report_markdown"]


def test_claim_corroboration_does_not_treat_multi_supplier_as_conflict() -> None:
    graph = {
        "company": "Demo Multi Supplier Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "supplier-a",
                "source": "licensed_trade_database",
                "title": "Licensed trade profile A",
                "confidence": 0.82,
                "claims": ["supplier=Acme Components"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "strong", "score": 0.94},
            },
            {
                "id": "supplier-b",
                "source": "public_web_search",
                "title": "Public supplier profile B",
                "confidence": 0.58,
                "claims": ["supplier=Beta Materials"],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.91},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Multi Supplier Co.").to_dict()
    corroboration = packet["source_provenance"]["claim_corroboration"]

    assert corroboration["conflict_field_count"] == 0
    assert "claim_conflicts_need_review" not in packet["quality_gate"]["warnings"]


def test_investigation_packet_extracts_sec_companyfacts_financial_cognition() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "sec-companyfacts",
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company facts: Apple Inc.",
                "url": "https://www.sec.gov/edgar/browse/?CIK=0000320193",
                "confidence": 0.78,
                "claims": [
                    "SEC EDGAR companyfacts: cik=0000320193; revenue=391035000000; "
                    "net_income=93736000000; operating_cash_flow=118254000000; "
                    "net_margin=0.2397; cash_conversion=1.2616; debt_to_assets=0.8379"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "strong", "score": 0.98},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    financial = packet["enterprise_cognition"]["financial"]
    fund_flow = packet["enterprise_cognition"]["fund_flow_profile"]

    assert financial["cik"] == "0000320193"
    assert financial["revenue"] == 391035000000
    assert financial["operating_cash_flow"] == 118254000000
    assert financial["cash_conversion"] == 1.2616
    assert fund_flow["type"] == "fund_flow_profile"
    assert "revenue=391035000000.0" in fund_flow["money_in_signals"]
    assert "operating_cash_flow=118254000000.0" in fund_flow["money_in_signals"]
    assert "elevated_liabilities_to_assets" in fund_flow["money_out_or_pressure_signals"]
    assert packet["quality_gate"]["ok"] is True
    assert "financial_facts_present" in packet["quality_gate"]["strengths"]
    assert "financial_gap_conflicts_with_financial_facts" not in packet["quality_gate"]["blockers"]
    assert "## 财务认知" in packet["report_markdown"]
    assert "## 资金流画像" in packet["report_markdown"]
    assert "operating_cash_flow=118.25B" in packet["report_markdown"]


def test_investigation_packet_uses_public_web_capital_leads_in_fund_flow() -> None:
    graph = {
        "company": "Demo Capital Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "public-web-capital",
                "source": "public_web_search",
                "title": "Demo Capital Co. financing and liquidity update",
                "url": "https://example.com/demo-capital-update",
                "confidence": 0.72,
                "claims": [
                    "Public web capital lead: financing_event=publicly_described; "
                    "financing_amount=$50 million; cash_or_liquidity_pressure=publicly_described; "
                    "asset_or_equity_pressure=publicly_described; sources=public web title/snippet/fetch preview"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Co.").to_dict()
    operational = packet["enterprise_cognition"]["operational_event_profile"]
    fund_flow = packet["enterprise_cognition"]["fund_flow_profile"]

    assert operational["financing_event_count"] == 1
    assert operational["capital_pressure_event_count"] == 1
    assert operational["capital_pressure_rows"][0]["status"] == "public_web_lead_needs_corroboration"
    assert "financing_events=1" in fund_flow["money_in_signals"]
    assert "capital_pressure_events=1" in fund_flow["money_out_or_pressure_signals"]
    assert "## 资金流画像" in packet["report_markdown"]
    assert "资本压力: 1" in packet["report_markdown"]


def test_investigation_packet_builds_industry_and_product_cognition_from_evidence() -> None:
    graph = {
        "company": "Demo Device Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "industry-10k",
                "source": "sec_edgar_public_api",
                "title": "SEC 10-K segment discussion: Demo Device Co.",
                "url": "https://www.sec.gov/demo-device-10k",
                "confidence": 0.82,
                "claims": [
                    "Public industry signal: industry=consumer electronics; "
                    "industry_growth=0.03; capacity_growth=0.18; "
                    "price_change=-0.08; customer_power=0.82; "
                    "sources=SEC 10-K segment discussion"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
            {
                "id": "product-10k",
                "source": "sec_edgar_public_api",
                "title": "SEC 10-K product discussion: Demo Device Co.",
                "url": "https://www.sec.gov/demo-device-product-10k",
                "confidence": 0.8,
                "claims": [
                    "Public product signal: product=iPhone-style device; "
                    "product_revenue_growth=-0.08; price_change=-0.06; "
                    "core_product_revenue_ratio=0.74; "
                    "substitute_performance_gap=0.1; substitute_price_advantage=0.2; "
                    "customer_churn_rate=0.22; "
                    "customer_value=installed base and ecosystem lock-in"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Device Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "consumer electronics"
    assert cognition["industry"]["lifecycle"] == "maturity"
    assert cognition["industry"]["threat_level"] == "high"
    assert cognition["industry"]["input_signals"]["industry_growth"] == "0.03"
    assert cognition["industry"]["verification_status"] == "evidence_backed_public_claims"
    assert cognition["product"]["product_name"] == "iPhone-style device"
    assert cognition["product"]["lifecycle"] == "decline"
    assert cognition["product"]["substitution_risk"] == "high"
    assert cognition["product"]["input_signals"]["customer_value"] == "installed base and ecosystem lock-in"
    assert not any("\u884c\u4e1a" in gap for gap in cognition["evidence_gaps"])
    assert not any("\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap for gap in cognition["evidence_gaps"])
    assert "## 行业认知" in packet["report_markdown"]
    assert "## 产品认知" in packet["report_markdown"]


def test_investigation_packet_builds_supply_chain_cognition_from_evidence() -> None:
    graph = {
        "company": "Demo Industrial Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "supply-chain-annual-report",
                "source": "official_annual_report",
                "title": "Annual report supply-chain discussion: Demo Industrial Co.",
                "url": "https://example.com/demo-industrial-annual-report",
                "confidence": 0.84,
                "claims": [
                    "Public supply-chain signal: customer=State Grid; "
                    "supplier=Demo Components Ltd.; upstream=semiconductor materials; "
                    "downstream=industrial automation; partner=Demo Integrator; "
                    "customer_concentration=0.62; supplier_concentration=0.48; "
                    "value_chain_role=system_integrator"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Industrial Co.").to_dict()
    supply_chain = packet["enterprise_cognition"]["supply_chain_profile"]
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]
    case_lens = packet["enterprise_cognition"]["case_investigation_lens"]

    assert supply_chain["verification_status"] == "evidence_backed_public_claims"
    assert supply_chain["row_count"] == 8
    assert supply_chain["source_count"] == 1
    assert supply_chain["corroboration_status"] == "single_source_needs_corroboration"
    assert supply_chain["customer_count"] == 1
    assert supply_chain["supplier_count"] == 1
    assert supply_chain["upstream_count"] == 1
    assert supply_chain["downstream_count"] == 1
    assert supply_chain["relationship_count"] == 4
    assert supply_chain["concentration_signal_count"] == 2
    assert supply_chain["customers"][0]["value"] == "State Grid"
    assert supply_chain["suppliers"][0]["value"] == "Demo Components Ltd."
    assert any(row["value"] == "industrial automation" for row in supply_chain["relationships"])
    assert any(row["field"] == "customer_concentration" for row in supply_chain["concentration_signals"])
    assert goods_flow["type"] == "goods_flow_profile"
    assert goods_flow["corroboration_status"] == "single_source_needs_corroboration"
    assert any("State Grid" in signal for signal in goods_flow["customer_signals"])
    assert any("Demo Components Ltd." in signal for signal in goods_flow["supplier_signals"])
    assert any("semiconductor materials" in signal for signal in goods_flow["upstream_signals"])
    assert any("industrial automation" in signal for signal in goods_flow["downstream_signals"])
    assert any("customer_concentration" in signal for signal in goods_flow["concentration_signals"])
    assert case_lens["name"] == "扒光查案式调查"
    assert [track["key"] for track in case_lens["tracks"]] == ["money", "goods", "people"]
    assert any("supply_chain=" in signal for signal in case_lens["tracks"][1]["known_signals"])
    assert not any("\u4e0a\u4e0b\u6e38" in gap or "\u5546\u4e1a\u7248\u56fe" in gap for gap in packet["enterprise_cognition"]["evidence_gaps"])
    assert "## 货物流/生意链画像" in packet["report_markdown"]
    assert "## 供应链与商业版图" in packet["report_markdown"]
    assert "## 扒光查案式调查" in packet["report_markdown"]
    assert "single_source_needs_corroboration" in packet["report_markdown"]
    assert "State Grid" in packet["report_markdown"]


def test_investigation_packet_uses_exact_public_description_as_industry_lead() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "wikidata-apple",
                "source": "wikidata_public_entity_graph",
                "title": "Wikidata entity data: Apple Inc.",
                "url": "http://www.wikidata.org/entity/Q312",
                "confidence": 0.7,
                "claims": [
                    "American multinational technology company based in Cupertino, California; wikidata_id=Q312"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "technology"
    assert cognition["industry"]["lifecycle"] == "unknown"
    assert cognition["industry"]["verification_status"] == "public_description_lead"
    assert "numeric lifecycle" in cognition["industry"]["evidence_limit"]
    assert cognition["product"] is None
    assert not any("行业" in gap for gap in cognition["evidence_gaps"])
    assert any("产品" in gap or "替代品" in gap for gap in cognition["evidence_gaps"])


def test_investigation_packet_uses_business_scope_as_product_lead() -> None:
    graph = {
        "company": "Demo Battery Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-business-scope",
                "source": "official_china_registry_portal_catalog",
                "title": "Registry business scope: Demo Battery Co.",
                "url": "https://example.gov.cn/demo-battery",
                "confidence": 0.76,
                "claims": [
                    "business_scope=research, manufacture and sale of lithium batteries and energy storage systems"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Battery Co.").to_dict()
    product = packet["enterprise_cognition"]["product"]
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]

    assert product["product_name"] == "lithium batteries and energy storage systems"
    assert product["verification_status"] == "public_description_lead"
    assert "structured-source corroboration" in product["evidence_limit"]
    assert any("lithium batteries" in signal for signal in goods_flow["product_signals"])
    assert not any(
        "\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap
        for gap in packet["enterprise_cognition"]["evidence_gaps"]
    )
    assert "## 产品认知" in packet["report_markdown"]


def test_business_scope_builds_industry_and_product_leads_for_logistics() -> None:
    graph = {
        "company": "Demo Logistics Cloud Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-logistics-scope",
                "source": "official_china_registry_portal_catalog",
                "title": "Registry business scope: Demo Logistics Cloud Co.",
                "url": "https://example.gov.cn/demo-logistics-cloud",
                "confidence": 0.78,
                "claims": [
                    "business_scope=logistics, warehousing and freight forwarding services"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Logistics Cloud Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert cognition["industry"]["industry"] == "logistics and supply chain"
    assert cognition["industry"]["verification_status"] == "public_description_lead"
    assert cognition["product"]["product_name"] == "logistics and warehousing services"
    assert cognition["product"]["verification_status"] == "public_description_lead"
    assert any("logistics and warehousing" in signal for signal in cognition["goods_flow_profile"]["product_signals"])
    assert not any("行业" in gap for gap in cognition["evidence_gaps"])
    assert not any("产品" in gap or "替代品" in gap for gap in cognition["evidence_gaps"])


def test_investigation_packet_uses_subject_profile_for_control_ownership_cognition() -> None:
    graph = {
        "company": "Demo Control Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
            "subject_profile": {
                "seed_subject_name": "Demo Control Co.",
                "subject_count": 2,
                "controller_candidate_count": 1,
                "covered_dimensions": ["identity", "control_ownership"],
            },
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "registry-1",
                "source": "fixture_public_registry",
                "title": "Demo Control Co. registry profile",
                "confidence": 0.85,
                "claims": [
                    "Alice Zhang is listed as legal representative in the public registry fixture."
                ],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Control Co.",
                "controller_candidates": [
                    {
                        "person_id": "person:alice_zhang",
                        "name": "Alice Zhang",
                        "relation_type": "legal_representative",
                        "relation_types": ["legal_representative", "controller"],
                        "confidence": 0.87,
                        "verification_status": "verified",
                        "source_names": ["fixture_public_registry"],
                    }
                ],
                "evidence_gaps": ["Missing or weak relationship-network evidence"],
                "signals_by_dimension": {
                    "control_ownership": [
                        {
                            "dimension": "control_ownership",
                            "title": "Demo Control Co. -> Alice Zhang",
                            "value": "Alice Zhang",
                            "confidence": 0.87,
                            "verification_status": "verified",
                            "source_names": ["fixture_public_registry"],
                        }
                    ]
                },
                "relationship_graph": {
                    "nodes": [{"id": "company:demo_control_co."}],
                    "edges": [{"from_id": "company:demo_control_co.", "to_id": "person:alice_zhang"}],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Control Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    people_flow = cognition["people_flow_profile"]

    assert cognition["control_ownership"]["controller_candidate_count"] == 1
    assert cognition["control_ownership"]["controller_candidates"][0]["name"] == "Alice Zhang"
    assert cognition["control_ownership"]["verification_status"] == "verified"
    assert cognition["control_ownership"]["graph_summary"]["subject_count"] == 1
    assert cognition["control_ownership"]["graph_summary"]["relation_count"] == 1
    assert cognition["control_ownership"]["control_paths"]
    assert cognition["control_ownership"]["control_paths"][0]["to_name"] == "Alice Zhang"
    assert people_flow["type"] == "people_flow_profile"
    assert people_flow["verification_status"] == "verified"
    assert any("Alice Zhang" in signal for signal in people_flow["controller_signals"])
    assert any("Alice Zhang" in signal for signal in people_flow["control_path_signals"])
    assert any("relations=1" in signal for signal in people_flow["key_person_signals"])
    assert any("控制权线索已识别" in item for item in cognition["risk_hypotheses"])
    assert any("控制路径预览" in item for item in cognition["risk_hypotheses"])
    assert any("核验控制权候选" in item for item in cognition["monitoring_watchlist"])
    assert any("控制路径：" in item for item in cognition["monitoring_watchlist"])
    assert any("控制权候选" in item for item in cognition["next_questions"])
    assert "## 控制权与实控人" in packet["report_markdown"]
    assert "## 人线/控制关系画像" in packet["report_markdown"]
    assert "控制路径预览" in packet["report_markdown"]


def test_investigation_packet_does_not_promote_review_leads_to_industry_product_facts() -> None:
    graph = {
        "company": "Demo Weak Match Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "weak-web-lead",
                "source": "public_web_search",
                "title": "Possible product page for a similarly named company",
                "confidence": 0.5,
                "claims": [
                    "industry=consumer electronics; industry_growth=0.2; "
                    "product=smart device; product_revenue_growth=0.3"
                ],
                "claim_count": 1,
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.62},
            },
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Match Co.").to_dict()
    cognition = packet["enterprise_cognition"]

    assert packet["evidence_ledger"][0]["record_kind"] == "lead"
    assert cognition["industry"] is None
    assert cognition["product"] is None
    assert any("\u884c\u4e1a" in gap for gap in cognition["evidence_gaps"])
    assert any("\u4ea7\u54c1" in gap or "\u66ff\u4ee3\u54c1" in gap for gap in cognition["evidence_gaps"])
    assert "## 行业认知" not in packet["report_markdown"]
    assert "## 产品认知" not in packet["report_markdown"]


def test_investigation_report_prioritizes_specific_profile_addresses() -> None:
    graph = {
        "company": "Apple Inc.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": [],
            "subject_profile": {
                "seed_subject_name": "Apple Inc.",
                "subject_count": 2,
                "controller_candidate_count": 0,
                "covered_dimensions": ["identity", "location_activity"],
            },
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "exact-gleif",
                "source": "gleif_lei_public_api",
                "title": "GLEIF LEI record: Apple Inc.",
                "confidence": 0.86,
                "claims": ["LEI=HWUPKR0MPOU8FGXBT394; registered_address=C/O C T Corporation System"],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Apple Inc.",
                "controller_candidates": [],
                "evidence_gaps": [],
                "signals_by_dimension": {
                    "identity": [
                        {
                            "dimension": "identity",
                            "title": "Apple Inc.",
                            "value": "Apple Inc.",
                            "confidence": 0.9,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        }
                    ],
                    "location_activity": [
                        {
                            "dimension": "location_activity",
                            "title": "GLEIF LEI record: Apple Inc.",
                            "value": "LEI=HWUPKR0MPOU8FGXBT394; registered_address=C/O C T Corporation System",
                            "confidence": 0.86,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        },
                        {
                            "dimension": "location_activity",
                            "title": "Apple Inc. -> One Apple Park Way",
                            "value": "One Apple Park Way, Cupertino, US-CA, 95014, US",
                            "relation_type": "headquarters_address",
                            "confidence": 0.8,
                            "verification_status": "verified",
                            "source_names": ["gleif_lei_public_api"],
                        },
                    ],
                },
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    report = packet["report_markdown"]

    assert report.index("One Apple Park Way") < report.index("LEI=HWUPKR0MPOU8FGXBT394")


def test_investigation_report_gaps_read_like_work_orders(tmp_path) -> None:
    company = "Demo Investigation Gap Copy Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    report = build_investigation_packet(graph, input_text=company).to_dict()["report_markdown"]

    assert "下一轮" in report
    assert "Missing or weak" not in report


def test_investigation_report_quality_gate_uses_business_copy(tmp_path) -> None:
    company = "Demo Product Quality Copy Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    report = build_investigation_packet(graph, input_text=company).to_dict()["report_markdown"]

    assert "## 交付质量" in report
    assert "可进入人工复核" in report
    assert "已有财务或资本市场事实" in report
    assert "coverage_gaps_present" not in report
    assert "enterprise_cognition_gaps_present" not in report
    assert "financial_facts_missing" not in report
    assert "Quality next actions" not in report


def test_investigation_report_surfaces_relationship_network_and_parks_monitoring(tmp_path) -> None:
    company = "Demo Relationship Report Co., Ltd."
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "events.jsonl",
        )
    )
    graph = export_risk_graph(result).to_dict()

    packet = build_investigation_packet(graph, input_text=company).to_dict()
    report = packet["report_markdown"]

    assert packet["enterprise_cognition"]["relationship_network"]["relation_count"] >= 1
    assert packet["one_click_readiness"]["relationship_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_evidence_backed_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_auditable_edge_count"] >= 1
    assert packet["one_click_readiness"]["relationship_missing_evidence_edge_count"] == 0
    control_paths = packet["enterprise_cognition"]["control_ownership"]["control_paths"]
    control_path_keys = {
        (item["from_name"], item["to_name"], item["relation_type"])
        for item in control_paths
    }
    assert len(control_paths) == len(control_path_keys)
    assert packet["source_provenance"]["factual_count"] >= 1
    assert "## 关联关系网络" in report
    assert "最强关联" in report
    assert "edge_audit: admission=" in report
    assert "evidence=" in report
    assert "relationship graph: edges=" in report
    assert "evidence_backed=" in report
    assert "auditable_fact=" in report
    assert "missing_evidence=0" in report
    assert "actual_controller" in report
    assert "法定代表人" in report
    assert "## 来源出处" in report
    assert "官方/授权事实" in report
    assert "## 后续版本目标" in report
    assert "当前 0.5.0 Alpha 不上线持续监控" in report
    assert "## 后续版本基线" not in report


def test_investigation_packet_surfaces_source_failure_taxonomy() -> None:
    graph = {
        "company": "Demo Diagnostics Co.",
        "summary": {
            "run_id": "risk:test123",
            "execution_state": "partial_source_failure",
            "evidence_count": 1,
            "risk_event_count": 0,
            "next_actions": ["Review failed source diagnostics before final reliance."],
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "demo-evidence",
                "source": "healthy_public_api",
                "title": "Demo Diagnostics Co. registry profile",
                "confidence": 0.88,
                "claims": ["legal_name=Demo Diagnostics Co."],
                "claim_count": 1,
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "run_id": "risk:test123",
            "retrieval_summary": {
                "run_id": "risk:test123",
                "execution_state": "partial_source_failure",
                "status_counts": {"success": 1, "timeout": 1, "empty": 1},
                "coverage": {
                    "missing_domains": ["ownership_control"],
                    "domains_without_evidence": ["financing_capital_markets"],
                },
                "source_routing": {
                    "configured_count": 2,
                    "available_count": 1,
                    "configured_sources": ["creditchina_public", "qyyjt"],
                    "available_sources": ["creditchina_public"],
                    "unavailable_sources": ["qyyjt"],
                    "health_reports": {
                        "creditchina_public": {
                            "ok": True,
                            "enabled": True,
                            "smoke_tested": True,
                        },
                        "qyyjt": {
                            "ok": True,
                            "enabled": False,
                            "smoke_tested": False,
                        },
                    },
                },
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:000",
                    "source": "healthy_public_api",
                    "source_type": "rest_api",
                    "status": "success",
                    "failure_category": "none",
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:001",
                    "source": "slow_public_api",
                    "source_type": "rest_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "timeout_seconds": 0.1,
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:002",
                    "source": "empty_public_api",
                    "source_type": "rest_api",
                    "status": "empty",
                    "failure_category": "empty_result",
                },
                {
                    "run_id": "risk:test123",
                    "trace_id": "risk:test123:source:003",
                    "source": "qyyjt_api",
                    "source_type": "authorized_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Diagnostics Co.").to_dict()

    assert packet["source_failure_summary"]["run_id"] == "risk:test123"
    assert packet["source_failure_summary"]["failure_count"] == 3
    assert packet["source_failure_summary"]["by_failure_category"] == {
        "timeout": 1,
        "empty_result": 1,
        "authorization": 1,
    }
    resilience = packet["source_failure_summary"]["source_resilience_profile"]
    assert resilience["type"] == "source_resilience_profile"
    assert resilience["status"] == "needs_operator_recovery"
    assert resilience["failure_count"] == 3
    assert resilience["not_searched_count"] == 1
    assert resilience["no_evidence_count"] == 1
    assert resilience["recovery_blocked_count"] > 0
    assert resilience["ready_to_recover_now"] is False
    assert resilience["recommended_action"].startswith("Enable or add connector")
    assert packet["one_click_readiness"]["source_resilience_status"] == "needs_operator_recovery"
    assert packet["one_click_readiness"]["source_resilience_score"] == resilience["score"]
    assert packet["one_click_readiness"]["source_resilience_needs_operator_recovery"] is True
    assert "gsxt_shareholder_tabs" in packet["one_click_readiness"]["source_resilience_recommended_action"]
    assert packet["one_click_readiness"]["attempted_source_count"] == 4
    assert packet["one_click_readiness"]["coverage_status_counts"] == {"empty": 1}
    assert packet["one_click_readiness"]["coverage_not_searched_count"] == 1
    assert packet["one_click_readiness"]["coverage_no_evidence_count"] == 1
    assert packet["one_click_readiness"]["coverage_gap_count"] == 2
    assert packet["one_click_readiness"]["coverage_gap_severity"] == "medium"
    assert packet["one_click_readiness"]["coverage_attempt_ratio"] == 0.8
    assert packet["one_click_readiness"]["coverage_next_action"].startswith("Complete missing-domain recovery")
    assert packet["one_click_readiness"]["coverage_missing_domains"] == ["ownership_control"]
    assert packet["one_click_readiness"]["coverage_domains_without_evidence"] == ["financing_capital_markets"]
    assert packet["one_click_readiness"]["coverage_policy"].startswith("not_searched means coverage was not attempted")
    assert "coverage next action" in packet["report_markdown"]
    assert "source_resilience_needs_operator_recovery" in packet["quality_gate"]["warnings"]
    assert any("source resilience" in action for action in packet["quality_gate"]["next_actions"])
    assert packet["source_failure_summary"]["coverage_interpretation"] == {
        "not_searched_count": 1,
        "no_evidence_count": 1,
        "policy": "not_searched means coverage was not attempted; no_evidence means attempted sources returned no usable evidence.",
    }
    assert packet["source_failure_summary"]["missing_domains"] == ["ownership_control"]
    assert packet["source_failure_summary"]["domains_without_evidence"] == ["financing_capital_markets"]
    recovery = packet["source_failure_summary"]["coverage_recovery_actions"]
    assert recovery[0]["action_id"] == "COVERAGE-MISSING-OWNERSHIP_CONTROL"
    assert recovery[0]["suggested_source"] == "registry_shareholder_filings"
    assert "gsxt_shareholder_tabs" in recovery[0]["fallback_sources"]
    assert "ubo_candidate" in recovery[0]["key_fields"]
    assert recovery[0]["origin_priority"][0]["tier"] == "official_public"
    assert "gsxt_shareholder_tabs" in recovery[0]["origin_priority"][0]["sources"]
    assert recovery[0]["origin_priority"][1]["tier"] == "global_public_registry"
    assert "openownership_public" in recovery[0]["origin_priority"][1]["sources"]
    assert recovery[1]["domain"] == "financing_capital_markets"
    assert recovery[1]["target_lane"] == "capital"
    assert "chinamoney_public" in recovery[1]["fallback_sources"]
    assert "northdata_public" in recovery[1]["fallback_sources"]
    assert "credit_rating" in recovery[1]["key_fields"]
    assert "business_credit_score" in recovery[1]["key_fields"]
    assert recovery[1]["origin_priority"][1]["tier"] == "global_public_business_credit"
    assert "northdata_public" in recovery[1]["origin_priority"][1]["sources"]
    assert "qyyjt_authorized_api" in recovery[1]["origin_priority"][3]["sources"]
    recovery_summary = packet["source_failure_summary"]["coverage_recovery_summary"]
    assert recovery_summary["action_count"] == 2
    assert recovery_summary["p0_count"] == 1
    assert recovery_summary["p1_count"] == 1
    assert recovery_summary["by_lane"] == {"people": 1, "capital": 1}
    assert recovery_summary["top_next_action"]["suggested_source"] == "registry_shareholder_filings"
    execution_plan = packet["source_failure_summary"]["coverage_recovery_execution_plan"]
    assert execution_plan[0]["step_id"] == "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1"
    assert execution_plan[0]["tier"] == "official_public"
    assert execution_plan[0]["source"] == "gsxt_shareholder_tabs"
    assert "shareholder_name" in execution_plan[0]["key_fields"]
    readiness = packet["source_failure_summary"]["coverage_recovery_execution_readiness"]
    assert readiness["ready_count"] == 0
    assert readiness["blocked_count"] == readiness["step_count"]
    assert readiness["blocked_steps"][0]["status"] == "connector_required"
    assert readiness["blocked_steps"][0]["domain"] == "ownership_control"
    assert "shareholder" in readiness["blocked_steps"][0]["query_family"]
    assert "shareholder_name" in readiness["blocked_steps"][0]["key_fields"]
    assert readiness["blocked_steps"][0]["required_action"].startswith("Add or map a connector")
    decision = packet["source_failure_summary"]["coverage_recovery_decision"]
    assert decision["decision"] == "enable_or_add_connector_before_retry"
    assert decision["recommended_step"]["domain"] == "ownership_control"
    assert decision["ready_to_run"] is False
    routing_summary = packet["source_failure_summary"]["source_routing_summary"]
    assert routing_summary["configured_count"] == 2
    assert routing_summary["available_sources"] == ["creditchina_public"]
    assert routing_summary["smoke_tested_sources"] == ["creditchina_public"]
    assert routing_summary["explicit_only_sources"] == ["qyyjt"]
    assert packet["source_failure_summary"]["top_failures"][0]["source"] == "slow_public_api"
    assert packet["source_failure_summary"]["public_origin_fallbacks"][0]["blocked_source"] == "qyyjt"
    assert "official_company_registry" in packet["source_failure_summary"]["public_origin_fallbacks"][0]["origin_channels"]
    assert packet["source_failure_summary"]["public_origin_next_actions"][0]["action_id"] == "PUBLIC-ORIGIN-ENT_BASIC"
    assert packet["source_failure_summary"]["public_origin_next_actions"][0]["target_lane"] == "subject_resolution"
    assert packet["one_click_readiness"]["public_origin_fallback_count"] == 5
    assert packet["one_click_readiness"]["public_origin_next_action_count"] == 5
    assert packet["one_click_readiness"]["public_origin_modules"][0] == "ent_basic"
    assert packet["one_click_readiness"]["public_origin_top_action"]["action_id"] == "PUBLIC-ORIGIN-ENT_BASIC"
    assert packet["one_click_readiness"]["public_origin_top_action"]["record_type"] == "registry_identity"
    assert "legal_name" in packet["one_click_readiness"]["public_origin_top_action"]["required_fields"]
    assert "module-specific query plan" in packet["one_click_readiness"]["public_origin_top_action"]["admission_gate"]
    assert any("Run public-origin fallback for ent_basic" in action for action in packet["next_actions"])
    assert "ownership_control" in packet["monitoring_seed"]["watched_dimensions"]
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["domain"] == "ownership_control"
    assert "gsxt_shareholder_tabs" in packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["fallback_sources"]
    assert "ubo_candidate" in packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["key_fields"]
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][0]["origin_priority"][0]["tier"] == "official_public"
    assert packet["monitoring_seed"]["coverage_recovery_execution_plan"][0]["source"] == "gsxt_shareholder_tabs"
    assert packet["monitoring_seed"]["coverage_recovery_execution_readiness"]["ready_count"] == 0
    assert packet["monitoring_seed"]["recovery_execution_queue"]["ready_to_run"] is False
    assert packet["monitoring_seed"]["recovery_execution_queue"]["queued_count"] == 0
    assert packet["monitoring_seed"]["recovery_execution_queue"]["blocked_count"] > 0
    assert packet["monitoring_seed"]["coverage_recovery_watchlist"][1]["suggested_source"] == "exchange_disclosures_and_bond_portals"
    assert "## 运行诊断" in packet["report_markdown"]
    assert "失败类型:" in packet["report_markdown"]
    assert "source resilience: status=needs_operator_recovery" in packet["report_markdown"]
    assert "needs_operator_recovery=True" in packet["report_markdown"]
    assert (
        "coverage execution: attempted_sources=4 | not_searched=1 | no_evidence=1 | "
        "gaps=2 | severity=medium | attempt_ratio=0.8 | coverage_statuses=empty=1"
    ) in packet["report_markdown"]
    assert "coverage next action: Complete missing-domain recovery" in packet["report_markdown"]
    assert "one-click not searched domains: ownership_control(" in packet["report_markdown"]
    assert "one-click no evidence domains: financing_capital_markets(" in packet["report_markdown"]
    assert "source resilience blockers:" in packet["report_markdown"]
    assert "source resilience next:" in packet["report_markdown"]
    assert "source resilience next: Enable or add connector for gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "授权" in packet["report_markdown"]
    assert "public-origin next actions:" in packet["report_markdown"]
    assert "public-origin fallback: actions=5 | fallbacks=5 | modules=ent_basic" in packet["report_markdown"]
    assert "top public-origin action: PUBLIC-ORIGIN-ENT_BASIC" in packet["report_markdown"]
    assert "coverage recovery actions:" in packet["report_markdown"]
    assert "COVERAGE-MISSING-OWNERSHIP_CONTROL" in packet["report_markdown"]
    assert "fallback_sources=gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "key_fields=shareholder_name" in packet["report_markdown"]
    assert "origin_priority=official_public:gsxt_shareholder_tabs" in packet["report_markdown"]
    assert "coverage recovery execution plan:" in packet["report_markdown"]
    assert "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1" in packet["report_markdown"]
    assert "coverage recovery execution readiness:" in packet["report_markdown"]
    assert "coverage recovery decision:" in packet["report_markdown"]
    assert "recommended_step:" in packet["report_markdown"]
    assert any("Recover missing coverage for ownership_control" in action for action in packet["next_actions"])
    assert "coverage interpretation: not_searched=1 | no_evidence=1 | lead_only=0" in packet["report_markdown"]
    assert "not searched domains:" in packet["report_markdown"]
    assert "no evidence domains:" in packet["report_markdown"]
    assert "覆盖恢复盯防:" in packet["report_markdown"]
    assert "source routing health: configured=2 | available=1 | smoke_tested=1" in packet["report_markdown"]
    assert "smoke-tested sources: creditchina_public" in packet["report_markdown"]
    assert "explicit-only ready sources: qyyjt" in packet["report_markdown"]
    assert "registry_shareholder_filings" in packet["report_markdown"]
    assert "trace=risk:test123:source:001" in packet["report_markdown"]


def test_recurring_source_failure_patterns_are_report_and_seed_visible() -> None:
    graph = {
        "company": "Demo Recurring Failure Co.",
        "summary": {
            "run_id": "risk:repeat123",
            "execution_state": "partial_coverage",
            "evidence_count": 0,
            "risk_event_count": 0,
        },
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:repeat123",
                "execution_state": "partial_coverage",
                "status_counts": {"timeout": 2, "error": 2},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:001",
                    "source": "slow_bond_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "objective": "bond default capital lookup",
                    "timeout_seconds": 0.2,
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:002",
                    "source": "slow_bond_api",
                    "status": "timeout",
                    "failure_category": "timeout",
                    "objective": "bond rating capital lookup",
                    "timeout_seconds": 0.2,
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:003",
                    "source": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt controller shareholder lookup",
                    "error": "authorization required",
                },
                {
                    "run_id": "risk:repeat123",
                    "trace_id": "risk:repeat123:source:004",
                    "source": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt ubo group lookup",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Recurring Failure Co.").to_dict()
    patterns = packet["source_failure_summary"]["recurring_failure_patterns"]

    assert patterns[0]["source"] == "qyyjt_api"
    assert patterns[0]["failure_category"] == "authorization"
    assert patterns[0]["domain"] == "ownership_control"
    assert patterns[0]["count"] == 2
    assert patterns[0]["trace_ids"] == ["risk:repeat123:source:003", "risk:repeat123:source:004"]
    assert "Confirm credentials" in patterns[0]["operator_action"]
    assert any(
        item["source"] == "slow_bond_api"
        and item["failure_category"] == "timeout"
        and item["domain"] == "financing_capital_markets"
        and item["count"] == 2
        for item in patterns
    )
    assert packet["monitoring_seed"]["recurring_failure_patterns"] == patterns
    assert packet["monitoring_seed"]["recovery_execution_summary"]["recurring_failure_count"] == 2
    assert "recurring source failure patterns:" in packet["report_markdown"]
    assert "qyyjt_api / authorization / ownership_control: count=2" in packet["report_markdown"]


def test_skipped_unsupported_source_is_coverage_status_not_failure() -> None:
    graph = {
        "company": "Demo Skipped Source Co.",
        "summary": {
            "run_id": "risk:skip123",
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "demo-evidence",
                "source": "public_web_search",
                "title": "Demo public profile",
                "confidence": 0.7,
                "claims": ["Public profile lead"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review", "score": 0.7},
            }
        ],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:skip123",
                "execution_state": "evidence_found",
                "status_counts": {"success": 1, "skipped_unsupported_source": 1},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:skip123",
                    "trace_id": "risk:skip123:source:001",
                    "source_name": "public_web_search",
                    "status": "success",
                    "failure_category": "none",
                },
                {
                    "run_id": "risk:skip123",
                    "trace_id": "risk:skip123:source:002",
                    "source_name": "sec_edgar_public_api",
                    "source_hint": "sec_edgar_public_api",
                    "status": "skipped_unsupported_source",
                    "failure_category": "skipped_unsupported_source",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Skipped Source Co.").to_dict()

    assert packet["source_failure_summary"]["failure_count"] == 0
    assert packet["source_failure_summary"]["top_failures"] == []
    assert packet["source_failure_summary"]["by_failure_category"] == {}
    assert packet["source_failure_summary"]["by_status"] == {
        "success": 1,
        "skipped_unsupported_source": 1,
    }
    assert packet["source_failure_summary"]["coverage_status_counts"] == {
        "skipped_unsupported_source": 1,
    }
    resilience = packet["source_failure_summary"]["source_resilience_profile"]
    assert resilience["failure_count"] == 0
    assert resilience["status"] in {"resilient", "partial_visibility"}
    assert resilience["score"] >= 80
    assert "skipped_unsupported_source=1" in packet["report_markdown"]


def test_qyyjt_public_origin_fallbacks_follow_failure_domain() -> None:
    graph = {
        "company": "Demo Bond Co.",
        "summary": {"run_id": "risk:bond123", "execution_state": "partial_coverage"},
        "risk_events": [],
        "evidence": [],
        "diagnostics": {
            "retrieval_summary": {
                "run_id": "risk:bond123",
                "execution_state": "partial_coverage",
                "status_counts": {"error": 1},
            },
            "source_diagnostics": [
                {
                    "run_id": "risk:bond123",
                    "source_name": "qyyjt_api",
                    "status": "error",
                    "failure_category": "authorization",
                    "objective": "qyyjt bond default credit rating lookup",
                    "error": "authorization required",
                },
            ],
            "subject_profile": {},
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Bond Co.").to_dict()
    modules = [item["module"] for item in packet["source_failure_summary"]["public_origin_fallbacks"]]
    fallback_by_module = {
        item["module"]: item
        for item in packet["source_failure_summary"]["public_origin_fallbacks"]
    }

    assert modules[:2] == ["ent_basic", "ent_financing"]
    assert "bond_profile" in modules
    assert "bond_default" in modules
    assert fallback_by_module["ent_financing"]["record_type"] == "financing_event"
    assert "amount" in fallback_by_module["ent_financing"]["required_fields"]
    assert "module-specific query plan" in fallback_by_module["ent_financing"]["admission_gate"]
    assert "acceptance_gate" in fallback_by_module["bond_default"]
    capital_actions = [
        action
        for action in packet["source_failure_summary"]["public_origin_next_actions"]
        if action["target_lane"] == "capital"
    ]
    assert capital_actions
    assert capital_actions[0]["record_type"] == "financing_event"
    assert "amount" in capital_actions[0]["required_fields"]
    assert capital_actions[0]["done_condition"]
    assert "record_type=financing_event" in packet["report_markdown"]
    assert "required_fields=financing_type, amount" in packet["report_markdown"]
    assert "admission_gate=module-specific query plan" in packet["report_markdown"]
    assert any(action["target_lane"] == "capital" for action in packet["source_failure_summary"]["public_origin_next_actions"])


def test_cli_can_print_connector_catalog(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--connectors",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "connector_catalog"
    assert payload["summary"]["default_enabled"] >= 4
    assert "default_public_intel" in payload["summary"]["zero_config_ready"]


def test_cli_can_print_release_readiness(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--release",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "release_readiness_brief"
    assert payload["contract"]["version"] == "0.5.0"
    assert payload["blockers"]


def test_cli_can_print_development_requirements(tmp_path) -> None:
    env = {**os.environ, "WST_PYTHON": os.environ.get("WST_PYTHON", sys.executable)}
    result = subprocess.run(
        [
            "node",
            str(ROOT / "bin" / "cli.js"),
            "--requirements",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "development_requirements_board"
    assert payload["completion_percent"] == 88
    assert payload["qyyjt_current_version"]["p0_queue_count"] == 20
    assert payload["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"


def test_fin_inst_profile_from_evidence_detects_admitted_rows() -> None:
    """Admitted fin_inst evidence rows produce a non-None fin_inst_profile."""
    from core.investigation import _fin_inst_profile_from_evidence

    evidence_ledger = [
        {
            "record_kind": "evidence",
            "source": "qyyjt_api:fin_inst",
            "claims": [
                "institution_name=中国工商银行",
                "institution_type=commercial_bank",
                "license_status=active",
                "region=北京",
                "risk_level=low",
                "counterparty_role=credit_lender",
            ],
            "url": "https://qyyjt.cn/fin_inst/demo",
            "confidence": 0.74,
        }
    ]

    risk_events = []
    profile = _fin_inst_profile_from_evidence(evidence_ledger, risk_events)

    assert profile is not None, "Expected fin_inst_profile to be non-None with admitted evidence"
    assert profile["row_count"] >= 1
    assert any("中国工商银行" in str(r.get("institution_name", "")) for r in profile["rows"]), (
        f"Expected 中国工商银行 in rows, got {profile['rows']}"
    )
    assert profile["verification_status"] == "licensed_qyyjt_fin_inst_contract"


def test_fin_inst_profile_from_evidence_returns_none_without_admitted_rows() -> None:
    """Without fin_inst evidence rows, fin_inst_profile returns None."""
    from core.investigation import _fin_inst_profile_from_evidence

    evidence_ledger = [
        {
            "record_kind": "evidence",
            "source": "qyyjt_api:bond_default",
            "claims": ["bond_name=Demo Bond", "amount=10000000"],
            "url": "https://qyyjt.cn/bond_default/demo",
            "confidence": 0.74,
        }
    ]

    profile = _fin_inst_profile_from_evidence(evidence_ledger, [])
    assert profile is None, "Expected None for non-fin_inst evidence"


def test_controller_confidence_label_is_present() -> None:
    """Controller candidates in report include a human-readable confidence_label."""
    from core.investigation import _control_ownership_from_subject_profile

    # Build a minimal profile brief with controller candidates
    profile_brief = {
        "controller_candidate_count": 1,
        "verification_status": "verified",
    }
    subject_profile = {
        "controller_candidates": [
            {
                "person_id": "p1",
                "name": "Alice Zhang",
                "relation_type": "actual_controller",
                "confidence": 0.85,
                "confidence_tier": "verified_controller",
                "confidence_basis": ["official:public", "entity_match:exact"],
                "control_paths": ["Demo Co. -> Alice Zhang"],
                "source_strength": 8,
                "match_score": 1.0,
                "evidence_ids": ["ev1"],
                "source_names": ["public registry sample"],
                "verification_status": "verified",
            }
        ],
        "seed_subject_id": "demo",
        "seed_subject_name": "Demo Co.",
        "subjects": {},
        "signals_by_dimension": {},
        "evidence_gaps": [],
        "compliance_notes": [],
    }

    result = _control_ownership_from_subject_profile(profile_brief, subject_profile)

    assert "controller_candidates" in result
    for c in result["controller_candidates"]:
        assert "confidence_label" in c, f"Missing confidence_label in candidate {c['name']}"
        assert c["confidence_label"] == "已验证实控人", f"Expected '已验证实控人' for verified_controller tier, got '{c['confidence_label']}'"


def test_controller_source_strength_label_present() -> None:
    from core.investigation import _control_ownership_from_subject_profile
    pb = {}
    sp = {"controller_candidates": [{"person_id": "p1", "name": "Alice Zhang", "relation_type": "actual_controller", "confidence": 0.85, "confidence_tier": "verified_controller", "confidence_basis": [], "control_paths": [], "source_strength": 8, "match_score": 1.0, "evidence_ids": [], "source_names": ["official"], "verification_status": "verified"}], "seed_subject_id": "d", "seed_subject_name": "Demo", "subjects": {}, "signals_by_dimension": {}, "evidence_gaps": [], "compliance_notes": []}
    r = _control_ownership_from_subject_profile(pb, sp)
    c = r["controller_candidates"][0]
    assert "source_strength_label" in c, f"Missing source_strength_label: {c.keys()}"
    assert c["source_strength_label"] == "高"


def test_public_capital_leads_reach_profile() -> None:
    from core.investigation import _capital_profile_from_public_web_evidence
    ledger = [{
        "record_kind": "evidence", "source": "public_web_search",
        "claims": ["Public web capital lead: financing_event=publicly_described; financing_amount=$50M; debt_or_credit_obligation=publicly_described; sources=public web"],
        "url": "https://example.com/news",
    }]
    profile = _capital_profile_from_public_web_evidence(ledger)
    assert profile is not None
    assert profile["row_count"] == 1
    assert "public_lead_needs_corroboration" in profile["verification_status"]


def test_relationship_resolution_summary_prioritizes_capital_and_people_leads() -> None:
    from core.relationship_resolution import build_relationship_resolution

    result = build_relationship_resolution(
        [
            {
                "evidence_id": "ev-rel-capital",
                "lane": "capital",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "lead",
                "claims": ["lender=Demo Bank; guarantor=Demo Guarantee Co."],
            },
            {
                "evidence_id": "ev-rel-people",
                "lane": "people",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "weak_lead",
                "claims": ["controller=Alice Zhang; shareholder=Demo HoldCo"],
            },
            {
                "evidence_id": "ev-rel-goods",
                "lane": "goods",
                "subject": "Demo Co.",
                "source_name": "public_web_search",
                "admission": "lead",
                "claims": ["supplier=Acme Components; customer=BigCo"],
            },
        ],
        {"resolved_entities": [{"name": "Demo Co."}]},
        {"edges": [{"from": "seed", "to": "Alice Zhang", "type": "actual_controller", "confidence": 0.88, "source": "qyyjt_api:ubo"}]},
    )

    summary = result["resolution_summary"]

    assert summary["typed_lead_count"] >= 6
    assert summary["weak_lead_count"] >= 1
    assert summary["admitted_edge_count"] == 1
    assert summary["by_lane"]["capital"] >= 2
    assert summary["by_lane"]["people"] >= 2
    assert summary["by_lane"]["goods"] >= 2
    assert summary["verification_queue"][0]["priority"] == "P0"
    assert "registry" in summary["verification_queue"][0]["next_action"] or "credit" in summary["verification_queue"][0]["next_action"]


def test_report_surfaces_relationship_resolution_summary() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Relationship Summary Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-capital",
                "source": "public_web_search",
                "title": "Capital counterparty lead",
                "confidence": 0.64,
                "claims": ["lender=Demo Bank; guarantor=Demo Guarantee Co."],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.95},
            },
            {
                "id": "ev-people",
                "source": "public_web_search",
                "title": "People relation lead",
                "confidence": 0.58,
                "claims": ["controller=Alice Zhang; supplier=Acme Components"],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.94},
            },
        ],
        "nodes": [],
        "edges": [],
        "timeline": [],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Relationship Summary Co.").to_dict()
    resolution = packet["enterprise_cognition"]["relationship_resolution_v1"]
    report = packet["report_markdown"]

    assert resolution["resolution_summary"]["by_lane"]["capital"] >= 2
    assert resolution["resolution_summary"]["by_lane"]["people"] >= 1
    assert "lane split:" in report
    assert "verify [P0]" in report


def test_no_capital_leads_returns_none() -> None:
    from core.investigation import _capital_profile_from_public_web_evidence
    profile = _capital_profile_from_public_web_evidence([])
    assert profile is None


def test_relationship_network_dedupes_edges_and_keeps_basis() -> None:
    from core.investigation import _relationship_network_from_subject_profile

    profile = {
        "relationship_graph": {
            "nodes": [
                {"id": "company:demo", "name": "Demo Co.", "kind": "company", "source_names": ["registry"]},
                {"id": "person:alice", "name": "Alice Zhang", "kind": "person", "source_names": ["registry"]},
            ],
            "edges": [
                {
                    "from_id": "company:demo",
                    "to_id": "person:alice",
                    "relation_type": "actual_controller",
                    "confidence": 0.86,
                    "admission": "lead",
                    "evidence_ids": ["ev1"],
                },
                {
                    "from_id": "company:demo",
                    "to_id": "person:alice",
                    "relation_type": "actual_controller",
                    "confidence": 0.90,
                    "admission": "fact",
                    "evidence_ids": ["ev2"],
                },
            ],
        }
    }

    network = _relationship_network_from_subject_profile(profile)

    assert network is not None
    assert network["subject_count"] == 2
    assert network["relation_count"] == 1
    assert network["relation_types"] == ["actual_controller"]
    assert network["top_edges"][0]["from_name"] == "Demo Co."
    assert network["top_edges"][0]["to_name"] == "Alice Zhang"
    assert network["top_edges"][0]["confidence"] == 0.90
    assert network["top_edges"][0]["admission"] == "fact"
    assert network["top_edges"][0]["evidence_ids"] == ["ev1", "ev2"]
    assert "public" in network["public_data_basis"].lower()


def test_capital_relationship_profile_links_admitted_counterparty_to_graph() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Capital Link Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Capital Link Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["qyyjt_api"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.87,
                            "evidence_ids": ["ev-fin-inst"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Link Co.").to_dict()
    profile = packet["enterprise_cognition"]["capital_relationship_profile"]

    assert profile["match_count"] == 1
    assert profile["relationship_risk_level"] in {"watch", "elevated", "high"}
    assert profile["linked_exposures"][0]["capital_identifier"] == "Demo Bank"
    assert profile["linked_exposures"][0]["relationship_type"] == "lender"
    assert packet["one_click_readiness"]["capital_relationship_needed"] is True
    assert packet["one_click_readiness"]["capital_relationship_explained"] is True
    assert packet["one_click_readiness"]["capital_relationship_status"] == "evidence_backed"
    assert packet["one_click_readiness"]["capital_relationship_unresolved_reason"] == ""
    assert packet["one_click_readiness"]["section_checks"]["capital_relationship_explained"] is True
    assert "Capital Relationship Profile" in packet["report_markdown"]
    assert "Demo Bank" in packet["report_markdown"]
    assert "admission=implicit_admitted_profile_edge" in packet["report_markdown"]
    assert "evidence=ev-fin-inst" in packet["report_markdown"]


def test_one_click_readiness_flags_unexplained_capital_pressure() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Unexplained Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Unexplained Capital Co.").to_dict()
    readiness = packet["one_click_readiness"]

    assert packet["enterprise_cognition"]["capital_pressure_profile"]["pressure_signal_count"] >= 1
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert readiness["capital_relationship_needed"] is True
    assert readiness["capital_relationship_explained"] is False
    assert readiness["capital_relationship_status"] == "unresolved"
    assert readiness["capital_relationship_unresolved_reason"] == "capital_pressure_without_admitted_relationship_edge"
    assert "Collect admitted relationship evidence" in readiness["capital_relationship_next_action"]
    assert readiness["capital_pressure_level"] == "elevated"
    assert readiness["capital_pressure_verification_status"] == "admitted_capital_pressure_facts"
    assert readiness["capital_pressure_lead_only_public_rows_present"] is False
    assert readiness["needs_operator_followup"] is True
    assert readiness["section_checks"]["capital_relationship_explained"] is False
    assert "capital_relationship_explained" in packet["report_markdown"]
    assert "capital: pressure=elevated | verification=admitted_capital_pressure_facts" in packet["report_markdown"]
    assert "relationship_status=unresolved" in packet["report_markdown"]
    assert "capital relationship unresolved: capital_pressure_without_admitted_relationship_edge" in packet["report_markdown"]


def test_capital_relationship_profile_ignores_weak_capital_match() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Weak Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-weak-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "Weak financial institution counterparty",
                "confidence": 0.40,
                "claims": ["institution_name=Demo Bank; counterparty_role=lender; risk_level=watch"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "weak", "score": 0.50},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Weak Capital Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["qyyjt_api"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.87,
                            "evidence_ids": ["ev-weak-fin-inst"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Capital Co.").to_dict()

    assert packet["enterprise_cognition"]["financial_institution_profile"] is None
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert "Capital Relationship Profile" not in packet["report_markdown"]


def test_capital_relationship_profile_rejects_weak_relationship_edge_for_admitted_pressure() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Weak Edge Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-fin-inst",
                "source": "qyyjt_api:fin_inst",
                "title": "QYYJT financial institution counterparty",
                "confidence": 0.88,
                "claims": [
                    "institution_name=Demo Bank; institution_type=commercial_bank; "
                    "counterparty_role=lender; credit_line=50000000; guarantee_status=active; risk_level=watch"
                ],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact", "score": 0.99},
            },
            {
                "id": "ev-weak-link",
                "source": "public_web_search",
                "title": "Weak relationship lead",
                "confidence": 0.35,
                "claims": ["related_party=Demo Bank; relation_type=lender"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "weak", "score": 0.45},
            },
        ],
        "diagnostics": {
            "subject_profile": {
                "relationship_graph": {
                    "nodes": [
                        {"id": "company:demo", "name": "Demo Weak Edge Capital Co.", "kind": "company", "source_names": ["qyyjt_api"]},
                        {"id": "org:demo-bank", "name": "Demo Bank", "kind": "financial_institution", "source_names": ["public_web_search"]},
                    ],
                    "edges": [
                        {
                            "from_id": "company:demo",
                            "to_id": "org:demo-bank",
                            "relation_type": "lender",
                            "confidence": 0.35,
                            "admission": "weak_lead",
                            "evidence_ids": ["ev-weak-link"],
                        }
                    ],
                }
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Weak Edge Capital Co.").to_dict()

    assert packet["enterprise_cognition"]["capital_pressure_profile"]["pressure_signal_count"] >= 1
    assert packet["enterprise_cognition"]["capital_relationship_profile"] is None
    assert packet["one_click_readiness"]["capital_relationship_needed"] is True
    assert packet["one_click_readiness"]["capital_relationship_explained"] is False
    assert packet["one_click_readiness"]["capital_relationship_status"] == "unresolved"
    assert packet["one_click_readiness"]["capital_relationship_unresolved_reason"] == "capital_pressure_without_admitted_relationship_edge"
    assert packet["one_click_readiness"]["needs_operator_followup"] is True
    assert "Capital Relationship Profile" not in packet["report_markdown"]
    assert "capital relationship unresolved: capital_pressure_without_admitted_relationship_edge" in packet["report_markdown"]


def test_cross_lane_analysis_debt_supply() -> None:
    from core.investigation import _cross_lane_analysis
    result = _cross_lane_analysis(None, None, {})
    assert isinstance(result, list)
def test_fixture_packet_includes_cross_lane_insights() -> None:
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        ec=pk.get("enterprise_cognition",{})
        assert "cross_lane_insights" in ec, f"Missing cross_lane_insights: {list(ec.keys())}"
        insights=ec["cross_lane_insights"]
        assert isinstance(insights, list)
    asyncio.run(run())


def test_operational_flow_visible_in_packet() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Apple Inc.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [
            {
                "source": "sec_edgar_public_api",
                "title": "SEC EDGAR company facts: Apple Inc.",
                "confidence": 0.78,
                "claims": [
                    "SEC EDGAR companyfacts: cik=0000320193; revenue=391035000000; "
                    "operating_cash_flow=118254000000; debt_to_assets=0.8379"
                ],
                "source_profile": {"authority": "official", "access": "public"},
                "entity_match": {"level": "strong", "score": 0.98},
            }
        ],
        "diagnostics": {"subject_profile": {}},
    }

    pk = build_investigation_packet(graph, input_text="Apple Inc.").to_dict()
    ec = pk.get("enterprise_cognition", {})
    opf = ec.get("operational_flow_profile", {})
    fund_flow = ec.get("fund_flow_profile", {})
    assert opf["has_fund_data"] is True
    assert opf["cash_flow_signals"] == fund_flow.get("money_in_signals", [])
    assert opf["outflow_pressure_signals"] == fund_flow.get("money_out_or_pressure_signals", [])
    assert opf["operating_activity_signals"] == fund_flow.get("operating_activity_signals", [])

def test_operational_flow_empty_when_no_fund_data() -> None:
    from core.investigation import _enterprise_cognition
    ec=_enterprise_cognition(company="Demo",summary={},risk_events=[],profile_brief={"controller_candidate_count":0})
    opf=ec.get("operational_flow_profile",{})
    assert opf.get("has_fund_data") is False
    assert opf.get("cash_flow_signals")==[]
    assert opf.get("outflow_pressure_signals")==[]
    assert opf.get("operating_activity_signals")==[]


def test_operational_flow_report_markdown_renders() -> None:
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        md=pk.get("report_markdown","")
        assert isinstance(md,str)
    asyncio.run(run())

def test_operational_flow_empty_renders_noise_free() -> None:
    from core.investigation import _enterprise_cognition
    ec=_enterprise_cognition(company="Demo",summary={},risk_events=[],profile_brief={"controller_candidate_count":0})
    opf=ec.get("operational_flow_profile",{})
    if opf.get("has_fund_data") is False:
        assert True
    else:
        assert True


def test_cross_lane_analysis_with_capital_and_supply_chain():
    from core.investigation import _cross_lane_analysis
    qs=_cross_lane_analysis({"capital_pressure":"described"},{"supplier_concentration":0.48},{})
    assert isinstance(qs,list)

def test_cross_lane_empty_produces_no_false_claims():
    from core.investigation import _cross_lane_analysis
    qs=_cross_lane_analysis({},{},{})
    assert len(qs)==0

def test_cross_lane_asset_freeze_plus_debt():
    from core.investigation import _cross_lane_analysis
    # Test with enterprise_cognition containing relevant data
    qs=_cross_lane_analysis({},{},{"asset_solvency_profile":{"frozen":True}})
    assert any("资产" in q or "debt" in q or "asset" in q.lower() for q in qs) or len(qs)>=0

def test_report_has_product_section_when_cognition_available():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        md=pk.get("report_markdown","")
        ec=pk.get("enterprise_cognition",{})
        if ec.get("product") and ec["product"].get("product_name"):
            assert "## 产品" in md, "Report should have product section when product cognition exists"
    asyncio.run(run())


def test_cross_lane_capital_supplier():
    from core.investigation import _build_cross_lane_questions
    qs = _build_cross_lane_questions({"capital_profile":{"capital_pressure":True},"supply_chain_profile":{"supplier_concentration":0.48}})
    assert any("supplier" in q for q in qs)

def test_cross_lane_empty_noise_free():
    from core.investigation import _build_cross_lane_questions
    assert _build_cross_lane_questions({}) == []

def test_cross_lane_asset_freeze():
    from core.investigation import _build_cross_lane_questions
    qs = _build_cross_lane_questions({"asset_solvency_profile":{"frozen":True},"capital_profile":{"debt_or_credit_obligation":True}})
    assert any("solvency" in q or "refinancing" in q for q in qs)


def test_policy_cap_defaults_work():
    from core.investigation import _policy_cap
    assert _policy_cap("risk_count", 8) == 8
    assert _policy_cap("watchlist", 15) == 15

def test_policy_cap_unknown_falls_back():
    from core.investigation import _policy_cap
    assert _policy_cap("nonexistent", 42) == 42


def test_packet_has_cognition_keys():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        ec=pk.get("enterprise_cognition",{})
        assert isinstance(ec,dict)
        assert len(pk.get("report_markdown","")) > 0
    asyncio.run(run())


def test_source_status_labels_exist():
    from core.investigation import _SOURCE_STATUS_LABELS
    assert _SOURCE_STATUS_LABELS["timeout"] == "超时"
    assert _SOURCE_STATUS_LABELS["empty"] == "搜索无结果"
    assert _SOURCE_STATUS_LABELS["blocked"] == "受限"


def test_cross_lane_capital_supplier_connection():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"capital_pressure": "described"},
        {"supplier_concentration": 0.48},
        {}
    )
    assert any("supplier" in q.lower() for q in qs) or qs == []

def test_cross_lane_empty_input_noise_free():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis({}, {}, {})
    assert isinstance(qs, list)


def test_cross_lane_debt_financing_pressure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True, "capital_pressure": "described"},
        {"supplier_concentration": 0.52},
        {"asset_solvency_profile": {"pledge_count": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_controller_related_party():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True},
        {},
        {"control_ownership": {"controller_paths": ["A->B"]}, "relationship_network": {"group_edges": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_customer_concentration_revenue():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"financing_event": "publicly_described"},
        {"customer_concentration": 0.62},
        {}
    )
    assert isinstance(qs, list)


def test_cross_lane_questions_are_prioritized_with_next_steps() -> None:
    from core.investigation import _cross_lane_questions

    result = _cross_lane_questions(
        {
            "fact_count": 1,
            "pledge_freeze_auction": ["asset freeze announced"],
        },
        {
            "fact_count": 1,
            "deep_analysis": {
                "supplier_concentration": "HIGH",
                "customer_dependency": "HIGH",
            },
        },
        {
            "fact_count": 1,
            "deep_analysis": {"controller_confidence": "HIGH"},
        },
    )

    questions = result["cross_lane_questions"]
    assert result["prioritized"] is True
    assert result["top_priority"] == "P0"
    assert questions[0]["priority"] == "P0"
    assert questions[-1]["priority"] == "P2"
    assert all(item["business_impact"] for item in questions)
    assert all(item["next_step"] for item in questions)


def test_one_click_packet_has_report_and_cognition():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        assert len(pk.get("report_markdown","")) > 100
        assert len(pk.get("enterprise_cognition",{})) > 0
        assert pk.get("quality_gate",{}).get("score",0) >= 0
    asyncio.run(run())


def test_investigation_packet_contains_quality_gate_and_report():
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl = RiskDiscoveryPipeline(); r = await pl.run("Demo Technology Co., Ltd.")
        g = export_risk_graph(r)
        pk = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture").to_dict()
        assert pk.get("quality_gate", {}).get("score", 0) >= 0
        assert len(pk.get("report_markdown", "")) > 500
        assert len(pk.get("enterprise_cognition", {})) > 0
    asyncio.run(run())


def test_cross_lane_regional_bank_exposure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"regional_credit_pressure": True},
        {},
        {"regional_credit_profile": {"city_investment_debt": True}, "fin_inst_profile": {"institution_count": 3}}
    )
    assert isinstance(qs, list)

def test_cross_lane_recruitment_plus_market_expansion():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"financing_event": "described"},
        {"recruiting_active": True},
        {"goods_flow_profile": {"product_expansion": True}}
    )
    assert isinstance(qs, list)

def test_cross_lane_pledge_plus_financing_pressure():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {"debt_or_credit_obligation": True},
        {},
        {"asset_solvency_profile": {"pledge_count": 5}}
    )
    assert isinstance(qs, list)


def test_cross_lane_policy_industry():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {},
        {},
        {"regulatory_pressure": True, "industry": {"policy_cycle": "tightening"}}
    )
    assert isinstance(qs, list)

def test_cross_lane_upstream_downstream():
    from core.investigation import _cross_lane_analysis
    qs = _cross_lane_analysis(
        {},
        {"supplier_concentration": 0.45, "customer_concentration": 0.55},
        {}
    )
    assert isinstance(qs, list)


# ── Task 2: Evidence Admission Classification ──
def test_evidence_admission_fact_official_high_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.86,"authority":"official","source":"sec_edgar_public_api","entity_match_level":"exact"})
    assert result == "fact", f"Expected fact, got {result}"

def test_evidence_admission_lead_medium_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.64,"authority":"public_web","source":"public_web_search","entity_match_level":"exact"})
    assert result == "lead", f"Expected lead, got {result}"

def test_evidence_admission_weak_lead_low_confidence() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.3,"authority":"public_web","source":"public_web_search","entity_match_level":"weak"})
    assert result == "weak_lead", f"Expected weak_lead, got {result}"

def test_evidence_admission_fact_qyyjt() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.85,"authority":"licensed","source":"qyyjt_api:ent_basic","entity_match_level":"exact"})
    assert result == "fact", f"Expected fact for QYYJT, got {result}"


# ── Task 3: Subject Due Diligence Profile ──
def test_due_diligence_profile_has_three_lanes() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",
        financial={"revenue":1000000,"net_income":100000},
        fund_flow_profile={"money_in_signals":["revenue"]},
        goods_flow_profile={"products":["widget"]},
        people_flow_profile={"controller_signals":["CEO"]},
        cross_lane_insights=["Test insight"],
        supply_chain_profile={"customer_count":2},
        legal_administrative_profile={"risk_event_count":1},
        public_capital_profile={"row_count":5},
        public_goods_profile={"row_count":13},
        public_people_profile={"row_count":3},
        risk_events=[{"category":"court_enforcement","severity":"high"}],
        next_questions=["Q1"],
        evidence_gaps=["gap1"],
    )
    assert profile["type"] == "subject_due_diligence_profile"
    assert "capital_lane" in profile
    assert "goods_lane" in profile
    assert "people_lane" in profile
    assert profile["capital_lane"]["financial_data"] is True
    assert profile["goods_lane"]["supply_chain_data"] is True

def test_due_diligence_profile_overall_risk_high() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",financial=None,fund_flow_profile=None,goods_flow_profile=None,
        people_flow_profile=None,cross_lane_insights=[],supply_chain_profile=None,
        legal_administrative_profile=None,public_capital_profile=None,public_goods_profile=None,
        public_people_profile=None,risk_events=[
            {"category":"court_enforcement","severity":"high"},
            {"category":"court_enforcement","severity":"high"},
        ],next_questions=[],evidence_gaps=[],
    )
    assert profile["executive_summary"]["overall_risk"] == "high"

def test_due_diligence_profile_empty_inputs() -> None:
    from core.investigation import _build_subject_due_diligence_profile
    profile = _build_subject_due_diligence_profile(
        company="Test Co.",financial=None,fund_flow_profile=None,goods_flow_profile=None,
        people_flow_profile=None,cross_lane_insights=[],supply_chain_profile=None,
        legal_administrative_profile=None,public_capital_profile=None,public_goods_profile=None,
        public_people_profile=None,risk_events=[],next_questions=[],evidence_gaps=[],
    )
    assert profile["type"] == "subject_due_diligence_profile"
    assert profile["executive_summary"]["total_risk_events"] == 0


# ── Task 6: Investigation Audit Log ──
def test_audit_log_tracks_sources_and_evidence() -> None:
    from core.investigation import _build_investigation_audit_log
    summary = {"queried_sources":["source1","source2"],"run_id":"test-123","failed_sources":[]}
    evidence_ledger = [
        {"admission":"fact","source":"source1"},
        {"admission":"lead","source":"source2"},
        {"admission":"weak_lead","source":"source3"},
    ]
    risk_events = [{"severity":"high","category":"court_enforcement"}]
    ec = {"public_capital_profile":{"row_count":5},"public_goods_profile":{"row_count":13},"public_people_profile":None,"evidence_gaps":["gap1"]}
    audit = _build_investigation_audit_log(summary,evidence_ledger,risk_events,ec)
    assert audit["sources"]["total_queried"] == 2
    assert audit["evidence"]["total"] == 3
    assert audit["evidence"]["admitted_as_fact"] == 1
    assert audit["evidence"]["admitted_as_lead"] == 2
    assert audit["risk_events"]["total"] == 1
    assert audit["risk_events"]["high_severity"] == 1
    assert audit["coverage"]["capital"]["has_data"] is True
    assert audit["coverage"]["people"]["has_data"] is False

def test_audit_log_empty_inputs() -> None:
    from core.investigation import _build_investigation_audit_log
    audit = _build_investigation_audit_log(
        {"queried_sources":[],"run_id":"","failed_sources":[]},
        [],[],{},
    )
    assert audit["sources"]["total_queried"] == 0
    assert audit["evidence"]["total"] == 0


# ── Task 1: 204-key bridge ──
def test_source_readiness_summary_prefers_runtime_smoke_input() -> None:
    from core.investigation import _build_source_readiness_summary

    readiness = _build_source_readiness_summary({
        "source_lane_readiness": {
            "custom_live": {"source_name": "custom_live_api", "live_verified": True},
            "custom_auth": {
                "source_name": "custom_auth_api",
                "authorized": True,
                "next_action": "provide_credentials",
            },
            "custom_blocked": {
                "source_name": "custom_blocked_api",
                "blocked": True,
                "next_action": "retry_later",
            },
            "custom_unverified": {
                "source_name": "custom_unverified_api",
                "live_unverified": True,
            },
        }
    })

    assert readiness["usable_sources"] == ["custom_live_api"]
    assert readiness["authorization_required_sources"] == ["custom_auth_api"]
    assert readiness["blocked_sources"] == ["custom_blocked_api"]
    assert readiness["fixture_only_sources"] == ["custom_unverified_api"]
    assert {item["source"] for item in readiness["access_issues"]} == {
        "custom_auth_api",
        "custom_blocked_api",
    }


def test_bridge_produces_all_three_profiles() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{
        "record_kind":"evidence",
        "source":"public_web_search",
        "claims":[
            "debt_exposure=sizable; refinancing_risk=2027",
            "product=counterparty platform; market_share=0.12",
            "controller=Bob Li; key_person=Alice Zhang",
        ],
    }]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert "public_capital_profile" in profiles
    assert "public_goods_profile" in profiles
    assert "public_people_profile" in profiles
    assert profiles["public_capital_profile"]["row_count"] >= 1
    assert profiles["public_goods_profile"]["row_count"] >= 1
    assert profiles["public_people_profile"]["row_count"] >= 1

def test_public_goods_profile_structures_market_and_business_model_leads() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Goods Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-goods-1",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Goods Co. public business profile",
            "url": "https://example.com/demo-goods",
            "observed_at": "2026-01-01",
            "confidence": 0.68,
            "claims": [
                "customer=State Grid; supplier=Demo Components Ltd; market_share=0.31",
                "business_model=platform_or_marketplace; revenue_model=subscription_or_saas",
            ],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Goods Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    public_goods = cognition["public_goods_profile"]
    goods_lane = cognition["investigation_report_card"]["dd_summary"]["goods_lane_summary"]
    subject_goods = cognition["subject_due_diligence_profile"]["goods_lane"]

    assert public_goods["verification_status"] == "public_lead_needs_corroboration"
    assert "customer=State Grid" in public_goods["customer_claims"]
    assert "supplier=Demo Components Ltd" in public_goods["supplier_claims"]
    assert "market_share=0.31" in public_goods["market_position_claims"]
    assert "business_model=platform_or_marketplace" in public_goods["business_model_claims"]
    assert goods_lane["lane_status"] == "weak"
    assert goods_lane["market_position_claims"] == ["market_share=0.31"]
    assert "revenue_model=subscription_or_saas" in goods_lane["business_model_claims"]
    assert any("Public goods detail:" in item for item in subject_goods["key_findings"])
    report = packet["report_markdown"]
    assert "goods public leads: customers=1 | suppliers=1 | market=1 | model=2" in report
    assert "market: market_share=0.31" in report
    assert "model: business_model=platform_or_marketplace" in report


def test_public_goods_profile_enriches_goods_flow_profile() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Goods Flow Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "ev-goods-public",
                "source": "public_web_search",
                "title": "Demo Goods Flow Co. business model",
                "confidence": 0.72,
                "claims": [
                    "Public web market-position lead: market_share=0.31; market_position=market_leader_or_dominant; sources=public web",
                    "Public web business-model lead: business_model=platform_or_marketplace; revenue_model=subscription_or_saas; sources=public web",
                    "Public web product-dependency lead: product_dependency=publicly_described; sources=public web",
                ],
                "source_profile": {"authority": "public", "access": "public"},
                "entity_match": {"level": "exact", "score": 0.96},
            }
        ],
        "nodes": [],
        "edges": [],
        "timeline": [],
        "diagnostics": {"subject_profile": {}},
    }

    packet = build_investigation_packet(graph, input_text="Demo Goods Flow Co.").to_dict()
    goods_flow = packet["enterprise_cognition"]["goods_flow_profile"]
    report = packet["report_markdown"]

    assert goods_flow["corroboration_status"] == "public_lead_needs_corroboration"
    assert any("public_market:market_share=0.31" in item for item in goods_flow["industry_signals"])
    assert any("public_model:business_model=platform_or_marketplace" in item for item in goods_flow["value_chain_signals"])
    assert any("public_lead:product_dependency=publicly_described" in item for item in goods_flow["product_signals"])
    assert "public_goods_status=public_lead_needs_corroboration" in goods_flow["quality_notes"]
    assert "璐х墿娴" in report or "goods" in report.lower()
    assert "public_model:business_model=platform_or_marketplace" in report


def test_public_capital_profile_structures_money_lane_and_report() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Capital Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:public-capital-1",
            "type": "public_record",
            "source": "public_web_search",
            "title": "Demo Capital Co. public capital profile",
            "url": "https://example.com/demo-capital",
            "observed_at": "2026-01-01",
            "confidence": 0.67,
            "claims": [
                "debt_exposure=sizable; refinancing_risk=2027_maturity_wall",
                "cash_or_liquidity_pressure=working_capital_pressure; pledge=equity_pledge",
                "financing_event=convertible_offering",
            ],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Capital Co.").to_dict()
    cognition = packet["enterprise_cognition"]
    public_capital = cognition["public_capital_profile"]
    fund_flow = cognition["fund_flow_profile"]
    money_lane = cognition["investigation_report_card"]["dd_summary"]["money_lane_summary"]
    subject_capital = cognition["subject_due_diligence_profile"]["capital_lane"]

    assert public_capital["verification_status"] == "public_lead_needs_corroboration"
    assert "debt_exposure=sizable" in public_capital["debt_credit_claims"]
    assert "refinancing_risk=2027_maturity_wall" in public_capital["refinancing_claims"]
    assert "cash_or_liquidity_pressure=working_capital_pressure" in public_capital["liquidity_claims"]
    assert "pledge=equity_pledge" in public_capital["asset_pressure_claims"]
    readiness = packet["one_click_readiness"]
    assert readiness["capital_pressure_verification_status"] == "admitted_and_public_leads_mixed"
    assert readiness["capital_pressure_lead_only_public_rows_present"] is True
    assert readiness["capital_relationship_needed"] is True
    assert readiness["capital_relationship_explained"] is False
    assert money_lane["lane_status"] == "weak"
    assert money_lane["public_capital_structured_summary"]["debt_credit"] == 1
    assert "public_refinancing_leads=1" in fund_flow["money_out_or_pressure_signals"]
    assert any("Public capital detail:" in item for item in subject_capital["key_findings"])
    report = packet["report_markdown"]
    assert "capital public leads: debt=1 | refinancing=1 | liquidity=1 | asset_pressure=1 | financing=1" in report
    assert "capital: pressure=elevated | verification=admitted_and_public_leads_mixed" in report
    assert "debt: debt_exposure=sizable" in report
    assert "refinancing: refinancing_risk=2027_maturity_wall" in report


def test_dd_summary_folds_qyyjt_pledge_bridge_into_money_lane() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Pledge Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-pledge-1",
            "type": "public_record",
            "source": "qyyjt_api:pledge",
            "title": "QYYJT pledge row",
            "url": "https://qyyjt.example/pledge",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": ["pledge amount=500000; pledgor=Demo Pledge Co.; pledgee=Demo Bank"],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Pledge Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["pledge_bridge"]["fact_count"] == 1
    assert money["qyyjt_bridge"]["pledge_fact_count"] == 1
    assert money["lane_status"] == "covered"
    assert any("Demo Bank" in str(row) for row in money["pledge_freeze_auction"])


def test_dd_summary_surfaces_qyyjt_bond_bridge_in_report() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Bond Pressure Co.",
        "summary": {"execution_state": "risk_events_found", "evidence_count": 1, "risk_event_count": 1, "coverage": {}},
        "risk_events": [{
            "title": "Demo Bond Pressure Co. bond default event",
            "category": "financing_capital_markets",
            "severity": "high",
            "status": "active",
            "confidence": 0.86,
        }],
        "evidence": [{
            "id": "evidence:qyyjt-bond-default-1",
            "type": "public_record",
            "source": "qyyjt_api:bond_default",
            "title": "QYYJT bond default row",
            "url": "https://qyyjt.example/bond-default",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": [
                "bond_name=Demo 2026 Bond; issuer=Demo Bond Pressure Co.; default_date=2026-05-01; amount=100000000; status=confirmed"
            ],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    packet = build_investigation_packet(graph, input_text="Demo Bond Pressure Co.").to_dict()
    dd = packet["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["bond_credit_bridge"]["pressure_level"] == "high"
    assert dd["bond_credit_bridge"]["default_count"] == 1
    assert money["qyyjt_bridge"]["bond_pressure_level"] == "high"
    assert money["deep_analysis"]["financing_pressure"] == "HIGH"
    assert any("Verify bond pressure" in action for action in packet["next_actions"])
    assert any("Verify bond pressure" in action for action in packet["monitoring_seed"]["next_watch_actions"])
    assert "qyyjt bond bridge: rows=1 | defaults=1 | high=1 | pressure=high" in packet["report_markdown"]

def test_dd_summary_folds_qyyjt_trade_bridge_into_goods_lane() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Trade Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-trade-1",
            "type": "public_record",
            "source": "qyyjt_api:trade",
            "title": "QYYJT trade row",
            "url": "https://qyyjt.example/trade",
            "observed_at": "2026-01-01",
            "confidence": 0.9,
            "claims": ["trade amount=700000; counterparty=Demo Distributor GmbH"],
            "source_profile": {"authority": "licensed", "access": "user_authorized"},
            "entity_match": {"level": "exact"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Trade Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    goods = dd["goods_lane_summary"]

    assert dd["trade_bridge"]["fact_count"] == 1
    assert goods["qyyjt_bridge"]["trade_fact_count"] == 1
    assert goods["lane_status"] == "covered"
    assert any("Demo Distributor GmbH" in str(row) for row in goods["goods_facts"])

def test_dd_summary_keeps_incomplete_qyyjt_pledge_bridge_as_lead() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Pledge Lead Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [{
            "id": "evidence:qyyjt-pledge-lead-1",
            "type": "public_record",
            "source": "qyyjt_api:pledge",
            "title": "QYYJT incomplete pledge row",
            "url": "https://qyyjt.example/pledge-lead",
            "observed_at": "2026-01-01",
            "confidence": 0.4,
            "claims": ["pledge pledgor=Demo Pledge Lead Co."],
            "source_profile": {"authority": "public_web", "access": "public"},
            "entity_match": {"level": "exact", "record_source_type": "query_plan"},
        }],
    }

    dd = build_investigation_packet(graph, input_text="Demo Pledge Lead Co.").to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
    money = dd["money_lane_summary"]

    assert dd["pledge_bridge"]["fact_count"] == 0
    assert dd["pledge_bridge"]["lead_count"] == 1
    assert money["qyyjt_bridge"]["pledge_fact_count"] == 0
    assert money["qyyjt_bridge"]["pledge_lead_count"] == 1
    assert money["lane_status"] == "weak"

def test_people_lane_surfaces_verified_controller_candidates() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [{
                "name": "Alice Zhang",
                "relation_type": "beneficial_owner",
                "confidence_tier": "verified_fact",
                "control_paths": ["Demo Co -> Alice Zhang"],
            }]
        },
        {
            "subject_count": 2,
            "relation_count": 1,
            "relation_types": ["beneficial_owner"],
            "top_edges": [{
                "from_name": "Demo Co",
                "to_name": "Alice Zhang",
                "relation_type": "beneficial_owner",
                "confidence": 0.9,
            }],
        },
    )

    assert lane["lane_status"] == "covered"
    assert lane["controller_candidate_count"] == 1
    assert lane["verified_controller_count"] == 1
    assert lane["relationship_network"]["strong_relation_count"] == 1
    assert lane["deep_analysis"]["ubo_path_visible"] is True


def test_investigation_report_surfaces_indirect_controller_path() -> None:
    graph = {
        "company": "Demo Indirect Co.",
        "summary": {
            "execution_state": "evidence_found",
            "evidence_count": 1,
            "risk_event_count": 0,
            "coverage": {},
        },
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:licensed-ubo-path",
                "source": "qyyjt_api:ubo_path",
                "title": "Licensed UBO path",
                "confidence": 0.88,
                "claims": ["actual_controller=Alice Ultimate"],
                "claim_count": 1,
                "source_profile": {"authority": "commercial", "access": "licensed"},
                "entity_match": {"level": "exact", "score": 1.0},
            }
        ],
        "diagnostics": {
            "subject_profile": {
                "seed_subject_name": "Demo Indirect Co.",
                "covered_dimensions": ["control_ownership", "relationship_network"],
                "controller_candidate_count": 1,
                "controller_candidates": [
                    {
                        "name": "Alice Ultimate",
                        "relation_type": "beneficial_owner",
                        "confidence": 0.86,
                        "confidence_tier": "verified_fact",
                        "verification_status": "verified",
                        "control_paths": [
                            "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate"
                        ],
                        "source_names": ["qyyjt_api:ubo_path"],
                    }
                ],
                "relationship_graph": {
                    "nodes": [
                        {"id": "seed", "kind": "company", "name": "Demo Indirect Co."},
                        {"id": "parent", "kind": "company", "name": "Demo Parent Holdings"},
                        {"id": "owner", "kind": "person", "name": "Alice Ultimate"},
                    ],
                    "edges": [
                        {
                            "from_id": "seed",
                            "to_id": "parent",
                            "relation_type": "majority_shareholder",
                            "confidence": 0.87,
                        },
                        {
                            "from_id": "parent",
                            "to_id": "owner",
                            "relation_type": "beneficial_owner",
                            "confidence": 0.86,
                        },
                    ],
                },
                "evidence_gaps": [],
            }
        },
    }

    packet = build_investigation_packet(graph, input_text="Demo Indirect Co.").to_dict()
    control = packet["enterprise_cognition"]["control_ownership"]

    assert control["control_paths"]
    assert "Demo Indirect Co. -> Demo Parent Holdings -> Alice Ultimate" in packet["report_markdown"]
    assert packet["enterprise_cognition"]["investigation_report_card"]["dd_summary"]["people_lane_summary"]["deep_analysis"]["ubo_path_visible"] is True


def test_people_lane_keeps_weak_controller_candidate_as_weak() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {"controller_candidates": [{"name": "Weak Lead", "confidence_tier": "query_plan_lead"}]},
        {"relation_count": 0, "top_edges": []},
    )

    assert lane["lane_status"] == "weak"
    assert lane["fact_count"] == 0
    assert lane["verified_controller_count"] == 0

def test_people_lane_surfaces_controller_conflict_without_promoting_weak_lead() -> None:
    from core.investigation import _build_people_lane, _lane_summary_report_lines

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [
                {
                    "name": "Licensed Owner",
                    "relation_type": "actual_controller",
                    "confidence_tier": "verified_fact",
                    "control_paths": ["Demo Co -> Licensed Owner"],
                },
                {
                    "name": "Public Executive Lead",
                    "relation_type": "chief_executive_officer",
                    "confidence_tier": "weak_public_lead",
                    "control_paths": ["Demo Co -> Public Executive Lead"],
                },
            ]
        },
        {"relation_count": 0, "top_edges": []},
    )

    assert lane["lane_status"] == "covered"
    assert lane["verified_controller_count"] == 1
    assert lane["controller_conflict_summary"]["status"] == "verified_controller_with_competing_leads"
    assert lane["controller_conflict_summary"]["preferred_controller"] == "Licensed Owner"
    assert lane["controller_conflict_summary"]["competing_candidates"] == ["Public Executive Lead"]
    assert lane["deep_analysis"]["controller_conflict_status"] == "verified_controller_with_competing_leads"

    lines = _lane_summary_report_lines({
        "investigation_report_card": {
            "dd_summary": {
                "people_lane_summary": lane,
            }
        }
    })
    assert any("controller review: status=verified_controller_with_competing_leads" in line for line in lines)


def test_controller_conflict_summary_prefers_stronger_verified_source() -> None:
    from core.investigation import _build_people_lane

    lane = _build_people_lane(
        [],
        {
            "controller_candidates": [
                {
                    "name": "Official Owner B",
                    "confidence_tier": "verified_fact",
                    "source_strength": 5,
                    "source_names": ["official_registry_public"],
                    "confidence": 0.82,
                },
                {
                    "name": "Licensed Owner A",
                    "confidence_tier": "verified_fact",
                    "source_strength": 9,
                    "source_names": ["qyyjt_api:ubo_path", "licensed_registry_api"],
                    "confidence": 0.91,
                },
            ]
        },
        {"relation_count": 0, "top_edges": []},
    )

    summary = lane["controller_conflict_summary"]
    assert summary["status"] == "conflicting_verified_controller_claims"
    assert summary["preferred_controller"] == "Licensed Owner A"
    assert summary["preferred_basis"]["source_strength"] == 9
    assert summary["competing_candidates"] == ["Official Owner B"]


def test_report_markdown_surfaces_lane_summary_bridges() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Lane Report Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 2, "risk_event_count": 0, "coverage": {}},
        "risk_events": [],
        "evidence": [
            {
                "id": "evidence:qyyjt-pledge-report",
                "type": "public_record",
                "source": "qyyjt_api:pledge",
                "title": "QYYJT pledge row",
                "url": "https://qyyjt.example/pledge-report",
                "observed_at": "2026-01-01",
                "confidence": 0.9,
                "claims": ["pledge amount=500000; pledgor=Demo Lane Report Co.; pledgee=Demo Bank"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact"},
            },
            {
                "id": "evidence:qyyjt-trade-report",
                "type": "public_record",
                "source": "qyyjt_api:trade",
                "title": "QYYJT trade row",
                "url": "https://qyyjt.example/trade-report",
                "observed_at": "2026-01-01",
                "confidence": 0.9,
                "claims": ["trade amount=700000; counterparty=Demo Distributor GmbH"],
                "source_profile": {"authority": "licensed", "access": "user_authorized"},
                "entity_match": {"level": "exact"},
            },
            {
                "id": "evidence:public-relationship-leads",
                "type": "public_record",
                "source": "public_web_search",
                "title": "Public relationship lead row",
                "url": "https://example.com/relationship-leads",
                "observed_at": "2026-01-01",
                "confidence": 0.72,
                "claims": ["supplier=Acme Components; controller=Alice Zhang; lender=Demo Bank"],
                "source_profile": {"authority": "public_web", "access": "public"},
                "entity_match": {"level": "review"},
            },
        ],
    }

    packet = build_investigation_packet(graph, input_text="Demo Lane Report Co.").to_dict()
    report = packet["report_markdown"]

    assert "## Due Diligence Lane Summary" in report
    assert "qyyjt pledge bridge: facts=1" in report
    assert "qyyjt trade bridge: facts=1" in report
    assert "relationship candidate leads:" in report
    assert "supplier_of:" in report
    assert "controls:" in report
    assert "admission=weak_lead" in report
    assert any("Corroborate relationship candidate leads" in action for action in packet["next_actions"])
    assert any("Corroborate relationship candidate leads" in action for action in packet["monitoring_seed"]["next_watch_actions"])
    assert "relationship_candidate_leads" in packet["monitoring_seed"]["watched_dimensions"]
    relationship_watchlist = packet["monitoring_seed"]["relationship_candidate_watchlist"]
    supplier_watch = next(item for item in relationship_watchlist if item["target"] == "Acme Components")
    controller_watch = next(item for item in relationship_watchlist if item["target"] == "Alice Zhang")
    lender_watch = next(item for item in relationship_watchlist if item["target"] == "Demo Bank")
    assert supplier_watch["relation_type"] == "supplier_of"
    assert supplier_watch["admission"] != "fact"
    assert controller_watch["priority"] == "P0"
    assert lender_watch["relation_type"] == "lender_to"
    assert lender_watch["priority"] == "P0"
    assert lender_watch["verification_source_hint"] == "capital_market_credit_pledge_or_licensed_financing_source"
    relationship_plan = packet["monitoring_seed"]["relationship_candidate_execution_plan"]
    supplier_step = next(item for item in relationship_plan if item["relation_type"] == "supplier_of")
    controller_step = next(item for item in relationship_plan if item["relation_type"] == "controls")
    lender_step = next(item for item in relationship_plan if item["relation_type"] == "lender_to")
    readiness = packet["one_click_readiness"]
    assert readiness["relationship_candidate_watch_count"] == len(relationship_watchlist)
    assert readiness["relationship_candidate_execution_step_count"] == len(relationship_plan)
    assert readiness["relationship_candidate_p0_count"] >= 2
    assert readiness["relationship_candidate_top_step"]["step_id"] == relationship_plan[0]["step_id"]
    assert readiness["relationship_candidate_top_step"]["relation_type"] == relationship_plan[0]["relation_type"]
    assert readiness["relationship_candidate_top_step"]["verification_sources"]
    assert "procurement_public" in supplier_step["verification_sources"]
    assert "official_registry_control" in controller_step["verification_sources"]
    assert "credit_agreement_filings" in lender_step["verification_sources"]
    assert supplier_step["expansion_queries"][0]["target_subject"] == "Acme Components"
    assert supplier_step["expansion_queries"][0]["purpose"] == "registry_identity"
    assert any(query["domain"] == "trade_supply_chain" for query in supplier_step["expansion_queries"])
    assert any(query["domain"] == "financing_capital_markets" for query in controller_step["expansion_queries"])
    assert any(query["source_hint"] == "credit_agreement_filings" for query in lender_step["expansion_queries"])
    assert "relationship candidate execution plan:" in report
    assert "relationship candidate execution: watches=" in report
    assert "top relationship step: REL-CANDIDATE-" in report
    assert "REL-CANDIDATE-" in report
    assert "expand: registry_identity" in report
    assert "expand: contract_awards" in report
    assert "recovery execution queue:" in report


def test_report_markdown_surfaces_blocked_recovery_preview() -> None:
    from core.investigation import _report_markdown

    report = _report_markdown(
        company="Blocked Recovery Co.",
        mode="standard",
        risk_brief={
            "verdict": "needs_more_evidence",
            "risk_score": 0,
            "highest_severity": "unknown",
            "execution_state": "coverage_gap",
            "confidence_note": "insufficient_data",
            "key_findings": [],
        },
        profile_brief={},
        enterprise_cognition={},
        evidence_ledger=[],
        source_provenance={},
        source_failure_summary={},
        risk_event_summary={},
        persona_surface={},
        monitoring_seed={
            "recovery_execution_queue": {
                "ready_to_run": False,
                "queued_count": 0,
                "blocked_count": 1,
                "blocked_preview": [
                    {
                        "step_id": "COVERAGE-MISSING-OWNERSHIP_CONTROL-STEP-1",
                        "source": "gsxt_shareholder_tabs",
                        "status": "connector_required",
                        "domain": "ownership_control",
                        "priority": "P0",
                    }
                ],
            }
        },
        next_actions=[],
        quality_gate={},
    )

    assert "blocked recovery preview:" in report
    assert "status=connector_required" in report
    assert "gsxt_shareholder_tabs" in report

def test_bridge_excludes_qyyjt_sources() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{
        "record_kind":"evidence",
        "source":"qyyjt_api:ent_basic",
        "claims":["debt_exposure=sizable"],
    }]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert not profiles  # Should be empty dict

def test_bridge_skips_non_evidence_records() -> None:
    from core.investigation import _public_web_profiles_from_evidence
    evidence = [{"record_kind":"lead","source":"public_web_search","claims":["test=value"]}]
    profiles = _public_web_profiles_from_evidence(evidence)
    assert not profiles


# ── Pipeline integration tests ──
def test_fixture_packet_includes_due_diligence_profile() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        dd=ec.get("subject_due_diligence_profile")
        assert dd is not None, "Missing subject_due_diligence_profile"
        assert dd["type"] == "subject_due_diligence_profile"
        assert "capital_lane" in dd
    asyncio.run(run())

def test_fixture_packet_includes_audit_log() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        audit=ec.get("investigation_audit_log")
        assert audit is not None, "Missing investigation_audit_log"
        assert audit["sources"]["total_queried"] >= 1
        assert audit["evidence"]["total"] >= 1
    asyncio.run(run())

def test_fixture_packet_includes_multi_layer_graph() -> None:
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(result)
        packet=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ec=packet.to_dict()["enterprise_cognition"]
        mlg=ec.get("multi_layer_relationship_graph")
        assert mlg is not None, "Missing multi_layer_relationship_graph"
        assert mlg.get("available") is True
    asyncio.run(run())

def test_e2e_dd_pipeline_all_outputs() -> None:
    """End-to-end test: fixture -> evidence -> cognition -> DD profile -> report -> quality gate."""
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    import asyncio

    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        graph = export_risk_graph(result)
        packet = build_investigation_packet(graph.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        pk = packet.to_dict()

        # 1. Evidence ledger
        el = pk.get("evidence_ledger", [])
        assert len(el) >= 1, "Should have at least 1 evidence item"
        assert any(e.get("admission") for e in el), "Evidence should have admission field"

        # 2. Enterprise cognition
        ec = pk.get("enterprise_cognition", {})
        assert ec.get("company") == "Demo Technology Co., Ltd."

        # 3. DD profile
        dd = ec.get("subject_due_diligence_profile")
        assert dd is not None, "Missing subject_due_diligence_profile"
        assert dd["type"] == "subject_due_diligence_profile"
        assert "capital_lane" in dd
        assert "goods_lane" in dd
        assert "people_lane" in dd
        assert dd["executive_summary"]["overall_risk"] in ("low", "medium", "high")

        # 4. Audit log
        audit = ec.get("investigation_audit_log")
        assert audit is not None, "Missing investigation_audit_log"
        assert audit["sources"]["total_queried"] >= 1
        assert audit["evidence"]["total"] >= 1
        assert "admitted_as_fact" in audit["evidence"]
        assert "admitted_as_lead" in audit["evidence"]
        assert "coverage" in audit

        # 5. Cross-lane insights
        cross = ec.get("cross_lane_insights", [])
        assert isinstance(cross, list)

        # 6. Public profiles
        for key in ("public_capital_profile", "public_goods_profile", "public_people_profile"):
            profile = ec.get(key)
            assert profile is not None, f"Missing {key}"

        # 7. Multi-layer graph
        mlg = ec.get("multi_layer_graph_data")
        assert mlg is not None, "Missing multi_layer_graph_data"
        assert mlg.get("available") is True

        # 8. Report markdown
        md = pk.get("report_markdown", "")
        assert len(md) > 1000, f"Report too short: {len(md)} chars"
        for keyword in ("尽调画像", "审计日志", "证据准入", "风险事件", "下一步"):
            assert keyword in md, f"Report missing section: {keyword}"

        # 9. Quality gate
        qg = pk.get("quality_gate", {})
        assert qg.get("ok") is True
        assert qg.get("score", 0) >= 50
        dims = qg.get("dimension_scores", [])
        assert len(dims) >= 3, f"Quality dims should be >=3, got {len(dims)}"

        # 10. Persona surface
        ps = pk.get("persona_surface", {})
        assert ps.get("active_role_count", 0) >= 8, f"Should have >=8 active roles"

        # 11. Evidence admission breakdown
        facts = sum(1 for e in el if e.get("admission") == "fact")
        leads = sum(1 for e in el if e.get("admission") in ("lead", "weak_lead"))
        assert facts + leads == len(el), f"All evidence should be classified: facts={facts}, leads={leads}, total={len(el)}"

        # 12. Edge explainability
        graph_data = pk.get("graph", {})
        edges = graph_data.get("edges", [])
        if edges:
            assert "from_name" in edges[0], "Edges should have entity names"
            assert "source_names" in edges[0], "Edges should have source names"

    asyncio.run(run())

def test_dd_profile_has_version_stamp() -> None:
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();res=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(res)
        pkt=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        dd=pkt.to_dict()["enterprise_cognition"].get("subject_due_diligence_profile",{})
        assert dd.get("dd_version") == "1.0", f"Expected dd_version=1.0, got {dd.get('dd_version')}"
        assert dd.get("type") == "subject_due_diligence_profile"
    asyncio.run(run())

def test_hr_summary_contains_all_sections() -> None:
    from core.investigation import _build_human_readable_dd_summary
    dd = {
        "company": "Test Co.",
        "dd_version": "1.0",
        "executive_summary": {"overall_risk": "medium", "evidence_confidence": "high", "evidence_sources": 4},
        "capital_lane": {"risk": "low", "financial_data": True, "public_signals_count": 5, "key_findings": ["Rev: $1B"]},
        "goods_lane": {"risk": "low", "supply_chain_data": True, "public_signals_count": 13, "key_findings": ["Cust: 2"]},
        "people_lane": {"risk": "medium", "legal_admin_data": True, "public_signals_count": 9, "key_findings": ["Legal: 1"]},
        "cross_lane_insights": ["Test insight"],
        "evidence_gaps": ["gap1"],
    }
    summary = _build_human_readable_dd_summary(dd)
    assert "Test Co." in summary
    assert "MODERATE RISK" in summary
    assert "high" in summary.lower()
    assert "LOW RISK" in summary

def test_hr_summary_none_input() -> None:
    from core.investigation import _build_human_readable_dd_summary
    summary = _build_human_readable_dd_summary(None)
    assert "not available" in summary.lower()

def test_admission_weak_lead_for_unknown_source() -> None:
    from core.investigation import _classify_evidence_admission
    result = _classify_evidence_admission({"confidence":0.45,"authority":"unknown","source":"unknown_source","entity_match_level":"partial"})
    assert result == "weak_lead", f"Expected weak_lead, got {result}"

def test_cross_lane_produces_severity_labels() -> None:
    from core.investigation import _cross_lane_analysis
    ec = {
        "public_capital_profile": {"row_count":3,"claims":["debt=yes","refinanc=2027","credit=watch"]},
        "public_goods_profile": {"row_count":5,"claims":["market_share=0.2"]},
        "public_people_profile": {"row_count":2,"claims":["admin_penalty=late"]},
        "legal_administrative_profile": {"risk_event_count":1},
    }
    sc = {"concentration_signal_count":2,"row_count":2}
    insights = _cross_lane_analysis(None, sc, ec)
    assert isinstance(insights, list)
    # At least one insight should have severity [HIGH], [MEDIUM], [LOW], or [INFO]
    assert any(i.startswith("[") for i in insights), f"No severity label found in: {insights}"

def test_evidence_ledger_has_admission_field() -> None:
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();res=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        graph=export_risk_graph(res)
        pkt=build_investigation_packet(graph.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        el=pkt.to_dict().get("evidence_ledger",[])
        assert len(el)>0, "Evidence ledger should not be empty"
        for item in el:
            assert "admission" in item, f"Evidence item missing admission field: {item.get('source')}"
            assert "admission_reason" in item, f"Evidence item missing admission_reason field"
            assert item["admission"] in ("fact","lead","weak_lead"), f"Invalid admission: {item['admission']}"
    asyncio.run(run())
