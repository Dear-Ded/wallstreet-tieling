#!/usr/bin/env python3
"""WorkBuddy adapter for desktop-agent runtime delivery."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from adapters._base import OpenAICompatibleLLM
from core.agent_tool_adapters import build_agent_tool_adapter_manifest
from core.connector_registry import ConnectorRegistry
from core.datasource_fixtures import build_datasource_fixture_pack
from core.development_requirements import build_development_requirements_board
from core.interfaces import OutputProvider, PlatformAdapter, ToolProvider, ToolResult
from core.investigation import build_investigation_packet
from core.one_click_defaults import resolve_one_click_retrieval_async
from core.release_contract import release_readiness_brief
from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture
from core.risk_graph_export import export_risk_graph

logger = logging.getLogger("wst.workbuddy")


class WorkBuddyLLM(OpenAICompatibleLLM):
    """WorkBuddy LLM wrapper using the repository config module."""

    def __init__(self, model: str | None = None):
        import api.config as cfg

        cfg.reload_config()
        super().__init__(
            api_key=cfg.API_KEY,
            api_base=cfg.API_BASE,
            model=model or os.environ.get("WALLSTREET_MODEL", "deepseek-chat"),
            timeout=int(os.environ.get("WALLSTREET_TIMEOUT", "300")),
        )


class WorkBuddyTools(ToolProvider):
    """Tool routing for WorkBuddy/OpenClaw/CodeBuddy expert-team hosts."""

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
            "agent_tool_adapters",
            "investigate_company",
            "due_diligence",
        }
        self._mds_tool = None
        self._default_public_tool = None
        self._mds_config = "adapters/multi_datasource/datasources.yaml"

    def available_tools(self) -> set[str]:
        return set(self._available)

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
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

        if tool_type == "agent_tool_adapters":
            return ToolResult(
                ok=True,
                data=build_agent_tool_adapter_manifest(),
                sources=["workbuddy:agent_tool_adapters"],
            )

        if tool_type in {"investigate_company", "due_diligence"}:
            return await self._investigate_company(query, tool_type, **kwargs)

        if tool_type in {"web", "host_mcp"}:
            return ToolResult(
                ok=True,
                data={
                    "query": query,
                    "tool_type": tool_type,
                    "hint": "delegated_to_host",
                    "fallback": "host_unavailable: use local datasource tools or evidence-gap output",
                },
                sources=[f"wb:{tool_type}"],
            )

        if tool_type == "default_public_intel":
            public_tool = self._get_default_public_tool()
            if public_tool is None:
                return ToolResult(
                    ok=False,
                    error="default_public_intel tool is not loaded",
                    data={"query": query, "tool_type": tool_type},
                    sources=["workbuddy:default_public_intel:error"],
                )
            return await public_tool.search(query, tool_type, **kwargs)

        if tool_type in {"multi_datasource", "mds"}:
            mds_tool = self._get_mds_tool()
            if mds_tool is None:
                return ToolResult(
                    ok=False,
                    error="multi_datasource tool is not loaded",
                    data={"query": query, "tool_type": tool_type},
                    sources=["workbuddy:multi_datasource:error"],
                )
            sources = kwargs.get("sources")
            use_cache = kwargs.get("use_cache", True)
            if sources and isinstance(sources, list):
                return await mds_tool.search(query, tool_type, sources=sources, use_cache=use_cache)
            return await mds_tool.search(query, tool_type, use_cache=use_cache)

        return ToolResult(
            ok=False,
            error=f"unknown tool_type: {tool_type}",
            data={"query": query, "tool_type": tool_type},
            sources=["workbuddy:unknown_tool"],
        )

    def _get_mds_tool(self):
        if self._mds_tool is None:
            try:
                from adapters.multi_datasource_tool import SearchEngineTool

                self._mds_tool = SearchEngineTool(config_path=self._mds_config)
            except Exception as exc:
                logger.warning("multi_datasource tool load failed: %s", exc)
                return None
        return self._mds_tool

    def _get_default_public_tool(self):
        if self._default_public_tool is None:
            try:
                from adapters.default_public_intel_tool import DefaultPublicIntelTool

                self._default_public_tool = DefaultPublicIntelTool()
            except Exception as exc:
                logger.warning("default_public_intel tool load failed: %s", exc)
                return None
        return self._default_public_tool

    async def _investigate_company(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        company = str(
            kwargs.get("company_name")
            or kwargs.get("company")
            or kwargs.get("name")
            or query
            or ""
        ).strip()
        if not company:
            return ToolResult(
                ok=False,
                error="company_name is required",
                data={"query": query, "tool_type": tool_type},
                sources=["workbuddy:investigate_company:validation"],
            )

        fixture_pack = bool(kwargs.get("fixture_pack", False))
        offline_fixture = bool(kwargs.get("offline_fixture", not fixture_pack))
        config_path = str(kwargs.get("config") or "")
        if sum(bool(item) for item in (fixture_pack, offline_fixture, config_path)) > 1:
            return ToolResult(
                ok=False,
                error="config, offline_fixture, and fixture_pack are mutually exclusive",
                data={"company": company, "tool_type": tool_type},
                sources=["workbuddy:investigate_company:validation"],
            )

        try:
            selected = await self._resolve_investigation_sources(
                company=company,
                fixture_pack=fixture_pack,
                offline_fixture=offline_fixture,
                config_path=config_path,
                fanout_rounds=_clamped_int(kwargs, "fanout_rounds", 1, 0, 3),
            )
            result = await RiskDiscoveryPipeline().run(
                company,
                records=selected["records"],
                search_engine=selected["search_engine"],
                store_path=kwargs.get("store") or None,
                existing_plan=selected["existing_plan"],
                retrieval_concurrency=_clamped_int(kwargs, "retrieval_concurrency", 4, 1, 20),
                fanout_rounds=selected["fanout_rounds"],
                max_fanout_tasks=_clamped_int(kwargs, "max_fanout_tasks", 24, 0, 80),
                query_timeout_seconds=_clamped_float(kwargs, "query_timeout_seconds", 20.0, 0.1, 120.0),
            )
            packet = build_investigation_packet(
                export_risk_graph(result).to_dict(),
                input_text=company,
                mode=str(kwargs.get("mode") or kwargs.get("depth") or "standard"),
            ).to_dict()
            return ToolResult(
                ok=True,
                data=packet,
                sources=["workbuddy:investigate_company"],
            )
        except Exception as exc:
            logger.exception("WorkBuddy investigate_company failed")
            return ToolResult(
                ok=False,
                error=str(exc),
                data={"company": company, "tool_type": tool_type},
                sources=["workbuddy:investigate_company:error"],
            )

    async def _resolve_investigation_sources(
        self,
        *,
        company: str,
        fixture_pack: bool,
        offline_fixture: bool,
        config_path: str,
        fanout_rounds: int,
    ) -> dict[str, Any]:
        records = None
        search_engine = None
        if fixture_pack:
            records = build_datasource_fixture_pack(company).all_records()
        elif offline_fixture:
            records = offline_enforcement_fixture(company)
        elif config_path:
            from adapters.multi_datasource import SearchEngine

            await SearchEngine.initialize(config_path)
            search_engine = SearchEngine

        selected = await resolve_one_click_retrieval_async(
            company=company,
            records=records,
            search_engine=search_engine,
            existing_plan=None,
            fanout_rounds=fanout_rounds,
            default_enabled=not bool(config_path or records),
        )
        return {
            "records": selected.records,
            "search_engine": selected.search_engine,
            "existing_plan": selected.existing_plan,
            "fanout_rounds": selected.fanout_rounds,
        }


class WorkBuddyOutput(OutputProvider):
    """Write WorkBuddy output files under the repository output directory."""

    def __init__(self):
        self._root = Path(__file__).resolve().parent.parent / "output"
        self._root.mkdir(exist_ok=True)

    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        target_dir = self._root / subdir if subdir else self._root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


def create_adapter(model: str | None = None) -> PlatformAdapter:
    return PlatformAdapter(
        llm=WorkBuddyLLM(model=model),
        tools=WorkBuddyTools(),
        output=WorkBuddyOutput(),
    )


def _clamped_int(data: dict[str, object], key: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(data.get(key, default)), high))
    except (ValueError, TypeError):
        return default


def _clamped_float(data: dict[str, object], key: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(float(data.get(key, default)), high))
    except (ValueError, TypeError):
        return default
