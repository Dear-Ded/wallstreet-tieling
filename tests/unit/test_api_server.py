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


def test_aggregate_endpoint_matches_agent_tool_contract() -> None:
    from api.server import app

    client = app.test_client()
    response = client.post(
        "/api/aggregate",
        json={
            "subject_id": "company:demo-agent-contract",
            "subject_name": "Demo Agent Contract Co.",
            "max_depth": 1,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["subject"]["id"] == "company:demo-agent-contract"
    assert payload["subject"]["name"] == "Demo Agent Contract Co."
    assert "identity" in payload["subject"]
    assert "relationship_graph" in payload
    assert "profile" in payload
    assert payload["profile"]["identity"] == payload["identity"]
    assert payload["adapter_summary"]["total_sources"] == payload["source_count"]


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
    assert "print_package" in payload["report_exports"]["formats"]
    assert "directory_bundle" in payload["report_exports"]["formats"]
    assert payload["report_exports"]["portable_html"]["document"].startswith("<!doctype html>")
    assert "Demo One Click Co., Ltd." in payload["report_exports"]["portable_html"]["document"]
    assert "report readiness summary" in payload["report_exports"]["portable_html"]["document"]
    assert "coverage gaps:" in payload["report_exports"]["portable_html"]["document"]
    print_package = payload["report_exports"]["print_package"]
    assert print_package["status"] == "ready_for_agent_renderer"
    assert print_package["docx"]["renderer_status"] == "runtime_cli_renderer_available"
    assert print_package["docx"]["runtime_entrypoint"] == "bin/investigate.py --export-docx"
    assert print_package["print_layout"]["preserve_full_report_text"] is True
    assert "source_provenance_appendix" in print_package["document_structure"]
    assert "operational_handoff_appendix" in print_package["document_structure"]
    assert print_package["delivery_checklist"]["status"] == "ready_for_desktop_agent_delivery"
    assert print_package["delivery_checklist"]["primary_print_file"] == print_package["docx"]["filename"]
    assert print_package["operational_handoff"]["summary"]["status"] == payload["one_click_readiness"]["status"]
    assert "official_document_metadata" in print_package["docx"]["renderer_capabilities"]
    assert "native_chart_summary_panels" in print_package["docx"]["renderer_capabilities"]
    assert "operational_handoff_tables" in print_package["docx"]["renderer_capabilities"]
    assert "embedded_local_image_evidence" in print_package["docx"]["renderer_capabilities"]
    assert payload["report_exports"]["directory_bundle"]["runtime_entrypoint"] == "bin/investigate.py --export-dir"
    assert payload["report_exports"]["future_formats"]["docx_red_head"] == "runtime_cli_renderer_available_via_export_docx"
    assert payload["report_markdown"].startswith("# \u534e\u5c14\u8857\u9a7b\u94c1\u5cad\u529e\u4e8b\u5904")
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
                        "source_diagnostics": [
                            {
                                "source": "source_c",
                                "status": "timeout",
                                "failure_category": "timeout",
                                "objective": "bond credit recovery",
                                "trace_id": "monitor:api-health:source:001",
                            }
                        ],
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
    assert payload["source_health"]["source_count"] == 3
    assert payload["source_health"]["sources"]["source_a"]["availability_ratio"] == 1.0
    assert payload["source_health"]["sources"]["source_b"]["down_count"] == 1
    assert payload["source_health"]["sources"]["source_c"]["down_count"] == 1
    assert payload["source_health"]["failure_category_counts"]["timeout"] == 1
    assert payload["source_health"]["failure_category_counts"]["source_unavailable"] == 1
    patterns = payload["source_health"]["recurring_failure_patterns"]
    assert any(
        item["source"] == "source_c" and item["failure_category"] == "timeout"
        for item in patterns
    )
    queue = payload["source_health"]["connector_recovery_queue"]
    assert queue[0]["source"] == "source_b"
    assert queue[0]["priority"] == "P0"
    assert queue[0]["release_warning"] is True
    assert payload["source_health"]["release_readiness_warning_count"] >= 1
    assert payload["source_health"]["release_readiness_warnings"][0]["priority"] == "P0"


def test_health_endpoint_does_not_overclaim_live_pipeline() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    checks = response.get_json()["checks"]
    assert checks["evidence_pipeline"] == "runtime_gated"
    assert checks["release_readiness"] in {"ready", "not_release_ready"}
    assert checks["desktop_agent_delivery"] == "desktop_agent_alpha_release_candidate"
    assert checks["desktop_agent_release_candidate"] is True
    assert checks["full_product_status"] == "not_final_release_ready"
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
    assert "\u57fa\u7ebf\u590d\u67e5" in monitor_text
    assert "\u540e\u7eed\u7248\u672c" in monitor_text
    assert "\u6301\u7eed\u76ef\u9632" not in monitor_text


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
    assert "needs_admission" in payload["groups"]
    assert payload["policy"]["public_boundary"]
    assert payload["summary"]["data_effectiveness"]["fact_capable_sources"] >= 4
    assert payload["data_effectiveness"]
    assert payload["qyyjt_benchmark"]["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert payload["qyyjt_benchmark"]["summary"]["surface_lanes"]["authorized_api"] == 4
    assert payload["qyyjt_benchmark"]["summary"]["p0_queue_count"] == 20
    assert payload["qyyjt_benchmark"]["summary"]["p0_queue"][0]["module"] == "search_multi"
    assert payload["qyyjt_benchmark"]["summary"]["public_origin_execution_summary"]["p0_count"] == 20
    assert payload["qyyjt_benchmark"]["summary"]["public_origin_execution_summary"]["top_action"]["module"] == "search_multi"
    section_batches = payload["qyyjt_benchmark"]["summary"]["public_origin_execution_summary"]["report_section_batches"]
    assert any(item["report_section"] == "legal_risk" for item in section_batches)
    assert any(item["report_section"] == "asset_solvency" for item in section_batches)
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
    assert payload["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert payload["delivery_decision"]["desktop_agent_release_candidate"] is True
    assert payload["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert payload["delivery_decision"]["runtime_blocking_surface_count"] == 0
    assert payload["delivery_decision"]["remaining_variant_blocker_count"] == 0
    assert payload["delivery_decision"]["variant_next_gate_count"] == len(payload["blockers"])
    assert payload["delivery_closure"]["type"] == "desktop_agent_alpha_delivery_closure"
    assert payload["delivery_closure"]["document"] == "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md"
    assert payload["delivery_closure"]["baseline_sequence"][-1] == "investigate_company"
    assert "aggregate_subject" in payload["delivery_closure"]["followup_tools"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in payload["delivery_closure"]["required_preserved_fields"]
    assert "report_exports.premium_html" in payload["delivery_closure"]["required_preserved_fields"]
    assert "report_exports.portable_html.premium_profile" in payload["delivery_closure"]["required_preserved_fields"]
    assert (
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html"
        in payload["delivery_closure"]["required_preserved_fields"]
    )
    assert "npm pack --dry-run --json" in payload["delivery_closure"]["required_verification_commands"]
    assert "npm run delivery:audit" in payload["delivery_closure"]["required_verification_commands"]
    assert "npm run objective:audit" in payload["delivery_closure"]["required_verification_commands"]
    assert payload["latest_acceptance_evidence"]["status"] == "passed"
    assert payload["latest_acceptance_evidence"]["observed_at"] == "2026-07-06 08:24 Asia/Shanghai"
    assert payload["latest_acceptance_evidence"]["python_tests_passed"] == 799
    focused_regression = payload["latest_acceptance_evidence"]["post_acceptance_focused_regressions"][0]
    assert focused_regression["observed_at"] == "2026-07-05 21:24 Asia/Shanghai"
    assert focused_regression["python_tests_passed"] == 223
    assert focused_regression["python_tests_skipped"] == 2
    assert "source_strengthening completion state with needs_admission=0" in focused_regression["covers"]
    premium_regression = payload["latest_acceptance_evidence"]["post_acceptance_focused_regressions"][1]
    assert premium_regression["observed_at"] == "2026-07-05 22:01 Asia/Shanghai"
    assert premium_regression["python_tests_passed"] == 14
    assert premium_regression["python_tests_skipped"] == 0
    assert "npm run agent:host-smoke" in premium_regression["node_smokes"]
    assert "npm run codex:mcp-smoke" in premium_regression["node_smokes"]
    assert "premium_html report_exports runtime contract" in premium_regression["covers"]
    assert "directory agent-handoff report_visibility.premium_html" in premium_regression["covers"]
    assert "Codex primary delivery lane and WorkBuddy secondary branch priority" in payload["latest_acceptance_evidence"]["covers"]
    assert "connector_catalog source_strengthening_queue" in payload["latest_acceptance_evidence"]["covers"]
    assert "official China source strengthening implementation_pack" in payload["latest_acceptance_evidence"]["covers"]
    assert "OpenSanctions and IDB public dataset source strengthening implementation_pack" in payload["latest_acceptance_evidence"]["covers"]
    assert "agent_tool_adapters first_run_recipe preserves source_strengthening_queue" in payload["latest_acceptance_evidence"]["covers"]
    assert "source_strengthening risk_enforcement lane routing" in payload["latest_acceptance_evidence"]["covers"]
    assert "source_strengthening execution_plan agent handoff" in payload["latest_acceptance_evidence"]["covers"]
    assert "manifest agent_summary deep drift verification" in payload["latest_acceptance_evidence"]["covers"]
    assert "agent_tool_adapters runtime contract" in payload["latest_acceptance_evidence"]["covers"]
    assert "agent_tool_adapters premium_html preservation guards" in payload["latest_acceptance_evidence"]["covers"]
    assert "premium_html report_exports runtime contract" in payload["latest_acceptance_evidence"]["covers"]
    assert "directory agent-handoff report_visibility.premium_html" in payload["latest_acceptance_evidence"]["covers"]
    assert "WorkBuddy investigate_company host smoke" in payload["latest_acceptance_evidence"]["covers"]
    assert "host-smoke Python runtime resolution" in payload["latest_acceptance_evidence"]["covers"]
    assert "release_preflight package go/no-go gate" in payload["latest_acceptance_evidence"]["covers"]
    assert "package privacy scan gate" in payload["latest_acceptance_evidence"]["covers"]
    assert "npm package dry-run content gate" in payload["latest_acceptance_evidence"]["covers"]
    assert "terminology guard public-copy hygiene" in payload["latest_acceptance_evidence"]["covers"]
    assert "report_exports.agent_decision_digest packet routing" in payload["latest_acceptance_evidence"]["covers"]
    assert "directory bundle verifier_output_fields handoff" in payload["latest_acceptance_evidence"]["covers"]
    assert "DOCX source provenance appendix and evidence source index" in payload["latest_acceptance_evidence"]["covers"]
    assert "DOCX relationship/capital appendix and delivery checklist" in payload["latest_acceptance_evidence"]["covers"]
    assert "source_resilience agent_autorun" in payload["latest_acceptance_evidence"]["covers"]
    assert "QYYJT public-origin agent_autorun" in payload["latest_acceptance_evidence"]["covers"]
    assert "capital risk and relationship autorun routes" in payload["latest_acceptance_evidence"]["covers"]
    assert "report_artifact_agent_autorun" in payload["latest_acceptance_evidence"]["covers"]
    assert payload["release_preflight"]["type"] == "desktop_agent_alpha_release_preflight"
    assert payload["release_preflight"]["status"] == "ready_for_local_packaging"
    assert payload["release_preflight"]["package_candidate_ready"] is True
    assert payload["release_preflight"]["final_submission_ready"] is False
    assert "npm pack --dry-run --json" in payload["release_preflight"]["required_verification_commands"]
    assert "npm run release:privacy-scan" in payload["release_preflight"]["required_verification_commands"]
    assert "npm run delivery:audit" in payload["release_preflight"]["required_verification_commands"]
    assert "marketplace/operator screenshots" in " ".join(payload["release_preflight"]["final_submission_blockers"])
    assert payload["runtime_delivery"]["current_release_surface_count"] >= 5
    assert payload["runtime_delivery"]["acceptance_status_counts"]["proof_defined"] >= 7
    assert payload["runtime_delivery"]["release_blocking_surface_count"] == 0
    assert payload["runtime_delivery"]["proof_test_count"] >= 6
    assert "test_investigate_cli_export_docx_writes_word_file" in payload["runtime_delivery"]["focused_test_command"]
    assert "test_node_cli_offline_fallback_writes_agent_handoff_bundle" in payload["runtime_delivery"]["focused_test_command"]
    runtime_surfaces = {item["surface"] for item in payload["runtime_delivery"]["surfaces"]}
    assert "printable_docx_export" in runtime_surfaces
    assert "risk_graph_capital_exposure" in runtime_surfaces
    assert "qyyjt_public_origin_execution_queue" in runtime_surfaces
    assert "source_health_trend_snapshot" in runtime_surfaces
    assert "source_health_release_warnings" in runtime_surfaces
    html_surface = next(item for item in payload["runtime_delivery"]["surfaces"] if item["surface"] == "portable_html_and_markdown_exports")
    assert "node_cli_offline_fixture_fallback_export_dir" in html_surface["entrypoints"]
    assert "node_cli_fallback_manifest.unavailable_outputs.docx" in html_surface["entrypoints"]
    source_health_handoff = payload["runtime_delivery"]["source_health_operator_handoff"]
    assert source_health_handoff["type"] == "source_health_operator_handoff"
    assert "/api/monitor/source-health" in source_health_handoff["trend_entrypoints"]
    assert "operator_action" in source_health_handoff["recovery_queue_fields"]
    assert source_health_handoff["release_action_policy"].startswith("Treat degraded source-health")
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


def test_release_preflight_endpoint_exposes_packaging_go_no_go() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/release-preflight")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "desktop_agent_alpha_release_preflight"
    assert payload["target"] == "desktop_agent_alpha"
    assert payload["status"] == "ready_for_local_packaging"
    assert payload["package_candidate_ready"] is True
    assert payload["final_submission_ready"] is False
    assert payload["blocking_items"] == []
    assert "npm pack --dry-run --json" in payload["required_verification_commands"]
    assert "npm run release:privacy-scan" in payload["required_verification_commands"]
    assert "npm run delivery:audit" in payload["required_verification_commands"]
    assert "npm run objective:audit" in payload["required_verification_commands"]
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in payload["required_preserved_fields"]
    assert "report_exports.premium_html" in payload["required_preserved_fields"]
    assert "report_exports.portable_html.premium_profile" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in payload["required_preserved_fields"]
    assert "qyyjt_public_origin_handoff.agent_autorun" in payload["required_preserved_fields"]
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in payload["required_preserved_fields"]
    assert payload["latest_acceptance"]["python_tests_passed"] == 799
    assert payload["packaging_review"]["dry_run_command"] == "npm pack --dry-run --json"
    assert payload["packaging_review"]["privacy_command"] == "npm run release:privacy-scan"
    assert "desktop-agent alpha release candidate" in payload["agent_handoff"]["safe_claim"].lower()


def test_delivery_audit_endpoint_exposes_single_go_no_go() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/delivery-audit")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "desktop_agent_alpha_delivery_audit"
    assert payload["target"] == "desktop_agent_alpha"
    assert payload["status"] == "pass"
    assert payload["ready_for_local_packaging"] is True
    assert payload["failed_checks"] == []
    assert payload["coverage"]["source_resilience"]["covered"] is True
    assert payload["coverage"]["qyyjt_public_origin"]["covered"] is True
    assert payload["coverage"]["capital_risk"]["covered"] is True
    assert payload["coverage"]["relationship_graph"]["covered"] is True
    assert payload["coverage"]["report_visibility"]["covered"] is True
    assert payload["verification_evidence"]["latest_acceptance"]["python_tests_passed"] == 799
    assert "not final polished product launch readiness" in payload["safe_claim"].lower()


def test_objective_audit_endpoint_maps_goal_to_evidence() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/objective-audit")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "objective_completion_audit"
    assert payload["status"] == "complete"
    assert payload["completion_percent"] == 100
    assert payload["release_gate"]["delivery_audit_status"] == "pass"
    assert payload["verification_evidence"]["latest_acceptance"]["python_tests_passed"] == 799
    assert payload["verification_evidence"]["public_release_hygiene"]["status"] == "pass"
    statuses = {item["id"]: item["status"] for item in payload["requirements"]}
    assert statuses["source_resilience"] == "complete"
    assert statuses["qyyjt_public_origin_mapping"] == "complete"
    assert statuses["relationship_graph"] == "complete"
    assert statuses["capital_risk"] == "complete"
    assert statuses["report_visibility"] == "complete"
    assert statuses["acceptance_closure"] == "complete"
    assert statuses["desktop_agent_delivery"] == "complete"
    assert statuses["workbuddy_expert_team_compatibility"] == "complete"
    assert statuses["public_release_hygiene"] == "complete"
    assert payload["failed_requirements"] == []


def test_requirements_endpoint_exposes_development_priority_board() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/requirements")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "development_requirements_board"
    assert payload["completion_percent"] == 94
    assert payload["summary"]["by_level"]["P0"] >= 6
    assert payload["summary"]["desktop_agent_delivery"] == "desktop_agent_alpha_release_candidate"
    assert payload["delivery_decision"]["status"] == "desktop_agent_alpha_release_candidate"
    assert payload["delivery_decision"]["desktop_agent_release_candidate"] is True
    assert payload["delivery_decision"]["full_product_status"] == "not_final_release_ready"
    assert payload["scope_rules"]["continuous_monitoring"] == "future_version_not_current_release"
    assert payload["qyyjt_current_version"]["p0_queue_count"] == 20
    assert all(item["id"] != "FUTURE.CONTINUOUS_MONITORING" for item in payload["next_focus"])


def test_agent_tools_endpoint_exposes_all_desktop_agent_adapters() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/agent-tools")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["type"] == "agent_tool_adapter_manifest"
    assert payload["release_target"] == "desktop_agent_alpha"
    assert payload["adapter_count"] == 7
    assert payload["all_current_release_ready"] is True
    assert set(payload["host_ids"]) == {
        "universal",
        "codex",
        "claude_code",
        "hermes",
        "doubao_office_task_mode",
        "open_claude_agents",
        "workbuddy_expert_team",
    }
    assert {"npm run agent:host-smoke", "npm run codex:mcp-smoke", "npm run api:smoke"} <= set(payload["required_smoke_commands"])
    shared_names = {item["name"] for item in payload["shared_tools"]}
    assert {
        "release_readiness",
        "release_preflight",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company",
        "aggregate_subject",
    } <= shared_names
    shared_tools = {item["name"]: item for item in payload["shared_tools"]}
    assert shared_tools["aggregate_subject"]["cli"].startswith("npx wallstreet-tieling --aggregate-subject")
    assert shared_tools["aggregate_subject"]["api"] == "POST /api/aggregate"
    assert shared_tools["release_preflight"]["cli"] == "npx wallstreet-tieling --release-preflight"
    assert shared_tools["release_preflight"]["api"] == "GET /api/release-preflight"
    assert "package_candidate_ready" in shared_tools["release_preflight"]["required_output_fields"]
    assert shared_tools["delivery_audit"]["api"] == "GET /api/delivery-audit"
    assert "failed_checks" in shared_tools["delivery_audit"]["required_output_fields"]
    phases = [item["phase"] for item in payload["execution_matrix"]]
    assert phases == [
        "release_gate",
        "delivery_audit",
        "source_catalog",
        "priority_board",
        "host_binding",
        "investigation_run",
        "followup_expansion",
    ]
    assert payload["execution_matrix"][0]["tool"] == "release_readiness"
    assert "desktop_agent_alpha_release_candidate" in payload["execution_matrix"][0]["done_condition"]
    assert payload["execution_matrix"][1]["tool"] == "delivery_audit"
    assert payload["execution_matrix"][-1]["tool"] == "aggregate_subject"
    assert payload["execution_matrix"][-1]["optional"] is True
    assert payload["first_run_recipe"]["sequence"][-1] == "investigate_company"
    assert "report_exports.directory_bundle.agent_handoff" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert "report_exports.premium_html" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert "report_exports.portable_html.premium_profile" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert (
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html"
        in payload["first_run_recipe"]["preserve_before_summarizing"]
    )
    assert "qyyjt_public_origin_handoff.agent_autorun" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert "enterprise_cognition.relationship_resolution_v1" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue" in payload["first_run_recipe"]["preserve_before_summarizing"]
    assert any("prose-only" in item for item in payload["first_run_recipe"]["do_not"])
    assert payload["default_host_id"] == "codex"
    assert payload["primary_host_id"] == "codex"
    assert payload["host_priority_order"][0] == "codex"
    assert "workbuddy_expert_team" in payload["secondary_host_ids"]
    assert set(payload["adapter_lookup"]) == set(payload["host_ids"])
    assert payload["adapter_lookup"]["codex"]["primary_mode"] == "codex_plugin_mcp"
    assert payload["adapter_lookup"]["codex"]["smoke_command"] == "npm run codex:mcp-smoke"
    assert payload["adapter_lookup"]["codex"]["delivery_priority"]["lane"] == "primary"
    assert payload["adapter_lookup"]["workbuddy_expert_team"]["delivery_priority"]["lane"] == "secondary"
    assert payload["adapter_lookup"]["codex"]["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix"
    assert payload["adapter_lookup"]["codex"]["required_packet_field_count"] >= 9
    for adapter in payload["adapters"]:
        assert adapter["current_release_supported"] is True
        assert adapter["execution_matrix_ref"] == "agent_tool_adapter_manifest.execution_matrix"
        assert adapter["tool_sequence"] == [
            "release_readiness",
            "delivery_audit",
            "connector_catalog",
            "development_requirements",
            "agent_tool_adapters",
            "investigate_company",
        ]
        assert adapter["fallback_order"]
        assert adapter["smoke_command"]
        assert "report_exports.agent_decision_digest" in adapter["required_packet_fields"]
        assert "report_exports.premium_html" in adapter["required_packet_fields"]
        assert "report_exports.portable_html.premium_profile" in adapter["required_packet_fields"]
        assert "enterprise_cognition.relationship_resolution_v1" in adapter["required_packet_fields"]
        assert "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.verifier_output_fields" in adapter["required_packet_fields"]
        assert "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html" in adapter["required_packet_fields"]
        assert "premium_html" in adapter["report_outputs"]
        assert "agent_handoff" in adapter["report_outputs"]


def test_api_docs_mentions_qyyjt_benchmark_surface() -> None:
    from api.server import app

    client = app.test_client()
    response = client.get("/api/docs")

    assert response.status_code == 200
    payload = response.get_json()
    assert "data.qyyjt_benchmark.summary.surface_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.summary.data_effectiveness" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.summary.admission_gate_summary" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.data_effectiveness[]" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.surface_profile.concrete_api_or_legacy_module_names" in payload["catalog_contract"]["connectors"]["response"]
    assert "GET /api/requirements" in payload["endpoints"]
    assert "GET /api/agent-tools" in payload["endpoints"]
    assert "GET /api/release-preflight" in payload["endpoints"]
    assert "GET /api/delivery-audit" in payload["endpoints"]
    assert "POST /api/aggregate" in payload["endpoints"]
    assert "agent_tools" in payload["catalog_contract"]
    assert "data.adapters[]" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "data.execution_matrix" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "data.first_run_recipe" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "data.adapter_lookup" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "data.default_host_id" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "data.minimum_pass_gates" in payload["catalog_contract"]["agent_tools"]["response"]
    assert "aggregate" in payload["catalog_contract"]
    assert payload["catalog_contract"]["aggregate"]["request"]["subject_id"].startswith("required")
    assert "subject" in payload["catalog_contract"]["aggregate"]["response"]
    assert "relationship_graph" in payload["catalog_contract"]["aggregate"]["response"]
    assert "profile" in payload["catalog_contract"]["aggregate"]["response"]
    assert "adapter_summary" in payload["catalog_contract"]["aggregate"]["response"]
    assert "data.qyyjt_current_version" in payload["catalog_contract"]["requirements"]["response"]
    assert "data.delivery_decision" in payload["catalog_contract"]["requirements"]["response"]
    assert "data.delivery_decision.desktop_agent_release_candidate" in payload["catalog_contract"]["requirements"]["response"]
    assert "data.delivery_decision.full_product_status" in payload["catalog_contract"]["requirements"]["response"]
    assert "data.delivery_decision" in payload["catalog_contract"]["release"]["response"]
    assert "data.delivery_decision.desktop_agent_release_candidate" in payload["catalog_contract"]["release"]["response"]
    assert "data.delivery_decision.full_product_status" in payload["catalog_contract"]["release"]["response"]
    assert "data.delivery_decision.remaining_variant_blocker_count" in payload["catalog_contract"]["release"]["response"]
    assert "data.delivery_decision.variant_next_gate_count" in payload["catalog_contract"]["release"]["response"]
    assert "data.release_preflight" in payload["catalog_contract"]["release"]["response"]
    assert "release_preflight" in payload["catalog_contract"]
    assert "data.package_candidate_ready" in payload["catalog_contract"]["release_preflight"]["response"]
    assert "data.final_submission_blockers" in payload["catalog_contract"]["release_preflight"]["response"]
    assert "data.latest_acceptance_evidence" in payload["catalog_contract"]["release"]["response"]
    assert "data.qyyjt_benchmark.summary.authorization_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.unsupported_profile" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.p0_queue" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.field_contracts" in payload["catalog_contract"]["connectors"]["response"]
    assert payload["catalog_contract"]["connectors"]["response"]["data.qyyjt_benchmark.summary.field_contracts"].startswith("all 45 QYYJT")
    assert "data.qyyjt_benchmark.summary.public_origin_plans" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.public_origin_execution_queue" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.public_origin_execution_summary" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.summary.public_origin_execution_summary.report_section_batches" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.qyyjt_benchmark.rows[]" in payload["catalog_contract"]["connectors"]["response"]
    assert "data.monitoring_seed.recovery_execution_summary" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.recovery_execution_queue" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.relationship_candidate_execution_plan" in payload["catalog_contract"]["investigate"]["response"]
    assert "data.monitoring_seed.recurring_failure_patterns" in payload["investigate_contract"]["response"]
    assert "data.monitoring_seed.source_repair_priority_queue" in payload["investigate_contract"]["response"]
    assert "data.monitoring_seed.source_health_trend_snapshot" in payload["investigate_contract"]["response"]
    assert "data.source_failure_summary.recurring_failure_patterns" in payload["investigate_contract"]["response"]
    assert "data.report_exports" in payload["investigate_contract"]["response"]
    assert "data.report_exports.agent_decision_digest" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.integrity_verifier_entrypoint" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.verifier_output_fields" in payload["investigate_contract"]["response"]
    assert "bundle_ready_to_verify" in payload["investigate_contract"]["response"]["data.report_exports.directory_bundle.verifier_output_fields"]
    assert "data.report_exports.directory_bundle.verification_recipe" in payload["investigate_contract"]["response"]
    assert "required verifier output fields" in payload["investigate_contract"]["response"]["data.report_exports.directory_bundle.verification_recipe"]
    assert "data.report_exports.directory_bundle.manifest_fields" in payload["investigate_contract"]["response"]
    assert "file_manifest sha256 rows" in payload["investigate_contract"]["response"]["data.report_exports.directory_bundle.manifest_fields"]
    assert "data.report_exports.directory_bundle.agent_handoff" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.delivery_files" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.bundle_integrity" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.bundle_verification" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.delivery_checklist" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.trust_boundaries" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.decision_digest" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.next_actions" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.acceptance_closure" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.reliance_limitations" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.relationship_resolution" in payload["investigate_contract"]["response"]
    assert "data.report_exports.directory_bundle.agent_handoff.relationship_resolution.verification_queue" in payload["investigate_contract"]["response"]
    assert "data.report_exports.portable_html.first_screen_handoff_cards" in payload["investigate_contract"]["response"]
    assert "data.report_exports.portable_html.first_screen_handoff_card_count" in payload["investigate_contract"]["response"]
    assert "data.report_exports.portable_html.first_screen_handoff_source" in payload["investigate_contract"]["response"]
    assert "data.report_exports.portable_html.delivery_checklist_source" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.operational_handoff" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.operational_handoff.cards.acceptance_closure_summary" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.operational_handoff.cards.reliance_limitation_top_action" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.relationship_capital_appendix" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.delivery_checklist" in payload["investigate_contract"]["response"]
    assert "data.report_exports.print_package.docx.renderer_capabilities" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_recommended_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_recommended_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_retry_policy" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_retryable" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_retry_max_attempts" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_recommended_step_ready_to_run" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_resilience_recommended_step_blocked_reason" in payload["investigate_contract"]["response"]
    assert "data.monitoring_seed.recovery_execution_queue.queue.replay_route" in payload["investigate_contract"]["response"]
    assert "data.monitoring_seed.recovery_execution_queue.blocked_preview.replay_route" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.operator_work_queue_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.operator_work_p0_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.operator_work_ready_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.operator_work_top_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.operator_work_queue" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.reliance_limitations" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.reliance_limitation_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.can_make_clean_conclusion" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.acceptance_closure_summary" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.acceptance_closure_status" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.acceptance_closure_blocking_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.acceptance_closure_top_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_repair_priority_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_repair_p0_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_repair_top_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_source_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_blocked_source_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_top_source" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_digest" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_digest.actionability" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_digest.subject_risk_verdict_allowed" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.source_health_trend_policy" in payload["investigate_contract"]["response"]
    assert "data.qyyjt_public_origin_handoff" in payload["investigate_contract"]["response"]
    assert "data.qyyjt_public_origin_handoff.report_section_batches" in payload["investigate_contract"]["response"]
    assert "data.qyyjt_public_origin_handoff.section_work_orders" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_verification_queue_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_verification_queue" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_verification_top_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_graph_audit_queue_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_graph_audit_queue" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_graph_audit_top_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_lead_only_edge_count" in payload["investigate_contract"]["response"]
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
    assert "data.one_click_readiness.public_origin_gap_bridge" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.public_origin_gap_bridge_top_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.control_path_closure_needed" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.control_path_signal_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.control_path_highest_hop_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.control_path_source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.control_path_closure_step" in payload["investigate_contract"]["response"]
    assert "data.graph.diagnostics.subject_profile.controller_candidates.source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.graph.diagnostics.subject_profile.controller_candidates.control_path_summaries.source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.graph.diagnostics.subject_profile.relationship_graph.edges.source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.enterprise_cognition.control_ownership.controller_candidates.source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.enterprise_cognition.control_ownership.control_paths.source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.goods_economics_closure_needed" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.goods_economics_signal_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.goods_economics_closure_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.people_control_closure_needed" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.people_control_signal_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.people_control_closure_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_watch_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_execution_step_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_candidate_top_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_status" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_unresolved_reason" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_next_action" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_relationship_closure_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.graph_capital_exposure" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.graph_capital_exposure_top_step" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.graph_capital_exposure_alignment_status" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.graph_capital_exposure_source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.capital_pressure_source_family_summary" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_evidence_backed_edge_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_auditable_edge_count" in payload["investigate_contract"]["response"]
    assert "data.one_click_readiness.relationship_missing_evidence_edge_count" in payload["investigate_contract"]["response"]
    assert "data.summary.capital_exposure" in payload["risk_graph_contract"]["response"]
    assert "relationship audit queue" in payload["risk_graph_contract"]["response"]["data.summary.capital_exposure"]
    assert "data.persona_surface" in payload["catalog_contract"]
