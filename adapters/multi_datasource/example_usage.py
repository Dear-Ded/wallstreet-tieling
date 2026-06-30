"""
完整使用示例 - 系统启动 → 初始化 → 随时调用检索
"""

import asyncio
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# =============================================================================
# 示例 1: 最简用法（一行代码调用）
# =============================================================================

async def example_1_basic():
    """最简用法：一行代码调用"""
    print("\n" + "="*60)
    print("示例 1: 最简用法")
    print("="*60)
    
    # 初始化（只需一次）
    from multi_datasource import SearchEngine
    await SearchEngine.initialize("datasources.yaml")
    
    # 一行代码查询
    result = await SearchEngine.search("jsonplaceholder", "posts/1")
    
    # 处理结果
    if result.is_success:
        print(f"\n✅ 查询成功!")
        print(f"   数据源: {result.source_name}")
        print(f"   查询耗时: {result.query_time:.3f}秒")
        print(f"   数据: {result.data}")
    else:
        print(f"\n❌ 查询失败: {result.error}")

# =============================================================================
# 示例 2: 同步调用（适合不支持 async 的环境）
# =============================================================================

def example_2_sync():
    """同步调用示例"""
    print("\n" + "="*60)
    print("示例 2: 同步调用")
    print("="*60)
    
    from multi_datasource import SearchEngine
    
    # 同步调用（内部会自动处理事件循环）
    result = SearchEngine.search_sync("jsonplaceholder", "posts/2")
    
    if result.is_success:
        print(f"\n✅ 查询成功!")
        print(f"   数据: {result.data}")
    else:
        print(f"\n❌ 查询失败: {result.error}")

# =============================================================================
# 示例 3: 缓存加速
# =============================================================================

async def example_3_cache():
    """缓存加速示例"""
    print("\n" + "="*60)
    print("示例 3: 缓存加速")
    print("="*60)
    
    from multi_datasource import SearchEngine
    
    # 第一次查询（实际查询）
    start = asyncio.get_event_loop().time()
    result1 = await SearchEngine.search("jsonplaceholder", "posts/1", use_cache=True)
    time1 = asyncio.get_event_loop().time() - start
    print(f"\n第一次查询: {time1:.3f}秒")
    
    # 第二次查询（缓存命中）
    start = asyncio.get_event_loop().time()
    result2 = await SearchEngine.search("jsonplaceholder", "posts/1", use_cache=True)
    time2 = asyncio.get_event_loop().time() - start
    print(f"第二次查询 (缓存): {time2:.3f}秒")
    print(f"缓存加速: {time1/time2:.1f}x")
    
    # 查看缓存统计
    stats = SearchEngine.cache_stats()
    print(f"\n缓存统计:")
    print(f"   命中: {stats['hits']}")
    print(f"   未命中: {stats['misses']}")
    print(f"   命中率: {stats['hit_rate']:.2%}")

# =============================================================================
# 示例 4: 查询所有数据源
# =============================================================================

async def example_4_query_all():
    """查询所有数据源示例"""
    print("\n" + "="*60)
    print("示例 4: 查询所有数据源")
    print("="*60)
    
    from multi_datasource import SearchEngine, ResultAggregator
    
    # 查询所有数据源
    aggregated = await SearchEngine.search_all("posts/1", concurrency=5)
    
    print(f"\n查询结果:")
    print(f"   成功: {aggregated.successful_count}")
    print(f"   失败: {aggregated.failed_count}")
    print(f"   成功率: {aggregated.success_rate:.2%}")
    print(f"   总耗时: {aggregated.total_time:.3f}秒")
    
    # 聚合结果
    if aggregated.successful_count > 0:
        all_data = ResultAggregator.merge_list(aggregated.results)
        print(f"\n聚合数据: {len(all_data)} 条")

# =============================================================================
# 示例 5: 在现有系统中集成
# =============================================================================

async def example_5_integration():
    """在现有系统中集成示例"""
    print("\n" + "="*60)
    print("示例 5: 在现有系统中集成")
    print("="*60)
    
    from multi_datasource import SearchEngine
    
    # 假设这是一个现有的信息检索系统
    class MyInformationSystem:
        def __init__(self):
            self.name = "我的信息检索系统"
        
        async def search(self, query: str, sources: list = None):
            """
            系统统一的搜索接口
            
            上层调用只需关心这个接口，无需关心底层数据源差异
            """
            if sources:
                # 查询指定的数据源
                results = []
                for source in sources:
                    result = await SearchEngine.search(source, query)
                    results.append(result)
                return results
            else:
                # 查询所有数据源
                return await SearchEngine.search_all(query)
    
    # 使用现有系统
    system = MyInformationSystem()
    
    print("\n[集成示例] 在现有系统中使用:")
    
    # 使用系统的统一接口查询
    results = await system.search("posts/1", sources=["jsonplaceholder"])
    
    for result in results:
        if result.is_success:
            print(f"   ✅ {result.source_name}: 查询成功")
        else:
            print(f"   ❌ {result.source_name}: {result.error}")

# =============================================================================
# 示例 6: 系统生命周期管理
# =============================================================================

async def example_6_lifecycle():
    """系统生命周期管理示例"""
    print("\n" + "="*60)
    print("示例 6: 系统生命周期管理")
    print("="*60)
    
    from multi_datasource import SearchEngine
    
    # =========================================================================
    # 阶段 1: 系统启动
    # =========================================================================
    print("\n[阶段 1] 系统启动...")
    await SearchEngine.initialize("datasources.yaml")
    print(f"   ✅ 搜索引擎初始化完成")
    print(f"   已加载数据源: {SearchEngine.list_sources()}")
    
    # =========================================================================
    # 阶段 2: 正常运行（随时调用）
    # =========================================================================
    print("\n[阶段 2] 系统正常运行...")
    
    # 模拟多次查询
    for i in range(3):
        print(f"\n   查询 {i+1}:")
        result = await SearchEngine.search("jsonplaceholder", f"posts/{i+1}")
        if result.is_success:
            print(f"     ✅ 成功 (耗时 {result.query_time:.3f}秒)")
        else:
            print(f"     ❌ 失败: {result.error}")
    
    # =========================================================================
    # 阶段 3: 查看系统状态
    # =========================================================================
    print("\n[阶段 3] 系统状态:")
    print(f"   缓存统计: {SearchEngine.cache_stats()}")
    print(f"   健康状态: {SearchEngine.health_check()}")
    
    # =========================================================================
    # 阶段 4: 系统关闭
    # =========================================================================
    print("\n[阶段 4] 系统关闭...")
    await SearchEngine.close()
    print("   ✅ 搜索引擎已关闭")

# =============================================================================
# 主程序
# =============================================================================

async def main():
    """主程序"""
    print("\n" + "🚀" * 30)
    print("多数据源模块 - 标准内置组件演示")
    print("🚀" * 30)
    
    try:
        # 运行示例（可以选择运行哪个示例）
        await example_1_basic()          # 最简用法
        await example_3_cache()          # 缓存加速
        await example_4_query_all()      # 查询所有数据源
        await example_5_integration()    # 在现有系统中集成
        await example_6_lifecycle()      # 系统生命周期管理
        
        # 同步调用示例（单独运行）
        # example_2_sync()
        
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 确保关闭
        from multi_datasource import SearchEngine
        try:
            await SearchEngine.close()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
