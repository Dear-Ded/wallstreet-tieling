#!/usr/bin/env python3
"""Tests for the retrieval-plan CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_retrieval_plan_cli_outputs_json_plan() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "retrieval_plan.py"),
            "测试科技有限公司",
            "--limit",
            "3",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["seed_company"] == "测试科技有限公司"
    assert len(payload["tasks"]) == 3
    assert any("实际控制人" in task["query"] for task in payload["tasks"])
    assert "coverage_domains" in payload
