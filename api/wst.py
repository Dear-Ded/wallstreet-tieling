#!/usr/bin/env python3
"""华尔街驻铁岭办事处 — CLI 入口 v0.5.0
真并发 Agent 架构 · 拟人化角色 · No Fabrication 六层防御

用法:
  python api/wst.py --target "腾讯科技(深圳)有限公司"
  python api/wst.py --target "字节跳动" --mode deep
  python api/wst.py --target "某小微公司" --mode sme
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import config
from .orchestrator import Orchestrator
from .agent_registry import AgentRegistry
from .personality import get_personality

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("wst")


def main():
    parser = argparse.ArgumentParser(
        description="华尔街驻铁岭办事处 · 多Agent尽调编排器 v0.5.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python api/wst.py --target "腾讯科技(深圳)有限公司"
  python api/wst.py --target "字节跳动" --mode deep
  python api/wst.py --target "某小微公司" --mode sme
  python api/wst.py --target "测试公司" --dry-run

环境变量:
  DEEPSEEK_API_KEY      DeepSeek API Key (优先)
  OPENAI_API_KEY        OpenAI API Key (fallback)
  DEEPSEEK_BASE_URL     API 端点

模式:
  simple    简单查询: 仅张铁柱
  standard  标准尽调: 张+李+王+赵+马 → 郑+吴 → 刘 [默认]
  deep      深度尽调: 全角色 + 条件分支
  sme       中小企业: 张+李+赵 → 郑 → 刘
  people    人员背调: 马+周 → 郑
  report    报告生成: 仅刘+颜
""",
    )
    parser.add_argument("--target", "-t", required=True, help="尽调目标企业名称")
    parser.add_argument("--model", "-m", default=config.DEFAULT_MODEL, help="模型名称")
    parser.add_argument("--mode", default="standard",
                        choices=["simple", "standard", "deep", "sme", "people", "report"])
    parser.add_argument("--roles", default=None, help="手动指定角色ID，逗号分隔")
    parser.add_argument("--concurrency", "-c", type=int, default=config.DEFAULT_CONCURRENCY)
    parser.add_argument("--max-retries", "-r", type=int, default=3)
    parser.add_argument("--output", "-o", default=None, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="干运行")

    args = parser.parse_args()

    # 解析手动角色
    roles_list = None
    if args.roles:
        roles_list = [r.strip() for r in args.roles.split(",") if r.strip()]
        invalid = [r for r in roles_list if r not in config.ROLE_FILE_MAP]
        if invalid:
            print(f"错误: 无效的角色ID: {invalid}")
            print(f"有效角色: {', '.join(config.ROLE_FILE_MAP.keys())}")
            sys.exit(1)

    # API Key 检查
    if not config.get_api_key():
        print("错误: 未设置 API Key。请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量。")
        sys.exit(1)

    if args.dry_run:
        template = config.MODE_TEMPLATES.get(args.mode, config.MODE_TEMPLATES["standard"])
        all_roles = roles_list if roles_list else (
            template.get("phase1", []) + template.get("phase2", []) + template.get("phase3", [])
        )
        print(f"\n── 目标: {args.target}")
        print(f"── 模式: {args.mode} ({template.get('desc', '')})")
        print(f"── 模型: {args.model}")
        print(f"── 激活角色: {', '.join(all_roles) if all_roles else '(无)'}\n")

        for phase in [1, 2, 3]:
            phase_roles = template.get(f"phase{phase}", [])
            if not phase_roles:
                continue
            print(f"Phase {phase} ({len(phase_roles)}个Agent):")
            for rid in phase_roles:
                p = get_personality(rid)
                print(f"  {p.display_name}({p.nickname}) — {p.background[:60]}...")
            print()

        print("(干运行模式 —— 未执行 API 调用)")
        return

    asyncio.run(run(
        target=args.target,
        model=args.model,
        mode=args.mode,
        concurrency=args.concurrency,
        max_retries=args.max_retries,
        roles=roles_list,
        output_dir=args.output,
    ))


async def run(target: str, model: str, mode: str,
              concurrency: int, max_retries: int,
              roles: list[str] | None, output_dir: str | None):
    """执行尽调"""
    orch = Orchestrator(
        target=target, model=model, mode=mode,
        concurrency=concurrency, max_retries=max_retries,
        roles=roles,
    )
    result = await orch.orchestrate(output_dir=output_dir)
    return result


if __name__ == "__main__":
    main()
