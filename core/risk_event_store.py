#!/usr/bin/env python3
"""Persistent risk-event ledger for investigative monitoring."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .intelligence_retrieval import EvidenceGraph, RiskEvent, RiskSeverity


@dataclass(frozen=True)
class StoredRiskEvent:
    company: str
    event: RiskEvent
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    seen_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at or self.first_seen_at,
            "seen_count": self.seen_count,
            "event": {
                "id": self.event.id,
                "category": self.event.category.value,
                "title": self.event.title,
                "severity": self.event.severity.value,
                "entity_ids": list(self.event.entity_ids),
                "evidence_ids": list(self.event.evidence_ids),
                "confidence": self.event.confidence,
                "rationale": self.event.rationale,
                "status": self.event.status,
            },
        }


class RiskEventStore:
    """Append-friendly JSONL storage for discovered risk events."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, company: str, events: list[RiskEvent], *, observed_at: str | None = None) -> int:
        observed_at = observed_at or self._now()
        existing_ids = {
            row["event"]["id"]
            for row in self._read_rows()
            if row.get("company") == company
        }
        rows = [
            StoredRiskEvent(
                company=company,
                event=event,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                seen_count=1,
            ).to_dict()
            for event in events
            if event.id not in existing_ids
        ]
        if not rows:
            return 0

        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        return len(rows)

    def append_from_graph(self, company: str, graph: EvidenceGraph, *, scan_id: str | None = None) -> dict[str, Any]:
        """Persist graph risk events and return a monitoring-ready summary."""
        observed_at = self._now()
        scan_id = scan_id or self._scan_id(company, observed_at)
        delta = self.diff_current_events(company, list(graph.risk_events), observed_at=observed_at)
        persisted = self.append(company, list(graph.risk_events), observed_at=observed_at)
        touched = self._mark_recurring_events(
            company,
            delta.get("recurring_event_ids", []),
            observed_at=observed_at,
        )
        alerts = self.latest_alerts(company=company)
        return {
            "scan_id": scan_id,
            "observed_at": observed_at,
            "persisted": persisted,
            "touched": touched,
            "current": len(graph.risk_events),
            "delta": delta,
            "alerts": alerts,
            "alert_count": len(alerts),
            "store": self.summary(),
        }

    def diff_current_events(
        self,
        company: str,
        events: list[RiskEvent],
        *,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Compare current scan events with the historical event ledger.

        The store is append-only, so "not_seen_in_current_scan" is a monitoring
        signal instead of proof that the underlying risk is resolved.
        """
        observed_at = observed_at or self._now()
        previous_rows = self.list_events(company=company, status="open")
        previous_by_id = {
            str(row.get("event", {}).get("id")): row
            for row in previous_rows
            if row.get("event", {}).get("id")
        }
        current_by_id = {event.id: event for event in events}

        new_ids = sorted(set(current_by_id) - set(previous_by_id))
        recurring_ids = sorted(set(current_by_id) & set(previous_by_id))
        not_seen_ids = sorted(set(previous_by_id) - set(current_by_id))

        return {
            "observed_at": observed_at,
            "new_event_count": len(new_ids),
            "recurring_event_count": len(recurring_ids),
            "not_seen_in_current_scan_count": len(not_seen_ids),
            "new_events": [self._event_delta_row(company, current_by_id[event_id]) for event_id in new_ids],
            "recurring_events": [
                {
                    **previous_by_id[event_id],
                    "last_seen_at": observed_at,
                    "seen_count": int(previous_by_id[event_id].get("seen_count") or 1) + 1,
                }
                for event_id in recurring_ids
            ],
            "recurring_event_ids": recurring_ids,
            "not_seen_in_current_scan": [previous_by_id[event_id] for event_id in not_seen_ids],
            "note": "not_seen_in_current_scan means the event was not reproduced in this run; it is not proof of risk resolution.",
        }

    def list_events(
        self,
        *,
        company: str | None = None,
        severity: RiskSeverity | str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        severity_value = severity.value if isinstance(severity, RiskSeverity) else severity
        rows = self._read_rows()
        if company is not None:
            rows = [row for row in rows if row.get("company") == company]
        if severity_value is not None:
            rows = [row for row in rows if row.get("event", {}).get("severity") == severity_value]
        if status is not None:
            rows = [row for row in rows if row.get("event", {}).get("status") == status]
        return rows

    def summary(self) -> dict[str, Any]:
        rows = self._read_rows()
        by_severity: dict[str, int] = {}
        by_company: dict[str, int] = {}
        for row in rows:
            severity = str(row.get("event", {}).get("severity", "unknown"))
            company = str(row.get("company", "unknown"))
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_company[company] = by_company.get(company, 0) + 1
        return {
            "total_events": len(rows),
            "by_severity": by_severity,
            "by_company": by_company,
        }

    def latest_alerts(
        self,
        *,
        company: str | None = None,
        severities: tuple[RiskSeverity | str, ...] = (RiskSeverity.CRITICAL, RiskSeverity.HIGH),
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return newest high-priority open events for monitoring surfaces."""
        severity_values = {
            severity.value if isinstance(severity, RiskSeverity) else str(severity)
            for severity in severities
        }
        rows = self.list_events(company=company, status="open")
        rows = [
            row for row in rows
            if row.get("event", {}).get("severity") in severity_values
        ]
        return rows[-limit:][::-1]

    @staticmethod
    def _event_delta_row(company: str, event: RiskEvent) -> dict[str, Any]:
        now = RiskEventStore._now()
        return StoredRiskEvent(
            company=company,
            event=event,
            first_seen_at=now,
            last_seen_at=now,
        ).to_dict()

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows

    def _mark_recurring_events(
        self,
        company: str,
        event_ids: list[str],
        *,
        observed_at: str,
    ) -> int:
        if not event_ids or not self.path.exists():
            return 0
        event_id_set = set(event_ids)
        rows = self._read_rows()
        touched = 0
        for row in rows:
            if row.get("company") != company:
                continue
            event_id = row.get("event", {}).get("id")
            if event_id not in event_id_set:
                continue
            row["last_seen_at"] = observed_at
            row["seen_count"] = int(row.get("seen_count") or 1) + 1
            touched += 1
        if touched:
            with self.path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                    handle.write("\n")
        return touched

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _scan_id(company: str, observed_at: str) -> str:
        safe_company = "-".join(company.lower().split())[:48] or "unknown"
        safe_time = observed_at.replace(":", "").replace("+", "z")
        return f"scan:{safe_company}:{safe_time}"
