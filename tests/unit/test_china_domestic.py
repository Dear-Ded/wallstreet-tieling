"""中国国内数据源门验证 — 所有适配器默认禁用,授权后可用。0真实HTTP。"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_tax_credit_unauthorized_blocks():
    from adapters.china_domestic_sources import EnterpriseTaxCreditLookup
    a = EnterpriseTaxCreditLookup(_make_gate())
    assert not a.is_available()
    r = a.query_tax_credit("test_company")
    assert r.get("error") == "source_not_authorized"


def test_tax_credit_authorized_allows():
    from adapters.china_domestic_sources import EnterpriseTaxCreditLookup
    a = EnterpriseTaxCreditLookup(_make_gate())
    a.enable()
    assert a.is_available()


def test_judicial_asset_unauthorized_blocks():
    from adapters.china_domestic_sources import EnterpriseJudicialAssetLookup
    a = EnterpriseJudicialAssetLookup(_make_gate())
    assert not a.is_available()
    r = a.query_bankruptcy("test")
    assert r.get("error") == "source_not_authorized"
    r2 = a.query_auction("test")
    assert r2.get("error") == "source_not_authorized"


def test_overseas_invest_unauthorized_blocks():
    from adapters.china_domestic_sources import EnterpriseOverseasInvestment
    a = EnterpriseOverseasInvestment(_make_gate())
    assert not a.is_available()


def test_baidu_credit_unauthorized_blocks():
    from adapters.china_domestic_sources import EnterpriseBaiduCreditLookup
    a = EnterpriseBaiduCreditLookup(_make_gate())
    assert not a.is_available()
    r = a.query_enterprise("test")
    assert r.get("error") == "source_not_authorized"


def test_shuidi_credit_unauthorized_blocks():
    from adapters.china_domestic_sources import EnterpriseShuidiCreditLookup
    a = EnterpriseShuidiCreditLookup(_make_gate())
    assert not a.is_available()


def test_all_source_types_enterprise_or_public():
    from adapters.china_domestic_sources import (
        EnterpriseTaxCreditLookup, EnterpriseJudicialAssetLookup,
        EnterpriseOverseasInvestment, EnterpriseBaiduCreditLookup,
        EnterpriseShuidiCreditLookup,
    )
    for cls in [EnterpriseTaxCreditLookup, EnterpriseJudicialAssetLookup,
                EnterpriseOverseasInvestment, EnterpriseBaiduCreditLookup,
                EnterpriseShuidiCreditLookup]:
        a = cls(_make_gate())
        assert "enterprise" in a.source_type.lower() or "public" in a.source_type.lower()


def test_disable_revokes():
    from adapters.china_domestic_sources import EnterpriseTaxCreditLookup
    gate = _make_gate()
    a = EnterpriseTaxCreditLookup(gate)
    a.enable()
    assert a.is_available()
    gate.disable_source("enterprise_tax_credit")
    assert not a.is_available()
