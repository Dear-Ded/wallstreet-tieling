"""Tests for core/risk_scorer.py — 风险量化引擎。"""

from __future__ import annotations

import pytest

from core.risk_scorer import (
    MAX_SCORE,
    RISK_WEIGHTS,
    score_entity,
    score_investigation,
)


def _biz(eid="business:abc", display="ABC 公司", **ctx):
    return {
        "id": eid, "type": "business", "value": display, "display": display,
        "sources": ["icp_beian"], "context": dict(ctx),
    }


def _person(eid="person:zhang", display="张三"):
    return {
        "id": eid, "type": "person", "value": display, "display": display,
        "sources": ["wenshu"], "context": {},
    }


def _pattern(name, eid, description="desc"):
    return {
        "pattern": name, "description": description,
        "entities": [eid], "severity": "medium",
    }


# -- baseline ---------------------------------------------------------------

def test_clean_business_scores_zero():
    e = _biz(phone="13800001111", address="某市某路1号")
    e["sources"] = ["icp_beian", "lagou"]
    r = score_entity(e)
    assert r["score"] == 0
    assert r["level"] == "low"
    assert r["factors"] == []
    assert "disclaimer" in r


def test_entity_id_and_display_echoed():
    r = score_entity(_biz())
    assert r["entity_id"] == "business:abc"
    assert r["display"] == "ABC 公司"
    assert r["type"] == "business"


# -- individual factors ------------------------------------------------------

def test_shell_signal_adds_30():
    r = score_entity(_biz())  # no phone / no address / no recruit
    assert r["score"] == 30
    assert r["level"] == "medium"
    assert any(f["factor"] == "shell_signal" for f in r["factors"])


def test_shell_not_applied_to_person():
    r = score_entity(_person())
    assert r["score"] == 0


def test_phone_only_not_shell():
    # 按口径：无电话、无地址、无招聘 = 三者全无；有电话即不触发空壳
    r = score_entity(_biz(phone="13800001111"))
    assert not any(f["factor"] == "shell_signal" for f in r["factors"])
    assert r["score"] == 0


def test_recruit_source_clears_shell():
    e = _biz()
    e["sources"] = ["zhipin"]
    r = score_entity(e)
    assert not any(f["factor"] == "shell_signal" for f in r["factors"])


def test_family_business_adds_10():
    e = _biz(phone="138", address="x")
    p = _pattern("family_business_signal", e["id"])
    r = score_entity(e, patterns=[p])
    assert r["score"] == 10
    assert r["level"] == "low"


def test_figurehead_adds_25():
    e = _biz(phone="1", address="x")
    p = _pattern("figurehead_risk", e["id"])
    r = score_entity(e, patterns=[p])
    assert r["score"] == 25
    assert r["level"] == "medium"


def test_shared_phone_adds_15():
    e = _biz(phone="1", address="x")
    p = _pattern("shared_phone_across_businesses", e["id"])
    r = score_entity(e, patterns=[p])
    assert r["score"] == 15


def test_shared_address_adds_15():
    e = _biz(phone="1", address="x")
    p = _pattern("shared_address_across_businesses", e["id"])
    r = score_entity(e, patterns=[p])
    assert r["score"] == 15


def test_beneficial_owner_adds_10():
    e = _person()
    p = _pattern("possible_beneficial_owner", e["id"])
    r = score_entity(e, patterns=[p])
    assert r["score"] == 10


def test_pattern_for_other_entity_ignored():
    e = _biz(phone="1", address="x")
    p = _pattern("figurehead_risk", "business:other")
    r = score_entity(e, patterns=[p])
    assert r["score"] == 0


def test_court_cases_20_each():
    e = _person()
    assocs = [
        {"from": e["id"], "to": "case:1", "relation": "co_party_in_case"},
        {"from": e["id"], "to": "case:2", "relation": "co_party_in_case"},
        # duplicate edge to same case counts once
        {"from": "case:1", "to": e["id"], "relation": "co_party_in_case"},
    ]
    r = score_entity(e, associations=assocs)
    assert r["score"] == 40
    assert any(f["factor"] == "court_cases" and f["points"] == 40
               for f in r["factors"])


def test_dishonest_executor_max_single_factor():
    e = _biz(phone="1", address="x", dishonest=True)
    r = score_entity(e)
    assert r["score"] == 50
    assert r["level"] == "high"
    assert any(f["factor"] == "dishonest_executor" for f in r["factors"])


def test_dishonest_keyword_in_context():
    e = _person()
    e["context"] = {"notice_type": "失信被执行人名单"}
    r = score_entity(e)
    assert r["score"] == 50


# -- aggregation, cap, levels -------------------------------------------------

def test_factors_stack_and_cap_at_100():
    e = _biz(dishonest=True)  # 50 + 30 shell
    p1 = _pattern("figurehead_risk", e["id"])          # 25
    p2 = _pattern("shared_phone_across_businesses", e["id"])   # 15
    p3 = _pattern("shared_address_across_businesses", e["id"])  # 15
    assocs = [{"from": e["id"], "to": "case:9",
               "relation": "co_party_in_case"}]        # 20
    r = score_entity(e, patterns=[p1, p2, p3], associations=assocs)
    assert r["score"] == MAX_SCORE == 100
    assert r["level"] == "critical"
    assert len(r["factors"]) == 6


def test_level_boundaries():
    e = _biz(phone="1", address="x")
    assert score_entity(e)["level"] == "low"          # 0
    p = _pattern("figurehead_risk", e["id"])          # 25
    assert score_entity(e, patterns=[p])["level"] == "medium"
    e2 = _biz(dishonest=True, phone="1", address="x")  # 50
    assert score_entity(e2)["level"] == "high"


def test_custom_weights_override():
    e = _biz(phone="1", address="x")
    p = _pattern("figurehead_risk", e["id"])
    r = score_entity(e, patterns=[p], weights={"figurehead_risk": 5})
    assert r["score"] == 5


def test_every_factor_carries_source():
    e = _biz(dishonest=True)
    r = score_entity(e, patterns=[_pattern("family_business_signal", e["id"])])
    for f in r["factors"]:
        assert f["source"], f
        assert f["evidence"], f


# -- score_investigation ------------------------------------------------------

def test_score_investigation_ranks_desc():
    risky = _biz(eid="business:risky", display="风险公司")
    clean = _biz(eid="business:clean", display="干净公司",
                 phone="13800001111", address="某路1号")
    clean["sources"] = ["lagou"]
    result = {
        "seed": {"type": "business_name", "value": "x"},
        "entities": [risky, clean],
        "interesting_patterns": [],
        "associations": [],
    }
    out = score_investigation(result)
    assert out["count"] == 2
    assert out["ranked"][0]["entity_id"] == "business:risky"
    assert out["ranked"][0]["score"] == 30
    assert out["ranked"][1]["score"] == 0


def test_score_investigation_top_n():
    ents = [_biz(eid=f"business:{i}", display=f"c{i}") for i in range(5)]
    result = {"entities": ents, "interesting_patterns": [],
              "associations": []}
    out = score_investigation(result, top_n=3)
    assert len(out["ranked"]) == 3
    assert out["count"] == 5


def test_score_investigation_skips_non_scored_types():
    result = {"entities": [
        {"id": "phone:1", "type": "phone", "display": "1",
         "sources": [], "context": {}},
        _biz(),
    ], "interesting_patterns": [], "associations": []}
    out = score_investigation(result)
    assert out["count"] == 1


def test_empty_investigation():
    out = score_investigation({})
    assert out["ranked"] == []
    assert out["count"] == 0


def test_weights_documented():
    assert RISK_WEIGHTS["dishonest_executor"] == max(RISK_WEIGHTS.values())
