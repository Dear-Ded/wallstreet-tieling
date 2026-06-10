#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 查询缓存
Phase 1 内同一 (target, query_type) 只查一次，消除重复 API 调用。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Coroutine


class QueryCache:
    """会话内查询缓存 — 生命周期 = 单次 Engine.run()"""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0

    def key(self, target: str, query_type: str) -> str:
        return hashlib.md5(f"{target}:{query_type}".encode()).hexdigest()[:16]

    async def get_or_fetch(
        self, target: str, query_type: str,
        fetcher: Callable[[str, str], Coroutine[Any, Any, Any]],
        ttl: float = 300.0,
    ) -> Any:
        """缓存命中返回缓存, 否则调用 fetcher 并缓存结果"""
        k = self.key(target, query_type)
        if k in self._store:
            ts, val = self._store[k]
            if time.time() - ts < ttl:
                self._hits += 1
                return val

        result = await fetcher(target, query_type)
        self._store[k] = (time.time(), result)
        self._misses += 1
        return result

    @property
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses,
                "total": self._hits + self._misses,
                "hit_rate": self._hits / max(self._hits + self._misses, 1)}


# ═══════════════════════════════════════════════════════════
#  全局缓存实例 (跨会话共享 — 供 OrgMemory 阶段使用)
# ═══════════════════════════════════════════════════════════

class GlobalCache:
    """跨会话缓存 — 同一个模型/同一个查询可跨次复用 (可选)"""
    _instance: "GlobalCache | None" = None

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}

    @classmethod
    def get(cls) -> "GlobalCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def key(self, model: str, target: str, query_type: str) -> str:
        raw = f"{model}:{target}:{query_type}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def get(self, model: str, target: str, query_type: str, ttl: float = 3600.0) -> Any | None:
        k = self.key(model, target, query_type)
        if k in self._store:
            ts, val = self._store[k]
            if time.time() - ts < ttl:
                return val
        return None

    def set(self, model: str, target: str, query_type: str, value: Any) -> None:
        k = self.key(model, target, query_type)
        self._store[k] = (time.time(), value)
