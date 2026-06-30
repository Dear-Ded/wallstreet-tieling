#!/usr/bin/env python3
"""Scan and normalize release terminology."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.terminology_guard import (  # noqa: E402
    default_rules,
    findings_summary,
    iter_text_files,
    normalize_file,
    normalize_text,
    scan_paths,
)


def force_utf8_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan public-release wording and normalize non-standard terminology."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan. Defaults to the repository root.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Normalize supported text files in place. Source files only fix comment-like lines.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "warn", "error"),
        default="error",
        help="Exit non-zero when findings at or above this severity exist.",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="Print the public terminology table without raw legacy expressions.",
    )
    parser.add_argument(
        "--text",
        default="",
        help="Normalize one text snippet and print the result.",
    )
    return parser


def _should_fail(summary: dict[str, object], threshold: str) -> bool:
    if threshold == "none":
        return False
    by_severity = summary.get("by_severity", {})
    if not isinstance(by_severity, dict):
        return False
    errors = int(by_severity.get("error", 0))
    warnings = int(by_severity.get("warn", 0))
    return errors > 0 if threshold == "error" else (errors + warnings) > 0


def _print_text_summary(summary: dict[str, object]) -> None:
    print("Terminology Guard")
    print(f"  findings: {summary['total']}")
    print(f"  by_severity: {summary['by_severity']}")
    print(f"  by_category: {summary['by_category']}")
    for item in summary["findings"]:
        print(
            "  - "
            f"{item['path']}:{item['line']}:{item['column']} "
            f"{item['severity']} {item['rule_id']} -> {item['replacement']}"
        )


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if args.list_rules:
        rules = [rule.to_public_dict() for rule in default_rules()]
        print(json.dumps(rules, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.text:
        print(normalize_text(args.text))
        return 0

    paths = [Path(item) for item in args.paths]
    if args.fix:
        for path in iter_text_files([item.resolve() for item in paths], root=ROOT):
            normalize_file(path)

    findings = scan_paths(paths, root=ROOT)
    summary = findings_summary(findings)
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_summary(summary)
    return 1 if _should_fail(summary, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
