#!/usr/bin/env python3
"""Tests for configurable datasource authentication handlers."""
from __future__ import annotations

import time

import pytest

from adapters.multi_datasource import AuthConfig, DataSourceConfig, QueryRequest, QueryStatus, RestApiDataSource
from adapters.multi_datasource.auth_handlers import (
    AuthChallengeRequired,
    AuthRequestContext,
    AuthResponseContext,
    BrowserHandoffChallengeProvider,
    ChallengeAwareAuthHandler,
    ChallengeDescriptor,
    ChallengeProviderRegistry,
    DisabledChallengeProvider,
    RefreshableBearerAuthHandler,
)


class FakeResponse:
    def __init__(self, *, status=200, headers=None, payload=None, text_payload=""):
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self.content_length = None
        self._payload = payload or {"ok": True}
        self._text_payload = text_payload

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload

    async def text(self):
        return self._text_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []
        self.closed = False

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.response


def make_config(auth: AuthConfig) -> DataSourceConfig:
    return DataSourceConfig(
        name="auth_demo",
        type="rest_api",
        base_url="https://api.example.com",
        auth=auth,
        rate_limit={"enabled": False},
    )


@pytest.mark.asyncio
async def test_rest_datasource_applies_api_key_header(monkeypatch):
    source = RestApiDataSource(
        make_config(AuthConfig(type="api_key", api_key="test-key", header_name="X-Test-Key"))
    )
    session = FakeSession(FakeResponse())

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    await source._do_query(QueryRequest(query="companies/search"))

    assert session.calls[0]["headers"]["X-Test-Key"] == "test-key"


@pytest.mark.asyncio
async def test_rest_datasource_applies_bearer_and_session_cookie(monkeypatch):
    source = RestApiDataSource(
        make_config(
            AuthConfig(
                type="challenge_aware",
                token="session-token",
                cookies={"sid": "abc"},
            )
        )
    )
    session = FakeSession(FakeResponse())

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    await source._do_query(QueryRequest(query="companies/search"))

    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer session-token"
    assert headers["Cookie"] == "sid=abc"


@pytest.mark.asyncio
async def test_rest_datasource_applies_request_signature(monkeypatch):
    source = RestApiDataSource(
        make_config(
            AuthConfig(
                type="request_signature",
                signature_secret="secret",
                signature_header="X-Demo-Signature",
            )
        )
    )
    session = FakeSession(FakeResponse())

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    await source._do_query(QueryRequest(query="companies/search", params={"q": "Demo"}))

    headers = session.calls[0]["headers"]
    assert headers["X-Demo-Signature"]
    assert headers["X-Timestamp"]


@pytest.mark.asyncio
async def test_refreshable_bearer_marks_expired_token():
    handler = RefreshableBearerAuthHandler(token="old", expires_at=time.time() - 1)
    context = AuthRequestContext("demo", "GET", "https://example.com")

    await handler.prepare(context)

    assert context.metadata["auth_refresh_required"] is True
    assert handler.refresh_required is True


@pytest.mark.asyncio
async def test_challenge_aware_handler_detects_human_verification():
    handler = ChallengeAwareAuthHandler()
    context = AuthRequestContext("demo", "GET", "https://example.com")
    response = AuthResponseContext(
        status=403,
        headers={"x-challenge": "captcha"},
        content_type="text/html",
        body_preview="captcha verification required",
    )

    with pytest.raises(AuthChallengeRequired) as exc:
        await handler.handle_response(context, response)

    assert exc.value.challenge_type == "human_verification"
    assert exc.value.details["handling"].startswith("requires configured")
    assert exc.value.details["provider"]["provider"] == "disabled"
    assert exc.value.details["provider"]["status"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_challenge_aware_handler_detects_chinese_hints():
    handler = ChallengeAwareAuthHandler()
    context = AuthRequestContext("demo", "GET", "https://example.com")
    response = AuthResponseContext(
        status=403,
        headers={"content-type": "text/html"},
        content_type="text/html",
        body_preview="请完成人机验证，输入验证码或拖动滑块继续。",
    )

    with pytest.raises(AuthChallengeRequired):
        await handler.handle_response(context, response)


@pytest.mark.asyncio
async def test_disabled_challenge_provider_returns_default_safe_handoff():
    provider = DisabledChallengeProvider()
    descriptor = ChallengeDescriptor("human_verification", "demo", 403)
    context = AuthRequestContext("demo", "GET", "https://example.com")

    handoff = await provider.handle_challenge(descriptor, context)

    assert handoff.status == "provider_not_configured"
    assert handoff.metadata["automation_enabled"] is False
    assert handoff.metadata["default_safe"] is True


@pytest.mark.asyncio
async def test_browser_handoff_challenge_provider_returns_ui_handoff():
    provider = BrowserHandoffChallengeProvider({"callback_url": "http://127.0.0.1/callback"})
    descriptor = ChallengeDescriptor("human_verification", "demo", 403)
    context = AuthRequestContext("demo", "GET", "https://example.com/challenge")

    handoff = await provider.handle_challenge(descriptor, context)

    assert handoff.provider == "browser_handoff"
    assert handoff.status == "handoff_required"
    assert handoff.metadata["handoff_url"] == "https://example.com/challenge"
    assert handoff.metadata["automation_enabled"] is False


def test_challenge_provider_registry_supports_configured_slots():
    registry = ChallengeProviderRegistry()

    assert registry.supported_providers() == ["browser_handoff", "disabled"]
    assert registry.build("browser_handoff").name == "browser_handoff"
    assert registry.build("unknown").name == "disabled"


@pytest.mark.asyncio
async def test_query_result_exposes_auth_challenge_metadata(monkeypatch):
    source = RestApiDataSource(make_config(AuthConfig(type="challenge_aware")))
    session = FakeSession(
        FakeResponse(
            status=403,
            headers={"content-type": "text/html", "x-challenge": "captcha"},
            payload={"error": "captcha"},
        )
    )

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(QueryRequest(query="companies/search"))

    assert result.status is QueryStatus.FAILED
    assert result.metadata["auth_challenge"]["type"] == "human_verification"
    assert result.metadata["auth_challenge"]["details"]["handling"].startswith("requires configured")
    assert result.metadata["auth_challenge"]["details"]["provider"]["status"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_query_result_detects_auth_challenge_from_response_body(monkeypatch):
    source = RestApiDataSource(make_config(AuthConfig(type="challenge_aware")))
    session = FakeSession(
        FakeResponse(
            status=403,
            headers={"content-type": "text/html"},
            payload={"error": "challenge"},
            text_payload="请完成人机验证，拖动滑块继续。",
        )
    )

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(QueryRequest(query="companies/search"))

    assert result.status is QueryStatus.FAILED
    assert result.metadata["auth_challenge"]["type"] == "human_verification"


@pytest.mark.asyncio
async def test_query_result_exposes_configured_browser_handoff_provider(monkeypatch):
    source = RestApiDataSource(
        make_config(
            AuthConfig(
                type="challenge_aware",
                challenge_provider="browser_handoff",
                challenge_provider_config={"session_scope": "tenant"},
            )
        )
    )
    session = FakeSession(
        FakeResponse(
            status=403,
            headers={"content-type": "text/html", "x-challenge": "captcha"},
            payload={"error": "captcha"},
        )
    )

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    result = await source.query(QueryRequest(query="companies/search"))

    provider = result.metadata["auth_challenge"]["details"]["provider"]
    assert provider["provider"] == "browser_handoff"
    assert provider["status"] == "handoff_required"
    assert provider["metadata"]["session_scope"] == "tenant"


@pytest.mark.asyncio
async def test_auth_handler_cannot_inject_newline_header(monkeypatch):
    source = RestApiDataSource(
        make_config(
            AuthConfig(
                type="api_key",
                api_key="test-key",
                header_name="X-Test-Key\nX-Injected",
            )
        )
    )
    session = FakeSession(FakeResponse())

    async def fake_get_session():
        return session

    monkeypatch.setattr(source, "_get_session", fake_get_session)

    with pytest.raises(ValueError, match="newline"):
        await source._do_query(QueryRequest(query="companies/search"))

    assert session.calls == []
