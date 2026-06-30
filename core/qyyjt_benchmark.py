#!/usr/bin/env python3
"""QYYJT module coverage and parity benchmark."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from adapters.qyyjt_adapter import QYYJTAdapter, QYYJTModule


class QYYJTCoverageClass(str, Enum):
    API = "api"
    QUERY_PLAN = "query_plan"
    DEFAULT = "default"


class QYYJTDeliveryLane(str, Enum):
    AUTHORIZED_API = "authorized_api"
    RICH_QUERY_PLAN = "rich_query_plan"
    GENERIC_FALLBACK = "generic_fallback"


@dataclass(frozen=True)
class QYYJTBenchmarkRow:
    module: str
    module_name: str
    module_family: str
    coverage_class: str
    implementation_status: str
    surface_lane: str
    user_visible_status: str
    authorization_mode: str
    source_kind: str
    live_route: str
    query_count: int
    api_entrypoint: bool
    official_connector: bool
    default_enabled: bool
    evidence_role: str
    report_admissibility: str
    admission_gate: str
    parity_priority: str
    acceptance_gate: str
    next_action: str
    field_contract: dict[str, Any]
    public_origin_plan: dict[str, Any]
    operator_work_item: dict[str, Any]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "module_name": self.module_name,
            "module_family": self.module_family,
            "coverage_class": self.coverage_class,
            "implementation_status": self.implementation_status,
            "surface_lane": self.surface_lane,
            "user_visible_status": self.user_visible_status,
            "authorization_mode": self.authorization_mode,
            "source_kind": self.source_kind,
            "live_route": self.live_route,
            "query_count": self.query_count,
            "api_entrypoint": self.api_entrypoint,
            "official_connector": self.official_connector,
            "default_enabled": self.default_enabled,
            "evidence_role": self.evidence_role,
            "report_admissibility": self.report_admissibility,
            "admission_gate": self.admission_gate,
            "parity_priority": self.parity_priority,
            "acceptance_gate": self.acceptance_gate,
            "next_action": self.next_action,
            "field_contract": self.field_contract,
            "public_origin_plan": self.public_origin_plan,
            "operator_work_item": self.operator_work_item,
            "notes": list(self.notes),
        }


def build_qyyjt_benchmark() -> dict[str, Any]:
    from .connector_registry import ConnectorRegistry

    adapter = QYYJTAdapter()
    registry = ConnectorRegistry()
    connector = registry.get("qyyjt_tool")
    connector_payload = connector.to_dict() if connector else {}

    rows = [_benchmark_row(adapter, registry, module) for module in QYYJTModule]
    counts = {
        "total_modules": len(rows),
        "api": sum(1 for row in rows if row.coverage_class == QYYJTCoverageClass.API.value),
        "query_plan": sum(1 for row in rows if row.coverage_class == QYYJTCoverageClass.QUERY_PLAN.value),
        "default": sum(1 for row in rows if row.coverage_class == QYYJTCoverageClass.DEFAULT.value),
    }
    api_modules = [row.module for row in rows if row.coverage_class == QYYJTCoverageClass.API.value]
    query_plan_modules = [row.module for row in rows if row.coverage_class == QYYJTCoverageClass.QUERY_PLAN.value]
    default_modules = [row.module for row in rows if row.coverage_class == QYYJTCoverageClass.DEFAULT.value]
    auth_required_modules = [row.module for row in rows if row.authorization_mode != "public_search_only"]
    public_only_modules = [row.module for row in rows if row.authorization_mode == "public_search_only"]
    unsupported_modules = [row.module for row in rows if row.coverage_class == QYYJTCoverageClass.DEFAULT.value]
    family_counts = _module_family_counts(rows)
    priority_counts = _priority_counts(rows)
    work_items = _operator_work_items(rows)
    p0_queue = [
        item for item in work_items
        if str(item["parity_priority"]).startswith("p0_")
    ]
    lane_counts = {
        lane.value: sum(1 for row in rows if row.surface_lane == lane.value)
        for lane in QYYJTDeliveryLane
    }
    coverage_status = "covered_with_gaps"
    if counts["query_plan"] == 0 and counts["default"] == 0:
        coverage_status = "api_only"
    elif counts["api"] == 0:
        coverage_status = "query_plan_only"

    return {
        "type": "qyyjt_benchmark",
        "version": "0.5.0",
        "summary": {
            "module_count": counts["total_modules"],
            "api_modules": counts["api"],
            "query_plan_modules": counts["query_plan"],
            "default_modules": counts["default"],
            "module_families": family_counts,
            "parity_priorities": priority_counts,
            "p0_queue": p0_queue,
            "p0_queue_count": len(p0_queue),
            "work_items": work_items,
            "surface_lanes": lane_counts,
            "field_contracts": _field_contracts(rows),
            "public_origin_plans": _public_origin_plans(rows),
            "surface_profile": {
                "concrete_api_or_legacy_modules": counts["api"],
                "rich_query_plan_modules": counts["query_plan"],
                "generic_fallback_modules": counts["default"],
                "concrete_api_or_legacy_module_names": api_modules,
                "rich_query_plan_module_names": query_plan_modules,
                "generic_fallback_module_names": default_modules,
            },
            "authorization_profile": {
                "auth_required_modules": len(auth_required_modules),
                "auth_required_module_names": auth_required_modules,
                "public_only_modules": len(public_only_modules),
                "public_only_module_names": public_only_modules,
            },
            "unsupported_profile": {
                "unsupported_modules": len(unsupported_modules),
                "unsupported_module_names": unsupported_modules,
                "unknown_semantics_modules": 0,
                "unknown_semantics_module_names": [],
            },
            "coverage_status": coverage_status,
            "benchmark_note": (
                "QYYJT 45-module surface benchmarked against the current adapter and connector catalog; "
                "concrete API routes, rich public query plans, and generic fallbacks are separated explicitly."
            ),
        },
        "connector": connector_payload,
        "rows": [row.to_dict() for row in rows],
    }


def _benchmark_row(adapter: QYYJTAdapter, registry: Any, module: QYYJTModule) -> QYYJTBenchmarkRow:
    query_info = adapter.get_module_query(module, "benchmark-case")
    query_count = len(list(query_info.get("queries") or []))
    api_entrypoint = module in {
        QYYJTModule.SEARCH_MULTI,
        QYYJTModule.BOND_PROFILE,
        QYYJTModule.REGION_CODE,
        QYYJTModule.REGION_ECONOMY,
    }
    if api_entrypoint:
        coverage_class = QYYJTCoverageClass.API.value
        implementation_status = "api_entrypoint"
        surface_lane = QYYJTDeliveryLane.AUTHORIZED_API.value
        user_visible_status = "concrete_api_or_legacy_route"
        authorization_mode = "user_authorized_or_legacy_credentials"
        source_kind = "api_or_legacy"
        live_route = "credentialed_api_or_legacy_http"
        evidence_role = "candidate_fact_after_authorized_live_validation"
        report_admissibility = "can_enter_evidence_ledger_after_field_mapping_and_provenance_checks"
        admission_gate = "valid authorized session, reviewed terms, successful live smoke, stable field mapping"
        parity_priority = _parity_priority(module, coverage_class)
        acceptance_gate = "live or fixture-backed API response maps to standardized records with source URL/provenance"
        next_action = _next_action_for_module(module, coverage_class)
        field_contract = _field_contract_for_module(module)
        notes = ("Adapter has a concrete request path for this module.",)
    elif query_count > 1:
        coverage_class = QYYJTCoverageClass.QUERY_PLAN.value
        implementation_status = "query_plan"
        surface_lane = QYYJTDeliveryLane.RICH_QUERY_PLAN.value
        user_visible_status = "rich_query_plan"
        authorization_mode = "public_search_only"
        source_kind = "websearch_plan"
        live_route = "websearch_fallback"
        evidence_role = "lead_only_not_verified_fact"
        report_admissibility = "follow_up_lead_only_until_corroborated_by_public_or_authorized_source"
        admission_gate = "module-specific query plan plus downstream source verification"
        parity_priority = _parity_priority(module, coverage_class)
        acceptance_gate = "query-plan output remains low-confidence lead and never raises risk events by itself"
        next_action = _next_action_for_module(module, coverage_class)
        field_contract = _field_contract_for_module(module)
        notes = ("Adapter emits multiple query-plan leads for this module.",)
    else:
        coverage_class = QYYJTCoverageClass.DEFAULT.value
        implementation_status = "default_fallback"
        surface_lane = QYYJTDeliveryLane.GENERIC_FALLBACK.value
        user_visible_status = "generic_fallback"
        authorization_mode = "public_search_only"
        source_kind = "websearch_plan"
        live_route = "default_module_query"
        evidence_role = "weak_lead_only"
        report_admissibility = "not_admissible_as_report_evidence"
        admission_gate = "replace with module-specific query plan or authorized connector"
        parity_priority = _parity_priority(module, coverage_class)
        acceptance_gate = "fallback row must be visible as weak coverage and excluded from evidence-ledger facts"
        next_action = _next_action_for_module(module, coverage_class)
        field_contract = _field_contract_for_module(module)
        notes = ("Adapter falls back to the generic module query path.",)

    connector = registry.get("qyyjt_tool")
    return QYYJTBenchmarkRow(
        module=module.value,
        module_name=module.name,
        module_family=_module_family(module),
        coverage_class=coverage_class,
        implementation_status=implementation_status,
        surface_lane=surface_lane,
        user_visible_status=user_visible_status,
        authorization_mode=authorization_mode,
        source_kind=source_kind,
        live_route=live_route,
        query_count=query_count,
        api_entrypoint=api_entrypoint,
        official_connector=bool(connector and connector.authority.value == "commercial"),
        default_enabled=bool(connector and connector.default_enabled),
        evidence_role=evidence_role,
        report_admissibility=report_admissibility,
        admission_gate=admission_gate,
        parity_priority=parity_priority,
        acceptance_gate=acceptance_gate,
        next_action=next_action,
        field_contract=field_contract,
        public_origin_plan=_public_origin_plan_for_module(module),
        operator_work_item=_operator_work_item(
            module=module,
            module_family=_module_family(module),
            coverage_class=coverage_class,
            surface_lane=surface_lane,
            parity_priority=parity_priority,
            evidence_role=evidence_role,
            report_admissibility=report_admissibility,
            admission_gate=admission_gate,
            acceptance_gate=acceptance_gate,
            next_action=next_action,
            field_contract=field_contract,
            public_origin_plan=_public_origin_plan_for_module(module),
        ),
        notes=notes,
    )


def _module_family(module: QYYJTModule) -> str:
    if module is QYYJTModule.SEARCH_MULTI:
        return "search"
    if module.name.startswith("ENTERPRISE_"):
        return "enterprise_due_diligence"
    if module.name in {
        "RISK_SCAN",
        "RISK_SIGNAL",
        "ACTUAL_CONTROLLER",
        "COURT_CASES",
        "COURT_ANNOUNCE",
        "DISHONESTY",
        "LIMIT_HIGH",
        "EXECUTION",
    }:
        return "risk_resolution"
    if module.name in {"NEWS_NEGATIVE", "NEWS_ALL", "RESEARCH_REPORT"}:
        return "news_intelligence"
    if module.name in {"FINANCIAL_STATEMENT", "FINANCIAL_INDICATORS"}:
        return "financial"
    if module.name.startswith("BOND_"):
        return "bond"
    if module.name.startswith("REGION_"):
        return "region"
    if module.name in {"RELATED_PARTIES", "UBO_CHAIN", "GROUP_NETWORK"}:
        return "ownership_and_relations"
    if module.name in {"WATCHLIST", "ALERT_PUSH"}:
        return "monitoring"
    if module.name == "FIN_INSTITUTION":
        return "financial_institutions"
    return "supplemental"


def _module_family_counts(rows: list[QYYJTBenchmarkRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.module_family] = counts.get(row.module_family, 0) + 1
    return dict(sorted(counts.items()))


def _priority_counts(rows: list[QYYJTBenchmarkRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.parity_priority] = counts.get(row.parity_priority, 0) + 1
    return dict(sorted(counts.items()))


def _operator_work_items(rows: list[QYYJTBenchmarkRow]) -> list[dict[str, Any]]:
    return [
        row.operator_work_item
        for row in sorted(
            rows,
            key=lambda item: (
                _priority_rank(item.parity_priority),
                item.module_family,
                item.module,
            ),
        )
    ]


def _field_contracts(rows: list[QYYJTBenchmarkRow]) -> dict[str, dict[str, Any]]:
    return {
        row.module: row.field_contract
        for row in rows
        if row.field_contract.get("record_type")
    }


def _public_origin_plans(rows: list[QYYJTBenchmarkRow]) -> dict[str, dict[str, Any]]:
    return {
        row.module: row.public_origin_plan
        for row in rows
        if row.public_origin_plan.get("origin_channels")
    }


def _operator_work_item(
    *,
    module: QYYJTModule,
    module_family: str,
    coverage_class: str,
    surface_lane: str,
    parity_priority: str,
    evidence_role: str,
    report_admissibility: str,
    admission_gate: str,
    acceptance_gate: str,
    next_action: str,
    field_contract: dict[str, Any],
    public_origin_plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "module": module.value,
        "module_name": module.name,
        "module_family": module_family,
        "parity_priority": parity_priority,
        "priority_rank": _priority_rank(parity_priority),
        "coverage_class": coverage_class,
        "surface_lane": surface_lane,
        "evidence_role": evidence_role,
        "report_admissibility": report_admissibility,
        "admission_gate": admission_gate,
        "acceptance_gate": acceptance_gate,
        "next_action": next_action,
        "field_contract": field_contract,
        "public_origin_plan": public_origin_plan,
        "done_when": _done_when_for_module(module, coverage_class),
    }


def _priority_rank(priority: str) -> int:
    if priority == "p0_subject_resolution_entrypoint":
        return 0
    if priority == "p0_report_critical":
        return 1
    if priority == "p0_replace_generic_fallback":
        return 2
    if priority == "p1_domain_depth":
        return 10
    return 20


def _parity_priority(module: QYYJTModule, coverage_class: str) -> str:
    if coverage_class == QYYJTCoverageClass.DEFAULT.value:
        return "p0_replace_generic_fallback"
    if module.name == "SEARCH_MULTI":
        return "p0_subject_resolution_entrypoint"
    if module.name in {
        "RISK_SCAN",
        "RISK_SIGNAL",
        "ACTUAL_CONTROLLER",
        "COURT_CASES",
        "DISHONESTY",
        "LIMIT_HIGH",
        "EXECUTION",
        "ENTERPRISE_BASIC",
        "ENTERPRISE_CREDIT",
        "ENTERPRISE_PENALTY",
        "RELATED_PARTIES",
        "UBO_CHAIN",
        "GROUP_NETWORK",
        "FINANCIAL_STATEMENT",
        "FINANCIAL_INDICATORS",
        "ENTERPRISE_FINANCING",
        "ENTERPRISE_CHANGE",
        "NEWS_NEGATIVE",
        "RESEARCH_REPORT",
    }:
        return "p0_report_critical"
    if module.name.startswith("BOND_") or module.name.startswith("REGION_") or module.name in {
        "CITY_INVEST",
        "FIN_INSTITUTION",
    }:
        return "p1_domain_depth"
    return "p2_supplemental"


def _next_action_for_module(module: QYYJTModule, coverage_class: str) -> str:
    if coverage_class == QYYJTCoverageClass.DEFAULT.value:
        return "Replace this generic fallback with module-specific queries or an admitted live connector before relying on it."

    actions = {
        "SEARCH_MULTI": "Harden subject resolution by mapping candidate name, identifier, entity type, and source URL before downstream modules run.",
        "RISK_SCAN": "Map the risk overview into normalized alert categories, severity, source refs, and verification status.",
        "RISK_SIGNAL": "Map risk labels and score details into report-visible signals without turning unverified leads into facts.",
        "ACTUAL_CONTROLLER": "Feed controller candidates into the UBO confidence model with relation type, source, and evidence refs.",
        "COURT_CASES": "Map court records into case parties, case number, cause, court, date, result, and source URL.",
        "COURT_ANNOUNCE": "Map hearing announcements into court, case number, cause, hearing date, parties, status, and source URL.",
        "DISHONESTY": "Map dishonesty records into enforceable subject, case number, court, obligation, status, and source URL.",
        "LIMIT_HIGH": "Map consumption restriction records into person/company target, case number, court, date, and status.",
        "EXECUTION": "Map enforcement records into subject, amount, case number, court, filing date, status, and source URL.",
        "ENTERPRISE_BASIC": "Map registry identity fields into legal name, identifier, status, address, representative, dates, and provenance.",
        "ENTERPRISE_CREDIT": "Map credit report sections into evidence-ledger facts only after source and field provenance are stable.",
        "ENTERPRISE_PENALTY": "Map administrative penalties into agency, decision number, violation, penalty, date, and source URL.",
        "RELATED_PARTIES": "Map related parties into typed relationship edges with confidence and source references.",
        "UBO_CHAIN": "Map ownership chains into beneficial-owner paths with layer depth, ownership ratio, and verification status.",
        "GROUP_NETWORK": "Map group network records into parent, subsidiary, affiliate, and shared-control graph edges.",
        "FINANCIAL_STATEMENT": "Map statement rows into period, metric, value, unit, accounting scope, and source provenance.",
        "FINANCIAL_INDICATORS": "Map ratio indicators into period, formula/meaning, value, unit, and report-quality warnings.",
        "ENTERPRISE_FINANCING": "Map financing, guarantee, debt, and pledge rows into risk-visible capital-pressure facts with amount, counterparty, date, and status.",
        "ENTERPRISE_CHANGE": "Map registry-change rows into change events with changed item, before/after values, date, and source provenance.",
        "NEWS_NEGATIVE": "Map negative-news rows into public-opinion risk events with title, publisher, date, sentiment, and source URL.",
        "RESEARCH_REPORT": "Map research-report rows into industry and product cognition signals with source, date, analyst view, and explicit evidence limits.",
        "BOND_CALENDAR": "Map bond calendar rows into dated repayment, maturity, coupon, put, or disclosure obligations with issuer and amount.",
        "MERGER": "Map merger and restructuring rows into capital-event facts plus relationship edges to counterparties.",
    }
    if module.name in actions:
        return actions[module.name]
    if module.name.startswith("BOND_"):
        return "Keep bond-specific query/API mapping as domain-depth coverage with issuer, instrument, date, rating, and source refs."
    if module.name.startswith("REGION_") or module.name == "CITY_INVEST":
        return "Keep regional/city-investment indicators as domain-depth coverage with geography, period, metric, and source refs."
    return "Keep the module-specific query plan visible as lead-only coverage until corroborated by public or authorized source records."


def _public_origin_plan_for_module(module: QYYJTModule) -> dict[str, Any]:
    """Describe lawful public-origin fallbacks when an authorized aggregator is unavailable."""
    groups: dict[str, dict[str, Any]] = {
        "registry": {
            "origin_channels": ["official_company_registry", "market_supervision_publicity"],
            "query_families": ["legal name + unified social credit code", "legal representative + registry status"],
            "evidence_boundary": "public registry facts only; no login/paywall/captcha bypass",
        },
        "legal": {
            "origin_channels": ["court_notice_portal", "judgment_publication", "enforcement_publicity", "credit_publicity"],
            "query_families": ["company + case number", "company + enforcement", "company + dishonesty/limit high consumption"],
            "evidence_boundary": "official public legal notices and court/enforcement publications only",
        },
        "capital": {
            "origin_channels": ["exchange_disclosures", "bond_information_portals", "credit_disclosure_portals", "company_announcements"],
            "query_families": ["company + bond/default/rating", "company + financing/guarantee/pledge", "company + annual report financials"],
            "evidence_boundary": "issuer disclosures, official exchange/bond portals, and public filings only",
        },
        "relationship": {
            "origin_channels": ["registry_shareholder_filings", "annual_reports", "company_announcements", "official_registry_branch_records"],
            "query_families": ["company + shareholder/subsidiary", "company + related party transaction", "company + actual controller"],
            "evidence_boundary": "public filings and official registry-derived relationship facts only",
        },
        "news": {
            "origin_channels": ["public_news_search", "company_announcements", "industry_publications"],
            "query_families": ["company + negative news", "company + product/partnership/channel", "company + industry research"],
            "evidence_boundary": "publicly accessible pages and licensed/user-authorized feeds only",
        },
        "commercial": {
            "origin_channels": ["customs_or_trade_publications", "tax_credit_publicity", "recruiting_public_pages", "ip_public_search"],
            "query_families": ["company + import/export/customer/supplier", "company + tax credit", "company + patent/trademark/recruiting"],
            "evidence_boundary": "public portals and public pages; treat as leads unless corroborated",
        },
        "regional": {
            "origin_channels": ["statistics_bureau", "finance_bureau", "regional_government_disclosures"],
            "query_families": ["region + GDP/fiscal revenue/debt", "city investment platform + region debt"],
            "evidence_boundary": "public statistical and fiscal disclosures only",
        },
    }
    module_groups = {
        "SEARCH_MULTI": "registry",
        "ENTERPRISE_BASIC": "registry",
        "ACTUAL_CONTROLLER": "relationship",
        "RELATED_PARTIES": "relationship",
        "UBO_CHAIN": "relationship",
        "GROUP_NETWORK": "relationship",
        "COURT_CASES": "legal",
        "COURT_ANNOUNCE": "legal",
        "DISHONESTY": "legal",
        "LIMIT_HIGH": "legal",
        "EXECUTION": "legal",
        "ENTERPRISE_PENALTY": "legal",
        "RISK_SCAN": "legal",
        "RISK_SIGNAL": "legal",
        "ENTERPRISE_CREDIT": "capital",
        "ENTERPRISE_FINANCING": "capital",
        "FINANCIAL_STATEMENT": "capital",
        "FINANCIAL_INDICATORS": "capital",
        "FIN_INSTITUTION": "capital",
        "BOND_PROFILE": "capital",
        "BOND_CREDIT": "capital",
        "BOND_ISSUE": "capital",
        "BOND_DEFAULT": "capital",
        "BOND_CALENDAR": "capital",
        "PLEDGE": "capital",
        "FREEZE": "legal",
        "AUCTION": "legal",
        "MERGER": "capital",
        "ENTERPRISE_CHANGE": "registry",
        "NEWS_NEGATIVE": "news",
        "NEWS_ALL": "news",
        "RESEARCH_REPORT": "news",
        "IMPORT_EXPORT": "commercial",
        "TAX": "commercial",
        "PATENT": "commercial",
        "TRADEMARK": "commercial",
        "COPYRIGHT": "commercial",
        "RECRUIT": "commercial",
        "LAND": "registry",
        "CITY_INVEST": "regional",
        "REGION_CODE": "regional",
        "REGION_ECONOMY": "regional",
        "REGION_DEBT": "regional",
    }
    group_name = module_groups.get(module.name, "news")
    plan = dict(groups[group_name])
    plan["fallback_mode"] = "public_origin_reconstruction"
    plan["compliance_rule"] = "do_not_bypass_authentication_paywalls_captcha_or_rate_limits"
    return plan


def _field_contract_for_module(module: QYYJTModule) -> dict[str, Any]:
    common = {
        "required_common_fields": [
            "subject_name",
            "source_name",
            "source_url",
            "observed_at",
            "confidence",
            "verification_status",
        ],
        "report_gate": "do_not_enter_report_as_fact_until_required_fields_and_provenance_are_present",
    }
    contracts: dict[str, dict[str, Any]] = {
        "SEARCH_MULTI": {
            "record_type": "subject_resolution_candidate",
            "required_fields": ["candidate_name", "identifier", "entity_type", "match_score"],
            "report_section": "subject_resolution",
        },
        "RISK_SCAN": {
            "record_type": "risk_overview",
            "required_fields": ["risk_category", "severity", "risk_label", "summary", "status"],
            "report_section": "risk_brief",
        },
        "RISK_SIGNAL": {
            "record_type": "risk_signal",
            "required_fields": ["signal_code", "signal_label", "severity", "signal_summary"],
            "report_section": "risk_brief",
        },
        "ACTUAL_CONTROLLER": {
            "record_type": "controller_candidate",
            "required_fields": ["person_name", "relation_type", "control_path", "confidence_basis"],
            "report_section": "control_ownership",
        },
        "COURT_CASES": {
            "record_type": "court_case",
            "required_fields": ["case_number", "court", "cause", "parties", "case_date", "case_status"],
            "report_section": "legal_risk",
        },
        "COURT_ANNOUNCE": {
            "record_type": "court_announcement",
            "required_fields": ["case_number", "court", "cause", "parties", "hearing_date", "status"],
            "report_section": "legal_risk",
        },
        "DISHONESTY": {
            "record_type": "dishonesty_record",
            "required_fields": ["case_number", "court", "obligation", "publish_date", "performance_status"],
            "report_section": "legal_risk",
        },
        "LIMIT_HIGH": {
            "record_type": "limit_high_consumption",
            "required_fields": ["case_number", "court", "restricted_subject", "publish_date", "status"],
            "report_section": "legal_risk",
        },
        "EXECUTION": {
            "record_type": "enforcement_record",
            "required_fields": ["case_number", "court", "amount", "filing_date", "execution_status"],
            "report_section": "legal_risk",
        },
        "ENTERPRISE_BASIC": {
            "record_type": "registry_identity",
            "required_fields": ["legal_name", "identifier", "status", "legal_representative", "registered_address"],
            "optional_fields": [
                "registered_capital",
                "establishment_date",
                "operating_period",
                "registration_authority",
                "business_scope",
                "company_type",
            ],
            "report_section": "subject_profile",
        },
        "ENTERPRISE_CREDIT": {
            "record_type": "credit_profile",
            "required_fields": ["credit_section", "credit_item", "credit_status", "reference_date"],
            "report_section": "credit_profile",
        },
        "ENTERPRISE_PENALTY": {
            "record_type": "administrative_penalty",
            "required_fields": ["agency", "decision_number", "violation", "penalty", "decision_date"],
            "report_section": "administrative_risk",
        },
        "RELATED_PARTIES": {
            "record_type": "related_party_edge",
            "required_fields": ["related_name", "relation_type", "relationship_direction", "confidence_basis"],
            "report_section": "relationship_graph",
        },
        "UBO_CHAIN": {
            "record_type": "ubo_path",
            "required_fields": ["beneficial_owner", "path_nodes", "ownership_ratio", "layer_depth"],
            "report_section": "control_ownership",
        },
        "GROUP_NETWORK": {
            "record_type": "group_network_edge",
            "required_fields": ["from_entity", "to_entity", "relation_type", "control_or_affiliation_basis"],
            "report_section": "relationship_graph",
        },
        "FINANCIAL_STATEMENT": {
            "record_type": "financial_statement_metric",
            "required_fields": ["period", "metric", "value", "unit", "accounting_scope"],
            "report_section": "financial_cognition",
        },
        "FINANCIAL_INDICATORS": {
            "record_type": "financial_indicator",
            "required_fields": ["period", "indicator", "value", "unit", "meaning"],
            "report_section": "financial_cognition",
        },
        "FIN_INSTITUTION": {
            "record_type": "financial_institution_profile",
            "required_fields": [
                "institution_name",
                "institution_type",
                "license_status",
                "region",
                "risk_level",
            ],
            "optional_fields": [
                "registration_number",
                "regulatory_authority",
                "counterparty_role",
                "credit_line",
                "guarantee_status",
                "source_provenance",
            ],
            "report_section": "financial_institution_counterparty",
        },
        "ENTERPRISE_FINANCING": {
            "record_type": "financing_event",
            "required_fields": ["financing_type", "amount", "counterparty", "event_date", "status"],
            "report_section": "financing_capital_markets",
        },
        "ENTERPRISE_CHANGE": {
            "record_type": "registry_change_event",
            "required_fields": ["change_item", "before_value", "after_value", "change_date"],
            "report_section": "subject_profile",
        },
        "NEWS_NEGATIVE": {
            "record_type": "negative_public_opinion",
            "required_fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
            "report_section": "risk_brief",
        },
        "NEWS_ALL": {
            "record_type": "news_opinion_event",
            "required_fields": ["news_title", "publisher", "publish_date", "sentiment", "summary"],
            "optional_fields": ["source_url", "topic", "impact_level"],
            "report_section": "risk_brief",
        },
        "RESEARCH_REPORT": {
            "record_type": "research_report_signal",
            "required_fields": ["report_title", "publisher", "publish_date", "industry", "product", "summary"],
            "optional_fields": ["industry_growth", "customer_value", "substitution_risk"],
            "report_section": "industry_product_cognition",
        },
        "BOND_PROFILE": {
            "record_type": "bond_profile",
            "required_fields": ["bond_name", "issuer", "maturity_date", "coupon_rate", "bond_status"],
            "optional_fields": ["bond_code", "issue_amount", "rating"],
            "report_section": "bond_credit_profile",
        },
        "BOND_CREDIT": {
            "record_type": "bond_rating",
            "required_fields": ["bond_name", "issuer", "rating", "rating_agency", "rating_date"],
            "optional_fields": ["outlook", "rating_reason"],
            "report_section": "bond_credit_profile",
        },
        "BOND_ISSUE": {
            "record_type": "bond_issue",
            "required_fields": ["bond_name", "issuer", "issue_date", "issue_amount", "bond_status"],
            "optional_fields": ["coupon_rate", "maturity_date"],
            "report_section": "bond_credit_profile",
        },
        "BOND_DEFAULT": {
            "record_type": "bond_default_event",
            "required_fields": ["bond_name", "issuer", "default_date", "amount", "status"],
            "optional_fields": ["summary"],
            "report_section": "bond_credit_profile",
        },
        "BOND_CALENDAR": {
            "record_type": "bond_calendar_event",
            "required_fields": ["bond_name", "issuer", "event_date", "event_type", "amount", "status"],
            "optional_fields": ["bond_code", "maturity_date"],
            "report_section": "bond_credit_profile",
        },
        "MERGER": {
            "record_type": "merger_restructuring_event",
            "required_fields": ["event_type", "counterparty", "announcement_date", "amount", "status"],
            "optional_fields": ["transaction_subject", "summary"],
            "report_section": "financing_capital_markets",
        },
        "CITY_INVEST": {
            "record_type": "regional_credit_indicator",
            "required_fields": ["region_name", "indicator", "period", "value", "risk_level"],
            "optional_fields": ["unit", "debt_ratio", "fiscal_revenue"],
            "report_section": "regional_credit_profile",
        },
        "REGION_CODE": {
            "record_type": "regional_credit_indicator",
            "required_fields": ["region_name", "indicator", "period", "value", "risk_level"],
            "optional_fields": ["unit", "region_code", "parent_region"],
            "report_section": "regional_credit_profile",
        },
        "REGION_ECONOMY": {
            "record_type": "regional_credit_indicator",
            "required_fields": ["region_name", "indicator", "period", "value", "risk_level"],
            "optional_fields": ["unit", "gdp", "fiscal_revenue", "debt_ratio"],
            "report_section": "regional_credit_profile",
        },
        "REGION_DEBT": {
            "record_type": "regional_credit_indicator",
            "required_fields": ["region_name", "indicator", "period", "value", "risk_level"],
            "optional_fields": ["unit", "debt_balance", "debt_ratio", "fiscal_revenue"],
            "report_section": "regional_credit_profile",
        },
        "PLEDGE": {
            "record_type": "equity_pledge",
            "required_fields": ["shareholder", "pledgee", "pledged_amount", "pledge_date", "status"],
            "optional_fields": ["ownership_ratio"],
            "report_section": "asset_solvency",
        },
        "FREEZE": {
            "record_type": "equity_freeze",
            "required_fields": ["subject", "court", "frozen_amount", "freeze_date", "status"],
            "optional_fields": ["case_number"],
            "report_section": "legal_risk",
        },
        "AUCTION": {
            "record_type": "judicial_auction",
            "required_fields": ["asset_name", "auction_date", "court", "amount", "status"],
            "optional_fields": ["asset_type"],
            "report_section": "asset_solvency",
        },
        "LAND": {
            "record_type": "land_asset",
            "required_fields": ["land_location", "area", "acquisition_date", "land_use", "status"],
            "optional_fields": ["amount"],
            "report_section": "asset_solvency",
        },
        "TAX": {
            "record_type": "tax_profile",
            "required_fields": ["tax_item", "tax_status", "period", "agency"],
            "optional_fields": ["amount"],
            "report_section": "administrative_risk",
        },
        "IMPORT_EXPORT": {
            "record_type": "trade_activity",
            "required_fields": ["trade_type", "country", "period", "amount", "status"],
            "optional_fields": ["counterparty"],
            "report_section": "operational_activity",
        },
        "PATENT": {
            "record_type": "ip_asset",
            "required_fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
            "optional_fields": ["owner"],
            "report_section": "ip_tech",
        },
        "TRADEMARK": {
            "record_type": "ip_asset",
            "required_fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
            "optional_fields": ["owner"],
            "report_section": "ip_tech",
        },
        "COPYRIGHT": {
            "record_type": "ip_asset",
            "required_fields": ["ip_type", "ip_title", "registration_number", "application_date", "status"],
            "optional_fields": ["owner"],
            "report_section": "ip_tech",
        },
        "RECRUIT": {
            "record_type": "recruiting_signal",
            "required_fields": ["position", "location", "publish_date", "headcount", "status"],
            "optional_fields": ["salary_range"],
            "report_section": "operational_activity",
        },
    }
    module_contract = contracts.get(module.name)
    if module_contract is None:
        module_contract = {
            "record_type": f"{module.value}_lead",
            "required_fields": ["module", "query", "summary"],
            "report_section": "follow_up_leads",
        }
    return {**common, **module_contract}


def _done_when_for_module(module: QYYJTModule, coverage_class: str) -> str:
    if coverage_class == QYYJTCoverageClass.API.value:
        return "authorized smoke or fixture maps non-empty response into standardized records with provenance"
    if module.name in {
        "RISK_SCAN",
        "RISK_SIGNAL",
        "ACTUAL_CONTROLLER",
        "COURT_CASES",
        "DISHONESTY",
        "LIMIT_HIGH",
        "EXECUTION",
        "ENTERPRISE_BASIC",
        "ENTERPRISE_CREDIT",
        "ENTERPRISE_PENALTY",
        "RELATED_PARTIES",
        "UBO_CHAIN",
        "GROUP_NETWORK",
        "FINANCIAL_STATEMENT",
        "FINANCIAL_INDICATORS",
        "ENTERPRISE_FINANCING",
        "ENTERPRISE_CHANGE",
        "NEWS_NEGATIVE",
        "RESEARCH_REPORT",
    }:
        return "lead output remains low-confidence until corroborated, and a concrete field contract exists for report admission"
    if coverage_class == QYYJTCoverageClass.DEFAULT.value:
        return "generic fallback is removed and the row has module-specific query or connector coverage"
    return "module-specific lead plan is preserved with explicit non-admissibility and acceptance gate"
