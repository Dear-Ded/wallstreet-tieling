#!/usr/bin/env python3
"""Print adapter readiness audit table as JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapter_audit import AdapterAuditor  # noqa: E402


def force_utf8_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit adapter implementation readiness.")
    parser.add_argument(
        "--needs-work",
        action="store_true",
        help="Return only adapters that still have blockers.",
    )
    return parser


def run(args: argparse.Namespace) -> dict:
    payload = AdapterAuditor(repo_root=ROOT).audit()
    if args.needs_work:
        payload["rows"] = [row for row in payload["rows"] if row["blockers"]]
        payload["filtered_count"] = len(payload["rows"])
    else:
        payload["filtered_count"] = payload["total"]
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    payload["rows"] = sorted(
        payload["rows"],
        key=lambda row: (
            priority_order.get(row.get("priority", "P3"), 3),
            -int(row.get("readiness_score", 0)),
            row.get("name", ""),
        ),
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    print(json.dumps(run(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
