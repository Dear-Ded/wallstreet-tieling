#!/usr/bin/env python3
"""Unit tests for core/association_graph.py SVG graph renderer."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from core.association_graph import (
    ASSOCIATION_GRAPH_CSS,
    build_association_graph_section,
    render_svg,
)


def _parse_svg(svg: str) -> ET.Element:
    cleaned = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    return ET.fromstring(cleaned)


def _sample():
    entities = [
        {"id": "biz1", "type": "business", "value": "测试公司A", "display": "测试公司A",
         "sources": ["amap"], "context": {}},
        {"id": "biz2", "type": "business", "value": "测试公司B", "display": "测试公司B",
         "sources": ["baidu_map"], "context": {}},
        {"id": "ph1", "type": "phone", "value": "13800001111", "display": "13800001111",
         "sources": ["amap", "baidu_map"], "context": {}},
        {"id": "per1", "type": "person", "value": "张三", "display": "张三",
         "sources": ["wenshu"], "context": {}},
    ]
    associations = [
        {"from": "ph1", "to": "biz1", "relation": "contact_of",
         "strength": "strong", "sources": ["amap"], "note": ""},
        {"from": "ph1", "to": "biz2", "relation": "contact_of",
         "strength": "strong", "sources": ["baidu_map"], "note": ""},
        {"from": "biz1", "to": "biz2", "relation": "same_phone",
         "strength": "strong", "sources": ["amap"], "note": "shared phone"},
        {"from": "per1", "to": "biz1", "relation": "co_party_in_case",
         "strength": "weak", "sources": ["wenshu"], "note": "same case X"},
    ]
    return entities, associations


def test_empty_inputs_return_empty_string():
    assert render_svg([], []) == ""
    assert render_svg(None, None) == ""
    assert render_svg({}, {}) == ""
    assert render_svg("garbage", 123) == ""
    assert build_association_graph_section(None) == ""
    assert build_association_graph_section({}) == ""


def test_single_node_renders():
    entities = [{"id": "b1", "type": "business", "value": "A", "display": "A",
                 "sources": [], "context": {}}]
    svg = render_svg(entities, [])
    root = _parse_svg(svg)
    circles = [el for el in root.iter() if el.tag == "circle"]
    assert len(circles) >= 1


def test_node_and_edge_counts():
    entities, associations = _sample()
    svg = render_svg(entities, associations)
    root = _parse_svg(svg)
    # 4 entity nodes + legend circles; entity nodes carry <title> with type label
    titles = [el for el in root.iter() if el.tag == "title"]
    assert any("测试公司A" in (t.text or "") for t in titles)
    lines = [el for el in root.iter() if el.tag == "line"]
    # 4 edges + 4 legend lines
    assert len(lines) == 8


def test_strength_styling():
    entities, associations = _sample()
    svg = render_svg(entities, associations)
    # weak edge must be dashed
    assert 'stroke-dasharray="6,4"' in svg
    # strong edge solid width 2.0
    assert 'stroke-width="2.0"' in svg


def test_type_colors():
    entities, associations = _sample()
    svg = render_svg(entities, associations)
    assert "#9f1d20" in svg  # business red
    assert "#2f7d4f" in svg  # phone green
    assert "#2f5d7d" in svg  # person blue


def test_unknown_edge_endpoints_skipped():
    entities, _ = _sample()
    associations = [
        {"from": "biz1", "to": "ghost", "relation": "x", "strength": "strong"},
        {"from": "ghost1", "to": "ghost2", "relation": "y", "strength": "weak"},
    ]
    svg = render_svg(entities, associations)
    root = _parse_svg(svg)  # must still be valid
    lines = [el for el in root.iter() if el.tag == "line"]
    assert len(lines) == 4  # only legend lines remain


def test_html_escaping():
    entities = [{"id": "b1", "type": "business",
                 "value": '<script>alert("x")</script>',
                 "display": '<script>alert("x")</script>',
                 "sources": [], "context": {}}]
    svg = render_svg(entities, [])
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_dict_entities_accepted():
    entities, associations = _sample()
    as_dict = {e["id"]: e for e in entities}
    svg = render_svg(as_dict, associations)
    root = _parse_svg(svg)
    assert root is not None


def test_pattern_overlay_edges():
    entities, associations = _sample()
    patterns = [{
        "pattern": "shared_phone_across_businesses",
        "description": "同一手机号关联 2 家企业",
        "entities": ["biz1", "biz2", "ph1"],
        "severity": "medium",
    }]
    svg = render_svg(entities, associations, patterns=patterns)
    assert "#b7791f" in svg  # pattern edge gold
    assert "shared_phone_across_businesses" in svg


def test_section_builder_with_assoc_result():
    entities, associations = _sample()
    result = {
        "seed": {"type": "business", "value": "测试公司A"},
        "entities": entities,
        "associations": associations,
        "interesting_patterns": [],
    }
    html = build_association_graph_section(result)
    assert "实体关联图谱" in html
    assert "<svg" in html
    assert "节点 4" in html


def test_section_builder_kwargs():
    entities, associations = _sample()
    html = build_association_graph_section(
        entities=entities, associations=associations)
    assert "实体关联图谱" in html


def test_max_nodes_pruning():
    entities = [
        {"id": f"n{i}", "type": "phone", "value": f"v{i}", "display": f"v{i}",
         "sources": [], "context": {}}
        for i in range(100)
    ]
    associations = [
        {"from": "n0", "to": f"n{i}", "relation": "r", "strength": "weak"}
        for i in range(1, 100)
    ]
    svg = render_svg(entities, associations, max_nodes=20)
    root = _parse_svg(svg)
    # entity node groups: one <g> per node (legend has no <g> wrappers)
    groups = [el for el in root.iter() if el.tag == "g"]
    node_groups = [g for g in groups
                   if any(c.tag == "circle" for c in g) and g.get("font-size") is None]
    assert len(node_groups) <= 20


def test_css_present():
    assert ".assoc-graph-section" in ASSOCIATION_GRAPH_CSS


def test_seed_centered_and_marked():
    entities, associations = _sample()
    svg = render_svg(entities, associations, seed="biz1")
    assert "调查起点" in svg
    # seed ring marker
    assert 'stroke-dasharray="4,3"' in svg


def test_engine_style_seed_type_mapping():
    # engine seeds use business_name/person_name; entities use business/person
    entities, associations = _sample()
    svg = render_svg(entities, associations,
                     seed={"type": "business_name", "value": "测试公司A"})
    assert "调查起点" in svg


def test_portable_html_embeds_graph_section():
    from core.investigation import _portable_report_html
    entities, associations = _sample()
    chart_packet = {
        "entity_association": {
            "seed": {"type": "business_name", "value": "测试公司A"},
            "entities": entities,
            "associations": associations,
            "interesting_patterns": [],
        },
    }
    html = _portable_report_html(
        company="测试", version="v", report_markdown="# r",
        one_click_readiness={}, summary={}, chart_packet=chart_packet)
    assert "实体关联图谱" in html
    assert ".assoc-graph-section" in html
    # graceful empty: no entity_association -> no section, no crash
    html2 = _portable_report_html(
        company="测试", version="v", report_markdown="# r",
        one_click_readiness={}, summary={}, chart_packet={})
    assert "实体关联图谱" not in html2
