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
    assert "谨慎投资" not in risk.recommendation
    assert "核验" in risk.recommendation


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


def test_zero_roe_is_scored_as_low_profitability():
    analyzer = EnhancedFinancialAnalyzer()
    ratios = analyzer._calculate_ratios({"roe": 0.0, "debt_to_equity": 0.2})
    risk = analyzer._assess_financial_risk(
        {"operating_cash_flow": 5},
        ratios,
        "default",
    )

    assert "净资产收益率过低" in risk.warning_flags


def test_missing_cash_flow_is_not_reported_as_healthy():
    analyzer = EnhancedFinancialAnalyzer()

    missing = analyzer._analyze_cash_flow({})
    explicit_none = analyzer._analyze_cash_flow(
        {
            "operating_cash_flow": None,
            "investing_cash_flow": None,
            "financing_cash_flow": None,
        }
    )
    partial = analyzer._analyze_cash_flow({"operating_cash_flow": -10})

    assert missing.health_status == "未知"
    assert missing.operating_cash_flow is None
    assert missing.free_cash_flow is None
    assert any("不能视为健康" in item for item in missing.warning_signals)
    assert explicit_none.health_status == "未知"
    assert partial.health_status == "预警"
    assert partial.free_cash_flow is None
    assert "自由现金流为负" not in partial.warning_signals
    assert "经营活动现金流为负" in partial.warning_signals


def test_missing_customer_concentration_is_not_treated_as_diversified():
    analyzer = EnhancedFinancialAnalyzer()
    ratios = analyzer._calculate_ratios({})
    quality = analyzer._analyze_earnings_quality({})

    model = analyzer._analyze_business_model({}, ratios, quality)

    assert model.revenue_dependency == "客户集中度缺少输入，不能视为分散"


@pytest.mark.asyncio
async def test_empty_financial_input_does_not_grade_as_excellent():
    analyzer = EnhancedFinancialAnalyzer()

    result = await analyzer.analyze_financial_health({})

    assert result["cash_flow_analysis"]["health_status"] == "未知"
    assert result["financial_risk"]["risk_level"] == "未知"
    assert result["health_grade"] == FinancialHealthGrade.UNKNOWN.value
    assert "不能把空结果当成低风险" in result["financial_risk"]["recommendation"]
    assert result["business_model"]["revenue_dependency"] == "客户集中度缺少输入，不能视为分散"
