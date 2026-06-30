"""
测试脚本：验证周通是否真的调用了多数据源
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.engine import Engine


async def test_zhou_tong_multi_datasource():
    """测试周通是否真的调用了多数据源"""
    print("🧪 测试：周通是否真的调用了多数据源")
    print("=" * 60)
    
    # 创建引擎（周通角色）
    # 注意：create_engine() 的第一个参数是公司名
    # mode 参数可能用于指定角色（需要确认）
    engine = Engine.create_engine(
        "特斯拉（上海）有限公司",
        model="deepseek-chat",
        mode="zhou-tong",  # 可能用于指定角色
    )
    
    # 模拟推导链拿到法人信息
    print("\n📋 模拟推导链：拿到法人信息")
    print("  法人：X（模拟）")
    print("  根据强制指令，应该立即调用 multi_datasource...")
    
    # 执行分析（触发 Agent 生成工具调用）
    print("\n🔍 执行分析（触发 Agent 生成工具调用）...")
    try:
        result = await engine.run()
        print(f"\n✅ 分析完成")
        print(f"  结果类型：{type(result)}")
        print(f"  结果预览：{str(result)[:200]}...")
        
        # 检查日志（WorkBuddyTools.search() 是否真的被调用）
        print("\n⚠️ 需要检查日志：")
        print("  1. 搜索代码目录中的 '🔥 强制调用多数据源' 日志")
        print("  2. 或者检查 SearchEngineTool 是否被调用")
        
    except Exception as e:
        print(f"\n❌ 查询失败：{e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🧪 测试完成")


if __name__ == "__main__":
    asyncio.run(test_zhou_tong_multi_datasource())
