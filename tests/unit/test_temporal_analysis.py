#!/usr/bin/env python3
"""时间线关联分析单元测试（stubbed，不联网）。"""

import sys
sys.path.insert(0, ".")

from datetime import datetime

from core.temporal_analysis import (
    parse_timestamp,
    entity_time,
    entity_uid,
    analyze_temporal_clusters,
    detect_temporal_patterns,
    analyze_temporal,
)


# ---------------------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------------------

def test_parse_iso_date():
    assert parse_timestamp("2024-03-05") == datetime(2024, 3, 5)


def test_parse_iso_datetime():
    assert parse_timestamp("2024-03-05 14:30:00") == datetime(2024, 3, 5, 14, 30, 0)


def test_parse_chinese_date():
    assert parse_timestamp("2024年3月5日") == datetime(2024, 3, 5)


def test_parse_chinese_date_nospace():
    assert parse_timestamp("2023年12月1日") == datetime(2023, 12, 1)


def test_parse_slash_date():
    assert parse_timestamp("2024/03/05") == datetime(2024, 3, 5)


def test_parse_compact_date():
    assert parse_timestamp("20240305") == datetime(2024, 3, 5)


def test_parse_unix_seconds():
    # 2024-01-01 00:00:00 UTC
    dt = parse_timestamp(1704067200)
    assert dt is not None and dt.year == 2024 and dt.month == 1


def test_parse_unix_millis():
    dt = parse_timestamp(1704067200000)
    assert dt is not None and dt.year == 2024 and dt.month == 1


def test_parse_datetime_passthrough():
    d = datetime(2024, 5, 6, 7, 8, 9)
    assert parse_timestamp(d) == d


def test_parse_invalid_returns_none():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None
    assert parse_timestamp("not a date") is None
    assert parse_timestamp("2024-13-45") is None
    assert parse_timestamp(-5) is None
    assert parse_timestamp(True) is None


# ---------------------------------------------------------------------------
# entity_time / entity_uid
# ---------------------------------------------------------------------------

def test_entity_time_top_level():
    e = {"type": "business", "value": "x", "created_at": "2024-01-15"}
    assert entity_time(e) == datetime(2024, 1, 15)


def test_entity_time_from_context():
    e = {"type": "business", "value": "x",
         "context": {"成立日期": "2023年6月1日"}}
    assert entity_time(e) == datetime(2023, 6, 1)


def test_entity_time_missing():
    assert entity_time({"type": "phone", "value": "13800000000"}) is None
    assert entity_time({}) is None
    assert entity_time(None) is None


def test_entity_uid_prefers_id():
    assert entity_uid({"id": "abc", "type": "x", "value": "y"}) == "abc"
    assert entity_uid({"type": "phone", "value": "138"}) == "phone:138"


# ---------------------------------------------------------------------------
# clustering
# ---------------------------------------------------------------------------

def _biz(name, date):
    return {"type": "business", "value": name, "display": name,
            "created_at": date}


def test_strong_cluster_within_7_days():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-01-03"),
            _biz("c", "2024-01-06")]
    clusters = analyze_temporal_clusters(ents)
    assert len(clusters) == 1
    assert clusters[0]["strength"] == "strong"
    assert clusters[0]["size"] == 3
    assert clusters[0]["span_days"] == 5


def test_weak_cluster_within_30_days():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-01-20")]
    clusters = analyze_temporal_clusters(ents)
    assert len(clusters) == 1
    assert clusters[0]["strength"] == "weak"


def test_no_cluster_when_far_apart():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-06-01")]
    assert analyze_temporal_clusters(ents) == []


def test_untimed_entities_ignored():
    ents = [_biz("a", "2024-01-01"),
            {"type": "phone", "value": "13800000000"}]
    assert analyze_temporal_clusters(ents) == []


def test_empty_input():
    assert analyze_temporal_clusters([]) == []


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------

def test_batch_creation_pattern():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-01-02"),
            _biz("c", "2024-01-04")]
    patterns = detect_temporal_patterns(ents)
    batch = [p for p in patterns if p["pattern"] == "batch_creation"]
    assert len(batch) == 1
    assert batch[0]["severity"] == "medium"
    assert len(batch[0]["entities"]) == 3


def test_no_batch_creation_with_two_entities():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-01-02")]
    patterns = detect_temporal_patterns(ents)
    assert not [p for p in patterns if p["pattern"] == "batch_creation"]


def test_domain_after_company_pattern():
    ents = [
        _biz("某某公司", "2024-01-01"),
        {"type": "domain", "value": "example.com",
         "display": "example.com", "created_at": "2024-02-01"},
    ]
    patterns = detect_temporal_patterns(ents)
    hit = [p for p in patterns if p["pattern"] == "domain_after_company"]
    assert len(hit) == 1
    assert hit[0]["delta_days"] == 31
    assert hit[0]["severity"] == "low"


def test_domain_before_company_no_pattern():
    ents = [
        _biz("某某公司", "2024-06-01"),
        {"type": "domain", "value": "example.com",
         "display": "example.com", "created_at": "2024-01-01"},
    ]
    patterns = detect_temporal_patterns(ents)
    assert not [p for p in patterns if p["pattern"] == "domain_after_company"]


def test_account_before_company_pattern():
    ents = [
        {"type": "douyin_account", "value": "dy123",
         "display": "dy123", "created_at": "2023-01-01"},
        _biz("某某公司", "2024-06-01"),
    ]
    patterns = detect_temporal_patterns(ents)
    hit = [p for p in patterns if p["pattern"] == "account_before_company"]
    assert len(hit) == 1
    assert hit[0]["delta_days"] > 400


def test_simultaneous_update_pattern():
    ents = [
        {"type": "business", "value": "a", "display": "a",
         "context": {"变更日期": "2024-05-01"}},
        {"type": "business", "value": "b", "display": "b",
         "context": {"变更日期": "2024-05-01"}},
    ]
    patterns = detect_temporal_patterns(ents)
    hit = [p for p in patterns if p["pattern"] == "simultaneous_update"]
    assert len(hit) == 1
    assert hit[0]["severity"] == "medium"


def test_patterns_are_leads_not_facts():
    ents = [_biz("a", "2024-01-01"), _biz("b", "2024-01-02"),
            _biz("c", "2024-01-03")]
    result = analyze_temporal(ents)
    assert "disclaimer" in result
    assert "lead" in result["disclaimer"]


# ---------------------------------------------------------------------------
# wrapper
# ---------------------------------------------------------------------------

def test_analyze_temporal_coverage():
    ents = [_biz("a", "2024-01-01"),
            {"type": "phone", "value": "13800000000"}]
    result = analyze_temporal(ents)
    assert result["timed_entity_count"] == 1
    assert result["total_entity_count"] == 2
    assert result["time_range"] == {"earliest": "2024-01-01",
                                   "latest": "2024-01-01"}
    assert result["data_boundary"] == "fully_public"


def test_analyze_temporal_empty():
    result = analyze_temporal([])
    assert result["clusters"] == []
    assert result["patterns"] == []
    assert result["time_range"] is None


def test_analyze_temporal_non_list():
    result = analyze_temporal(None)
    assert result["total_entity_count"] == 0
