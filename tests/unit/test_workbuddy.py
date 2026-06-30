#!/usr/bin/env python3
"""Tests for WorkBuddy tool routing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.interfaces import ToolResult
from adapters.workbuddy import WorkBuddyTools


class FakeMdsTool:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        self.calls.append({"query": query, "tool_type": tool_type, **kwargs})
        return ToolResult(ok=True, data={"query": query}, sources=["fake:mds"])


@pytest.mark.asyncio
async def test_web_search_is_delegated_to_host():
    tools = WorkBuddyTools()

    result = await tools.search("test company", "web")

    assert result.ok is True
    assert result.data["hint"] == "delegated_to_host"
    assert result.sources == ["wb:web"]


@pytest.mark.asyncio
async def test_host_mcp_is_delegated_to_host():
    tools = WorkBuddyTools()

    result = await tools.search("connector_catalog", "host_mcp")

    assert result.ok is True
    assert result.data["hint"] == "delegated_to_host"
    assert result.sources == ["wb:host_mcp"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_connector_catalog():
    tools = WorkBuddyTools()

    result = await tools.search("", "connector_catalog")

    assert result.ok is True
    assert result.data["type"] == "connector_catalog"
    assert "default_public_intel" in result.data["summary"]["zero_config_ready"]
    assert result.data["summary"]["data_effectiveness"]["fact_capable_sources"] >= 4
    assert result.sources == ["workbuddy:connector_catalog"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_release_readiness():
    tools = WorkBuddyTools()

    result = await tools.search("", "release_readiness")

    assert result.ok is True
    assert result.data["type"] == "release_readiness_brief"
    assert result.data["persona_surface"]["role_count"] == 13
    assert result.data["contract"]["variants"]["workbuddy_expert_team"]["readiness"] == "alpha"
    assert result.sources == ["workbuddy:release_readiness"]


@pytest.mark.asyncio
async def test_workbuddy_exposes_development_requirements():
    tools = WorkBuddyTools()

    result = await tools.search("", "development_requirements")

    assert result.ok is True
    assert result.data["type"] == "development_requirements_board"
    assert result.data["completion_percent"] == 88
    assert result.data["qyyjt_current_version"]["p0_queue_count"] == 20
    assert result.data["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"
    assert result.sources == ["workbuddy:development_requirements"]


@pytest.mark.asyncio
async def test_mds_failure_returns_tool_result(monkeypatch):
    tools = WorkBuddyTools()
    monkeypatch.setattr(tools, "_get_mds_tool", lambda: None)

    result = await tools.search("test company", "multi_datasource")

    assert result.ok is False
    assert result.data["query"] == "test company"
    assert result.data["tool_type"] == "multi_datasource"
    assert result.error


@pytest.mark.asyncio
async def test_force_keyword_path_does_not_crash():
    tools = WorkBuddyTools()
    fake = FakeMdsTool()
    tools._mds_tool = fake

    result = await tools.search("测试公司 股东 信息", "mds", sources=["demo"], use_cache=False)

    assert result.ok is True
    assert fake.calls == [
        {
            "query": "测试公司 股东 信息",
            "tool_type": "mds",
            "sources": ["demo"],
            "use_cache": False,
        }
    ]


@pytest.mark.asyncio
async def test_default_public_intel_failure_is_standardized(monkeypatch):
    tools = WorkBuddyTools()
    monkeypatch.setattr(tools, "_get_default_public_tool", lambda: None)

    result = await tools.search("Demo Co.", "default_public_intel")

    assert result.ok is False
    assert result.data["tool_type"] == "default_public_intel"
    assert result.sources == ["workbuddy:default_public_intel:error"]


@pytest.mark.asyncio
async def test_unknown_tool_type_is_reported():
    tools = WorkBuddyTools()

    result = await tools.search("test company", "unknown")

    assert result.ok is False
    assert "unknown" in result.data["tool_type"]
