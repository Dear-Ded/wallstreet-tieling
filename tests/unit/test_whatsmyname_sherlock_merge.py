"""Sherlock dataset merge (2026-10-21): detect semantics + merged data checks."""

import json
import os
import urllib.request

from adapters.whatsmyname_adapter import WhatsMyNameLookup


def _adapter():
    return WhatsMyNameLookup(
        robots_checker=lambda d, u: True, sleeper=lambda s: None
    )


class _FakeResp:
    def __init__(self, status=200, body=b"", final_url=""):
        self.status = status
        self._body = body
        self._final = final_url

    def read(self):
        return self._body

    def geturl(self):
        return self._final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, status=200, body=b"", final_url="https://example.com/x"):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=15: _FakeResp(status, body, final_url),
    )


def _site(**kw):
    base = {
        "name": "TestSherlock",
        "uri_check": "https://example.com/{account}",
        "cat": "",
    }
    base.update(kw)
    return base


def test_dataset_merge_site_count():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "adapters", "_vendor",
        "whatsmyname", "wmn-data.json",
    )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sites = data["sites"]
    assert len(sites) == 978, f"expected 692+286=978, got {len(sites)}"
    sherlock = [s for s in sites if s.get("source") == "sherlock-project/sherlock"]
    assert len(sherlock) == 286
    # no duplicate normalized names after merge
    names = ["".join(c for c in s.get("name", "").lower() if c.isalnum())
             for s in sites]
    assert len(names) == len(set(names)), "duplicate site names after merge"
    # all merged entries carry detection semantics + license
    for s in sherlock:
        assert s.get("detect") in ("message", "status_code", "response_url")
        assert s.get("license") == "MIT"
        assert "{account}" in s["uri_check"]


def test_detect_message_found(monkeypatch):
    _patch_urlopen(monkeypatch, 200, b"<html>profile of testuser</html>")
    a = _adapter()
    site = _site(detect="message", m_strings=["<title>404 Not Found</title>"])
    assert a.check_site(site, "testuser")["found"] is True


def test_detect_message_missing(monkeypatch):
    _patch_urlopen(monkeypatch, 200, b"<head><title>404 Not Found</title></head>")
    a = _adapter()
    site = _site(detect="message", m_strings=["<title>404 Not Found</title>"])
    assert a.check_site(site, "nouser")["found"] is False


def test_detect_message_transport_error_gives_none(monkeypatch):
    def _boom(req, timeout=15):
        raise ConnectionError("down")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    a = _adapter()
    site = _site(detect="message", m_strings=["nope"])
    assert a.check_site(site, "u")["found"] is None


def test_detect_status_code_found(monkeypatch):
    _patch_urlopen(monkeypatch, 200, b"ok")
    a = _adapter()
    assert a.check_site(_site(detect="status_code"), "u")["found"] is True


def test_detect_status_code_missing(monkeypatch):
    _patch_urlopen(monkeypatch, 404, b"not found")
    a = _adapter()
    assert a.check_site(_site(detect="status_code"), "u")["found"] is False


def test_detect_response_url_found(monkeypatch):
    a = _adapter()
    site = _site(detect="response_url", error_url="https://example.com/error")

    class _FakeOpener:
        def open(self, req, timeout=15):
            return _FakeResp(200, b"profile", "https://example.com/john")

    class _FakeRecorder:
        final_url = "https://example.com/john"

    monkeypatch.setattr(
        WhatsMyNameLookup, "_record_redirects",
        staticmethod(lambda: (_FakeOpener(), _FakeRecorder())),
    )
    assert a.check_site(site, "john")["found"] is True


def test_detect_response_url_missing(monkeypatch):
    a = _adapter()
    site = _site(detect="response_url", error_url="https://example.com/error")

    class _FakeOpener:
        def open(self, req, timeout=15):
            return _FakeResp(200, b"oops", "https://example.com/error")

    class _FakeRecorder:
        final_url = "https://example.com/error"

    monkeypatch.setattr(
        WhatsMyNameLookup, "_record_redirects",
        staticmethod(lambda: (_FakeOpener(), _FakeRecorder())),
    )
    assert a.check_site(site, "ghost")["found"] is False


def test_regex_check_mismatch_skips(monkeypatch):
    _patch_urlopen(monkeypatch, 200, b"anything")
    a = _adapter()
    site = _site(detect="status_code", regex_check="^[a-z0-9]{4,12}$")
    result = a.check_site(site, "AB!")  # violates the site's username rules
    assert result["found"] is None
    assert "regex_mismatch" in result["note"]


def test_regex_check_match_proceeds(monkeypatch):
    _patch_urlopen(monkeypatch, 200, b"ok")
    a = _adapter()
    site = _site(detect="status_code", regex_check="^[a-z0-9]{4,12}$")
    assert a.check_site(site, "john42")["found"] is True
