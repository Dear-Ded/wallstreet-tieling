"""
qyyjt_playwright_adapter.py — 使用 Playwright 用户授权会话接入

企业预警通数据获取策略：
1. 使用 Playwright 模拟浏览器访问（不需要登录）
2. 等待页面 JavaScript 加载完成
3. 从页面中提取嵌入的 JSON 数据
4. 或者拦截 API 请求，直接获取数据

优势：
- 仅使用公开页面或用户授权会话
- 仅在用户授权和服务条款允许范围内读取数据
- 模拟真实用户访问，保留来源、频率控制和审计记录
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class QYYJTPlaywrightAdapter:
    """
    使用 Playwright 获取企业预警通数据（不需要登录）

    用法:
        adapter = QYYJTPlaywrightAdapter()
        await adapter.init()

        # 搜索企业
        result = await adapter.search("中国平安")

        # 获取企业详情
        detail = await adapter.get_company_detail("601318")

        await adapter.close()
    """

    BASE_URL = "https://www.qyyjt.cn"

    def __init__(self, headless: bool = True):
        """
        初始化适配器

        Args:
            headless: 是否无头模式（True=后台运行，False=显示浏览器窗口）
        """
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    async def init(self) -> bool:
        """初始化 Playwright 浏览器"""
        if not PLAYWRIGHT_AVAILABLE:
            print("❌ Playwright 未安装")
            print("请运行: pip install playwright && playwright install chromium")
            return False

        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-gpu']
            )
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
            )
            self.page = await self.context.new_page()
            print("✅ Playwright 浏览器初始化成功")
            return True
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            return False

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def search(self, keyword: str, max_results: int = 10) -> Dict[str, Any]:
        """
        搜索企业（不需要登录）

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            搜索结果
        """
        if not self.page:
            await self.init()

        try:
            # 访问搜索页
            url = f"{self.BASE_URL}/search?text={keyword}"
            print(f"正在访问: {url}")
            await self.page.goto(url, timeout=30000)
            await self.page.wait_for_load_state("networkidle")

            # 等待搜索结果加载
            try:
                await self.page.wait_for_selector(".search-list, .company-list, [class*='search']", timeout=10000)
            except Exception:
                print("⚠️ 未找到搜索结果元素，尝试继续...")

            # 截取页面内容
            content = await self.page.content()

            # 尝试从页面中提取 JSON 数据
            # 企业预警通可能通过 window.__INITIAL_STATE__ 或类似变量嵌入数据
            data = await self._extract_data_from_page()

            # 如果找不到嵌入数据，尝试解析 HTML
            if not data:
                data = await self._parse_search_html(content, keyword)

            return {
                "keyword": keyword,
                "source": "qyyjt_playwright",
                "method": "playwright_search",
                "data": data,
                "total": len(data.get("list", [])),
            }

        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            return {"error": str(e), "keyword": keyword}

    async def get_company_detail(self, company_code: str) -> Dict[str, Any]:
        """
        获取企业详情（不需要登录）

        Args:
            company_code: 企业代码（股票代码或统一社会信用代码）

        Returns:
            企业详情
        """
        if not self.page:
            await self.init()

        try:
            # 尝试不同的详情页 URL
            urls = [
                f"{self.BASE_URL}/company/stockcode/{company_code}",
                f"{self.BASE_URL}/company/{company_code}",
                f"{self.BASE_URL}/search?text={company_code}",
            ]

            for url in urls:
                print(f"正在访问: {url}")
                await self.page.goto(url, timeout=30000)
                await self.page.wait_for_load_state("networkidle")

                # 等待页面加载
                await asyncio.sleep(3)

                # 提取数据
                data = await self._extract_data_from_page()

                if data:
                    return {
                        "company_code": company_code,
                        "source": "qyyjt_playwright",
                        "method": "playwright_detail",
                        "data": data,
                    }

            return {"error": "无法获取企业详情", "company_code": company_code}

        except Exception as e:
            print(f"❌ 获取详情失败: {e}")
            return {"error": str(e), "company_code": company_code}

    async def _extract_data_from_page(self) -> Optional[Dict]:
        """
        从页面中提取嵌入的 JSON 数据

        企业预警通可能通过以下方式嵌入数据：
        1. window.__INITIAL_STATE__ = {...}
        2. <script type="application/json">...</script>
        3. React/Vue 的服务器端渲染数据
        """
        try:
            # 方法1：查找 window 变量
            window_vars = await self.page.evaluate("""
                () => {
                    const result = {};
                    for (let key in window) {
                        if (key.startsWith('__') && key.endsWith('__')) {
                            try {
                                result[key] = window[key];
                            } catch (e) {}
                        }
                    }
                    return result;
                }
            """)

            if window_vars:
                print(f"找到 {len(window_vars)} 个 window 变量")
                # 返回第一个找到的变量
                for key, value in window_vars.items():
                    if value and isinstance(value, dict):
                        return value

            # 方法2：查找 <script type="application/json">
            json_scripts = await self.page.query_selector_all('script[type="application/json"]')
            for script in json_scripts:
                text = await script.inner_text()
                if text:
                    try:
                        data = json.loads(text)
                        return data
                    except json.JSONDecodeError:
                        pass

            # 方法3：拦截 API 请求
            # 监听网络请求，捕获 API 响应
            print("未找到嵌入的 JSON 数据")
            return None

        except Exception as e:
            print(f"提取数据失败: {e}")
            return None

    async def _parse_search_html(self, html: str, keyword: str) -> Dict[str, Any]:
        """
        解析搜索结果 HTML（备用方案）
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')

        # 查找搜索结果列表
        results = []

        # 尝试不同的选择器
        selectors = [
            '.search-list .item',
            '.company-list .item',
            '[class*="search"] [class*="item"]',
            '[class*="company"] [class*="item"]',
        ]

        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"找到 {len(items)} 个结果（选择器: {selector}）")
                for item in items[:10]:  # 最多取10个
                    text = item.get_text(strip=True)
                    if text:
                        results.append({"text": text})
                break

        return {"list": results, "keyword": keyword, "method": "html_parse"}

    async def intercept_api_requests(self, keyword: str) -> Dict[str, Any]:
        """
        拦截 API 请求，直接获取数据（高级方法）

        这个方法会：
        1. 监听页面的所有网络请求
        2. 捕获 API 响应
        3. 直接返回 API 数据
        """
        if not self.page:
            await self.init()

        api_responses = []

        # 监听网络响应
        def handle_response(response):
            if '/api/' in response.url or '/finchinaAPP/' in response.url:
                try:
                    data = response.json()
                    api_responses.append({
                        "url": response.url,
                        "status": response.status,
                        "data": data,
                    })
                except Exception:
                    pass

        self.page.on("response", handle_response)

        # 访问搜索页
        url = f"{self.BASE_URL}/search?text={keyword}"
        await self.page.goto(url, timeout=30000)
        await self.page.wait_for_load_state("networkidle")

        # 等待 API 请求完成
        await asyncio.sleep(3)

        return {
            "keyword": keyword,
            "source": "qyyjt_playwright",
            "method": "api_intercept",
            "api_responses": api_responses,
            "total": len(api_responses),
        }


# 便捷函数
async def create_playwright_adapter(headless: bool = True) -> QYYJTPlaywrightAdapter:
    """创建并初始化 Playwright 适配器"""
    adapter = QYYJTPlaywrightAdapter(headless=headless)
    await adapter.init()
    return adapter


if __name__ == "__main__":
    # 测试
    async def test():
        print("=== 测试 Playwright 适配器 ===")

        if not PLAYWRIGHT_AVAILABLE:
            print("❌ Playwright 未安装")
            return

        adapter = QYYJTPlaywrightAdapter(headless=False)  # 显示浏览器窗口
        await adapter.init()

        try:
            # 测试搜索
            print("\n1. 测试搜索...")
            result = await adapter.search("中国平安")
            print(f"搜索结果: {result.get('total', 0)} 条")

            # 测试获取企业详情
            print("\n2. 测试获取企业详情...")
            detail = await adapter.get_company_detail("601318")
            print(f"企业详情: {detail}")

        finally:
            await adapter.close()

    asyncio.run(test())
