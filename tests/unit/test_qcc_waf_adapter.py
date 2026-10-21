"""Tests for 企查查 WAF-bypass adapter (offline fixtures).

Covers: pure-Python acw_sc__v2 solver (4 verified challenge vectors),
challenge detection, arg1 extraction, firm profile parsing, block markers,
proxy spec parsing, and the query() wiring with a mocked transport.
No network access.
"""

import re

from adapters.qcc_waf_adapter import (
    QccWafBypassLookup,
    extract_arg1,
    is_waf_challenge,
    parse_proxy,
    solve_acw_sc__v2,
)

# (arg1, expected deterministic 51-char cookie prefix), verified 2026-10-21
# against qcc's live WAF JS via 4 independent challenge pages.
VECTORS = [
    ("5df5b7bfeecf2ae32715f06d2f1dd7fa19cb727fafa987f988",
     "1234cf0d46-fcb052b1ff3517af7ceaf2e716ed927ffbddd257"),
    ("5df5b1e495af8606ac71732461ece7becefd0941510049a4d9",
     "1234cf0d46-4fd35abefb65c4e11a06f89c7254e6017eecd917"),
    ("5df5b146c50fff4a85fe2b9fabd2e9766f22615c9375d42b65",
     "1234cf0d46-622b58bdf7a5656c104fffc5f95ffa6b24e2d1e9"),
    ("5df5b17bf160dd5bcd62518c754352fb109bd82163a110ba8b",
     "1234cf0d46-b9b15cb40fb512b1165dfdfd681c07d55753d822"),
]

CHALLENGE_FIXTURE = (
    '<textarea id="renderData" style="display:none">'
    '{"l1":"var arg1=\'5df5b7bfeecf2ae32715f06d2f1dd7fa19cb727fafa987f988\';"}'
    "</textarea><html><head></head><body>"
    "<script>/* acw_sc__v2 challenge */</script></body></html>"
)

FIRM_FIXTURE = """<html><head>
<title>阿里巴巴（中国）有限公司_企查查</title>
</head><body>
<div class="company-info">
<span>法定代表人：马云</span>
<span>注册资本：15298.6万美元</span>
<span>成立日期：1999-09-09</span>
<span>经营状态：存续</span>
</div></body></html>"""

BLOCK_423_FIXTURE = (
    '<html><head><title>访问超频 - 企查查</title></head><body>'
    '<iframe src="https://verify.qcc.com/block?reqid=-5"></iframe>'
    "当前IP在使用过程中触发安全规则，被暂停服务。</body></html>"
)


def _adapter(body: str, status: int = 200):
    return QccWafBypassLookup(
        proxy="127.0.0.1:9999",
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


# ------------------------------------------------------------ solver


def test_solve_acw_sc__v2_vectors():
    for arg1, expected in VECTORS:
        got = solve_acw_sc__v2(arg1)
        assert got[:51] == expected, arg1
        assert len(got) == 61
        assert re.fullmatch(r"[0-9a-f-]{51}[0-9a-f]{10}", got)


def test_solve_acw_sc__v2_deterministic_prefix_random_tail():
    arg1 = VECTORS[0][0]
    outs = {solve_acw_sc__v2(arg1) for _ in range(5)}
    prefixes = {o[:51] for o in outs}
    assert len(prefixes) == 1  # deterministic part stable
    tails = {o[51:] for o in outs}
    assert len(tails) > 1  # random tail varies
    assert all(re.fullmatch(r"[0-9a-f]{10}", t) for t in tails)


def test_extract_arg1_and_challenge_detection():
    assert is_waf_challenge(CHALLENGE_FIXTURE)
    assert extract_arg1(CHALLENGE_FIXTURE) == VECTORS[0][0]
    assert not is_waf_challenge(FIRM_FIXTURE)
    assert extract_arg1(FIRM_FIXTURE) is None
    assert extract_arg1("<html></html>") is None


# ------------------------------------------------------------ parsing


def test_parse_firm_profile_fields():
    p = QccWafBypassLookup.parse_firm_profile(FIRM_FIXTURE)
    assert not p["blocked"]
    assert p["company_name"] == "阿里巴巴（中国）有限公司"
    assert p["legal_rep"] == "马云"
    assert "15298.6" in p["capital"]
    assert "1999" in p["founded"]
    assert p["status"] == "存续"


def test_parse_firm_profile_blocked_markers():
    p = QccWafBypassLookup.parse_firm_profile(BLOCK_423_FIXTURE)
    assert p["blocked"] is True
    assert p["block_reason"] == "ip_suspended_or_405"
    p2 = QccWafBypassLookup.parse_firm_profile(CHALLENGE_FIXTURE)
    assert p2["blocked"] is True
    assert p2["block_reason"] == "waf_challenge_unsolved"


def test_parse_firm_profile_graceful_empty():
    p = QccWafBypassLookup.parse_firm_profile("<html><head><title>x</title></head></html>")
    assert not p["blocked"]
    assert p["company_name"] == "x" or p["company_name"] == ""
    assert p["legal_rep"] == ""


# ------------------------------------------------------------ adapter wiring


def test_normalize_firm_id():
    a = _adapter("")
    assert a.normalize_firm_id("a59b3c1f33224db1eac88afb1906efbd") == \
        "a59b3c1f33224db1eac88afb1906efbd"
    assert a.normalize_firm_id(
        "https://www.qcc.com/firm/a59b3c1f33224db1eac88afb1906efbd.html") == \
        "a59b3c1f33224db1eac88afb1906efbd"
    assert a.normalize_firm_id("not-a-firm-id") is None
    assert a.normalize_firm_id("") is None


def test_build_url_clean_no_query():
    a = _adapter("")
    url = a._build_url("a59b3c1f33224db1eac88afb1906efbd")
    assert url == "https://www.qcc.com/firm/a59b3c1f33224db1eac88afb1906efbd.html"
    assert "?" not in url


def test_parse_proxy():
    assert parse_proxy("121.46.226.221:10808") == ("121.46.226.221", 10808)
    assert parse_proxy("socks5h://121.46.226.221:10808") == ("121.46.226.221", 10808)
    try:
        parse_proxy("not-a-proxy")
        raise AssertionError("should raise")
    except ValueError:
        pass


def test_query_returns_profile_fields():
    a = _adapter(FIRM_FIXTURE)
    r = a.query("a59b3c1f33224db1eac88afb1906efbd")
    assert r["response_status"] == 200
    assert r["source_domain"] == "www.qcc.com"
    assert r["data_boundary"] == "fully_public"
    prof = r["fields"]["profile"]
    assert prof["company_name"] == "阿里巴巴（中国）有限公司"
    assert r["fields"]["blocked"] is False


def test_query_blocked_surface():
    a = _adapter(BLOCK_423_FIXTURE)
    r = a.query("a59b3c1f33224db1eac88afb1906efbd")
    assert r["fields"]["blocked"] is True
    assert r["fields"]["block_reason"] == "ip_suspended_or_405"


def test_adapter_defaults_conservative():
    a = QccWafBypassLookup.__new__(QccWafBypassLookup)
    assert QccWafBypassLookup.min_request_interval >= 8.0
    assert QccWafBypassLookup.requires_credentials is False
    assert QccWafBypassLookup.data_boundary == "fully_public"
