# Desktop Agent Host Guide

Current scope: `0.5.0 Alpha` is a desktop-agent/tooling release. The polished
HTML product, mini-program, mobile app, and standalone desktop app are
later-version targets.

## Host Tracks

| Host track | Primary entrypoints | Runtime path |
| --- | --- | --- |
| Universal | `SKILL.md`, `bin/cli.js`, `api/server.py`, `deploy/mcp-server.json` | CLI, REST API, MCP, Docker, copy/paste prompt |
| Codex | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md` | Codex plugin, Codex skill, packaged MCP smoke |
| Claude Code | `CLAUDE.md`, `SKILL.md`, `docs/CLAUDE_CODE_ADAPTER.md` | repo handoff, project knowledge pack, MCP |
| Hermes | `SKILL.md`, `bin/cli.js`, `deploy/mcp-server.json`, `docs/HERMES_AGENT_SETUP.md` | skill prompt, CLI, MCP, API contract |
| Doubao Office Task Mode | `SKILL.md`, `bin/cli.js`, `api/server.py`, `docs/OFFICE_TASK_MODE_HANDOFF.md` | one-line office task prompt, Markdown/JSON packet |
| OpenClaude / open-source agents | `CLAUDE.md`, `SKILL.md`, `docs/API_CONTRACTS.md`, `docs/OPEN_AGENT_COMPATIBILITY.md` | repo instructions, CLI fallback, MCP/API fallback |
| WorkBuddy Expert Team | `adapters/workbuddy.py`, `SKILL.md`, `sub-skills/` | 13-role expert-team adapter, WorkBuddy tool routing, and `investigate_company` packet execution |

## Required Smoke

Run the host-neutral smoke before making stronger release claims:

```bash
npm run agent:host-smoke
```

Use `docs/AGENT_HOST_SMOKE_CHECKLIST.md` for host-specific Claude Code,
Hermes, Doubao Office Task Mode, OpenClaude/open-source agent, and WorkBuddy
checks.

The smoke verifies:

- `release_readiness` exposes all desktop-agent variants.
- `connector_catalog` exposes default-ready and QYYJT source metadata.
- `connector_catalog.groups.explicit_only` exposes advanced authorized sources
  including China tax-credit, judicial-asset, MOFCOM overseas-investment,
  Aiqicha, and Shuidi connectors; these must stay default-off until the user or
  deployment enables them and admission gates pass.
- `development_requirements` exposes the executable P0/P1/P2/Future board.
- `development_requirements.delivery_decision` exposes the current desktop-agent
  alpha handoff decision separately from full-product launch readiness.
- `delivery_closure` exposes the current desktop-agent alpha release-closure
  contract, required verification commands, preserved packet fields, and
  open submission items without implying full-product readiness.
- `agent_tool_adapters` exposes the host-specific baseline tool sequence,
  fallback order, smoke command, required packet fields, and report outputs for
  all seven desktop-agent tracks.
- `agent_tool_adapters.required_packet_fields` requires hosts to preserve
  `report_exports.directory_bundle.agent_handoff` and
  `report_exports.directory_bundle.agent_handoff.delivery_decision`,
  `report_exports.directory_bundle.agent_handoff.report_visibility`, and
  `report_exports.directory_bundle.agent_handoff.capital_risk_panel`, so the
  desktop-agent alpha decision, report visibility, and capital-risk reliance
  gate are not lost during host-specific formatting.
- `investigate_company` returns a versioned `investigation_packet` with
  evidence ledger, report Markdown, enterprise cognition, quality gate, and the
  current-release monitoring boundary.
- `investigate_company` exposes runtime handoffs for
  `qyyjt_public_origin_handoff`, `source_resilience_recommended_step`,
  `capital_verification_queue_count`, and
  `relationship_graph_audit_queue_count`.
- `report_exports` exposes Markdown, JSON packet, portable HTML, and
  `print_package` DOCX renderer capability metadata.

For release-impacting changes, run the full gate:

```bash
npm run acceptance
```

Before publishing a packaged desktop-agent claim, run:

```bash
npm pack --dry-run --json
```

The dry run must show the shared CLI/API/MCP/agent docs, smoke scripts,
`release/variants.yaml`, and skill assets in the package, while excluding
local collaboration fixtures, generated outputs, cookies, browser profiles,
private reports, and runtime state.

## Minimal Operator Prompt

Use this when a host can only receive natural-language instructions:

```text
You are running Wallstreet Tieling 0.5.0 Alpha as a desktop-agent host. Load the
repository instructions, then use CLI/API/MCP tools when available. First run
release_readiness, connector_catalog, development_requirements, and
delivery_closure. For an investigation, call agent_tool_adapters to read the
host-specific sequence and fallback order, then call investigate_company or run
`npx wallstreet-tieling --investigate "<company>"`. Return the
investigation_packet summary, evidence ledger, report_markdown, quality_gate,
source gaps, connector_catalog.groups.explicit_only,
connector_catalog.connectors[].data_effectiveness, qyyjt_public_origin_handoff,
source_resilience_recommended_step, capital_verification_queue_count,
relationship_graph_audit_queue_count, report_exports,
report_exports.directory_bundle.agent_handoff.delivery_decision,
report_exports.directory_bundle.agent_handoff.report_visibility,
report_exports.directory_bundle.agent_handoff.capital_risk_panel, and the
delivery_closure open submission items. Use portable_html when the host can
save an HTML artifact, and use the DOCX runtime renderer metadata before
offering `--export-docx`. Do not collapse delivery_decision, delivery_closure,
agent_handoff, quality_gate, or evidence_ledger into prose only. Do not claim
polished immersive HTML/app delivery or continuous monitoring as
current-release features.
```
