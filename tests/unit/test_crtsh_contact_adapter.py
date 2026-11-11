"""Tests for crt.sh contact-extraction adapter (offline fixtures)."""

import json

from adapters.crtsh_contact_adapter import CrtshContactLookup

FIXTURE_CRTSH = json.dumps([
    {"id": 1, "issuer_ca_id": 1,
     "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
     "common_name": "example.com",
     "name_value": "example.com\nwww.example.com",
     "not_before": "2026-01-01T00:00:00", "not_after": "2026-04-01T00:00:00",
     "serial_number": "abc"},
    {"id": 2, "issuer_ca_id": 2,
     "issuer_name": "C=US, O=Acme Internal PKI, CN=acme-ca",
     "common_name": "shop.acme.com",
     "name_value": "shop.acme.com\nadmin@acme.com",
     "not_before": "2026-01-01T00:00:00", "not_after": "2027-01-01T00:00:00",
     "serial_number": "def"},
])


def _adapter(body, status=200):
    return CrtshContactLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_wildcard_default():
    a = _adapter("")
    url = a._build_url("Example.COM")
    assert "q=%25.example.com" in url and "output=json" in url


def test_extract_filters_ca_noise_and_finds_contacts():
    fields = _adapter(FIXTURE_CRTSH).query("example.com")["fields"]
    org_names = [o["name"] for o in fields["org_names"]]
    assert "Acme Internal PKI" in org_names
    assert not any("encrypt" in o.lower() for o in org_names)
    emails = [e["email"] for e in fields["contact_emails"]]
    assert "admin@acme.com" in emails


def test_5xx_degrades_gracefully():
    result = _adapter("<html>502</html>", status=502).query("example.com")
    assert result["fields"]["service_unavailable"] is True


def test_parse_entry_offline():
    parsed = CrtshContactLookup.parse_crtsh_result(FIXTURE_CRTSH)
    assert parsed["org_count"] == 1
    assert parsed["contact_email_count"] == 1
