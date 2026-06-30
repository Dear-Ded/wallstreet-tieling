#!/usr/bin/env python3
"""Product intelligence primitives for enterprise risk discovery."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProductLifecycle(str, Enum):
    INTRODUCTION = "introduction"
    GROWTH = "growth"
    MATURITY = "maturity"
    DECLINE = "decline"
    UNKNOWN = "unknown"


class ProductRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ProductIntelligenceReport:
    product_name: str
    lifecycle: ProductLifecycle
    customer_value: str
    repeat_purchase_logic: str
    substitution_risk: ProductRiskLevel
    product_dependency: str
    can_survive_without_product: str
    risk_triggers: list[str] = field(default_factory=list)
    investigation_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "lifecycle": self.lifecycle.value,
            "customer_value": self.customer_value,
            "repeat_purchase_logic": self.repeat_purchase_logic,
            "substitution_risk": self.substitution_risk.value,
            "product_dependency": self.product_dependency,
            "can_survive_without_product": self.can_survive_without_product,
            "risk_triggers": self.risk_triggers,
            "investigation_questions": self.investigation_questions,
        }


class ProductIntelligenceEngine:
    """Analyzes whether a company is resilient beyond its core product."""

    def analyze(self, product_name: str, signals: dict[str, Any]) -> ProductIntelligenceReport:
        lifecycle = self._lifecycle(signals)
        triggers = self._risk_triggers(signals, lifecycle)
        substitution = self._substitution_risk(signals, triggers)
        dependency = self._dependency(signals)
        return ProductIntelligenceReport(
            product_name=product_name,
            lifecycle=lifecycle,
            customer_value=self._customer_value(signals),
            repeat_purchase_logic=self._repeat_purchase_logic(signals),
            substitution_risk=substitution,
            product_dependency=dependency,
            can_survive_without_product=self._survival_without_product(signals, substitution, dependency),
            risk_triggers=triggers,
            investigation_questions=self._questions(signals, lifecycle, substitution, dependency),
        )

    def _lifecycle(self, signals: dict[str, Any]) -> ProductLifecycle:
        revenue_growth = self._num(signals.get("product_revenue_growth"))
        price_change = self._num(signals.get("price_change"))
        repeat_rate = self._num(signals.get("repeat_purchase_rate"))
        if revenue_growth is None:
            return ProductLifecycle.UNKNOWN
        if revenue_growth < -0.05:
            return ProductLifecycle.DECLINE
        if revenue_growth >= 0.2 and (repeat_rate is None or repeat_rate >= 0.3):
            return ProductLifecycle.GROWTH
        if price_change is not None and price_change < -0.05:
            return ProductLifecycle.MATURITY
        if 0 <= revenue_growth < 0.08:
            return ProductLifecycle.MATURITY
        return ProductLifecycle.GROWTH

    def _customer_value(self, signals: dict[str, Any]) -> str:
        value = str(signals.get("customer_value") or "").strip()
        if value:
            return value
        gross_margin = self._num(signals.get("gross_margin"))
        switching_cost = self._num(signals.get("switching_cost"))
        if switching_cost is not None and switching_cost >= 0.6:
            return "产品可能嵌入客户流程，客户切换成本较高"
        if gross_margin is not None and gross_margin >= 0.4:
            return "较高毛利暗示客户认可差异化价值，需验证具体购买理由"
        return "客户购买理由尚不清晰，需要穿透产品功能、场景和竞品"

    def _repeat_purchase_logic(self, signals: dict[str, Any]) -> str:
        repeat_rate = self._num(signals.get("repeat_purchase_rate"))
        subscription_ratio = self._num(signals.get("subscription_revenue_ratio"))
        if subscription_ratio is not None and subscription_ratio >= 0.4:
            return "订阅或持续服务收入占比较高"
        if repeat_rate is not None and repeat_rate >= 0.5:
            return "复购率较高，客户持续购买逻辑较强"
        if repeat_rate is not None and repeat_rate < 0.2:
            return "复购弱，可能依赖新客获取或项目制订单"
        return "复购逻辑需要用订单、续约和客户留存数据验证"

    def _dependency(self, signals: dict[str, Any]) -> str:
        core_product_revenue_ratio = self._num(signals.get("core_product_revenue_ratio"))
        if core_product_revenue_ratio is not None and core_product_revenue_ratio >= 0.7:
            return "高度依赖单一核心产品"
        if core_product_revenue_ratio is not None and core_product_revenue_ratio >= 0.4:
            return "核心产品依赖度偏高"
        return "产品组合相对分散或依赖度未明"

    def _risk_triggers(self, signals: dict[str, Any], lifecycle: ProductLifecycle) -> list[str]:
        triggers: list[str] = []
        if lifecycle is ProductLifecycle.DECLINE:
            triggers.append("核心产品收入下滑")
        if lifecycle is ProductLifecycle.MATURITY:
            triggers.append("产品进入成熟期或价格承压")
        if self._num(signals.get("price_change")) is not None and float(signals["price_change"]) < -0.05:
            triggers.append("产品价格下行")
        if self._num(signals.get("substitute_performance_gap")) is not None and float(signals["substitute_performance_gap"]) >= 0.0:
            triggers.append("替代品性能接近或超过")
        if self._num(signals.get("substitute_price_advantage")) is not None and float(signals["substitute_price_advantage"]) >= 0.15:
            triggers.append("替代品价格优势明显")
        if self._num(signals.get("customer_churn_rate")) is not None and float(signals["customer_churn_rate"]) >= 0.2:
            triggers.append("客户流失率偏高")
        return list(dict.fromkeys(triggers))

    def _substitution_risk(
        self,
        signals: dict[str, Any],
        triggers: list[str],
    ) -> ProductRiskLevel:
        explicit = self._num(signals.get("substitution_risk"))
        if explicit is not None and explicit >= 0.65:
            return ProductRiskLevel.HIGH
        if "替代品性能接近或超过" in triggers and "替代品价格优势明显" in triggers:
            return ProductRiskLevel.HIGH
        if any("替代品" in trigger for trigger in triggers):
            return ProductRiskLevel.MEDIUM
        return ProductRiskLevel.LOW

    def _survival_without_product(
        self,
        signals: dict[str, Any],
        substitution: ProductRiskLevel,
        dependency: str,
    ) -> str:
        alternative_revenue_ratio = self._num(signals.get("alternative_revenue_ratio")) or 0
        if "高度依赖" in dependency and substitution is ProductRiskLevel.HIGH:
            return "不能轻易脱离，核心产品被替代将显著冲击企业生存"
        if "高度依赖" in dependency and alternative_revenue_ratio < 0.2:
            return "脱离核心产品后的收入承接能力弱"
        if alternative_revenue_ratio >= 0.4:
            return "存在一定替代收入来源，但仍需验证利润率和现金流"
        return "需要结合产品矩阵、客户迁移和成本结构继续验证"

    def _questions(
        self,
        signals: dict[str, Any],
        lifecycle: ProductLifecycle,
        substitution: ProductRiskLevel,
        dependency: str,
    ) -> list[str]:
        questions = [
            "客户为什么买这个产品，而不是竞品或替代方案？",
            "客户持续购买来自刚需、切换成本、渠道绑定，还是价格优势？",
            "核心产品收入能否拆到客户、合同、回款和毛利？",
        ]
        if lifecycle in {ProductLifecycle.MATURITY, ProductLifecycle.DECLINE}:
            questions.append("产品进入成熟或下行阶段后，企业是否仍有提价和获客能力？")
        if substitution is not ProductRiskLevel.LOW:
            questions.append("替代品在性能、价格、渠道和交付周期上已经威胁到哪些客户？")
        if "依赖" in dependency:
            questions.append("如果核心产品收入下降30%，企业是否还有第二增长曲线？")
        return questions

    @staticmethod
    def _num(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
