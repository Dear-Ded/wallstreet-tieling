#!/usr/bin/env python3
"""Tests for context budgeting and capsule compression."""
from __future__ import annotations

from core.context_budget import ContextBudgetManager


def test_context_capsule_keeps_evidence_and_risk_lines():
    manager = ContextBudgetManager(max_summary_chars=300)
    capsule = manager.build_capsule(
        [
            {
                "ok": True,
                "name": "analyst",
                "text": "\n".join(
                    [
                        "Registry base facts look normal. [source: qcc, company=Demo, time=2026-06-18]",
                        "Found enforcement risk that needs verification. [来源: court, company=Demo, time=2026-06-18]",
                        "Ordinary filler " * 100,
                    ]
                ),
            }
        ],
        target="Demo Co.",
    )

    assert capsule.source_count == 2
    assert any("source" in line.lower() for line in capsule.evidence_lines)
    assert any("enforcement risk" in line.lower() for line in capsule.risk_lines)
    assert capsule.compressed_chars < capsule.original_chars
    assert "# Context Summary" in capsule.to_prompt_text()
    assert "# Risk Signals" in capsule.to_prompt_text()


def test_context_capsule_excludes_failed_results_and_dedupes():
    manager = ContextBudgetManager()
    capsule = manager.build_capsule(
        [
            {"ok": True, "name": "A", "text": "Cash-flow anomaly. [source: x]"},
            {"ok": True, "name": "A", "text": "Cash-flow anomaly. [source: x]"},
            {"ok": False, "name": "B", "text": "should not appear"},
        ]
    )

    prompt_text = capsule.to_prompt_text()

    assert "should not appear" not in prompt_text
    assert prompt_text.count("Cash-flow anomaly") == 3  # summary + risk + evidence, no recent duplicate


def test_context_capsule_uses_recent_lines_when_no_evidence_or_risk():
    manager = ContextBudgetManager(max_recent_lines=2)
    capsule = manager.build_capsule(
        [
            {"ok": True, "name": "A", "text": "first line\nsecond line\nthird line"},
        ]
    )

    assert capsule.evidence_lines == []
    assert capsule.risk_lines == []
    assert capsule.recent_lines == ["A: second line", "A: third line"]
