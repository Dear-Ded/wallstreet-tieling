"""
任务#2: 财务分析增强模块
Financial Analysis Enhancement Module

增强功能:
1. 多数据源财务数据融合
2. 财务比率自动计算与行业对比
3. 现金流健康度评估
4. 财务风险预警
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FinancialHealthGrade(str, Enum):
    """财务健康等级"""
    EXCELLENT = "优秀"
    GOOD = "良好"
    FAIR = "一般"
    POOR = "较差"
    CRITICAL = "危险"


class FinancialRatio(BaseModel):
    """财务比率"""
    
    # 盈利能力
    roe: Optional[float] = Field(None, description="净资产收益率")
    roa: Optional[float] = Field(None, description="总资产收益率")
    gross_margin: Optional[float] = Field(None, description="毛利率")
    net_margin: Optional[float] = Field(None, description="净利率")
    
    # 偿债能力
    current_ratio: Optional[float] = Field(None, description="流动比率")
    quick_ratio: Optional[float] = Field(None, description="速动比率")
    debt_to_equity: Optional[float] = Field(None, description="资产负债率")
    interest_coverage: Optional[float] = Field(None, description="利息保障倍数")
    
    # 运营能力
    asset_turnover: Optional[float] = Field(None, description="总资产周转率")
    inventory_turnover: Optional[float] = Field(None, description="存货周转率")
    receivables_turnover: Optional[float] = Field(None, description="应收账款周转率")
    
    # 成长能力
    revenue_growth: Optional[float] = Field(None, description="营收增长率")
    profit_growth: Optional[float] = Field(None, description="利润增长率")


class CashFlowAnalysis(BaseModel):
    """现金流分析"""
    
    operating_cash_flow: float = Field(..., description="经营活动现金流")
    investing_cash_flow: float = Field(..., description="投资活动现金流")
    financing_cash_flow: float = Field(..., description="筹资活动现金流")
    
    free_cash_flow: Optional[float] = Field(None, description="自由现金流")
    cash_flow_coverage: Optional[float] = Field(None, description="现金流覆盖倍数")
    
    health_status: str = Field(..., description="现金流健康状态")
    warning_signals: List[str] = Field(default_factory=list, description="预警信号")


class FinancialRisk(BaseModel):
    """财务风险"""
    
    risk_level: str = Field(..., description="风险等级")
    risk_score: float = Field(..., ge=0, le=100, description="风险评分")
    
    warning_flags: List[str] = Field(default_factory=list, description="预警标识")
    detailed_risks: Dict[str, Any] = Field(default_factory=dict, description="详细风险")
    
    recommendation: str = Field(..., description="建议措施")


class EarningsQualityAnalysis(BaseModel):
    """盈利质量与财务真实性分析"""

    cash_conversion_ratio: Optional[float] = Field(None, description="经营现金流/净利润")
    accrual_pressure: Optional[float] = Field(None, description="利润未转化为现金的压力")
    receivables_growth_gap: Optional[float] = Field(None, description="应收账款增速-收入增速")
    inventory_growth_gap: Optional[float] = Field(None, description="存货增速-收入增速")
    capex_intensity: Optional[float] = Field(None, description="资本开支/收入")
    related_party_revenue_ratio: Optional[float] = Field(None, description="关联方收入占比")
    warning_signals: List[str] = Field(default_factory=list, description="盈利质量预警")


class BusinessModelAnalysis(BaseModel):
    """企业如何赚钱以及是否可持续"""

    revenue_dependency: str = Field(..., description="收入依赖判断")
    profit_driver: str = Field(..., description="利润驱动判断")
    sustainability: str = Field(..., description="商业模式可持续性判断")
    key_questions: List[str] = Field(default_factory=list, description="下一步核查问题")


class EnhancedFinancialAnalyzer:
    """增强版财务分析器"""
    
    def __init__(self):
        self.industry_benchmarks = self._load_industry_benchmarks()
    
    def _load_industry_benchmarks(self) -> Dict[str, Dict[str, float]]:
        """加载行业基准数据"""
        return {
            "科技": {
                "roe": 0.15,
                "gross_margin": 0.40,
                "debt_to_equity": 0.50,
            },
            "制造": {
                "roe": 0.12,
                "gross_margin": 0.25,
                "debt_to_equity": 0.60,
            },
            "金融": {
                "roe": 0.10,
                "gross_margin": 0.60,
                "debt_to_equity": 0.85,
            },
            # 默认基准
            "default": {
                "roe": 0.12,
                "gross_margin": 0.30,
                "debt_to_equity": 0.60,
            }
        }
    
    async def analyze_financial_health(
        self,
        financial_data: Dict[str, Any],
        industry: str = "default"
    ) -> Dict[str, Any]:
        """综合分析财务健康度"""
        
        # 1. 计算财务比率
        ratios = self._calculate_ratios(financial_data)
        
        # 2. 分析现金流
        cash_flow = self._analyze_cash_flow(financial_data)
        
        # 3. 评估财务风险
        risk = self._assess_financial_risk(financial_data, ratios, industry)

        # 4. 财务情报：盈利质量与商业模式
        earnings_quality = self._analyze_earnings_quality(financial_data)
        business_model = self._analyze_business_model(financial_data, ratios, earnings_quality)
        
        # 5. 生成综合评分
        health_grade = self._calculate_health_grade(ratios, cash_flow, risk)
        
        return {
            "financial_ratios": self._dump_model(ratios),
            "cash_flow_analysis": self._dump_model(cash_flow),
            "financial_risk": self._dump_model(risk),
            "earnings_quality": self._dump_model(earnings_quality),
            "business_model": self._dump_model(business_model),
            "health_grade": health_grade,
            "industry_benchmark": self.industry_benchmarks.get(industry, self.industry_benchmarks["default"]),
            "analysis_timestamp": datetime.now().isoformat()
        }
    
    def _calculate_ratios(self, data: Dict[str, Any]) -> FinancialRatio:
        """计算财务比率"""
        # 简化实现 - 实际应从财务数据计算
        return FinancialRatio(
            roe=data.get("roe"),
            roa=data.get("roa"),
            gross_margin=data.get("gross_margin"),
            net_margin=data.get("net_margin"),
            current_ratio=data.get("current_ratio"),
            debt_to_equity=data.get("debt_to_equity"),
            asset_turnover=data.get("asset_turnover"),
            revenue_growth=data.get("revenue_growth"),
            profit_growth=data.get("profit_growth")
        )

    def _analyze_earnings_quality(self, data: Dict[str, Any]) -> EarningsQualityAnalysis:
        """分析利润是否真正转化为现金，以及是否存在财务粉饰压力。"""
        revenue = self._num(data.get("revenue"))
        net_profit = self._num(data.get("net_profit"))
        operating_cash_flow = self._num(data.get("operating_cash_flow"))
        receivables_growth = self._growth(data.get("receivables"), data.get("prior_receivables"))
        inventory_growth = self._growth(data.get("inventory"), data.get("prior_inventory"))
        revenue_growth = data.get("revenue_growth")
        if revenue_growth is None:
            revenue_growth = self._growth(data.get("revenue"), data.get("prior_revenue"))
        revenue_growth = self._num(revenue_growth)
        capex = abs(self._num(data.get("capital_expenditure")) or 0)
        related_party_revenue = self._num(data.get("related_party_revenue"))

        cash_conversion_ratio = self._safe_div(operating_cash_flow, net_profit)
        accrual_pressure = self._safe_div((net_profit or 0) - (operating_cash_flow or 0), revenue)
        receivables_growth_gap = self._gap(receivables_growth, revenue_growth)
        inventory_growth_gap = self._gap(inventory_growth, revenue_growth)
        capex_intensity = self._safe_div(capex, revenue)
        related_party_revenue_ratio = self._safe_div(related_party_revenue, revenue)

        warnings: list[str] = []
        if net_profit and net_profit > 0 and cash_conversion_ratio is not None and cash_conversion_ratio < 0.5:
            warnings.append("利润现金转化率偏低")
        if accrual_pressure is not None and accrual_pressure > 0.15:
            warnings.append("利润与经营现金流背离")
        if receivables_growth_gap is not None and receivables_growth_gap > 0.2:
            warnings.append("应收账款增速显著高于收入增速")
        if inventory_growth_gap is not None and inventory_growth_gap > 0.2:
            warnings.append("存货增速显著高于收入增速")
        if related_party_revenue_ratio is not None and related_party_revenue_ratio > 0.2:
            warnings.append("关联方收入占比较高")
        if capex_intensity is not None and capex_intensity > 0.25 and (operating_cash_flow or 0) <= 0:
            warnings.append("高资本开支叠加经营现金流承压")

        return EarningsQualityAnalysis(
            cash_conversion_ratio=cash_conversion_ratio,
            accrual_pressure=accrual_pressure,
            receivables_growth_gap=receivables_growth_gap,
            inventory_growth_gap=inventory_growth_gap,
            capex_intensity=capex_intensity,
            related_party_revenue_ratio=related_party_revenue_ratio,
            warning_signals=warnings,
        )

    def _analyze_business_model(
        self,
        data: Dict[str, Any],
        ratios: FinancialRatio,
        earnings_quality: EarningsQualityAnalysis,
    ) -> BusinessModelAnalysis:
        """回答这家公司怎么赚钱，以及这种赚钱方式能不能持续。"""
        top_customer_ratio = self._num(data.get("top_customer_ratio"))
        recurring_revenue_ratio = self._num(data.get("recurring_revenue_ratio"))
        gross_margin = ratios.gross_margin
        net_margin = ratios.net_margin

        if top_customer_ratio is not None and top_customer_ratio >= 0.5:
            revenue_dependency = "高度依赖单一或少数核心客户"
        elif top_customer_ratio is not None and top_customer_ratio >= 0.3:
            revenue_dependency = "核心客户集中度偏高"
        else:
            revenue_dependency = "未发现明显客户集中依赖"

        if gross_margin is not None and gross_margin >= 0.4:
            profit_driver = "较高毛利驱动"
        elif net_margin is not None and net_margin <= 0.03:
            profit_driver = "低净利率，可能依赖规模或费用控制"
        else:
            profit_driver = "利润驱动需结合产品、客户与费用结构继续核查"

        warnings = earnings_quality.warning_signals
        if len(warnings) >= 3:
            sustainability = "可持续性存疑，需要核查收入确认、客户质量和资金链"
        elif recurring_revenue_ratio is not None and recurring_revenue_ratio >= 0.5 and len(warnings) == 0:
            sustainability = "收入连续性较好，暂未发现明显财务质量压力"
        else:
            sustainability = "可持续性需要结合行业景气、产品替代和客户续约继续验证"

        questions = [
            "收入来自哪些产品和客户，是否能穿透到合同和回款？",
            "毛利率变化是产品力提升、价格变化，还是成本口径变化？",
            "经营现金流能否覆盖利润、资本开支和债务偿付？",
        ]
        if top_customer_ratio is not None and top_customer_ratio >= 0.3:
            questions.append("核心客户流失后收入和现金流会下降多少？")
        if earnings_quality.related_party_revenue_ratio is not None and earnings_quality.related_party_revenue_ratio > 0.2:
            questions.append("关联方交易是否具备商业实质和独立定价？")

        return BusinessModelAnalysis(
            revenue_dependency=revenue_dependency,
            profit_driver=profit_driver,
            sustainability=sustainability,
            key_questions=questions,
        )
    
    def _analyze_cash_flow(self, data: Dict[str, Any]) -> CashFlowAnalysis:
        """分析现金流"""
        operating = data.get("operating_cash_flow", 0)
        investing = data.get("investing_cash_flow", 0)
        financing = data.get("financing_cash_flow", 0)
        
        free_cash_flow = operating + investing  # 简化计算
        
        # 健康状态判断
        health_status = "健康"
        warnings = []
        
        if operating < 0:
            health_status = "预警"
            warnings.append("经营活动现金流为负")
        
        if free_cash_flow < 0:
            health_status = "危险"
            warnings.append("自由现金流为负")
        
        return CashFlowAnalysis(
            operating_cash_flow=operating,
            investing_cash_flow=investing,
            financing_cash_flow=financing,
            free_cash_flow=free_cash_flow,
            health_status=health_status,
            warning_signals=warnings
        )
    
    def _assess_financial_risk(
        self,
        data: Dict[str, Any],
        ratios: FinancialRatio,
        industry: str
    ) -> FinancialRisk:
        """评估财务风险"""
        risk_score = 0.0
        warnings = []
        
        # 偿债能力风险
        if ratios.debt_to_equity and ratios.debt_to_equity > 0.7:
            risk_score += 30
            warnings.append("资产负债率过高")
        
        # 盈利能力风险
        if ratios.roe and ratios.roe < 0.05:
            risk_score += 20
            warnings.append("净资产收益率过低")
        
        # 现金流风险
        if data.get("operating_cash_flow", 0) < 0:
            risk_score += 30
            warnings.append("经营现金流为负")

        earnings_quality = self._analyze_earnings_quality(data)
        if len(earnings_quality.warning_signals) >= 3:
            risk_score += 20
            warnings.append("多项盈利质量异常")
        elif earnings_quality.warning_signals:
            risk_score += 10
            warnings.extend(earnings_quality.warning_signals[:2])

        risk_score = min(risk_score, 100)
        
        # 确定风险等级
        if risk_score >= 70:
            risk_level = "高"
            recommendation = "建议深入调查财务风险，谨慎投资"
        elif risk_score >= 40:
            risk_level = "中"
            recommendation = "建议关注财务风险指标变化"
        else:
            risk_level = "低"
            recommendation = "财务风险可控"
        
        return FinancialRisk(
            risk_level=risk_level,
            risk_score=risk_score,
            warning_flags=warnings,
            detailed_risks={
                "debt_risk": risk_score * 0.4,
                "profit_risk": risk_score * 0.3,
                "earnings_quality_signals": earnings_quality.warning_signals,
            },
            recommendation=recommendation
        )
    
    def _calculate_health_grade(
        self,
        ratios: FinancialRatio,
        cash_flow: CashFlowAnalysis,
        risk: FinancialRisk
    ) -> str:
        """计算财务健康等级"""
        score = 100 - risk.risk_score
        
        if score >= 80:
            return FinancialHealthGrade.EXCELLENT.value
        elif score >= 65:
            return FinancialHealthGrade.GOOD.value
        elif score >= 50:
            return FinancialHealthGrade.FAIR.value
        elif score >= 35:
            return FinancialHealthGrade.POOR.value
        else:
            return FinancialHealthGrade.CRITICAL.value

    @staticmethod
    def _dump_model(model: BaseModel) -> Dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    @staticmethod
    def _num(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _safe_div(cls, numerator: Any, denominator: Any) -> Optional[float]:
        top = cls._num(numerator)
        bottom = cls._num(denominator)
        if top is None or bottom in (None, 0):
            return None
        return top / bottom

    @classmethod
    def _growth(cls, current: Any, previous: Any) -> Optional[float]:
        now = cls._num(current)
        before = cls._num(previous)
        if now is None or before in (None, 0):
            return None
        return (now - before) / abs(before)

    @staticmethod
    def _gap(left: Optional[float], right: Optional[float]) -> Optional[float]:
        if left is None or right is None:
            return None
        return left - right


# 导出
__all__ = [
    "EnhancedFinancialAnalyzer",
    "FinancialRatio",
    "CashFlowAnalysis",
    "BusinessModelAnalysis",
    "EarningsQualityAnalysis",
    "FinancialRisk",
    "FinancialHealthGrade"
]
