#!/usr/bin/env python3
"""Enterprise cognition profile for risk discovery.

This layer is the product-facing "digital twin" entrypoint: it composes
strategy, finance, industry, product, and event signals into monitorable risk
hypotheses instead of merely producing a longer report.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .enterprise_strategy import EnterpriseStrategyEngine
from .financial_analyzer_v2 import EnhancedFinancialAnalyzer
from .industry_intelligence import IndustryIntelligenceEngine
from .intelligence_retrieval import RiskEvent, RiskSeverity
from .product_intelligence import ProductIntelligenceEngine
from .risk_event_store import RiskEventStore


_SEVERITY_WEIGHT = {
    "critical": 100,
    "high": 80,
    "medium": 50,
    "low": 20,
}


@dataclass
class EnterpriseCognitionProfile:
    company: str
    strategy: dict[str, Any]
    financial: dict[str, Any] | None = None
    industry: dict[str, Any] | None = None
    product: dict[str, Any] | None = None
    risk_events: list[dict[str, Any]] = field(default_factory=list)
    risk_hypotheses: list[str] = field(default_factory=list)
    monitoring_watchlist: list[str] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "strategy": self.strategy,
            "financial": self.financial,
            "industry": self.industry,
            "product": self.product,
            "risk_events": self.risk_events,
            "risk_hypotheses": self.risk_hypotheses,
            "monitoring_watchlist": self.monitoring_watchlist,
            "next_questions": self.next_questions,
            "evidence_gaps": self.evidence_gaps,
        }


class EnterpriseCognitionEngine:
    """Builds a unified enterprise intelligence profile from typed signals."""

    def __init__(
        self,
        *,
        risk_event_store: RiskEventStore | str | Path | None = None,
        strategy_engine: EnterpriseStrategyEngine | None = None,
        financial_analyzer: EnhancedFinancialAnalyzer | None = None,
        industry_engine: IndustryIntelligenceEngine | None = None,
        product_engine: ProductIntelligenceEngine | None = None,
    ) -> None:
        self.strategy_engine = strategy_engine or EnterpriseStrategyEngine()
        self.financial_analyzer = financial_analyzer or EnhancedFinancialAnalyzer()
        self.industry_engine = industry_engine or IndustryIntelligenceEngine()
        self.product_engine = product_engine or ProductIntelligenceEngine()
        if isinstance(risk_event_store, RiskEventStore) or risk_event_store is None:
            self.risk_event_store = risk_event_store
        else:
            self.risk_event_store = RiskEventStore(risk_event_store)

    async def build_profile(
        self,
        company: str,
        inputs: dict[str, Any] | None = None,
    ) -> EnterpriseCognitionProfile:
        """Compose investigation modules into one structured cognition profile."""
        payload = inputs or {}
        enterprise_signals = dict(payload.get("enterprise") or {})
        financial_payload = payload.get("financial")
        industry_payload = payload.get("industry")
        product_payload = payload.get("product")

        strategy = self.strategy_engine.analyze(company, enterprise_signals).to_dict()
        financial = await self._build_financial(financial_payload, industry_payload)
        industry = self._build_industry(industry_payload, financial_payload, enterprise_signals)
        product = self._build_product(product_payload, financial_payload, enterprise_signals)
        risk_events = self._collect_risk_events(company, payload)

        evidence_gaps = self._evidence_gaps(financial, industry, product, risk_events)
        risk_hypotheses = self._risk_hypotheses(
            strategy=strategy,
            financial=financial,
            industry=industry,
            product=product,
            risk_events=risk_events,
            evidence_gaps=evidence_gaps,
        )
        monitoring_watchlist = self._monitoring_watchlist(strategy, financial, industry, product, risk_events)
        next_questions = self._next_questions(strategy, financial, industry, product, risk_events, evidence_gaps)

        return EnterpriseCognitionProfile(
            company=company,
            strategy=strategy,
            financial=financial,
            industry=industry,
            product=product,
            risk_events=risk_events,
            risk_hypotheses=risk_hypotheses,
            monitoring_watchlist=monitoring_watchlist,
            next_questions=next_questions,
            evidence_gaps=evidence_gaps,
        )

    def build_profile_sync(
        self,
        company: str,
        inputs: dict[str, Any] | None = None,
    ) -> EnterpriseCognitionProfile:
        """Synchronous wrapper for CLI/plugin integrations."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.build_profile(company, inputs))
        raise RuntimeError("build_profile_sync cannot run inside an active event loop; await build_profile instead")

    async def _build_financial(
        self,
        financial_payload: dict[str, Any] | None,
        industry_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not financial_payload:
            return None
        industry_name = "default"
        if industry_payload:
            industry_name = str(industry_payload.get("name") or industry_payload.get("industry") or "default")
        return await self.financial_analyzer.analyze_financial_health(financial_payload, industry=industry_name)

    def _build_industry(
        self,
        industry_payload: dict[str, Any] | None,
        financial_payload: dict[str, Any] | None,
        enterprise_signals: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not industry_payload:
            return None
        name = str(industry_payload.get("name") or industry_payload.get("industry") or "unknown")
        signals = dict(industry_payload.get("signals") or industry_payload)
        signals.setdefault("top_customer_ratio", enterprise_signals.get("top_customer_ratio"))
        if financial_payload:
            signals.setdefault("company_gross_margin", financial_payload.get("gross_margin"))
        return self.industry_engine.analyze(name, signals).to_dict()

    def _build_product(
        self,
        product_payload: dict[str, Any] | None,
        financial_payload: dict[str, Any] | None,
        enterprise_signals: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not product_payload:
            return None
        name = str(product_payload.get("name") or product_payload.get("product_name") or "unknown")
        signals = dict(product_payload.get("signals") or product_payload)
        signals.setdefault("top_customer_ratio", enterprise_signals.get("top_customer_ratio"))
        if financial_payload:
            signals.setdefault("gross_margin", financial_payload.get("gross_margin"))
        return self.product_engine.analyze(name, signals).to_dict()

    def _collect_risk_events(self, company: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.risk_event_store is not None:
            rows.extend(self.risk_event_store.list_events(company=company))

        for event in payload.get("risk_events") or []:
            row = self._event_to_row(company, event)
            if row is not None:
                rows.append(row)

        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            event_id = str(row.get("event", {}).get("id") or row.get("id") or "")
            if not event_id:
                event_id = str(len(by_id))
            current = by_id.get(event_id)
            if current is None or self._risk_score(row) > self._risk_score(current):
                by_id[event_id] = row

        return sorted(by_id.values(), key=self._risk_score, reverse=True)

    @staticmethod
    def _event_to_row(company: str, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, RiskEvent):
            return {
                "company": company,
                "event": {
                    "id": raw.id,
                    "category": raw.category.value,
                    "title": raw.title,
                    "severity": raw.severity.value,
                    "entity_ids": list(raw.entity_ids),
                    "evidence_ids": list(raw.evidence_ids),
                    "confidence": raw.confidence,
                    "rationale": raw.rationale,
                    "status": raw.status,
                },
            }
        if not isinstance(raw, dict):
            return None
        if "event" in raw:
            row = dict(raw)
            row.setdefault("company", company)
            return row
        return {"company": company, "event": dict(raw)}

    def _risk_hypotheses(
        self,
        *,
        strategy: dict[str, Any],
        financial: dict[str, Any] | None,
        industry: dict[str, Any] | None,
        product: dict[str, Any] | None,
        risk_events: list[dict[str, Any]],
        evidence_gaps: list[str],
    ) -> list[str]:
        hypotheses: list[tuple[int, str]] = []

        for row in risk_events[:5]:
            event = row.get("event", {})
            severity = str(event.get("severity") or "low")
            title = str(event.get("title") or "公开风险事件")
            category = str(event.get("category") or "unknown")
            hypotheses.append((_SEVERITY_WEIGHT.get(severity, 0) + 10, f"{severity.upper()}公开事件：{title}（{category}）"))

        if financial:
            risk = financial.get("financial_risk", {})
            score = self._num(risk.get("risk_score")) or 0
            level = str(risk.get("risk_level") or "未知")
            if score >= 40:
                hypotheses.append((int(score), f"财务风险为{level}，需验证利润、现金流和偿债压力是否同时恶化"))

            earnings = financial.get("earnings_quality", {})
            warnings = earnings.get("warning_signals") or []
            if warnings:
                hypotheses.append((65 + len(warnings), f"盈利质量存在异常：{'、'.join(warnings[:3])}"))

            model = financial.get("business_model", {})
            dependency = str(model.get("revenue_dependency") or "")
            if "依赖" in dependency:
                hypotheses.append((60, f"收入结构可能脆弱：{dependency}"))

        if industry:
            triggers = industry.get("risk_triggers") or []
            threat = str(industry.get("threat_level") or "medium")
            if triggers:
                hypotheses.append(
                    (_SEVERITY_WEIGHT.get(threat, 50), f"行业压力可能传导至企业：{'、'.join(triggers[:3])}")
                )

        if product:
            triggers = product.get("risk_triggers") or []
            substitution = str(product.get("substitution_risk") or "low")
            if triggers:
                hypotheses.append(
                    (_SEVERITY_WEIGHT.get(substitution, 40), f"产品层风险可能削弱经营基本盘：{'、'.join(triggers[:3])}")
                )

        if not hypotheses and evidence_gaps:
            focus = "、".join(strategy.get("investigation_focus") or evidence_gaps[:3])
            hypotheses.append((20, f"当前证据不足，需先补齐{focus}后再判断核心风险"))

        ordered = [text for _, text in sorted(hypotheses, key=lambda item: item[0], reverse=True)]
        return self._dedupe(ordered)[:8]

    def _monitoring_watchlist(
        self,
        strategy: dict[str, Any],
        financial: dict[str, Any] | None,
        industry: dict[str, Any] | None,
        product: dict[str, Any] | None,
        risk_events: list[dict[str, Any]],
    ) -> list[str]:
        watch = [
            "新增司法执行、行政处罚、经营异常和负面舆情",
            "实控人、股东、高管和关联企业变更",
        ]
        watch.extend(str(item) for item in strategy.get("primary_signals") or [])
        if financial:
            watch.extend(
                [
                    "经营现金流/净利润现金转化率",
                    "应收账款、存货与收入增速差",
                    "关联交易收入占比和大客户回款",
                ]
            )
        if industry:
            watch.extend(str(item) for item in industry.get("next_three_year_watchlist") or [])
        if product:
            watch.extend(str(item) for item in product.get("risk_triggers") or [])
        for row in risk_events[:3]:
            event = row.get("event", {})
            title = str(event.get("title") or "").strip()
            if title:
                watch.append(f"跟踪风险事件状态：{title}")
        return self._dedupe(watch)[:15]

    def _next_questions(
        self,
        strategy: dict[str, Any],
        financial: dict[str, Any] | None,
        industry: dict[str, Any] | None,
        product: dict[str, Any] | None,
        risk_events: list[dict[str, Any]],
        evidence_gaps: list[str],
    ) -> list[str]:
        buckets: list[list[str]] = []
        buckets.append([str(item) for item in strategy.get("questions") or []])
        if financial:
            buckets.append([str(item) for item in financial.get("business_model", {}).get("key_questions") or []])
        if industry:
            buckets.append([str(item) for item in industry.get("investigation_questions") or []])
        if product:
            buckets.append([str(item) for item in product.get("investigation_questions") or []])

        questions = self._round_robin(buckets)
        if risk_events:
            questions.append("已发现风险事件能否穿透到责任主体、金额、时间线和当前状态？")
        for gap in evidence_gaps:
            questions.append(f"缺口补证：{gap}")
        return self._dedupe(questions)[:15]

    @staticmethod
    def _evidence_gaps(
        financial: dict[str, Any] | None,
        industry: dict[str, Any] | None,
        product: dict[str, Any] | None,
        risk_events: list[dict[str, Any]],
    ) -> list[str]:
        gaps: list[str] = []
        if financial is None:
            gaps.append("财务数据、现金流、应收、存货和客户集中度")
        if industry is None:
            gaps.append("行业增速、产能、价格、政策和竞争格局")
        if product is None:
            gaps.append("核心产品、客户购买理由、复购和替代品")
        if not risk_events:
            gaps.append("司法执行、行政处罚、舆情和公开风险事件")
        return gaps

    @staticmethod
    def _risk_score(row: dict[str, Any]) -> int:
        event = row.get("event", {})
        severity = str(event.get("severity") or "low")
        confidence = EnterpriseCognitionEngine._num(event.get("confidence")) or 0.5
        return int(_SEVERITY_WEIGHT.get(severity, 0) * confidence)

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in items if item.strip()))

    @staticmethod
    def _round_robin(buckets: list[list[str]]) -> list[str]:
        merged: list[str] = []
        max_len = max((len(bucket) for bucket in buckets), default=0)
        for index in range(max_len):
            for bucket in buckets:
                if index < len(bucket):
                    merged.append(bucket[index])
        return merged

    @staticmethod
    def _num(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


__all__ = ["EnterpriseCognitionEngine", "EnterpriseCognitionProfile"]
