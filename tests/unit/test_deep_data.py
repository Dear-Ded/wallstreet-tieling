"""深度数据源验证"""

def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")

def test_hibp_real_data():
    """HaveIBeenPwned: Adobe → real events"""
    from adapters.deep_data_final import PublicSecurityEventLookup
    a = PublicSecurityEventLookup(_make_gate()); a.enable()
    r = a.query_domain_events("adobe.com")
    assert r.get("authorized")
    if "error" not in r:
        assert r["fields"]["event_count"] >= 1
        names = [e["name"] for e in r["fields"]["events"]]
        assert "Adobe" in names or any("Adobe" in n for n in names)

def test_phone_real_data():
    """AbstractAPI demo: 电话归属"""
    from adapters.deep_data_final import TelecomAttributionLookup
    a = TelecomAttributionLookup(_make_gate()); a.enable()
    r = a.query_phone("+12025550100", "California")
    assert r.get("authorized")
    if "error" not in r and r["fields"].get("valid"):
        assert r["fields"]["country"] == "United States of America"

def test_both_unauthorized_block():
    from adapters.deep_data_final import PublicSecurityEventLookup, TelecomAttributionLookup
    for cls in [PublicSecurityEventLookup, TelecomAttributionLookup]:
        a = cls(_make_gate())
        r = a.query_domain_events("test.com") if hasattr(a,'query_domain_events') else a.query_phone("+1")
        assert r.get("error") == "source_not_authorized"
