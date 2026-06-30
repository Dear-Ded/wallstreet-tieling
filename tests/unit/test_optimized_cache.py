#!/usr/bin/env python3
"""Tests for optimized query cache."""
from __future__ import annotations

import pickle

import pytest

from core.optimized_cache import GlobalCacheManager, OptimizedQueryCache, cached


@pytest.mark.asyncio
async def test_get_or_fetch_caches_hits_and_expires():
    cache = OptimizedQueryCache(max_size=2, default_ttl=10)
    calls = 0

    async def fetcher(target, query_type, **kwargs):
        nonlocal calls
        calls += 1
        return {"target": target, "query_type": query_type, **kwargs}

    first = await cache.get_or_fetch("abc", "工商信息", fetcher, region="ln")
    second = await cache.get_or_fetch("abc", "工商信息", fetcher, region="ln")
    assert first == second
    assert calls == 1
    assert cache.stats["hits"] == 1

    key = cache._make_key("abc", "工商信息", region="ln")
    ts, value = cache._cache[key]
    cache._cache[key] = (ts - 20, value)
    third = await cache.get_or_fetch("abc", "工商信息", fetcher, ttl=1, region="ln")

    assert third == first
    assert calls == 2
    assert cache.stats["misses"] == 2


@pytest.mark.asyncio
async def test_lru_eviction_and_remove():
    cache = OptimizedQueryCache(max_size=1)

    async def fetcher(target, query_type, **kwargs):
        return target

    await cache.get_or_fetch("a", "type", fetcher)
    await cache.get_or_fetch("b", "type", fetcher)

    assert cache.stats["evictions"] == 1
    assert cache.stats["size"] == 1
    cache.remove("b", "type")
    assert cache.stats["size"] == 0


def test_warm_up_and_persistence(tmp_path):
    persist_path = tmp_path / "cache.pkl"
    cache = OptimizedQueryCache(max_size=2, persist_path=str(persist_path))

    cache.warm_up([
        ("a", "工商信息", {"a": 1}),
        ("b", "工商信息", {"b": 2}),
        ("c", "工商信息", {"c": 3}),
    ])
    cache.save_to_disk()

    assert cache.stats["size"] == 2
    assert persist_path.exists()
    loaded = pickle.loads(persist_path.read_bytes())
    assert len(loaded) == 2

    reloaded = OptimizedQueryCache(persist_path=str(persist_path))
    assert reloaded.stats["size"] == 2


def test_global_cache_manager_reuses_named_cache():
    GlobalCacheManager._instance = None
    manager = GlobalCacheManager.get_instance()
    cache_a = manager.get_cache("module-a")
    cache_b = manager.get_cache("module-a")

    assert cache_a is cache_b
    manager.set_ttl("工商信息", 123)
    assert manager._default_ttls["工商信息"] == 123
    assert "module-a" in manager.get_all_stats()


@pytest.mark.asyncio
async def test_cached_decorator_uses_named_cache():
    GlobalCacheManager._instance = None
    calls = 0

    @cached(target_param="company", query_type_param="info_type", cache_name="decorator")
    async def fetch(company: str, info_type: str):
        nonlocal calls
        calls += 1
        return {"company": company, "info_type": info_type}

    first = await fetch(company="abc", info_type="工商信息")
    second = await fetch(company="abc", info_type="工商信息")

    assert first == second
    assert calls == 1
