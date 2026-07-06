#!/usr/bin/env python3
"""Smoke tests for the batch risk-monitoring CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_risk_monitor_cli_offline_fixture_is_executable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_monitor.py"),
            "Demo Monitor A Co., Ltd.",
            "Demo Monitor B Co., Ltd.",
            "--offline-fixture",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
            "--run-store",
            str(tmp_path / "monitor-runs.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["company_count"] == 2
    assert payload["ok_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["run_id"].startswith("monitor:")
    assert payload["store_summary"]["total_events"] == 2
    assert len(payload["alerts"]) == 2
    assert (tmp_path / "monitor-runs.jsonl").exists()


def test_risk_monitor_cli_reads_companies_file(tmp_path) -> None:
    companies = tmp_path / "companies.txt"
    companies.write_text(
        "# watchlist\nDemo File A Co., Ltd.\n\nDemo File B Co., Ltd.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_monitor.py"),
            "--companies-file",
            str(companies),
            "--offline-fixture",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
            "--run-store",
            str(tmp_path / "monitor-runs.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["company_count"] == 2
    assert {item["company"] for item in payload["results"]} == {
        "Demo File A Co., Ltd.",
        "Demo File B Co., Ltd.",
    }


def test_risk_monitor_cli_lists_history(tmp_path) -> None:
    run_store = tmp_path / "monitor-runs.jsonl"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_monitor.py"),
            "Demo History Co., Ltd.",
            "--offline-fixture",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
            "--run-store",
            str(run_store),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_monitor.py"),
            "--history",
            "--run-store",
            str(run_store),
            "--company-filter",
            "Demo History Co., Ltd.",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["run_count"] == 1
    assert payload["company_filter"] == "Demo History Co., Ltd."
    assert payload["runs"][0]["results"][0]["company"] == "Demo History Co., Ltd."


def test_risk_monitor_cli_reports_source_health_from_run_store(tmp_path) -> None:
    run_store = tmp_path / "monitor-runs.jsonl"
    run_store.write_text(
        json.dumps(
            {
                "run_id": "monitor:health",
                "started_at": "2026-06-20T00:00:00Z",
                "completed_at": "2026-06-20T00:00:01Z",
                "company_count": 1,
                "ok_count": 1,
                "failed_count": 0,
                "results": [
                    {
                        "company": "Demo Source Health Co., Ltd.",
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

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_monitor.py"),
            "--source-health",
            "--run-store",
            str(run_store),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["run_count"] == 1
    assert payload["source_count"] == 2
    assert payload["sources"]["source_a"]["availability_ratio"] == 1.0
    assert payload["sources"]["source_b"]["down_count"] == 1
    assert payload["connector_recovery_queue"][0]["source"] == "source_b"
    assert payload["connector_recovery_queue"][0]["priority"] == "P0"
    assert payload["connector_recovery_queue"][0]["status"] == "source_down"
    assert payload["release_readiness_warning_count"] == 1
    assert payload["release_readiness_warnings"][0]["source"] == "source_b"
