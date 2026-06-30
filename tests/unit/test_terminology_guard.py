#!/usr/bin/env python3
"""Tests for the public-release terminology guard."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.terminology_guard import normalize_text, scan_text


ROOT = Path(__file__).resolve().parent.parent.parent


def _u(*codepoints: int) -> str:
    return "".join(chr(item) for item in codepoints)


def test_scan_text_reports_professional_replacement_without_raw_match() -> None:
    text = "需要" + _u(0x7ED5, 0x8FC7, 0x767B, 0x5F55, 0x9650, 0x5236)

    findings = scan_text(text, path="demo.md")

    assert len(findings) == 1
    assert findings[0].replacement == "用户授权会话接入"
    assert findings[0].legacy_label == "non-standard session-access wording"


def test_normalize_text_rewrites_multiple_sensitive_families() -> None:
    text = (
        "支持"
        + _u(0x9A8C, 0x8BC1, 0x7801, 0x7ED5, 0x8FC7)
        + "和"
        + _u(0x5F00, 0x76D2)
        + "能力"
    )

    normalized = normalize_text(text)

    assert "挑战响应自动化处理" in normalized
    assert "深度主体画像" in normalized


def test_terminology_guard_cli_scans_files(tmp_path: Path) -> None:
    sample = tmp_path / "sample.md"
    sample.write_text(
        "文档提到了" + _u(0x793E, 0x5DE5, 0x5E93),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "terminology_guard.py"),
            str(sample),
            "--format",
            "json",
            "--fail-on",
            "none",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["total"] == 1
    assert payload["findings"][0]["replacement"] == "多源公开主体数据库"


def test_terminology_guard_cli_can_fix_markdown(tmp_path: Path) -> None:
    sample = tmp_path / "sample.md"
    sample.write_text(
        "文档提到了" + _u(0x4EBA, 0x8089),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "terminology_guard.py"),
            str(sample),
            "--fix",
            "--fail-on",
            "none",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert sample.read_text(encoding="utf-8") == "文档提到了公开主体线索核验"
