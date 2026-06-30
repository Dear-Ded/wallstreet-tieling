#!/usr/bin/env python3
"""Tests for lightweight API server endpoints."""
from __future__ import annotations

import json
from types import SimpleNamespace


def test_risk_graph_endpoint_returns_structured_payload(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/risk-graph",
        json={
            "company": "Demo API Graph Co., Ltd.",
            "offline_fixture": True,
            "store": str(tmp_path / "risk-events.jsonl"),
            "fanout_rounds": 2,
            "max_fanout_tasks": 12,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["company"] == "Demo API Graph Co., Ltd."
    assert payload["data"]["summary"]["execution_state"] == "risk_events_found"
    assert payload["data"]["summary"]["next_actions"]
    assert payload["data"]["summary"]["risk_event_count"] == 1
    assert payload["data"]["risk_events"][0]["severity"] == "high"
    assert payload["data"]["risk_events"][0]["entity_names"] == ["Demo API Graph Co., Ltd."]
    assert payload["data"]["risk_events"][0]["evidence_refs"][0]["source"] == "offline_court_fixture"
    assert payload["data"]["evidence"][0]["omitted_claim_count"] == 0
    assert payload["data"]["diagnostics"]["context_capsule"]["summary"]
    assert payload["data"]["diagnostics"]["subject_profile"]["recursion_policy"]["default_depth"] == 3
    assert payload["data"]["diagnostics"]["monitoring_delta"]["observed_at"]
    assert payload["data"]["timeline"]


def test_risk_graph_endpoint_validates_input() -> None:
    from api.server import app

    client = app.test_client()
    response = client.post("/api/risk-graph", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_risk_graph_endpoint_rejects_conflicting_modes(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/risk-graph",
        json={
            "company": "Demo Conflict Co., Ltd.",
            "offline_fixture": True,
            "config": str(tmp_path / "datasources.yaml"),
        },
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"


def test_risk_graph_endpoint_accepts_official_public_smoke(monkeypatch, tmp_path) -> None:
    import api.server as server

    class FakeSearchEngine:
        initialized_with: str | None = None

        @classmethod
        async def initialize(cls, config_path: str):
            cls.initialized_with = config_path
            return cls

    async def fake_pipeline_run(self, company, **kwargs):
        assert kwargs["search_engine"].initialized_with == str(tmp_path / "official-public-smoke.yaml")
        assert kwargs["existing_plan"].tasks[0].source_hint == "gleif_lei_public_api"
        assert kwargs["fanout_rounds"] == 1
        assert kwargs["identifier_fanout_only"] is True
        return SimpleNamespace(
            graph=SimpleNamespace(entities={}, evidence={}, relations=[], risk_events=[]),
            company=company,
            store_path=str(tmp_path / "events.jsonl"),
            retrieval_summary={
                "execution_state": "not_executed",
                "coverage": {},
                "next_actions": [],
                "entity_resolution": {},
            },
            risk_event_summary={"alert_count": 0, "delta": {}},
            subject_profile={},
            queried_sources=[],
            failed_sources=[],
            source_diagnostics=[],
            to_dict=lambda: {"first_alert": None},
        )

    monkeypatch.setattr(server, "build_official_public_smoke_config", lambda: tmp_path / "official-public-smoke.yaml")
    monkeypatch.setattr("adapters.multi_datasource.SearchEngine", FakeSearchEngine)
    monkeypatch.setattr(server.RiskDiscoveryPipeline, "run", fake_pipeline_run)

    client = server.app.test_client()
    response = client.post(
        "/api/risk-graph",
        json={
            "company": "Demo Official API Co., Ltd.",
            "official_public_smoke": True,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["company"] == "Demo Official API Co., Ltd."


def test_investigate_endpoint_rejects_official_smoke_with_fixture() -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/investigate",
        json={
            "company": "Demo Conflict Co., Ltd.",
            "official_public_smoke": True,
            "fixture_pack": True,
        },
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"


def test_investigate_endpoint_accepts_one_line_message(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/investigate",
        json={
            "message": "Demo One Click Co., Ltd.",
            "offline_fixture": True,
            "store": str(tmp_path / "risk-events.jsonl"),
            "mode": "standard",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "investigation_packet"
    assert payload["version"] == "0.5.0"
    assert payload["input"] == "Demo One Click Co., Ltd."
    assert payload["one_click"] is True
    assert payload["summary"]["execution_state"] == "risk_events_found"
    assert payload["summary"]["entity_resolution"]["strong_match_count"] >= 1
    assert payload["graph"]["company"] == "Demo One Click Co., Ltd."
    assert payload["graph"]["risk_events"]
    assert payload["risk_brief"]["risk_score"] > 0
    assert payload["enterprise_cognition"]["company"] == "Demo One Click Co., Ltd."
    assert payload["enterprise_cognition"]["monitoring_watchlist"]
    assert payload["evidence_ledger"]
    assert payload["evidence_ledger"][0]["entity_match_level"] in {"exact", "strong"}
    assert payload["monitoring_seed"]["ready_for_continuous_watch"] is True
    assert payload["monitoring_seed"]["current_release_monitoring_enabled"] is False
    assert payload["monitoring_seed"]["feature_scope"] == "future_version_not_current_release"
    assert payload["report_exports"]["type"] == "report_exports"
    assert "portable_html" in payload["report_exports"]["formats"]
    assert payload["report_exports"]["portable_html"]["document"].startswith("<!doctype html>")
    assert "Demo One Click Co., Ltd." in payload["report_exports"]["portable_html"]["document"]
    assert "report readiness summary" in payload["report_exports"]["portable_html"]["document"]
    assert "coverage gaps:" in payload["report_exports"]["portable_html"]["document"]
    assert payload["report_exports"]["future_formats"]["docx_red_head"] == "p2_template_required_not_current_release_blocker"
    assert payload["report_markdown"].startswith("# 华尔街驻铁岭办事处")
    assert payload["next_actions"]


def test_investigate_endpoint_defaults_to_public_one_click(monkeypatch, tmp_path) -> None:
    import api.server as server
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline

    class FakeDefaultSearch:
        pass

    calls = {}
    original_resolve = server.resolve_one_click_retrieval_async
    original_run = RiskDiscoveryPipeline.run

    async def fake_resolve(**kwargs):
        calls["resolve"] = kwargs
        return await original_resolve(
            **{
                **kwargs,
                "search_engine": FakeDefaultSearch(),
                "existing_plan": None,
                "default_enabled": False,
            }
        )

    async def fake_pipeline_run(self, company, **kwargs):
        calls["run"] = kwargs
        return await original_run(
            RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl"),
            company,
            records=build_datasource_fixture_pack(company).all_records(),
            store_path=tmp_path / "risk-events.jsonl",
        )

    monkeypatch.setattr(server, "resolve_one_click_retrieval_async", fake_resolve)
    monkeypatch.setattr(server.RiskDiscoveryPipeline, "run", fake_pipeline_run)

    client = server.app.test_client()
    response = client.post("/api/investigate", json={"company": "Demo Default API Co., Ltd."})

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "investigation_packet"
    assert payload["summary"]["evidence_count"] == 6
    assert calls["resolve"]["records"] is None
    assert calls["resolve"]["search_engine"] is None
    assert isinstance(calls["run"]["search_engine"], FakeDefaultSearch)


def test_investigate_endpoint_accepts_fixture_pack(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/investigate",
        json={
            "company": "Demo API Fixture Pack Co., Ltd.",
            "fixture_pack": True,
            "store": str(tmp_path / "risk-events.jsonl"),
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["evidence_count"] == 6
    assert payload["summary"]["subject_profile"]["controller_candidate_count"] >= 1
    assert payload["profile_brief"]["controller_candidate_count"] >= 1
    assert payload["graph"]["diagnostics"]["subject_profile"]["controller_candidates"]
    routing_summary = payload["source_failure_summary"]["source_routing_summary"]
    assert routing_summary["policy"].startswith("Routing health describes source availability")
    coverage_watchlist = payload["monitoring_seed"]["coverage_recovery_watchlist"]
    assert any(item["domain"] == "administrative_risk" for item in coverage_watchlist)
    assert any(item["suggested_source"] == "creditchina_public" for item in coverage_watchlist)
    execution_plan = payload["monitoring_seed"]["coverage_recovery_execution_plan"]
    assert any(item["tier"] == "official_public" for item in execution_plan)
    assert any(item["source"] == "creditchina_public" for item in execution_plan)
    execution_readiness = payload["monitoring_seed"]["coverage_recovery_execution_readiness"]
    assert execution_readiness["step_count"] >= len(execution_plan)
    assert "ready_count" in execution_readiness
    assert "blocked_count" in execution_readiness
    recovery_queue = payload["monitoring_seed"]["recovery_execution_queue"]
    assert "ready_to_run" in recovery_queue
    assert "queued_count" in recovery_queue
    assert "blocked_count" in recovery_queue
    recovery_summary = payload["monitoring_seed"]["recovery_execution_summary"]
    assert recovery_summary["blocked_count"] == recovery_queue["blocked_count"]
    assert recovery_summary["policy"].startswith("Use ready queue items")
    assert "relationship_candidate_leads" in payload["monitoring_seed"]["watched_dimensions"]
    relationship_watchlist = payload["monitoring_seed"]["relationship_candidate_watchlist"]
    assert any(item["relation_type"] == "supplier_of" for item in relationship_watchlist)
    assert any(item["priority"] == "P0" for item in relationship_watchlist)
    relationship_plan = payload["monitoring_seed"]["relationship_candidate_execution_plan"]
    supplier_step = next(item for item in relationship_plan if item["relation_type"] == "supplier_of")
    assert supplier_step["expansion_queries"][0]["target_subject"]
    assert any(query["domain"] == "trade_supply_chain" for query in supplier_step["expansion_queries"])


def test_investigate_endpoint_reports_not_executed_without_sources(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/investigate",
        json={
            "company": "Demo No Source Co., Ltd.",
            "store": str(tmp_path / "risk-events.jsonl"),
            "default_public_one_click": False,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["execution_state"] == "not_executed"
    assert payload["risk_brief"]["verdict"] == "insufficient_data"
    assert payload["graph"]["evidence"] == []
    assert payload["next_actions"]


def test_investigate_endpoint_validates_input() -> None:
    from api.server import app

    client = app.test_client()
    response = client.post("/api/investigate", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_monitor_run_endpoint_executes_and_persists_batch(tmp_path) -> None:
    from api.server import app

    risk_store = tmp_path / "risk-events.jsonl"
    run_store = tmp_path / "monitor-runs.jsonl"

    client = app.test_client()
    response = client.post(
        "/api/monitor/run",
        json={
            "companies": [
                "Demo API Monitor A Co., Ltd.",
                "Demo API Monitor B Co., Ltd.",
                "Demo API Monitor A Co., Ltd.",
            ],
            "offline_fixture": True,
            "store": str(risk_store),
            "run_store": str(run_store),
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["run_id"].startswith("monitor:")
    assert payload["company_count"] == 2
    assert payload["ok_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["store_summary"]["total_events"] == 2
    assert len(payload["alerts"]) == 2
    assert run_store.exists()
    assert risk_store.exists()

    history = client.get(
        "/api/monitor/runs",
        query_string={"run_store": str(run_store), "company": "Demo API Monitor A Co., Ltd."},
    )
    assert history.status_code == 200
    history_payload = history.get_json()["data"]
    assert history_payload["run_count"] == 1
    assert history_payload["runs"][0]["results"][0]["delta"]["new_event_count"] == 1


def test_monitor_run_endpoint_validates_input_and_mode_conflict(tmp_path) -> None:
    from api.server import app

    client = app.test_client()
    missing = client.post("/api/monitor/run", json={})
    assert missing.status_code == 400
    assert missing.get_json()["error"]["code"] == "validation_error"

    conflict = client.post(
        "/api/monitor/run",
        json={
            "company": "Demo Monitor Conflict Co., Ltd.",
            "offline_fixture": True,
            "config": str(tmp_path / "datasources.yaml"),
        },
    )
    assert conflict.status_code == 422
    assert conflict.get_json()["error"]["code"] == "validation_error"


def test_monitor_runs_endpoint_returns_persisted_history(tmp_path) -> None:
    from api.server import app

    run_store = tmp_path / "monitor-runs.jsonl"
    run_store.write_text(
        json.dumps(
            {
                "run_id": "monitor:api-history",
                "started_at": "2026-06-20T00:00:00Z",
                "completed_at": "2026-06-20T00:00:01Z",
                "company_count": 1,
                "ok_count": 1,
                "failed_count": 0,
                "results": [{"company": "Demo API History Co., Ltd."}],
                "failures": [],
                "store_summary": {},
                "alerts": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    client = app.test_client()
    response = client.get(
        "/api/monitor/runs",
        query_string={
            "run_store": str(run_store),
            "company": "Demo API History Co., Ltd.",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["run_count"] == 1
    assert payload["company_filter"] == "Demo API History Co., Ltd."
    assert payload["runs"][0]["run_id"] == "monitor:api-history"


def test_monitor_source_health_endpoint_returns_trends(tmp_path) -> None:
    from api.server import app

    run_store = tmp_path / "monitor-runs.jsonl"
    run_store.write_text(
        json.dumps(
            {
                "run_id": "monitor:api-health",
                "started_at": "2026-06-20T00:00:00Z",
                "completed_at": "2026-06-20T00:00:01Z",
                "company_count": 1,
                "ok_count": 1,
                "failed_count": 0,
                "results": [
                    {
                        "company": "Demo API Health Co., Ltd.",
                        "retrieval_summary": {
                            "source_routing": {
                                "health_reports": {
                                    "source_a": {"ok": True, "status": "up"},
                                    "source_b": {"ok": False, "status": "down"},
                                }
                            }
                        },
                    }
                ],
                "failures": [],
                "store_summary": {},
                "alerts": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    client = app.test_client()
    response = client.get(
        "/api/monitor/source-health",
        query_string={"run_store": str(run_store)},
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["source_health"]["run_count"] == 1
    assert payload["source_health"]["source_count"] == 2
    assert payload["source_health"]["sources"]["source_a"]["availability_ratio"] == 1.0
    assert payload["source_health"]["sources"]["source_b"]["down_count"] == 1


def test_health_endpoint_does_not_overclaim_live_pipeline() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    checks = response.get_json()["checks"]
    assert checks["evidence_pipeline"] == "runtime_gated"
    assert checks["release_readiness"] in {"ready", "not_release_ready"}
    assert isinstance(checks["blocker_count"], int)
    assert checks["smoke_status"]["public_sources"] == "fixture_only"
    assert "does not certify live data" in checks["smoke_status"]["note"]


def test_api_index_labels_monitoring_as_explicit_baseline_recheck() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    payload = response.get_json()
    monitor_text = payload["endpoints"]["POST /api/monitor/run"]
    assert "基线复查" in monitor_text
    assert "后续版本" in monitor_text
    assert "持续盯防" not in monitor_text


def test_api_docs_marks_monitoring_as_later_version_scope() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/docs")

    assert response.status_code == 200
    payload = response.get_json()
    endpoint_text = payload["endpoints"]["POST /api/monitor/run"]
    assert "baseline re-check" in endpoint_text
    assert "continuous monitoring is later-version scope" in endpoint_text


def test_connectors_endpoint_exposes_product_catalog() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/connectors")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "connector_catalog"
    assert payload["summary"]["default_enabled"] >= 4
    assert "default_public_intel" in payload["summary"]["zero_config_ready"]
    assert payload["groups"]["needs_admission"]
    assert payload["policy"]["public_boundary"]
    assert payload["summary"]["data_effectiveness"]["fact_capable_sources"] >= 4
    assert payload["data_effectiveness"]
    assert payload["qyyjt_benchmark"]["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert payload["qyyjt_benchmark"]["summary"]["surface_lanes"]["authorized_api"] == 4
    assert payload["qyyjt_benchmark"]["summary"]["p0_queue_count"] == 20
    assert payload["qyyjt_benchmark"]["summary"]["p0_queue"][0]["module"] == "search_multi"
    assert payload["qyyjt_benchmark"]["summary"]["field_contracts"]["financial"]["record_type"] == "financial_statement_metric"


def test_release_endpoint_exposes_variant_contract() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/release")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "release_readiness_brief"
    assert payload["version"] == "0.5.0"
    assert payload["persona_surface"]["role_count"] == 13
    assert set(payload["contract"]["variants"]) == {
        "universal",
        "codex",
        "claude_code",
        "hermes",
        "doubao_office_task_mode",
        "open_claude_agents",
        "workbuddy_expert_team",
    }
    assert payload["blockers"]
    assert payload["next_focus"]


def test_requirements_endpoint_exposes_development_priority_board() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/requirements")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "development_requirements_board"
    assert payload["completion_percent"] == 88
    assert payload["summary"]["by_level"]["P0"] >= 6
    assert payload["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"
    assert payload["qyyjt_current_version"]["p0_queue_count"] == 20
    assert all(item["id"] != "FUTURE.CONTINUOUS_MONITORING" for item in payload["next_focus"])


def test_api_docs_mentions_qyyjt_benchmark_surface() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/docs")

    assert response.status_code == 200
    payload = response.get_json()
    assert "data.qyyjt_benchmark.summary.surface_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.summary.data_effectiveness" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.data_effectiveness[]" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.surface_profile.concrete_api_or_legacy_module_names" in payload["catalog_contract"]["connectors"]["response"]
    assert "GET /api/requirements" in payload["endpoints"]
    assert "data.qyyjt_current_version" in payload["catalog_contract"]["requirements"]["response"]
    assert "data.qyyjt_benchmark.summary.authorization_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.unsupported_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.p0_queue" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.field_contracts" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.public_origin_plans" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.rows[]" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.monitoring_seed.recovery_execution_summary" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.recovery_execution_queue" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.relationship_candidate_execution_plan" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.recurring_failure_patterns" in payload["investigate_contract"]["response"]
    assert "data.source_failure_summary.recurring_failure_patterns" in payload["investigate_contract"]["response"]
    assert "data.report_exports" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_recommended_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_not_searched_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_no_evidence_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_gap_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_gap_severity" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_attempt_ratio" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_next_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_missing_domains" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.coverage_domains_without_evidence" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.public_origin_next_action_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.public_origin_modules" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.public_origin_top_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_watch_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_execution_step_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_top_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_status" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_unresolved_reason" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_next_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_evidence_backed_edge_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_auditable_edge_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_missing_evidence_edge_count" in payload["investigate_contract"]["response"]
    assert "data.persona_surface" in payload["catalog_contract"]
