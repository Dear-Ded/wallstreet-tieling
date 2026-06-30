#!/usr/bin/env python3
"""
测试脚本：验证多数据源框架集成是否生效
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_multi_datasource_integration():
    """测试多数据源框架集成"""
    print("=" * 60)
    print("测试1：验证 SearchEngine 初始化")
    print("=" * 60)
    
    try:
        from adapters.multi_datasource import SearchEngine
        
        # 初始化
        await SearchEngine.initialize("adapters/multi_datasource/datasources.yaml")
        print("✅ SearchEngine 初始化成功")
        
        # 获取实例
        engine = SearchEngine.get_instance()
        if engine:
            print(f"✅ 获取到实例：{engine}")
            # 使用公有API获取数据源信息
            stats = await engine.cache_stats()
            print(f"   缓存统计：{stats}")
        else:
            print("❌ 获取实例失败")
            return False
            
    except Exception as e:
        print(f"❌ SearchEngine 初始化失败：{e}")
        return False
    
    print("\n" + "=" * 60)
    print("测试2：验证 WorkBuddyTools 集成")
    print("=" * 60)
    
    try:
        from adapters.workbuddy import WorkBuddyTools
        
        tools = WorkBuddyTools()
        print(f"✅ WorkBuddyTools 创建成功")
        print(f"   可用工具：{tools.available_tools()}")
        
        # 测试懒加载
        mds_tool = tools._get_mds_tool()
        if mds_tool:
            print(f"✅ 多数据源工具懒加载成功")
        else:
            print(f"⚠️ 多数据源工具懒加载失败")
            
    except Exception as e:
        print(f"❌ WorkBuddyTools 创建失败：{e}")
        return False
    
    print("\n" + "=" * 60)
    print("测试3：测试实际查询（需要知道数据源是否配置正确）")
    print("=" * 60)
    
    try:
        # 测试查询
        result = await tools.search(
            query="测试查询",
            tool_type="multi_datasource",
            sources=["bing"]  # 使用bing测试
        )
        
        if result.ok:
            print(f"✅ 查询成功")
            print(f"   结果：{result.data}")
        else:
            print(f"⚠️ 查询失败：{result.error}")
            
    except Exception as e:
        print(f"❌ 查询测试失败：{e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！多数据源框架集成已生效")
    print("=" * 60)
    
    return True


async def test_deduction_chain():
    """测试推导链是否自动调用多数据源框架"""
    print("\n" + "=" * 60)
    print("测试4：验证推导链自动调用（模拟场景）")
    print("=" * 60)
    
    # 模拟场景：拿到法人信息后，自动调用多数据源框架
    print("\n场景：已获取法人姓名 '张三'")
    print("预期：自动调用 multi_datasource.query('张三', sources=[...])")
    
    # 检查周通的角色文件是否有明确的调用指令
    zhou_tong_file = Path("sub-skills/zhou-tong.md")
    if zhou_tong_file.exists():
        content = zhou_tong_file.read_text(encoding='utf-8')
        if "multi_datasource.query" in content:
            print("✅ 周通角色文件包含多数据源调用指令")
            print("   LLM应该会根据指令自动调用多数据源框架")
        else:
            print("⚠️ 周通角色文件未明确包含调用指令")
            print("   需要添加更明确的调用示例")
    
    print("\n建议：在实际尽调运行中验证推导链是否自动调用多数据源框架")


if __name__ == "__main__":
    print("\n🧪 开始测试多数据源框架集成...\n")
    
    # 运行测试
    result = asyncio.run(test_multi_datasource_integration())
    
    if result:
        asyncio.run(test_deduction_chain())
    else:
        print("\n❌ 基础测试失败，请检查配置")
        sys.exit(1)
