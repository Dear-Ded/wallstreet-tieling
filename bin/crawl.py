#!/usr/bin/env python3
"""Run a crawler preset and print standardized records (JSON).

Examples:
  python bin/crawl.py --preset xueqiu --code 600519 --discussion-pages 2 --entity 贵州茅台
  python bin/crawl.py --preset site_links --url https://www.example.com/ --max-depth 1
  python bin/crawl.py --preset xueqiu --code 600519 --checkpoint .crawl/xueqiu.json --resume
Proxies: set WST_PROXY_URLS="http://user:pass@host:port,..." (operator-supplied).
Authorized cookies: --cookie domain=name=value (repeatable), e.g. a session you own.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.crawl_presets import build_site_crawl, build_xueqiu_run  # noqa: E402
from core.crawl_runtime import ProxyPool, RequestQueue, SessionPool  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preset", required=True, choices=["xueqiu", "site_links"])
    p.add_argument("--code", action="append", default=[])
    p.add_argument("--url", action="append", default=[])
    p.add_argument("--entity", default="")
    p.add_argument("--discussion-pages", type=int, default=1)
    p.add_argument("--max-depth", type=int, default=2)
    p.add_argument("--max-requests", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--checkpoint", default="")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--ignore-robots", action="store_true", help="only for sources you are authorized to crawl")
    p.add_argument("--cookie", action="append", default=[], help="domain=name=value (operator-owned session)")
    args = p.parse_args(argv)

    sessions = SessionPool(proxy_pool=ProxyPool.from_env())
    for spec in args.cookie:
        domain, name, value = spec.split("=", 2)
        sessions.import_cookies(domain, {name: value})
    common = {"session_pool": sessions, "checkpoint_path": args.checkpoint or None}
    if args.resume and args.checkpoint and Path(args.checkpoint).exists():
        common["queue"] = RequestQueue.load(args.checkpoint)
    if args.preset == "xueqiu":
        if not args.code and "queue" not in common:
            p.error("--code is required")
        run = build_xueqiu_run(args.code, entity=args.entity, discussion_pages=args.discussion_pages, **common)
    else:
        if not args.url and "queue" not in common:
            p.error("--url is required")
        run = build_site_crawl(args.url, entity=args.entity, max_depth=args.max_depth,
                               obey_robots=not args.ignore_robots, **common)
    summary = run.run(max_requests=args.max_requests, concurrency=args.concurrency)
    print(json.dumps({"summary": summary, "standardized_records": run.standardized_records()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
