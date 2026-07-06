# Claude Project Knowledge Pack

Scope: Claude Code and Claude Project hosts that consume repository knowledge
files before calling local CLI, REST API, or MCP tools.

## Load Order

1. `CLAUDE.md`
2. `SKILL.md`
3. `docs/DESKTOP_AGENT_HOSTS.md`
4. `docs/CLAUDE_CODE_ADAPTER.md`
5. `docs/API_CONTRACTS.md`
6. `docs/DATASOURCE_ADMISSION.md`
7. `PROJECT_TASKBOARD.md`
8. `docs/PROJECT_MAP.md`
9. `docs/SEARCH_INTEGRATION_LEDGER.md`
10. `release/variants.yaml`
11. `deploy/mcp-server.json`

## Runtime Discovery

Run these before making release or capability claims:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --requirements
npx wallstreet-tieling --agent-tools
```

Claude hosts should call MCP `agent_tool_adapters` when MCP is available. The
baseline tool sequence is `release_readiness`, `connector_catalog`,
`development_requirements`, then `investigate_company`; use `aggregate_subject`
only for bounded follow-up on related subjects surfaced by the packet.

Run one deterministic packet smoke:

```bash
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
```

Use the REST API smoke when the host can run Python:

```bash
python tools/api-smoke.py
```

Use the shared host smoke when the host can run Node:

```bash
npm run agent:host-smoke
```

## Required Packet Fields

Claude hosts must surface these fields before treating a packet as ready for
operator review:

- `quality_gate`
- `evidence_ledger`
- `report_markdown`
- `qyyjt_public_origin_handoff`
- `one_click_readiness.source_resilience_recommended_step`
- `one_click_readiness.capital_verification_queue_count`
- `one_click_readiness.relationship_graph_audit_queue_count`
- `report_exports.portable_html.first_screen_handoff_cards`
- `report_exports.print_package.docx.renderer_capabilities`
- `enterprise_cognition.control_ownership.controller_conflict_summary`
- `agent_tool_adapters.shared_tools`
- `agent_tool_adapters.adapters[].tool_sequence`

## Current-Release Boundary

- The current release is desktop-agent first.
- Polished immersive HTML, mini-program, mobile app, and standalone desktop app
  are later-version targets.
- Continuous monitoring is later-version scope; the current packet exposes
  baseline seeds and explicit follow-up queues only.
- Empty retrieval or blocked sources must be reported as coverage gaps, not as
  low-risk findings.
- Public, licensed, or user-authorized evidence only; keep source, confidence,
  and verification status attached to claims.
