#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — CLI 独立适配器
不需要 WorkBuddy — 纯命令行运行，直接调 HTTP API。
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

from adapters._base import OpenAICompatibleLLM
from core.interfaces import LLMProvider, ToolProvider, ToolResult, OutputProvider, PlatformAdapter


class StandaloneLLM(OpenAICompatibleLLM):
    """CLI 模式 — 环境变量配置 API"""

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model: str | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("WALLSTREET_API_KEY",
                     os.environ.get("OPENAI_API_KEY",
                     os.environ.get("DEEPSEEK_API_KEY", ""))),
            api_base=api_base or os.environ.get("WALLSTREET_API_BASE",
                      os.environ.get("OPENAI_BASE_URL",
                      "https://api.deepseek.com/v1")),
            model=model or os.environ.get("WALLSTREET_MODEL", "deepseek-chat"),
            timeout=int(os.environ.get("WALLSTREET_TIMEOUT", "300")),
        )


class NoopTools(ToolProvider):
    def available_tools(self): return {"web"}
    async def search(self, query, tool_type, **kwargs):
        return ToolResult(ok=True, data={"query": query, "tool_type": tool_type,
                         "hint": "use_llm_knowledge"})


class StandaloneOutput(OutputProvider):
    def __init__(self, output_dir: str = ""):
        self._root = Path(output_dir) if output_dir else Path.cwd() / "output"
        self._root.mkdir(exist_ok=True)

    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        target_dir = self._root / subdir if subdir else self._root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


async def run_cli(company: str, *, mode: str = "standard", model: str | None = None):
    """CLI 一键尽调入口"""
    from core.engine import Engine

    adapter = PlatformAdapter(
        llm=StandaloneLLM(model=model),
        tools=NoopTools(),
        output=StandaloneOutput(),
    )
    engine = Engine(target=company, adapter=adapter, mode=mode, model=model)

    print(f"\n{'='*60}")
    print(f"  华尔街驻铁岭办事处 v4.0 — {company}")
    print(f"  模式: {mode} | 模型: {adapter.llm.default_model}")
    print(f"{'='*60}\n")

    result = await engine.run()
    ts = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r'[^\w\-]', '', company)
    path = adapter.output.write(result["report"], f"report-{slug}-{ts}.md")
    print(f"\n报告: {path} | 角色: {result['roles_activated']} | 分支: {len(result['branches_triggered'])}")
    return result


if __name__ == "__main__":
    company = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "测试公司"
    mode = __import__("sys").argv[2] if len(__import__("sys").argv) > 2 else "standard"
    asyncio.run(run_cli(company, mode=mode))
