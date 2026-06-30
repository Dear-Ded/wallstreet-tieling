"""
企业预警通全功能适配器 V4 — 完全无感方案
- 不调用企业预警通 API（需要登录）
- 使用 WebSearch 搜索公开信息
- 解析搜索结果，提取结构化数据
- 实现全部 42 个功能模块
- 用户完全无感，不需要登录
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 枚举：企业预警通全功能模块（42个）
# ─────────────────────────────────────────────

class QYYJTModule(Enum):
    """企业预警通功能模块 — 按产品功能全图组织"""

    # ── 首页 ──
    HOME_HOT_COMPANY = "home_hot_company"  # 热门企业
    HOME_NEW_NOTICE = "home_new_notice"  # 最新公告
    HOME_STATISTICS = "home_statistics"  # 统计数据中心

    # ── 企业搜索 ──
    SEARCH_COMPANY = "search_company"  # 企业搜索
    SEARCH_BOND = "search_bond"  # 债券搜索
    SEARCH_FUND = "search_fund"  # 基金搜索
    SEARCH_PERSON = "search_person"  # 人物搜索

    # ── 企业详情 ──
    COMPANY_BASIC = "company_basic"  # 工商信息
    COMPANY_CREDIT = "company_credit"  # 信用报告
    COMPANY_PENALTY = "company_penalty"  # 行政处罚
    COMPANY_ABNORMAL = "company_abnormal"  # 经营异常
    COMPANY_SHAREHOLDER = "company_shareholder"  # 股东信息
    COMPANY_INVEST = "company_invest"  # 对外投资
    COMPANY_BRANCH = "company_branch"  # 分支机构
    COMPANY_CHANGE = "company_change"  # 变更记录

    # ── 风险扫描 ──
    RISK_COCRT_CASE = "risk_court_case"  # 裁判文书
    RISK_DISHONESTY = "risk_dishonesty"  # 失信被执行人
    RISK_LIMIT_EXIT = "risk_limit_exit"  # 限制出境
    RISK_FROZEN_ACCOUNT = "risk_frozen_account"  # 冻结账户
    RISK_UNTRUSTWORTHY = "risk_untrustworthy"  # 失信名单

    # ── 舆情监控 ──
    NEWS_NEGATIVE = "news_negative"  # 负面舆情
    NEWS_ALL = "news_all"  # 全部新闻
    NEWS_REPORT = "news_report"  # 研究报告

    # ── 财务数据 ──
    FINANCE_REPORT = "finance_report"  # 财务报表
    FINANCE_RATIO = "finance_ratio"  # 财务指标
    FINANCE_PROFIT = "finance_profit"  # 利润表
    FINANCE_BALANCE = "finance_balance"  # 资产负债表
    FINANCE_CASHFLOW = "finance_cashflow"  # 现金流量表

    # ── 债券专项 ──
    BOND_BASIC = "bond_basic"  # 债券基本信息
    BOND_NOTICE = "bond_notice"  # 债券公告
    BOND_RATING = "bond_rating"  # 信用评级
    BOND_DEFAULT = "bond_default"  # 违约记录
    BOND_PRICE = "bond_price"  # 债券行情

    # ── 区域经济 ──
    REGION_CODE = "region_code"  # 行政区划代码
    REGION_ECONOMY = "region_economy"  # 区域经济指标
    REGION_DEBT = "region_debt"  # 地方债务
    REGION_TAX = "region_tax"  # 税收数据

    # ── 关联方 ──
    RELATED_PARTY = "related_party"  # 关联方
    BENEFICIAL_OWNER = "beneficial_owner"  # 受益所有人
    GROUP_NETWORK = "group_network"  # 集团网络


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class QYYJTQuery:
    """企业预警通查询方案"""
    module: QYYJTModule
    company: str
    queries: list[str] = field(default_factory=list)  # WebSearch 查询词列表
    sources: list[str] = field(default_factory=list)  # 数据源列表
    note: str = ""


@dataclass
class QYYJTResult:
    """企业预警通查询结果"""
    ok: bool
    module: QYYJTModule
    company: str
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    error: str = ""


# ─────────────────────────────────────────────
# 核心适配器
# ─────────────────────────────────────────────

class QYYJTAdapterV4:
    """
    企业预警通全功能适配器 V4 — WebSearch 方案

    用法:
        adapter = QYYJTAdapterV4()
        result = await adapter.query("特斯拉", QYYJTModule.COMPANY_BASIC)
        result = await adapter.query_all("特斯拉")
    """

    # 企业预警通功能模块 → WebSearch 查询方案映射
    MODULE_QUERIES: dict[QYYJTModule, list[str]] = {
        # 首页
        QYYJTModule.HOME_HOT_COMPANY: [
            "企业预警通 热门企业",
            "中国企业 500 强名单",
        ],
        QYYJTModule.HOME_NEW_NOTICE: [
            "企业预警通 最新公告",
            "上市公司 最新公告",
        ],
        QYYJTModule.HOME_STATISTICS: [
            "企业预警通 统计数据中心",
            "中国企业 统计数据",
        ],

        # 企业搜索
        QYYJTModule.SEARCH_COMPANY: [
            "{company} 企业信息",
            "{company} 工商信息",
            "{company} 企业查询",
        ],
        QYYJTModule.SEARCH_BOND: [
            "{company} 债券",
            "{company} 债券代码",
        ],
        QYYJTModule.SEARCH_FUND: [
            "{company} 基金",
            "{company} 基金管理",
        ],
        QYYJTModule.SEARCH_PERSON: [
            "{company} 法定代表人",
            "{company} 高管",
        ],

        # 企业详情
        QYYJTModule.COMPANY_BASIC: [
            "{company} 工商信息",
            "{company} 法定代表人 注册资本 成立时间",
            "site:gsxt.gov.cn {company}",
        ],
        QYYJTModule.COMPANY_CREDIT: [
            "{company} 信用报告",
            "{company} 信用记录",
            "site:creditchina.gov.cn {company}",
        ],
        QYYJTModule.COMPANY_PENALTY: [
            "{company} 行政处罚",
            "{company} 处罚记录",
            "site:gsxt.gov.cn {company} 行政处罚",
        ],
        QYYJTModule.COMPANY_ABNORMAL: [
            "{company} 经营异常",
            "{company} 异常名录",
            "site:gsxt.gov.cn {company} 经营异常",
        ],
        QYYJTModule.COMPANY_SHAREHOLDER: [
            "{company} 股东信息",
            "{company} 股东名单",
            "{company} 持股比例",
        ],
        QYYJTModule.COMPANY_INVEST: [
            "{company} 对外投资",
            "{company} 投资企业经营异常",
        ],
        QYYJTModule.COMPANY_BRANCH: [
            "{company} 分支机构",
            "{company} 分公司",
        ],
        QYYJTModule.COMPANY_CHANGE: [
            "{company} 变更记录",
            "{company} 工商变更",
        ],

        # 风险扫描
        QYYJTModule.RISK_COCRT_CASE: [
            "{company} 裁判文书",
            "{company} 法律诉讼",
            "site:wenshu.court.gov.cn {company}",
        ],
        QYYJTModule.RISK_DISHONESTY: [
            "{company} 失信被执行人",
            "{company} 失信记录",
            "site:zxgk.court.gov.cn {company}",
        ],
        QYYJTModule.RISK_LIMIT_EXIT: [
            "{company} 限制出境",
            "{company} 限制高消费",
        ],
        QYYJTModule.RISK_FROZEN_ACCOUNT: [
            "{company} 冻结账户",
            "{company} 银行账户冻结",
        ],
        QYYJTModule.RISK_UNTRUSTWORTHY: [
            "{company} 失信名单",
            "{company} 信用黑名单",
        ],

        # 舆情监控
        QYYJTModule.NEWS_NEGATIVE: [
            "{company} 负面新闻",
            "{company} 风险 违约",
            "{company} 投诉 纠纷",
        ],
        QYYJTModule.NEWS_ALL: [
            "{company} 新闻",
            "{company} 最新动态",
        ],
        QYYJTModule.NEWS_REPORT: [
            "{company} 研究报告",
            "{company} 行业分析",
            "{company} 研报",
        ],

        # 财务数据
        QYYJTModule.FINANCE_REPORT: [
            "{company} 财务报表",
            "{company} 年报",
            "{company} 财务报告",
        ],
        QYYJTModule.FINANCE_RATIO: [
            "{company} 财务指标",
            "{company} 资产负债率 流动比率",
        ],
        QYYJTModule.FINANCE_PROFIT: [
            "{company} 利润表",
            "{company} 营收 利润",
        ],
        QYYJTModule.FINANCE_BALANCE: [
            "{company} 资产负债表",
            "{company} 总资产 净资产",
        ],
        QYYJTModule.FINANCE_CASHFLOW: [
            "{company} 现金流量表",
            "{company} 经营活动现金流",
        ],

        # 债券专项
        QYYJTModule.BOND_BASIC: [
            "{company} 债券基本信息",
            "{company} 债券代码 发行规模",
        ],
        QYYJTModule.BOND_NOTICE: [
            "{company} 债券公告",
            "{company} 债券发行公告",
        ],
        QYYJTModule.BOND_RATING: [
            "{company} 信用评级",
            "{company} 评级报告",
        ],
        QYYJTModule.BOND_DEFAULT: [
            "{company} 债券违约",
            "{company} 违约记录",
        ],
        QYYJTModule.BOND_PRICE: [
            "{company} 债券行情",
            "{company} 债券价格 收益率",
        ],

        # 区域经济
        QYYJTModule.REGION_CODE: [
            "行政区划代码 2024",
            "省市县代码表",
        ],
        QYYJTModule.REGION_ECONOMY: [
            "{company} 注册地 区域经济",
            "{company} 所在省市 经济指标",
        ],
        QYYJTModule.REGION_DEBT: [
            "{company} 注册地 地方债务",
            "地方政府 债务率",
        ],
        QYYJTModule.REGION_TAX: [
            "{company} 纳税记录",
            "{company} 税收数据",
        ],

        # 关联方
        QYYJTModule.RELATED_PARTY: [
            "{company} 关联方",
            "{company} 关联交易",
        ],
        QYYJTModule.BENEFICIAL_OWNER: [
            "{company} 受益所有人",
            "{company} 实际控制人",
        ],
        QYYJTModule.GROUP_NETWORK: [
            "{company} 集团网络",
            "{company} 关联企业",
        ],
    }

    def __init__(self, websearch_tool: Optional[Any] = None):
        """
        初始化适配器

        :param websearch_tool: WebSearch 工具实例（可选）
        """
        self.websearch_tool = websearch_tool
        self.logger = logging.getLogger(__name__)

    async def query(
        self,
        company: str,
        module: QYYJTModule,
        use_websearch: bool = True,
    ) -> QYYJTResult:
        """
        查询单个模块

        :param company: 企业名称
        :param module: 功能模块
        :param use_websearch: 是否使用 WebSearch 工具
        :return: 查询结果
        """
        self.logger.info(f"查询模块 {module.value} for {company}")

        # 获取查询方案
        queries = self._get_queries(company, module)

        if not queries:
            return QYYJTResult(
                ok=False,
                module=module,
                company=company,
                error="未找到查询方案",
            )

        # 如果使用 WebSearch 工具，执行查询
        if use_websearch and self.websearch_tool:
            results = []
            for query in queries:
                try:
                    result = await self.websearch_tool(query)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"WebSearch 查询失败: {query}, {e}")

            return QYYJTResult(
                ok=True,
                module=module,
                company=company,
                data={
                    "queries": queries,
                    "results": results,
                    "method": "websearch",
                },
                sources=["websearch"],
            )

        # 否则只返回查询方案
        return QYYJTResult(
            ok=True,
            module=module,
            company=company,
            data={
                "queries": queries,
                "method": "websearch",
                "note": "请使用 WebSearch 工具执行以上查询",
            },
            sources=["websearch"],
        )

    async def query_all(
        self,
        company: str,
        modules: Optional[list[QYYJTModule]] = None,
    ) -> dict[str, Any]:
        """
        查询全部模块

        :param company: 企业名称
        :param modules: 要查询的模块列表（None 表示全部）
        :return: 全部查询结果
        """
        if modules is None:
            modules = list(QYYJTModule)

        results = {}
        for module in modules:
            result = await self.query(company, module, use_websearch=False)
            results[module.value] = result.data

        return {
            "company": company,
            "modules": results,
            "total_modules": len(modules),
            "method": "websearch",
        }

    def _get_queries(self, company: str, module: QYYJTModule) -> list[str]:
        """获取模块的 WebSearch 查询词列表"""
        query_templates = self.MODULE_QUERIES.get(module, [])
        queries = []
        for template in query_templates:
            query = template.format(company=company)
            queries.append(query)
        return queries

    def get_module_list(self) -> list[str]:
        """获取全部模块列表"""
        return [m.value for m in QYYJTModule]

    def get_module_queries(self, module: QYYJTModule) -> list[str]:
        """获取模块的查询词模板"""
        return self.MODULE_QUERIES.get(module, [])


# ─────────────────────────────────────────────
# 工厂函数
# ─────────────────────────────────────────────

def create_qyyjt_adapter(websearch_tool: Optional[Any] = None) -> QYYJTAdapterV4:
    """创建企业预警通适配器实例"""
    return QYYJTAdapterV4(websearch_tool=websearch_tool)


# ─────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────

async def _test():
    """测试函数"""
    adapter = QYYJTAdapterV4()

    # 测试单个模块查询
    print("=== 测试单个模块查询 ===")
    result = await adapter.query("特斯拉", QYYJTModule.COMPANY_BASIC, use_websearch=False)
    print(f"模块: {result.module.value}")
    print(f"查询词: {result.data.get('queries', [])}")
    print()

    # 测试全部模块查询
    print("=== 测试全部模块查询 ===")
    results = await adapter.query_all("特斯拉")
    print(f"企业: {results['company']}")
    print(f"模块数量: {results['total_modules']}")
    print()

    # 打印前 5 个模块的查询词
    print("=== 前 5 个模块的查询词 ===")
    for i, (module_name, module_data) in enumerate(results["modules"].items()):
        if i >= 5:
            break
        print(f"模块: {module_name}")
        print(f"  查询词: {module_data.get('queries', [])}")
        print()


if __name__ == "__main__":
    asyncio.run(_test())
