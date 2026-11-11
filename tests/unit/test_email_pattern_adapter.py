"""Tests for email pattern candidate adapter (offline, MX check stubbed)."""

from adapters.email_intel_adapter import EmailIntelLookup
from adapters.email_pattern_adapter import (
    EmailPatternLookup,
    generate_patterns,
    parse_subject,
)


def _adapter(monkeypatch=None):
    a = EmailPatternLookup(
        execute_query=lambda url, headers: (200, "", ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )
    return a


def test_generate_patterns_common_shapes():
    pats = generate_patterns("San", "Zhang")
    for p in ["san.zhang", "sanzhang", "san_zhang", "szhang", "san.z",
              "zhang.san", "sz", "san"]:
        assert p in pats, p
    assert len(pats) == len(set(pats))


def test_generate_patterns_empty_on_bad_input():
    assert generate_patterns("", "Zhang") == []
    assert generate_patterns("San", "") == []
    # 非字母字符被清洗而非报错："San123!" → "san123"
    assert "san123.zhang" in generate_patterns("San123!", "Zhang")


def test_parse_subject_keyword_form():
    f, l, d = parse_subject("San Zhang@example.com", {})
    assert (f, l, d) == ("San", "Zhang", "example.com")


def test_parse_subject_params_form():
    f, l, d = parse_subject("", {"first_name": "San", "last_name": "Zhang",
                                 "domain": "Example.COM"})
    assert (f, l, d) == ("San", "Zhang", "example.com")


def test_query_returns_low_confidence_candidates(monkeypatch):
    monkeypatch.setattr(EmailIntelLookup, "_check_mx", staticmethod(lambda d: True))
    a = _adapter()
    out = a.query("San Zhang@example.com")
    f = out["fields"]
    assert f["confidence"] == "low"
    assert f["domain_has_mx"] is True
    assert f["candidate_count"] >= 10
    assert all(c["confidence"] == "low" for c in f["candidates"])
    assert f["candidates"][0]["email"] == "san.zhang@example.com"
    assert "SMTP" in f["data_note"] and "红线" in f["data_note"]


def test_query_rejects_invalid_input():
    a = _adapter()
    out = a.query("not-an-email")
    assert out["fields"]["candidates"] == []
    assert "无效" in out["fields"]["data_note"]
