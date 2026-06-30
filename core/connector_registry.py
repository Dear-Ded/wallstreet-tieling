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
        if self.name == "qyyjt_tool":
            return "authorized_fact_source_when_field_contract_passes"
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized GitHub public profile lookup.",
                "Use as a key-person technical-background lead until entity context and standardized records are added.",
                "Live smoke is available behind WST_LIVE_VERIFIED_SOURCES=1 and is not part of default unit tests.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "entity_resolution_required"),
        ),
        ConnectorCapability(
            name="verified_wikipedia_enterprise_entry",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized Wikipedia public enterprise entry lookup.",
                "Useful for broad company history, product, subsidiary, controversy, and industry leads.",
                "Treat as corroboration-needed public lead until extraction and provenance contracts are standardized.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "cc_by_sa_attribution_required"),
        ),
        ConnectorCapability(
            name="verified_crtsh_domain_lookup",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized crt.sh certificate-transparency domain discovery.",
                "Useful for enterprise digital-asset and related-domain leads.",
                "Keep lead-only until domain ownership attribution and standardized records are validated.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "domain_attribution_required"),
        ),
        ConnectorCapability(
            name="verified_whois_rdap_domain_lookup",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.IP_TECH, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.OWNERSHIP_CONTROL),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized ICANN RDAP/WHOIS domain public-record lookup.",
                "Useful for domain registration, nameserver, and digital-asset relationship leads.",
                "Keep lead-only until domain ownership attribution and privacy-redaction handling are standardized.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "domain_attribution_required"),
        ),
        ConnectorCapability(
            name="verified_cross_platform_profile_check",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Verified runtime adapter for user-authorized public cross-platform profile presence checks.",
                "Useful for enterprise key-person CDD leads and technical-background consistency checks.",
                "Default unit tests do not run live network checks; use WST_LIVE_DEEP_PROFILE=1 for manual smoke.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "entity_resolution_required"),
        ),
        ConnectorCapability(
            name="mass_cross_platform_profiler",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only adapter for broad public cross-platform profile presence checks.",
                "Useful as a people-lane identity consistency lead after a user enables the source.",
                "Keep lead-only until identity matching, false-positive handling, and provenance contracts are reviewed.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "lead_only_until_standardized",
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only adapter for user-owned Telegram API access to public data aggregation services.",
                "Returns service plans and credential-required states unless user supplies API credentials.",
                "Keep lead-only until source-specific provenance, service terms, and standardized output contracts are reviewed.",
            ),
            risk_flags=("explicit_enable_required", "user_credentials_required", "lead_only_until_standardized"),
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only autonomous adapter for user-authorized public registry lookups.",
                "Queries Credit China, Aiqicha, GSXT, and court-public endpoints only after source enablement.",
                "Keep lead-only until field contracts, entity resolution, and challenge handling are reviewed.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "lead_only_until_standardized",
                "interactive_challenge_required",
                "entity_resolution_required",
            ),
        ),
        ConnectorCapability(
            name="autonomous_public_records",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.LOCATION_ASSETS),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only public-record aggregation adapter for user-authorized research.",
                "Default unit tests assert authorization blocking and never run live network calls.",
                "Keep lead-only until identity matching, provenance, and data minimization contracts are reviewed.",
            ),
            risk_flags=(
                "explicit_enable_required",
                "lead_only_until_standardized",
                "entity_resolution_required",
                "data_minimization_review_required",
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "OpenSanctions dataset catalog entry for public sanctions, politically exposed person, and watchlist datasets.",
                "Dataset license, update cadence, and local indexing strategy must be selected before production enablement.",
                "Treat matches as review leads until entity resolution confidence is established.",
            ),
            risk_flags=("license_review_required", "entity_resolution_required"),
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=True,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "IDB public sanctions dataset catalog entry for procurement debarment coverage.",
                "Catalog metadata is usable now; subject-level matching requires a cached local index.",
                "Treat future matches as review leads until entity resolution confidence is established.",
            ),
            risk_flags=("local_index_required", "entity_resolution_required"),
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise officer public profile consistency adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Use as a people-lane lead source until entity-match and standardized-record admission are added.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized"),
        ),
        ConnectorCapability(
            name="enterprise_domain_security_assessment",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.FINANCING_CAPITAL_MARKETS, RetrievalDomain.IP_TECH),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise domain security-event signal adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Useful for capital/compliance risk leads, not default report facts.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized"),
        ),
        ConnectorCapability(
            name="enterprise_contact_attribution_verification",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.LOCATION_ASSETS, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only enterprise public contact attribution adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Use for goods/location consistency leads after public contact context is available.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized"),
        ),
        ConnectorCapability(
            name="enterprise_key_personnel_record_crosscheck",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only key-personnel public record cross-check adapter.",
                "Requires UserAuthorizationGate enablement before any network request.",
                "Use as a CDD lead source until entity resolution and provenance contracts are complete.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized"),
        ),
        ConnectorCapability(
            name="authorized_companies_house_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.OWNERSHIP_CONTROL, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Companies House API adapter behind UserAuthorizationGate and user-provided API key.",
                "Keep explicit-only until credential handling, health checks, and standardized records are validated.",
            ),
            risk_flags=("api_key_required", "explicit_enable_required", "standardized_records_pending"),
        ),
        ConnectorCapability(
            name="authorized_sec_edgar_full_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.FINANCING_CAPITAL_MARKETS, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Full EDGAR adapter behind explicit user enablement for deeper filing lookup.",
                "Separate from the default-off public SEC connector until runtime health and field contracts are validated.",
            ),
            risk_flags=("explicit_enable_required", "requires_user_agent_contact", "standardized_records_pending"),
        ),
        ConnectorCapability(
            name="authorized_opensanctions_api",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "OpenSanctions API adapter behind UserAuthorizationGate and user-provided API key.",
                "Keep explicit-only until license review, entity resolution, and standardized output contracts are complete.",
            ),
            risk_flags=("api_key_required", "license_review_required", "explicit_enable_required", "entity_resolution_required"),
        ),
        ConnectorCapability(
            name="runtime_visual_challenge_solver",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.ADMINISTRATIVE_RISK),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for user-authorized visual-challenge assisted public registry lookups.",
                "Catalog-visible only until standardized records, live health, and source-specific admission are validated.",
            ),
            risk_flags=("explicit_enable_required", "interactive_challenge_required", "standardized_records_pending"),
        ),
        ConnectorCapability(
            name="runtime_username_cross_platform_verifier",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.PEOPLE, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for enterprise key-person public cross-platform username verification.",
                "Lead-only until user authorization, entity context, rate limits, and provenance contracts are validated.",
            ),
            risk_flags=("explicit_enable_required", "lead_only_until_standardized", "entity_resolution_required"),
        ),
        ConnectorCapability(
            name="runtime_aiqicha_session_lookup",
            shape=ConnectorShape.WEB_PAGE,
            access=SourceAccess.USER_AUTHORIZED,
            authority=SourceAuthority.PUBLIC_WEB,
            domains=(RetrievalDomain.CORPORATE_REGISTRY, RetrievalDomain.OWNERSHIP_CONTROL, RetrievalDomain.RELATED_ENTITIES),
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=False,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Explicit-only runtime adapter for user-supplied Aiqicha browser-session public enterprise lookup.",
                "Keep as lead-only catalog entry until session handling, parser contracts, and admission rules are reviewed.",
            ),
            risk_flags=("explicit_enable_required", "user_session_required", "standardized_records_pending"),
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Official China registry portal catalog entry for enterprise identity and controller leads.",
                "Validated browser-handoff snapshot parser is available for visible official fields.",
                "Kept default-off until stable live health semantics and capture workflow are validated.",
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Official China credit-publicity portal catalog entry for administrative and credit-publicity records.",
                "Validated snapshot parser maps visible notice and penalty fields into provenance-retained records.",
                "Kept disabled until live health semantics and official-page capture workflow are validated.",
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
            status=ConnectorStatus.NEEDS_REVIEW,
            configurable_endpoint=True,
            health_check=False,
            standardized_records=False,
            default_enabled=False,
            notes=(
                "Official China court-enforcement catalog entry for enforcement and judicial-risk leads.",
                "Validated snapshot parser maps visible enforcement fields into provenance-retained risk records.",
                "Kept disabled until stable public access pattern, live health semantics, and capture workflow are validated.",
            ),
            risk_flags=("manual_portal_flow", "live_health_pending", "browser_handoff_required"),
        ),
    ]
