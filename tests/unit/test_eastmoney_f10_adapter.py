"""Tests for 东方财富 F10 上市公司档案 adapter (offline fixtures)."""

import json

from adapters.eastmoney_f10_adapter import EastmoneyF10Lookup, normalize_stock_code

FIXTURE_SURVEY = json.dumps({
    "jbzl": {
        "gsmc": "贵州茅台酒股份有限公司",
        "ywmc": "Kweichow Moutai Co.,Ltd.",
        "agdm": "600519",
        "agjc": "贵州茅台",
        "zqlb": "上交所主板A股",
        "sshy": "酿酒行业",
        "ssjys": "上海证券交易所",
        "frdb": "陈华",
        "dsz": "陈华",
        "zjl": "王莉(代)",
        "dm": "余思明",
        "gsdj": "9152000071430580XT",
        "zczb": "12.50亿",
        "zcdz": "贵州省仁怀市茅台镇",
        "jyfw": "茅台酒及系列酒的生产与销售",
        "gsjj": "公司成立于1999年",
    },
    "fxxg": {"ssrq": "2001-08-27", "mgfxj": "31.39", "clrq": "1999-11-20"},
    "SecuCode": "SH600519",
    "SecurityCode": "600519",
})

FIXTURE_HOLDERS = {
    "survey": json.loads(FIXTURE_SURVEY),
    "holders": [
        {"HOLDER_RANK": 1, "HOLDER_NAME": "中国贵州茅台酒厂(集团)有限责任公司",
         "HOLD_NUM_RATIO": 54.5, "HOLD_NUM": 681282935,
         "HOLD_NUM_CHANGE": "不变", "END_DATE": "2026-06-30 00:00:00"},
        {"HOLDER_RANK": 2, "HOLDER_NAME": "香港中央结算有限公司",
         "HOLD_NUM_RATIO": 5.2, "HOLD_NUM": 65000000,
         "HOLD_NUM_CHANGE": "增持", "END_DATE": "2026-06-30 00:00:00"},
    ],
}


def _adapter(merged, robots_ok=True):
    return EastmoneyF10Lookup(
        execute_query=lambda url, headers: (200, merged, ""),
        robots_checker=lambda domain, url: robots_ok,
        sleeper=lambda s: None,
    )


def test_normalize_stock_code_variants():
    assert normalize_stock_code("600519") == "SH600519"
    assert normalize_stock_code("SH600519") == "SH600519"
    assert normalize_stock_code("sh600519") == "SH600519"
    assert normalize_stock_code("600519.SH") == "SH600519"
    assert normalize_stock_code("000001") == "SZ000001"
    assert normalize_stock_code("SZ300750") == "SZ300750"
    assert normalize_stock_code("430000") == "BJ430000"


def test_normalize_stock_code_rejects_garbage():
    assert normalize_stock_code("贵州茅台") is None
    assert normalize_stock_code("12345") is None
    assert normalize_stock_code("") is None
    assert normalize_stock_code("ABCDEF") is None


def test_build_url_uses_normalized_code():
    a = _adapter({})
    url = a._build_url("600519")
    assert "code=SH600519" in url
    assert url.startswith("https://emweb.securities.eastmoney.com/")


def test_extract_company_fields_and_holders():
    a = _adapter(FIXTURE_HOLDERS)
    out = a.query("600519")
    assert out["response_status"] == 200
    f = out["fields"]
    assert f["company_name"] == "贵州茅台酒股份有限公司"
    assert f["legal_rep"] == "陈华"
    assert f["credit_code"] == "9152000071430580XT"
    assert f["reg_capital"] == "12.50亿"
    assert f["ipo_date"] == "2001-08-27"
    assert f["holder_count"] == 2
    assert f["top_holders"][0]["name"] == "中国贵州茅台酒厂(集团)有限责任公司"
    assert f["top_holders"][0]["ratio"] == 54.5
    assert f["top_holders"][0]["report_date"] == "2026-06-30"
    assert f["source"] == "eastmoney_f10"


def test_extract_skips_placeholder_values():
    a = _adapter({"survey": {"jbzl": {"gsmc": "测试公司", "bgdm": "--", "lxdh": ""}}, "holders": []})
    out = a.query("600519")
    assert out["fields"]["company_name"] == "测试公司"
    assert "bgdm" not in out["fields"]
    assert "phone" not in out["fields"]
    assert "top_holders" not in out["fields"]


def test_empty_survey_returns_empty_fields():
    a = _adapter({"survey": {}, "holders": []})
    out = a.query("600519")
    assert out["fields"] == {}
    assert out["field_count"] == 0


def test_robots_disallowed_blocks_query():
    a = _adapter(FIXTURE_HOLDERS, robots_ok=False)
    out = a.query("600519")
    assert out["fields"] == {}
    assert "robots_txt_disallowed" in out["error"]


def test_audit_trail_integrity():
    a = _adapter(FIXTURE_HOLDERS)
    a.query("600519")
    assert a.audit.verify_integrity()
    trail = a.audit.get_trail()
    assert trail[0]["source_domain"] == "emweb.securities.eastmoney.com"
    assert trail[0]["data_boundary"] == "fully_public"
    assert not trail[0]["requires_credentials"]


def test_query_subject_is_hashed_not_plaintext():
    a = _adapter(FIXTURE_HOLDERS)
    out = a.query("600519")
    assert out["query_subject_hash"] != "600519"
    assert len(out["query_subject_hash"]) == 12
