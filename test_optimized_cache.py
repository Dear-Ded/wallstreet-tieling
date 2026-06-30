#!/usr/bin/env python3
"""
测试脚本：验证增强版缓存模块
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_optimized_cache():
    """测试增强版缓存"""
    print("=" * 60)
    print("测试：增强版缓存模块")
    print("=" * 60)
    
    try:
        from core.optimized_cache import OptimizedQueryCache, GlobalCacheManager, cached
        
        # 测试1：基本功能
        print("\n测试1：基本缓存功能")
        cache = OptimizedQueryCache(max_size=10, default_ttl=60)
        
        async def mock_fetcher(target, query_type):
            print(f"  [fetcher] 查询 {target} 的 {query_type}")
            return f"{target}-{query_type}-result"
        
        # 第一次查询（未命中）
        result1 = await cache.get_or_fetch("公司A", "工商信息", mock_fetcher)
        print(f"  结果1：{result1}")
        print(f"  统计：{cache.stats}")
        
        # 第二次查询（命中）
        result2 = await cache.get_or_fetch("公司A", "工商信息", mock_fetcher)
        print(f"  结果2：{result2}")
        print(f"  统计：{cache.stats}")
        
        assert result1 == result2, "缓存命中失败"
        assert cache.stats["hits"] == 1, "命中次数错误"
        print("✅ 测试1通过")
        
        # 测试2：LRU淘汰
        print("\n测试2：LRU淘汰")
        for i in range(15):
            await cache.get_or_fetch(f"公司{i}", "工商信息", mock_fetcher)
        
        print(f"  当前大小：{len(cache._cache)}")
        print(f"  淘汰次数：{cache.stats['evictions']}")
        assert len(cache._cache) <= 10, "LRU淘汰失败"
        print("✅ 测试2通过")
        
        # 测试3：缓存统计
        print("\n测试3：缓存统计")
        cache.print_stats()
        print("✅ 测试3通过")
        
        # 测试4：自动缓存装饰器
        print("\n测试4：自动缓存装饰器")
        
        call_count = 0
        
        @cached(target_param="company", query_type_param="info_type", ttl=60)
        async def get_company_info(company: str, info_type: str):
            nonlocal call_count
            call_count += 1
            return f"{company}-{info_type}-data"
        
        # 第一次调用
        r1 = await get_company_info("公司A", "工商信息")
        print(f"  结果1：{r1}")
        print(f"  调用次数：{call_count}")
        
        # 第二次调用（应该命中缓存）
        r2 = await get_company_info("公司A", "工商信息")
        print(f"  结果2：{r2}")
        print(f"  调用次数：{call_count}")
        
        assert r1 == r2, "缓存装饰器失败"
        assert call_count == 1, "装饰器缓存未命中"
        print("✅ 测试4通过")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！增强版缓存模块工作正常")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🧪 开始测试增强版缓存模块...\n")
    
    result = asyncio.run(test_optimized_cache())
    
    if not result:
        sys.exit(1)
