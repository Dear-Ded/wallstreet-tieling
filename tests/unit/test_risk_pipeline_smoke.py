#!/usr/bin/env python3
"""Smoke tests for the offline retrieval-to-risk pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_risk_pipeline_smoke_cli_emits_monitoring_payload(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_pipeline_smoke.py"),
            "Demo Technology Co., Ltd.",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["company"] == "Demo Technology Co., Ltd."
    assert payload["risk_event_count"] >= 1
    assert payload["risk_event_summary"]["persisted"] >= 1
    assert payload["risk_event_summary"]["alert_count"] >= 1
    assert payload["first_alert"]["event"]["severity"] in {"high", "critical"}
