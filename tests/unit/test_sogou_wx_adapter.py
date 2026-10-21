"""Tests for Sogou WeChat article search adapter."""
import pytest
from adapters.sogou_wx_adapter import SogouWxArticleLookup


SAMPLE_HTML = """
<html><body><ul class="news-list">
<li>
<h3><a href="/link?url=abc123&type=2" id="sogou_vr_1_title_0"><em>海底捞</em>为什么永远有人在排队</a></h3>
<p class="txt-info" id="sogou_vr_1_summary_0">火锅店测评，<em>海底捞</em>服务一流</p>
<div class="s-p">
<span class="all-time-y2">丁香生活研究所</span><span class="s2"><script>document.write(timeConvert('1594007644'))</script></span>
</div>
</li>
<li>
<h3><a href="/link?url=def456&type=2" id="sogou_vr_1_title_1">探店：<em>海底捞</em>新菜测评</a></h3>
<p class="txt-info" id="sogou_vr_1_summary_1">新品尝鲜</p>
<div class="s-p">
<span class="all-time-y2">吃货小分队</span><span class="s2"><script>document.write(timeConvert('1700000000'))</script></span>
</div>
</li>
</ul></body></html>
"""


def test_parse_article_list_extracts_fields():
    articles = SogouWxArticleLookup.parse_article_list(SAMPLE_HTML)
    assert len(articles) == 2
    a0 = articles[0]
    assert "海底捞" in a0["title"]
    assert a0["account"] == "丁香生活研究所"
    assert a0["published_date"] == "2020-07-06"  # 1594007644
    assert "火锅店测评" in a0["summary"]
    assert a0["sogou_link"].startswith("/link?url=")


def test_parse_article_list_second_timestamp():
    articles = SogouWxArticleLookup.parse_article_list(SAMPLE_HTML)
    assert articles[1]["published_date"] == "2023-11-14"  # 1700000000
    assert articles[1]["account"] == "吃货小分队"


def test_parse_empty_html():
    assert SogouWxArticleLookup.parse_article_list("") == []
    assert SogouWxArticleLookup.parse_article_list("<html></html>") == []


def test_parse_no_timestamp():
    html = '<h3><a href="/link?url=x">测试标题文章</a></h3><span class="all-time-y2">某账号</span>'
    articles = SogouWxArticleLookup.parse_article_list(html)
    assert len(articles) == 1
    assert articles[0]["published_date"] == ""
    assert articles[0]["account"] == "某账号"


def test_extract_public_fields():
    adapter = SogouWxArticleLookup()
    result = adapter._extract_public_fields(SAMPLE_HTML)
    assert result["article_count"] == 2
    assert result["source"] == "weixin.sogou.com"


def test_build_url():
    adapter = SogouWxArticleLookup()
    url = adapter._build_url("海底捞", page=2)
    assert "type=2" in url
    assert "page=2" in url
    assert "weixin.sogou.com" in url


def test_adapter_metadata():
    adapter = SogouWxArticleLookup()
    assert adapter.data_boundary == "fully_public"
    assert adapter.requires_credentials is False
    assert adapter.source_domain == "weixin.sogou.com"
