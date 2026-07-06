#!/usr/bin/env python3
"""Tests for API optimization helpers."""
from __future__ import annotations

import asyncio

import pytest

from core.api_optimizer import APIOptimizer, MultiLevelCache, PerformanceMonitor, RateLimiter, RequestBatcher, cached


def test_cache_hit_miss_expiry_and_eviction():
    cache = MultiLevelCache(max_memory_items=2, default_ttl=10)

    assert cache.get("missing") is None
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1

    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.stats["evictions"] == 1

    cache.set("short", "value", ttl=1)
    cache.l1_cache["short"].created_at -= 2
    assert cache.get("short") is None

    stats = cache.get_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 3


def test_cached_decorator_reuses_sync_result():
    cache = MultiLevelCache()
    calls = 0

    @cached(cache)
    def fetch(value):
        nonlocal calls
        calls += 1
        return {"value": value}

    assert fetch("x") == {"value": "x"}
    assert fetch("x") == {"value": "x"}
    assert calls == 1


@pytest.mark.asyncio
async def test_cached_decorator_reuses_async_result():
    cache = MultiLevelCache()
    calls = 0

    @cached(cache, key_func=lambda value: f"fixed:{value}")
    async def fetch(value):
        nonlocal calls
        calls += 1
        return {"value": value}

    assert await fetch("x") == {"value": "x"}
    assert await fetch("x") == {"value": "x"}
    assert calls == 1


@pytest.mark.asyncio
async def test_request_batcher_groups_requests():
    batcher = RequestBatcher(max_wait_time=0.001)
    seen_batches = []

    async def fetch(items):
        seen_batches.append(list(items))
        return [f"result:{item}" for item in items]

    results = await asyncio.gather(
        batcher.execute("companies", "a", fetch),
        batcher.execute("companies", "b", fetch),
    )

    assert results == ["result:a", "result:b"]
    assert seen_batches == [["a", "b"]]


@pytest.mark.asyncio
async def test_rate_limiter_waits_when_bucket_is_empty(monkeypatch):
    limiter = RateLimiter(rate=2, burst=1)
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("core.api_optimizer.asyncio.sleep", fake_sleep)
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert sleeps == pytest.approx([0.5], abs=0.001)


@pytest.mark.asyncio
async def test_performance_monitor_records_stats_and_alerts():
    monitor = PerformanceMonitor()

    await monitor.record_latency("/search", 0.1)
    await monitor.record_latency("/search", 6.0)

    stats = monitor.get_stats("/search")
    assert stats["count"] == 2
    assert stats["max_latency"] == 6.0
    assert monitor.alerts[-1]["type"] == "high_latency"


@pytest.mark.asyncio
async def test_api_optimizer_caches_and_reports(monkeypatch):
    optimizer = APIOptimizer()
    calls = 0

    async def fetch(company):
        nonlocal calls
        calls += 1
        return {"company": company}

    async def no_wait(tokens=1):
        return True

    monkeypatch.setattr(optimizer.rate_limiter, "acquire", no_wait)

    first = await optimizer.optimized_request("/company", fetch, "abc")
    second = await optimizer.optimized_request("/company", fetch, "abc")
    report = optimizer.get_performance_report()

    assert first == second == {"company": "abc"}
    assert calls == 1
    assert report["cache_stats"]["hits"] == 1
    assert "/company" in report["api_stats"]
    assert report["alerts"] == optimizer.monitor.alerts[-10:]
