#!/usr/bin/env python3
"""Run an offline retrieval-to-risk-event smoke pipeline."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.risk_discovery_pipeline import (  # noqa: E402
    RiskDiscoveryPipeline,
    offline_enforcement_fixture,
)


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an offline smoke test for retrieval evidence, graph risk events, and alert storage."
    )
    parser.add_argument("company", help="Company name to investigate.")
    parser.add_argument(
        "--store",
        default="",
        help="JSONL store path. Defaults to a temporary file.",
    )
    return parser


async def run_pipeline_async(company: str, store_path: str | Path | None = None) -> dict:
    if store_path:
        path = Path(store_path)
    else:
        path = Path(tempfile.gettempdir()) / "wallstreet-tieling-risk-smoke.jsonl"
        path.unlink(missing_ok=True)

    result = await RiskDiscoveryPipeline().run(
        company,
        records=offline_enforcement_fixture(company),
        store_path=path,
    )
    return result.to_dict()


def run_pipeline(company: str, store_path: str | Path | None = None) -> dict:
    return asyncio.run(run_pipeline_async(company, store_path))


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = run_pipeline(args.company, args.store or None)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
