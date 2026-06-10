#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 平台无关能力接口
引擎核心通过这三个抽象接口与外部世界交互，不依赖任何具体平台。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    """模型调用结果 — 平台无关的标准化格式"""
    ok: bool
    text: str
    model: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    error: str = ""


@dataclass
class ToolResult:
    """工具/搜索调用结果"""
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    error: str = ""


# ═══════════════════════════════════════════════════════════
#  抽象接口
# ═══════════════════════════════════════════════════════════

class LLMProvider(ABC):
    """模型调用接口 — 引擎不管你怎么调模型，只管要结果

    适配器职责:
        - 构建请求 payload（格式因平台而异）
        - 处理认证（API Key / Token / MCP）
        - 解析响应（提取 text + tokens + latency）
        - 处理重试 / 超时 / 熔断（平台层面）
    """

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
        agent_name: str = "",
    ) -> LLMResponse:
        """发送一次对话请求，返回标准化的 LLMResponse"""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """当前默认模型名"""
        ...


class ToolProvider(ABC):
    """工具/数据源接口 — 引擎只管'我要查什么'，不管'用什么工具查'

    适配器职责:
        - 维护可用工具注册表
        - 处理工具发现/降级（如 tyc-mcp 不可用时用 WebSearch）
        - 格式化查询为工具能接受的参数
        - 解析结果为标准化的 ToolResult
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        tool_type: str,  # "company_search" | "financial" | "risk" | "people" | "web"
        **kwargs,
    ) -> ToolResult:
        """执行一次搜索/查询"""
        ...

    @abstractmethod
    def available_tools(self) -> set[str]:
        """返回当前可用的工具类型集合"""
        ...


class OutputProvider(ABC):
    """输出接口 — 引擎只管'我要写文件'，不管写到哪里

    适配器职责:
        - 确定输出目录（文件系统 / 云存储 / 内存）
        - 处理编码和格式
        - 返回可访问的文件路径或 URI
    """

    @abstractmethod
    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        """写入内容到文件系统，返回路径"""
        ...
