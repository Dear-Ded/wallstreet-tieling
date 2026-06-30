# Codex Plugin Market Readiness

Status: pre-submission engineering package for `v0.5.0 Alpha`.

状态：`v0.5.0 Alpha` 预提交工程包。公开表述应强调开源免费、信息平权、企业认知和证据优先；不要暗示已通过市场审核或达到生产级全自动尽调。

## What Is Available In Alpha

- Plugin manifest: `.codex-plugin/plugin.json`
- Codex skill entrypoint: `skills/wallstreet-tieling/SKILL.md`
- Executable MCP server: `lib/mcp-server.js`
- Product MCP tools: `investigate_company`, `due_diligence`, `connector_catalog`, `release_readiness`, `development_requirements`
- Runtime release contract: `npx wallstreet-tieling --release`
- Runtime datasource catalog: `npx wallstreet-tieling --connectors`
- Runtime development requirement board: `npx wallstreet-tieling --requirements`
- Risk graph API contract: `docs/API_CONTRACTS.md`
- Executable graph CLI: `bin/risk_graph.py`
- Executable monitoring CLI: `bin/risk_monitor.py`
- Configurable datasource authentication framework
- Structured evidence graph export
- Monitoring delta summaries
- Standardized record quality audit reports

## Submission Claims Allowed Now

- Enterprise intelligence and risk discovery workflow
- Evidence-first due diligence planning
- Public, licensed, or user-authorized datasource integration pattern
- Graph/timeline/risk-event output surfaces
- Connector quality diagnostics
- Runtime connector catalog and release-readiness metadata
- Runtime P0/P1/P2/Future development requirements, with QYYJT current-version parity and continuous monitoring parked as later-version scope
- MCP-backed one-click investigation packet with enterprise cognition, profile, evidence ledger, and report markdown
- Offline fixture mode for deterministic smoke tests
- Free and open-source information-equality positioning, with provenance and confidence retained

## Submission Claims Not Yet Allowed

- Fully automated live investigation across all advertised sources
- Guaranteed controller or UBO discovery for every jurisdiction
- CAPTCHA bypass or unauthorized access automation
- Marketplace-approved status
- Production-grade financial intelligence engine
- Production-grade industry/product intelligence engine
- Any claim that the system can replace human legal, credit, investment, or compliance review

## Public Copy Guardrails

- Use `0.5.0 Alpha` when naming the release.
- Say "due-diligence draft" or "investigation packet", not "final report" unless a human review boundary is visible.
- Say the current desktop-agent variants are alpha: Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy Expert Team.
- Keep the one-sentence experience human: "Ask in plain language; get an evidence-led draft."
- Keep bilingual copy where practical for the public portal and README.

## Required Verification

Run from the repository root:

```powershell
npm run acceptance
```

`tools/run-acceptance.ps1` is the single local release gate. It covers:

- focused Python regression tests for investigation, API, release variants, release hygiene, WorkBuddy, encoding, enterprise cognition, official/public smoke, and QYYJT surfaces
- Codex plugin validator (`validate_plugin.py`)
- terminology guard
- Node syntax checks for `bin/cli.js`, `lib/mcp-server.js`, and `tools/codex-mcp-smoke.js`
- Packaged Codex MCP backing smoke: `connector_catalog`, `release_readiness`, `development_requirements`, and `investigate_company`
- Desktop-agent host smoke: Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy release variants plus the shared agent packet path

Latest local verification target:

- Plugin validator: passed in acceptance gate.
- Focused regression: acceptance gate.
- Node syntax checks: acceptance gate.
- Packaged Codex MCP backing smoke: acceptance gate.
- Desktop-agent host smoke: acceptance gate.
- Marketplace submission and host-level approval are still pending.

## Safety Boundary

The plugin package must not include tokens, cookies, local browser profiles,
local collaboration databases, or private environment files. Credentials must be
provided by the user through environment variables or host-authorized
integrations.
