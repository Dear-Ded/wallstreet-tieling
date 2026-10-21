"""semanticscholar _extract 分支 + 引擎接线（fixture 离线）。"""
from core.entity_association import (
    EntityAssociationEngine,
    create_engine_with_all_adapters,
    _SEED_FANOUT,
)


def _fake_result():
    return {
        "fields": {
            "author_found": True,
            "match_level": "exact",
            "search_total": 22,
            "candidates_considered": 2,
            "author": {
                "author_id": "2287034803",
                "name": "Geoffrey Hinton",
                "affiliations": ["University of Toronto"],
                "paper_count": 4,
                "citation_count": 0,
                "h_index": 0,
                "url": "https://www.semanticscholar.org/author/2287034803",
                "homepage": "https://example.org/~ghinton",
            },
            "top_papers": [
                {"paper_id": "p1", "title": "Deep Learning Study", "year": 2020, "author_count": 3},
            ],
            "co_authors": [
                {"name": "Y. LeCun", "author_id": "999", "shared_papers": 2,
                 "paper_titles": ["Deep Learning Study"]},
                {"name": "Geoffrey Hinton", "author_id": "2287034803", "shared_papers": 3,
                 "paper_titles": []},  # self must be excluded
            ],
            "co_author_count": 2,
        }
    }


def test_semanticscholar_extract_author_person():
    e = EntityAssociationEngine(semanticscholar=None)
    ents = e._extract("semanticscholar", _fake_result())
    author = ents[0]
    assert author["type"] == "person"
    assert "semanticscholar" in author["sources"]
    ctx = author["context"]
    assert ctx["affiliations"] == ["University of Toronto"]
    assert ctx["paper_count"] == 4
    assert ctx["citation_count"] == 0
    assert ctx["h_index"] == 0
    assert ctx["homepage"] == "https://example.org/~ghinton"
    assert ctx["match_level"] == "exact"
    # 简介文本进 context.description 供联系方式管道挖
    assert "University of Toronto" in ctx["description"]
    assert "https://example.org/~ghinton" in ctx["description"]


def test_semanticscholar_extract_coauthors_are_co_author_persons():
    e = EntityAssociationEngine(semanticscholar=None)
    ents = e._extract("semanticscholar", _fake_result())
    by_display = {x["display"]: x for x in ents}
    assert "Y. LeCun" in by_display
    co = by_display["Y. LeCun"]
    assert co["type"] == "person"
    assert co["context"]["relation"] == "co_author"
    assert co["context"]["with_author"] == "Geoffrey Hinton"
    assert co["context"]["shared_papers"] == 2
    # self excluded
    assert len(ents) == 2


def test_semanticscholar_not_found():
    e = EntityAssociationEngine(semanticscholar=None)
    assert e._extract("semanticscholar", {"fields": {"author_found": False}}) == []
    assert e._extract("semanticscholar", {"fields": {}}) == []


def test_semanticscholar_wired_in_fanout_and_factory():
    assert "semanticscholar" in _SEED_FANOUT["person_name"]
    eng = create_engine_with_all_adapters()
    assert eng.semanticscholar is not None
    assert type(eng.semanticscholar).__name__ == "SemanticScholarLookup"
    assert eng.semanticscholar.data_boundary == "fully_public"
    assert eng.semanticscholar.requires_credentials is False
