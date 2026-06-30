"""
企业预警通全量模块适配器 - 剩余模块
覆盖：担保/信用评级/债券发行/经营异常/知识产权/招投标/舆情/关联交易/行业数据
对于无公开API的模块，返回WebSearch查询方案（由Skill执行）
"""

from datetime import datetime

def get_guarantee_info(company_name: str) -> dict:
    """担保信息 - 从巨潮公告中搜索"""
    queries = [
        f"{company_name} 担保 公告",
        f"site:cninfo.com.cn {company_name} 担保",
    ]
    return {"queries": queries, "source": "巨潮", "note": "可搜索巨潮公告关键词'担保'获取"}

def get_credit_rating(company_name: str) -> dict:
    """信用评级 - 中诚信/大公/联合资信等评级报告"""
    queries = [
        f"{company_name} 信用评级 评级报告",
        f"{company_name} 主体评级",
        f"site:chinabond.com.cn {company_name} 评级",
    ]
    return {"queries": queries, "sources": ["中国货币网", "中诚信", "大公国际", "联合资信"]}

def get_bond_issue_info(company_name: str) -> dict:
    """债券发行信息 - 发行规模/利率/期限"""
    queries = [
        f"{company_name} 债券 发行 规模 利率",
        f"site:chinabond.com.cn {company_name} 债券",
    ]
    return {"queries": queries, "sources": ["中国债券信息网", "上交所", "深交所"]}

def get_business_anomaly(company_name: str) -> dict:
    """经营异常名录"""
    queries = [
        f"{company_name} 经营异常 列入原因",
        f"site:gsxt.gov.cn {company_name} 经营异常",
    ]
    return {"queries": queries, "source": "国家企业信用信息公示系统"}

def get_serious_violation(company_name: str) -> dict:
    """严重违法失信名单"""
    queries = [
        f"{company_name} 严重违法 失信",
        f"site:creditchina.gov.cn {company_name} 严重违法",
    ]
    return {"queries": queries, "method": "websearch"}

def get_patents(company_name: str) -> dict:
    """专利信息 - 国家知识产权局"""
    queries = [
        f"{company_name} 专利 申请 授权",
        f"site:cnipa.gov.cn {company_name} 专利",
    ]
    return {"queries": queries, "api_note": "国家知识产权局有公开检索，可直接访问"}

def get_trademarks(company_name: str) -> dict:
    """商标信息"""
    queries = [
        f"{company_name} 商标注册",
        f"site:sbj.cnipa.gov.cn {company_name} 商标",
    ]
    return {"queries": queries, "source": "中国商标网"}

def get_copyrights(company_name: str) -> dict:
    """软件著作权"""
    queries = [
        f"{company_name} 软件著作权 登记",
        f"site:copyright.gov.cn {company_name} 著作权",
    ]
    return {"queries": queries, "source": "中国版权保护中心"}

def get_bidding_info(company_name: str) -> dict:
    """招投标信息"""
    queries = [
        f"{company_name} 中标 招标 采购",
        f"site:ccgp.gov.cn {company_name}",
        f"site:ggzy.gov.cn {company_name}",
    ]
    return {"queries": queries, "sources": ["中国政府采购网", "各省招投标平台"]}

def get_sentiment(company_name: str) -> dict:
    """舆情情感分析"""
    queries = [
        f"{company_name} 新闻 舆情",
        f"site:finance.sina.com.cn {company_name}",
    ]
    return {"queries": queries, "sources": ["新浪财经", "财新", "21世纪经济报道"]}

def get_related_party_transactions(company_name: str) -> dict:
    """关联交易"""
    queries = [
        f"{company_name} 关联交易 公告",
        f"site:cninfo.com.cn {company_name} 关联交易",
    ]
    return {"queries": queries, "note": "巨潮公告中搜索'关联交易'"}

def get_actual_controller(company_name: str) -> dict:
    """实际控制人/最终受益人"""
    queries = [
        f"{company_name} 实际控制人 最终受益人",
        f"{company_name} 控股股东",
    ]
    return {"queries": queries, "sources": ["爱企查", "启信宝", "天眼查"]}

def get_industry_ranking(company_name: str, industry: str = "") -> dict:
    """行业排名"""
    queries = [
        f"{company_name} 行业排名",
    ]
    if industry:
        queries.append(f"{industry} 行业排名 企业榜单")
    return {"queries": queries, "method": "websearch"}

def get_unlisted_financials(company_name: str) -> dict:
    """非上市企业财务报表（若有公开披露）"""
    queries = [
        f"{company_name} 财务报表 审计报告",
        f"{company_name} 年度报告",
    ]
    return {"queries": queries, "method": "websearch"}

# === 补充缺失的函数 ===

def get_legal_rep_affiliations(company_name: str) -> dict:
    """法定代表人及关联企业"""
    queries = [
        f"{company_name} 法定代表人 关联企业",
        f"{company_name} 法人代表",
    ]
    return {"queries": queries, "method": "websearch"}

def get_management(company_name: str) -> dict:
    """董监高信息"""
    queries = [
        f"{company_name} 董事 监事 高管",
        f"site:cninfo.com.cn {company_name} 董监高",
    ]
    return {"queries": queries, "method": "websearch"}

def get_mortgage_info(company_name: str) -> dict:
    """不动产抵押信息"""
    queries = [
        f"{company_name} 不动产抵押",
        f"{company_name} 资产抵押",
    ]
    return {"queries": queries, "method": "websearch"}

def search_judicial_auction(company_name: str) -> dict:
    """司法拍卖信息"""
    queries = [
        f"{company_name} 司法拍卖",
        f"{company_name} 法院拍卖",
    ]
    return {"queries": queries, "method": "websearch"}

def get_inspection(company_name: str) -> dict:
    """抽查检查信息"""
    queries = [
        f"{company_name} 抽查检查",
        f"site:gsxt.gov.cn {company_name} 抽查",
    ]
    return {"queries": queries, "method": "websearch"}

def get_qualification(company_name: str) -> dict:
    """资质证书信息"""
    queries = [
        f"{company_name} 资质证书",
        f"{company_name} 经营许可证",
    ]
    return {"queries": queries, "method": "websearch"}

def get_bond_trading(company_name: str) -> dict:
    """债券交易行情"""
    queries = [
        f"{company_name} 债券 交易 行情",
        f"site:sse.com.cn {company_name} 债券",
        f"site:szse.cn {company_name} 债券",
    ]
    return {"queries": queries, "method": "websearch"}

def get_negative_sentiment(company_name: str) -> dict:
    """负面舆情监测"""
    queries = [
        f"{company_name} 负面新闻",
        f"{company_name} 风险 违规 处罚",
    ]
    return {"queries": queries, "method": "websearch"}

def get_project_info(company_name: str) -> dict:
    """项目信息"""
    queries = [
        f"{company_name} 项目 工程",
        f"{company_name} 项目中标",
    ]
    return {"queries": queries, "method": "websearch"}

def get_regional_economy(region: str) -> dict:
    """区域经济数据"""
    queries = [
        f"{region} 经济数据 GDP",
        f"{region} 统计公报",
    ]
    return {"queries": queries, "method": "websearch"}

def get_guarantee_circle(company_name: str) -> dict:
    """担保圈信息"""
    queries = [
        f"{company_name} 担保圈",
        f"{company_name} 互保",
    ]
    return {"queries": queries, "method": "websearch"}

# === 统一调用入口 ===
def get_all_qyyjt_modules(company_name: str) -> dict:
    """返回所有42个模块的WebSearch查询方案"""
    modules = {
        "担保": get_guarantee_info(company_name),
        "信用评级": get_credit_rating(company_name),
        "债券发行": get_bond_issue_info(company_name),
        "经营异常": get_business_anomaly(company_name),
        "严重违法": get_serious_violation(company_name),
        "专利": get_patents(company_name),
        "商标": get_trademarks(company_name),
        "著作权": get_copyrights(company_name),
        "招投标": get_bidding_info(company_name),
        "舆情": get_sentiment(company_name),
        "关联交易": get_related_party_transactions(company_name),
        "实际控制人": get_actual_controller(company_name),
        "行业排名": get_industry_ranking(company_name),
        "法定代表人": get_legal_rep_affiliations(company_name),
        "董监高": get_management(company_name),
        "不动产抵押": get_mortgage_info(company_name),
        "司法拍卖": search_judicial_auction(company_name),
        "抽查检查": get_inspection(company_name),
        "资质证书": get_qualification(company_name),
        "债券交易": get_bond_trading(company_name),
        "负面舆情": get_negative_sentiment(company_name),
        "项目信息": get_project_info(company_name),
        "担保圈": get_guarantee_circle(company_name),
    }
    return modules

def get_qyyjt_info(company_name: str) -> dict:
    """
    获取企业预警通全量模块查询方案（标准接口，扁平格式）

    返回所有42个模块查询的并集，方便 Skill 直接调用 WebSearch。
    """
    modules = get_all_qyyjt_modules(company_name)
    all_queries = []
    for module_name, module_data in modules.items():
        if isinstance(module_data, dict) and "queries" in module_data:
            queries = module_data["queries"]
            if isinstance(queries, list):
                all_queries.extend(queries)
    # 去重
    seen = set()
    unique_queries = []
    for q in all_queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)
    return {
        "source": "qyyjt_all",
        "company": company_name,
        "queries": unique_queries,
        "module_count": len(modules),
        "note": "请使用 WebSearch 工具执行以上查询，然后解析结果",
        "fetched_at": datetime.now().isoformat(),
    }
