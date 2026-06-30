#!/usr/bin/env python3
"""Tests for persistent risk-event storage."""
from __future__ import annotations

from core.intelligence_retrieval import EvidenceGraph, RetrievalDomain, RiskEvent, RiskSeverity
from core.risk_event_store import RiskEventStore


def make_event(event_id: str, severity: RiskSeverity = RiskSeverity.HIGH) -> RiskEvent:
    return RiskEvent(
        id=event_id,
        category=RetrievalDomain.COURT_ENFORCEMENT,
        title="Court risk",
        severity=severity,
        entity_ids=("company:测试科技有限公司",),
        evidence_ids=("evidence:1",),
        confidence=0.8,
        rationale="Matched keywords: 失信",
    )


def test_append_deduplicates_events(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    event = make_event("risk:abc")

    assert store.append("测试科技有限公司", [event]) == 1
    assert store.append("测试科技有限公司", [event]) == 0

    rows = store.list_events(company="测试科技有限公司")
    assert len(rows) == 1
    assert rows[0]["event"]["id"] == "risk:abc"
    assert rows[0]["first_seen_at"]
    assert rows[0]["last_seen_at"]
    assert rows[0]["seen_count"] == 1


def test_filter_by_severity_and_status(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    store.append(
        "测试科技有限公司",
        [
            make_event("risk:high", RiskSeverity.HIGH),
            make_event("risk:medium", RiskSeverity.MEDIUM),
        ],
    )

    rows = store.list_events(severity=RiskSeverity.HIGH, status="open")

    assert len(rows) == 1
    assert rows[0]["event"]["id"] == "risk:high"


def test_summary_groups_by_company_and_severity(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    store.append("测试科技有限公司", [make_event("risk:high", RiskSeverity.HIGH)])
    store.append("样例制造有限公司", [make_event("risk:low", RiskSeverity.LOW)])

    summary = store.summary()

    assert summary["total_events"] == 2
    assert summary["by_company"]["测试科技有限公司"] == 1
    assert summary["by_severity"]["high"] == 1
    assert summary["by_severity"]["low"] == 1


def test_latest_alerts_returns_recent_high_priority_open_events(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    company = "测试科技有限公司"
    store.append(
        company,
        [
            make_event("risk:low", RiskSeverity.LOW),
            make_event("risk:high-1", RiskSeverity.HIGH),
            make_event("risk:critical", RiskSeverity.CRITICAL),
        ],
    )

    alerts = store.latest_alerts(company=company)

    assert [row["event"]["id"] for row in alerts] == ["risk:critical", "risk:high-1"]


def test_append_from_graph_returns_monitoring_summary(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    graph = EvidenceGraph()
    graph.add_risk_event(make_event("risk:high", RiskSeverity.HIGH))
    graph.add_risk_event(make_event("risk:medium", RiskSeverity.MEDIUM))

    summary = store.append_from_graph("测试科技有限公司", graph)
    duplicate_summary = store.append_from_graph("测试科技有限公司", graph)

    assert summary["persisted"] == 2
    assert summary["scan_id"].startswith("scan:")
    assert summary["observed_at"]
    assert summary["touched"] == 0
    assert summary["current"] == 2
    assert summary["delta"]["new_event_count"] == 2
    assert summary["delta"]["recurring_event_count"] == 0
    assert summary["alert_count"] == 1
    assert summary["alerts"][0]["event"]["id"] == "risk:high"
    assert summary["store"]["total_events"] == 2
    assert duplicate_summary["persisted"] == 0
    assert duplicate_summary["touched"] == 2
    assert duplicate_summary["delta"]["new_event_count"] == 0
    assert duplicate_summary["delta"]["recurring_event_count"] == 2
    assert duplicate_summary["store"]["total_events"] == 2
    rows = store.list_events(company="测试科技有限公司")
    assert all(row["seen_count"] == 2 for row in rows)
    assert all(row["last_seen_at"] >= row["first_seen_at"] for row in rows)


def test_diff_current_events_marks_not_seen_without_claiming_resolution(tmp_path):
    store = RiskEventStore(tmp_path / "events.jsonl")
    company = "Demo Delta Co., Ltd."
    old_event = make_event("risk:old", RiskSeverity.HIGH)
    current_event = make_event("risk:new", RiskSeverity.CRITICAL)

    store.append(company, [old_event])

    delta = store.diff_current_events(company, [current_event])

    assert delta["new_event_count"] == 1
    assert delta["observed_at"]
    assert delta["recurring_event_count"] == 0
    assert delta["not_seen_in_current_scan_count"] == 1
    assert delta["new_events"][0]["event"]["id"] == "risk:new"
    assert delta["not_seen_in_current_scan"][0]["event"]["id"] == "risk:old"
    assert "not proof" in delta["note"]
