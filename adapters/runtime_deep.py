"""
企业尽调深度采集运行时适配器 — 真实第三方库集成。
安装依赖后即用: pip install ddddocr maigret telethon beautifulsoup4 lxml。
所有适配器门控,默认禁用。
"""

from __future__ import annotations
from adapters.safe_research_adapter import SafeResearchAdapter
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import json, urllib.request, urllib.parse, time, hashlib, re, os, base64


# ================================================================
# ddddocr 光学字符识别 — 真实集成
# ================================================================
class VisualChallengeSolver(SafeResearchAdapter):
    """使用ddddocr(5k★ GitHub)进行政府网站字符序列识别。真实运行时适配器。"""

    source_domain = "government_public_query"
    source_type = "enterprise_ocr_assisted_public_query"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True
    min_request_interval = 3.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "visual_challenge_solver"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="光学字符识别辅助查询",
            source_type="public_ocr_assisted_public_query",
            default_config={"investigation_lane": "money", "ocr_engine": "ddddocr"})
        self._ocr = None
        try:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        except ImportError:
            pass

    def is_available(self) -> bool:
        if not self._gate.is_authorized(self._source_key): return False
        if self._ocr is None: return False
        return True

    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def solve_image(self, image_bytes: bytes) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized" if not self._gate.is_authorized(self._source_key) else "ocr_engine_not_available"}
        try:
            result = self._ocr.classification(image_bytes)
            self._gate.log_access(self._source_key, "ocr_solve", hashlib.sha256(image_bytes).hexdigest()[:12], f"len_{len(result)}")
            return {"result": result, "engine": "ddddocr", "authorized": True, "response_status": 200}
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def query_gsxt(self, company_name: str) -> dict[str, Any]:
        """完整的GSXT查询流程: 获取验证图片→OCR识别→提交查询→解析结果"""
        if not self.is_available():
            return {"error": "source_not_authorized" if not self._gate.is_authorized(self._source_key) else "ocr_engine_not_available"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]

        try:
            # Step 1: GET GSXT搜索页 → 提取token + captcha URL
            sess = urllib.request
            req1 = sess.Request("http://www.gsxt.gov.cn/corp-query-search-1.html",
                headers={"User-Agent": "Mozilla/5.0 (compatible; DueDiligence/1.0)"})
            with sess.urlopen(req1, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                token_match = re.search(r'name="token"[^>]*value="([^"]+)"', html)
                captcha_match = re.search(r'<img[^>]*id="captcha"[^>]*src="([^"]+)"', html)
                if not token_match:
                    return {"error": "token_not_found", "authorized": True}
                token = token_match.group(1)

            # Step 2: 下载验证图片 → OCR识别
            if captcha_match:
                captcha_url = captcha_match.group(1)
                if not captcha_url.startswith("http"):
                    captcha_url = "http://www.gsxt.gov.cn" + captcha_url
                req2 = sess.Request(captcha_url, headers={"User-Agent": "Mozilla/5.0"})
                with sess.urlopen(req2, timeout=10) as resp2:
                    img_bytes = resp2.read()
                captcha_result = self._ocr.classification(img_bytes)
            else:
                captcha_result = ""

            # Step 3: POST查询
            import urllib.parse as up
            data = up.urlencode({"searchword": company_name, "captcha": captcha_result, "token": token}).encode()
            req3 = sess.Request("http://www.gsxt.gov.cn/corp-query-search-1.html", data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
            with sess.urlopen(req3, timeout=15) as resp3:
                result_html = resp3.read().decode("utf-8", errors="replace")

            # Step 4: 解析结果
            result_count = len(re.findall(r'<a[^>]*corp-query-entprise-info[^>]*>([^<]+)</a>', result_html))
            self._gate.log_access(self._source_key, "gsxt_full_query", target, f"results_{result_count}")
            return {"query_subject_hash": target, "source": "gsxt.gov.cn", "authorized": True,
                    "access_path": "gsxt_ocr_full_chain", "investigation_lane": "money",
                    "fields": {"gsxt_results_found": result_count, "ocr_engine": "ddddocr"},
                    "field_count": 1, "response_status": 200}

        except Exception as e:
            self._gate.log_access(self._source_key, "gsxt_query_error", target, type(e).__name__)
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# Maigret/Sherlock 用户名跨平台验证 — 真实集成
# ================================================================
class UsernameCrossPlatformVerifier(SafeResearchAdapter):
    """使用Maigret(34k★)/Sherlock(85k★)进行跨平台公开身份验证。真实运行时适配器。"""

    source_domain = "public_social_platforms"
    source_type = "enterprise_executive_cross_platform_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 10.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "username_verifier"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="跨平台公开身份验证",
            source_type="public_cross_platform_identity",
            default_config={"investigation_lane": "people", "compliance": "FATF CDD"})
        self._has_maigret = False
        try:
            import maigret
            self._has_maigret = True
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def verify_username(self, username: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(username.encode()).hexdigest()[:12]

        if self._has_maigret:
            try:
                import maigret
                import asyncio
                async def search():
                    return await maigret.search(username=username)
                result = asyncio.run(search())
                platforms = list(result.keys()) if result else []
                self._gate.log_access(self._source_key, "maigret_search", target, f"platforms_{len(platforms)}")
                return {"query_subject_hash": target, "authorized": True, "engine": "maigret",
                        "investigation_lane": "people", "investigation_purpose": "企业高管公开跨平台身份验证",
                        "fields": {"platforms_found": len(platforms), "platforms": platforms[:20]},
                        "field_count": 2, "response_status": 200}
            except Exception as e:
                self._gate.log_access(self._source_key, "maigret_error", target, type(e).__name__)
                return {"error": str(e), "authorized": True, "engine": "maigret"}

        # 回退: 手动HTTP验证
        platforms = ["github", "gitlab", "keybase", "medium", "dev.to", "producthunt", "ycombinator-news"]
        found = []
        for platform in platforms:
            try:
                url = f"https://{platform}.com/{username}" if platform != "ycombinator-news" else f"https://news.ycombinator.com/user?id={username}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DueDiligence/1.0)"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        found.append(platform)
            except Exception: pass
            time.sleep(1.0)

        self._gate.log_access(self._source_key, "manual_platform_check", target, f"found_{len(found)}")
        return {"query_subject_hash": target, "authorized": True, "engine": "manual_http",
                "investigation_lane": "people", "investigation_purpose": "企业高管跨平台公开身份验证",
                "fields": {"platforms_found": len(found), "platforms": found},
                "field_count": 2, "response_status": 200}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 爱企查cookie会话持久化 — 真实集成
# ================================================================
class AiqichaSessionLookup(SafeResearchAdapter):
    """使用ENScan_GO(4.5k★)或直接HTTP+BeautifulSoup查询爱企查。真实运行时适配器。"""

    source_domain = "aiqicha_baidu"
    source_type = "enterprise_baidu_public_registry"
    data_boundary = "user_authorized"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "aiqicha_session"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="爱企查会话查询",
            source_type="public_baidu_enterprise_lookup",
            default_config={"investigation_lane": "money", "auth_method": "cookie_session_persistence",
                           "platform_url": "https://aiqicha.baidu.com"})
        self._has_bs4 = False
        try:
            import bs4
            self._has_bs4 = True
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_company(self, company_name: str, cookie_str: str = "") -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if cookie_str:
            headers["Cookie"] = cookie_str

        try:
            url = f"https://aiqicha.baidu.com/s?q={urllib.parse.quote(company_name)}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            fields = {}
            patterns = [
                ("legal_person", r'法定代表人[：:]\s*(\S+)'),
                ("registered_capital", r'注册资本[：:]\s*(\S+)'),
                ("establishment_date", r'成立日期[：:]\s*(\S+)'),
                ("uscc", r'统一社会信用代码[：:]\s*(\S+)'),
            ]
            for key, pattern in patterns:
                m = re.search(pattern, html)
                if m: fields[key] = m.group(1)

            self._gate.log_access(self._source_key, "aiqicha_query", target, f"fields_{len(fields)}")
            return {"query_subject_hash": target, "source": "aiqicha.baidu.com", "authorized": True,
                    "investigation_lane": "money", "investigation_purpose": "企业工商注册公开信息查询 — 爱企查(百度)",
                    "fields": fields, "field_count": len(fields),
                    "note": "从GSXT等官方源聚合的公开工商信息。cookie由用户自行从浏览器中获取",
                    "response_status": 200}
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}
