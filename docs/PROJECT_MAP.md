# 项目总图 / Project Map

This is the canonical checklist for the current `wallstreet-tieling` release.
Scope: `0.5.0 Alpha` current-release only. Monitoring baselines stay in the
later-version bucket.

Private development takeover guide: `docs/PRIVATE_DEV_HANDOFF.md`.

Dirty workspace takeover rule: read
`docs/PRIVATE_DEV_HANDOFF.md#16-dirty-worktree-notice` before staging or
committing. The current private workspace has intentional tracked
modifications, deleted tracked files, new project files, audit/report outputs,
and runtime artifacts. Do not stage the whole tree.

## 1. Current Goal

One line in, one useful investigation packet out.

The current product must:

- accept a company name in plain language;
- route it through the 13-role expert surface;
- retrieve public or user-authorized evidence;
- normalize that evidence into a graph, profile, and report;
- expose gaps instead of fabricating certainty;
- ship through CLI, API, MCP, plugin, skill-prompt, and desktop-agent host surfaces.

## 2. Canonical Checklist

### In Place

- [x] One-click investigation packet.
- [x] Evidence ledger and risk graph export.
- [x] Subject profile with controller/relationship coverage.
- [x] Financial, industry, product, and control-ownership cognition.
- [x] Quality gate for report readiness.
- [x] Public/official connector registry and admission contract.
- [x] Default one-click public retrieval path.
- [x] Official-public smoke path.
- [x] Search integration ledger for source-by-source retrieval status.
- [x] QYYJT benchmark matrix and operator queue.
- [x] API, CLI, MCP, skill-prompt, and desktop-agent host surfaces.
- [x] Release contract for Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy.

### Still Evolving

- [ ] Stronger controller/UBO confidence model.
- [ ] Broader industry and product extraction from live/public sources.
- [ ] Cleaner handling of transient source failures in report tails.
- [ ] Live API field mapping for QYYJT beyond the admitted skeleton.
- [ ] Hosted deployment and release refresh.
- [ ] Observability: run IDs, trace IDs, metrics, and health dashboards.
- [ ] Productized report outputs: printable red-head Word document package,
      premium full-fidelity HTML report, and a third owner-confirmed output
      form.
- [ ] Dirty-worktree closure: split the current private workspace into narrow,
      reviewed commits without runtime artifacts or sibling-project files.

### Future Version Only

- [ ] Continuous watch / monitoring baseline as a repeated job.

## 3. Module Map

| Layer | Module | Responsibility | Borrowed pattern |
|---|---|---|---|
| Product surface | `api/server.py` | HTTP entrypoints for graph, investigation, monitor, connectors, and release data. | OpenBB-style shared provider layer |
| Product surface | `bin/investigate.py`, `bin/risk_discovery.py`, `bin/risk_graph.py`, `bin/risk_monitor.py` | CLI entrypoints for packet, graph, and monitoring runs. | Scrapy/Crawlee-style executable workflow |
| MCP surface | `lib/mcp-server.js` | Exposes the product as tool calls for hosts and plugins. | LangGraph-style stateful tool entrypoint |
| Retrieval planning | `core/intelligence_retrieval.py` | Turns a company name into retrieval domains, tasks, evidence classes, and source profiles. | Sherlock/Maigret module discipline |
| Execution pipeline | `core/risk_discovery_pipeline.py` | Runs retrieval tasks, ingests evidence, builds risk events, and collects failures. | Scrapy/Crawlee retries, queues, checkpoints |
| Subject model | `core/subject_profile.py` | Builds bounded entity expansion and controller/relationship views. | SpiderFoot/OpenCTI entity graph model |
| Packet builder | `core/investigation.py` | Converts graph output into the readable investigation packet and report. | web-check-style provenance-first report surface |
| Quality gate | `core/investigation_quality.py` | Decides whether the packet is usable, warned, or blocked. | Explicit gate/diagnostic contract |
| Source catalog | `core/connector_registry.py` | Declares connector readiness, authority, access, and default policy. | Sherlock/Maigret source registry |
| Default routing | `core/one_click_defaults.py` | Provides no-config public retrieval behavior. | OpenBB-style default provider path |
| Official smoke | `core/official_public_smoke.py` | Builds a constrained config/plan for live official-public validation. | Minimal conformance harness |
| Monitoring ledger | `core/risk_monitor.py` | Persists run history and health trends. | LangGraph/Crawlee-style checkpoint ledger |
| Release contract | `core/release_contract.py` | Defines variant/readiness metadata for distribution surfaces. | Single-source release manifest |
| QYYJT benchmark | `core/qyyjt_benchmark.py` | Tracks 45-module coverage and work queue. | Registry + queue discipline |
| Data plane | `adapters/multi_datasource/__init__.py` | Normalized connector framework, validation, retries, and source health. | Scrapy-style connector middleware |
| WorkBuddy | `adapters/workbuddy.py` | Bundled persona/tool/output adapter for the 13-role expert surface. | Shell-style host adapter |

## 4. Functional Breakdown

### Retrieval

Goal: coverage-first, source-aware search.

Implementation:

- keep the live source-by-source status in `docs/SEARCH_INTEGRATION_LEDGER.md`;
- split a company name into retrieval domains;
- assign tasks with source hints and expected evidence shapes;
- keep source authority and access explicit;
- retain failed routes instead of pretending the scan was complete.

### Evidence Graph

Goal: standardized records first, narrative second.

Implementation:

- ingest connector output into normalized evidence;
- keep claims, URLs, timestamps, and confidence;
- classify leads versus evidence;
- export graph, timeline, and diagnostics.

### Subject Profile

Goal: tell who the company is, who controls it, and what is connected to it.

Implementation:

- bounded recursion over relations and identifiers;
- controller/UBO candidates with evidence gaps;
- label sensitive leads instead of hiding them.

### Packet and Report

Goal: one human-readable artifact.

Implementation:

- summary, risk brief, profile brief, evidence ledger, cognition, quality gate;
- report text with explicit gaps and next actions;
- no fake certainty when the evidence is thin.

### Anthropomorphic Shell

Goal: keep the 13-role persona surface visible and consistent across all user
touchpoints.

Implementation:

- preserve named roles and persona routing in README, CLI, API, MCP, static UI,
  and WorkBuddy surfaces;
- keep the expert-team framing separate from the core evidence pipeline so it
  reads like a product feature, not decorative copy;
- make the shell consistent without letting it override evidence quality or
  source policy.

### Connector Admission

Goal: keep source policy honest.

Implementation:

- declare official/public/licensed/user-authorized boundaries;
- require standardized records and provenance;
- keep public and credentialed depth separated.

### Release and Distribution

Goal: same core, desktop-agent first surfaces.

Implementation:

- Universal: CLI/API/MCP/skill prompt;
- Codex: plugin + skill;
- Claude Code: handoff assets and MCP-friendly files;
- Hermes: CLI/MCP/API-compatible local agent workflow;
- Doubao Office Task Mode: one-line task prompt plus Markdown/JSON packet;
- OpenClaude/open-source agents: repo instructions plus CLI/MCP/API fallback;
- WorkBuddy: persona routing and host adapter.

### Monitoring

Goal: later-version repeatable watch jobs, not current-release scope.

Implementation:

- persist run history and deltas;
- keep it separate from the current single-shot product truth.

## 5. Evolution Line

1. Tighten the current packet.
2. Strengthen controller/UBO and relationship confidence.
3. Broaden industry/product extraction.
4. Keep QYYJT live/API mapping separate from the main product path.
5. Improve release/deployment and hosted refresh.
6. Promote monitoring into a later version only after the one-shot product is stable.
7. Keep the anthropomorphic shell consistent across every product surface.

## 6. Ponytail Rules Applied

- Keep the current surface small and explicit.
- Prefer existing modules over new abstractions.
- Use the minimum new code that explains the product truth.
- Delete drift before adding more layers.
