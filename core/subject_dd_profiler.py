"""
主体深度尽调画像编排器 — 集成所有深度采集适配器,服务主线调查管线(money/goods/people)。
默认禁用,通过 UserAuthorizationGate 显式授权后接入 investigation pipeline。
"""

from __future__ import annotations
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import hashlib, json, time


class SubjectDeepDueDiligenceProfiler:
    """
    企业主体深度尽调画像编排器。

    调查管线映射:
    - PEOPLE线: 关键人员身份验证/跨平台档案核验/公开记录交叉核实
    - MONEY线: 企业信息安全历史评估/纳税信用/司法拍卖破产记录/境外投资备案
    - GOODS线: 供应链物流公开记录/公共采购合同/住宿经营许可/域名资产可见性

    安全设计:
    - 默认所有子适配器禁用
    - 用户必须为每个尽调维度显式授权
    - 所有查询经过 UserAuthorizationGate
    - 所有结果标记 investigation_lane
    - 集成到 build_investigation_packet 的可选高级模块中

    使用方式:
        gate = UserAuthorizationGate("user_id")
        profiler = SubjectDeepDueDiligenceProfiler(gate)
        profiler.enable_people_lane()          # 用户显式授权PEOPLE管线
        result = profiler.profile_subject("企业名", "高管名", "企业域名")
    """

    def __init__(self, auth_gate: UserAuthorizationGate):
        self._gate = auth_gate
        self._adapters: dict[str, Any] = {}
        self._lane_sources: dict[str, list[str]] = {"money": [], "goods": [], "people": []}
        self._init_adapters()

    def _init_adapters(self) -> None:
        """注册所有可用的深度采集适配器。每个适配器默认禁用。"""
        # PEOPLE 管线适配器
        self._register_people_adapters()
        # MONEY 管线适配器
        self._register_money_adapters()
        # GOODS 管线适配器
        self._register_goods_adapters()

    def _register_people_adapters(self) -> None:
        """注册人员调查管线适配器"""
        lane = "people"
        try:
            from adapters.enterprise_profiling import ExecutiveIdentityVerification
            a = ExecutiveIdentityVerification(self._gate)
            self._adapters["executive_identity"] = a
            self._lane_sources[lane].append("executive_identity")
        except ImportError: pass

        try:
            from adapters.runtime_deep import UsernameCrossPlatformVerifier
            a = UsernameCrossPlatformVerifier(self._gate)
            self._adapters["cross_platform_verification"] = a
            self._lane_sources[lane].append("cross_platform_verification")
        except ImportError: pass

        try:
            from adapters.deep_osint import OpenSourceOSINTIntegration
            a = OpenSourceOSINTIntegration(self._gate)
            self._adapters["opensource_osint"] = a
            self._lane_sources[lane].append("opensource_osint")
        except ImportError: pass

        try:
            from adapters.enterprise_profiling import KeyPersonnelRecordCrossCheck
            a = KeyPersonnelRecordCrossCheck(self._gate)
            self._adapters["personnel_cross_check"] = a
            self._lane_sources[lane].append("personnel_cross_check")
        except ImportError: pass

        try:
            from adapters.deep_osint import MessagePlatformAggregationLookup
            a = MessagePlatformAggregationLookup(self._gate)
            self._adapters["message_platform_aggregation"] = a
            self._lane_sources[lane].append("message_platform_aggregation")
        except ImportError: pass

    def _register_money_adapters(self) -> None:
        """注册财务/风险调查管线适配器"""
        lane = "money"
        try:
            from adapters.enterprise_profiling import EnterpriseDomainSecurityAssessment
            a = EnterpriseDomainSecurityAssessment(self._gate)
            self._adapters["domain_security"] = a
            self._lane_sources[lane].append("domain_security")
        except ImportError: pass

        try:
            from adapters.enterprise_logistics import EnterpriseCustomerConcentration
            a = EnterpriseCustomerConcentration(self._gate)
            self._adapters["customer_concentration"] = a
            self._lane_sources[lane].append("customer_concentration")
        except ImportError: pass

        try:
            from adapters.china_domestic_sources import EnterpriseTaxCreditLookup
            a = EnterpriseTaxCreditLookup(self._gate)
            self._adapters["tax_credit"] = a
            self._lane_sources[lane].append("tax_credit")
        except ImportError: pass

        try:
            from adapters.china_domestic_sources import EnterpriseJudicialAssetLookup
            a = EnterpriseJudicialAssetLookup(self._gate)
            self._adapters["judicial_asset"] = a
            self._lane_sources[lane].append("judicial_asset")
        except ImportError: pass

        try:
            from adapters.china_domestic_sources import EnterpriseOverseasInvestment
            a = EnterpriseOverseasInvestment(self._gate)
            self._adapters["overseas_invest"] = a
            self._lane_sources[lane].append("overseas_invest")
        except ImportError: pass

    def _register_goods_adapters(self) -> None:
        """注册供应链/运营调查管线适配器"""
        lane = "goods"
        try:
            from adapters.enterprise_logistics import EnterpriseLogisticsLookup
            a = EnterpriseLogisticsLookup(self._gate)
            self._adapters["logistics"] = a
            self._lane_sources[lane].append("logistics")
        except ImportError: pass

        try:
            from adapters.enterprise_logistics import EnterpriseProcurementLookup
            a = EnterpriseProcurementLookup(self._gate)
            self._adapters["procurement"] = a
            self._lane_sources[lane].append("procurement")
        except ImportError: pass

        try:
            from adapters.enterprise_logistics import EnterpriseHospitalityLookup
            a = EnterpriseHospitalityLookup(self._gate)
            self._adapters["hospitality"] = a
            self._lane_sources[lane].append("hospitality")
        except ImportError: pass

        try:
            from adapters.enterprise_profiling import EnterpriseContactAttribution
            a = EnterpriseContactAttribution(self._gate)
            self._adapters["contact_attribution"] = a
            self._lane_sources[lane].append("contact_attribution")
        except ImportError: pass

        try:
            from adapters.deep_osint import CommercialPlatformSessionLookup
            a = CommercialPlatformSessionLookup(self._gate)
            self._adapters["commercial_platform"] = a
            self._lane_sources[lane].append("commercial_platform")
        except ImportError: pass

        try:
            from adapters.runtime_deep import AiqichaSessionLookup
            a = AiqichaSessionLookup(self._gate)
            self._adapters["aiqicha_lookup"] = a
            self._lane_sources[lane].append("aiqicha_lookup")
        except ImportError: pass

    # ================================================================
    # 用户授权接口
    # ================================================================

    def enable_people_lane(self, hours: int = 24) -> dict:
        """用户授权启用 PEOPLE 调查管线"""
        results = {}
        for key in self._lane_sources.get("people", []):
            a = self._adapters.get(key)
            if a and hasattr(a, 'enable'):
                results[key] = a.enable(hours)
        return {"lane": "people", "sources_authorized": len(results), "details": results}

    def enable_money_lane(self, hours: int = 24) -> dict:
        """用户授权启用 MONEY 调查管线"""
        results = {}
        for key in self._lane_sources.get("money", []):
            a = self._adapters.get(key)
            if a and hasattr(a, 'enable'):
                results[key] = a.enable(hours)
        return {"lane": "money", "sources_authorized": len(results), "details": results}

    def enable_goods_lane(self, hours: int = 24) -> dict:
        """用户授权启用 GOODS 调查管线"""
        results = {}
        for key in self._lane_sources.get("goods", []):
            a = self._adapters.get(key)
            if a and hasattr(a, 'enable'):
                results[key] = a.enable(hours)
        return {"lane": "goods", "sources_authorized": len(results), "details": results}

    def enable_all_lanes(self, hours: int = 24) -> dict:
        """用户授权启用全部调查管线"""
        return {
            "people": self.enable_people_lane(hours),
            "money": self.enable_money_lane(hours),
            "goods": self.enable_goods_lane(hours),
        }
    def get_lane_status(self) -> dict:
        """获取各管线的授权和可用状态"""
        status = {}
        for lane in ["people", "money", "goods"]:
            sources = self._lane_sources.get(lane, [])
            authorized = sum(1 for k in sources if self._adapters.get(k) and hasattr(self._adapters[k], 'is_available') and self._adapters[k].is_available())
            status[lane] = {"total_sources": len(sources), "authorized": authorized, "sources": sources}
        return status

    # ================================================================
    # 主体画像编排 — 服务主线尽调
    # ================================================================

    def profile_subject(
        self,
        company_name: str,
        executive_name: str = "",
        company_domain: str = "",
        *,
        execute_live: bool = False,
    ) -> dict[str, Any]:
        """
        对企业主体执行深度尽调画像。

        输入: 企业名称(必填), 高管姓名(可选), 企业域名(可选)
        输出: 按 money/goods/people 分类的结构化尽调数据
        """
        target = hashlib.sha256(company_name.encode()).hexdigest()[:12]
        profile = {
            "subject_hash": target,
            "company_name_hash": target,
            "investigation_mode": "deep_due_diligence",
            "execution_mode": "live_authorized" if execute_live else "dry_run_plan_only",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "authorization_status": self.get_lane_status(),
            "execution_plan": self._build_execution_plan(company_name, executive_name, company_domain),
            "money_lane_findings": {},
            "goods_lane_findings": {},
            "people_lane_findings": {},
            "evidence_sources_queried": {},
        }
        if not execute_live:
            return profile

        # PEOPLE 管线 — 人员调查
        if company_name:
            profile["people_lane_findings"] = self._run_people_lane(executive_name or company_name, company_domain)

        # MONEY 管线 — 财务/风险调查
        if company_domain or company_name:
            profile["money_lane_findings"] = self._run_money_lane(company_domain or company_name, company_name)

        # GOODS 管线 — 供应链/运营调查
        if company_name or company_domain:
            profile["goods_lane_findings"] = self._run_goods_lane(company_name, company_domain)

        return profile

    def _build_execution_plan(self, company_name: str, executive_name: str, company_domain: str) -> dict:
        target_subject = executive_name or company_name

        def lane_rows(lane: str, target: str) -> list[dict[str, Any]]:
            target_hash = hashlib.sha256(str(target).encode()).hexdigest()[:12] if target else ""
            rows = []
            for key in self._lane_sources.get(lane, []):
                adapter = self._adapters.get(key)
                ready = bool(adapter and hasattr(adapter, "is_available") and adapter.is_available())
                rows.append({"source": key, "target_hash": target_hash, "ready": ready})
            return rows

        return {
            "default_behavior": "plan_only_no_network",
            "live_execution_requires": "execute_live=True plus lane-level UserAuthorizationGate enablement",
            "people": lane_rows("people", target_subject),
            "money": lane_rows("money", company_domain or company_name),
            "goods": lane_rows("goods", company_name or company_domain),
        }

    def _run_people_lane(self, subject: str, domain: str) -> dict:
        findings = {}
        for key in self._lane_sources.get("people", []):
            a = self._adapters.get(key)
            if not a or not hasattr(a, 'is_available') or not a.is_available():
                continue
            try:
                if key == "executive_identity":
                    r = a.verify_executive_identity(subject, domain)
                elif key == "cross_platform_verification":
                    r = a.verify_username(subject)
                elif key == "personnel_cross_check":
                    r = a.cross_check_personnel(subject)
                elif key in ("opensource_osint", "message_platform_aggregation"):
                    continue  # 需额外参数,由上层按需调用
                else:
                    continue
                findings[key] = r
                self._gate.log_access(f"dd_profiler_people", key, hashlib.sha256(subject.encode()).hexdigest()[:12], "executed")
            except Exception as e:
                findings[key] = {"error": str(e)}
        return findings

    def _run_money_lane(self, domain_or_name: str, full_name: str) -> dict:
        findings = {}
        for key in self._lane_sources.get("money", []):
            a = self._adapters.get(key)
            if not a or not hasattr(a, 'is_available') or not a.is_available():
                continue
            try:
                if key == "domain_security":
                    r = a.assess_domain_risk(domain_or_name)
                elif key == "customer_concentration":
                    r = a.analyze_customer_concentration(domain_or_name)
                elif key == "tax_credit":
                    r = a.query_tax_credit(full_name)
                elif key == "judicial_asset":
                    r = a.query_bankruptcy(full_name)
                elif key == "overseas_invest":
                    r = a.query_overseas_investment(full_name)
                else:
                    continue
                findings[key] = r
                self._gate.log_access(f"dd_profiler_money", key, hashlib.sha256(domain_or_name.encode()).hexdigest()[:12], "executed")
            except Exception as e:
                findings[key] = {"error": str(e)}
        return findings

    def _run_goods_lane(self, company: str, domain: str) -> dict:
        findings = {}
        for key in self._lane_sources.get("goods", []):
            a = self._adapters.get(key)
            if not a or not hasattr(a, 'is_available') or not a.is_available():
                continue
            try:
                if key == "logistics":
                    r = a.query_import_records(company)
                elif key == "procurement":
                    r = a.query_us_contracts(company)
                elif key == "hospitality":
                    r = a.verify_lodging_license(company)
                elif key == "contact_attribution":
                    r = a.verify_business_phone(company)
                elif key == "commercial_platform":
                    r = a.query_with_session(company)
                elif key == "aiqicha_lookup":
                    r = a.query_company(company)
                else:
                    continue
                findings[key] = r
                self._gate.log_access(f"dd_profiler_goods", key, hashlib.sha256(company.encode()).hexdigest()[:12], "executed")
            except Exception as e:
                findings[key] = {"error": str(e)}
        return findings
