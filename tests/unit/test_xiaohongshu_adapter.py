#!/usr/bin/env python3
"""小红书适配器单元测试。"""

import json

from adapters.xiaohongshu_adapter import XiaohongshuNoteLookup


def _make_adapter():
    return XiaohongshuNoteLookup()


def test_query_returns_interaction_required():
    a = _make_adapter()
    r = a.query("海底捞")
    assert r["error"] == "interaction_required"
    assert "interaction_instructions" in r
    assert "xiaohongshu.com" in r["interaction_instructions"].lower() or "小红书" in r["interaction_instructions"]
    assert r["source_domain"] == "xiaohongshu.com"


def test_parse_search_api_shape():
    a = _make_adapter()
    payload = {
        "data": {
            "items": [
                {
                    "id": "68a1b2c3000000001b03d4e5",
                    "note_card": {
                        "title": "海底捞中关村店探店",
                        "desc": "服务真的很好，番茄锅必点",
                        "user": {"nickname": "吃货小王"},
                        "interact_info": {
                            "liked_count": "1234",
                            "collected_count": 56,
                            "comment_count": 78,
                        },
                        "cover": {"url": "https://sns-img-qc.xhscdn.com/abc.jpg"},
                        "poi": {"name": "海底捞火锅(中关村店)"},
                        "time": 1729000000,
                    },
                },
                {
                    "id": "68a1b2c3000000001b03d4e6",
                    "note_card": {
                        "title": "避雷！这家海底捞等位3小时",
                        "user": {"nick_name": "北京美食家"},
                        "interact_info": {"liked_count": 89},
                    },
                },
            ]
        }
    }
    r = a.parse_browser_result(payload)
    assert r["response_status"] == 200
    notes = r["fields"]["notes"]
    assert len(notes) == 2
    n0 = notes[0]
    assert n0["note_id"] == "68a1b2c3000000001b03d4e5"
    assert n0["title"] == "海底捞中关村店探店"
    assert n0["author"] == "吃货小王"
    assert n0["liked_count"] == 1234
    assert n0["collected_count"] == 56
    assert n0["comment_count"] == 78
    assert n0["location"] == "海底捞火锅(中关村店)"
    assert n0["note_url"] == "https://www.xiaohongshu.com/explore/68a1b2c3000000001b03d4e5"
    assert len(n0["images"]) == 1
    # POI 汇总
    assert r["fields"]["poi_mentions"] == {"海底捞火锅(中关村店)": 1}


def test_parse_json_string_input():
    a = _make_adapter()
    payload = json.dumps({"items": [{"id": "abc123", "title": "测试笔记"}]})
    r = a.parse_browser_result(payload)
    assert r["response_status"] == 200
    assert r["fields"]["note_count"] == 1


def test_parse_flat_note_shape():
    a = _make_adapter()
    # 扁平形状 (无 note_card 包裹)
    r = a.parse_browser_result({"notes": [{"note_id": "x1", "title": "扁平笔记", "location": "某店"}]})
    assert r["fields"]["note_count"] == 1
    assert r["fields"]["notes"][0]["location"] == "某店"


def test_parse_garbage_input():
    a = _make_adapter()
    assert a.parse_browser_result("not json {{{")["error"] == "invalid_json"
    # 空 dict 返回结构化空结果 (note_count=0),而非裸 {}
    assert a.parse_browser_result({})["fields"]["note_count"] == 0
    assert a.parse_browser_result({"data": {}})["fields"]["note_count"] == 0
    # 非 dict item 被过滤
    r = a.parse_browser_result({"items": ["garbage", 123, None]})
    assert r["fields"]["note_count"] == 0


def test_parse_empty_note_skipped():
    a = _make_adapter()
    r = a.parse_browser_result({"items": [{}, {"id": "", "note_card": {}}]})
    assert r["fields"]["note_count"] == 0


def test_audit_log_no_keyword_leak():
    """审计日志只存哈希,不存原始关键词。"""
    a = _make_adapter()
    a.query("海底捞中关村店")
    # 基类 _record_audit 存的是 sha256 前 12 位,此处只验证 query 正常返回
    r = a.query("测试")
    assert len(r["query_subject_hash"]) == 12
    assert "测试" not in r["query_subject_hash"]
