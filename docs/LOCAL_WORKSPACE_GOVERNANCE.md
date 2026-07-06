# Local Workspace Governance

This document governs the local development tree after the public GitHub release
surface has been cleaned.

## Why This Exists

The repository now has three different classes of local state:

- shipping source and public docs that can be mirrored to GitHub;
- ignored local runtime state needed for development and autonomous runs;
- auxiliary worktrees and beautification isolation lanes that must not drift
  into the release package by accident.

The goal is to keep those boundaries explicit.

## Root-Level Boundaries

Tracked release-facing paths:

- `adapters/`, `api/`, `bin/`, `core/`, `deploy/`, `docs/`, `release/`,
  `skills/`, `sub-skills/`, `tools/`
- release-facing root docs such as `README.md`, `PROJECT_TASKBOARD.md`,
  `CHANGELOG.md`, `SECURITY.md`, and `CONTRIBUTING.md`

Ignored local-only paths:

- `.codex-autonomous/`
- `.workbuddy/`
- `.reasonix/`
- `.colab/`
- `deliverables/`
- `audit_reports/`
- `output/`, `outputs/`, `.tmp/`, `.cache/`, `.pytest_cache/`
- local secrets, browser profiles, cookies, sqlite/db artifacts, and ad hoc
  logs

Do not convert ignored runtime state into tracked release documentation.

## Worktree Policy

Use `npm run worktrees:audit:json` as the source of truth for auxiliary
worktree review.

Current worktree classes:

- `primary-worktree`: the active shipping branch; keep it clean.
- `migration-candidate-runtime-contract`: contains possible runtime/report/API
  contract changes that must be diffed and merged intentionally.
- `migration-candidate-release-hygiene`: contains possible package/public-doc
  hygiene changes that must be reviewed before merge.
- `migration-candidate-verifier`: contains report verifier or acceptance-gate
  changes that must be reviewed before merge.
- `beautification-artifact-review`: isolation lanes for report/UI ideas only;
  do not merge blindly into release runtime.
- `needs-manual-review`: anything ambiguous or controller-owned.

Do not delete dirty worktrees just because they are old. Review them, classify
them, then either merge useful deltas or remove them after confirming they no
longer carry needed work.

## NightPilot Policy

NightPilot is a local operating layer, not a public product surface.

Use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 tools/nightpilot-state-audit.py --json
```

to inspect queue health. Use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 tools/nightpilot-state-audit.py --apply-prune-stale-terminal --json
```

only to remove stale terminal queue entries that are both old and clearly
invalid for continued scheduling:

- empty worktree reference;
- missing worktree path;
- terminal task still pointing at the primary worktree.

Do not prune `ready` tasks through this tool.

## Hygiene Commands

Repository-local hygiene:

```powershell
npm run hygiene:audit:json
powershell -NoProfile -ExecutionPolicy Bypass -File tools/local-hygiene-clean.ps1 -DryRun
```

NightPilot retention cleanup:

```powershell
<nightpilot-python> <nightpilot-controller> cleanup --dry-run
```

Worktree review:

```powershell
npm run worktrees:audit:json
```

## Release Rule

Before any future public push or package claim:

1. keep the primary worktree clean;
2. verify ignored runtime state stays ignored;
3. rerun release hygiene and package privacy gates;
4. confirm local auxiliary work has not leaked into release-facing files.
