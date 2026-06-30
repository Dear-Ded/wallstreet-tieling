#!/usr/bin/env python3
"""Tests for the unified enterprise cognition profile."""
from __future__ import annotations

import pytest

from core.enterprise_cognition import EnterpriseCognitionEngine


@pytest.mark.asyncio
async def test_cognition_profile_combines_strategy_finance_industry_product_and_events():
    engine = EnterpriseCognitionEngine()

    profile = await engine.build_profile(
        "样例制造",
        {
            "enterprise": {
                "employees": 600,
                "annual_revenue": 90_000_000,
                "top_customer_ratio": 0.62,
            },
            "financial": {
                "revenue": 1000,
                "prior_revenue": 900,
                "net_profit": 120,
                "operating_cash_flow": 20,
                "investing_cash_flow": -260,
                "financing_cash_flow": 80,
                "receivables": 520,
                "prior_receivables": 240,
                "inventory": 430,
                "prior_inventory": 210,
                "gross_margin": 0.36,
                "net_margin": 0.04,
                "debt_to_equity": 0.78,
                "related_party_revenue": 260,
                "top_customer_ratio": 0.62,
            },
            "industry": {
                "name": "制造",
                "signals": {
                    "industry_growth": 0.03,
                    "capacity_growth": 0.2,
                    "price_change": -0.08,
                    "customer_power": 0.8,
                    "sources": ["industry_report"],
                },
            },
            "product": {
                "name": "通用零部件",
                "signals": {
                    "product_revenue_growth": -0.1,
                    "price_change": -0.08,
                    "core_product_revenue_ratio": 0.82,
                    "substitute_performance_gap": 0.1,
                    "substitute_price_advantage": 0.2,
                    "customer_churn_rate": 0.25,
                },
            },
            "risk_events": [
                {
                    "id": "risk-1",
                    "category": "court_enforcement",
                    "title": "新增被执行记录",
                    "severity": "high",
                    "confidence": 0.9,
                }
            ],
        },
    )

    data = profile.to_dict()

    assert data["company"] == "样例制造"
    assert data["strategy"]["segment"] == "mid_market"
    assert data["financial"]["financial_risk"]["risk_level"] in {"中", "高"}
    assert data["industry"]["threat_level"] == "high"
    assert data["product"]["substitution_risk"] == "high"
    assert data["risk_events"][0]["event"]["id"] == "risk-1"
    assert any("公开事件" in item for item in data["risk_hypotheses"])
    assert any("盈利质量" in item for item in data["risk_hypotheses"])
    assert any("产品层风险" in item for item in data["risk_hypotheses"])
    assert any("经营现金流" in item for item in data["monitoring_watchlist"])
    assert any("核心产品" in item for item in data["next_questions"])
    assert data["evidence_gaps"] == []


@pytest.mark.asyncio
async def test_cognition_profile_surfaces_evidence_gaps_when_inputs_are_sparse():
    engine = EnterpriseCognitionEngine()

    profile = await engine.build_profile("空白样例", {"enterprise": {"employees": 20}})

    assert profile.strategy["segment"] == "sme"
    assert "财务数据、现金流、应收、存货和客户集中度" in profile.evidence_gaps
    assert "行业增速、产能、价格、政策和竞争格局" in profile.evidence_gaps
    assert "核心产品、客户购买理由、复购和替代品" in profile.evidence_gaps
    assert any("当前证据不足" in item for item in profile.risk_hypotheses)
    assert any(question.startswith("缺口补证") for question in profile.next_questions)


def test_cognition_profile_sync_wrapper_for_cli_and_plugin_use():
    engine = EnterpriseCognitionEngine()

    profile = engine.build_profile_sync("同步样例", {"enterprise": {"listed": True}})

    assert profile.company == "同步样例"
    assert profile.strategy["segment"] == "listed"
