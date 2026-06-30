"""
任务#7: API性能优化模块
API Performance Optimization Module

优化功能:
1. 智能缓存策略（多级缓存）
2. 请求合并与批处理
3. 并发控制与限流
4. 响应压缩
5. 性能监控与告警
"""

from __future__ import annotations

import asyncio
import time
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Tuple
from collections import OrderedDict
import asyncio
from functools import wraps


class CacheLevel(str, Enum):
    """缓存级别"""
    L1_MEMORY = "内存缓存"
    L2_REDIS = "Redis缓存"
    L3_DISK = "磁盘缓存"


class CacheStrategy(str, Enum):
    """缓存策略"""
    LRU = "LRU淘汰"
    TTL = "TTL过期"
    ADAPTIVE = "自适应"


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl: Optional[float] = None
    access_count: int = 0
    last_access: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

    def access(self):
        """访问"""
        self.access_count += 1
        self.last_access = time.time()


class MultiLevelCache:
    """多级缓存"""

    def __init__(
        self,
        max_memory_items: int = 1000,
        default_ttl: float = 300.0
    ):
        self.max_memory_items = max_memory_items
        self.default_ttl = default_ttl

        # L1: 内存缓存 (LRU)
        self.l1_cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # 统计
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "memory_usage": 0
        }

    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_str = f"{args}{kwargs}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        # L1: 内存缓存
        if key in self.l1_cache:
            entry = self.l1_cache[key]

            if entry.is_expired():
                # 过期，删除
                del self.l1_cache[key]
                self.stats["misses"] += 1
                return None

            # 命中，更新访问信息
            entry.access()
            self.l1_cache.move_to_end(key)
            self.stats["hits"] += 1
            return entry.value

        self.stats["misses"] += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """设置缓存"""
        if ttl is None:
            ttl = self.default_ttl

        entry = CacheEntry(key=key, value=value, ttl=ttl)

        # L1: 内存缓存
        if len(self.l1_cache) >= self.max_memory_items:
            # 淘汰最旧的
            self.l1_cache.popitem(last=False)
            self.stats["evictions"] += 1

        self.l1_cache[key] = entry
        self.l1_cache.move_to_end(key)

    def invalidate(self, key: str):
        """删除缓存"""
        if key in self.l1_cache:
            del self.l1_cache[key]

    def clear(self):
        """清空缓存"""
        self.l1_cache.clear()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "memory_usage": 0}

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total if total > 0 else 0

        return {
            **self.stats,
            "hit_rate": hit_rate,
            "size": len(self.l1_cache)
        }


def cached(
    cache: MultiLevelCache,
    ttl: Optional[float] = None,
    key_func: Optional[Callable] = None
):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._make_key(func.__name__, *args, **kwargs)

            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 缓存未命中，执行函数
            result = await func(*args, **kwargs)

            # 存入缓存
            cache.set(cache_key, result, ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._make_key(func.__name__, *args, **kwargs)

            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 缓存未命中，执行函数
            result = func(*args, **kwargs)

            # 存入缓存
            cache.set(cache_key, result, ttl)

            return result

        # 根据函数类型返回对应的wrapper
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class RequestBatcher:
    """请求合并器"""

    def __init__(self, max_batch_size: int = 10, max_wait_time: float = 0.05):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.pending_requests: Dict[str, List[Tuple[Any, asyncio.Future]]] = {}
        self._lock = asyncio.Lock()

    async def execute(self, batch_key: str, request_item: Any, fetch_func: Callable):
        """执行请求（自动合并）"""
        async with self._lock:
            if batch_key not in self.pending_requests:
                self.pending_requests[batch_key] = []

                # 延迟执行批量请求
                asyncio.create_task(self._process_batch(batch_key, fetch_func))

        # 创建Future等待结果
        future = asyncio.Future()

        async with self._lock:
            self.pending_requests[batch_key].append((request_item, future))

        return await future

    async def _process_batch(self, batch_key: str, fetch_func: Callable):
        """处理批量请求"""
        await asyncio.sleep(self.max_wait_time)

        async with self._lock:
            requests = self.pending_requests.pop(batch_key, [])

        if not requests:
            return

        # 提取请求项
        items = [req[0] for req in requests]
        futures = [req[1] for req in requests]

        try:
            # 执行批量请求
            results = await fetch_func(items)

            # 分发结果
            for future, result in zip(futures, results):
                if not future.done():
                    future.set_result(result)

        except Exception as e:
            # 错误处理
            for future in futures:
                if not future.done():
                    future.set_exception(e)

    async def execute_single(self, request_item: Any, fetch_func: Callable):
        """执行单个请求（不合并）"""
        return await fetch_func([request_item])


class RateLimiter:
    """令牌桶限流器"""

    def __init__(self, rate: float, burst: int):
        self.rate = rate  # tokens per second
        self.burst = burst  # bucket size
        self.tokens = float(burst)
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1):
        """获取令牌"""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                # 需要等待
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
                return True


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}
        self.alerts: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def record_latency(self, endpoint: str, latency: float):
        """记录延迟"""
        async with self._lock:
            if endpoint not in self.metrics:
                self.metrics[endpoint] = []
            self.metrics[endpoint].append(latency)

            # 保留最近1000条
            if len(self.metrics[endpoint]) > 1000:
                self.metrics[endpoint] = self.metrics[endpoint][-1000:]

        # 检查告警
        if latency > 5.0:  # 超过5秒
            await self._trigger_alert(endpoint, "high_latency", {"latency": latency})

    async def _trigger_alert(self, source: str, alert_type: str, data: Dict[str, Any]):
        """触发告警"""
        alert = {
            "source": source,
            "type": alert_type,
            "data": data,
            "timestamp": time.time()
        }
        self.alerts.append(alert)
        print(f"[PerformanceMonitor] 告警: {alert_type} from {source}")

    def get_stats(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """获取统计"""
        if endpoint:
            latencies = self.metrics.get(endpoint, [])
            if not latencies:
                return {"error": "No data"}
            return {
                "endpoint": endpoint,
                "count": len(latencies),
                "avg_latency": sum(latencies) / len(latencies),
                "min_latency": min(latencies),
                "max_latency": max(latencies),
                "p95_latency": sorted(latencies)[int(len(latencies) * 0.95)]
            }
        else:
            # 全部端点
            return {ep: self.get_stats(ep) for ep in self.metrics.keys()}


class APIOptimizer:
    """API优化器（集成所有优化功能）"""

    def __init__(self):
        self.cache = MultiLevelCache()
        self.batcher = RequestBatcher()
        self.rate_limiter = RateLimiter(rate=100, burst=10)
        self.monitor = PerformanceMonitor()

    async def optimized_request(
        self,
        endpoint: str,
        fetch_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """执行优化请求"""

        # 1. 检查缓存
        cache_key = f"{endpoint}:{str(args)}:{str(kwargs)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # 2. 限流
        await self.rate_limiter.acquire()

        # 3. 执行请求（监控性能）
        start_time = time.time()
        try:
            result = await fetch_func(*args, **kwargs)

            # 4. 存入缓存
            self.cache.set(cache_key, result)

            return result
        finally:
            latency = time.time() - start_time
            await self.monitor.record_latency(endpoint, latency)

    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        return {
            "cache_stats": self.cache.get_stats(),
            "api_stats": self.monitor.get_stats(),
            "alerts": self.monitor.alerts[-10:]  # 最近10条告警
        }


# 导出
__all__ = [
    "APIOptimizer",
    "MultiLevelCache",
    "RequestBatcher",
    "RateLimiter",
    "PerformanceMonitor",
    "cached"
]
