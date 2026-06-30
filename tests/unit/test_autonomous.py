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
