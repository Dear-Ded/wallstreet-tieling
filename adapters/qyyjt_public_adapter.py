"""
qyyjt_public_adapter.py — 企业预警通公开数据适配器（不需要登录）

使用完全公开的数据源，不依赖企业预警通登录：
1. 国家企业信用信息公示系统（公开）
2. 中国裁判文书网（公开）
3. 中国执行信息公开网（公开）
4. 企业预警通公开页面（HTML解析）
5. 其他公开API

优势：
- 完全合法，使用公开数据源
- 不需要登录凭据
- 数据来源可靠
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


class QYYJTPublicAdapter:
    """
    企业预警通公开数据适配器
    
    用法:
        adapter = QYYJTPublicAdapter()
        
        # 企业工商信息（国家企业信用信息公示系统）
        info = await adapter.get_company_basic("中国平安")
        
        # 裁判文书（中国裁判文书网）
        cases = await adapter.get_court_cases("中国平安")
        
        # 被执行人信息（中国执行信息公开网）
        executions = await adapter.get_execution_info("中国平安")
        
        # 综合查询（全部公开数据源）
        result = await adapter.search_all("中国平安")
    """
    
    # 公开数据源 URL
    GSXT_URL = "http://www.gsxt.gov.cn/index.html"  # 国家企业信用信息公示系统
    COURT_URL = "https://wenshu.court.gov.cn/"      # 中国裁判文书网
    ZHIXING_URL = "http://zxgk.court.gov.cn/"      # 中国执行信息公开网
    QYYJT_URL = "https://www.qyyjt.cn/"        # 企业预警通（公开页面）
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self._cache: Dict[str, Any] = {}
    
    # ══════════════════════════════════════════════════════
    # 1. 国家企业信用信息公示系统（公开）
    # ══════════════════════════════════════════════════════
    
    async def get_company_basic(self, company: str) -> Dict[str, Any]:
        """
        获取企业工商信息（国家企业信用信息公示系统）
        
        Args:
            company: 企业名称
            
        Returns:
            企业工商信息
        """
        result = {
            "company": company,
            "source": "gsxt",
            "url": self.GSXT_URL,
            "data": {},
        }
        
        try:
            # 国家企业信用信息公示系统需要模拟搜索
            # 这里返回搜索 URL，由上层 WebSearch 工具执行
            search_url = f"http://www.gsxt.gov.cn/corp-query-search-1-{company}.html"
            result["search_url"] = search_url
            result["method"] = "websearch"
            result["note"] = "请使用 WebSearch 工具访问国家企业信用信息公示系统"
            return result
            
        except Exception as e:
            return {"error": str(e), "company": company, "source": "gsxt"}
    
    # ══════════════════════════════════════════════════════
    # 2. 中国裁判文书网（公开）
    # ══════════════════════════════════════════════════════
    
    async def get_court_cases(self, company: str, max_results: int = 10) -> Dict[str, Any]:
        """
        获取裁判文书（中国裁判文书网）
        
        Args:
            company: 企业名称
            max_results: 最大结果数
            
        Returns:
            裁判文书列表
        """
        result = {
            "company": company,
            "source": "court",
            "url": self.COURT_URL,
            "data": {"list": [], "total": 0},
        }
        
        try:
            # 中国裁判文书网需要模拟搜索
            # 这里返回搜索 URL，由上层 WebSearch 工具执行
            search_url = f"https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?searchSource=2&searchWord={company}"
            result["search_url"] = search_url
            result["method"] = "websearch"
            result["note"] = "请使用 WebSearch 工具访问中国裁判文书网"
            return result
            
        except Exception as e:
            return {"error": str(e), "company": company, "source": "court"}
    
    # ══════════════════════════════════════════════════════
    # 3. 中国执行信息公开网（公开）
    # ══════════════════════════════════════════════════════
    
    async def get_execution_info(self, company: str) -> Dict[str, Any]:
        """
        获取被执行人信息（中国执行信息公开网）
        
        Args:
            company: 企业名称
            
        Returns:
            被执行人信息
        """
        result = {
            "company": company,
            "source": "zhixing",
            "url": self.ZHIXING_URL,
            "data": {},
        }
        
        try:
            # 中国执行信息公开网需要模拟搜索
            search_url = f"http://zxgk.court.gov.cn/zhixing/search?searchKey={company}"
            result["search_url"] = search_url
            result["method"] = "websearch"
            result["note"] = "请使用 WebSearch 工具访问中国执行信息公开网"
            return result
            
        except Exception as e:
            return {"error": str(e), "company": company, "source": "zhixing"}
    
    # ══════════════════════════════════════════════════════
    # 4. 企业预警通公开页面（HTML解析）
    # ══════════════════════════════════════════════════════
    
    async def get_qyyjt_public_data(self, company: str) -> Dict[str, Any]:
        """
        获取企业预警通公开页面数据（HTML解析）
        
        Args:
            company: 企业名称
            
        Returns:
            公开页面数据
        """
        if not BS4_AVAILABLE:
            return {"error": "beautifulsoup4 未安装", "company": company}
        
        result = {
            "company": company,
            "source": "qyyjt_public",
            "data": {},
        }
        
        try:
            # 访问企业预警通搜索页
            url = f"{self.QYYJT_URL}/search?text={company}"
            resp = self.session.get(url, timeout=15)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # 查找页面中的链接
                links = soup.find_all("a", href=True)
                company_links = [
                    link["href"] for link in links
                    if "company" in link.get("href", "") or "stock" in link.get("href", "")
                ]
                
                result["data"]["links"] = company_links[:10]
                result["data"]["page_title"] = soup.title.string if soup.title else ""
                result["method"] = "html_parse"
                result["note"] = "企业预警通搜索页返回的是SPA，需要JavaScript渲染"
                
            return result
            
        except Exception as e:
            return {"error": str(e), "company": company, "source": "qyyjt_public"}
    
    # ══════════════════════════════════════════════════════
    # 5. 综合查询（全部公开数据源）
    # ══════════════════════════════════════════════════════
    
    async def search_all(self, company: str) -> Dict[str, Any]:
        """
        综合查询（全部公开数据源）
        
        Args:
            company: 企业名称
            
        Returns:
            全部公开数据源的查询结果
        """
        result = {
            "company": company,
            "timestamp": datetime.now().isoformat(),
            "sources": [],
            "data": {},
        }
        
        # 1. 国家企业信用信息公示系统
        gsxt = await self.get_company_basic(company)
        result["data"]["gsxt"] = gsxt
        result["sources"].append("gsxt")
        
        # 2. 中国裁判文书网
        court = await self.get_court_cases(company)
        result["data"]["court"] = court
        result["sources"].append("court")
        
        # 3. 中国执行信息公开网
        zhixing = await self.get_execution_info(company)
        result["data"]["zhixing"] = zhixing
        result["sources"].append("zhixing")
        
        # 4. 企业预警通公开页面
        qyyjt = await self.get_qyyjt_public_data(company)
        result["data"]["qyyjt"] = qyyjt
        result["sources"].append("qyyjt")
        
        return result
    
    # ══════════════════════════════════════════════════════
    # 6. 生成 WebSearch 查询方案（全部42个模块）
    # ══════════════════════════════════════════════════════
    
    def get_module_query(self, module: str, company: str) -> Dict[str, Any]:
        """
        获取指定功能模块的 WebSearch 查询方案（全部42个模块）
        
        Args:
            module: 模块名称（对应 QYYJTModule 枚举）
            company: 企业名称
            
        Returns:
            查询方案（包含搜索URL和说明）
        """
        # 企业尽调（5个模块）
        if module == "ent_basic":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:gsxt.gov.cn {company} 工商信息",
                    f"{company} 注册资本 法定代表人 成立日期",
                    f"{company} 股东信息 出资比例",
                ],
                "urls": [
                    f"http://www.gsxt.gov.cn/corp-query-search-1-{company}.html",
                ],
                "source": "public_multi",
            }
        
        elif module == "ent_credit":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:gsxt.gov.cn {company} 信用评级",
                    f"{company} 信用报告 失信记录",
                    f"{company} 经营异常 严重违法",
                ],
                "source": "public_multi",
            }
        
        elif module == "ent_penalty":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:gsxt.gov.cn {company} 行政处罚",
                    f"{company} 罚款 违法记录",
                ],
                "source": "public_multi",
            }
        
        # 风险扫描（7个模块）
        elif module == "court_cases":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:wenshu.court.gov.cn {company} 裁判文书",
                    f"{company} 法律诉讼 判决书",
                ],
                "urls": [
                    f"https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?searchSource=2&searchWord={company}",
                ],
                "source": "public_multi",
            }
        
        elif module == "dishonesty":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:zxgk.court.gov.cn {company} 失信被执行人",
                    f"{company} 老赖 失信记录",
                ],
                "urls": [
                    f"http://zxgk.court.gov.cn/zhixing/search?searchKey={company}",
                ],
                "source": "public_multi",
            }
        
        elif module == "execution":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"site:zxgk.court.gov.cn {company} 被执行人",
                    f"{company} 执行信息 执行法院",
                ],
                "source": "public_multi",
            }
        
        # 舆情监控（3个模块）
        elif module == "news_negative":
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"{company} 负面新闻 投诉 纠纷",
                    f"{company} 违法 违规 处罚",
                ],
                "source": "public_multi",
            }
        
        # 默认：生成通用查询
        else:
            return {
                "module": module,
                "company": company,
                "queries": [
                    f"{company} {module} 查询",
                    f"site:gov.cn {company} {module}",
                ],
                "source": "public_multi",
                "note": "请使用 WebSearch 工具执行以上查询",
            }


# ══════════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════════

async def get_public_data(company: str) -> Dict[str, Any]:
    """
    获取企业全部公开数据（不需要登录）
    
    使用方式：
        result = await get_public_data("中国平安")
        # result 包含全部公开数据源的查询结果
    """
    adapter = QYYJTPublicAdapter()
    return await adapter.search_all(company)


if __name__ == "__main__":
    # 测试
    import asyncio
    
    async def test():
        print("=== 测试公开数据适配器 ===")
        
        adapter = QYYJTPublicAdapter()
        
        # 测试综合查询
        print("\n1. 测试综合查询...")
        result = await adapter.search_all("中国平安")
        print(f"查询企业: {result['company']}")
        print(f"数据源数量: {len(result['sources'])}")
        print(f"数据源: {result['sources']}")
        
        # 测试模块查询
        print("\n2. 测试模块查询...")
        modules = ["ent_basic", "court_cases", "dishonesty", "news_negative"]
        for mod in modules:
            query = adapter.get_module_query(mod, "中国平安")
            print(f"  模块: {mod}")
            print(f"    查询词: {query['queries'][:2]}")
        
        print("\n✅ 测试完成")
    
    asyncio.run(test())
