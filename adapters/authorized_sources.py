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

    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": "authorized_companies_house_api",
            "default_enabled": False,
            "requires_user_authorization": True,
            "requires_api_key": True,
            "standardized_records": True,
            "record_type": "companies_house_company_search_result",
            "required_fields": ["company_name", "company_number", "company_status", "source_url"],
            "fact_gate": "explicit user authorization plus exact/strong company-name or company-number match before report-fact reliance",
        }

    def standardize_search_result(self, company_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized Companies House search response into registry lead records."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}

        records: list[dict[str, Any]] = []
        for item in result.get("sample") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            number = str(item.get("number") or "").strip()
            status = str(item.get("status") or "").strip()
            address = str(item.get("address") or "").strip()
            if not name and not number:
                continue
            source_url = (
                f"https://find-and-update.company-information.service.gov.uk/company/{urllib.parse.quote(number)}"
                if number
                else "https://find-and-update.company-information.service.gov.uk/"
            )
            match = self._company_match(company_name, name, {"company_number": number})
            records.append({
                "source_name": "authorized_companies_house_api",
                "source_type": "public_api",
                "source_hint": "authorized_companies_house_api",
                "record_type": "companies_house_company_search_result",
                "entity": name or company_name,
                "title": f"Companies House company registry lead: {name or number}",
                "summary": f"company_name={name}; company_number={number}; company_status={status}; address={address}",
                "url": source_url,
                "confidence": 0.78 if match["level"] in {"exact", "strong"} else 0.55,
                "registered_address": address,
                "jurisdiction": "GB",
                "entity_match": match,
                "evidence": [
                    {
                        "type": "authorized_official_company_registry_search",
                        "provider": "Companies House",
                        "company_number": number,
                        "company_status": status,
                        "source_url": source_url,
                        "manual_review_required": True,
                    }
                ],
                "raw": item,
            })
        return {"standardized_records": records, "raw": result}

    @staticmethod
    def _company_match(seed_name: str, candidate_name: str, identifiers: dict[str, Any] | None = None) -> dict[str, Any]:
        seed = " ".join(str(seed_name or "").casefold().split())
        candidate = " ".join(str(candidate_name or "").casefold().split())
        if seed and candidate and seed == candidate:
            level, score, method = "exact", 1.0, "normalized_company_name_exact"
        elif seed and candidate and (seed in candidate or candidate in seed):
            level, score, method = "strong", 0.9, "normalized_company_name_contains"
        else:
            level, score, method = "review", 0.55, "authorized_registry_search_candidate"
        return {
            "level": level,
            "score": score,
            "method": method,
            "identifiers": identifiers or {},
        }


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


    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": "authorized_sec_edgar_full_api",
            "default_enabled": False,
            "requires_user_authorization": True,
            "standardized_records": True,
            "record_types": ["sec_edgar_authorized_company_lookup", "sec_edgar_authorized_filing_history"],
            "required_fields": ["cik", "ticker_or_company_name", "source_url", "retrieved_at"],
            "fact_gate": "explicit user authorization plus CIK/ticker/company-name match before report-fact reliance",
        }

    def standardize_ticker_result(self, ticker: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized SEC ticker lookup into an issuer identity lead."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}
        cik = str(result.get("cik") or "").zfill(10) if result.get("cik") else ""
        company_name = str(result.get("company_name") or "").strip()
        ticker_value = str(result.get("ticker") or ticker or "").strip().upper()
        if not cik and not company_name:
            return {"standardized_records": [], "raw": result}
        source_url = f"https://data.sec.gov/submissions/CIK{cik}.json" if cik else "https://www.sec.gov/files/company_tickers.json"
        record = {
            "source_name": "authorized_sec_edgar_full_api",
            "source_type": "public_api",
            "source_hint": "authorized_sec_edgar_full_api",
            "record_type": "sec_edgar_authorized_company_lookup",
            "entity": company_name or ticker_value,
            "title": f"SEC EDGAR issuer identity lead: {company_name or ticker_value}",
            "summary": f"ticker={ticker_value}; cik={cik}; company_name={company_name}",
            "url": source_url,
            "confidence": 0.86 if cik else 0.62,
            "jurisdiction": "US",
            "entity_match": {
                "level": "exact" if ticker_value and str(ticker).upper() == ticker_value else "strong",
                "score": 0.96 if cik else 0.75,
                "method": "authorized_sec_ticker_to_cik",
                "identifiers": {"cik": cik, "ticker": ticker_value},
            },
            "evidence": [
                {
                    "type": "authorized_official_sec_issuer_lookup",
                    "provider": "SEC EDGAR",
                    "cik": cik,
                    "ticker": ticker_value,
                    "source_url": source_url,
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}

    def standardize_filing_history_result(self, cik: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized SEC filing-history response into capital-market disclosure leads."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}
        cik_value = str(result.get("cik") or cik or "").zfill(10)
        company_name = str(result.get("company_name") or "").strip()
        filing_types = result.get("filing_types") if isinstance(result.get("filing_types"), dict) else {}
        source_url = f"https://data.sec.gov/submissions/CIK{cik_value}.json"
        summary = (
            f"cik={cik_value}; company_name={company_name}; "
            f"total_recent_filings={result.get('total_recent_filings', 0)}; filing_types={filing_types}"
        )
        record = {
            "source_name": "authorized_sec_edgar_full_api",
            "source_type": "public_api",
            "source_hint": "authorized_sec_edgar_full_api",
            "record_type": "sec_edgar_authorized_filing_history",
            "entity": company_name or cik_value,
            "title": f"SEC EDGAR filing history lead: {company_name or cik_value}",
            "summary": summary,
            "url": source_url,
            "confidence": 0.82,
            "jurisdiction": "US",
            "risk_category": "financing_capital_markets",
            "entity_match": {
                "level": "strong",
                "score": 0.94,
                "method": "authorized_sec_cik_filing_history",
                "identifiers": {"cik": cik_value},
            },
            "evidence": [
                {
                    "type": "authorized_official_sec_filing_history",
                    "provider": "SEC EDGAR",
                    "cik": cik_value,
                    "filing_types": filing_types,
                    "source_url": source_url,
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}


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

    def health_check(self) -> dict[str, Any]:
        return {
            "source": "opensanctions",
            "ok": True,
            "mode": "schema_contract",
            "requires_authorization": True,
            "requires_api_key": True,
            "license": "CC BY-NC 4.0",
            "license_review": "non_commercial_or_authorized_use_required",
            "output_contract": [
                "total_results",
                "matches",
                "sample",
                "license",
                "entity_match",
                "evidence",
            ],
        }

    def standardize_result(self, entity_name: str, result: dict[str, Any]) -> dict[str, Any]:
        sample = result.get("sample") if isinstance(result, dict) else []
        sample = [item for item in sample if isinstance(item, dict)]
        clean_entity = entity_name.strip()
        records = []
        for item in sample[:10]:
            matched_name = str(item.get("name") or "").strip()
            match_level = "exact" if matched_name and matched_name.casefold() == clean_entity.casefold() else "review"
            records.append(
                {
                    "source_name": "authorized_opensanctions_api",
                    "source_type": "public_api",
                    "source_hint": "authorized_opensanctions_api",
                    "record_type": "authorized_watchlist_subject_match",
                    "entity": matched_name or clean_entity,
                    "title": f"OpenSanctions authorized match lead: {matched_name or clean_entity}",
                    "summary": (
                        f"query={clean_entity}; schema={item.get('schema', '')}; "
                        f"countries={','.join(str(country) for country in item.get('countries', []))}"
                    ),
                    "url": f"https://www.opensanctions.org/search/?q={urllib.parse.quote(clean_entity)}",
                    "confidence": 0.84 if match_level == "exact" else 0.58,
                    "entity_match": {
                        "level": match_level,
                        "score": 0.92 if match_level == "exact" else 0.58,
                        "method": "authorized_opensanctions_caption_to_query",
                        "identifiers": {"query": clean_entity, "matched_name": matched_name},
                    },
                    "entities": [
                        {
                            "kind": "person_or_company",
                            "name": matched_name or clean_entity,
                            "relation": "watchlist_match_candidate",
                            "confidence": 0.78 if match_level == "exact" else 0.55,
                            "source": "OpenSanctions",
                        }
                    ],
                    "evidence": [
                        {
                            "type": "authorized_watchlist_search_result",
                            "provider": "OpenSanctions",
                            "source_url": f"https://www.opensanctions.org/search/?q={urllib.parse.quote(clean_entity)}",
                            "schema": item.get("schema", ""),
                            "countries": item.get("countries", []),
                            "license": "CC BY-NC 4.0",
                            "license_review": "non_commercial_or_authorized_use_required",
                            "entity_match_level": match_level,
                        }
                    ],
                    "raw": item,
                }
            )
        return {"health": self.health_check(), "standardized_records": records, "raw": result}
