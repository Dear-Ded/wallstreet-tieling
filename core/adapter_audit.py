#!/usr/bin/env python3
"""Adapter readiness audit built on connector capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .connector_registry import ConnectorCapability, ConnectorRegistry
from .source_admission import DataSourceTier, SourceAdmissionEvaluator


@dataclass(frozen=True)
class AdapterAuditRow:
    """One connector's implementation and readiness status."""

    name: str
    production_ready: bool
    readiness_score: int = 0
    priority: str = "P3"
    code_paths: tuple[str, ...] = ()
    test_paths: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    capability: dict[str, Any] = field(default_factory=dict)
    quality_gate: dict[str, Any] = field(default_factory=dict)
    admission: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "production_ready": self.production_ready,
            "readiness_score": self.readiness_score,
            "priority": self.priority,
            "code_paths": list(self.code_paths),
            "test_paths": list(self.test_paths),
            "blockers": list(self.blockers),
            "next_actions": list(self.next_actions),
            "capability": self.capability,
            "quality_gate": self.quality_gate,
            "admission": self.admission,
        }


class AdapterAuditor:
    """Produces an actionable readiness table for datasource adapters."""

    IMPLEMENTATION_MAP: dict[str, dict[str, tuple[str, ...]]] = {
        "default_public_intel": {
            "code_paths": (
                "adapters/default_public_intel_tool.py",
                "adapters/public_web_search_tool.py",
                "adapters/qyyjt_tool.py",
                "adapters/telegram_public_service_tool.py",
            ),
            "test_paths": (
                "tests/unit/test_default_public_intel_tool.py",
                "tests/unit/test_public_web_search_tool.py",
                "tests/unit/test_qyyjt_tool.py",
                "tests/unit/test_telegram_public_service_tool.py",
            ),
            "quality_paths": (
                "core/record_quality.py",
                "adapters/default_public_intel_tool.py",
            ),
            "quality_test_paths": (
                "tests/unit/test_record_quality.py",
                "tests/unit/test_default_public_intel_tool.py",
            ),
        },
        "multi_datasource_rest_api": {
            "code_paths": (
                "adapters/multi_datasource/__init__.py",
                "adapters/multi_datasource_tool.py",
                "bin/risk_discovery.py",
            ),
            "test_paths": (
                "tests/unit/test_multi_datasource.py",
                "tests/unit/test_risk_discovery_pipeline.py",
                "tests/unit/test_risk_discovery_cli.py",
            ),
            "quality_paths": ("core/record_quality.py",),
            "quality_test_paths": ("tests/unit/test_multi_datasource.py",),
        },
        "qyyjt_tool": {
            "code_paths": (
                "adapters/qyyjt_adapter.py",
                "adapters/qyyjt_tool.py",
            ),
            "test_paths": (
                "tests/unit/test_qyyjt_adapter.py",
                "tests/unit/test_qyyjt_tool.py",
            ),
            "quality_paths": (
                "core/record_quality.py",
                "adapters/qyyjt_tool.py",
            ),
            "quality_test_paths": (
                "tests/unit/test_record_quality.py",
                "tests/unit/test_qyyjt_tool.py",
            ),
        },
        "telegram_bot_public_service": {
            "code_paths": (
                "adapters/telegram_public_service_tool.py",
                "adapters/multi_datasource/datasources.yaml",
            ),
            "test_paths": (
                "tests/unit/test_connector_registry.py",
                "tests/unit/test_telegram_public_service_tool.py",
            ),
            "quality_paths": (
                "core/record_quality.py",
                "adapters/telegram_public_service_tool.py",
            ),
            "quality_test_paths": (
                "tests/unit/test_record_quality.py",
                "tests/unit/test_telegram_public_service_tool.py",
            ),
        },
        "public_web_search": {
            "code_paths": (
                "adapters/public_web_search_tool.py",
                "core/intelligence_retrieval.py",
            ),
            "test_paths": (
                "tests/unit/test_public_web_search_tool.py",
                "tests/unit/test_intelligence_retrieval.py",
            ),
            "quality_paths": (
                "core/record_quality.py",
                "adapters/public_web_search_tool.py",
            ),
            "quality_test_paths": (
                "tests/unit/test_record_quality.py",
                "tests/unit/test_public_web_search_tool.py",
            ),
        },
    }

    def __init__(
        self,
        *,
        registry: ConnectorRegistry | None = None,
        repo_root: str | Path | None = None,
    ):
        self.registry = registry or ConnectorRegistry()
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    def audit(self) -> dict[str, Any]:
        rows = [self._row(connector) for connector in self.registry.list()]
        return {
            "total": len(rows),
            "production_ready": sum(1 for row in rows if row.production_ready),
            "needs_work": sum(1 for row in rows if not row.production_ready),
            "rows": [row.to_dict() for row in rows],
        }

    def _row(self, connector: ConnectorCapability) -> AdapterAuditRow:
        mapping = self.IMPLEMENTATION_MAP.get(connector.name, {})
        code_paths = tuple(mapping.get("code_paths", ()))
        test_paths = tuple(mapping.get("test_paths", ()))
        quality_gate = self._quality_gate(mapping)
        admission = self._admission(connector)
        blockers = self._blockers(connector, code_paths, test_paths, quality_gate, admission)
        readiness_score = self._readiness_score(connector, code_paths, test_paths, quality_gate, blockers)
        return AdapterAuditRow(
            name=connector.name,
            production_ready=connector.production_ready and not blockers,
            readiness_score=readiness_score,
            priority=self._priority(connector, blockers, readiness_score),
            code_paths=code_paths,
            test_paths=test_paths,
            blockers=tuple(blockers),
            next_actions=tuple(self._next_actions(connector, blockers, quality_gate)),
            capability=connector.to_dict(),
            quality_gate=quality_gate,
            admission=admission,
        )

    def _blockers(
        self,
        connector: ConnectorCapability,
        code_paths: tuple[str, ...],
        test_paths: tuple[str, ...],
        quality_gate: dict[str, Any],
        admission: dict[str, Any],
    ) -> list[str]:
        blockers: list[str] = []
        if not connector.health_check:
            blockers.append("missing_health_check")
        if not connector.standardized_records:
            blockers.append("missing_standardized_records")
        if not connector.provenance_required:
            blockers.append("missing_provenance_requirement")
        if not connector.production_ready:
            blockers.append(f"connector_status:{connector.status.value}")
        if not admission.get("production_admissible", False):
            blockers.append(f"admission:{admission.get('decision', 'unknown')}")
        for path in code_paths:
            if not (self.repo_root / path).exists():
                blockers.append(f"missing_code:{path}")
        for path in test_paths:
            if not (self.repo_root / path).exists():
                blockers.append(f"missing_test:{path}")
        for missing in quality_gate.get("missing_paths", []):
            blockers.append(f"missing_quality_gate:{missing}")
        for missing in quality_gate.get("missing_test_paths", []):
            blockers.append(f"missing_quality_test:{missing}")
        return sorted(set(blockers))

    def _admission(self, connector: ConnectorCapability) -> dict[str, Any]:
        evaluator = SourceAdmissionEvaluator()
        if connector.name == "qyyjt_tool":
            return evaluator.evaluate(
                evaluator.qyyjt_admission_input(
                    source_description="default QYYJT public-service entry for public business-record leads",
                    terms_reviewed=False,
                    live_validation_ok=False,
                    default_enabled=connector.default_enabled,
                )
            ).to_dict()
        if connector.name == "telegram_bot_public_service":
            return evaluator.evaluate(
                evaluator.telegram_public_service_admission_input(
                    source_description="default public Telegram service delivery for public business-record leads",
                    terms_reviewed=False,
                    live_validation_ok=False,
                    default_enabled=connector.default_enabled,
                )
            ).to_dict()
        if connector.name in {"public_web_search", "default_public_intel"}:
            return evaluator.from_connector(
                connector,
                tier=DataSourceTier.PUBLIC_WEB,
                source_description=(
                    "default public intelligence fan-out"
                    if connector.name == "default_public_intel"
                    else "public web search provider for URL-level leads"
                ),
                terms_reviewed=True,
                live_validation_ok=True,
            ).to_dict()
        tier = self._infer_tier(connector)
        return evaluator.from_connector(
            connector,
            tier=tier,
            source_description="generic user-configured datasource",
            terms_reviewed=True,
            live_validation_ok=connector.production_ready,
        ).to_dict()

    @staticmethod
    def _infer_tier(connector: ConnectorCapability) -> DataSourceTier:
        access = connector.access.value
        authority = connector.authority.value
        if access == "public" and authority == "official":
            return DataSourceTier.OFFICIAL_PUBLIC
        if access == "public":
            return DataSourceTier.PUBLIC_WEB
        if access == "licensed":
            return DataSourceTier.LICENSED_COMMERCIAL
        if access == "user_authorized":
            return DataSourceTier.USER_AUTHORIZED_SERVICE
        if access == "internal" or authority == "internal":
            return DataSourceTier.INTERNAL_PRIVATE
        return DataSourceTier.UNKNOWN

    def _quality_gate(self, mapping: dict[str, tuple[str, ...]]) -> dict[str, Any]:
        quality_paths = tuple(mapping.get("quality_paths", ()))
        quality_test_paths = tuple(mapping.get("quality_test_paths", ()))
        missing_paths = tuple(
            path for path in quality_paths
            if not (self.repo_root / path).exists()
        )
        missing_test_paths = tuple(
            path for path in quality_test_paths
            if not (self.repo_root / path).exists()
        )
        return {
            "enabled": bool(quality_paths),
            "paths": list(quality_paths),
            "test_paths": list(quality_test_paths),
            "missing_paths": list(missing_paths),
            "missing_test_paths": list(missing_test_paths),
            "ok": bool(quality_paths) and not missing_paths and not missing_test_paths,
        }

    @staticmethod
    def _next_actions(
        connector: ConnectorCapability,
        blockers: list[str],
        quality_gate: dict[str, Any],
    ) -> list[str]:
        actions: list[str] = []
        if "missing_health_check" in blockers:
            actions.append("add connector-level connectivity/health check")
        if "missing_standardized_records" in blockers:
            actions.append("map raw output into standardized_records with source_name/source_type/evidence")
        if not quality_gate.get("ok"):
            actions.append("attach standardized record quality report and tests")
        if any(item.startswith("connector_status:") for item in blockers):
            actions.append("resolve risk flags and promote status when tests prove readiness")
        if any(item.startswith("admission:") for item in blockers):
            actions.append("complete datasource admission checklist")
        if connector.risk_flags:
            actions.append("address risk flags: " + ", ".join(connector.risk_flags))
        if not actions:
            actions.append("keep covered by smoke tests and monitor live failures")
        return actions

    @staticmethod
    def _readiness_score(
        connector: ConnectorCapability,
        code_paths: tuple[str, ...],
        test_paths: tuple[str, ...],
        quality_gate: dict[str, Any],
        blockers: list[str],
    ) -> int:
        score = 0
        if connector.status.value == "active":
            score += 25
        elif connector.status.value in {"experimental", "needs_review"}:
            score += 10
        if connector.health_check:
            score += 15
        if connector.standardized_records:
            score += 15
        if connector.provenance_required:
            score += 10
        if code_paths and all(not item.startswith("missing_code:") for item in blockers):
            score += 10
        if test_paths and all(not item.startswith("missing_test:") for item in blockers):
            score += 10
        if quality_gate.get("ok"):
            score += 15
        score -= min(20, 5 * len(connector.risk_flags))
        return max(0, min(100, score))

    @staticmethod
    def _priority(
        connector: ConnectorCapability,
        blockers: list[str],
        readiness_score: int,
    ) -> str:
        if not blockers:
            return "P3"
        high_impact_flags = {
            "needs_live_cookie_or_api_validation",
            "requires_live_search_provider",
            "requires_fetcher",
            "requires_source_legitimacy_review",
        }
        if high_impact_flags.intersection(connector.risk_flags):
            return "P0"
        if readiness_score >= 70:
            return "P1"
        if readiness_score >= 45:
            return "P2"
        return "P3"
