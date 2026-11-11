#!/usr/bin/env python3
"""Tests for core/kinship_extract.py — 亲属关系表述抽取层."""
from __future__ import annotations

import pytest

from core.kinship_extract import (
    extract_kinship_statements,
    extract_self_claimed_kinship,
    statement_note,
)


def _one(text, **kw):
    sts = extract_kinship_statements(text, **kw)
    assert len(sts) == 1, sts
    return sts[0]


def test_spouse_xi夫妻关系():
    st = _one("张三与李四系夫妻关系，共同持有公司股份。")
    assert (st["person_a"], st["person_b"]) == ("张三", "李四")
    assert st["relation_kind"] == "spouse"
    assert st["evidence_level"] == "exact"


def test_parent_child_zhi子():
    st = _one("王五系赵六之子，为公司实际控制人。")
    assert st["relation_kind"] == "parent_child"
    assert {st["person_a"], st["person_b"]} == {"王五", "赵六"}


def test_sibling_xi兄弟关系():
    st = _one("陈七与周八系兄弟关系。")
    assert st["relation_kind"] == "sibling"


def test_zhi妻_with_trailing_verb():
    # "李四现任董事"：裸名 + 动词尾巴，需剥离为"李四"
    st = _one("张三之妻李四现任公司董事。")
    assert (st["person_a"], st["person_b"]) == ("张三", "李四")
    assert st["relation_kind"] == "spouse"


def test_anaphoric_qi子_with_focus():
    st = _one("其子李四已成年。", focus_name="张三")
    assert (st["person_a"], st["person_b"]) == ("张三", "李四")
    assert st["relation_kind"] == "parent_child"


def test_anaphoric_peiou_with_focus():
    st = _one("配偶：李四。", focus_name="张三")
    assert (st["person_a"], st["person_b"]) == ("张三", "李四")
    assert st["relation_kind"] == "spouse"


def test_fuqi_suffix():
    st = _one("张三、李四夫妇合计持股5%。")
    assert st["relation_kind"] == "spouse"


def test_inferred_family_wengxu():
    st = _one("张三、李四为翁婿关系。", focus_name="张三")
    assert st["relation_kind"] == "inferred_family"


def test_de_structure():
    st = _one("张三的父亲李四曾任董事长。")
    assert (st["person_a"], st["person_b"]) == ("张三", "李四")
    assert st["relation_kind"] == "parent_child"


def test_noise_fuqi店_not_extracted():
    assert extract_kinship_statements("夫妻店模式经营多年。") == []


def test_noise_xiongdi公司_not_extracted():
    assert extract_kinship_statements("兄弟公司之间存在关联交易。") == []


def test_noise_zhi子公司_not_extracted():
    # "张三之子公司"：组织残片不得当成人名
    assert extract_kinship_statements("张三之子公司持有上市公司股份。") == []


def test_evidence_level_strong():
    st = _one("张三与李四系夫妻关系。", evidence_level="strong")
    assert st["evidence_level"] == "strong"


def test_evidence_level_invalid_raises():
    with pytest.raises(ValueError):
        extract_kinship_statements("张三与李四系夫妻关系。", evidence_level="nope")


def test_source_ref_and_quote():
    st = _one("张三与李四系夫妻关系。", source_ref="《简式权益变动报告书》")
    assert st["source_ref"] == "《简式权益变动报告书》"
    assert "夫妻关系" in st["quote"]


def test_dedup():
    sts = extract_kinship_statements("张三与李四系夫妻关系。张三与李四系夫妻关系。")
    assert len(sts) == 1


def test_self_claimed_bio():
    sts = extract_self_claimed_kinship("本人系张三之妻，现居北京。", profile_name="李四")
    assert len(sts) == 1
    st = sts[0]
    assert st["person_a"] == "李四" and st["person_b"] == "张三"
    assert st["relation_kind"] == "spouse"
    assert st["evidence_level"] == "review"


def test_self_claimed_de_pattern():
    sts = extract_self_claimed_kinship("张三的儿子，爱好摄影。", profile_name="李四")
    assert len(sts) == 1
    assert sts[0]["relation_kind"] == "parent_child"
    assert sts[0]["evidence_level"] == "review"


def test_self_claimed_empty_bio():
    assert extract_self_claimed_kinship("Less is more", profile_name="阿北") == []


def test_statement_note_wording_exact():
    note = statement_note({
        "person_a": "张三", "person_b": "李四", "relation_kind": "spouse",
        "evidence_level": "exact", "source_ref": "《简式权益变动报告书》"})
    assert note.startswith("披露显示")
    assert "断言" not in note and "实锤" not in note


def test_statement_note_wording_strong():
    note = statement_note({
        "person_a": "张三", "person_b": "李四", "relation_kind": "parent_child",
        "evidence_level": "strong", "source_ref": "裁判文书"})
    assert note.startswith("文书载明")


def test_statement_note_wording_review():
    note = statement_note({
        "person_a": "李四", "person_b": "张三", "relation_kind": "spouse",
        "evidence_level": "review", "source_ref": "profile_bio"})
    assert note.startswith("自述/疑似")
