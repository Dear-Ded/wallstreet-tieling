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

    def health_check(self) -> dict[str, Any]:
        return {
            "source": "runtime_visual_challenge_solver",
            "ok": True,
            "mode": "schema_contract",
            "requires_authorization": True,
            "requires_runtime_dependency": "ddddocr",
            "default_enabled": False,
            "output_contract": [
                "engine",
                "access_path",
                "fields",
                "source_url",
                "entity_match",
                "evidence",
            ],
            "report_gate": "OCR-assisted public-query output remains lead-only until official page provenance and exact/strong subject match pass",
        }

    def standardize_result(self, subject: str, result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"health": self.health_check(), "standardized_records": [], "raw": result}
        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        source = str(result.get("source") or "gsxt.gov.cn")
        record = {
            "source_name": "runtime_visual_challenge_solver",
            "source_type": self.source_type,
            "source_hint": "runtime_visual_challenge_solver",
            "record_type": "ocr_assisted_public_registry_query_lead",
            "entity": subject.strip(),
            "title": f"OCR-assisted public registry query lead: {subject.strip()}",
            "summary": (
                f"source={source}; engine={result.get('engine') or fields.get('ocr_engine') or 'ddddocr'}; "
                f"field_count={result.get('field_count', len(fields))}"
            ),
            "url": "https://www.gsxt.gov.cn/",
            "confidence": 0.56,
            "entity_match": {
                "level": "review",
                "score": 0.56,
                "method": "ocr_assisted_query_requires_official_result_identity_fields",
                "identifiers": {"subject": subject.strip(), "query_subject_hash": result.get("query_subject_hash", "")},
            },
            "entities": [
                {
                    "kind": "company",
                    "name": subject.strip(),
                    "relation": "ocr_assisted_registry_query_subject",
                    "confidence": 0.56,
                    "source": source,
                }
            ],
            "evidence": [
                {
                    "type": "ocr_assisted_public_query",
                    "provider": source,
                    "source_url": "https://www.gsxt.gov.cn/",
                    "engine": result.get("engine") or fields.get("ocr_engine") or "ddddocr",
                    "access_path": result.get("access_path", ""),
                    "entity_match_level": "review",
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"health": self.health_check(), "standardized_records": [record], "raw": result}

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
    def health_check(self) -> dict[str, Any]:
        return {
            "source": "runtime_username_cross_platform_verifier",
            "ok": True,
            "mode": "schema_contract",
            "requires_authorization": True,
            "optional_runtime_dependency": "maigret",
            "default_enabled": False,
            "output_contract": [
                "engine",
                "platforms_found",
                "platforms",
                "entity_match",
                "evidence",
            ],
            "report_gate": "username matches remain lead-only until person context, false-positive review, and exact/strong identity match pass",
        }

    def standardize_result(self, username: str, result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"health": self.health_check(), "standardized_records": [], "raw": result}
        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        platforms = [str(item) for item in fields.get("platforms", []) if str(item).strip()]
        found = int(fields.get("platforms_found") or len(platforms))
        confidence = min(0.82, 0.45 + found * 0.05)
        clean_username = username.strip().lstrip("@")
        record = {
            "source_name": "runtime_username_cross_platform_verifier",
            "source_type": self.source_type,
            "source_hint": "runtime_username_cross_platform_verifier",
            "record_type": "runtime_cross_platform_username_lead",
            "entity": clean_username,
            "title": f"Runtime cross-platform username lead: {clean_username}",
            "summary": f"engine={result.get('engine', '')}; platforms_found={found}",
            "url": "",
            "confidence": confidence,
            "entity_match": {
                "level": "review",
                "score": confidence,
                "method": "runtime_username_presence_requires_person_context",
                "identifiers": {"username": clean_username, "platform_count": found},
            },
            "entities": [
                {
                    "kind": "person_or_account",
                    "name": clean_username,
                    "relation": "runtime_cross_platform_profile_candidate",
                    "confidence": confidence,
                    "source": result.get("engine", "cross_platform_runtime"),
                }
            ],
            "evidence": [
                {
                    "type": "runtime_cross_platform_username_presence",
                    "provider": str(platform),
                    "source_url": self._platform_url(platform, clean_username),
                    "engine": result.get("engine", ""),
                    "username": clean_username,
                    "entity_match_level": "review",
                    "manual_review_required": True,
                }
                for platform in platforms[:30]
            ],
            "raw": result,
        }
        return {"health": self.health_check(), "standardized_records": [record], "raw": result}

    @staticmethod
    def _platform_url(platform: str, username: str) -> str:
        if platform == "ycombinator-news":
            return f"https://news.ycombinator.com/user?id={urllib.parse.quote(username)}"
        return f"https://{platform}.com/{urllib.parse.quote(username)}"


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

    def health_check(self) -> dict[str, Any]:
        return {
            "source": "runtime_aiqicha_session_lookup",
            "ok": True,
            "mode": "schema_contract",
            "requires_authorization": True,
            "requires_user_session": True,
            "default_enabled": False,
            "output_contract": [
                "legal_person",
                "registered_capital",
                "establishment_date",
                "uscc",
                "entity_match",
                "evidence",
            ],
            "report_gate": "Aiqicha session results remain lead-only until user session authorization, official-source provenance, and exact/strong entity match pass",
        }

    def standardize_result(self, company_name: str, result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"health": self.health_check(), "standardized_records": [], "raw": result}
        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        clean_company = company_name.strip()
        uscc = str(fields.get("uscc") or "").strip()
        source_url = f"https://aiqicha.baidu.com/s?q={urllib.parse.quote(clean_company)}"
        record = {
            "source_name": "runtime_aiqicha_session_lookup",
            "source_type": self.source_type,
            "source_hint": "runtime_aiqicha_session_lookup",
            "record_type": "runtime_aiqicha_enterprise_registry_lead",
            "entity": clean_company,
            "title": f"Aiqicha session enterprise registry lead: {clean_company}",
            "summary": "; ".join(
                part
                for part in (
                    f"legal_person={fields.get('legal_person')}" if fields.get("legal_person") else "",
                    f"registered_capital={fields.get('registered_capital')}" if fields.get("registered_capital") else "",
                    f"establishment_date={fields.get('establishment_date')}" if fields.get("establishment_date") else "",
                    f"uscc={uscc}" if uscc else "",
                )
                if part
            ),
            "url": source_url,
            "confidence": 0.68 if uscc else 0.58,
            "registration_authority": "Aiqicha/Baidu aggregated public registry",
            "entity_match": {
                "level": "strong" if uscc else "review",
                "score": 0.86 if uscc else 0.58,
                "method": "queried_company_to_aiqicha_visible_registry_fields",
                "identifiers": {
                    "company_name": clean_company,
                    "unified_social_credit_code": uscc,
                    "query_subject_hash": result.get("query_subject_hash", ""),
                },
            },
            "entities": [
                {
                    "kind": "company",
                    "name": clean_company,
                    "relation": "queried_subject",
                    "confidence": 0.68 if uscc else 0.58,
                    "source": "Aiqicha",
                    "unified_social_credit_code": uscc,
                }
            ],
            "evidence": [
                {
                    "type": "user_authorized_commercial_registry_session_lookup",
                    "provider": "Aiqicha/Baidu",
                    "source_url": source_url,
                    "field_keys": sorted(fields.keys()),
                    "requires_user_session": True,
                    "entity_match_level": "strong" if uscc else "review",
                    "manual_review_required": True,
                }
            ],
            "raw": fields,
        }
        return {"health": self.health_check(), "standardized_records": [record], "raw": result}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}
