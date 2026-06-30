#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0"""
from __future__ import annotations

import asyncio
import re
import time

from core.interfaces import LLMProvider, LLMResponse


class OpenAICompatibleLLM(LLMProvider):
    """OpenAI 兼容格式的 LLM 调用基类 — WorkBuddy/CLI/任何兼容 API 共用"""

    def __init__(self, api_key: str, api_base: str, model: str, timeout: int = 300):
        self._api_key = api_key
        self._api_base = api_base
        self._model = model
        self._timeout = timeout

    @staticmethod
    def _safe_error_text(text: str, limit: int = 500) -> str:
        """Keep transient provider errors useful without leaking credentials."""
        redacted = re.sub(
            r"(?i)(authorization|api[-_ ]?key|token|cookie|secret)\s*[:=]\s*['\"]?[^'\"\s,;}]+",
            r"\1=[REDACTED]",
            text or "",
        )
        return redacted.strip().replace("\r", " ").replace("\n", " ")[:limit]

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
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    elapsed = (time.monotonic() - t0) * 1000
                    if resp.status != 200:
                        try:
                            body = self._safe_error_text(await resp.text())
                        except Exception:
                            body = ""
                        suffix = f": {body}" if body else ""
                        return LLMResponse(ok=False, text="", model=model,
                                          latency_ms=int(elapsed), error=f"HTTP {resp.status}{suffix}")
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
