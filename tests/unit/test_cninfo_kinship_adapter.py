#!/usr/bin/env python3
"""Tests for adapters/cninfo_kinship_adapter.py — 巨潮资讯亲属关系抽取."""
from __future__ import annotations

import json

from adapters.cninfo_kinship_adapter import CninfoKinshipLookup

# hisAnnouncement/query 返回形状（2026-10-21 实测采样，已脱敏裁剪）
_SEARCH_FIXTURE = {
    "totalAnnouncement": 2,
    "announcements": [
        {
            "secCode": "002388", "secName": "新亚制程",
            "announcementId": "1225613004",
            "announcementTitle": "简式权益变动报告书（张三）",
            "announcementTime": 1792512000000,
            "adjunctUrl": "finalpage/2026-10-21/1225613004.PDF",
        },
        {
            "secCode": "603825", "secName": "ST华扬",
            "announcementId": "1225612883",
            "announcementTitle": "关于日常关联交易的公告",
            "announcementTime": 1792512000000,
            "adjunctUrl": "finalpage/2026-10-21/1225612883.PDF",
        },
    ],
}

_DISCLOSURE_TEXT = """
证券代码：002388 证券简称：新亚制程

简式权益变动报告书

一、信息披露义务人介绍
信息披露义务人张三与李四系夫妻关系，二人合计持有公司股份 10.97%。

二、信息披露义务人的一致行动关系说明
张三、李四夫妇为一致行动人。
"""


def test_parse_announcement_list():
    anns = CninfoKinshipLookup.parse_announcement_list(_SEARCH_FIXTURE)
    assert len(anns) == 2
    a0 = anns[0]
    assert a0["sec_code"] == "002388"
    assert a0["title"] == "简式权益变动报告书（张三）"
    assert a0["date"] == "2026-10-21"
    assert a0["pdf_url"] == (
        "http://static.cninfo.com.cn/finalpage/2026-10-21/1225613004.PDF")


def test_parse_announcement_list_bad_input():
    assert CninfoKinshipLookup.parse_announcement_list("not json") == []
    assert CninfoKinshipLookup.parse_announcement_list(None) == []


def test_extract_kinship_from_text():
    sts = CninfoKinshipLookup.extract_kinship_from_text(
        _DISCLOSURE_TEXT, "张三", "《简式权益变动报告书》")
    kinds = {(s["person_a"], s["person_b"], s["relation_kind"]) for s in sts}
    assert ("张三", "李四", "spouse") in kinds
    assert all(s["evidence_level"] == "exact" for s in sts)
    assert all("简式权益变动报告书" in s["source_ref"] for s in sts)


def _queryable(monkeypatch, pdf_text=_DISCLOSURE_TEXT):
    adapter = CninfoKinshipLookup(
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )
    monkeypatch.setattr(
        adapter, "_post_search",
        lambda keyword, page_size: (200, json.dumps(_SEARCH_FIXTURE), ""))
    calls = {"n": 0}

    def _fake_fetch(pdf_url):
        calls["n"] += 1
        return (pdf_text, "")

    monkeypatch.setattr(adapter, "_fetch_pdf_text", _fake_fetch)
    return adapter, calls


def test_query_end_to_end(monkeypatch):
    adapter, calls = _queryable(monkeypatch)
    result = adapter.query("张三")
    assert result["response_status"] == 200
    assert result["data_boundary"] == "fully_public"
    fields = result["fields"]
    assert fields["total_count"] == 2
    # 权益变动报告书优先抓取（max_pdfs=2，标题加权排序）
    assert calls["n"] == 2
    assert fields["pdfs_fetched"] == 2
    kinds = {(s["person_a"], s["person_b"], s["relation_kind"])
             for s in fields["kinship_statements"]}
    assert ("张三", "李四", "spouse") in kinds
    st = fields["kinship_statements"][0]
    assert st["evidence_level"] == "exact"
    assert st["pdf_url"].startswith("http://static.cninfo.com.cn/")


def test_query_fetch_text_off(monkeypatch):
    adapter, calls = _queryable(monkeypatch)
    result = adapter.query("张三", fetch_text=False)
    assert result["fields"]["kinship_statements"] == []
    assert calls["n"] == 0
    # 公告元数据仍作为线索返回
    assert len(result["fields"]["announcements"]) == 2


def test_query_pdf_unavailable_graceful(monkeypatch):
    adapter, calls = _queryable(monkeypatch, pdf_text=None)

    def _fail(pdf_url):
        calls["n"] += 1
        return (None, "pdf_tool_unavailable")

    monkeypatch.setattr(adapter, "_fetch_pdf_text", _fail)
    result = adapter.query("张三", max_pdfs=1)
    assert result["fields"]["kinship_statements"] == []
    assert result["fields"]["announcements"][0].get("pdf_note") == \
        "pdf_tool_unavailable"


def test_adapter_attrs():
    adapter = CninfoKinshipLookup()
    assert adapter.data_boundary == "fully_public"
    assert adapter.requires_credentials is False
    assert adapter.requires_interaction is False
    assert adapter.min_request_interval >= 5.0
    assert adapter.source_domain == "cninfo.com.cn"


def test_query_robots_disallowed(monkeypatch):
    adapter = CninfoKinshipLookup(
        robots_checker=lambda domain, url: False,
        sleeper=lambda s: None,
    )
    result = adapter.query("张三")
    assert "robots_txt_disallowed" in result["error"]
