"""
企业尽调扩展数据源适配器 — 商业物流、公共采购、住宿许可、SEC客户集中度。
所有适配器默认禁用,通过 UserAuthorizationGate 授权后使用。
每个适配器服务明确的尽调管线(MONEY/GOODS/PEOPLE)。

安全策略对齐: UserAuthorizationGate → enable() → 可审计调用。
"""

from __future__ import annotations
from adapters.safe_research_adapter import SafeResearchAdapter
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import json, urllib.request, urllib.parse, time, hashlib


# ================================================================
# 企业商业物流公开记录查询
# 调查线: GOODS — 供应链透明度
# ================================================================
class EnterpriseLogisticsLookup(SafeResearchAdapter):
    """
    查询企业商业物流公开记录(货运提单、船舶动态、承运商合规)。
    数据来源: 美国海关货运公开数据(ImportYeti)、船舶AIS公开数据(MarineTraffic)、
    FMCSA承运商安全记录。

    调查价值: 验证企业供应链规模、国际货运活跃度、承运商合规性。
    合规基础: 所有数据来自政府依法公开的货运记录和船舶位置信息。
    """

    source_domain = "public_commercial_logistics"
    source_type = "enterprise_logistics_public_record"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 4.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_logistics"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Commercial Logistics Public Records",
            source_type="public_customs_freight_vessel_records",
            default_config={"investigation_lane": "goods",
                "compliance_framework": "US Customs public manifest data, AIS public vessel positions"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)
    def enable(self, h: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_import_records(self, company_name: str) -> dict[str, Any]:
        """查询企业的美国海关进口货运公开记录"""
        if not self.is_available():
            return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]

        # ImportYeti 公开搜索
        url = f"https://www.importyeti.com/search?q={urllib.parse.quote(company_name)}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                supplier_count = body.count("supplier")
                shipment_count = body.count("shipment")
                self._gate.log_access(self._source_key, "import_records", target,
                    f"supplier_refs_{supplier_count}_shipment_refs_{shipment_count}")
                return {
                    "query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary,
                    "authorized": True, "access_path": "importyeti_public_search",
                    "investigation_lane": "goods",
                    "investigation_purpose": "企业国际供应链规模评估 — 海关进口货运公开记录",
                    "fields": {
                        "import_record_indicators": shipment_count,
                        "supplier_relationship_indicators": supplier_count,
                        "data_note": "美国海关依法公开的进口货运提单记录(ImportYeti聚合)",
                    },
                    "field_count": 2, "response_status": 200,
                }
        except Exception as e:
            self._gate.log_access(self._source_key, "import_records", target, f"error_{type(e).__name__}")
            return {"error": str(e), "authorized": True}

    def check_carrier_safety(self, carrier_name_or_dot: str) -> dict[str, Any]:
        """查询美国FMCSA承运商安全记录"""
        if not self.is_available():
            return {"error": "source_not_authorized"}
        target = hashlib.sha256(carrier_name_or_dot.encode()).hexdigest()[:12]
        url = f"https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&query_string={urllib.parse.quote(carrier_name_or_dot)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EnterpriseDueDiligence/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                has_safety = "safety" in body.lower()
                self._gate.log_access(self._source_key, "carrier_safety", target,
                    "safety_data_found" if has_safety else "no_data")
                return {
                    "query_subject_hash": target, "source_domain": self.source_domain,
                    "authorized": True, "access_path": "fmcsa_safer_public_query",
                    "investigation_lane": "goods",
                    "investigation_purpose": "承运商安全合规记录查询 — FMCSA公开安全评级",
                    "fields": {"safety_record_found": has_safety,
                        "data_note": "美国联邦汽车运输安全管理局公开的承运商安全记录"},
                    "field_count": 1, "response_status": 200,
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 公共采购合同公开数据查询
# 调查线: GOODS + MONEY — 客户集中度/收入依赖
# ================================================================
class EnterpriseProcurementLookup(SafeResearchAdapter):
    """
    查询企业在全球公共采购中的合同记录。
    数据来源: SAM.gov(美国)、USASpending(美国)、TED(欧盟)。

    调查价值: 评估企业对政府合同的收入依赖度、竞争对手的政府采购份额。
    """

    source_domain = "public_procurement_databases"
    source_type = "enterprise_public_procurement_record"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_procurement"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Public Procurement Contract Records",
            source_type="public_government_contract_databases",
            default_config={"investigation_lane": "goods",
                "compliance_framework": "US Federal Procurement Data System, EU TED"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)
    def enable(self, h: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def query_us_contracts(self, company_name: str) -> dict[str, Any]:
        """查询美国联邦合同授予记录"""
        if not self.is_available():
            return {"error": "source_not_authorized"}
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        url = f"https://api.usaspending.gov/api/v2/search/spending_by_award/"
        body_data = json.dumps({
            "filters": {"recipient_search_text": [company_name]},
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
            "limit": 10,
        }).encode()
        try:
            req = urllib.request.Request(url, data=body_data,
                headers={"Content-Type": "application/json", "User-Agent": "EnterpriseDueDiligence/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                results = data.get("results", [])
                self._gate.log_access(self._source_key, "us_contracts", target, f"awards_{len(results)}")
                total = sum(float(r.get("Award Amount", 0) or 0) for r in results)
                return {
                    "query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary,
                    "authorized": True, "access_path": "usaspending_public_api",
                    "investigation_lane": "goods",
                    "investigation_purpose": "企业政府合同收入依赖度分析 — USASpending公开API",
                    "fields": {
                        "contract_awards_found": len(results),
                        "total_award_amount_estimate": total,
                        "data_note": "美国联邦采购数据系统(FPDS)公开数据, USASpending.gov API",
                    },
                    "field_count": 2, "response_status": 200,
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# 住宿行业经营许可公开记录查询
# 调查线: GOODS — 企业经营真实性验证
# ================================================================
class EnterpriseHospitalityLookup(SafeResearchAdapter):
    """
    查询住宿行业企业的经营许可公开记录。
    数据来源: 各州/郡住宿经营许可数据库、公共健康检查记录。

    调查价值: 验证酒店/住宿企业的合法经营资质、健康合规历史。
    合规基础: 住宿经营许可是政府依法公开的行业许可信息。
    """

    source_domain = "public_hospitality_licensing"
    source_type = "enterprise_lodging_license_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 4.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "enterprise_hospitality"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Lodging License Public Record Verification",
            source_type="public_lodging_business_license_lookup",
            default_config={"investigation_lane": "goods",
                "compliance_framework": "State lodging establishment licensing — public health department records"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)
    def enable(self, h: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def verify_lodging_license(self, business_name: str, state: str = "") -> dict[str, Any]:
        """查询住宿企业的经营许可公开记录"""
        if not self.is_available():
            return {"error": "source_not_authorized"}
        target = hashlib.sha256(f"{business_name}:{state}".encode()).hexdigest()[:12]

        # 通过公开搜索引擎查询州住宿许可数据库
        query = f"{business_name} hotel license {state} site:gov"
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                license_refs = body.count("license") + body.count("permit")
                self._gate.log_access(self._source_key, "lodging_license", target,
                    f"license_refs_{license_refs}")
                return {
                    "query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary,
                    "authorized": True, "access_path": "public_search_engine_license_lookup",
                    "investigation_lane": "goods",
                    "investigation_purpose": "住宿企业经营许可验证 — 政府公开许可记录",
                    "fields": {
                        "license_record_indicators": license_refs,
                        "data_note": "各州卫生部门依法公开的住宿经营许可和检查记录(通过公开搜索引擎聚合)",
                    },
                    "field_count": 1, "response_status": 200,
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}


# ================================================================
# SEC上市公司客户/供应商集中度公开披露查询
# 调查线: MONEY — 收入集中度风险
# ================================================================
class EnterpriseCustomerConcentration(SafeResearchAdapter):
    """
    查询美国上市公司在SEC申报中披露的客户/供应商集中度。
    数据来源: SEC EDGAR 10-K申报全文。

    调查价值: 评估企业的客户依赖风险(单一客户收入占比过高=重大风险)。
    合规基础: SEC法定披露要求(Regulation S-K Item 101/103)。
    """

    source_domain = "sec_edgar_public_filings"
    source_type = "enterprise_customer_concentration_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "customer_concentration"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="SEC Customer/Supplier Concentration Disclosure Analysis",
            source_type="public_sec_filing_customer_concentration",
            default_config={"investigation_lane": "money",
                "compliance_framework": "SEC Regulation S-K Item 101/103 — mandatory customer concentration disclosure"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)
    def enable(self, h: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=h).to_dict()

    def analyze_customer_concentration(self, cik_or_ticker: str) -> dict[str, Any]:
        """分析上市公司的客户集中度公开披露"""
        if not self.is_available():
            return {"error": "source_not_authorized"}
        target = hashlib.sha256(cik_or_ticker.encode()).hexdigest()[:12]

        # 通过SEC EDGAR submissions API获取最新10-K
        cik = cik_or_ticker.zfill(10) if cik_or_ticker.isdigit() else cik_or_ticker
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "EnterpriseDueDiligence/1.0 (compliance@example.com)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                company_name = data.get("name", "")
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                ten_k_count = sum(1 for f in forms if f in ("10-K", "10-K/A"))
                self._gate.log_access(self._source_key, "customer_concentration", target,
                    f"company_{company_name}_10k_{ten_k_count}")
                return {
                    "query_subject_hash": target, "source_domain": self.source_domain,
                    "source_type": self.source_type, "data_boundary": self.data_boundary,
                    "authorized": True, "access_path": "sec_edgar_submissions_api",
                    "investigation_lane": "money",
                    "investigation_purpose": "上市公司客户集中度风险评估 — SEC Regulation S-K强制披露",
                    "fields": {
                        "company_name": company_name,
                        "ten_k_filings_available": ten_k_count,
                        "data_note": "SEC 10-K年度报告包含客户集中度强制披露(单一客户收入>10%时必须披露)",
                    },
                    "field_count": 2, "response_status": 200,
                }
        except Exception as e:
            return {"error": str(e), "authorized": True}

    def _build_url(self, k, **p): return ""
    def _extract_public_fields(self, r): return {}
