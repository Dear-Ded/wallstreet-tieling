# Search Integration Ledger

Scope: `wallstreet-tieling` current-release `0.5.0 Alpha`.

This document is the source-by-source record for the retrieval stack. It is the
canonical place to check what is wired, what is partial, and what still needs
live field mapping.

## Current Flow

company name -> retrieval plan -> source routing -> standardized records ->
evidence graph -> subject profile -> report -> quality gate

Current retrieval planning now includes explicit case-style deep dives for
upstream/downstream, suppliers, customers, dealers, procurement/sales partners,
industry sector, business model, competitive landscape, market share, product,
customer value, and profit model. These searches still obey the evidence
boundary: thin public hits remain leads until source-specific extraction,
entity matching, and corroboration make them report-admissible facts.

The report organization layer now includes the `曝光查案式调查` lens: money
tracks cash, financing, solvency, and operating activity; goods tracks product,
industry, upstream/downstream, customers, suppliers, partners, and
concentration; people tracks controllers, UBO/key people, relationship networks,
and legal/admin signals. This lens organizes the investigation output; it does
not replace source admission, entity resolution, or module-level evidence gates.
The static workbench renders this same `case_investigation_lens` in the brief
panel and fallback Markdown export.
The money track now has a dedicated `fund_flow_profile`, linking admitted
revenue, operating cash flow, financing events, bond pressure, and
asset/solvency pressure into the report-visible `资金流画像`.
The goods track now has a dedicated `goods_flow_profile`, linking admitted
product, industry, upstream/downstream, customer, supplier, partner,
concentration, value-chain, and pressure-point evidence into the report-visible
`货物流/生意链画像`.
The people track now has a dedicated `people_flow_profile`, linking admitted
controller, key-person, relationship-edge, control-path, and legal/admin
pressure evidence into the report-visible `人线/控制关系画像`.
RetrievalPlan seed tasks now carry `params.investigation_track` plus
`params.case_questions` for money, goods, and people tasks, preserving the
case-style investigation objective through connector execution and exports.
Public web extraction now emits conservative subject-specific capital and
key-person leads for financing, debt/credit, liquidity pressure,
pledged/frozen/auction pressure, and public role cues. Exact/strong public-web
capital leads can feed `operational_event_profile` and `fund_flow_profile` as
corroboration-needed rows; weak/review matches remain leads.

## What Is Wired

| Layer | Status | Current behavior | Gap |
|---|---|---|---|
| `PublicWebSearchTool` | ready | zero-config public search, provider health, URL-level verification, standardized record mapping, conservative subject-specific industry/product leads with explicit customer-value, SaaS/subscription, switching-cost, and value-chain-role cues; explicit supply-chain leads for customer, supplier, partner, upstream/downstream, and concentration statements; capital/key-person leads for financing, debt/credit, liquidity pressure, pledged/frozen/auction pressure, and public role cues when present | live provider quality still depends on the configured endpoint or provider; industry/product/supply-chain/capital/people extraction remains intentionally conservative |
| `DefaultOneClickSearchEngine` | ready | runs the zero-config default public-intel route without implicit official-public smoke initialization; explicit official-public smoke remains available for live validation | default public sources still depend on public access/provider quality |
| `RiskDiscoveryPipeline` | ready | schedules retrieval tasks, fanout, diagnostics, timeout handling, record ingestion, and timeout-budget propagation into compatible child sources; investigation packets aggregate recurring source/category/domain failure patterns into report-visible operator actions; source-resilience status and recommended recovery action now reach quality gate, one-click readiness, report Markdown, and API docs | source failures stay visible; coverage gaps remain explicit |
| `adapters.multi_datasource.SearchEngine` | ready | normalized connector routing, health checks, manual gates, retries, and auto-disable; SEC EDGAR submissions now emit structured key-person entities and exact CIK single-record match metadata; Wikidata EntityData emits key-person board-member and owner-of relationship entities | some portals remain manual-gate or user-authorized |
| `Official-public smoke` | ready | constrained live validation path for official/public sources | not a blanket live-parity guarantee |
| `QYYJTTool` + `QYYJTBenchmark` | partial | 45-module surface tracked; API/legacy vs query-plan vs fallback separated; field contracts and report admission enforced; report-critical modules emit module-level API payloads; admitted registry, controller, court/enforcement, administrative-penalty, relation, UBO/group-network, credit-profile, financial, financing, registry-change, negative-news, and research rows feed graph/report lanes; enterprise-credit rows now feed risk events, `enterprise_cognition.credit_profile`, and the report `信用画像` section; admitted `court_cases`, `dishonesty`, `limit_high`, `execution`, and `ent_penalty` rows now feed `enterprise_cognition.legal_administrative_profile` and the report `法务行政画像` section; admitted `ent_basic` rows render a report-visible registry snapshot; admitted `ent_financing`, `ent_change`, and `news_negative` rows feed `enterprise_cognition.operational_event_profile` and the report `经营事件画像` section; admitted tax, import/export, and recruiting rows feed `enterprise_cognition.commercial_activity_profile` and the report `经营活跃度画像` section; admitted `research` rows can feed industry/product cognition; evidence-backed customer, supplier, upstream/downstream, partner, value-chain-role, and concentration claims now feed `enterprise_cognition.supply_chain_profile` and the report `供应链与商业版图` section; admitted product, industry, and supply-chain facts now also feed `enterprise_cognition.goods_flow_profile` and the report `货物流/生意链画像`; admitted QYYJT API facts carry source URL, observed/retrieved time, confidence, and verification status in `report_admission`; controller candidates carry confidence tier, basis, match score, source strength, and control paths; weak `search_multi` subject candidates stay diagnostics and do not promote graph entities; query-plan rows remain evidence-ledger leads only and cannot create pattern-extracted domain entities, relationship edges, controller candidates, or structured risk events | broader live API field mapping still needed |
| `DevelopmentRequirementsBoard` | ready | `/api/requirements`, CLI `--requirements`, MCP `development_requirements`, and WorkBuddy expose executable P0/P1/P2/Future priority, completion, QYYJT current-version scope, next focus, and acceptance gates; current-release completion is `94%`, with evidence admission and controller/UBO subject-profile now at `98%`, release hygiene at `98%`, industry/product/supply-chain extraction at `95%`, runtime surface contracts at `94%`, and productized Word/HTML outputs at `24%` after field-contract/report-admission failures, source-specific public goods parsing, focused-test Windows temp/Python-spawn hardening, full acceptance refresh, DOCX official metadata/red-head/chart-panel polish, and subject-profile source-family provenance were wired into API docs and the release contract | board must be updated when a P0/P1/P2 lane materially changes |
| `CLI/API/MCP/workbench` | ready | `investigate_company`, `connector_catalog`, `development_requirements`, static workbench, and API routes expose the same retrieval and priority surface; connector catalog includes `data_effectiveness` so UI/plugins can distinguish fact-capable sources, lead-only sources, authorization-gated fact sources, analysis outputs, and current limitations; Node CLI forwards explicit `--store` paths for one-click investigations; packaged Codex MCP smoke uses an isolated writable risk-event store; API docs now declare one-click source-resilience and relationship-graph readiness fields; the static workbench renders investigation `persona_surface`, quality, evidence, graph preview, money/goods/people fallback profiles, QYYJT queue, and release metadata | UI is a surface, not a separate retrieval engine |
| `China domestic advanced sources` | ready | `connector_catalog` now exposes `enterprise_tax_credit_public_records`, `enterprise_judicial_asset_public_records`, `enterprise_mofcom_overseas_investment_public_records`, `enterprise_baidu_aiqicha_public_aggregation`, and `enterprise_shuidi_credit_public_aggregation` as explicit-only advanced connectors mapped to the existing `adapters.china_domestic_sources` runtime gates | default one-click remains unchanged; report facts still require user authorization, provenance, exact/strong entity match, and admission review |
| `RetrievalPlan` / `SearchTask` / `RiskDiscoveryPipeline` | ready | search tasks export `retrieval_layer`; seed execution runs entity-anchor, overview, prioritized drill-down, then specialist batches; money/goods/people case tasks export `params.investigation_track` and `params.case_questions`; diagnostics and connector params carry the layer plus `result_limit`, `source_budget`, and `per_source_result_limit`; default public-intel uses the layer to keep anchor/overview fan-out narrow and maps budgets into public-web `max_results` plus QYYJT module scopes | provider-specific parsers can still honor `per_source_result_limit` and case-track params more deeply where it improves latency or report coverage |

Recent QYYJT bridge:

- Admitted city-investment, region-code, region-economy, and region-debt rows
  now feed `enterprise_cognition.regional_credit_profile`, structured
  financing-capital risk events, and a report-visible regional/city-investment
  credit section.
- Admitted court-announcement, merger/restructuring, and bond-calendar rows now
  feed `enterprise_cognition.legal_administrative_profile`,
  `enterprise_cognition.operational_event_profile`,
  `enterprise_cognition.bond_credit_profile`, relationship-network edges, and
  report-visible cognition sections.
- QYYJT public-origin fallback diagnostics now include the target module record
  type, required fields, admission gate, and acceptance gate, and the same
  contract is visible in report Markdown next actions.
- RIX-001 expanded public-web case-style extraction for conservative
  money/goods/people leads: major investment, refinancing, capital structure,
  market share, business model, revenue model, sales channel, founder/CFO/CTO
  and Chinese role/supply-chain patterns. Codex review removed an empty
  supply-chain claim regression and preserved the lead-only boundary.

## Source Classes

- Public web search: zero-config and provider-based public search.
- Official/public APIs: GLEIF, SEC, OFAC, UN, and Wikidata.
- Manual-gate official portals: health is tracked, but live automation is not treated as production health.
- QYYJT: admitted field-complete payloads become graph/report facts; query-plan rows and weak subject-resolution candidates remain leads/diagnostics and are filtered out of graph facts, relation edges, risk events, and controller candidates.
- China domestic advanced sources: tax-credit, judicial asset/bankruptcy, MOFCOM overseas investment, Aiqicha, and Shuidi adapters are visible in `connector_catalog` as explicit-only advanced connectors; they do not run in the default one-click lane until authorized and admitted.

## Known Gaps

- QYYJT live/API field mapping beyond the admitted P0 graph/report bridge and module-level payload bridge for report-critical rows.
- Broader live/public industry, product, supply-chain, customer/supplier, and competitive-position extraction; supply-chain and source-specific public goods-economics pages now have public-web extraction and report paths but still need broader corroboration and non-English template coverage.
- More fact-capable source depth: the new capability matrix exposes breadth, but deeper parser coverage and cross-source corroboration are still required.
- Cleaner transient source-failure handling in report tails.
- Runtime state stores now have explicit env/config overrides and writable temp fallback for restricted execution environments.
- Broader controller/UBO source-specific live field aliases and conflict-resolution precedence beyond the current registry, GLEIF, SEC, QYYJT, Wikidata, and graph-level confidence model.
- Provider-specific parsers can still honor `per_source_result_limit` more deeply where it improves latency or report coverage.
- Requirement board maintenance when current P0/P1 completion changes.

## Verification Snapshot

- `npm run acceptance`: `799 passed, 9 skipped` on 2026-07-06 08:24 Asia/Shanghai, plugin validation passed, API smoke passed including `/api/release-preflight`, Apple Inc. default one-click acceptance passed, terminology guard public-copy hygiene passed with `0 findings`, `npm run release:privacy-scan` scanned the npm package payload with `0 findings`, `npm run release:preflight` returned `ready_for_local_packaging`, `npm run delivery:audit` is now a mandatory go/no-go gate returning `pass`, `npm run objective:audit` is now the active-goal completion gate, and the run covered REST API smoke, packaged Codex MCP smoke with retrieval-plan coverage, host-neutral desktop-agent smoke, Codex primary delivery lane and WorkBuddy secondary branch priority, connector_catalog source_strengthening_queue, official China source strengthening implementation_pack, OpenSanctions and IDB public dataset source strengthening implementation_pack, agent_tool_adapters first_run_recipe preserves source_strengthening_queue, source_strengthening risk_enforcement lane routing, source_strengthening execution_plan agent handoff, WorkBuddy investigate_company host smoke, host-smoke Python runtime resolution, release_preflight package go/no-go gate, delivery_audit go/no-go gate, objective_audit active-goal completion gate, package privacy scan gate, runtime handoff contracts, aggregate_subject CLI/API/MCP release surface, npm package dry-run content gate, source-resilience retry policy, source recovery execution queue, source_resilience agent_autorun, QYYJT public-origin agent_autorun, capital risk and relationship autorun routes, report_artifact_agent_autorun, control-path verification/source-family handoff, capital source-family handoff, controller source-family provenance, report-admission contract enforcement, QYYJT public-origin work orders, relationship graph audit handoff gating, API contract visibility, DOCX native Word table rendering/local-image embedding, DOCX official metadata/red-head/chart-panel polish, DOCX source provenance appendix/evidence source index output, executable agent-handoff routing, report_exports.agent_decision_digest packet routing, directory bundle verifier_output_fields handoff, directory bundle verification_recipe handoff, latest_acceptance_evidence release handoff, decision_digest handoff, bundle_integrity handoff, delivery checklist handoff, portable HTML checklist rendering, manifest file_manifest/agent_summary, manifest agent_summary deep drift verification, executable report-bundle verifier with tamper and handoff-schema detection, API smoke manifest-field gating, Node fallback export-dir manifest contract alignment, focused-test Windows temp/Python-spawn hardening, source-specific public goods parsing, package privacy scan Windows cache cleanup hardening, relationship-edge admission preservation, controller-conflict audit details, and capability-audit blocker classification hardening.
- Post-acceptance focused regression on 2026-07-05 21:24 Asia/Shanghai: `223 passed, 2 skipped` across runtime-deep, Telegram, autonomous-source, connector-registry, release-variant, API, investigation-export, and WorkBuddy tests. The run proves the source-strengthening queue can be empty after all connector contracts are strengthened while `summary.source_strengthening.candidate_count`, Codex/API smokes, agent-handoff completion status, and bundle verifier semantics stay aligned.
- focused evidence-admission contract regression after wiring report_admission into EvidenceGraph and the investigation evidence ledger: `156 passed` for investigation packet and intelligence retrieval suites; QYYJT report-admission focused set also passed.
- focused controller/UBO source-family regression after exposing source families on subject-profile controller candidates, control-path summaries, relationship edges, API docs, and release-contract runtime surfaces: `38 passed`.
- focused public-web source-specific goods regression after routing industry-report market size, pricing power, peer comparison, CAC/LTV, revenue model, moat, competitor set, and capacity-cycle signals into public_goods_profile plus goods-flow report lanes: `3 passed`.
- default focused regression after pytest tmp_path/asyncio hardening, resolved Python propagation to Node CLI tests, and Node CLI offline/read-only fallback for Python child-process EPERM: `406 passed`.
- focused control-path/source-recovery handoff regression: CLI directory bundle, API docs, release contract, REST smoke, Codex MCP smoke, and host-neutral agent smoke passed after adding `agent-handoff.json` source recovery and control-path verification queues.
- focused public-web/investigation regression after adding public capital/key-person leads and fund-flow admission: `50 passed`
- focused investigation regression after adding people-flow report cognition: `23 passed`
- focused public-web/default-public-intel/investigation regression after adding public supply-chain lead extraction: `55 passed`
- focused encoding/investigation/public-web/default-public-intel regression after adding structured workbench lens rendering: `63 passed`
- focused investigation/public-web/default-public-intel/requirements regression after adding the money/goods/people `曝光查案式调查` lens: `59 passed`
- focused investigation/retrieval/requirements regression after adding supply-chain/business-map report cognition: `52 passed`
- focused evidence-admission/QYYJT/subject-profile/investigation regression after sealing query-plan leads from graph facts: `87 passed`; Apple Inc. default one-click compact check reports `Factual=0`, `Leads=5`, `TopEdges=0`
- focused QYYJT commercial-activity/report regression: `45 passed`
- focused QYYJT/connector/investigation/release regression after regional-credit profile bridge: `73 passed`
- focused QYYJT/investigation/requirements regression after court-announcement, merger/restructuring, and bond-calendar bridge: `54 passed`
- focused public-web/default-public-intel/investigation/requirements/release-hygiene regression after RIX-001 review patch: `90 passed`
- focused retrieval-layer budget/default-public-intel/pipeline regression: `47 passed`
- focused Wikidata/subject-profile/intelligence regression after board-member and owner-of extraction: `103 passed`
- focused SEC/subject-profile/intelligence/requirements regression after structured key-person admission: `105 passed`
- focused retrieval-layer/pipeline regression: `40 passed`
- focused default-public-intel/retrieval-layer regression: `46 passed`
- focused retrieval-layer/default-public-intel/pipeline/API/CLI/WorkBuddy regression: `97 passed`
- focused QYYJT/current-board regression after financing/change/news/research bridge: `26 passed`
- focused API/WorkBuddy/investigation/record-quality regression after queue expansion: `50 passed`
- focused public-web/default-intel/investigation regression after industry/product bridge: `48 passed`
- broader requirements/QYYJT/search/API/WorkBuddy/investigation/release/encoding/hygiene regression: `111 passed`
- focused QYYJT provenance/record-quality regression: `25 passed`
- focused QYYJT legal/admin profile regression: `21 passed`
- focused investigation/quality/requirements regression: `26 passed`
- focused P0 QYYJT/API/subject-profile regression: `76 passed`
- focused requirements/QYYJT/API/WorkBuddy regression: `50 passed`
- focused QYYJT/report-quality regression: `42 passed`
- packaged Codex MCP smoke now covers `development_requirements` and `retrieval_plan`
- focused QYYJT/search/investigation regressions: `67 passed`
- focused QYYJT quality regressions: `19 passed`
- focused QYYJT/subject-profile/intelligence/investigation controller-fusion regressions: `69 passed`
- focused QYYJT/quality/intelligence regressions: `43 passed`
- static encoding/workbench persona-surface regression: `8 passed`
- static workbench browser check: desktop and mobile loaded on `127.0.0.1:4187`, expert-team block visible, no mobile horizontal overflow; temporary server closed
