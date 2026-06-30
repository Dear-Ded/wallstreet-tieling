#!/usr/bin/env python3
"""Run one batch risk-monitoring pass for companies."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.risk_discovery_pipeline import offline_enforcement_fixture  # noqa: E402
from core.risk_monitor import (  # noqa: E402
    RiskMonitor,
    RiskMonitorRunStore,
    default_monitor_run_store_path,
)


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one enterprise risk monitoring pass."
    )
    parser.add_argument(
        "companies",
        nargs="*",
        help="Company names to monitor.",
    )
    parser.add_argument(
        "--companies-file",
        default="",
        help="UTF-8 text file with one company per line.",
    )
    parser.add_argument(
        "--store",
        default="",
        help="JSONL risk-event store path. Defaults to the product store.",
    )
    parser.add_argument(
        "--run-store",
        default="",
        help="JSONL monitor-run ledger path. Defaults to the product monitor-run store.",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="List persisted monitor runs instead of starting a new scan.",
    )
    parser.add_argument(
        "--source-health",
        action="store_true",
        help="Summarize datasource health trends from persisted monitor runs.",
    )
    parser.add_argument(
        "--company-filter",
        default="",
        help="Optional company filter for --history or --source-health.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum monitor-run history rows to return.",
    )
    parser.add_argument(
        "--config",
        default="",
        help="YAML datasource config path for live configured-source monitoring.",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Use deterministic offline public-record fixtures. No network, key, or model required.",
    )
    parser.add_argument(
        "--retrieval-concurrency",
        type=int,
        default=4,
        help="Maximum concurrent retrieval tasks per company.",
    )
    return parser


def load_companies(args: argparse.Namespace) -> list[str]:
    companies = list(args.companies)
    if args.companies_file:
        path = Path(args.companies_file)
        companies.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return companies


async def run(args: argparse.Namespace) -> dict:
    run_store_path = args.run_store or default_monitor_run_store_path()
    if args.history or args.source_health:
        run_store = RiskMonitorRunStore(run_store_path)
        company_filter = args.company_filter or (args.companies[0] if args.companies else "")
        if args.source_health:
            return run_store.source_health_trends(company=company_filter or None)
        rows = run_store.list_runs(company=company_filter or None)
        limit = max(1, args.limit)
        return {
            "run_count": len(rows),
            "runs": rows[-limit:][::-1],
            "company_filter": company_filter or None,
            "run_store": str(run_store.path),
        }

    companies = load_companies(args)
    if not companies:
        raise SystemExit("provide at least one company or --companies-file")
    if args.config and args.offline_fixture:
        raise SystemExit("--config and --offline-fixture are mutually exclusive")

    search_engine = None
    if args.config:
        from adapters.multi_datasource import SearchEngine

        await SearchEngine.initialize(args.config)
        search_engine = SearchEngine

    records_by_company = None
    if args.offline_fixture:
        records_by_company = {
            company: offline_enforcement_fixture(company)
            for company in companies
        }

    monitor = RiskMonitor(
        risk_event_store=args.store or None,
        monitor_run_store=run_store_path,
    )
    result = await monitor.run_once(
        companies,
        search_engine=search_engine,
        records_by_company=records_by_company,
        retrieval_concurrency=max(1, args.retrieval_concurrency),
    )
    return result.to_dict()


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = asyncio.run(run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
