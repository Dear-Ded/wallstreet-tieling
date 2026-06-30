#!/usr/bin/env python3
"""Datasource compliance review and production-admission framework."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .connector_registry import ConnectorCapability


class DataSourceTier(str, Enum):
    OFFICIAL_PUBLIC = "official_public"
    PUBLIC_WEB = "public_web"
    LICENSED_COMMERCIAL = "licensed_commercial"
    USER_AUTHORIZED_SERVICE = "user_authorized_service"
    COMMUNITY_DELIVERY = "community_delivery"
    INTERNAL_PRIVATE = "internal_private"
    UNKNOWN = "unknown"


class AdmissionDecision(str, Enum):
    PRODUCTION_READY = "production_ready"
    CONDITIONAL_PRODUCTION = "conditional_production"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AdmissionInput:
    """Evidence supplied by a connector, deployment, or user configuration."""

    connector_name: str
    tier: DataSourceTier = DataSourceTier.UNKNOWN
    public_or_authorized: bool = False
    terms_reviewed: bool = False
    provenance_retained: bool = False
    audit_log_enabled: bool = False
    source_description: str = ""
    authorization_evidence: str = ""
    live_validation_ok: bool = False
    standardized_records_ok: bool = False
    default_enabled: bool = False
    default_public_entry: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdmissionReport:
    """Machine-readable datasource admission result."""

    connector_name: str
    tier: str
    decision: AdmissionDecision
    score: int
    production_route: str
    blockers: tuple[str, ...] = ()
    controls: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def production_admissible(self) -> bool:
        return self.decision in {
            AdmissionDecision.PRODUCTION_READY,
            AdmissionDecision.CONDITIONAL_PRODUCTION,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_name": self.connector_name,
            "tier": self.tier,
            "decision": self.decision.value,
            "score": self.score,
            "production_route": self.production_route,
            "production_admissible": self.production_admissible,
            "blockers": list(self.blockers),
            "controls": list(self.controls),
            "next_actions": list(self.next_actions),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class AdmissionPolicy:
    """Default-safe production admission policy for public/authorized sources."""

    required_controls: tuple[str, ...] = (
        "public_or_authorized",
        "provenance_retained",
        "audit_log_enabled",
        "standardized_records_ok",
    )
    conditional_controls: tuple[str, ...] = (
        "source_description",
        "authorization_evidence",
        "live_validation_ok",
    )
    disallowed_default_enabled_tiers: tuple[DataSourceTier, ...] = (
        DataSourceTier.LICENSED_COMMERCIAL,
        DataSourceTier.USER_AUTHORIZED_SERVICE,
        DataSourceTier.COMMUNITY_DELIVERY,
    )


class SourceAdmissionEvaluator:
    """Evaluates whether a datasource can enter production routing."""

    def __init__(self, policy: AdmissionPolicy | None = None):
        self.policy = policy or AdmissionPolicy()

    def evaluate(self, item: AdmissionInput) -> AdmissionReport:
        controls = self._controls(item)
        blockers: list[str] = []

        for control in self.policy.required_controls:
            if control not in controls:
                blockers.append(f"missing_{control}")
        if "source_description" not in controls:
            blockers.append("missing_source_description")
        if "live_validation_ok" not in controls:
            blockers.append("missing_live_validation_ok")
        if "authorization_evidence" not in controls and item.tier in {
            DataSourceTier.LICENSED_COMMERCIAL,
            DataSourceTier.USER_AUTHORIZED_SERVICE,
            DataSourceTier.COMMUNITY_DELIVERY,
        }:
            blockers.append("missing_authorization_evidence")

        if (
            item.default_enabled
            and item.tier in self.policy.disallowed_default_enabled_tiers
            and not item.default_public_entry
        ):
            blockers.append("cannot_default_enable_user_authorized_or_licensed_source")
        if item.tier is DataSourceTier.UNKNOWN:
            blockers.append("unknown_source_tier")
        if not item.terms_reviewed and item.tier in {
            DataSourceTier.LICENSED_COMMERCIAL,
            DataSourceTier.USER_AUTHORIZED_SERVICE,
            DataSourceTier.COMMUNITY_DELIVERY,
        }:
            blockers.append("terms_or_service_scope_not_reviewed")

        score = self._score(item, blockers)
        hard_blockers = set(blockers) - {
            "missing_live_validation_ok",
            "missing_authorization_evidence",
            "terms_or_service_scope_not_reviewed",
        }
        if not blockers and item.live_validation_ok:
            decision = AdmissionDecision.PRODUCTION_READY
            production_route = "active"
        elif self._conditional_ready(item, blockers, hard_blockers):
            decision = AdmissionDecision.CONDITIONAL_PRODUCTION
            production_route = "user_configured_production"
        elif item.public_or_authorized:
            decision = AdmissionDecision.REVIEW_REQUIRED
            production_route = "review_gate"
        else:
            decision = AdmissionDecision.REJECTED
            production_route = "blocked"

        return AdmissionReport(
            connector_name=item.connector_name,
            tier=item.tier.value,
            decision=decision,
            score=score,
            production_route=production_route,
            blockers=tuple(sorted(set(blockers))),
            controls=tuple(sorted(controls)),
            next_actions=tuple(self._next_actions(item, blockers, decision)),
            notes=item.notes,
        )

    def from_connector(
        self,
        connector: ConnectorCapability,
        *,
        tier: DataSourceTier,
        source_description: str = "",
        authorization_evidence: str = "",
        live_validation_ok: bool = False,
        terms_reviewed: bool = False,
        audit_log_enabled: bool = True,
    ) -> AdmissionReport:
        return self.evaluate(
            AdmissionInput(
                connector_name=connector.name,
                tier=tier,
                public_or_authorized=connector.access.value in {
                    "public",
                    "licensed",
                    "user_authorized",
                },
                terms_reviewed=terms_reviewed,
                provenance_retained=connector.provenance_required,
                audit_log_enabled=audit_log_enabled,
                source_description=source_description,
                authorization_evidence=authorization_evidence,
                live_validation_ok=live_validation_ok,
                standardized_records_ok=connector.standardized_records,
                default_enabled=connector.default_enabled,
                default_public_entry=connector.default_enabled and connector.access.value == "public",
                notes=connector.notes,
            )
        )

    @staticmethod
    def qyyjt_admission_input(
        *,
        source_description: str = "licensed enterprise-warning public-data aggregation service",
        authorization_evidence: str = "",
        live_validation_ok: bool = False,
        terms_reviewed: bool = False,
        default_enabled: bool = True,
    ) -> AdmissionInput:
        return AdmissionInput(
            connector_name="qyyjt_tool",
            tier=DataSourceTier.LICENSED_COMMERCIAL,
            public_or_authorized=True,
            terms_reviewed=terms_reviewed,
            provenance_retained=True,
            audit_log_enabled=True,
            source_description=source_description,
            authorization_evidence=authorization_evidence,
            live_validation_ok=live_validation_ok,
            standardized_records_ok=True,
            default_enabled=default_enabled,
            default_public_entry=True,
            notes=(
                "Default public entry may route low-confidence public leads without user credentials.",
                "Credentialed/API depth requires user authorization, service-scope review, and live validation.",
                "Fallback public-search plans remain leads, not verified facts.",
            ),
        )

    @staticmethod
    def telegram_public_service_admission_input(
        *,
        source_description: str = "",
        authorization_evidence: str = "",
        live_validation_ok: bool = False,
        terms_reviewed: bool = False,
        default_enabled: bool = True,
    ) -> AdmissionInput:
        return AdmissionInput(
            connector_name="telegram_bot_public_service",
            tier=DataSourceTier.COMMUNITY_DELIVERY,
            public_or_authorized=True,
            terms_reviewed=terms_reviewed,
            provenance_retained=True,
            audit_log_enabled=True,
            source_description=source_description,
            authorization_evidence=authorization_evidence,
            live_validation_ok=live_validation_ok,
            standardized_records_ok=True,
            default_enabled=default_enabled,
            default_public_entry=True,
            notes=(
                "Default public entry may route configured public bot/service leads.",
                "Telegram is a delivery shape; admission depends on underlying source legitimacy.",
                "Must retain bot/service metadata, source description, and authorization scope.",
            ),
        )

    def _controls(self, item: AdmissionInput) -> set[str]:
        controls: set[str] = set()
        if item.public_or_authorized:
            controls.add("public_or_authorized")
        if item.terms_reviewed:
            controls.add("terms_reviewed")
        if item.provenance_retained:
            controls.add("provenance_retained")
        if item.audit_log_enabled:
            controls.add("audit_log_enabled")
        if item.source_description.strip():
            controls.add("source_description")
        if item.authorization_evidence.strip():
            controls.add("authorization_evidence")
        if item.live_validation_ok:
            controls.add("live_validation_ok")
        if item.standardized_records_ok:
            controls.add("standardized_records_ok")
        if item.default_public_entry:
            controls.add("default_public_entry")
        return controls

    def _conditional_ready(
        self,
        item: AdmissionInput,
        blockers: list[str],
        hard_blockers: set[str],
    ) -> bool:
        tolerated = {
            "missing_authorization_evidence",
            "missing_live_validation_ok",
            "terms_or_service_scope_not_reviewed",
        }
        return (
            item.public_or_authorized
            and item.provenance_retained
            and item.audit_log_enabled
            and item.standardized_records_ok
            and item.source_description.strip()
            and not hard_blockers
            and set(blockers).issubset(tolerated)
        )

    @staticmethod
    def _score(item: AdmissionInput, blockers: list[str]) -> int:
        score = 0
        score += 20 if item.public_or_authorized else 0
        score += 15 if item.terms_reviewed else 0
        score += 15 if item.provenance_retained else 0
        score += 10 if item.audit_log_enabled else 0
        score += 10 if item.source_description.strip() else 0
        score += 10 if item.authorization_evidence.strip() else 0
        score += 10 if item.live_validation_ok else 0
        score += 10 if item.standardized_records_ok else 0
        score -= min(30, 5 * len(blockers))
        return max(0, min(100, score))

    @staticmethod
    def _next_actions(
        item: AdmissionInput,
        blockers: list[str],
        decision: AdmissionDecision,
    ) -> list[str]:
        if decision is AdmissionDecision.PRODUCTION_READY:
            return ["enable production routing for reviewed deployments and monitor live failures"]
        actions: list[str] = []
        if "unknown_source_tier" in blockers:
            actions.append("classify datasource tier before routing")
        if "missing_source_description" in blockers:
            actions.append("add source description and underlying data provenance")
        if "terms_or_service_scope_not_reviewed" in blockers:
            actions.append("record terms/service-scope review for this deployment")
        if "missing_authorization_evidence" in blockers:
            actions.append("attach user authorization evidence or license reference")
        if "missing_live_validation_ok" in blockers:
            actions.append("run live validation and record standardized output quality")
        if "cannot_default_enable_user_authorized_or_licensed_source" in blockers:
            actions.append("keep disabled by default; enable only after user configuration")
        if decision is AdmissionDecision.CONDITIONAL_PRODUCTION:
            actions.append("allow user-configured production routing with default-off safeguards")
        if not actions:
            actions.append("complete admission checklist before production routing")
        return actions
