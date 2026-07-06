#!/usr/bin/env python3
"""Connector capability registry for public or authorized intelligence sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .intelligence_retrieval import (
    ConnectorShape,
    RetrievalDomain,
    SourceAccess,
    SourceAuthority,
)
from .qyyjt_benchmark import build_qyyjt_benchmark


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    CONDITIONALLY_ACTIVE = "conditionally_active"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class ConnectorCapability:
    """Auditable metadata for a datasource or tool connector."""

    name: str
    shape: ConnectorShape
    access: SourceAccess
    authority: SourceAuthority
    domains: tuple[RetrievalDomain, ...] = ()
    status: ConnectorStatus = ConnectorStatus.EXPERIMENTAL
    configurable_endpoint: bool = True
    health_check: bool = False
    standardized_records: bool = False
    provenance_required: bool = True
    default_enabled: bool = False
    notes: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()

    @property
    def production_ready(self) -> bool:
        return (
            self.status in {ConnectorStatus.ACTIVE, ConnectorStatus.CONDITIONALLY_ACTIVE}
            and self.health_check
            and self.standardized_records
            and self.provenance_required
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "shape": self.shape.value,
            "access": self.access.value,
            "authority": self.authority.value,
            "domains": [domain.value for domain in self.domains],
            "status": self.status.value,
            "configurable_endpoint": self.configurable_endpoint,
            "health_check": self.health_check,
            "standardized_records": self.standardized_records,
            "provenance_required": self.provenance_required,
            "default_enabled": self.default_enabled,
            "production_ready": self.production_ready,
            "notes": list(self.notes),
            "risk_flags": list(self.risk_flags),
            "data_effectiveness": self.data_effectiveness(),
        }

    def data_effectiveness(self) -> dict[str, Any]:
        """Describe what this source can really contribute to analysis."""
        admission_mode = self._admission_mode()
        analysis_outputs = self._analysis_outputs()
        can_feed_facts = admission_mode in {
            "fact_source_when_subject_match_passes",
            "authorized_fact_source_when_field_contract_passes",
            "user_authorized_fact_source_when_entity_match_passes",
        }
        return {
            "admission_mode": admission_mode,
            "admission_gates": self._admission_gates(admission_mode),
            "can_feed_report_facts": can_feed_facts,
            "can_feed_report_leads": self.standardized_records or self.status is not ConnectorStatus.DISABLED,
            "analysis_outputs": analysis_outputs,
            "default_use": "default_on" if self.default_enabled else "available_when_configured",
            "effective_when": self._effective_when(admission_mode),
            "limitations": self._effectiveness_limitations(),
        }

    def _admission_mode(self) -> str:
        if not self.standardized_records:
            return "catalog_or_manual_plan_only"
        if self.name == "idb_sanctioned_firms_dataset_catalog":
            return "catalog_source_requires_local_subject_index"
        if self.name == "qyyjt_tool":
            return "authorized_fact_source_when_field_contract_passes"
        if self.name in {
            "autonomous_enterprise_registry",
            "autonomous_public_records",
            "mass_cross_platform_profiler",
            "runtime_aiqicha_session_lookup",
            "runtime_username_cross_platform_verifier",
            "runtime_visual_challenge_solver",
            "telegram_public_aggregation",
            "verified_crtsh_domain_lookup",
            "verified_cross_platform_profile_check",
            "verified_github_public_profile",
            "verified_whois_rdap_domain_lookup",
            "verified_wikipedia_enterprise_entry",
        }:
            return "lead_source_with_exact_match_promotion"
        if self.access is SourceAccess.USER_AUTHORIZED:
            return "user_authorized_fact_source_when_entity_match_passes"
        if self.authority is SourceAuthority.OFFICIAL and self.production_ready:
            return "fact_source_when_subject_match_passes"
        if self.authority is SourceAuthority.COMMERCIAL and self.production_ready:
            return "authorized_fact_source_when_field_contract_passes"
        if self.authority is SourceAuthority.PUBLIC_WEB:
            return "lead_source_with_exact_match_promotion"
        if self.authority is SourceAuthority.COMMUNITY:
            return "corroboration_lead_source"
        return "review_lead_source"

    def _admission_gates(self, admission_mode: str) -> list[str]:
        common = ["standardized_records_required", "provenance_required"]
        if admission_mode == "fact_source_when_subject_match_passes":
            return [*common, "entity_match_exact_or_strong", "official_or_production_ready_source"]
        if admission_mode == "authorized_fact_source_when_field_contract_passes":
            return [*common, "field_contract_required", "report_admission_required", "authorized_or_licensed_boundary"]
        if admission_mode == "user_authorized_fact_source_when_entity_match_passes":
            return [*common, "user_authorization_required", "entity_match_exact_or_strong"]
        if admission_mode == "lead_source_with_exact_match_promotion":
            return [*common, "lead_only_by_default", "exact_match_or_corroboration_before_fact_reliance"]
        if admission_mode == "corroboration_lead_source":
            return [*common, "corroboration_only", "secondary_source_required_for_fact_reliance"]
        if admission_mode == "catalog_source_requires_local_subject_index":
            return [*common, "catalog_coverage_only", "local_subject_index_required", "exact_match_or_strong_match_before_fact_reliance"]
        if admission_mode == "catalog_or_manual_plan_only":
            return ["catalog_visible_only", "connector_or_parser_admission_required"]
        return [*common, "manual_review_required"]

    def _analysis_outputs(self) -> list[str]:
        mapping = {
            RetrievalDomain.CORPORATE_REGISTRY: "registry_identity",
            RetrievalDomain.OWNERSHIP_CONTROL: "controller_ubo_relationships",
            RetrievalDomain.COURT_ENFORCEMENT: "legal_enforcement_risk",
            RetrievalDomain.ADMINISTRATIVE_RISK: "administrative_credit_risk",
            RetrievalDomain.NEWS_PUBLIC_OPINION: "public_opinion_events",
            RetrievalDomain.FINANCING_CAPITAL_MARKETS: "financing_capital_markets",
            RetrievalDomain.PEOPLE: "key_people_and_watchlist",
            RetrievalDomain.RELATED_ENTITIES: "relationship_network",
            RetrievalDomain.LOCATION_ASSETS: "asset_location_solvency",
            RetrievalDomain.SOCIAL_WEB: "public_statements_accounts",
            RetrievalDomain.PROCUREMENT_PROJECTS: "procurement_debarment",
            RetrievalDomain.IP_TECH: "ip_technology_assets",
        }
        outputs = [mapping[domain] for domain in self.domains if domain in mapping]
        if not outputs and self.domains:
            outputs = [domain.value for domain in self.domains]
        return sorted(dict.fromkeys(outputs))

    def _effective_when(self, admission_mode: str) -> str:
        if admission_mode == "catalog_or_manual_plan_only":
            return "Useful for routing and manual follow-up until live health and standardized-record admission are complete."
        if admission_mode == "authorized_fact_source_when_field_contract_passes":
            return "Useful as report facts only when authorized/API payloads satisfy field contracts, provenance, confidence, and entity-match gates."
        if admission_mode == "user_authorized_fact_source_when_entity_match_passes":
            return "Useful as facts when the deployment owner supplies the dataset and entity resolution reaches the required match level."
        if admission_mode == "fact_source_when_subject_match_passes":
            return "Useful as facts after source-specific subject matching and provenance checks pass."
        if admission_mode == "lead_source_with_exact_match_promotion":
            return "Useful for broad discovery; stays lead-only unless exact/strong subject matching and source evidence support fact admission."
        if admission_mode == "corroboration_lead_source":
            return "Useful for corroboration and expansion; treat as lower-confidence unless official or licensed evidence supports it."
        return "Useful for review leads until admission, health, and entity-resolution gates are stronger."

    def _effectiveness_limitations(self) -> list[str]:
        limitations = list(self.risk_flags)
        if not self.health_check:
            limitations.append("live_health_not_validated")
        if not self.standardized_records:
            limitations.append("standardized_records_not_ready")
        if not self.default_enabled:
            limitations.append("not_default_enabled")
        return sorted(dict.fromkeys(limitations))


class ConnectorRegistry:
    """In-memory registry for connector audit and routing metadata."""

    def __init__(self, connectors: list[ConnectorCapability] | None = None):
        self._connectors: dict[str, ConnectorCapability] = {}
        for connector in connectors or default_connector_capabilities():
            self.register(connector)

    def register(self, connector: ConnectorCapability) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> ConnectorCapability | None:
        return self._connectors.get(name)

    def list(
        self,
        *,
        domain: RetrievalDomain | None = None,
        shape: ConnectorShape | None = None,
        production_ready: bool | None = None,
    ) -> list[ConnectorCapability]:
        connectors = list(self._connectors.values())
        if domain is not None:
            connectors = [item for item in connectors if domain in item.domains]
        if shape is not None:
            connectors = [item for item in connectors if item.shape is shape]
        if production_ready is not None:
            connectors = [
                item for item in connectors
                if item.production_ready is production_ready
            ]
        return sorted(connectors, key=lambda item: item.name)

    def audit_summary(self) -> dict[str, Any]:
        connectors = self.list()
        by_status: dict[str, int] = {}
        by_shape: dict[str, int] = {}
        by_access: dict[str, int] = {}
        by_authority: dict[str, int] = {}
        for connector in connectors:
            by_status[connector.status.value] = by_status.get(connector.status.value, 0) + 1
            by_shape[connector.shape.value] = by_shape.get(connector.shape.value, 0) + 1
            by_access[connector.access.value] = by_access.get(connector.access.value, 0) + 1
            by_authority[connector.authority.value] = by_authority.get(connector.authority.value, 0) + 1
        return {
            "total": len(connectors),
            "production_ready": sum(1 for item in connectors if item.production_ready),
            "default_enabled": sum(1 for item in connectors if item.default_enabled),
            "by_status": by_status,
            "by_shape": by_shape,
            "by_access": by_access,
            "by_authority": by_authority,
            "connectors": [connector.to_dict() for connector in connectors],
        }

    def product_catalog(self) -> dict[str, Any]:
        """Return a product-facing datasource catalog for UI/API consumers."""
        connectors = self.list()
        qyyjt_benchmark = build_qyyjt_benchmark()
        connector_payloads = [self._product_connector_payload(item) for item in connectors]
        default_enabled = [item for item in connectors if item.default_enabled]
        production_ready = [item for item in connectors if item.production_ready]
        needs_admission = [
            item for item in connectors
            if not item.production_ready or item.status is ConnectorStatus.NEEDS_REVIEW
        ]
        explicit_only = [
            item for item in connectors
            if not item.default_enabled and item.access is SourceAccess.USER_AUTHORIZED
        ]
        admission_counts: dict[str, int] = {}
        for payload in connector_payloads:
            decision = str(payload.get("admission", {}).get("decision") or "unknown")
            admission_counts[decision] = admission_counts.get(decision, 0) + 1
        return {
            "type": "connector_catalog",
            "version": "0.5.0",
            "summary": {
                "total": len(connectors),
                "default_enabled": len(default_enabled),
                "production_ready": len(production_ready),
                "needs_admission": len(needs_admission),
                "explicit_only": len(explicit_only),
                "admission_counts": admission_counts,
                "zero_config_ready": [
                    item.name
                    for item in production_ready
                    if item.default_enabled and item.access is SourceAccess.PUBLIC
                ],
                "qyyjt_benchmark": qyyjt_benchmark["summary"],
                "data_effectiveness": _data_effectiveness_summary(connector_payloads),
                "admission_gate_summary": _admission_gate_summary(connector_payloads),
                "source_strengthening": _source_strengthening_summary(connector_payloads),
            },
            "groups": {
                "default_enabled": [self._product_connector_payload(item) for item in default_enabled],
                "production_ready": [self._product_connector_payload(item) for item in production_ready],
                "needs_admission": [self._product_connector_payload(item) for item in needs_admission],
                "explicit_only": [self._product_connector_payload(item) for item in explicit_only],
                "official_or_high_authority": [
                    self._product_connector_payload(item)
                    for item in connectors
                    if item.authority in {SourceAuthority.OFFICIAL, SourceAuthority.COMMERCIAL}
                ],
            },
            "connectors": connector_payloads,
            "data_effectiveness": _data_effectiveness_matrix(connector_payloads),
            "source_strengthening_queue": _source_strengthening_queue(connector_payloads),
            "qyyjt_benchmark": qyyjt_benchmark,
            "policy": {
                "default_mode": "public_zero_config",
                "public_boundary": "public, licensed, or user-authorized sources with provenance retained",
                "empty_result_rule": "empty results are coverage gaps, not low-risk conclusions",
                "high_sensitivity_rule": "sensitive business-relevant leads remain visible with source, confidence, and verification status",
                "production_route_rule": "only production_ready admission can be enabled by default; conditional sources require deployment review or user configuration",
            },
        }

    @staticmethod
    def _product_connector_payload(connector: ConnectorCapability) -> dict[str, Any]:
        payload = connector.to_dict()
        payload["admission"] = _admission_report_for_connector(connector)
        return payload


def _admission_report_for_connector(connector: ConnectorCapability) -> dict[str, Any]:
    """Return a production-admission report without creating import cycles."""
    from .source_admission import AdmissionInput, DataSourceTier, SourceAdmissionEvaluator

    evaluator = SourceAdmissionEvaluator()
    if connector.name == "qyyjt_tool":
        return evaluator.evaluate(evaluator.qyyjt_admission_input()).to_dict()
    if connector.name == "telegram_bot_public_service":
        return evaluator.evaluate(
            evaluator.telegram_public_service_admission_input(
                source_description="public or user-configured business-record delivery service"
            )
        ).to_dict()

    tier = _admission_tier_for_connector(connector)
    source_description = _source_description(connector)
    is_public_official_or_web = connector.access is SourceAccess.PUBLIC and connector.authority in {
        SourceAuthority.OFFICIAL,
        SourceAuthority.PUBLIC_WEB,
        SourceAuthority.COMMUNITY,
    }
    live_validation_ok = bool(
        connector.production_ready
        and connector.status is ConnectorStatus.ACTIVE
        and connector.health_check
        and connector.standardized_records
    )
    terms_reviewed = bool(tier in {DataSourceTier.OFFICIAL_PUBLIC, DataSourceTier.PUBLIC_WEB})
    return evaluator.evaluate(
        AdmissionInput(
            connector_name=connector.name,
            tier=tier,
            public_or_authorized=connector.access in {
                SourceAccess.PUBLIC,
                SourceAccess.LICENSED,
                SourceAccess.USER_AUTHORIZED,
            },
            terms_reviewed=terms_reviewed,
            provenance_retained=connector.provenance_required,
            audit_log_enabled=True,
            source_description=source_description,
            authorization_evidence="public no-credential source" if is_public_official_or_web else "",
            live_validation_ok=live_validation_ok,
            standardized_records_ok=connector.standardized_records,
            default_enabled=connector.default_enabled,
            default_public_entry=connector.default_enabled and connector.access is SourceAccess.PUBLIC,
            notes=connector.notes,
        )
    ).to_dict()


def _source_strengthening_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    queue = _source_strengthening_queue(payloads)
    by_priority: dict[str, int] = {}
    for item in queue:
        priority = str(item.get("priority") or "P3")
        by_priority[priority] = by_priority.get(priority, 0) + 1
    return {
        "type": "source_strengthening_summary",
        "candidate_count": len(queue),
        "by_priority": by_priority,
        "top_connectors": [item["connector"] for item in queue[:5]],
        "policy": (
            "Promote public or user-authorized sources only by adding health checks, standardized records, "
            "provenance, entity-match gates, and admission tests; do not treat catalog-only rows as facts."
        ),
    }


def _source_strengthening_queue(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        payload
        for payload in payloads
        if not payload.get("production_ready")
    ]
    ranked = sorted(candidates, key=_source_strengthening_sort_key)
    return [_source_strengthening_item(payload, index) for index, payload in enumerate(ranked[:12], start=1)]


def _source_strengthening_sort_key(payload: dict[str, Any]) -> tuple[int, int, str]:
    access = str(payload.get("access") or "")
    authority = str(payload.get("authority") or "")
    health_ready = bool(payload.get("health_check"))
    standardized = bool(payload.get("standardized_records"))
    risk_count = len(payload.get("risk_flags") or [])
    if access == "public" and authority == "official" and health_ready and not standardized:
        bucket = 0
    elif access == "public" and authority in {"official", "public_web", "community"}:
        bucket = 1
    elif access == "public":
        bucket = 2
    elif access == "user_authorized" and health_ready:
        bucket = 3
    else:
        bucket = 4
    return (bucket, risk_count, str(payload.get("name") or ""))


def _source_strengthening_item(payload: dict[str, Any], rank: int) -> dict[str, Any]:
    data_effectiveness = _dict(payload.get("data_effectiveness"))
    admission = _dict(payload.get("admission"))
    missing = _source_strengthening_missing_contracts(payload)
    priority = _source_strengthening_priority(payload)
    lane = _source_strengthening_lane(payload)
    implementation_pack = _source_strengthening_implementation_pack(payload)
    execution_plan = _source_strengthening_execution_plan(payload, missing, lane, implementation_pack)
    return {
        "type": "source_strengthening_work_order",
        "rank": rank,
        "priority": priority,
        "lane": lane,
        "connector": payload.get("name"),
        "access": payload.get("access"),
        "authority": payload.get("authority"),
        "domains": list(payload.get("domains") or []),
        "current_status": payload.get("status"),
        "can_feed_report_facts_now": bool(data_effectiveness.get("can_feed_report_facts")),
        "can_feed_report_leads_now": bool(data_effectiveness.get("can_feed_report_leads")),
        "admission_decision": admission.get("decision"),
        "missing_contracts": missing,
        "next_action": _source_strengthening_next_action(payload, missing, lane, implementation_pack),
        "runtime_companion": _dict(implementation_pack.get("runtime_companion")),
        "execution_plan": execution_plan,
        "implementation_pack": implementation_pack,
        "acceptance_commands": implementation_pack["acceptance_commands"],
        "done_condition": (
            "connector has health_check=true, standardized_records=true, provenance retained, "
            "entity/field admission tests, and connector_catalog exposes production_admissible or conditional production"
        ),
        "do_not": [
            "do not enable by default until production admission passes",
            "do not promote lead-only or catalog-only rows into report facts",
            "do not require credentials or external accounts for public-zero-config runs",
        ],
    }


def _source_strengthening_implementation_pack(payload: dict[str, Any]) -> dict[str, Any]:
    connector = str(payload.get("name") or "")
    pack = _SOURCE_STRENGTHENING_IMPLEMENTATION_PACKS.get(connector)
    if pack:
        return pack
    return {
        "type": "source_strengthening_implementation_pack",
        "target_files": ["core/connector_registry.py", "tests/unit/test_connector_registry.py"],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "required_common_fields": [
                "source_name",
                "source_url",
                "entity",
                "summary",
                "evidence",
                "confidence",
                "entity_match",
            ],
            "report_gate": "standardized records must retain provenance and remain lead-only until source admission passes",
        },
        "operator_notes": [
            "Prefer fixture or validated snapshot tests before any live network work.",
            "Do not add credentials or enable the source by default as part of strengthening.",
        ],
    }


_SOURCE_STRENGTHENING_IMPLEMENTATION_PACKS: dict[str, dict[str, Any]] = {
    "gleif_lei_relationship_traversal_public_api": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource/__init__.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/relationship_resolution.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_gleif_relationship_traversal_maps_parent_edges tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "gleif_relationship_edge",
            "source_hint": "gleif_lei_relationship_traversal_public_api",
            "required_fields": [
                "subject_lei",
                "related_lei",
                "relationship_type",
                "relationship_status",
                "source_url",
            ],
            "relationship_fields": [
                "direct_parent",
                "ultimate_parent",
                "branch_relationship",
                "relationship_period",
            ],
            "report_gate": "relationship edges remain graph leads until subject LEI resolution, source URL, relationship status/period, and exact/strong entity match pass admission tests",
        },
        "operator_notes": [
            "Reuse the stable GLEIF LEI lookup for subject resolution before traversing relationship endpoints.",
            "Bound traversal depth and deduplicate by subject_lei, related_lei, and relationship_type before graph admission.",
            "Do not mark the existing gleif_lei_public_api as incomplete; this work order only deepens relationship traversal.",
        ],
    },
    "idb_sanctioned_firms_dataset_catalog": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource/__init__.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/connector_registry.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_idb_provider_maps_public_dataset_catalog_metadata tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "procurement_debarment_dataset_catalog",
            "source_hint": "idb_sanctioned_firms_dataset_catalog",
            "required_fields": [
                "dataset_title",
                "dataset_url",
                "coverage_summary",
                "refresh_or_update_hint",
            ],
            "subject_match_fields": [
                "local_index_path",
                "firm_name",
                "country",
                "sanction_or_debarment_basis",
            ],
            "report_gate": "catalog metadata stays coverage evidence only; subject-level procurement risk requires a reviewed local index, exact/strong entity match, source URL, and admission tests",
        },
        "operator_notes": [
            "Use the catalog to locate and refresh the public dataset; do not infer a subject hit from catalog metadata alone.",
            "Pair with idb_local_subject_index before adding procurement debarment facts to reports.",
        ],
        "runtime_companion": {
            "type": "source_strengthening_runtime_companion",
            "connector": "idb_local_subject_index",
            "source_hint": "idb_local_subject_index",
            "required_config": ["index_path"],
            "record_type": "procurement_debarment_subject_match",
            "subject_match_levels": ["exact", "strong", "review"],
            "promotion_gate": "subject-level procurement risk requires the configured local index record, source_url, provenance, exact/strong entity match for fact reliance, and admission tests",
            "focused_test": "tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_local_index_datasource_maps_csv_procurement_match",
        },
    },
    "opensanctions_public_dataset_catalog": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource/__init__.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/connector_registry.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_opensanctions_catalog_provider_maps_public_dataset_metadata tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "watchlist_dataset_catalog",
            "source_hint": "opensanctions_public_dataset_catalog",
            "required_fields": [
                "dataset_name",
                "dataset_url",
                "dataset_scope",
                "last_seen_or_modified",
                "license",
            ],
            "subject_match_fields": [
                "local_index_path",
                "entity_name",
                "aliases",
                "topics",
                "match_rationale",
            ],
            "report_gate": "catalog rows are not subject facts; watchlist or PEP facts require a reviewed local/API subject record, license review, exact/strong entity match, and admission tests",
        },
        "operator_notes": [
            "Use the public catalog to select datasets and refresh cadence before local subject indexing.",
            "Keep license and attribution status visible in the agent handoff before report reliance.",
        ],
        "runtime_companion": {
            "type": "source_strengthening_runtime_companion",
            "connector": "opensanctions_local_subject_index",
            "source_hint": "opensanctions_local_subject_index",
            "required_config": ["index_path"],
            "record_type": "watchlist_subject_match",
            "subject_match_levels": ["exact", "strong", "review"],
            "promotion_gate": "watchlist/PEP facts require a reviewed local or licensed API subject record, attribution/license review, exact/strong entity match for fact reliance, and admission tests",
            "focused_test": "tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_local_index_datasource_maps_jsonl_subject_match",
        },
    },
    "official_china_registry_portal_catalog": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource_tool.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/connector_registry.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_official_registry_portal_validated_snapshot_maps_standard_record tests/unit/test_multi_datasource.py::TestDataSourceManager::test_official_portal_health_report_exposes_manual_gate_semantics tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "official_registry_snapshot",
            "source_hint": "official_china_registry",
            "required_fields": [
                "legal_name",
                "unified_social_credit_code",
                "legal_representative",
                "registered_address",
            ],
            "relationship_fields": ["shareholders", "legal_representative"],
            "report_gate": "official snapshot records can enter the graph as review leads; report facts require exact/strong entity match and admission_tests",
        },
        "operator_notes": [
            "Use browser-handoff or validated page snapshot inputs; do not automate challenge bypass.",
            "Keep source default-off until source admission and entity-match gates are green.",
        ],
    },
    "official_china_credit_portal_catalog": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource_tool.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/connector_registry.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_official_credit_portal_validated_snapshot_maps_risk_event tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "official_credit_publicity_snapshot",
            "source_hint": "official_china_credit_publicity",
            "required_fields": [
                "legal_name",
                "notice_date",
                "issuing_authority",
                "credit_notice",
            ],
            "risk_fields": ["administrative_penalty", "credit_notice"],
            "report_gate": "risk events remain review leads until subject match, notice URL, issuing authority, and admission_tests pass",
        },
        "operator_notes": [
            "Retain notice URL, title, issuing authority, date, and page snapshot metadata.",
            "No-result snapshots are coverage evidence, not a clean-risk conclusion.",
        ],
    },
    "official_china_court_enforcement_catalog": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/multi_datasource_tool.py",
            "adapters/multi_datasource/datasources.yaml",
            "core/connector_registry.py",
            "tests/unit/test_multi_datasource.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_multi_datasource.py::TestRestApiDataSource::test_official_court_portal_validated_snapshot_maps_enforcement_event tests/unit/test_connector_registry.py -q",
            "npm run codex:mcp-smoke",
        ],
        "field_contract": {
            "record_type": "official_court_enforcement_snapshot",
            "source_hint": "official_china_court_enforcement",
            "required_fields": [
                "case_number",
                "subject_name",
                "court",
                "filing_date",
            ],
            "risk_fields": ["execution_amount", "case_status"],
            "report_gate": "enforcement events require exact/strong subject match, case URL/provenance, and admission_tests before fact reliance",
        },
        "operator_notes": [
            "Use browser-handoff or validated snapshot capture for challenge-aware official pages.",
            "Never treat inaccessible or challenge pages as no-risk evidence.",
        ],
    },
}


def _source_strengthening_priority(payload: dict[str, Any]) -> str:
    if payload.get("access") == "public" and payload.get("authority") == "official":
        return "P1"
    if payload.get("access") == "public":
        return "P2"
    return "P3"


def _source_strengthening_lane(payload: dict[str, Any]) -> str:
    domains = set(payload.get("domains") or [])
    if {"administrative_risk", "court_enforcement", "procurement_projects"} & domains:
        return "risk_enforcement"
    if {"corporate_registry", "ownership_control", "related_entities"} & domains:
        return "identity_relationships"
    if {"financing_capital_markets", "location_assets"} & domains:
        return "capital_assets"
    if {"people", "social_web"} & domains:
        return "people_reputation"
    return "general_enrichment"


def _source_strengthening_missing_contracts(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not payload.get("health_check"):
        missing.append("health_check")
    if not payload.get("standardized_records"):
        missing.append("standardized_records")
    if not payload.get("provenance_required"):
        missing.append("provenance")
    if "license_review_required" in set(payload.get("risk_flags") or []):
        missing.append("license_review")
    admission = _dict(payload.get("admission"))
    if not admission.get("production_admissible"):
        missing.append("admission_tests")
    data_effectiveness = _dict(payload.get("data_effectiveness"))
    admission_mode = str(data_effectiveness.get("admission_mode") or "")
    if (
        payload.get("access") == "public"
        and payload.get("authority") == "official"
        and admission_mode != "catalog_source_requires_local_subject_index"
    ):
        missing.append("entity_match_gate")
    return sorted(dict.fromkeys(missing))


def _source_strengthening_next_action(
    payload: dict[str, Any],
    missing: list[str],
    lane: str,
    implementation_pack: dict[str, Any],
) -> str:
    field_contract = _dict(implementation_pack.get("field_contract"))
    connector = str(payload.get("name") or "this connector")
    source_hint = str(field_contract.get("source_hint") or connector)
    record_type = str(field_contract.get("record_type") or "standardized_source_record")
    target_files = [str(item) for item in implementation_pack.get("target_files") or []]
    first_target = target_files[0] if target_files else "the connector implementation"
    first_step = _source_strengthening_contract_action(missing)
    return (
        f"For {connector}, first {first_step}; implement or verify {record_type} "
        f"({source_hint}) in {first_target}; route output through {lane}; prove with the "
        "implementation_pack acceptance command before any report-fact promotion."
    )


def _source_strengthening_execution_plan(
    payload: dict[str, Any],
    missing: list[str],
    lane: str,
    implementation_pack: dict[str, Any],
) -> dict[str, Any]:
    field_contract = _dict(implementation_pack.get("field_contract"))
    target_files = [str(item) for item in implementation_pack.get("target_files") or []]
    acceptance_commands = [
        str(item) for item in implementation_pack.get("acceptance_commands") or []
    ]
    connector = str(payload.get("name") or "")
    source_hint = str(field_contract.get("source_hint") or connector)
    record_type = str(field_contract.get("record_type") or "standardized_source_record")
    report_gate = str(
        field_contract.get("report_gate")
        or "standardized records must retain provenance and pass admission gates before fact reliance"
    )
    return {
        "type": "source_strengthening_execution_plan",
        "connector": connector,
        "source_hint": source_hint,
        "record_type": record_type,
        "lane": lane,
        "first_target_file": target_files[0] if target_files else "core/connector_registry.py",
        "target_files": target_files,
        "runtime_companion": _dict(implementation_pack.get("runtime_companion")),
        "primary_acceptance_command": acceptance_commands[0] if acceptance_commands else "",
        "ordered_steps": _source_strengthening_ordered_steps(missing, lane, record_type, report_gate),
        "report_gate": report_gate,
        "promotion_gate": (
            "Only promote from lead/catalog coverage to report facts after source-specific "
            "standardized records, provenance, exact-or-strong entity match, and admission tests pass."
        ),
    }


def _source_strengthening_ordered_steps(
    missing: list[str],
    lane: str,
    record_type: str,
    report_gate: str,
) -> list[str]:
    steps = [_source_strengthening_contract_action(missing)]
    if "standardized_records" in missing:
        steps.append(
            f"Map raw or snapshot output into {record_type} records with source URL, evidence, confidence, and entity-match fields."
        )
    if "health_check" in missing:
        steps.append(
            "Add connector health/schema checks that can run in fixture or validated-snapshot mode without enabling live calls by default."
        )
    if "entity_match_gate" in missing:
        steps.append(
            "Add exact-or-strong entity matching before the connector can feed report facts or relationship graph nodes."
        )
    if "license_review" in missing:
        steps.append(
            "Record dataset license, update cadence, attribution, and local-index policy before enabling subject-level screening workflows."
        )
    if "admission_tests" in missing:
        steps.append(
            "Add source admission tests and keep the source out of default facts until the admission decision is green."
        )
    steps.append(f"Expose the result in the {lane} lane and keep the report gate visible: {report_gate}")
    return _dedupe_strings(steps)


def _source_strengthening_contract_action(missing: list[str]) -> str:
    if "standardized_records" in missing:
        return "map raw output into standardized records with source_name, source_url, evidence, confidence, and entity-match fields"
    if "health_check" in missing:
        return "add connector-level connectivity and schema health check without enabling live calls by default"
    if "entity_match_gate" in missing:
        return "add exact-or-strong entity matching before report fact promotion"
    if "license_review" in missing:
        return "record dataset license, attribution, refresh cadence, and local-index policy"
    if "admission_tests" in missing:
        return "add source admission tests and keep the connector out of default facts until they pass"
    return "review connector for production promotion"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _admission_tier_for_connector(connector: ConnectorCapability):
    from .source_admission import DataSourceTier

    if connector.authority is SourceAuthority.OFFICIAL and connector.access is SourceAccess.PUBLIC:
        return DataSourceTier.OFFICIAL_PUBLIC
    if connector.access is SourceAccess.PUBLIC and connector.shape in {
        ConnectorShape.SEARCH_ENGINE,
        ConnectorShape.WEB_PAGE,
        ConnectorShape.REST_API,
    }:
        return DataSourceTier.PUBLIC_WEB
    if connector.access is SourceAccess.LICENSED:
        return DataSourceTier.LICENSED_COMMERCIAL
    if connector.access is SourceAccess.USER_AUTHORIZED:
        return DataSourceTier.USER_AUTHORIZED_SERVICE
    if connector.shape is ConnectorShape.TELEGRAM_BOT:
        return DataSourceTier.COMMUNITY_DELIVERY
    if connector.access is SourceAccess.INTERNAL:
        return DataSourceTier.INTERNAL_PRIVATE
    return DataSourceTier.UNKNOWN


def _source_description(connector: ConnectorCapability) -> str:
    if connector.notes:
        return " ".join(str(item) for item in connector.notes[:2] if str(item).strip())
    return f"{connector.name} connector"


def _data_effectiveness_summary(connector_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    fact_sources = [
        item["name"]
        for item in connector_payloads
        if item.get("data_effectiveness", {}).get("can_feed_report_facts")
    ]
    lead_sources = [
        item["name"]
        for item in connector_payloads
        if item.get("data_effectiveness", {}).get("can_feed_report_leads")
    ]
    default_fact_sources = [
        item["name"]
        for item in connector_payloads
        if item.get("default_enabled") and item.get("data_effectiveness", {}).get("can_feed_report_facts")
    ]
    modes: dict[str, int] = {}
    outputs: dict[str, int] = {}
    for item in connector_payloads:
        effectiveness = item.get("data_effectiveness", {})
        mode = str(effectiveness.get("admission_mode") or "unknown")
        modes[mode] = modes.get(mode, 0) + 1
        for output in effectiveness.get("analysis_outputs") or []:
            outputs[str(output)] = outputs.get(str(output), 0) + 1
    return {
        "fact_capable_sources": len(fact_sources),
        "lead_capable_sources": len(lead_sources),
        "default_fact_capable_sources": len(default_fact_sources),
        "fact_source_names": fact_sources,
        "default_fact_source_names": default_fact_sources,
        "by_admission_mode": modes,
        "analysis_output_coverage": outputs,
    }


def _admission_gate_summary(connector_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    default_on = [item for item in connector_payloads if item.get("default_enabled")]
    default_fact_sources = [
        item
        for item in default_on
        if item.get("data_effectiveness", {}).get("can_feed_report_facts")
    ]
    default_lead_only_sources = [
        item
        for item in default_on
        if not item.get("data_effectiveness", {}).get("can_feed_report_facts")
        and item.get("data_effectiveness", {}).get("can_feed_report_leads")
    ]
    gate_counts: dict[str, int] = {}
    for item in connector_payloads:
        for gate in item.get("data_effectiveness", {}).get("admission_gates") or []:
            gate_counts[str(gate)] = gate_counts.get(str(gate), 0) + 1
    return {
        "default_on_count": len(default_on),
        "default_fact_source_count": len(default_fact_sources),
        "default_lead_only_source_count": len(default_lead_only_sources),
        "default_fact_sources": [
            {
                "name": item.get("name"),
                "admission_mode": item.get("data_effectiveness", {}).get("admission_mode"),
                "admission_gates": list(item.get("data_effectiveness", {}).get("admission_gates") or []),
                "analysis_outputs": list(item.get("data_effectiveness", {}).get("analysis_outputs") or [])[:8],
            }
            for item in default_fact_sources
        ],
        "default_lead_only_sources": [
            {
                "name": item.get("name"),
                "admission_mode": item.get("data_effectiveness", {}).get("admission_mode"),
                "admission_gates": list(item.get("data_effectiveness", {}).get("admission_gates") or []),
            }
            for item in default_lead_only_sources
        ],
        "gate_counts": dict(sorted(gate_counts.items())),
        "policy": "Default-on sources still require their admission gates before report-fact reliance; lead-only defaults must be corroborated before fact promotion.",
    }


def _data_effectiveness_matrix(connector_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "default_enabled": item["default_enabled"],
            "production_ready": item["production_ready"],
            **item.get("data_effectiveness", {}),
        }
        for item in connector_payloads
    ]


def default_connector_capabilities() -> list[ConnectorCapability]:
    """Return built-in connector capability metadata."""
    return [
        ConnectorCapability(
            name="default_public_intel",
            shape=ConnectorShape.SEARCH_ENGINE,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=tuple(RetrievalDomain),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=True,
            notes=(
                "Product-facing default public intelligence entrypoint.",
                "Fans out to public web, QYYJT public leads, and configured public Telegram services.",
                "Uses only public/no-credential entry points by default.",
                "Credentialed/API/private depth remains gated by datasource admission.",
            ),
            risk_flags=(),
        ),
        ConnectorCapability(
            name="multi_datasource_rest_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=tuple(RetrievalDomain),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=True,
            notes=(
                "Generic user-configured HTTP API connector with startup connectivity checks.",
            ),
        ),
        ConnectorCapability(
            name="qyyjt_tool",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.COMMERCIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.COURT_ENFORCEMENT,
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.NEWS_PUBLIC_OPINION,
                RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=True,
            notes=(
                "Default public entry maps QYYJT public-service leads into standardized records.",
                "Public-service leads are explicitly low-confidence leads, not verified facts.",
                "Credentialed/API depth remains gated by user authorization, license/terms review, provenance retention, and live validation.",
            ),
            risk_flags=("credentialed_depth_requires_admission",),
        ),
        ConnectorCapability(
            name="telegram_bot_public_service",
            shape=ConnectorShape.TELEGRAM_BOT,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.COMMUNITY,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.SOCIAL_WEB,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=True,
            notes=(
                "Default public entry supports public Telegram service delivery with provenance retained.",
                "Bridge retains bot handle, request time, returned source text, and user configuration.",
                "Live providers can be injected by the host app and are normalized through the same evidence contract.",
                "Source review reports identify missing bot handle, endpoint, authorization scope, and source description.",
                "Credentialed/private service depth remains gated by source legitimacy review, user authorization, and live transport validation.",
            ),
            risk_flags=(
                "credentialed_depth_requires_admission",
            ),
        ),
        ConnectorCapability(
            name="public_web_search",
            shape=ConnectorShape.SEARCH_ENGINE,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(
                RetrievalDomain.NEWS_PUBLIC_OPINION,
                RetrievalDomain.SOCIAL_WEB,
                RetrievalDomain.LOCATION_ASSETS,
                RetrievalDomain.IP_TECH,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=True,
            notes=(
                "Search result bridge normalizes supplied public hits into standardized records.",
                "Search results are deduplicated and can be URL-fetched when an approved fetcher is configured.",
                "Zero-config public search uses the default DuckDuckGo Instant Answer provider for starter reports.",
                "Advanced live providers can be injected as callables or configured through a self-hosted SearXNG endpoint.",
                "Provider health reports expose zero-config readiness, missing configuration, and next actions for non-technical users.",
                "Provider validation reports smoke-check configured providers, standardization, and record quality.",
            ),
            risk_flags=(),
        ),
        ConnectorCapability(
            name="gleif_lei_public_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "GLEIF public LEI API catalog entry for legal entity identity and relationship leads.",
                "Basic company-name query mapping and standardized record output are implemented.",
                "Advanced relationship traversal remains pending.",
                "Useful for overseas entity identity, parent relationship, and funder/counterparty checks.",
            ),
            risk_flags=("advanced_relationship_mapping_pending",),
        ),
        ConnectorCapability(
            name="gleif_lei_relationship_traversal_public_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "GLEIF relationship-record traversal for direct/ultimate parent and branch relationship endpoints.",
                "Keep separate from the stable LEI identity lookup so entity identity remains production-ready while relationship-depth work is verified.",
                "Emits bounded relationship-edge records with subject/related LEIs, source URLs, and exact/strong entity-match gates.",
            ),
            risk_flags=("default_off_until_deployment_review", "relationship_fact_reliance_requires_exact_or_strong_entity_match"),
        ),
        ConnectorCapability(
            name="sec_edgar_public_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.FINANCING_CAPITAL_MARKETS,
                RetrievalDomain.ADMINISTRATIVE_RISK,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "SEC EDGAR public data entry for US issuer filings, ownership forms, and capital-market signals.",
                "CIK submissions lookup and ticker-catalog standardization are implemented.",
                "Company-name to CIK resolver is still required before default production routing.",
                "Should retain accession number, filing type, filing date, and SEC URL as provenance.",
            ),
            risk_flags=("company_name_to_cik_resolver_pending", "requires_user_agent_contact"),
        ),
        ConnectorCapability(
            name="verified_github_public_profile",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized GitHub public profile lookup.",
                "Schema health and standardized public developer profile lead records are available.",
                "Use as a key-person technical-background lead until person/company context is corroborated.",
                "Live smoke is available behind WST_LIVE_VERIFIED_SOURCES=1 and is not part of default unit tests.",
            ),
            risk_flags=("explicit_enable_required", "entity_resolution_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="verified_wikipedia_enterprise_entry",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized Wikipedia public enterprise entry lookup.",
                "Schema health and standardized public encyclopedia profile lead records are available.",
                "Useful for broad company history, product, subsidiary, controversy, and industry leads with attribution retained.",
            ),
            risk_flags=("explicit_enable_required", "cc_by_sa_attribution_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="verified_crtsh_domain_lookup",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized crt.sh certificate-transparency domain discovery.",
                "Schema health and standardized certificate-transparency domain asset records are available.",
                "Useful for enterprise digital-asset and related-domain leads after domain attribution review.",
            ),
            risk_flags=("explicit_enable_required", "domain_attribution_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="verified_whois_rdap_domain_lookup",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.OWNERSHIP_CONTROL),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized ICANN RDAP/WHOIS domain public-record lookup.",
                "Schema health and standardized domain registration records are available.",
                "Useful for domain registration, nameserver, and digital-asset relationship leads after domain attribution review.",
            ),
            risk_flags=("explicit_enable_required", "domain_attribution_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="verified_cross_platform_profile_check",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized public cross-platform profile presence checks.",
                "Schema health and standardized cross-platform public profile lead records are available.",
                "Useful for enterprise key-person CDD leads and technical-background consistency checks after person-context review.",
                "Default unit tests do not run live network checks; use WST_LIVE_DEEP_PROFILE=1 for manual smoke.",
            ),
            risk_flags=("explicit_enable_required", "entity_resolution_required", "false_positive_review_required"),
        ),
        ConnectorCapability(
            name="mass_cross_platform_profiler",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only adapter for broad public cross-platform profile presence checks.",
                "Schema health and standardized mass digital-footprint lead records are available.",
                "Useful as a people-lane identity consistency lead after a user enables the source and reviews false positives.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "entity_resolution_required",
                "false_positive_review_required",
            ),
        ),
        ConnectorCapability(
            name="telegram_public_aggregation",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.ADMINISTRATIVE_RISK, RetrievalDomain.CORPORATE_REGISTRY),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only adapter for user-owned Telegram API access to public data aggregation services.",
                "Returns service plans and credential-required states unless user supplies API credentials.",
                "Schema health and standardized aggregation service-plan lead records are available.",
                "Keep lead-only until source-specific provenance, service terms, user credentials, and returned evidence are reviewed.",
            ),
            risk_flags=("explicit_enable_required", "user_credentials_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="autonomous_enterprise_registry",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.COURT_ENFORCEMENT,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only autonomous adapter for user-authorized public registry lookups.",
                "Queries Credit China, Aiqicha, GSXT, and court-public endpoints only after source enablement.",
                "Schema health and standardized public-registry lead records are available without enabling live calls by default.",
                "Keep lead-only until entity resolution, provenance, and challenge/session handling are reviewed.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "interactive_challenge_required",
                "entity_resolution_required",
                "manual_review_required",
            ),
        ),
        ConnectorCapability(
            name="autonomous_public_records",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.LOCATION_ASSETS),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only public-record aggregation adapter for user-authorized research.",
                "Schema health and standardized data-minimized public-record presence leads are available.",
                "Default unit tests assert authorization blocking and never run live network calls.",
                "Keep lead-only until identity matching, provenance, and data minimization review pass.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "entity_resolution_required",
                "data_minimization_review_required",
                "manual_review_required",
            ),
        ),
        ConnectorCapability(
            name="opensanctions_public_dataset_catalog",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.ADMINISTRATIVE_RISK,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "OpenSanctions dataset catalog entry for public sanctions, politically exposed person, and watchlist datasets.",
                "Dataset catalog rows expose license, license URL, publisher, update cadence, attribution, and local-index policy as standardized coverage evidence.",
                "Treat matches as review leads until entity resolution confidence is established.",
            ),
            risk_flags=("entity_resolution_required", "local_or_authorized_subject_index_required"),
        ),
        ConnectorCapability(
            name="opensanctions_local_subject_index",
            shape=ConnectorShape.LOCAL_FILE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.ADMINISTRATIVE_RISK,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Local OpenSanctions-compatible subject index for reviewed public or user-authorized dataset snapshots.",
                "Supports JSON, JSONL, NDJSON, and CSV records with explainable entity matching.",
                "Deployment owner supplies and updates the local index file.",
            ),
            risk_flags=("requires_configured_local_index", "dataset_refresh_policy_required"),
        ),
        ConnectorCapability(
            name="ofac_consolidated_sanctions_xml",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "U.S. Treasury OFAC official public consolidated sanctions XML for watchlist screening.",
                "Subject-level records are emitted only when entity resolution reaches review-or-better confidence.",
                "The connector retains OFAC URL, program/list metadata, raw names, and match rationale for audit.",
            ),
            risk_flags=("watchlist_match_requires_human_review",),
        ),
        ConnectorCapability(
            name="un_sc_consolidated_sanctions_xml",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "United Nations Security Council official public consolidated sanctions XML for watchlist screening.",
                "Subject-level records are emitted only when entity resolution reaches review-or-better confidence.",
                "The connector retains UN reference number, list type, listed date, aliases, and source URL for audit.",
            ),
            risk_flags=("watchlist_match_requires_human_review",),
        ),
        ConnectorCapability(
            name="idb_sanctioned_firms_dataset_catalog",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.ADMINISTRATIVE_RISK,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "IDB public sanctions dataset catalog entry for procurement debarment coverage.",
                "Catalog metadata is standardized as coverage evidence and carries the idb_local_subject_index runtime companion policy.",
                "Subject-level procurement risk facts require the configured local index and exact/strong entity matching.",
            ),
            risk_flags=("local_index_required_for_subject_facts", "catalog_coverage_only"),
        ),
        ConnectorCapability(
            name="idb_local_subject_index",
            shape=ConnectorShape.LOCAL_FILE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.PROCUREMENT_PROJECTS,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Local IDB-style subject index for reviewed public or user-authorized procurement screening snapshots.",
                "Supports JSON, JSONL, NDJSON, and CSV records with explainable entity matching.",
                "Deployment owner supplies and updates the local index file.",
            ),
            risk_flags=("requires_configured_local_index", "dataset_refresh_policy_required"),
        ),
        ConnectorCapability(
            name="world_bank_debarred_firms_public_list",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.PROCUREMENT_PROJECTS,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "World Bank official public debarred firms list for procurement exclusion screening.",
                "Subject-level evidence is emitted only on exact/strong entity-resolution match.",
                "Keep default off until latency and HTML stability are validated for each deployment.",
            ),
            risk_flags=("html_structure_monitoring_required",),
        ),
        ConnectorCapability(
            name="wikidata_public_entity_graph",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.COMMUNITY,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
                RetrievalDomain.SOCIAL_WEB,
                RetrievalDomain.IP_TECH,
            ),
            status=ConnectorStatus.ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Wikidata EntitySearch API entry for public entity graph enrichment, aliases, websites, and identifiers.",
                "EntitySearch query mapping and standardized record output are implemented.",
                "Community graph statements must stay lower-confidence unless corroborated by official or licensed sources.",
            ),
            risk_flags=("community_source_corroboration_required", "rate_limit_monitoring_required"),
        ),
        ConnectorCapability(
            name="enterprise_executive_identity_verification",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.SOCIAL_WEB),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise officer public profile consistency adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Schema health and standardized people-lane identity consistency lead records are available without enabling live calls by default.",
                "Use as a people-lane lead source after key-person context and explicit authorization.",
            ),
            risk_flags=("explicit_enable_required", "key_person_context_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="enterprise_domain_security_assessment",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.FINANCING_CAPITAL_MARKETS, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise domain security-event signal adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Schema health and standardized domain security lead records are available without enabling live calls by default.",
                "Useful for capital/compliance risk leads after exact domain attribution and explicit authorization.",
            ),
            risk_flags=("explicit_enable_required", "domain_attribution_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="enterprise_contact_attribution_verification",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.LOCATION_ASSETS, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise public contact attribution adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Schema health and standardized location/contact consistency lead records are available without enabling live calls by default.",
                "Use for goods/location consistency leads after public contact context and explicit authorization.",
            ),
            risk_flags=("explicit_enable_required", "public_contact_context_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="enterprise_key_personnel_record_crosscheck",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only key-personnel public record cross-check adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Schema health and standardized key-personnel cross-check lead records are available without enabling live calls by default.",
                "Use as a CDD lead source after key-person/company context and explicit authorization.",
            ),
            risk_flags=("explicit_enable_required", "key_person_context_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="authorized_companies_house_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.OWNERSHIP_CONTROL, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Companies House API adapter behind UserAuthorizationGate and user-provided API key.",
                "Schema health and standardized company registry search lead records are available without storing API keys.",
                "Keep explicit-only until the user provides authorization and exact/strong subject matching passes.",
            ),
            risk_flags=("api_key_required", "explicit_enable_required", "entity_match_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="authorized_sec_edgar_full_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.FINANCING_CAPITAL_MARKETS, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Full EDGAR adapter behind explicit user enablement for deeper filing lookup.",
                "Schema health and standardized issuer lookup / filing-history lead records are available without enabling live calls by default.",
                "Separate from the default-off public SEC connector; this path requires explicit user authorization.",
            ),
            risk_flags=("explicit_enable_required", "requires_user_agent_contact", "entity_match_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="authorized_opensanctions_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "OpenSanctions API adapter behind UserAuthorizationGate and user-provided API key.",
                "Schema health and standardized authorized watchlist match lead records are available.",
                "Keep explicit-only; CC BY-NC or authorized-use license review must be retained before report reliance.",
            ),
            risk_flags=("api_key_required", "explicit_enable_required", "entity_resolution_required", "license_review_required"),
        ),
        ConnectorCapability(
            name="runtime_visual_challenge_solver",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for user-authorized visual-challenge assisted public registry lookups.",
                "Schema health and standardized OCR-assisted public-query lead records are available.",
                "Lead-only until official page provenance, exact/strong subject match, and challenge/session review pass.",
            ),
            risk_flags=("explicit_enable_required", "interactive_challenge_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="runtime_username_cross_platform_verifier",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for enterprise key-person public cross-platform username verification.",
                "Schema health and standardized runtime cross-platform username lead records are available.",
                "Lead-only until person context, false-positive review, rate limits, and provenance contracts are validated.",
            ),
            risk_flags=("explicit_enable_required", "entity_resolution_required", "false_positive_review_required"),
        ),
        ConnectorCapability(
            name="runtime_aiqicha_session_lookup",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.OWNERSHIP_CONTROL, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for user-supplied Aiqicha browser-session public enterprise lookup.",
                "Schema health and standardized Aiqicha visible registry lead records are available.",
                "Keep lead-only until user session authorization, official-source provenance, and exact/strong entity match pass.",
            ),
            risk_flags=("explicit_enable_required", "user_session_required", "manual_review_required"),
        ),
        ConnectorCapability(
            name="official_china_registry_portal_catalog",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.OWNERSHIP_CONTROL,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Official China registry portal catalog entry for enterprise identity and controller leads.",
                "Validated browser-handoff snapshot parser is available for visible official fields.",
                "Exact-or-strong entity-match gating is implemented for validated snapshots before fact reliance.",
                "Manual-gate health semantics are implemented through browser handoff or validated snapshots.",
                "Kept default-off; conditional production requires validated snapshot provenance and subject match.",
            ),
            risk_flags=("manual_portal_flow", "live_health_pending", "browser_handoff_required"),
        ),
        ConnectorCapability(
            name="official_china_credit_portal_catalog",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.CORPORATE_REGISTRY,
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Official China credit-publicity portal catalog entry for administrative and credit-publicity records.",
                "Validated snapshot parser maps visible notice and penalty fields into provenance-retained records.",
                "Exact-or-strong entity-match gating is implemented for validated snapshots before fact reliance.",
                "Manual-gate health semantics are implemented through official-page handoff or validated snapshots.",
                "Kept default-off; conditional production requires validated snapshot provenance and subject match.",
            ),
            risk_flags=("manual_portal_flow", "live_health_pending", "browser_handoff_or_page_snapshot_required"),
        ),
        ConnectorCapability(
            name="official_china_court_enforcement_catalog",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(
                RetrievalDomain.COURT_ENFORCEMENT,
                RetrievalDomain.ADMINISTRATIVE_RISK,
                RetrievalDomain.PEOPLE,
                RetrievalDomain.RELATED_ENTITIES,
            ),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Official China court-enforcement catalog entry for enforcement and judicial-risk leads.",
                "Validated snapshot parser maps visible enforcement fields into provenance-retained risk records.",
                "Exact-or-strong entity-match gating is implemented for validated snapshots before fact reliance.",
                "Manual-gate health semantics are implemented through browser handoff or validated snapshots.",
                "Kept default-off; conditional production requires validated snapshot provenance and subject match.",
            ),
            risk_flags=("manual_portal_flow", "live_health_pending", "browser_handoff_required"),
        ),
        ConnectorCapability(
            name="enterprise_tax_credit_public_records",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.ADMINISTRATIVE_RISK, RetrievalDomain.FINANCING_CAPITAL_MARKETS),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "China SAT and provincial tax-credit public disclosure adapter from adapters.china_domestic_sources.",
                "Explicit-only because runtime access is mediated by UserAuthorizationGate.",
                "Use for tax-credit and major tax-violation compliance leads after subject match and provenance review.",
            ),
            risk_flags=("explicit_enable_required", "entity_match_required", "live_response_schema_monitoring_required"),
        ),
        ConnectorCapability(
            name="enterprise_judicial_asset_public_records",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.COURT_ENFORCEMENT, RetrievalDomain.ADMINISTRATIVE_RISK, RetrievalDomain.LOCATION_ASSETS),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Court judicial auction and bankruptcy/restructuring public-record adapter from adapters.china_domestic_sources.",
                "Explicit-only through UserAuthorizationGate; useful for asset-disposal and insolvency risk lanes.",
                "Promote only with case/page provenance, exact-or-strong subject match, and admission review.",
            ),
            risk_flags=("explicit_enable_required", "entity_match_required", "manual_portal_flow", "live_response_schema_monitoring_required"),
        ),
        ConnectorCapability(
            name="enterprise_mofcom_overseas_investment_public_records",
            shape=ConnectorShape.OFFICIAL_PLATFORM,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.FINANCING_CAPITAL_MARKETS, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "MOFCOM overseas investment filing public-record adapter from adapters.china_domestic_sources.",
                "Explicit-only through UserAuthorizationGate; useful for offshore investment and cross-border entity leads.",
                "Report reliance requires filing/page provenance, subject match, and investment-relationship review.",
            ),
            risk_flags=("explicit_enable_required", "entity_match_required", "cross_border_relationship_review_required"),
        ),
        ConnectorCapability(
            name="enterprise_baidu_aiqicha_public_aggregation",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.COMMERCIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.OWNERSHIP_CONTROL, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Baidu Aiqicha free public aggregation adapter from adapters.china_domestic_sources.",
                "Explicit-only because it is an aggregator surface and runtime access is user-gated.",
                "Treat rows as corroboration leads unless official-source provenance and exact-or-strong entity match are retained.",
            ),
            risk_flags=("explicit_enable_required", "aggregator_source_review_required", "official_origin_provenance_required"),
        ),
        ConnectorCapability(
            name="enterprise_shuidi_credit_public_aggregation",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.COMMERCIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.ADMINISTRATIVE_RISK, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.CONDITIONALLY_ACTIVE,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "Shuidi Credit public credit aggregation adapter from adapters.china_domestic_sources.",
                "Explicit-only because it is an aggregator/credit surface and runtime access is user-gated.",
                "Use as corroboration until official-origin provenance, subject match, and admission gates pass.",
            ),
            risk_flags=("explicit_enable_required", "aggregator_source_review_required", "official_origin_provenance_required"),
        ),
    ]
