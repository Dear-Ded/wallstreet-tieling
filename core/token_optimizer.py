#!/usr/bin/env python3
"""
LLM Token优化模块
策略：
1. 响应缓存（相同prompt不重复调用）
2. Prompt压缩（移除冗余信息）
3. 批量调用（合并多个查询）
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional, Callable, Coroutine
from functools import wraps


# =============================================================================
# 1. LLM响应缓存
# =============================================================================

class LLMResponseCache:
    """
    LLM响应缓存
    
    缓存相同prompt的LLM响应，避免重复调用
    """
    
    def __init__(self, max_size: int = 500, ttl: float = 3600):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: TTL（秒）
        """
        self._cache: dict[str, tuple[float, Any]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0
    
    def _make_key(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        **kwargs
    ) -> str:
        """生成缓存键"""
        content = {
            "system": system_prompt,
            "user": user_prompt,
            "model": model,
            **kwargs
        }
        return hashlib.md5(
            json.dumps(content, sort_keys=True).encode('utf-8')
        ).hexdigest()[:16]
    
    def get(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        **kwargs
    ) -> Optional[Any]:
        """获取缓存的响应"""
        k = self._make_key(system_prompt, user_prompt, model, **kwargs)
        
        if k in self._cache:
            ts, val = self._cache[k]
            if time.time() - ts < self._ttl:
                self._hits += 1
                return val
            else:
                # 过期
                del self._cache[k]
        
        self._misses += 1
        return None
    
    def set(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        response: Any,
        **kwargs
    ):
        """缓存响应"""
        k = self._make_key(system_prompt, user_prompt, model, **kwargs)
        
        if len(self._cache) >= self._max_size:
            # 简单淘汰：删除第一个
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        
        self._cache[k] = (time.time(), response)
    
    @property
    def stats(self) -> dict:
        """获取统计"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": self._hits / max(total, 1),
            "size": len(self._cache),
            "max_size": self._max_size,
        }
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# =============================================================================
# 2. Prompt压缩
# =============================================================================

def compress_prompt(prompt: str, max_length: int = 2000) -> str:
    """
    压缩prompt
    
    策略：
    1. 移除多余空行
    2. 移除重复内容
    3. 截断到最大长度
    
    Args:
        prompt: 原始prompt
        max_length: 最大长度（字符）
        
    Returns:
        压缩后的prompt
    """
    if not prompt:
        return prompt
    
    # 1. 移除多余空行
    lines = prompt.split('\n')
    compressed_lines = []
    prev_empty = False
    
    for line in lines:
        if line.strip() == '':
            if not prev_empty:
                compressed_lines.append(line)
            prev_empty = True
        else:
            compressed_lines.append(line)
            prev_empty = False
    
    result = '\n'.join(compressed_lines)
    
    # 2. 截断到最大长度
    if len(result) > max_length:
        result = result[:max_length] + "\n...[截断]"
    
    return result


def compress_system_prompt(system_prompt: str) -> str:
    """
    压缩system prompt（更激进）
    
    策略：
    1. 保留角色定义（前200字）
    2. 保留核心指令（中间部分）
    3. 移除示例（如果有）
    """
    # 简单实现：截断到1500字
    return compress_prompt(system_prompt, max_length=1500)


def compress_user_prompt(user_prompt: str) -> str:
    """
    压缩user prompt
    
    策略：
    1. 保留问题/指令（前500字）
    2. 压缩上下文（中间部分）
    3. 保留关键数据（后200字）
    """
    # 简单实现：截断到1000字
    return compress_prompt(user_prompt, max_length=1000)


# =============================================================================
# 3. 装饰器：自动缓存LLM调用
# =============================================================================

def cached_llm_call(cache: LLMResponseCache):
    """
    装饰器：自动缓存LLM调用
    
    用法：
    @cached_llm_call(cache)
    async def chat(system_prompt, user_prompt, model, ...):
        ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 提取参数
            system_prompt = kwargs.get('system_prompt', '')
            user_prompt = kwargs.get('user_prompt', '')
            model = kwargs.get('model', 'default')
            
            # 检查缓存
            cached_response = cache.get(system_prompt, user_prompt, model)
            if cached_response:
                return cached_response
            
            # 调用原函数
            response = await func(*args, **kwargs)
            
            # 缓存响应
            cache.set(system_prompt, user_prompt, model, response)
            
            return response
        return wrapper
    return decorator


# =============================================================================
# 4. 批量LLM调用
# =============================================================================

async def batch_llm_call(
    llm_client,
    prompts: list[tuple[str, str]],  # [(system_prompt, user_prompt), ...]
    model: str = "default",
    max_concurrent: int = 5
) -> list[Any]:
    """
    批量LLM调用（并发）
    
    Args:
        llm_client: LLM客户端
        prompts: prompt列表
        model: 模型名
        max_concurrent: 最大并发数
        
    Returns:
        响应列表
    """
    import asyncio
    
    # 创建信号量限制并发
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def call_one(system_prompt: str, user_prompt: str):
        async with semaphore:
            return await llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model
            )
    
    # 并发调用
    tasks = [
        call_one(system, user)
        for system, user in prompts
    ]
    
    return await asyncio.gather(*tasks)


# =============================================================================
# 5. Token使用统计
# =============================================================================

class TokenUsageStats:
    """Token使用统计"""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self.cache_hits = 0
    
    def record(self, input_tokens: int, output_tokens: int, cached: bool = False):
        """记录一次LLM调用"""
        if cached:
            self.cache_hits += 1
        else:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.call_count += 1
    
    def summary(self) -> dict:
        """生成统计摘要"""
        return {
            "total_calls": self.call_count,
            "cache_hits": self.cache_hits,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": self._estimate_cost(),
        }
    
    def _estimate_cost(self) -> float:
        """估算成本（USD）"""
        # 假设：input $0.001/1K tokens, output $0.002/1K tokens
        input_cost = (self.total_input_tokens / 1000) * 0.001
        output_cost = (self.total_output_tokens / 1000) * 0.002
        return input_cost + output_cost
    
    def print_summary(self):
        """打印统计摘要"""
        stats = self.summary()
        print("=" * 60)
        print("Token使用统计")
        print("=" * 60)
        print(f"总调用次数: {stats['total_calls']}")
        print(f"缓存命中次数: {stats['cache_hits']}")
        print(f"总输入Token: {stats['total_input_tokens']:,}")
        print(f"总输出Token: {stats['total_output_tokens']:,}")
        print(f"估算成本: ${stats['estimated_cost_usd']:.4f}")
        print("=" * 60)


# =============================================================================
# 全局实例
# =============================================================================

# 全局LLM响应缓存
global_llm_cache = LLMResponseCache(max_size=500, ttl=3600)

# 全局Token统计
global_token_stats = TokenUsageStats()
