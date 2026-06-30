#!/usr/bin/env python3
"""Tests for token optimization helpers."""
from __future__ import annotations

import asyncio

import pytest

from core.token_optimizer import (
    LLMResponseCache,
    TokenUsageStats,
    batch_llm_call,
    cached_llm_call,
    compress_prompt,
    compress_system_prompt,
    compress_user_prompt,
)


def test_llm_response_cache_hit_miss_expiry_and_size_limit():
    cache = LLMResponseCache(max_size=1, ttl=10)

    assert cache.get("sys", "user", "model") is None
    cache.set("sys", "user", "model", {"text": "ok"})
    assert cache.get("sys", "user", "model") == {"text": "ok"}
    cache.set("sys2", "user", "model", {"text": "new"})

    assert cache.get("sys", "user", "model") is None
    assert cache.get("sys2", "user", "model") == {"text": "new"}

    key = cache._make_key("sys2", "user", "model")
    ts, value = cache._cache[key]
    cache._cache[key] = (ts - 20, value)
    assert cache.get("sys2", "user", "model") is None


def test_prompt_compression_removes_extra_blanks_and_truncates():
    prompt = "第一行\n\n\n第二行\n" + ("x" * 50)
    compressed = compress_prompt(prompt, max_length=20)

    assert "\n\n\n" not in compressed
    assert compressed.endswith("...[截断]")
    assert len(compress_system_prompt("x" * 3000)) <= 1510
    assert len(compress_user_prompt("x" * 3000)) <= 1010


@pytest.mark.asyncio
async def test_cached_llm_call_reuses_response():
    cache = LLMResponseCache()
    calls = 0

    @cached_llm_call(cache)
    async def chat(*, system_prompt, user_prompt, model):
        nonlocal calls
        calls += 1
        return {"content": user_prompt}

    first = await chat(system_prompt="sys", user_prompt="hello", model="m")
    second = await chat(system_prompt="sys", user_prompt="hello", model="m")

    assert first == second
    assert calls == 1


@pytest.mark.asyncio
async def test_batch_llm_call_preserves_order_and_model():
    class FakeLLM:
        async def chat(self, *, system_prompt, user_prompt, model):
            await asyncio.sleep(0)
            return f"{model}:{system_prompt}:{user_prompt}"

    results = await batch_llm_call(
        FakeLLM(),
        [("s1", "u1"), ("s2", "u2")],
        model="m",
        max_concurrent=1,
    )

    assert results == ["m:s1:u1", "m:s2:u2"]


def test_token_usage_stats_tracks_cost_and_cache_hits():
    stats = TokenUsageStats()
    stats.record(1000, 500)
    stats.record(1000, 500, cached=True)
    summary = stats.summary()

    assert summary["total_calls"] == 1
    assert summary["cache_hits"] == 1
    assert summary["total_input_tokens"] == 1000
    assert summary["total_output_tokens"] == 500
    assert summary["estimated_cost_usd"] == pytest.approx(0.002)
