"""Tests for patent person-lane wiring (官方公示反查人 lane, 2026-10-21).

- person_name seed -> patent adapter 必须以 mode="inventor" 定向检索
  (inventor:"姓名"),而不是默认 keyword 全字段检索.
- business_name seed -> patent 保持默认 mode (assignee/keyword 语义不变).
- _extract("patent") 把 inventor 拆成 person 实体.
"""

from core.entity_association import EntityAssociationEngine


_PATENTS = [
    {
        "publication_number": "CN110086609B",
        "title": "数据备份方法",
        "inventor": "姚辉",
        "assignee": "华为技术有限公司",
        "filing_date": "2019-03-27",
    },
    {
        "publication_number": "CN112180955B",
        "title": "电力设备",
        "inventor": "姚辉、李娜",
        "assignee": "国网安徽省电力有限公司",
        "filing_date": "2020-01-01",
    },
]


class _StubPatent:
    def __init__(self):
        self.calls = []

    def query(self, keyword, **kwargs):
        self.calls.append({"keyword": keyword, "kwargs": dict(kwargs)})
        return {
            "fields": {
                "patents": _PATENTS,
                "patent_count": len(_PATENTS),
            },
            "field_count": 2,
        }


def test_person_name_fanout_uses_inventor_mode():
    stub = _StubPatent()
    eng = EntityAssociationEngine(patent=stub)
    out = eng.associate({"type": "person_name", "value": "姚辉"})
    assert stub.calls, "patent adapter should have been called"
    assert stub.calls[0]["keyword"] == "姚辉"
    assert stub.calls[0]["kwargs"].get("mode") == "inventor"
    persons = {e["value"] for e in out["entities"] if e["type"] == "person"}
    # 两条专利的发明人:姚辉、李娜(顿号拆分)
    assert "姚辉" in persons
    assert "李娜" in persons
    inv = [e for e in out["entities"]
           if e["type"] == "person" and e.get("context", {}).get("from") == "patent_inventor"]
    assert inv, "inventor person entities expected"
    assert all("patent" in e.get("sources", []) for e in inv)


def test_business_name_fanout_keeps_default_mode():
    stub = _StubPatent()
    eng = EntityAssociationEngine(patent=stub)
    eng.associate({"type": "business_name", "value": "华为技术有限公司"})
    assert stub.calls, "patent adapter should have been called"
    # business 维度不强制 inventor mode(默认 keyword 语义)
    assert "mode" not in stub.calls[0]["kwargs"]


def test_extract_patent_splits_inventor_to_person():
    eng = EntityAssociationEngine()
    result = {"fields": {"patents": _PATENTS}}
    ents = eng._extract("patent", result)
    persons = [e for e in ents if e["type"] == "person"]
    assert {p["value"] for p in persons} == {"姚辉", "李娜"}
    for p in persons:
        assert p["context"]["from"] == "patent_inventor"
        assert p["context"]["publication_number"].startswith("CN")
    # 申请人仍走 business 实体
    biz = [e for e in ents if e["type"] == "business"]
    assert {b["value"] for b in biz} == {"华为技术有限公司", "国网安徽省电力有限公司"}
