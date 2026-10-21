"""Unit tests for DNSdumpsterLookup (dnsdumpster.com DNS recon adapter)."""
import json
import pytest
from adapters.dnsdumpster_adapter import DNSdumpsterLookup


SAMPLE_A_TABLE = """\
<table id="a_rec_table">
<tr><th>Host</th><th>IP</th><th>ASN</th><th>ASN Name</th><th>Open Services (from DB)</th><th>RevIP</th><th></th></tr>
<tr>
<td>beta.example.com</td>
<td>93.184.216.34<br>
<span class="xs-text">34.216.184.93.in-addr.arpa</span></td>
<td><span class="xs-text light-text">ASN:</span><span class="sm-text">15133</span><br>
<span class="sm-text">93.184.216.0/24</span></td>
<td><span class="sm-text">EDGECAST - Edgecast Inc.</span><br>
<span class="sm-text">United States</span></td>
<td><span class="xs-text light-text">https:</span> nginx<br></td>
<td><span class="sm-text" style="text-align: center;">5</span></td>
<td><div class="kebab-menu"></div></td>
</tr>
<tr>
<td>hr.example.com</td>
<td>93.184.216.35<br></td>
<td><span class="xs-text light-text">ASN:</span><span class="sm-text">15133</span><br>
<span class="sm-text">93.184.216.0/24</span></td>
<td><span class="sm-text">EDGECAST</span></td>
<td></td>
<td><span class="sm-text">1</span></td>
<td></td>
</tr>
</table>
"""

SAMPLE_PAGE = """\
<!-- templates/index.html -->
<div class="main-alert">Free users are limited to 50 results for a single domain.</div>
<h2>A Records (subdomains from dataset)</h2>
""" + SAMPLE_A_TABLE + """\
<h2>MX Records</h2>
<table>
<tr><th>Host</th><th>IP</th><th>ASN</th><th>ASN Name</th></tr>
<tr>
<td>10 mail.example.com</td>
<td>93.184.216.100<br><span class="xs-text">mail.example.com</span></td>
<td><span class="xs-text light-text">ASN:</span><span class="sm-text">15133</span><br>
<span class="sm-text">93.184.216.0/24</span></td>
<td><span class="sm-text">EDGECAST</span></td>
<td></td><td></td><td></td>
</tr>
</table>
<h2>NS Records</h2>
<table>
<tr><td>ns1.example.com</td><td>93.184.216.2<br></td>
<td><span class="xs-text light-text">ASN:</span><span class="sm-text">15133</span><br>
<span class="sm-text">93.184.216.0/24</span></td>
<td><span class="sm-text">EDGECAST</span></td><td></td><td></td><td></td></tr>
</table>
<h2>TXT Records</h2>
<table>
<tr><td>&#34;v=spf1 include:_spf.example.com ~all&#34;</td></tr>
<tr><td>&#34;google-site-verification=abc123&#34;</td></tr>
</table>
"""

INVALID_PAGE = """\
<!-- templates/error.html -->
<div class="alert-danger">
<p>Error: Invalid domain, check input and try again.</p>
</div>
"""


def _adapter(**overrides):
    a = DNSdumpsterLookup(**overrides)
    a._robots_checker = lambda *args: True
    return a


# ------------------------------------------------------------------
# Domain normalization
# ------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("example.com", "example.com"),
    ("https://example.com/", "example.com"),
    ("http://www.example.com/path?q=1", "example.com"),
    ("WWW.EXAMPLE.COM:8080/x", "example.com"),
    ("  sub.example.com  ", "sub.example.com"),
    ("", ""),
])
def test_normalize_domain(raw, expected):
    assert DNSdumpsterLookup._normalize_domain(raw) == expected


# ------------------------------------------------------------------
# A-record table parsing
# ------------------------------------------------------------------

def test_parse_host_table_basic():
    records = DNSdumpsterLookup._parse_host_table(
        SAMPLE_A_TABLE.split("</table>")[0] + "</table>"
    )
    assert len(records) == 2
    first = records[0]
    assert first["host"] == "beta.example.com"
    assert first["ip"] == "93.184.216.34"
    assert first["reverse_dns"] == "34.216.184.93.in-addr.arpa"
    assert first["asn_number"] == "15133"
    assert first["asn_prefix"] == "93.184.216.0/24"
    assert "EDGECAST" in first["asn_name"]
    assert "https:" in first["open_services"] and "nginx" in first["open_services"]
    assert first["revip_count"] == 5


def test_parse_host_table_missing_optionals():
    records = DNSdumpsterLookup._parse_host_table(
        SAMPLE_A_TABLE.split("</table>")[0] + "</table>"
    )
    second = records[1]
    assert second["host"] == "hr.example.com"
    assert second["reverse_dns"] == ""
    assert second["open_services"] == ""
    assert second["revip_count"] == 1


def test_parse_host_table_skips_header():
    records = DNSdumpsterLookup._parse_host_table("<table><tr><th>Host</th></tr></table>")
    assert records == []


# ------------------------------------------------------------------
# Full page parsing
# ------------------------------------------------------------------

def test_parse_result_html_full():
    fields = DNSdumpsterLookup.parse_result_html(SAMPLE_PAGE)
    assert fields["subdomain_count"] == 2
    assert fields["subdomains"] == ["beta.example.com", "hr.example.com"]
    assert fields["truncated"] is False
    assert fields["free_tier_limit_noticed"] is True
    assert fields["ip_count"] == 4
    assert set(fields["distinct_ips"]) == {
        "93.184.216.34", "93.184.216.35", "93.184.216.100", "93.184.216.2"}
    assert fields["distinct_asns"] == ["AS15133"]
    assert len(fields["mx_records"]) == 1
    mx = fields["mx_records"][0]
    assert mx["priority"] == 10
    assert mx["host"] == "mail.example.com"
    assert mx["ip"] == "93.184.216.100"
    assert len(fields["ns_records"]) == 1
    assert fields["ns_records"][0]["host"] == "ns1.example.com"
    assert fields["txt_records"] == [
        "v=spf1 include:_spf.example.com ~all",
        "google-site-verification=abc123",
    ]


def test_interesting_subdomains_flagged():
    fields = DNSdumpsterLookup.parse_result_html(SAMPLE_PAGE)
    labels = {i["label"] for i in fields["interesting_subdomains"]}
    assert "hr" in labels
    assert "beta" in labels


def test_invalid_domain_detected():
    fields = DNSdumpsterLookup.parse_result_html(INVALID_PAGE)
    assert fields["query_rejected"] == "invalid_domain"
    assert fields["subdomain_count"] == 0


def test_parse_empty_and_garbage():
    assert DNSdumpsterLookup.parse_result_html("") == {}
    assert DNSdumpsterLookup.parse_result_html("<html>502 Bad Gateway</html>")["subdomain_count"] == 0


def test_truncated_when_hitting_cap():
    rows = "".join(
        f"<tr><td>h{i}.example.com</td><td>1.2.3.{i % 250}<br></td>"
        f"<td><span>ASN:</span><span>1</span></td><td>x</td><td></td><td>0</td><td></td></tr>"
        for i in range(50)
    )
    page = f'<table id="a_rec_table">{rows}</table>'
    fields = DNSdumpsterLookup.parse_result_html(page)
    assert fields["subdomain_count"] == 50
    assert fields["truncated"] is True


# ------------------------------------------------------------------
# Transport / query()
# ------------------------------------------------------------------

def test_build_url_is_post_endpoint_and_stashes_domain():
    a = _adapter()
    url = a._build_url("https://www.example.com/x")
    assert url == "https://dnsdumpster.com/htmld/"
    assert a._last_domain == "example.com"


def _stub_execute(url, headers):
    assert url == "https://dnsdumpster.com/htmld/"
    return (200, SAMPLE_PAGE, "")


def test_query_success():
    a = _adapter(execute_query=_stub_execute)
    result = a.query("example.com")
    assert result["response_status"] == 200
    assert result["fields"]["subdomain_count"] == 2
    assert "query_subject_hash" in result
    assert len(a.audit.get_trail()) == 1


def test_query_empty_body_returns_empty_fields():
    a = _adapter(execute_query=lambda u, h: (200, "", ""))
    result = a.query("example.com")
    assert result["fields"] == {}
    assert result["response_status"] == 200


def test_execute_query_rejects_empty_domain():
    a = _adapter()
    a._last_domain = ""
    status, raw, err = a._execute_query("https://dnsdumpster.com/htmld/", {})
    assert status == 0
    assert raw is None
    assert "empty_domain" in err


def test_execute_query_posts_target_form(monkeypatch):
    import urllib.request
    captured = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html>ok</html>"

    def fake_urlopen(req, **kwargs):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["data"] = req.data
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    a = _adapter()
    a._build_url("example.com")
    status, raw, err = a._execute_query("https://dnsdumpster.com/htmld/", a._build_headers())
    assert status == 200
    assert err == ""
    assert captured["method"] == "POST"
    assert b"target=example.com" in captured["data"]


# ------------------------------------------------------------------
# Metadata / audit
# ------------------------------------------------------------------

def test_default_metadata():
    a = DNSdumpsterLookup()
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.requires_interaction is False
    assert a.min_request_interval >= 5.0


def test_robots_disallowed_returns_empty():
    a = DNSdumpsterLookup()
    a._robots_checker = lambda *args: False
    result = a.query("example.com")
    assert result["fields"] == {} or result.get("error")


def test_audit_record_has_no_raw_query():
    a = _adapter(execute_query=_stub_execute)
    a.query("example.com")
    trail = a.audit.get_trail()
    assert len(trail) == 1
    rec = trail[0]
    assert rec["source_domain"] == "dnsdumpster.com"
    assert rec["data_boundary"] == "fully_public"
    assert "example.com" not in json.dumps(rec, ensure_ascii=False)
