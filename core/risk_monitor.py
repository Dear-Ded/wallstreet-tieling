#!/usr/bin/env python3
"""Batch monitoring loop for enterprise risk discovery."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .risk_discovery_pipeline import RiskDiscoveryPipeline, RiskDiscoveryResult
from .risk_event_store import RiskEventStore
from .storage_paths import runtime_state_path


def default_monitor_run_store_path() -> Path:
    """Default local monitor-run ledger path for product surfaces."""
    return runtime_state_path(
        "monitor-runs.jsonl",
        filename_env_var="WST_MONITOR_RUN_STORE",
    )


@dataclass(frozen=True)
class RiskMonitorRun:
    """Result of one monitoring pass across one or more companies."""

    run_id: str
    started_at: str
    completed_at: str
    company_count: int
    ok_count: int
    failed_count: int
    results: list[dict[str, Any]]
    failures: list[dict[str, str]]
    store_summary: dict[str, Any]
    alerts: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "company_count": self.company_count,
            "ok_count": self.ok_count,
            "failed_count": self.failed_count,
            "results": self.results,
            "failures": self.failures,
            "store_summary": self.store_summary,
            "alerts": self.alerts,
        }


class RiskMonitorRunStore:
    """Append-friendly JSONL ledger for monitoring runs and checkpoints."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, run: RiskMonitorRun) -> str:
        payload = run.to_dict()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return run.run_id

    def list_runs(self, *, company: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if company is not None:
                companies = {
                    str(item.get("company"))
                    for item in row.get("results", [])
                    if isinstance(item, dict)
                }
                if company not in companies:
                    continue
            rows.append(row)
        return rows

    def source_health_trends(self, *, company: str | None = None) -> dict[str, Any]:
        """Summarize configured source health across persisted monitor runs."""
        rows = self.list_runs(company=company)
        sources: dict[str, dict[str, Any]] = {}
        for row in rows:
            run_id = str(row.get("run_id") or "")
            for result in row.get("results", []):
                if not isinstance(result, dict):
                    continue
                result_company = str(result.get("company") or "")
                routing = (
                    result.get("retrieval_summary", {})
                    .get("source_routing", {})
                )
                if not isinstance(routing, dict):
                    continue
                health_reports = routing.get("health_reports", {})
                health = routing.get("health", {})
                if isinstance(health_reports, dict) and health_reports:
                    for source_name, report in health_reports.items():
                        if isinstance(report, dict):
                            ok = bool(report.get("ok", report.get("status") in {"up", "ok", "available"}))
                            status = str(report.get("status") or ("up" if ok else "down"))
                        else:
                            ok = bool(report)
                            status = "up" if ok else "down"
                        self._accumulate_source_trend(
                            sources,
                            source_name=str(source_name),
                            ok=ok,
                            status=status,
                            run_id=run_id,
                            company=result_company,
                        )
                elif isinstance(health, dict):
                    for source_name, ok_value in health.items():
                        ok = bool(ok_value)
                        self._accumulate_source_trend(
                            sources,
                            source_name=str(source_name),
                            ok=ok,
                            status="up" if ok else "down",
                            run_id=run_id,
                            company=result_company,
                        )

        return {
            "run_count": len(rows),
            "source_count": len(sources),
            "sources": {
                name: {
                    **payload,
                    "companies": sorted(payload["companies"]),
                    "run_ids": sorted(payload["run_ids"]),
                    "availability_ratio": (
                        payload["ok_count"] / payload["observed_count"]
                        if payload["observed_count"]
                        else 0.0
                    ),
                }
                for name, payload in sorted(sources.items())
            },
        }

    @staticmethod
    def _accumulate_source_trend(
        sources: dict[str, dict[str, Any]],
        *,
        source_name: str,
        ok: bool,
        status: str,
        run_id: str,
        company: str,
    ) -> None:
        row = sources.setdefault(
            source_name,
            {
                "observed_count": 0,
                "ok_count": 0,
                "down_count": 0,
                "latest_status": "",
                "companies": set(),
                "run_ids": set(),
            },
        )
        row["observed_count"] += 1
        row["ok_count"] += 1 if ok else 0
        row["down_count"] += 0 if ok else 1
        row["latest_status"] = status
        if company:
            row["companies"].add(company)
        if run_id:
            row["run_ids"].add(run_id)


class RiskMonitor:
    """Runs repeatable company monitoring scans with persistent risk events."""

    def __init__(
        self,
        *,
        pipeline: RiskDiscoveryPipeline | None = None,
        risk_event_store: RiskEventStore | str | Path | None = None,
        monitor_run_store: RiskMonitorRunStore | str | Path | None = None,
    ):
        if isinstance(risk_event_store, RiskEventStore):
            store = risk_event_store
        elif risk_event_store is not None:
            store = RiskEventStore(risk_event_store)
        else:
            store = None

        self.pipeline = pipeline or RiskDiscoveryPipeline(risk_event_store=store)
        self.risk_event_store = store or self.pipeline.risk_event_store
        if isinstance(monitor_run_store, RiskMonitorRunStore):
            self.monitor_run_store = monitor_run_store
        elif monitor_run_store is not None:
            self.monitor_run_store = RiskMonitorRunStore(monitor_run_store)
        else:
            self.monitor_run_store = RiskMonitorRunStore(default_monitor_run_store_path())

    async def run_once(
        self,
        companies: list[str],
        *,
        search_engine: Any | None = None,
        records_by_company: dict[str, list[dict[str, Any]]] | None = None,
        retrieval_concurrency: int = 4,
        query_timeout_seconds: float = 20.0,
    ) -> RiskMonitorRun:
        """Run one monitoring pass and return alert-ready summary data."""
        started_at = self._now()
        normalized_companies = self._normalize_companies(companies)
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        for company in normalized_companies:
            try:
                result = await self.pipeline.run(
                    company,
                    search_engine=search_engine,
                    records=(records_by_company or {}).get(company),
                    store_path=self.risk_event_store.path,
                    retrieval_concurrency=retrieval_concurrency,
                    query_timeout_seconds=query_timeout_seconds,
                )
            except Exception as exc:
                failures.append(
                    {
                        "company": company,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            results.append(self._monitor_result(result))

        completed_at = self._now()
        run = RiskMonitorRun(
            run_id=self._run_id(started_at, normalized_companies),
            started_at=started_at,
            completed_at=completed_at,
            company_count=len(normalized_companies),
            ok_count=len(results),
            failed_count=len(failures),
            results=results,
            failures=failures,
            store_summary=self.risk_event_store.summary(),
            alerts=self.risk_event_store.latest_alerts(limit=20),
        )
        if self.monitor_run_store is not None:
            self.monitor_run_store.append(run)
        return run

    @staticmethod
    def _monitor_result(result: RiskDiscoveryResult) -> dict[str, Any]:
        return {
            "company": result.company,
            "ok": result.ok,
            "evidence_count": result.evidence_count,
            "risk_event_count": result.risk_event_count,
            "persisted": result.risk_event_summary.get("persisted", 0),
            "alert_count": result.risk_event_summary.get("alert_count", 0),
            "delta": result.risk_event_summary.get("delta", {}),
            "first_alert": (
                result.risk_event_summary["alerts"][0]
                if result.risk_event_summary.get("alerts")
                else None
            ),
            "retrieval_summary": result.retrieval_summary,
        }

    @staticmethod
    def _normalize_companies(companies: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for company in companies:
            value = " ".join(str(company).split())
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _run_id(started_at: str, companies: list[str]) -> str:
        payload = json.dumps(
            {"started_at": started_at, "companies": companies},
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"monitor:{digest}"


def run_monitor_once(
    companies: list[str],
    *,
    risk_event_store: RiskEventStore | str | Path | None = None,
    monitor_run_store: RiskMonitorRunStore | str | Path | None = None,
    search_engine: Any | None = None,
    records_by_company: dict[str, list[dict[str, Any]]] | None = None,
    retrieval_concurrency: int = 4,
) -> RiskMonitorRun:
    """Synchronous helper for CLI scripts and smoke checks."""
    monitor = RiskMonitor(
        risk_event_store=risk_event_store,
        monitor_run_store=monitor_run_store,
    )
    return asyncio.run(
        monitor.run_once(
            companies,
            search_engine=search_engine,
            records_by_company=records_by_company,
            retrieval_concurrency=retrieval_concurrency,
        )
    )
