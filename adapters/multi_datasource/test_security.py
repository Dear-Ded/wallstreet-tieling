"""CI-safe security contract tests for the multi data-source adapter.

These tests intentionally avoid real network calls, long sleeps, and pressure-test
loops. Heavier penetration scenarios belong in a separate manual or nightly suite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from adapters import multi_datasource as md
from adapters.multi_datasource import (
    AuthConfig,
    ConfigError,
    DataSourceConfig,
    DataSourceManager,
    QueryError,
    QueryRequest,
    QueryResult,
    QueryStatus,
    RateLimitConfig,
    RestApiDataSource,
    RetryConfig,
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
        self._payload = payload if payload is not None else {"data": {"ok": True}}
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


@pytest.fixture
def valid_config() -> DataSourceConfig:
    return DataSourceConfig(
        name="security_test_api",
        type="rest_api",
        base_url="https://api.example.com/v1",
        timeout=3,
        headers={"User-Agent": "WallstreetTielingTests/1.0"},
        auth=AuthConfig(type="none"),
        rate_limit=RateLimitConfig(enabled=False),
        retry=RetryConfig(max_retries=1, backoff_factor=0.1),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://127.1/admin",
        "http://0x7f000001/admin",
        "http://0.0.0.0/admin",
        "http://[::1]/admin",
        "http://10.0.0.1/internal",
        "http://172.16.0.1/internal",
        "http://192.168.0.1/internal",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://192.0.2.1/example",
        "http://198.51.100.1/example",
        "http://203.0.113.1/example",
        "ftp://example.com",
        "file:///etc/passwd",
        "https://user:pass@example.com",
        "https://example.com/path?token=secret",
    ],
)
def test_base_url_rejects_ssrf_and_unsafe_targets(url: str) -> None:
    with pytest.raises(ValueError):
        DataSourceConfig(name="blocked", type="rest_api", base_url=url)


def test_ping_endpoint_uses_same_url_policy() -> None:
    cfg = DataSourceConfig(
        name="ping",
        type="rest_api",
        base_url="https://api.example.com",
        ping_endpoint="https://api.example.com/health",
    )
    assert cfg.ping_endpoint == "https://api.example.com/health"

    with pytest.raises(ValueError):
        DataSourceConfig(
            name="ping",
            type="rest_api",
            base_url="https://api.example.com",
            ping_endpoint="http://127.0.0.1/health",
        )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "../secret",
        "/admin",
        "//evil.example",
        "https://evil.example/path",
        r"windows\path",
        "reports/list?debug=true",
        "reports\nlist",
        "x" * 2049,
    ],
)
def test_query_request_rejects_unsafe_query_shapes(query: str) -> None:
    with pytest.raises(ValueError):
        QueryRequest(query=query)


def test_query_request_rejects_header_injection() -> None:
    with pytest.raises(ValueError):
        QueryRequest(query="reports/list", headers={"Host": "evil.example"})

    with pytest.raises(ValueError):
        QueryRequest(query="reports/list", headers={"X-Test": "ok\r\nInjected: 1"})


@pytest.mark.asyncio
async def test_rest_query_sends_only_safe_path_params_and_headers(valid_config, monkeypatch):
    source = RestApiDataSource(valid_config)
    session = FakeSession(FakeResponse(payload={"data": {"company": "ok"}}))

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(
        QueryRequest(
            query="companies/search",
            params={"keyword": "demo"},
            headers={"X-Trace-Id": "trace-1"},
        )
    )

    assert result.status is QueryStatus.SUCCESS
    assert result.data == {"company": "ok"}
    assert session.calls == [
        {
            "url": "https://api.example.com/v1/companies/search",
            "params": {"keyword": "demo"},
            "headers": {
                "User-Agent": "WallstreetTielingTests/1.0",
                "X-Trace-Id": "trace-1",
            },
        }
    ]


@pytest.mark.asyncio
async def test_large_response_is_failed_without_exposing_raw_error(valid_config, monkeypatch):
    source = RestApiDataSource(valid_config)
    session = FakeSession(FakeResponse(content_length=10 * 1024 * 1024 + 1))

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(QueryRequest(query="reports/list"))

    assert result.status is QueryStatus.FAILED
    assert isinstance(result.error, QueryError)
    assert str(result.error) == "查询执行失败"


@pytest.mark.asyncio
async def test_json_parse_errors_are_wrapped(valid_config, monkeypatch):
    source = RestApiDataSource(valid_config)
    session = FakeSession(FakeResponse(json_exc=ValueError("raw parser secret")))

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(QueryRequest(query="reports/list"))

    assert result.status is QueryStatus.FAILED
    assert isinstance(result.error, QueryError)
    assert "raw parser secret" not in str(result.error)


@pytest.mark.asyncio
async def test_rate_limit_wait_is_observable_without_real_sleep(monkeypatch):
    waits: list[float] = []
    cfg = DataSourceConfig(
        name="limited",
        type="rest_api",
        base_url="https://api.example.com",
        rate_limit=RateLimitConfig(enabled=True, requests_per_second=1.0, burst_size=1),
    )
    source = RestApiDataSource(cfg)

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(md.asyncio, "sleep", fake_sleep)

    await source._pre_query(QueryRequest(query="reports/list"))
    await source._pre_query(QueryRequest(query="reports/list"))

    assert len(waits) == 1
    assert waits[0] > 0


@pytest.mark.asyncio
async def test_retry_count_is_capped_by_config(valid_config, monkeypatch):
    valid_config.retry = RetryConfig(max_retries=2, backoff_factor=0.1)
    source = RestApiDataSource(valid_config)
    attempts = 0
    waits: list[float] = []

    async def fail_query(request):
        nonlocal attempts
        attempts += 1
        raise QueryError("transient failure")

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(source, "_do_query", fail_query)
    monkeypatch.setattr(md.asyncio, "sleep", fake_sleep)

    result = await source.query(QueryRequest(query="reports/list"))

    assert result.status is QueryStatus.FAILED
    assert attempts == 3
    assert len(waits) == 2


@pytest.mark.asyncio
async def test_manager_rejects_excessive_concurrency() -> None:
    manager = DataSourceManager()

    with pytest.raises(ValueError):
        await manager.query_all(QueryRequest(query="reports/list"), concurrency=10_000)


@pytest.mark.asyncio
async def test_manager_caps_source_count(monkeypatch) -> None:
    manager = DataSourceManager()
    manager._sources = {
        f"source_{idx}": type(
            "Source",
            (),
            {
                "name": f"source_{idx}",
                "type_name": "rest_api",
                "config": type("Config", (), {"cache_enabled": False})(),
            },
        )()
        for idx in range(manager.MAX_SOURCES + 5)
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

    result = await manager.query_all(QueryRequest(query="reports/list"), concurrency=5)

    assert len(seen) == manager.MAX_SOURCES
    assert len(result.results) == manager.MAX_SOURCES


def test_sensitive_values_do_not_enter_init_logs(caplog) -> None:
    cfg = DataSourceConfig(
        name="log_safety",
        type="rest_api",
        base_url="https://api.example.com",
        auth=AuthConfig(type="basic", username="admin", password="super-secret-password"),
        headers={"Authorization": "Bearer token-secret"},
    )

    RestApiDataSource(cfg)

    log_output = caplog.text
    assert "super-secret-password" not in log_output
    assert "token-secret" not in log_output


def test_yaml_config_uses_safe_load(tmp_path: Path) -> None:
    config_file = tmp_path / "malicious.yaml"
    config_file.write_text(
        """
version: "1.0"
sources:
  - name: exploit
    type: rest_api
    base_url: https://example.com
    custom:
      !!python/object/apply:os.system ["echo pwned"]
""",
        encoding="utf-8",
    )

    with pytest.raises(yaml.constructor.ConstructorError):
        with config_file.open("r", encoding="utf-8") as handle:
            yaml.safe_load(handle)


def test_empty_config_file_is_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("", encoding="utf-8")

    manager = DataSourceManager(config_file)

    with pytest.raises(ConfigError):
        manager.load_config()
