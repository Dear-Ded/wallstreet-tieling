# Open Agent Compatibility

Scope: OpenClaude-style open-source desktop, terminal, and coding agents that
can read repo instructions and call local CLI, REST API, or MCP tools.

## Minimum Requirements

- Node.js 18 or newer.
- Python 3.11 or newer.
- `pip install -r requirements.txt`.
- `npm install` when using MCP or Node CLI smoke scripts.
- Writable temp/state directory for local ledgers and smoke runs.

## Optional Environment Variables

- `WST_PYTHON`: absolute path to the Python runtime used by Node wrappers.
- `WST_NODE`: absolute path to Node.js for PowerShell acceptance scripts.
- `WST_MCP_TIMEOUT_MS`: MCP tool timeout in milliseconds; default recommendation is `120000`.
- `WST_QUERY_TIMEOUT_SECONDS`: per-query timeout for public retrieval; acceptance uses `8`.
- `WST_STATE_DIR`: local runtime state directory.
- `WST_TEST_STATE_DIR`: focused-test state directory.
- `WST_ACCEPTANCE_STATE_DIR`: full acceptance state directory.

## Host Fallback Order

1. MCP: `npx wallstreet-tieling --mcp`
2. CLI: `npx wallstreet-tieling --investigate "<company>"`
3. REST API: `python api/server.py`
4. Prompt-only: `SKILL.md` plus `docs/API_CONTRACTS.md`

## Required Smoke

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --delivery-closure
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --agent-tools
python tools/api-smoke.py
npm run agent:host-smoke
```

## Packet Handling

Open agents should preserve the full JSON investigation packet and expose:

- `report_markdown`
- `quality_gate`
- `evidence_ledger`
- `qyyjt_public_origin_handoff`
- `one_click_readiness`
- `report_exports`
- `report_exports.directory_bundle.agent_handoff`
- `report_exports.directory_bundle.agent_handoff.report_visibility`
- `report_exports.directory_bundle.agent_handoff.capital_risk_panel`
- `report_exports.directory_bundle.agent_handoff.delivery_decision`
- `delivery_closure`
- `enterprise_cognition`

When converting to another local artifact, do not drop findings from the
Markdown report, evidence ledger, delivery decision, delivery closure, or agent
handoff. If a field is missing, report the gap and the relevant next action.

## Release Closure

Open agents must treat `delivery_closure` as the machine-readable release
closure source for the desktop-agent alpha target. It records the required
verification commands, fields that must survive host formatting, and submission
items that remain outside the current release claim. Do not infer full-product
readiness from a successful investigation packet; the current release remains
desktop-agent alpha unless `delivery_closure.status` and the full acceptance
evidence support a stronger claim.
