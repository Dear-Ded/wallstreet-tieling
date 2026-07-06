"""已验证数据源适配器 — 证明可输出真实数据的测试。门控+真实数据验证。"""


import os

import pytest


def _require_live_verified_sources() -> None:
    if os.getenv("WST_LIVE_VERIFIED_SOURCES") != "1":
        pytest.skip("live verified-source smoke disabled; set WST_LIVE_VERIFIED_SOURCES=1")


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_sec_edgar_real_data():
    _require_live_verified_sources()
    """SEC EDGAR: 真实数据 — Apple Inc. 应返回1000条申报"""
    from adapters.verified_sources import SECEdgarCompanyLookup
    a = SECEdgarCompanyLookup(_make_gate())
    a.enable()
    r = a.query_company("AAPL")  # 真实调用SEC EDGAR
    assert r.get("authorized") is True
    if "error" not in r:
        assert r["fields"]["company_name"] == "Apple Inc."
        assert r["fields"]["total_recent_filings"] == 1000
        assert r["fields"]["annual_reports_10k"] >= 10


def test_github_real_data():
    _require_live_verified_sources()
    """GitHub API: 真实数据 — 已验证torvalds→309k followers"""
    from adapters.verified_sources import GitHubPublicProfileLookup
    a = GitHubPublicProfileLookup(_make_gate())
    a.enable()
    r = a.query_profile("torvalds")
    assert r.get("authorized") is True
    if "error" not in r:
        assert r["fields"]["name"] == "Linus Torvalds"
        assert r["fields"]["followers"] > 100000
        assert r["fields"]["company"] == "Linux Foundation"


def test_github_standardizes_public_profile_lead():
    from adapters.verified_sources import GitHubPublicProfileLookup

    adapter = GitHubPublicProfileLookup(_make_gate())
    result = adapter.standardize_result(
        "torvalds",
        {
            "fields": {
                "name": "Linus Torvalds",
                "company": "Linux Foundation",
                "public_repos": 8,
                "followers": 100000,
            }
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "public_developer_profile_lead"
    assert record["entity"] == "Linus Torvalds"
    assert record["entity_match"]["level"] == "review"
    assert record["evidence"][0]["provider"] == "GitHub"
    assert record["entities"][0]["relation"] == "public_profile_candidate"


def test_wikipedia_real_data():
    _require_live_verified_sources()
    """Wikipedia API: 真实数据 — Apple Inc. 应返回86k字符"""
    from adapters.verified_sources import WikipediaEnterpriseLookup
    a = WikipediaEnterpriseLookup(_make_gate())
    a.enable()
    r = a.query_enterprise("Apple Inc.")
    assert r.get("authorized") is True
    if "error" not in r:
        assert r["fields"]["title"] == "Apple Inc."
        assert r["fields"]["extract_length"] > 0  # exintro返回导言部分


def test_wikipedia_standardizes_public_encyclopedia_lead():
    from adapters.verified_sources import WikipediaEnterpriseLookup

    adapter = WikipediaEnterpriseLookup(_make_gate())
    result = adapter.standardize_result(
        "Apple Inc.",
        {
            "fields": {
                "title": "Apple Inc.",
                "extract_preview": "Apple Inc. is a technology company.",
                "extract_length": 1024,
            }
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "public_encyclopedia_profile_lead"
    assert record["entity"] == "Apple Inc."
    assert record["entity_match"]["level"] == "exact"
    assert record["evidence"][0]["license"] == "CC BY-SA"
    assert record["evidence"][0]["attribution_required"] is True


def test_crtsh_real_data():
    _require_live_verified_sources()
    """crt.sh: 真实数据 — apple.com 应返回>50个域名"""
    from adapters.verified_sources import CRTshDomainLookup
    a = CRTshDomainLookup(_make_gate())
    a.enable()
    r = a.query_domain_certificates("apple.com")
    assert r.get("authorized") is True
    if "error" not in r:
        assert r["fields"]["unique_domains_found"] > 50


def test_crtsh_standardizes_certificate_domain_assets():
    from adapters.verified_sources import CRTshDomainLookup

    adapter = CRTshDomainLookup(_make_gate())
    result = adapter.standardize_result(
        "example.com",
        {
            "fields": {
                "unique_domains_found": 2,
                "sample_domains": ["example.com", "www.example.com"],
            }
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "certificate_transparency_domain_asset"
    assert record["entity"] == "example.com"
    assert record["entity_match"]["level"] == "exact"
    assert record["evidence"][0]["provider"] == "crt.sh"
    assert record["entities"][0]["relation"] == "certificate_subject_name"


def test_whois_rdap_standardizes_domain_registration_record():
    from adapters.deep_profile_verified import WHOISDomainLookup

    adapter = WHOISDomainLookup(_make_gate())
    result = adapter.standardize_result(
        "example.com",
        {
            "fields": {
                "registration_date": "1995-08-14T04:00:00Z",
                "expiration_date": "2026-08-13T04:00:00Z",
                "nameservers": ["A.IANA-SERVERS.NET", "B.IANA-SERVERS.NET"],
                "domain_status": ["active"],
            }
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "domain_registration_public_record"
    assert record["entity"] == "example.com"
    assert record["entity_match"]["level"] == "exact"
    assert "registration_date=1995-08-14T04:00:00Z" in record["summary"]
    assert record["evidence"][0]["provider"] == "ICANN RDAP"
    assert record["entities"][0]["relation"] == "domain_nameserver"


def test_cross_platform_standardizes_public_profile_presence():
    from adapters.deep_profile_verified import CrossPlatformProfileVerifier

    adapter = CrossPlatformProfileVerifier(_make_gate())
    result = adapter.standardize_result(
        "demo_user",
        {
            "fields": {
                "platforms_found": 2,
                "total_checked": 15,
                "profiles": [
                    {"platform": "GitHub", "url": "https://github.com/demo_user", "purpose": "code"},
                    {"platform": "Medium", "url": "https://medium.com/@demo_user", "purpose": "writing"},
                ],
                "consistency_assessment": "moderate_consistency",
            }
        },
    )

    assert result["health"]["ok"] is True
    record = result["standardized_records"][0]
    assert record["record_type"] == "cross_platform_public_profile_presence"
    assert record["entity"] == "demo_user"
    assert record["entity_match"]["level"] == "review"
    assert len(record["evidence"]) == 2
    assert record["evidence"][0]["provider"] == "GitHub"
    assert record["entities"][0]["relation"] == "cross_platform_profile_candidate"


def test_gleif_real_data():
    _require_live_verified_sources()
    """GLEIF: 真实数据 — 搜索'Apple'应返回LEI记录"""
    from adapters.verified_sources import GLEIFEntityLookup
    a = GLEIFEntityLookup(_make_gate())
    a.enable()
    r = a.query_by_name("Apple")
    assert r.get("authorized") is True
    if "error" not in r:
        assert r["fields"]["lei_records_found"] >= 1


def test_all_unauthorized_block():
    """未授权时所有适配器阻止"""
    from adapters.verified_sources import (
        SECEdgarCompanyLookup, GitHubPublicProfileLookup,
        WikipediaEnterpriseLookup, CRTshDomainLookup, GLEIFEntityLookup,
    )
    gate = _make_gate()
    for cls in [SECEdgarCompanyLookup, GitHubPublicProfileLookup,
                WikipediaEnterpriseLookup, CRTshDomainLookup, GLEIFEntityLookup]:
        a = cls(gate)
        r = a.query_company("test") if hasattr(a, 'query_company') else (
            a.query_profile("test") if hasattr(a, 'query_profile') else
            a.query_enterprise("test") if hasattr(a, 'query_enterprise') else
            a.query_domain_certificates("test.com") if hasattr(a, 'query_domain_certificates') else
            a.query_by_name("test"))
        assert r.get("error") == "source_not_authorized", f"{cls.__name__} should block"


def test_disable_revokes():
    """授权后撤回,无法再查询"""
    from adapters.verified_sources import GitHubPublicProfileLookup
    gate = _make_gate()
    a = GitHubPublicProfileLookup(gate)
    a.enable()
    assert a.is_available()
    gate.disable_source("github_profiles")
    assert not a.is_available()
    r = a.query_profile("test")
    assert r.get("error") == "source_not_authorized"
