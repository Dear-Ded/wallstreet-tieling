# Claude Code Adapter

Wallstreet Tieling can be used by Claude Code as a repository-native product:
repo instructions, executable CLI, MCP tools, and machine-readable release
metadata all point at the same shared core.

## What Claude Code Should Load

- `CLAUDE.md`: repository handoff and development rules.
- `SKILL.md`: product skill and role system.
- `README.md`: public product portal.
- `docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md`: Claude Project load order and packet-surface checklist.
- `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`: current delivery status,
  verification commands, and packet-preservation rules.
- `PROJECT_TASKBOARD.md`: active product board and current next task.
- `docs/PROJECT_MAP.md`: module map and release-scope checklist.
- `docs/SEARCH_INTEGRATION_LEDGER.md`: retrieval/source integration status.
- `release/variants.yaml`: source of truth for release variants.
- `deploy/mcp-server.json`: MCP server configuration.
- `docs/API_CONTRACTS.md`: REST contract.
- `docs/AGENT_HOST_SMOKE_CHECKLIST.md`: host-specific smoke checklist.
- `docs/DATASOURCE_ADMISSION.md`: datasource admission policy.

## Quick Smoke

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-docx outputs/demo.docx
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-html outputs/demo.html --export-json outputs/demo.json
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-dir outputs/demo-report-bundle
git status --short
```

The investigation packet should be treated as ready for operator review only
after Claude Code has surfaced these runtime fields:

- `qyyjt_public_origin_handoff`
- `one_click_readiness.source_resilience_recommended_step`
- `one_click_readiness.capital_verification_queue_count`
- `one_click_readiness.relationship_graph_audit_queue_count`
- `report_exports.portable_html.first_screen_handoff_cards`
- `report_exports.print_package.docx.renderer_capabilities`

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
- `agent_tool_adapters`
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
- Before staging or committing, run the public release hygiene commands in
  `README.md` and `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`.
- Do not stage the whole dirty tree. Keep `.tmp/`, `outputs/`,
  `tmp-events.jsonl`, browser state, cookies, tokens, local credentials, and
  sibling-project files out of release commits.

## Release Status

The Claude Code variant is `alpha`: the repo has working instructions,
knowledge-pack guidance, MCP-friendly assets, runtime handoff fields, portable
HTML handoff cards, and a DOCX runtime renderer exposed through `--export-docx`.
It is covered by the shared desktop-agent host smoke and remains alpha until
marketplace/operator review artifacts and real host screenshots are finalized.
