#!/usr/bin/env python3
"""Run the executable risk-discovery pipeline from a company name."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.risk_discovery_pipeline import (  # noqa: E402
    RiskDiscoveryPipeline,
    offline_enforcement_fixture,
)
from core.datasource_fixtures import build_datasource_fixture_pack  # noqa: E402
from core.official_public_smoke import (  # noqa: E402
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)
from core.one_click_defaults import resolve_one_click_retrieval_async  # noqa: E402


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run company-name to retrieval diagnostics, risk events, and alerts."
    )
    parser.add_argument("company", help="Company name to investigate.")
    parser.add_argument(
        "--store",
        default="",
        help="JSONL risk-event store path. Defaults to the product store.",
    )
    parser.add_argument(
        "--config",
        default="",
        help=(
            "YAML datasource config path. When provided, the CLI initializes "
            "SearchEngine, runs datasource health checks, and routes retrieval "
            "through currently available sources."
        ),
    )
    parser.add_argument(
        "--retrieval-concurrency",
        type=int,
        default=4,
        help="Maximum concurrent retrieval tasks in the risk discovery pipeline.",
    )
    parser.add_argument(
        "--query-timeout-seconds",
        type=float,
        default=20.0,
        help="Maximum seconds to wait for one retrieval task before recording a timeout diagnostic.",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Use deterministic offline public-record fixture. No network, key, or model required.",
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
    parser.add_argument(
        "--include-plan",
        action="store_true",
        help="Include the full retrieval plan in JSON output.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact human-readable run summary instead of JSON.",
    )
    return parser


async def run(args: argparse.Namespace) -> dict:
    pipeline = RiskDiscoveryPipeline()
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
        fanout_rounds=1,
        default_enabled=True,
    )

    result = await pipeline.run(
        args.company,
        records=selected.records,
        search_engine=selected.search_engine,
        store_path=args.store or None,
        existing_plan=selected.existing_plan,
        retrieval_concurrency=max(1, args.retrieval_concurrency),
        fanout_rounds=1 if args.official_public_smoke else selected.fanout_rounds,
        identifier_fanout_only=bool(args.official_public_smoke),
        query_timeout_seconds=max(0.1, args.query_timeout_seconds),
    )
    return result.to_dict(include_plan=args.include_plan)


def render_summary(payload: dict) -> str:
    """Render a compact smoke/run summary for non-technical users."""
    summary = payload.get("retrieval_summary") or {}
    routing = summary.get("source_routing") or {}
    coverage = summary.get("coverage") or {}
    subject_profile = payload.get("subject_profile") or {}
    gaps = subject_profile.get("evidence_gaps") or []
    diagnostics = payload.get("source_diagnostics") or []

    lines = [
        f"# 华尔街驻铁岭办事处调查摘要 / Investigation Summary",
        "",
        f"- 主体 / Subject: {payload.get('company', '')}",
        f"- 执行状态 / State: {summary.get('execution_state', 'unknown')}",
        f"- 证据数 / Evidence: {payload.get('evidence_count', 0)}",
        f"- 实体数 / Entities: {payload.get('entity_count', 0)}",
        f"- 风险事件 / Risk events: {payload.get('risk_event_count', 0)}",
        f"- 可用数据源 / Available sources: {routing.get('available_count', 0)}/{routing.get('configured_count', 0)}",
        "",
        "## 数据源 / Sources",
    ]
    for item in diagnostics:
        lines.append(
            "- "
            f"{item.get('source_name', 'unknown')}: {item.get('status', 'unknown')}, "
            f"records={item.get('record_count', 0)}, ingested={item.get('ingested_count', 0)}"
        )

    lines.extend(
        [
            "",
            "## 覆盖 / Coverage",
            "- 已取证领域 / With evidence: "
            + ", ".join(coverage.get("domains_with_evidence") or ["none"]),
            "- 待补领域 / Needs more evidence: "
            + ", ".join(coverage.get("domains_without_evidence") or ["none"]),
            "",
            "## 下一步 / Next Actions",
        ]
    )
    next_actions = summary.get("next_actions") or []
    for action in next_actions[:5]:
        lines.append(f"- {action}")
    if gaps:
        lines.append("")
        lines.append("## 证据缺口 / Evidence Gaps")
        for gap in gaps[:5]:
            lines.append(f"- {gap}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = asyncio.run(run(args))
    if args.summary:
        print(render_summary(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
