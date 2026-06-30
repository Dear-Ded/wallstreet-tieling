# External Reference Radar

This project should learn from mature open-source systems without copying them blindly. The product goal is not "more agents" or "more prompts"; it is executable enterprise risk discovery: connectors feed evidence, evidence builds graphs and events, events trigger monitoring, and reports become one render surface.

Last refreshed: 2026-06-20

## Current Scan

| Project | Reference | Useful pattern for wallstreet-tieling |
|---|---|---|
| Sherlock | https://github.com/sherlock-project/sherlock | Username fan-out works because every site has a module contract, timeout behavior, and confidence interpretation. Borrow the registry discipline, not the personal-data framing. |
| Maigret | https://github.com/soxoj/maigret | Large source coverage needs normalized output and per-source metadata, otherwise 3000+ sites become noise. |
| SpiderFoot | https://github.com/smicallef/spiderfoot | OSINT becomes useful when scan runs, modules, entities, and relationships are first-class records. |
| web-check | https://github.com/lissy93/web-check | Website intelligence should be a composed checklist with provenance and human-readable diagnostics. |
| OpenBB | https://github.com/OpenBB-finance/OpenBB | Data access is infrastructure: one provider layer can serve CLI, API, MCP, UI, and notebooks. |
| OpenCTI | https://github.com/opencti-platform/opencti | Durable intelligence graphs beat one-off summaries. Connectors should map into common objects. |
| Scrapy | https://github.com/scrapy/scrapy | Crawling needs middleware, throttling, retries, pipelines, and item normalization as default architecture. |
| Crawlee | https://github.com/apify/crawlee | Production crawling should treat request queues, sessions, retries, and storage/checkpoints as first-class runtime objects. |
| Scrapling | https://github.com/D4Vinci/Scrapling | Modern scraping benefits from adaptive fetch strategies and stable extraction contracts. |
| SeleniumBase | https://github.com/seleniumbase/SeleniumBase | Browser automation is useful for authorized workflows, but public release should keep challenge handling as explicit handoff/provider slots. |
| LangGraph | https://github.com/langchain-ai/langgraph | Long-running agent workflows need checkpoints and explicit state transitions; roles alone are not enough. |
| financial-services-qcc | https://github.com/duhu2000/financial-services-qcc | Useful as a QCC/KYB/IC Memo scenario and report-template reference, but not as a dependency: shallow clone `b138843` showed hard-coded local paths, generated reports checked into the repo, minimal executable tests, and credential-oriented install scripts. |
| mcp-skills | https://github.com/tyc-tech/mcp-skills | Useful for the L0/L1/L2/L3 tool-layering pattern, entity anchoring before drill-down, and progressive tool disclosure. Treat as design reference only: shallow clone `07cf201` is a skills catalog with no license and no executable connector/runtime tests in the public repo. |

## Decisions Imported Into This Project

- Data sources are registered connectors with access model, authority, domains, health status, default policy, standardized-record support, and executable fixture packs for connector conformance.
- Raw results are not enough. Every connector must map into `standardized_records` or declare why it cannot.
- Public release defaults to public or user-authorized sources. Credentialed depth goes through admission review.
- Human-verification handling is a provider slot and handoff contract, not a bypass promise.
- Subject profiling uses bounded graph recursion, default depth 3, evidence-backed high-sensitivity leads, and explicit inference labels.
- Monitoring should evolve toward graph/event/timeline first; reports are rendered views.
- Monitoring runs are durable checkpoints. A scan/run ledger should retain per-company deltas, source routing, retrieval summaries, and alerts so the system can compare time, not only generate one-off output.
- Enterprise-source orchestration should expose a small high-confidence default surface first, then progressively drill down. Borrow the mcp-skills L0 entity-anchor -> L1 overview -> L2 prioritized drill-down -> L3 specialist pattern, but implement it as executable connector/task metadata rather than prompt-only instructions.
- QCC/KYB/IC Memo references are useful for business-section taxonomy, but any imported pattern must pass this project's evidence admission, source licensing, field-contract, and acceptance gates.

## Near-Term Engineering Queue

1. Make connector audits part of CI: executable, healthy, standardized, provenance-rich, tested.
2. Use datasource fixture packs as provider conformance tests for public registry, public web search, Telegram delivery shape, and licensed API examples.
3. Extend monitor-run ledgers into scheduled jobs, UI history, and source-health trend charts.
4. Expose graph/timeline/profile payloads through API and Codex plugin smoke tests.
5. Keep public/private variants sharing the same connector contract while differing only in configured sources and safety defaults.
6. Add retrieval-layer metadata for entity-anchor, overview, prioritized drill-down, and specialist query stages so broad source coverage does not overload the model or promote wrong-subject facts.
