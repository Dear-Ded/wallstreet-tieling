# Release Portal

This repository is the public product portal for **wallstreet-tieling 0.5.0 Alpha**.

本仓库是 **wallstreet-tieling 0.5.0 Alpha** 的公开门户：开源、免费、证据优先，用一句人话发起企业尽调草稿，而不是承诺自动给出最终裁判。

The project is built as one shared enterprise-intelligence core with desktop-agent first distribution variants. The machine-readable source of truth is `release/variants.yaml`.

## Product Core

The shared core is responsible for:

- 13-role anthropomorphic expert-team routing and coordination
- Anthropomorphic shell and persona-consistent product framing across surfaces,
  including the runtime investigation packet and report
- Investigation planning from a company name
- Broad public-or-authorized evidence retrieval
- Retrieval status is tracked in `docs/SEARCH_INTEGRATION_LEDGER.md`
- Evidence graph and risk-event generation
- Enterprise Warning (QYYJT) admitted-field graph bridge for structured
  licensed/API risk, controller, credit, financial, legal/admin, registry,
  operating-event, and industry/product payloads
- Deep subject profiles and bounded entity fan-out
- Enterprise cognition profile
- Financial, industry, and product intelligence
- Due-diligence draft generation with evidence gaps instead of fabricated facts
- Executable development requirement board for P0/P1/P2/Future scope,
  current completion, next focus, and current-release vs later-version boundaries
- Desktop-agent entrypoints for CLI, API, MCP, skill-prompt, and host-specific
  workflows; polished HTML and app surfaces are later-version targets

Every public-facing claim should keep provenance, confidence, and human-review boundaries visible.

## Distribution Variants

| Variant | Current readiness | Primary entrypoints | Purpose |
|---|---:|---|---|
| Universal | alpha | `SKILL.md`, `bin/cli.js`, `api/server.py`, `adapters/cli.py`, `deploy/mcp-server.json` | Host-neutral CLI, API, MCP, Docker, and copy/paste usage |
| Codex | alpha | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md`, `bin/retrieval_plan.py` | Codex plugin and Codex skill workflow |
| Claude Code | alpha | `CLAUDE.md`, `SKILL.md`, `adapters/README.md`, `docs/CLAUDE_CODE_ADAPTER.md`, `deploy/mcp-server.json` | Claude Code repo handoff, Claude Project knowledge pack, and MCP-friendly assets |
| Hermes | alpha | `SKILL.md`, `bin/cli.js`, `deploy/mcp-server.json`, `docs/API_CONTRACTS.md`, `deploy/multi-platform-guide.md` | Hermes-style local agent workflow through skill, CLI, MCP, and API contracts |
| Doubao Office Task Mode | alpha | `SKILL.md`, `bin/cli.js`, `api/server.py`, `docs/API_CONTRACTS.md`, `deploy/multi-platform-guide.md` | Office-task agent workflow with one-line prompts and Markdown/JSON packets |
| OpenClaude / Open Source Agents | alpha | `SKILL.md`, `CLAUDE.md`, `bin/cli.js`, `deploy/mcp-server.json`, `docs/API_CONTRACTS.md`, `deploy/multi-platform-guide.md` | Open-source agent workflow with repo instructions and CLI/MCP/API fallback |
| WorkBuddy Expert Team | alpha | `adapters/workbuddy.py`, `SKILL.md`, `sub-skills/` | WorkBuddy/OpenClaw/CodeBuddy 13-role expert-team workflow with persona routing, catalog, and release-readiness tools |

All desktop-agent variants are alpha in 0.5.0. None should be described as marketplace-approved, production-grade, or fully automated live due diligence.

所有桌面 Agent 适配版在 0.5.0 都是 alpha，不应描述成已通过市场审核、生产级或全自动实时尽调。

## Release Gates

Before publishing a claim in the public portal:

- The claim must map to a real entrypoint, test, or roadmap item.
- The local release gate must pass: `npm run acceptance`.
- Data-source claims must distinguish live, configured, planned, and fallback sources.
- Credentials must come from environment variables or user-authorized host integrations.
- No tokens, cookies, browser profiles, local SQLite DBs, or generated secrets may be tracked.
- Core outputs must expose evidence gaps instead of inventing facts.
- Desktop-agent entrypoints must expose equivalent release, connector, and investigation behavior without requiring the polished HTML workbench.

## Next Product Milestones

1. Add host-level smoke tests for Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy variants.
2. Tighten the host-neutral CLI/API/MCP packet contract for desktop agents.
3. Build a stronger enterprise relationship graph and broader retrieval coverage.
4. Continue auditing every information source and label it as live, configured, planned, or fallback.
5. Close current-release P0 items from `npx wallstreet-tieling --requirements` before widening UI or hosted-demo polish.

Monitoring baselines are a later-version target and are intentionally not part of the current release claim set.
Current 0.5.0 reports expose a reusable baseline only; they do not promise live continuous monitoring.

## Latest Local Verification

- Latest full acceptance: `728 passed, 9 skipped`, plugin validation passed, and Apple Inc. default one-click acceptance passed after source-resilience readiness, coverage execution, coverage-gap severity/action fields, public-origin recovery actions, relationship-candidate execution, unresolved capital-relationship status, rich query-plan lead-only sealing, desktop-agent report exports, API contract visibility, and agent smoke gates.
- Latest executable requirement board: `88%` current-release completion after adding the P2 productized report-output scope; QYYJT current-version parity is `94%`; evidence admission is `92%`; report value/cognition is `95%`; controller/UBO subject-profile is `93%`; public source breadth is `89%`; operational observability is `78%`; release hygiene is `95%`; productized Word/HTML report outputs are `12%` and planned.
- Runtime connector catalog now includes `data_effectiveness`, separating fact-capable sources, lead-capable sources, authorization-gated fact sources, analysis-output coverage, and limitations.
- Retrieval planning now includes explicit supply-chain and industry-analysis deep-dive tasks; industry/product/supply-chain extraction is `88%`; evidence-backed supply-chain claims now render in `供应链与商业版图`; public web can conservatively extract explicit customer/supplier/partner/upstream/downstream/concentration, market-position, business-model, sales-channel, capital-structure, and public people-role statements, while deeper source-specific parsing and corroboration remain open.
- Investigation reports now expose the `扒光查案式调查` lens: money tracks cash, financing, solvency, and operating activity; goods tracks product, industry, upstream/downstream, customers, suppliers, partners, and concentration; people tracks controllers, UBO/key people, relationship networks, and legal/admin signals.
- RetrievalPlan seed tasks now carry the same money/goods/people case lens through `params.investigation_track` and `params.case_questions`, so source execution can keep the deep-investigation objective visible.
- Public web extraction now emits conservative subject-specific capital and key-person leads for financing, debt/credit, liquidity pressure, pledged/frozen/auction pressure, and public role cues; exact/strong public-web capital leads can feed `operational_event_profile` and `fund_flow_profile` as corroboration-needed rows.
- Investigation packets now expose `fund_flow_profile`, linking revenue, operating cash flow, financing events, bond pressure, and asset/solvency pressure into a report-visible `资金流画像`.
- Investigation packets now expose `goods_flow_profile`, linking admitted product, industry, upstream/downstream, customer, supplier, partner, concentration, value-chain, and pressure-point evidence into a report-visible `货物流/生意链画像`.
- Investigation packets now expose `people_flow_profile`, linking controllers, key people, relationship edges, control paths, legal/admin pressure, and next questions into a report-visible `人线/控制关系画像`.
- One-click readiness now exposes source-resilience status and recommended recovery action, plus relationship graph edge counts split by evidence-backed, auditable fact, missing-evidence, and lead-only edges for desktop-agent hosts.
- One-click readiness now also exposes coverage execution, coverage-gap count/severity/attempt ratio/next action, QYYJT/public-origin fallback actions, relationship-candidate execution steps, unresolved capital-pressure relationship status, and portable report export metadata for desktop-agent hosts.
- Subject-profile relationship graph edges now preserve evidence-derived admission, source names, and source strength before they reach quality gates, report Markdown, API contracts, or agent hosts.
- API index/docs and plugin prompts now label monitoring execution as explicit baseline re-checks; live continuous monitoring remains later-version scope.
- Static workbench now surfaces the same `case_investigation_lens`, `goods_flow_profile`, and `people_flow_profile` in the brief panel and fallback Markdown export, so the money/goods/people tracks are visible outside the raw report body.
- Quality gate now warns on single-source supply-chain/business-map profiles and records a strength only when supply-chain claims have multi-source support.
- Latest focused investigation/quality/requirements regression after adding goods-flow report cognition: `31 passed`.
- Latest focused intelligence-retrieval/requirements regression after adding case-track task metadata: `31 passed`; single-file investigation retry passed with `22 passed` after a transient Node `VirtualAlloc failed` run.
- Latest focused public-web/investigation regression after adding public capital/key-person leads and fund-flow admission: `50 passed`.
- Latest focused investigation regression after adding people-flow report cognition: `23 passed`.
- Latest focused investigation-quality/investigation regression after adding supply-chain corroboration quality checks: `27 passed`.
- Latest focused encoding/investigation/public-web/default-public-intel regression after adding structured workbench lens rendering: `63 passed`.
- Latest focused investigation/public-web/default-public-intel/requirements regression after adding the money/goods/people report lens: `59 passed`.
- Latest focused public-web/default-public-intel/investigation regression after adding public supply-chain lead extraction: `55 passed`.
- Latest focused investigation/retrieval/requirements regression after adding supply-chain/business-map report cognition: `52 passed`.
- Runtime state stores now support explicit env overrides and writable temp fallback, so restricted environments do not break risk-event, monitor-run, or memory storage.
- Acceptance now redirects TEMP, state, and pytest cache paths to a writable acceptance state directory with a fresh TEMP subdirectory per run, so running under a protected install directory no longer writes `.pytest_cache` in the protected repo root or reuses stale pytest temp folders.
- Focused regression runs are available through `npm run test:focused`; the script uses the same writable state/cache policy and a fresh TEMP subdirectory to avoid ad hoc pytest permission failures.
- Release hygiene retries transient Windows page-file failures from `git ls-files` (`WinError 1455`) before treating them as real release failures.
- Package variant tests now verify that every local `tools/*` file referenced by npm scripts exists and is included in the npm package whitelist; `npm pack --dry-run --json` confirms `tools/run-terminology-check.ps1` is packaged.
- Workspace Python runtime was refreshed from `requirements.txt` so API/CLI tests have Flask, aiohttp, requests, PyYAML, pytest, and pytest-asyncio available.
- Latest focused evidence-admission/QYYJT/subject-profile/investigation regression: `87 passed`; Apple Inc. default one-click compact check reports `Factual=0`, `Leads=5`, and `TopEdges=0` after query-plan leads were sealed out of graph facts.
- Latest focused QYYJT commercial-activity/report regression: `45 passed`.
- Latest focused report-value/control-path regression: `20 passed`.
- Latest focused retrieval-layer budget/default-public-intel/pipeline regression: `47 passed`.
- Latest focused Wikidata/subject-profile/intelligence regression after board-member and owner-of extraction: `103 passed`.
- Latest focused SEC/subject-profile/intelligence/requirements regression after structured key-person admission: `105 passed`.
- Latest focused retrieval-layer/pipeline regression: `40 passed`.
- Latest focused default-public-intel/retrieval-layer regression: `46 passed`.
- Latest focused retrieval-layer/default-public-intel/pipeline/API/CLI/WorkBuddy regression: `97 passed`.
- Latest focused QYYJT/current-board regression after financing/change/news/research bridge: `26 passed`.
- Latest focused API/WorkBuddy/investigation/record-quality regression after queue expansion: `50 passed`.
- Latest focused public-web/default-intel/investigation regression after industry/product bridge: `48 passed`.
- Latest focused QYYJT legal/admin profile regression: `21 passed`.
- Latest focused QYYJT provenance/record-quality regression: `25 passed`.
- Latest focused investigation/quality/requirements regression: `26 passed`.
- Latest focused requirement/API/QYYJT/WorkBuddy regression: `50 passed`.
- Latest focused P0 QYYJT/API/subject-profile regression: `76 passed`.
- Latest focused QYYJT/report-quality regression: `42 passed`.
- Latest broader requirements/QYYJT/search/API/WorkBuddy/investigation/release/encoding/hygiene regression: `111 passed`.
- Focused QYYJT/investigation graph regression: `79 passed`.
- Focused investigation/API/WorkBuddy/release regression: `53 passed`.
- `npm run terminology:check`: `0 findings`.
- Packaged Codex MCP smoke covers `connector_catalog`, `release_readiness`, `development_requirements`, and `investigate_company`.
- Static workbench Playwright checks passed at desktop and mobile widths with no page errors or horizontal overflow.
- Static workbench export QA verified Markdown, JSON, and portable HTML report downloads from the current packet.
