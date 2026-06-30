#!/usr/bin/env python3
"""Tests for enhanced financial analyzer."""
from __future__ import annotations

import pytest

from core.financial_analyzer_v2 import EnhancedFinancialAnalyzer, FinancialHealthGrade


@pytest.mark.asyncio
async def test_analyze_financial_health_returns_expected_sections():
    analyzer = EnhancedFinancialAnalyzer()
    result = await analyzer.analyze_financial_health(
        {
            "roe": 0.2,
            "gross_margin": 0.4,
            "debt_to_equity": 0.3,
            "operating_cash_flow": 100,
            "investing_cash_flow": -20,
            "financing_cash_flow": 10,
        },
        industry="科技",
    )

    assert result["financial_ratios"]["roe"] == 0.2
    assert result["cash_flow_analysis"]["health_status"] == "健康"
    assert result["financial_risk"]["risk_level"] == "低"
    assert result["earnings_quality"]["warning_signals"] == []
    assert "怎么赚钱" not in result["business_model"]["sustainability"]
    assert result["health_grade"] in {grade.value for grade in FinancialHealthGrade}
    assert result["industry_benchmark"]["roe"] == 0.15


def test_cash_flow_flags_negative_flow():
    analyzer = EnhancedFinancialAnalyzer()
    cash_flow = analyzer._analyze_cash_flow(
        {
            "operating_cash_flow": -10,
            "investing_cash_flow": -5,
            "financing_cash_flow": 1,
        }
    )

    assert cash_flow.health_status == "危险"
    assert "经营活动现金流为负" in cash_flow.warning_signals
    assert "自由现金流为负" in cash_flow.warning_signals


def test_risk_scoring_reflects_leverage_and_cash_flow():
    analyzer = EnhancedFinancialAnalyzer()
    ratios = analyzer._calculate_ratios({"roe": 0.01, "debt_to_equity": 0.9})
    risk = analyzer._assess_financial_risk(
        {"operating_cash_flow": -1},
        ratios,
        "科技",
    )

    assert risk.risk_score >= 80
    assert risk.risk_level == "高"
    assert "资产负债率过高" in risk.warning_flags
    assert "净资产收益率过低" in risk.warning_flags


def test_earnings_quality_flags_cash_receivables_inventory_and_related_party_pressure():
    analyzer = EnhancedFinancialAnalyzer()

    quality = analyzer._analyze_earnings_quality(
        {
            "revenue": 1000,
            "prior_revenue": 900,
            "net_profit": 120,
            "operating_cash_flow": 20,
            "receivables": 500,
            "prior_receivables": 250,
            "inventory": 400,
            "prior_inventory": 200,
            "related_party_revenue": 260,
            "capital_expenditure": 300,
        }
    )

    assert quality.cash_conversion_ratio < 0.5
    assert "利润现金转化率偏低" in quality.warning_signals
    assert "应收账款增速显著高于收入增速" in quality.warning_signals
    assert "存货增速显著高于收入增速" in quality.warning_signals
    assert "关联方收入占比较高" in quality.warning_signals


def test_business_model_identifies_customer_dependency_and_review_questions():
    analyzer = EnhancedFinancialAnalyzer()
    ratios = analyzer._calculate_ratios({"gross_margin": 0.45, "net_margin": 0.12})
    quality = analyzer._analyze_earnings_quality(
        {
            "revenue": 1000,
            "net_profit": 100,
            "operating_cash_flow": 90,
            "related_party_revenue": 300,
        }
    )

    model = analyzer._analyze_business_model(
        {
            "top_customer_ratio": 0.62,
            "recurring_revenue_ratio": 0.2,
        },
        ratios,
        quality,
    )

    assert model.revenue_dependency == "高度依赖单一或少数核心客户"
    assert model.profit_driver == "较高毛利驱动"
    assert any("核心客户流失" in question for question in model.key_questions)
    assert any("关联方交易" in question for question in model.key_questions)
