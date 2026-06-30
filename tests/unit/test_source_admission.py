#!/usr/bin/env python3
"""Tests for datasource compliance admission framework."""
from __future__ import annotations

from core.connector_registry import ConnectorRegistry
from core.source_admission import (
    AdmissionDecision,
    DataSourceTier,
    SourceAdmissionEvaluator,
)


def test_qyyjt_can_be_conditionally_admitted_before_live_validation() -> None:
    evaluator = SourceAdmissionEvaluator()

    report = evaluator.evaluate(
        evaluator.qyyjt_admission_input(
            source_description="licensed enterprise warning service for public business records",
            terms_reviewed=False,
            live_validation_ok=False,
        )
    )

    assert report.decision is AdmissionDecision.CONDITIONAL_PRODUCTION
    assert report.production_admissible is True
    assert report.production_route == "user_configured_production"
    assert "allow user-configured production routing" in " ".join(report.next_actions)
    assert "terms_or_service_scope_not_reviewed" in report.blockers


def test_qyyjt_becomes_production_ready_with_terms_and_live_validation() -> None:
    evaluator = SourceAdmissionEvaluator()

    report = evaluator.evaluate(
        evaluator.qyyjt_admission_input(
            authorization_evidence="user-provided cookie or API authorization",
            terms_reviewed=True,
            live_validation_ok=True,
        )
    )

    assert report.decision is AdmissionDecision.PRODUCTION_READY
    assert report.score >= 90
    assert report.blockers == ()


def test_telegram_requires_underlying_source_description() -> None:
    evaluator = SourceAdmissionEvaluator()

    report = evaluator.evaluate(
        evaluator.telegram_public_service_admission_input(
            source_description="",
            authorization_evidence="user configured bot",
            live_validation_ok=True,
            terms_reviewed=True,
        )
    )

    assert report.decision is AdmissionDecision.REVIEW_REQUIRED
    assert "missing_source_description" in report.blockers
    assert "add source description" in " ".join(report.next_actions)


def test_telegram_can_be_conditionally_admitted_as_delivery_shape() -> None:
    evaluator = SourceAdmissionEvaluator()

    report = evaluator.evaluate(
        evaluator.telegram_public_service_admission_input(
            source_description="public registry aggregation returned by user-configured bot",
            authorization_evidence="user configured bot handle and scope",
            live_validation_ok=False,
            terms_reviewed=True,
        )
    )

    assert report.decision is AdmissionDecision.CONDITIONAL_PRODUCTION
    assert report.production_admissible is True
    assert report.production_route == "user_configured_production"
    assert "missing_live_validation_ok" in report.blockers


def test_evaluator_can_build_report_from_connector_metadata() -> None:
    registry = ConnectorRegistry()
    connector = registry.get("telegram_bot_public_service")
    assert connector is not None

    report = SourceAdmissionEvaluator().from_connector(
        connector,
        tier=DataSourceTier.COMMUNITY_DELIVERY,
        source_description="public or user-authorized business records",
        authorization_evidence="deployment provided service metadata",
        terms_reviewed=True,
        live_validation_ok=True,
    )

    assert report.decision is AdmissionDecision.PRODUCTION_READY
    assert report.production_admissible is True
