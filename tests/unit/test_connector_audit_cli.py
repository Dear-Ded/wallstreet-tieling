#!/usr/bin/env python3
"""Smoke tests for connector audit CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_connector_audit_cli_emits_summary() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "connector_audit.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["total"] >= 5
    assert payload["production_ready"] >= 5
    assert payload["filtered_count"] == payload["total"]


def test_connector_audit_cli_filters_production_ready() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "connector_audit.py"),
            "--production-ready",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["filtered_count"] >= 3
    assert {item["name"] for item in payload["filtered"]} >= {
        "multi_datasource_rest_api",
        "default_public_intel",
        "qyyjt_tool",
        "telegram_bot_public_service",
    }
