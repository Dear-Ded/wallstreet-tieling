# Release Portal

This is the public release portal for **wallstreet-tieling 0.5.0 Alpha**.

The project is a desktop-agent-first enterprise due-diligence and risk-discovery
toolkit. It produces evidence-bound investigation packets from public,
licensed, or user-authorized sources. It does not claim marketplace approval,
final SaaS production readiness, guaranteed live coverage for every source, or
automated final legal/credit/investment conclusions.

## Release Decision

Current public claim:

```text
Desktop-agent alpha release candidate.
Ready for local packaging and public GitHub review.
Not final polished product launch readiness.
```

Machine-readable checks:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --release-preflight
npx wallstreet-tieling --delivery-audit
npx wallstreet-tieling --objective-audit
```

Operator checklist: `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`.
Asset checklist: `docs/RELEASE_ASSET_CHECKLIST.md`.

Expected current state:

- `release_preflight.status == ready_for_local_packaging`
- `delivery_audit.status == pass`
- `delivery_audit.failed_checks == []`
- `objective_audit.status == complete`
- `objective_audit.failed_requirements == []`

## Distribution Variants

| Variant | Current readiness | Primary entrypoints |
|---|---:|---|
| Universal | alpha | `bin/cli.js`, `api/server.py`, `deploy/mcp-server.json`, `SKILL.md` |
| Codex | alpha | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md`, `lib/mcp-server.js` |
| Claude Code | alpha | `CLAUDE.md`, `docs/CLAUDE_CODE_ADAPTER.md`, `docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md` |
| Hermes | alpha | `docs/HERMES_AGENT_SETUP.md`, `docs/API_CONTRACTS.md`, `deploy/multi-platform-guide.md` |
| Doubao Office Task Mode | alpha | `docs/OFFICE_TASK_MODE_HANDOFF.md`, CLI/API packet outputs |
| OpenClaude / open agents | alpha | `docs/OPEN_AGENT_COMPATIBILITY.md`, CLI/MCP/API fallback |
| WorkBuddy Expert Team | alpha | `adapters/workbuddy.py`, `docs/workbuddy/`, 13-role expert-team branch |

The source of truth for release variants is `release/variants.yaml`.

## Product Core

- 13-role anthropomorphic expert-team routing and coordination.
- Investigation planning from a company or organization name.
- Public, licensed, or user-authorized evidence retrieval.
- Evidence graph, relationship graph, capital-risk panel, and risk-event
  generation.
- QYYJT/public-origin mapping and report-section work orders.
- Due-diligence report outputs with provenance, confidence, and gaps.
- CLI, REST API, MCP, Codex plugin, skill prompt, and desktop-agent host
  adapters.

## Latest Local Verification

Current evidence:

- `npm run acceptance`: `799 passed, 9 skipped` at `2026-07-06 08:24 Asia/Shanghai`
- `npm run terminology:check`: `0 findings`
- `npm run api:smoke`: passed
- `npm run codex:mcp-smoke`: passed
- `npm run agent:host-smoke`: passed
- `npm run release:preflight`: `ready_for_local_packaging`
- `npm run delivery:audit`: `pass`
- `npm run objective:audit`: `complete`
- `npm run release:privacy-scan`: `issue_count=0`
- `npm pack --dry-run --json`: passed

## Public Boundaries

Do not claim:

- marketplace approval;
- final polished product launch readiness;
- all sources are live and guaranteed reachable;
- legal, credit, compliance, or investment conclusions without human review;
- CAPTCHA, login, payment, account, or permission bypass;
- current-release mini-program, mobile app, standalone desktop app, or
  always-on monitoring.

Do claim:

- desktop-agent alpha local package readiness;
- evidence-first investigation packet generation;
- source, confidence, and gap preservation;
- host-neutral CLI/API/MCP/Codex/Claude/Hermes/Doubao/OpenAgent/WorkBuddy alpha
  compatibility.

## Next Product Milestones

1. Capture marketplace/operator screenshots from real host review surfaces.
2. Tighten public GitHub presentation, screenshots, and hosted demo copy.
3. Continue report experience polish for Word and premium full-fidelity HTML.
4. Improve live-source breadth and source-specific field mapping.
5. Keep release hygiene, privacy scan, and package dry-run gates mandatory.
