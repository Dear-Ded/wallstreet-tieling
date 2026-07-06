# Codex Plugin Market Readiness

Status: pre-submission engineering package for `v0.5.0 Alpha`.

Public copy must say the product is an alpha desktop-agent release. Do not claim
marketplace approval, fully automated live coverage, or production-grade
compliance/credit replacement.

## Available In Alpha

- Plugin manifest: `.codex-plugin/plugin.json`
- Codex skill entrypoint: `skills/wallstreet-tieling/SKILL.md`
- Executable MCP server: `lib/mcp-server.js`
- Product MCP tools: `investigate_company`, `due_diligence`,
  `connector_catalog`, `release_readiness`, `development_requirements`, and
  `agent_tool_adapters`
- Runtime release contract: `npx wallstreet-tieling --release`
- Runtime datasource catalog: `npx wallstreet-tieling --connectors`
- Runtime development board: `npx wallstreet-tieling --requirements`
- Runtime agent adapter manifest: `npx wallstreet-tieling --agent-tools`
- Runtime retrieval plan smoke: `bin/retrieval_plan.py`
- Host smoke checklist: `docs/AGENT_HOST_SMOKE_CHECKLIST.md`
- REST contract: `docs/API_CONTRACTS.md`
- Structured investigation packet with enterprise cognition, evidence ledger,
  quality gate, Markdown report, portable HTML metadata, and DOCX renderer
  metadata

## Allowed Submission Claims

- Enterprise intelligence and risk discovery workflow.
- Evidence-first due-diligence planning.
- Public, licensed, or user-authorized datasource integration pattern.
- Graph, timeline, risk-event, and report-ready output surfaces.
- Connector quality diagnostics and datasource admission metadata.
- Runtime P0/P1/P2/Future development requirements.
- MCP-backed one-click investigation packet.
- Offline fixture mode for deterministic smoke tests.
- Open-source information-equality positioning with provenance and confidence
  retained.

## Claims Not Allowed Yet

- Fully automated live investigation across every advertised source.
- Guaranteed controller or UBO discovery for every jurisdiction.
- CAPTCHA bypass or unauthorized access automation.
- Marketplace-approved status.
- Production-grade financial, legal, investment, or compliance replacement.
- Polished immersive HTML workbench, mini-program, mobile app, or standalone
  desktop app as current-release features.
- Always-on continuous monitoring as a current-release feature.

## Required Verification

Run from the repository root:

```powershell
npm run acceptance
npm pack --dry-run --json
```

The acceptance gate covers:

- Focused Python regression tests for investigation, API, release variants,
  release hygiene, WorkBuddy, encoding, enterprise cognition, official/public
  smoke, and QYYJT surfaces.
- Codex plugin validator.
- Terminology guard.
- Node syntax checks for CLI, MCP, and smoke scripts.
- Packaged Codex MCP smoke: `connector_catalog`, `release_readiness`,
  `development_requirements`, `agent_tool_adapters`, `retrieval_plan`, and
  `investigate_company`.
- REST API smoke.
- Desktop-agent host smoke for Universal, Codex, Claude Code, Hermes, Doubao
  Office Task Mode, OpenClaude/open-source agents, and WorkBuddy.
- NPM package dry-run verification that agent delivery files are included and
  local runtime artifacts are excluded.

Latest local verification target:

- Plugin validator: passed in acceptance gate.
- Focused regression: acceptance gate.
- Node syntax checks: acceptance gate.
- Packaged Codex MCP backing smoke: acceptance gate, including retrieval plan
  and investigation cognition profile.
- REST API smoke: acceptance gate.
- Desktop-agent host smoke: acceptance gate.
- Marketplace submission and host-level approval are still pending.

## Submission Boundary

- Human-captured marketplace screenshots are still required before final
  submission.
- Use `docs/RELEASE_ASSET_CHECKLIST.md` as the capture source of truth.
- Screenshot content must show the manifest/skill, release readiness output,
  connector catalog output, and one offline fixture investigation packet.
- The package must not include tokens, cookies, local browser profiles, local
  collaboration databases, generated secrets, or private environment files.
- Credentials must come from environment variables or host-authorized
  integrations.
