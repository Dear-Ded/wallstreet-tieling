#!/usr/bin/env python3
"""Tests for GdCreditCompanyLookup (Guangdong credit platform adapter)."""

import json
from unittest import mock

from adapters.gd_credit_adapter import GdCreditCompanyLookup


def _make_adapter():
    return GdCreditCompanyLookup(
        robots_checker=lambda domain, url: True,
    )


def test_query_returns_interaction_required():
    """搜索需要滑块验证码,query() 返回 interaction_required."""
    adapter = _make_adapter()
    result = adapter.query("腾讯")
    assert result["error"] == "interaction_required"
    assert "interaction_instructions" in result
    assert "credit.gd.gov.cn" in result["interaction_instructions"]
    assert result["source_domain"] == "credit.gd.gov.cn"
    assert result["query_subject_hash"]  # 审计哈希仍生成,不存原文


def test_requires_interaction_flag():
    adapter = _make_adapter()
    assert adapter.requires_interaction is True
    assert adapter.requires_credentials is False
    assert adapter.data_boundary == "fully_public"


def test_parse_browser_result_extracts_companies():
    """parse_browser_result() 正确提取搜索结果中的企业和 masterdataid."""
    adapter = _make_adapter()
    mock_response = {
        "code": 200,
        "data": {
            "total": 2,
            "rows": [
                {
                    "ZTMC": "开平市枫源纸品有限公司",
                    "TYSHXYDM": "91440783MA520W5H6C",
                    "FDDBRXM": "谭振尧",
                    "ZHUSUO": "开平市水口镇新风开发区红新路1号-6",
                    "CXZT": "存续（在营、开业、在册）",
                    "MASTERDATAID": "GDS_e0d4df08af9887a96bcb595e57a2c0d7",
                    "MASTERDATAIDENCRYPT": "C92C2948",
                },
                {
                    "ZTMC": "测试公司",
                    "MASTERDATAID": "GDS_test123",
                },
            ],
        },
    }
    parsed = adapter.parse_browser_result(mock_response)
    fields = parsed["fields"]
    assert fields["total_count"] == 2
    assert len(fields["companies"]) == 2
    first = fields["companies"][0]
    assert first["company_name"] == "开平市枫源纸品有限公司"
    assert first["credit_code"] == "91440783MA520W5H6C"
    assert first["legal_rep"] == "谭振尧"
    assert first["masterdataid"] == "GDS_e0d4df08af9887a96bcb595e57a2c0d7"


def test_parse_browser_result_accepts_json_string():
    adapter = _make_adapter()
    raw = json.dumps({"code": 200, "data": {"total": 0, "rows": []}})
    parsed = adapter.parse_browser_result(raw)
    assert parsed["fields"]["total_count"] == 0
    assert parsed["fields"]["companies"] == []


def test_parse_browser_result_handles_garbage():
    adapter = _make_adapter()
    parsed = adapter.parse_browser_result("not json {{{")
    assert parsed["fields"]["parse_error"] is True
    parsed2 = adapter.parse_browser_result(None)
    assert parsed2["fields"]["parse_error"] is True


def test_query_detail_extracts_fields():
    """query_detail() 全自动,正确提取企业信用详情字段."""
    adapter = _make_adapter()
    mock_payload = {
        "code": 200,
        "data": {
            "MASTERDATAID": "GDS_e0d4df08af9887a96bcb595e57a2c0d7",
            "ZTMC": "开平市枫源纸品有限公司",
            "TYSHXYDM": "91440783MA520W5H6C",
            "FDDBRXM": "谭振尧",
            "CLRQ": "2018-07-17",
            "ZHUSUO": "开平市水口镇新风开发区红新路1号-6",
            "QYLX": "有限责任公司(自然人独资)",
            "CXZT": "存续（在营、开业、在册）",
            "ZCZB": "100.0",
            "SSHY": "制造业",
            "MASTERDATAIDENCRYPT": "C92C2948",
        },
    }
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch(
        "urllib.request.urlopen", return_value=mock_resp
    ):
        result = adapter.query_detail("GDS_e0d4df08af9887a96bcb595e57a2c0d7")

    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["found"] is True
    assert fields["company_name"] == "开平市枫源纸品有限公司"
    assert fields["credit_code"] == "91440783MA520W5H6C"
    assert fields["legal_rep"] == "谭振尧"
    assert fields["established_date"] == "2018-07-17"
    assert fields["address"] == "开平市水口镇新风开发区红新路1号-6"
    assert fields["registered_capital"] == "100.0"
    assert fields["industry"] == "制造业"
    # 审计不存原文
    assert "GDS_e0d4df08af9887a96bcb595e57a2c0d7" not in json.dumps(
        adapter.audit.get_trail()
    )


def test_query_detail_handles_network_error():
    adapter = _make_adapter()
    with mock.patch(
        "urllib.request.urlopen", side_effect=TimeoutError("timed out")
    ):
        result = adapter.query_detail("GDS_xxx")
    assert "error" in result
    assert "detail_request_failed" in result["error"]


def test_query_hot_extracts_list():
    """query_hot() 全自动,返回热搜企业榜."""
    adapter = _make_adapter()
    mock_payload = {
        "code": 200,
        "data": [
            {"ztmc": "开平市枫源纸品有限公司",
             "masterdataid": "GDS_e0d4df08af9887a96bcb595e57a2c0d7",
             "eid": "C92C2948", "hotnum": 11},
        ],
    }
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("urllib.request.urlopen", return_value=mock_resp):
        result = adapter.query_hot()

    assert result["response_status"] == 200
    companies = result["fields"]["companies"]
    assert len(companies) == 1
    assert companies[0]["company_name"] == "开平市枫源纸品有限公司"
    assert companies[0]["masterdataid"] == "GDS_e0d4df08af9887a96bcb595e57a2c0d7"
