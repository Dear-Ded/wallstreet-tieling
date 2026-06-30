#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 - 集成多数据源工具"""
from __future__ import annotations

import os
import logging
from pathlib import Path

from adapters._base import OpenAICompatibleLLM
from core.connector_registry import ConnectorRegistry
from core.development_requirements import build_development_requirements_board
from core.interfaces import LLMProvider, ToolProvider, ToolResult, OutputProvider, PlatformAdapter
from core.release_contract import release_readiness_brief

logger = logging.getLogger("wst.workbuddy")


# =============================================================================
#  WorkBuddy LLM
# =============================================================================

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


# =============================================================================
#  WorkBuddy 工具（集成多数据源）
# =============================================================================

class WorkBuddyTools(ToolProvider):
    """WorkBuddy 工具 — Host MCP / WebSearch / 多数据源 / 产品目录"""

    def __init__(self):
        self._available = {
            "web",
            "host_mcp",
            "multi_datasource",
            "mds",
            "default_public_intel",
            "connector_catalog",
            "release_readiness",
            "development_requirements",
        }
        self._mds_tool = None  # MultiDataSourceTool 实例（懒加载）
        self._default_public_tool = None
        self._mds_config = "adapters/multi_datasource/datasources.yaml"

    def _get_mds_tool(self):
        """懒加载多数据源工具"""
        if self._mds_tool is None:
            try:
                from adapters.multi_datasource_tool import SearchEngineTool
                self._mds_tool = SearchEngineTool(config_path=self._mds_config)
                print("✅ 搜索引擎工具已加载")
            except Exception as e:
                print(f"⚠️ 搜索引擎工具加载失败: {e}")
                return None
        return self._mds_tool

    def available_tools(self) -> set[str]:
        """返回可用工具列表"""
        return self._available

    def _get_default_public_tool(self):
        """懒加载默认公开情报工具。"""
        if self._default_public_tool is None:
            try:
                from adapters.default_public_intel_tool import DefaultPublicIntelTool
                self._default_public_tool = DefaultPublicIntelTool()
            except Exception as e:
                logger.warning("默认公开情报工具加载失败: %s", e)
                return None
        return self._default_public_tool

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        """
        执行工具查询
        
        Args:
            query: 查询字符串
            tool_type: 工具类型（"web" / "multi_datasource" / "mds"）
            **kwargs: 其他参数
            
        Returns:
            ToolResult 包含查询结果
        """
        if tool_type == "connector_catalog":
            return ToolResult(
                ok=True,
                data=ConnectorRegistry().product_catalog(),
                sources=["workbuddy:connector_catalog"],
            )

        if tool_type == "release_readiness":
            return ToolResult(
                ok=True,
                data=release_readiness_brief(),
                sources=["workbuddy:release_readiness"],
            )

        if tool_type == "development_requirements":
            return ToolResult(
                ok=True,
                data=build_development_requirements_board(),
                sources=["workbuddy:development_requirements"],
            )

        # WebSearch / Host MCP 工具（委托给 WorkBuddy 宿主执行）
        if tool_type in {"web", "host_mcp"}:
            return ToolResult(
                ok=True,
                data={"query": query, "tool_type": tool_type,
                      "hint": "delegated_to_host",
                      "fallback": "host_unavailable: use local datasource tools or evidence-gap output"},
                sources=[f"wb:{tool_type}"],
            )

        if tool_type == "default_public_intel":
            public_tool = self._get_default_public_tool()
            if public_tool is None:
                return ToolResult(
                    ok=False,
                    error="默认公开情报工具未加载",
                    data={"query": query, "tool_type": tool_type},
                    sources=["workbuddy:default_public_intel:error"],
                )
            return await public_tool.search(query, tool_type, **kwargs)
        
        # 多数据源工具（本地执行）
        elif tool_type in ("multi_datasource", "mds"):
            mds_tool = self._get_mds_tool()
            if mds_tool is None:
                return ToolResult(
                    ok=False,
                    error="多数据源工具未加载",
                    data={"query": query, "tool_type": tool_type}
                )
            
            # 执行查询
            sources = kwargs.get("sources")  # 指定数据源列表
            use_cache = kwargs.get("use_cache", True)
            
            # 🔥 强制调用逻辑（不依赖 LLM 生成工具调用）
            # 如果 query 包含法人/实控人/关系人/公开联系方式等关键词，强制调用多数据源
            force_keywords = ["法人", "实控人", "实际控制人", "股东", "公开联系方式", "电话", "地址"]
            query_lower = query.lower()
            if any(kw in query_lower for kw in force_keywords):
                print(f"🔥 强制调用多数据源：query='{query}'")
                logger.info("强制调用多数据源：query='%s'", query)
            
            if sources and isinstance(sources, list):
                # 查询指定的数据源
                result = await mds_tool.search(query, tool_type, sources=sources, use_cache=use_cache)
            else:
                # 查询所有数据源
                result = await mds_tool.search(query, tool_type, use_cache=use_cache)
            
            return result
        
        # 未知工具类型
        else:
            return ToolResult(
                ok=False,
                error=f"未知工具类型: {tool_type}",
                data={"query": query, "tool_type": tool_type}
            )


# =============================================================================
#  WorkBuddy 输出
# =============================================================================

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


# =============================================================================
#  工厂函数
# =============================================================================

def create_adapter(model: str | None = None) -> PlatformAdapter:
    return PlatformAdapter(
        llm=WorkBuddyLLM(model=model),
        tools=WorkBuddyTools(),
        output=WorkBuddyOutput(),
    )
