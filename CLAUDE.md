# CLAUDE.md

You are working on **wallstreet-tieling / 华尔街驻铁岭办事处**.

## Product Positioning

This is not just a chatbot, search wrapper, or report generator. Treat it as an **Enterprise Intelligence & Risk Discovery System** with a first-class 13-role anthropomorphic expert-team surface:

1. Route work through named roles and task division.
2. Build evidence from broad public or user-authorized retrieval.
3. Map entities and relations.
4. Derive risk events.
5. Produce monitorable hypotheses and evidence gaps.

Continuous monitoring is a later-version target, not the current release focus.

The public repository is the product release portal. The current release is desktop-agent first, not a polished HTML product. The shared core must support these alpha distribution variants:

- Universal version
- Codex plugin/skill version
- Claude Code / Claude Project version
- Hermes desktop/coding agent version
- Doubao Office Task Mode version
- OpenClaude / open-source agent version
- WorkBuddy expert-team version

The source of truth for variant readiness is `release/variants.yaml`.
The source of truth for public release status is `PROJECT_TASKBOARD.md` and
`release/variants.yaml`.

## Core Entry Points

- Unified engine: `core/engine.py`
- Enterprise cognition profile: `core/enterprise_cognition.py`
- Retrieval planning: `core/intelligence_retrieval.py`
- Risk event store: `core/risk_event_store.py`
- Financial intelligence: `core/financial_analyzer_v2.py`
- Industry intelligence: `core/industry_intelligence.py`
- Product intelligence: `core/product_intelligence.py`
- WorkBuddy adapter: `adapters/workbuddy.py`
- Codex plugin: `.codex-plugin/plugin.json`
- Codex skill: `skills/wallstreet-tieling/SKILL.md`
- Runtime datasource catalog: `npx wallstreet-tieling --connectors` or `GET /api/connectors`
- Runtime release contract: `npx wallstreet-tieling --release` or `GET /api/release`
- Runtime requirements board: `npx wallstreet-tieling --requirements` or `GET /api/requirements`
- Project taskboard: `PROJECT_TASKBOARD.md`
- Project map: `docs/PROJECT_MAP.md`
- Search integration ledger: `docs/SEARCH_INTEGRATION_LEDGER.md`

## Claude Code Handoff

Claude Code should treat this repository as an executable product, not only as
a prompt pack.

Start here:

1. Read `README.md`, `AGENTS.md`, `PROJECT_TASKBOARD.md`,
   `docs/PROJECT_MAP.md`, `docs/SEARCH_INTEGRATION_LEDGER.md`, `CLAUDE.md`,
   `SKILL.md`, and `release/variants.yaml`.
2. Run `npx wallstreet-tieling --release` to see the current release contract.
3. Run `npx wallstreet-tieling --connectors` to see datasource readiness.
4. Run `npx wallstreet-tieling --requirements` to see the executable P0/P1/P2/Future board.
5. Run `git status --short` before staging and stage only intentional files.
6. Use `npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only` for a local smoke test.
7. Use `npx wallstreet-tieling --mcp` when a host supports MCP tools.

Claude Project knowledge pack:

- `README.md`
- `AGENTS.md`
- `PROJECT_TASKBOARD.md`
- `docs/PROJECT_MAP.md`
- `docs/SEARCH_INTEGRATION_LEDGER.md`
- `SKILL.md`
- `CLAUDE.md`
- `docs/CLAUDE_CODE_ADAPTER.md`
- `docs/API_CONTRACTS.md`
- `docs/DATASOURCE_ADMISSION.md`
- `references/data-sources.md`

Claude Code acceptance checklist:

- The repo loads without requiring secrets.
- The offline investigation smoke path returns a report.
- `/api/connectors` or `--connectors` exposes zero-config and admission-gated sources.
- `/api/release` or `--release` exposes all desktop-agent variants and their gates.
- `/api/requirements` or `--requirements` exposes P0/P1/P2/Future scope,
  including QYYJT as current-version work and monitoring as Future work.
- No tokens, cookies, browser profiles, local collaboration databases, or generated secrets are staged.

## Development Rules

- Preserve unrelated dirty worktree changes.
- Review `git status --short` before staging or committing; do not stage the
  whole tree.
- Stage and commit only files intentionally touched for the current task.
- Keep `.tmp/`, `outputs/`, `tmp-events.jsonl`, browser state, cookies,
  tokens, local credentials, and sibling-project files out of release commits.
- Do not commit tokens, cookies, browser profiles, local SQLite collaboration DBs, or generated secrets.
- Use public, licensed, or user-authorized sources only.
- Treat social-web and associative clues as leads until corroborated.
- Do not fabricate facts. Output evidence gaps when data is missing.

## Validation

Prefer the bundled Windows Python runtime when available:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest tests\unit\test_enterprise_cognition.py tests\unit\test_release_variants.py -q
```

For shared core changes, also run:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest tests\unit\test_engine.py tests\unit\test_intelligence_retrieval.py tests\unit\test_risk_event_store.py -q
```

For Claude Code packaging changes, run:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest tests\unit\test_release_variants.py tests\unit\test_encoding_integrity.py tests\unit\test_release_hygiene.py -q
node --check lib\mcp-server.js
node --check bin\cli.js
```

## Current Product Direction

Prioritize work that improves risk discovery:

- Role-driven orchestration and persona consistency
- Unified information ingestion
- Broad evidence retrieval and source coverage
- Enterprise relationship graph
- Risk event database
- Signal-triggered analysis
- Finance, industry, and product intelligence depth

Later-version work may add continuous monitoring, but it should not steer current release scope.

Avoid adding more roles unless the new role materially improves discovery quality. The existing 13-role expert-team setting is a core product surface, not garnish.
