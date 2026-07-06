# Project Map / 项目总图

This is the public module map and release checklist for `wallstreet-tieling`
`0.5.0 Alpha`.

Public release operators should start with:

- `README.md`
- `docs/RELEASE_PORTAL.md`
- `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`
- `docs/API_CONTRACTS.md`
- `docs/AGENT_HOST_SMOKE_CHECKLIST.md`

Before publishing or mirroring the repository, run the release hygiene commands
listed in `README.md` and confirm no runtime state, generated reports, local
paths, credentials, cookies, browser profiles, or private coordination notes are
staged.

## 1. Current Goal

One line in, one useful investigation packet out.

The current product must:

- accept a company name in plain language;
- route it through the 13-role expert surface;
- retrieve public, licensed, or user-authorized evidence;
- normalize evidence into a graph, profile, and report;
- expose gaps instead of fabricating certainty;
- ship through CLI, API, MCP, plugin, skill-prompt, and desktop-agent host surfaces.

## 2. Current Release Checklist

### Ready In 0.5.0 Alpha

- [x] One-click investigation packet.
- [x] Evidence ledger and risk graph export.
- [x] Subject profile with controller and relationship coverage.
- [x] Financial, industry, product, and control-ownership cognition.
- [x] Quality gate for report readiness.
- [x] Public/official connector registry and admission contract.
- [x] Default one-click public retrieval path.
- [x] QYYJT/public-origin mapping queue and report-section work orders.
- [x] Relationship graph audit and relationship-resolution handoff.
- [x] Capital-risk panel and capital verification queue.
- [x] Report exports for Markdown, JSON, portable HTML, DOCX metadata, and directory bundles.
- [x] API, CLI, MCP, skill-prompt, and desktop-agent host surfaces.
- [x] Release contract for Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy.
- [x] Objective audit and Superpowers final review evidence.

### Still Evolving

- [ ] Stronger controller/UBO confidence model.
- [ ] Broader industry and product extraction from live/public sources.
- [ ] Cleaner handling of transient source failures in report tails.
- [ ] Live API field mapping for QYYJT beyond the admitted skeleton.
- [ ] Hosted deployment and release refresh.
- [ ] Observability: run IDs, trace IDs, metrics, and health dashboards.
- [ ] Productized report outputs: printable red-head Word document package,
      premium full-fidelity HTML report, and a third owner-confirmed output form.
- [ ] Public repository hygiene: keep release commits narrow, reviewed, and free
      of runtime artifacts, local paths, generated reports, or private coordination files.

### Future Version Only

- [ ] Continuous watch / monitoring baseline as a repeated job.
- [ ] Mini-program, mobile app, and standalone desktop app surfaces.
- [ ] Fully polished public HTML workbench as the primary product surface.

## 3. Module Map

| Layer | Module | Responsibility |
|---|---|---|
| Product surface | `api/server.py` | HTTP entrypoints for graph, investigation, monitor, connectors, release, delivery, and objective audit data. |
| Product surface | `bin/cli.js`, `bin/investigate.py`, `bin/risk_discovery.py`, `bin/risk_graph.py` | CLI entrypoints for release metadata, investigation packets, graph exports, and report bundles. |
| MCP surface | `lib/mcp-server.js` | Exposes the product as tool calls for hosts and plugins. |
| Retrieval planning | `core/intelligence_retrieval.py` | Turns a company name into retrieval domains, tasks, evidence classes, and source profiles. |
| Execution pipeline | `core/risk_discovery_pipeline.py` | Runs retrieval tasks, ingests evidence, builds risk events, and collects failures. |
| Subject model | `core/subject_profile.py` | Builds bounded entity expansion and controller/relationship views. |
| Relationship model | `core/relationship_resolution.py` | Normalizes relationship edges and verification queues. |
| Packet builder | `core/investigation.py` | Converts graph output into the investigation packet, reports, and handoff artifacts. |
| Quality gate | `core/investigation_quality.py` | Decides whether the packet is usable, warned, or blocked. |
| Source catalog | `core/connector_registry.py` | Declares connector readiness, authority, access, source-strengthening state, and default policy. |
| Default routing | `core/one_click_defaults.py` | Provides no-config public retrieval behavior. |
| Release contract | `core/release_contract.py` | Defines release readiness, delivery audit, release preflight, and objective audit metadata. |
| Agent adapters | `core/agent_tool_adapters.py` | Defines per-host sequences, packet preservation rules, smoke commands, and WorkBuddy secondary branch behavior. |
| Report verification | `bin/verify_report_bundle.py` | Verifies directory bundles, manifest integrity, and agent-handoff fields. |
| QYYJT benchmark | `core/qyyjt_benchmark.py` | Tracks 45-module coverage and public-origin work queues. |

## 4. Distribution Surfaces

| Surface | Entry |
|---|---|
| npm package | `package.json`, `bin/cli.js` |
| Codex plugin | `.codex-plugin/plugin.json`, `skills/wallstreet-tieling/SKILL.md` |
| MCP | `lib/mcp-server.js`, `deploy/mcp-server.json` |
| REST API | `api/server.py` |
| Static workbench | `index.html` |
| Claude Code | `CLAUDE.md`, `docs/CLAUDE_CODE_ADAPTER.md`, `docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md` |
| Hermes / open agents | `docs/HERMES_AGENT_SETUP.md`, `docs/OPEN_AGENT_COMPATIBILITY.md` |
| Doubao Office Task Mode | `docs/OFFICE_TASK_MODE_HANDOFF.md` |
| WorkBuddy | `docs/workbuddy/`, `agent_tool_adapters` WorkBuddy branch |

## 5. Release Gates

Run before public release claims:

```bash
npm run acceptance
npm run api:smoke
npm run codex:mcp-smoke
npm run agent:host-smoke
npm run release:preflight
npm run delivery:audit
npm run objective:audit
npm run release:privacy-scan
npm pack --dry-run --json
```

Current evidence is recorded in:

- `docs/DESKTOP_AGENT_ALPHA_DELIVERY.md`
- `docs/RELEASE_PORTAL.md`
- `docs/SUPERPOWERS_FINAL_REVIEW.md`
- `core/release_contract.py`
