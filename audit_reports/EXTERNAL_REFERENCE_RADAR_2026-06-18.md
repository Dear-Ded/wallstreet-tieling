# External reference radar for wallstreet-tieling

This project should keep learning from mature open-source systems without copying their shape blindly. The goal is to extract product and architecture patterns that improve executable risk discovery.

## Reference projects

### OpenBB

Reference: https://github.com/OpenBB-finance/OpenBB

Why it matters:

- OpenBB positions data access as infrastructure: connect once, consume through Python, workspace UI, Excel, MCP, and REST.
- This maps directly to wallstreet-tieling's need for one datasource layer that serves CLI, Codex plugin, WorkBuddy, reports, and future dashboards.

What to borrow:

- Provider abstraction with strict standard output contracts.
- Separation between data integration, analysis logic, and presentation surface.
- A "free/open information access" product narrative that is still enterprise-grade.

### SpiderFoot

Reference: https://github.com/smicallef/spiderfoot

Why it matters:

- SpiderFoot is an OSINT automation system with many data sources and both web UI and CLI usage.
- It proves that broad-source intelligence only becomes useful when source modules, scan state, and navigable results are structured.

What to borrow:

- Source modules should report capability, health, and failure state.
- Scan runs should be first-class objects, not loose logs.
- UI/CLI should help users navigate relationships and leads, not just dump raw search results.

### OpenCTI

Reference: https://github.com/opencti-platform/opencti

Why it matters:

- OpenCTI structures, stores, organizes, and visualizes intelligence knowledge and observables.
- The same pattern is needed here for enterprise observables: company, person, address, account, filing, case, product, project, and risk event.

What to borrow:

- Intelligence graph as the durable center, with connectors feeding normalized objects.
- Connector ecosystem discipline: every source maps into a common model.
- Dashboard surfaces should prioritize correlation and escalation, not just document generation.

### LangGraph

Reference: https://github.com/langchain-ai/langgraph

Why it matters:

- LangGraph focuses on long-running, stateful agent workflows.
- wallstreet-tieling has long-running work: monitor watchlists, retry unstable model calls, escalate signals, and preserve checkpoints.

What to borrow:

- Treat workflow state and checkpoints as product features.
- Use explicit graph/state transitions for monitoring and escalation flows.
- Keep agent roles bounded by state-machine responsibilities; avoid adding more personas as a substitute for durable state.

### financial-services-qcc

Reference: https://github.com/duhu2000/financial-services-qcc

Why it matters:

- It is close to the same business neighborhood: QCC-based KYB, IC Memo, credit due diligence, UBO, litigation, IP, and exportable reports.
- The public repository has enough scenario material to cross-check our section taxonomy and user-facing report expectations.

Quality read:

- Treat it as partial/experimental, not a dependency. Shallow clone `b138843` showed hard-coded local paths under `/Users/qcc`, generated sample reports committed into the repo, credential setup scripts, and limited executable test discipline.
- Borrow report/skill taxonomy only after translating it into our source admission, field-contract, provenance, and acceptance-gate model.

### mcp-skills

Reference: https://github.com/tyc-tech/mcp-skills

Why it matters:

- Its strongest idea is not any single skill, but tool exposure discipline: L0 entity anchoring, L1 overview, L2 prioritized drill-down, and L3 specialist tools.
- This maps directly to our need to avoid dumping too many similar enterprise-intelligence tools into one model context.

Quality read:

- Treat it as design reference only. Shallow clone `07cf201` is a public skills catalog with no license and no executable connector/runtime tests in the repo.
- Borrow the progressive disclosure pattern and entity-disambiguation wording, then implement those as code-level connector/task metadata.

## Translation into current roadmap

Immediate engineering implications:

- Promote datasource adapters from "helper calls" into registered connectors with health, capability, standardized records, and provenance completeness checks.
- Treat monitoring runs as first-class records with run id, input watchlist, source health snapshot, discovered deltas, and alert decisions.
- Move from report-first outputs toward graph/event/timeline-first outputs; reports become rendered views.
- Keep public and private variants sharing the same connector contract while differing in configured sources and compliance defaults.

Near-term implementation queue:

1. Adapter audit table: every adapter gets status for executable, healthy, standardized, provenance-rich, and tested.
2. Monitoring delta model: distinguish newly discovered events from already-known open events.
3. Connector capability registry: source type, access model, authority, domains, supported query shapes, and default safety settings.
4. Graph/timeline API: return entity nodes, relations, risk events, and evidence chains for UI/plugin consumers.
5. Retrieval layering: add entity-anchor, overview, prioritized drill-down, and specialist-stage metadata to connector/query planning so broad source coverage stays controllable and wrong-subject facts are blocked early.
