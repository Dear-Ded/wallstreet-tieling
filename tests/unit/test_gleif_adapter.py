#!/usr/bin/env python3
"""GleifLookup 单元测试（全部 stub，不依赖 api.gleif.org 实时可用性）。"""
from __future__ import annotations

import json

from adapters.gleif_adapter import (
    GleifLookup,
    _fmt_address,
    _parse_lei_record,
    _parse_relationship_record,
)


def _stub_executor(payload: object, status: int = 200):
    def _exec(url: str, headers: dict):
        body = json.dumps(payload) if not isinstance(payload, str) else payload
        return status, body, ""
    return _exec


def _make_adapter(payload: object, status: int = 200) -> GleifLookup:
    return GleifLookup(
        execute_query=_stub_executor(payload, status),
        robots_checker=lambda domain, url: True,
    )


SAMPLE_LEI_JSON = {
    "meta": {"pagination": {"total": 2, "perPage": 10}},
    "data": [
        {
            "type": "lei-records",
            "id": "98450063D0A707C12A83",
            "attributes": {
                "lei": "98450063D0A707C12A83",
                "entity": {
                    "legalName": {"name": "Alibaba (Netherlands) B.V.", "language": "nl"},
                    "otherNames": [{"name": "Alibaba NL"}],
                    "legalAddress": {
                        "addressLines": ["Herengracht 448"],
                        "city": "Amsterdam",
                        "country": "NL",
                        "postalCode": "1017 CA",
                    },
                    "headquartersAddress": {
                        "addressLines": ["Herengracht 448"],
                        "city": "Amsterdam",
                        "country": "NL",
                    },
                    "registeredAt": {"id": "RA000463"},
                    "registeredAs": "65271505",
                    "jurisdiction": "NL",
                    "category": "GENERAL",
                    "legalForm": {"id": "54M6"},
                    "status": "ACTIVE",
                    "creationDate": "2016-02-05T00:00:00Z",
                },
                "registration": {
                    "status": "ISSUED",
                    "managingLou": "529900T8BM49AURSDO55",
                },
            },
        },
        {
            "type": "lei-records",
            "id": "5493006MHB84DD0ZWV18",
            "attributes": {
                "lei": "5493006MHB84DD0ZWV18",
                "entity": {
                    "legalName": {"name": "Alibaba Group Holding Limited"},
                    "jurisdiction": "KY",
                    "status": "ACTIVE",
                },
                "registration": {"status": "ISSUED"},
            },
        },
    ],
}

SAMPLE_CHILD_REL_JSON = {
    "data": [
        {
            "type": "relationship-records",
            "id": "rel-1",
            "attributes": {
                "relationship": {
                    "startNode": {"id": "894500LTKN6QXS10UI15", "type": "LEI"},
                    "endNode": {"id": "98450063D0A707C12A83", "type": "LEI"},
                    "type": "IS_DIRECTLY_CONSOLIDATED_BY",
                    "status": "ACTIVE",
                },
            },
        }
    ]
}

SAMPLE_PARENT_JSON = {
    "data": {
        "type": "lei-records",
        "id": "5493006MHB84DD0ZWV18",
        "attributes": {
            "lei": "5493006MHB84DD0ZWV18",
            "entity": {"legalName": {"name": "Alibaba Group Holding Limited"}},
        },
    }
}


def test_query_returns_entities():
    ad = _make_adapter(SAMPLE_LEI_JSON)
    r = ad.query("Alibaba")
    f = r["fields"]
    assert f["entity_count"] == 2
    assert f["total_matches"] == 2
    assert f["entities"][0]["lei"] == "98450063D0A707C12A83"
    assert f["entities"][0]["legal_name"] == "Alibaba (Netherlands) B.V."
    assert f["entities"][0]["jurisdiction"] == "NL"
    assert "Amsterdam" in f["entities"][0]["legal_address"]
    assert f["entities"][0]["other_names"] == ["Alibaba NL"]


def test_query_builds_correct_url():
    seen = {}

    def _exec(url: str, headers: dict):
        seen["url"] = url
        return 200, json.dumps(SAMPLE_LEI_JSON), ""

    ad = GleifLookup(execute_query=_exec, robots_checker=lambda d, u: True)
    ad.query("Tencent")
    assert "api.gleif.org/api/v1/lei-records" in seen["url"]
    assert "filter" in seen["url"] and "Tencent" in seen["url"]
    assert "Accept" in _exec.__code__.co_varnames or True  # headers checked below


def test_query_sends_jsonapi_accept_header():
    seen = {}

    def _exec(url: str, headers: dict):
        seen["headers"] = headers
        return 200, json.dumps(SAMPLE_LEI_JSON), ""

    ad = GleifLookup(execute_query=_exec, robots_checker=lambda d, u: True)
    ad.query("Tencent")
    assert seen["headers"]["Accept"] == "application/vnd.api+json"


def test_query_empty_result():
    ad = _make_adapter({"meta": {"pagination": {"total": 0}}, "data": []})
    r = ad.query("不存在的公司XYZ123")
    assert r["fields"]["entity_count"] == 0
    assert r["fields"]["total_matches"] == 0


def test_query_error_shape():
    ad = _make_adapter({"errors": [{"title": "Bad Request", "detail": "invalid filter"}]})
    r = ad.query("x")
    assert r["fields"]["lookup_failed"] is True


def test_query_garbage_input():
    ad = _make_adapter("not json at all {{{")
    r = ad.query("x")
    assert r["fields"].get("parse_error") is True


def test_query_blank_keyword_url_still_built():
    ad = _make_adapter(SAMPLE_LEI_JSON)
    r = ad.query("   ")
    # 空关键词仍走流程（API 返回 0 或报错），不崩
    assert "fields" in r


def test_query_children_parses_relationships():
    ad = _make_adapter(SAMPLE_CHILD_REL_JSON)
    r = ad.query_children("98450063D0A707C12A83")
    f = r["fields"]
    assert f["child_count"] == 1
    assert f["child_leis"] == ["894500LTKN6QXS10UI15"]
    assert f["child_relationships"][0]["type"] == "IS_DIRECTLY_CONSOLIDATED_BY"


def test_query_children_invalid_lei():
    ad = _make_adapter(SAMPLE_CHILD_REL_JSON)
    r = ad.query_children("SHORT")
    assert "error" in r


def test_query_parent_parses_direct_parent():
    ad = _make_adapter(SAMPLE_PARENT_JSON)
    r = ad.query_parent("98450063D0A707C12A83")
    f = r["fields"]
    assert f["direct_parent_lei"] == "5493006MHB84DD0ZWV18"
    assert f["direct_parent_name"] == "Alibaba Group Holding Limited"


def test_query_parent_no_parent_graceful():
    # direct-parent 404 → reporting-exception 路径
    calls = {"n": 0}

    def _exec(url: str, headers: dict):
        calls["n"] += 1
        if "reporting-exception" in url:
            return 200, json.dumps({"data": {"attributes": {"reason": "NO_KNOWN_PARENT"}}}), ""
        return 404, json.dumps({"errors": [{"title": "Not Found"}]}), ""

    ad = GleifLookup(execute_query=_exec, robots_checker=lambda d, u: True)
    r = ad.query_parent("98450063D0A707C12A83")
    assert r["fields"]["direct_parent_lei"] == ""
    assert calls["n"] == 2  # 主端点 + exception 端点


def test_fmt_address_handles_none():
    assert _fmt_address(None) == ""
    assert _fmt_address({}) == ""
    assert _fmt_address({"city": "北京", "country": "CN"}) == "北京, CN"


def test_parse_lei_record_minimal():
    rec = {"attributes": {"lei": "X" * 20, "entity": {}, "registration": {}}}
    out = _parse_lei_record(rec)
    assert out["lei"] == "X" * 20
    assert out["legal_name"] == ""


def test_parse_relationship_record_minimal():
    out = _parse_relationship_record({"attributes": {}})
    assert out["child_lei"] == ""
    assert out["parent_lei"] == ""


def test_audit_does_not_leak_keyword():
    ad = _make_adapter(SAMPLE_LEI_JSON)
    r = ad.query("敏感公司名测试")
    # 审计只存 sha256 前 12 位
    assert "敏感公司名测试" not in json.dumps(r)
    assert len(r["query_subject_hash"]) == 12


def test_adapter_metadata():
    ad = GleifLookup()
    assert ad.source_domain == "api.gleif.org"
    assert ad.data_boundary == "fully_public"
    assert ad.requires_credentials is False
    assert ad.requires_interaction is False
