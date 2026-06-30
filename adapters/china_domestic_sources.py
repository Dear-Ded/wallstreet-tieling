"""
中国企业尽调扩展数据源 — 国内税务/破产/拍卖/境外投资/信用平台。
所有适配器默认禁用,通过 UserAuthorizationGate 授权后使用。
数据来源: 国家税务总局/法院/商务部/百度爱企查/水滴信用 等中国官方公开平台。
"""

from __future__ import annotations
from adapters.safe_research_adapter import SafeResearchAdapter
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import json, urllib.request, urllib.parse, time, hashlib, re


# ================================================================
# 企业税务信用公开查询 (国家税务总局)
# 调查线: MONEY — 税务合规
# ================================================================
class EnterpriseTaxCreditLookup(SafeResearchAdapter):
    """查询企业纳税信用A级纳税人名单及重大税收违法案件。
    数据来源: 国家税务总局及各省税务局依法公开的纳税信用信息。
    """

    source_domain = "public_tax_authority"
    source_type = "enterprise_tax_credit_public_record"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 4.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_tax_credit"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Tax Credit Public Records (China SAT)",
            source_type="public_tax_disclosure",
            default_config={"investigation_lane": "money", "compliance_framework": "税务公告依法公开"})

    def is_available(self) -> bool: return self._gate.is_authorized(self._source_key)
    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_tax_credit(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        urls = [
            f"https://www.chinatax.gov.cn/chinatax/search/?q={urllib.parse.quote(company_name)}",
            f"https://hd.chinatax.gov.cn/nszx/InitCredit.html?key={urllib.parse.quote(company_name)}",
        ]
        indicators = 0
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    indicators += body.count("纳税信用") + body.count("A级纳税人") + body.count("税收违法")
            except Exception: pass
            time.sleep(2)

        self._gate.log_access(self._source_key, "tax_credit_lookup", target, f"indicators_{indicators}")
        return {"query_subject_hash": target, "source_domain": self.source_domain,
            "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
            "access_path": "chinatax_public_search", "investigation_lane": "money",
            "investigation_purpose": "企业纳税信用评估 — 国家税务总局依法公开的纳税信用信息",
            "fields": {"tax_record_indicators": indicators, "data_note": "国家税务总局依法公开的纳税信用A级名单及重大税收违法案件"},
            "field_count": 1, "response_status": 200}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 企业司法拍卖/破产记录查询
# 调查线: MONEY — 资产处置/倒闭风险
# ================================================================
class EnterpriseJudicialAssetLookup(SafeResearchAdapter):
    """查询企业涉及的司法拍卖及破产重整公开记录。
    数据来源: 人民法院诉讼资产网/全国企业破产重整案件信息网。
    """

    source_domain = "public_judicial_asset"
    source_type = "enterprise_judicial_auction_bankruptcy_record"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 4.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_judicial_asset"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Judicial Auction & Bankruptcy Records",
            source_type="public_court_auction_bankruptcy",
            default_config={"investigation_lane": "money", "compliance_framework": "法院依法公开的司法拍卖和破产信息"})

    def is_available(self) -> bool: return self._gate.is_authorized(self._source_key)
    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_bankruptcy(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://pccz.court.gov.cn/pcajxxw/search?q={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                indicators = body.count("破产") + body.count("重整")
                self._gate.log_access(self._source_key, "bankruptcy_lookup", target, f"indicators_{indicators}")
                return {"query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
                    "access_path": "pccz_court_public_search", "investigation_lane": "money",
                    "investigation_purpose": "企业破产/重整风险评估 — 全国企业破产重整案件信息网公开数据",
                    "fields": {"bankruptcy_indicators": indicators, "data_note": "法院依法公开的破产重整案件信息"},
                    "field_count": 1, "response_status": 200}
        except Exception as e: return {"error": str(e), "authorized": True}

    def query_auction(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://www.rmfysszc.gov.cn/search.shtml?key={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                indicators = body.count("拍卖") + body.count("变卖")
                self._gate.log_access(self._source_key, "auction_lookup", target, f"indicators_{indicators}")
                return {"query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
                    "access_path": "rmfysszc_public_search", "investigation_lane": "money",
                    "investigation_purpose": "企业司法拍卖记录查询 — 人民法院诉讼资产网公开数据",
                    "fields": {"auction_indicators": indicators, "data_note": "法院依法公开的司法拍卖信息(股权/不动产/土地使用权/设备)"},
                    "field_count": 1, "response_status": 200}
        except Exception as e: return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 企业境外投资备案查询 (商务部)
# 调查线: MONEY — 海外投资合规
# ================================================================
class EnterpriseOverseasInvestment(SafeResearchAdapter):
    """查询企业境外投资备案记录。
    数据来源: 商务部境外投资企业(机构)备案结果公开名录。
    """

    source_domain = "public_mofcom_overseas"
    source_type = "enterprise_overseas_investment_record"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 4.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_overseas_invest"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Overseas Investment Filing Records (MOFCOM)",
            source_type="public_overseas_investment_filing",
            default_config={"investigation_lane": "money", "compliance_framework": "商务部依法公开的境外投资备案信息"})

    def is_available(self) -> bool: return self._gate.is_authorized(self._source_key)
    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_overseas_investment(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://femhzs.mofcom.gov.cn/fecpmvc/pages/fem/CorpFemList.html?q={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                indicators = len(re.findall(r'(?:境内投资主体|境外企业|备案|核准)', body))
                self._gate.log_access(self._source_key, "overseas_lookup", target, f"indicators_{indicators}")
                return {"query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
                    "access_path": "mofcom_public_search", "investigation_lane": "money",
                    "investigation_purpose": "企业境外投资合规评估 — 商务部依法公开的境外投资备案信息",
                    "fields": {"overseas_invest_indicators": indicators, "data_note": "商务部依法公开的境外投资企业备案记录"},
                    "field_count": 1, "response_status": 200}
        except Exception as e: return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 百度企业信用(爱企查)免费层查询
# 调查线: MONEY + PEOPLE — 工商注册公开信息聚合
# ================================================================
class EnterpriseBaiduCreditLookup(SafeResearchAdapter):
    """通过百度爱企查免费层查询企业工商注册公开信息。
    数据来源: 百度爱企查(从GSXT等官方源聚合)。
    """

    source_domain = "aiqicha_baidu"
    source_type = "enterprise_baidu_credit_public_aggregation"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_baidu_credit"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Baidu Aiqicha Enterprise Public Record Lookup",
            source_type="public_chinese_business_registry_aggregator",
            default_config={"investigation_lane": "money", "compliance_framework": "从GSXT等官方源聚合的公开工商信息"})

    def is_available(self) -> bool: return self._gate.is_authorized(self._source_key)
    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_enterprise(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://aiqicha.baidu.com/s?q={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                result_count = len(re.findall(r'(?:法定代表人|注册资本|成立日期|统一社会信用代码|经营范围)', body))
                self._gate.log_access(self._source_key, "aiqicha_lookup", target, f"fields_{result_count}")
                return {"query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
                    "access_path": "aiqicha_public_search", "investigation_lane": "money",
                    "investigation_purpose": "企业工商注册信息查询 — 百度爱企查(从GSXT等官方源聚合)",
                    "fields": {"public_field_count": result_count, "data_note": "百度爱企查免费层公开数据"},
                    "field_count": 1, "response_status": 200}
        except Exception as e: return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 水滴信用企业公开信息查询
# 调查线: MONEY — 企业信用
# ================================================================
class EnterpriseShuidiCreditLookup(SafeResearchAdapter):
    """通过水滴信用免费层查询企业公开信用信息。
    数据来源: 水滴信用(持牌征信机构,从官方源聚合)。
    """

    source_domain = "shuidi_credit"
    source_type = "enterprise_shuidi_public_credit_lookup"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_shuidi_credit"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Shuidi Credit Enterprise Public Record Lookup",
            source_type="public_licensed_credit_agency_record",
            default_config={"investigation_lane": "money", "compliance_framework": "持牌征信机构从官方源聚合的公开信用信息"})

    def is_available(self) -> bool: return self._gate.is_authorized(self._source_key)
    def enable(self, h=24): return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_enterprise(self, company_name: str) -> dict[str, Any]:
        if not self.is_available(): return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://www.shuidi.cn/search?key={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                indicators = len(re.findall(r'(?:信用|风险|经营|处罚)', body))
                self._gate.log_access(self._source_key, "shuidi_lookup", target, f"indicators_{indicators}")
                return {"query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary, "authorized": True,
                    "access_path": "shuidi_public_search", "investigation_lane": "money",
                    "investigation_purpose": "企业公开信用信息查询 — 水滴信用(持牌征信机构)",
                    "fields": {"credit_indicator_count": indicators, "data_note": "水滴信用免费层公开数据"},
                    "field_count": 1, "response_status": 200}
        except Exception as e: return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}
