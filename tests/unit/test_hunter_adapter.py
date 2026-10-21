"""Hunter.io 域名邮箱检索适配器单元测试。"""

from adapters.hunter_adapter import HunterDomainLookup

SAMPLE_OK = {
    "data": {
        "domain": "example.com",
        "disposable": False,
        "webmail": False,
        "accept_all": True,
        "pattern": "{first}.{last}",
        "organization": "Example Inc",
        "description": "Demo company",
        "country": "US",
        "city": None,
        "emails": [
            {
                "value": "jane.doe@example.com",
                "type": "personal",
                "confidence": 92,
                "sources": [{"domain": "example.com", "uri": "https://example.com/team"}],
                "first_name": "Jane",
                "last_name": "Doe",
                "position": "CEO",
                "seniority": "executive",
                "department": "executive",
                "linkedin": "https://linkedin.com/in/janedoe",
                "phone_number": "",
            },
            {
                "value": "contact@example.com",
                "type": "generic",
                "confidence": 70,
                "sources": [],
                "first_name": "",
                "last_name": "",
                "position": "",
                "seniority": "",
                "department": "",
                "linkedin": "",
                "phone_number": "",
            },
        ],
    },
    "meta": {"results": 2, "limit": 10, "offset": 0,
             "params": {"domain": "example.com"}},
}

SAMPLE_ERROR = {
    "errors": [
        {"id": "authentication_failed", "code": 401,
         "details": "No user found for the API key supplied"}
    ]
}


def _adapter(key="dummy-key"):
    return HunterDomainLookup(api_key=key, sleeper=lambda s: None)


def test_extract_public_fields_ok():
    a = _adapter()
    fields = a._extract_public_fields(SAMPLE_OK)
    assert fields["domain"] == "example.com"
    assert fields["organization"] == "Example Inc"
    assert fields["email_count"] == 2
    first = fields["emails"][0]
    assert first["value"] == "jane.doe@example.com"
    assert first["first_name"] == "Jane"
    assert first["position"] == "CEO"
    assert first["source_count"] == 1
    assert "note" in fields["data_note"] or "Hunter" in fields["data_note"]


def test_extract_public_fields_error():
    a = _adapter()
    fields = a._extract_public_fields(SAMPLE_ERROR)
    assert fields["lookup_failed"] is True
    assert fields["error_id"] == "authentication_failed"


def test_extract_garbage_input():
    a = _adapter()
    assert a._extract_public_fields("not-json") == {"parse_error": True}
    assert a._extract_public_fields(None)["lookup_failed"] is True


def test_build_url_contains_params():
    a = _adapter(key="KEY123")
    url = a._build_url("Example.COM", limit=5)
    assert "domain=example.com" in url
    assert "limit=5" in url
    assert "api_key=KEY123" in url
    assert url.startswith("https://api.hunter.io/v2/domain-search")


def test_requires_credentials_no_key():
    a = HunterDomainLookup(sleeper=lambda s: None)
    result = a.query("example.com")
    assert result["error"] == "Query blocked: credentials_required"
    assert result["fields"] == {}


def test_query_subject_hashed_not_plaintext():
    a = _adapter()
    result = a.query("example.com")
    assert result["query_subject_hash"]
    assert "example.com" not in str(result)


def test_source_domain_and_boundary():
    assert HunterDomainLookup.source_domain == "api.hunter.io"
    assert HunterDomainLookup.data_boundary == "fully_public"
    assert HunterDomainLookup.requires_credentials is True
    assert HunterDomainLookup.min_request_interval == 2.0


def test_audit_trail_integrity():
    a = _adapter()
    a.query("example.com")
    assert a.audit.verify_integrity()
    trail = a.audit.get_trail()
    assert trail[0]["source_domain"] == "api.hunter.io"


def test_query_domain_helper():
    b = HunterDomainLookup(api_key="k", sleeper=lambda s: None,
                           execute_query=lambda url, h: (200, SAMPLE_OK, ""))
    result = b.query_domain("Example.com", limit=5)
    assert result["fields"]["domain"] == "example.com"
