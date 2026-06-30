#!/usr/bin/env python3
"""Tests for industry intelligence engine."""
from __future__ import annotations

from core.industry_intelligence import IndustryIntelligenceEngine, IndustryLifecycle, IndustryThreatLevel


def test_growth_industry_highlights_profit_pool_and_questions():
    engine = IndustryIntelligenceEngine()

    report = engine.analyze(
        "新能源",
        {
            "industry_growth": 0.22,
            "capacity_growth": 0.18,
            "company_gross_margin": 0.46,
            "customer_power": 0.3,
            "moat": "技术壁垒",
            "sources": ["industry_report", "news"],
        },
    )

    assert report.lifecycle is IndustryLifecycle.GROWTH
    assert "利润环节" in report.profit_pool_position
    assert "技术壁垒" in report.enterprise_survival_logic
    assert report.threat_level in {IndustryThreatLevel.LOW, IndustryThreatLevel.MEDIUM}
    assert report.source_coverage == ["industry_report", "news"]
    assert report.investigation_questions


def test_mature_industry_flags_capacity_and_price_pressure():
    engine = IndustryIntelligenceEngine()

    report = engine.analyze(
        "制造",
        {
            "industry_growth": 0.03,
            "capacity_growth": 0.2,
            "price_change": -0.12,
            "customer_power": 0.75,
            "substitution_risk": 0.7,
        },
    )

    assert report.lifecycle is IndustryLifecycle.MATURITY
    assert "新增产能快于需求增长" in report.risk_triggers
    assert "产品价格下行" in report.risk_triggers
    assert "替代品或技术路线威胁" in report.risk_triggers
    assert report.threat_level is IndustryThreatLevel.HIGH
    assert any("价格战" in item for item in report.next_three_year_watchlist)


def test_declining_industry_updates_questions():
    engine = IndustryIntelligenceEngine()

    report = engine.analyze(
        "传统零售",
        {
            "industry_growth": -0.04,
            "top_customer_ratio": 0.62,
            "switching_cost": 0.2,
            "value_chain_role": "distributor",
        },
    )

    assert report.lifecycle is IndustryLifecycle.DECLINE
    assert report.threat_level is IndustryThreatLevel.MEDIUM
    assert "高议价" not in report.profit_pool_position
    assert any("核心客户" in question for question in report.investigation_questions)
