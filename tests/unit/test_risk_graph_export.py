#!/usr/bin/env python3
"""Tests for compact risk graph export."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture
from core.risk_graph_export import export_risk_graph


ROOT = Path(__file__).resolve().parent.parent.parent


def test_export_risk_graph_has_plugin_friendly_sections(tmp_path) -> None:
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            "Demo Graph Co., Ltd.",
            records=offline_enforcement_fixture("Demo Graph Co., Ltd."),
        )
    )

    payload = export_risk_graph(result).to_dict()

    assert payload["company"] == "Demo Graph Co., Ltd."
    assert payload["summary"]["entity_count"] >= 1
    assert payload["summary"]["execution_state"] == "risk_events_found"
    assert payload["summary"]["evidence_count"] == 1
    assert payload["summary"]["risk_event_count"] == 1
    assert payload["summary"]["highest_severity"] == "high"
    assert payload["summary"]["subject_profile"]["seed_subject_name"] == "Demo Graph Co., Ltd."
    assert payload["summary"]["subject_profile"]["subject_count"] >= 1
    assert "risk_events" in payload["summary"]["subject_profile"]["covered_dimensions"]
    assert payload["summary"]["coverage"]["attempted_domain_count"] == 1
    assert payload["summary"]["next_actions"]
    assert payload["nodes"][0]["kind"] == "company"
    assert payload["evidence"][0]["claim_count"] >= 1
    assert payload["evidence"][0]["omitted_claim_count"] == 0
    assert payload["risk_events"][0]["severity"] == "high"
    assert payload["risk_events"][0]["entity_names"] == ["Demo Graph Co., Ltd."]
    assert payload["risk_events"][0]["evidence_refs"][0]["source"] == "offline_court_fixture"
    assert any(edge["type"] == "has_risk_event" for edge in payload["edges"])
    assert any(item["kind"] == "risk_event" for item in payload["timeline"])
    assert payload["diagnostics"]["retrieval_summary"]["ingested_count"] == 1
    assert payload["diagnostics"]["source_routing"] == {}
    assert payload["diagnostics"]["context_capsule"]["summary"]
    assert "record_quality" in payload["diagnostics"]
    assert payload["diagnostics"]["monitoring_delta"]["new_event_count"] == 1


def test_export_risk_graph_trims_large_claim_sets(tmp_path) -> None:
    records = [
        {
            "source_name": "large_public_fixture",
            "source_type": "rest_api",
            "source_hint": "court_and_credit_sources",
            "entity": "Demo Large Graph Co., Ltd.",
            "title": "Demo Large Graph Co., Ltd. enforcement notice",
            "summary": "Public enforcement risk signal.",
            "confidence": 0.8,
            "evidence": [
                {"claim": f"claim {index} " + ("x" * 400)}
                for index in range(10)
            ],
        }
    ]
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=tmp_path / "events.jsonl").run(
            "Demo Large Graph Co., Ltd.",
            records=records,
        )
    )

    payload = export_risk_graph(result).to_dict()

    assert payload["evidence"][0]["claim_count"] == 11
    assert len(payload["evidence"][0]["claims"]) == 11
    assert payload["evidence"][0]["omitted_claim_count"] == 0
    assert all(len(claim) <= 260 for claim in payload["evidence"][0]["claims"])
    assert payload["diagnostics"]["context_capsule"]["compressed_chars"] < 2500


def test_risk_graph_cli_offline_fixture_is_executable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_graph.py"),
            "Demo Graph CLI Co., Ltd.",
            "--offline-fixture",
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

    assert payload["company"] == "Demo Graph CLI Co., Ltd."
    assert payload["summary"]["risk_event_count"] == 1
    assert payload["summary"]["alert_count"] == 1
    assert payload["risk_events"][0]["evidence_ids"]


def test_risk_graph_cli_fixture_pack_exports_multi_source_graph(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_graph.py"),
            "Demo Graph Fixture Co., Ltd.",
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

    assert payload["company"] == "Demo Graph Fixture Co., Ltd."
    assert payload["summary"]["evidence_count"] == 6
    assert payload["summary"]["risk_event_count"] >= 1
    assert payload["summary"]["subject_profile"]["controller_candidate_count"] >= 1
    capital_exposure = payload["summary"]["capital_exposure"]
    assert capital_exposure["type"] == "capital_exposure_summary"
    assert capital_exposure["pressure_level"] == "elevated"
    assert capital_exposure["capital_evidence_count"] >= 1
    assert capital_exposure["pressure_signal_count"] >= 1
    assert capital_exposure["inflow_signal_count"] >= 1
    assert capital_exposure["relationship_status"] == "needs_relationship_mapping"
    assert capital_exposure["evidence_ids"]
    assert capital_exposure["relationship_audit_queue_count"] >= 1
    assert capital_exposure["relationship_audit_top_step"]["priority"] == "P0"
    assert capital_exposure["relationship_audit_top_step"]["kind"] == "capital_relationship_mapping_required"
    assert capital_exposure["relationship_audit_top_step"]["done_condition"] == "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason"
    assert capital_exposure["verification_queue_count"] >= 2
    assert capital_exposure["verification_queue"][0]["priority"] == "P0"
    assert any(
        item["kind"] in {"risk_event_verification", "capital_evidence_review"}
        for item in capital_exposure["verification_queue"]
    )
    assert any(
        item["kind"] == "relationship_mapping_required"
        and item["priority"] == "P0"
        and item["done_condition"] == "at_least_one_admitted_capital_relationship_edge_or_explicit_no_relationship_reason"
        for item in capital_exposure["verification_queue"]
    )
    assert "lenders" in capital_exposure["next_action"]
    assert {
        item["source"]
        for item in payload["evidence"]
    } >= {
        "public_registry",
        "public_web_search",
        "fixture_telegram_public_service:demo_bot",
        "fixture_licensed_registry_api",
        "gleif_lei_public_api",
        "sec_edgar_public_api",
    }


def test_export_risk_graph_separates_current_alerts_from_monitoring_history(tmp_path) -> None:
    store_path = tmp_path / "events.jsonl"
    company = "Demo Historical Alert Co., Ltd."
    asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=store_path).run(
            company,
            records=offline_enforcement_fixture(company),
            store_path=store_path,
        )
    )
    result = asyncio.run(
        RiskDiscoveryPipeline(risk_event_store=store_path).run(
            company,
            records=[],
            store_path=store_path,
        )
    )

    payload = export_risk_graph(result).to_dict()

    assert payload["summary"]["risk_event_count"] == 0
    assert payload["summary"]["alert_count"] == 0
    assert payload["summary"]["monitoring_alert_count"] == 1
    assert payload["diagnostics"]["monitoring_delta"]["not_seen_in_current_scan_count"] == 1
