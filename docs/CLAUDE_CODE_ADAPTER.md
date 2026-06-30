# Claude Code Adapter

Wallstreet Tieling can be used by Claude Code as a repository-native product:
repo instructions, executable CLI, MCP tools, and machine-readable release
metadata all point at the same shared core.

## What Claude Code Should Load

- `CLAUDE.md`: repository handoff and development rules.
- `SKILL.md`: product skill and role system.
- `README.md`: public product portal.
- `docs/PRIVATE_DEV_HANDOFF.md`: private takeover state, current route, and
  dirty-worktree checkpoint.
- `PROJECT_TASKBOARD.md`: active product board and current next task.
- `docs/PROJECT_MAP.md`: module map and release-scope checklist.
- `docs/SEARCH_INTEGRATION_LEDGER.md`: retrieval/source integration status.
- `release/variants.yaml`: source of truth for release variants.
- `deploy/mcp-server.json`: MCP server configuration.
- `docs/API_CONTRACTS.md`: REST contract.
- `docs/DATASOURCE_ADMISSION.md`: datasource admission policy.

## Quick Smoke

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
git status --short
```

## MCP Setup

Use the package MCP entrypoint instead of a prompt-only wrapper:

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

Available product tools:

- `investigate_company`
- `due_diligence`
- `connector_catalog`
- `release_readiness`
- `development_requirements`
- `financial_analysis`
- `people_investigation`
- `anti_nominee_detection`
- `load_skill`

## Operating Rules

- Treat empty retrieval as a coverage gap, not a low-risk conclusion.
- Keep source, confidence, and verification status with every claim.
- Use public, licensed, or user-authorized sources only.
- Do not commit secrets, local runtime ledgers, browser profiles, or generated credentials.
- Preserve unrelated dirty worktree changes.
- Before staging or committing, compare `git status --short` with
  `docs/PRIVATE_DEV_HANDOFF.md#16-dirty-worktree-notice`.
- Do not stage the whole dirty tree. Keep `.tmp/`, `outputs/`,
  `tmp-events.jsonl`, browser state, cookies, tokens, local credentials, and
  sibling-project files out of release commits.

## Release Status

The Claude Code variant is `alpha`: the repo has working instructions,
knowledge-pack guidance, and MCP-friendly assets. It still needs broader
host-level smoke coverage before it should be called stable.
