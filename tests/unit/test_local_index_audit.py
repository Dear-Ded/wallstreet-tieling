#!/usr/bin/env python3
"""Tests for local subject-index audit contract."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from adapters.multi_datasource import LocalIndexDataSource


ROOT = Path(__file__).resolve().parent.parent.parent


def test_local_index_audit_marks_clean_jsonl_ready(tmp_path: Path) -> None:
    index_path = tmp_path / "subjects.jsonl"
    index_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "DEMO WATCHLIST CO",
                        "dataset": "reviewed-public-watchlist",
                        "category": "sanctions",
                        "severity": "high",
                        "source_url": "https://example.invalid/source/demo",
                    }
                ),
                json.dumps(
                    {
                        "firm_name": "DEMO PROCUREMENT CO",
                        "dataset": "reviewed-procurement",
                        "category": "procurement",
                        "severity": "medium",
                        "url": "https://example.invalid/procurement/demo",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    payload = LocalIndexDataSource.audit_index_file(index_path)

    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["record_count"] == 2
    assert payload["matchable_count"] == 2
    assert payload["provenance_count"] == 2
    assert payload["severity_counts"]["high"] == 1
    assert payload["category_counts"]["procurement"] == 1


def test_local_index_audit_flags_missing_name_and_provenance(tmp_path: Path) -> None:
    index_path = tmp_path / "subjects.csv"
    index_path.write_text(
        "name,summary,severity\n"
        "DEMO CO,Has name but no source,medium\n"
        ",Missing name and source,low\n",
        encoding="utf-8",
    )

    payload = LocalIndexDataSource.audit_index_file(index_path)

    assert payload["ok"] is False
    assert payload["status"] == "needs_review"
    assert payload["record_count"] == 2
    assert payload["matchable_count"] == 1
    assert payload["provenance_count"] == 0
    assert "some_records_missing_matchable_name" in payload["warnings"]
    assert "some_records_missing_source_or_dataset" in payload["warnings"]


def test_local_index_audit_cli_emits_json(tmp_path: Path) -> None:
    index_path = tmp_path / "subjects.json"
    index_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "name": "DEMO WATCHLIST CO",
                        "dataset": "reviewed-public-watchlist",
                        "source_url": "https://example.invalid/source/demo",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "local_index_audit.py"), str(index_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["record_count"] == 1
