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
        failure_category_counts: dict[str, int] = {}
        failure_patterns: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            run_id = str(row.get("run_id") or "")
            for result in row.get("results", []):
                if not isinstance(result, dict):
                    continue
                result_company = str(result.get("company") or "")
                for diagnostic in result.get("source_diagnostics", []):
                    if not isinstance(diagnostic, dict):
                        continue
                    status = str(diagnostic.get("status") or "").strip().lower()
                    category = _monitor_failure_category(status, diagnostic)
                    source_name = _monitor_source_name(diagnostic)
                    if category == "none":
                        self._accumulate_source_trend(
                            sources,
                            source_name=source_name,
                            ok=True,
                            status=status or "success",
                            run_id=run_id,
                            company=result_company,
                        )
                        continue
                    failure_category_counts[category] = failure_category_counts.get(category, 0) + 1
                    self._accumulate_source_trend(
                        sources,
                        source_name=source_name,
                        ok=False,
                        status=status or category,
                        run_id=run_id,
                        company=result_company,
                    )
                    _accumulate_monitor_failure_pattern(
                        failure_patterns,
                        source_name=source_name,
                        category=category,
                        domain=_monitor_failure_domain(diagnostic),
                        run_id=run_id,
                        company=result_company,
                        trace_id=str(diagnostic.get("trace_id") or ""),
                    )
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
                        if not ok:
                            category = str(report.get("failure_category") or "") if isinstance(report, dict) else ""
                            category = category or _monitor_failure_category(status, {"status": status})
                            failure_category_counts[category] = failure_category_counts.get(category, 0) + 1
                            _accumulate_monitor_failure_pattern(
                                failure_patterns,
                                source_name=str(source_name),
                                category=category,
                                domain="source_health",
                                run_id=run_id,
                                company=result_company,
                                trace_id="",
                            )
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
                        if not ok:
                            category = "source_unavailable"
                            failure_category_counts[category] = failure_category_counts.get(category, 0) + 1
                            _accumulate_monitor_failure_pattern(
                                failure_patterns,
                                source_name=str(source_name),
                                category=category,
                                domain="source_health",
                                run_id=run_id,
                                company=result_company,
                                trace_id="",
                            )

        recurring_failure_patterns = _monitor_failure_pattern_rows(failure_patterns)
        normalized_sources = {
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
        }
        connector_recovery_queue = _monitor_connector_recovery_queue(
            normalized_sources,
            recurring_failure_patterns,
        )
        release_readiness_warnings = _monitor_release_readiness_warnings(
            connector_recovery_queue,
            failure_category_counts,
        )
        return {
            "run_count": len(rows),
            "source_count": len(sources),
            "failure_category_counts": dict(sorted(failure_category_counts.items())),
            "failure_pattern_count": len(failure_patterns),
            "recurring_failure_patterns": recurring_failure_patterns,
            "connector_recovery_queue": connector_recovery_queue,
            "release_readiness_warnings": release_readiness_warnings,
            "release_readiness_warning_count": len(release_readiness_warnings),
            "sources": normalized_sources,
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
            "source_diagnostics": result.source_diagnostics[:50],
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


def _monitor_source_name(row: dict[str, Any]) -> str:
    return (
        str(row.get("source") or row.get("source_name") or row.get("source_hint") or "unknown").strip()
        or "unknown"
    )


def _monitor_failure_category(status: str, row: dict[str, Any]) -> str:
    category = str(row.get("failure_category") or "").strip().lower()
    if category and category not in {"none", "success", "ok"}:
        return category
    status = str(status or row.get("status") or "").strip().lower()
    error = str(row.get("error") or "").strip().lower()
    if status in {"success", "ok", "up"}:
        return "none"
    if status in {"empty", "no_results"}:
        return "empty_result"
    if status == "timeout" or "timeout" in error or "timed out" in error:
        return "timeout"
    if status in {"down", "unavailable"}:
        return "source_unavailable"
    if status in {"failed", "error"}:
        if "unauthorized" in error or "forbidden" in error or "permission" in error:
            return "authorization"
        if "rate" in error and "limit" in error:
            return "rate_limit"
        if "connection" in error or "network" in error or "dns" in error:
            return "network"
        return "connector_error"
    if not status:
        return "unknown"
    return status


def _monitor_failure_domain(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("objective", "source", "source_name", "source_hint", "error", "domain")
    ).lower()
    if any(term in text for term in ("bond", "financ", "credit", "debt", "pledge", "freeze", "auction", "capital")):
        return "financing_capital_markets"
    if any(term in text for term in ("shareholder", "ubo", "controller", "owner", "related", "group")):
        return "ownership_control"
    if any(term in text for term in ("court", "case", "judgment", "enforcement", "penalty", "dishonesty", "legal")):
        return "legal_admin"
    if any(term in text for term in ("supplier", "customer", "procurement", "trade", "import", "export")):
        return "trade_supply_chain"
    if any(term in text for term in ("patent", "trademark", "copyright", "ip")):
        return "ip_assets"
    if any(term in text for term in ("news", "negative", "media", "opinion")):
        return "public_opinion"
    return "general_retrieval"


def _accumulate_monitor_failure_pattern(
    patterns: dict[tuple[str, str, str], dict[str, Any]],
    *,
    source_name: str,
    category: str,
    domain: str,
    run_id: str,
    company: str,
    trace_id: str,
) -> None:
    key = (source_name, category, domain)
    row = patterns.setdefault(
        key,
        {
            "source": source_name,
            "failure_category": category,
            "domain": domain,
            "count": 0,
            "run_ids": set(),
            "companies": set(),
            "trace_ids": set(),
            "operator_action": _monitor_failure_operator_action(category, source_name, domain),
        },
    )
    row["count"] += 1
    if run_id:
        row["run_ids"].add(run_id)
    if company:
        row["companies"].add(company)
    if trace_id:
        row["trace_ids"].add(trace_id)


def _monitor_failure_pattern_rows(patterns: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in patterns.values():
        rows.append(
            {
                "source": row["source"],
                "failure_category": row["failure_category"],
                "domain": row["domain"],
                "count": int(row["count"]),
                "run_ids": sorted(row["run_ids"])[:8],
                "companies": sorted(row["companies"])[:8],
                "trace_ids": sorted(row["trace_ids"])[:8],
                "operator_action": row["operator_action"],
                "is_recurring": int(row["count"]) >= 2 or len(row["run_ids"]) >= 2,
            }
        )
    rows.sort(
        key=lambda item: (
            not bool(item.get("is_recurring")),
            -int(item.get("count") or 0),
            str(item.get("failure_category")),
            str(item.get("source")),
        )
    )
    return rows[:12]


def _monitor_connector_recovery_queue(
    sources: dict[str, dict[str, Any]],
    recurring_failure_patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build an operator queue from persisted source-health trends."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for pattern in recurring_failure_patterns:
        by_source.setdefault(str(pattern.get("source") or "unknown"), []).append(pattern)

    rows: list[dict[str, Any]] = []
    for source_name, health in sources.items():
        observed_count = int(health.get("observed_count") or 0)
        down_count = int(health.get("down_count") or 0)
        availability_ratio = float(health.get("availability_ratio") or 0.0)
        patterns = by_source.get(source_name, [])
        if down_count == 0 and availability_ratio >= 0.99 and not patterns:
            continue
        top_pattern = patterns[0] if patterns else {}
        category = str(top_pattern.get("failure_category") or ("source_unavailable" if down_count else "degraded")).strip()
        domain = str(top_pattern.get("domain") or "source_health").strip()
        priority = _monitor_recovery_priority(category, availability_ratio, down_count, observed_count)
        status = _monitor_recovery_status(category, availability_ratio)
        action = (
            str(top_pattern.get("operator_action") or "").strip()
            or _monitor_failure_operator_action(category, source_name, domain)
        )
        rows.append(
            {
                "queue_id": f"MONITOR-SOURCE-RECOVERY-{len(rows) + 1}",
                "source": source_name,
                "priority": priority,
                "status": status,
                "failure_category": category,
                "domain": domain,
                "observed_count": observed_count,
                "down_count": down_count,
                "availability_ratio": round(availability_ratio, 3),
                "recurring_failure_count": sum(1 for item in patterns if item.get("is_recurring")),
                "run_ids": list(health.get("run_ids") or [])[:8],
                "companies": list(health.get("companies") or [])[:8],
                "operator_action": action,
                "release_warning": priority in {"P0", "P1"},
                "done_condition": "source_availability_recovers_above_threshold_or_release_notes_mark_degraded_coverage",
            }
        )
    rows.sort(
        key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(item.get("priority") or "P2"), 9),
            float(item.get("availability_ratio") or 0.0),
            -int(item.get("down_count") or 0),
            str(item.get("source") or ""),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["queue_id"] = f"MONITOR-SOURCE-RECOVERY-{index}"
    return rows[:12]


def _monitor_recovery_priority(category: str, availability_ratio: float, down_count: int, observed_count: int) -> str:
    category = str(category or "").strip().lower()
    if category in {"authorization", "source_unavailable"}:
        return "P0"
    if observed_count >= 2 and availability_ratio < 0.5:
        return "P0"
    if category in {"timeout", "rate_limit", "network", "connector_error"}:
        return "P1"
    if down_count:
        return "P1"
    return "P2"


def _monitor_recovery_status(category: str, availability_ratio: float) -> str:
    category = str(category or "").strip().lower()
    if category == "authorization":
        return "authorization_required"
    if category == "source_unavailable":
        return "source_down"
    if category in {"timeout", "rate_limit", "network", "connector_error"}:
        return "degraded_connector"
    if availability_ratio < 1.0:
        return "degraded_availability"
    return "monitoring"


def _monitor_release_readiness_warnings(
    connector_recovery_queue: list[dict[str, Any]],
    failure_category_counts: dict[str, int],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for item in connector_recovery_queue[:8]:
        priority = str(item.get("priority") or "P2")
        if priority not in {"P0", "P1"}:
            continue
        warnings.append(
            {
                "warning_id": f"RELEASE-SOURCE-{len(warnings) + 1}",
                "source": item.get("source"),
                "priority": priority,
                "status": item.get("status"),
                "failure_category": item.get("failure_category"),
                "availability_ratio": item.get("availability_ratio"),
                "impact": "Release remains usable, but affected source coverage must be disclosed or recovered before stronger readiness claims.",
                "operator_action": item.get("operator_action"),
                "done_condition": item.get("done_condition"),
            }
        )
    if failure_category_counts.get("authorization"):
        warnings.append(
            {
                "warning_id": f"RELEASE-SOURCE-{len(warnings) + 1}",
                "source": "authorized_sources",
                "priority": "P0",
                "status": "authorization_required",
                "failure_category": "authorization",
                "availability_ratio": None,
                "impact": "Authorized-source failures must stay default-blocked and visible in release notes.",
                "operator_action": "Confirm credentials and user authorization before enabling the affected source family.",
                "done_condition": "authorization_gate_is_explicit_and_audited_or_source_remains_disabled",
            }
        )
    return warnings[:12]


def _monitor_failure_operator_action(category: str, source: str, domain: str) -> str:
    if category == "authorization":
        return f"Confirm credentials or explicit authorization for {source} before retrying {domain}."
    if category == "timeout":
        return f"Retry {source} with lower concurrency or a larger timeout; keep {domain} marked as incomplete until recovered."
    if category == "rate_limit":
        return f"Back off {source} and retry with lower concurrency; preserve {domain} as partial coverage."
    if category == "empty_result":
        return f"Try alternate official/public sources for {domain}; empty {source} results are coverage gaps, not risk clearance."
    if category == "network":
        return f"Retry {source} after network health check; do not treat missing {domain} evidence as clean."
    return f"Repair or replace {source} for {domain}; keep affected monitor results marked as incomplete coverage."


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
