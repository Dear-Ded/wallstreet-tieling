#!/usr/bin/env python3
"""Dependency-free SVG chart renderers for the portable HTML report.

The portable HTML report previously listed chart metadata as a plain table
("Visual evidence panels") without rendering any actual chart. This module
turns packet data that already exists -- quality-gate dimension scores,
risk severity counts, source authority mix, and evidence/lead/gap counts --
into inline, print-friendly SVG charts.

Design constraints (same as core/report_docx.py):
- zero runtime dependencies beyond the standard library;
- every string that reaches the SVG is HTML-escaped;
- charts degrade gracefully: empty or malformed input yields an empty
  string, never an exception, so report generation can never break because
  of a chart.
"""

from __future__ import annotations

import html
from typing import Any, Iterable, Mapping


# Keep the palette aligned with the portable report theme (red/gold/night).
_COLOR_GOOD = "#2f7d4f"
_COLOR_WARN = "#b7791f"
_COLOR_BAD = "#9f1d20"
_COLOR_MUTED = "#8a7a63"
_COLOR_TRACK = "#e9dfcf"

_DIMENSION_LABELS = {
    "evidence_coverage": "证据覆盖",
    "source_diversity": "来源多样性",
    "report_completeness": "报告完整度",
    "risk_detection": "风险检出",
    "data_quality": "数据质量",
}

_SEVERITY_ORDER = ["critical", "high", "medium", "low"]
_SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
}
_SEVERITY_COLORS = {
    "critical": "#9f1d20",
    "high": "#c25e2a",
    "medium": "#b7791f",
    "low": "#2f7d4f",
}


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN guard
        return default
    return number


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score_color(score: float) -> str:
    if score >= 80:
        return _COLOR_GOOD
    if score >= 50:
        return _COLOR_WARN
    return _COLOR_BAD


def render_dimension_bars(
    dimensions: Iterable[Mapping[str, Any]],
    *,
    width: int = 560,
    bar_height: int = 22,
    gap: int = 14,
    label_width: int = 110,
) -> str:
    """Render quality-gate dimension scores as horizontal bars.

    Each item may carry ``dimension`` (key), ``label`` (override),
    ``score`` and ``max``. Missing/invalid items are skipped.
    """
    rows: list[tuple[str, float, float]] = []
    for item in dimensions or []:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("dimension") or item.get("key") or "").strip()
        label = str(item.get("label") or _DIMENSION_LABELS.get(key) or key or "维度").strip()
        score = _num(item.get("score"))
        maximum = _num(item.get("max"), 100.0)
        if maximum <= 0:
            maximum = 100.0
        rows.append((label, score, maximum))
    if not rows:
        return ""
    row_h = bar_height + gap
    height = row_h * len(rows) + gap
    bar_w = width - label_width - 70
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="交付质量维度得分" xmlns="http://www.w3.org/2000/svg">'
    ]
    for index, (label, score, maximum) in enumerate(rows):
        y = gap + index * row_h
        ratio = _clamp01(score / maximum)
        fill_w = round(bar_w * ratio)
        color = _score_color(score / maximum * 100.0)
        parts.append(
            f'<text x="0" y="{y + 15}" font-size="12" fill="#3d3a34">{_esc(label)}</text>'
            f'<rect x="{label_width}" y="{y}" width="{bar_w}" height="{bar_height}" rx="6" fill="{_COLOR_TRACK}"/>'
            f'<rect x="{label_width}" y="{y}" width="{fill_w}" height="{bar_height}" rx="6" fill="{color}"/>'
            f'<text x="{label_width + bar_w + 8}" y="{y + 15}" font-size="12" fill="#3d3a34">'
            f"{_esc(f'{score:g}/{maximum:g}')}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def render_severity_bars(
    severity_counts: Mapping[str, Any] | None,
    risk_score: Any = None,
    *,
    width: int = 560,
) -> str:
    """Render risk severity counts as horizontal bars plus a risk score badge."""
    counts: dict[str, int] = {}
    for key in _SEVERITY_ORDER:
        raw = (severity_counts or {}).get(key) if isinstance(severity_counts, Mapping) else 0
        try:
            counts[key] = max(0, int(raw or 0))
        except (TypeError, ValueError):
            counts[key] = 0
    total = sum(counts.values())
    if total <= 0 and risk_score is None:
        return ""
    bar_height = 20
    gap = 12
    label_width = 60
    bar_w = width - label_width - 140
    height = (bar_height + gap) * len(_SEVERITY_ORDER) + gap + (44 if risk_score is not None else 0)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="风险严重程度分布" xmlns="http://www.w3.org/2000/svg">'
    ]
    y0 = gap
    if risk_score is not None:
        score = _num(risk_score)
        color = _score_color(100.0 - min(100.0, max(0.0, score)))
        # risk_score: higher means riskier, so invert the color scale.
        parts.append(
            f'<text x="0" y="{y0 + 16}" font-size="13" font-weight="bold" fill="#3d3a34">综合风险评分</text>'
            f'<circle cx="{width - 60}" cy="{y0 + 12}" r="20" fill="none" stroke="{_COLOR_TRACK}" stroke-width="8"/>'
            f'<circle cx="{width - 60}" cy="{y0 + 12}" r="20" fill="none" stroke="{color}" stroke-width="8" '
            f'stroke-dasharray="{2 * 3.1416 * 20 * _clamp01(score / 100.0):.1f} 999" '
            f'transform="rotate(-90 {width - 60} {y0 + 12})" stroke-linecap="round"/>'
            f'<text x="{width - 60}" y="{y0 + 17}" font-size="13" font-weight="bold" text-anchor="middle" fill="#3d3a34">'
            f"{_esc(f'{score:g}')}</text>"
        )
        y0 += 44
    peak = max(max(counts.values()), 1)
    for index, key in enumerate(_SEVERITY_ORDER):
        y = y0 + index * (bar_height + gap)
        value = counts[key]
        fill_w = round(bar_w * (value / peak))
        parts.append(
            f'<text x="0" y="{y + 14}" font-size="12" fill="#3d3a34">{_esc(_SEVERITY_LABELS[key])}</text>'
            f'<rect x="{label_width}" y="{y}" width="{bar_w}" height="{bar_height}" rx="6" fill="{_COLOR_TRACK}"/>'
            f'<rect x="{label_width}" y="{y}" width="{fill_w}" height="{bar_height}" rx="6" fill="{_SEVERITY_COLORS[key]}"/>'
            f'<text x="{label_width + bar_w + 8}" y="{y + 14}" font-size="12" fill="#3d3a34">{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_source_mix_bars(
    by_authority: Mapping[str, Any] | None,
    by_access: Mapping[str, Any] | None = None,
    *,
    width: int = 560,
) -> str:
    """Render source authority/access mix as stacked horizontal bars (100%)."""
    def _clean(mapping: Mapping[str, Any] | None) -> list[tuple[str, int]]:
        rows: list[tuple[str, int]] = []
        if isinstance(mapping, Mapping):
            for key, raw in mapping.items():
                try:
                    value = max(0, int(raw or 0))
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    rows.append((str(key), value))
        rows.sort(key=lambda item: item[1], reverse=True)
        return rows[:6]

    groups: list[tuple[str, list[tuple[str, int]]]] = [
        ("按权威度", _clean(by_authority)),
        ("按访问方式", _clean(by_access)),
    ]
    groups = [(title, rows) for title, rows in groups if rows]
    if not groups:
        return ""
    palette = ["#9f1d20", "#a16f2b", "#2f5d7d", "#2f7d4f", "#6b5b8e", "#8a7a63"]
    bar_w = width - 150
    parts = [
        f'<svg viewBox="0 0 {width} {34 * len(groups) + 10}" width="100%" role="img" '
        f'aria-label="来源构成" xmlns="http://www.w3.org/2000/svg">'
    ]
    for gi, (title, rows) in enumerate(groups):
        y = 8 + gi * 34
        total = sum(value for _, value in rows)
        parts.append(f'<text x="0" y="{y + 13}" font-size="12" fill="#3d3a34">{_esc(title)}</text>')
        x = 150
        for si, (label, value) in enumerate(rows):
            seg_w = max(2, round(bar_w * value / total)) if total else 0
            color = palette[si % len(palette)]
            parts.append(
                f'<rect x="{x}" y="{y}" width="{seg_w}" height="18" fill="{color}">'
                f"<title>{_esc(label)}: {value}</title></rect>"
            )
            x += seg_w
        legend = "  ".join(f"{label} {value}" for label, value in rows)
        parts.append(f'<text x="150" y="{y + 30}" font-size="10" fill="#6b6257">{_esc(legend)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_evidence_donut(
    factual: Any = 0,
    lead: Any = 0,
    gaps: Any = 0,
    *,
    size: int = 170,
) -> str:
    """Render evidence vs lead vs coverage-gap counts as a donut chart."""
    def _clean_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    segments = [
        ("已证实", _clean_int(factual), "#2f7d4f"),
        ("线索", _clean_int(lead), "#b7791f"),
        ("覆盖缺口", _clean_int(gaps), "#9f1d20"),
    ]
    total = sum(value for _, value, _ in segments)
    if total <= 0:
        return ""
    radius = 60
    stroke = 26
    center = size // 2
    circumference = 2 * 3.1416 * radius
    parts = [
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'aria-label="证据与线索构成" xmlns="http://www.w3.org/2000/svg">'
    ]
    offset = 0.0
    for label, value, color in segments:
        if value <= 0:
            continue
        frac = value / total
        dash = circumference * frac
        parts.append(
            f'<circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-dasharray="{dash:.1f} {circumference:.1f}" '
            f'stroke-dashoffset="{-offset:.1f}" transform="rotate(-90 {center} {center})">'
            f"<title>{_esc(label)}: {value}</title></circle>"
        )
        offset += dash
    parts.append(
        f'<text x="{center}" y="{center - 2}" font-size="20" font-weight="bold" text-anchor="middle" fill="#1f2933">{total}</text>'
        f'<text x="{center}" y="{center + 16}" font-size="11" text-anchor="middle" fill="#6b6257">证据条目</text>'
        "</svg>"
    )
    return "".join(parts)


def _packet_get(packet: Mapping[str, Any], *path: str) -> Any:
    node: Any = packet
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def build_report_chart_section(packet: Mapping[str, Any] | None) -> str:
    """Build the full "风险可视化" HTML section from an investigation packet.

    Returns an empty string when the packet carries no chartable data, so
    callers can simply omit the section.
    """
    if not isinstance(packet, Mapping):
        return ""
    quality_gate = _packet_get(packet, "quality_gate")
    risk_brief = _packet_get(packet, "risk_brief")
    source_provenance = _packet_get(packet, "source_provenance")
    readiness = _packet_get(packet, "one_click_readiness")

    charts: list[tuple[str, str]] = []

    dimensions = quality_gate.get("dimension_scores") if isinstance(quality_gate, Mapping) else None
    svg = render_dimension_bars(dimensions or [])
    if svg:
        charts.append(("交付质量维度", svg))

    severity_counts = risk_brief.get("severity_counts") if isinstance(risk_brief, Mapping) else None
    risk_score = risk_brief.get("risk_score") if isinstance(risk_brief, Mapping) else None
    svg = render_severity_bars(severity_counts, risk_score)
    if svg:
        charts.append(("风险信号", svg))

    by_authority = source_provenance.get("by_authority") if isinstance(source_provenance, Mapping) else None
    by_access = source_provenance.get("by_access") if isinstance(source_provenance, Mapping) else None
    svg = render_source_mix_bars(by_authority, by_access)
    if svg:
        charts.append(("来源构成", svg))

    factual = source_provenance.get("factual_count") if isinstance(source_provenance, Mapping) else 0
    lead = source_provenance.get("lead_count") if isinstance(source_provenance, Mapping) else 0
    gaps = readiness.get("coverage_gap_count") if isinstance(readiness, Mapping) else 0
    svg = render_evidence_donut(factual, lead, gaps)
    if svg:
        charts.append(("证据构成", svg))

    if not charts:
        return ""
    cards = "\n".join(
        f'      <div class="chart-card"><h3>{_esc(title)}</h3>{body}</div>'
        for title, body in charts
    )
    return (
        '    <section class="chart-section" aria-label="风险可视化">\n'
        '      <h2>风险可视化</h2>\n'
        '      <div class="chart-grid">\n'
        f"{cards}\n"
        "      </div>\n"
        "    </section>\n"
    )


CHART_SECTION_CSS = """
    .chart-section{background:var(--glass);border:1px solid #d5c6ae;border-radius:18px;padding:18px 20px;margin:18px 0;box-shadow:0 18px 40px rgba(31,41,51,.07);}
    .chart-section h2{font-size:18px;margin:0 0 12px;color:#9f1d20;}
    .chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;}
    .chart-card{background:#fffdf8;border:1px solid #eadfce;border-radius:14px;padding:14px 16px;}
    .chart-card h3{font-size:13px;margin:0 0 10px;color:#7b6b58;letter-spacing:.06em;}
    .chart-card svg{display:block;max-width:100%;height:auto;}
    @media print{.chart-section{box-shadow:none;break-inside:avoid;}}
"""
