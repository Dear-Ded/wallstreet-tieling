#!/usr/bin/env python3
"""Industry intelligence primitives for enterprise risk discovery."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IndustryLifecycle(str, Enum):
    INTRODUCTION = "introduction"
    GROWTH = "growth"
    MATURITY = "maturity"
    DECLINE = "decline"
    UNKNOWN = "unknown"


class IndustryThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class IndustrySignal:
    name: str
    value: Any
    source: str = ""
    confidence: float = 0.5


@dataclass
class IndustryIntelligenceReport:
    industry: str
    lifecycle: IndustryLifecycle
    profit_pool_position: str
    enterprise_survival_logic: str
    threat_level: IndustryThreatLevel
    risk_triggers: list[str] = field(default_factory=list)
    next_three_year_watchlist: list[str] = field(default_factory=list)
    investigation_questions: list[str] = field(default_factory=list)
    source_coverage: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "lifecycle": self.lifecycle.value,
            "profit_pool_position": self.profit_pool_position,
            "enterprise_survival_logic": self.enterprise_survival_logic,
            "threat_level": self.threat_level.value,
            "risk_triggers": self.risk_triggers,
            "next_three_year_watchlist": self.next_three_year_watchlist,
            "investigation_questions": self.investigation_questions,
            "source_coverage": self.source_coverage,
        }


class IndustryIntelligenceEngine:
    """Turns industry facts into risk-discovery questions and triggers."""

    def analyze(self, industry: str, signals: dict[str, Any]) -> IndustryIntelligenceReport:
        lifecycle = self._classify_lifecycle(signals)
        risk_triggers = self._risk_triggers(signals, lifecycle)
        threat_level = self._threat_level(risk_triggers, signals)
        return IndustryIntelligenceReport(
            industry=industry,
            lifecycle=lifecycle,
            profit_pool_position=self._profit_pool_position(signals),
            enterprise_survival_logic=self._survival_logic(signals, lifecycle),
            threat_level=threat_level,
            risk_triggers=risk_triggers,
            next_three_year_watchlist=self._watchlist(signals, lifecycle),
            investigation_questions=self._questions(signals, lifecycle),
            source_coverage=self._source_coverage(signals),
        )

    def _classify_lifecycle(self, signals: dict[str, Any]) -> IndustryLifecycle:
        growth = self._num(signals.get("industry_growth"))
        growth_delta = self._num(signals.get("growth_delta"))
        capacity_growth = self._num(signals.get("capacity_growth"))

        if growth is None:
            return IndustryLifecycle.UNKNOWN
        if growth < 0:
            return IndustryLifecycle.DECLINE
        if growth >= 0.15 and (growth_delta is None or growth_delta >= 0):
            return IndustryLifecycle.GROWTH
        if growth <= 0.05 or (growth_delta is not None and growth_delta < -0.05):
            return IndustryLifecycle.MATURITY
        if capacity_growth is not None and capacity_growth > growth + 0.1:
            return IndustryLifecycle.MATURITY
        return IndustryLifecycle.GROWTH

    def _profit_pool_position(self, signals: dict[str, Any]) -> str:
        gross_margin = self._num(signals.get("company_gross_margin"))
        upstream_power = self._num(signals.get("supplier_power"))
        customer_power = self._num(signals.get("customer_power"))
        value_chain_role = str(signals.get("value_chain_role") or "unknown")

        if gross_margin is not None and gross_margin >= 0.4 and customer_power is not None and customer_power < 0.5:
            return "企业可能处在较高利润环节，需验证产品差异化和客户粘性"
        if upstream_power is not None and upstream_power >= 0.7:
            return "上游议价强，利润可能被原材料或关键资源挤压"
        if customer_power is not None and customer_power >= 0.7:
            return "下游客户议价强，利润可能被渠道或大客户压缩"
        if value_chain_role in {"oem", "processing", "distributor"}:
            return "企业可能处在低议价环节，需核查规模效率和客户稳定性"
        return "利润池位置需要结合产品、客户和成本结构继续验证"

    def _survival_logic(self, signals: dict[str, Any], lifecycle: IndustryLifecycle) -> str:
        moat = str(signals.get("moat") or "").strip()
        top_customer_ratio = self._num(signals.get("top_customer_ratio"))
        switching_cost = self._num(signals.get("switching_cost"))

        if moat:
            return f"企业生存逻辑主要依赖：{moat}"
        if top_customer_ratio is not None and top_customer_ratio >= 0.5:
            return "企业生存高度依赖核心客户，行业风险会通过客户订单快速传导"
        if switching_cost is not None and switching_cost >= 0.6:
            return "企业依赖客户切换成本和存量关系维持收入"
        if lifecycle is IndustryLifecycle.GROWTH:
            return "企业可能依赖行业增量生存，需验证自身份额是否同步提升"
        return "企业生存逻辑尚不清晰，需要穿透产品、客户和渠道"

    def _risk_triggers(self, signals: dict[str, Any], lifecycle: IndustryLifecycle) -> list[str]:
        triggers: list[str] = []
        if lifecycle in {IndustryLifecycle.MATURITY, IndustryLifecycle.DECLINE}:
            triggers.append("行业增速放缓或下行")
        if self._num(signals.get("capacity_growth")) and self._num(signals.get("industry_growth")):
            if float(signals["capacity_growth"]) > float(signals["industry_growth"]) + 0.1:
                triggers.append("新增产能快于需求增长")
        if self._num(signals.get("price_change")) is not None and float(signals["price_change"]) < -0.05:
            triggers.append("产品价格下行")
        if self._num(signals.get("substitution_risk")) is not None and float(signals["substitution_risk"]) >= 0.6:
            triggers.append("替代品或技术路线威胁")
        if self._num(signals.get("policy_risk")) is not None and float(signals["policy_risk"]) >= 0.6:
            triggers.append("政策或监管不确定性上升")
        if self._num(signals.get("customer_power")) is not None and float(signals["customer_power"]) >= 0.7:
            triggers.append("客户议价能力强")
        return triggers

    def _threat_level(
        self,
        triggers: list[str],
        signals: dict[str, Any],
    ) -> IndustryThreatLevel:
        if len(triggers) >= 3:
            return IndustryThreatLevel.HIGH
        if len(triggers) >= 1:
            return IndustryThreatLevel.MEDIUM
        if self._num(signals.get("industry_growth")) is not None and float(signals["industry_growth"]) >= 0.15:
            return IndustryThreatLevel.LOW
        return IndustryThreatLevel.MEDIUM

    def _watchlist(self, signals: dict[str, Any], lifecycle: IndustryLifecycle) -> list[str]:
        watch = [
            "行业需求增速和新增产能的差值",
            "核心产品价格与毛利率变化",
            "头部企业份额变化和渠道策略",
        ]
        if lifecycle in {IndustryLifecycle.MATURITY, IndustryLifecycle.DECLINE}:
            watch.append("落后产能出清速度和价格战强度")
        if self._num(signals.get("substitution_risk")) is not None:
            watch.append("替代技术商业化进度")
        return watch

    def _questions(self, signals: dict[str, Any], lifecycle: IndustryLifecycle) -> list[str]:
        questions = [
            "企业收入增长来自行业增长、份额提升，还是价格上涨？",
            "企业处在产业链哪个利润环节，是否有议价能力？",
            "如果行业增速下行，企业能靠什么维持订单和毛利？",
        ]
        if lifecycle in {IndustryLifecycle.MATURITY, IndustryLifecycle.DECLINE}:
            questions.append("行业进入存量竞争后，企业是否会被价格战或产能出清波及？")
        if self._num(signals.get("top_customer_ratio")) is not None and float(signals["top_customer_ratio"]) >= 0.3:
            questions.append("核心客户集中度是否会放大行业下行对企业订单和回款的冲击？")
        if self._num(signals.get("customer_power")) is not None and float(signals["customer_power"]) >= 0.7:
            questions.append("核心客户是否能把成本或降价压力转嫁给企业？")
        return questions

    @staticmethod
    def _source_coverage(signals: dict[str, Any]) -> list[str]:
        raw_sources = signals.get("sources") or []
        return [str(source) for source in raw_sources if str(source).strip()]

    @staticmethod
    def _num(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
