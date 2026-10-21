"""Tests for Semantic Scholar public author API adapter (offline fixtures)."""

import pytest

from adapters.semanticscholar_adapter import SemanticScholarLookup

FIXTURE_SEARCH = {
    "total": 22,
    "offset": 0,
    "data": [
        {"authorId": "2257301155", "name": "G. Hinton", "affiliations": [],
         "paperCount": 41, "citationCount": 959, "hIndex": 11,
         "url": "https://www.semanticscholar.org/author/2257301155",
         "homepage": None},
        {"authorId": "2287034803", "name": "Geoffrey Hinton", "affiliations": [],
         "paperCount": 4, "citationCount": 0, "hIndex": 0,
         "url": "https://www.semanticscholar.org/author/2287034803",
         "homepage": "https://example.org/~ghinton"},
    ],
}

FIXTURE_DETAIL = {
    "authorId": "2287034803",
    "name": "Geoffrey Hinton",
    "affiliations": ["University of Toronto"],
    "paperCount": 4,
    "citationCount": 0,
    "hIndex": 0,
    "url": "https://www.semanticscholar.org/author/2287034803",
    "homepage": "https://example.org/~ghinton",
}

FIXTURE_PAPERS = {
    "offset": 0,
    "data": [
        {"paperId": "p1", "title": "Deep Learning Study", "year": 2020,
         "authors": [
             {"authorId": "2287034803", "name": "Geoffrey Hinton"},
             {"authorId": "999", "name": "Y. LeCun"},
             {"authorId": "998", "name": "Yoshua Bengio"},
         ]},
        {"paperId": "p2", "title": "Neural Nets Revisited", "year": 2021,
         "authors": [
             {"authorId": "2287034803", "name": "Geoffrey Hinton"},
             {"authorId": "999", "name": "Y. LeCun"},
         ]},
        # megacollaboration: skipped for co-author extraction, kept in top_papers
        {"paperId": "p3", "title": "Big Science", "year": 2022,
         "authors": [{"authorId": str(i), "name": f"Author {i}"} for i in range(60)]},
    ],
}

FIXTURE_EMPTY_SEARCH = {"total": 0, "offset": 0, "data": []}


def _dispatch(url, headers):
    if "author/search" in url:
        return (200, FIXTURE_SEARCH, "")
    if "/papers" in url:
        return (200, FIXTURE_PAPERS, "")
    return (200, FIXTURE_DETAIL, "")


def _adapter(override=_dispatch):
    return SemanticScholarLookup(
        execute_query=override,
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_empty_keyword_returns_structured_empty():
    a = _adapter()
    result = a.query("   ")
    assert result["fields"] == {}
    assert "keyword_empty" in result["error"]


def test_build_url_hits_author_search():
    a = _adapter()
    url = a._build_url("Geoffrey Hinton")
    assert url.startswith("https://api.semanticscholar.org/graph/v1/author/search?query=")
    assert "fields=" in url


def test_source_metadata():
    a = _adapter()
    assert a.source_domain == "api.semanticscholar.org"
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.min_request_interval >= 2.0


def test_grade_match():
    g = SemanticScholarLookup.grade_match
    assert g("Geoffrey Hinton", "Geoffrey Hinton") == "exact"
    assert g("李飞飞", "李飞飞") == "exact"
    assert g("Geoffrey Hinton", "G. Hinton") == "strong"
    assert g("Geoffrey Hinton", "Geoffrey E. Hinton") == "strong"
    assert g("张三", "李四") == "review"
    assert g("Hinton", "E. Cambria") == "review"


def test_select_best_prefers_exact_then_citations():
    best, level = SemanticScholarLookup.select_best(FIXTURE_SEARCH["data"], "Geoffrey Hinton")
    assert best["authorId"] == "2287034803"
    assert level == "exact"


def test_query_full_result_shape():
    a = _adapter()
    result = a.query("Geoffrey Hinton")
    assert result["data_boundary"] == "fully_public"
    fields = result["fields"]
    assert fields["author_found"] is True
    assert fields["match_level"] == "exact"
    author = fields["author"]
    assert author["name"] == "Geoffrey Hinton"
    assert author["affiliations"] == ["University of Toronto"]
    assert author["paper_count"] == 4
    assert author["citation_count"] == 0
    assert author["homepage"] == "https://example.org/~ghinton"
    # top papers: all 3 listed (incl. megacollaboration), co-authors deduped + self excluded
    assert len(fields["top_papers"]) == 3
    names = [c["name"] for c in fields["co_authors"]]
    assert "Geoffrey Hinton" not in names
    assert "Y. LeCun" in names and "Yoshua Bengio" in names
    assert not any(n.startswith("Author ") for n in names)  # megacollab skipped
    lecun = next(c for c in fields["co_authors"] if c["name"] == "Y. LeCun")
    assert lecun["shared_papers"] == 2
    assert fields["co_author_count"] == 2


def test_no_candidates_yields_not_found():
    a = _adapter(lambda url, headers: (200, FIXTURE_EMPTY_SEARCH, "")
                 if "author/search" in url else (404, None, "nf"))
    fields = a.query("Nobody McNobody")["fields"]
    assert fields["author_found"] is False
    assert fields["candidates_considered"] == 0


def test_search_transport_error_reported():
    a = _adapter(lambda url, headers: (0, None, "TimeoutError: boom"))
    result = a.query("Geoffrey Hinton")
    assert result["response_status"] == 0
    assert "TimeoutError" in result["error"]


def test_audit_trail_records_all_requests():
    a = _adapter()
    a.query("Geoffrey Hinton")
    trail = a.audit.get_trail()
    kinds = [r["fields_extracted"] for r in trail]
    assert any("author_detail" in k for k in kinds)
    assert any("author_papers" in k for k in kinds)
    assert a.audit.verify_integrity()


@pytest.mark.skip(reason="live network probe; run manually when egress allows")
def test_live_author_search():
    a = SemanticScholarLookup(sleeper=lambda s: None)
    result = a.query("Geoffrey Hinton")
    assert result["response_status"] == 200
    assert result["fields"]["author_found"] is True
