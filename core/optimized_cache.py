#!/usr/bin/env python3
"""
增强版缓存模块 - 优化性能
支持：LRU淘汰、缓存预热、持久化、详细统计
"""
from __future__ import annotations

import hashlib
import json
import time
import pickle
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional
from collections import OrderedDict


class OptimizedQueryCache:
    """
    增强版查询缓存
    
    特性：
    1. LRU淘汰策略（防止内存溢出）
    2. 详细缓存统计（命中率、miss率、淘汰次数）
    3. 缓存预热（启动时加载热点数据）
    4. 可配置TTL（不同查询类型不同TTL）
    5. 缓存持久化（可选，保存到磁盘）
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 300.0,
        persist_path: Optional[str] = None
    ):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数（LRU淘汰）
            default_ttl: 默认TTL（秒）
            persist_path: 持久化文件路径（可选）
        """
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._persist_path = Path(persist_path) if persist_path else None
        
        # 统计信息
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        # 加载持久化缓存
        if self._persist_path and self._persist_path.exists():
            self._load_from_disk()
    
    def _make_key(self, target: str, query_type: str, **kwargs) -> str:
        """生成缓存键（稳定）"""
        content = {
            "target": target,
            "query_type": query_type,
            **kwargs
        }
        return hashlib.md5(
            json.dumps(content, sort_keys=True).encode('utf-8')
        ).hexdigest()[:16]
    
    async def get_or_fetch(
        self,
        target: str,
        query_type: str,
        fetcher: Callable[[str, str], Coroutine[Any, Any, Any]],
        ttl: Optional[float] = None,
        **kwargs
    ) -> Any:
        """
        获取缓存或执行查询
        
        Args:
            target: 查询目标（如企业名）
            query_type: 查询类型（如"工商信息"）
            fetcher: 查询函数
            ttl: TTL（秒），None使用默认TTL
            **kwargs: 其他参数（会纳入缓存键）
            
        Returns:
            查询结果
        """
        k = self._make_key(target, query_type, **kwargs)
        ttl = ttl or self._default_ttl
        
        # 检查缓存
        if k in self._cache:
            ts, val = self._cache[k]
            if time.time() - ts < ttl:
                # 缓存命中
                self._hits += 1
                # LRU：移动到末尾（最新）
                self._cache.move_to_end(k)
                return val
            else:
                # 缓存过期
                del self._cache[k]
        
        # 缓存未命中，执行查询
        self._misses += 1
        result = await fetcher(target, query_type, **kwargs)
        
        # 存入缓存
        self._cache[k] = (time.time(), result)
        self._cache.move_to_end(k)  # LRU
        
        # LRU淘汰
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # 删除最旧的
            self._evictions += 1
        
        return result
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def remove(self, target: str, query_type: str, **kwargs):
        """删除指定缓存"""
        k = self._make_key(target, query_type, **kwargs)
        if k in self._cache:
            del self._cache[k]
    
    @property
    def stats(self) -> dict:
        """获取缓存统计"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": self._hits / max(total, 1),
            "miss_rate": self._misses / max(total, 1),
            "evictions": self._evictions,
            "size": len(self._cache),
            "max_size": self._max_size,
        }
    
    def print_stats(self):
        """打印缓存统计"""
        stats = self.stats
        print("=" * 60)
        print("缓存统计")
        print("=" * 60)
        print(f"命中次数: {stats['hits']}")
        print(f"未命中次数: {stats['misses']}")
        print(f"总查询次数: {stats['total']}")
        print(f"命中率: {stats['hit_rate']:.2%}")
        print(f"淘汰次数: {stats['evictions']}")
        print(f"当前大小: {stats['size']}/{stats['max_size']}")
        print("=" * 60)
    
    def warm_up(self, warm_data: list[tuple[str, str, Any]]):
        """
        缓存预热
        
        Args:
            warm_data: [(target, query_type, result), ...]
        """
        for target, query_type, result in warm_data:
            k = self._make_key(target, query_type)
            self._cache[k] = (time.time(), result)
            self._cache.move_to_end(k)
        
        # 如果超过max_size，淘汰最旧的
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        
        print(f"✅ 缓存预热完成：{len(warm_data)} 条数据已加载")
    
    def save_to_disk(self):
        """保存缓存到磁盘"""
        if not self._persist_path:
            return
        
        try:
            with open(self._persist_path, 'wb') as f:
                pickle.dump(dict(self._cache), f)
            print(f"✅ 缓存已保存到：{self._persist_path}")
        except Exception as e:
            print(f"❌ 缓存保存失败：{e}")
    
    def _load_from_disk(self):
        """从磁盘加载缓存"""
        if not self._persist_path or not self._persist_path.exists():
            return
        
        try:
            with open(self._persist_path, 'rb') as f:
                data = pickle.load(f)
                self._cache = OrderedDict(data)
            print(f"✅ 缓存已从磁盘加载：{len(self._cache)} 条数据")
        except Exception as e:
            print(f"❌ 缓存加载失败：{e}")


# =============================================================================
# 全局缓存管理器（单例）
# =============================================================================

class GlobalCacheManager:
    """
    全局缓存管理器（单例模式）
    
    管理所有模块的缓存，提供统一的缓存接口
    """
    
    _instance: Optional["GlobalCacheManager"] = None
    
    def __init__(self):
        self._caches: dict[str, OptimizedQueryCache] = {}
        self._default_ttls = {
            "工商信息": 3600,      # 1小时
            "风险扫描": 1800,      # 30分钟
            "财务报表": 7200,      # 2小时
            "舆情监控": 600,       # 10分钟
            "default": 300        # 5分钟
        }
    
    @classmethod
    def get_instance(cls) -> "GlobalCacheManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_cache(self, module_name: str) -> OptimizedQueryCache:
        """获取指定模块的缓存"""
        if module_name not in self._caches:
            self._caches[module_name] = OptimizedQueryCache(
                max_size=1000,
                default_ttl=self._default_ttls["default"]
            )
        return self._caches[module_name]
    
    def set_ttl(self, query_type: str, ttl: float):
        """设置指定查询类型的TTL"""
        self._default_ttls[query_type] = ttl
    
    def get_all_stats(self) -> dict:
        """获取所有模块的缓存统计"""
        return {
            module: cache.stats
            for module, cache in self._caches.items()
        }
    
    def print_all_stats(self):
        """打印所有模块的缓存统计"""
        print("\n" + "=" * 60)
        print("全局缓存统计")
        print("=" * 60)
        for module, cache in self._caches.items():
            stats = cache.stats
            print(f"\n模块: {module}")
            print(f"  命中率: {stats['hit_rate']:.2%}")
            print(f"  大小: {stats['size']}/{stats['max_size']}")
            print(f"  淘汰次数: {stats['evictions']}")
        print("=" * 60)
    
    def clear_all(self):
        """清空所有缓存"""
        for cache in self._caches.values():
            cache.clear()
        print("✅ 所有缓存已清空")
    
    def save_all(self):
        """保存所有缓存到磁盘"""
        for module, cache in self._caches.items():
            cache.save_to_disk()
        print("✅ 所有缓存已保存")


# =============================================================================
# 装饰器：自动缓存
# =============================================================================

def cached(
    target_param: str = "target",
    query_type_param: str = "query_type",
    ttl: Optional[float] = None,
    cache_name: str = "default"
):
    """
    缓存装饰器
    
    用法：
    @cached(target_param="company_name", query_type_param="info_type", ttl=3600)
    async def get_company_info(company_name: str, info_type: str):
        ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 获取target和query_type
            if target_param in kwargs:
                target = kwargs[target_param]
            else:
                target = args[0]  # 假设第一个参数是target
            
            if query_type_param in kwargs:
                query_type = kwargs[query_type_param]
            else:
                query_type = func.__name__  # 使用函数名作为query_type
            
            # 获取缓存
            cache_manager = GlobalCacheManager.get_instance()
            cache = cache_manager.get_cache(cache_name)
            
            # 定义fetcher
            async def fetcher(t, qt, **kw):
                return await func(*args, **kwargs)
            
            # 获取或查询
            return await cache.get_or_fetch(
                target=target,
                query_type=query_type,
                fetcher=fetcher,
                ttl=ttl
            )
        return wrapper
    return decorator
