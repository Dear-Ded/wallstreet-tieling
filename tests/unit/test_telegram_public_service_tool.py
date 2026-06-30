#!/usr/bin/env python3
"""Tests for Telegram public-service normalization bridge."""
from __future__ import annotations

import pytest

from adapters.telegram_public_service_tool import (
    TelegramPublicService,
    TelegramPublicServiceTool,
    normalize_telegram_public_service_payload,
    query_telegram_public_service_provider,
    telegram_public_service_results_to_standardized_records,
)
from core.risk_discovery_pipeline import RiskDiscoveryPipeline


def test_telegram_public_service_maps_payloads_to_standardized_records() -> None:
    service = TelegramPublicService(
        name="demo_bot",
        bot_handle="@demo_public_bot",
        endpoint="https://t.me/demo_public_bot",
        source_description="public registry aggregation returned by user-configured bot",
        enabled=True,
    )

    records = telegram_public_service_results_to_standardized_records(
        "Demo Telegram Co., Ltd.",
        [
            {
                "title": "Demo Telegram Co., Ltd. public risk clue",
                "text": "Public bot response mentions 被执行 and requires corroboration.",
                "message_url": "https://t.me/demo_public_bot/10",
                "confidence": 0.58,
            }
        ],
        service=service,
    )

    assert records[0]["source_name"] == "telegram_bot_public_service:demo_bot"
    assert records[0]["source_type"] == "telegram_bot"
    assert records[0]["source_hint"] == "telegram_bot_public_service"
    assert records[0]["url"] == "https://t.me/demo_public_bot/10"
    assert records[0]["confidence"] == 0.58
    claims = [item["claim"] for item in records[0]["evidence"]]
    assert any("source legitimacy review" in claim for claim in claims)
    assert "bot_handle=@demo_public_bot" in claims


@pytest.mark.asyncio
async def test_telegram_tool_returns_record_quality_report() -> None:
    tool = TelegramPublicServiceTool()

    result = await tool.search(
        "Demo Telegram Co., Ltd.",
        "telegram_bot_public_service",
        service={"name": "demo_bot", "source_description": "public records"},
        results=[
            {
                "title": "Demo Telegram Co., Ltd. public risk clue",
                "text": "Public service lead.",
                "message_url": "https://t.me/demo_public_bot/10",
            }
        ],
    )

    assert result.ok
    assert result.data["record_quality"]["ok"] is True
    assert result.data["record_quality"]["record_count"] == 1


def test_telegram_health_check_requires_enabled_service_provenance() -> None:
    tool = TelegramPublicServiceTool(
        services=[
            TelegramPublicService(name="missing_description", enabled=True),
            TelegramPublicService(
                name="reviewed_service",
                source_description="public or user-authorized business records",
                enabled=True,
            ),
        ]
    )

    health = tool.health_check()

    assert health["ok"] is False
    assert health["standardized_records"] is True
    assert health["enabled_count"] == 2
    assert health["missing_provenance"] == ["missing_description"]
    assert health["supports_live_provider"] is True


def test_telegram_source_review_report_marks_missing_metadata() -> None:
    tool = TelegramPublicServiceTool(
        services=[
            TelegramPublicService(name="incomplete", enabled=True),
            TelegramPublicService(
                name="ready",
                bot_handle="@ready_bot",
                source_description="public or user-authorized registry service",
                enabled=True,
            ),
        ]
    )

    report = tool.source_review_report()
    rows = {row["name"]: row for row in report["rows"]}

    assert report["ok"] is False
    assert rows["incomplete"]["review_ready"] is False
    assert "source_description" in rows["incomplete"]["missing"]
    assert rows["ready"]["review_ready"] is True
    assert rows["ready"]["next_action"] == "ready_for_user_authorized_transport_test"
    assert rows["ready"]["admission"]["decision"] == "conditional_production"
    assert rows["ready"]["admission"]["production_route"] == "user_configured_production"


def test_telegram_source_review_report_promotes_live_reviewed_service() -> None:
    tool = TelegramPublicServiceTool(
        services=[
            TelegramPublicService(
                name="reviewed_live",
                bot_handle="@reviewed_bot",
                source_description="public registry aggregation returned by user-configured bot",
                authorization_evidence="user_supplied_service_scope",
                terms_reviewed=True,
                live_validation_ok=True,
                enabled=True,
            )
        ]
    )

    report = tool.source_review_report()
    row = report["rows"][0]

    assert report["ok"] is True
    assert row["review_ready"] is True
    assert row["admission"]["decision"] == "production_ready"
    assert row["admission"]["production_route"] == "active"


def test_normalize_telegram_provider_payload_handles_common_shapes() -> None:
    payload = {
        "messages": [
            {
                "message": "Public bot response.",
                "url": "https://t.me/demo/1",
                "confidence": 0.6,
            },
            "Plain text public lead.",
        ]
    }

    records = normalize_telegram_public_service_payload(payload)

    assert records[0]["text"] == "Public bot response."
    assert records[0]["message_url"] == "https://t.me/demo/1"
    assert records[1]["text"] == "Plain text public lead."


@pytest.mark.asyncio
async def test_telegram_provider_slot_accepts_callable_provider() -> None:
    service = TelegramPublicService(
        name="demo_bot",
        bot_handle="@demo_public_bot",
        source_description="public registry aggregation returned by user-configured bot",
    )

    async def provider(query: str, service=None, max_results: int = 10):
        assert service.name == "demo_bot"
        return {
            "results": [
                {
                    "title": f"{query} public lead",
                    "text": "Provider returned public-service lead.",
                    "message_url": "https://t.me/demo_public_bot/20",
                }
            ]
        }

    payloads = await query_telegram_public_service_provider(
        "Demo Telegram Co., Ltd.",
        provider=provider,
        service=service,
    )

    assert payloads[0]["message_url"] == "https://t.me/demo_public_bot/20"


@pytest.mark.asyncio
async def test_telegram_tool_uses_live_provider_slot() -> None:
    async def provider(query: str, service=None, max_results: int = 10):
        return [
            {
                "title": f"{query} provider lead",
                "text": "User-authorized public service returned a risk lead.",
                "message_url": "https://t.me/demo_public_bot/21",
            }
        ]

    tool = TelegramPublicServiceTool(provider=provider)

    result = await tool.search(
        "Demo Telegram Co., Ltd.",
        "telegram_bot_public_service",
        service={
            "name": "demo_bot",
            "bot_handle": "@demo_public_bot",
            "source_description": "public records",
        },
    )

    assert result.ok is True
    assert result.data["provider_configured"] is True
    assert result.data["transport_attempted"] is True
    assert result.data["result_count"] == 1
    assert result.data["record_quality"]["ok"] is True


@pytest.mark.asyncio
async def test_telegram_tool_feeds_risk_discovery_pipeline(tmp_path) -> None:
    service = TelegramPublicService(
        name="demo_bot",
        bot_handle="@demo_public_bot",
        source_description="public risk clues returned from user-configured service",
    )
    tool = TelegramPublicServiceTool()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    class TelegramWrapper:
        def health_check(self):
            return tool.health_check()

        async def search(self, query: str, tool_type: str, **kwargs):
            return await tool.search(
                query,
                "telegram_bot_public_service",
                service=service,
                results=[
                    {
                        "title": f"{query} public enforcement clue",
                        "text": "User-configured public service returned 被执行 risk lead.",
                        "message_url": "https://t.me/demo_public_bot/11",
                    }
                ],
            )

    result = await pipeline.run("Demo Telegram Co., Ltd.", search_engine=TelegramWrapper())

    assert result.queried_sources == ["telegram_bot_public_service"]
    assert result.evidence_count >= 1
    assert result.risk_event_summary["alert_count"] >= 1
