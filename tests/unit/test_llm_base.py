#!/usr/bin/env python3
"""Tests for OpenAI-compatible LLM adapter behavior."""
from __future__ import annotations

import pytest

from adapters._base import OpenAICompatibleLLM


class FakeResponse:
    def __init__(self, status: int, body: str = "", payload: dict | None = None):
        self.status = status
        self._body = body
        self._payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._body

    async def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


@pytest.mark.asyncio
async def test_llm_http_error_preserves_transient_body(monkeypatch):
    import aiohttp

    response = FakeResponse(
        503,
        "Selected model is at capacity. Please try a different model. token=secret-token",
    )
    session = FakeSession(response)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: session)

    llm = OpenAICompatibleLLM("test-key", "https://api.example.com/v1", "demo-model")

    result = await llm.chat("system", "user")

    assert result.ok is False
    assert "HTTP 503" in result.error
    assert "Selected model is at capacity" in result.error
    assert "secret-token" not in result.error
    assert "[REDACTED]" in result.error


@pytest.mark.asyncio
async def test_llm_success_maps_message_and_usage(monkeypatch):
    import aiohttp

    response = FakeResponse(
        200,
        payload={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 12},
        },
    )
    session = FakeSession(response)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: session)

    llm = OpenAICompatibleLLM("test-key", "https://api.example.com/v1", "demo-model")

    result = await llm.chat("system", "user")

    assert result.ok is True
    assert result.text == "ok"
    assert result.tokens_used == 12
