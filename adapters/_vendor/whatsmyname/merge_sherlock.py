#!/usr/bin/env python3
"""Merge sherlock-project/sherlock site list into wmn-data.json (one-off, auditable).

Sherlock data schema (sherlock_project/resources/data.json, MIT):
    "<name>": {"url": "https://.../{}/", "urlMain": "...", "errorType": "message|status_code|response_url",
               "errorMsg": [...], "errorUrl": "...", "regexCheck": "...", "username_claimed": "..."}

Conversion rules (documented, kept minimal):
- dedup: normalized name (alnum+lower) against existing wmn entries AND
  against CHINESE_SITES (runtime-appended; Chinese versions keep priority).
- uri_check/uri_pretty: url with "{}" -> "{account}".
- detect: sherlock errorType carried through as site["detect"], interpreted by
  WhatsMyNameLookup.check_site:
    message      -> errorMsg list in body => not found; absent => found
    status_code  -> 200 => found; >=400 => not found
    response_url -> final URL == errorUrl => not found; otherwise => found
- regexCheck carried through as site["regex_check"]; username mismatch => skip.
- attribution: source + license per entry.

Usage:
    python merge_sherlock.py --sherlock /tmp/sherlock-data.json [--dry-run]
    (downloads from GitHub master when --sherlock is omitted)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

SHERLOCK_URL = (
    "https://raw.githubusercontent.com/sherlock-project/sherlock/master/"
    "sherlock_project/resources/data.json"
)
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wmn-data.json")


def norm(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalnum())


def load_sherlock(path: str | None) -> dict:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        req = urllib.request.Request(
            SHERLOCK_URL, headers={"User-Agent": "WallstreetTieling/0.6.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, dict) and "url" in v}


def convert(name: str, s: dict) -> dict:
    url = s["url"].replace("{}", "{account}")
    err_type = s.get("errorType", "message")
    entry: dict = {
        "name": name,
        "uri_check": url,
        "uri_pretty": url,
        "e_code": None,
        "e_string": "",
        "m_code": None,
        "m_string": "",
        "cat": "",
        "detect": err_type,
        "source": "sherlock-project/sherlock",
        "license": "MIT",
    }
    if err_type == "message":
        msgs = [m for m in (s.get("errorMsg") or []) if m]
        entry["m_strings"] = msgs
        entry["m_string"] = msgs[0] if msgs else ""
    if err_type == "response_url" and s.get("errorUrl"):
        entry["error_url"] = s["errorUrl"]
    if s.get("regexCheck"):
        entry["regex_check"] = s["regexCheck"]
    note = f"Sherlock dataset merge (2026-10-21, MIT): errorType={err_type}"
    if s.get("urlMain"):
        note += f"; urlMain={s['urlMain']}"
    if s.get("isNSFW"):
        note += "; NSFW"
    entry["note"] = note
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sherlock", default=None, help="local sherlock data.json (else download)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sherlock = load_sherlock(args.sherlock)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    sites = data.get("sites", [])
    wmn_before = len(sites)

    existing = {norm(s.get("name", "")) for s in sites}
    # CHINESE_SITES are runtime-appended with priority; keep them winning.
    chinese = {"douban", "zhihu", "bilibili_search", "douyin_search",
               "xiaohongshu_search", "kuaishou_search"}
    chinese_norm = {norm(c) for c in chinese}

    added, skipped_dup, skipped_chinese, skipped_noplug = [], [], [], []
    for name in sorted(sherlock, key=str.lower):
        n = norm(name)
        if "{}" not in sherlock[name]["url"]:
            # no username placeholder in probe URL: cannot enumerate -> skip
            skipped_noplug.append(name)
            continue
        if n in existing:
            skipped_dup.append(name)
            continue
        if n in chinese_norm:
            skipped_chinese.append(name)
            continue
        entry = convert(name, sherlock[name])
        sites.append(entry)
        existing.add(n)
        added.append(name)

    print(f"sherlock entries: {len(sherlock)}")
    print(f"wmn before: {wmn_before}")
    print(f"added: {len(added)}, skipped dup-of-wmn: {len(skipped_dup)}, "
          f"skipped chinese-priority: {len(skipped_chinese)}, "
          f"skipped no-placeholder: {len(skipped_noplug)}")
    if skipped_dup:
        print("  dup sample:", skipped_dup[:10])
    if skipped_chinese:
        print("  chinese-priority:", skipped_chinese)
    if skipped_noplug:
        print("  no-placeholder:", skipped_noplug)

    if args.dry_run:
        print("dry-run: not writing")
        return 0

    data["sites"] = sites
    meta = data.setdefault("meta", {})
    meta["sherlock_merge"] = {
        "date": "2026-10-21",
        "sherlock_repo": "sherlock-project/sherlock",
        "sherlock_license": "MIT",
        "added": len(added),
        "skipped_dup": len(skipped_dup),
        "skipped_chinese_priority": skipped_chinese,
    }
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {DATA_PATH}: {len(sites)} sites total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
