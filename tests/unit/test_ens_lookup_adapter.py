"""Tests for ENS bidirectional lookup adapter (offline fixtures)."""

import json

from adapters.ens_lookup_adapter import ENSLookup, _looks_like_address

FIXTURE_NAME = json.dumps({
    "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "name": "vitalik.eth",
    "displayName": "vitalik.eth",
    "avatar": "https://metadata.ens.domains/mainnet/avatar/vitalik.eth",
})
FIXTURE_UNRESOLVED = json.dumps({"address": "", "name": ""})


def _adapter(body, status=200):
    return ENSLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_encodes_name():
    a = _adapter("")
    assert a._build_url("vitalik.eth").endswith("/ens/resolve/vitalik.eth")
    assert "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045" in a._build_url("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


def test_forward_lookup_name_to_address():
    fields = _adapter(FIXTURE_NAME).query("vitalik.eth")["fields"]
    assert fields["resolved"] is True
    assert fields["name"] == "vitalik.eth"
    assert fields["address"] == "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_reverse_lookup_address_to_name():
    fields = _adapter(FIXTURE_NAME).query("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")["fields"]
    assert fields["resolved"] is True
    assert fields["name"] == "vitalik.eth"


def test_unresolved_returns_not_resolved():
    fields = _adapter(FIXTURE_UNRESOLVED).query("no-such-name-xyz.eth")["fields"]
    assert fields["resolved"] is False


def test_parse_entry_offline():
    parsed = ENSLookup.parse_lookup_result(FIXTURE_NAME)
    assert parsed["resolved"] is True and parsed["name"] == "vitalik.eth"


def test_looks_like_address():
    assert _looks_like_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    assert not _looks_like_address("vitalik.eth")
    assert not _looks_like_address("0xZZZ")
