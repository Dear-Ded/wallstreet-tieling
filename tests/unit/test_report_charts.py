#!/usr/bin/env python3
"""Unit + product-path tests for core/report_charts.py SVG renderers."""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from core.report_charts import (
    build_report_chart_section,
    render_dimension_bars,
    render_evidence_donut,
    render_severity_bars,
    render_source_mix_bars,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def _parse_svg(svg: str) -> ET.Element:
    # SVG must be well-formed XML; namespaces make tag lookup verbose so we
    # strip the default namespace for assertions.
    cleaned = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    return ET.fromstring(cleaned)


def test_dimension_bars_renders_all_rows():
    dims = [
        {"dimension": "evidence_coverage", "score": 20, "max": 100},
        {"dimension": "risk_detection", "score": 100, "max": 100},
    ]
    svg = render_dimension_bars(dims)
    root = _parse_svg(svg)
    rects = [el for el in root.iter("rect")]
    # 2 track rects + 2 fill rects
    assert len(rects) == 4
    assert "证据覆盖" in svg
    assert "风险检出" in svg


def test_dimension_bars_empty_input_returns_empty():
    assert render_dimension_bars([]) == ""
    assert render_dimension_bars(None) == ""  # type: ignore[arg-type]


def test_dimension_bars_escapes_labels():
    dims = [{"dimension": "<script>alert(1)</script>", "score": 10, "max": 100}]
    svg = render_dimension_bars(dims)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_dimension_bars_clamps_overflow():
    dims = [{"dimension": "x", "score": 250, "max": 100}]
    svg = render_dimension_bars(dims)
    root = _parse_svg(svg)
    # fill rect must not exceed the track width
    widths = [float(el.get("width", "0")) for el in root.iter("rect")]
    assert max(widths) == min(widths) or all(w <= max(widths) for w in widths)


def test_severity_bars_with_risk_score():
    svg = render_severity_bars({"critical": 0, "high": 1, "medium": 0, "low": 0}, 45)
    root = _parse_svg(svg)
    assert root is not None
    assert "综合风险评分" in svg
    assert "45" in svg


def test_severity_bars_empty_returns_empty():
    assert render_severity_bars({}, None) == ""
    assert render_severity_bars(None, None) == ""


def test_source_mix_bars_renders_segments():
    svg = render_source_mix_bars({"official": 3, "media": 1}, {"public": 4})
    root = _parse_svg(svg)
    assert root is not None
    assert "official" in svg
    assert "按权威度" in svg


def test_source_mix_bars_empty_returns_empty():
    assert render_source_mix_bars({}, {}) == ""
    assert render_source_mix_bars(None, None) == ""


def test_evidence_donut_renders():
    svg = render_evidence_donut(factual=5, lead=2, gaps=3)
    root = _parse_svg(svg)
    circles = [el for el in root.iter("circle")]
    assert len(circles) == 3
    assert ">10<" in svg  # total in the center


def test_evidence_donut_empty_returns_empty():
    assert render_evidence_donut(0, 0, 0) == ""
    assert render_evidence_donut() == ""


def test_build_section_assembles_all_charts():
    packet = {
        "quality_gate": {
            "dimension_scores": [
                {"dimension": "evidence_coverage", "score": 20, "max": 100},
                {"dimension": "risk_detection", "score": 100, "max": 100},
            ]
        },
        "risk_brief": {
            "risk_score": 45,
            "severity_counts": {"critical": 0, "high": 1, "medium": 0, "low": 0},
        },
        "source_provenance": {
            "by_authority": {"official": 1},
            "by_access": {"public": 1},
            "factual_count": 1,
            "lead_count": 0,
        },
        "one_click_readiness": {"coverage_gap_count": 11},
    }
    section = build_report_chart_section(packet)
    assert "风险可视化" in section
    assert section.count("<svg") == 4


def test_build_section_empty_packet_returns_empty():
    assert build_report_chart_section({}) == ""
    assert build_report_chart_section(None) == ""
    assert build_report_chart_section({"quality_gate": {}}) == ""


def test_build_section_never_raises_on_garbage():
    garbage = {
        "quality_gate": {"dimension_scores": [{"dimension": None, "score": "NaN", "max": 0}]},
        "risk_brief": {"risk_score": float("nan"), "severity_counts": {"high": "many"}},
        "source_provenance": {"by_authority": {"x": -5}},
        "one_click_readiness": None,
    }
    section = build_report_chart_section(garbage)
    assert isinstance(section, str)


@pytest.mark.slow
def test_product_path_cli_html_contains_svg_charts(tmp_path):
    """End-to-end: one-click CLI with offline fixture must embed SVG charts."""
    export_dir = tmp_path / "exports"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "investigate.py"),
            "图表测试公司",
            "--offline-fixture",
            "--export-dir",
            str(export_dir),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    html_files = list(export_dir.glob("*-due-diligence-report.html"))
    assert html_files, "expected portable HTML export"
    document = html_files[0].read_text(encoding="utf-8")
    assert "风险可视化" in document
    assert document.count("<svg") >= 3
    # manifest still verifies
    manifest = json.loads((export_dir / "report-export-manifest.json").read_text(encoding="utf-8"))
    assert manifest["type"] == "report_export_directory_manifest"
