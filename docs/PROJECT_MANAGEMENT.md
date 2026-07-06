# Project Management System

This repository uses a release-gated project management model. The goal is to
keep high-speed agent development from turning into an unreviewable pile of
worktrees, runtime outputs, stale handoffs, and undocumented behavior.

## Current Product Track

Primary track:

- Desktop-agent distribution for Codex, Claude Code, Hermes-style hosts,
  Doubao Office Task Mode, OpenClaude/open-source agents, WorkBuddy, and
  universal CLI/API/MCP hosts.

Secondary tracks:

- Premium HTML and report experience.
- Marketplace/operator screenshots and submission assets.
- Source-strengthening and live-source admission.

Future-only tracks:

- Mini-program, mobile app, standalone desktop app, and hosted SaaS.

## Source Of Truth

Use these files in this order:

1. `PROJECT_TASKBOARD.md`
2. `docs/REQUIREMENT_INTAKE.md`
3. `docs/PROJECT_MAP.md`
4. `docs/RELEASE_PORTAL.md`
5. `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`
6. `docs/API_CONTRACTS.md`
7. `release/variants.yaml`
8. `core/development_requirements.py`

## Work Lanes

| Lane | Purpose | Preferred files |
| --- | --- | --- |
| Runtime | Investigation packet, graph, report, adapters | `core/`, `adapters/`, `bin/`, `api/`, `lib/` |
| Agent delivery | Host adapters, MCP, CLI/API contracts, release gates | `core/agent_tool_adapters.py`, `core/release_contract.py`, `release/`, `deploy/` |
| Report output | DOCX, HTML, Markdown, JSON, verifier | `core/report_docx.py`, `core/investigation.py`, `bin/verify_report_bundle.py` |
| Source admission | Source registry, public/authorized adapters, resilience | `core/connector_registry.py`, `adapters/`, `docs/SEARCH_INTEGRATION_LEDGER.md` |
| Public release | README, package list, hygiene, package dry-run | `README.md`, `package.json`, `docs/`, `tools/` |
| Local hygiene | Worktrees, caches, runtime state, ignored outputs | local-only; do not commit generated files |

## Requirement Intake

The maintainer may describe goals with abstract product language rather than
technical names. Treat that as normal input. Use `docs/REQUIREMENT_INTAKE.md`
to translate requests into scoped lanes, files, verification, and taskboard
updates.

Do not require the maintainer to provide schemas, class names, endpoint names,
branch names, or test commands. Those are agent responsibilities.

## Branch And Worktree Rules

- Main development branch: `codex/security-ci-hardening`.
- Public release remote: `public`.
- Public release branches must not inherit private development history unless
  the public remote already shares that history. Use clean snapshot commits when
  histories diverge.
- Remove clean worktrees after their work has been merged, released, or
  superseded.
- Do not remove dirty worktrees until their changes have been reviewed,
  migrated, or explicitly discarded.

## Definition Of Done

- Runtime behavior exists, not just documentation.
- Tests or smoke checks cover the behavior.
- Report/API/CLI/MCP/agent handoff surfaces agree where applicable.
- Public docs are updated if operator behavior changed.
- Release-significant changes pass privacy scan and package dry-run.
- No runtime outputs, local paths, cookies, browser profiles, private reports,
  or private handoff notes are staged.

## Release Gate

```bash
npm run acceptance
npm run api:smoke
npm run codex:mcp-smoke
npm run agent:host-smoke
npm run release:preflight
npm run delivery:audit
npm run objective:audit
npm run release:privacy-scan
npm pack --dry-run --json
```

## Local Hygiene Cadence

After each release or long unattended session:

- Confirm `git status --short --branch` is clean or intentionally dirty.
- Remove clean stale worktrees with `git worktree remove`.
- Keep dirty worktrees until reviewed.
- Delete reusable caches: `.tmp/`, `.pytest_cache/`, `.coverage`,
  `__pycache__/`, pytest scratch directories, `output/`, and `outputs/`.
- Keep local state out of git: `.codex-autonomous/`, `.workbuddy/`, `.colab/`,
  local source credentials, private reports, and generated artifacts.
- Run `git worktree prune` after removing worktrees.
- Run `powershell -NoProfile -ExecutionPolicy Bypass -File tools/local-hygiene-audit.ps1`
  to inspect managed local caches, logs, generated outputs, and auxiliary
  worktrees.

## Local Directory Policy

| Path class | Policy |
| --- | --- |
| Source tree (`core/`, `adapters/`, `api/`, `bin/`, `lib/`) | Commit only reviewed runtime changes with tests. |
| Public docs (`README.md`, `docs/`, `PROJECT_TASKBOARD.md`) | Keep public-safe, current, and linked from README where useful. |
| Release metadata (`package.json`, `release/`, `deploy/`) | Treat as release-critical; run package dry-run after edits. |
| Runtime state (`.codex-autonomous/`, `.workbuddy/`, `.colab/`) | Local-only. Do not commit. Keep only while useful for coordination. |
| Generated outputs (`output/`, `outputs/`, `.tmp/`, pytest scratch dirs) | Delete after verification unless needed for an active bug. |
| Local secrets/config (`config/datasources_qyyjt.yaml`, cookies, profiles) | Local-only. Never package or commit. |
| Historical scratch reports (`audit_reports/`, ignored docs, backups) | Archive outside the active repository or delete after review. |
| Auxiliary worktrees | Remove if clean and superseded; preserve if dirty until reviewed. |

## Cache And Log Policy

Managed local-only paths:

- `.tmp/`: acceptance runs, npm package privacy workspaces, short-lived smoke
  artifacts. Delete after release gates pass.
- `.pytest_cache/`, `.coverage`, `__pycache__/`: test/runtime caches. Delete
  after test sessions when doing release cleanup.
- `output/`, `outputs/`: generated reports and local API outputs. Keep only
  when tied to an active bug or screenshot task.
- `tmp-events.jsonl`: local event stream scratch file. Delete after debugging.
- `.codex-autonomous/`: NightPilot state. Keep while unattended development is
  active; do not publish or package.
- `.workbuddy/`, `.colab/`: local collaborator state. Keep local only.
- `node_modules/`, `package-lock.json`: local dependency/runtime state for this
  package. Do not include in public package contents unless intentionally
  changing dependency policy.
- `config/datasources_qyyjt.yaml`: local authorized-source configuration. Never
  commit or package.
- `audit_reports/`, ignored top-level notes, backup HTML files, and helper
  scripts: historical local material. Archive outside the active repo or delete
  after review.

Retention default:

- Release caches: delete immediately after release verification.
- Test caches: delete after focused/full test run unless debugging a failure.
- Local investigation outputs: keep only with an owner and active reason.
- Dirty auxiliary worktrees: review before deletion; never bulk-delete blindly.

Health command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/local-hygiene-audit.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools/local-hygiene-audit.ps1 -Json
```

## Current Post-Release State

Public snapshot published:

- Remote: `public`
- Branches: `master`, `main`
- Commit: `19470c3 chore: publish desktop agent alpha snapshot`

Development branch synchronized:

- Remote: `origin`
- Branch: `codex/security-ci-hardening`
- Commit: `056f15d docs: polish public project homepage`

Remaining local hygiene queue:

- Review dirty auxiliary worktrees before removal.
- Decide whether ignored historical `audit_reports/`, top-level scratch
  scripts, and local backup files should be archived outside the repository.
- Keep `deliverables/` until the premium HTML/report track is explicitly
  migrated or archived.
