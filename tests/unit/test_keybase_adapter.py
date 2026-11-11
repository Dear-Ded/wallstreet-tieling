#!/usr/bin/env python3
"""Unit tests for KeybaseIdentityLookup."""

from __future__ import annotations

import json

from adapters.keybase_adapter import KeybaseIdentityLookup
from core.connector_registry import ConnectorRegistry


def _stub(payload):
    body = json.dumps(payload)
    return KeybaseIdentityLookup(
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )


def _max_payload():
    return {"status": {"code": 0}, "them": [{
        "basics": {"username": "max"},
        "proofs_summary": {
            "twitter": [{"proof_type": "twitter", "nametag": "maxtaco", "state": 1}],
            "github": [{"proof_type": "github", "nametag": "maxtaco", "state": 1}],
        },
    }]}


def test_keybase_extracts_proofs():
    adapter = _stub(_max_payload())
    result = adapter.query("max")
    assert result["fields"]["user_found"] is True
    assert result["fields"]["proof_count"] == 2
    assert set(result["fields"]["linked_platforms"]) == {"twitter", "github"}
    assert result["fields"]["linked_identities"]["twitter"] == ["maxtaco"]


def test_keybase_unknown_user():
    adapter = _stub({"status": {"code": 0}, "them": []})
    result = adapter.query("nobody-xyz-123")
    assert result["fields"]["user_found"] is False


def test_keybase_no_proofs_user():
    payload = {"status": {"code": 0}, "them": [
        {"basics": {"username": "torvalds"}, "proofs_summary": {}}]}
    adapter = _stub(payload)
    result = adapter.query("torvalds")
    assert result["fields"]["user_found"] is True
    assert result["fields"]["proof_count"] == 0


def _deep_payload():
    return {"status": {"code": 0}, "them": [{
        "basics": {"username": "max"},
        "profile": {
            "full_name": "Max Krohn",
            "location": "New York, NY",
            "bio": "Keybase.io co-founder",
        },
        "proofs_summary": {
            "all": [{
                "proof_type": "twitter", "nametag": "maxtaco", "state": 1,
                "service_url": "https://twitter.com/maxtaco",
                "proof_url": "https://twitter.com/maxtaco/status/1",
                "sig_id": "a" * 64,
            }],
        },
        "stellar": {
            "hidden": False,
            "primary": {"account_id": "GABC123STELLAR"},
        },
        "cryptocurrency_addresses": {
            "bitcoin": [{"address": "1BYzrCvfbn81dfiksmD1Bdgt8pgLi1SD7Z",
                         "sig_id": "b" * 64}],
        },
        "devices": {
            "deadbeef": {"name": "home-desktop", "type": "desktop",
                         "status": 1, "ctime": 1672435629},
        },
        "public_keys": {
            "primary": {"kid": "0101deadbeef", "key_type": 1,
                        "bundle": "-----BEGIN PGP PUBLIC KEY BLOCK-----"},
        },
        "sigs": {
            "last": {"sig_id": "c" * 64, "seqno": 847,
                     "payload_hash": "d" * 64},
        },
    }]}


def test_keybase_extracts_identity_deep():
    adapter = _stub(_deep_payload())
    result = adapter.query("max")
    fields = result["fields"]
    assert fields["user_found"] is True
    assert fields["full_name"] == "Max Krohn"
    assert fields["location"] == "New York, NY"
    assert fields["bio"] == "Keybase.io co-founder"
    # per-proof deep links
    proof = fields["proofs"][0]
    assert proof["proof_type"] == "twitter"
    assert proof["service_url"] == "https://twitter.com/maxtaco"
    assert proof["proof_url"] == "https://twitter.com/maxtaco/status/1"
    assert proof["sig_id"] == "a" * 64
    deep = fields["identity_deep"]
    assert deep["stellar_account"] == "GABC123STELLAR"
    assert deep["crypto_addresses"]["bitcoin"][0]["address"].startswith("1BYzr")
    assert deep["device_count"] == 1
    assert deep["devices"][0]["name"] == "home-desktop"
    assert deep["primary_pgp_key"]["kid"] == "0101deadbeef"
    assert deep["primary_pgp_key"]["has_bundle"] is True
    assert deep["sig_chain"]["last_seqno"] == 847
    assert deep["sig_chain"]["last_sig_id"] == "c" * 64
    # PGP bundle itself is not persisted
    assert "BEGIN PGP" not in json.dumps(fields)


def test_keybase_deep_absent_fields_default_safely():
    adapter = _stub(_max_payload())
    result = adapter.query("max")
    fields = result["fields"]
    assert fields["full_name"] is None
    assert fields["location"] is None
    deep = fields["identity_deep"]
    assert deep["stellar_account"] is None
    assert deep["crypto_addresses"] == {}
    assert deep["device_count"] == 0
    assert deep["sig_chain"]["last_seqno"] is None


def test_keybase_audit_integrity():
    adapter = _stub(_max_payload())
    adapter.query("max")
    assert adapter.audit.verify_integrity() is True


def test_keybase_registered_default_off():
    names = {c.name: c for c in ConnectorRegistry().list()}
    assert "public_keybase_identity_proofs" in names
    assert names["public_keybase_identity_proofs"].default_enabled is False
