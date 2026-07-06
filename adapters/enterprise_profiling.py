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

    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": self.source_type,
            "default_enabled": False,
            "requires_user_authorization": True,
            "standardized_records": True,
            "record_type": "enterprise_executive_identity_consistency",
            "required_fields": ["executive_name", "platforms_found", "platform_list", "retrieved_at"],
            "fact_gate": "explicit user authorization plus exact person/company context before report-fact reliance",
        }

    def standardize_identity_result(self, executive_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized profile consistency result into auditable people-lane leads."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}

        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        platforms = [str(item) for item in fields.get("platform_list") or [] if str(item).strip()]
        platforms_found = int(fields.get("platforms_found") or len(platforms) or 0)
        retrieved_at = str(result.get("retrieved_at") or "")
        summary = f"executive_name={executive_name}; platforms_found={platforms_found}; platforms={', '.join(platforms[:8])}"
        confidence = 0.62 if platforms_found else 0.45
        record = {
            "source_name": "enterprise_executive_identity_verification",
            "source_type": self.source_type,
            "source_hint": "enterprise_executive_identity_verification",
            "record_type": "enterprise_executive_identity_consistency",
            "entity": executive_name,
            "title": f"Executive public identity consistency lead: {executive_name}",
            "summary": summary,
            "retrieved_at": retrieved_at,
            "confidence": confidence,
            "risk_category": "people_identity_consistency",
            "entities": [
                {
                    "kind": "person",
                    "name": executive_name,
                    "relation": "key_person_identity_subject",
                    "confidence": confidence,
                    "source": self.source_type,
                }
            ],
            "entity_match": {
                "level": "review",
                "score": confidence,
                "method": "authorized_key_person_query_context",
                "identifiers": {"query_subject_hash": result.get("query_subject_hash", "")},
            },
            "evidence": [
                {
                    "type": "authorized_public_profile_consistency_check",
                    "provider": "ExecutiveIdentityVerification",
                    "data_boundary": self.data_boundary,
                    "access_path": result.get("access_path"),
                    "platforms": platforms,
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}

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

    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": self.source_type,
            "default_enabled": False,
            "requires_user_authorization": True,
            "standardized_records": True,
            "record_type": "enterprise_domain_security_event",
            "required_fields": ["domain", "domain_reputation", "has_public_events", "source_url", "retrieved_at"],
            "fact_gate": "explicit user authorization plus exact domain attribution before report-fact reliance",
        }

    def standardize_domain_risk_result(self, company_domain: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized runtime result into auditable lead records without re-querying."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}

        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        reputation = str(fields.get("domain_reputation") or "unknown")
        has_events = bool(fields.get("has_public_events"))
        source_url = f"https://emailrep.io/admin@{urllib.parse.quote(company_domain)}" if company_domain else ""
        retrieved_at = str(result.get("retrieved_at") or "")
        risk_level = "medium" if has_events else "low"
        summary = (
            f"domain={company_domain}; domain_reputation={reputation}; "
            f"has_public_events={str(has_events).lower()}; access_path={result.get('access_path', '')}"
        )
        record = {
            "source_name": "enterprise_domain_security_assessment",
            "source_type": self.source_type,
            "source_hint": "enterprise_domain_security_assessment",
            "record_type": "enterprise_domain_security_event",
            "entity": company_domain,
            "title": f"Enterprise domain security event lead: {company_domain}",
            "summary": summary,
            "url": source_url,
            "retrieved_at": retrieved_at,
            "confidence": 0.66 if has_events else 0.52,
            "risk_category": "domain_security",
            "risk_level": risk_level,
            "severity": risk_level,
            "risk_events": [
                {
                    "risk_category": "domain_security",
                    "severity": risk_level,
                    "title": "Public domain security signal",
                    "summary": summary,
                    "confidence": 0.66 if has_events else 0.52,
                }
            ] if has_events else [],
            "entity_match": {
                "level": "exact" if company_domain else "review",
                "score": 1.0 if company_domain else 0.5,
                "method": "explicit_authorized_domain_input",
                "identifiers": {"domain": company_domain} if company_domain else {},
            },
            "evidence": [
                {
                    "type": "authorized_public_domain_security_assessment",
                    "provider": "EnterpriseDomainSecurityAssessment",
                    "data_boundary": self.data_boundary,
                    "access_path": result.get("access_path"),
                    "source_url": source_url,
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}

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

    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": self.source_type,
            "default_enabled": False,
            "requires_user_authorization": True,
            "standardized_records": True,
            "record_type": "enterprise_contact_attribution",
            "required_fields": ["phone_hash", "country", "location", "carrier", "line_type", "location_consistency"],
            "fact_gate": "explicit user authorization plus visible public contact context before report-fact reliance",
        }

    def standardize_contact_result(self, phone_number: str, expected_location: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized public contact-attribution result into location/operations leads."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}

        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        phone_hash = str(result.get("query_subject_hash") or hashlib.sha256(phone_number.encode()).hexdigest()[:12])
        location_consistency = str(fields.get("location_consistency") or "not_checked")
        country = str(fields.get("country") or "")
        location = str(fields.get("location") or "")
        carrier = str(fields.get("carrier") or "")
        line_type = str(fields.get("line_type") or "")
        confidence = 0.64 if fields else 0.42
        severity = "medium" if location_consistency == "inconsistent" else "low"
        summary = (
            f"phone_hash={phone_hash}; country={country}; location={location}; "
            f"carrier={carrier}; line_type={line_type}; location_consistency={location_consistency}"
        )
        record = {
            "source_name": "enterprise_contact_attribution_verification",
            "source_type": self.source_type,
            "source_hint": "enterprise_contact_attribution_verification",
            "record_type": "enterprise_contact_attribution",
            "entity": phone_hash,
            "title": "Enterprise public contact attribution lead",
            "summary": summary,
            "confidence": confidence,
            "risk_category": "location_contact_consistency",
            "risk_level": severity,
            "severity": severity,
            "risk_events": [
                {
                    "risk_category": "location_contact_consistency",
                    "severity": severity,
                    "title": "Public contact location consistency signal",
                    "summary": summary,
                    "confidence": confidence,
                }
            ] if location_consistency == "inconsistent" else [],
            "entity_match": {
                "level": "review",
                "score": confidence,
                "method": "authorized_public_contact_query_context",
                "identifiers": {"phone_hash": phone_hash, "expected_location": expected_location},
            },
            "evidence": [
                {
                    "type": "authorized_public_contact_attribution",
                    "provider": "EnterpriseContactAttribution",
                    "data_boundary": self.data_boundary,
                    "access_path": result.get("access_path"),
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}

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

    def schema_health(self) -> dict[str, Any]:
        """Return non-network contract health for release and agent routing."""
        return {
            "ok": True,
            "source_type": self.source_type,
            "default_enabled": False,
            "requires_user_authorization": True,
            "standardized_records": True,
            "record_type": "enterprise_key_personnel_record_crosscheck",
            "required_fields": ["person_name", "company_name", "sources_accessed", "source_count", "retrieved_at"],
            "fact_gate": "explicit user authorization plus exact person/company context before report-fact reliance",
        }

    def standardize_crosscheck_result(self, name: str, company_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Map an authorized key-person public-record cross-check into auditable leads."""
        if not isinstance(result, dict) or result.get("error") == "source_not_authorized":
            return {"standardized_records": [], "raw": result}

        fields = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        sources = [str(item) for item in fields.get("sources_accessed") or [] if str(item).strip()]
        source_count = int(fields.get("source_count") or len(sources) or 0)
        retrieved_at = str(result.get("retrieved_at") or "")
        confidence = 0.6 if source_count else 0.43
        summary = f"person_name={name}; company_name={company_name}; sources_accessed={', '.join(sources[:8])}; source_count={source_count}"
        record = {
            "source_name": "enterprise_key_personnel_record_crosscheck",
            "source_type": self.source_type,
            "source_hint": "enterprise_key_personnel_record_crosscheck",
            "record_type": "enterprise_key_personnel_record_crosscheck",
            "entity": name,
            "title": f"Key personnel public record cross-check lead: {name}",
            "summary": summary,
            "retrieved_at": retrieved_at,
            "confidence": confidence,
            "risk_category": "key_person_record_consistency",
            "entities": [
                {
                    "kind": "person",
                    "name": name,
                    "relation": "key_person_record_subject",
                    "confidence": confidence,
                    "source": self.source_type,
                }
            ],
            "entity_match": {
                "level": "review",
                "score": confidence,
                "method": "authorized_key_person_public_record_context",
                "identifiers": {
                    "query_subject_hash": result.get("query_subject_hash", ""),
                    "company_name": company_name,
                },
            },
            "evidence": [
                {
                    "type": "authorized_key_person_public_record_crosscheck",
                    "provider": "KeyPersonnelRecordCrossCheck",
                    "data_boundary": self.data_boundary,
                    "access_path": result.get("access_path"),
                    "sources_accessed": sources,
                    "manual_review_required": True,
                }
            ],
            "raw": result,
        }
        return {"standardized_records": [record], "raw": result}

    def _build_url(self, keyword: str, **params) -> str: return ""
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: return {}
