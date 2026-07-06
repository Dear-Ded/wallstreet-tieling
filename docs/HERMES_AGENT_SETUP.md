# Hermes Agent Setup

Scope: Hermes-style desktop/coding agents that can read repository instructions
and call local CLI, MCP, or REST API tools.

## Recommended Runtime

Use the package entrypoints:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
```

Use MCP when the host supports tool servers:

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

Use REST API when the host prefers HTTP:

```bash
python api/server.py
python tools/api-smoke.py
```

## Timeout Defaults

- `WST_MCP_TIMEOUT_MS=120000` for MCP tool calls.
- `WST_QUERY_TIMEOUT_SECONDS=8` for one-click public retrieval acceptance.
- `WST_TEST_STATE_DIR` or `WST_ACCEPTANCE_STATE_DIR` may point to writable temp
  storage in restricted desktop-agent environments.
- If a host has unstable network/proxy access, retry the same public or
  authorized route before marking it failed; still report the failure category
  in source diagnostics.

## Required Host Behavior

- Call `release_readiness`, `connector_catalog`, `development_requirements`, and
  `agent_tool_adapters` before making capability claims.
- For investigations, surface `quality_gate`, `evidence_ledger`,
  `qyyjt_public_origin_handoff`, source-resilience recovery steps, capital
  verification queue, relationship graph audit queue, and report export metadata.
- Do not require the polished HTML workbench for current-release operation.
- Keep continuous monitoring as later-version scope.
