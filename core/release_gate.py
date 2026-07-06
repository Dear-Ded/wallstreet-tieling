"""Runtime release gate for enforceable DD release decisions."""


def compute_release_decision(live_readiness, blocker_gate, realness_score, evidence_depth, graph_quality, source_readiness):
    """Compute release decision from quality gates."""
    del source_readiness

    blockers = []
    score = 100
    bl = blocker_gate or {}
    lr = live_readiness or {}

    if not lr.get("ready_for_live_smoke"):
        blockers.append(
            {
                "blocker_id": "RELEASE-001",
                "reason": "Not ready for live smoke - all sources fixture_only",
                "severity": "critical",
            }
        )
        score -= 50

    if not bl.get("is_clear", False):
        score -= min(50, bl.get("blocker_count", 0) * 5)

    rs = realness_score or {}
    rv = rs.get("realness_score", 0)
    if rv < 70:
        blockers.append(
            {
                "blocker_id": "RELEASE-002",
                "reason": f"Realness score too low: {rv}/100",
                "severity": "high",
            }
        )
        score -= 20

    ed = evidence_depth or {}
    source_depth = ed.get("source_depth", 0)
    if source_depth < 50:
        blockers.append(
            {
                "blocker_id": "RELEASE-003",
                "reason": f"Source depth insufficient: {source_depth}",
                "severity": "high",
            }
        )
        score -= 15

    gq = graph_quality or {}
    issue_count = gq.get("issue_count", 0)
    if not gq.get("is_clean"):
        blockers.append(
            {
                "blocker_id": "RELEASE-004",
                "reason": f"Graph quality issues: {issue_count} issues",
                "severity": "medium",
            }
        )
        score -= 10

    if lr.get("status") == "fixture_only" or not lr.get("ready_for_live_smoke"):
        decision = "internal_alpha"
    elif blockers:
        decision = "beta_candidate"
    elif score >= 80:
        decision = "release_candidate"
    else:
        decision = "beta_candidate"

    return {
        "release_decision": decision,
        "release_score": max(0, score),
        "release_blockers": blockers,
        "blocker_count": len(blockers),
        "gatepass_audit": [
            {"gate": "live_readiness", "passed": lr.get("ready_for_live_smoke", False)},
            {"gate": "blocker_clear", "passed": bl.get("is_clear", False)},
            {"gate": "realness", "passed": rv >= 70, "score": rv},
            {"gate": "source_depth", "passed": source_depth >= 50},
            {"gate": "graph_quality", "passed": gq.get("is_clean", False)},
        ],
    }
