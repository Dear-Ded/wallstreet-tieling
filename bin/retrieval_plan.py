#!/usr/bin/env python3
"""Emit an investigative retrieval plan as JSON."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_planner_class():
    module_path = ROOT / "core" / "intelligence_retrieval.py"
    spec = importlib.util.spec_from_file_location("wst_intelligence_retrieval", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load retrieval planner from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.InvestigativeRetrievalPlanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a broad evidence-first retrieval plan from a company name."
    )
    parser.add_argument("company", help="Company name to investigate.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit returned tasks. 0 means return all tasks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    planner_class = load_planner_class()
    plan = planner_class().build_company_plan(args.company)
    payload = plan.to_dict()
    if args.limit > 0:
        payload["tasks"] = payload["tasks"][: args.limit]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
