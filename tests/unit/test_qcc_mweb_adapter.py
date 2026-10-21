"""Tests for 企查查移动站搜索适配器 (offline fixtures).

Covers: "正确途径"签名 KAT 向量（2026-10-21 经 live server 验证：
该签名带回 Status 200 真实结果）、key 序敏感性、searchMulti 响应解析
(200/201/405)、query() 接线、保守默认配置。No network access.
"""

import json

from adapters.qcc_mweb_adapter import (
    QccMwebSearch,
    parse_search_results,
    sign_search_request,
)

# KAT 向量：2026-10-21 实测，带此签名 POST 返回 Status 200 真实结果。
# body key 序必须为 searchKey/isAgg/pageSize（与客户端一致）。
KAT_BODY = {"searchKey": "阿里巴巴", "isAgg": "false", "pageSize": 5}
KAT_BODY_JSON = '{"searchKey":"阿里巴巴","isAgg":"false","pageSize":5}'
KAT_SIGN_NAME = "272a7bfd6c84f9233ae1"
KAT_SIGN_VALUE = (
    "f3392c4f5cf287f8ed4b54fb9b63f9b545994b4a4235a2aa10f148104716c8687e"
    "38db99d50f63b4e481d432687a57f88ed5dd4278e4e955e79c8e5a42f1804f"
)

RESULT_200_FIXTURE = {
    "Status": 200,
    "Result": [
        {
            "KeyNo": "8c9f7ddc1a7bcee3d1f7676773fe9404",
            "Name": "<em>阿里巴巴</em>（中国）有限公司",
            "Type": 0,
            "No": "330100400013364",
            "OperName": "蒋芳",
            "StartDate": 1174838400000,
            "RegistCapi": "15460.55039万美元",
            "EntType": "有限责任公司(台港澳法人独资)",
            "ShortStatus": "存续",
        },
        {
            "KeyNo": "a59b3c1f33224db1eac88afb1906efbd",
            "Name": "阿里巴巴<em>云</em>计算有限公司",
            "No": "91330106565262471B",
            "OperName": "张勇",
            "StartDate": 1222819200000,
            "RegistCapi": "100000万人民币",
            "ShortStatus": "存续",
        },
    ],
    "Paging": {"PageSize": 5, "PageIndex": 1, "TotalRecords": 8003},
}

RESULT_201_FIXTURE = {"Status": 201}
SIGN_REJECTED_FIXTURE = {
    "status": 405,
    "message": "请通过正确途径使用企查查",
}


def _adapter(payload, status: int = 200):
    return QccMwebSearch(
        page_size=5,
        execute_query=lambda url, headers: (status, payload, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


# ------------------------------------------------------------ 签名 KAT


def test_sign_request_known_answer():
    name, value, body_bytes = sign_search_request(KAT_BODY)
    assert name == KAT_SIGN_NAME
    assert value == KAT_SIGN_VALUE
    assert body_bytes == KAT_BODY_JSON.encode("utf-8")
    assert len(name) == 20 and all(c in "0123456789abcdef" for c in name)
    assert len(value) == 128 and all(c in "0123456789abcdef" for c in value)


def test_sign_request_deterministic():
    outs = {sign_search_request(KAT_BODY) for _ in range(3)}
    assert len(outs) == 1  # 无随机数、无时间戳


def test_sign_request_key_order_matters():
    # key 序不同 -> body 不同 -> 签名不同（服务端按 body 验签）
    other = {"pageSize": 5, "isAgg": "false", "searchKey": "阿里巴巴"}
    assert sign_search_request(other)[1] != KAT_SIGN_VALUE
    assert sign_search_request(other)[2] != KAT_BODY_JSON.encode("utf-8")


def test_sign_request_keyword_sensitive():
    other = {"searchKey": "腾讯", "isAgg": "false", "pageSize": 5}
    name, value, _ = sign_search_request(other)
    assert name == KAT_SIGN_NAME  # header 名只与 path 有关
    assert value != KAT_SIGN_VALUE  # header 值绑定 body


# ------------------------------------------------------------ 响应解析


def test_parse_search_results_200():
    out = parse_search_results(RESULT_200_FIXTURE)
    assert out["blocked"] is False
    assert out["total_records"] == 8003
    assert out["returned"] == 2
    r0 = out["results"][0]
    assert r0["name"] == "阿里巴巴（中国）有限公司"  # <em> 已剥离
    assert r0["key_no"] == "8c9f7ddc1a7bcee3d1f7676773fe9404"
    assert r0["legal_rep"] == "蒋芳"
    assert r0["reg_no"] == "330100400013364"
    assert "15460.55039" in r0["capital"]
    assert r0["founded"] == "2007-03-26"  # 1174838400000 ms
    assert r0["status"] == "存续"
    r1 = out["results"][1]
    assert r1["name"] == "阿里巴巴云计算有限公司"
    assert r1["legal_rep"] == "张勇"


def test_parse_search_results_201_empty():
    out = parse_search_results(RESULT_201_FIXTURE)
    assert out["blocked"] is False
    assert out["results"] == []
    assert out["total_records"] == 0


def test_parse_search_results_405_blocked():
    out = parse_search_results(SIGN_REJECTED_FIXTURE)
    assert out["blocked"] is True
    assert out["block_reason"] == "signature_rejected_405"
    assert out["results"] == []


def test_parse_search_results_garbage():
    out = parse_search_results({"Status": 500})
    assert out["blocked"] is True
    assert out["results"] == []
    out2 = parse_search_results("not json")
    assert out2["blocked"] is True


# ------------------------------------------------------------ 适配器接线


def test_build_url_and_headers():
    a = _adapter(RESULT_200_FIXTURE)
    url = a._build_url("阿里巴巴")
    assert url == "https://m.qcc.com/api/search/searchMulti"
    headers = a._build_headers()
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["Content-Type"] == "application/json"
    assert headers[KAT_SIGN_NAME] == KAT_SIGN_VALUE
    # body 即签名覆盖的精确字节
    assert a._pending_body == KAT_BODY_JSON.encode("utf-8")
    parsed = json.loads(a._pending_body.decode("utf-8"))
    assert list(parsed.keys()) == ["searchKey", "isAgg", "pageSize"]


def test_build_url_rejects_empty_keyword():
    a = _adapter(RESULT_200_FIXTURE)
    for bad in ("", "   "):
        try:
            a._build_url(bad)
            raise AssertionError("should raise")
        except ValueError:
            pass


def test_query_returns_results():
    a = _adapter(RESULT_200_FIXTURE)
    r = a.query("阿里巴巴")
    assert r["response_status"] == 200
    assert r["source_domain"] == "m.qcc.com"
    assert r["data_boundary"] == "fully_public"
    assert r["fields"]["blocked"] is False
    assert r["fields"]["total_records"] == 8003
    assert r["fields"]["results"][0]["key_no"] == \
        "8c9f7ddc1a7bcee3d1f7676773fe9404"


def test_query_signature_rejected_surfaces_blocked():
    a = _adapter(SIGN_REJECTED_FIXTURE)
    r = a.query("阿里巴巴")
    assert r["fields"]["blocked"] is True
    assert r["fields"]["block_reason"] == "signature_rejected_405"


def test_query_empty_results():
    a = _adapter(RESULT_201_FIXTURE)
    r = a.query("不存在的公司xyz123abc")
    assert r["fields"]["blocked"] is False
    assert r["fields"]["results"] == []


def test_adapter_defaults_conservative():
    assert QccMwebSearch.min_request_interval >= 8.0
    assert QccMwebSearch.requires_credentials is False
    assert QccMwebSearch.requires_interaction is False
    assert QccMwebSearch.data_boundary == "fully_public"
    assert QccMwebSearch.source_domain == "m.qcc.com"
