#!/usr/bin/env python3
"""Audit a local public/authorized subject index before enabling it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.multi_datasource import LocalIndexDataSource  # noqa: E402


def force_utf8_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a local subject index file.")
    parser.add_argument("index_path", help="Path to a JSON, JSONL, NDJSON, or CSV local index.")
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit non-zero when the index needs review.",
    )
    return parser


def run(args: argparse.Namespace) -> dict:
    return LocalIndexDataSource.audit_index_file(args.index_path)


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = run(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_on_review and not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
