#!/usr/bin/env python3
"""广东信用平台 (credit.gd.gov.cn) 企业信用查询适配器 — 线下商业 lane.

广东省公共信用信息平台是广东省官方的企业信用公开平台,收录广东企业的
注册信息、经营状态、行政许可/处罚等信用数据。对广东个体工商户/小微企业
尽调的价值:官方注册信息、法定代表人、经营状态、注册资本。

**混合模式:**
- 按名称搜索 (POST /company/web/booleanQueryListByPage): 需要滑块验证码,
  query() 返回 interaction_required,附带浏览器操作指引;
  parse_browser_result() 解析浏览器复制的搜索 JSON。
- 按 MASTERDATAID 查详情 (POST /infoclass/web/getDetailByInclsCode):
  无需验证码,query_detail() 全自动直调。
- 热搜榜 (POST /searchhotResult/web/getTopFifteen): 无需验证码,
  query_hot() 全自动直调。

公开数据,无需登录,无需凭证。3 秒间隔。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class GdCreditCompanyLookup(SafeResearchAdapter):
    """广东信用平台企业查询 (混合模式: 搜索 browser-assisted, 详情全自动).

    查询维度: 企业名称 / 统一社会信用代码 / MASTERDATAID
    提取字段: 企业名称、统一社会信用代码、法定代表人、成立日期、
              注册地址、经营状态、注册资本、行业、经营范围
    """

    source_domain = "credit.gd.gov.cn"
    source_type = "guangdong_credit_registry"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True  # 搜索需要浏览器辅助 (滑块验证码)
    min_request_interval = 3.0

    SEARCH_URL = "https://credit.gd.gov.cn/page/creditFind/index.html"
    SEARCH_API = (
        "https://credit.gd.gov.cn/gdcreditwebApi2/company/web/booleanQueryListByPage"
    )
    DETAIL_API = (
        "https://credit.gd.gov.cn/gdcreditwebApi2/infoclass/web/getDetailByInclsCode"
    )
    HOT_API = (
        "https://credit.gd.gov.cn/gdcreditwebApi2/searchhotResult/web/getTopFifteen"
    )
    DETAIL_CLS = "v_ssztjcxx_label"

    BROWSER_INSTRUCTIONS = (
        "1. 在浏览器中打开 https://credit.gd.gov.cn/page/creditFind/index.html\n"
        "2. 在搜索框输入企业名称或统一社会信用代码,点击查询\n"
        "3. 完成滑块验证码\n"
        "4. 打开浏览器开发者工具 (F12) > Network\n"
        "5. 找到对 /company/web/booleanQueryListByPage 的 POST 请求,复制 Response JSON\n"
        "6. 调用 parse_browser_result(response_json) 解析\n"
        "7. 用返回的 masterdataid 调用 query_detail(masterdataid) 查企业详情 (全自动)"
    )

    _DETAIL_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json",
        "Request-Client-Set": "xygd-web",
        "X-Requested-With": "XMLHttpRequest",
    }

    def _build_url(self, keyword: str, **params) -> str:
        return self.SEARCH_URL

    # -- search: browser-assisted -----------------------------------------

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """返回 interaction_required,不直接发起搜索请求 (滑块验证码)."""
        start = time.monotonic()
        self._enforce_rate_limit()
        self._record_audit(
            keyword=keyword,
            url=self.SEARCH_URL,
            status=0,
            fields=[],
        )
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "fields": {},
            "field_count": 0,
            "error": "interaction_required",
            "interaction_instructions": self.BROWSER_INSTRUCTIONS,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def parse_browser_result(self, response_json: str | dict) -> dict[str, Any]:
        """解析从浏览器复制的搜索结果 JSON。

        Args:
            response_json: 浏览器 Network 面板中
                booleanQueryListByPage 响应的 JSON (字符串或 dict)

        Returns:
            结构化的企业列表,含 masterdataid (可用于 query_detail)
        """
        return {
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "fields": self._extract_search_fields(response_json),
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """基类抽象方法: 默认走搜索结果解析."""
        return self._extract_search_fields(raw_data)

    def _extract_search_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}

        inner = data.get("data") or {}
        rows = inner.get("rows") or []
        companies = []
        for item in rows[:20]:
            if not isinstance(item, dict):
                continue
            companies.append({
                "company_name": item.get("ZTMC", ""),
                "credit_code": item.get("TYSHXYDM", ""),
                "legal_rep": item.get("FDDBRXM", ""),
                "address": item.get("ZHUSUO", "") or item.get("ZCDZ", ""),
                "status": item.get("CXZT", ""),
                "masterdataid": item.get("MASTERDATAID", ""),
                "eid": item.get("MASTERDATAIDENCRYPT", ""),
            })
        return {
            "total_count": inner.get("total", len(companies)),
            "companies": companies,
            "data_note": "广东省公共信用信息平台公开数据,仅供参考",
        }

    # -- detail: fully automatic (no captcha) ------------------------------

    def query_detail(self, masterdataid: str) -> dict[str, Any]:
        """按 MASTERDATAID 查企业信用详情 (全自动,无需验证码).

        Args:
            masterdataid: 搜索结果中的 MASTERDATAID (如 GDS_xxx)

        Returns:
            企业信用详情: 名称/信用代码/法人/地址/状态/注册资本/行业等
        """
        start = time.monotonic()
        self._enforce_rate_limit()
        result = self._build_empty_result(masterdataid, "detail")
        try:
            payload = urllib.parse.urlencode({
                "clsCode": self.DETAIL_CLS,
                "jsonArgs": json.dumps({"MASTERDATAID": masterdataid}),
            }).encode("utf-8")
            req = urllib.request.Request(
                self.DETAIL_API, data=payload, headers=self._DETAIL_HEADERS
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            fields = self._extract_detail_fields(data.get("data") or {})
            result = {
                "query_subject_hash": hashlib.sha256(
                    masterdataid.encode()
                ).hexdigest()[:12],
                "source_domain": self.source_domain,
                "source_type": self.source_type,
                "data_boundary": self.data_boundary,
                "response_status": 200,
                "fields": fields,
                "field_count": len(fields),
                "duration_ms": (time.monotonic() - start) * 1000,
            }
        except Exception as exc:  # noqa: BLE001 - adapter must not hard-crash
            result["error"] = f"detail_request_failed: {type(exc).__name__}"
        self._record_audit(
            keyword=masterdataid,
            url=self.DETAIL_API,
            status=result.get("response_status", 0),
            fields=list(result.get("fields", {}).keys()),
        )
        return result

    def _extract_detail_fields(self, data: dict) -> dict[str, Any]:
        if not isinstance(data, dict) or not data:
            return {"found": False}
        return {
            "found": True,
            "company_name": data.get("ZTMC", "") or data.get("QYMC", ""),
            "credit_code": data.get("TYSHXYDM", ""),
            "legal_rep": data.get("FDDBRXM", ""),
            "established_date": data.get("CLRQ", "") or data.get("ZCRQ", ""),
            "address": data.get("ZHUSUO", "") or data.get("ZCDZ", ""),
            "company_type": data.get("QYLX", ""),
            "status": data.get("CXZT", "") or data.get("DJZT", ""),
            "registered_capital": data.get("ZCZB", ""),
            "industry": data.get("SSHY", "") or data.get("HYML", ""),
            "business_scope": data.get("JYFW", ""),
            "subject_type": data.get("ZTLX", ""),
            "masterdataid": data.get("MASTERDATAID", ""),
            "eid": data.get("MASTERDATAIDENCRYPT", ""),
            "data_note": "广东省公共信用信息平台公开数据,仅供参考",
        }

    # -- hot search: fully automatic (no captcha) --------------------------

    def query_hot(self) -> dict[str, Any]:
        """热搜企业榜 (全自动,无需验证码)."""
        start = time.monotonic()
        self._enforce_rate_limit()
        result = self._build_empty_result("hot", "hot_search")
        try:
            payload = urllib.parse.urlencode({}).encode("utf-8")
            req = urllib.request.Request(
                self.HOT_API, data=payload, headers=self._DETAIL_HEADERS
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            rows = (data.get("data") or [])
            companies = [
                {
                    "company_name": r.get("ztmc", ""),
                    "masterdataid": r.get("masterdataid", ""),
                    "eid": r.get("eid", ""),
                    "hotnum": r.get("hotnum", 0),
                }
                for r in rows[:20] if isinstance(r, dict)
            ]
            result = {
                "query_subject_hash": "hot_search",
                "source_domain": self.source_domain,
                "source_type": self.source_type,
                "data_boundary": self.data_boundary,
                "response_status": 200,
                "fields": {"companies": companies, "count": len(companies)},
                "field_count": len(companies),
                "duration_ms": (time.monotonic() - start) * 1000,
            }
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"hot_request_failed: {type(exc).__name__}"
        self._record_audit(
            keyword="hot_search",
            url=self.HOT_API,
            status=result.get("response_status", 0),
            fields=["companies"],
        )
        return result
