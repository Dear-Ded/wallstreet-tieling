#!/usr/bin/env python3
"""Tests for the kinship reasoning layer (亲属关系 lane, 2026-10-21).

Covers: _extract branch for cninfo_kinship, _kinship_disclosure_associations
(relation kinds / strength mapping / wording guard), douban self-claimed
wiring, person_name fanout, factory injection.
"""
from __future__ import annotations

from core.entity_association import (
    _SEED_FANOUT,
    _douban_user_entities,
    create_engine_with_all_adapters,
    entity_id,
    EntityAssociationEngine,
)


def _engine():
    return EntityAssociationEngine()


def _cninfo_result():
    return {
        "fields": {
            "kinship_statements": [
                {
                    "person_a": "张三", "person_b": "李四",
                    "relation_kind": "spouse", "evidence_level": "exact",
                    "quote": "张三与李四系夫妻关系",
                    "source_ref": "《简式权益变动报告书》",
                    "pdf_url": "http://static.cninfo.com.cn/x.PDF",
                },
                {
                    "person_a": "王五", "person_b": "赵六",
                    "relation_kind": "parent_child", "evidence_level": "strong",
                    "quote": "王五系赵六之子",
                    "source_ref": "裁判文书(2024)1号",
                    "pdf_url": "",
                },
            ]
        }
    }


def _merged(engine, *entity_lists):
    entities = {}
    for ents in entity_lists:
        engine._merge_entities(entities, ents)
    return entities


def test_extract_cninfo_kinship_person_entities():
    engine = _engine()
    ents = engine._extract("cninfo_kinship", _cninfo_result())
    by_value = {e["value"]: e for e in ents}
    assert set(by_value) == {"张三", "李四", "王五", "赵六"}
    e = by_value["张三"]
    assert e["type"] == "person"
    assert e["sources"] == ["cninfo_kinship"]
    assert e["context"]["from"] == "kinship_statement"
    assert e["context"]["kinship"]["relation_kind"] == "spouse"


def test_extract_cninfo_kinship_empty():
    engine = _engine()
    assert engine._extract("cninfo_kinship", {"fields": {}}) == []


def test_kinship_associations_kinds_strengths_wording():
    engine = _engine()
    entities = _merged(engine, engine._extract("cninfo_kinship", _cninfo_result()))
    assocs = engine._kinship_disclosure_associations(entities)
    by_rel = {a["relation"]: a for a in assocs}
    assert set(by_rel) == {"kinship_spouse", "kinship_parent_child"}

    spouse = by_rel["kinship_spouse"]
    assert spouse["strength"] == "exact"
    assert spouse["note"].startswith("披露显示")
    assert "张三" in spouse["note"] and "李四" in spouse["note"]

    pc = by_rel["kinship_parent_child"]
    assert pc["strength"] == "strong"
    assert pc["note"].startswith("文书载明")

    # 绝不断言措辞
    for a in assocs:
        assert "实锤" not in a["note"]
        assert "确认" not in a["note"] or "待核实" in a["note"]


def test_kinship_associations_dedup():
    engine = _engine()
    ents = engine._extract("cninfo_kinship", _cninfo_result())
    entities = _merged(engine, ents, ents)  # 同一 statement 进两次
    assocs = engine._kinship_disclosure_associations(entities)
    rels = [a["relation"] for a in assocs]
    assert len(rels) == len(set(rels)) == 2


def test_kinship_associations_invalid_level_skipped():
    engine = _engine()
    bad = {"fields": {"kinship_statements": [{
        "person_a": "张三", "person_b": "李四",
        "relation_kind": "spouse", "evidence_level": "nope",
        "quote": "x", "source_ref": ""}]}}
    entities = _merged(engine, engine._extract("cninfo_kinship", bad))
    assert engine._kinship_disclosure_associations(entities) == []


def test_douban_self_claimed_wiring():
    profile = {
        "nickname": "李四",
        "self_claimed_kinship": [{
            "person_a": "", "person_b": "张三",
            "relation_kind": "spouse", "evidence_level": "review",
            "quote": "张三的妻子", "source_ref": "profile_bio",
        }],
    }
    ents = _douban_user_entities(profile, {}, "douban_user")
    assert len(ents) == 1
    assert ents[0]["context"]["self_claimed_kinship"][0]["person_b"] == "张三"

    engine = _engine()
    # 补一个张三实体，使 pair 完整
    extra = [{"type": "person", "value": "张三", "sources": ["x"], "context": {}}]
    entities = _merged(engine, ents, extra)
    assocs = engine._kinship_disclosure_associations(entities)
    assert len(assocs) == 1
    a = assocs[0]
    assert a["relation"] == "kinship_spouse"
    assert a["strength"] == "review"
    assert a["note"].startswith("自述/疑似")
    # person_a 回填为资料主人
    assert "李四" in a["note"]


def test_inferred_family_relation_name():
    engine = _engine()
    res = {"fields": {"kinship_statements": [{
        "person_a": "张三", "person_b": "李四",
        "relation_kind": "inferred_family", "evidence_level": "review",
        "quote": "张三、李四为翁婿关系", "source_ref": "某报道"}]}}
    entities = _merged(engine, engine._extract("cninfo_kinship", res))
    assocs = engine._kinship_disclosure_associations(entities)
    assert assocs[0]["relation"] == "kinship_inferred_family"
    assert assocs[0]["strength"] == "review"


def test_person_name_fanout_includes_cninfo_kinship():
    assert "cninfo_kinship" in _SEED_FANOUT["person_name"]


def test_factory_injects_cninfo_kinship():
    engine = create_engine_with_all_adapters()
    assert engine.cninfo_kinship is not None
    assert type(engine.cninfo_kinship).__name__ == "CninfoKinshipLookup"
    assert "cninfo_kinship" in _SEED_FANOUT["person_name"]


def test_entity_id_stable_for_kinship_persons():
    assert entity_id("person", "张三") == entity_id("person", "张三")
