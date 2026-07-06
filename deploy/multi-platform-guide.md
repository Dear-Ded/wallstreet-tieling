# Multi-Platform Desktop Agent Guide

Wallstreet Tieling `0.5.0 Alpha` is delivered first as a desktop-agent
tooling package. The same runtime core can be used through CLI, REST API, MCP,
Codex skill/plugin, Claude Code instructions, Hermes-style local agents,
Doubao Office Task Mode, OpenClaude-style agents, and WorkBuddy.

Current-release target: usable investigation packets for desktop agents.
Polished immersive HTML, mini-program, mobile app, and standalone desktop app
remain later-version targets.

## Required Baseline

Every host should start with the same discovery sequence:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --agent-tools
```

The fourth command returns the `agent_tool_adapter_manifest`. Agents should use
it before host-specific formatting because it defines the baseline tool
sequence, fallback order, smoke command, required packet fields, and report
outputs for all supported hosts.

Canonical runtime sequence:

1. `release_readiness`
2. `connector_catalog`
3. `development_requirements`
4. `investigate_company`

Use `aggregate_subject` only after an investigation packet identifies a related
company, controller, or other subject that needs bounded follow-up.

## Supported Host Tracks

| Track | Primary files | Runtime path | Smoke |
|---|---|---|---|
| Universal | `SKILL.md`, `bin/cli.js`, `api/server.py`, `deploy/mcp-server.json` | CLI, REST API, MCP, Docker, copy/paste prompt | `npm run agent:host-smoke` |
| Codex | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md` | Codex plugin, Codex skill, MCP | `npm run codex:mcp-smoke` |
| Claude Code | `CLAUDE.md`, `docs/CLAUDE_CODE_ADAPTER.md`, `docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md` | repo instructions, project knowledge pack, MCP | `npm run agent:host-smoke` |
| Hermes | `SKILL.md`, `docs/HERMES_AGENT_SETUP.md`, `docs/API_CONTRACTS.md` | skill prompt, CLI, MCP, REST API | `npm run agent:host-smoke` |
| Doubao Office Task Mode | `docs/OFFICE_TASK_MODE_HANDOFF.md`, `docs/API_CONTRACTS.md` | copy/paste Chinese handoff, CLI, REST API, Markdown/JSON packet | `npm run api:smoke` |
| OpenClaude / Open Source Agents | `docs/OPEN_AGENT_COMPATIBILITY.md`, `CLAUDE.md`, `SKILL.md` | MCP, CLI, REST API, prompt-only fallback | `npm run agent:host-smoke` |
| WorkBuddy Expert Team | `adapters/workbuddy.py`, `sub-skills/`, `SKILL.md` | expert-team routing and tool delegation | `python -m pytest tests/unit/test_workbuddy.py -q` |

## MCP Configuration

Use this when a host supports local MCP servers:

```json
{
  "mcpServers": {
    "wallstreet-tieling": {
      "command": "npx",
      "args": ["-y", "wallstreet-tieling", "--mcp"],
      "env": {
        "WST_MCP_TIMEOUT_MS": "120000"
      }
    }
  }
}
```

Required MCP tools for current release:

- `release_readiness`
- `connector_catalog`
- `development_requirements`
- `agent_tool_adapters`
- `investigate_company`
- `aggregate_subject`

## CLI Usage

```bash
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-html outputs/demo.html --export-json outputs/demo.json
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-docx outputs/demo.docx
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-dir outputs/demo-report-bundle
```

The packet must preserve:

- `quality_gate`
- `evidence_ledger`
- `report_markdown`
- `qyyjt_public_origin_handoff`
- `one_click_readiness`
- `report_exports.agent_decision_digest`
- `report_exports.print_package`
- `report_exports.directory_bundle.agent_handoff`

## REST API Usage

Run the local API:

```bash
python api/server.py
```

Important endpoints:

- `GET /api/health`
- `GET /api/release`
- `GET /api/connectors`
- `GET /api/requirements`
- `GET /api/agent-tools`
- `POST /api/investigate`

Run the REST smoke:

```bash
npm run api:smoke
```

## Docker Usage

```bash
docker build -t wallstreet-tieling -f deploy/Dockerfile .
docker run --rm -p 8080:8080 wallstreet-tieling
```

Use environment variables for credentials and state paths. Do not bake API
keys, cookies, browser profiles, local collaboration databases, or generated
secrets into images or release artifacts.

## Host Boundaries

- Use public, licensed, or user-authorized data only.
- Treat blocked, empty, or unsearched sources as coverage gaps.
- Do not turn lead-only social or web clues into facts without corroboration.
- Do not require polished HTML or a graphical workbench for current-release
  desktop-agent operation.
- Do not claim marketplace approval, production-grade compliance replacement,
  or fully automated live coverage for `0.5.0 Alpha`.

## Acceptance Gate

Before raising a release claim, run:

```bash
npm run acceptance
```

For fast host checks during development:

```bash
npm run agent:host-smoke
npm run codex:mcp-smoke
npm run api:smoke
```
