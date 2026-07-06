# Worktree Review Queue

This queue keeps post-release cleanup from becoming destructive. Dirty
auxiliary worktrees may contain useful work, obsolete experiments, screenshots,
or generated state. Do not bulk-delete them. Review, migrate, archive, or
discard them deliberately.

Current primary branch: `codex/security-ci-hardening`.

Last reviewed from main workspace: `2026-07-06`.

Latest high-value migration pass: `2026-07-06`.

Health commands:

```powershell
npm run worktrees:audit
npm run worktrees:audit:json
npm run hygiene:audit
```

## Review Rules

- `remove-candidate-clean`: safe to remove after confirming no active process is
  using it.
- `migration-candidate-runtime-contract`: compare against mainline before
  removal; many changes may already be present in the released delivery
  contract.
- `migration-candidate-release-hygiene`: compare release docs/package tests
  against current public snapshot before removal.
- `migration-candidate-verifier`: inspect verifier and negative-test changes
  before removal.
- `beautification-artifact-review`: keep until screenshot/material and premium
  HTML decisions are complete; archive outside the active repo if not needed.
- `needs-manual-review`: inspect diff stats and file intent before deciding.
- Never remove `.codex-autonomous/`, `.workbuddy/`, `.colab/`, local authorized
  config, or dirty auxiliary worktrees as part of routine hygiene cleanup.

## Current Queue

| Worktree | Classification | Dirty | Files / reason | Next action |
| --- | --- | ---: | --- | --- |
| `<user-codex-worktrees>/wallstreet-tieling-unattended` | needs-manual-review | 2 | `bin/cli.js`, `package-lock.json` | Compare CLI diff; ignore/remove local lockfile if redundant. |
| `deliverables/.../expert-thirteen-system` | beautification-artifact-review | 6 | persona/runtime/report tests plus `index.html` | Preserve until premium HTML/report lane decides whether persona copy or tests matter. |
| `deliverables/.../immersive-report-shell` | beautification-artifact-review | 1 | `index.html` | Likely artifact; compare against current isolated portal before archive. |
| `deliverables/.../implement-first-slice` | beautification-artifact-review | 3 | report/API/test changes | Compare if any report-contract idea survived into main; otherwise archive. |
| `deliverables/.../long-reading-renderer` | beautification-artifact-review | 9 | API, report, release docs/tests | High-value candidate for premium report lane; inspect before removal. |
| `deliverables/.../plan-autonomous-lane` | beautification-artifact-review | 5 | taskboard/requirements/search-ledger | Likely planning artifact; preserve until taskboard reconciliation. |
| `beautification-portal-v111-cinematic-report-pass` | beautification-artifact-review | 3 | screenshots and `.playwright-mcp/` | Archive screenshots into release assets if useful, then remove. |
| `beautification-portal-v112-immersion-qa-pass` | beautification-artifact-review | 1 | `.playwright-mcp/` | Runtime artifact; remove after screenshot/material audit. |
| `contract-preservation-sweep` | migration-candidate-runtime-contract | 16 | CLI/API/MCP/release/verifier/test contract files | Compare against current delivery/objective audit; migrate only missing assertions. |
| `implement-first-slice` | migration-candidate-verifier | 4 | verifier, API contracts, tests | Compare verifier negative coverage before removal. |
| `p0-agent-delivery-contract-audit` | migration-candidate-runtime-contract | 11 | agent adapter/API/docs/smoke changes | Compare preserved packet fields against current mainline. |
| `p0-codex-skill-functional-hardening` | migration-candidate-runtime-contract | 6 | MCP, skill, encoding tests | Check if skill/MCP hardening is already in mainline. |
| `plan-autonomous-lane` | needs-manual-review | 10 | taskboard/API/requirements/workbuddy tests | Compare planning/requirements changes; likely superseded by current board. |
| `release-hygiene-packaging-sweep` | migration-candidate-release-hygiene | 5 | `.gitignore`, README, ledger, package, release tests | Compare against current public hygiene commits before removal. |
| `review-release-hygiene` | migration-candidate-release-hygiene | 1 | release hygiene test | Inspect if the test covers a gap not in current privacy scan. |
| `runtime-acceptance-closure-p0` | migration-candidate-runtime-contract | 12 | acceptance evidence, release docs, smokes | Compare against latest acceptance evidence and release portal. |
| `runtime-agent-release-closure-p0` | migration-candidate-runtime-contract | 13 | API/CLI/agent adapters/release docs/tools | Compare against delivery audit and host smoke coverage. |
| `runtime-contract-drift-audit-p0` | migration-candidate-runtime-contract | 16 | broad contract and smoke files | High-value diff; inspect before removal. |
| `runtime-release-preflight-final-p0` | migration-candidate-release-hygiene | 6 | release contract/docs/package/tests | Compare preflight gates and remove if superseded. |
| `scout-context` | needs-manual-review | 1 | `bin/cli.js` | Likely obsolete scout edit; compare CLI diff. |
| `verifier-negative-coverage` | migration-candidate-verifier | 3 | verifier/API contract/test | Inspect before removal; possible useful negative test. |
| `wallstreet-tieling-release-verify` | needs-manual-review | 5 | delivery doctor/packet/release contract/test/smoke | Inspect for still-useful release doctor ideas before removal. |

## Migration Decisions

### 2026-07-06 High-Value Pass

Reviewed:

- `runtime-contract-drift-audit-p0`
- `verifier-negative-coverage`
- `review-release-hygiene`
- `wallstreet-tieling-release-verify`

Decisions:

- `verifier-negative-coverage`: mostly superseded by mainline. Current
  `bin/verify_report_bundle.py` already rejects stale `agent_summary`
  delivery decision, decision digest, report visibility, and work-queue fields,
  and current tests cover those failures. Keep worktree until final cleanup,
  but do not migrate wholesale.
- `review-release-hygiene`: one low-risk idea was migrated into mainline:
  `test_npm_package_file_allowlist_excludes_runtime_and_private_artifacts`.
  This protects `package.json.files` from adding runtime/private prefixes even
  before `npm pack` is run.
- `wallstreet-tieling-release-verify`: do not migrate wholesale. The
  `agent_delivery_packet` / `agent_delivery_doctor` idea is useful, but the
  candidate depends on surfaces not currently present in mainline
  (`source_preflight`, `report_delivery_targets`, and extra final-smoke
  scripts). Treat it as a design input for a future narrow branch, not as a
  copy-paste patch.
- `runtime-contract-drift-audit-p0`: keep as a high-value compare source. It
  touches broad CLI/API/MCP/release/verifier contracts; many concepts appear
  already represented by current `delivery_audit`, `objective_audit`,
  `agent_tool_adapters`, and report bundle verifier. It needs file-by-file
  comparison before deletion.

Immediate result:

- Mainline gained a package file allowlist regression test.
- No dirty auxiliary worktree was deleted.
- No isolated beautification artifact was promoted directly into production.

## Beautification Isolation Review

The beautification lane has a separate review and worker instruction file:

- `docs/BEAUTIFICATION_ISOLATION_REVIEW.md`

Summary:

- `deliverables/beautification-helper/portal-report.html` is a useful
  report-serving prototype, not just decoration.
- Do not merge it directly into production `index.html`.
- Migrate only the packet normalization, data-slot contract, verifier gates,
  V120-V122 acceptance checklist, and selected final screenshots.
- Keep browser profiles, old model/asset experiments, early screenshots, and
  scattered V-notes out of public package and production code.
- Future beautification work should freeze the current prototype and focus on a
  minimal production integration path.

## Closure Path

1. Review the three high-value buckets first: runtime contract, verifier, and
   release hygiene.
2. For each worktree, run `git -C <path> diff --stat` and inspect only files
   that touch current release contracts, verifiers, or smoke tests.
3. If useful, migrate into a new narrow branch from
   `codex/security-ci-hardening`, add focused tests, and commit.
4. If obsolete, record the decision here, remove the worktree, and run
   `git worktree prune`.
5. Leave beautification artifacts alone until screenshot and marketplace asset
   selection is complete.
