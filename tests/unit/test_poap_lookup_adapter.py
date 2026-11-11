"""Tests for POAP badge holdings adapter (offline fixtures)."""

import json

from adapters.poap_lookup_adapter import POAPBadgeLookup

FIXTURE_SCAN = json.dumps([
    {"event": {"id": 1, "fancy_id": "ethcc-2024", "name": "EthCC 2024",
               "event_url": "", "image_url": "https://assets.poap.xyz/x.png",
               "country": "Belgium", "city": "Brussels",
               "description": "d", "year": 2024,
               "start_date": "08-Jul-2024", "end_date": "11-Jul-2024",
               "timezone": "Europe/Brussels", "expiry_date": ""}},
    {"event": {"id": 2, "fancy_id": "devcon-7", "name": "Devcon 7",
               "event_url": "", "image_url": "https://assets.poap.xyz/y.png",
               "country": "Thailand", "city": "Bangkok",
               "description": "d", "year": 2024,
               "start_date": "12-Nov-2024", "end_date": "15-Nov-2024",
               "timezone": "Asia/Bangkok", "expiry_date": ""}},
])
FIXTURE_EMPTY = json.dumps([])


def _adapter(body, status=200):
    return POAPBadgeLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url():
    a = _adapter("")
    url = a._build_url("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    assert url.startswith("https://frontend.poap.tech/actions/scan/0x")


def test_scan_parses_badges_and_cities():
    fields = _adapter(FIXTURE_SCAN).query("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")["fields"]
    assert fields["badge_count"] == 2
    names = [b["event_name"] for b in fields["badges"]]
    assert "EthCC 2024" in names and "Devcon 7" in names
    assert "Brussels" in fields["cities_seen"] and "Bangkok" in fields["cities_seen"]


def test_empty_scan():
    fields = _adapter(FIXTURE_EMPTY).query("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")["fields"]
    assert fields["badge_count"] == 0 and fields["badges"] == []


def test_invalid_address_short_circuits():
    result = _adapter(FIXTURE_SCAN).query("not-an-address")
    assert result["error"] == "invalid_ethereum_address"
    assert result["fields"] == {}


def test_parse_entry_offline():
    badges = POAPBadgeLookup.parse_scan_result(FIXTURE_SCAN)
    assert len(badges) == 2 and badges[0]["city"] == "Brussels"
