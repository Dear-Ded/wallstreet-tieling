#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0"""
from __future__ import annotations

import os
from pathlib import Path

from adapters._base import OpenAICompatibleLLM
from core.interfaces import LLMProvider, ToolProvider, ToolResult, OutputProvider, PlatformAdapter


# ═══════════════════════════════════════════════════════════
#  WorkBuddy LLM
# ═══════════════════════════════════════════════════════════

class WorkBuddyLLM(OpenAICompatibleLLM):
    """WorkBuddy 内置模型 — 走 config 模块 (DEEPSEEK_API_KEY / OPENAI_API_KEY)"""

    def __init__(self, model: str | None = None):
        import api.config as cfg
        cfg.reload_config()
        super().__init__(
            api_key=cfg.API_KEY,
            api_base=cfg.API_BASE,
            model=model or os.environ.get("WALLSTREET_MODEL", "deepseek-chat"),
            timeout=int(os.environ.get("WALLSTREET_TIMEOUT", "300")),
        )


# ═══════════════════════════════════════════════════════════
#  WorkBuddy 工具
# ═══════════════════════════════════════════════════════════

class WorkBuddyTools(ToolProvider):
    """WorkBuddy 工具 — MCP 优先 → WebSearch → LLM 知识兜底"""

    def __init__(self):
        self._available = {"web"}

    def available_tools(self) -> set[str]:
        return self._available

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        """委托给 WorkBuddy 宿主执行，引擎提示词引导宿主选工具。
        宿主不可用时返回占位提示。
        """
        return ToolResult(
            ok=True,
            data={"query": query, "tool_type": tool_type,
                  "hint": "delegated_to_host",
                  "fallback": "host_unavailable: use WebSearch or LLM knowledge"},
            sources=[f"wb:{tool_type}"],
        )


# ═══════════════════════════════════════════════════════════
#  WorkBuddy 输出
# ═══════════════════════════════════════════════════════════

class WorkBuddyOutput(OutputProvider):
    """WorkBuddy 输出 — 写入 skill 的 output/ 目录"""

    def __init__(self):
        self._root = Path(__file__).resolve().parent.parent / "output"
        self._root.mkdir(exist_ok=True)

    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        target_dir = self._root / subdir if subdir else self._root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


# ═══════════════════════════════════════════════════════════
#  工厂函数
# ═══════════════════════════════════════════════════════════

def create_adapter(model: str | None = None) -> PlatformAdapter:
    return PlatformAdapter(
        llm=WorkBuddyLLM(model=model),
        tools=WorkBuddyTools(),
        output=WorkBuddyOutput(),
    )
