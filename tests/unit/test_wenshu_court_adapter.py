#!/usr/bin/env python3
"""Tests for WenshuCaseLookup (browser-assisted adapter)."""

import json

from adapters.wenshu_court_adapter import WenshuCaseLookup


def _make_adapter():
    return WenshuCaseLookup(
        robots_checker=lambda domain, url: True,
    )


def test_query_returns_interaction_required():
    """query() 不直接发起请求,返回 interaction_required."""
    adapter = _make_adapter()
    result = adapter.query("沙县小吃")
    assert result["error"] == "interaction_required"
    assert "interaction_instructions" in result
    assert "wenshu.court.gov.cn" in result["interaction_instructions"]
    assert result["source_domain"] == "wenshu.court.gov.cn"
    assert result["query_subject_hash"]  # 审计哈希仍生成


def test_requires_interaction_flag():
    adapter = _make_adapter()
    assert adapter.requires_interaction is True
    assert adapter.requires_credentials is False
    assert adapter.data_boundary == "fully_public"


def test_parse_browser_result_extracts_cases():
    """parse_browser_result() 正确提取案件字段."""
    adapter = _make_adapter()
    mock_response = {
        "code": 1,
        "success": True,
        "result": {
            "count": 2,
            "resultList": [
                {
                    "s1": "张三诉李四买卖合同纠纷一案",
                    "s2": "北京市朝阳区人民法院",
                    "s5": "abc123docid",
                    "s6": "民事判决书",
                    "s7": "(2024)京0105民初12345号",
                    "s8": "民事案件",
                    "s11": "买卖合同纠纷",
                    "s17": "张三,李四",
                    "s31": "2024-05-20",
                },
                {
                    "s1": "王五诉赵六租赁合同纠纷",
                    "s2": "上海市浦东新区人民法院",
                    "s5": "def456docid",
                    "s6": "民事裁定书",
                    "s7": "(2024)沪0115民初67890号",
                    "s8": "民事案件",
                    "s11": "租赁合同纠纷",
                    "s17": "王五,赵六",
                    "s31": "2024-06-15",
                },
            ],
        },
    }
    result = adapter.parse_browser_result(mock_response)
    fields = result["fields"]
    assert fields["total_count"] == 2
    assert len(fields["cases"]) == 2

    first = fields["cases"][0]
    assert first["title"] == "张三诉李四买卖合同纠纷一案"
    assert first["court"] == "北京市朝阳区人民法院"
    assert first["case_number"] == "(2024)京0105民初12345号"
    assert first["doc_type"] == "民事判决书"
    assert "abc123docid" in first["doc_url"]


def test_parse_browser_result_accepts_json_string():
    """parse_browser_result() 接受 JSON 字符串输入."""
    adapter = _make_adapter()
    mock_response = json.dumps({
        "result": {
            "count": 1,
            "resultList": [{"s1": "测试案件", "s7": "(2024)测试1号"}],
        },
    })
    result = adapter.parse_browser_result(mock_response)
    assert result["fields"]["total_count"] == 1
    assert result["fields"]["cases"][0]["title"] == "测试案件"


def test_parse_browser_result_handles_garbage():
    """parse_browser_result() 优雅处理无效输入."""
    adapter = _make_adapter()
    result = adapter.parse_browser_result("not valid json {{{")
    assert result["fields"]["parse_error"] is True

    result = adapter.parse_browser_result({})
    assert result["fields"]["total_count"] == 0
    assert result["fields"]["cases"] == []


def test_audit_trail_recorded():
    """query() 仍记录审计日志."""
    adapter = _make_adapter()
    adapter.query("测试商户")
    trail = adapter.audit.get_trail()
    assert len(trail) == 1
    assert trail[0]["source_domain"] == "wenshu.court.gov.cn"


def test_parse_doc_text_extracts_kinship():
    """parse_doc_text(): 文书全文 -> 亲属关系表述（strong）. (亲属关系 lane)"""
    adapter = _make_adapter()
    doc = (
        "原告张三与被告李四系夫妻关系，双方于 2020 年登记结婚。"
        "婚生子张小明现年 5 岁。"
    )
    result = adapter.parse_doc_text(doc, focus_name="张三", case_number="(2024)沪01民1号")
    stmts = result["kinship_statements"]
    assert result["statement_count"] >= 1
    kinds = {(s["person_a"], s["person_b"], s["relation_kind"]) for s in stmts}
    assert ("张三", "李四", "spouse") in kinds
    assert all(s["evidence_level"] == "strong" for s in stmts)
    assert all("裁判文书" in s["source_ref"] for s in stmts)


def test_parse_doc_text_no_kinship():
    adapter = _make_adapter()
    result = adapter.parse_doc_text("本院认为，合同合法有效，应予履行。")
    assert result["kinship_statements"] == []
    assert result["statement_count"] == 0


def test_extract_kinship_from_doc_text_static():
    stmts = WenshuCaseLookup.extract_kinship_from_doc_text(
        "王五系赵六之子。", focus_name="王五")
    assert len(stmts) == 1
    assert stmts[0]["relation_kind"] == "parent_child"
    assert stmts[0]["evidence_level"] == "strong"
