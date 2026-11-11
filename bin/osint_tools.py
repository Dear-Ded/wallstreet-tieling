#!/usr/bin/env python3
"""Optional SOCMINT tools: detect what is installed, run one, or normalize saved output.

Examples:
  python bin/osint_tools.py --detect
  python bin/osint_tools.py --run maigret --query some_user --top-sites 200
  python bin/osint_tools.py --run sherlock --query some_user --site GitHub --site GitLab
  python bin/osint_tools.py --run holehe --query someone@example.com
  python bin/osint_tools.py --run phoneinfoga --query +12025550123 --phoneinfoga-url http://127.0.0.1:5000/api
  python bin/osint_tools.py --recursive --query some_user --max-depth 2
  python bin/osint_tools.py --parse maigret --file report_some_user_simple.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.osint_tools import (  # noqa: E402
    OptionalToolRunner,
    RecursiveIdentitySearch,
    ToolRun,
    detect_optional_tools,
    parse_holehe_rows,
    parse_maigret_report,
    parse_sherlock_csv,
    tool_run_to_standardized_records,
    utc_now,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--detect", action="store_true", help="report installed optional tools (runtime detection)")
    mode.add_argument("--run", choices=["maigret", "sherlock", "holehe", "phoneinfoga"])
    mode.add_argument("--recursive", action="store_true", help="bounded recursive username/email/phone search")
    mode.add_argument("--parse", choices=["maigret", "sherlock", "holehe"], help="normalize a saved tool report")
    p.add_argument("--query", default="")
    p.add_argument("--kind", default="username", choices=["username", "email", "phone"])
    p.add_argument("--file", default="")
    p.add_argument("--subject", default="")
    p.add_argument("--top-sites", type=int, default=500)
    p.add_argument("--all-sites", action="store_true")
    p.add_argument("--site", action="append", default=[])
    p.add_argument("--timeout", type=float, default=None)
    p.add_argument("--max-depth", type=int, default=2)
    p.add_argument("--max-identifiers", type=int, default=20)
    p.add_argument("--proxy", default=None, help="proxy URL passed to tools that support it (or WST_OSINT_PROXY)")
    p.add_argument("--phoneinfoga-url", default=None)
    args = p.parse_args(argv)

    if args.detect:
        print(json.dumps(detect_optional_tools(), ensure_ascii=False, indent=2))
        return 0

    if args.parse:
        text = Path(args.file).read_text(encoding="utf-8")
        parser = {"maigret": parse_maigret_report, "sherlock": parse_sherlock_csv,
                  "holehe": lambda t: parse_holehe_rows(t, email=args.query)}[args.parse]
        run = ToolRun(tool=args.parse, query=args.query or Path(args.file).stem, query_kind=args.kind,
                      command=[f"parse {args.file}"], observations=parser(text), finished_at=utc_now())
        print(json.dumps(tool_run_to_standardized_records(run, subject=args.subject), ensure_ascii=False, indent=2))
        return 0

    if not args.query:
        p.error("--query is required for --run/--recursive")
    runner = OptionalToolRunner(proxy=args.proxy, phoneinfoga_url=args.phoneinfoga_url)
    if args.recursive:
        options = {"maigret": {"top_sites": None if args.all_sites else args.top_sites, "all_sites": args.all_sites}}
        result = RecursiveIdentitySearch(runner, max_depth=args.max_depth, max_identifiers=args.max_identifiers,
                                         tool_options=options).search(args.kind, args.query)
        print(json.dumps({"visited": result.visited, "truncated": result.truncated, "edges": result.edges,
                          "standardized_records": result.standardized_records(subject=args.subject)},
                         ensure_ascii=False, indent=2))
        return 0
    if args.run == "maigret":
        run = runner.run_maigret(args.query, top_sites=None if args.all_sites else args.top_sites,
                                 all_sites=args.all_sites, sites=args.site or None, timeout=args.timeout)
    elif args.run == "sherlock":
        run = runner.run_sherlock(args.query, sites=args.site or None, timeout=args.timeout)
    elif args.run == "holehe":
        run = runner.run_holehe(args.query, timeout=args.timeout)
    else:
        run = runner.run_phoneinfoga(args.query, timeout=args.timeout)
    print(json.dumps({"run": run.to_dict(), "standardized_records": tool_run_to_standardized_records(run, subject=args.subject)},
                     ensure_ascii=False, indent=2))
    return 0 if run.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
