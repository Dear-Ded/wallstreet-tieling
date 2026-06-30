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
