#!/usr/bin/env python3
"""Quality checks for standardized evidence records."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RecordQualityFinding:
    """One structured issue found in a standardized record."""

    severity: str
    code: str
    message: str
    index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "index": self.index,
        }


@dataclass(frozen=True)
class RecordQualityReport:
    """Adapter-facing quality report for standardized records."""

    ok: bool
    record_count: int
    finding_count: int
    findings: list[RecordQualityFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record_count": self.record_count,
            "finding_count": self.finding_count,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def audit_standardized_records(records: list[dict[str, Any]]) -> RecordQualityReport:
    """Validate evidence-pipeline records without blocking experimental sources.

    The report is intended for connector readiness gates and CI smoke tests. It
    checks for traceability and useful graph inputs, not final factual truth.
    """
    findings: list[RecordQualityFinding] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.append(_finding(index, "error", "record_not_object", "record must be a dict"))
            continue

        _require_text(findings, index, record, "source_name")
        _require_text(findings, index, record, "source_type")
        if not _has_any_text(record, ("entity", "title", "summary")):
            findings.append(
                _finding(
                    index,
                    "error",
                    "missing_subject",
                    "record must include at least one of entity/title/summary",
                )
            )
        if not _has_any_text(record, ("url", "published_at", "retrieved_at")):
            findings.append(
                _finding(
                    index,
                    "warning",
                    "weak_temporal_or_url_provenance",
                    "record should include url, published_at, or retrieved_at for stronger provenance",
                )
            )
        if not isinstance(record.get("evidence"), list) or not record.get("evidence"):
            findings.append(
                _finding(
                    index,
                    "warning",
                    "missing_evidence_claims",
                    "record should include evidence claim objects",
                )
            )
        confidence = record.get("confidence", 0.5)
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            findings.append(_finding(index, "error", "invalid_confidence", "confidence must be numeric"))
        else:
            if value < 0 or value > 1:
                findings.append(
                    _finding(index, "error", "invalid_confidence", "confidence must be between 0 and 1")
                )

    has_error = any(finding.severity == "error" for finding in findings)
    return RecordQualityReport(
        ok=not has_error,
        record_count=len(records),
        finding_count=len(findings),
        findings=findings,
    )


def _require_text(
    findings: list[RecordQualityFinding],
    index: int,
    record: dict[str, Any],
    key: str,
) -> None:
    if not str(record.get(key) or "").strip():
        findings.append(_finding(index, "error", f"missing_{key}", f"record must include {key}"))


def _has_any_text(record: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(str(record.get(key) or "").strip() for key in keys)


def _finding(index: int, severity: str, code: str, message: str) -> RecordQualityFinding:
    return RecordQualityFinding(
        severity=severity,
        code=code,
        message=message,
        index=index,
    )
