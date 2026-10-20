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


def test_keybase_audit_integrity():
    adapter = _stub(_max_payload())
    adapter.query("max")
    assert adapter.audit.verify_integrity() is True


def test_keybase_registered_default_off():
    names = {c.name: c for c in ConnectorRegistry().list()}
    assert "public_keybase_identity_proofs" in names
    assert names["public_keybase_identity_proofs"].default_enabled is False
