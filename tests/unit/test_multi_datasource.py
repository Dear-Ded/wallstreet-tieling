#!/usr/bin/env python3
"""tests for adapters.multi_datasource."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import multi_datasource as md
from adapters.multi_datasource import (
    ConfigError,
    DataSourceConfig,
    DataSourceManager,
    HealthReport,
    QueryError,
    QueryRequest,
    QueryResult,
    QueryStatus,
    RateLimiter,
    LocalIndexDataSource,
    RestApiDataSource,
    SearchEngine,
    StandardizedRecord,
    standardize_records,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        content_type: str = "application/json",
        content_length: int | None = None,
        payload=None,
        json_exc: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = {"content-type": content_type}
        self.content_length = content_length
        self._payload = payload
        self._json_exc = json_exc

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.response

    async def close(self):
        self.closed = True


class FakeSequenceSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if not self.responses:
            raise RuntimeError("no fake response left")
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


class FakeHealthSession:
    def __init__(self, response: FakeResponse, get_response: FakeResponse | None = None) -> None:
        self.response = response
        self.get_response = get_response or response
        self.calls: list[dict[str, object]] = []

    def head(self, url, headers=None):
        self.calls.append({"method": "HEAD", "url": url, "headers": headers})
        return self.response

    def get(self, url, headers=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return self.get_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestDataSourceConfig:
    def test_base_url_normalization(self):
        cfg = DataSourceConfig(
            name="demo",
            type="rest_api",
            base_url="https://example.com/api/",
        )
        assert cfg.base_url == "https://example.com/api"

    @pytest.mark.parametrize(
        "base_url",
        [
            "ftp://example.com",
            "http://127.0.0.1",
            "https://localhost",
            "https://user:pass@example.com",
            "https://169.254.169.254/latest/meta-data",
        ],
    )
    def test_base_url_rejects_risky_targets(self, base_url):
        with pytest.raises(ValueError):
            DataSourceConfig(
                name="demo",
                type="rest_api",
                base_url=base_url,
            )

    def test_ping_endpoint_is_validated(self):
        cfg = DataSourceConfig(
            name="demo",
            type="rest_api",
            base_url="https://example.com",
            ping_endpoint="https://example.com/health",
        )
        assert cfg.ping_endpoint == "https://example.com/health"

        with pytest.raises(ValueError):
            DataSourceConfig(
                name="demo",
                type="rest_api",
                base_url="https://example.com",
                ping_endpoint="https://localhost/health",
            )


class TestQueryRequest:
    def test_rejects_blank_query(self):
        with pytest.raises(ValueError):
            QueryRequest(query="   ")

    @pytest.mark.parametrize(
        "query",
        [
            "/health",
            "../secret",
            "//evil",
            "https://evil.example",
            "foo?bar=baz",
            r"foo\bar",
            "foo\nbar",
        ],
    )
    def test_rejects_risky_query_formats(self, query):
        with pytest.raises(ValueError):
            QueryRequest(query=query)

    def test_rejects_sensitive_headers_and_control_chars(self):
        with pytest.raises(ValueError):
            QueryRequest(query="reports/list", headers={"Host": "evil"})

        with pytest.raises(ValueError):
            QueryRequest(query="reports/list", headers={"X-Test": "ok\r\nInjected: 1"})

    def test_cache_key_is_stable(self):
        left = QueryRequest(
            query="reports/list",
            params={"page": 1},
            filters=[{"field": "status", "op": "eq", "value": "ok"}],
        )
        right = QueryRequest(
            query="reports/list",
            params={"page": 1},
            filters=[{"field": "status", "op": "eq", "value": "ok"}],
        )
        assert left.cache_key() == right.cache_key()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_waits_when_bucket_is_empty(self, monkeypatch):
        limiter = RateLimiter(rate=1.0, burst=1)
        waits: list[float] = []

        async def fake_sleep(delay):
            waits.append(delay)

        monkeypatch.setattr(md.asyncio, "sleep", fake_sleep)

        await limiter.acquire()
        await limiter.acquire()

        assert len(waits) == 1
        assert waits[0] > 0


class TestRestApiDataSource:
    @pytest.fixture
    def config(self):
        return DataSourceConfig(
            name="demo",
            type="rest_api",
            base_url="https://api.example.com/v1",
            rate_limit={"enabled": False},
        )

    @pytest.mark.asyncio
    async def test_query_builds_safe_request(self, config, monkeypatch):
        source = RestApiDataSource(config)
        session = FakeSession(FakeResponse(payload={"data": {"ok": True}}))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        request = QueryRequest(
            query="reports/list",
            params={"page": 2},
            headers={"X-Trace": "abc"},
        )

        data = await source._do_query(request)

        assert data == {"data": {"ok": True}}
        assert session.calls[0]["url"] == "https://api.example.com/v1/reports/list"
        assert session.calls[0]["params"] == {"page": 2}
        assert session.calls[0]["headers"] == {"X-Trace": "abc"}

    @pytest.mark.asyncio
    async def test_query_rejects_large_response(self, config, monkeypatch):
        source = RestApiDataSource(config)
        session = FakeSession(
            FakeResponse(content_length=10 * 1024 * 1024 + 1, payload={"data": []})
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        request = QueryRequest(query="reports/list")

        with pytest.raises(QueryError):
            await source._do_query(request)

    @pytest.mark.asyncio
    async def test_query_wraps_json_parse_errors(self, config, monkeypatch):
        source = RestApiDataSource(config)
        session = FakeSession(FakeResponse(json_exc=ValueError("bad json")))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        request = QueryRequest(query="reports/list")

        with pytest.raises(QueryError, match="响应解析失败"):
            await source._do_query(request)

    def test_rate_limiter_is_initialized_when_enabled(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="demo",
                type="rest_api",
                base_url="https://api.example.com",
            )
        )
        assert source._rate_limiter is not None

    @pytest.mark.asyncio
    async def test_success_result_includes_standardized_records(self, config, monkeypatch):
        source = RestApiDataSource(config)
        session = FakeSession(
            FakeResponse(
                payload={
                    "data": [
                        {
                            "company_name": "Acme Ltd",
                            "title": "Risk notice",
                            "url": "https://example.com/risk",
                            "confidence": 0.8,
                        }
                    ]
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="companies/search"))

        assert result.is_success
        records = result.metadata["standardized_records"]
        assert records[0]["source_name"] == "demo"
        assert records[0]["entity"] == "Acme Ltd"
        assert records[0]["title"] == "Risk notice"

    @pytest.mark.asyncio
    async def test_gleif_provider_maps_company_query_to_official_api(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="gleif",
                type="rest_api",
                base_url="https://api.gleif.org/api/v1",
                headers={"Accept": "application/vnd.api+json"},
                custom={"provider_type": "gleif_lei"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "data": [
                        {
                            "id": "5493001KJTIIGC8Y1R12",
                            "attributes": {
                                "entity": {
                                    "legalName": {"name": "Demo Global Ltd"},
                                    "registeredAt": {"id": "RA000001"},
                                    "jurisdiction": "US-CA",
                                    "legalAddress": {
                                        "addressLines": ["One Infinite Loop"],
                                        "city": "Cupertino",
                                        "region": "California",
                                        "postalCode": "95014",
                                        "country": "US",
                                    },
                                    "headquartersAddress": {
                                        "addressLines": ["One Apple Park Way"],
                                        "city": "Cupertino",
                                        "region": "California",
                                        "postalCode": "95014",
                                        "country": "US",
                                    },
                                    "directParent": {
                                        "lei": "549300PARENTDIRECT",
                                        "legalName": {"name": "Demo Direct Parent Ltd"},
                                    },
                                    "ultimateParent": {
                                        "lei": "549300PARENTULTIM",
                                        "legalName": {"name": "Demo Ultimate Parent Ltd"},
                                    },
                                },
                                "registration": {"status": "ISSUED"},
                            },
                        }
                    ]
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Demo Global Ltd"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://api.gleif.org/api/v1/lei-records"
        assert session.calls[0]["params"]["filter[entity.legalName]"] == "Demo Global Ltd"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "Demo Global Ltd"
        assert "GLEIF LEI record" in records[0]["title"]
        assert records[0]["lei"] == "5493001KJTIIGC8Y1R12"
        assert records[0]["registration_authority"] == "RA000001"
        assert records[0]["jurisdiction"] == "US-CA"
        assert records[0]["registered_address"] == "One Infinite Loop, Cupertino, California, 95014, US"
        assert records[0]["headquarters_address"] == "One Apple Park Way, Cupertino, California, 95014, US"
        assert {
            "kind": "address",
            "name": "One Infinite Loop, Cupertino, California, 95014, US",
            "relation": "registered_address",
            "confidence": 0.82,
            "source": "GLEIF",
        } in records[0]["entities"]
        assert {
            "kind": "company",
            "name": "Demo Direct Parent Ltd",
            "relation": "direct_parent",
            "confidence": 0.76,
            "source": "GLEIF",
            "lei": "549300PARENTDIRECT",
        } in records[0]["entities"]
        assert {
            "kind": "company",
            "name": "Demo Ultimate Parent Ltd",
            "relation": "ultimate_parent",
            "confidence": 0.76,
            "source": "GLEIF",
            "lei": "549300PARENTULTIM",
        } in records[0]["entities"]
        assert any(
            item["type"] == "official_public_api_relation"
            and item["relation"] == "ultimate_parent"
            and item["name"] == "Demo Ultimate Parent Ltd"
            for item in records[0]["evidence"]
        )

    @pytest.mark.asyncio
    async def test_gleif_relationship_traversal_maps_parent_edges(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="gleif_relationship",
                type="rest_api",
                base_url="https://api.gleif.org/api/v1",
                headers={"Accept": "application/vnd.api+json"},
                custom={"provider_type": "gleif_relationship_traversal"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "data": [
                        {
                            "id": "549300SUBJECTLEI0",
                            "links": {
                                "self": "https://api.gleif.org/api/v1/lei-records/549300SUBJECTLEI0",
                                "relationship-record": "https://api.gleif.org/api/v1/lei-records/549300SUBJECTLEI0/relationships",
                            },
                            "attributes": {
                                "entity": {
                                    "legalName": {"name": "Demo Global Ltd"},
                                    "directParent": {
                                        "lei": "549300PARENTDIRECT",
                                        "legalName": {"name": "Demo Direct Parent Ltd"},
                                    },
                                    "ultimateParent": {
                                        "lei": "549300PARENTULTIM",
                                        "legalName": {"name": "Demo Ultimate Parent Ltd"},
                                    },
                                }
                            },
                        }
                    ]
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Demo Global Ltd"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://api.gleif.org/api/v1/lei-records"
        assert session.calls[0]["params"]["filter[entity.legalName]"] == "Demo Global Ltd"
        records = result.metadata["standardized_records"]
        assert {record["relationship_type"] for record in records} == {"direct_parent", "ultimate_parent"}
        direct = next(record for record in records if record["relationship_type"] == "direct_parent")
        assert direct["record_type"] == "gleif_relationship_edge"
        assert direct["subject_lei"] == "549300SUBJECTLEI0"
        assert direct["subject_name"] == "Demo Global Ltd"
        assert direct["related_lei"] == "549300PARENTDIRECT"
        assert direct["related_name"] == "Demo Direct Parent Ltd"
        assert direct["relationship_status"] == "reported"
        assert direct["entity_match"]["level"] == "exact"
        assert direct["entity_match"]["method"] == "query_subject_name_plus_source_reported_lei"
        assert direct["entity_match"]["identifiers"]["subject_lei"] == "549300SUBJECTLEI0"
        assert direct["entity_match"]["identifiers"]["related_lei"] == "549300PARENTDIRECT"
        assert direct["url"] == "https://api.gleif.org/api/v1/lei-records/549300SUBJECTLEI0/relationships"
        assert {
            "kind": "company",
            "name": "Demo Direct Parent Ltd",
            "relation": "direct_parent",
            "confidence": 0.76,
            "source": "GLEIF",
            "lei": "549300PARENTDIRECT",
        } in direct["entities"]
        assert any(
            item["type"] == "official_public_api_relation"
            and item["relationship_type"] == "direct_parent"
            and item["source_url"] == "https://api.gleif.org/api/v1/lei-records/549300SUBJECTLEI0/relationships"
            and item["entity_match_level"] == "exact"
            for item in direct["evidence"]
        )

    @pytest.mark.asyncio
    async def test_sec_provider_supports_cik_submission_lookup(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="sec",
                type="rest_api",
                base_url="https://data.sec.gov",
                headers={"Accept": "application/json", "User-Agent": "test@example.invalid"},
                custom={"provider_type": "sec_edgar"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "cik": "320193",
                    "name": "Apple Inc.",
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "filingDate": ["2025-10-31"],
                            "accessionNumber": ["0000320193-25-000001"],
                        }
                    },
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Apple Inc", params={"cik": "320193"}))

        assert result.is_success
        assert session.calls[0]["url"] == "https://data.sec.gov/submissions/CIK0000320193.json"
        assert "cik" not in session.calls[0]["params"]
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "Apple Inc."
        assert "10-K" in records[0]["summary"]

    @pytest.mark.asyncio
    async def test_sec_provider_maps_structured_key_people_from_submission_payload(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="sec",
                type="rest_api",
                base_url="https://data.sec.gov",
                headers={"Accept": "application/json", "User-Agent": "test@example.invalid"},
                custom={"provider_type": "sec_edgar"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "cik": "320193",
                    "name": "Apple Inc.",
                    "officers": [
                        {"name": "Tim Cook", "title": "Chief Executive Officer"},
                        {"fullName": "Luca Maestri", "officerTitle": "Chief Financial Officer"},
                    ],
                    "directors": [{"personName": "Arthur Levinson", "role": "Chairman of the Board"}],
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "filingDate": ["2025-10-31"],
                            "accessionNumber": ["0000320193-25-000001"],
                        }
                    },
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Apple Inc. 工商信息 注册资本 法定代表人", params={"cik": "320193"}))

        assert result.is_success
        record = result.metadata["standardized_records"][0]
        related_people = {
            (item["name"], item["relation"], item.get("position"))
            for item in record["entities"]
            if item["kind"] == "person"
        }
        assert ("Tim Cook", "chief_executive_officer", "Chief Executive Officer") in related_people
        assert ("Luca Maestri", "chief_financial_officer", "Chief Financial Officer") in related_people
        assert ("Arthur Levinson", "chairperson", "Chairman of the Board") in related_people
        assert record["source_hint"] == "sec_edgar_public_api"
        assert record["entity_match"]["level"] == "exact"
        assert "key_people=chief_executive_officer:Tim Cook" in record["summary"]
        assert record["evidence"][0]["key_people_count"] == 3

    @pytest.mark.asyncio
    async def test_sec_provider_filters_ticker_catalog_by_company_query(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="sec",
                type="rest_api",
                base_url="https://data.sec.gov",
                headers={"Accept": "application/json", "User-Agent": "test@example.invalid"},
                custom={"provider_type": "sec_edgar"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Apple"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.sec.gov/files/company_tickers.json"
        records = result.metadata["standardized_records"]
        assert [record["entity"] for record in records] == ["Apple Inc."]
        assert "AAPL" in records[0]["summary"]

    @pytest.mark.asyncio
    async def test_sec_provider_supports_companyfacts_financial_quality_lookup(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="sec",
                type="rest_api",
                base_url="https://data.sec.gov",
                headers={"Accept": "application/json", "User-Agent": "test@example.invalid"},
                custom={"provider_type": "sec_edgar"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "cik": "320193",
                    "entityName": "Apple Inc.",
                    "facts": {
                        "us-gaap": {
                            "Revenues": {
                                "units": {"USD": [{"end": "2025-09-27", "filed": "2025-10-31", "val": 391035000000}]}
                            },
                            "NetIncomeLoss": {
                                "units": {"USD": [{"end": "2025-09-27", "filed": "2025-10-31", "val": 93736000000}]}
                            },
                            "NetCashProvidedByUsedInOperatingActivities": {
                                "units": {"USD": [{"end": "2025-09-27", "filed": "2025-10-31", "val": 118000000000}]}
                            },
                            "Assets": {
                                "units": {"USD": [{"end": "2025-09-27", "filed": "2025-10-31", "val": 352000000000}]}
                            },
                            "Liabilities": {
                                "units": {"USD": [{"end": "2025-09-27", "filed": "2025-10-31", "val": 260000000000}]}
                            },
                        }
                    },
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(
            QueryRequest(query="Apple Inc.", params={"cik": "320193", "sec_endpoint": "companyfacts"})
        )

        assert result.is_success
        assert session.calls[0]["url"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "Apple Inc."
        assert "SEC EDGAR company facts" in records[0]["title"]
        assert "revenue=3.91035e+11" in records[0]["summary"]
        assert records[0]["evidence"][0]["provider"] == "SEC EDGAR companyfacts"
        assert records[0]["raw"]["ratios"]["cash_conversion"] > 1

    @pytest.mark.asyncio
    async def test_sec_companyfacts_chooses_latest_fact_across_revenue_concepts(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="sec",
                type="rest_api",
                base_url="https://data.sec.gov",
                headers={"Accept": "application/json", "User-Agent": "test@example.invalid"},
                custom={"provider_type": "sec_edgar"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "cik": "320193",
                    "entityName": "Apple Inc.",
                    "facts": {
                        "us-gaap": {
                            "Revenues": {
                                "units": {"USD": [{"end": "2018-09-29", "filed": "2018-11-05", "val": 265595000000}]}
                            },
                            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                                "units": {"USD": [{"end": "2026-03-28", "filed": "2026-05-01", "val": 290000000000}]}
                            },
                            "NetIncomeLoss": {
                                "units": {"USD": [{"end": "2026-03-28", "filed": "2026-05-01", "val": 71000000000}]}
                            },
                        }
                    },
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(
            QueryRequest(query="Apple Inc.", params={"cik": "320193", "sec_endpoint": "companyfacts"})
        )

        record = result.metadata["standardized_records"][0]
        assert record["raw"]["metrics"]["revenue"]["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
        assert record["evidence"][0]["revenue"] == 290000000000

    @pytest.mark.asyncio
    async def test_opensanctions_catalog_provider_maps_public_dataset_metadata(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="opensanctions",
                type="rest_api",
                base_url="https://data.opensanctions.org",
                headers={"Accept": "application/json"},
                custom={"provider_type": "opensanctions_dataset_catalog"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "datasets": {
                        "default": {
                            "name": "default",
                            "title": "Default screening dataset",
                            "category": "sanctions",
                            "summary": "Consolidated public screening data.",
                            "license": "CC-BY",
                            "license_url": "https://www.opensanctions.org/licensing/",
                            "updated_at": "2026-06-30",
                        }
                    }
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Apple Inc."))

        assert result.is_success
        assert session.calls[0]["url"] == "https://data.opensanctions.org/datasets/latest/index.json"
        records = result.data["source_catalog_records"]
        assert records[0]["entity"] == "Default screening dataset"
        assert "OpenSanctions dataset coverage" in records[0]["title"]
        assert records[0]["record_type"] == "watchlist_dataset_catalog"
        assert records[0]["source_hint"] == "opensanctions_public_dataset_catalog"
        assert "license=CC-BY" in records[0]["summary"]
        assert records[0]["evidence"][0]["provider"] == "OpenSanctions"
        assert records[0]["evidence"][0]["license"] == "CC-BY"
        assert records[0]["evidence"][0]["license_url"] == "https://www.opensanctions.org/licensing/"
        assert records[0]["evidence"][0]["updated_at"] == "2026-06-30"
        assert records[0]["evidence"][0]["license_review"]["status"] == "metadata_exposed"
        assert "catalog rows are coverage evidence only" in records[0]["evidence"][0]["license_review"]["subject_screening_policy"]
        assert result.metadata["standardized_records"][0]["entity"] == "Default screening dataset"
        assert result.metadata["standardized_records"][0]["evidence"][0]["provider"] == "OpenSanctions"

    @pytest.mark.asyncio
    async def test_wikidata_provider_builds_sparql_and_maps_entity_graph_records(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="wikidata",
                type="rest_api",
                base_url="https://www.wikidata.org/w",
                headers={"Accept": "application/json"},
                custom={"provider_type": "wikidata_entity_search"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "search": [
                        {
                            "id": "Q312",
                            "label": "Apple Inc.",
                            "description": "American technology company",
                            "concepturi": "http://www.wikidata.org/entity/Q312",
                            "aliases": ["Apple Computer"],
                        },
                        {
                            "id": "Q487819",
                            "label": "Apple Inc. v. Samsung Electronics Co.",
                            "description": "United States Supreme Court case",
                            "concepturi": "http://www.wikidata.org/entity/Q487819",
                        }
                    ]
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="Apple Inc."))

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.wikidata.org/w/api.php"
        assert session.calls[0]["params"]["action"] == "wbsearchentities"
        assert session.calls[0]["params"]["search"] == "Apple Inc."
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "Apple Inc."
        assert "Wikidata entity graph match" in records[0]["title"]
        assert "wikidata_id=Q312" in records[0]["summary"]
        assert records[0]["entity_match"]["level"] == "exact"
        assert records[1]["entity_match"]["level"] == "review"
        assert records[1]["entity_match"]["identifiers"]["wikidata_id"] == "Q487819"

    @pytest.mark.asyncio
    async def test_wikidata_provider_maps_entitydata_key_people(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="wikidata_public_entity_graph",
                type="rest_api",
                base_url="https://www.wikidata.org/w",
                headers={"Accept": "application/json"},
                custom={"provider_type": "wikidata_entity_search"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSession(
            FakeResponse(
                payload={
                    "entities": {
                        "Q312": {
                            "id": "Q312",
                            "labels": {"en": {"value": "Apple Inc."}},
                            "descriptions": {"en": {"value": "American technology company"}},
                            "_linked_entities": {
                                "Q19837": {"labels": {"en": {"value": "Tim Cook"}}},
                                "Q19848": {"labels": {"en": {"value": "Steve Jobs"}}},
                                "Q209225": {"labels": {"en": {"value": "Andrea Jung"}}},
                                "Q95": {"labels": {"en": {"value": "Google LLC"}}},
                            },
                            "claims": {
                                "P169": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "entity-type": "item",
                                                    "numeric-id": 19837,
                                                    "id": "Q19837",
                                                }
                                            }
                                        }
                                    }
                                ],
                                "P112": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "entity-type": "item",
                                                    "numeric-id": 19848,
                                                    "id": "Q19848",
                                                }
                                            }
                                        }
                                    }
                                ],
                                "P3320": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "entity-type": "item",
                                                    "numeric-id": 209225,
                                                    "id": "Q209225",
                                                }
                                            }
                                        }
                                    }
                                ],
                                "P1830": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "entity-type": "item",
                                                    "numeric-id": 95,
                                                    "id": "Q95",
                                                }
                                            }
                                        }
                                    }
                                ],
                            },
                        }
                    }
                }
            )
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(
            QueryRequest(
                query="Apple Inc.",
                params={"wikidata_endpoint": "entitydata", "wikidata_id": "Q312"},
            )
        )

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.wikidata.org/wiki/Special:EntityData/Q312.json"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "Apple Inc."
        related_people = {
            (item["name"], item["relation"])
            for item in records[0]["entities"]
            if item["kind"] == "person"
        }
        assert ("Tim Cook", "chief_executive_officer") in related_people
        assert ("Steve Jobs", "founder") in related_people
        assert ("Andrea Jung", "board_member") in related_people
        related_companies = {
            (item["name"], item["relation"])
            for item in records[0]["entities"]
            if item["kind"] == "company"
        }
        assert ("Google LLC", "owner_of") in related_companies
        assert "chief_executive_officer:Tim Cook" in records[0]["summary"]
        assert "board_member:Andrea Jung" in records[0]["summary"]
        assert "owner_of:Google LLC" in records[0]["summary"]

    @pytest.mark.asyncio
    async def test_wikidata_entitydata_enriches_related_qid_labels(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="wikidata_public_entity_graph",
                type="rest_api",
                base_url="https://www.wikidata.org/w",
                headers={"Accept": "application/json"},
                custom={"provider_type": "wikidata_entity_search"},
                rate_limit={"enabled": False},
            )
        )
        session = FakeSequenceSession(
            [
                FakeResponse(
                    payload={
                        "entities": {
                            "Q312": {
                                "id": "Q312",
                                "labels": {"en": {"value": "Apple Inc."}},
                                "descriptions": {"en": {"value": "American technology company"}},
                                "claims": {
                                    "P31": [
                                        {
                                            "mainsnak": {
                                                "datavalue": {
                                                    "value": {
                                                        "entity-type": "item",
                                                        "numeric-id": 1,
                                                        "id": "Q1",
                                                    }
                                                }
                                            }
                                        }
                                    ],
                                    "P169": [
                                        {
                                            "mainsnak": {
                                                "datavalue": {
                                                    "value": {
                                                        "entity-type": "item",
                                                        "numeric-id": 19837,
                                                        "id": "Q19837",
                                                    }
                                                }
                                            }
                                        }
                                    ],
                                    "P112": [
                                        {
                                            "mainsnak": {
                                                "datavalue": {
                                                    "value": {
                                                        "entity-type": "item",
                                                        "numeric-id": 19848,
                                                        "id": "Q19848",
                                                    }
                                                }
                                            }
                                        }
                                    ],
                                },
                            }
                        }
                    }
                ),
                FakeResponse(
                    payload={
                        "entities": {
                            "Q19837": {"labels": {"en": {"value": "Tim Cook"}}},
                            "Q19848": {"labels": {"en": {"value": "Steve Jobs"}}},
                        }
                    }
                ),
            ]
        )

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(
            QueryRequest(
                query="Apple Inc.",
                params={"wikidata_endpoint": "entitydata", "wikidata_id": "Q312"},
            )
        )

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.wikidata.org/wiki/Special:EntityData/Q312.json"
        assert session.calls[1]["url"] == "https://www.wikidata.org/w/api.php"
        assert session.calls[1]["params"]["action"] == "wbgetentities"
        assert session.calls[1]["params"]["ids"] == "Q19837|Q19848"
        records = result.metadata["standardized_records"]
        related_people = {
            (item["name"], item["relation"])
            for item in records[0]["entities"]
            if item["kind"] == "person"
        }
        assert ("Tim Cook", "chief_executive_officer") in related_people
        assert ("Steve Jobs", "founder") in related_people
        assert not any(item["name"] == "Q19837" for item in records[0]["entities"])

    @pytest.mark.asyncio
    async def test_ofac_provider_maps_consolidated_xml_to_risk_record(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="ofac",
                type="rest_api",
                base_url="https://www.treasury.gov/ofac/downloads/consolidated",
                headers={"Accept": "text/xml"},
                custom={"provider_type": "ofac_consolidated_xml"},
                rate_limit={"enabled": False},
            )
        )
        xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <sdnList xmlns="https://www.treasury.gov/ofac/downloads/sanctions/1.0">
          <sdnEntry>
            <uid>123</uid>
            <lastName>DEMO SANCTIONED ENTITY</lastName>
            <sdnType>Entity</sdnType>
            <programList><program>SDGT</program></programList>
          </sdnEntry>
        </sdnList>
        """

        class TextResponse(FakeResponse):
            async def text(self):
                return xml_payload

        session = FakeSession(TextResponse(content_type="text/xml", payload=None))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="DEMO SANCTIONED ENTITY"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "DEMO SANCTIONED ENTITY"
        assert "OFAC consolidated sanctions entry" in records[0]["title"]
        assert records[0]["entity_match"]["level"] == "exact"
        assert records[0]["risk_events"][0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_ofac_provider_does_not_emit_unrelated_entries(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="ofac",
                type="rest_api",
                base_url="https://www.treasury.gov/ofac/downloads/consolidated",
                headers={"Accept": "text/xml"},
                custom={"provider_type": "ofac_consolidated_xml"},
                rate_limit={"enabled": False},
            )
        )
        xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <sdnList xmlns="https://www.treasury.gov/ofac/downloads/sanctions/1.0">
          <sdnEntry>
            <uid>123</uid>
            <lastName>UNRELATED LISTED ENTITY</lastName>
            <sdnType>Entity</sdnType>
            <programList><program>SDGT</program></programList>
          </sdnEntry>
        </sdnList>
        """

        class TextResponse(FakeResponse):
            async def text(self):
                return xml_payload

        session = FakeSession(TextResponse(content_type="text/xml", payload=None))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="DEMO PROCUREMENT CO"))

        assert result.is_success
        assert result.metadata["standardized_records"] == []
        assert result.data["raw"]["parsed_count"] == 1

    @pytest.mark.asyncio
    async def test_un_sc_provider_maps_consolidated_xml_to_risk_record(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="un_sc_consolidated_sanctions_xml",
                type="rest_api",
                base_url="https://scsanctions.un.org",
                headers={"Accept": "application/xml"},
                custom={"provider_type": "un_sc_consolidated_sanctions_xml"},
                rate_limit={"enabled": False},
            )
        )
        xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <CONSOLIDATED_LIST dateGenerated="2026-06-20T23:00:05.607Z">
          <INDIVIDUALS>
            <INDIVIDUAL>
              <DATAID>6907993</DATAID>
              <FIRST_NAME>ERIC</FIRST_NAME>
              <SECOND_NAME>BADEGE</SECOND_NAME>
              <UN_LIST_TYPE>DRC</UN_LIST_TYPE>
              <REFERENCE_NUMBER>CDi.001</REFERENCE_NUMBER>
              <LISTED_ON>2012-12-31</LISTED_ON>
              <COMMENTS1>Official public list entry.</COMMENTS1>
              <INDIVIDUAL_ALIAS><ALIAS_NAME>DEMO WATCH PERSON</ALIAS_NAME></INDIVIDUAL_ALIAS>
            </INDIVIDUAL>
          </INDIVIDUALS>
          <ENTITIES />
        </CONSOLIDATED_LIST>
        """

        calls: list[dict[str, object]] = []

        async def fake_text_get(url, *, params, headers, max_size):
            calls.append({"url": url, "params": params, "headers": headers, "max_size": max_size})
            return xml_payload

        async def fake_get_session():
            return FakeSession(FakeResponse())

        monkeypatch.setattr(source, "_get_session", fake_get_session)
        monkeypatch.setattr(source, "_blocking_public_text_get", fake_text_get)

        result = await source.query(QueryRequest(query="DEMO WATCH PERSON"))

        assert result.is_success
        assert calls[0]["url"] == "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "ERIC BADEGE"
        assert "UN Security Council consolidated list match" in records[0]["title"]
        assert records[0]["entity_match"]["level"] in {"exact", "strong", "review"}
        assert records[0]["risk_events"][0]["severity"] == "high"
        assert records[0]["evidence"][0]["provider"] == "United Nations Security Council"

    @pytest.mark.asyncio
    async def test_idb_provider_maps_public_dataset_catalog_metadata(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="idb_sanctioned_firms_dataset_catalog",
                type="rest_api",
                base_url="https://data.iadb.org",
                headers={"Accept": "text/html"},
                custom={"provider_type": "idb_sanctioned_firms_dataset_catalog"},
                rate_limit={"enabled": False},
            )
        )
        html_payload = """
        <html><head>
          <meta name="citation_title" content="Dataset of Sanctioned firms and individuals" />
          <meta name="citation_publisher" content="IADB" />
          <meta name="citation_doi" content="doi:10.60966/7pfpgt0f" />
          <meta name="citation_online_date" content="2025-03-09" />
          <meta name="description" content="Explore the IDB Sanctions List with global coverage." />
        </head><body></body></html>
        """

        class TextResponse(FakeResponse):
            async def text(self):
                return html_payload

        session = FakeSession(TextResponse(content_type="text/html", payload=None))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="DEMO PROCUREMENT CO"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://data.iadb.org/dataset/dataset-of-sanctioned-firms-and-individuals"
        assert result.metadata["standardized_records"][0]["record_type"] == "procurement_debarment_dataset_catalog"
        records = result.data["source_catalog_records"]
        assert records[0]["entity"] == "Dataset of Sanctioned firms and individuals"
        assert "IDB sanctions dataset coverage" in records[0]["title"]
        assert "doi:10.60966/7pfpgt0f" in records[0]["summary"]
        assert records[0]["evidence"][0]["runtime_companion"] == "idb_local_subject_index"
        assert "catalog rows are coverage evidence only" in records[0]["evidence"][0]["subject_screening_policy"]

    @pytest.mark.asyncio
    async def test_world_bank_provider_maps_exact_public_debarment_match(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="world_bank_debarred_firms_public_list",
                type="rest_api",
                base_url="https://www.worldbank.org",
                headers={"Accept": "text/html"},
                custom={"provider_type": "world_bank_debarred_firms"},
                rate_limit={"enabled": False},
            )
        )
        html_payload = """
        <html><body><table>
          <tr><th>Firm Name</th><th>Address</th><th>Country</th><th>From Date</th><th>To Date</th><th>Grounds</th></tr>
          <tr>
            <td>DEMO PROCUREMENT CO</td>
            <td>1 Public Procurement Road</td>
            <td>US</td>
            <td>2025-01-01</td>
            <td>2028-01-01</td>
            <td>Fraudulent Practice</td>
          </tr>
        </table></body></html>
        """

        class TextResponse(FakeResponse):
            async def text(self):
                return html_payload

        session = FakeSession(TextResponse(content_type="text/html", payload=None))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="DEMO PROCUREMENT CO"))

        assert result.is_success
        assert session.calls[0]["url"] == "https://www.worldbank.org/en/projects-operations/procurement/debarred-firms"
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "DEMO PROCUREMENT CO"
        assert "World Bank debarred firm listing" in records[0]["title"]
        assert records[0]["entity_match"]["level"] == "exact"
        assert records[0]["risk_events"][0]["severity"] == "high"
        assert records[0]["registered_address"] == "1 Public Procurement Road"

    @pytest.mark.asyncio
    async def test_world_bank_provider_ignores_unrelated_public_debarment_rows(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="world_bank_debarred_firms_public_list",
                type="rest_api",
                base_url="https://www.worldbank.org",
                headers={"Accept": "text/html"},
                custom={"provider_type": "world_bank_debarred_firms"},
                rate_limit={"enabled": False},
            )
        )
        html_payload = """
        <html><body><table>
          <tr><th>Firm Name</th><th>Address</th><th>Country</th></tr>
          <tr><td>UNRELATED SUPPLIER LLC</td><td>2 Public Road</td><td>US</td></tr>
        </table></body></html>
        """

        class TextResponse(FakeResponse):
            async def text(self):
                return html_payload

        session = FakeSession(TextResponse(content_type="text/html", payload=None))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="DEMO PROCUREMENT CO"))

        assert result.is_success
        assert result.metadata["standardized_records"] == []

    @pytest.mark.asyncio
    async def test_official_portal_catalog_provider_returns_handoff_record(self, monkeypatch):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_registry_portal_catalog",
                type="rest_api",
                base_url="https://www.gsxt.gov.cn",
                description="National Enterprise Credit Information Publicity System portal catalog entry.",
                auth={"type": "challenge_aware", "challenge_provider": "browser_handoff"},
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_china_registry",
                    "source_legitimacy": "official_public_portal",
                    "coverage_domains": ["corporate_registry", "ownership_control", "related_entities"],
                    "adapter_required": True,
                    "parser_status": "pending_source_specific_parser",
                    "health_semantics": "manual_catalog_until_parser_exists",
                    "expected_fields": ["legal_name", "legal_representative", "shareholders"],
                    "handoff_steps": ["Search exact legal entity name.", "Retain visible official fields."],
                    "provenance_required": True,
                },
                rate_limit={"enabled": False},
            )
        )

        result = source.format_result({"probe": "catalog_only"})

        assert result["standardized_records"] == []
        records = result["source_catalog_records"]
        assert records[0]["source_name"] == "official_china_registry_portal_catalog"
        assert records[0]["url"] == "https://www.gsxt.gov.cn"
        assert "Official portal catalog handoff" in records[0]["title"]
        assert "corporate_registry" in records[0]["summary"]
        assert "parser_status=pending_source_specific_parser" in records[0]["summary"]
        assert records[0]["evidence"][0]["adapter_required"] is True
        assert records[0]["evidence"][0]["challenge_provider"] == "browser_handoff"
        assert records[0]["evidence"][0]["expected_fields"] == [
            "legal_name",
            "legal_representative",
            "shareholders",
        ]
        assert records[0]["evidence"][0]["health_semantics"] == "manual_catalog_until_parser_exists"

    def test_official_registry_portal_validated_snapshot_maps_standard_record(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_registry_portal_catalog",
                type="rest_api",
                base_url="https://www.gsxt.gov.cn",
                description="National Enterprise Credit Information Publicity System portal catalog entry.",
                auth={"type": "challenge_aware", "challenge_provider": "browser_handoff"},
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_china_registry",
                    "source_legitimacy": "official_public_portal",
                    "expected_fields": [
                        "legal_name",
                        "unified_social_credit_code",
                        "legal_representative",
                        "shareholders",
                        "registered_address",
                    ],
                },
                rate_limit={"enabled": False},
            )
        )
        source._current_query_hint = "Demo China Registry Co., Ltd."

        result = source.format_result({
            "page_status": "validated_result",
            "source_url": "https://www.gsxt.gov.cn/corp-query-entprise-info-123.html",
            "retrieved_at": "2026-06-21T16:00:00",
            "fields": {
                "legal_name": "Demo China Registry Co., Ltd.",
                "unified_social_credit_code": "91110000123456789X",
                "legal_representative": "Alice Zhang",
                "shareholders": ["Bob Li", "Demo Holdings Ltd."],
                "registered_address": "No. 1 Public Road, Beijing",
                "business_status": "active",
            },
        })

        assert result["source_catalog_records"] == []
        records = result["standardized_records"]
        assert records[0]["entity"] == "Demo China Registry Co., Ltd."
        assert records[0]["source_hint"] == "official_china_registry"
        assert records[0]["record_type"] == "official_registry_snapshot"
        assert records[0]["entity_match"]["level"] == "exact"
        assert records[0]["entity_match_level"] == "exact"
        assert records[0]["entity_match_score"] == 1.0
        assert records[0]["entity_match"]["identifiers"]["unified_social_credit_code"] == "91110000123456789X"
        assert records[0]["registered_address"] == "No. 1 Public Road, Beijing"
        assert records[0]["raw"]["unified_social_credit_code"] == "91110000123456789X"
        assert records[0]["evidence"][0]["type"] == "official_portal_validated_snapshot"
        assert records[0]["evidence"][0]["manual_review_required"] is True
        assert {item["relation"] for item in records[0]["entities"]} >= {
            "legal_representative",
            "shareholder",
            "registered_address",
        }
        assert result["raw"]["parse_status"] == "parsed_validated_snapshot"

    def test_official_credit_portal_validated_snapshot_maps_risk_event(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_credit_portal_catalog",
                type="rest_api",
                base_url="https://www.creditchina.gov.cn",
                description="Credit China public portal catalog entry.",
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_china_credit_publicity",
                    "source_legitimacy": "official_public_portal",
                    "expected_fields": ["legal_name", "administrative_penalty", "credit_notice"],
                },
                rate_limit={"enabled": False},
            )
        )
        source._current_query_hint = "Demo Credit Risk Co., Ltd."

        result = source.format_result({
            "page_status": "validated_result",
            "source_url": "https://www.creditchina.gov.cn/xinyongxinxixiangqing/notice-demo",
            "fields": {
                "legal_name": "Demo Credit Risk Co., Ltd.",
                "credit_notice": "Administrative penalty notice",
                "administrative_penalty": "Penalty for late disclosure",
                "issuing_authority": "Demo Market Supervision Bureau",
                "notice_date": "2026-06-20",
            },
        })

        record = result["standardized_records"][0]
        assert record["source_hint"] == "official_china_credit_publicity"
        assert record["record_type"] == "official_credit_publicity_snapshot"
        assert record["entity_match"]["level"] == "exact"
        assert record["entity_match_level"] == "exact"
        assert record["risk_category"] == "administrative_risk"
        assert record["severity"] == "medium"
        assert record["risk_events"][0]["risk_category"] == "administrative_risk"
        assert "Penalty for late disclosure" in record["summary"]
        assert record["published_at"] == "2026-06-20"

    def test_official_court_portal_validated_snapshot_maps_enforcement_event(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_court_enforcement_catalog",
                type="rest_api",
                base_url="https://zxgk.court.gov.cn",
                description="China Enforcement Information public portal catalog entry.",
                auth={"type": "challenge_aware", "challenge_provider": "browser_handoff"},
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_court_enforcement",
                    "source_legitimacy": "official_public_portal",
                    "expected_fields": [
                        "case_number",
                        "subject_name",
                        "court",
                        "filing_date",
                        "execution_amount",
                    ],
                },
                rate_limit={"enabled": False},
            )
        )
        source._current_query_hint = "Demo Enforcement Co., Ltd."

        result = source.format_result({
            "page_status": "validated_result",
            "source_url": "https://zxgk.court.gov.cn/zhzxgk/detail-demo",
            "fields": {
                "case_number": "(2026) Demo Exec 001",
                "subject_name": "Demo Enforcement Co., Ltd.",
                "court": "Demo Intermediate People's Court",
                "filing_date": "2026-06-19",
                "execution_amount": "1000000",
                "case_status": "active",
            },
        })

        record = result["standardized_records"][0]
        assert record["source_hint"] == "official_china_court_enforcement"
        assert record["record_type"] == "official_court_enforcement_snapshot"
        assert record["entity_match"]["level"] == "exact"
        assert record["entity_match_level"] == "exact"
        assert record["risk_category"] == "court_enforcement"
        assert record["severity"] == "high"
        assert record["risk_events"][0]["severity"] == "high"
        assert "(2026) Demo Exec 001" in record["summary"]
        assert record["published_at"] == "2026-06-19"

    def test_official_portal_missing_expected_fields_remains_review_handoff(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_registry_portal_catalog",
                type="rest_api",
                base_url="https://www.gsxt.gov.cn",
                description="National Enterprise Credit Information Publicity System portal catalog entry.",
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_china_registry",
                    "expected_fields": ["legal_name", "legal_representative"],
                },
                rate_limit={"enabled": False},
            )
        )
        source._current_query_hint = "Demo Missing Fields Co., Ltd."

        result = source.format_result({
            "page_status": "validated_result",
            "source_url": "https://www.gsxt.gov.cn/captcha-or-error",
            "fields": {"page_title": "captcha challenge"},
        })

        assert result["standardized_records"] == []
        assert result["source_catalog_records"][0]["evidence"][0]["type"] == "official_portal_parser_review"
        assert result["raw"]["parse_status"] == "review_required"

    def test_official_portal_validated_no_result_maps_auditable_no_result_record(self):
        source = RestApiDataSource(
            DataSourceConfig(
                name="official_china_court_enforcement_catalog",
                type="rest_api",
                base_url="https://zxgk.court.gov.cn",
                description="China Enforcement Information public portal catalog entry.",
                custom={
                    "provider_type": "official_portal_catalog",
                    "evidence_role": "official_court_enforcement",
                    "source_legitimacy": "official_public_portal",
                },
                rate_limit={"enabled": False},
            )
        )
        source._current_query_hint = "Demo No Enforcement Co., Ltd."

        result = source.format_result({
            "page_status": "validated_no_result",
            "source_url": "https://zxgk.court.gov.cn/search-demo",
            "retrieved_at": "2026-06-21T16:30:00",
            "fields": {"subject_name": "Demo No Enforcement Co., Ltd."},
        })

        record = result["standardized_records"][0]
        assert record["entity"] == "Demo No Enforcement Co., Ltd."
        assert record["record_type"] == "official_portal_no_result_snapshot"
        assert record["entity_match"]["level"] == "no_result"
        assert record["entity_match_level"] == "no_result"
        assert record["evidence"][0]["type"] == "official_portal_no_result"
        assert result["raw"]["parse_status"] == "parsed_validated_no_result"

    @pytest.mark.asyncio
    async def test_local_index_datasource_maps_jsonl_subject_match(self, tmp_path):
        index_path = tmp_path / "opensanctions-local.jsonl"
        index_path.write_text(
            "\n".join([
                '{"name":"DEMO WATCHLIST CO","dataset":"default","category":"sanctions","summary":"Configured public index lead","url":"https://example.invalid/default/demo"}',
                '{"name":"UNRELATED ENTITY","dataset":"default","category":"sanctions"}',
            ]),
            encoding="utf-8",
        )
        source = LocalIndexDataSource(
            DataSourceConfig(
                name="opensanctions_local_index",
                type="local_index",
                base_url="https://local.invalid",
                custom={
                    "index_path": str(index_path),
                    "provider": "OpenSanctions local index",
                    "dataset": "default",
                },
                rate_limit={"enabled": False},
            )
        )

        result = await source.query(QueryRequest(query="DEMO WATCHLIST CO"))

        assert result.is_success
        records = result.metadata["standardized_records"]
        assert records[0]["entity"] == "DEMO WATCHLIST CO"
        assert records[0]["entity_match"]["level"] == "exact"
        assert records[0]["risk_events"][0]["severity"] == "medium"
        assert result.data["raw"]["parsed_count"] == 2
        assert result.data["raw"]["match_count"] == 1

    @pytest.mark.asyncio
    async def test_local_index_datasource_maps_csv_procurement_match(self, tmp_path):
        index_path = tmp_path / "idb-local.csv"
        index_path.write_text(
            "firm_name,dataset,category,summary,url,severity\n"
            "DEMO PROCUREMENT CO,idb,procurement,Configured procurement index lead,https://example.invalid/idb/demo,high\n"
            "UNRELATED SUPPLIER,idb,procurement,Unrelated lead,https://example.invalid/idb/unrelated,high\n",
            encoding="utf-8",
        )
        source = LocalIndexDataSource(
            DataSourceConfig(
                name="idb_local_index",
                type="local_index",
                base_url="https://local.invalid",
                custom={
                    "index_path": str(index_path),
                    "provider": "IDB local index",
                    "dataset": "idb",
                },
                rate_limit={"enabled": False},
            )
        )

        result = await source.query(QueryRequest(query="DEMO PROCUREMENT CO"))

        assert result.is_success
        records = result.metadata["standardized_records"]
        assert len(records) == 1
        assert records[0]["entity"] == "DEMO PROCUREMENT CO"
        assert records[0]["risk_events"][0]["severity"] == "high"
        assert records[0]["evidence"][0]["provider"] == "IDB local index"

    @pytest.mark.asyncio
    async def test_failure_result_includes_structured_error_details(self, config, monkeypatch):
        source = RestApiDataSource(config)
        session = FakeSession(FakeResponse(status=500, payload={"error": "down"}))

        async def fake_get_session():
            return session

        monkeypatch.setattr(source, "_get_session", fake_get_session)

        result = await source.query(QueryRequest(query="reports/list"))

        assert result.status is QueryStatus.FAILED
        assert result.metadata["error_details"]["type"] == "RuntimeError"
        assert result.metadata["request"]["query"] == "reports/list"


class TestStandardizedRecords:
    def test_standardizes_list_of_dicts(self):
        records = standardize_records(
            [{"companyName": "Demo Co", "headline": "New filing", "score": "0.9"}],
            "demo",
            "rest_api",
            "Demo Co",
        )

        assert len(records) == 1
        assert isinstance(records[0], StandardizedRecord)
        assert records[0].entity == "Demo Co"
        assert records[0].title == "New filing"
        assert records[0].confidence == 0.9

    def test_standardizes_nested_result_payload(self):
        records = standardize_records(
            {"results": [{"name": "Nested Co", "summary": "matched"}]},
            "demo",
            "rest_api",
            "Nested Co",
        )

        assert records[0].entity == "Nested Co"
        assert records[0].summary == "matched"


class TestDataSourceManager:
    def test_default_datasources_template_is_loadable_and_default_safe(self):
        config_path = (
            Path(__file__).parent.parent.parent
            / "adapters"
            / "multi_datasource"
            / "datasources.yaml"
        )
        manager = DataSourceManager(config_path)

        manager.load_config()

        sources = {source.name: source for source in manager.config.sources}
        enabled = {source.name for source in manager.config.sources if source.enabled}

        assert "github_public_api" in sources
        assert enabled == {"github_public_api"}
        assert sources["public_web_search_searxng"].custom["provider_type"] == "searxng"
        assert sources["licensed_registry_api"].auth.type == "bearer"
        assert sources["signed_public_records_api"].auth.type == "request_signature"
        assert sources["challenge_aware_public_portal"].auth.type == "challenge_aware"
        assert sources["telegram_public_service_example"].custom["source_review_required"] is True
        assert {
            "gleif_lei_public_api",
            "gleif_lei_relationship_traversal_public_api",
            "sec_edgar_public_api",
            "opensanctions_public_dataset_catalog",
            "opensanctions_local_subject_index",
            "ofac_consolidated_sanctions_xml",
            "un_sc_consolidated_sanctions_xml",
            "idb_sanctioned_firms_dataset_catalog",
            "idb_local_subject_index",
            "world_bank_debarred_firms_public_list",
            "wikidata_public_entity_graph",
            "official_china_registry_portal_catalog",
            "official_china_credit_portal_catalog",
            "official_china_court_enforcement_catalog",
        } <= set(sources)
        assert sources["gleif_lei_public_api"].custom["provider_type"] == "gleif_lei"
        assert "relationship" in sources["gleif_lei_public_api"].custom["controller_relevance"]
        assert sources["gleif_lei_relationship_traversal_public_api"].custom["provider_type"] == "gleif_relationship_traversal"
        assert "related_lei" in sources["gleif_lei_relationship_traversal_public_api"].custom["fact_promotion_gate"]
        assert sources["sec_edgar_public_api"].custom["provider_type"] == "sec_edgar"
        assert sources["sec_edgar_public_api"].custom["provenance_required"] is True
        assert sources["opensanctions_public_dataset_catalog"].custom["provider_type"] == "opensanctions_dataset_catalog"
        assert "controller" in sources["opensanctions_public_dataset_catalog"].custom["controller_relevance"]
        assert sources["opensanctions_local_subject_index"].type == "local_index"
        assert sources["opensanctions_local_subject_index"].custom["index_path"].endswith("opensanctions-subjects.jsonl")
        assert sources["ofac_consolidated_sanctions_xml"].custom["provider_type"] == "ofac_consolidated_xml"
        assert sources["ofac_consolidated_sanctions_xml"].custom["provenance_required"] is True
        assert sources["un_sc_consolidated_sanctions_xml"].custom["provider_type"] == "un_sc_consolidated_sanctions_xml"
        assert sources["un_sc_consolidated_sanctions_xml"].custom["provenance_required"] is True
        assert sources["idb_sanctioned_firms_dataset_catalog"].custom["provider_type"] == "idb_sanctioned_firms_dataset_catalog"
        assert sources["idb_sanctioned_firms_dataset_catalog"].custom["local_index_required_for_subject_matching"] is True
        assert sources["idb_local_subject_index"].type == "local_index"
        assert sources["idb_local_subject_index"].custom["index_path"].endswith("idb-subjects.csv")
        assert sources["world_bank_debarred_firms_public_list"].custom["provider_type"] == "world_bank_debarred_firms"
        assert sources["world_bank_debarred_firms_public_list"].custom["provenance_required"] is True
        assert sources["wikidata_public_entity_graph"].custom["provider_type"] == "wikidata_entity_search"
        assert sources["official_china_registry_portal_catalog"].custom["provider_type"] == "official_portal_catalog"
        assert sources["official_china_credit_portal_catalog"].custom["provider_type"] == "official_portal_catalog"
        assert sources["official_china_court_enforcement_catalog"].custom["provider_type"] == "official_portal_catalog"
        assert "legal_representative" in sources["official_china_registry_portal_catalog"].custom["expected_fields"]
        assert "administrative_penalty" in sources["official_china_credit_portal_catalog"].custom["expected_fields"]
        assert "case_number" in sources["official_china_court_enforcement_catalog"].custom["expected_fields"]
        assert sources["official_china_registry_portal_catalog"].custom["parser_status"] == "validated_snapshot_parser_available"
        assert sources["official_china_credit_portal_catalog"].custom["accepted_page_statuses"] == [
            "validated_result",
            "validated_no_result",
        ]
        assert sources["official_china_court_enforcement_catalog"].custom["health_semantics"] == (
            "browser_handoff_or_validated_snapshot_no_live_health"
        )

    def test_load_config_rejects_empty_yaml(self, tmp_path):
        config_path = tmp_path / "empty.yaml"
        config_path.write_text("", encoding="utf-8")

        manager = DataSourceManager(config_path)

        with pytest.raises(ConfigError):
            manager.load_config()

    @pytest.mark.asyncio
    async def test_query_multiple_caps_source_count(self, monkeypatch):
        manager = DataSourceManager()
        manager._sources = {
            f"s{i}": SimpleNamespace(name=f"s{i}", config=SimpleNamespace(cache_enabled=False))
            for i in range(105)
        }

        seen: list[str] = []

        async def fake_query_single(source_name, request, use_cache=True):
            seen.append(source_name)
            return QueryResult(
                source_name=source_name,
                source_type="rest_api",
                status=QueryStatus.SUCCESS,
                data={"ok": True},
            )

        monkeypatch.setattr(manager, "query_single", fake_query_single)

        result = await manager.query_multiple(
            list(manager._sources.keys()),
            QueryRequest(query="reports/list"),
            concurrency=3,
        )

        assert len(seen) == manager.MAX_SOURCES
        assert len(result.results) == manager.MAX_SOURCES

    def test_available_sources_filters_health_and_sorts_by_priority(self):
        manager = DataSourceManager()
        manager._sources = {
            "slow": SimpleNamespace(
                name="slow",
                type_name="rest_api",
                config=SimpleNamespace(enabled=True, priority=50),
            ),
            "fast": SimpleNamespace(
                name="fast",
                type_name="rest_api",
                config=SimpleNamespace(enabled=True, priority=10),
            ),
            "down": SimpleNamespace(
                name="down",
                type_name="rest_api",
                config=SimpleNamespace(enabled=True, priority=1),
            ),
            "disabled": SimpleNamespace(
                name="disabled",
                type_name="rest_api",
                config=SimpleNamespace(enabled=False, priority=0),
            ),
        }
        manager._health_status = {"slow": True, "fast": True, "down": False}

        assert [source.name for source in manager.available_sources()] == ["fast", "slow"]

    @pytest.mark.asyncio
    async def test_query_available_uses_only_healthy_sources(self, monkeypatch):
        manager = DataSourceManager()
        manager._sources = {
            "healthy": SimpleNamespace(
                name="healthy",
                type_name="rest_api",
                config=SimpleNamespace(enabled=True, priority=10, cache_enabled=False),
            ),
            "unhealthy": SimpleNamespace(
                name="unhealthy",
                type_name="rest_api",
                config=SimpleNamespace(enabled=True, priority=1, cache_enabled=False),
            ),
        }
        manager._health_status = {"healthy": True, "unhealthy": False}
        seen: list[str] = []

        async def fake_query_single(source_name, request, use_cache=True):
            seen.append(source_name)
            return QueryResult(
                source_name=source_name,
                source_type="rest_api",
                status=QueryStatus.SUCCESS,
                data={"ok": True},
            )

        monkeypatch.setattr(manager, "query_single", fake_query_single)

        result = await manager.query_available(QueryRequest(query="reports/list"))

        assert seen == ["healthy"]
        assert result.successful_count == 1

    @pytest.mark.asyncio
    async def test_health_report_all_exposes_structured_skipped_report(self):
        manager = DataSourceManager()
        manager._sources = {
            "manual": SimpleNamespace(
                name="manual",
                type_name="rest_api",
                config=SimpleNamespace(
                    ping=False,
                    ping_endpoint="",
                    base_url="https://api.example.com",
                    auto_disable_on_fail=True,
                ),
            )
        }

        reports = await manager.health_report_all()

        assert isinstance(reports["manual"], HealthReport)
        assert reports["manual"].ok is True
        assert reports["manual"].status == "skipped"
        assert reports["manual"].to_dict()["endpoint"] == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_official_portal_health_report_exposes_manual_gate_semantics(self):
        manager = DataSourceManager()
        manager._sources = {
            "official_china_registry_portal_catalog": SimpleNamespace(
                name="official_china_registry_portal_catalog",
                type_name="rest_api",
                config=SimpleNamespace(
                    ping=False,
                    ping_endpoint="",
                    base_url="https://www.gsxt.gov.cn",
                    auto_disable_on_fail=True,
                    custom={
                        "provider_type": "official_portal_catalog",
                        "parser_status": "validated_snapshot_parser_available",
                        "health_semantics": "browser_handoff_or_validated_snapshot_no_live_health",
                        "accepted_page_statuses": ["validated_result", "validated_no_result"],
                    },
                    auth=SimpleNamespace(challenge_provider="browser_handoff"),
                ),
            )
        }

        reports = await manager.health_report_all()
        report = reports["official_china_registry_portal_catalog"]

        assert report.ok is True
        assert report.status == "manual_gate"
        assert report.auth_challenge["type"] == "official_portal_manual_gate"
        assert report.auth_challenge["details"]["provider"] == "browser_handoff"
        assert report.auth_challenge["details"]["parser_status"] == "validated_snapshot_parser_available"
        assert report.auth_challenge["details"]["accepted_page_statuses"] == [
            "validated_result",
            "validated_no_result",
        ]
        assert manager._health_status["official_china_registry_portal_catalog"] is True

    @pytest.mark.asyncio
    async def test_health_report_all_updates_status_and_auto_disable(self, monkeypatch):
        manager = DataSourceManager()
        config = SimpleNamespace(
            ping=True,
            ping_endpoint="https://api.example.com/health",
            base_url="https://api.example.com",
            auto_disable_on_fail=True,
            enabled=True,
        )
        manager._sources = {
            "down": SimpleNamespace(name="down", type_name="rest_api", config=config)
        }

        async def fake_check(name, source):
            return False

        monkeypatch.setattr(manager, "_check_single_connectivity", fake_check)

        reports = await manager.health_report_all()

        assert reports["down"].ok is False
        assert reports["down"].status == "down"
        assert manager._health_status["down"] is False
        assert config.enabled is False

    @pytest.mark.asyncio
    async def test_connectivity_check_sends_configured_headers(self, monkeypatch):
        manager = DataSourceManager()
        config = SimpleNamespace(
            ping=True,
            ping_endpoint="https://data.sec.gov/submissions/CIK0000320193.json",
            base_url="https://data.sec.gov",
            ping_timeout=5,
            headers={"User-Agent": "wallstreet-tieling-test@example.invalid"},
        )
        source = SimpleNamespace(name="sec", type_name="rest_api", config=config)
        fake_session = FakeHealthSession(FakeResponse(status=200))

        class FakeClientSession:
            def __init__(self, timeout=None):
                self.timeout = timeout

            async def __aenter__(self):
                return fake_session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", FakeClientSession)

        assert await manager._check_single_connectivity("sec", source) is True
        assert fake_session.calls[0]["headers"] == {
            "User-Agent": "wallstreet-tieling-test@example.invalid"
        }

    @pytest.mark.asyncio
    async def test_connectivity_check_falls_back_to_get_when_head_is_rejected(self, monkeypatch):
        manager = DataSourceManager()
        config = SimpleNamespace(
            ping=True,
            ping_endpoint="https://data.sec.gov/submissions/CIK0000320193.json",
            base_url="https://data.sec.gov",
            ping_timeout=5,
            headers={"User-Agent": "wallstreet-tieling-test@example.invalid"},
        )
        source = SimpleNamespace(name="sec", type_name="rest_api", config=config)
        fake_session = FakeHealthSession(
            FakeResponse(status=403),
            get_response=FakeResponse(status=200),
        )

        class FakeClientSession:
            def __init__(self, timeout=None):
                self.timeout = timeout

            async def __aenter__(self):
                return fake_session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", FakeClientSession)

        assert await manager._check_single_connectivity("sec", source) is True
        assert [call["method"] for call in fake_session.calls] == ["HEAD", "GET"]

    @pytest.mark.asyncio
    async def test_health_check_all_keeps_bool_compatibility(self, monkeypatch):
        manager = DataSourceManager()

        async def fake_reports():
            return {
                "up": HealthReport("up", "rest_api", True, "up", "https://up.example"),
                "down": HealthReport("down", "rest_api", False, "down", "https://down.example"),
            }

        monkeypatch.setattr(manager, "health_report_all", fake_reports)

        assert await manager.health_check_all() == {"up": True, "down": False}

    @pytest.mark.asyncio
    async def test_check_connectivity_refreshes_structured_health_reports(self, monkeypatch):
        manager = DataSourceManager()
        manager._sources = {
            "official": SimpleNamespace(
                name="official",
                type_name="rest_api",
                config=SimpleNamespace(
                    ping=True,
                    ping_endpoint="https://api.example.com/health",
                    base_url="https://api.example.com",
                    auto_disable_on_fail=True,
                    enabled=True,
                ),
            )
        }

        async def fake_check(name, source):
            return True

        monkeypatch.setattr(manager, "_check_single_connectivity", fake_check)

        assert await manager.check_connectivity() == {"official": True}
        assert manager._health_reports["official"].status == "up"
        assert manager._health_reports["official"].detail == "connectivity check passed"

    @pytest.mark.asyncio
    async def test_search_engine_search_available_returns_aggregated_result(self, monkeypatch):
        manager = DataSourceManager()

        async def fake_query_available(request, filter_types=None, concurrency=10, use_cache=True):
            return md.AggregatedResult(
                results=[
                    QueryResult(
                        source_name="healthy",
                        source_type="rest_api",
                        status=QueryStatus.SUCCESS,
                        data={"query": request.query},
                    )
                ]
            )

        monkeypatch.setattr(manager, "query_available", fake_query_available)

        engine = SearchEngine()
        engine._manager = manager
        engine._initialized = True
        monkeypatch.setattr(SearchEngine, "_instance", engine)

        result = await SearchEngine.search_available("reports/list")

        assert result.successful_count == 1
        assert result.results[0].data == {"query": "reports/list"}
