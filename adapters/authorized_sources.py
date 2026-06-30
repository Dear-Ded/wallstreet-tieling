"""
已授权数据源的运行时适配器 — 通过用户授权网关执行查询。
所有查询必须先通过 UserAuthorizationGate.is_authorized() 检查。
默认安全(disabled) → 用户显式授权(enabled) → 可审计调用。
"""

from __future__ import annotations
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import json
import urllib.request
import urllib.parse
import time
import hashlib


class AuthorizedCompaniesHouseLookup:
    """
    英国公司注册处公开API查询(需用户注册的免费API Key)。
    用户注册: https://developer.company-information.service.gov.uk/
    获取免费API Key → 通过授权网关启用此数据源 → 开始查询。
    """

    def __init__(self, auth_gate: UserAuthorizationGate, api_key: str = ""):
        self._gate = auth_gate
        self._api_key = api_key
        self._source_key = "companies_house"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="UK Companies House — Official Company Registry",
            source_type="public_api",
            default_config={"base_url": "https://api.company-information.service.gov.uk", "rate_limit_rpm": 120},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key) and bool(self._api_key)

    def enable(self, api_key: str = "", duration_hours: int = 168) -> dict:
        """用户授权启用: 提供免费API Key即可"""
        if api_key:
            self._api_key = api_key
        record = self._gate.enable_source(self._source_key, {"api_key_provided": bool(self._api_key)}, duration_hours)
        return record.to_dict()

    def search_company(self, company_name: str) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized", "message": "用户需先注册Companies House免费API Key并通过授权网关启用此数据源"}

        target_hash = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://api.company-information.service.gov.uk/search/companies?q={urllib.parse.quote(company_name)}&items_per_page=10"

        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Basic {self._api_key}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                items = data.get("items", [])
                self._gate.log_access(self._source_key, "company_search", target_hash, f"found_{len(items)}")
                return {
                    "query_subject_hash": target_hash,
                    "source": "companies_house_uk",
                    "authorized": True,
                    "total_results": data.get("total_results", 0),
                    "companies_found": len(items),
                    "sample": [
                        {"name": c.get("title", ""), "number": c.get("company_number", ""),
                         "status": c.get("company_status", ""), "address": c.get("address", {}).get("locality", "")}
                        for c in items[:5]
                    ],
                }
        except Exception as e:
            self._gate.log_access(self._source_key, "company_search", target_hash, f"error_{type(e).__name__}")
            return {"error": str(e), "authorized": True}


class AuthorizedSECEdgarLookup:
    """
    美国SEC EDGAR公开数据查询(无需API Key, 但需通过授权网关显式启用)。
    该数据源无凭证要求, 但遵循项目'默认安全'原则 — 用户必须显式授权。
    """

    def __init__(self, auth_gate: UserAuthorizationGate):
        self._gate = auth_gate
        self._source_key = "sec_edgar_full"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="US SEC EDGAR — Public Company Filings Database",
            source_type="public_api",
            default_config={"rate_limit_rps": 8, "user_agent_required": True},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, duration_hours: int = 168) -> dict:
        record = self._gate.enable_source(self._source_key, duration_hours=duration_hours)
        return record.to_dict()

    def lookup_company_by_ticker(self, ticker: str) -> dict[str, Any]:
        """通过股票代码查找CIK编号"""
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(ticker.encode()).hexdigest()[:12]
        try:
            req = urllib.request.Request(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": "EnterpriseDueDiligence/1.0 (compliance@example.com)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for entry in data.values():
                    if entry.get("ticker", "").upper() == ticker.upper():
                        self._gate.log_access(self._source_key, "ticker_lookup", target_hash, "found")
                        return {
                            "query_subject_hash": target_hash,
                            "source": "sec_edgar",
                            "authorized": True,
                            "cik": str(entry["cik_str"]).zfill(10),
                            "ticker": entry["ticker"],
                            "company_name": entry["title"],
                        }
                self._gate.log_access(self._source_key, "ticker_lookup", target_hash, "not_found")
                return {"error": "ticker_not_found", "authorized": True}
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def get_filing_history(self, cik: str) -> dict[str, Any]:
        """获取公司的SEC申报历史"""
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(cik.encode()).hexdigest()[:12]
        try:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "EnterpriseDueDiligence/1.0 (compliance@example.com)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                form_counts = {}
                for f in forms:
                    form_counts[f] = form_counts.get(f, 0) + 1
                self._gate.log_access(self._source_key, "filing_history", target_hash, f"found_{len(forms)}")
                return {
                    "query_subject_hash": target_hash,
                    "source": "sec_edgar",
                    "authorized": True,
                    "cik": cik,
                    "company_name": data.get("name", ""),
                    "total_recent_filings": len(forms),
                    "filing_types": dict(sorted(form_counts.items(), key=lambda x: -x[1])[:10]),
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}


class AuthorizedOpenSanctionsLookup:
    """
    OpenSanctions公开制裁与合规名单查询(非商业用途免费API Key)。
    用户注册: https://www.opensanctions.org/
    """

    def __init__(self, auth_gate: UserAuthorizationGate, api_key: str = ""):
        self._gate = auth_gate
        self._api_key = api_key
        self._source_key = "opensanctions"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="OpenSanctions — Global Sanctions & Compliance Database",
            source_type="public_api",
            default_config={"base_url": "https://api.opensanctions.org", "non_commercial_use_only": True},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key) and bool(self._api_key)

    def enable(self, api_key: str = "", duration_hours: int = 168) -> dict:
        if api_key:
            self._api_key = api_key
        return self._gate.enable_source(self._source_key, {"api_key_provided": bool(self._api_key)}, duration_hours).to_dict()

    def search_entity(self, entity_name: str) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(entity_name.encode()).hexdigest()[:12]
        url = f"https://api.opensanctions.org/search/default?q={urllib.parse.quote(entity_name)}&limit=10"

        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"ApiKey {self._api_key}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                self._gate.log_access(self._source_key, "entity_search", target_hash, f"found_{len(results)}")
                return {
                    "query_subject_hash": target_hash,
                    "source": "opensanctions",
                    "authorized": True,
                    "total_results": data.get("total", {}).get("value", 0),
                    "matches": len(results),
                    "sample": [
                        {"name": r.get("caption", ""), "schema": r.get("schema", ""),
                         "countries": r.get("properties", {}).get("country", [])}
                        for r in results[:5]
                    ],
                    "compliance_note": "CC BY-NC 4.0 — 仅限非商业尽调使用",
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}
