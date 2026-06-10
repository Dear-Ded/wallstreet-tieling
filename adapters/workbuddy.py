#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — WorkBuddy 平台适配器
在 WorkBuddy 环境中运行: 使用内置模型调用 + MCP 工具 + Skill 工具。
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from core.interfaces import LLMProvider, LLMResponse, ToolProvider, ToolResult, OutputProvider


# ═══════════════════════════════════════════════════════════
#  WorkBuddy LLM 适配器
# ═══════════════════════════════════════════════════════════

class WorkBuddyLLM(LLMProvider):
    """WorkBuddy 环境下的模型调用 — 走内置模型（积分/API Key）"""

    def __init__(self, model: str | None = None):
        import api.config as cfg
        cfg.reload_config()
        self._api_key = cfg.API_KEY
        self._api_base = cfg.API_BASE
        self._model = model or os.environ.get("WALLSTREET_MODEL", "deepseek-chat")
        self._timeout = int(os.environ.get("WALLSTREET_TIMEOUT", "300"))

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt, user_prompt, *, model=None,
                   temperature=0.3, max_tokens=8192, agent_name="") -> LLMResponse:
        """调用 OpenAI 兼容 API"""
        import aiohttp
        model = model or self._model
        t0 = time.monotonic()

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._api_base.rstrip('/')}/chat/completions"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    elapsed = (time.monotonic() - t0) * 1000
                    if resp.status != 200:
                        return LLMResponse(ok=False, text="", model=model,
                                          latency_ms=int(elapsed), error=f"HTTP {resp.status}")
                    data = await resp.json()
                    choice = data.get("choices", [{}])[0]
                    text = choice.get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    return LLMResponse(
                        ok=True, text=text, model=model,
                        tokens_used=usage.get("total_tokens", 0),
                        latency_ms=int(elapsed),
                    )
        except asyncio.TimeoutError:
            return LLMResponse(ok=False, text="", model=model, error="timeout")
        except Exception as e:
            return LLMResponse(ok=False, text="", model=model, error=str(e))


# ═══════════════════════════════════════════════════════════
#  WorkBuddy 工具适配器
# ═══════════════════════════════════════════════════════════

class WorkBuddyTools(ToolProvider):
    """WorkBuddy 环境下的工具调用 — MCP + Skill"""

    def __init__(self):
        self._available = {"web"}  # 基础 WebSearch 始终可用

    def available_tools(self) -> set[str]:
        return self._available

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        """在 WorkBuddy 环境中搜索 — 委托给宿主执行"""
        # WorkBuddy 环境中，实际的搜索由宿主 Agent 通过 MCP/Skill 完成。
        # 引擎提示系统提示词会引导宿主选择合适的工具。
        # 这里返回一个占位结果，表示"请宿主决定用什么工具查"。
        return ToolResult(
            ok=True,
            data={"query": query, "tool_type": tool_type, "hint": "delegated_to_host"},
            sources=[f"wb:{tool_type}"],
        )


# ═══════════════════════════════════════════════════════════
#  WorkBuddy 输出适配器
# ═══════════════════════════════════════════════════════════

class WorkBuddyOutput(OutputProvider):
    """WorkBuddy 环境下的文件输出 — 写入 skill 的 output/ 目录"""

    def __init__(self):
        self._root = Path(__file__).resolve().parent.parent / "output"
        self._root.mkdir(exist_ok=True)

    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        target_dir = self._root / subdir if subdir else self._root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
