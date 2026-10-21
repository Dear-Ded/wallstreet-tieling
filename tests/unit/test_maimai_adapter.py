"""Tests for MaimaiArticleLookup adapter."""
import json
import pytest
from adapters.maimai_adapter import MaimaiArticleLookup


SAMPLE_SOGOU_HTML = """
<html><body>
<a href="https://maimai.cn/article/detail?fid=1852506051&amp;efid=_8ikJIc-S-L_S93RhUkydg">article1</a>
<a href="https://maimai.cn/article/detail?fid=1746172043&efid=Uo_TKYGVr74ZP7xOB965Bg">article2</a>
<a href="https://example.com/not-maimai">other</a>
</body></html>"""


def _make_next_data(feed: dict) -> str:
    payload = {"props": {"pageProps": {"data": {"feed": feed}}}}
    return (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></html>"
    )


SAMPLE_FEED = {
    "id": 1852506051,
    "efid": "_8ikJIc-S-L_S93RhUkydg",
    "title": "<dref t=1 v=170995573 j=0 ac=0>代晴</dref> 采购指南",
    "crtime": "2024-11-04 09:15:08",
    "likes": {"n": 2, "me": 0},
    "dviews": 39,
    "views": 0,
    "main": {
        "text": "采购必知的285个寻源网站",
        "html": "<p>采购必知</p>",
        "pics": [],
        "u": {
            "id": 170995573,
            "mmid": "170995573",
            "name": "代晴",
            "realname": "代晴",
            "company": "某科技公司",
            "position": "采购经理",
            "career": "采购经理",
        },
        "utype": 2,
    },
}


def test_parse_search_results_extracts_urls():
    arts = MaimaiArticleLookup.parse_search_results(SAMPLE_SOGOU_HTML)
    assert len(arts) == 2
    assert arts[0]["fid"] == "1852506051"
    assert arts[0]["efid"] == "_8ikJIc-S-L_S93RhUkydg"
    assert arts[0]["url"].startswith("https://maimai.cn/article/detail")
    assert arts[1]["fid"] == "1746172043"


def test_parse_search_results_empty():
    assert MaimaiArticleLookup.parse_search_results("") == []
    assert MaimaiArticleLookup.parse_search_results("<rss></rss>") == []


def test_parse_article_extracts_author():
    html = _make_next_data(SAMPLE_FEED)
    parsed = MaimaiArticleLookup.parse_article(html)
    assert parsed["fid"] == "1852506051"
    assert "代晴" in parsed["title"]
    assert "<dref" not in parsed["title"]
    assert parsed["author"]["name"] == "代晴"
    assert parsed["author"]["company"] == "某科技公司"
    assert parsed["author"]["position"] == "采购经理"
    assert parsed["author"]["mmid"] == "170995573"
    assert parsed["likes"] == 2
    assert parsed["views"] == 39
    assert parsed["publish_time"] == "2024-11-04 09:15:08"
    assert "采购必知" in parsed["text"]


def test_parse_article_garbage_input():
    assert MaimaiArticleLookup.parse_article("") == {}
    assert MaimaiArticleLookup.parse_article("<html></html>") == {}
    assert MaimaiArticleLookup.parse_article(
        '<script id="__NEXT_DATA__" type="application/json">not json</script>'
    ) == {}


def test_parse_article_missing_author():
    feed = {"id": 1, "main": {"text": "hi", "u": {}}}
    parsed = MaimaiArticleLookup.parse_article(_make_next_data(feed))
    assert parsed["author"]["name"] == ""
    assert parsed["text"] == "hi"


def test_build_url_targets_sogou_site_search():
    a = MaimaiArticleLookup()
    url = a._build_url("腾讯")
    assert "sogou.com/web" in url
    assert "maimai.cn" in url


def test_adapter_metadata():
    a = MaimaiArticleLookup()
    assert a.source_domain == "maimai.cn"
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.requires_interaction is False
