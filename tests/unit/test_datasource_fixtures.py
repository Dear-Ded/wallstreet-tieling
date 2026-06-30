#!/usr/bin/env python3
"""Tests for datasource fixture packs used by connector authors."""
from __future__ import annotations

import asyncio

from core.datasource_fixtures import build_datasource_fixture_pack
from core.record_quality import audit_standardized_records
from core.risk_discovery_pipeline import RiskDiscoveryPipeline


def test_datasource_fixture_pack_covers_primary_connector_families() -> None:
    pack = build_datasource_fixture_pack("Demo Fixture Co., Ltd.")

    families = pack.by_source_family()
    assert set(families) == {
        "public_registry",
        "official_global",
        "public_web",
        "telegram_delivery",
        "licensed_api",
    }
    assert all(records for records in families.values())
    assert len(pack.all_records()) == 6
    assert {
        record["source_hint"]
        for record in pack.all_records()
    } >= {
        "registry_sources",
        "gleif_lei_public_api",
        "sec_edgar_public_api",
        "public_account_sources",
        "telegram_bot_public_service",
        "registry_and_commercial_sources",
    }


def test_datasource_fixture_pack_passes_record_quality_gate() -> None:
    pack = build_datasource_fixture_pack("Demo Quality Co., Ltd.")

    report = audit_standardized_records(pack.all_records())

    assert report.ok is True
    assert report.record_count == 6
    assert not [finding for finding in report.findings if finding.severity == "error"]


def test_datasource_fixture_pack_feeds_risk_pipeline_and_subject_profile(tmp_path) -> None:
    company = "Demo Pipeline Fixture Co., Ltd."
    pack = build_datasource_fixture_pack(company)
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            company,
            records=pack.all_records(),
            store_path=tmp_path / "risk-events.jsonl",
        )
    )

    assert result.ok is True
    assert result.evidence_count == 6
    assert result.entity_count >= 5
    assert result.risk_event_count >= 1
    assert result.retrieval_summary["record_count"] == 6
    assert result.retrieval_summary["ingested_count"] == 6
    assert result.risk_event_summary["alert_count"] >= 1
    assert "person:bob_li" in result.subject_profile["subjects"]
    assert result.subject_profile["controller_candidates"]
