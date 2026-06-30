#!/usr/bin/env python3
"""Tests for zero-config one-click retrieval defaults."""
from __future__ import annotations

from core.interfaces import ToolResult
from core.one_click_defaults import (
    DEFAULT_ONE_CLICK_SOURCE,
    DefaultOneClickSearchEngine,
    build_default_one_click_plan,
    build_default_one_click_search_engine,
)


class CapturingPublicTool:
    def __init__(self):
        self.calls = []

    def available_tools(self) -> set[str]:
        return {DEFAULT_ONE_CLICK_SOURCE}

    def health_check(self) -> dict:
        return {"ok": True}

    async def search(self, query: str, tool_type: str, **kwargs):
        self.calls.append({"query": query, "tool_type": tool_type, "kwargs": kwargs})
        return ToolResult(
            ok=True,
            data={
                "source_name": DEFAULT_ONE_CLICK_SOURCE,
                "source_type": "public_intel_fanout",
                "standardized_records": [],
            },
            sources=[DEFAULT_ONE_CLICK_SOURCE],
        )


async def test_default_one_click_engine_does_not_initialize_official_sources_by_default() -> None:
    engine = await build_default_one_click_search_engine()

    assert engine.official_engine is None
    assert engine.list_sources() == [DEFAULT_ONE_CLICK_SOURCE]
    assert engine.available_sources() == [DEFAULT_ONE_CLICK_SOURCE]
    assert engine.can_handle_source_hint(DEFAULT_ONE_CLICK_SOURCE) is True
    assert engine.can_handle_source_hint("sec_edgar_public_api") is False
    assert engine.can_handle_source_hint("gleif_lei_public_api") is False


def test_default_one_click_health_does_not_overclaim_missing_public_health() -> None:
    class NoHealthPublicTool:
        def available_tools(self) -> set[str]:
            return {DEFAULT_ONE_CLICK_SOURCE}

    engine = DefaultOneClickSearchEngine(public_tool=NoHealthPublicTool())

    assert engine.health_check()[DEFAULT_ONE_CLICK_SOURCE] is False


async def test_default_one_click_engine_passes_bounded_timeout_to_public_fanout() -> None:
    public_tool = CapturingPublicTool()
    engine = DefaultOneClickSearchEngine(public_tool=public_tool)

    await engine.search(
        DEFAULT_ONE_CLICK_SOURCE,
        "Demo Budget Co.",
        params={"company": "Demo Budget Co.", "query_timeout_seconds": 8},
    )

    kwargs = public_tool.calls[0]["kwargs"]

    assert kwargs["company"] == "Demo Budget Co."
    assert kwargs["query_timeout_seconds"] == 8
    assert kwargs["child_timeout_seconds"] == 3.0
    assert kwargs["public_web_options"]["request_timeout_seconds"] == 3.0


async def test_default_one_click_engine_forwards_task_public_options() -> None:
    public_tool = CapturingPublicTool()
    engine = DefaultOneClickSearchEngine(public_tool=public_tool)

    await engine.search(
        DEFAULT_ONE_CLICK_SOURCE,
        "Demo Option Co.",
        params={
            "company": "Demo Option Co.",
            "qyyjt_options": {"modules": ["ent_financing"]},
            "qyyjt_public_plan_limit": 3,
            "execute_qyyjt_public_plan": True,
        },
    )

    kwargs = public_tool.calls[0]["kwargs"]
    assert kwargs["qyyjt_options"] == {"modules": ["ent_financing"]}
    assert kwargs["qyyjt_public_plan_limit"] == 3
    assert kwargs["execute_qyyjt_public_plan"] is True


def test_default_one_click_plan_includes_targeted_money_and_goods_public_tasks() -> None:
    plan = build_default_one_click_plan("Demo Deep Default Co.")
    default_tasks = [task for task in plan.tasks if task.source_hint == DEFAULT_ONE_CLICK_SOURCE]

    money_task = next(task for task in default_tasks if "capital" in task.objective.lower())
    goods_task = next(task for task in default_tasks if "goods" in task.objective.lower())

    money_modules = {module.value for module in money_task.params["qyyjt_options"]["modules"]}
    goods_modules = {module.value for module in goods_task.params["qyyjt_options"]["modules"]}
    assert {"ent_financing", "financial", "fin_indic", "bond_profile"} <= money_modules
    assert {"import_export", "patent", "trademark", "recruit"} <= goods_modules
    assert money_task.params["qyyjt_public_plan_limit"] == 3
    assert goods_task.params["qyyjt_public_plan_limit"] == 3
    assert money_task.params["execute_qyyjt_public_plan"] is True
    assert goods_task.params["execute_qyyjt_public_plan"] is True
