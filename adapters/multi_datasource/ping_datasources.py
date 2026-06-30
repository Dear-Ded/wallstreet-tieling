#!/usr/bin/env python3
"""
多数据源可达性检测脚本

使用方法:
    python -m adapters.multi_datasource.ping_datasources [--config CONFIG] [--fix] [--verbose]

参数:
    --config CONFIG   配置文件路径 (默认: datasources.yaml)
    --fix                 自动禁用不可达的数据源 (修改配置文件)
    --verbose             显示详细日志
    --timeout TIMEOUT    检测超时时间 (秒, 默认: 5)

示例:
    # 检测可达性 (不修改配置)
    python -m adapters.multi_datasource.ping_datasources

    # 检测并自动禁用不可达数据源
    python -m adapters.multi_datasource.ping_datasources --fix

    # 使用自定义配置文件
    python -m adapters.multi_datasource.ping_datasources --config my_datasources.yaml --fix
"""
from __future__ import annotations

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.multi_datasource import DataSourceManager, ConfigError


async def main():
    parser = argparse.ArgumentParser(description="多数据源可达性检测脚本")
    parser.add_argument("--config", type=str, default="datasources.yaml",
                        help="配置文件路径 (默认: datasources.yaml)")
    parser.add_argument("--fix", action="store_true",
                        help="自动禁用不可达的数据源 (修改配置文件)")
    parser.add_argument("--verbose", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--timeout", type=int, default=5,
                        help="检测超时时间 (秒, 默认: 5)")
    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("ping_datasources")

    # 检查配置文件
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return 1

    print("=" * 70)
    print(f"多数据源可达性检测")
    print(f"配置文件: {config_path}")
    print(f"自动修复: {'是' if args.fix else '否'}")
    print("=" * 70)

    try:
        # 加载配置
        manager = DataSourceManager()
        manager.config_path = config_path
        manager.load_config()

        # 设置检测超时
        for source_config in manager.config.sources:
            source_config.ping_timeout = args.timeout

        # 初始化数据源
        print("\n📋 初始化数据源...")
        manager.initialize_sources()

        # 检测可达性
        print("\n🔍 检测可达性...")
        connectivity_results = await manager.check_connectivity()

        # 打印报告
        print("\n" + "=" * 70)
        print("可达性检测报告")
        print("=" * 70)

        reachable_count = 0
        unreachable_count = 0

        for name, is_reachable in connectivity_results.items():
            source = manager.get_source(name)
            priority = source.config.priority if source else "?"
            enabled = "✅" if source and source.config.enabled else "❌"

            if is_reachable:
                print(f"  ✅ {name:<30} 优先级: {priority:<5} {enabled} 可达")
                reachable_count += 1
            else:
                print(f"  ❌ {name:<30} 优先级: {priority:<5} {enabled} 不可达")
                unreachable_count += 1

        print("-" * 70)
        print(f"总计: {len(connectivity_results)} 个 | "
              f"可达: {reachable_count} 个 | "
              f"不可达: {unreachable_count} 个")
        print("=" * 70)

        # 自动修复
        if args.fix and unreachable_count > 0:
            print("\n🔧 自动修复: 禁用不可达数据源...")
            _fix_config(config_path, connectivity_results)

        # 返回状态码
        if unreachable_count > 0:
            print(f"\n⚠️  有 {unreachable_count} 个数据源不可达")
            return 1
        else:
            print("\n✅ 所有数据源均可达")
            return 0

    except ConfigError as e:
        print(f"\n❌ 配置错误: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    finally:
        # 清理资源
        if 'manager' in locals():
            await manager.close()


def _fix_config(config_path: Path, results: dict) -> None:
    """
    修复配置文件: 禁用不可达的数据源

    Args:
        config_path: 配置文件路径
        results: 数据源名称 -> 是否可达
    """
    import yaml

    with open(config_path, 'r', encoding='utf-8') as f:
        config_dict = yaml.safe_load(f)

    fixed_count = 0

    for source in config_dict.get('sources', []):
        name = source.get('name', '')
        if name in results and not results[name]:
            if source.get('enabled', True):
                source['enabled'] = False
                fixed_count += 1
                print(f"  ✅ 已禁用: {name}")

    if fixed_count > 0:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, allow_unicode=True, sort_keys=False)
        print(f"\n✅ 已修复 {fixed_count} 个数据源 (配置文件已更新)")
    else:
        print("\n✅ 没有需要修复的数据源")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
