#!/usr/bin/env python3
"""Tests for the executable risk-discovery pipeline."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from adapters.multi_datasource import AggregatedResult, QueryResult, QueryStatus
from core.interfaces import ToolResult
from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture
from core.risk_event_store import RiskEventStore


def test_offline_pipeline_persists_alert_payload(tmp_path) -> None:
    store = RiskEventStore(tmp_path / "risk-events.jsonl")
    pipeline = RiskDiscoveryPipeline(risk_event_store=store)

    result = asyncio.run(async_run_pipeline(pipeline, "Demo Technology Co., Ltd."))

    assert result.ok is True
    assert result.run_id.startswith("risk:")
    assert result.to_dict()["run_id"] == result.run_id
    assert result.evidence_count == 1
    assert result.risk_event_count == 1
    assert result.risk_event_summary["alert_count"] == 1
    assert result.to_dict()["first_alert"]["event"]["severity"] == "high"
    assert result.to_dict()["first_alert"]["event"]["entity_ids"] == [
        "company:demo_technology_co.,_ltd."
    ]
    assert result.queried_sources == ["offline_court_fixture"]
    assert result.retrieval_summary["execution_state"] == "risk_events_found"
    assert result.retrieval_summary["run_id"] == result.run_id
    assert result.retrieval_summary["status_counts"] == {"success": 1}
    assert result.retrieval_summary["record_count"] == 1
    assert result.retrieval_summary["ingested_count"] == 1
    assert result.retrieval_summary["entity_resolution"]["strong_match_count"] == 1
    assert result.retrieval_summary["entity_resolution"]["average_score"] == 1.0
    assert result.retrieval_summary["coverage"]["attempted_domains"] == [
        "court_enforcement"
    ]
    assert result.retrieval_summary["coverage"]["missing_domains"]
    assert result.retrieval_summary["next_actions"]
    assert result.source_diagnostics[0]["query"]
    assert result.source_diagnostics[0]["run_id"] == result.run_id
    assert result.source_diagnostics[0]["trace_id"].startswith(result.run_id)
    assert result.source_diagnostics[0]["failure_category"] == "none"
    assert result.source_diagnostics[0]["source_profile"]["provenance_required"] is True
    assert store.summary()["total_events"] == 1


@dataclass
class FakeSearchEngine:
    include_empty: bool = False
    include_failed: bool = False

    def list_sources(self) -> list[str]:
        sources = ["healthy_public_api"]
        if self.include_empty:
            sources.append("empty_public_api")
        if self.include_failed:
            sources.append("failed_public_api")
        sources.append("disabled_public_api")
        return sources

    def available_sources(self) -> list[str]:
        sources = ["healthy_public_api"]
        if self.include_empty:
            sources.append("empty_public_api")
        if self.include_failed:
            sources.append("failed_public_api")
        return sources

    def health_check(self) -> dict[str, bool]:
        return {
            source: source != "disabled_public_api"
            for source in self.list_sources()
        }

    def health_report(self) -> dict[str, dict[str, Any]]:
        return {
            source: {
                "source_name": source,
                "source_type": "rest_api",
                "ok": source != "disabled_public_api",
                "status": "up" if source != "disabled_public_api" else "down",
                "endpoint": f"https://example.invalid/{source}",
            }
            for source in self.list_sources()
        }

    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        results = [
            QueryResult(
                source_name="healthy_public_api",
                source_type="rest_api",
                status=QueryStatus.SUCCESS,
                metadata={
                    "standardized_records": [
                        {
                            "source_name": "healthy_public_api",
                            "source_type": "rest_api",
                            "entity": params["company"],
                            "title": f"{params['company']} administrative penalty notice",
                            "summary": "The company has a public administrative penalty signal.",
                            "url": "https://example.invalid/admin/demo",
                            "confidence": 0.75,
                            "evidence": [{"claim": "行政处罚 public record needs verification."}],
                        }
                    ]
                },
            )
        ]
        if self.include_empty:
            results.append(
                QueryResult(
                    source_name="empty_public_api",
                    source_type="rest_api",
                    status=QueryStatus.SUCCESS,
                    metadata={"standardized_records": []},
                )
            )
        if self.include_failed:
            results.append(
                QueryResult(
                    source_name="failed_public_api",
                    source_type="rest_api",
                    status=QueryStatus.FAILED,
                    error=RuntimeError("temporary source outage"),
                )
            )
        return AggregatedResult(
            results=results
        )


class LayerRecordingSearchEngine:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def available_sources(self) -> list[str]:
        return ["layer_public_api"]

    def health_check(self) -> dict[str, bool]:
        return {"layer_public_api": True}

    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        self.calls.append(dict(params))
        return AggregatedResult(
            results=[
                QueryResult(
                    source_name="layer_public_api",
                    source_type="rest_api",
                    status=QueryStatus.SUCCESS,
                    metadata={"standardized_records": []},
                )
            ]
        )


def test_pipeline_executes_search_tasks_by_progressive_retrieval_layer(tmp_path) -> None:
    engine = LayerRecordingSearchEngine()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Demo Layered Execution Co.",
            search_engine=engine,
            retrieval_concurrency=8,
            fanout_rounds=0,
        )
    )

    order = {
        "entity_anchor": 0,
        "overview": 1,
        "prioritized_drilldown": 2,
        "specialist": 3,
    }
    assert engine.calls
    layers = [str(item.get("retrieval_layer")) for item in engine.calls]
    assert layers == sorted(layers, key=lambda item: order[item])
    budgets = {item["retrieval_layer"]: item for item in engine.calls}
    assert budgets["entity_anchor"]["result_limit"] == 3
    assert budgets["entity_anchor"]["source_budget"] == "anchor"
    assert budgets["specialist"]["result_limit"] == 12
    assert budgets["specialist"]["source_budget"] == "specialist"
    assert {item["retrieval_layer"] for item in result.source_diagnostics} >= {
        "entity_anchor",
        "overview",
        "prioritized_drilldown",
        "specialist",
    }


@dataclass
class DirectSourceSearchEngine:
    direct_calls: list[tuple[str, str]] = None
    available_calls: int = 0

    def __post_init__(self):
        if self.direct_calls is None:
            self.direct_calls = []

    def list_sources(self) -> list[str]:
        return ["gleif_lei_public_api"]

    def available_sources(self) -> list[str]:
        return ["gleif_lei_public_api"]

    async def search(self, source_name: str, query: str, params: dict[str, Any] | None = None, **kwargs):
        self.direct_calls.append((source_name, query))
        return QueryResult(
            source_name=source_name,
            source_type="rest_api",
            status=QueryStatus.SUCCESS,
            metadata={
                "standardized_records": [
                    {
                        "source_name": source_name,
                        "source_type": "rest_api",
                        "source_hint": source_name,
                        "entity": params["company"],
                        "title": f"{params['company']} official identity record",
                        "summary": "Official public identity lead.",
                        "confidence": 0.82,
                    }
                ]
            },
        )

    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        self.available_calls += 1
        return AggregatedResult(results=[])


def test_pipeline_routes_task_source_hint_to_exact_configured_source(tmp_path) -> None:
    from core.official_public_smoke import build_official_public_smoke_plan

    engine = DirectSourceSearchEngine()
    plan = build_official_public_smoke_plan("Demo Direct Source Co., Ltd.")
    plan.tasks = [task for task in plan.tasks if task.source_hint == "gleif_lei_public_api"]
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Demo Direct Source Co., Ltd.",
            search_engine=engine,
            existing_plan=plan,
        )
    )

    assert result.evidence_count == 1
    assert engine.direct_calls == [("gleif_lei_public_api", "Demo Direct Source Co., Ltd.")]
    assert engine.available_calls == 0


def test_pipeline_ingests_search_engine_standardized_records(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run("Demo Manufacturing Co., Ltd.", search_engine=FakeSearchEngine())
    )

    assert result.queried_sources
    assert result.failed_sources == []
    assert result.evidence_count >= 1
    assert result.risk_event_summary["store"]["total_events"] >= 1
    assert result.retrieval_summary["status_counts"]["success"] >= 1
    assert result.retrieval_summary["ingested_count"] >= 1
    assert result.retrieval_summary["entity_resolution"]["strong_match_count"] >= 1
    assert result.retrieval_summary["coverage"]["planned_domain_count"] >= 10
    assert result.retrieval_summary["coverage"]["domains_with_evidence"]
    assert result.retrieval_summary["source_routing"]["configured_count"] == 2
    assert result.retrieval_summary["source_routing"]["available_sources"] == [
        "healthy_public_api"
    ]
    assert result.retrieval_summary["source_routing"]["unavailable_sources"] == [
        "disabled_public_api"
    ]
    assert (
        result.retrieval_summary["source_routing"]["health_reports"]["healthy_public_api"]["status"]
        == "up"
    )
    assert (
        result.retrieval_summary["source_routing"]["health_reports"]["disabled_public_api"]["status"]
        == "down"
    )


def test_pipeline_reports_empty_and_failed_sources(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Demo Monitoring Co., Ltd.",
            search_engine=FakeSearchEngine(include_empty=True, include_failed=True),
        )
    )

    assert "failed_public_api" in result.failed_sources
    assert set(result.queried_sources) == {
        "empty_public_api",
        "failed_public_api",
        "healthy_public_api",
    }
    assert result.retrieval_summary["status_counts"]["success"] >= 1
    assert result.retrieval_summary["status_counts"]["empty"] >= 1
    assert result.retrieval_summary["status_counts"]["failed"] >= 1
    assert any(item["status"] == "empty" for item in result.source_diagnostics)
    assert any(item["status"] == "failed" for item in result.source_diagnostics)
    assert any(item["failure_category"] == "empty_result" for item in result.source_diagnostics)
    assert any(item["failure_category"] == "connector_error" for item in result.source_diagnostics)
    assert all(item["trace_id"].startswith(result.run_id) for item in result.source_diagnostics)
    assert any(item["source_type"] == "rest_api" for item in result.source_diagnostics)
    assert result.retrieval_summary["execution_state"] in {
        "risk_events_found",
        "partial_source_failure",
    }
    assert any("failed source" in action.lower() for action in result.retrieval_summary["next_actions"])


@dataclass
class RaisingSearchEngine:
    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        raise TimeoutError("source routing timeout")


@dataclass
class ErrorDetailSearchEngine:
    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        return AggregatedResult(
            results=[
                QueryResult(
                    source_name="official_public_api",
                    source_type="rest_api",
                    status=QueryStatus.FAILED,
                    error=RuntimeError("query failed"),
                    metadata={
                        "error_details": {
                            "type": "ClientResponseError",
                            "http_status": 403,
                            "url": "https://example.invalid/public-api",
                        }
                    },
                )
            ]
        )


@dataclass
class SlowSearchEngine:
    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        await asyncio.sleep(10)
        return AggregatedResult(results=[])


def test_pipeline_surfaces_structured_error_details(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run("Demo Error Details Co., Ltd.", search_engine=ErrorDetailSearchEngine())
    )

    assert result.source_diagnostics[0]["error_details"] == {
        "type": "ClientResponseError",
        "http_status": 403,
        "url": "https://example.invalid/public-api",
    }


def test_pipeline_times_out_slow_search_tasks_without_hanging(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Demo Slow Source Co., Ltd.",
            search_engine=SlowSearchEngine(),
            retrieval_concurrency=3,
            query_timeout_seconds=0.01,
        )
    )

    assert result.ok is False
    assert result.evidence_count == 0
    assert result.retrieval_summary["execution_state"] == "all_sources_failed"
    assert result.retrieval_summary["status_counts"]["timeout"] == len(result.source_diagnostics)
    assert result.failed_sources
    assert all(item["status"] == "timeout" for item in result.source_diagnostics)
    assert all(item["failure_category"] == "timeout" for item in result.source_diagnostics)
    assert all(item["timeout_seconds"] == 0.1 for item in result.source_diagnostics)
    assert any("timed-out source diagnostics" in action for action in result.retrieval_summary["next_actions"])


def test_pipeline_reports_search_engine_exceptions(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run("Demo Timeout Co., Ltd.", search_engine=RaisingSearchEngine())
    )

    assert result.failed_sources == ["search_engine"]
    assert result.ok is False
    assert result.retrieval_summary["execution_state"] == "all_sources_failed"
    assert result.retrieval_summary["status_counts"]["failed"] == len(
        result.source_diagnostics
    )
    assert result.evidence_count == 0
    assert result.source_diagnostics[0]["objective"]
    assert result.source_diagnostics[0]["source_hint"]


@dataclass
class TrackingSearchEngine:
    active: int = 0
    max_active: int = 0

    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return AggregatedResult(results=[])


def test_pipeline_runs_retrieval_tasks_concurrently(tmp_path) -> None:
    search_engine = TrackingSearchEngine()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Demo Concurrent Co., Ltd.",
            search_engine=search_engine,
            retrieval_concurrency=4,
        )
    )

    assert search_engine.max_active > 1
    assert result.ok is True
    assert result.retrieval_summary["execution_state"] == "no_evidence_found"
    assert result.retrieval_summary["attempts"] == len(result.source_diagnostics)
    assert result.retrieval_summary["status_counts"]["no_results"] >= 1


@dataclass
class ToolSearchEngine:
    async def search(self, query: str, tool_type: str, **kwargs) -> ToolResult:
        return ToolResult(
            ok=True,
            data={
                "source_name": "tool_api",
                "source_type": "rest_api",
                "standardized_records": [
                    {
                        "source_name": "tool_api",
                        "source_type": "rest_api",
                        "entity": kwargs["company"],
                        "title": f"{kwargs['company']} public filing",
                        "summary": "Tool provider returned a public filing signal.",
                        "confidence": 0.67,
                        "evidence": [{"claim": "公开备案 record needs verification."}],
                        "risk_events": [
                            {
                                "category": "administrative_risk",
                                "severity": "high",
                                "title": "Structured tool risk signal",
                                "rationale": "Tool provider returned a structured risk event.",
                                "status": "open",
                            }
                        ],
                    }
                ],
                "record_quality": {
                    "ok": True,
                    "record_count": 1,
                    "finding_count": 0,
                    "findings": [],
                },
            },
            sources=["tool:api"],
        )


def test_pipeline_accepts_tool_provider_search(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run("Demo Tool Co., Ltd.", search_engine=ToolSearchEngine())
    )

    assert result.queried_sources == ["tool_api"]
    assert result.retrieval_summary["status_counts"]["success"] >= 1
    assert result.source_diagnostics[0]["record_quality"]["ok"] is True
    assert result.retrieval_summary["record_quality"]["report_count"] >= 1
    assert result.retrieval_summary["record_quality"]["ok_count"] >= 1
    assert result.risk_event_summary["alert_count"] >= 1
    assert result.graph.risk_events[0].title == "Structured tool risk signal"


@dataclass
class FanoutSearchEngine:
    queries: list[str] = None

    def __post_init__(self):
        if self.queries is None:
            self.queries = []

    async def search_available(self, query: str, params: dict[str, Any], concurrency: int = 5):
        self.queries.append(query)
        records = []
        if "actual controller" not in query.lower():
            records = [
                {
                    "source_name": "registry_public_api",
                    "source_type": "official_platform",
                    "source_hint": "registry_sources",
                    "entity": params["company"],
                    "title": f"{params['company']} registry profile",
                    "summary": "Public registry profile names Bob Li as actual controller.",
                    "url": "https://example.invalid/registry/fanout",
                    "confidence": 0.86,
                    "raw": {"actual_controller": {"name": "Bob Li"}},
                    "evidence": [{"claim": "Bob Li is a public actual-controller candidate."}],
                }
            ]
        return AggregatedResult(
            results=[
                QueryResult(
                    source_name="registry_public_api",
                    source_type="official_platform",
                    status=QueryStatus.SUCCESS,
                    metadata={"standardized_records": records},
                )
            ]
        )


@dataclass
class SecIdentifierFanoutSearchEngine:
    calls: list[tuple[str, str, dict[str, Any]]] = None

    def __post_init__(self):
        if self.calls is None:
            self.calls = []

    def list_sources(self) -> list[str]:
        return ["sec_edgar_public_api"]

    def available_sources(self) -> list[str]:
        return ["sec_edgar_public_api"]

    async def search(self, source_name: str, query: str, params: dict[str, Any] | None = None, **kwargs):
        params = dict(params or {})
        self.calls.append((source_name, query, params))
        if params.get("sec_endpoint") == "companyfacts":
            records = [
                {
                    "source_name": source_name,
                    "source_type": "rest_api",
                    "source_hint": source_name,
                    "entity": "Apple Inc.",
                    "title": "SEC EDGAR company facts: Apple Inc.",
                    "summary": "cik=0000320193; revenue=391035000000; operating_cash_flow=110543000000",
                    "confidence": 0.78,
                    "entity_match": {"level": "strong", "score": 0.98},
                    "evidence": [
                        {
                            "provider": "SEC EDGAR companyfacts",
                            "cik": "0000320193",
                            "revenue": 391035000000,
                            "operating_cash_flow": 110543000000,
                        }
                    ],
                }
            ]
        else:
            records = [
                {
                    "source_name": source_name,
                    "source_type": "rest_api",
                    "source_hint": source_name,
                    "entity": "Apple Inc.",
                    "title": "SEC EDGAR company ticker match: Apple Inc.",
                    "summary": "ticker=AAPL; cik=0000320193",
                    "confidence": 0.62,
                    "raw": {"ticker": "AAPL", "cik_str": 320193},
                    "evidence": [
                        {
                            "provider": "SEC EDGAR",
                            "ticker": "AAPL",
                            "cik": "0000320193",
                        }
                    ],
                }
            ]
        return QueryResult(
            source_name=source_name,
            source_type="rest_api",
            status=QueryStatus.SUCCESS,
            metadata={"standardized_records": records},
        )


@dataclass
class WikidataEntityDataFanoutSearchEngine:
    calls: list[tuple[str, str, dict[str, Any]]] = None

    def __post_init__(self):
        if self.calls is None:
            self.calls = []

    def list_sources(self) -> list[str]:
        return ["wikidata_public_entity_graph"]

    def available_sources(self) -> list[str]:
        return ["wikidata_public_entity_graph"]

    async def search(self, source_name: str, query: str, params: dict[str, Any] | None = None, **kwargs):
        params = dict(params or {})
        self.calls.append((source_name, query, params))
        if params.get("wikidata_endpoint") == "entitydata":
            records = [
                {
                    "source_name": source_name,
                    "source_type": "rest_api",
                    "source_hint": source_name,
                    "entity": "Apple Inc.",
                    "title": "Wikidata entity data: Apple Inc.",
                    "summary": "relationships=chief_executive_officer:Tim Cook, founder:Steve Jobs",
                    "confidence": 0.7,
                    "wikidata_id": "Q312",
                    "wikidata_endpoint": "entitydata",
                    "entity_match": {"level": "exact", "score": 1.0},
                    "entities": [
                        {
                            "kind": "person",
                            "name": "Tim Cook",
                            "relation": "chief_executive_officer",
                            "confidence": 0.72,
                            "source": "Wikidata",
                            "wikidata_id": "Q19837",
                        },
                        {
                            "kind": "person",
                            "name": "Steve Jobs",
                            "relation": "founder",
                            "confidence": 0.72,
                            "source": "Wikidata",
                            "wikidata_id": "Q19848",
                        },
                    ],
                    "evidence": [{"provider": "Wikidata", "wikidata_id": "Q312"}],
                }
            ]
        else:
            records = [
                {
                    "source_name": source_name,
                    "source_type": "rest_api",
                    "source_hint": source_name,
                    "entity": "Apple Inc.",
                    "title": "Wikidata entity graph match: Apple Inc.",
                    "summary": "wikidata_id=Q312",
                    "confidence": 0.56,
                    "raw": {"wikidata_id": "Q312"},
                    "evidence": [{"provider": "Wikidata", "wikidata_id": "Q312"}],
                }
            ]
        return QueryResult(
            source_name=source_name,
            source_type="rest_api",
            status=QueryStatus.SUCCESS,
            metadata={"standardized_records": records},
        )


def test_pipeline_fans_out_sec_cik_to_companyfacts_financial_quality(tmp_path) -> None:
    from core.one_click_defaults import build_default_one_click_plan

    engine = SecIdentifierFanoutSearchEngine()
    plan = build_default_one_click_plan("Apple Inc.")
    plan.tasks = [task for task in plan.tasks if task.source_hint == "sec_edgar_public_api"]
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Apple Inc.",
            search_engine=engine,
            existing_plan=plan,
            fanout_rounds=1,
            max_fanout_tasks=4,
        )
    )

    assert result.ok is True
    assert any(call[2].get("sec_endpoint") == "companyfacts" for call in engine.calls)
    assert any(call[2].get("cik") == "0000320193" for call in engine.calls)
    assert any("company facts" in evidence.title.lower() for evidence in result.graph.evidence.values())
    apple = result.graph.entities["company:apple_inc."]
    assert apple.attributes["cik"] == "320193"
    assert apple.attributes["ticker"] == "AAPL"


def test_pipeline_fans_out_wikidata_qid_to_key_people(tmp_path) -> None:
    from core.one_click_defaults import build_default_one_click_plan

    engine = WikidataEntityDataFanoutSearchEngine()
    plan = build_default_one_click_plan("Apple Inc.")
    plan.tasks = [task for task in plan.tasks if task.source_hint == "wikidata_public_entity_graph"]
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(
        pipeline.run(
            "Apple Inc.",
            search_engine=engine,
            existing_plan=plan,
            fanout_rounds=1,
            max_fanout_tasks=4,
        )
    )

    assert result.ok is True
    assert any(call[2].get("wikidata_endpoint") == "entitydata" for call in engine.calls)
    assert any(call[2].get("wikidata_id") == "Q312" for call in engine.calls)
    assert "person:tim_cook" in result.subject_profile["subjects"]
    assert "person:steve_jobs" in result.subject_profile["subjects"]
    candidates = {
        (item["name"], item["relation_type"])
        for item in result.subject_profile["controller_candidates"]
    }
    assert ("Tim Cook", "chief_executive_officer") in candidates
    assert ("Steve Jobs", "founder") in candidates


def test_pipeline_runs_bounded_entity_fanout_from_discovered_controller(tmp_path) -> None:
    engine = FanoutSearchEngine()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")
    initial_task_count = len(pipeline.planner.build_company_plan("Demo Fanout Co., Ltd.").tasks)

    result = asyncio.run(
        pipeline.run(
            "Demo Fanout Co., Ltd.",
            search_engine=engine,
            retrieval_concurrency=3,
            fanout_rounds=1,
            max_fanout_tasks=8,
        )
    )

    joined_queries = " ".join(engine.queries).lower()
    assert result.ok is True
    assert "person:bob_li" in result.subject_profile["subjects"]
    assert "bob li" in joined_queries
    assert "beneficial owner" in joined_queries
    assert "vehicle collateral" in joined_queries
    assert "traffic violation" in joined_queries
    assert len(result.retrieval_plan.tasks) <= initial_task_count + 8


def test_pipeline_distinguishes_not_executed_from_clean_result(tmp_path) -> None:
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = asyncio.run(pipeline.run("Demo Not Executed Co., Ltd."))

    assert result.ok is False
    assert result.evidence_count == 0
    assert result.risk_event_count == 0
    assert result.retrieval_summary["execution_state"] == "not_executed"
    assert result.retrieval_summary["attempts"] == 0
    assert result.retrieval_summary["coverage"]["missing_domains"]
    assert any("--config" in action for action in result.retrieval_summary["next_actions"])


def test_entity_resolution_summary_treats_unknown_level_as_unknown() -> None:
    pipeline = RiskDiscoveryPipeline()
    plan = pipeline.planner.build_company_plan("Demo Unknown Match Co.")
    task = plan.tasks[0]
    from core.intelligence_retrieval import EvidenceIngestor

    EvidenceIngestor.ingest_standardized_records(
        plan.graph,
        seed_entity_id="company:demo_unknown_match_co.",
        task=task,
        records=[
            {
                "source_name": "fixture",
                "source_type": "rest_api",
                "entity": "Demo Unknown Match Co.",
                "title": "Unknown match fixture",
                "entity_match": {"level": "unknown", "score": 0.0},
            }
        ],
    )

    summary = RiskDiscoveryPipeline._entity_resolution_summary(plan)

    assert summary["evidence_with_match_count"] == 0
    assert summary["unknown_match_count"] == 1
    assert summary["average_score"] is None


async def async_run_pipeline(pipeline: RiskDiscoveryPipeline, company: str):
    return await pipeline.run(company, records=offline_enforcement_fixture(company))
