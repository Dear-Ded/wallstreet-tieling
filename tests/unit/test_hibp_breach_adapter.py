"""Tests for HaveIBeenPwned public breach catalog adapter (offline fixtures)."""

import urllib.request

import pytest

from adapters.hibp_breach_adapter import HIBPBreachCatalog

FIXTURE = """
<table><tbody>
<tr id="Adobe">
  <td data-name="breach" data-value="Adobe"><div class="d-flex align-items-center"><div>Adobe</div></div></td>
  <td data-name="pwncount" data-value="152445165">152.4M</td>
  <td data-name="date" data-value="635217120000000000" class="d-none d-md-table-cell">4 Dec 2013</td>
  <td data-name="breachDate" data-value="635164416000000000" class="d-none d-lg-table-cell">Oct 2013</td>
  <td class="table-actions"><a href="/Breach/Adobe" class="btn">go</a></td>
</tr>
<tr id="LinkedInScrape2023">
  <td data-name="breach" data-value="LinkedIn Scraped and Fake Data"><div><div>LinkedIn Scraped and Fake Data</div></div></td>
  <td data-name="pwncount" data-value="0"></td>
  <td data-name="date" data-value="638349984000000000" class="d-none d-md-table-cell">14 Nov 2023</td>
  <td data-name="breachDate" data-value="638349984000000000" class="d-none d-lg-table-cell">Nov 2023</td>
  <td class="table-actions"><a href="/Breach/LinkedInScrape2023" class="btn">go</a></td>
</tr>
</tbody></table>
"""

ROBOTS_OK = """User-agent: *
Content-Signal: ai-train=no, ai-input=no, search=yes
Disallow: /account/*
Disallow: /unifiedsearch/*
"""

ROBOTS_BLOCK = """User-agent: *
Disallow: /PwnedWebsites
"""


class _Resp:
    def __init__(self, body):
        self.status = 200
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def net():
    """Fake urllib.request.urlopen keyed by URL suffix; records calls."""
    calls = []
    bodies = {"robots": ROBOTS_OK, "catalog": FIXTURE}

    def fake_urlopen(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        if url.endswith("/robots.txt"):
            return _Resp(bodies["robots"])
        return _Resp(bodies["catalog"])

    real = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        yield calls, bodies
    finally:
        urllib.request.urlopen = real


def _adapter():
    return HIBPBreachCatalog(sleeper=lambda s: None)


def test_parse_catalog_rows():
    rows = HIBPBreachCatalog.parse_catalog(FIXTURE)
    assert len(rows) == 2
    adobe = rows[0]
    assert adobe["id"] == "Adobe"
    assert adobe["title"] == "Adobe"
    assert adobe["pwn_count"] == 152445165
    assert adobe["pwn_count_display"] == "152.4M"
    assert adobe["added_date"] == "4 Dec 2013"
    assert adobe["breach_date"] == "Oct 2013"
    assert adobe["breach_url"] == "https://haveibeenpwned.com/Breach/Adobe"


def test_parse_catalog_empty():
    assert HIBPBreachCatalog.parse_catalog("") == []


def test_query_exact_match(net):
    r = _adapter().query("adobe")
    assert r["data_boundary"] == "fully_public"
    assert r["match_count"] == 1
    assert r["breaches"][0]["id"] == "Adobe"
    assert r["catalog_size"] == 2


def test_query_partial_match(net):
    r = _adapter().query("linkedin")
    assert r["match_count"] == 1
    assert r["breaches"][0]["id"] == "LinkedInScrape2023"


def test_query_no_match(net):
    r = _adapter().query("definitelynotabreachedservicexyz")
    assert r["match_count"] == 0
    assert r["breaches"] == []
    assert r["response_status"] == 200


def test_query_empty_keyword(net):
    r = _adapter().query("   ")
    assert "empty_query" in r["error"]


def test_catalog_cached_second_query_no_refetch(net):
    calls, _ = net
    a = _adapter()
    a.query("adobe")
    a.query("linkedin")
    catalog_hits = [u for u in calls if u.endswith("/PwnedWebsites")]
    assert len(catalog_hits) == 1, f"catalog refetched: {calls}"


def test_robots_disallow_blocks_query(net):
    _, bodies = net
    bodies["robots"] = ROBOTS_BLOCK
    r = _adapter().query("adobe")
    assert "robots_txt_disallowed" in r["error"]
    assert r["fields"] == {}


def test_robots_allows_pwnedwebsites(net):
    # Content-Signal line makes urllib.robotparser drop all rules (entries==[]);
    # the hand-written parser must still work.
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(ROBOTS_OK.splitlines())
    assert rp.entries == [], "urllib quirk precondition changed"
    assert _adapter()._check_robots() is True  # /PwnedWebsites not disallowed


def test_audit_trail_recorded(net):
    a = _adapter()
    a.query("adobe")
    trail = a.audit.get_trail()
    assert trail, "audit trail empty"
    assert trail[-1]["source_domain"] == "haveibeenpwned.com"
    assert trail[-1]["data_boundary"] == "fully_public"
    assert trail[-1]["robots_txt_allowed"] is True


def test_rate_limit_and_no_credentials():
    assert HIBPBreachCatalog.min_request_interval >= 3.0
    assert HIBPBreachCatalog.requires_credentials is False
