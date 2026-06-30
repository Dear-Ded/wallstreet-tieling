"""深度主体画像已验证数据源 — 真实数据产出证明"""

import os

import pytest


def _require_live_deep_profile() -> None:
    if os.getenv("WST_LIVE_DEEP_PROFILE") != "1":
        pytest.skip("live deep-profile smoke disabled; set WST_LIVE_DEEP_PROFILE=1")


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_whois_real_data():
    _require_live_deep_profile()
    """WHOIS RDAP: apple.com → 4 nameservers + registration/expiration dates"""
    from adapters.deep_profile_verified import WHOISDomainLookup
    a = WHOISDomainLookup(_make_gate())
    a.enable()
    r = a.query_domain("apple.com")
    assert r.get("authorized")
    if "error" not in r:
        assert r["fields"]["domain_status"] != []
        assert r["fields"]["nameservers"] != []
        print(f"WHOIS: {r['fields']['registration_date']} → {r['fields']['expiration_date']}, {len(r['fields']['nameservers'])} nameservers")


def test_cross_platform_real_data():
    _require_live_deep_profile()
    """跨平台验证: torvalds → 4/15 platforms"""
    from adapters.deep_profile_verified import CrossPlatformProfileVerifier
    a = CrossPlatformProfileVerifier(_make_gate())
    a.enable()
    r = a.verify_executive_profiles("torvalds")
    assert r.get("authorized")
    if "error" not in r:
        assert r["fields"]["platforms_found"] >= 3  # GitHub + Twitter + Keybase
        assert r["fields"]["consistency_assessment"] != ""
        print(f"跨平台: {r['fields']['platforms_found']}/{r['fields']['total_checked']} found → {r['fields']['consistency_assessment']}")


def test_whois_unauthorized_blocks():
    from adapters.deep_profile_verified import WHOISDomainLookup
    a = WHOISDomainLookup(_make_gate())
    r = a.query_domain("test.com")
    assert r.get("error") == "source_not_authorized"


def test_cross_platform_unauthorized_blocks():
    from adapters.deep_profile_verified import CrossPlatformProfileVerifier
    a = CrossPlatformProfileVerifier(_make_gate())
    r = a.verify_executive_profiles("test")
    assert r.get("error") == "source_not_authorized"


def test_disable_revokes_both():
    from adapters.deep_profile_verified import WHOISDomainLookup, CrossPlatformProfileVerifier
    gate = _make_gate()
    w = WHOISDomainLookup(gate)
    c = CrossPlatformProfileVerifier(gate)
    w.enable(); c.enable()
    assert w.is_available() and c.is_available()
    gate.disable_source("whois_domain")
    gate.disable_source("cross_platform_profiles")
    assert not w.is_available() and not c.is_available()
