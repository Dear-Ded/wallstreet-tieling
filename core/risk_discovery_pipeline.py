#!/usr/bin/env python3
"""Executable company-name to risk-alert pipeline."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

from .intelligence_retrieval import (
    EvidenceGraph,
    EvidenceIngestor,
    EntityKind,
    InvestigativeRetrievalPlanner,
    InvestigationEntity,
    RetrievalDomain,
    RetrievalLayer,
    RetrievalPlan,
    SearchTask,
)
from .risk_event_store import RiskEventStore
from .subject_profile import SubjectProfileBuilder
from .storage_paths import runtime_state_path


class _RetrievalQueryTimeout(Exception):
    """Raised when the product-level retrieval budget is exhausted."""


@dataclass(frozen=True)
class RiskDiscoveryResult:
    """Monitoring-ready output for a single company risk discovery run."""

    ok: bool
    run_id: str
    company: str
    store_path: str
    retrieval_plan: RetrievalPlan
    queried_sources: list[str]
    failed_sources: list[str]
    source_diagnostics: list[dict[str, Any]]
    retrieval_summary: dict[str, Any]
    evidence_count: int
    entity_count: int
    risk_event_count: int
    risk_event_summary: dict[str, Any]
    subject_profile: dict[str, Any]

    @property
    def graph(self) -> EvidenceGraph:
        return self.retrieval_plan.graph

    def to_dict(self, *, include_plan: bool = False) -> dict[str, Any]:
        payload = {
            "ok": self.ok,
            "run_id": self.run_id,
            "company": self.company,
            "store_path": self.store_path,
            "queried_sources": self.queried_sources,
            "failed_sources": self.failed_sources,
            "source_diagnostics": self.source_diagnostics,
            "retrieval_summary": self.retrieval_summary,
            "evidence_count": self.evidence_count,
            "entity_count": self.entity_count,
            "risk_event_count": self.risk_event_count,
            "risk_event_summary": self.risk_event_summary,
            "subject_profile": self.subject_profile,
            "first_alert": (
                self.risk_event_summary["alerts"][0]
                if self.risk_event_summary.get("alerts")
                else None
            ),
        }
        if include_plan:
            payload["retrieval_plan"] = self.retrieval_plan.to_dict()
        return payload


class RiskDiscoveryPipeline:
    """Runs configured retrieval results into graph, risk events, and alerts."""

    LAYER_BUDGETS: dict[RetrievalLayer, dict[str, Any]] = {
        RetrievalLayer.ENTITY_ANCHOR: {
            "result_limit": 3,
            "source_budget": "anchor",
            "per_source_result_limit": 3,
        },
        RetrievalLayer.OVERVIEW: {
            "result_limit": 5,
            "source_budget": "overview",
            "per_source_result_limit": 5,
        },
        RetrievalLayer.PRIORITIZED_DRILLDOWN: {
            "result_limit": 8,
            "source_budget": "drilldown",
            "per_source_result_limit": 8,
        },
        RetrievalLayer.SPECIALIST: {
            "result_limit": 12,
            "source_budget": "specialist",
            "per_source_result_limit": 12,
        },
    }

    def __init__(
        self,
        *,
        planner: InvestigativeRetrievalPlanner | None = None,
        risk_event_store: RiskEventStore | str | Path | None = None,
    ):
        self.planner = planner or InvestigativeRetrievalPlanner()
        if isinstance(risk_event_store, RiskEventStore):
            self.risk_event_store = risk_event_store
        else:
            store_path = risk_event_store or runtime_state_path(
                "risk-events.jsonl",
                filename_env_var="WST_RISK_EVENT_STORE",
            )
            self.risk_event_store = RiskEventStore(store_path)

    async def run(
        self,
        company: str,
        *,
        search_engine: Any | None = None,
        records: list[dict[str, Any]] | None = None,
        store_path: str | Path | None = None,
        existing_plan: RetrievalPlan | None = None,
        retrieval_concurrency: int = 4,
        fanout_rounds: int = 1,
        max_fanout_tasks: int = 24,
        identifier_fanout_only: bool = False,
        query_timeout_seconds: float = 20.0,
    ) -> RiskDiscoveryResult:
        """Run one executable risk-discovery pass.

        `records` is the offline/test path. `search_engine` is any initialized
        object exposing `search_available(...)`, including the multi-source
        SearchEngine singleton. Both paths converge into the same graph/event
        ingestion flow.
        """
        run_id = f"risk:{uuid.uuid4().hex[:12]}"
        plan = existing_plan or self.planner.build_company_plan(company)
        seed_id = self._seed_entity_id(plan)
        queried_sources: list[str] = []
        failed_sources: list[str] = []
        source_diagnostics: list[dict[str, Any]] = []

        if records is not None:
            task = self._default_task(plan)
            evidence_items = EvidenceIngestor.ingest_standardized_records(
                plan.graph,
                seed_entity_id=seed_id,
                task=task,
                records=records,
            )
            queried_sources = sorted(
                {
                    str(record.get("source_name") or record.get("source") or "offline_records")
                    for record in records
                }
            )
            source_diagnostics.append(
                {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": "offline_records",
                    "status": "success" if evidence_items else "empty",
                    "record_count": len(records),
                    "ingested_count": len(evidence_items),
                }
            )
        elif search_engine is not None:
            await self._execute_search_engine(
                plan,
                seed_id,
                search_engine,
                queried_sources,
                failed_sources,
                source_diagnostics,
                retrieval_concurrency=max(1, retrieval_concurrency),
                query_timeout_seconds=max(0.1, float(query_timeout_seconds)),
            )
            await self._execute_entity_fanout(
                plan,
                seed_id,
                search_engine,
                queried_sources,
                failed_sources,
                source_diagnostics,
                retrieval_concurrency=max(1, retrieval_concurrency),
                fanout_rounds=max(0, fanout_rounds),
                max_fanout_tasks=max(0, max_fanout_tasks),
                identifier_fanout_only=identifier_fanout_only,
                query_timeout_seconds=max(0.1, float(query_timeout_seconds)),
            )

        source_routing = self._source_routing_snapshot(search_engine)
        store = RiskEventStore(store_path) if store_path else self.risk_event_store
        risk_event_summary = store.append_from_graph(plan.seed_company, plan.graph)
        subject_profile = SubjectProfileBuilder().build(
            plan.graph,
            seed_subject_id=seed_id,
        ).to_dict()
        queried_sources = sorted(set(queried_sources))
        failed_sources = sorted(set(failed_sources))
        self._finalize_source_diagnostics(run_id, source_diagnostics)
        retrieval_summary = self._build_retrieval_summary(
            source_diagnostics,
            evidence_count=len(plan.graph.evidence),
            risk_event_count=len(plan.graph.risk_events),
            plan=plan,
            source_routing=source_routing,
            run_id=run_id,
        )

        ok = retrieval_summary["execution_state"] not in {
            "not_executed",
            "no_available_sources",
            "all_sources_failed",
        }

        return RiskDiscoveryResult(
            ok=ok,
            run_id=run_id,
            company=plan.seed_company,
            store_path=str(store.path),
            retrieval_plan=plan,
            queried_sources=queried_sources,
            failed_sources=failed_sources,
            source_diagnostics=source_diagnostics,
            retrieval_summary=retrieval_summary,
            evidence_count=len(plan.graph.evidence),
            entity_count=len(plan.graph.entities),
            risk_event_count=len(plan.graph.risk_events),
            risk_event_summary=risk_event_summary,
            subject_profile=subject_profile,
        )

    async def _execute_search_engine(
        self,
        plan: RetrievalPlan,
        seed_id: str,
        search_engine: Any,
        queried_sources: list[str],
        failed_sources: list[str],
        source_diagnostics: list[dict[str, Any]],
        retrieval_concurrency: int,
        query_timeout_seconds: float,
    ) -> None:
        for layer in (
            RetrievalLayer.ENTITY_ANCHOR,
            RetrievalLayer.OVERVIEW,
            RetrievalLayer.PRIORITIZED_DRILLDOWN,
            RetrievalLayer.SPECIALIST,
        ):
            tasks = [
                task for task in plan.tasks
                if task.effective_retrieval_layer() is layer
            ]
            if not tasks:
                continue
            await self._execute_task_batch(
                plan,
                seed_id,
                tasks,
                search_engine,
                queried_sources,
                failed_sources,
                source_diagnostics,
                retrieval_concurrency=retrieval_concurrency,
                query_timeout_seconds=query_timeout_seconds,
            )

    async def _execute_entity_fanout(
        self,
        plan: RetrievalPlan,
        seed_id: str,
        search_engine: Any,
        queried_sources: list[str],
        failed_sources: list[str],
        source_diagnostics: list[dict[str, Any]],
        *,
        retrieval_concurrency: int,
        fanout_rounds: int,
        max_fanout_tasks: int,
        identifier_fanout_only: bool,
        query_timeout_seconds: float,
    ) -> None:
        """Run bounded associative tasks for discovered people, addresses, and accounts."""
        if fanout_rounds <= 0 or max_fanout_tasks <= 0:
            return

        seen_task_keys = self._task_keys(plan.tasks)
        executed = 0
        for round_index in range(1, fanout_rounds + 1):
            candidates = self._fanout_tasks_for_graph(
                plan,
                seen_task_keys,
                round_index,
                identifier_fanout_only=identifier_fanout_only,
            )
            if not candidates:
                return
            budget = max_fanout_tasks - executed
            if budget <= 0:
                return
            tasks = candidates[:budget]
            plan.tasks.extend(tasks)
            plan.coverage_domains.update(task.domain for task in tasks)
            for task in tasks:
                seen_task_keys.add(self._task_key(task))
            await self._execute_task_batch(
                plan,
                seed_id,
                tasks,
                search_engine,
                queried_sources,
                failed_sources,
                source_diagnostics,
                retrieval_concurrency=retrieval_concurrency,
                query_timeout_seconds=query_timeout_seconds,
            )
            executed += len(tasks)

    async def _execute_task_batch(
        self,
        plan: RetrievalPlan,
        seed_id: str,
        tasks: list[SearchTask],
        search_engine: Any,
        queried_sources: list[str],
        failed_sources: list[str],
        source_diagnostics: list[dict[str, Any]],
        *,
        retrieval_concurrency: int,
        query_timeout_seconds: float,
    ) -> None:
        semaphore = asyncio.Semaphore(retrieval_concurrency)

        async def run_task(task: SearchTask) -> None:
            async with semaphore:
                await self._execute_search_task(
                    plan,
                    seed_id,
                    task,
                    search_engine,
                    queried_sources,
                    failed_sources,
                    source_diagnostics,
                    query_timeout_seconds=query_timeout_seconds,
                )

        await asyncio.gather(*(run_task(task) for task in tasks))

    def _fanout_tasks_for_graph(
        self,
        plan: RetrievalPlan,
        seen_task_keys: set[tuple[str, str, str]],
        round_index: int,
        *,
        identifier_fanout_only: bool = False,
    ) -> list[SearchTask]:
        tasks: list[SearchTask] = []
        for entity in sorted(plan.graph.entities.values(), key=lambda item: (item.kind.value, item.name)):
            if not identifier_fanout_only and entity.attributes.get("seed") is not True:
                for task in self.planner.expand_from_entity(entity):
                    key = self._task_key(task)
                    if key in seen_task_keys:
                        continue
                    tasks.append(
                        SearchTask(
                            domain=task.domain,
                            query=task.query,
                            source_hint=task.source_hint,
                            objective=f"Fanout round {round_index}: {task.objective}",
                            priority=task.priority + (round_index * 5),
                            expected_evidence=task.expected_evidence,
                            fanout_entities=task.fanout_entities,
                            source_profile=task.source_profile,
                            params=dict(task.params),
                        )
                    )
                    seen_task_keys.add(key)
            for task in self._identifier_fanout_tasks(entity, seen_task_keys, round_index):
                tasks.append(task)
                seen_task_keys.add(self._task_key(task))
            for task in self._public_graph_fanout_tasks(entity, seen_task_keys, round_index):
                tasks.append(task)
                seen_task_keys.add(self._task_key(task))
        return sorted(tasks, key=lambda item: (item.priority, item.domain.value, item.query))

    @staticmethod
    def _task_keys(tasks: list[SearchTask]) -> set[tuple[str, str, str]]:
        return {RiskDiscoveryPipeline._task_key(task) for task in tasks}

    @staticmethod
    def _task_key(task: SearchTask) -> tuple[str, str, str]:
        params_key = ""
        if task.params:
            params_key = "|" + "|".join(f"{key}={task.params[key]}" for key in sorted(task.params))
        return (task.domain.value, task.source_hint, task.query + params_key)

    @staticmethod
    def _identifier_fanout_tasks(
        entity: InvestigationEntity,
        seen_task_keys: set[tuple[str, str, str]],
        round_index: int,
    ) -> list[SearchTask]:
        """Create high-authority follow-up tasks from official identifiers."""
        if entity.kind is not EntityKind.COMPANY:
            return []
        cik = RiskDiscoveryPipeline._entity_attribute(entity, "cik")
        if not cik:
            return []
        task = SearchTask(
            RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            entity.name,
            "sec_edgar_public_api",
            f"Fanout round {round_index}: collect SEC companyfacts financial metrics for the matched issuer.",
            19 + (round_index * 5),
            (),
            (),
            params={"cik": str(cik).zfill(10), "sec_endpoint": "companyfacts"},
        )
        return [] if RiskDiscoveryPipeline._task_key(task) in seen_task_keys else [task]

    @staticmethod
    def _public_graph_fanout_tasks(
        entity: InvestigationEntity,
        seen_task_keys: set[tuple[str, str, str]],
        round_index: int,
    ) -> list[SearchTask]:
        """Create public knowledge-graph detail tasks from exact entity ids."""
        if entity.kind is not EntityKind.COMPANY:
            return []
        wikidata_id = RiskDiscoveryPipeline._entity_attribute(entity, "wikidata_id")
        if not wikidata_id:
            return []
        task = SearchTask(
            RetrievalDomain.OWNERSHIP_CONTROL,
            entity.name,
            "wikidata_public_entity_graph",
            f"Fanout round {round_index}: collect public knowledge-graph key-person and organization relations.",
            17 + (round_index * 5),
            (),
            (EntityKind.PERSON, EntityKind.COMPANY),
            params={"wikidata_endpoint": "entitydata", "wikidata_id": wikidata_id},
        )
        return [] if RiskDiscoveryPipeline._task_key(task) in seen_task_keys else [task]

    @staticmethod
    def _entity_attribute(entity: InvestigationEntity, key: str) -> str:
        value = entity.attributes.get(key)
        if value not in (None, ""):
            return str(value)
        raw = entity.attributes.get("raw")
        if isinstance(raw, dict):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    async def _execute_search_task(
        self,
        plan: RetrievalPlan,
        seed_id: str,
        task: SearchTask,
        search_engine: Any,
        queried_sources: list[str],
        failed_sources: list[str],
        source_diagnostics: list[dict[str, Any]],
        *,
        query_timeout_seconds: float,
    ) -> None:
        try:
            result = await self._run_retrieval_query_with_timeout(
                plan,
                task,
                search_engine,
                query_timeout_seconds=query_timeout_seconds,
            )
        except _RetrievalQueryTimeout:
            source_name = task.source_hint or "search_engine"
            failed_sources.append(source_name)
            source_diagnostics.append(
                {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": source_name,
                    "status": "timeout",
                    "record_count": 0,
                    "ingested_count": 0,
                    "error": f"query timed out after {query_timeout_seconds:g} seconds",
                    "timeout_seconds": query_timeout_seconds,
                }
            )
            return
        except Exception as exc:
            failed_sources.append("search_engine")
            source_diagnostics.append(
                {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": "search_engine",
                    "status": "failed",
                    "record_count": 0,
                    "ingested_count": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return

        result_items = list(getattr(result, "results", []))
        if getattr(result, "unsupported_source_hint", False):
            source_name = str(getattr(result, "source_name", "") or task.source_hint or "search_engine")
            source_diagnostics.append(
                {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": source_name,
                    "status": "skipped_unsupported_source",
                    "record_count": 0,
                    "ingested_count": 0,
                    "reason": str(
                        getattr(
                            result,
                            "skip_reason",
                            "source hint is not supported by the selected retrieval tool",
                        )
                    ),
                }
            )
            return
        if not result_items:
            source_diagnostics.append(
                {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": "search_engine",
                    "status": "no_results",
                    "record_count": 0,
                    "ingested_count": 0,
                }
            )
            return

        for item in result_items:
            source_name = str(getattr(item, "source_name", "unknown"))
            queried_sources.append(source_name)
            if not getattr(item, "is_success", False):
                failed_sources.append(source_name)
                source_diagnostics.append(
                    {
                        **self._task_diagnostic_base(task),
                        "domain": task.domain.value,
                        "source_name": source_name,
                        "source_type": str(getattr(item, "source_type", "") or ""),
                        "status": "failed",
                        "record_count": 0,
                        "ingested_count": 0,
                        "error": str(getattr(item, "error", "") or ""),
                        "error_details": self._error_details(item),
                    }
                )
                continue
            records = self._standardized_records(item)
            evidence_items = EvidenceIngestor.ingest_query_result(
                plan.graph,
                seed_entity_id=seed_id,
                task=task,
                query_result=item,
            )
            source_diagnostics.append(
                diagnostic := {
                    **self._task_diagnostic_base(task),
                    "domain": task.domain.value,
                    "source_name": source_name,
                    "source_type": str(getattr(item, "source_type", "") or ""),
                    "status": "success" if evidence_items else "empty",
                    "record_count": len(records),
                    "ingested_count": len(evidence_items),
                    "record_quality": self._record_quality(item),
                    **self._query_result_diagnostic_metadata(item),
                }
            )
            self._append_child_source_diagnostics(
                parent=diagnostic,
                query_result=item,
                queried_sources=queried_sources,
                failed_sources=failed_sources,
                source_diagnostics=source_diagnostics,
            )

    async def _run_retrieval_query(
        self,
        plan: RetrievalPlan,
        task: SearchTask,
        search_engine: Any,
        *,
        query_timeout_seconds: float,
    ) -> Any:
        layer = task.effective_retrieval_layer()
        params = {
            "company": plan.seed_company,
            "domain": task.domain.value,
            "objective": task.objective,
            "retrieval_layer": layer.value,
            "query_timeout_seconds": query_timeout_seconds,
            **self._retrieval_layer_budget(layer),
            **dict(task.params),
        }
        timeout_kw = max(1, int(query_timeout_seconds))
        configured_sources = set(self._configured_source_names(search_engine))
        if task.source_hint in configured_sources and hasattr(search_engine, "search"):
            search_kwargs = {"params": params}
            if self._call_accepts_kw(getattr(search_engine, "search"), "timeout"):
                search_kwargs["timeout"] = timeout_kw
            return self._single_result_to_aggregated(
                await search_engine.search(
                    task.source_hint,
                    task.query,
                    **search_kwargs,
                )
            )
        if hasattr(search_engine, "search_available"):
            available_kwargs = {
                "params": params,
                "concurrency": 5,
            }
            if self._call_accepts_kw(getattr(search_engine, "search_available"), "timeout"):
                available_kwargs["timeout"] = timeout_kw
            return await search_engine.search_available(
                task.query,
                **available_kwargs,
            )
        if hasattr(search_engine, "search"):
            can_handle = getattr(search_engine, "can_handle_source_hint", None)
            if callable(can_handle) and not can_handle(task.source_hint):
                return SimpleNamespace(
                    results=[],
                    unsupported_source_hint=True,
                    source_name=task.source_hint,
                    skip_reason="source hint is not supported by the selected retrieval tool",
                )
            tool_result = await search_engine.search(task.query, "multi_datasource", **params)
            return self._tool_result_to_query_result(tool_result)
        raise TypeError("retrieval object must expose search_available(...) or search(...)")

    @classmethod
    def _retrieval_layer_budget(cls, layer: RetrievalLayer) -> dict[str, Any]:
        return dict(cls.LAYER_BUDGETS.get(layer, cls.LAYER_BUDGETS[RetrievalLayer.SPECIALIST]))

    async def _run_retrieval_query_with_timeout(
        self,
        plan: RetrievalPlan,
        task: SearchTask,
        search_engine: Any,
        *,
        query_timeout_seconds: float,
    ) -> Any:
        query_task = asyncio.create_task(
            self._run_retrieval_query(
                plan,
                task,
                search_engine,
                query_timeout_seconds=query_timeout_seconds,
            )
        )
        done, pending = await asyncio.wait({query_task}, timeout=query_timeout_seconds)
        if pending:
            query_task.cancel()
            with suppress(asyncio.CancelledError):
                await query_task
            raise _RetrievalQueryTimeout()
        return next(iter(done)).result()

    @staticmethod
    def _configured_source_names(search_engine: Any) -> list[str]:
        list_sources = getattr(search_engine, "list_sources", None)
        if not callable(list_sources):
            return []
        try:
            sources = list_sources()
        except Exception:
            return []
        return [str(item) for item in sources] if isinstance(sources, list) else []

    @staticmethod
    def _call_accepts_kw(method: Any, name: str) -> bool:
        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            return False
        return any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ) or name in signature.parameters

    @staticmethod
    def _single_result_to_aggregated(result: Any) -> Any:
        return SimpleNamespace(results=[result])

    @staticmethod
    def _default_task(plan: RetrievalPlan) -> SearchTask:
        court_tasks = plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)
        return court_tasks[0] if court_tasks else plan.tasks[0]

    @staticmethod
    def _task_diagnostic_base(task: SearchTask) -> dict[str, Any]:
        """Return task metadata that makes empty and failed retrieval actionable."""
        return {
            "query": task.query,
            "objective": task.objective,
            "source_hint": task.source_hint,
            "priority": task.priority,
            "retrieval_layer": task.effective_retrieval_layer().value,
            "expected_evidence": [item.value for item in task.expected_evidence],
            "fanout_entities": [item.value for item in task.fanout_entities],
            "source_profile": task.resolved_source_profile().to_dict(),
        }

    @staticmethod
    def _seed_entity_id(plan: RetrievalPlan) -> str:
        for entity_id, entity in plan.graph.entities.items():
            if entity.attributes.get("seed") is True:
                return entity_id
        normalized = "_".join(plan.seed_company.lower().split())
        return f"company:{normalized}"

    @staticmethod
    def _standardized_records(query_result: Any) -> list[dict[str, Any]]:
        metadata = getattr(query_result, "metadata", {}) or {}
        records = metadata.get("standardized_records", [])
        return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []

    @staticmethod
    def _record_quality(query_result: Any) -> dict[str, Any] | None:
        data = getattr(query_result, "data", {}) or {}
        if not isinstance(data, dict):
            return None
        quality = data.get("record_quality")
        return quality if isinstance(quality, dict) else None

    @staticmethod
    def _query_result_diagnostic_metadata(query_result: Any) -> dict[str, Any]:
        metadata = getattr(query_result, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return {}
        allowed = {
            "child_source_diagnostics",
            "qyyjt_public_plan_executed",
            "qyyjt_public_plan_failed",
            "qyyjt_public_plan_diagnostics",
            "selected_sources",
            "queried_sources",
            "failed_sources",
        }
        return {key: metadata[key] for key in allowed if key in metadata}

    @staticmethod
    def _append_child_source_diagnostics(
        *,
        parent: dict[str, Any],
        query_result: Any,
        queried_sources: list[str],
        failed_sources: list[str],
        source_diagnostics: list[dict[str, Any]],
    ) -> None:
        metadata = getattr(query_result, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return
        children = metadata.get("child_source_diagnostics")
        if not isinstance(children, list):
            return
        parent_source = str(parent.get("source_name") or "")
        for child in children:
            if not isinstance(child, dict):
                continue
            child_source = str(child.get("source_name") or "").strip()
            if not child_source:
                continue
            status = str(child.get("status") or "unknown").strip() or "unknown"
            source_diagnostics.append(
                {
                    **{
                        key: value
                        for key, value in parent.items()
                        if key
                        in {
                            "query",
                            "objective",
                            "source_hint",
                            "priority",
                            "retrieval_layer",
                            "expected_evidence",
                            "domain",
                        }
                    },
                    "source_name": child_source,
                    "source_type": str(child.get("source_type") or "child_source"),
                    "status": status,
                    "record_count": int(child.get("record_count") or 0),
                    "ingested_count": int(child.get("ingested_count") or 0),
                    "error": child.get("error"),
                    "parent_source_name": parent_source,
                    "diagnostic_scope": "child_source",
                }
            )
            if status in {"failed", "timeout"}:
                failed_sources.append(child_source)
            elif status not in {"skipped_unsupported_source"}:
                queried_sources.append(child_source)

    @staticmethod
    def _error_details(query_result: Any) -> dict[str, Any] | None:
        metadata = getattr(query_result, "metadata", {}) or {}
        if isinstance(metadata, dict) and isinstance(metadata.get("error_details"), dict):
            return metadata["error_details"]
        return None

    @staticmethod
    def _tool_result_to_query_result(tool_result: Any) -> Any:
        data = getattr(tool_result, "data", {}) or {}
        records = RiskDiscoveryPipeline._extract_standardized_records(data)
        source_names = getattr(tool_result, "sources", []) or []
        source_name = "tool_provider"
        if source_names:
            source_name = str(source_names[0]).split(":", 1)[-1]
        source_type = "tool_provider"
        if isinstance(data, dict):
            source_name = str(data.get("source_name") or data.get("source") or source_name)
            source_type = str(data.get("source_type") or source_type)
        metadata = {"standardized_records": records}
        if isinstance(data, dict):
            if isinstance(data.get("source_diagnostics"), list):
                metadata["child_source_diagnostics"] = data["source_diagnostics"]
            for key in (
                "qyyjt_public_plan_executed",
                "qyyjt_public_plan_failed",
                "qyyjt_public_plan_diagnostics",
                "selected_sources",
                "queried_sources",
                "failed_sources",
            ):
                if key in data:
                    metadata[key] = data[key]
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    source_name=source_name,
                    source_type=source_type,
                    is_success=bool(getattr(tool_result, "ok", False)),
                    error=getattr(tool_result, "error", None),
                    data=data,
                    metadata=metadata,
                )
            ]
        )

    @staticmethod
    def _extract_standardized_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            records = payload.get("standardized_records")
            if isinstance(records, list):
                return [item for item in records if isinstance(item, dict)]
            aggregated = payload.get("aggregated")
            if isinstance(aggregated, dict):
                extracted: list[dict[str, Any]] = []
                for result in aggregated.get("results", []):
                    extracted.extend(RiskDiscoveryPipeline._extract_standardized_records(result))
                return extracted
            nested_results = payload.get("results")
            if isinstance(nested_results, list):
                extracted = []
                for result in nested_results:
                    extracted.extend(RiskDiscoveryPipeline._extract_standardized_records(result))
                return extracted
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                return RiskDiscoveryPipeline._extract_standardized_records(metadata)
        return []

    @staticmethod
    def _build_retrieval_summary(
        diagnostics: list[dict[str, Any]],
        *,
        evidence_count: int,
        risk_event_count: int,
        plan: RetrievalPlan | None = None,
        source_routing: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        by_domain: dict[str, dict[str, int]] = {}
        ingested_count = 0
        record_count = 0
        quality_reports = 0
        quality_ok = 0
        quality_findings = 0
        quality_codes: dict[str, int] = {}
        public_plan_summary = {
            "qyyjt_public_plan_executed": 0,
            "qyyjt_public_plan_failed": 0,
            "triggered_attempts": 0,
            "domains": {},
        }

        for item in diagnostics:
            status = str(item.get("status") or "unknown")
            domain = str(item.get("domain") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
            domain_stats = by_domain.setdefault(
                domain,
                {
                    "attempts": 0,
                    "success": 0,
                    "empty": 0,
                    "failed": 0,
                    "timeout": 0,
                    "records": 0,
                    "ingested": 0,
                },
            )
            domain_stats["attempts"] += 1
            domain_stats[status] = domain_stats.get(status, 0) + 1
            records = int(item.get("record_count") or 0)
            ingested = int(item.get("ingested_count") or 0)
            domain_stats["records"] += records
            domain_stats["ingested"] += ingested
            record_count += records
            ingested_count += ingested
            quality = item.get("record_quality")
            if isinstance(quality, dict):
                quality_reports += 1
                if quality.get("ok") is True:
                    quality_ok += 1
                finding_count = int(quality.get("finding_count") or 0)
                quality_findings += finding_count
                for finding in quality.get("findings", []):
                    if isinstance(finding, dict):
                        code = str(finding.get("code") or "unknown")
                        quality_codes[code] = quality_codes.get(code, 0) + 1
            executed = int(item.get("qyyjt_public_plan_executed") or 0)
            failed = int(item.get("qyyjt_public_plan_failed") or 0)
            if executed or failed:
                public_plan_summary["qyyjt_public_plan_executed"] += executed
                public_plan_summary["qyyjt_public_plan_failed"] += failed
                public_plan_summary["triggered_attempts"] += 1
                domains = public_plan_summary["domains"]
                domains[domain] = domains.get(domain, 0) + executed

        planned_domains = sorted(
            domain.value for domain in plan.coverage_domains
        ) if plan is not None else []
        attempted_domains = sorted(
            domain for domain, stats in by_domain.items()
            if int(stats.get("attempts") or 0) > 0
        )
        domains_with_evidence = sorted(
            domain for domain, stats in by_domain.items()
            if int(stats.get("ingested") or 0) > 0
        )
        missing_domains = sorted(set(planned_domains) - set(attempted_domains))
        domains_without_evidence = sorted(set(attempted_domains) - set(domains_with_evidence))
        execution_state = RiskDiscoveryPipeline._execution_state(
            diagnostics,
            evidence_count=evidence_count,
            risk_event_count=risk_event_count,
            source_routing=source_routing,
        )

        summary = {
            "run_id": run_id,
            "execution_state": execution_state,
            "attempts": len(diagnostics),
            "status_counts": statuses,
            "record_count": record_count,
            "ingested_count": ingested_count,
            "evidence_count": evidence_count,
            "risk_event_count": risk_event_count,
            "coverage": {
                "planned_domain_count": len(planned_domains),
                "attempted_domain_count": len(attempted_domains),
                "domains_with_evidence_count": len(domains_with_evidence),
                "planned_domains": planned_domains,
                "attempted_domains": attempted_domains,
                "domains_with_evidence": domains_with_evidence,
                "missing_domains": missing_domains,
                "domains_without_evidence": domains_without_evidence,
            },
            "next_actions": RiskDiscoveryPipeline._next_actions(
                execution_state=execution_state,
                statuses=statuses,
                missing_domains=missing_domains,
                domains_without_evidence=domains_without_evidence,
                source_routing=source_routing,
            ),
            "by_domain": by_domain,
            "record_quality": {
                "report_count": quality_reports,
                "ok_count": quality_ok,
                "finding_count": quality_findings,
                "finding_codes": quality_codes,
            },
            "public_plan_summary": public_plan_summary,
            "entity_resolution": RiskDiscoveryPipeline._entity_resolution_summary(plan),
        }
        if source_routing is not None:
            summary["source_routing"] = source_routing
        return summary

    @staticmethod
    def _finalize_source_diagnostics(run_id: str, diagnostics: list[dict[str, Any]]) -> None:
        for index, item in enumerate(diagnostics, start=1):
            item.setdefault("run_id", run_id)
            item.setdefault("trace_id", f"{run_id}:source:{index:03d}")
            item.setdefault("failure_category", RiskDiscoveryPipeline._failure_category(item))

    @staticmethod
    def _failure_category(item: dict[str, Any]) -> str:
        status = str(item.get("status") or "").strip().lower()
        error = str(item.get("error") or "").strip().lower()
        if status in {"success"}:
            return "none"
        if status in {"empty", "no_results"}:
            return "empty_result"
        if status == "timeout" or "timeout" in error or "timed out" in error:
            return "timeout"
        if status == "failed":
            if "unauthorized" in error or "forbidden" in error or "permission" in error:
                return "authorization"
            if "rate" in error and "limit" in error:
                return "rate_limit"
            if "connection" in error or "network" in error or "dns" in error:
                return "network"
            return "connector_error"
        if not status:
            return "unknown"
        return status

    @staticmethod
    def _entity_resolution_summary(plan: RetrievalPlan | None) -> dict[str, Any]:
        """Summarize how strongly collected evidence matches the seed subject."""
        if plan is None:
            return {
                "evidence_with_match_count": 0,
                "strong_match_count": 0,
                "review_match_count": 0,
                "weak_match_count": 0,
                "unknown_match_count": 0,
                "level_counts": {},
                "average_score": None,
            }

        level_counts: dict[str, int] = {}
        scores: list[float] = []
        unknown = 0
        for evidence in plan.graph.evidence.values():
            match = evidence.entity_match
            if not isinstance(match, dict):
                unknown += 1
                continue
            level = str(match.get("level") or "unknown")
            if level == "unknown":
                unknown += 1
                continue
            level_counts[level] = level_counts.get(level, 0) + 1
            try:
                scores.append(float(match.get("score")))
            except (TypeError, ValueError):
                pass

        strong = level_counts.get("exact", 0) + level_counts.get("strong", 0)
        review = level_counts.get("review", 0)
        weak = level_counts.get("weak", 0)
        average = round(sum(scores) / len(scores), 4) if scores else None
        return {
            "evidence_with_match_count": sum(level_counts.values()),
            "strong_match_count": strong,
            "review_match_count": review,
            "weak_match_count": weak,
            "unknown_match_count": unknown,
            "level_counts": level_counts,
            "average_score": average,
        }

    @staticmethod
    def _execution_state(
        diagnostics: list[dict[str, Any]],
        *,
        evidence_count: int,
        risk_event_count: int,
        source_routing: dict[str, Any] | None,
    ) -> str:
        if risk_event_count > 0:
            return "risk_events_found"
        if evidence_count > 0:
            return "evidence_found"
        if not diagnostics:
            if source_routing and int(source_routing.get("available_count") or 0) == 0:
                return "no_available_sources"
            return "not_executed"
        statuses = {str(item.get("status") or "unknown") for item in diagnostics}
        if statuses <= {"failed", "timeout"}:
            return "all_sources_failed"
        if statuses <= {"no_results", "empty", "skipped_unsupported_source"}:
            return "no_evidence_found"
        if "failed" in statuses or "timeout" in statuses:
            return "partial_source_failure"
        return "no_evidence_found"

    @staticmethod
    def _next_actions(
        *,
        execution_state: str,
        statuses: dict[str, int],
        missing_domains: list[str],
        domains_without_evidence: list[str],
        source_routing: dict[str, Any] | None,
    ) -> list[str]:
        actions: list[str] = []
        available_count = int((source_routing or {}).get("available_count") or 0)
        configured_count = int((source_routing or {}).get("configured_count") or 0)
        if execution_state == "not_executed":
            actions.append("Run with --offline-fixture for a smoke test or provide --config for live datasource routing.")
        if configured_count > 0 and available_count == 0:
            actions.append("No configured datasource is currently available; inspect health_reports before treating this as a clean company.")
        if statuses.get("failed") or statuses.get("timeout"):
            actions.append("Review failed source or timed-out source diagnostics and retry transient connector failures before final risk judgment.")
        if statuses.get("no_results") or statuses.get("empty"):
            actions.append("Empty retrieval is a coverage signal, not proof of no risk; expand source coverage or refine queries for empty domains.")
        if statuses.get("skipped_unsupported_source"):
            actions.append("Some planned sources were skipped because the selected retrieval tool cannot execute them; provide a datasource config with those connectors enabled.")
        if missing_domains:
            actions.append("Execute missing planned domains: " + ", ".join(missing_domains[:6]))
        if domains_without_evidence:
            actions.append("Prioritize new sources for evidence-poor domains: " + ", ".join(domains_without_evidence[:6]))
        if execution_state == "risk_events_found":
            actions.append("Escalate high-severity events into verification and monitoring before report generation.")
        if not actions:
            actions.append("Continue scheduled monitoring and compare future scans against the event ledger.")
        return actions

    @staticmethod
    def _source_routing_snapshot(search_engine: Any | None) -> dict[str, Any] | None:
        """Return a compact datasource routing snapshot for CLI/API diagnostics."""
        if search_engine is None:
            return None

        def call_optional(name: str, default: Any) -> Any:
            method = getattr(search_engine, name, None)
            if not callable(method):
                return default
            if inspect.iscoroutinefunction(method):
                return default
            try:
                value = method()
                return value
            except Exception as exc:
                return {"error": f"{type(exc).__name__}: {exc}"}

        configured_sources = call_optional("list_sources", [])
        available_sources = call_optional("available_sources", [])
        health = RiskDiscoveryPipeline._source_health_snapshot(search_engine)
        if health is None:
            health = call_optional("health_check", {})
        health_reports = RiskDiscoveryPipeline._source_health_reports_snapshot(search_engine)
        if health_reports is None:
            health_reports = call_optional("health_report", {})

        if not isinstance(configured_sources, list):
            configured_sources = []
        if not isinstance(available_sources, list):
            available_sources = []
        if not isinstance(health, dict):
            health = {}
        if not isinstance(health_reports, dict):
            health_reports = {}

        configured_set = {str(item) for item in configured_sources}
        available_set = {str(item) for item in available_sources}
        unavailable = sorted(configured_set - available_set)

        return {
            "configured_count": len(configured_set),
            "available_count": len(available_set),
            "configured_sources": sorted(configured_set),
            "available_sources": sorted(available_set),
            "unavailable_sources": unavailable,
            "health": {str(key): bool(value) for key, value in health.items()},
            "health_reports": {
                str(key): value
                for key, value in health_reports.items()
                if isinstance(value, dict)
            },
        }

    @staticmethod
    def _source_health_snapshot(search_engine: Any) -> dict[str, bool] | None:
        get_instance = getattr(search_engine, "get_instance", None)
        if not callable(get_instance):
            return None
        try:
            instance = get_instance()
        except Exception:
            return None
        manager = getattr(instance, "_manager", None)
        health = getattr(manager, "_health_status", None)
        if isinstance(health, dict):
            return {str(key): bool(value) for key, value in health.items()}
        return None

    @staticmethod
    def _source_health_reports_snapshot(search_engine: Any) -> dict[str, dict[str, Any]] | None:
        get_instance = getattr(search_engine, "get_instance", None)
        if not callable(get_instance):
            return None
        try:
            instance = get_instance()
        except Exception:
            return None
        manager = getattr(instance, "_manager", None)
        reports = getattr(manager, "_health_reports", None)
        if not isinstance(reports, dict):
            return None

        normalized: dict[str, dict[str, Any]] = {}
        for key, value in reports.items():
            if hasattr(value, "to_dict") and callable(value.to_dict):
                normalized[str(key)] = value.to_dict()
            elif isinstance(value, dict):
                normalized[str(key)] = value
        return normalized


def offline_enforcement_fixture(company: str) -> list[dict[str, Any]]:
    """Return a deterministic public-record fixture for executable smoke tests."""
    return [
        {
            "source_name": "offline_court_fixture",
            "source_type": "local_file",
            "source_hint": "court_and_credit_sources",
            "entity": company,
            "title": f"{company} public enforcement notice",
            "summary": (
                "Offline fixture: public enforcement signal found; 被执行 public record requires verification. "
                "Case status, amount, timeline, and current performance status need verification."
            ),
            "url": "https://example.invalid/court/enforcement/demo",
            "published_at": "2026-06-18",
            "confidence": 0.82,
            "evidence": [
                {"claim": "A public court record indicates a possible 被执行 enforcement-related signal."},
                {"claim": "Follow-up should verify docket id, court, amount, and performance status."},
            ],
        }
    ]
