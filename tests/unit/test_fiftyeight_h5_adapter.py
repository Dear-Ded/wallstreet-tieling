"""Tests for 58同城 mobile H5 adapter (offline fixtures, 2026-10-21 structure)."""

from adapters.fiftyeight_h5_adapter import FiftyEightH5Listing

FIXTURE_LIST = """
<div class="list-item-wrap">
<div class="list-item-container" infoid="88779658380251" uid="111707704000328">
<a class="list-item" onclick=newTrackClickLog(this)
href="https://m.58.com/bj/zufang/88779658380251x.shtml?sid=abc&tid=def">
<div class="list-item-img-container"><div class="list-item-img"
bg-src="https://pic2.58cdn.com.cn/anjuke_58/abcd?w=240&h=180" alt="pic"></div></div>
<ul class="list-item-info">
<li class="list-item-info-title strongbox"> 六号线 北关 家和园 业主 全屋定制 </li>
<li class="list-item-info-addr"><span class="list-item-info-addr-text strongbox"> 2室 永顺 -家和园(通州) </span></li>
<li class="list-item-info-price"><span class="list-item-info-price-wrapper">
<i class="strongbox">4100</i> 元 <span class="list-item-info-date"></span></span></li>
</ul></a></div>
<div class="list-item-container" infoid="88932750017373" uid="999">
<a class="list-item" onclick=newTrackClickLog(this)
href="https://m.58.com/bj/zufang/88932750017373x.shtml">
<ul class="list-item-info">
<li class="list-item-info-title strongbox"> 朝阳 三里屯 一居室 精装 </li>
<li class="list-item-info-addr"><span class="list-item-info-addr-text strongbox"> 1室 三里屯 </span>
<span class="list-item-info-sp-tag">广告</span></li>
<li class="list-item-info-price"><span class="list-item-info-price-wrapper">
<i class="strongbox">6800</i> 元</span></li>
</ul></a></div>
</div>
"""

FIXTURE_DETAIL = """
<html><head><title>【10图】六号线 北关 家和园 业主 全屋定制，永顺北街_通州永顺整租房房源-北京58同城租房网</title></head>
<body><h1>六号线 北关 家和园 业主 全屋定制</h1>
<script>var x={"price":"4100元/月","name":"test"};</script>
<div class="detail-desc-box"><p>南北通透，拎包入住。</p></div>
</body></html>
"""


def _adapter(body, status=200):
    return FiftyEightH5Listing(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_no_query_string():
    a = _adapter("")
    assert a._build_url("kw", city="bj", channel="zufang") == "https://m.58.com/bj/zufang/"


def test_build_url_sanitizes_inputs():
    a = _adapter("")
    assert a._build_url("kw", city="BJ ", channel="zufang") == "https://m.58.com/bj/zufang/"
    assert a._build_url("kw", city="!bad", channel="../x") == "https://m.58.com/bj/zufang/"


def test_parse_listing_list():
    items = FiftyEightH5Listing.parse_listing_list(FIXTURE_LIST)
    assert len(items) == 2
    first = items[0]
    assert first["infoid"] == "88779658380251"
    assert first["detail_url"] == "https://m.58.com/bj/zufang/88779658380251x.shtml"
    assert "六号线" in first["title"]
    assert "2室" in first["addr"]
    assert first["price"].startswith("4100")
    assert first["image"].startswith("https://pic2.58cdn.com.cn")
    assert items[1]["tag"] == "广告"


def test_parse_detail_no_phone():
    d = FiftyEightH5Listing.parse_detail(FIXTURE_DETAIL)
    assert d["login_gated"] is False
    assert "六号线" in d["title"]
    assert "4100" in d["price"]
    assert "南北通透" in d["description"]


def test_login_gate_detected():
    d = FiftyEightH5Listing.parse_detail("<html>404.58.com 反爬</html>")
    assert d["login_gated"] is True


def test_query_returns_structured_leads():
    a = _adapter(FIXTURE_LIST)
    result = a.query("通州租房", city="bj", channel="zufang")
    fields = result["fields"]
    assert fields["blocked"] is False
    assert fields["listing_count"] == 2
    assert result["source_domain"] == "m.58.com"
    assert result["response_status"] == 200
    assert a.audit.verify_integrity()


def test_query_detail_enrichment_opt_in():
    calls = []

    def fake(url, headers):
        calls.append(url)
        if url.endswith("zufang/"):
            return (200, FIXTURE_LIST, "")
        return (200, FIXTURE_DETAIL, "")

    a = FiftyEightH5Listing(
        execute_query=fake,
        robots_checker=lambda d, u: True,
        sleeper=lambda s: None,
    )
    result = a.query("kw", detail=True)
    first = result["fields"]["listings"][0]
    assert "detail" in first
    assert first["detail"]["login_gated"] is False
    assert all("?" not in u for u in calls), "no query strings (robots /*?*)"


def test_blocked_page_returns_empty_listings():
    a = _adapter("<html>404.58.com</html>")
    fields = a._extract_public_fields("<html>404.58.com</html>")
    assert fields["blocked"] is True
    assert fields["listings"] == []
