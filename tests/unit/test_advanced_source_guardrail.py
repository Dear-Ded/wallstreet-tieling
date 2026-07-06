"""
高级数据源管线集成验证 — 证明高级适配器不接入默认一键尽调。
"""


def test_all_advanced_sources_default_disabled():
    """所有高级数据源默认不接入一键尽调"""
    from core.advanced_source_registry import (
        ADVANCED_SOURCE_REGISTRY, is_source_enabled_by_default,
    )
    for key in ADVANCED_SOURCE_REGISTRY:
        assert not is_source_enabled_by_default(key), f"{key} should default to disabled"


def test_gate_prevents_investigation_invocation():
    """未授权的高级适配器在调用时被gate拦截"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import ExecutiveIdentityVerification
    gate = UserAuthorizationGate("test")
    adapter = ExecutiveIdentityVerification(gate)
    # 未授权
    assert not adapter.is_available()
    r = adapter.verify_executive_identity("any_name")
    assert r.get("error") == "source_not_authorized"


def test_authorized_adapter_can_be_invoked():
    """授权后适配器可被调用(网络可能不可达,但gate通过)"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import EnterpriseDomainSecurityAssessment
    gate = UserAuthorizationGate("test")
    adapter = EnterpriseDomainSecurityAssessment(gate)
    adapter.enable()
    assert adapter.is_available()
    r = adapter.assess_domain_risk("example-company-not-real-99999.com")
    # gate通过 — 网络可能失败,但不返回 source_not_authorized
    assert r.get("error") != "source_not_authorized"


def test_domain_security_adapter_exposes_schema_health_and_standard_records():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import EnterpriseDomainSecurityAssessment

    gate = UserAuthorizationGate("test")
    adapter = EnterpriseDomainSecurityAssessment(gate)

    health = adapter.schema_health()
    assert health["ok"] is True
    assert health["standardized_records"] is True
    assert health["record_type"] == "enterprise_domain_security_event"

    result = adapter.standardize_domain_risk_result(
        "example-company.invalid",
        {
            "authorized": True,
            "access_path": "public_security_event_registry",
            "fields": {"domain_reputation": "medium", "has_public_events": True},
            "retrieved_at": "2026-07-05T20:00:00",
        },
    )

    record = result["standardized_records"][0]
    assert record["record_type"] == "enterprise_domain_security_event"
    assert record["source_hint"] == "enterprise_domain_security_assessment"
    assert record["entity_match"]["level"] == "exact"
    assert record["risk_events"][0]["risk_category"] == "domain_security"


def test_enterprise_executive_identity_adapter_standardizes_authorized_result():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import ExecutiveIdentityVerification

    gate = UserAuthorizationGate("test")
    adapter = ExecutiveIdentityVerification(gate)

    health = adapter.schema_health()
    assert health["ok"] is True
    assert health["record_type"] == "enterprise_executive_identity_consistency"

    result = adapter.standardize_identity_result(
        "Alice Zhang",
        {
            "authorized": True,
            "access_path": "professional_network_public_profile_verification",
            "query_subject_hash": "abc123",
            "fields": {"platforms_found": 2, "platform_list": ["github", "medium"]},
            "retrieved_at": "2026-07-05T20:10:00",
        },
    )

    record = result["standardized_records"][0]
    assert record["record_type"] == "enterprise_executive_identity_consistency"
    assert record["source_hint"] == "enterprise_executive_identity_verification"
    assert record["entity"] == "Alice Zhang"
    assert record["evidence"][0]["platforms"] == ["github", "medium"]


def test_enterprise_contact_attribution_adapter_standardizes_authorized_result():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import EnterpriseContactAttribution

    gate = UserAuthorizationGate("test")
    adapter = EnterpriseContactAttribution(gate)

    health = adapter.schema_health()
    assert health["ok"] is True
    assert health["record_type"] == "enterprise_contact_attribution"

    result = adapter.standardize_contact_result(
        "+15551234567",
        "Beijing",
        {
            "authorized": True,
            "access_path": "public_telecom_attribution",
            "query_subject_hash": "phonehash123",
            "fields": {
                "country": "CN",
                "location": "Shanghai",
                "carrier": "Demo Carrier",
                "line_type": "mobile",
                "location_consistency": "inconsistent",
            },
        },
    )

    record = result["standardized_records"][0]
    assert record["record_type"] == "enterprise_contact_attribution"
    assert record["source_hint"] == "enterprise_contact_attribution_verification"
    assert record["risk_events"][0]["risk_category"] == "location_contact_consistency"
    assert record["entity_match"]["identifiers"]["phone_hash"] == "phonehash123"


def test_key_personnel_crosscheck_adapter_standardizes_authorized_result():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.enterprise_profiling import KeyPersonnelRecordCrossCheck

    gate = UserAuthorizationGate("test")
    adapter = KeyPersonnelRecordCrossCheck(gate)

    health = adapter.schema_health()
    assert health["ok"] is True
    assert health["record_type"] == "enterprise_key_personnel_record_crosscheck"

    result = adapter.standardize_crosscheck_result(
        "Bob Li",
        "Demo Holdings",
        {
            "authorized": True,
            "access_path": "public_government_record_aggregation",
            "query_subject_hash": "personhash123",
            "fields": {"sources_accessed": ["fastpeoplesearch"], "source_count": 1},
        },
    )

    record = result["standardized_records"][0]
    assert record["record_type"] == "enterprise_key_personnel_record_crosscheck"
    assert record["source_hint"] == "enterprise_key_personnel_record_crosscheck"
    assert record["entity_match"]["identifiers"]["company_name"] == "Demo Holdings"
    assert record["evidence"][0]["sources_accessed"] == ["fastpeoplesearch"]


def test_authorized_companies_house_adapter_standardizes_search_result():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedCompaniesHouseLookup

    gate = UserAuthorizationGate("test")
    adapter = AuthorizedCompaniesHouseLookup(gate, api_key="not-used-in-standardizer")

    health = adapter.schema_health()
    assert health["ok"] is True
    assert health["record_type"] == "companies_house_company_search_result"
    assert health["requires_api_key"] is True

    result = adapter.standardize_search_result(
        "Demo PLC",
        {
            "authorized": True,
            "source": "companies_house_uk",
            "sample": [
                {"name": "Demo PLC", "number": "01234567", "status": "active", "address": "London"},
            ],
        },
    )

    record = result["standardized_records"][0]
    assert record["record_type"] == "companies_house_company_search_result"
    assert record["source_hint"] == "authorized_companies_house_api"
    assert record["entity_match"]["level"] == "exact"
    assert record["jurisdiction"] == "GB"
    assert record["evidence"][0]["company_number"] == "01234567"


def test_authorized_sec_edgar_adapter_standardizes_ticker_and_filing_history():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedSECEdgarLookup

    gate = UserAuthorizationGate("test")
    adapter = AuthorizedSECEdgarLookup(gate)

    health = adapter.schema_health()
    assert health["ok"] is True
    assert "sec_edgar_authorized_company_lookup" in health["record_types"]

    ticker_result = adapter.standardize_ticker_result(
        "AAPL",
        {"authorized": True, "source": "sec_edgar", "cik": "0000320193", "ticker": "AAPL", "company_name": "Apple Inc."},
    )
    ticker_record = ticker_result["standardized_records"][0]
    assert ticker_record["record_type"] == "sec_edgar_authorized_company_lookup"
    assert ticker_record["source_hint"] == "authorized_sec_edgar_full_api"
    assert ticker_record["entity_match"]["identifiers"]["cik"] == "0000320193"

    filing_result = adapter.standardize_filing_history_result(
        "0000320193",
        {
            "authorized": True,
            "source": "sec_edgar",
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "total_recent_filings": 3,
            "filing_types": {"10-K": 1, "8-K": 2},
        },
    )
    filing_record = filing_result["standardized_records"][0]
    assert filing_record["record_type"] == "sec_edgar_authorized_filing_history"
    assert filing_record["risk_category"] == "financing_capital_markets"
    assert filing_record["evidence"][0]["filing_types"] == {"10-K": 1, "8-K": 2}


def test_registry_excludes_from_default_packet():
    """高级数据源注册表确认所有条目 default_enabled=False"""
    from core.advanced_source_registry import ADVANCED_SOURCE_REGISTRY
    for key, entry in ADVANCED_SOURCE_REGISTRY.items():
        assert entry.get("default_enabled") is False, f"{key} default_enabled must be False"
        assert "investigation_lanes" in entry


def test_lane_mapping_coverage():
    """每个调查线至少有一个高级数据源"""
    from core.advanced_source_registry import get_sources_for_lane
    for lane in ["money", "goods", "people"]:
        sources = get_sources_for_lane(lane)
        assert len(sources) > 0, f"No advanced sources for lane: {lane}"


def test_no_advanced_source_in_default_pipeline():
    """验证: 默认一键尽调不包含任何高级适配器"""
    from core.advanced_source_registry import ADVANCED_SOURCE_REGISTRY, is_source_enabled_by_default
    enabled_defaults = [k for k in ADVANCED_SOURCE_REGISTRY if is_source_enabled_by_default(k)]
    assert len(enabled_defaults) == 0, f"These should not be in default pipeline: {enabled_defaults}"
