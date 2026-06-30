#!/usr/bin/env python3
"""User-configured Telegram public-service normalizer.

This bridge treats Telegram bots as a delivery shape for public or
user-authorized data. It does not scrape private chats or bypass access
controls; callers provide returned payloads from their own configured service,
and the bridge maps them into the evidence format used by risk discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.interfaces import ToolProvider, ToolResult
from core.record_quality import audit_standardized_records
from core.source_admission import SourceAdmissionEvaluator


@dataclass(frozen=True)
class TelegramPublicService:
    """Auditable metadata for one user-configured Telegram service."""

    name: str
    bot_handle: str = ""
    endpoint: str = ""
    source_description: str = ""
    authorization_scope: str = "public_or_user_authorized"
    enabled: bool = False
    terms_reviewed: bool = False
    authorization_evidence: str = ""
    live_validation_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bot_handle": self.bot_handle,
            "endpoint": self.endpoint,
            "source_description": self.source_description,
            "authorization_scope": self.authorization_scope,
            "enabled": self.enabled,
            "terms_reviewed": self.terms_reviewed,
            "authorization_evidence": self.authorization_evidence,
            "live_validation_ok": self.live_validation_ok,
        }


class TelegramPublicServiceTool(ToolProvider):
    """Normalize Telegram public-service payloads into evidence records."""

    def __init__(
        self,
        services: list[TelegramPublicService] | None = None,
        provider: Any = None,
    ):
        self.services = services or []
        self.provider = provider
        self._available = {
            "telegram_bot_public_service",
            "telegram_public_service",
            "telegram_bot",
        }

    def available_tools(self) -> set[str]:
        return set(self._available)

    def health_check(self) -> dict[str, Any]:
        configured = [service.to_dict() for service in self.services]
        enabled = [service for service in self.services if service.enabled]
        missing_provenance = [
            service.name
            for service in self.services
            if service.enabled and not service.source_description.strip()
        ]
        return {
            "ok": not missing_provenance,
            "configured_count": len(self.services),
            "enabled_count": len(enabled),
            "standardized_records": True,
            "requires_external_transport": True,
            "live_provider_configured": self.provider is not None,
            "supports_live_provider": True,
            "default_enabled": False,
            "missing_provenance": missing_provenance,
            "services": configured,
            "notes": [
                "Telegram is treated only as a user-configured delivery shape.",
                "Underlying data must be public or user-authorized and provenance must be retained.",
            ],
        }

    def source_review_report(self) -> dict[str, Any]:
        """Return a review checklist for configured Telegram delivery services."""
        rows: list[dict[str, Any]] = []
        for service in self.services:
            missing: list[str] = []
            if not service.source_description.strip():
                missing.append("source_description")
            if not service.authorization_scope.strip():
                missing.append("authorization_scope")
            if not (service.bot_handle.strip() or service.endpoint.strip()):
                missing.append("bot_handle_or_endpoint")
            admission = SourceAdmissionEvaluator().evaluate(
                SourceAdmissionEvaluator.telegram_public_service_admission_input(
                    source_description=service.source_description,
                    authorization_evidence=service.authorization_evidence
                    or _service_authorization_evidence(service),
                    terms_reviewed=service.terms_reviewed,
                    live_validation_ok=service.live_validation_ok,
                )
            ).to_dict()
            rows.append(
                {
                    **service.to_dict(),
                    "review_ready": service.enabled and not missing,
                    "admission": admission,
                    "missing": missing,
                    "next_action": (
                        "ready_for_user_authorized_transport_test"
                        if service.enabled and not missing
                        else "complete_source_legitimacy_and_transport_metadata"
                    ),
                }
            )
        return {
            "ok": all(row["review_ready"] for row in rows if row["enabled"]),
            "default_enabled": False,
            "requires_external_transport": True,
            "rows": rows,
        }

    async def search(
        self,
        query: str,
        tool_type: str = "telegram_bot_public_service",
        **kwargs: Any,
    ) -> ToolResult:
        if tool_type not in self._available:
            return ToolResult(
                ok=False,
                error=f"unsupported Telegram public-service tool type: {tool_type}",
                data={"query": query, "tool_type": tool_type},
                sources=["telegram_bot_public_service:error"],
            )

        service = _coerce_service(kwargs.get("service"))
        raw_results = kwargs.get("results") or kwargs.get("payloads") or []
        provider = kwargs.get("provider") or kwargs.get("transport") or self.provider
        transport_attempted = False
        if not raw_results and provider is not None:
            transport_attempted = True
            raw_results = await query_telegram_public_service_provider(
                query,
                provider=provider,
                service=service,
                max_results=int(kwargs.get("max_results", 10) or 10),
                provider_options=dict(kwargs.get("provider_options", {}) or {}),
            )
        records = telegram_public_service_results_to_standardized_records(
            query,
            raw_results,
            service=service,
        )
        quality = audit_standardized_records(records)
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "source_name": "telegram_bot_public_service",
                "source_type": "telegram_bot",
                "standardized_records": records,
                "record_quality": quality.to_dict(),
                "result_count": len(records),
                "service": service.to_dict() if service else None,
                "provider_configured": provider is not None,
                "transport_attempted": transport_attempted,
            },
            sources=["telegram_bot_public_service:standardized_records"],
        )


async def query_telegram_public_service_provider(
    query: str,
    *,
    provider: Any = None,
    service: TelegramPublicService | None = None,
    max_results: int = 10,
    provider_options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run a configured user-authorized Telegram service provider.

    Providers are intentionally injected by the host app or deployment. The
    bridge only calls them, normalizes the returned payload shape, and keeps the
    configured service metadata attached to downstream evidence records.
    """
    if provider is None:
        return []
    provider_options = provider_options or {}
    if hasattr(provider, "search") and callable(provider.search):
        raw = provider.search(query, service=service, max_results=max_results, **provider_options)
    elif hasattr(provider, "query") and callable(provider.query):
        raw = provider.query(query, service=service, max_results=max_results, **provider_options)
    elif callable(provider):
        raw = provider(query, service=service, max_results=max_results, **provider_options)
    else:
        return []
    if hasattr(raw, "__await__"):
        raw = await raw
    return normalize_telegram_public_service_payload(raw)[:max_results]


def normalize_telegram_public_service_payload(raw: Any) -> list[dict[str, Any]]:
    """Map common provider payloads into a list of bot-service result dicts."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        candidates = (
            raw.get("results")
            or raw.get("items")
            or raw.get("messages")
            or raw.get("data")
            or raw.get("payloads")
        )
    else:
        candidates = raw
    if not isinstance(candidates, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if isinstance(item, str):
            normalized.append({"text": item})
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("message") or item.get("content") or item.get("summary")
        title = item.get("title") or item.get("name")
        url = item.get("message_url") or item.get("url") or item.get("source_url")
        if not (text or title or url):
            continue
        normalized.append(
            {
                "title": title or "",
                "text": text or "",
                "message_url": url or "",
                "published_at": item.get("published_at") or item.get("date") or item.get("observed_at"),
                "confidence": item.get("confidence", 0.35),
                "raw": item,
            }
        )
    return normalized


def telegram_public_service_results_to_standardized_records(
    query: str,
    results: list[dict[str, Any]],
    *,
    service: TelegramPublicService | None = None,
) -> list[dict[str, Any]]:
    """Map returned bot-service payloads into standardized evidence records."""

    service = service or TelegramPublicService(name="user_configured_telegram_service")
    records: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue

        body = str(
            item.get("summary")
            or item.get("text")
            or item.get("content")
            or item.get("message")
            or ""
        ).strip()
        title = str(item.get("title") or item.get("name") or query).strip()
        url = str(item.get("url") or item.get("message_url") or item.get("source_url") or "").strip()
        if not title and not body and not url:
            continue

        source_name = f"telegram_bot_public_service:{service.name}"
        records.append(
            {
                "source_name": source_name,
                "source_type": "telegram_bot",
                "source_hint": "telegram_bot_public_service",
                "entity": str(item.get("entity") or query),
                "title": title or query,
                "summary": body,
                "url": url,
                "published_at": item.get("published_at") or item.get("observed_at") or item.get("date"),
                "confidence": _clamp(item.get("confidence", 0.35)),
                "evidence": _evidence_claims(item, service, body),
                "raw": {
                    "service": service.to_dict(),
                    "payload": item,
                },
            }
        )
    return records


def _evidence_claims(
    item: dict[str, Any],
    service: TelegramPublicService,
    body: str,
) -> list[dict[str, str]]:
    claims = [
        {
            "claim": (
                "Telegram public-service result is user-configured and requires "
                "source legitimacy review."
            )
        },
        {"claim": f"authorization_scope={service.authorization_scope}"},
    ]
    if service.bot_handle:
        claims.append({"claim": f"bot_handle={service.bot_handle}"})
    if service.source_description:
        claims.append({"claim": f"source_description={service.source_description}"})
    if body:
        claims.append({"claim": body})
    for evidence in item.get("evidence") or []:
        if isinstance(evidence, dict):
            value = evidence.get("claim") or evidence.get("text") or evidence.get("value")
        else:
            value = evidence
        if str(value or "").strip():
            claims.append({"claim": str(value)})
    return claims


def _coerce_service(raw: Any) -> TelegramPublicService | None:
    if raw is None:
        return None
    if isinstance(raw, TelegramPublicService):
        return raw
    if isinstance(raw, dict):
        return TelegramPublicService(
            name=str(raw.get("name") or "user_configured_telegram_service"),
            bot_handle=str(raw.get("bot_handle") or raw.get("handle") or ""),
            endpoint=str(raw.get("endpoint") or raw.get("url") or ""),
            source_description=str(raw.get("source_description") or raw.get("description") or ""),
            authorization_scope=str(raw.get("authorization_scope") or "public_or_user_authorized"),
            enabled=bool(raw.get("enabled", False)),
            terms_reviewed=bool(raw.get("terms_reviewed", False)),
            authorization_evidence=str(raw.get("authorization_evidence") or ""),
            live_validation_ok=bool(raw.get("live_validation_ok", False)),
        )
    return TelegramPublicService(name=str(raw))


def _service_authorization_evidence(service: TelegramPublicService) -> str:
    parts = []
    if service.authorization_scope.strip():
        parts.append(f"scope={service.authorization_scope.strip()}")
    if service.bot_handle.strip():
        parts.append(f"bot={service.bot_handle.strip()}")
    if service.endpoint.strip():
        parts.append(f"endpoint={service.endpoint.strip()}")
    return ";".join(parts)


def _clamp(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.35
    return max(0.0, min(1.0, value))


def create_telegram_public_service_tool(
    services: list[TelegramPublicService] | None = None,
) -> TelegramPublicServiceTool:
    return TelegramPublicServiceTool(services=services)
