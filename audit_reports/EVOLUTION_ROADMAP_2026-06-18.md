# wallstreet-tieling 2026-06-18 development roadmap

## Working rule

This is a long-running product project, not a one-off coding task. The user may describe needs in product language, emotional language, or incomplete non-technical terms. The developer role is to translate that into a plan, keep priorities ordered, implement with judgment, and avoid blindly following every interruption when it would hurt the product direction.

## Product position

The project is evolving from an "AI due diligence assistant" into an Enterprise Intelligence & Risk Discovery System.

The target is not longer reports. The target is risk discovery:

- collect public or authorized evidence,
- normalize source records,
- connect entities, people, events, products, finance, and industry context,
- detect contradictions and abnormal signals,
- preserve provenance and evidence chains,
- produce reports only as one output of the intelligence workflow.

## Current implemented baseline

As of this checkpoint, the private/dev branch contains these working pieces:

- Multi-source retrieval layer with standardized result records, health state, available-source routing, and source-level connectivity behavior.
- Search tooling that prefers healthy/available sources instead of blindly querying every configured source.
- Context-budget capsules that reduce raw-context explosion in orchestrator and engine paths.
- Evidence ingestion from standardized retrieval results into `EvidenceGraph` and risk events.
- `RiskEventStore.latest_alerts()` for high-priority monitoring surfaces.
- Initial Wu Dehou process supervision layer with structured `SupervisionEvent` records.
- Orchestrator integration that records supervision pass/reject events and returns `supervision_log`.
- Retry hardening for unstable model proxy conditions such as capacity errors, timeouts, 429, and 5xx responses.
- Executable offline smoke path: `python bin/risk_pipeline_smoke.py "Demo Technology Co., Ltd."` runs company-name input through retrieval planning, evidence graph ingestion, risk-event persistence, and alert output without API keys, network, or model access.
- `RiskDiscoveryPipeline` core entrypoint now owns the reusable company-name -> retrieval execution -> standardized evidence -> graph -> risk-event store -> alert payload path. The smoke CLI is a thin wrapper over this production path.
- Retrieval execution now exposes `retrieval_summary` and `source_diagnostics`, so empty sources, failed sources, ingested record counts, and domain-level attempts are visible instead of silently disappearing.
- `bin/risk_discovery.py` can now run either a deterministic offline fixture or a user-provided datasource YAML via `--config`; the configured path initializes `SearchEngine`, uses its startup connectivity checks, and routes through available sources.
- Risk discovery output now includes datasource routing diagnostics when configured sources are used: configured sources, available sources, unavailable sources, and health states.
- Datasource health now has structured `HealthReport` diagnostics for plugin/portal status panels, while the legacy bool health API remains compatible.
- `RiskMonitor` adds a reusable batch monitoring loop for watchlists: multiple companies in, persisted risk events and high-priority alerts out.
- `bin/risk_monitor.py` is a formal executable monitoring CLI with direct company arguments, `--companies-file`, `--config`, `--offline-fixture`, and JSON output.
- `bin/risk_graph.py` exports a compact graph/timeline payload with nodes, edges, evidence, risk events, timeline rows, summary, and diagnostics for plugin/UI consumers.
- `/api/risk-graph` returns the same compact graph/timeline payload for portal, plugin, or local service consumers.
- CI now protects both single-company risk discovery and batch monitoring offline smoke paths.
- Connector capability registry now covers production readiness for REST datasources plus review-aware bridges for QYYJT, public web search, and Telegram-style public services.
- Adapter readiness audit now emits `readiness_score` and `priority`, turning connector cleanup into a sortable P0/P1/P2/P3 work queue.
- Public web-search results can now be normalized into standardized evidence records and fed into the risk discovery pipeline as URL-verification leads.
- Public web-search normalization now removes common tracking parameters, generates stable dedupe keys, and collapses duplicate hits before evidence ingestion.
- Public web-search records now support approved URL-level fetcher callbacks or fixture content, attaching content hash, preview, HTTP status, and verification evidence.
- Public web-search now has a live provider slot: callable providers and self-hosted SearXNG JSON endpoints can feed the same dedupe/fetch/standardization path.
- Telegram public-service delivery is now modeled as a user-configured, disabled-by-default bridge that preserves bot handle, service description, authorization scope, payload, and provenance notes before graph ingestion.
- Public web-search provider configuration now has a product-facing health report: missing SearXNG/provider settings, provider readiness, and next action are visible before a query runs.
- Public web-search now has a zero-config default provider path (`auto` -> DuckDuckGo Instant Answer) for first-run smoke and starter reports, while advanced users can still inject providers or configure SearXNG.
- Telegram public-service now has a live provider slot and source-review report, so bot-style delivery can be tested as user-authorized transport while keeping source legitimacy metadata explicit.
- QYYJT now exposes a structured authorization report for cookie validity, optional API smoke checks, next action, and standardized record readiness.
- Datasource production admission now has a machine-readable framework with tiers, production decisions, blockers, controls, next actions, and conditional routes for QYYJT and Telegram public-service deployments.
- Public, no-credential entries for public web, QYYJT, and Telegram public-service are default-on; credentialed/API/private depth remains gated by user authorization, terms/scope review, provenance retention, audit logging, standardized records, and live validation.
- The default multi-datasource YAML template is now clean, loadable, default-safe, and covers public REST, SearXNG, licensed bearer auth, request signing, challenge-aware handoff, and Telegram service metadata without secrets.
- `config.example.yaml` is now a clean 0.5.0 template with retrieval/provider, monitoring, retry, and context-budget settings, plus tests that verify it parses and ships no real secrets.
- Adapter readiness audit now reports the bridge code/test paths for public web search and Telegram public services, keeping them visible as review-gated connectors rather than hidden experiments.
- Multi-source REST connectors now use a configurable authentication handler layer for basic auth, API keys, bearer/session auth, request signing, refresh detection, and challenge-aware authorization handoff.
- Human-verification handling now has a default-safe provider slot: `disabled` reports structured challenge metadata, while `browser_handoff` returns a UI/plugin handoff contract without bypassing access controls.
- Codex plugin metadata is updated to `v0.5.0` and validates with the local plugin validator.
- API/plugin contracts are documented for graph, timeline, evidence, risk events, and monitoring delta payloads.
- Standardized record quality reports are attached to public web, Telegram public-service, and QYYJT tool outputs.
- Risk graph/API diagnostics now expose record-quality summaries directly, so plugin and portal consumers can render connector quality without unpacking raw retrieval internals.

Latest focused verification:

- `python -m py_compile api/orchestrator.py api/personality.py core/supervision.py tests/unit/test_orchestrator.py tests/unit/test_personality.py`
- `pytest tests/unit/test_orchestrator.py tests/unit/test_personality.py tests/unit/test_core.py tests/unit/test_release_variants.py -q`
- `pytest tests/unit/test_risk_pipeline_smoke.py tests/unit/test_risk_event_store.py tests/unit/test_engine.py -q`
- `python bin/risk_pipeline_smoke.py "Demo Technology Co., Ltd."`
- `pytest tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_pipeline_smoke.py tests/unit/test_risk_event_store.py tests/unit/test_engine.py -q`
- Result after diagnostics hardening: 24 passed, 5 warnings.
- `python bin/risk_discovery.py "Demo CLI Co., Ltd." --offline-fixture`
- `python bin/risk_monitor.py "Demo Technology Co., Ltd." "Demo Manufacturing Co., Ltd." --offline-fixture`
- `pytest tests/unit/test_multi_datasource.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_discovery_cli.py -q`
- `pytest tests/unit/test_risk_monitor.py tests/unit/test_risk_monitor_cli.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_event_store.py -q`
- Result after monitoring runner: 39 passed for datasource/discovery focus; 16 passed for monitor/store focus; 5 known Pydantic deprecation warnings remain.
- `pytest tests/unit/test_telegram_public_service_tool.py tests/unit/test_public_web_search_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after connector bridge work: 18 passed, 5 known Pydantic deprecation warnings remain.
- `python <CODEX_PLUGIN_VALIDATOR> .`
- `pytest tests/unit/test_auth_handlers.py tests/unit/test_intelligence_retrieval.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_risk_event_store.py tests/unit/test_risk_monitor.py tests/unit/test_record_quality.py tests/unit/test_public_web_search_tool.py tests/unit/test_telegram_public_service_tool.py tests/unit/test_qyyjt_tool.py tests/unit/test_api_server.py -q`
- Result after plugin metadata and risk-discovery hardening: 57 passed, 5 known Pydantic deprecation warnings remain.
- `python -m py_compile core/risk_graph_export.py tests/unit/test_risk_graph_export.py`
- `pytest tests/unit/test_risk_graph_export.py tests/unit/test_api_server.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after graph diagnostics quality exposure: 11 passed, 5 known Pydantic deprecation warnings remain.
- `python -m py_compile adapters/multi_datasource/auth_handlers.py adapters/multi_datasource/__init__.py tests/unit/test_auth_handlers.py`
- `pytest tests/unit/test_auth_handlers.py tests/unit/test_multi_datasource.py -q`
- Result after challenge-provider slot hardening: 43 passed, 5 known Pydantic deprecation warnings remain.
- `python -m py_compile adapters/multi_datasource/__init__.py tests/unit/test_multi_datasource.py core/risk_discovery_pipeline.py tests/unit/test_risk_discovery_pipeline.py`
- `pytest tests/unit/test_risk_discovery_pipeline.py tests/unit/test_multi_datasource.py -q`
- Result after datasource health-report diagnostics: 39 passed, 5 known Pydantic deprecation warnings remain.
- `python -m py_compile core/adapter_audit.py bin/adapter_audit.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py`
- `pytest tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py -q`
- `python bin/adapter_audit.py --needs-work`
- Result after adapter readiness prioritization: 5 passed; P0 queue is QYYJT, public web search, and Telegram public-service connectors.
- `python -m py_compile adapters/public_web_search_tool.py tests/unit/test_public_web_search_tool.py`
- `pytest tests/unit/test_public_web_search_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py -q`
- Result after public-web dedupe hardening: 17 passed; `requires_deduplication` removed from the public-web-search connector risk flags.
- `python -m py_compile adapters/public_web_search_tool.py tests/unit/test_public_web_search_tool.py tests/unit/test_record_quality.py core/connector_registry.py tests/unit/test_connector_registry.py`
- `pytest tests/unit/test_public_web_search_tool.py tests/unit/test_record_quality.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after public-web URL fetcher handoff: 29 passed; `requires_fetcher` removed from the public-web-search connector risk flags.
- `pytest tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_public_web_search_tool.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after public-web live provider slot: 29 passed; public web search moved from P0 to P1 with only provider configuration remaining.
- `python -m py_compile adapters/qyyjt_tool.py tests/unit/test_qyyjt_tool.py adapters/qyyjt_adapter.py`
- `pytest tests/unit/test_qyyjt_tool.py tests/unit/test_qyyjt_adapter.py -q`
- Result after QYYJT authorization reporting: 11 passed; QYYJT can now report cookie validity, optional API smoke status, next action, and record quality.
- `python -m py_compile adapters/telegram_public_service_tool.py tests/unit/test_telegram_public_service_tool.py`
- `pytest tests/unit/test_telegram_public_service_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after Telegram live provider slot: 25 passed; Telegram public service can now call injected user-authorized providers and emit source-review metadata.
- `python -m py_compile adapters/public_web_search_tool.py tests/unit/test_public_web_search_tool.py`
- `pytest tests/unit/test_public_web_search_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_risk_discovery_pipeline.py -q`
- Result after public-web provider health reports: 34 passed; public web search now reports configured/missing providers and attempted empty-provider queries.
- `pytest tests/unit/test_multi_datasource.py tests/unit/test_auth_handlers.py tests/unit/test_adapter_audit.py tests/unit/test_connector_registry.py -q`
- Result after datasource template cleanup: 56 passed; default `adapters/multi_datasource/datasources.yaml` loads successfully and enables only the safe public smoke source by default.
- `pytest tests/unit/test_config.py -q`
- Result after config example cleanup: 30 passed; `config.example.yaml` parses and is covered by a no-real-secret test.
- `pytest tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_risk_discovery_cli.py -q`
- Result after risk-discovery execution-state hardening: 13 passed; not-executed, all-failed, no-evidence, evidence-found, and risk-events-found states are now distinguishable.
- `pytest tests/unit/test_qyyjt_tool.py tests/unit/test_qyyjt_adapter.py tests/unit/test_public_web_search_tool.py tests/unit/test_telegram_public_service_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_risk_discovery_cli.py tests/unit/test_record_quality.py -q`
- Result after graph export context-capsule hardening: 64 passed; graph payloads now include execution state, coverage, next actions, source routing alias, risk-event entity names/evidence refs, trimmed claims, omitted-claim counts, and context capsule diagnostics.
- `pytest tests/unit/test_intelligence_retrieval.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py -q`
- Result after structured risk-event ingestion: 23 passed; standardized connector records can now provide `risk_events`, `risk_category`, and `severity` directly instead of relying only on keyword detection.
- `pytest tests/unit/test_risk_event_store.py tests/unit/test_risk_monitor.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_engine.py -q`
- Result after recurring-event tracking: 34 passed; event store now exposes scan id, observed time, first/last seen, seen count, touched count, and non-resolution not-seen semantics.
- `pytest tests/unit/test_context_budget.py tests/unit/test_risk_graph_export.py tests/unit/test_engine.py -q`
- Result after context capsule cleanup: 21 passed; context capsule detection now recognizes English and Chinese source/risk markers instead of stale mojibake-only patterns.
- `pytest tests/unit/test_intelligence_retrieval.py tests/unit/test_context_budget.py tests/unit/test_risk_event_store.py tests/unit/test_risk_monitor.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_qyyjt_tool.py tests/unit/test_public_web_search_tool.py tests/unit/test_telegram_public_service_tool.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_record_quality.py -q`
- Result after the combined risk-discovery hardening pass: 82 passed, 5 known Pydantic deprecation warnings remain.
- `pytest tests/unit/test_source_admission.py tests/unit/test_qyyjt_tool.py tests/unit/test_telegram_public_service_tool.py tests/unit/test_connector_registry.py tests/unit/test_connector_audit_cli.py tests/unit/test_adapter_audit.py tests/unit/test_adapter_audit_cli.py tests/unit/test_public_web_search_tool.py -q`
- Result after datasource admission and default-on public entries: 71 passed.
- `pytest tests/unit/test_intelligence_retrieval.py tests/unit/test_context_budget.py tests/unit/test_risk_event_store.py tests/unit/test_risk_monitor.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_api_server.py tests/unit/test_record_quality.py -q`
- Regression after datasource admission and default-on public entries: 29 passed, 5 known Pydantic deprecation warnings remain.

## Wu Dehou role decision

Wu Dehou should not be reduced to flavor text or a prompt-only "harsh character".

His product role is:

- process supervisor,
- quality gate owner,
- evidence-chain enforcer,
- retry and downgrade trigger,
- low-quality output blocker,
- progress pressure surface.

His tone can stay high-pressure and internet-native, but the engineering behavior must be auditable: reject, retry, degrade, freeze, log, and expose why.

## Model proxy resilience

The current runtime may be connected through a model relay/proxy. Transient failures must not stop the workflow immediately.

Retryable examples:

- `Selected model is at capacity. Please try a different model.`
- timeout,
- connection reset/disconnect,
- HTTP 408/409/425/429,
- HTTP 500/502/503/504/520/522/524,
- temporary unavailable / rate limit / capacity wording.

The system should retry with capped exponential backoff, log a redacted error summary, and only degrade after retries are exhausted.

## Public vs private boundary

Public repo/portal:

- release-ready, bilingual, clean,
- open-source and free positioning,
- public or authorized data only,
- provenance, evidence chains, and compliance-friendly wording,
- no tokens, cookies, private endpoints, experimental gray-zone notes, or local-only operational traces.

Private/local repo:

- preserve working experimental routes and user-authored artifacts,
- optimize instead of deleting,
- keep connector experiments auditable,
- never commit secrets or browser cookies.

## Near-term milestones

### M1: supervision and reliability hardening

- Finish Wu Dehou supervision integration.
- Add checkpoint events at phase start/mid/end, not only pass/reject.
- Record retry attempts as supervision or metrics events.
- Add tests for transient model failures and degraded outputs.

### M2: retrieval-to-graph production path

- Done: formal discovery CLI can execute configured datasource YAML or offline fixture.
- Done: available-source routing and datasource diagnostics are exposed in discovery output.
- Done: datasource health reports expose routable status, endpoint, latency, and challenge handoff metadata for UI/plugin consumers.
- Done: standardized records ingest into evidence graph, risk events, risk store, and alert payloads.
- Done: public web-search and Telegram-style public service bridges normalize returned payloads into the same evidence contract.
- Done: public web-search bridge normalizes URLs, removes common tracking parameters, and deduplicates repeated hits before graph ingestion.
- Done: public web-search bridge supports URL-level fetch verification through approved provider callbacks or fixture content.
- Done: public web-search bridge supports injected live search providers and self-hosted SearXNG-style JSON search endpoints.
- Done: public web-search bridge exposes configuration-aware provider health reports for non-technical users.
- Done: QYYJT bridge exposes live authorization readiness reporting with optional API smoke diagnostics.
- Done: Telegram public-service bridge supports injected live providers and source-review readiness reports.
- Done: default multi-datasource config template is cleaned and tested as a default-safe, user-configurable endpoint/auth/provider entry.
- Done: root `config.example.yaml` is cleaned and tested as the user-facing local configuration template.
- Done: connector audit/readiness audit now exposes which bridges still need live provider, transport, source legitimacy, or production promotion.
- Done: compact graph/timeline export exists for Codex/plugin/portal consumers, reducing the need to ship full retrieval plans into every downstream context.
- Done: configurable datasource authentication handlers exist, including challenge detection metadata for UI/plugin provider handoff.
- Done: human-verification provider slot exists with default-safe disabled mode and browser/plugin handoff metadata.
- Done: standardized records now extract richer business entities from fields, raw payloads, explicit entity lists, and evidence text, including people, addresses, contacts, domains, cases, projects, and assets.
- Done: monitoring summaries now include event delta counts for new, recurring, and not-reproduced risk events without falsely treating absence as resolution.
- Done: standardized record quality audit exists for connector readiness checks, covering source identity, subject fields, URL/time provenance, evidence claims, and confidence ranges.
- Done: public web, Telegram public-service, and QYYJT tool bridges now return record-quality reports with their standardized records.
- Done: graph/timeline/delta contracts are documented for API and plugin-facing consumers.
- Done: adapter readiness audit now exposes quality-gate paths and tests for each connector.
- Done: adapter readiness audit now exposes readiness score and P0/P1/P2/P3 priority for next-work selection.
- Done: risk-discovery pipeline surfaces record-quality diagnostics for tool-provider search results.
- Done: graph/API diagnostics expose record-quality summaries directly for portal/plugin rendering.
- Done: risk-discovery pipeline now separates not executed, no available sources, all sources failed, no evidence found, evidence found, and risk events found, so plugins no longer confuse "did not run" with "no risk".
- Done: source diagnostics now carry query, objective, source hint, expected evidence, fanout entities, source profile, and source type where available.
- Done: graph export now ships plugin-friendly risk-event refs with entity names, evidence source/URL/access/authority, summary execution state, source-routing alias, and next actions.
- Done: graph export now trims large claim sets and exposes omitted-claim counts plus a compact context capsule to reduce downstream context explosion.
- Done: standardized connector records can now inject structured risk events with category, severity, title, rationale, confidence, and status into the evidence graph.
- Done: the risk-event ledger now tracks scan id, observed time, first seen, last seen, and seen count, so recurring risks become monitoring signals instead of duplicate rows.
- Done: context capsule compression has been cleaned to support English and Chinese source/risk markers, improving plugin payloads and downstream agent context cost.
- Done: deep subject profiles now aggregate identity, controller, contact, location, asset, behavior, relation-network, public-statement, and risk-event signals from the same evidence graph.
- Done: subject-profile recursion is defaulted to three hops and capped so public association expansion stays useful without context explosion.
- Next: audit every real adapter with the record-quality gate and promote only connectors with clear provenance/failure-mode tests.
- Next: promote connector status only after live/provider-specific quality reports are collected.

### M3: enterprise intelligence engines

- Deepen Financial Intelligence Engine beyond basic ratio analysis.
- Deepen Industry Intelligence Engine beyond market-size summaries.
- Add Product Intelligence Engine signals into risk discovery.
- Connect financial, industry, product, person, and capital signals into one risk timeline.
- Done: first reusable batch monitoring loop and CLI exist for company watchlists.
- Next: add scheduled re-check metadata, delta detection, and signal-triggered escalation.

### M4: Codex/plugin release track

- Keep four target variants visible: universal, Codex, Claude Code, WorkBuddy expert team.
- Maintain release gates for claims, security, and quality.
- Keep public portal at version `0.5.0` until the implementation actually supports the next claim set.
- Done: `.codex-plugin/plugin.json` is aligned to `v0.5.0`, public repo URLs, and current Enterprise Intelligence positioning.
- Done: `docs/PLUGIN_MARKET_READINESS.md` separates allowed claims from not-yet-allowed claims for submission review.
- Next: add repo-local marketplace packaging or install instructions only after the public portal/release copy is clean.

## Gaps still open

- Test coverage is not yet at the long-term target.
- Some older docs are mojibake or stale and should be replaced by clean current docs instead of patched in place.
- Observability is still thin: retry metrics, source health, graph ingestion counts, and supervision outcomes need dashboard surfaces.
- Real connector quality varies; each adapter needs health checks, schema mapping, and failure-mode tests.
- The system has a first batch monitoring loop and event delta summary, but still needs stronger continuous scheduling and signal-triggered analysis.

## Next recommended action

Continue hardening M2 and M3: real adapter audit, provenance completeness, entity/relation extraction, monitoring deltas, and signal-triggered escalation. The project already has enough agents and enough persona design. The next value comes from reliable evidence flow, graph/event modeling, and risk discovery.
