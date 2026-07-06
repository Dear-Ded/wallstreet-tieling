#!/usr/bin/env python3
"""Tests for batch risk monitoring runs."""
from __future__ import annotations

import pytest

from core.risk_discovery_pipeline import offline_enforcement_fixture
from core.risk_monitor import RiskMonitor, RiskMonitorRun, RiskMonitorRunStore, run_monitor_once


@pytest.mark.asyncio
async def test_risk_monitor_runs_multiple_companies_and_persists_alerts(tmp_path) -> None:
    store_path = tmp_path / "risk-events.jsonl"
    monitor = RiskMonitor(risk_event_store=store_path)
    companies = ["Demo Alpha Co., Ltd.", "Demo Beta Co., Ltd.", "Demo Alpha Co., Ltd."]
    records = {
        company: offline_enforcement_fixture(company)
        for company in {"Demo Alpha Co., Ltd.", "Demo Beta Co., Ltd."}
    }

    run = await monitor.run_once(companies, records_by_company=records)

    assert run.company_count == 2
    assert run.run_id.startswith("monitor:")
    assert run.ok_count == 2
    assert run.failed_count == 0
    assert len(run.results) == 2
    assert run.store_summary["total_events"] == 2
    assert len(run.alerts) == 2
    assert {item["company"] for item in run.results} == {
        "Demo Alpha Co., Ltd.",
        "Demo Beta Co., Ltd.",
    }
    assert all(item["delta"]["new_event_count"] == 1 for item in run.results)
    assert run.to_dict()["alerts"][0]["event"]["severity"] == "high"


@pytest.mark.asyncio
async def test_risk_monitor_persists_run_ledger_with_deltas(tmp_path) -> None:
    store_path = tmp_path / "risk-events.jsonl"
    run_store = RiskMonitorRunStore(tmp_path / "monitor-runs.jsonl")
    monitor = RiskMonitor(
        risk_event_store=store_path,
        monitor_run_store=run_store,
    )
    company = "Demo Run Ledger Co., Ltd."

    run = await monitor.run_once(
        [company],
        records_by_company={company: offline_enforcement_fixture(company)},
    )

    rows = run_store.list_runs(company=company)
    assert len(rows) == 1
    assert rows[0]["run_id"] == run.run_id
    assert rows[0]["results"][0]["company"] == company
    assert rows[0]["results"][0]["delta"]["new_event_count"] == 1
    assert rows[0]["results"][0]["retrieval_summary"]["execution_state"] == "risk_events_found"


def test_risk_monitor_run_store_summarizes_source_health_trends(tmp_path) -> None:
    run_store = RiskMonitorRunStore(tmp_path / "monitor-runs.jsonl")
    run_store.append(
        RiskMonitorRun(
            run_id="monitor:first",
            started_at="2026-06-20T00:00:00Z",
            completed_at="2026-06-20T00:00:01Z",
            company_count=1,
            ok_count=1,
            failed_count=0,
            results=[
                {
                    "company": "Demo Health Co., Ltd.",
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
                            "trace_id": "monitor:first:source:001",
                        }
                    ],
                }
            ],
            failures=[],
            store_summary={},
            alerts=[],
        )
    )
    run_store.append(
        RiskMonitorRun(
            run_id="monitor:second",
            started_at="2026-06-20T00:01:00Z",
            completed_at="2026-06-20T00:01:01Z",
            company_count=1,
            ok_count=1,
            failed_count=0,
            results=[
                {
                    "company": "Demo Health Co., Ltd.",
                    "retrieval_summary": {
                        "source_routing": {
                            "health": {
                                "source_a": True,
                                "source_b": True,
                            }
                        }
                    },
                    "source_diagnostics": [
                        {
                            "source": "source_c",
                            "status": "timeout",
                            "failure_category": "timeout",
                            "objective": "bond credit recovery",
                            "trace_id": "monitor:second:source:001",
                        }
                    ],
                }
            ],
            failures=[],
            store_summary={},
            alerts=[],
        )
    )

    trends = run_store.source_health_trends(company="Demo Health Co., Ltd.")

    assert trends["run_count"] == 2
    assert trends["source_count"] == 3
    assert trends["sources"]["source_a"]["availability_ratio"] == 1.0
    assert trends["sources"]["source_a"]["ok_count"] == 2
    assert trends["sources"]["source_b"]["ok_count"] == 1
    assert trends["sources"]["source_b"]["down_count"] == 1
    assert trends["sources"]["source_b"]["companies"] == ["Demo Health Co., Ltd."]
    assert trends["sources"]["source_c"]["down_count"] == 2
    assert trends["failure_category_counts"]["timeout"] == 2
    assert trends["failure_category_counts"]["source_unavailable"] == 1
    pattern = trends["recurring_failure_patterns"][0]
    assert pattern["source"] == "source_c"
    assert pattern["failure_category"] == "timeout"
    assert pattern["domain"] == "financing_capital_markets"
    assert pattern["count"] == 2
    assert pattern["is_recurring"] is True
    assert "larger timeout" in pattern["operator_action"]
    recovery_queue = trends["connector_recovery_queue"]
    assert recovery_queue[0]["source"] == "source_c"
    assert recovery_queue[0]["priority"] == "P0"
    assert recovery_queue[0]["status"] == "degraded_connector"
    assert recovery_queue[0]["recurring_failure_count"] == 1
    assert recovery_queue[0]["release_warning"] is True
    assert "source_availability_recovers" in recovery_queue[0]["done_condition"]
    warnings = trends["release_readiness_warnings"]
    assert trends["release_readiness_warning_count"] == len(warnings)
    assert warnings[0]["source"] == "source_c"
    assert warnings[0]["failure_category"] == "timeout"
    assert "stronger readiness claims" in warnings[0]["impact"]


@pytest.mark.asyncio
async def test_risk_monitor_isolates_company_failures(tmp_path) -> None:
    class FailingPipeline:
        def __init__(self, risk_event_store):
            self.risk_event_store = risk_event_store

        async def run(self, company, **kwargs):
            raise RuntimeError(f"cannot scan {company}")

    store = RiskMonitor(risk_event_store=tmp_path / "risk-events.jsonl").risk_event_store
    monitor = RiskMonitor(
        pipeline=FailingPipeline(store),
        risk_event_store=store,
    )

    run = await monitor.run_once(["Demo Failure Co., Ltd."])

    assert run.ok_count == 0
    assert run.failed_count == 1
    assert run.failures[0]["company"] == "Demo Failure Co., Ltd."
    assert "cannot scan Demo Failure Co., Ltd." in run.failures[0]["error"]


def test_run_monitor_once_sync_helper(tmp_path) -> None:
    company = "Demo Sync Co., Ltd."

    run = run_monitor_once(
        [company],
        risk_event_store=tmp_path / "risk-events.jsonl",
        monitor_run_store=tmp_path / "monitor-runs.jsonl",
        records_by_company={company: offline_enforcement_fixture(company)},
    )

    assert run.company_count == 1
    assert run.ok_count == 1
    assert run.alerts[0]["company"] == company
    assert run.results[0]["source_diagnostics"]
