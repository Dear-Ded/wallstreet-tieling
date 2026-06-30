"""runtime_lookups_v2 门集成验证 — 0真实HTTP。"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_asset_lookup_gated_blocks_when_unauthorized():
    from adapters.runtime_lookups_v2 import EnterpriseAssetLookup
    gate = _make_gate()
    a = EnterpriseAssetLookup(auth_gate=gate)
    assert not a.is_available()
    r = a.query_organization_assets("test")
    assert r.get("error") == "source_not_authorized"


def test_asset_lookup_gated_allows_after_enable():
    from adapters.runtime_lookups_v2 import EnterpriseAssetLookup
    gate = _make_gate()
    a = EnterpriseAssetLookup(auth_gate=gate)
    a.enable()
    assert a.is_available()


def test_domain_lookup_gated_blocks():
    from adapters.runtime_lookups_v2 import DomainReputationLookup
    gate = _make_gate()
    a = DomainReputationLookup(auth_gate=gate)
    assert not a.is_available()
    r = a.check_domain("test.com")
    assert r.get("error") == "source_not_authorized"


def test_security_lookup_gated_blocks():
    from adapters.runtime_lookups_v2 import PublicRecordSecurityLookup
    gate = _make_gate()
    a = PublicRecordSecurityLookup(auth_gate=gate)
    assert not a.is_available()


def test_identity_lookup_gated_blocks():
    from adapters.runtime_lookups_v2 import PublicIdentityVerification
    gate = _make_gate()
    a = PublicIdentityVerification(auth_gate=gate)
    assert not a.is_available()


def test_all_adapters_work_without_gate():
    """向后兼容: 不传gate时，is_available()=True"""
    from adapters.runtime_lookups_v2 import EnterpriseAssetLookup
    a = EnterpriseAssetLookup()
    assert a.is_available()


def test_disable_revokes():
    """撤回授权后不可用"""
    from adapters.runtime_lookups_v2 import DomainReputationLookup
    gate = _make_gate()
    a = DomainReputationLookup(auth_gate=gate)
    a.enable()
    assert a.is_available()
    gate.disable_source("domain_reputation_lookup")
    assert not a.is_available()
