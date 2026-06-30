#!/usr/bin/env python3
"""ToolProvider bridge for QYYJT retrieval plans and records."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from core.interfaces import ToolProvider, ToolResult
from core.record_quality import audit_standardized_records
from core.source_admission import SourceAdmissionEvaluator
from core.qyyjt_benchmark import build_qyyjt_benchmark

from .qyyjt_adapter import QYYJTAdapter, QYYJTModule

logger = logging.getLogger("wst.qyyjt_tool")


DEFAULT_MODULES = (
    QYYJTModule.RISK_SCAN,
    QYYJTModule.COURT_CASES,
    QYYJTModule.NEWS_NEGATIVE,
    QYYJTModule.ACTUAL_CONTROLLER,
    QYYJTModule.RELATED_PARTIES,
)


class QYYJTTool(ToolProvider):
    """Expose QYYJT as a standard ToolProvider for risk discovery."""

    def __init__(
        self,
        *,
        adapter: QYYJTAdapter | None = None,
        modules: list[QYYJTModule] | None = None,
        prefer_api: bool = False,
    ):
        self.adapter = adapter or QYYJTAdapter()
        self.modules = modules or list(DEFAULT_MODULES)
        self.prefer_api = prefer_api
        self._available = {"qyyjt", "enterprise_warning", "multi_datasource", "mds"}

    def available_tools(self) -> set[str]:
        return set(self._available)

    async def health_check(self, *, check_cookie: bool = False) -> dict[str, Any]:
        """Return a non-invasive health snapshot for the QYYJT bridge."""
        module_queries_ok = True
        errors: list[str] = []
        try:
            for module in self.modules:
                query_info = self.adapter.get_module_query(module, "healthcheck")
                if not query_info.get("queries"):
                    module_queries_ok = False
                    errors.append(f"module_without_queries:{module.value}")
        except Exception as exc:
            module_queries_ok = False
            errors.append(f"module_query_error:{type(exc).__name__}")

        cookie_valid = None
        if check_cookie:
            try:
                cookie_valid = await self.adapter.cookie_manager.test_cookies_valid()
            except Exception as exc:
                cookie_valid = False
                errors.append(f"cookie_check_error:{type(exc).__name__}")

        ok = module_queries_ok and (cookie_valid is not False)
        return {
            "ok": ok,
            "module_queries_ok": module_queries_ok,
            "cookie_checked": check_cookie,
            "cookie_valid": cookie_valid,
            "standardized_records": True,
            "errors": errors,
        }

    async def authorization_report(
        self,
        *,
        company: str = "healthcheck",
        smoke_api: bool = False,
        terms_reviewed: bool = False,
        authorization_evidence: str = "",
    ) -> dict[str, Any]:
        """Return a structured live-authorization readiness report."""
        health = await self.health_check(check_cookie=True)
        report: dict[str, Any] = {
            "ok": bool(health["ok"]),
            "company": company,
            "cookie_checked": True,
            "cookie_valid": health.get("cookie_valid"),
            "module_queries_ok": health.get("module_queries_ok"),
            "standardized_records": True,
            "smoke_api": {
                "enabled": smoke_api,
                "attempted": False,
                "ok": None,
                "error_type": "",
            },
            "errors": list(health.get("errors", [])),
            "next_action": "ready" if health.get("cookie_valid") else "provide_or_refresh_user_authorized_cookie",
        }
        if smoke_api and health.get("cookie_valid"):
            report["smoke_api"]["attempted"] = True
            try:
                payload = await self.adapter.query(
                    company,
                    modules=[QYYJTModule.SEARCH_MULTI],
                    prefer_api=True,
                )
                ok = payload.get("source") in {"api", "mixed"} and bool(payload.get("api_data"))
                report["smoke_api"]["ok"] = ok
                report["api_source"] = payload.get("source")
                report["api_keys"] = sorted((payload.get("api_data") or {}).keys())
                if not ok:
                    report["errors"].append("api_smoke_returned_no_data")
                    report["next_action"] = "verify_qyyjt_api_permissions_or_endpoint_mapping"
            except Exception as exc:
                report["smoke_api"]["ok"] = False
                report["smoke_api"]["error_type"] = type(exc).__name__
                report["errors"].append(f"api_smoke_error:{type(exc).__name__}")
                report["next_action"] = "verify_qyyjt_cookie_and_api_permissions"
        report["ok"] = bool(report.get("cookie_valid")) and not report["errors"]
        report["admission"] = SourceAdmissionEvaluator().evaluate(
            SourceAdmissionEvaluator.qyyjt_admission_input(
                authorization_evidence=authorization_evidence
                or (
                    "cookie_validated"
                    if report.get("cookie_valid")
                    else ""
                ),
                terms_reviewed=terms_reviewed,
                live_validation_ok=bool(report.get("cookie_valid")) and not report["errors"],
            )
        ).to_dict()
        benchmark = build_qyyjt_benchmark()
        report["benchmark"] = {
            "type": benchmark["type"],
            "version": benchmark["version"],
            "summary": benchmark["summary"],
        }
        return report

    async def search(self, query: str, tool_type: str = "qyyjt", **kwargs: Any) -> ToolResult:
        if tool_type not in self._available:
            return ToolResult(
                ok=False,
                error=f"unsupported QYYJT tool type: {tool_type}",
                data={"query": query, "tool_type": tool_type},
                sources=["qyyjt:error"],
            )

        company = str(kwargs.get("company") or query).strip()
        modules = self._parse_modules(kwargs.get("modules")) or self.modules
        prefer_api = bool(kwargs.get("prefer_api", self.prefer_api))

        try:
            raw = await self.adapter.query(company, modules=modules, prefer_api=prefer_api)
        except Exception as exc:
            logger.warning("QYYJT query failed: %s", type(exc).__name__)
            return ToolResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                data={"query": query, "company": company},
                sources=["qyyjt:error"],
            )

        records = qyyjt_result_to_standardized_records(raw)
        quality = audit_standardized_records(records)
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "company": company,
                "source_name": "qyyjt",
                "source_type": "tool_provider",
                "standardized_records": records,
                "record_quality": quality.to_dict(),
                "raw": raw,
            },
            sources=["qyyjt:standardized_records"],
        )

    @staticmethod
    def _parse_modules(raw_modules: Any) -> list[QYYJTModule] | None:
        if not raw_modules:
            return None
        parsed: list[QYYJTModule] = []
        for item in raw_modules:
            if isinstance(item, QYYJTModule):
                parsed.append(item)
                continue
            try:
                parsed.append(QYYJTModule(str(item)))
            except ValueError:
                try:
                    parsed.append(QYYJTModule[str(item)])
                except KeyError:
                    logger.warning("Ignoring unknown QYYJT module: %s", item)
        return parsed


def qyyjt_result_to_standardized_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map QYYJT output into evidence-pipeline standardized records.

    API payloads can be treated as source records. WebSearch fallback items are
    marked as query-plan leads with lower confidence so they do not masquerade
    as verified evidence.
    """
    company = str(payload.get("company") or "").strip()
    records: list[dict[str, Any]] = []

    api_data = payload.get("api_data")
    if isinstance(api_data, dict):
        for key, value in api_data.items():
            if value in ({}, [], None):
                continue
            contract = _qyyjt_contract_for_key(key)
            record_units = _qyyjt_record_units(value)
            for index, record_value in enumerate(record_units, start=1):
                raw_value = value if len(record_units) == 1 else record_value
                extracted_fields = _infer_qyyjt_contract_fields(
                    key,
                    contract,
                    _extract_qyyjt_contract_fields(record_value, contract),
                )
                source_url = (
                    _qyyjt_source_url(record_value)
                    or _qyyjt_source_url(value)
                    or _qyyjt_module_source_url(key)
                )
                confidence = _qyyjt_confidence(contract, extracted_fields)
                provenance = _qyyjt_common_provenance(
                    company=company,
                    key=key,
                    record_value=record_value,
                    parent_value=value,
                    payload=payload,
                    confidence=confidence,
                    source_url=source_url,
                )
                report_admission = _qyyjt_report_admission(contract, extracted_fields, provenance)
                claims = [
                    {"claim": f"QYYJT API module returned non-empty data for {company}."},
                    *[
                        {"claim": f"{field}={extracted_fields[field]}"}
                        for field in [
                            *list(contract.get("required_fields", [])),
                            *list(contract.get("optional_fields", [])),
                        ]
                        if str(extracted_fields.get(field) or "").strip()
                    ],
                    *[
                        {"claim": f"{field}={provenance[field]}"}
                        for field in ("source_name", "observed_at", "verification_status")
                        if str(provenance.get(field) or "").strip()
                    ],
                ]
                if source_url:
                    claims.append({"claim": f"source_url={source_url}"})
                title = f"QYYJT API result: {key}"
                if len(record_units) > 1:
                    title = f"{title} #{index}"
                records.append(
                    {
                        "source_name": f"qyyjt_api:{key}",
                        "source_type": "licensed_api",
                        "source_hint": "registry_and_commercial_sources",
                        "entity": company,
                        "title": title,
                        "url": source_url,
                        "published_at": provenance.get("published_at"),
                        "retrieved_at": provenance.get("retrieved_at"),
                        "summary": _qyyjt_api_summary(key, contract, extracted_fields),
                        "confidence": confidence,
                        "evidence": claims,
                        "source_url": source_url,
                        "verification_status": provenance.get("verification_status"),
                        "qyyjt_provenance": provenance,
                        "qyyjt_module": key,
                        "field_contract": contract,
                        "extracted_fields": extracted_fields,
                        "report_admission": report_admission,
                        **_qyyjt_structured_payload(company, key, contract, extracted_fields, report_admission),
                        "raw": raw_value,
                    }
                )

    for item in payload.get("websearch_queries") or []:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        module = str(item.get("module") or "unknown")
        module_name = str(item.get("module_name") or module)
        note = str(item.get("note") or "").strip()
        records.append(
            {
                "source_name": "qyyjt_websearch_plan",
                "source_type": "query_plan",
                "source_hint": "web_search",
                "entity": company,
                "title": f"QYYJT lead: {module_name}",
                "summary": query,
                "confidence": 0.3,
                "evidence": [
                    {"claim": "QYYJT fallback generated a public-search lead, not a verified fact."},
                    {"claim": query},
                    *([{"claim": note}] if note else []),
                ],
                "raw": item,
            }
        )

    return records


def _qyyjt_contract_for_key(key: str) -> dict[str, Any]:
    benchmark = build_qyyjt_benchmark()
    contracts = benchmark.get("summary", {}).get("field_contracts", {})
    normalized_key = {"search": "search_multi"}.get(str(key), str(key))
    contract = contracts.get(normalized_key)
    if isinstance(contract, dict):
        return contract
    return {
        "record_type": f"{key}_api_payload",
        "required_fields": [],
        "required_common_fields": [
            "subject_name",
            "source_name",
            "source_url",
            "observed_at",
            "confidence",
            "verification_status",
        ],
        "report_section": "follow_up_leads",
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }


def _extract_qyyjt_contract_fields(value: Any, contract: dict[str, Any]) -> dict[str, Any]:
    fields = [
        str(item)
        for item in [
            *list(contract.get("required_fields", [])),
            *list(contract.get("optional_fields", [])),
        ]
        if str(item).strip()
    ]
    if not fields:
        return {}
    records = _qyyjt_payload_records(value)
    extracted: dict[str, Any] = {}
    for field in fields:
        aliases = _qyyjt_field_aliases(field)
        for record in records:
            found = _first_present(record, aliases)
            if found not in (None, ""):
                extracted[field] = found
                break
    return extracted


def _infer_qyyjt_contract_fields(
    key: str,
    contract: dict[str, Any],
    extracted_fields: dict[str, Any],
) -> dict[str, Any]:
    """Fill safe module-specific defaults needed for report admission."""
    record_type = str(contract.get("record_type") or "")
    fields = dict(extracted_fields)
    if record_type == "related_party_edge":
        if fields.get("related_name") and not fields.get("relationship_direction"):
            fields["relationship_direction"] = "subject_to_related"
        if fields.get("related_name") and not fields.get("confidence_basis"):
            fields["confidence_basis"] = f"licensed QYYJT {key} module"
    return fields


def _qyyjt_payload_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("list", "records", "data", "items", "rows", "result"):
            nested = value.get(key)
            if isinstance(nested, list):
                rows = [item for item in nested if isinstance(item, dict)]
                if rows:
                    return rows
            if isinstance(nested, dict):
                return [nested]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _qyyjt_record_units(value: Any) -> list[Any]:
    records = _qyyjt_payload_records(value)
    if records:
        return records
    return [value]


def _qyyjt_source_url(value: Any) -> str | None:
    for record in _qyyjt_payload_records(value):
        url = _first_present(record, ("source_url", "sourceUrl", "url", "detailUrl", "link"))
        if url:
            return str(url)
    return None


def _qyyjt_module_source_url(key: str) -> str:
    return f"https://qyyjt.cn/modules/{str(key).strip() or 'unknown'}"


def _qyyjt_observed_at(record: dict[str, Any]) -> str | None:
    value = _first_present(
        record,
        (
            "observed_at",
            "observedAt",
            "retrieved_at",
            "retrievedAt",
            "published_at",
            "publishedAt",
            "publishDate",
            "date",
            "caseDate",
            "filingDate",
            "decisionDate",
            "referenceDate",
            "reportDate",
        ),
    )
    return str(value) if value not in (None, "") else None


def _qyyjt_verification_status(
    *,
    source_url: str | None,
    confidence: float,
    payload: dict[str, Any],
) -> str:
    cookie_valid = payload.get("cookie_valid")
    source = str(payload.get("source") or "")
    if cookie_valid is True and source_url and confidence >= 0.72:
        return "licensed_api_with_source_url"
    if cookie_valid is True and confidence >= 0.72:
        return "licensed_api_field_contract"
    if source in {"api", "mixed"} and source_url:
        return "api_payload_with_source_url"
    return "api_payload_field_contract"


def _qyyjt_common_provenance(
    *,
    company: str,
    key: str,
    record_value: Any,
    parent_value: Any,
    payload: dict[str, Any],
    confidence: float,
    source_url: str | None,
) -> dict[str, Any]:
    record = _qyyjt_payload_records(record_value)[0] if _qyyjt_payload_records(record_value) else {}
    parent_record = _qyyjt_payload_records(parent_value)[0] if _qyyjt_payload_records(parent_value) else {}
    observed_at = _qyyjt_observed_at(record) or _qyyjt_observed_at(parent_record)
    retrieved_at = str(payload.get("retrieved_at") or payload.get("timestamp") or "").strip()
    if not retrieved_at:
        retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "subject_name": company,
        "source_name": f"qyyjt_api:{key}",
        "source_url": source_url,
        "observed_at": observed_at or retrieved_at,
        "published_at": observed_at,
        "retrieved_at": retrieved_at,
        "confidence": confidence,
        "verification_status": _qyyjt_verification_status(
            source_url=source_url,
            confidence=confidence,
            payload=payload,
        ),
        "authorization_state": "user_authorized" if payload.get("cookie_valid") is True else "unknown_or_fixture",
    }


def _first_present(record: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for alias in aliases:
        if alias in record and record[alias] not in (None, ""):
            return record[alias]
        value = lowered.get(alias.lower())
        if value not in (None, ""):
            return value
    return None


def _qyyjt_field_aliases(field: str) -> tuple[str, ...]:
    aliases = {
        "candidate_name": ("candidate_name", "name", "entName", "companyName", "title"),
        "identifier": ("identifier", "creditCode", "unifiedSocialCreditCode", "uscc", "code", "regNo"),
        "entity_type": ("entity_type", "type", "entityType", "subjectType"),
        "match_score": ("match_score", "score", "matchScore"),
        "risk_category": ("risk_category", "category", "riskType", "type"),
        "severity": ("severity", "level", "riskLevel", "grade"),
        "risk_label": ("risk_label", "label", "riskLabel", "tag"),
        "summary": ("summary", "desc", "description", "content"),
        "status": ("status", "state"),
        "signal_code": ("signal_code", "signalCode", "code"),
        "signal_label": ("signal_label", "signalLabel", "label"),
        "signal_summary": ("signal_summary", "summary", "desc", "description"),
        "person_name": ("person_name", "personName", "name", "controller", "actualController", "actualControllerName", "controllerName"),
        "relation_type": ("relation_type", "relationType", "transaction_type", "transactionType", "role", "roleName", "type"),
        "control_path": ("control_path", "controlPath", "path", "pathNodes", "nodes", "controlChain"),
        "confidence_basis": ("confidence_basis", "basis", "reason", "confidenceBasis", "sourceBasis"),
        "case_number": ("case_number", "caseNo", "caseNumber", "docket"),
        "court": ("court", "courtName"),
        "cause": ("cause", "caseCause", "reason"),
        "parties": ("parties", "party", "litigants"),
        "case_date": ("case_date", "caseDate", "date"),
        "case_status": ("case_status", "caseStatus", "status"),
        "hearing_date": ("hearing_date", "hearingDate", "openDate", "courtDate", "date"),
        "obligation": ("obligation", "duty", "obligationDesc"),
        "publish_date": ("publish_date", "publishDate", "date"),
        "performance_status": ("performance_status", "performanceStatus", "status"),
        "restricted_subject": ("restricted_subject", "subject", "name"),
        "amount": ("amount", "execMoney", "money", "caseAmount", "financing_amount", "financingAmount"),
        "filing_date": ("filing_date", "filingDate", "caseDate", "date"),
        "execution_status": ("execution_status", "executionStatus", "status"),
        "legal_name": ("legal_name", "name", "entName", "companyName", "enterpriseName"),
        "legal_representative": ("legal_representative", "legalRep", "legalRepName", "legalPerson", "frName"),
        "registered_address": ("registered_address", "address", "regAddress"),
        "registered_capital": ("registered_capital", "regCapital", "registeredCapital", "capital", "regCap"),
        "establishment_date": ("establishment_date", "estiblishTime", "establishTime", "establishedDate", "setupDate", "startDate"),
        "operating_period": ("operating_period", "operatingPeriod", "businessTerm", "term", "opFrom", "opTo"),
        "registration_authority": ("registration_authority", "regInstitute", "registrationAuthority", "authority", "regOrg"),
        "business_scope": ("business_scope", "businessScope", "scope", "opscope", "经营范围"),
        "company_type": ("company_type", "companyType", "entType", "enterpriseType", "type"),
        "credit_section": ("credit_section", "section", "module"),
        "credit_item": ("credit_item", "item", "name"),
        "credit_status": ("credit_status", "status", "state"),
        "reference_date": ("reference_date", "date", "referenceDate"),
        "agency": ("agency", "org", "authority", "department"),
        "decision_number": ("decision_number", "decisionNo", "documentNo", "caseNo"),
        "violation": ("violation", "illegalFact", "reason"),
        "penalty": ("penalty", "penaltyContent", "punishment"),
        "decision_date": ("decision_date", "decisionDate", "date"),
        "related_name": ("related_name", "relatedName", "related_entity", "relatedEntity", "counterparty", "name", "targetName"),
        "relationship_direction": ("relationship_direction", "direction", "edgeDirection", "relationDirection"),
        "beneficial_owner": ("beneficial_owner", "ubo", "owner", "name", "beneficialOwner", "beneficialOwnerName", "ultimateBeneficialOwner"),
        "path_nodes": ("path_nodes", "path", "nodes", "pathNodes", "controlChain"),
        "ownership_ratio": ("ownership_ratio", "ratio", "shareRatio", "holdingRatio", "percent"),
        "layer_depth": ("layer_depth", "depth", "level", "layer"),
        "from_entity": ("from_entity", "from", "source", "fromName", "sourceName"),
        "to_entity": ("to_entity", "to", "target", "name", "toName", "targetName"),
        "control_or_affiliation_basis": ("control_or_affiliation_basis", "basis", "reason", "confidenceBasis"),
        "period": ("period", "date", "reportDate", "year"),
        "metric": ("metric", "metric_name", "metricName", "name", "item"),
        "value": ("value", "metric_value", "metricValue", "indicator_value", "indicatorValue", "amount", "val"),
        "unit": ("unit",),
        "accounting_scope": ("accounting_scope", "accountingScope", "scope"),
        "indicator": ("indicator", "indicator_name", "indicatorName", "name", "item"),
        "meaning": ("meaning", "desc", "description"),
        "financing_type": ("financing_type", "financingType", "financeType", "type", "module"),
        "counterparty": ("counterparty", "lender", "investor", "guarantor", "pledgee", "party"),
        "event_date": ("event_date", "eventDate", "financing_date", "financingDate", "date", "publishDate"),
        "event_type": ("event_type", "eventType", "calendarType", "type", "action"),
        "announcement_date": ("announcement_date", "announcementDate", "announceDate", "publishDate", "date"),
        "transaction_subject": ("transaction_subject", "targetAsset", "subjectMatter", "targetName", "assetName"),
        "change_item": ("change_item", "changeItem", "item", "field", "changeMatter"),
        "before_value": ("before_value", "before", "oldValue", "changeBefore"),
        "after_value": ("after_value", "after", "newValue", "changeAfter"),
        "change_date": ("change_date", "changeDate", "date", "publishDate"),
        "news_title": ("news_title", "title", "newsTitle", "headline"),
        "publisher": ("publisher", "source", "media", "org", "author"),
        "sentiment": ("sentiment", "tone", "riskLevel", "label"),
        "report_title": ("report_title", "title", "reportTitle"),
        "industry": ("industry", "industryName", "sector"),
        "product": ("product", "productName", "coreProduct"),
        "industry_growth": ("industry_growth", "industryGrowth", "growth", "growthRate"),
        "customer_value": ("customer_value", "customerValue", "userValue", "value"),
        "substitution_risk": ("substitution_risk", "substitutionRisk", "replaceRisk", "risk"),
        "bond_name": ("bond_name", "bondName", "name", "securityName", "债券名称"),
        "bond_code": ("bond_code", "bondCode", "code", "securityCode"),
        "issuer": ("issuer", "issuerName", "companyName", "entName"),
        "maturity_date": ("maturity_date", "maturityDate", "dueDate"),
        "coupon_rate": ("coupon_rate", "couponRate", "rate"),
        "bond_status": ("bond_status", "status", "state"),
        "issue_amount": ("issue_amount", "issueAmount", "amount", "money"),
        "issue_date": ("issue_date", "issueDate", "date", "publishDate"),
        "rating": ("rating", "creditRating", "rateLevel", "grade"),
        "rating_agency": ("rating_agency", "ratingAgency", "agency", "org"),
        "rating_date": ("rating_date", "ratingDate", "date"),
        "outlook": ("outlook", "ratingOutlook"),
        "rating_reason": ("rating_reason", "reason", "summary", "desc"),
        "default_date": ("default_date", "defaultDate", "eventDate", "date"),
        "region_name": ("region_name", "regionName", "areaName", "cityName", "provinceName", "name"),
        "region_code": ("region_code", "regionCode", "areaCode", "code"),
        "parent_region": ("parent_region", "parentRegion", "parentName", "province"),
        "debt_ratio": ("debt_ratio", "debtRatio", "debtRate", "debtBurdenRatio"),
        "debt_balance": ("debt_balance", "debtBalance", "debtAmount", "debt"),
        "fiscal_revenue": ("fiscal_revenue", "fiscalRevenue", "publicBudgetRevenue", "revenue"),
        "gdp": ("gdp", "regionalGdp", "GDP"),
        "risk_level": ("risk_level", "riskLevel", "level", "rating", "grade", "status"),
        "shareholder": ("shareholder", "shareholderName", "holder", "pledgor"),
        "pledgee": ("pledgee", "pledgeeName", "creditor"),
        "pledged_amount": ("pledged_amount", "pledgedAmount", "amount", "shares", "shareAmount"),
        "pledge_date": ("pledge_date", "pledgeDate", "startDate", "date"),
        "subject": ("subject", "freeze_subject", "freezeSubject", "name", "entity", "personName", "companyName"),
        "frozen_amount": ("frozen_amount", "freeze_amount", "freezeAmount", "frozenAmount", "amount", "shares", "shareAmount"),
        "freeze_date": ("freeze_date", "freezeDate", "date"),
        "asset_name": ("asset_name", "auction_subject", "auctionSubject", "assetName", "name", "title"),
        "asset_type": ("asset_type", "assetType", "type"),
        "auction_date": ("auction_date", "auctionDate", "date"),
        "land_location": ("land_location", "landLocation", "location", "address"),
        "area": ("area", "landArea", "acreage"),
        "acquisition_date": ("acquisition_date", "acquisitionDate", "date"),
        "land_use": ("land_use", "landUse", "usage", "purpose"),
        "tax_item": ("tax_item", "taxItem", "item", "name"),
        "tax_status": ("tax_status", "taxStatus", "status", "state"),
        "trade_type": ("trade_type", "tradeType", "type"),
        "country": ("country", "region", "market"),
        "ip_type": ("ip_type", "ipType", "type"),
        "ip_title": ("ip_title", "ipTitle", "title", "name"),
        "registration_number": ("registration_number", "registrationNumber", "regNo", "certNo", "patentNo"),
        "application_date": ("application_date", "applicationDate", "applyDate", "date"),
        "owner": ("owner", "ownerName", "applicant", "holder"),
        "position": ("position", "jobTitle", "title", "name"),
        "location": ("location", "city", "address"),
        "headcount": ("headcount", "count", "recruitCount", "number"),

        # financial_institution_profile
        "institution_name": ("institution_name", "institutionName", "name", "instName", "银行名称", "机构名称"),
        "institution_type": ("institution_type", "institutionType", "instType", "type", "机构类型", "银行类型"),
        "license_status": ("license_status", "licenseStatus", "licStatus", "status", "牌照状态"),
        "region": ("region", "area", "city", "province", "regionName", "所在地区"),
        "risk_level": ("risk_level", "riskLevel", "level", "rating", "grade", "status", "风险等级"),
        "registration_number": ("registration_number", "registrationNumber", "regNo", "certNo", "patentNo", "许可证号"),
        "regulatory_authority": ("regulatory_authority", "regulatoryAuthority", "regulator", "authority", "监管机构"),
        "counterparty_role": ("counterparty_role", "counterpartyRole", "role", "relation", "对手方角色"),
        "credit_line": ("credit_line", "creditLine", "creditAmount", "facility", "授信额度"),
        "guarantee_status": ("guarantee_status", "guaranteeStatus", "guarantee", "担保状态"),
        "source_provenance": ("source_provenance", "sourceProvenance", "provenance", "数据来源"),
    }
    return aliases.get(field, (field,))


def _qyyjt_api_summary(key: str, contract: dict[str, Any], extracted_fields: dict[str, Any]) -> str:
    missing = [
        field
        for field in contract.get("required_fields", [])
        if not str(extracted_fields.get(field) or "").strip()
    ]
    if missing:
        return (
            f"Enterprise-warning API returned {key}; field contract still needs: "
            + ", ".join(str(item) for item in missing[:6])
        )
    return f"Enterprise-warning API returned {key} with required field contract coverage."


def _qyyjt_confidence(contract: dict[str, Any], extracted_fields: dict[str, Any]) -> float:
    record_type = str(contract.get("record_type") or "")
    if record_type == "subject_resolution_candidate":
        return max(0.5, min(0.98, _float_or_default(extracted_fields.get("match_score"), 0.72)))
    if record_type in {"controller_candidate", "ubo_path"}:
        return 0.82
    if record_type in {"registry_identity", "related_party_edge", "group_network_edge"}:
        return 0.78
    if record_type in {
        "court_case",
        "dishonesty_record",
        "limit_high_consumption",
        "enforcement_record",
        "administrative_penalty",
        "court_announcement",
        "credit_profile",
        "financing_event",
        "registry_change_event",
        "negative_public_opinion",
        "research_report_signal",
        "bond_profile",
        "bond_rating",
        "bond_issue",
        "bond_default_event",
        "bond_calendar_event",
        "merger_restructuring_event",
        "regional_credit_indicator",
        "equity_pledge",
        "asset_freeze",
        "equity_freeze",
        "judicial_auction",
        "land_asset",
        "tax_profile",
        "trade_activity",
        "ip_asset",
        "recruiting_signal",
    }:
        return 0.74
    return 0.72


def _qyyjt_report_admission(
    contract: dict[str, Any],
    extracted_fields: dict[str, Any],
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    required = [str(item) for item in contract.get("required_fields", []) if str(item).strip()]
    missing = [field for field in required if not str(extracted_fields.get(field) or "").strip()]
    provenance = provenance or {}
    required_common = [
        str(item) for item in contract.get("required_common_fields", [])
        if str(item).strip()
    ]
    missing_common = [
        field for field in required_common
        if not str(provenance.get(field) or "").strip()
    ]
    return {
        "admissible": not missing and not missing_common and bool(required),
        "report_section": contract.get("report_section"),
        "record_type": contract.get("record_type"),
        "missing_required_fields": missing,
        "missing_common_fields": missing_common,
        "provenance": provenance,
        "gate": contract.get("report_gate"),
    }



# Map benchmark record_type to handler dispatch name
_QYYJT_RECORD_MAP = {
    "equity_pledge": "pledge",
    "equity_freeze": "freeze",
    "asset_freeze": "freeze",
    "judicial_auction": "auction",
    "related_party_transaction": "related_party",
    "bond_default_event": "bond_default",
    "bond_calendar_event": "bond_calendar",
    "trade_activity": "trade",
    "tax_profile": "tax",
    "ip_asset": "ip",
    "financial_institution_profile": "fin_inst",
    "ubo_path": "ubo_path",
    "group_network_edge": "group_network",
    "recruiting_signal": "recruiting",
    "financial_statement_metric": "financial_statement",
    "financial_indicator": "financial_indicator",
    "regional_credit_indicator": "regional_credit",
    "credit_profile": "credit_profile",
    "financing_event": "financing_event",
    "research_report_signal": "research_report",
    "negative_public_opinion": "negative_public_opinion",
    "news_opinion_event": "news_opinion",
    "merger_restructuring_event": "merger",
    "court_announcement": "court_announcement",
    "court_case": "court_case",
    "administrative_penalty": "administrative_penalty",
    "enforcement_record": "enforcement",
    "dishonesty_record": "dishonesty",
    "limit_high_consumption": "limit_high_consumption",
    "registry_change_event": "registry_change",
    "subject_resolution_candidate": "subject_resolution",
    "risk_overview": "risk_overview",
    "risk_signal": "risk_signal",
    "controller_candidate": "controller_candidate",
    "registry_identity": "registry_identity",
}

def _qyyjt_structured_payload(
    company: str,
    key: str,
    contract: dict[str, Any],
    extracted_fields: dict[str, Any],
    report_admission: dict[str, Any],
) -> dict[str, Any]:
    if not report_admission.get("admissible"):
        return {}

    record_type = str(contract.get("record_type") or "")
    if record_type == "subject_resolution_candidate":
        match_score = _float_or_default(extracted_fields.get("match_score"), 0.0)
        level = _subject_resolution_level(match_score)
        payload: dict[str, Any] = {
            "entity_match": {
                "level": level,
                "score": match_score,
                "basis": "qyyjt_search_multi_candidate",
                "identifier": extracted_fields.get("identifier"),
                "entity_type": extracted_fields.get("entity_type"),
            },
        }
        if level in {"exact", "strong"}:
            payload["entities"] = [
                {
                    "kind": "company",
                    "name": extracted_fields.get("candidate_name") or company,
                    "relation": "subject_resolution_candidate",
                    "confidence": max(0.5, min(0.98, match_score or 0.72)),
                    "identifier": extracted_fields.get("identifier"),
                    "entity_type": extracted_fields.get("entity_type"),
                    "match_score": match_score,
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "risk_overview":
        return {
            "risk_events": [
                {
                    "risk_category": extracted_fields.get("risk_category"),
                    "severity": extracted_fields.get("severity"),
                    "title": extracted_fields.get("risk_label") or f"QYYJT risk signal: {key}",
                    "summary": extracted_fields.get("summary"),
                    "status": extracted_fields.get("status"),
                    "confidence": 0.72,
                }
            ]
        }

    if record_type == "risk_signal":
        return {
            "risk_events": [
                {
                    "risk_category": extracted_fields.get("signal_code") or "risk_signal",
                    "severity": extracted_fields.get("severity"),
                    "title": extracted_fields.get("signal_label") or f"QYYJT risk signal: {key}",
                    "summary": extracted_fields.get("signal_summary"),
                    "status": "open",
                    "confidence": 0.72,
                }
            ]
        }

    if record_type == "controller_candidate":
        control_path = str(extracted_fields.get("control_path") or "").strip()
        return {
            "entities": [
                {
                    "kind": "person",
                    "name": extracted_fields.get("person_name"),
                    "relation": extracted_fields.get("relation_type") or "actual_controller_candidate",
                    "confidence": 0.82,
                    "control_path": control_path,
                    "confidence_basis": extracted_fields.get("confidence_basis"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "relations": _qyyjt_control_path_relations(
                company=company,
                path_nodes=control_path,
                fallback_to=extracted_fields.get("person_name"),
                relation_type=extracted_fields.get("relation_type") or "actual_controller_candidate",
                confidence=0.82,
                confidence_basis=extracted_fields.get("confidence_basis"),
            ),
        }

    if record_type == "registry_identity":
        entities: list[dict[str, Any]] = []
        representative = extracted_fields.get("legal_representative")
        if representative:
            entities.append(
                {
                    "kind": "person",
                    "name": representative,
                    "relation": "legal_representative",
                    "confidence": 0.72,
                    "source": f"qyyjt_api:{key}",
                }
            )
        address = extracted_fields.get("registered_address")
        if address:
            entities.append(
                {
                    "kind": "address",
                    "name": address,
                    "relation": "registered_address",
                    "confidence": 0.68,
                    "source": f"qyyjt_api:{key}",
                }
            )
        payload: dict[str, Any] = {
            "legal_name": extracted_fields.get("legal_name") or company,
            "unified_social_credit_code": extracted_fields.get("identifier"),
            "status": extracted_fields.get("status"),
        }
        for field in (
            "registered_capital",
            "establishment_date",
            "operating_period",
            "registration_authority",
            "business_scope",
            "company_type",
        ):
            value = extracted_fields.get(field)
            if value not in (None, ""):
                payload[field] = value
        if entities:
            payload["entities"] = entities
        return payload

    if record_type == "court_case":
        return {
            "entities": [
                {
                    "kind": "case",
                    "name": extracted_fields.get("case_number"),
                    "relation": "court_case",
                    "confidence": 0.72,
                    "court": extracted_fields.get("court"),
                    "case_status": extracted_fields.get("case_status"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "court_enforcement",
                    "severity": "medium",
                    "title": f"Court case: {extracted_fields.get('case_number')}",
                    "summary": _join_present(
                        "court",
                        extracted_fields.get("court"),
                        "cause",
                        extracted_fields.get("cause"),
                        "parties",
                        extracted_fields.get("parties"),
                        "date",
                        extracted_fields.get("case_date"),
                        "status",
                        extracted_fields.get("case_status"),
                    ),
                    "status": extracted_fields.get("case_status"),
                    "confidence": 0.72,
                }
            ],
        }

    if record_type == "court_announcement":
        return {
            "entities": [
                {
                    "kind": "case",
                    "name": extracted_fields.get("case_number"),
                    "relation": "court_announcement",
                    "confidence": 0.72,
                    "court": extracted_fields.get("court"),
                    "case_status": extracted_fields.get("status"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "court_enforcement",
                    "severity": "medium",
                    "title": f"Court announcement: {extracted_fields.get('case_number')}",
                    "summary": _join_present(
                        "court",
                        extracted_fields.get("court"),
                        "cause",
                        extracted_fields.get("cause"),
                        "parties",
                        extracted_fields.get("parties"),
                        "hearing_date",
                        extracted_fields.get("hearing_date"),
                        "status",
                        extracted_fields.get("status"),
                    ),
                    "status": extracted_fields.get("status"),
                    "confidence": 0.72,
                }
            ],
        }

    if record_type == "dishonesty_record":
        return {
            "entities": [
                {
                    "kind": "case",
                    "name": extracted_fields.get("case_number"),
                    "relation": "dishonesty_record",
                    "confidence": 0.74,
                    "court": extracted_fields.get("court"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "court_enforcement",
                    "severity": "high",
                    "title": f"Dishonesty record: {extracted_fields.get('case_number')}",
                    "summary": _join_present(
                        "court",
                        extracted_fields.get("court"),
                        "obligation",
                        extracted_fields.get("obligation"),
                        "publish_date",
                        extracted_fields.get("publish_date"),
                        "performance_status",
                        extracted_fields.get("performance_status"),
                    ),
                    "status": extracted_fields.get("performance_status"),
                    "confidence": 0.74,
                }
            ],
        }

    if record_type == "limit_high_consumption":
        return {
            "entities": [
                {
                    "kind": "case",
                    "name": extracted_fields.get("case_number"),
                    "relation": "limit_high_consumption",
                    "confidence": 0.72,
                    "court": extracted_fields.get("court"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "court_enforcement",
                    "severity": "high",
                    "title": f"Consumption restriction: {extracted_fields.get('case_number')}",
                    "summary": _join_present(
                        "court",
                        extracted_fields.get("court"),
                        "restricted_subject",
                        extracted_fields.get("restricted_subject"),
                        "publish_date",
                        extracted_fields.get("publish_date"),
                        "status",
                        extracted_fields.get("status"),
                    ),
                    "status": extracted_fields.get("status"),
                    "confidence": 0.72,
                }
            ],
        }

    if record_type == "enforcement_record":
        return {
            "entities": [
                {
                    "kind": "case",
                    "name": extracted_fields.get("case_number"),
                    "relation": "enforcement_record",
                    "confidence": 0.74,
                    "court": extracted_fields.get("court"),
                    "amount": extracted_fields.get("amount"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "court_enforcement",
                    "severity": "high",
                    "title": f"Enforcement record: {extracted_fields.get('case_number')}",
                    "summary": _join_present(
                        "court",
                        extracted_fields.get("court"),
                        "amount",
                        extracted_fields.get("amount"),
                        "filing_date",
                        extracted_fields.get("filing_date"),
                        "execution_status",
                        extracted_fields.get("execution_status"),
                    ),
                    "status": extracted_fields.get("execution_status"),
                    "confidence": 0.74,
                }
            ],
        }

    if record_type == "administrative_penalty":
        return {
            "risk_events": [
                {
                    "risk_category": "administrative_risk",
                    "severity": "medium",
                    "title": f"Administrative penalty: {extracted_fields.get('decision_number')}",
                    "summary": _join_present(
                        "agency",
                        extracted_fields.get("agency"),
                        "violation",
                        extracted_fields.get("violation"),
                        "penalty",
                        extracted_fields.get("penalty"),
                        "decision_date",
                        extracted_fields.get("decision_date"),
                    ),
                    "status": "open",
                    "confidence": 0.72,
                }
            ]
        }

    if record_type in {"related_party_edge", "ubo_path", "group_network_edge"}:
        graph_payload = _qyyjt_relationship_payload(company, key, record_type, extracted_fields)
        if not graph_payload:
            return {}
        return graph_payload

    if record_type == "credit_profile":
        status = str(extracted_fields.get("credit_status") or "").strip()
        payload: dict[str, Any] = {
            "credit_profile": [
                {
                    "section": extracted_fields.get("credit_section"),
                    "item": extracted_fields.get("credit_item"),
                    "status": status,
                    "reference_date": extracted_fields.get("reference_date"),
                    "source": f"qyyjt_api:{key}",
                    "confidence": 0.74,
                }
            ]
        }
        if _credit_status_is_risky(status):
            payload["risk_events"] = [
                {
                    "risk_category": "administrative_risk",
                    "severity": "medium",
                    "title": f"Credit profile warning: {extracted_fields.get('credit_item')}",
                    "summary": _join_present(
                        "section",
                        extracted_fields.get("credit_section"),
                        "item",
                        extracted_fields.get("credit_item"),
                        "status",
                        status,
                        "reference_date",
                        extracted_fields.get("reference_date"),
                    ),
                    "status": status,
                    "confidence": 0.74,
                }
            ]
        return payload

    if record_type == "financial_statement_metric":
        return {
            "financial_metrics": [
                {
                    "period": extracted_fields.get("period"),
                    "metric": extracted_fields.get("metric"),
                    "value": extracted_fields.get("value"),
                    "unit": extracted_fields.get("unit"),
                    "accounting_scope": extracted_fields.get("accounting_scope"),
                    "source": f"qyyjt_api:{key}",
                    "confidence": 0.72,
                }
            ]
        }

    if record_type == "financial_indicator":
        payload: dict[str, Any] = {
            "financial_indicators": [
                {
                    "period": extracted_fields.get("period"),
                    "indicator": extracted_fields.get("indicator"),
                    "value": extracted_fields.get("value"),
                    "unit": extracted_fields.get("unit"),
                    "meaning": extracted_fields.get("meaning"),
                    "source": f"qyyjt_api:{key}",
                    "confidence": 0.72,
                }
            ]
        }
        solvency_event = _qyyjt_financial_indicator_risk_event(extracted_fields)
        if solvency_event:
            payload["risk_events"] = [solvency_event]
        return payload

    if record_type == "financing_event":
        status = str(extracted_fields.get("status") or "").strip()
        counterparty = str(extracted_fields.get("counterparty") or "").strip()
        payload: dict[str, Any] = {
            "risk_events": [
                {
                    "risk_category": "financing_capital_markets",
                    "severity": _qyyjt_financing_severity(status),
                    "title": f"Financing event: {extracted_fields.get('financing_type')}",
                    "summary": _join_present(
                        "type",
                        extracted_fields.get("financing_type"),
                        "amount",
                        extracted_fields.get("amount"),
                        "counterparty",
                        extracted_fields.get("counterparty"),
                        "event_date",
                        extracted_fields.get("event_date"),
                        "status",
                        status,
                    ),
                    "status": status,
                    "confidence": 0.74,
                }
            ]
        }
        if counterparty:
            payload["entities"] = [
                {
                    "kind": "company",
                    "name": counterparty,
                    "relation": "financing_counterparty",
                    "confidence": 0.74,
                    "source": f"qyyjt_api:{key}",
                }
            ]
            payload["relations"] = [
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": counterparty,
                    "to_kind": "company",
                    "relation_type": "financing_counterparty",
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT financing event module",
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "registry_change_event":
        return {
            "risk_events": [
                {
                    "risk_category": "corporate_registry",
                    "severity": "low",
                    "title": f"Registry change: {extracted_fields.get('change_item')}",
                    "summary": _join_present(
                        "item",
                        extracted_fields.get("change_item"),
                        "before",
                        extracted_fields.get("before_value"),
                        "after",
                        extracted_fields.get("after_value"),
                        "change_date",
                        extracted_fields.get("change_date"),
                    ),
                    "status": "observed",
                    "confidence": 0.72,
                }
            ]
        }

    if record_type == "negative_public_opinion":
        return {
            "risk_events": [
                {
                    "risk_category": "public_opinion",
                    "severity": _qyyjt_public_opinion_severity(extracted_fields.get("sentiment")),
                    "title": f"Negative news: {extracted_fields.get('news_title')}",
                    "summary": _join_present(
                        "publisher",
                        extracted_fields.get("publisher"),
                        "publish_date",
                        extracted_fields.get("publish_date"),
                        "sentiment",
                        extracted_fields.get("sentiment"),
                        "summary",
                        extracted_fields.get("summary"),
                    ),
                    "status": "open",
                    "confidence": 0.74,
                }
            ]
        }

    if record_type in {"watchlist_lead", "alert_push_lead"}:
        module = str(extracted_fields.get("module") or key).strip()
        query = str(extracted_fields.get("query") or "").strip()
        summary = str(extracted_fields.get("summary") or "").strip()
        return {
            "risk_events": [
                {
                    "risk_category": "follow_up_lead",
                    "severity": "medium" if record_type == "alert_push_lead" else "low",
                    "title": f"QYYJT {record_type.replace('_', ' ')}: {module}",
                    "summary": _join_present("module", module, "query", query, "summary", summary),
                    "status": "lead_only_pending_verification",
                    "confidence": 0.4,
                }
            ],
            "follow_up_leads": [
                {
                    "module": module,
                    "query": query,
                    "summary": summary,
                    "source": f"qyyjt_api:{key}",
                    "evidence_role": "lead_only_not_verified_fact",
                    "confidence": 0.4,
                }
            ],
        }

    if record_type == "research_report_signal":
        return {
            "industry_product_signals": [
                {
                    "industry": extracted_fields.get("industry"),
                    "product": extracted_fields.get("product"),
                    "report_title": extracted_fields.get("report_title"),
                    "publisher": extracted_fields.get("publisher"),
                    "publish_date": extracted_fields.get("publish_date"),
                    "summary": extracted_fields.get("summary"),
                    "source": f"qyyjt_api:{key}",
                    "confidence": 0.74,
                }
            ]
        }

    if record_type in {"bond_profile", "bond_rating", "bond_issue", "bond_default_event", "bond_calendar_event"}:
        status = str(extracted_fields.get("status") or extracted_fields.get("bond_status") or "").strip()
        is_default = record_type == "bond_default_event"
        title_prefix = {
            "bond_profile": "Bond profile",
            "bond_rating": "Bond rating",
            "bond_issue": "Bond issue",
            "bond_default_event": "Bond default",
            "bond_calendar_event": "Bond calendar",
        }[record_type]
        payload: dict[str, Any] = {
            "entities": [
                {
                    "kind": "asset",
                    "name": extracted_fields.get("bond_name"),
                    "relation": record_type,
                    "confidence": 0.74,
                    "bond_code": extracted_fields.get("bond_code"),
                    "issuer": extracted_fields.get("issuer"),
                    "rating": extracted_fields.get("rating"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "financing_capital_markets",
                    "severity": "high" if is_default else _qyyjt_bond_severity(status, extracted_fields.get("rating")),
                    "title": f"{title_prefix}: {extracted_fields.get('bond_name')}",
                    "summary": _join_present(
                        "issuer",
                        extracted_fields.get("issuer"),
                        "event_type",
                        extracted_fields.get("event_type"),
                        "event_date",
                        extracted_fields.get("event_date"),
                        "rating",
                        extracted_fields.get("rating"),
                        "agency",
                        extracted_fields.get("rating_agency"),
                        "amount",
                        extracted_fields.get("amount") or extracted_fields.get("issue_amount"),
                        "status",
                        status,
                    ),
                    "status": status or extracted_fields.get("outlook"),
                    "confidence": 0.74,
                }
            ],
        }
        bond_name = str(extracted_fields.get("bond_name") or "").strip()
        issuer = str(extracted_fields.get("issuer") or "").strip()
        if bond_name:
            payload["relations"] = [
                {
                    "from_name": issuer or company,
                    "from_kind": "company",
                    "to_name": bond_name,
                    "to_kind": "asset",
                    "relation_type": record_type,
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT bond module",
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "merger_restructuring_event":
        status = str(extracted_fields.get("status") or "").strip()
        counterparty = str(extracted_fields.get("counterparty") or "").strip()
        payload: dict[str, Any] = {
            "risk_events": [
                {
                    "risk_category": "financing_capital_markets",
                    "severity": _qyyjt_financing_severity(status),
                    "title": f"Merger/restructuring event: {extracted_fields.get('event_type')}",
                    "summary": _join_present(
                        "counterparty",
                        counterparty,
                        "announcement_date",
                        extracted_fields.get("announcement_date"),
                        "amount",
                        extracted_fields.get("amount"),
                        "transaction_subject",
                        extracted_fields.get("transaction_subject"),
                        "status",
                        status,
                    ),
                    "status": status,
                    "confidence": 0.74,
                }
            ]
        }
        if counterparty:
            payload["entities"] = [
                {
                    "kind": "company",
                    "name": counterparty,
                    "relation": "merger_restructuring_counterparty",
                    "confidence": 0.74,
                    "transaction_subject": extracted_fields.get("transaction_subject"),
                    "source": f"qyyjt_api:{key}",
                }
            ]
            payload["relations"] = [
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": counterparty,
                    "to_kind": "company",
                    "relation_type": "merger_restructuring_counterparty",
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT merger/restructuring module",
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "regional_credit_indicator":
        risk_level = str(extracted_fields.get("risk_level") or "").strip()
        region_name = extracted_fields.get("region_name")
        indicator = extracted_fields.get("indicator")
        return {
            "risk_events": [
                {
                    "risk_category": "financing_capital_markets",
                    "severity": _qyyjt_regional_credit_severity(risk_level, extracted_fields.get("debt_ratio")),
                    "title": f"Regional credit indicator: {region_name} {indicator}",
                    "summary": _join_present(
                        "period",
                        extracted_fields.get("period"),
                        "value",
                        extracted_fields.get("value"),
                        "unit",
                        extracted_fields.get("unit"),
                        "debt_ratio",
                        extracted_fields.get("debt_ratio"),
                        "debt_balance",
                        extracted_fields.get("debt_balance"),
                        "fiscal_revenue",
                        extracted_fields.get("fiscal_revenue"),
                        "risk_level",
                        risk_level,
                    ),
                    "status": risk_level or "observed",
                    "confidence": 0.72,
                }
            ]
        }

    if record_type in {"equity_pledge", "asset_freeze", "equity_freeze", "judicial_auction", "land_asset"}:
        normalized_record_type = "equity_freeze" if record_type == "asset_freeze" else record_type
        asset_name = (
            extracted_fields.get("asset_name")
            or extracted_fields.get("land_location")
            or extracted_fields.get("shareholder")
            or extracted_fields.get("subject")
        )
        status = str(extracted_fields.get("status") or "").strip()
        category = "court_enforcement" if normalized_record_type in {"equity_freeze", "judicial_auction"} else "location_assets"
        pledgee = str(extracted_fields.get("pledgee") or "").strip()
        court = str(extracted_fields.get("court") or "").strip()
        payload = {
            "entities": [
                {
                    "kind": "asset",
                    "name": asset_name,
                    "relation": normalized_record_type,
                    "confidence": 0.74,
                    "amount": extracted_fields.get("amount")
                    or extracted_fields.get("pledged_amount")
                    or extracted_fields.get("frozen_amount"),
                    "status": status,
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": category,
                    "severity": _qyyjt_asset_severity(normalized_record_type, status),
                    "title": f"{normalized_record_type}: {asset_name}",
                    "summary": _join_present(
                        "shareholder",
                        extracted_fields.get("shareholder"),
                        "pledgee",
                        extracted_fields.get("pledgee"),
                        "court",
                        extracted_fields.get("court"),
                        "amount",
                        extracted_fields.get("amount")
                        or extracted_fields.get("pledged_amount")
                        or extracted_fields.get("frozen_amount"),
                        "date",
                        extracted_fields.get("pledge_date")
                        or extracted_fields.get("freeze_date")
                        or extracted_fields.get("auction_date")
                        or extracted_fields.get("acquisition_date"),
                        "status",
                        status,
                    ),
                    "status": status,
                    "confidence": 0.74,
                }
            ],
        }
        relations: list[dict[str, Any]] = []
        if asset_name:
            relations.append(
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": asset_name,
                    "to_kind": "asset",
                    "relation_type": normalized_record_type,
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT asset solvency module",
                    "source": f"qyyjt_api:{key}",
                }
            )
        if pledgee and normalized_record_type == "equity_pledge":
            relations.append(
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": pledgee,
                    "to_kind": "company",
                    "relation_type": "equity_pledgee",
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT pledge module",
                    "source": f"qyyjt_api:{key}",
                }
            )
        if court and normalized_record_type in {"equity_freeze", "judicial_auction"}:
            relations.append(
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": court,
                    "to_kind": "organization",
                    "relation_type": f"{normalized_record_type}_court",
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT court asset module",
                    "source": f"qyyjt_api:{key}",
                }
            )
        if relations:
            payload["relations"] = relations
        return payload

    if record_type == "tax_profile":
        status = str(extracted_fields.get("tax_status") or extracted_fields.get("status") or "").strip()
        payload = {
            "risk_events": [
                {
                    "risk_category": "administrative_risk",
                    "severity": "medium" if _credit_status_is_risky(status) else "low",
                    "title": f"Tax profile: {extracted_fields.get('tax_item')}",
                    "summary": _join_present(
                        "agency",
                        extracted_fields.get("agency"),
                        "period",
                        extracted_fields.get("period"),
                        "amount",
                        extracted_fields.get("amount"),
                        "status",
                        status,
                    ),
                    "status": status,
                    "confidence": 0.74,
                }
            ]
        }
        return payload

    if record_type == "trade_activity":
        status = str(extracted_fields.get("status") or "").strip()
        counterparty = str(extracted_fields.get("counterparty") or "").strip()
        payload = {
            "risk_events": [
                {
                    "risk_category": "corporate_registry",
                    "severity": "low",
                    "title": f"Trade activity: {extracted_fields.get('trade_type')}",
                    "summary": _join_present(
                        "country",
                        extracted_fields.get("country"),
                        "period",
                        extracted_fields.get("period"),
                        "amount",
                        extracted_fields.get("amount"),
                        "counterparty",
                        extracted_fields.get("counterparty"),
                        "status",
                        status,
                    ),
                    "status": status,
                    "confidence": 0.72,
                }
            ]
        }
        if counterparty:
            payload["entities"] = [
                {
                    "kind": "company",
                    "name": counterparty,
                    "relation": "trade_counterparty",
                    "confidence": 0.72,
                    "trade_type": extracted_fields.get("trade_type"),
                    "country": extracted_fields.get("country"),
                    "source": f"qyyjt_api:{key}",
                }
            ]
            payload["relations"] = [
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": counterparty,
                    "to_kind": "company",
                    "relation_type": "trade_counterparty",
                    "confidence": 0.72,
                    "confidence_basis": "licensed QYYJT import/export module",
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "ip_asset":
        title = extracted_fields.get("ip_title")
        return {
            "entities": [
                {
                    "kind": "asset",
                    "name": title,
                    "relation": "ip_asset",
                    "confidence": 0.74,
                    "ip_type": extracted_fields.get("ip_type"),
                    "registration_number": extracted_fields.get("registration_number"),
                    "status": extracted_fields.get("status"),
                    "source": f"qyyjt_api:{key}",
                }
            ],
            "risk_events": [
                {
                    "risk_category": "ip_tech",
                    "severity": "low",
                    "title": f"IP asset: {title}",
                    "summary": _join_present(
                        "type",
                        extracted_fields.get("ip_type"),
                        "registration_number",
                        extracted_fields.get("registration_number"),
                        "application_date",
                        extracted_fields.get("application_date"),
                        "status",
                        extracted_fields.get("status"),
                    ),
                    "status": extracted_fields.get("status"),
                    "confidence": 0.72,
                }
            ],
        }

    if record_type == "recruiting_signal":
        return {
            "risk_events": [
                {
                    "risk_category": "corporate_registry",
                    "severity": "low",
                    "title": f"Recruiting signal: {extracted_fields.get('position')}",
                    "summary": _join_present(
                        "location",
                        extracted_fields.get("location"),
                        "publish_date",
                        extracted_fields.get("publish_date"),
                        "headcount",
                        extracted_fields.get("headcount"),
                        "salary",
                        extracted_fields.get("salary_range"),
                        "status",
                        extracted_fields.get("status"),
                    ),
                    "status": extracted_fields.get("status"),
                    "confidence": 0.72,
                }
            ]
        }

    if record_type == "financial_institution_profile":
        institution_name = extracted_fields.get("institution_name")
        institution_type = extracted_fields.get("institution_type")
        license_status = str(extracted_fields.get("license_status") or "").strip()
        risk_level = str(extracted_fields.get("risk_level") or "").strip()
        counterparty_role = str(extracted_fields.get("counterparty_role") or "").strip()
        region = extracted_fields.get("region")

        severity = "high" if license_status and license_status.lower() in {"revoked", "suspended", "withdrawn", "expired", "吊销", "注销", "撤销"} else "medium" if risk_level and risk_level.lower() in {"high", "高风险", "关注", "watch"} else "low"
        entity = {
            "kind": "asset",
            "name": institution_name,
            "relation": "financial_institution_counterparty",
            "confidence": 0.74,
            "institution_type": institution_type,
            "license_status": license_status,
            "region": region,
            "risk_level": risk_level,
            "source": f"qyyjt_api:{key}",
        }
        payload = {
            "entities": [entity],
            "risk_events": [
                {
                    "risk_category": "financing_capital_markets",
                    "severity": severity,
                    "title": f"Financial institution counterparty: {institution_name}",
                    "summary": _join_present(
                        "institution_type",
                        institution_type,
                        "region",
                        region,
                        "license_status",
                        license_status,
                        "risk_level",
                        risk_level,
                        "counterparty_role",
                        counterparty_role,
                        "credit_line",
                        extracted_fields.get("credit_line"),
                        "guarantee_status",
                        extracted_fields.get("guarantee_status"),
                        "regulatory_authority",
                        extracted_fields.get("regulatory_authority"),
                    ),
                    "status": license_status or "observed",
                    "confidence": 0.74,
                }
            ],
        }
        if counterparty_role:
            payload["relations"] = [
                {
                    "from_name": company,
                    "from_kind": "company",
                    "to_name": institution_name,
                    "to_kind": "company",
                    "relation_type": f"financial_institution_{counterparty_role}",
                    "confidence": 0.74,
                    "confidence_basis": "licensed QYYJT fin_inst module",
                    "source": f"qyyjt_api:{key}",
                }
            ]
        return payload

    if record_type == "news_opinion_event":
        title = extracted_fields.get("news_title")
        sentiment = str(extracted_fields.get("sentiment") or "").strip()
        return {
            "risk_events": [
                {
                    "risk_category": "news_public_opinion",
                    "severity": "high" if sentiment in {"negative", "negative_sentiment", "负面"} else "medium" if sentiment in {"neutral", "中性"} else "low",
                    "title": f"News/opinion: {title}",
                    "summary": _join_present(
                        "publisher", extracted_fields.get("publisher"),
                        "publish_date", extracted_fields.get("publish_date"),
                        "sentiment", sentiment,
                        "topic", extracted_fields.get("topic"),
                        "impact_level", extracted_fields.get("impact_level"),
                        "source_url", extracted_fields.get("source_url"),
                    ),
                    "status": sentiment or "observed",
                    "confidence": 0.70,
                }
            ]
        }

    return {}


def _qyyjt_relationship_payload(
    company: str,
    key: str,
    record_type: str,
    extracted_fields: dict[str, Any],
) -> dict[str, Any]:
    source = f"qyyjt_api:{key}"
    if record_type == "ubo_path":
        owner = str(extracted_fields.get("beneficial_owner") or "").strip()
        if not owner:
            return {}
        relation_type = "beneficial_owner"
        control_path = extracted_fields.get("path_nodes") or f"{company} -> {owner}"
        return {
            "entities": [
                {
                    "kind": "person",
                    "name": owner,
                    "relation": relation_type,
                    "confidence": 0.82,
                    "control_path": _path_nodes_text(control_path),
                    "ownership_ratio": extracted_fields.get("ownership_ratio"),
                    "layer_depth": extracted_fields.get("layer_depth"),
                    "confidence_basis": "licensed QYYJT UBO chain",
                    "source": source,
                }
            ],
            "relations": _qyyjt_control_path_relations(
                company=company,
                path_nodes=control_path,
                fallback_to=owner,
                relation_type=relation_type,
                confidence=0.82,
                confidence_basis="licensed QYYJT UBO chain",
            ),
        }

    if record_type == "group_network_edge":
        from_entity = str(extracted_fields.get("from_entity") or company).strip()
        to_entity = str(extracted_fields.get("to_entity") or "").strip()
        if not to_entity:
            return {}
        relation_type = str(extracted_fields.get("relation_type") or "group_network_edge").strip()
        basis = extracted_fields.get("control_or_affiliation_basis")
        return {
            "entities": [
                {
                    "kind": "company",
                    "name": to_entity,
                    "relation": relation_type,
                    "confidence": 0.78,
                    "confidence_basis": basis,
                    "source": source,
                }
            ],
            "relations": [
                {
                    "from_name": from_entity,
                    "from_kind": "company",
                    "to_name": to_entity,
                    "to_kind": "company",
                    "relation_type": relation_type,
                    "confidence": 0.78,
                    "confidence_basis": basis,
                    "source": source,
                }
            ],
        }

    related_name = str(extracted_fields.get("related_name") or "").strip()
    if not related_name:
        return {}
    relation_type = str(extracted_fields.get("relation_type") or "related_party_edge").strip()
    direction = str(extracted_fields.get("relationship_direction") or "outbound").strip().lower()
    basis = extracted_fields.get("confidence_basis")
    if direction in {"inbound", "reverse", "target_to_subject"}:
        from_name, to_name = related_name, company
    else:
        from_name, to_name = company, related_name
    return {
        "entities": [
            {
                "kind": "company",
                "name": related_name,
                "relation": relation_type,
                "confidence": 0.78,
                "relationship_direction": direction,
                "confidence_basis": basis,
                "source": source,
            }
        ],
        "relations": [
            {
                "from_name": from_name,
                "from_kind": "company",
                "to_name": to_name,
                "to_kind": "company",
                "relation_type": relation_type,
                "confidence": 0.78,
                "confidence_basis": basis,
                "source": source,
            }
        ],
    }


def _qyyjt_control_path_relations(
    *,
    company: str,
    path_nodes: Any,
    fallback_to: Any,
    relation_type: Any,
    confidence: float,
    confidence_basis: Any,
) -> list[dict[str, Any]]:
    nodes = _coerce_path_nodes(path_nodes)
    fallback = str(fallback_to or "").strip()
    if not nodes and fallback:
        nodes = [company, fallback]
    if len(nodes) < 2:
        return []
    if _same_name(nodes[0], company) is False:
        nodes.insert(0, company)

    relations: list[dict[str, Any]] = []
    for index in range(len(nodes) - 1):
        from_name = nodes[index]
        to_name = nodes[index + 1]
        is_last = index == len(nodes) - 2
        relations.append(
            {
                "from_name": from_name,
                "from_kind": "company",
                "to_name": to_name,
                "to_kind": "person" if is_last else "company",
                "relation_type": str(relation_type or "control_path"),
                "confidence": confidence,
                "confidence_basis": confidence_basis,
            }
        )
    return relations


def _coerce_path_nodes(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, tuple):
        values = list(raw)
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        delimiter = "->" if "->" in text else ">"
        values = text.split(delimiter)
    nodes: list[str] = []
    for item in values:
        if isinstance(item, dict):
            name = item.get("name") or item.get("entity") or item.get("value") or item.get("title")
        else:
            name = item
        value = " ".join(str(name or "").split())
        if value:
            nodes.append(value)
    return nodes


def _path_nodes_text(raw: Any) -> str:
    nodes = _coerce_path_nodes(raw)
    return " -> ".join(nodes) if nodes else str(raw or "").strip()


def _same_name(left: Any, right: Any) -> bool:
    return " ".join(str(left or "").casefold().split()) == " ".join(str(right or "").casefold().split())


def _subject_resolution_level(score: float) -> str:
    if score >= 0.95:
        return "exact"
    if score >= 0.8:
        return "strong"
    if score >= 0.55:
        return "review"
    return "weak"


def _credit_status_is_risky(status: str) -> bool:
    normalized = status.strip().lower()
    if not normalized:
        return False
    clean_markers = {"normal", "active", "valid", "good", "clear", "none", "0"}
    if normalized in clean_markers:
        return False
    risk_markers = (
        "abnormal",
        "overdue",
        "dishonest",
        "default",
        "restricted",
        "warning",
        "risk",
        "penalty",
        "invalid",
        "revoked",
        "cancelled",
        "注销",
        "吊销",
        "异常",
        "失信",
        "逾期",
        "限制",
        "处罚",
        "风险",
    )
    return any(marker in normalized for marker in risk_markers)


def _qyyjt_financing_severity(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if any(marker in normalized for marker in ("default", "overdue", "breach", "abnormal", "risk", "逾期", "违约", "异常", "风险")):
        return "high"
    if any(marker in normalized for marker in ("pending", "pledge", "guarantee", "担保", "质押", "待定")):
        return "medium"
    return "low"


def _qyyjt_bond_severity(status: Any, rating: Any) -> str:
    normalized = f"{status or ''} {rating or ''}".strip().lower()
    if any(marker in normalized for marker in ("default", "违约", "cc", "caa", "风险")):
        return "high"
    if any(marker in normalized for marker in ("negative", "watch", "downgrade", "bbb", "bb", "下调", "负面")):
        return "medium"
    return "low"


def _qyyjt_regional_credit_severity(risk_level: Any, debt_ratio: Any) -> str:
    normalized = str(risk_level or "").strip().lower()
    if any(marker in normalized for marker in ("high", "red", "critical", "severe", "高", "红", "严重")):
        return "high"
    if any(marker in normalized for marker in ("medium", "yellow", "warning", "中", "黄", "预警")):
        return "medium"
    try:
        ratio = float(str(debt_ratio or "").strip().rstrip("%"))
    except (TypeError, ValueError):
        return "low"
    if ratio >= 120:
        return "high"
    if ratio >= 80:
        return "medium"
    return "low"


def _qyyjt_financial_indicator_risk_event(extracted_fields: dict[str, Any]) -> dict[str, Any] | None:
    indicator = str(extracted_fields.get("indicator") or "").strip()
    value = _float_or_default(extracted_fields.get("value"), -1)
    if not indicator or value < 0:
        return None
    normalized = indicator.casefold().replace("-", "_").replace(" ", "_")
    debt_markers = (
        "debt_to_assets",
        "liability_to_asset",
        "asset_liability_ratio",
        "debt_to_equity",
        "gearing",
        "leverage",
    )
    if not any(marker in normalized for marker in debt_markers):
        return None
    if value >= 0.85 or (value > 1 and value >= 85):
        severity = "high"
    elif value >= 0.7 or (value > 1 and value >= 70):
        severity = "medium"
    else:
        return None
    return {
        "risk_category": "financing_capital_markets",
        "severity": severity,
        "title": f"Financial solvency warning: {indicator}",
        "summary": _join_present(
            "period",
            extracted_fields.get("period"),
            "indicator",
            indicator,
            "value",
            extracted_fields.get("value"),
            "unit",
            extracted_fields.get("unit"),
            "meaning",
            extracted_fields.get("meaning"),
        ),
        "status": "observed",
        "confidence": 0.72,
    }


def _qyyjt_asset_severity(record_type: str, status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if record_type in {"equity_freeze", "judicial_auction"}:
        return "high"
    if any(marker in normalized for marker in ("active", "pending", "pledge", "frozen", "auction", "质押", "冻结", "拍卖")):
        return "medium"
    return "low"


def _qyyjt_public_opinion_severity(sentiment: Any) -> str:
    normalized = str(sentiment or "").strip().lower()
    if any(marker in normalized for marker in ("critical", "severe", "重大", "严重")):
        return "high"
    if any(marker in normalized for marker in ("negative", "warning", "risk", "负面", "预警", "风险")):
        return "medium"
    return "low"


def _float_or_default(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _join_present(*items: Any) -> str:
    parts: list[str] = []
    for index in range(0, len(items), 2):
        key = str(items[index])
        value = items[index + 1] if index + 1 < len(items) else None
        if value in (None, ""):
            continue
        parts.append(f"{key}={value}")
    return "; ".join(parts)


def create_qyyjt_tool(**kwargs: Any) -> QYYJTTool:
    return QYYJTTool(**kwargs)


def qyyjt_authorized_smoke_summary() -> dict[str, Any]:
    """Return a safe, no-credentials summary of authorized QYYJT smoke coverage.

    Never prints, logs, or returns cookies, tokens, or credentials.
    Reports the gap when no authorized session is available.
    """
    from core.qyyjt_benchmark import build_qyyjt_benchmark

    benchmark = build_qyyjt_benchmark()
    modules = benchmark["rows"]
    surface = benchmark["summary"]["surface_profile"]

    auth_required = surface.get("auth_required_module_names", [])
    p0_modules = [item["module"] for item in benchmark["summary"]["p0_queue"]]
    p1_priority = "p1_domain_depth"
    p1_modules = sorted(
        row["module"] for row in modules
        if row.get("parity_priority") == p1_priority
    )

    return {
        "type": "qyyjt_authorized_smoke_summary",
        "smoke_available": False,
        "smoke_status": "authorized_session_not_available",
        "smoke_note": "Configure authorized QYYJT session to populate verified coverage. No credentials stored or logged.",
        "modules_needing_authorization": {
            "count": len(auth_required),
            "names": sorted(auth_required),
        },
        "p0_queue": {
            "total": len(p0_modules),
            "smoke_verified": 0,
            "fixture_verified": len(p0_modules),
        },
        "p1_domain_depth": {
            "total": len(p1_modules),
            "smoke_verified": 0,
            "names": p1_modules,
        },
    }
