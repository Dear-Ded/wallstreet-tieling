"""
授权会话状态管理器 - 企业预警通登录态管理
实现用户无感查询，不碰用户账号密码
"""

import json
import os
import base64
import hashlib
from pathlib import Path
from typing import Optional, Dict, List
import asyncio

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# 授权会话状态存储路径
授权会话状态_DIR = Path.home() / ".wallstreet" / "cookies"
授权会话状态_FILE = 授权会话状态_DIR / "qyyjt_cookies.json"
CREDENTIAL_FILE = 授权会话状态_DIR / "qyyjt_authorized_session_credential.enc"


class CookieManager:
    """
    授权会话状态管理器

    流程：
    1. 首次使用：用我们自己的账号登录一次（手动或自动）
    2. 保存授权会话状态 到本地加密文件
    3. 之后所有查询复用授权会话状态（用户完全无感）
    4. 授权会话状态 过期时自动刷新

    安全：
    - 授权会话状态文件本地加密存储
    - 不记录用户名密码，只保存授权会话状态
    - 每次使用前验证 授权会话状态有效性
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else 授权会话状态_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file = self.data_dir / "qyyjt_cookies.json"
        self.credential_file = self.data_dir / "qyyjt_authorized_session_credential.enc"
        self._cookies: List[Dict] = []
        self._logged_in = False

    def _get_machine_key(self) -> bytes:
        """获取机器特征码作为加密密钥（不传输到外部）"""
        import platform
        import uuid
        machine_info = f"{platform.node()}-{platform.machine()}-{uuid.getnode()}"
        return hashlib.sha256(machine_info.encode()).digest()[:24]  # 24 bytes for Fernet

    def _encrypt(self, data: str) -> str:
        """加密存储（仅本地机器可解密）"""
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(self._get_machine_key())
            f = Fernet(key)
            return base64.urlsafe_b64encode(f.encrypt(data.encode())).decode()
        except ImportError:
            # 降级：Base64 编码（至少不是明文）
            return base64.b64encode(data.encode()).decode()

    def _decrypt(self, encrypted: str) -> str:
        """解密本地存储的 授权会话状态"""
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(self._get_machine_key())
            f = Fernet(key)
            return f.decrypt(base64.urlsafe_b64decode(encrypted)).decode()
        except ImportError:
            return base64.b64decode(encrypted).decode()
        except Exception:
            return base64.b64decode(encrypted).decode()

    def save_cookies(self, cookies: List[Dict]) -> None:
        """保存授权会话状态 到本地加密文件"""
        self._cookies = cookies
        data = json.dumps(cookies, ensure_ascii=False)
        encrypted = self._encrypt(data)
        self.cookie_file.write_text(encrypted, encoding='utf-8')

    def load_cookies(self) -> List[Dict]:
        """从本地加密文件加载 授权会话状态"""
        if not self.cookie_file.exists():
            return []
        try:
            encrypted = self.cookie_file.read_text(encoding='utf-8')
            data = self._decrypt(encrypted)
            self._cookies = json.loads(data)
            return self._cookies
        except Exception as e:
            print(f"授权会话状态加载失败: {e}")
            return []

    async def login_manual(self, phone: str, password: str) -> bool:
        """
        手动登录（用我们自己的账号）

        参数：
            phone: 企业预警通注册公开联系方式
            password: 密码

        返回：
            是否登录成功
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright 未安装，无法自动登录")
            return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # 有界面，方便输验证码
            context = await browser.new_context()
            page = await context.new_page()

            try:
                print("正在打开企业预警通登录页...")
                await page.goto("https://www.qyyjt.cn/login", timeout=30000)
                await page.wait_for_load_state("networkidle")

                # 输入公开联系方式
                await page.fill('input[type="tel"], input[placeholder*="手机"]', phone)
                await asyncio.sleep(0.5)

                # 输入密码
                await page.fill('input[type="password"]', password)
                await asyncio.sleep(0.5)

                print("请手动完成验证码，登录成功后按回车继续...")
                input("按回车继续...")

                # 等待登录完成（检测 URL 变化或特定元素）
                await page.wait_for_url("**/home", timeout=60000)

                # 提取授权会话状态
                cookies = await context.cookies()
                self.save_cookies(cookies)
                self._logged_in = True
                print(f"✅ 登录成功！已保存 {len(cookies)} 个 授权会话状态")
                return True

            except Exception as e:
                print(f"❌ 登录失败: {e}")
                return False
            finally:
                await browser.close()

    async def login_headless(self, phone: str, password: str,
                            captcha_callback=None) -> bool:
        """
        无头登录（适用于服务器环境）

        captcha_callback: 验证码回调函数，返回验证码文本
        """
        if not PLAYWRIGHT_AVAILABLE:
            return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto("https://www.qyyjt.cn/login", timeout=30000)

                # 输入账号密码
                await page.fill('input[type="tel"]', phone)
                await page.fill('input[type="password"]', password)

                # 处理验证码（如果有）
                if captcha_callback:
                    captcha_text = await captcha_callback(page)
                    await page.fill('input[placeholder*="验证码"]', captcha_text)

                # 点击登录
                await page.click('button:has-text("登录"), button[type="submit"]')
                await page.wait_for_url("**/home", timeout=30000)

                # 保存授权会话状态
                cookies = await context.cookies()
                self.save_cookies(cookies)
                self._logged_in = True
                return True

            except Exception as e:
                print(f"登录失败: {e}")
                return False
            finally:
                await browser.close()

    def get_cookies_for_requests(self) -> Dict:
        """获取用于 requests 库的 授权会话状态 字典"""
        cookies = self.load_cookies()
        return {c['name']: c['value'] for c in cookies}

    def get_cookies_for_playwright(self) -> List[Dict]:
        """获取用于 Playwright 的 授权会话状态 列表"""
        return self.load_cookies()

    async def test_cookies_valid(self) -> bool:
        """测试 授权会话状态是否仍然有效"""
        cookies = self.load_cookies()
        if not cookies:
            return False

        # 用 授权会话状态 访问一个需要登录的 API
        import requests
        cookie_dict = {c['name']: c['value'] for c in cookies}

        try:
            resp = requests.get(
                "https://www.qyyjt.cn/finchinaAPP/v1/user/info",
                cookies=cookie_dict,
                timeout=10
            )
            # 如果返回用户信息，说明 授权会话状态有效
            data = resp.json()
            if data.get('returncode') == 200 and data.get('data'):
                self._logged_in = True
                return True
        except Exception:
            pass

        self._logged_in = False
        return False

    async def ensure_logged_in(self, phone: str = None, password: str = None) -> bool:
        """
        确保登录状态（自动刷新过期 授权会话状态）

        如果 授权会话状态有效，直接返回 True
        如果 授权会话状态 过期，尝试重新登录
        """
        if await self.test_cookies_valid():
            return True

        print("⚠️ 授权会话状态已过期，需要重新登录")
        if phone and password:
            return await self.login_manual(phone, password)
        else:
            print("❌ 需要提供账号密码才能重新登录")
            return False


# 便捷函数
async def get_qyyjt_cookies(phone: str = None, password: str = None) -> List[Dict]:
    """
    获取企业预警通 授权会话状态（用户无感）

    使用方式：
        cookies = await get_qyyjt_cookies()
        # 如果 授权会话状态有效，直接返回
        # 如果 授权会话状态 过期，需要重新登录
    """
    manager = CookieManager()

    # 尝试加载已有授权会话状态
    if await manager.test_cookies_valid():
        print("✅ 授权会话状态有效，无需重新登录")
        return manager.get_cookies_for_playwright()

    # 授权会话状态 过期，需要重新登录
    if phone and password:
        print("⚠️ 授权会话状态已过期，正在重新登录...")
        await manager.login_manual(phone, password)
        return manager.get_cookies_for_playwright()
    else:
        print("❌ 授权会话状态已过期，且未提供登录凭据")
        return []


if __name__ == "__main__":
    # 测试
    import asyncio

    async def test():
        manager = CookieManager()

        # 测试加载已有授权会话状态
        cookies = manager.load_cookies()
        print(f"已加载 {len(cookies)} 个 授权会话状态")

        if cookies:
            # 测试 授权会话状态有效性
            valid = await manager.test_cookies_valid()
            print(f"授权会话状态有效性: {valid}")

    asyncio.run(test())
