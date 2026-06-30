#!/usr/bin/env python3
"""Tests for product intelligence engine."""
from __future__ import annotations

from core.product_intelligence import ProductIntelligenceEngine, ProductLifecycle, ProductRiskLevel


def test_growth_product_identifies_customer_value_and_repeat_logic():
    engine = ProductIntelligenceEngine()

    report = engine.analyze(
        "工业软件",
        {
            "product_revenue_growth": 0.35,
            "repeat_purchase_rate": 0.62,
            "subscription_revenue_ratio": 0.48,
            "switching_cost": 0.7,
            "core_product_revenue_ratio": 0.45,
        },
    )

    assert report.lifecycle is ProductLifecycle.GROWTH
    assert "切换成本" in report.customer_value
    assert report.repeat_purchase_logic == "订阅或持续服务收入占比较高"
    assert report.substitution_risk is ProductRiskLevel.LOW
    assert "偏高" in report.product_dependency


def test_mature_product_flags_price_and_substitution_pressure():
    engine = ProductIntelligenceEngine()

    report = engine.analyze(
        "通用零部件",
        {
            "product_revenue_growth": 0.03,
            "price_change": -0.08,
            "substitute_performance_gap": 0.02,
            "substitute_price_advantage": 0.2,
            "customer_churn_rate": 0.25,
            "core_product_revenue_ratio": 0.75,
        },
    )

    assert report.lifecycle is ProductLifecycle.MATURITY
    assert report.substitution_risk is ProductRiskLevel.HIGH
    assert "产品价格下行" in report.risk_triggers
    assert "替代品性能接近或超过" in report.risk_triggers
    assert "核心产品被替代" in report.can_survive_without_product
    assert any("第二增长曲线" in question for question in report.investigation_questions)


def test_declining_product_with_alternative_revenue_has_partial_resilience():
    engine = ProductIntelligenceEngine()

    report = engine.analyze(
        "传统硬件",
        {
            "product_revenue_growth": -0.12,
            "core_product_revenue_ratio": 0.5,
            "alternative_revenue_ratio": 0.45,
            "substitution_risk": 0.4,
        },
    )

    assert report.lifecycle is ProductLifecycle.DECLINE
    assert report.substitution_risk is ProductRiskLevel.LOW
    assert "一定替代收入来源" in report.can_survive_without_product
    assert "核心产品收入下滑" in report.risk_triggers
