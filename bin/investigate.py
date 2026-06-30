#!/usr/bin/env python3
"""Run one-click investigation and return a product-facing packet."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.datasource_fixtures import build_datasource_fixture_pack  # noqa: E402
from core.investigation import build_investigation_packet  # noqa: E402
from core.official_public_smoke import (  # noqa: E402
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)
from core.one_click_defaults import resolve_one_click_retrieval_async  # noqa: E402
from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture  # noqa: E402
from core.risk_graph_export import export_risk_graph  # noqa: E402


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-click company investigation packet: verdict, report, graph, evidence, and watch seed."
    )
    parser.add_argument("company", help="Company name or unified social credit identifier.")
    parser.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"], help="Investigation mode label.")
    parser.add_argument("--store", default="", help="JSONL risk-event store path.")
    parser.add_argument("--config", default="", help="YAML datasource config path.")
    parser.add_argument("--retrieval-concurrency", type=int, default=4, help="Maximum concurrent retrieval tasks.")
    parser.add_argument("--query-timeout-seconds", type=float, default=20.0, help="Maximum seconds to wait for one retrieval task.")
    parser.add_argument("--fanout-rounds", type=int, default=1, help="Bounded entity fan-out rounds.")
    parser.add_argument("--max-fanout-tasks", type=int, default=24, help="Maximum generated fan-out tasks.")
    parser.add_argument("--offline-fixture", action="store_true", help="Use deterministic offline public-record fixture.")
    parser.add_argument("--fixture-pack", action="store_true", help="Use the multi-source datasource fixture pack.")
    parser.add_argument("--official-public-smoke", action="store_true", help="Run live official/public datasource smoke with selected public sources.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON packet explicitly. This is also the default unless --report-only is used.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print Markdown report instead of the full JSON packet.",
    )
    return parser


async def run(args: argparse.Namespace) -> dict:
    mode_count = sum(bool(item) for item in (args.config, args.offline_fixture, args.fixture_pack, args.official_public_smoke))
    if mode_count > 1:
        raise SystemExit("--config, --offline-fixture, --fixture-pack, and --official-public-smoke are mutually exclusive")

    records = None
    if args.fixture_pack:
        records = build_datasource_fixture_pack(args.company).all_records()
    elif args.offline_fixture:
        records = offline_enforcement_fixture(args.company)

    search_engine = None
    existing_plan = None
    config_path = args.config
    if args.official_public_smoke:
        config_path = str(build_official_public_smoke_config())
        existing_plan = build_official_public_smoke_plan(args.company)
    if config_path:
        from adapters.multi_datasource import SearchEngine

        await SearchEngine.initialize(config_path)
        search_engine = SearchEngine

    selected = await resolve_one_click_retrieval_async(
        company=args.company,
        records=records,
        search_engine=search_engine,
        existing_plan=existing_plan,
        fanout_rounds=clamp_int(args.fanout_rounds, 0, 3),
        default_enabled=True,
    )

    result = await RiskDiscoveryPipeline().run(
        args.company,
        records=selected.records,
        search_engine=selected.search_engine,
        store_path=args.store or None,
        existing_plan=selected.existing_plan,
        retrieval_concurrency=clamp_int(args.retrieval_concurrency, 1, 20),
        fanout_rounds=1 if args.official_public_smoke else selected.fanout_rounds,
        max_fanout_tasks=clamp_int(args.max_fanout_tasks, 0, 80),
        identifier_fanout_only=bool(args.official_public_smoke),
        query_timeout_seconds=clamp_float(args.query_timeout_seconds, 0.1, 120.0),
    )
    graph_payload = export_risk_graph(result).to_dict()
    return build_investigation_packet(
        graph_payload,
        input_text=args.company,
        mode=args.mode,
    ).to_dict()


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    if args.json and args.report_only:
        raise SystemExit("--json and --report-only are mutually exclusive")
    payload = asyncio.run(run(args))
    if args.report_only:
        print(payload["report_markdown"])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
