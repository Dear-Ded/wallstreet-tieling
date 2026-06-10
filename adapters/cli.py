#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 独立 CLI 适配器
不需要 WorkBuddy — 纯命令行运行，直接调 API。
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from core.interfaces import LLMProvider, LLMResponse, ToolProvider, ToolResult, OutputProvider


class StandaloneLLM(LLMProvider):
    """独立 CLI 模式 — 直接调 HTTP API（OpenAI 兼容格式）"""

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model: str | None = None):
        self._api_key = api_key or os.environ.get("WALLSTREET_API_KEY",
                         os.environ.get("OPENAI_API_KEY",
                         os.environ.get("DEEPSEEK_API_KEY", "")))
        self._api_base = api_base or os.environ.get("WALLSTREET_API_BASE",
                          os.environ.get("OPENAI_BASE_URL",
                          "https://api.deepseek.com/v1"))
        self._model = model or os.environ.get("WALLSTREET_MODEL", "deepseek-chat")
        self._timeout = int(os.environ.get("WALLSTREET_TIMEOUT", "300"))

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt, user_prompt, *, model=None,
                   temperature=0.3, max_tokens=8192, agent_name="") -> LLMResponse:
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
                async with session.post(url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout)) as resp:
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


class StandaloneOutput(OutputProvider):
    """独立 CLI 模式 — 输出到本地文件系统"""

    def __init__(self, output_dir: str = ""):
        self._root = Path(output_dir) if output_dir else Path.cwd() / "output"
        self._root.mkdir(exist_ok=True)

    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        target_dir = self._root / subdir if subdir else self._root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


# ═══════════════════════════════════════════════════════════
#  一键启动
# ═══════════════════════════════════════════════════════════

async def run_cli(company: str, *, mode: str = "standard", model: str | None = None):
    """CLI 一键尽调入口"""
    from core.engine import Engine
    from core.interfaces import PlatformAdapter

    llm = StandaloneLLM(model=model)
    output = StandaloneOutput()

    # CLI 模式下工具返回占位结果（提示引擎用模型能力）
    class NoopTools(ToolProvider):
        def available_tools(self): return {"web"}
        async def search(self, query, tool_type, **kwargs):
            return ToolResult(ok=True, data={"query": query, "tool_type": tool_type, "hint": "use_llm_knowledge"})

    adapter = PlatformAdapter(llm=llm, tools=NoopTools(), output=output)
    engine = Engine(target=company, adapter=adapter, mode=mode, model=model)

    print(f"\n{'='*60}")
    print(f"  华尔街驻铁岭办事处 v4.0 — {company}")
    print(f"  模式: {mode} | 模型: {llm.default_model}")
    print(f"{'='*60}\n")

    result = await engine.run()

    ts = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r'[^\w\-]', '', company)
    path = output.write(result["report"], f"report-{slug}-{ts}.md")

    print(f"\n报告已保存: {path}")
    print(f"角色激活: {result['roles_activated']}")
    print(f"分支触发: {len(result['branches_triggered'])} 个")

    return result


if __name__ == "__main__":
    import sys, re
    company = sys.argv[1] if len(sys.argv) > 1 else "测试公司"
    mode = sys.argv[2] if len(sys.argv) > 2 else "standard"
    asyncio.run(run_cli(company, mode=mode))
