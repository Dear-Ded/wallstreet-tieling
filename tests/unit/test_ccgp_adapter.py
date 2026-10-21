#!/usr/bin/env python3
"""Tests for adapters.ccgp_adapter (CcgpBidLookup)."""

import json
import pytest

from adapters.ccgp_adapter import CcgpBidLookup


# ---------------------------------------------------------------------------
# parse_search_results
# ---------------------------------------------------------------------------

def _make_search_html(results, total=None):
    """构造一个模拟的 bxsearch 结果页。"""
    json_str = json.dumps(results, ensure_ascii=False)
    total = total if total is not None else len(results)
    return f"""<html><head><title>test</title></head><body>
<div>共 {total} 条结果</div>
<script>var a='{json_str}';</script>
</body></html>"""


def test_parse_search_results_basic():
    results = [
        {"number": "1", "title": "测试项目成交公告",
         "dep": "测试单位", "proj_nm": "测试项目",
         "date": "2026-10-21",
         "lnk": "http://www.ccgp.gov.cn/cggg/dfgg/cjgg/202610/t20261021_1.htm"},
        {"number": "2", "title": "另一个项目",
         "dep": "另一单位", "proj_nm": "另一项目",
         "date": "2026-10-20",
         "lnk": "http://www.ccgp.gov.cn/cggg/dfgg/cjgg/202610/t20261020_2.htm"},
    ]
    html = _make_search_html(results)
    parsed = CcgpBidLookup.parse_search_results(html)
    assert not parsed["rate_limited"]
    assert parsed["total"] == 2
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["title"] == "测试项目成交公告"
    assert parsed["results"][1]["lnk"].endswith("t20261020_2.htm")


def test_parse_search_results_empty():
    html = _make_search_html([], total=0)
    parsed = CcgpBidLookup.parse_search_results(html)
    assert not parsed["rate_limited"]
    assert parsed["total"] == 0
    assert parsed["results"] == []


def test_parse_search_results_rate_limited():
    html = "<html><body>您的访问过于频繁,请稍后再试。</body></html>"
    parsed = CcgpBidLookup.parse_search_results(html)
    assert parsed["rate_limited"]
    assert parsed["results"] == []


def test_parse_search_results_malformed():
    html = "<html><body>no json here</body></html>"
    parsed = CcgpBidLookup.parse_search_results(html)
    assert not parsed["rate_limited"]
    assert parsed["results"] == []


# ---------------------------------------------------------------------------
# parse_detail_page
# ---------------------------------------------------------------------------

def _make_detail_html():
    """构造一个模拟的成交公告详情页。"""
    return """<html><head><title>测试项目成交公告</title></head><body>
<h2><strong><span>三、中标（成交）信息</span></strong></h2>
<div>
序号 供应商名称 社会信用代码 供应商地址 评审报价 中标/成交金额
1 测试科技有限公司 91110000MA00TEST01 北京市海淀区测试路1号 100.00元 95.50元
</div>
<h2>四、主要标的信息</h2>
<div>名称：测试设备 数量：10</div>
<h2>五、评审专家名单：</h2>
<div>张三、李四、王五</div>
<h2>九、凡对本次公告内容提出询问，请按以下方式联系</h2>
<div>
1.采购人信息
单位名称：测试采购单位
单位地址：北京市朝阳区采购路2号
联系人：赵先生
联系电话：13800001111
2.采购代理机构信息
单位名称：测试代理公司
联系人：钱女士
联系电话：010-88887777
</div>
</body></html>"""


def test_parse_detail_page_title():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    assert detail["title"] == "测试项目成交公告"


def test_parse_detail_page_supplier():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    assert len(detail["suppliers"]) >= 1
    s = detail["suppliers"][0]
    assert s["credit_code"] == "91110000MA00TEST01"
    assert "测试科技" in s.get("name", "")
    assert s.get("amount") == "95.50"


def test_parse_detail_page_contacts():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    names = [c["name"] for c in detail["contacts"]]
    assert "赵先生" in names
    assert "钱女士" in names


def test_parse_detail_page_phones():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    phones_joined = " ".join(detail["phones"])
    assert "13800001111" in phones_joined
    assert "01088887777" in phones_joined or "010-88887777" in phones_joined


def test_parse_detail_page_buyer():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    assert "测试采购单位" in detail["buyer"].get("name", "")


def test_parse_detail_page_experts():
    detail = CcgpBidLookup.parse_detail_page(_make_detail_html())
    assert "张三" in detail["experts"]
    assert "李四" in detail["experts"]


def test_parse_detail_page_empty():
    detail = CcgpBidLookup.parse_detail_page("<html><body>empty</body></html>")
    assert detail["suppliers"] == []
    assert detail["contacts"] == []
    assert detail["phones"] == []


# ---------------------------------------------------------------------------
# query() input validation (no network)
# ---------------------------------------------------------------------------

def test_query_empty_keyword():
    adapter = CcgpBidLookup()
    result = adapter.query("")
    assert result["status"] == "invalid_input"


def test_query_whitespace_keyword():
    adapter = CcgpBidLookup()
    result = adapter.query("   ")
    assert result["status"] == "invalid_input"


def test_query_detail_invalid_url():
    adapter = CcgpBidLookup()
    result = adapter.query_detail("")
    assert result["status"] == "invalid_input"
    result = adapter.query_detail("not-a-url")
    assert result["status"] == "invalid_input"


# ---------------------------------------------------------------------------
# adapter metadata
# ---------------------------------------------------------------------------

def test_adapter_metadata():
    adapter = CcgpBidLookup()
    assert adapter.source_domain == "www.ccgp.gov.cn"
    assert adapter.data_boundary == "fully_public"
    assert not adapter.requires_interaction


def test_search_url_constants():
    assert "search.ccgp.gov.cn" in CcgpBidLookup.SEARCH_URL
    assert "bxsearch" in CcgpBidLookup.SEARCH_URL
