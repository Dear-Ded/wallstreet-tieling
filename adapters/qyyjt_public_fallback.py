#!/usr/bin/env python3
"""
QYYJT Public Fallback Adapter — query-template DRAFT.

STATUS: query-template draft only. Not connected to search engine.
42 module search templates defined. Zero data retrieval verified.
Do not claim as working fallback until live search provider is integrated.
 — 42 query-template draft only, not wired, zero data retrieval verified.

This adapter defines SEARCH QUERY TEMPLATES only. It does NOT scrape or retrieve
data. Templates must be connected to a live search provider (DuckDuckGo/SearXNG)
before any data retrieval is possible.

For each QYYJT module, it defines search query templates (NOT live data connectors):
- Search query template
- Expected field mapping
- Source URL pattern
- Confidence level
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Module → public search templates
MODULE_SEARCH_TEMPLATES = {
    # ====== P0 Report-Critical ======
    "ent_basic": {
        "query": "{company} 企业信用信息公示 system site:gsxt.gov.cn OR site:qichacha.com OR site:tianyancha.com",
        "fields": ["legal_name", "identifier", "status", "legal_representative", "registered_capital"],
        "source_hint": "public_registry_search",
    },
    "ent_credit": {
        "query": "{company} 信用报告 信用评级 OR site:creditchina.gov.cn",
        "fields": ["credit_section", "credit_item", "credit_status", "reference_date"],
        "source_hint": "public_credit_search",
    },
    "ent_penalty": {
        "query": "{company} 行政处罚 site:creditchina.gov.cn OR site:gsxt.gov.cn",
        "fields": ["agency", "decision_number", "violation", "penalty", "decision_date"],
        "source_hint": "public_penalty_search",
    },
    "ent_financing": {
        "query": "{company} 融资 增资 股东变更 OR site:gsxt.gov.cn",
        "fields": ["financing_type", "amount", "counterparty", "event_date", "status"],
        "source_hint": "public_financing_search",
    },
    "ent_change": {
        "query": "{company} 工商变更 site:gsxt.gov.cn",
        "fields": ["change_item", "before_value", "after_value", "change_date"],
        "source_hint": "public_change_search",
    },
    "risk_scan": {
        "query": "{company} 风险 诉讼 失信 处罚 经营异常",
        "fields": ["risk_category", "severity", "risk_label", "summary", "status"],
        "source_hint": "public_risk_search",
    },
    "risk_signal": {
        "query": "{company} 风险信号 预警 负面",
        "fields": ["signal_code", "signal_label", "severity", "signal_summary"],
        "source_hint": "public_signal_search",
    },
    "actual_controller": {
        "query": "{company} 实际控制人 股东 最终受益人",
        "fields": ["person_name", "relation_type", "control_path", "confidence_basis"],
        "source_hint": "public_controller_search",
    },
    "court_cases": {
        "query": "{company} 裁判文书 site:wenshu.court.gov.cn",
        "fields": ["case_number", "court", "cause", "parties", "case_date", "case_status"],
        "source_hint": "public_court_search",
    },
    "dishonesty": {
        "query": "{company} 失信被执行人 site:zxgk.court.gov.cn",
        "fields": ["case_number", "court", "obligation", "publish_date", "performance_status"],
        "source_hint": "public_dishonesty_search",
    },
    "limit_high": {
        "query": "{company} 限制高消费 site:zxgk.court.gov.cn",
        "fields": ["case_number", "court", "restricted_subject", "publish_date", "status"],
        "source_hint": "public_limit_search",
    },
    "execution": {
        "query": "{company} 被执行人 site:zxgk.court.gov.cn",
        "fields": ["case_number", "court", "amount", "filing_date", "execution_status"],
        "source_hint": "public_execution_search",
    },
    "news_negative": {
        "query": "{company} 负面新闻 处罚 违规 诉讼",
        "fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
        "source_hint": "public_news_search",
    },
    "research": {
        "query": "{company} 行业研究报告 研报",
        "fields": ["report_title", "publisher", "publish_date", "industry", "product", "summary"],
        "source_hint": "public_research_search",
    },
    "financial": {
        "query": "{company} 财务报表 营收 利润 site:cninfo.com.cn OR site:sse.com.cn",
        "fields": ["period", "metric", "value", "unit", "accounting_scope"],
        "source_hint": "public_financial_search",
    },
    "fin_indic": {
        "query": "{company} 财务指标 市盈率 市净率 资产负债率",
        "fields": ["period", "indicator", "value", "unit", "meaning"],
        "source_hint": "public_indicator_search",
    },
    "related": {
        "query": "{company} 关联方 子公司 对外投资 site:gsxt.gov.cn",
        "fields": ["related_name", "relation_type", "relationship_direction", "confidence_basis"],
        "source_hint": "public_related_search",
    },
    "ubo": {
        "query": "{company} 最终受益人 实际控制人 股东穿透",
        "fields": ["beneficial_owner", "path_nodes", "ownership_ratio", "layer_depth"],
        "source_hint": "public_ubo_search",
    },
    "group": {
        "query": "{company} 集团 子公司 关联公司 network",
        "fields": ["from_entity", "to_entity", "relation_type", "control_or_affiliation_basis"],
        "source_hint": "public_group_search",
    },

    # ====== P1 Domain-Depth ======
    "bond_credit": {
        "query": "{company} 债券 评级 site:csrc.gov.cn OR site:sse.com.cn",
        "fields": ["bond_name", "issuer", "rating", "rating_agency", "rating_date"],
        "source_hint": "public_bond_search",
    },
    "bond_profile": {
        "query": "{company} 债券 发行 site:csrc.gov.cn OR site:sse.com.cn",
        "fields": ["bond_name", "issuer", "maturity_date", "coupon_rate", "bond_status"],
        "source_hint": "public_bond_search",
    },
    "bond_issue": {
        "query": "{company} 债券发行 site:sse.com.cn OR site:szse.cn",
        "fields": ["bond_name", "issuer", "issue_date", "issue_amount", "bond_status"],
        "source_hint": "public_bond_search",
    },
    "bond_default": {
        "query": "{company} 债券违约 site:csrc.gov.cn OR 债券 逾期",
        "fields": ["bond_name", "issuer", "default_date", "amount", "status"],
        "source_hint": "public_bond_search",
    },
    "bond_calendar": {
        "query": "{company} 债券 到期 付息 site:sse.com.cn OR site:szse.cn",
        "fields": ["bond_name", "issuer", "event_date", "event_type", "amount", "status"],
        "source_hint": "public_bond_search",
    },
    "city_invest": {
        "query": "{company} 城建 基础设施 地方投资",
        "fields": ["region_name", "indicator", "period", "value", "risk_level"],
        "source_hint": "public_city_search",
    },
    "region_code": {
        "query": "{company} 工商注册 所在地区 行政区划",
        "fields": ["region_name", "indicator", "period", "value", "risk_level"],
        "source_hint": "public_region_search",
    },
    "region_economy": {
        "query": "{company} 地区经济 site:stats.gov.cn",
        "fields": ["region_name", "indicator", "period", "value", "risk_level"],
        "source_hint": "public_region_search",
    },
    "region_debt": {
        "query": "{company} 地方债务 site:mof.gov.cn OR 城投",
        "fields": ["region_name", "indicator", "period", "value", "risk_level"],
        "source_hint": "public_region_search",
    },
    "fin_inst": {
        "query": "{company} 金融机构 银行 counterparty 关联 金融",
        "fields": ["institution_name", "institution_type", "license_status", "region", "risk_level"],
        "source_hint": "public_fininst_search",
    },

    # ====== P2 Supplemental ======
    "merger": {
        "query": "{company} 并购 重组 site:csrc.gov.cn",
        "fields": ["event_type", "counterparty", "announcement_date", "amount", "status"],
        "source_hint": "public_merger_search",
    },
    "pledge": {
        "query": "{company} 股权质押 site:gsxt.gov.cn",
        "fields": ["shareholder", "pledgee", "pledged_amount", "pledge_date", "status"],
        "source_hint": "public_pledge_search",
    },
    "freeze": {
        "query": "{company} 股权冻结 site:gsxt.gov.cn",
        "fields": ["subject", "court", "frozen_amount", "freeze_date", "status"],
        "source_hint": "public_freeze_search",
    },
    "auction": {
        "query": "{company} 司法拍卖 site:zxgk.court.gov.cn",
        "fields": ["asset_name", "auction_date", "court", "amount", "status"],
        "source_hint": "public_auction_search",
    },
    "land": {
        "query": "{company} 土地 site:landchina.com OR 土地出让",
        "fields": ["land_location", "area", "acquisition_date", "land_use", "status"],
        "source_hint": "public_land_search",
    },
    "tax": {
        "query": "{company} 纳税 site:chinatax.gov.cn OR 纳税信用",
        "fields": ["tax_item", "tax_status", "period", "agency"],
        "source_hint": "public_tax_search",
    },
    "import_export": {
        "query": "{company} 进出口 site:customs.gov.cn OR 外贸",
        "fields": ["trade_type", "country", "period", "amount", "status"],
        "source_hint": "public_trade_search",
    },
    "patent": {
        "query": "{company} 专利 site:cnipa.gov.cn",
        "fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
        "source_hint": "public_ip_search",
    },
    "trademark": {
        "query": "{company} 商标 site:cnipa.gov.cn",
        "fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
        "source_hint": "public_ip_search",
    },
    "copyright": {
        "query": "{company} 著作权 site:ccopyright.com.cn",
        "fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
        "source_hint": "public_ip_search",
    },
    "recruit": {
        "query": "{company} 招聘 site:51job.com OR site:zhaopin.com OR site:linkedin.com",
        "fields": ["position", "location", "publish_date", "headcount", "status"],
        "source_hint": "public_recruit_search",
    },
    "court_announce": {
        "query": "{company} 法院公告 site:wenshu.court.gov.cn OR site:court.gov.cn",
        "fields": ["case_number", "court", "cause", "parties", "hearing_date", "status"],
        "source_hint": "public_court_search",
    },
    "news_all": {
        "query": "{company} 新闻",
        "fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
        "source_hint": "public_news_search",
    },
}


def get_module_query_template(module: str) -> dict[str, Any]:
    """Get the search query template for a QYYJT module."""
    return MODULE_SEARCH_TEMPLATES.get(module, {})


def build_public_query(company: str, module: str) -> str:
    """Build a public search query for a specific module."""
    template = MODULE_SEARCH_TEMPLATES.get(module)
    if not template:
        return f"{company}"
    return template["query"].format(company=company)


def get_public_source_hint(module: str) -> str:
    """Get the source hint for a module's public search."""
    return MODULE_SEARCH_TEMPLATES.get(module, {}).get("source_hint", "public_web_search")


@dataclass
class PublicSearchModuleMapping:
    """Mapping from a QYYJT module to its public search fallback."""
    module: str
    query_template: str
    fields: list[str]
    source_hint: str

    @staticmethod
    def all() -> list["PublicSearchModuleMapping"]:
        return [
            PublicSearchModuleMapping(
                module=mod,
                query_template=v["query"],
                fields=v["fields"],
                source_hint=v["source_hint"],
            )
            for mod, v in MODULE_SEARCH_TEMPLATES.items()
        ]

    def query_for(self, company: str) -> str:
        return self.query_template.format(company=company)
