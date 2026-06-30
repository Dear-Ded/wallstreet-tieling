#!/usr/bin/env python3
"""Tests for standardized record quality gates."""
from __future__ import annotations

import asyncio

from adapters.public_web_search_tool import public_web_results_to_standardized_records
from adapters.qyyjt_tool import qyyjt_result_to_standardized_records
from adapters.telegram_public_service_tool import (
    TelegramPublicService,
    telegram_public_service_results_to_standardized_records,
)
from core.record_quality import audit_standardized_records


def test_audit_accepts_public_web_records_with_provenance() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Co",
            [
                {
                    "title": "Demo Co public filing",
                    "url": "https://example.com/filing",
                    "snippet": "Public filing lead.",
                    "confidence": 0.6,
                }
            ],
        )
    )

    report = audit_standardized_records(records)

    assert report.ok is True
    assert report.record_count == 1
    assert not [finding for finding in report.findings if finding.severity == "error"]


def test_audit_accepts_telegram_records_but_flags_missing_url_as_warning() -> None:
    records = telegram_public_service_results_to_standardized_records(
        "Demo Co",
        [{"title": "Demo bot lead", "text": "Public service lead.", "confidence": 0.4}],
        service=TelegramPublicService(
            name="demo_bot",
            bot_handle="@demo_bot",
            source_description="User-authorized public service.",
        ),
    )

    report = audit_standardized_records(records)

    assert report.ok is True
    assert any(finding.code == "weak_temporal_or_url_provenance" for finding in report.findings)


def test_audit_accepts_qyyjt_records_and_rejects_invalid_confidence() -> None:
    records = qyyjt_result_to_standardized_records(
        {
            "company": "Demo Co",
            "api_data": {"risk": {"status": "hit"}},
        }
    )
    records.append(
        {
            "source_name": "bad_source",
            "source_type": "test",
            "entity": "Demo Co",
            "title": "Bad confidence",
            "url": "https://example.com/bad",
            "confidence": 2,
            "evidence": [{"claim": "bad"}],
        }
    )

    report = audit_standardized_records(records)

    assert report.ok is False
    assert any(finding.code == "invalid_confidence" for finding in report.findings)
    assert not [
        finding for finding in report.findings
        if finding.index == 0 and finding.code == "weak_temporal_or_url_provenance"
    ]


def test_audit_rejects_records_without_source_or_subject() -> None:
    report = audit_standardized_records([{"confidence": 0.5}])

    assert report.ok is False
    codes = {finding.code for finding in report.findings}
    assert {"missing_source_name", "missing_source_type", "missing_subject"} <= codes
