#!/usr/bin/env python3
"""Export a compact risk graph/timeline JSON payload for a company."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture  # noqa: E402
from core.risk_graph_export import export_risk_graph  # noqa: E402
from core.datasource_fixtures import build_datasource_fixture_pack  # noqa: E402
from core.official_public_smoke import (  # noqa: E402
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run risk discovery and export graph, evidence, events, and timeline JSON."
    )
    parser.add_argument("company", help="Company name to investigate.")
    parser.add_argument("--store", default="", help="JSONL risk-event store path.")
    parser.add_argument("--config", default="", help="YAML datasource config path.")
    parser.add_argument(
        "--retrieval-concurrency",
        type=int,
        default=4,
        help="Maximum concurrent retrieval tasks.",
    )
    parser.add_argument(
        "--query-timeout-seconds",
        type=float,
        default=20.0,
        help="Maximum seconds to wait for one retrieval task.",
    )
    parser.add_argument(
        "--fanout-rounds",
        type=int,
        default=1,
        help="Bounded entity fan-out rounds after seed retrieval.",
    )
    parser.add_argument(
        "--max-fanout-tasks",
        type=int,
        default=24,
        help="Maximum generated fan-out tasks.",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Use deterministic offline public-record fixture.",
    )
    parser.add_argument(
        "--fixture-pack",
        action="store_true",
        help="Use the multi-source datasource fixture pack for connector demos.",
    )
    parser.add_argument(
        "--official-public-smoke",
        action="store_true",
        help="Run live official/public datasource smoke with selected public sources.",
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

    result = await RiskDiscoveryPipeline().run(
        args.company,
        records=records,
        search_engine=search_engine,
        store_path=args.store or None,
        existing_plan=existing_plan,
        retrieval_concurrency=max(1, args.retrieval_concurrency),
        fanout_rounds=1 if args.official_public_smoke else max(0, args.fanout_rounds),
        max_fanout_tasks=max(0, args.max_fanout_tasks),
        identifier_fanout_only=bool(args.official_public_smoke),
        query_timeout_seconds=max(0.1, args.query_timeout_seconds),
    )
    return export_risk_graph(result).to_dict()


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = asyncio.run(run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
