#!/usr/bin/env python3
"""Enterprise segmentation and investigation strategy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EnterpriseSegment(str, Enum):
    LISTED = "listed"
    MID_MARKET = "mid_market"
    SME = "sme"
    UNKNOWN = "unknown"


@dataclass
class EnterpriseStrategyReport:
    segment: EnterpriseSegment
    investigation_focus: list[str] = field(default_factory=list)
    primary_signals: list[str] = field(default_factory=list)
    priority_roles: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.value,
            "investigation_focus": self.investigation_focus,
            "primary_signals": self.primary_signals,
            "priority_roles": self.priority_roles,
            "questions": self.questions,
            "rationale": self.rationale,
        }


class EnterpriseStrategyEngine:
    """Chooses different investigation strategies by company type."""

    def analyze(self, company: str, signals: dict[str, Any]) -> EnterpriseStrategyReport:
        segment = self._segment(signals)
        if segment is EnterpriseSegment.LISTED:
            return EnterpriseStrategyReport(
                segment=segment,
                investigation_focus=[
                    "财务质量",
                    "资本市场预期",
                    "治理结构",
                    "行业景气和估值变化",
                ],
                primary_signals=[
                    "利润与现金流背离",
                    "应收和存货异常",
                    "资本开支和回购分红",
                    "大客户与关联交易",
                ],
                priority_roles=["li-ming-yuan", "wang-si-yuan", "zheng-shen-zhi", "zhao-gang"],
                questions=[
                    "这家公司靠什么持续赚钱，资本市场预期是否过高？",
                    "财报里的增长能不能被现金流和回款验证？",
                    "治理结构和关联交易是否会放大风险？",
                ],
                rationale="上市公司以财务、行业和治理结构为主。",
            )

        if segment is EnterpriseSegment.MID_MARKET:
            return EnterpriseStrategyReport(
                segment=segment,
                investigation_focus=[
                    "客户集中度",
                    "供应商依赖",
                    "实控人和资金链",
                    "司法与行政风险",
                ],
                primary_signals=[
                    "核心客户集中",
                    "应收账款和回款压力",
                    "供应商压价或断供",
                    "老板相关联关系和借贷",
                ],
                priority_roles=["zhang-tie-zhu", "li-ming-yuan", "zhao-gang", "ma-li-quan"],
                questions=[
                    "客户流失后公司还能不能活？",
                    "这家公司是谁在真正控制，资金链是否会断？",
                    "供应链和回款的压力会不会直接击穿利润？",
                ],
                rationale="中型企业更容易死在客户、供应商和资金链。",
            )

        if segment is EnterpriseSegment.SME:
            return EnterpriseStrategyReport(
                segment=segment,
                investigation_focus=[
                    "老板背景",
                    "家庭与关系链",
                    "履约历史",
                    "商业信誉",
                ],
                primary_signals=[
                    "实控人变化",
                    "家庭成员和关键岗位",
                    "公开履约纠纷",
                    "个人商业行为模式",
                ],
                priority_roles=["zhang-tie-zhu", "ma-li-quan", "zhao-gang"],
                questions=[
                    "老板是什么风格，是否会直接决定企业生死？",
                    "这家公司是不是基本等于老板本人？",
                    "是否存在履约历史、信誉或关系链风险？",
                ],
                rationale="小微企业本质上往往是老板在经营。",
            )

        return EnterpriseStrategyReport(
            segment=EnterpriseSegment.UNKNOWN,
            investigation_focus=["基础工商", "财务", "行业", "人员", "风险"],
            primary_signals=[],
            priority_roles=["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang"],
            questions=[
                "先确认企业规模、经营模式和主要收入来源。",
                "再决定用哪一套企业策略深入调查。",
            ],
            rationale="企业类型不明时先做通用分层。",
        )

    def _segment(self, signals: dict[str, Any]) -> EnterpriseSegment:
        if signals.get("listed") is True:
            return EnterpriseSegment.LISTED
        employees = self._num(signals.get("employees"))
        annual_revenue = self._num(signals.get("annual_revenue"))
        top_customer_ratio = self._num(signals.get("top_customer_ratio"))

        if annual_revenue is not None and annual_revenue >= 500_000_000:
            return EnterpriseSegment.LISTED
        if employees is not None and employees >= 500 or annual_revenue is not None and annual_revenue >= 50_000_000:
            return EnterpriseSegment.MID_MARKET
        if top_customer_ratio is not None and top_customer_ratio >= 0.5:
            return EnterpriseSegment.SME
        if employees is not None and employees < 100:
            return EnterpriseSegment.SME
        return EnterpriseSegment.UNKNOWN

    @staticmethod
    def _num(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
