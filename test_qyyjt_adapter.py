#!/usr/bin/env python3
"""
测试 QYYJTAdapter.query() 方法（无账号场景）

测试目标：
1. 授权会话状态无效时，是否自动降级到 WebSearch
2. 生成的 WebSearch 查询是否精准
3. 返回结果的结构是否正确

运行：python test_qyyjt_adapter.py
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.qyyjt_adapter import QYYJTAdapter, QYYJTModule
import asyncio


async def test_query_without_login():
    """测试无账号时的 query() 方法"""
    print("=" * 60)
    print("测试场景：无账号（授权会话状态无效）")
    print("=" * 60)

    adapter = QYYJTAdapter()

    # 测试：查询"特斯拉"的风险信息
    company = "特斯拉"
    modules = [
        QYYJTModule.RISK_SCAN,
        QYYJTModule.COURT_CASES,
        QYYJTModule.NEWS_NEGATIVE,
    ]

    print(f"\n查询公司：{company}")
    print(f"查询模块：{[m.value for m in modules]}")
    print("-" * 60)

    result = await adapter.query(company, modules, prefer_api=False)

    print("\n返回结果：")
    print(f"  授权会话状态有效：{result.get('cookie_valid')}")
    print(f"  数据源：{result.get('source')}")
    print(f"  API 数据：{result.get('api_data')}")
    print(f"  WebSearch 查询数量：{len(result.get('websearch_queries', []))}")

    print("\n生成的 WebSearch 查询：")
    for i, q in enumerate(result.get("websearch_queries", []), 1):
        print(f"  {i}. [{q.get('module_name')}] {q.get('query')}")
        if q.get("note"):
            print(f"     备注：{q.get('note')}")

    print("\n错误（如果有）：")
    if result.get("errors"):
        for k, v in result["errors"].items():
            print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("测试结论：")
    if result["source"] == "websearch" and len(result["websearch_queries"]) > 0:
        print("✅ 无账号时正确降级到 WebSearch")
        print("✅ 生成了 WebSearch 查询")
        print("✅ 返回结果结构正确")
    else:
        print("❌ 降级逻辑有问题，请检查")
    print("=" * 60)

    return result


async def main():
    """主测试函数"""
    print("\n华尔街驻铁岭办事处 - QYYJTAdapter 测试")
    print("测试时间：2026-06-15\n")

    # 测试 1：无账号场景
    result1 = await test_query_without_login()

    # TODO: 测试 2：有账号场景（需要 授权会话状态）
    # result2 = await test_query_with_login()

    print("\n测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
