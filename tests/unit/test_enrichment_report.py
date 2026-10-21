#!/usr/bin/env python3
"""Focused tests: intel-enrichment rendering into report sections.

Covers core/enrichment_report.py (pure rendering) and the wiring in
core/investigation.py::_report_markdown (with/without enrichments).
"""

from core.enrichment_report import (
    extract_enrichments,
    payload_kind,
    render_enrichment_html,
    render_enrichment_markdown,
    render_enrichments_html,
    render_enrichments_markdown,
)

DOMAIN_PAYLOAD = {
    "type": "domain_intel_enrichment",
    "domain": "example.com",
    "sources": {
        "urlscan": {"fields": {
            "total_scans": 2,
            "recent_scans": [
                {"scanned_url": "https://example.com/",
                 "scan_date": "2026-10-01T00:00:00",
                 "page_title": "Example",
                 "result_url": "https://urlscan.io/result/abc/"},
            ],
        }},
        "hackertarget": {"fields": {
            "dnslookup": {"records": {"A": ["93.184.216.34"]}},
            "reverseiplookup": {"neighbor_count": 25,
                                "neighbors": ["a.com", "b.com"]},
        }},
        "ipapi": {"fields": {
            "country": "US", "city": "Los Angeles",
            "org": "Example Org", "as": "AS15133",
            "is_hosting": True, "is_proxy": False,
        }},
    },
    "source_count": 3,
    "risk_notes": ["同 IP 存在 25 个邻居域名，共享主机"],
    "policy": "基础设施公开数据；risk_notes 仅为线索提示。",
}

PEOPLE_PAYLOAD = {
    "type": "people_lead_graph",
    "subject_hash": "abc123def456",
    "identifiers_provided": {"name": True, "email": True,
                             "username": True, "github_username": False},
    "sources": {
        "email_intel": {"fields": {"domain": "example.com",
                                   "is_disposable": False,
                                   "is_role_account": False}},
        "github_deep": {"fields": {
            "profile": {"login": "alice", "name": "Alice",
                        "company": "Example Inc", "public_repos": 12},
            "affiliations": {"orgs": [{"login": "example-org"}]},
        }},
        "username_footprint": {"fields": {
            "platforms_found": 5, "coverage_ratio": "5/692",
            "by_category": {"code": ["GitHub"]},
        }},
        "officer_records": {"error": "upstream timeout"},
    },
    "source_count": 4,
    "corroborations": [
        {"type": "domain_company_consistent",
         "detail": "邮箱域名 example.com 与 GitHub 公开公司一致（线索，非断言）"},
    ],
    "policy": "corroborations 仅为线索提示，不做身份断言。",
}

ASSOCIATION_PAYLOAD = {
    "seed": {"type": "phone", "value": "13800001111"},
    "entities": [
        {"type": "person", "value": "张三", "display": "张三"},
        {"type": "phone", "value": "13800001111", "display": "13800001111"},
    ],
    "associations": [
        {"from": "张三", "to": "13800001111",
         "relation": "same_phone", "confidence": 0.95},
    ],
    "interesting_patterns": [
        {"pattern_type": "possible_family_with",
         "detail": "同姓聚类：张三 / 张小三（疑似，需复核）",
         "confidence": 0.6},
    ],
    "risk_scores": {
        "ranked": [{"display": "张三", "score": 25, "level": "中"}],
        "count": 1,
        "disclaimer": "评分仅供排序线索。",
    },
    "disclaimer": "Associations are investigative leads.",
}

CONTACTS_PAYLOAD = {
    "contacts": [
        {"type": "mobile", "value": "13800001111",
         "confidence": 0.9, "sources": ["微博简介"]},
        {"type": "wechat", "value": "alice_wx", "confidence": 0.7},
    ],
    "by_entity": {},
    "summary": {"note": "公开文本挖掘"},
}


def test_payload_kind_detection():
    assert payload_kind(DOMAIN_PAYLOAD) == "domain"
    assert payload_kind(PEOPLE_PAYLOAD) == "people"
    assert payload_kind(ASSOCIATION_PAYLOAD) == "association"
    assert payload_kind(CONTACTS_PAYLOAD) == "contacts"
    assert payload_kind({}) == "unknown"
    assert payload_kind({"type": "whatever"}) == "unknown"
    assert payload_kind(None) == "unknown"


def test_extract_enrichments_from_packet():
    packet = {
        "company": "Demo",
        "enrichment": DOMAIN_PAYLOAD,
        "people_enrichment": PEOPLE_PAYLOAD,
        "entity_association": ASSOCIATION_PAYLOAD,
        "unrelated": {"type": "something_else"},
    }
    found = extract_enrichments(packet)
    kinds = {payload_kind(p) for p in found}
    assert kinds == {"domain", "people", "association"}


def test_extract_enrichments_dedup_and_scan():
    packet = {
        "a": DOMAIN_PAYLOAD,
        "b": dict(DOMAIN_PAYLOAD),  # duplicate
        "enrichments": [CONTACTS_PAYLOAD],
    }
    found = extract_enrichments(packet)
    assert sum(1 for p in found if payload_kind(p) == "domain") == 1
    assert any(payload_kind(p) == "contacts" for p in found)


def test_extract_enrichments_empty_packet():
    assert extract_enrichments({}) == []
    assert extract_enrichments(None) == []


def test_domain_markdown_sections():
    lines = render_enrichment_markdown(DOMAIN_PAYLOAD)
    text = "\n".join(lines)
    assert "## 情报富化 · 域名基础设施" in text
    assert "example.com" in text
    assert "urlscan" in text
    assert "93.184.216.34" in text
    assert "25 个" in text
    assert "Los Angeles" in text
    assert "线索（lead" in text
    assert "https://urlscan.io/result/abc/" in text  # 来源链接
    assert "⚠️" in text  # risk note


def test_people_markdown_sections():
    lines = render_enrichment_markdown(PEOPLE_PAYLOAD)
    text = "\n".join(lines)
    assert "## 情报富化 · 人物公开情报" in text
    assert "画像摘要" in text
    assert "GitHub 画像" in text
    assert "alice" in text
    assert "跨平台身份" in text
    assert "5 个" in text
    assert "交叉印证" in text
    assert "数据源失败" in text  # officer_records error degrades gracefully
    assert "线索（lead" in text


def test_association_markdown_sections():
    lines = render_enrichment_markdown(ASSOCIATION_PAYLOAD)
    text = "\n".join(lines)
    assert "## 情报富化 · 实体关联发现" in text
    assert "13800001111" in text
    assert "same_phone" in text
    assert "风险评分" in text
    assert "25 分" in text


def test_contacts_markdown_sections():
    lines = render_enrichment_markdown(CONTACTS_PAYLOAD)
    text = "\n".join(lines)
    assert "## 情报富化 · 联系方式提取" in text
    assert "手机" in text
    assert "微信" in text
    assert "alice_wx" in text


def test_empty_enrichment_renders_nothing():
    assert render_enrichment_markdown({}) == []
    assert render_enrichment_markdown(
        {"type": "domain_intel_enrichment", "domain": "x.com",
         "sources": {}, "risk_notes": []}) == []
    assert render_enrichment_markdown(
        {"type": "people_lead_graph", "sources": {},
         "corroborations": []}) == []
    assert render_enrichments_markdown([]) == []
    assert render_enrichments_html([]) == ""


def test_people_note_only_degrades():
    payload = {"type": "people_lead_graph", "sources": {},
               "corroborations": [],
               "note": "未提供任何人物情报适配器，未执行查询（默认关闭）"}
    lines = render_enrichment_markdown(payload)
    text = "\n".join(lines)
    assert "人物公开情报" in text
    assert "未执行查询" in text


def test_html_escaping_and_structure():
    evil = dict(DOMAIN_PAYLOAD)
    evil["domain"] = "<script>alert(1)</script>"
    frag = render_enrichment_html(evil)
    assert "<script>" not in frag
    assert "&lt;script&gt;" in frag
    assert "visual-panel" in frag
    assert "metric-strip" in frag


def test_html_fragments_for_all_kinds():
    for payload in (DOMAIN_PAYLOAD, PEOPLE_PAYLOAD,
                    ASSOCIATION_PAYLOAD, CONTACTS_PAYLOAD):
        frag = render_enrichment_html(payload)
        assert "visual-panel" in frag, payload_kind(payload)
        assert "情报富化" in frag
    combined = render_enrichments_html(
        [DOMAIN_PAYLOAD, PEOPLE_PAYLOAD])
    assert combined.count("visual-panel") == 2


def test_report_markdown_wiring_with_and_without():
    from core.investigation import _report_markdown
    base = dict(
        company="测试公司", mode="standard",
        risk_brief={}, profile_brief={}, enterprise_cognition={},
        evidence_ledger=[], source_provenance={},
        source_failure_summary={}, risk_event_summary={},
        persona_surface={}, monitoring_seed={},
        next_actions=[],
    )
    without = _report_markdown(**base)
    assert "情报富化" not in without
    with_enrich = _report_markdown(
        **base, enrichments=[DOMAIN_PAYLOAD, PEOPLE_PAYLOAD])
    assert "情报富化 · 域名基础设施" in with_enrich
    assert "情报富化 · 人物公开情报" in with_enrich
    # section sits before 下一步
    assert with_enrich.index("情报富化") < with_enrich.index("## 下一步")
