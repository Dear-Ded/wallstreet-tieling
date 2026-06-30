#!/usr/bin/env python3
"""Tests for module collaboration primitives."""
from __future__ import annotations

import asyncio

import pytest

from core.module_collaboration import (
    CollaborationOrchestrator,
    DataBus,
    FinancialAnalysisModule,
    MessageType,
    ModuleInterface,
    ModuleMessage,
    ModuleRegistry,
    ModuleStatus,
)


class EchoModule(ModuleInterface):
    def __init__(self, name: str = "echo"):
        super().__init__(name)
        self.events: list[ModuleMessage] = []
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task)

    async def _handle_task(self, message: ModuleMessage):
        self.events.append(message)
        self.status = ModuleStatus.RUNNING


def test_registry_and_bus_basics():
    registry = ModuleRegistry()
    module = EchoModule()
    registry.register(module)
    assert registry.get_module("echo") is module
    assert registry.get_module_status("echo") == ModuleStatus.INITIALIZING

    bus = DataBus()
    bus.subscribe("foo", "sub-a")
    bus.publish("foo", 123, "publisher-a")
    assert bus.get("foo") == 123
    assert bus.get_with_metadata("foo")["publisher"] == "publisher-a"


@pytest.mark.asyncio
async def test_module_message_delivery_and_dispatch():
    registry = ModuleRegistry()
    sender = EchoModule("sender")
    receiver = EchoModule("receiver")
    registry.register(sender)
    registry.register(receiver)

    await sender.send_message(
        receiver="receiver",
        msg_type=MessageType.TASK_ASSIGN,
        payload={"task": "demo"},
        registry=registry,
    )

    assert receiver.events[0].payload["task"] == "demo"


@pytest.mark.asyncio
async def test_orchestrator_dispatches_only_running_modules():
    orchestrator = CollaborationOrchestrator()
    module = EchoModule("financial_analyzer")
    orchestrator.register_module(module)
    module.start()

    await orchestrator.dispatch_task("analyze", ["financial_analyzer"], {"company": "abc"})

    assert module.events
    assert module.events[0].payload["task_name"] == "analyze"
    summary = await orchestrator.broadcast_status()
    assert summary["financial_analyzer"] == ModuleStatus.RUNNING.value


@pytest.mark.asyncio
async def test_financial_analysis_module_publishes_result():
    orchestrator = CollaborationOrchestrator()
    module = FinancialAnalysisModule()
    orchestrator.register_module(module)
    module.start()

    await orchestrator.dispatch_task("analyze", ["financial_analyzer"], {"company": "abc"})

    assert orchestrator.data_bus.get("financial_analysis_result")["status"] == "completed"
