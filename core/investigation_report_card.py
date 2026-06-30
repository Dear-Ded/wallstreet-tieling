#!/usr/bin/env python3
"""Report-card and release-gate helpers for investigation packets."""
from __future__ import annotations

from typing import Any


def build_blocker_gate(cap_audit, graph_sanity, quality, live_readiness, gqa=None) -> dict:
    """Blockers that prevent production readiness."""
    blockers = []
    capability_audit = cap_audit or {}
    capabilities = capability_audit.get("capabilities", {})
    for name, item in capabilities.items():
        if not item.get("wired_to_pipeline"):
            blockers.append({
                "blocker": f"{name}_not_wired",
                "severity": "critical",
                "reason": f"{name} not wired to pipeline",
            })
        if not item.get("tested") and item.get("implemented"):
            blockers.append({
                "blocker": f"{name}_untested",
                "severity": "high",
                "reason": f"{name} has no tests",
            })
    if live_readiness and not live_readiness.get("ready_for_live_smoke"):
        blockers.append({
            "blocker": "live_unverified_blocker",
            "severity": "high",
            "reason": "All sources fixture_only or live_unverified - no live data",
        })
    if cap_audit and cap_audit.get("fixture_only_count", 0) > 0:
        blockers.append({
            "blocker": "majority_fixture_only",
            "severity": "high",
            "reason": f"{cap_audit.get('fixture_only_count', 0)}/{cap_audit.get('total', 1)} capabilities are fixture_only",
        })
    if graph_sanity and not graph_sanity.get("is_sane"):
        blockers.append({
            "blocker": "graph_quality_blocker",
            "severity": "medium",
            "reason": f"Flags: {graph_sanity.get('graph_quality_flags', [])}",
        })
    if gqa and not gqa.get("is_clean"):
        blockers.append({
            "blocker": "graph_quality_blocker_v2",
            "severity": "medium",
            "reason": f"Graph has {gqa.get('issue_count', 0)} issues, score={gqa.get('score', 0)}",
        })
    if gqa and gqa.get("strong_edges", 0) == 0 and gqa.get("edge_count", 0) > 0:
        blockers.append({
            "blocker": "no_strong_graph_edges",
            "severity": "high",
            "reason": "All graph edges are weak leads - no fact-level connections",
        })
    if quality and quality.get("low_quality_actions", 0) > 0:
        blockers.append({
            "blocker": "strategy_quality_blocker",
            "severity": "medium",
            "reason": f"{quality.get('low_quality_actions')} low-quality actions",
        })
    return {"blockers": blockers, "blocker_count": len(blockers), "is_clear": len(blockers) == 0}


def build_realness_score(cap_audit, depth, live_readiness, blocker_gate, graph_sanity) -> dict:
    """Score how real vs surface-level an investigation packet is."""
    score = 0
    capability_audit = cap_audit or {}
    total = capability_audit.get("total", 12)
    wired = capability_audit.get("wired", 0)
    if total:
        score += int((wired / total) * 25)
    tested = capability_audit.get("tested", 0)
    if total:
        score += int((tested / total) * 25)
    score += 25 if live_readiness and live_readiness.get("ready_for_live_smoke") else (5 if live_readiness else 0)
    depth_payload = depth or {}
    score += int(depth_payload.get("overall_depth", 0) / 4)
    score += 10 if graph_sanity and graph_sanity.get("is_sane") else (3 if graph_sanity else 0)
    blockers = blocker_gate or {}
    score += 5 if blockers.get("is_clear") else -min(10, blockers.get("blocker_count", 0) * 3)
    score = max(0, min(100, score))
    return {
        "realness_score": score,
        "verdict": "real" if score >= 70 else ("mostly_fixture" if score >= 40 else "fake_or_surface"),
    }


def build_report_language(harness, live_boundary, release_dec, money_status, goods_status, people_status) -> dict:
    """Data-driven report language based on runtime state."""
    source_lanes = (harness or {}).get("source_lane_readiness", {})
    fixture_count = sum(1 for value in source_lanes.values() if value.get("fixture_only"))
    live_count = sum(1 for value in source_lanes.values() if value.get("live_verified"))
    return {
        "release_decision_label": f"version: {release_dec} - live_verified={live_count}; fixture_or_unverified={fixture_count}",
        "source_truth_label": f"sources: live_verified={live_count}; fixture_or_unverified={fixture_count}",
        "next_action_label": "provide authorized credentials or user-uploaded facts" if not live_count else "live data source connected",
        "money_lane_status": str(money_status),
        "goods_lane_status": str(goods_status),
        "people_lane_status": str(people_status),
    }


def build_packet_quality_flags(
    release_decision: str,
    harness: dict[str, Any],
    source_readiness: dict[str, Any],
    money_status: str,
    goods_status: str,
    people_status: str,
    evidence_trace: list[dict[str, Any]],
    evidence_gaps: list[str],
    executable_next_steps: list[dict[str, Any]],
) -> dict[str, bool]:
    trace_sections = {
        str(item.get("report_section") or "")
        for item in evidence_trace or []
        if isinstance(item, dict)
    }

    def lane_visible(status: str, section: str) -> bool:
        return str(status or "missing") not in {"", "missing", "unknown"} or section in trace_sections

    source_lanes = _dict((harness or {}).get("source_lane_readiness"))
    return {
        "release_decision_visible": bool(str(release_decision or "").strip()),
        "source_truth_visible": bool(source_lanes or any(source_readiness.get(key) for key in (
            "usable_sources",
            "fixture_only_sources",
            "blocked_sources",
            "authorization_required_sources",
            "parse_failed_sources",
            "access_issues",
        ))),
        "money_lane_visible": lane_visible(money_status, "money_lane"),
        "goods_lane_visible": lane_visible(goods_status, "goods_lane"),
        "people_lane_visible": lane_visible(people_status, "people_lane"),
        "next_actions_concrete": bool(evidence_gaps or executable_next_steps),
        "fixture_live_boundary_visible": "fixture_only" in str(harness or {}) or "live_unverified" in str(harness or {}),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
