"""Boundary tests for optional runtime lookup adapters."""
from __future__ import annotations

import json


def _allow_robots(domain: str, url: str) -> bool:
    return True


def test_enterprise_asset_lookup_boundary() -> None:
    from adapters.runtime_lookups import EnterpriseAssetLookup

    adapter = EnterpriseAssetLookup()

    assert adapter.data_boundary == "fully_public"
    assert adapter.source_type == "public_internet_infrastructure_index"
    assert adapter.requires_credentials is True
    assert "internet_asset_index" in adapter.source_domain


def test_domain_reputation_lookup_boundary() -> None:
    from adapters.runtime_lookups import DomainReputationLookup

    adapter = DomainReputationLookup()
    fields = adapter._extract_public_fields('{"pulse_info":{"pulses":[]}}')

    assert adapter.data_boundary == "fully_public"
    assert fields["disclosure_type"] == "publicly_reported_security_observations"


def test_public_record_security_lookup_boundary() -> None:
    from adapters.runtime_lookups import PublicRecordSecurityLookup

    adapter = PublicRecordSecurityLookup()
    result = adapter._extract_public_fields(json.dumps([{"Name": "TestEvent"}]))

    assert "GDPR" in result["compliance_framework"]
    assert result["access_level"] == "fully_public_notification_database"


def test_public_identity_verification_boundary() -> None:
    from adapters.runtime_lookups import PublicIdentityVerification

    adapter = PublicIdentityVerification()

    assert adapter.data_boundary == "fully_public"
    assert adapter.requires_credentials is False


def test_all_adapters_inherit_safe_base() -> None:
    from adapters.runtime_lookups import (
        DomainReputationLookup,
        EnterpriseAssetLookup,
        PublicIdentityVerification,
        PublicRecordSecurityLookup,
    )
    from adapters.safe_research_adapter import SafeResearchAdapter

    for cls in [
        EnterpriseAssetLookup,
        DomainReputationLookup,
        PublicRecordSecurityLookup,
        PublicIdentityVerification,
    ]:
        assert issubclass(cls, SafeResearchAdapter)


def test_credentialed_runtime_adapter_does_not_execute_without_credentials() -> None:
    from adapters.runtime_lookups import DomainReputationLookup

    calls: list[str] = []

    def fail_if_called(url: str, headers: dict[str, str]):
        calls.append(url)
        return 200, "{}", ""

    adapter = DomainReputationLookup(
        execute_query=fail_if_called,
        robots_checker=_allow_robots,
        sleeper=lambda seconds: None,
    )

    result = adapter.check_domain("example.com")

    assert calls == []
    assert result["error"] == "Query blocked: credentials_required"
    assert result["response_status"] == 0
    assert result["data_boundary"] == "fully_public"


def test_credentialed_runtime_adapter_uses_injected_executor_with_credentials() -> None:
    from adapters.runtime_lookups import DomainReputationLookup

    calls: list[tuple[str, dict[str, str]]] = []

    def fake_execute(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        return 200, '{"pulse_info":{"pulses":[{"name":"demo"}]}}', ""

    adapter = DomainReputationLookup(
        api_credentials={"domain_reputation_key": "test-key"},
        execute_query=fake_execute,
        robots_checker=_allow_robots,
        sleeper=lambda seconds: None,
    )

    result = adapter.check_domain("example.com")

    assert len(calls) == 1
    assert calls[0][1]["X-OTX-API-KEY"] == "test-key"
    assert result["response_status"] == 200
    assert result["fields"]["public_report_count"] == 1


def test_runtime_adapters_are_not_default_public_intel_sources() -> None:
    from adapters.default_public_intel_tool import DefaultPublicIntelTool

    tool = DefaultPublicIntelTool()
    blocked = {
        "enterprise_asset_lookup",
        "domain_reputation_lookup",
        "public_record_security_lookup",
        "public_identity_verification",
        "internet_asset_index",
        "public_security_information_registry",
        "public_security_event_registry",
        "public_search_engine",
    }

    assert blocked.isdisjoint(set(tool.list_sources()))
    assert blocked.isdisjoint(set(tool.health_report()))


def test_no_blocked_imports() -> None:
    import adapters.runtime_lookups as rt

    assert hasattr(rt, "EnterpriseAssetLookup")
    assert hasattr(rt, "DomainReputationLookup")
    assert hasattr(rt, "PublicRecordSecurityLookup")
    assert hasattr(rt, "PublicIdentityVerification")
