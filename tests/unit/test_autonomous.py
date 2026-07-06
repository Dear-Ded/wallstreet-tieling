"""Autonomous source adapters must be explicit-only by default."""

import os

import pytest


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate

    return UserAuthorizationGate("test")


def _require_live_autonomous() -> None:
    if os.getenv("WST_LIVE_AUTONOMOUS") != "1":
        pytest.skip("live autonomous-source smoke disabled; set WST_LIVE_AUTONOMOUS=1")


def test_enterprise_registry_blocks_until_authorized() -> None:
    from adapters.autonomous_sources import AutonomousEnterpriseRegistryLookup

    adapter = AutonomousEnterpriseRegistryLookup(_make_gate())

    assert adapter.query_credit_china("test")["error"] == "source_not_authorized"
    assert adapter.query_aiqicha("test")["error"] == "source_not_authorized"
    assert adapter.query_gsxt_with_ocr("test")["error"] == "source_not_authorized"
    assert adapter.query_execution_court("test")["error"] == "source_not_authorized"


def test_public_record_aggregator_blocks_until_authorized() -> None:
    from adapters.autonomous_sources import AutonomousPublicRecordAggregator

    adapter = AutonomousPublicRecordAggregator(_make_gate())

    assert adapter.query_public_records("Test Person")["error"] == "source_not_authorized"


def test_autonomous_authorization_can_be_revoked() -> None:
    from adapters.autonomous_sources import AutonomousEnterpriseRegistryLookup
    from adapters.autonomous_sources import AutonomousPublicRecordAggregator

    gate = _make_gate()
    registry = AutonomousEnterpriseRegistryLookup(gate)
    records = AutonomousPublicRecordAggregator(gate)

    registry.enable()
    records.enable()
    assert registry.is_available()
    assert records.is_available()

    gate.disable_source("autonomous_enterprise_registry")
    gate.disable_source("autonomous_public_records")
    assert not registry.is_available()
    assert not records.is_available()


def test_enterprise_registry_standardizes_public_registry_leads() -> None:
    from adapters.autonomous_sources import AutonomousEnterpriseRegistryLookup

    adapter = AutonomousEnterpriseRegistryLookup(_make_gate())
    result = adapter.standardize_result(
        "Demo Holdings",
        {
            "query_subject_hash": "abc123",
            "source": "creditchina.gov.cn",
            "access_method": "standard_http_get",
            "data_boundary": "fully_public",
            "fields": {
                "penalty_records_found": 1,
                "credit_items_found": 3,
                "page": 1,
            },
            "field_count": 3,
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "autonomous_enterprise_public_registry_lead"
    assert record["source_hint"] == "autonomous_enterprise_registry"
    assert record["entity"] == "Demo Holdings"
    assert record["entity_match"]["level"] == "review"
    assert record["risk_events"][0]["risk_category"] == "administrative_penalty"
    assert record["evidence"][0]["provider"] == "creditchina.gov.cn"
    assert record["evidence"][0]["manual_review_required"] is True


def test_public_records_standardizes_minimized_presence_leads() -> None:
    from adapters.autonomous_sources import AutonomousPublicRecordAggregator

    adapter = AutonomousPublicRecordAggregator(_make_gate())
    result = adapter.standardize_result(
        "Demo Person",
        {
            "query_subject_hash": "person123",
            "source": "public_records_aggregators",
            "access_method": "standard_http_get",
            "fields": {
                "sources_accessed": ["fastpeoplesearch", "thatsthem"],
                "source_count": 2,
                "record_indicators": 8,
            },
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "autonomous_public_record_presence_lead"
    assert record["source_hint"] == "autonomous_public_records"
    assert record["entity_match"]["level"] == "review"
    assert record["raw"]["data_minimization"] == "detailed address/phone fields are not standardized without review"
    assert record["evidence"][0]["data_minimization"] == "presence_and_indicator_counts_only"


def test_credit_china_live_data() -> None:
    _require_live_autonomous()
    from adapters.autonomous_sources import AutonomousEnterpriseRegistryLookup

    adapter = AutonomousEnterpriseRegistryLookup(_make_gate())
    adapter.enable()
    result = adapter.query_credit_china("中国石油")
    assert result.get("response_status") == 200


def test_public_records_live_data() -> None:
    _require_live_autonomous()
    from adapters.autonomous_sources import AutonomousPublicRecordAggregator

    adapter = AutonomousPublicRecordAggregator(_make_gate())
    adapter.enable()
    result = adapter.query_public_records("Bill Gates")
    assert result.get("response_status") == 200
