#!/usr/bin/env python3
"""Audit and prune stale NightPilot queue entries for local workspace hygiene."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ACTIVE_STATUSES = {"ready", "retry_wait"}
TERMINAL_STATUSES = {"verified", "failed", "blocked_auth", "blocked_worktree"}


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_task(task: dict[str, Any], root: Path, cutoff: datetime) -> dict[str, Any]:
    status = str(task.get("status", ""))
    next_run_at = parse_iso(task.get("nextRunAt"))
    worktree_raw = str(task.get("worktree", "") or "")
    worktree = Path(worktree_raw) if worktree_raw else None
    worktree_exists = bool(worktree and worktree.exists())
    is_primary = bool(worktree and worktree.resolve() == root.resolve()) if worktree_exists else False
    is_active = status in ACTIVE_STATUSES
    is_terminal = status in TERMINAL_STATUSES or status.startswith("blocked")
    is_stale = bool(next_run_at and next_run_at < cutoff)
    prune_reasons: list[str] = []
    if is_terminal and is_stale:
        if not worktree_raw:
            prune_reasons.append("empty_worktree")
        elif not worktree_exists:
            prune_reasons.append("missing_worktree")
        elif is_primary:
            prune_reasons.append("primary_worktree_reference")
    return {
        "id": task.get("id", ""),
        "status": status,
        "attempts": int(task.get("attempts", 0) or 0),
        "next_run_at": task.get("nextRunAt"),
        "worktree": worktree_raw,
        "worktree_exists": worktree_exists,
        "is_active": is_active,
        "is_terminal": is_terminal,
        "is_stale": is_stale,
        "prune_reasons": prune_reasons,
        "prune_candidate": bool(prune_reasons),
    }


def build_report(root: Path, stale_days: int) -> tuple[dict[str, Any], dict[str, Any]]:
    state_path = root / ".codex-autonomous" / "state.json"
    if not state_path.exists():
        return (
            {
                "type": "nightpilot_state_audit",
                "root": str(root),
                "state_exists": False,
                "state_path": str(state_path),
            },
            {},
        )

    state = load_state(state_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    queue = state.get("queue", [])
    tasks = [summarize_task(task, root, cutoff) for task in queue]
    candidates = [task for task in tasks if task["prune_candidate"]]

    report = {
        "type": "nightpilot_state_audit",
        "root": str(root),
        "state_exists": True,
        "state_path": str(state_path),
        "updated_at": state.get("updatedAt"),
        "stale_days": stale_days,
        "queue_size": len(tasks),
        "ready_count": sum(1 for task in tasks if task["status"] in ACTIVE_STATUSES),
        "terminal_count": sum(1 for task in tasks if task["is_terminal"]),
        "stale_terminal_candidate_count": len(candidates),
        "stale_terminal_candidates": candidates,
    }
    return report, state


def apply_prune(state: dict[str, Any], stale_ids: set[str]) -> int:
    before = len(state.get("queue", []))
    state["queue"] = [task for task in state.get("queue", []) if task.get("id") not in stale_ids]
    return before - len(state["queue"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--stale-days", type=int, default=2)
    parser.add_argument("--apply-prune-stale-terminal", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report, state = build_report(root, args.stale_days)
    if args.apply_prune_stale_terminal and report.get("state_exists"):
        stale_ids = {task["id"] for task in report["stale_terminal_candidates"]}
        removed = apply_prune(state, stale_ids)
        if removed:
            state_path = root / ".codex-autonomous" / "state.json"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["applied_prune"] = True
        report["removed_count"] = removed
    else:
        report["applied_prune"] = False
        report["removed_count"] = 0

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"queue={report.get('queue_size', 0)} ready={report.get('ready_count', 0)} "
            f"terminal={report.get('terminal_count', 0)} prune_candidates={report.get('stale_terminal_candidate_count', 0)}"
        )
        for candidate in report.get("stale_terminal_candidates", []):
            reasons = ",".join(candidate["prune_reasons"])
            print(f"- {candidate['id']}: {candidate['status']} reasons={reasons} worktree={candidate['worktree']}")
        if args.apply_prune_stale_terminal:
            print(f"removed={report['removed_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
