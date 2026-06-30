# Desktop Agent Host Guide

Current scope: `0.5.0 Alpha` is a desktop-agent/tooling release. The polished
HTML product, mini-program, mobile app, and standalone desktop app are
later-version targets.

## Host Tracks

| Host track | Primary entrypoints | Runtime path |
|---|---|---|
| Universal | `SKILL.md`, `bin/cli.js`, `api/server.py`, `deploy/mcp-server.json` | CLI, REST API, MCP, Docker, copy/paste prompt |
| Codex | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md` | Codex plugin, Codex skill, packaged MCP smoke |
| Claude Code | `CLAUDE.md`, `SKILL.md`, `docs/CLAUDE_CODE_ADAPTER.md` | repo handoff, project knowledge pack, MCP |
| Hermes | `SKILL.md`, `bin/cli.js`, `deploy/mcp-server.json` | skill prompt, CLI, MCP, API contract |
| Doubao Office Task Mode | `SKILL.md`, `bin/cli.js`, `api/server.py` | one-line office task prompt, Markdown/JSON packet |
| OpenClaude / open-source agents | `CLAUDE.md`, `SKILL.md`, `docs/API_CONTRACTS.md` | repo instructions, CLI fallback, MCP/API fallback |
| WorkBuddy | `adapters/workbuddy.py`, `SKILL.md`, `sub-skills/` | 13-role expert-team adapter and skill prompt |

## Required Smoke

Run the host-neutral smoke before making stronger release claims:

```bash
npm run agent:host-smoke
```

The smoke verifies:

- `release_readiness` exposes all desktop-agent variants.
- `connector_catalog` exposes default-ready and QYYJT source metadata.
- `development_requirements` exposes the executable P0/P1/P2/Future board.
- `investigate_company` returns a versioned `investigation_packet` with
  evidence ledger, report Markdown, enterprise cognition, quality gate, and the
  current-release monitoring boundary.

For release-impacting changes, run the full gate:

```bash
npm run acceptance
```

## Minimal Operator Prompt

Use this when a host can only receive natural-language instructions:

```text
You are running Wallstreet Tieling 0.5.0 Alpha as a desktop-agent host. Load the
repository instructions, then use CLI/API/MCP tools when available. First run
release_readiness, connector_catalog, and development_requirements. For an
investigation, call investigate_company or run `npx wallstreet-tieling
--investigate "<company>"`. Return the investigation_packet summary, evidence
ledger, report_markdown, quality_gate, source gaps, and next_actions. Do not
claim polished HTML/app delivery or continuous monitoring as current-release
features.
```
