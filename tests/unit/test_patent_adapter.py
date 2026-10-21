"""Tests for adapters/patent_adapter.py (Google Patents)."""

import json
import urllib.parse

from adapters.patent_adapter import PatentLookup, _build_gp_url, _parse_patent_entry


def _sample_response():
    return {
        "results": {
            "total_num_results": 2,
            "total_num_pages": 1,
            "cluster": [
                {
                    "result": [
                        {
                            "id": "patent/CN110086609B/en",
                            "patent": {
                                "title": " 数据备份方法",
                                "snippet": "xxx",
                                "priority_date": "2019-03-27",
                                "filing_date": "2019-03-27",
                                "grant_date": "2020-10-09",
                                "publication_date": "2020-10-09",
                                "inventor": "姚辉",
                                "assignee": "华为技术有限公司",
                                "publication_number": "CN110086609B",
                                "language": "zh",
                            },
                        },
                        {
                            "id": "patent/CN112180955B/en",
                            "patent": {
                                "title": "电力设备",
                                "snippet": "yyy",
                                "priority_date": "",
                                "filing_date": "2020-01-01",
                                "grant_date": "",
                                "publication_date": "2021-02-02",
                                "inventor": "姚辉",
                                "assignee": "国网安徽省电力有限公司",
                                "publication_number": "CN112180955B",
                                "language": "zh",
                            },
                        },
                    ]
                }
            ],
        }
    }


def test_build_url_keyword():
    url = _build_gp_url("华为")
    assert "patents.google.com/xhr/query" in url
    # inner q=华为 should be double-encoded in url param
    assert "url=" in url


def test_build_url_modes():
    a = PatentLookup()
    url_a = a._build_url("华为技术有限公司", mode="assignee")
    # decode twice to check the assignee: operator survived
    inner = urllib.parse.unquote(urllib.parse.unquote(url_a.split("url=")[1].split("&exp=")[0]))
    assert 'assignee:"华为技术有限公司"' in inner

    url_i = a._build_url("姚辉", mode="inventor")
    inner_i = urllib.parse.unquote(urllib.parse.unquote(url_i.split("url=")[1].split("&exp=")[0]))
    assert 'inventor:"姚辉"' in inner_i


def test_parse_patent_entry():
    entry = _sample_response()["results"]["cluster"][0]["result"][0]
    p = _parse_patent_entry(entry)
    assert p["publication_number"] == "CN110086609B"
    assert p["inventor"] == "姚辉"
    assert p["assignee"] == "华为技术有限公司"
    assert p["filing_date"] == "2019-03-27"
    assert p["url"] == "https://patents.google.com/patent/CN110086609B/en"


def test_extract_public_fields():
    a = PatentLookup()
    fields = a._extract_public_fields(json.dumps(_sample_response()))
    assert fields["patent_count"] == 2
    assert fields["patents_returned"] == 2
    assert len(fields["patents"]) == 2
    # 同一发明人在两家公司 → 关联信号
    assert fields["distinct_inventors"] == ["姚辉"]
    assert len(fields["distinct_assignees"]) == 2


def test_extract_empty():
    a = PatentLookup()
    fields = a._extract_public_fields(None)
    assert fields["patent_count"] == 0
    assert fields["patents"] == []


def test_extract_garbage():
    a = PatentLookup()
    fields = a._extract_public_fields("not json {{{")
    assert fields["patent_count"] == 0
    assert fields.get("parse_error") is True


def test_query_by_assignee_uses_mode():
    captured = {}

    def fake_execute(url, headers):
        captured["url"] = url
        return (200, json.dumps(_sample_response()), "")

    a = PatentLookup(execute_query=fake_execute, robots_checker=lambda d, u: True, sleeper=lambda s: None)
    result = a.query_by_assignee("华为技术有限公司")
    assert result["response_status"] == 200
    assert result["fields"]["patent_count"] == 2
    assert "assignee" in urllib.parse.unquote(captured["url"])


def test_query_by_inventor_uses_mode():
    captured = {}

    def fake_execute(url, headers):
        captured["url"] = url
        return (200, json.dumps(_sample_response()), "")

    a = PatentLookup(execute_query=fake_execute, robots_checker=lambda d, u: True, sleeper=lambda s: None)
    result = a.query_by_inventor("姚辉")
    assert result["fields"]["patent_count"] == 2
    assert "inventor" in urllib.parse.unquote(captured["url"])


def test_audit_no_raw_query_leak():
    def fake_execute(url, headers):
        return (200, json.dumps(_sample_response()), "")

    a = PatentLookup(execute_query=fake_execute, robots_checker=lambda d, u: True, sleeper=lambda s: None)
    a.query("华为技术有限公司", mode="assignee")
    trail = a.audit.get_trail()
    assert len(trail) == 1
    rec = trail[0]
    # 审计只存 hash，不存原文
    assert rec["query_params_hash"] != "华为技术有限公司"
    assert len(rec["query_params_hash"]) == 12
    assert rec["data_boundary"] == "fully_public"
    assert a.audit.verify_integrity()


def test_default_off_metadata():
    a = PatentLookup()
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.requires_interaction is False
    assert a.source_domain == "patents.google.com"
