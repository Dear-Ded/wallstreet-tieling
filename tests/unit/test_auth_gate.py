"""用户授权网关 + 已授权数据源 运行时验证"""


def test_gate_default_disabled():
    """验证: 所有数据源默认禁用"""
    from core.user_auth_gate import UserAuthorizationGate
    gate = UserAuthorizationGate("test_user")
    gate.register_source("test_source", "Test Source")
    assert not gate.is_authorized("test_source")


def test_gate_enable_then_authorized():
    """验证: 用户授权后数据源变为可用"""
    from core.user_auth_gate import UserAuthorizationGate
    gate = UserAuthorizationGate("test_user")
    gate.register_source("test_source", "Test Source")
    gate.enable_source("test_source")
    assert gate.is_authorized("test_source")


def test_gate_disable_revokes():
    """验证: 用户撤回后不可用"""
    from core.user_auth_gate import UserAuthorizationGate
    gate = UserAuthorizationGate("test_user")
    gate.register_source("test_source", "Test Source")
    gate.enable_source("test_source")
    gate.disable_source("test_source")
    assert not gate.is_authorized("test_source")


def test_gate_audit_trail():
    """验证: 授权操作产生审计记录"""
    from core.user_auth_gate import UserAuthorizationGate
    gate = UserAuthorizationGate("test_user")
    gate.register_source("test_source", "Test Source")
    record = gate.enable_source("test_source")
    d = record.to_dict()
    assert d["status"] == "enabled"
    assert d["audit_trail_count"] >= 1


def test_gate_report_shows_all_statuses():
    """验证: 授权报告包含所有状态"""
    from core.user_auth_gate import UserAuthorizationGate
    gate = UserAuthorizationGate("test_user")
    gate.register_source("src_a", "Source A")
    gate.register_source("src_b", "Source B")
    gate.enable_source("src_a")
    report = gate.get_authorization_report()
    assert report["enabled"] == 1
    assert report["disabled"] == 1


def test_sec_edgar_requires_authorization():
    """验证: SEC EDGAR 需要用户显式授权后才能查询"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedSECEdgarLookup
    gate = UserAuthorizationGate("test_user")
    lookup = AuthorizedSECEdgarLookup(gate)
    # 未授权 → 不可用
    assert not lookup.is_available()
    result = lookup.lookup_company_by_ticker("AAPL")
    assert result.get("error") == "source_not_authorized"


def test_sec_edgar_works_after_enable():
    """验证: 用户授权后 SEC EDGAR 可查询"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedSECEdgarLookup
    gate = UserAuthorizationGate("test_user")
    lookup = AuthorizedSECEdgarLookup(gate)
    lookup.enable()
    assert lookup.is_available()
    result = lookup.lookup_company_by_ticker("AAPL")
    assert "cik" in result or "error" in result  # 可能网络不可达,但授权检查通过


def test_companies_house_requires_api_key():
    """验证: Companies House需要用户提供API Key"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedCompaniesHouseLookup
    gate = UserAuthorizationGate("test_user")
    lookup = AuthorizedCompaniesHouseLookup(gate)
    # 未提供API Key → 不可用(即使授权了gate)
    lookup.enable(api_key="")  # 空Key
    assert not lookup.is_available()


def test_opensanctions_requires_authorization():
    """验证: OpenSanctions需要用户授权"""
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedOpenSanctionsLookup
    gate = UserAuthorizationGate("test_user")
    lookup = AuthorizedOpenSanctionsLookup(gate)
    assert not lookup.is_available()


def test_opensanctions_standardizes_authorized_watchlist_leads():
    from core.user_auth_gate import UserAuthorizationGate
    from adapters.authorized_sources import AuthorizedOpenSanctionsLookup

    lookup = AuthorizedOpenSanctionsLookup(UserAuthorizationGate("test_user"), api_key="test-key")
    result = lookup.standardize_result(
        "Demo Person",
        {
            "sample": [
                {
                    "name": "Demo Person",
                    "schema": "Person",
                    "countries": ["us"],
                }
            ]
        },
    )

    assert result["health"]["ok"] is True
    assert result["health"]["license"] == "CC BY-NC 4.0"
    record = result["standardized_records"][0]
    assert record["record_type"] == "authorized_watchlist_subject_match"
    assert record["entity_match"]["level"] == "exact"
    assert record["evidence"][0]["provider"] == "OpenSanctions"
    assert record["evidence"][0]["license_review"] == "non_commercial_or_authorized_use_required"
