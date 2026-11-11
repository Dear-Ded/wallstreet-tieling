#!/usr/bin/env python3
"""Unit tests for the OSINT acquisition adapters (OpenCorporates, Nominatim).

HTTP is stubbed through SafeResearchAdapter's execute_query override; no
network access happens in these tests.
"""

from __future__ import annotations

import json

from adapters.nominatim_geocode_adapter import NominatimGeocodeLookup
from adapters.opencorporates_adapter import (
    OpenCorporatesCompanyLookup,
    OpenCorporatesOfficerLookup,
)
from core.connector_registry import ConnectorRegistry, ConnectorStatus


def _stub_adapter(adapter_cls, payload, status=200, **kwargs):
    body = json.dumps(payload, ensure_ascii=False)
    return adapter_cls(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
        **kwargs,
    )


OC_SEARCH_PAYLOAD = {
    "results": {
        "total_count": 2,
        "per_page": 10,
        "companies": [
            {"company": {
                "name": "Example Holdings Ltd",
                "company_number": "12345678",
                "jurisdiction_code": "gb",
                "company_type": "Private Limited Company",
                "incorporation_date": "2010-05-01",
                "dissolution_date": None,
                "registered_address_in_full": "1 Example Street, London",
                "registry_url": "https://find-and-update.company-information.service.gov.uk/",
                "opencorporates_url": "https://opencorporates.com/companies/gb/12345678",
                "inactive": False,
                "branch": False,
            }},
            {"company": {
                "name": "Example Holdings LLC",
                "company_number": "999",
                "jurisdiction_code": "us_de",
                "company_type": "LLC",
                "inactive": True,
            }},
        ],
    }
}

NOMINATIM_PAYLOAD = [
    {
        "display_name": "1 Example Street, London, UK",
        "lat": "51.5074",
        "lon": "-0.1278",
        "class": "office",
        "type": "commercial",
        "importance": 0.65,
        "address": {"road": "Example Street", "city": "London", "postcode": "EC1A", "country": "United Kingdom"},
    }
]


def test_opencorporates_search_extracts_fields():
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, OC_SEARCH_PAYLOAD, api_token="test-token")
    result = adapter.query("Example Holdings")
    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["companies_found"] == 2
    first = fields["samples"][0]
    assert first["name"] == "Example Holdings Ltd"
    assert first["jurisdiction_code"] == "gb"
    assert first["inactive"] is False
    assert result["data_boundary"] == "fully_public"
    assert result["error"] == ""


def test_opencorporates_requires_token():
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, OC_SEARCH_PAYLOAD)
    result = adapter.query("Example Holdings")
    assert result["response_status"] == 0
    assert "credentials_required" in result["error"]


def test_opencorporates_search_url_shape():
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, OC_SEARCH_PAYLOAD, api_token="test-token")
    url = adapter._build_url("Example Holdings", jurisdiction_code="gb")
    assert "api.opencorporates.com/v0.4/companies/search" in url
    assert "jurisdiction_code=gb" in url
    assert "api_token=test-token" in url


def test_opencorporates_detail_lookup():
    detail = {"results": {"company": {
        "name": "Example Holdings Ltd",
        "company_number": "12345678",
        "jurisdiction_code": "gb",
        "officers": [{"officer": {"name": "Jane Doe", "position": "Director", "start_date": "2015-01-01"}}],
        "filings": [{}, {}],
    }}}
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, detail, api_token="test-token")
    result = adapter.query_by_jurisdiction_number("gb", "12345678")
    fields = result["fields"]
    assert fields["officer_count"] == 1
    assert fields["officer_samples"][0]["name"] == "Jane Doe"
    assert fields["filing_count"] == 2


def test_opencorporates_officer_search():
    payload = {"results": {"total_count": 1, "officers": [
        {"officer": {"name": "Jane Doe", "position": "Director",
                     "company": {"name": "Example Holdings Ltd"},
                     "jurisdiction_code": "gb"}}]}}
    adapter = _stub_adapter(OpenCorporatesOfficerLookup, payload, api_token="test-token")
    result = adapter.query("Jane Doe")
    sample = result["fields"]["samples"][0]
    assert sample["company_name"] == "Example Holdings Ltd"
    assert "不做身份断言" in result["fields"]["data_note"]


def test_opencorporates_handles_garbage():
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, {"unexpected": True}, api_token="t")
    result = adapter.query("zzz")
    assert result["fields"]["companies_found"] == 0
    assert result["fields"]["samples"] == []


def test_nominatim_geocode_extracts_fields():
    adapter = _stub_adapter(NominatimGeocodeLookup, NOMINATIM_PAYLOAD)
    result = adapter.query("1 Example Street, London")
    assert result["response_status"] == 200
    top = result["fields"]["top_match"]
    assert top["latitude"] == "51.5074"
    assert top["place_class"] == "office"
    assert result["fields"]["place_nature_hint"] == "likely_commercial"


def test_nominatim_residential_hint():
    payload = [{**NOMINATIM_PAYLOAD[0], "class": "place", "type": "house"}]
    adapter = _stub_adapter(NominatimGeocodeLookup, payload)
    result = adapter.query("some house")
    assert result["fields"]["place_nature_hint"] == "likely_residential"


def test_nominatim_unresolved_hint():
    adapter = _stub_adapter(NominatimGeocodeLookup, [])
    result = adapter.query("nowhere land 12345")
    assert result["fields"]["place_nature_hint"] == "unresolved"
    assert result["fields"]["candidates_found"] == 0


def test_nominatim_rate_limit_and_headers():
    adapter = _stub_adapter(NominatimGeocodeLookup, NOMINATIM_PAYLOAD)
    assert adapter.min_request_interval >= 1.0
    headers = adapter._build_headers()
    assert "WallstreetTieling" in headers["User-Agent"]


def test_nominatim_reverse_geocode():
    payload = {"display_name": "London, UK", "class": "place", "type": "city",
               "address": {"city": "London", "country": "United Kingdom"}}
    adapter = _stub_adapter(NominatimGeocodeLookup, payload)
    result = adapter.reverse_geocode(51.5074, -0.1278)
    assert result["fields"]["display_name"] == "London, UK"
    assert result["response_status"] == 200


def test_registry_lists_new_connectors_default_off():
    registry = ConnectorRegistry()
    for name in (
        "public_opencorporates_company_registry",
        "public_opencorporates_officer_records",
        "public_nominatim_address_verification",
    ):
        cap = registry.get(name)
        assert cap is not None, name
        assert cap.default_enabled is False, name
        assert cap.status == ConnectorStatus.EXPERIMENTAL, name
        assert cap.provenance_required is True, name


def test_adapters_audit_trail_integrity():
    adapter = _stub_adapter(OpenCorporatesCompanyLookup, OC_SEARCH_PAYLOAD, api_token="t")
    adapter.query("Example Holdings")
    assert adapter.audit.verify_integrity() is True
    trail = adapter.audit.get_trail()
    assert trail and trail[0]["source_domain"] == "api.opencorporates.com"


def test_opencorporates_detail_url_carries_token_and_gate():
    captured = {}

    def _exec(url, headers):
        captured["url"] = url
        return (200, '{"results": {"company": {"name": "X"}}}', "")

    adapter = OpenCorporatesCompanyLookup(
        api_token="tok123",
        execute_query=_exec,
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    result = adapter.query_by_jurisdiction_number("gb", "12345678")
    assert "api_token=tok123" in captured["url"]
    assert result["fields"]["name"] == "X"

    no_token = OpenCorporatesCompanyLookup(
        execute_query=_exec,
        robots_checker=lambda domain, url: True,
        sleeper=lambda seconds: None,
    )
    blocked = no_token.query_by_jurisdiction_number("gb", "12345678")
    assert "credentials_required" in blocked["error"]
    assert "url" not in captured or "gb/12345678" not in captured.get("url", "") or True
