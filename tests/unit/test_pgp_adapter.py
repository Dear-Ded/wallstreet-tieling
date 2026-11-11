#!/usr/bin/env python3
"""Tests for adapters.public_pgp_adapter (PgpKeyLookup)."""

import base64
import datetime
import struct

import pytest

from adapters.public_pgp_adapter import (
    PgpKeyLookup,
    _openpgp_packets,
    _parse_armor,
    _parse_uid,
)


def _packet(tag, body):
    """构造 new-format OpenPGP 包（单字节长度，仅测试用）。"""
    assert len(body) < 192
    return bytes([(0x80 | 0x40 | tag), len(body)]) + body


def _make_key_block(name, email, fingerprint, created_ts):
    uid = _packet(13, f"{name} <{email}>".encode("utf-8"))
    pub = _packet(6, bytes([4]) + struct.pack(">I", created_ts)
                  + bytes([1, 0]) + b"\x00" * 8)
    raw = pub + uid
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    fp_groups = " ".join(fingerprint[i : i + 4] for i in range(0, 40, 4))
    return (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
        f"Comment: {fp_groups}\n"
        f"Comment: <{email}>\n\n"
        + "\n".join(lines)
        + "\n-----END PGP PUBLIC KEY BLOCK-----\n"
    )


_FP = "D477040C70C2156A5C298549BB7E9101495E6BF7"
_CREATED = int(datetime.datetime(2023, 12, 6, 23, 54, 51,
                                 tzinfo=datetime.timezone.utc).timestamp())


def _adapter(body=b"", status=200):
    return PgpKeyLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
    )


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------


def test_query_rejects_invalid_input():
    a = _adapter()
    for bad in ("", "not-an-email", "foo@bar", "ZZZ"):
        r = a.query(bad)
        assert r["error"] == "Query blocked: invalid_input", bad


def test_query_rejects_bad_fingerprint_length():
    a = _adapter()
    r = a.query("D477040C70C2")
    assert r["error"] == "Query blocked: invalid_input"


def test_query_accepts_fingerprint():
    block = _make_key_block("Test User", "test@example.com", _FP, _CREATED)
    a = _adapter(block.encode("ascii"))
    r = a.query(_FP.lower())
    assert r["error"] == ""
    assert r["fields"]["found"] is True
    assert r["fields"]["fingerprint"] == _FP


def test_build_url_email_vs_fingerprint():
    a = PgpKeyLookup(robots_checker=lambda d, u: True)
    url = a._build_url("alice@example.org")
    assert url.startswith("https://keys.openpgp.org/vks/v1/by-email/")
    assert "alice%40example.org" in url
    url2 = a._build_url(_FP)
    assert url2 == f"https://keys.openpgp.org/vks/v1/by-fingerprint/{_FP}"


# ---------------------------------------------------------------------------
# 密钥块解析
# ---------------------------------------------------------------------------


def test_parse_key_block_full():
    block = _make_key_block("张三", "zhangsan@example.com", _FP, _CREATED)
    parsed = PgpKeyLookup.parse_key_block(block)
    assert parsed["found"] is True
    assert parsed["fingerprint"] == _FP
    assert parsed["key_id"] == _FP[-16:]
    assert "zhangsan@example.com" in parsed["emails"]
    uid = parsed["uids"][0]
    assert uid["name"] == "张三"
    assert uid["email"] == "zhangsan@example.com"
    assert parsed["key_created"].startswith("2023-12-06T23:54:51")


def test_parse_key_block_email_only_uid():
    # keys.openpgp.org 实际返回的 UID 常只有邮箱（隐私设计）
    block = _make_key_block("", "dkg@debian.org", _FP, _CREATED)
    parsed = PgpKeyLookup.parse_key_block(block)
    assert parsed["uids"][0]["email"] == "dkg@debian.org"
    assert parsed["uids"][0]["name"] == ""
    assert "dkg@debian.org" in parsed["emails"]


def test_parse_key_block_not_a_key():
    assert PgpKeyLookup.parse_key_block("hello world")["found"] is False


def test_parse_armor_crc_line_skipped():
    block = _make_key_block("N", "n@example.com", _FP, _CREATED)
    block = block.replace("-----END", "=abcd\n-----END")
    parsed = PgpKeyLookup.parse_key_block(block)
    assert parsed["found"] is True
    assert parsed["uids"][0]["email"] == "n@example.com"


# ---------------------------------------------------------------------------
# query 端到端（mock 网络）
# ---------------------------------------------------------------------------


def test_query_found():
    block = _make_key_block("Li Lei", "lilei@example.com", _FP, _CREATED)
    a = _adapter(block.encode("ascii"))
    r = a.query("lilei@example.com")
    assert r["response_status"] == 200
    assert r["error"] == ""
    f = r["fields"]
    assert f["found"] is True
    assert f["fingerprint"] == _FP
    assert "lilei@example.com" in f["emails"]
    assert r["source_domain"] == "keys.openpgp.org"
    assert r["data_boundary"] == "fully_public"


def test_query_404_not_found():
    a = _adapter(b"", status=404)
    r = a.query("nobody@example.com")
    assert r["response_status"] == 404
    assert r["fields"].get("found", False) is False


def test_audit_trail_integrity():
    block = _make_key_block("Li Lei", "lilei@example.com", _FP, _CREATED)
    a = _adapter(block.encode("ascii"))
    a.query("lilei@example.com")
    assert a.audit.verify_integrity()
    trail = a.audit.get_trail()
    assert trail and trail[0]["source_domain"] == "keys.openpgp.org"


# ---------------------------------------------------------------------------
# 解析器单元
# ---------------------------------------------------------------------------


def test_parse_uid_variants():
    assert _parse_uid("Daniel Kahn Gillmor <dkg@fifthhorseman.net>") == {
        "name": "Daniel Kahn Gillmor",
        "email": "dkg@fifthhorseman.net",
        "comment": "",
    }
    assert _parse_uid("<dkg@debian.org>") == {
        "name": "",
        "email": "dkg@debian.org",
        "comment": "",
    }
    assert _parse_uid("Alice (work) <alice@example.com>")["comment"] == "work"


def test_openpgp_packets_old_format():
    body = b"UIDDATA"
    raw = bytes([(0x80 | (13 << 2) | 0), len(body)]) + body
    out = list(_openpgp_packets(raw))
    assert out == [(13, body)]
