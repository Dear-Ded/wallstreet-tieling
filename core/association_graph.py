#!/usr/bin/env python3
"""Dependency-free SVG association-graph renderer for the entity engine.

``core/entity_association.py`` produces ``entities`` + ``associations`` but
no visualization. This module turns that output into an inline, print-
friendly SVG relationship graph: nodes are entities (colored by type),
edges are associations (styled by strength). It is the "dig to the root"
view: who is linked to whom, at a glance.

Design constraints (same as core/report_charts.py):
- zero runtime dependencies beyond the standard library;
- every string that reaches the SVG is HTML-escaped;
- graceful degradation: empty or malformed input yields an empty string,
  never an exception, so report generation can never break because of it.
"""

from __future__ import annotations

import hashlib
import html
import math
from typing import Any, Iterable, Mapping


_TYPE_COLORS = {
    "person": ("#2f5d7d", "#1d3a4f"),      # blue
    "business": ("#9f1d20", "#6e1416"),    # red
    "phone": ("#2f7d4f", "#1e5233"),       # green
    "address": ("#a16f2b", "#6e4c1d"),     # gold/brown
    "email": ("#6b5b8e", "#473d60"),       # purple
    "domain": ("#0f766e", "#0a4f4b"),      # teal
}
_TYPE_LABELS = {
    "person": "自然人",
    "business": "企业",
    "phone": "电话",
    "address": "地址",
    "email": "邮箱",
    "domain": "域名",
}
_DEFAULT_NODE = ("#8a7a63", "#5c5347")

# seed type -> entity type (engine seeds use business_name/person_name)
_SEED_TYPE_MAP = {
    "business_name": "business",
    "person_name": "person",
}

_STRENGTH_STYLE = {
    # strength -> (stroke_width, dasharray or "")
    "exact": (3.0, ""),
    "strong": (2.0, ""),
    "weak": (1.5, "6,4"),
}
_PATTERN_EDGE_COLOR = "#b7791f"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _shorten(text: str, limit: int = 12) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _norm_entities(entities: Any) -> dict[str, dict[str, Any]]:
    """Accept the engine's entity list (or an id-keyed dict); return id->node."""
    out: dict[str, dict[str, Any]] = {}
    if isinstance(entities, Mapping):
        items: Iterable[Any] = entities.values()
    elif isinstance(entities, (list, tuple)):
        items = entities
    else:
        return out
    for e in items:
        if not isinstance(e, Mapping):
            continue
        eid = str(e.get("id") or "").strip()
        if not eid or eid in out:
            continue
        etype = str(e.get("type") or "unknown").strip().lower()
        display = str(e.get("display") or e.get("value") or eid).strip()
        sources = e.get("sources")
        out[eid] = {
            "type": etype if etype in _TYPE_COLORS else "unknown",
            "value": str(e.get("value") or "").strip(),
            "display": display,
            "sources": list(sources) if isinstance(sources, (list, tuple)) else [],
        }
    return out


def _norm_edges(associations: Any) -> list[dict[str, Any]]:
    """Keep only real graph edges (entries carrying from/to entity ids)."""
    out: list[dict[str, Any]] = []
    if not isinstance(associations, (list, tuple)):
        return out
    for a in associations:
        if not isinstance(a, Mapping):
            continue
        frm = str(a.get("from") or "").strip()
        to = str(a.get("to") or "").strip()
        if not frm or not to or frm == to:
            continue
        strength = str(a.get("strength") or "weak").strip().lower()
        if strength not in _STRENGTH_STYLE:
            strength = "weak"
        out.append({
            "from": frm,
            "to": to,
            "relation": str(a.get("relation") or "关联").strip(),
            "strength": strength,
            "sources": list(a.get("sources")) if isinstance(a.get("sources"), (list, tuple)) else [],
            "note": str(a.get("note") or "").strip(),
        })
    return out


def _layout(nodes: dict[str, dict[str, Any]],
            edges: list[dict[str, Any]],
            seed: str | None,
            width: int, height: int) -> dict[str, tuple[float, float]]:
    """BFS-layered radial layout: seed at center, others on rings by hop distance."""
    cx, cy = width / 2.0, height / 2.0
    if not nodes:
        return {}
    adjacency: dict[str, set[str]] = {nid: set() for nid in nodes}
    for e in edges:
        adjacency.setdefault(e["from"], set()).add(e["to"])
        adjacency.setdefault(e["to"], set()).add(e["from"])

    if seed and seed in nodes:
        root = seed
    else:
        root = max(nodes, key=lambda nid: (len(adjacency.get(nid, ())), -_stable_hash(nid)))

    # BFS layers
    layers: list[list[str]] = []
    seen = {root}
    frontier = [root]
    while frontier:
        layers.append(frontier)
        nxt: list[str] = []
        for nid in frontier:
            for nb in sorted(adjacency.get(nid, ()), key=lambda x: (_stable_hash(x))):
                if nb not in seen and nb in nodes:
                    seen.add(nb)
                    nxt.append(nb)
        frontier = nxt
    # orphan nodes (no path to root) on the outermost ring
    orphans = [nid for nid in nodes if nid not in seen]
    if orphans:
        layers.append(sorted(orphans, key=_stable_hash))

    pos: dict[str, tuple[float, float]] = {}
    pos[root] = (cx, cy)
    ring_gap = min(width, height) / 2.0 / max(len(layers), 1) * 0.92
    for li in range(1, len(layers)):
        ring = layers[li]
        radius = ring_gap * li
        # keep inside the canvas with margin
        radius = min(radius, min(width, height) / 2.0 - 46)
        n = len(ring)
        for i, nid in enumerate(ring):
            angle = 2 * math.pi * i / n - math.pi / 2
            # deterministic slight jitter to break perfect symmetry
            jitter = ((_stable_hash(nid) % 100) / 100.0 - 0.5) * 0.22
            angle += jitter
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            pos[nid] = (round(x, 1), round(y, 1))
    return pos


def _prune(nodes: dict[str, dict[str, Any]],
           edges: list[dict[str, Any]],
           seed: str | None,
           max_nodes: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Cap the graph: keep the seed plus highest-degree nodes."""
    if len(nodes) <= max_nodes or max_nodes <= 0:
        return nodes, edges
    degree: dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        degree[e["from"]] = degree.get(e["from"], 0) + 1
        degree[e["to"]] = degree.get(e["to"], 0) + 1
    keep = set()
    if seed and seed in nodes:
        keep.add(seed)
    ranked = sorted(nodes, key=lambda nid: (-degree.get(nid, 0), _stable_hash(nid)))
    for nid in ranked:
        if len(keep) >= max_nodes:
            break
        keep.add(nid)
    nodes = {nid: n for nid, n in nodes.items() if nid in keep}
    edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return nodes, edges


def render_svg(
    entities: Any,
    associations: Any,
    *,
    seed: str | dict[str, Any] | None = None,
    patterns: Any = None,
    max_nodes: int = 60,
    width: int = 720,
    height: int = 560,
) -> str:
    """Render the entity association graph as an inline SVG string.

    ``entities``: engine entity list (or id-keyed dict).
    ``associations``: engine association list; only entries with
    ``from``/``to`` become edges.
    ``seed``: entity id (or ``{"type","value"}`` seed dict) placed at center.
    ``patterns``: optional ``interesting_patterns`` list; patterns listing
    entity ids become weak gold "pattern" edges with the pattern as tooltip.
    """
    try:
        return _render_svg(entities, associations, seed=seed,
                           patterns=patterns, max_nodes=max_nodes,
                           width=width, height=height)
    except Exception:
        return ""


def _render_svg(entities: Any,
                associations: Any,
                *,
                seed: str | dict[str, Any] | None,
                patterns: Any,
                max_nodes: int,
                width: int,
                height: int) -> str:
    nodes = _norm_entities(entities)
    if not nodes:
        return ""
    edges = _norm_edges(associations)

    # seed may be an id string or a {"type","value"} dict (engine seed form).
    # Engine seed types are business_name/person_name; entity types are
    # business/person -- map them before matching.
    seed_id: str | None = None
    if isinstance(seed, str) and seed in nodes:
        seed_id = seed
    elif isinstance(seed, Mapping):
        stype = _SEED_TYPE_MAP.get(str(seed.get("type") or ""),
                                   str(seed.get("type") or ""))
        svalue = str(seed.get("value") or "")
        for nid, n in nodes.items():
            if n["type"] == stype and (n.get("display") == svalue or
                                       n.get("value") == svalue):
                seed_id = nid
                break
        if seed_id is None and svalue:
            for nid, n in nodes.items():
                if n.get("display") == svalue or n.get("value") == svalue:
                    seed_id = nid
                    break

    # pattern overlays: weak gold edges between pattern member ids
    if isinstance(patterns, (list, tuple)):
        for p in patterns:
            if not isinstance(p, Mapping):
                continue
            members = p.get("entities")
            if not isinstance(members, (list, tuple)):
                continue
            ids = [str(m) for m in members if str(m) in nodes]
            label = str(p.get("pattern") or "pattern")
            desc = str(p.get("description") or "")
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({
                        "from": ids[i], "to": ids[j],
                        "relation": "pattern:" + label,
                        "strength": "weak",
                        "sources": [],
                        "note": desc,
                        "pattern_edge": True,
                    })

    # drop edges pointing at unknown nodes
    edges = [e for e in edges if e["from"] in nodes and e["to"] in nodes]
    if not edges and len(nodes) == 1:
        pass  # single node still renders
    elif not edges:
        # no edges at all: still render nodes in a circle so the section
        # shows what was found; layout() handles the orphan ring.
        pass

    nodes, edges = _prune(nodes, edges, seed_id, max_nodes)
    pos = _layout(nodes, edges, seed_id, width, height)

    degree: dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        degree[e["from"]] += 1
        degree[e["to"]] += 1

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="实体关联图谱" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="#fffdf8"/>',
    ]

    # edges first (under nodes)
    for e in edges:
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        w, dash = _STRENGTH_STYLE[e["strength"]]
        color = _PATTERN_EDGE_COLOR if e.get("pattern_edge") else "#9a8f7d"
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        tip_bits = [e["relation"]]
        if e["note"]:
            tip_bits.append(e["note"][:120])
        if e["sources"]:
            tip_bits.append("来源: " + ", ".join(e["sources"][:4]))
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="{w}"{dash_attr} opacity="0.75">'
            f"<title>{_esc(' | '.join(tip_bits))}</title></line>"
        )

    # nodes
    for nid, n in nodes.items():
        x, y = pos[nid]
        fill, stroke = _TYPE_COLORS.get(n["type"], _DEFAULT_NODE)
        r = 10 + min(8, degree.get(nid, 0))
        if nid == seed_id:
            r += 3
        label = _shorten(n["display"])
        tip_bits = [f"{_TYPE_LABELS.get(n['type'], n['type'])}: {n['display']}"]
        if n["sources"]:
            tip_bits.append("来源: " + ", ".join(n["sources"][:5]))
        tip_bits.append(f"关联度: {degree.get(nid, 0)}")
        if nid == seed_id:
            tip_bits.append("调查起点")
        parts.append(
            f'<g>'
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2">'
            f"<title>{_esc(' | '.join(tip_bits))}</title></circle>"
        )
        if nid == seed_id:
            parts.append(
                f'<circle cx="{x}" cy="{y}" r="{r + 5}" fill="none" '
                f'stroke="{stroke}" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.8"/>'
            )
        parts.append(
            f'<text x="{x}" y="{y + r + 14}" font-size="11" text-anchor="middle" fill="#3d3a34">'
            f"{_esc(label)}</text>"
            f"</g>"
        )

    # legend
    lx, ly = 12, 16
    parts.append(f'<g font-size="11" fill="#3d3a34">')
    parts.append(f'<text x="{lx}" y="{ly}" font-weight="bold">图例</text>')
    ly += 16
    for tkey in ("person", "business", "phone", "address", "email", "domain"):
        fill, _ = _TYPE_COLORS[tkey]
        parts.append(
            f'<circle cx="{lx + 6}" cy="{ly - 4}" r="6" fill="{fill}"/>'
            f'<text x="{lx + 18}" y="{ly}">{_TYPE_LABELS[tkey]}</text>'
        )
        lx += 78
        if lx > width - 160:
            lx = 12
            ly += 18
    ly += 20
    lx = 12
    for skey, cname in (("exact", "精确"), ("strong", "强"), ("weak", "弱")):
        w, dash = _STRENGTH_STYLE[skey]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 30}" y2="{ly - 4}" '
            f'stroke="#9a8f7d" stroke-width="{w}"{dash_attr}/>'
            f'<text x="{lx + 36}" y="{ly}">{cname}关联</text>'
        )
        lx += 100
    parts.append(
        f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 30}" y2="{ly - 4}" '
        f'stroke="{_PATTERN_EDGE_COLOR}" stroke-width="1.5" stroke-dasharray="6,4"/>'
        f'<text x="{lx + 36}" y="{ly}">模式信号</text>'
    )
    parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)


def build_association_graph_section(
    assoc_result: Mapping[str, Any] | None = None,
    *,
    entities: Any = None,
    associations: Any = None,
    patterns: Any = None,
    seed: Any = None,
    max_nodes: int = 60,
) -> str:
    """Build the full "实体关联图谱" HTML section for the portable report.

    Accepts either the raw ``associate()`` result dict, or explicit
    ``entities``/``associations``/``patterns``/``seed`` kwargs. Returns ""
    when there is nothing graphable, so callers can simply omit the section.
    """
    try:
        if isinstance(assoc_result, Mapping):
            entities = assoc_result.get("entities", entities)
            associations = assoc_result.get("associations", associations)
            patterns = assoc_result.get("interesting_patterns", patterns)
            seed = assoc_result.get("seed", seed)
        svg = render_svg(entities, associations, seed=seed,
                         patterns=patterns, max_nodes=max_nodes)
        if not svg:
            return ""
        node_count = len(_norm_entities(entities))
        edge_count = len(_norm_edges(associations))
        return (
            '    <section class="assoc-graph-section" aria-label="实体关联图谱">\n'
            '      <h2>实体关联图谱</h2>\n'
            f'      <p class="assoc-graph-meta">节点 {node_count} · 关联边 {edge_count} · '
            '悬停查看详情（关联均为调查线索，非身份断言）</p>\n'
            '      <div class="assoc-graph-wrap">\n'
            f"{svg}\n"
            "      </div>\n"
            "    </section>\n"
        )
    except Exception:
        return ""


ASSOCIATION_GRAPH_CSS = """
    .assoc-graph-section{background:var(--glass);border:1px solid #d5c6ae;border-radius:18px;padding:18px 20px;margin:18px 0;box-shadow:0 18px 40px rgba(31,41,51,.07);}
    .assoc-graph-section h2{font-size:18px;margin:0 0 6px;color:#9f1d20;}
    .assoc-graph-meta{font-size:12px;color:#7b6b58;margin:0 0 12px;}
    .assoc-graph-wrap{background:#fffdf8;border:1px solid #eadfce;border-radius:14px;padding:10px;}
    .assoc-graph-wrap svg{display:block;max-width:100%;height:auto;}
    @media print{.assoc-graph-section{box-shadow:none;break-inside:avoid;}}
"""
