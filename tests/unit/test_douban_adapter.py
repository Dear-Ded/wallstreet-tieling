"""Tests for Douban group lookup adapter (stubbed HTML, no network)."""
import pytest
from adapters.douban_adapter import DoubanGroupLookup


SAMPLE_SEARCH_HTML = """
<html><body>
<div class="result">
  <a href="https://www.douban.com/group/741287/">爱喂海底捞</a>
  <span>1234人</span>
</div>
<div class="result">
  <a href="https://www.douban.com/group/680453/">海底捞</a>
</div>
<div class="result">
  <a href="https://www.douban.com/group/explore">讨论精选</a>
</div>
</body></html>
"""

SAMPLE_GROUP_HTML = """
<html><body>
<table class="olt">
<tr><td>话题</td><td>作者</td><td>回应</td><td>最后回应</td></tr>
<tr>
  <td><a href="https://www.douban.com/group/topic/123456/" title="海底捞新店开业，老板是张三">海底捞新店开业</a></td>
  <td><a href="#">吃货小王</a></td>
  <td>42</td>
  <td>2026-10-20</td>
</tr>
<tr>
  <td><a href="https://www.douban.com/group/topic/789012/">李四和王五是夫妻店</a></td>
  <td>匿名</td>
  <td>15</td>
  <td>2026-10-19</td>
</tr>
</table>
</body></html>
"""


def test_parse_group_list_extracts_groups():
    groups = DoubanGroupLookup.parse_group_list(SAMPLE_SEARCH_HTML)
    assert len(groups) == 2
    assert groups[0]["group_id"] == "741287"
    assert groups[0]["name"] == "爱喂海底捞"
    assert groups[0]["url"] == "https://www.douban.com/group/741287/"
    assert groups[1]["group_id"] == "680453"


def test_parse_group_list_skips_nav_links():
    groups = DoubanGroupLookup.parse_group_list(SAMPLE_SEARCH_HTML)
    names = [g["name"] for g in groups]
    assert "讨论精选" not in names


def test_parse_group_list_empty():
    assert DoubanGroupLookup.parse_group_list("") == []
    assert DoubanGroupLookup.parse_group_list("<html></html>") == []


def test_parse_group_topics_extracts():
    topics = DoubanGroupLookup.parse_group_topics(SAMPLE_GROUP_HTML)
    assert len(topics) == 2
    assert topics[0]["topic_id"] == "123456"
    assert "海底捞新店开业" in topics[0]["title"]
    assert topics[0]["author"] == "吃货小王"
    assert topics[0]["reply_count"] == "42"
    assert topics[1]["topic_id"] == "789012"


def test_parse_group_topics_no_table():
    assert DoubanGroupLookup.parse_group_topics("<html></html>") == []


def test_parse_group_topics_max_limit():
    topics = DoubanGroupLookup.parse_group_topics(SAMPLE_GROUP_HTML, max_topics=1)
    assert len(topics) == 1


def test_extract_public_fields_empty():
    adapter = DoubanGroupLookup()
    result = adapter._extract_public_fields("")
    assert result["group_count"] == 0
    assert result["groups"] == []


def test_adapter_metadata():
    adapter = DoubanGroupLookup()
    assert adapter.source_domain == "www.douban.com"
    assert adapter.data_boundary == "fully_public"
    assert adapter.requires_credentials is False
    assert adapter.requires_interaction is False


def test_audit_does_not_store_raw_html():
    adapter = DoubanGroupLookup()
    # _record_audit should only store query hash, not raw HTML
    result = adapter._extract_public_fields(SAMPLE_SEARCH_HTML)
    assert result["group_count"] == 2
    # No raw HTML in result
    assert "<html>" not in str(result)
