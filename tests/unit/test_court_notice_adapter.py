#!/usr/bin/env python3
"""Tests for CourtNoticeLookup (人民法院公告网, browser-assisted)."""

import json

import pytest

from adapters.court_notice_adapter import CourtNoticeLookup


@pytest.fixture
def adapter():
    return CourtNoticeLookup()


class TestQuery:
    def test_query_returns_interaction_required(self, adapter):
        result = adapter.query("华为技术有限公司")
        assert result["error"] == "interaction_required"
        assert "interaction_instructions" in result
        assert "rmfygg.court.gov.cn" in result["interaction_instructions"]
        assert result["source_domain"] == "rmfygg.court.gov.cn"
        assert result["data_boundary"] == "fully_public"

    def test_query_audit_no_leak(self, adapter):
        """审计记录不包含原始关键词明文."""
        result = adapter.query("敏感企业名称测试")
        assert result["query_subject_hash"] != "敏感企业名称测试"
        assert len(result["query_subject_hash"]) == 12

    def test_query_empty_keyword(self, adapter):
        result = adapter.query("")
        assert result["error"] == "interaction_required"

    def test_notice_types_documented(self, adapter):
        assert "62" in adapter.NOTICE_TYPES
        assert "66" in adapter.NOTICE_TYPES


class TestParseBrowserResult:
    def test_parse_datatables_format(self, adapter):
        """Liferay DataTables 标准响应格式."""
        raw = json.dumps({
            "iTotalRecords": 2,
            "iTotalDisplayRecords": 2,
            "aaData": [
                ["1", "华为技术有限公司送达公告", "送达公告", "深圳市中级人民法院",
                 "华为技术有限公司", "2026-10-20"],
                ["2", "华为技术有限公司开庭公告", "开庭公告", "广东省高级人民法院",
                 "华为技术有限公司;张三", "2026-10-19"],
            ],
        })
        result = adapter.parse_browser_result(raw)
        fields = result["fields"]
        assert fields["total_count"] == 2
        assert len(fields["notices"]) == 2
        assert "华为" in fields["notices"][0]["title"]
        assert fields["notices"][0]["court"] == "深圳市中级人民法院"
        assert fields["notices"][0]["publish_date"] == "2026-10-20"

    def test_parse_dict_rows(self, adapter):
        raw = {
            "total": 1,
            "data": [
                {
                    "title": "某公司破产公告",
                    "noticeType": "破产公告",
                    "courtName": "北京市第一中级人民法院",
                    "partyName": "某科技有限公司",
                    "caseNo": "(2026)京01破123号",
                    "publishDate": "2026-09-01",
                }
            ],
        }
        result = adapter.parse_browser_result(raw)
        notices = result["fields"]["notices"]
        assert len(notices) == 1
        assert notices[0]["title"] == "某公司破产公告"
        assert notices[0]["case_number"] == "(2026)京01破123号"
        assert notices[0]["court"] == "北京市第一中级人民法院"

    def test_parse_html_stripped(self, adapter):
        """aaData 中的 HTML 标签应被清理."""
        raw = json.dumps({
            "iTotalRecords": 1,
            "aaData": [
                ["1", '<a href="#">测试公告标题</a>', "送达公告",
                 "测试法院", "测试当事人", "2026-10-21"],
            ],
        })
        result = adapter.parse_browser_result(raw)
        notice = result["fields"]["notices"][0]
        assert "<a" not in notice["title"]
        assert notice["title"] == "测试公告标题"

    def test_parse_invalid_json(self, adapter):
        result = adapter.parse_browser_result("not json {{{")
        assert result["fields"]["parse_error"] is True

    def test_parse_non_dict(self, adapter):
        result = adapter.parse_browser_result([1, 2, 3])
        assert result["fields"]["parse_error"] is True

    def test_parse_empty_result(self, adapter):
        raw = json.dumps({"iTotalRecords": 0, "aaData": []})
        result = adapter.parse_browser_result(raw)
        assert result["fields"]["total_count"] == 0
        assert result["fields"]["notices"] == []

    def test_parse_dict_input(self, adapter):
        """直接传 dict 也应工作."""
        result = adapter.parse_browser_result({"total": 0, "data": []})
        assert result["fields"]["total_count"] == 0


class TestAdapterMetadata:
    def test_default_off(self, adapter):
        """默认关闭,需要显式启用."""
        assert adapter.requires_interaction is True
        assert adapter.requires_credentials is False
        assert adapter.data_boundary == "fully_public"

    def test_rate_limit(self, adapter):
        assert adapter.min_request_interval >= 3.0
