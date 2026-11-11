"""Unit tests for Zauba customs adapter (offline parsing + validation)."""
import pytest
from adapters.customs_adapter import ZaubaCustomsLookup

SAMPLE_SEARCH_HTML = """
<html><head><title>Huawei Importers | Zauba</title></head><body>
<table class="table table-striped table-hover table-bordered" id="data-table">
<thead><tr><th>Importer</th></tr></thead><tbody>
<tr><td class="party-name"><a href="/general-motors-llc-report-ithqgcuo9dkb">GENERAL MOTORS LLC</a></td><td class="metric-cell">139</td><td class="metric-cell weight-cell">1.5 thousand metric tons</td><td class="metric-cell">14 May 2026</td></tr>
<tr><td class="party-name"><a href="/cornell-dubilier-electronics-inc-report-3v5mxgh9j1bk">CORNELL DUBILIER ELECTRONICS INC</a></td><td class="metric-cell">40</td><td class="metric-cell weight-cell">223 metric tons</td><td class="metric-cell">29 Sep 2026</td></tr>
</tbody></table></body></html>
"""

SAMPLE_DETAIL_HTML = """
<html><head><title>SHANGHAI HUAWEI AUTOMOTIVE PARTS CO LTD | Zauba</title></head><body>
<p>HS Code: 870829</p><p>HS Code: 8517</p>
<table><thead><tr><th>Port of Discharge</th><th>Shipments</th><th>Total Weight (kg)</th></tr></thead>
<tbody><tr><td>LOS ANGELES, CA</td><td>185</td><td>2,644,372</td></tr>
<tr><td>HOUSTON, TX</td><td>55</td><td>127,907</td></tr></tbody></table>
<a href="/general-motors-llc-report-ithqgcuo9dkb">GENERAL MOTORS LLC</a>
<a href="/gm-fairfax-asm-report-67maiex8vs1t">GM FAIRFAX ASM</a>
</body></html>
"""


def test_parse_search_page_basic():
    parties = ZaubaCustomsLookup.parse_search_page(SAMPLE_SEARCH_HTML)
    assert len(parties) == 2
    assert parties[0]["name"] == "GENERAL MOTORS LLC"
    assert parties[0]["shipment_count"] == 139
    assert parties[0]["total_weight"] == "1.5 thousand metric tons"
    assert parties[0]["latest_shipment"] == "14 May 2026"
    assert parties[0]["report_url"] == "https://www.zauba.com/general-motors-llc-report-ithqgcuo9dkb"
    assert parties[1]["name"] == "CORNELL DUBILIER ELECTRONICS INC"
    assert parties[1]["shipment_count"] == 40


def test_parse_search_page_empty():
    assert ZaubaCustomsLookup.parse_search_page("") == []
    assert ZaubaCustomsLookup.parse_search_page("<html></html>") == []


def test_parse_search_page_max_results():
    parties = ZaubaCustomsLookup.parse_search_page(SAMPLE_SEARCH_HTML, max_results=1)
    assert len(parties) == 1


def test_parse_detail_page():
    d = ZaubaCustomsLookup.parse_detail_page(SAMPLE_DETAIL_HTML)
    assert d["company_name"] == "SHANGHAI HUAWEI AUTOMOTIVE PARTS CO LTD"
    assert "870829" in d["hs_codes"]
    assert "8517" in d["hs_codes"]
    assert "GENERAL MOTORS LLC" in d["counterparties"]
    assert "GM FAIRFAX ASM" in d["counterparties"]
    assert d["ports_of_discharge"][0]["port"] == "LOS ANGELES, CA"
    assert d["ports_of_discharge"][0]["shipments"] == 185
    assert d["ports_of_discharge"][0]["total_weight_kg"] == 2644372


def test_parse_detail_page_empty():
    assert ZaubaCustomsLookup.parse_detail_page("") == {}


def test_query_empty_keyword():
    a = ZaubaCustomsLookup()
    r = a.query("")
    assert r["status"] == "invalid_input"


def test_query_invalid_category():
    a = ZaubaCustomsLookup()
    r = a.query("huawei", category="bogus")
    assert r["status"] == "invalid_input"


def test_query_company_detail_invalid_url():
    a = ZaubaCustomsLookup()
    r = a.query_company_detail("https://example.com/foo")
    assert r["error"] == "invalid_report_url"
    r = a.query_company_detail("")
    assert r["error"] == "invalid_report_url"


def test_adapter_metadata():
    a = ZaubaCustomsLookup()
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.requires_interaction is False
    assert a.min_request_interval >= 2.0


def test_live_search_smoke():
    """Live smoke (mocked HTTP): zauba search returns structured parties."""
    pytest.importorskip("requests")
    a = ZaubaCustomsLookup()
    # monkeypatch robots check to avoid network dependency in unit run
    a._check_robots = lambda: True
    import unittest.mock as mock
    fake_html = SAMPLE_SEARCH_HTML
    with mock.patch("urllib.request.urlopen") as mg:
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = fake_html.encode("utf-8")
        fake_resp.status = 200
        mg.return_value.__enter__.return_value = fake_resp
        r = a.query("huawei", category="exporters", max_results=5)
    assert r["fields"]["party_count"] == 2
    assert r["fields"]["category"] == "exporters"
    assert r["fields"]["parties"][0]["name"] == "GENERAL MOTORS LLC"
    assert r["data_boundary"] == "fully_public"
