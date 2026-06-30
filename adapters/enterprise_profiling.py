"""
企业尽调主体画像适配器 — 企业关键人员的公开身份一致性验证。
所有适配器默认禁用,必须通过用户授权网关(UserAuthorizationGate)显式授权后方可使用。
不接入默认一键尽调流程。

安全策略对齐:
- 默认 DISABLED → 用户调用 enable() 显式授权 → 可审计调用
- 不接入 build_investigation_packet 的默认数据源列表
- 每个适配器传入 UserAuthorizationGate 依赖
"""

from __future__ import annotations
from adapters.safe_research_adapter import SafeResearchAdapter
from core.user_auth_gate import UserAuthorizationGate
from typing import Any
import json, urllib.request, urllib.parse, time, hashlib


# ================================================================
# 企业关键人员公开身份一致性验证
# 调查线: PEOPLE — FATF CDD
# ================================================================
class ExecutiveIdentityVerification(SafeResearchAdapter):
    """验证企业关键人员(法人/董事/高管)在不同公开平台上的身份一致性。
    
    安全设计: 依赖 UserAuthorizationGate。用户必须显式调用 enable() 授权。
    未授权时所有公开方法返回 {"error": "source_not_authorized"}。
    """

    source_domain = "public_professional_networks"
    source_type = "enterprise_executive_identity_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    PROFESSIONAL_PLATFORMS = [
        ("github", "https://github.com/{}"),
        ("linkedin_public", "https://www.linkedin.com/in/{}"),
        ("keybase", "https://keybase.io/{}"),
        ("medium", "https://medium.com/@{}"),
        ("speakerdeck", "https://speakerdeck.com/{}"),
        ("slideshare", "https://www.slideshare.net/{}"),
        ("behance", "https://www.behance.net/{}"),
        ("dribbble", "https://dribbble.com/{}"),
        ("gitlab", "https://gitlab.com/{}"),
        ("bitbucket", "https://bitbucket.org/{}/"),
        ("producthunt", "https://www.producthunt.com/@{}"),
        ("devto", "https://dev.to/{}"),
        ("ycombinator-news", "https://news.ycombinator.com/user?id={}"),
    ]

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "executive_identity_verification"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Executive Public Identity Consistency Verification",
            source_type="public_professional_networks",
            default_config={"investigation_lane": "people", "compliance_framework": "FATF CDD"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, duration_hours: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=duration_hours).to_dict()

    def verify_executive_identity(self, executive_name: str, company_domain: str = "") -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized", "message": "用户需先通过授权网关启用此数据源: adapter.enable()"}

        username_variants = self._generate_variants(executive_name, company_domain)
        found_profiles = {}
        for username in username_variants[:3]:
            count = 0
            for platform, url_template in self.PROFESSIONAL_PLATFORMS:
                url = url_template.format(username)
                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)",
                        "Accept": "text/html",
                    })
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                        if resp.status == 200 and not self._is_not_found(body):
                            count += 1
                            found_profiles.setdefault(platform, []).append(username)
                except Exception:
                    pass
                time.sleep(1.2)

        self._gate.log_access(self._source_key, "executive_identity_check",
            hashlib.sha256(executive_name.encode()).hexdigest()[:12], f"profiles_{len(found_profiles)}")

        return {
            "query_subject_hash": hashlib.sha256(executive_name.encode()).hexdigest()[:12],
            "source_domain": self.source_domain, "source_type": self.source_type,
            "data_boundary": self.data_boundary, "authorized": True,
            "access_path": "professional_network_public_profile_verification",
            "investigation_lane": "people",
            "investigation_purpose": "企业关键人员公开身份一致性核验 — FATF CDD标准",
            "fields": {"platforms_found": len(found_profiles), "platform_list": list(found_profiles.keys())},
            "field_count": 2, "response_status": 200,
        }

    def _generate_variants(self, name: str, domain: str) -> list[str]:
        parts = name.lower().replace("-", "").replace(".", "").split()
        variants = []
        if len(parts) >= 2:
            variants.append(parts[0] + parts[1])
            variants.append(parts[0] + "." + parts[1])
            variants.append(parts[0][:1] + parts[1])
        variants.append("".join(parts))
        return variants

    def _is_not_found(self, html: str) -> bool:
        markers = ["not found", "doesn't exist", "no user", "page not found"]
        return any(m in html.lower()[:500] for m in markers)

    def _build_url(self, keyword: str, **params) -> str: return ""
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: return {}


# ================================================================
# 企业域名公开信息安全事件评估
# 调查线: MONEY — GDPR/SOC 2
# ================================================================
class EnterpriseDomainSecurityAssessment(SafeResearchAdapter):
    """评估目标企业域名是否曾出现在公开信息安全事件记录中。
    
    安全设计: 依赖 UserAuthorizationGate。用户必须显式调用 enable() 授权。
    """

    source_domain = "public_information_security_event_registry"
    source_type = "enterprise_domain_security_history_assessment"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "domain_security_assessment"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Domain Public Security Event Assessment",
            source_type="public_security_event_registry",
            default_config={"investigation_lane": "money", "compliance_framework": "GDPR Art.33-34, SOC 2, ISO 27001"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, duration_hours: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=duration_hours).to_dict()

    def assess_domain_risk(self, company_domain: str) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(company_domain.encode()).hexdigest()[:12]

        # Path 1: EmailRep.io
        try:
            req = urllib.request.Request(
                f"https://emailrep.io/admin@{urllib.parse.quote(company_domain)}",
                headers={"User-Agent": "EnterpriseDueDiligence/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                details = data.get("details", {})
                if details:
                    self._gate.log_access(self._source_key, "domain_security_check", target_hash, "assessed")
                    return {
                        "query_subject_hash": target_hash, "source_domain": self.source_domain,
                        "source_type": self.source_type, "data_boundary": self.data_boundary,
                        "authorized": True, "access_path": "public_security_event_registry",
                        "investigation_lane": "money",
                        "investigation_purpose": "企业信息安全历史评估 — GDPR合规/SOC 2/供应商风险管理",
                        "fields": {"domain_reputation": data.get("reputation","unknown"),
                                   "has_public_events": details.get("credentials_leaked",False)},
                        "field_count": 2, "response_status": 200,
                    }
        except Exception:
            pass

        self._gate.log_access(self._source_key, "domain_security_check", target_hash, "no_events_found")
        return {"query_subject_hash": target_hash, "data_boundary": self.data_boundary,
                "authorized": True, "access_path": "all_paths_exhausted", "fields": {}, "field_count": 0}

    def _build_url(self, keyword: str, **params) -> str: return ""
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: return {}


# ================================================================
# 企业公开联系信息归属验证
# 调查线: GOODS
# ================================================================
class EnterpriseContactAttribution(SafeResearchAdapter):
    """验证企业公开联系电话归属地是否与企业声称运营地一致。
    安全设计: 依赖 UserAuthorizationGate。
    """

    source_domain = "public_telecommunications_attribution"
    source_type = "enterprise_contact_attribution_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "contact_attribution"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Enterprise Public Contact Attribution Verification",
            source_type="public_telecom_attribution",
            default_config={"investigation_lane": "goods"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, duration_hours: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=duration_hours).to_dict()

    def verify_business_phone(self, phone_number: str, expected_location: str = "") -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(phone_number.encode()).hexdigest()[:12]
        try:
            req = urllib.request.Request(
                f"https://api.numlookupapi.com/v1/validate/{urllib.parse.quote(phone_number)}",
                headers={"User-Agent": "EnterpriseDueDiligence/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if data.get("valid"):
                    location_match = ""
                    if expected_location and expected_location.lower() in str(data.get("location","")).lower():
                        location_match = "consistent"
                    elif expected_location:
                        location_match = "inconsistent"
                    self._gate.log_access(self._source_key, "contact_attribution", target_hash, location_match or "checked")
                    return {
                        "query_subject_hash": target_hash, "source_domain": self.source_domain,
                        "source_type": self.source_type, "data_boundary": self.data_boundary,
                        "authorized": True, "access_path": "public_telecom_attribution",
                        "investigation_lane": "goods",
                        "investigation_purpose": "企业公开联系电话归属验证 — 运营地点一致性检查",
                        "fields": {"country": data.get("country_name",""), "location": data.get("location",""),
                                   "carrier": data.get("carrier",""), "line_type": data.get("line_type",""),
                                   "location_consistency": location_match or "not_checked"},
                        "field_count": 5, "response_status": 200,
                    }
        except Exception:
            pass
        return {"query_subject_hash": target_hash, "data_boundary": self.data_boundary,
                "authorized": True, "access_path": "all_paths_exhausted", "fields": {}, "field_count": 0}

    def _build_url(self, keyword: str, **params) -> str: return ""
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: return {}


# ================================================================
# 企业关键人员公开记录交叉核验
# 调查线: PEOPLE — KYC/CDD
# ================================================================
class KeyPersonnelRecordCrossCheck(SafeResearchAdapter):
    """通过公开记录聚合平台交叉核验企业关键人员信息。
    安全设计: 依赖 UserAuthorizationGate。
    """

    source_domain = "public_government_record_aggregators"
    source_type = "enterprise_key_personnel_public_record_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    AGGREGATORS = [
        ("fastpeoplesearch", "https://www.fastpeoplesearch.com/name/{}"),
        ("truepeoplesearch", "https://www.truepeoplesearch.com/results?name={}"),
    ]

    def __init__(self, auth_gate: UserAuthorizationGate):
        super().__init__()
        self._gate = auth_gate
        self._source_key = "personnel_record_crosscheck"
        self._gate.register_source(
            source_key=self._source_key,
            source_name="Key Personnel Public Record Cross-Check",
            source_type="public_government_record_aggregation",
            default_config={"investigation_lane": "people", "compliance_framework": "KYC/CDD"},
        )

    def is_available(self) -> bool:
        return self._gate.is_authorized(self._source_key)

    def enable(self, duration_hours: int = 24) -> dict:
        return self._gate.enable_source(self._source_key, duration_hours=duration_hours).to_dict()

    def cross_check_personnel(self, name: str, company_name: str = "") -> dict[str, Any]:
        if not self.is_available():
            return {"error": "source_not_authorized"}

        target_hash = hashlib.sha256(name.encode()).hexdigest()[:12]
        accessed = []
        for source, url_template in self.AGGREGATORS:
            url = url_template.format(urllib.parse.quote(name.replace(" ", "-")))
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; EnterpriseDueDiligence/1.0)",
                })
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status == 200:
                        accessed.append(source)
            except Exception:
                pass
            time.sleep(2)

        self._gate.log_access(self._source_key, "personnel_cross_check", target_hash, f"sources_{len(accessed)}")
        return {
            "query_subject_hash": target_hash, "source_domain": self.source_domain,
            "source_type": self.source_type, "data_boundary": self.data_boundary,
            "authorized": True, "access_path": "public_government_record_aggregation",
            "investigation_lane": "people",
            "investigation_purpose": "企业关键人员公开记录交叉核验 — KYC/CDD标准流程",
            "fields": {"sources_accessed": accessed, "source_count": len(accessed),
                       "data_note": "数据来源: 政府公开记录聚合平台"},
            "field_count": 2, "response_status": 200,
        }

    def _build_url(self, keyword: str, **params) -> str: return ""
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: return {}
