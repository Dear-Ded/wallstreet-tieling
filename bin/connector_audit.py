#!/usr/bin/env python3
"""Print connector capability audit summary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.connector_registry import ConnectorRegistry  # noqa: E402
from core.intelligence_retrieval import ConnectorShape, RetrievalDomain  # noqa: E402


def force_utf8_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit registered datasource connectors.")
    parser.add_argument("--domain", default="", help="Filter by retrieval domain.")
    parser.add_argument("--shape", default="", help="Filter by connector shape.")
    parser.add_argument(
        "--production-ready",
        action="store_true",
        help="Return only production-ready connectors.",
    )
    return parser


def run(args: argparse.Namespace) -> dict:
    registry = ConnectorRegistry()
    domain = RetrievalDomain(args.domain) if args.domain else None
    shape = ConnectorShape(args.shape) if args.shape else None
    connectors = registry.list(
        domain=domain,
        shape=shape,
        production_ready=True if args.production_ready else None,
    )
    summary = registry.audit_summary()
    summary["filtered"] = [connector.to_dict() for connector in connectors]
    summary["filtered_count"] = len(connectors)
    return summary


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    print(json.dumps(run(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
