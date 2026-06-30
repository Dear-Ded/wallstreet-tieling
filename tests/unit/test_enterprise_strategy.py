#!/usr/bin/env python3
"""Tests for enterprise investigation strategy."""
from __future__ import annotations

from core.enterprise_strategy import EnterpriseSegment, EnterpriseStrategyEngine


def test_listed_company_strategy_prioritizes_finance_and_governance():
    engine = EnterpriseStrategyEngine()

    report = engine.analyze("样例股份", {"listed": True})

    assert report.segment is EnterpriseSegment.LISTED
    assert "财务质量" in report.investigation_focus
    assert "治理结构" in report.investigation_focus
    assert "li-ming-yuan" in report.priority_roles
    assert "wang-si-yuan" in report.priority_roles


def test_mid_market_strategy_prioritizes_customers_supply_chain_and_cash():
    engine = EnterpriseStrategyEngine()

    report = engine.analyze(
        "样例制造",
        {
            "employees": 800,
            "annual_revenue": 80_000_000,
        },
    )

    assert report.segment is EnterpriseSegment.MID_MARKET
    assert "客户集中度" in report.investigation_focus
    assert "供应商依赖" in report.investigation_focus
    assert any("资金链" in question for question in report.questions)


def test_sme_strategy_prioritizes_owner_and_reputation():
    engine = EnterpriseStrategyEngine()

    report = engine.analyze(
        "样例小店",
        {
            "employees": 30,
            "top_customer_ratio": 0.55,
        },
    )

    assert report.segment is EnterpriseSegment.SME
    assert "老板背景" in report.investigation_focus
    assert "商业信誉" in report.investigation_focus
    assert "ma-li-quan" in report.priority_roles
    assert any("老板" in question for question in report.questions)
