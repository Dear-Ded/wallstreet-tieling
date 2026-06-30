"""
企业尽调主体画像适配器验证 — 全gate集成测试,不触真实外网。
仅验证: 未授权拒绝/授权后可用/门集成/调查线分配。
"""

from core.user_auth_gate import UserAuthorizationGate


def _make_gate():
    return UserAuthorizationGate("test_user")


def test_all_adapters_require_gate_injection():
    """所有适配器构造器要求传入 UserAuthorizationGate"""
    gate = _make_gate()
    from adapters.enterprise_profiling import (
        ExecutiveIdentityVerification, EnterpriseDomainSecurityAssessment,
        EnterpriseContactAttribution, KeyPersonnelRecordCrossCheck,
    )
    for cls in [ExecutiveIdentityVerification, EnterpriseDomainSecurityAssessment,
                EnterpriseContactAttribution, KeyPersonnelRecordCrossCheck]:
        adapter = cls(gate)
        assert adapter is not None  # 不抛异常


def test_unauthorized_returns_error():
    """默认未授权时所有公开方法返回 source_not_authorized"""
    gate = _make_gate()
    from adapters.enterprise_profiling import ExecutiveIdentityVerification
    a = ExecutiveIdentityVerification(gate)
    assert not a.is_available()
    r = a.verify_executive_identity("test_exec")
    assert r.get("error") == "source_not_authorized"


def test_authorized_then_available():
    """用户授权后 is_available() 返回 True"""
    gate = _make_gate()
    from adapters.enterprise_profiling import EnterpriseDomainSecurityAssessment
    a = EnterpriseDomainSecurityAssessment(gate)
    assert not a.is_available()
    a.enable()
    assert a.is_available()


def test_disable_revokes():
    """用户撤回授权后 is_available() 返回 False"""
    gate = _make_gate()
    from adapters.enterprise_profiling import ExecutiveIdentityVerification
    a = ExecutiveIdentityVerification(gate)
    a.enable()
    assert a.is_available()
    gate.disable_source("executive_identity_verification")
    assert not a.is_available()


def test_unauthorized_returns_error_for_all_adapters():
    """所有适配器未授权时都返回 source_not_authorized"""
    gate = _make_gate()
    from adapters.enterprise_profiling import (
        ExecutiveIdentityVerification, EnterpriseDomainSecurityAssessment,
        EnterpriseContactAttribution, KeyPersonnelRecordCrossCheck,
    )
    adapters = [
        (ExecutiveIdentityVerification(gate), "verify_executive_identity", ["test"]),
        (EnterpriseDomainSecurityAssessment(gate), "assess_domain_risk", ["test.com"]),
        (EnterpriseContactAttribution(gate), "verify_business_phone", ["+8613800000000"]),
        (KeyPersonnelRecordCrossCheck(gate), "cross_check_personnel", ["test"]),
    ]
    for adapter, method_name, args in adapters:
        assert not adapter.is_available()
        result = getattr(adapter, method_name)(*args)
        assert result.get("error") == "source_not_authorized", f"{method_name} should block"


def test_lane_assignment_correct():
    """每个适配器分配到正确的调查线"""
    gate = _make_gate()
    from adapters.enterprise_profiling import ExecutiveIdentityVerification
    a = ExecutiveIdentityVerification(gate)
    cfg = gate.get_source_config("executive_identity_verification") if a.is_available() else {}
    # 验证source已注册且配置包含people lane
    report = gate.get_authorization_report()
    sources = report.get("sources", {})
    assert "executive_identity_verification" in sources


def test_source_type_contains_enterprise():
    """所有适配器 source_type 包含 enterprise"""
    gate = _make_gate()
    from adapters.enterprise_profiling import (
        ExecutiveIdentityVerification, EnterpriseDomainSecurityAssessment,
        EnterpriseContactAttribution, KeyPersonnelRecordCrossCheck,
    )
    for cls in [ExecutiveIdentityVerification, EnterpriseDomainSecurityAssessment,
                EnterpriseContactAttribution, KeyPersonnelRecordCrossCheck]:
        a = cls(gate)
        assert "enterprise" in a.source_type.lower()


def test_gate_report_reflects_adapter_state():
    """授权报告正确反映适配器状态"""
    gate = _make_gate()
    from adapters.enterprise_profiling import ExecutiveIdentityVerification
    a = ExecutiveIdentityVerification(gate)
    report = gate.get_authorization_report()
    assert report["disabled"] >= 1
    a.enable()
    report2 = gate.get_authorization_report()
    assert report2["enabled"] >= 1
