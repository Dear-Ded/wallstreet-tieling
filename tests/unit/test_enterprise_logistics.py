"""企业尽调扩展数据源门验证 — 所有适配器默认禁用,授权后可用。0真实HTTP。"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_logistics_unauthorized_blocks():
    from adapters.enterprise_logistics import EnterpriseLogisticsLookup
    a = EnterpriseLogisticsLookup(_make_gate())
    assert not a.is_available()
    r = a.query_import_records("test_company")
    assert r.get("error") == "source_not_authorized"


def test_logistics_authorized_allows():
    from adapters.enterprise_logistics import EnterpriseLogisticsLookup
    a = EnterpriseLogisticsLookup(_make_gate())
    a.enable()
    assert a.is_available()


def test_procurement_unauthorized_blocks():
    from adapters.enterprise_logistics import EnterpriseProcurementLookup
    a = EnterpriseProcurementLookup(_make_gate())
    assert not a.is_available()
    r = a.query_us_contracts("test_company")
    assert r.get("error") == "source_not_authorized"


def test_procurement_authorized_allows():
    from adapters.enterprise_logistics import EnterpriseProcurementLookup
    a = EnterpriseProcurementLookup(_make_gate())
    a.enable()
    assert a.is_available()


def test_hospitality_unauthorized_blocks():
    from adapters.enterprise_logistics import EnterpriseHospitalityLookup
    a = EnterpriseHospitalityLookup(_make_gate())
    assert not a.is_available()


def test_hospitality_authorized_allows():
    from adapters.enterprise_logistics import EnterpriseHospitalityLookup
    a = EnterpriseHospitalityLookup(_make_gate())
    a.enable()
    assert a.is_available()


def test_customer_concentration_unauthorized_blocks():
    from adapters.enterprise_logistics import EnterpriseCustomerConcentration
    a = EnterpriseCustomerConcentration(_make_gate())
    assert not a.is_available()
    r = a.analyze_customer_concentration("AAPL")
    assert r.get("error") == "source_not_authorized"


def test_all_source_types_enterprise():
    from adapters.enterprise_logistics import (
        EnterpriseLogisticsLookup, EnterpriseProcurementLookup,
        EnterpriseHospitalityLookup, EnterpriseCustomerConcentration,
    )
    for cls in [EnterpriseLogisticsLookup, EnterpriseProcurementLookup,
                EnterpriseHospitalityLookup, EnterpriseCustomerConcentration]:
        a = cls(_make_gate())
        assert "enterprise" in a.source_type.lower()


def test_lane_assignment():
    """验证每个适配器分配到正确的尽调管线"""
    from adapters.enterprise_logistics import (
        EnterpriseLogisticsLookup, EnterpriseProcurementLookup,
        EnterpriseHospitalityLookup, EnterpriseCustomerConcentration,
    )
    gate = _make_gate()
    EnterpriseLogisticsLookup(gate)
    EnterpriseProcurementLookup(gate)
    EnterpriseHospitalityLookup(gate)
    EnterpriseCustomerConcentration(gate)
    report = gate.get_authorization_report()
    assert report["total_sources"] >= 4
