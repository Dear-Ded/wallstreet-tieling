#!/usr/bin/env python3
"""大众点评适配器单元测试（stubbed，不联网）。"""

import sys
sys.path.insert(0, ".")

from adapters.dianping_adapter import (
    DianpingShopLookup,
    _parse_shop_html,
    _extract_field,
    _extract_number,
)


SAMPLE_HTML = """
<html><body>
<script>
window.shopData = {"shopId":"10000001","shopName":"川味王",
"branchName":"天河店","address":"广州大道北******",
"regionName":"同和/京溪","cityName":"广州",
"phone":"020-******68","avgPrice":85,"shopType":10,
"tasteScore":8.5,"envScore":7.8,"serviceScore":8.2,"commentCount":1234};
</script>
</body></html>
"""

EMPTY_HTML = "<html><body>no shop data here</body></html>"


def test_extract_field():
    assert _extract_field(SAMPLE_HTML, "shopName") == "川味王"
    assert _extract_field(SAMPLE_HTML, "regionName") == "同和/京溪"
    assert _extract_field(EMPTY_HTML, "shopName") is None
    assert _extract_field("", "shopName") is None


def test_extract_number():
    assert _extract_number(SAMPLE_HTML, "avgPrice") == 85.0
    assert _extract_number(SAMPLE_HTML, "tasteScore") == 8.5
    assert _extract_number(EMPTY_HTML, "avgPrice") is None


def test_parse_shop_html_found():
    r = _parse_shop_html(SAMPLE_HTML, "10000001")
    assert r["shop_found"] is True
    assert r["shop_name"] == "川味王"
    assert r["shop_id"] == "10000001"
    assert r["branch_name"] == "天河店"
    assert "广州大道北" in r["address"]
    assert r["avg_price"] == 85.0
    assert r["comment_count"] == 1234.0


def test_parse_shop_html_not_found():
    r = _parse_shop_html(EMPTY_HTML, "999")
    assert r["shop_found"] is False
    assert r["shop_id"] == "999"


def test_query_by_id_routing():
    a = DianpingShopLookup()
    # 纯数字走自主模式（不实际联网，只验证路由逻辑不抛异常结构）
    # 这里只测 query() 的分发逻辑
    r = a.query("not-a-shop")
    assert r.get("interaction_required") is True


def test_query_by_url_extracts_id():
    a = DianpingShopLookup()
    # URL 格式错误时返回 invalid_url，不联网
    r = a.query_by_url("https://example.com/noshop")
    assert r["shop_found"] is False
    assert r["error"] == "invalid_url"


def test_query_invalid_shop_id():
    a = DianpingShopLookup()
    r = a.query_by_shop_id("abc!!")
    assert r["shop_found"] is False
    assert r["error"] == "invalid_shop_id"


if __name__ == "__main__":
    test_extract_field()
    test_extract_number()
    test_parse_shop_html_found()
    test_parse_shop_html_not_found()
    test_query_by_id_routing()
    test_query_by_url_extracts_id()
    test_query_invalid_shop_id()
    print("All dianping adapter tests passed.")
