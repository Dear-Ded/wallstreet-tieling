#!/usr/bin/env python3
"""Smoke tests for adapter audit CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_adapter_audit_cli_emits_rows() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "adapter_audit.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["total"] >= 4
    assert payload["production_ready"] >= 1
    assert payload["filtered_count"] == payload["total"]
    rest_row = next(row for row in payload["rows"] if row["name"] == "multi_datasource_rest_api")
    assert rest_row["quality_gate"]["ok"] is True
    assert rest_row["quality_gate"]["paths"]


def test_adapter_audit_cli_filters_needs_work() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "adapter_audit.py"),
            "--needs-work",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["filtered_count"] >= 0
    assert all(row["blockers"] for row in payload["rows"])
