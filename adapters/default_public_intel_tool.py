#!/usr/bin/env python3
"""Default public intelligence fan-out tool for first-run risk discovery."""
from __future__ import annotations

import asyncio
from typing import Any

from core.interfaces import ToolProvider, ToolResult
from core.record_quality import audit_standardized_records

from .creditchina_adapter import CreditchinaAdapter
from .public_web_search_tool import PublicWebSearchTool
from .qyyjt_adapter import QYYJTModule
from .qyyjt_tool import DEFAULT_MODULES, QYYJTTool
from .telegram_public_service_tool import TelegramPublicServiceTool


class DefaultPublicIntelTool(ToolProvider):
    """Run default-on public entries behind one product-facing tool.

    The default path uses only public/no-credential entry points. Credentialed
    depth remains available through each child connector's admission workflow.
    """

    def __init__(
        self,
        *,
        public_web: PublicWebSearchTool | None = None,
        qyyjt: QYYJTTool | None = None,
        telegram: TelegramPublicServiceTool | None = None,
        creditchina: CreditchinaAdapter | None = None,
        enabled_sources: tuple[str, ...] | None = None,
    ):
        self.public_web = public_web or PublicWebSearchTool()
        self.qyyjt = qyyjt or QYYJTTool()
        self.telegram = telegram or TelegramPublicServiceTool()
        self.creditchina = creditchina or CreditchinaAdapter()
        self.enabled_sources = enabled_sources or (
            "public_web_search",
            "qyyjt",
            "telegram_bot_public_service",
        )
        self._available = {
            "default_public_intel",
            "multi_datasource",
            "mds",
            "public_intel",
            "one_click_due_diligence",
        }

    def available_tools(self) -> set[str]:
        return set(self._available)

    def list_sources(self) -> list[str]:
        """Return configured child sources for routing diagnostics."""
        return list(self.enabled_sources)

    def available_sources(self) -> list[str]:
        """Return enabled child sources whose static health check is routable."""
        children = self._child_health()
        available: list[str] = []
        for name in self.enabled_sources:
            child = children.get(name)
            if isinstance(child, dict) and child.get("ok") is True:
                available.append(name)
        return available

    def can_handle_source_hint(self, source_hint: str) -> bool:
        """Return whether this default fan-out can honestly execute a planner source hint."""
        hint = str(source_hint or "").strip()
        return hint in {
            "default_public_intel",
            "web_search",
            "news_and_web_search",
            "registry_and_web_search",
            "relationship_network_sources",
            "supply_chain_sources",
            "industry_research_sources",
            "public_contact_sources",
            "public_account_sources",
            "location_activity_sources",
            "asset_and_location_sources",
            "public_behavior_sources",
        }

    def health_check(self) -> dict[str, Any]:
        children = self._child_health()
        enabled = [name for name in self.enabled_sources if name in children]
        return {
            "ok": any(bool(children[name].get("ok", False)) for name in enabled),
            "default_enabled": True,
            "default_public_entry": True,
            "enabled_sources": enabled,
            "children": children,
            "notes": [
                "Default public intelligence fan-out uses public/no-credential entries only.",
                "Credentialed or private depth remains gated by datasource admission.",
            ],
        }

    def health_report(self) -> dict[str, dict[str, Any]]:
        """Return product-facing child source readiness for API diagnostics."""
        enabled = set(self.enabled_sources)
        reports: dict[str, dict[str, Any]] = {}
        for name, child in self._child_health().items():
            ok = bool(child.get("ok", False))
            reports[name] = {
                "ok": ok,
                "status": "up" if ok and name in enabled else "available_explicit" if ok else "down",
                "enabled": name in enabled,
                "default_public_entry": bool(child.get("default_public_entry", False)),
                "requires_credentials": bool(child.get("requires_credentials", False)),
                "data_boundary": child.get("data_boundary"),
                "smoke_tested": name in {"public_web_search", "creditchina_public"},
                "smoke_test_file": "tests/unit/test_source_smoke.py"
                if name in {"public_web_search", "creditchina_public"}
                else None,
            }
        return reports

    def _child_health(self) -> dict[str, dict[str, Any]]:
        return {
            "public_web_search": self.public_web.health_check(),
            "qyyjt": {
                "ok": True,
                "default_public_entry": True,
                "notes": [
                    "QYYJT default entry emits public-search leads without user credentials."
                ],
            },
            "telegram_bot_public_service": self.telegram.health_check(),
            "creditchina_public": {
                "ok": True,
                "default_public_entry": False,
                "source_domain": self.creditchina.source_domain,
                "data_boundary": self.creditchina.data_boundary,
                "requires_credentials": self.creditchina.requires_credentials,
                "notes": [
                    "Credit China public adapter is available as an explicit administrative-risk source."
                ],
            },
        }

    async def search(
        self,
        query: str,
        tool_type: str = "default_public_intel",
        **kwargs: Any,
    ) -> ToolResult:
        if tool_type not in self._available:
            return ToolResult(
                ok=False,
                error=f"unsupported default public intel tool type: {tool_type}",
                data={"query": query, "tool_type": tool_type},
                sources=["default_public_intel:error"],
            )

        child_timeout_seconds = (
            _coerce_child_timeout(kwargs.get("child_timeout_seconds"))
            if kwargs.get("child_timeout_seconds") is not None
            else _bounded_child_timeout(kwargs.get("query_timeout_seconds"))
        )
        retrieval_layer = str(kwargs.get("retrieval_layer") or "").strip()
        selected_sources = self._enabled_sources_for_layer(retrieval_layer)

        child_results = await asyncio.gather(
            *[
                asyncio.wait_for(
                    self._run_child(name, query, kwargs),
                    timeout=child_timeout_seconds,
                )
                for name in selected_sources
            ],
            return_exceptions=True,
        )

        records: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        queried_sources: list[str] = []
        failed_sources: list[str] = []
        qyyjt_public_plan_executed = 0
        qyyjt_public_plan_failed = 0
        qyyjt_public_plan_diagnostics: list[dict[str, Any]] = []

        for source_name, result in zip(selected_sources, child_results):
            if isinstance(result, Exception):
                failed_sources.append(source_name)
                diagnostics.append(
                    {
                        "source_name": source_name,
                        "status": "failed",
                        "error": f"{type(result).__name__}: {result}",
                        "record_count": 0,
                    }
                )
                continue

            queried_sources.append(source_name)
            child_data = getattr(result, "data", {}) or {}
            child_records = _extract_standardized_records(child_data)
            records.extend(child_records)
            status = "success" if getattr(result, "ok", False) and child_records else "empty"
            diagnostic = {
                "source_name": source_name,
                "status": status if getattr(result, "ok", False) else "failed",
                "record_count": len(child_records),
                "error": getattr(result, "error", None),
            }
            if source_name == "qyyjt" and isinstance(child_data, dict):
                executed = int(child_data.get("qyyjt_public_plan_executed") or 0)
                failed = int(child_data.get("qyyjt_public_plan_failed") or 0)
                plan_diagnostics = child_data.get("qyyjt_public_plan_diagnostics")
                qyyjt_public_plan_executed += executed
                qyyjt_public_plan_failed += failed
                if isinstance(plan_diagnostics, list):
                    qyyjt_public_plan_diagnostics.extend(
                        item for item in plan_diagnostics if isinstance(item, dict)
                    )
                diagnostic["qyyjt_public_plan_executed"] = executed
                diagnostic["qyyjt_public_plan_failed"] = failed
                diagnostic["qyyjt_public_plan_diagnostics"] = (
                    [item for item in plan_diagnostics if isinstance(item, dict)]
                    if isinstance(plan_diagnostics, list)
                    else []
                )
            diagnostics.append(diagnostic)
            if not getattr(result, "ok", False):
                failed_sources.append(source_name)

        quality = audit_standardized_records(records).to_dict()
        return ToolResult(
            ok=bool(records) or bool(queried_sources),
            data={
                "query": query,
                "source_name": "default_public_intel",
                "source_type": "public_intel_fanout",
                "standardized_records": records,
                "record_quality": quality,
                "queried_sources": queried_sources,
                "failed_sources": sorted(set(failed_sources)),
                "source_diagnostics": diagnostics,
                "default_public_entry": True,
                "retrieval_layer": retrieval_layer or None,
                "selected_sources": selected_sources,
                "qyyjt_public_plan_executed": qyyjt_public_plan_executed,
                "qyyjt_public_plan_failed": qyyjt_public_plan_failed,
                "qyyjt_public_plan_diagnostics": qyyjt_public_plan_diagnostics,
            },
            sources=[f"default_public_intel:{source}" for source in queried_sources],
        )

    def _enabled_sources_for_layer(self, retrieval_layer: str) -> tuple[str, ...]:
        layer = str(retrieval_layer or "").strip()
        if layer in {"entity_anchor", "overview"}:
            preferred = tuple(
                source for source in self.enabled_sources
                if source in {"public_web_search", "qyyjt"}
            )
            return preferred or self.enabled_sources
        return self.enabled_sources

    async def _run_child(self, name: str, query: str, kwargs: dict[str, Any]) -> ToolResult:
        if name == "public_web_search":
            public_web_options = dict(kwargs.get("public_web_options", {}) or {})
            budget = _layer_budget(str(kwargs.get("retrieval_layer") or ""))
            public_web_options.setdefault("max_results", budget["public_web_max_results"])
            public_web_options.setdefault(
                "request_timeout_seconds",
                _coerce_child_timeout(kwargs.get("child_timeout_seconds"))
                if kwargs.get("child_timeout_seconds") is not None
                else _bounded_child_timeout(kwargs.get("query_timeout_seconds")),
            )
            return await self.public_web.search(
                query,
                "public_web_search",
                **public_web_options,
            )
        if name == "qyyjt":
            qyyjt_options = dict(kwargs.get("qyyjt_options", {}) or {})
            budget = _layer_budget(str(kwargs.get("retrieval_layer") or ""))
            if "modules" not in qyyjt_options and budget.get("qyyjt_modules"):
                qyyjt_options["modules"] = budget["qyyjt_modules"]
            result = await self.qyyjt.search(
                query,
                "qyyjt",
                prefer_api=False,
                company=kwargs.get("company") or query,
                **qyyjt_options,
            )
            if not bool(kwargs.get("execute_qyyjt_public_plan", True)):
                return result
            if kwargs.get("child_timeout_seconds") is not None and _coerce_child_timeout(kwargs.get("child_timeout_seconds")) < 1.0:
                data = dict(result.data or {})
                data["qyyjt_public_plan_executed"] = 0
                data["qyyjt_public_plan_skipped_reason"] = "child_timeout_budget_too_small"
                return ToolResult(ok=result.ok, data=data, sources=result.sources, error=result.error)
            return await self._attach_qyyjt_public_plan_results(result, kwargs, budget)
        if name == "telegram_bot_public_service":
            return await self.telegram.search(
                query,
                "telegram_bot_public_service",
                **dict(kwargs.get("telegram_options", {}) or {}),
            )
        if name == "creditchina_public":
            return await self._run_creditchina(query, kwargs)
        return ToolResult(
            ok=False,
            error=f"unknown default public intel source: {name}",
            data={"query": query, "source_name": name},
            sources=[f"default_public_intel:{name}:error"],
        )

    async def _run_creditchina(self, query: str, kwargs: dict[str, Any]) -> ToolResult:
        options = dict(kwargs.get("creditchina_options", {}) or {})
        result = await asyncio.to_thread(self.creditchina.query, query, **options)
        fields = result.get("fields") if isinstance(result, dict) else {}
        fields = fields if isinstance(fields, dict) else {}
        ok = not str(result.get("error") or "").strip() if isinstance(result, dict) else False
        records = []
        if ok and fields:
            records.append(
                {
                    "source_name": "creditchina_public",
                    "source_type": "government_public_disclosure",
                    "entity": query,
                    "title": f"Credit China public administrative disclosure for {query}",
                    "url": result.get("url") or f"https://{self.creditchina.source_domain}/",
                    "retrieved_at": result.get("observed_at"),
                    "confidence": 0.72,
                    "evidence": [
                        {
                            "field": key,
                            "value": value,
                            "source": "creditchina_public",
                        }
                        for key, value in fields.items()
                    ],
                    "source_profile": {
                        "authority": "official",
                        "access": "public",
                        "data_boundary": self.creditchina.data_boundary,
                    },
                }
            )
        return ToolResult(
            ok=ok,
            data={
                "query": query,
                "source_name": "creditchina_public",
                "source_type": "government_public_disclosure",
                "standardized_records": records,
                "raw": result,
                "audit_trail": self.creditchina.audit.get_trail(),
            },
            sources=["creditchina_public"] if ok else [],
            error=str(result.get("error") or "") if isinstance(result, dict) else "invalid creditchina result",
        )

    async def _attach_qyyjt_public_plan_results(
        self,
        result: ToolResult,
        kwargs: dict[str, Any],
        budget: dict[str, Any],
    ) -> ToolResult:
        data = dict(result.data or {})
        raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
        plan_items = [
            item for item in (raw.get("websearch_queries") or [])
            if isinstance(item, dict) and str(item.get("query") or "").strip()
        ]
        plan_limit = int(kwargs.get("qyyjt_public_plan_limit", budget.get("qyyjt_public_plan_limit", 2)) or 0)
        if plan_limit <= 0 or not plan_items:
            data["qyyjt_public_plan_executed"] = 0
            return ToolResult(ok=result.ok, data=data, sources=result.sources, error=result.error)

        public_web_options = dict(kwargs.get("public_web_options", {}) or {})
        child_timeout = (
            _coerce_child_timeout(kwargs.get("child_timeout_seconds"))
            if kwargs.get("child_timeout_seconds") is not None
            else _bounded_child_timeout(kwargs.get("query_timeout_seconds"))
        )
        plan_timeout = max(0.1, min(child_timeout * 0.45, 1.0))
        merged_records = list(data.get("standardized_records") or [])
        diagnostics: list[dict[str, Any]] = []
        executed = 0
        failures = 0
        for item in plan_items[:plan_limit]:
            plan_query = str(item.get("query") or "").strip()
            try:
                plan_result = await asyncio.wait_for(
                    self.public_web.search(
                        plan_query,
                        "public_web_search",
                        max_results=int(public_web_options.get("qyyjt_plan_max_results", 2) or 2),
                        request_timeout_seconds=plan_timeout,
                        **{
                            key: value
                            for key, value in public_web_options.items()
                            if key not in {"qyyjt_plan_max_results", "max_results", "request_timeout_seconds"}
                        },
                    ),
                    timeout=plan_timeout,
                )
            except Exception as exc:
                failures += 1
                diagnostics.append({
                    "query": plan_query,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            executed += 1
            records = _extract_standardized_records(plan_result.data)
            for record in records:
                enriched = dict(record)
                enriched["source_name"] = "qyyjt_public_plan:" + str(item.get("module") or "unknown")
                enriched["source_hint"] = "qyyjt_public_plan_executed"
                enriched["qyyjt_plan_query"] = plan_query
                merged_records.append(enriched)
            diagnostics.append({
                "query": plan_query,
                "status": "success" if records else "empty",
                "record_count": len(records),
            })

        data["standardized_records"] = merged_records
        data["record_quality"] = audit_standardized_records(merged_records).to_dict()
        data["qyyjt_public_plan_executed"] = executed
        data["qyyjt_public_plan_failed"] = failures
        data["qyyjt_public_plan_diagnostics"] = diagnostics
        return ToolResult(
            ok=bool(merged_records) or bool(result.ok),
            data=data,
            sources=[*result.sources, *([ "qyyjt:public_plan_results" ] if executed else [])],
            error=result.error,
        )


def _extract_standardized_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    records = payload.get("standardized_records")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    nested = payload.get("aggregated")
    if isinstance(nested, dict):
        extracted: list[dict[str, Any]] = []
        for item in nested.get("results", []):
            extracted.extend(_extract_standardized_records(item))
        return extracted
    return []


def _bounded_child_timeout(raw: Any) -> float:
    try:
        timeout_seconds = float(raw)
    except (TypeError, ValueError):
        timeout_seconds = 6.0
    return max(0.1, min(timeout_seconds * 0.5, 3.0))


def _coerce_child_timeout(raw: Any) -> float:
    try:
        timeout_seconds = float(raw)
    except (TypeError, ValueError):
        timeout_seconds = 3.0
    return max(0.1, min(timeout_seconds, 30.0))


def _layer_budget(retrieval_layer: str) -> dict[str, Any]:
    layer = str(retrieval_layer or "").strip()
    if layer == "entity_anchor":
        return {
            "public_web_max_results": 3,
            "qyyjt_modules": [QYYJTModule.SEARCH_MULTI, QYYJTModule.ENTERPRISE_BASIC],
            "qyyjt_public_plan_limit": 1,
        }
    if layer == "overview":
        return {
            "public_web_max_results": 5,
            "qyyjt_modules": [QYYJTModule.RISK_SCAN, QYYJTModule.ACTUAL_CONTROLLER, QYYJTModule.RELATED_PARTIES],
            "qyyjt_public_plan_limit": 2,
        }
    if layer == "prioritized_drilldown":
        return {
            "public_web_max_results": 8,
            "qyyjt_modules": list(DEFAULT_MODULES),
            "qyyjt_public_plan_limit": 5,
        }
    return {
        "public_web_max_results": 10,
        "qyyjt_modules": None,
        "qyyjt_public_plan_limit": 2,
    }


def create_default_public_intel_tool(**kwargs: Any) -> DefaultPublicIntelTool:
    return DefaultPublicIntelTool(**kwargs)
