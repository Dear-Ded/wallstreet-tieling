#!/usr/bin/env python3
"""Executable development requirement levels for the current release."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .qyyjt_benchmark import build_qyyjt_benchmark


VERSION = "0.5.0"
CURRENT_RELEASE = "0.5.0 Alpha"
LEVEL_ORDER = {"P0": 0, "P1": 1, "P2": 2, "Future": 3}
LEVEL_WEIGHTS = {"P0": 5, "P1": 3, "P2": 1}


@dataclass(frozen=True)
class DevelopmentRequirement:
    id: str
    level: str
    title: str
    lane: str
    status: str
    completion_percent: int
    current_version_scope: bool
    user_goal: str
    implemented: tuple[str, ...]
    gaps: tuple[str, ...]
    next_actions: tuple[str, ...]
    acceptance_gates: tuple[str, ...]
    runtime_surfaces: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "lane": self.lane,
            "status": self.status,
            "completion_percent": self.completion_percent,
            "current_version_scope": self.current_version_scope,
            "user_goal": self.user_goal,
            "implemented": list(self.implemented),
            "gaps": list(self.gaps),
            "next_actions": list(self.next_actions),
            "acceptance_gates": list(self.acceptance_gates),
            "runtime_surfaces": list(self.runtime_surfaces),
            "tags": list(self.tags),
        }


def build_development_requirements_board() -> dict[str, Any]:
    """Return the current machine-readable development priority board."""
    qyyjt = build_qyyjt_benchmark()
    items = _requirements(qyyjt)
    current_items = [item for item in items if item.current_version_scope]

    return {
        "type": "development_requirements_board",
        "version": VERSION,
        "release": CURRENT_RELEASE,
        "completion_percent": _weighted_completion(current_items),
        "summary": {
            "current_release_completion_percent": _weighted_completion(current_items),
            "total_items": len(items),
            "current_scope_items": len(current_items),
            "by_level": _count_by(items, "level"),
            "by_status": _count_by(items, "status"),
            "p0_open_count": sum(1 for item in current_items if item.level == "P0" and item.status != "done"),
            "release_decision": "not_final_release_ready",
            "next_major_gate": "finish open P0 requirements, then run full acceptance and live/public smoke",
        },
        "level_policy": {
            "P0": "Current-release blocker. If open, the product is not final-release ready.",
            "P1": "Current-release value amplifier. It should improve breadth, reliability, or user value after P0 is stable.",
            "P2": "Polish, docs, or surface work. It cannot outrank evidence, retrieval, report quality, or release gates.",
            "Future": "Explicitly parked outside this version. Do not spend current-release capacity here unless re-scoped.",
        },
        "scope_rules": {
            "current_release": CURRENT_RELEASE,
            "continuous_monitoring": "future_version_not_current_release",
            "public_data_boundary": "public, licensed, or user-authorized evidence only; weak leads never become facts",
            "ui_work_rule": "UI work is P2 unless it changes the executable investigation output or release gate.",
            "qyyjt_rule": "QYYJT parity is current-version P0/P1 work; every module must stay tracked with an acceptance gate.",
        },
        "qyyjt_current_version": _qyyjt_requirement_snapshot(qyyjt),
        "next_focus": _next_focus(current_items),
        "acceptance_gates": _acceptance_gates(current_items),
        "requirements": [item.to_dict() for item in items],
    }


def _requirements(qyyjt: dict[str, Any]) -> list[DevelopmentRequirement]:
    qyyjt_summary = qyyjt["summary"]
    surface = qyyjt_summary["surface_profile"]
    p0_queue_count = int(qyyjt_summary.get("p0_queue_count") or 0)
    module_count = int(qyyjt_summary.get("module_count") or 0)
    api_modules = int(surface.get("concrete_api_or_legacy_modules") or 0)
    query_plan_modules = int(surface.get("rich_query_plan_modules") or 0)

    return [
        DevelopmentRequirement(
            id="P0.ONE_CLICK_PRODUCT_LOOP",
            level="P0",
            title="Vertical one-click enterprise intelligence loop",
            lane="one_click_product",
            status="in_progress",
            completion_percent=92,
            current_version_scope=True,
            user_goal="Enter a company and receive a useful evidence-backed investigation packet, not a pile of raw source output.",
            implemented=(
                "CLI/API/MCP one-click investigation packet is executable.",
                "Evidence ledger, graph preview, quality gate, report Markdown, and public/fixture/live modes are wired.",
                "Default public route can produce a packet and expose coverage gaps without pretending gaps are low risk.",
                "Report Markdown now renders run/source failure diagnostics so source failures are visible in the same artifact.",
                "Packet JSON and Markdown now expose one_click_readiness with fact/lead counts, quality status, recovery counts, and loop-section checks.",
                "One-click readiness now exposes coverage execution, coverage-gap count/severity/attempt ratio/next action, public-origin fallback actions, relationship-candidate execution steps, unresolved capital-pressure relationship status, and source resilience without requiring agents to inspect diagnostics.",
                "Investigation packets now include report_exports for Markdown, full JSON packet, and portable printable HTML; red-head docx and premium HTML remain P2 output targets.",
            ),
            gaps=(
                "Live public sources can still miss product and hard risk-event facts for some companies.",
                "Report cognition still needs broader real-company product/risk facts from additional source-specific parsers.",
            ),
            next_actions=(
                "Run one China-style fixture case and one live/public Apple-style case after retrieval changes.",
                "Patch the weakest packet section observed in actual output before widening scope.",
            ),
            acceptance_gates=(
                "bin/investigate.py returns type=investigation_packet with evidence_ledger and report_markdown.",
                "Quality gate distinguishes ready_for_human_review, usable_with_warnings, incomplete_coverage, and source_failure.",
                "Default route must not return all_sources_failed for the acceptance company.",
                "Report Markdown includes a One-click Product Loop section before key findings.",
            ),
            runtime_surfaces=("bin/investigate.py", "/api/investigate", "investigate_company MCP", "skill/agent packet"),
            tags=("investigation", "report", "quality_gate"),
        ),
        DevelopmentRequirement(
            id="P0.QYYJT_CURRENT_VERSION_PARITY",
            level="P0",
            title="Enterprise Warning QYYJT current-version parity",
            lane="information_retrieval",
            status="in_progress",
            completion_percent=94,
            current_version_scope=True,
            user_goal="Track and close QYYJT module coverage as a benchmark, with facts admitted only when source and fields are good enough.",
            implemented=(
                f"{module_count} QYYJT modules are tracked in the runtime benchmark.",
                f"{api_modules} concrete API or legacy modules and {query_plan_modules} rich query-plan modules are separated.",
                f"{p0_queue_count} current-version P0 work items expose done_when, next_action, and acceptance_gate.",
                "Admitted registry, legal, penalty, controller, UBO/group, credit, and financial payloads can feed graph/report lanes.",
                "Enterprise-credit rows now reach risk events, enterprise cognition, and report-visible credit profile output.",
                "Court, dishonesty, limit-high, enforcement, and administrative-penalty rows now feed a report-visible legal/admin cognition profile.",
                "Enterprise-basic rows now feed a report-visible registry snapshot with legal name, identifier, status, capital, address, representative, dates, authority, type, and business scope.",
                "Financing, registry-change, and negative-news rows now feed a report-visible operational-event profile instead of only risk-event rows.",
                "Admitted QYYJT API facts now carry common provenance: source URL, observed/retrieved time, confidence, and verification status.",
                "QYYJT field_contracts are now available for all 45 modules, not only the P0 queue, so the tool bridge can use non-P0 contracts instead of falling back to generic payload rows.",
                "Domain-depth and supplemental modules now have concrete contracts for bond profile/rating/issue/default, pledge, freeze, auction, land, tax, import/export, patent, trademark, copyright, and recruiting records.",
                "Admitted bond-default, equity-pledge, and IP-asset payloads now produce structured graph entities or risk events instead of remaining generic leads.",
                "Admitted bond, asset/solvency, and IP payloads now feed dedicated enterprise cognition profiles and report sections.",
                "Admitted tax, import/export, and recruiting payloads now feed a commercial-activity cognition profile and report-visible operating-activity section.",
                "Admitted city-investment, region-code, region-economy, and region-debt payloads now feed a regional-credit cognition profile, structured financing-capital risk events, and a report-visible regional/city-investment credit section.",
                "Admitted court-announcement, merger/restructuring, and bond-calendar payloads now feed legal/admin, operational-event, bond-credit, relationship-network, and report-visible cognition sections.",
                "Admitted financial-institution counterparty (fin_inst) payloads now feed relationship-network edges, risk events, fund-flow cognition, capital-pressure summaries, and report-visible counterparty rows with role, credit-line, guarantee, regulatory, license, and risk fields when field contract and provenance gates pass.",
                "Admitted financing-event, bond, pledge, freeze, and auction-style capital payloads now emit relationship edges so capital pressure can connect to counterparties, bond assets, pledgees, and court asset actions.",
                "All 45 QYYJT field-contract record types now have a structured bridge; watchlist and alert-push modules remain visible as lead-only follow-up work rather than verified facts.",
                "QYYJT public-origin fallback diagnostics now carry module field contracts, required fields, record type, admission gate, and acceptance gate into JSON next actions and report Markdown.",
            ),
            gaps=(
                "Some non-P0 contracts still need broader fixture coverage and live-authorized smoke evidence.",
                "Broader live/API field mapping is still needed before all non-P0 modules can be treated as production-depth parity.",
            ),
            next_actions=(
                "Broaden fixture-backed mapping for the next highest-value non-P0 modules that materially improve legal, solvency, industry, or relationship report sections.",
                "Add live-authorized smoke evidence before treating any new module as production-depth parity.",
            ),
            acceptance_gates=(
                "QYYJT rows expose field_contract, report_admission, evidence_role, and acceptance_gate.",
                "Weak or query-plan QYYJT leads never promote graph facts or controller candidates.",
                "Current P0 modules have standardized records with source URL or provenance when admitted.",
                "QYYJT public-origin fallback rows expose required fields and admission gates before an agent can treat follow-up results as report evidence.",
            ),
            runtime_surfaces=("ConnectorRegistry.product_catalog", "/api/connectors", "--connectors", "connector_catalog MCP"),
            tags=("qyyjt", "enterprise_warning", "retrieval", "current_release"),
        ),
        DevelopmentRequirement(
            id="P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION",
            level="P0",
            title="Evidence admission and entity-resolution integrity",
            lane="evidence_graph",
            status="in_progress",
            completion_percent=92,
            current_version_scope=True,
            user_goal="Keep facts, leads, subject matches, and weak lookalikes separate so the report is trustworthy.",
            implemented=(
                "Standardized records carry source profile, evidence type, entity_match, field_contract, and QYYJT module metadata.",
                "Licensed/user-authorized evidence can be verified when confidence and field gates pass.",
                "Weak subject-resolution candidates are counted as weak matches instead of promoted facts.",
                "Registry identifiers now normalize common aliases such as `creditCode`, `unifiedSocialCreditCode`, and `regNo` into entity-resolution evidence and graph attributes.",
                "GLEIF parent relationship entities are extracted only through subject-matched records, preserving the existing rule that review-level registry candidates cannot attach related entities to the seed subject.",
                "SEC CIK/submissions records now emit source-specific exact match metadata when the official single-company record matches an expanded investigation query.",
                "Exact/strong provider entity_match metadata now allows explicit structured entities through the admission gate while weak/review matches remain blocked.",
                "Wikidata EntityData exact/strong matches now admit deeper structured relationship entities such as board members and owner-of company links while preserving weak/review blocking.",
                "Query-plan and rich-query-plan records now stay evidence-ledger leads only: they cannot promote candidate entities, pattern-extracted domains, structured relations, subject-profile signals, controller candidates, risk events, or packet evidence classification into graph facts.",
                "Subject-profile relationship graph edges now preserve admission, source_names, and numeric source_strength derived from bound evidence instead of dropping graph audit semantics.",
            ),
            gaps=(
                "More source-specific exact/strong matching rules are still needed for future licensed feeds and less-structured public sources.",
                "Some older adapters still need full field-contract admission semantics.",
            ),
            next_actions=(
                "Add source-specific match/admission tests whenever a connector becomes default-on or report-admissible.",
                "Keep query-plan and weak-match regression tests in the acceptance path.",
            ),
            acceptance_gates=(
                "Weak entity_match levels do not create graph entities.",
                "Query-plan and rich-query-plan records remain leads and cannot generate entities, relations, controller candidates, subject-profile signals, risk events, or evidence-classified packet rows by themselves.",
                "Evidence export preserves source, access, authority, confidence, and match basis.",
                "Subject-profile relationship graph edges preserve evidence-derived admission and source-strength metadata.",
            ),
            runtime_surfaces=("RiskDiscoveryPipeline", "EvidenceGraph", "subject_profile", "investigation packet"),
            tags=("evidence", "entity_resolution", "provenance"),
        ),
        DevelopmentRequirement(
            id="P0.CONTROLLER_UBO_SUBJECT_PROFILE",
            level="P0",
            title="Controller, UBO, and subject-profile fusion",
            lane="subject_profile",
            status="in_progress",
            completion_percent=93,
            current_version_scope=True,
            user_goal="Explain who controls the company and why the system believes it, with paths and confidence.",
            implemented=(
                "Controller candidates carry confidence_tier, confidence_basis, source_strength, match_score, and control_paths.",
                "QYYJT related, UBO, and group payloads emit relationship edges instead of flat notes.",
                "Licensed/authorized controller facts outrank weak public leads.",
                "QYYJT enterprise-basic legal representatives now enter the key-person candidate lane with explicit `legal_representative` basis instead of being lost as a generic person entity.",
                "Generic registry fields now preserve specific relationship types for actual controller, legal representative, shareholder, director, supervisor, manager, and executive instead of collapsing them into one generic role lead.",
                "Generic registry ingestion now recognizes more UBO/controller aliases such as actualControllerName, beneficialOwnerName, ultimateBeneficialOwner, shareholderName, and shareRatio.",
                "Controller candidates preserve ownership ratio, layer depth, confidence basis, and list-style control paths as readable path evidence.",
                "QYYJT UBO/controller field aliases now include controlChain, holdingRatio, legalRepName, and sourceBasis-style payloads.",
                "GLEIF LEI formatter now extracts direct/ultimate-parent relationship records into standardized company entities and subject-profile relationship edges.",
                "SEC submissions formatter now maps structured officers, executives, directors, insiders, and key-people fields into source-backed person relations.",
                "SEC official key-person relations now flow into controller_candidates and suppress the control/ownership evidence gap without being presented as UBO facts.",
                "Wikidata EntityData now extracts board-member and owner-of relationships; board members enter key-person candidates and owner-of companies enter the relationship graph.",
                "Verified controller conflicts from the people lane now reach the quality gate as explicit review warnings, while verified facts with competing public leads remain review-only instead of being promoted to equal facts.",
                "Controller conflict summaries now choose the preferred controller by verified tier, source strength, source count, and confidence instead of input order.",
                "Quality gate now treats fact/admitted/evidence relationship edges with evidence_ids as auditable strengths, while weak or evidence-less edges remain review warnings.",
            ),
            gaps=(
                "Broader live-source controller/UBO mapping remains incomplete for additional indirect ownership variants and conflict-resolution precedence across more source families.",
                "Recursive key-person follow-up remains bounded and conservative.",
            ),
            next_actions=(
                "Add more case fixtures for indirect ownership variants and source-family precedence when controller claims conflict.",
                "Tune recursive key-person follow-up only when it improves the one-click report without increasing false facts.",
            ),
            acceptance_gates=(
                "Controller candidates exclude query-plan and weak evidence.",
                "Report renders control path, tier, and basis.",
                "Relationship graph includes evidence-backed relation edges.",
                "Quality gate warns when verified controller or UBO claims conflict.",
                "Quality gate warns when relationship graph edges lack fact admission or evidence_ids.",
            ),
            runtime_surfaces=("core/subject_profile.py", "core/investigation.py", "report Markdown"),
            tags=("ubo", "controller", "subject_profile"),
        ),
        DevelopmentRequirement(
            id="P0.REPORT_VALUE_COGNITION",
            level="P0",
            title="User-readable report value and enterprise cognition",
            lane="reporting",
            status="in_progress",
            completion_percent=95,
            current_version_scope=True,
            user_goal="The final report should tell a non-technical user what matters, what is known, what is missing, and what to do next.",
            implemented=(
                "Report includes quality, provenance, risk ledger, relationship graph, registry snapshot, financial, credit, legal/admin, operational-event, industry, product, and persona sections.",
                "Source-backed claims feed enterprise cognition instead of only dumping raw JSON.",
                "Evidence-backed customer, supplier, upstream/downstream, partner, value-chain-role, and concentration signals now render as a report-visible supply-chain/business-map section.",
                "Report JSON and Markdown now expose the `扒光查案式调查` lens, organizing deep-dive work into money, goods, and people tracks without narrowing the broader investigation scope.",
                "Static workbench now surfaces the same `case_investigation_lens` in the brief panel and fallback Markdown export, so the money/goods/people tracks are not only hidden inside report text.",
                "Quality gate now warns on single-source supply-chain profiles and records a strength only when supply-chain claims have multi-source support.",
                "Report JSON and Markdown now expose a `fund_flow_profile` that links revenue, operating cash flow, financing events, bond pressure, and asset/solvency pressure into the money-in/money-out track.",
                "Report JSON and Markdown now expose a `capital_pressure_profile` that summarizes admitted financing, credit, bond, asset-solvency, financial-counterparty, and public capital leads into a pressure level, source basis, and next verification questions.",
                "Report JSON and Markdown now expose a `capital_relationship_profile` that links admitted capital-pressure rows to admitted relationship-network edges without promoting weak leads.",
                "Report JSON, Markdown, static workbench brief, and fallback export now expose a `goods_flow_profile` that connects products, industry position, upstream/downstream, customers, suppliers, partners, concentration, and pressure points into the goods-in/goods-out track.",
                "The goods-flow profile now consumes public_goods_profile market, business-model, product, customer, supplier, and channel leads as corroboration-needed public signals instead of leaving them only in the separate public-lead bucket.",
                "Report JSON, Markdown, static workbench brief, and fallback export now expose a `people_flow_profile` that connects controllers, key people, relationship edges, control paths, legal/admin pressure, and next questions into the who-controls/who-acts-together track.",
                "Current report explicitly parks continuous monitoring as later-version scope.",
                "Report now renders dedicated bond credit, asset/solvency, and IP/technology sections when QYYJT domain-depth evidence is admitted.",
                "Fixture-backed report output now deduplicates repeated controller path previews before presenting control/ownership hypotheses and Markdown control-path rows.",
                "Apple-style default one-click output now downgrades clean-sounding no-risk verdicts to insufficient-data when the quality gate is blocked and only lead evidence is present.",
                "Relationship-network top edges now deduplicate repeated from/to/relation rows before report rendering.",
                "Report Markdown now surfaces blocked recovery execution preview rows with source, status, domain, and priority so coverage gaps become concrete follow-up work instead of hidden counters.",
                "Quality gate now consumes coverage_recovery_decision: ready recovery steps become non-penalizing strengths plus next actions, while blocked recovery steps remain explicit warnings and next actions.",
                "Cross-lane investigation questions now carry priority, business impact, and concrete next_step fields, sorted so P0 cash-flow, solvency, and control risks appear before lower-impact exploration.",
                "Report Markdown now surfaces one-click readiness status, evidence counts, recovery counts, and missing loop checks in the product-facing artifact.",
                "One-click readiness and report Markdown now expose capital pressure level, verification status, public-lead-only marker, and capital relationship closure state.",
                "Relationship-network report rows now include edge admission and evidence IDs so graph claims are auditable from the human report, not only from raw JSON.",
                "One-click readiness and report loop now expose relationship graph edge counts, evidence-backed edge counts, auditable fact edge counts, missing evidence counts, and lead-only edge counts.",
            ),
            gaps=(
                "Industry/product extraction is still thin when public sources provide only generic descriptions.",
                "Next-question recommendations still need more real-company tuning after live/public packet review.",
            ),
            next_actions=(
                "Continue tightening missing-data explanations and source-failure copy from actual packet output.",
                "Make missing-data explanations short, concrete, and action-oriented.",
            ),
            acceptance_gates=(
                "Report Markdown and JSON packet agree on quality, evidence, risk, controller, cognition, and gaps.",
                "Report never claims continuous monitoring as a current-version feature.",
                "Lead-only facts are labeled as leads in user-facing text.",
                "Recovery execution queues show both ready queries and blocked preview rows when connector/admission work prevents execution.",
                "Quality gate next_actions include the selected ready or blocked coverage-recovery decision.",
                "Cross-lane questions expose priority, business_impact, and next_step fields in deterministic order.",
                "One-click readiness reports capital pressure verification state and whether capital pressure is still public-lead-only.",
                "Relationship-network report rows include admission state and evidence identifiers for top edges.",
            ),
            runtime_surfaces=("investigation_packet", "report_markdown", "static workbench", "static export"),
            tags=("report", "enterprise_cognition", "non_technical_user"),
        ),
        DevelopmentRequirement(
            id="P0.RELEASE_ACCEPTANCE_HYGIENE",
            level="P0",
            title="Release acceptance and public-package hygiene",
            lane="release",
            status="in_progress",
            completion_percent=95,
            current_version_scope=True,
            user_goal="The package must pass acceptance and not ship secrets, private state, or misleading release claims.",
            implemented=(
                "Acceptance script runs focused Python tests, plugin validator, terminology guard, syntax checks, MCP smoke, and one-click smoke.",
                "Release, connector, and persona contracts are exposed at runtime.",
                "Public-data boundary and packaging file list are explicit.",
                "Node CLI now forwards `--store`, and packaged Codex MCP smoke uses an isolated writable risk-event store instead of relying on user-home write access.",
                "Runtime state paths now support explicit env/config overrides and writable temp fallback for risk-event, monitor-run, and memory stores.",
                "Acceptance now includes storage-path regression tests so restricted execution environments do not silently break local state.",
                "Acceptance now redirects TEMP, state, and pytest cache paths to a writable acceptance state directory with per-run TEMP subdirectories, avoiding protected install-directory and stale pytest temp permission noise.",
                "`npm run test:focused` now uses the same writable state/cache policy and a fresh TEMP subdirectory for focused regression runs.",
                "Release hygiene now retries `git ls-files` on transient Windows page-file pressure (`WinError 1455`) before treating it as a real failure.",
                "Package variant tests now ensure every local `tools/*` script referenced by npm scripts exists and is included in the npm package file whitelist.",
                "Adapter audit now infers datasource tiers from connector metadata so official-public connectors are not blocked by unknown_source_tier, while user-authorized deep sources remain review-gated and default-off.",
                "Latest full acceptance passed with 721 Python tests, 9 skipped tests, plugin validation, and Apple Inc. default one-click acceptance after source-resilience readiness, relationship-graph auditability, and relationship-edge admission preservation.",
                "API index/docs and plugin prompts now describe monitor execution as explicit baseline re-checks, keeping continuous monitoring in later-version scope.",
            ),
            gaps=(
                "Full acceptance must continue to be rerun after each current P0 change.",
                "Docs and public portal wording need final truth alignment before public release claims.",
            ),
            next_actions=(
                "Run focused tests for changed lanes, then full npm run acceptance with extended timeout.",
                "Update taskboard and search ledger only after tests pass.",
            ),
            acceptance_gates=(
                "npm run acceptance passes with configured Python and Node runtimes.",
                "Plugin validator passes.",
                "No secrets, cookies, private databases, or overclaims are shipped.",
                "Adapter audit distinguishes official-public, public-web, licensed, and user-authorized tiers without promoting review-only deep sources.",
                "NPM script references to local `tools/*` files stay aligned with the package file whitelist.",
                "Current-release API/plugin wording labels monitoring endpoints as explicit baseline re-checks, not continuous monitoring.",
            ),
            runtime_surfaces=("tools/run-acceptance.ps1", "tools/run-focused-tests.ps1", "package.json", "deploy/mcp-server.json"),
            tags=("release", "acceptance", "hygiene"),
        ),
        DevelopmentRequirement(
            id="P1.PUBLIC_SOURCE_BREADTH",
            level="P1",
            title="Public and official source breadth",
            lane="retrieval",
            status="in_progress",
            completion_percent=89,
            current_version_scope=True,
            user_goal="Use multiple public or authorized sources so one source failure does not kill the investigation.",
            implemented=(
                "Default public intel, GLEIF, SEC, Wikidata, OFAC, UN, and datasource fixtures are wired.",
                "Official-public smoke path is available for constrained live validation.",
                "Default public web results can now contribute conservative industry/product leads when the hit is subject-specific.",
                "Public web leads can now carry explicit customer-value, subscription/SaaS, switching-cost, and value-chain-role claims when the source text says so.",
                "External reference review recorded the TYC-style L0 entity-anchor, L1 overview, L2 prioritized drill-down, and L3 specialist-tool pattern as the preferred evolution path for broad retrieval orchestration.",
                "SearchTask now exposes an executable retrieval_layer (`entity_anchor`, `overview`, `prioritized_drilldown`, `specialist`) in RetrievalPlan JSON output.",
                "RiskDiscoveryPipeline now executes seed search tasks by retrieval_layer order and passes the layer through diagnostics and connector parameters.",
                "DefaultPublicIntelTool now uses retrieval_layer to limit entity-anchor/overview fan-out to high-value public web and QYYJT entries before opening full default sources for deeper layers.",
                "Wikidata EntityData now maps board-member and owner-of relationship claims into standardized graph records instead of leaving them as raw knowledge-graph fields.",
                "RiskDiscoveryPipeline now attaches layer budgets (`result_limit`, `source_budget`, `per_source_result_limit`) to retrieval params; default public-intel maps those budgets to public-web `max_results` and QYYJT module scopes unless callers explicitly override them.",
                "Connector catalog now exposes a runtime `data_effectiveness` matrix that separates fact-capable sources, lead-capable sources, default fact sources, analysis-output coverage, admission modes, and source limitations.",
                "Public web extraction now emits conservative supply-chain leads for subject-specific customers, suppliers, partners, upstream/downstream, and concentration statements.",
                "Public web extraction now recognizes broader subject-specific money, goods, market-position, business-model, and people-role leads from public titles, snippets, and fetched previews while keeping weak matches lead-only.",
            ),
            gaps=(
                "Some official portals remain manual-gate or default-off.",
                "Live source availability and rate limits still affect coverage.",
                "Individual specialist adapters can still honor `per_source_result_limit` more deeply inside provider-specific parsers.",
                "The capability matrix shows breadth and admission mode, but more sources still need deeper field extraction and cross-source corroboration.",
            ),
            next_actions=(
                "Push `per_source_result_limit` into provider-specific parsers where it materially improves one-click report coverage or latency.",
                "Prioritize sources that materially improve the one-click report.",
                "Keep manual-gate sources out of default-on paths until admission is complete.",
            ),
            acceptance_gates=(
                "Default-enabled connectors are production-ready or conditionally active with explicit policy.",
                "Source failures are visible and do not erase partial evidence.",
            ),
            runtime_surfaces=("ConnectorRegistry", "DefaultOneClickSearchEngine", "official-public smoke"),
            tags=("retrieval", "connectors", "public_sources"),
        ),
        DevelopmentRequirement(
            id="P1.INDUSTRY_PRODUCT_EXTRACTION",
            level="P1",
            title="Industry, product, and supply-chain intelligence extraction",
            lane="enterprise_cognition",
            status="in_progress",
            completion_percent=90,
            current_version_scope=True,
            user_goal="Go beyond registry facts and explain what the company does, sells, and depends on.",
            implemented=(
                "SEC companyfacts and explicit source-backed claims can populate minimum financial/product cognition.",
                "Conservative public-description leads prevent hallucinated product detail.",
                "Subject-specific public web titles/snippets/fetch previews can now feed conservative industry and product cognition through the default public-intel route.",
                "QYYJT research rows can feed source-backed industry/product cognition when admitted fields are present.",
                "Public web extraction now captures explicit customer-value, SaaS/subscription model, switching-cost, and value-chain-role signals for product/industry cognition.",
                "Public web extraction now captures conservative subject-specific capital and key-person leads, including financing, debt/credit, liquidity pressure, pledged/frozen/auction pressure, CEO/director/controller/beneficial-owner/shareholder role cues, and structured public role entities.",
                "RetrievalPlan now explicitly schedules supply-chain deep-dive tasks for upstream/downstream, customers, suppliers, dealers, procurement, sales, and partners.",
                "RetrievalPlan now explicitly schedules industry-research tasks for sector, business model, competitive landscape, market share, products, customer value, and profit model.",
                "RetrievalPlan seed tasks now carry `params.investigation_track` and `params.case_questions` for the money/goods/people case lens, so execution layers can preserve the deep-investigation objective instead of running generic keyword searches.",
                "Evidence-backed supply-chain claims now populate `enterprise_cognition.supply_chain_profile`, remove the supply-chain evidence gap, drive next questions/watchlist entries, and render in report Markdown.",
                "Default public-intel pipeline can now carry subject-specific public web customer/supplier/partner/concentration statements into the supply-chain/business-map report section.",
                "`goods_flow_profile` now converts admitted product, industry, and supply-chain facts into a report-visible goods-in/goods-out investigation view with upstream, downstream, customer, supplier, partner, concentration, value-chain, pressure-point, and next-question fields.",
                "Exact/strong public-web capital leads can now feed the operational-event profile and `fund_flow_profile` as corroboration-needed financing/capital-pressure rows.",
                "RIX-001 expanded public-web extraction for major investment, refinancing, capital structure, market share, business model, revenue model, sales channel, founder, CFO, CTO, president, and Chinese role/supply-chain patterns with fixture-backed regression coverage.",
                "Exact/strong registry business_scope and public descriptions can now produce conservative industry and product-line leads across common sectors such as logistics, semiconductors, software, payments, education, healthcare, industrial equipment, and consumer goods without promoting them to verified facts.",
            ),
            gaps=(
                "Live/public product facts can remain sparse when descriptions do not mention concrete product or service categories.",
                "Supply-chain and customer concentration extraction now has a public-web and report path, but still needs source-specific parsers and corroboration logic.",
                "Industry analysis still needs deeper extraction of competitors, market structure, policy cycle, unit economics, and upstream/downstream bargaining power.",
                "Public web extraction is keyword-based and intentionally conservative until richer source-specific parsers are added.",
            ),
            next_actions=(
                "Add extraction contracts for product, industry, customer, supplier, and business-model claims.",
                "Add report cognition that compares market position, upstream/downstream leverage, and competitor/customer concentration from source-backed evidence.",
                "Test that thin public descriptions stay leads unless corroborated.",
            ),
            acceptance_gates=(
                "Industry/product/supply-chain statements cite evidence or are labeled as gaps/leads.",
                "No product detail is invented from generic company descriptions.",
                "Business-scope industry/product extraction is report-visible only as public_description_lead until structured revenue, market, or product signals corroborate it.",
            ),
            runtime_surfaces=("enterprise_cognition", "report Markdown", "quality gate"),
            tags=("industry", "product", "supply_chain", "business_model"),
        ),
        DevelopmentRequirement(
            id="P1.RUNTIME_SURFACE_CONTRACTS",
            level="P1",
            title="Runtime surface contract consistency",
            lane="platform",
            status="in_progress",
            completion_percent=84,
            current_version_scope=True,
            user_goal="API, CLI, MCP, skill prompts, WorkBuddy, Hermes, Doubao Office Task Mode, and OpenClaude-style agents should expose the same product truth.",
            implemented=(
                "Connector catalog, release readiness, and investigation packet are shared across surfaces.",
                "Desktop-agent surfaces can consume shared investigation packets, connector metadata, and QYYJT queue data.",
                "/api/docs now declares one_click_readiness source-resilience and relationship-graph readiness fields so desktop-agent hosts can consume the first-screen handoff contract.",
                "MCP and CLI investigation entrypoints now expose and enforce the same bounded execution controls as the API contract: retrieval concurrency 1..20, fanout rounds 0..3, max fanout tasks 0..80, and query timeout 0.1..120 seconds.",
            ),
            gaps=(
                "New runtime status surfaces must be added everywhere, not just in one UI.",
                "Some docs still lag behind executable contracts.",
            ),
            next_actions=(
                "Expose every product-critical status as shared core data, then connect API/CLI/MCP/skill-prompt/WorkBuddy/open-agent hosts.",
                "Keep encoding and command-help tests updated for every new surface.",
            ),
            acceptance_gates=(
                "API, CLI, MCP, skill-prompt, WorkBuddy, and open-agent hosts all load the same status source.",
                "Encoding guard covers new public command text.",
                "/api/docs lists product-critical one_click_readiness fields for source recovery and relationship graph auditability.",
                "CLI/MCP/API investigation entrypoints enforce the same execution bounds for desktop-agent hosts.",
            ),
            runtime_surfaces=("api/server.py", "bin/cli.js", "lib/mcp-server.js", "SKILL.md", "adapters/workbuddy.py"),
            tags=("api", "cli", "mcp", "skill", "workbuddy", "desktop_agent"),
        ),
        DevelopmentRequirement(
            id="P1.PERSONA_SURFACE",
            level="P1",
            title="Anthropomorphic expert-team shell",
            lane="persona",
            status="in_progress",
            completion_percent=84,
            current_version_scope=True,
            user_goal="Keep the 13-role expert-team identity visible as a real product surface, not only marketing copy.",
            implemented=(
                "Persona surface appears in release metadata, investigation packet, report Markdown, API, CLI/MCP, and skill-prompt surfaces.",
                "Role grouping and routing principles are available in runtime payloads.",
            ),
            gaps=(
                "Cross-surface wording and role activation still need final consistency pass.",
                "Persona should remain tied to actual module routing, not decorative copy.",
            ),
            next_actions=(
                "Map persona roles to the concrete investigation lanes they influence.",
                "Keep persona display as a support layer under retrieval/report correctness.",
            ),
            acceptance_gates=(
                "Investigation packet exposes persona_surface.",
                "Report and workbench render the expert-team section.",
            ),
            runtime_surfaces=("api/personality.py", "core/investigation.py", "index.html"),
            tags=("persona", "expert_team", "brand"),
        ),
        DevelopmentRequirement(
            id="P1.OPERATIONAL_OBSERVABILITY",
            level="P1",
            title="Operational observability and failure taxonomy",
            lane="operations",
            status="in_progress",
            completion_percent=78,
            current_version_scope=True,
            user_goal="When a source or run fails, the user should know what failed and what can still be trusted.",
            implemented=(
                "Risk pipeline already tracks queried sources, failed sources, diagnostics, and monitor-run stores.",
                "Timeouts and partial coverage are visible in summary paths.",
                "Risk-discovery runs now expose run_id in result, summary, and graph export.",
                "Source diagnostics now carry trace_id and normalized failure_category values.",
                "Investigation packets now expose source_failure_summary and render a report-level 运行诊断 section.",
                "Source diagnostics now expose coverage_recovery_decision with the next ready or blocked recovery step, blocker reason, key fields, and a report-visible recommended action.",
                "Source diagnostics now expose source_resilience_profile with score, status, failure pressure, coverage pressure, recovery readiness, blockers, and recommended action.",
                "Source diagnostics now aggregate recurring source failure patterns by source, failure category, and domain, then expose operator actions in source_failure_summary, monitoring_seed, and report Markdown.",
                "Quality gate now consumes source_resilience_profile directly, so retrieval health problems remain visible even when legacy summary.failed_sources is empty.",
                "One-click readiness now surfaces source_resilience_profile status, score, operator-recovery flag, and recommended action for desktop-agent hosts.",
                "API, WorkBuddy, and report paths inherit the same diagnostics through the shared investigation packet.",
            ),
            gaps=(
                "Metrics aggregation and health dashboard are not production-grade.",
                "Cross-run metrics storage and dashboarding still need production hardening beyond per-packet recurring-pattern aggregation.",
            ),
            next_actions=(
                "Persist recurring failure categories across monitor runs for health dashboards.",
                "Use the diagnostics payload to drive release readiness signals and source repair prioritization.",
            ),
            acceptance_gates=(
                "Every retrieval run has a stable run identifier and failure category.",
                "Report tail can distinguish timeout, auth, empty result, parser, and source unavailable.",
                "Investigation packet exposes source_failure_summary for API/UI reuse.",
                "Investigation packet and report expose source_resilience_profile without treating retrieval health as a subject risk verdict.",
                "Repeated source/category/domain failures appear in recurring_failure_patterns with concrete operator_action guidance.",
                "Quality gate warnings include source_resilience_needs_operator_recovery when source_resilience_profile requires operator recovery.",
                "One-click readiness exposes source resilience recovery status and the recommended operator action.",
            ),
            runtime_surfaces=("RiskDiscoveryPipeline.diagnostics", "report tail", "/api/investigate"),
            tags=("observability", "diagnostics", "source_health"),
        ),
        DevelopmentRequirement(
            id="P2.STATIC_WORKBENCH_SURFACE",
            level="P2",
            title="Static workbench operating surface",
            lane="ui",
            status="in_progress",
            completion_percent=74,
            current_version_scope=True,
            user_goal="Provide a useful local demo and investigation viewer without confusing UI polish for core product progress.",
            implemented=(
                "Workbench accepts company input, renders packet, evidence, graph preview, QYYJT queue, release status, and persona brief.",
                "Desktop/mobile static smoke passed with no horizontal overflow.",
            ),
            gaps=(
                "Hosted refresh remains a deployment task.",
                "UI should not absorb P0 time unless it exposes real investigation output better.",
            ),
            next_actions=(
                "Keep the workbench as a thin viewer over runtime APIs.",
                "Avoid decorative-only changes until P0/P1 lanes are closed.",
            ),
            acceptance_gates=(
                "Workbench loads offline fallback and local API data.",
                "Exported Markdown/JSON/HTML includes the same packet data.",
            ),
            runtime_surfaces=("index.html", "static export"),
            tags=("ui", "workbench", "p2"),
        ),
        DevelopmentRequirement(
            id="P2.PRODUCTIZED_REPORT_OUTPUTS",
            level="P2",
            title="Productized report output packages",
            lane="report_delivery",
            status="planned",
            completion_percent=12,
            current_version_scope=True,
            user_goal="Deliver investigation results in three productized forms: printable government-style Word documents, full-fidelity premium HTML reports, and a third owner-confirmed package format still to be confirmed.",
            implemented=(
                "The runtime investigation_packet already carries structured JSON, report Markdown, evidence ledger, graph data, diagnostics, and report-visible cognition sections that output generators can consume.",
                "Static workbench export already proves the packet can be converted to portable HTML without dropping core packet data.",
            ),
            gaps=(
                "Word report generator is not implemented: it must produce a red-head official-document front section that follows formal public-document layout conventions, a concise investigation-result brief, the full due-diligence body, charts, collected image evidence, print margins, page numbers, table of contents, and binding-friendly layout.",
                "Premium HTML report is not implemented: it must preserve the full due-diligence result while adding high-end interaction, immersive motion, refined visual hierarchy, charts, imagery, and non-generic design language.",
                "The requested third productized output form is not specified yet.",
            ),
            next_actions=(
                "Define the Word document template contract: red-head header, official-document typography, brief-report section, investigation body, chart/image placement, pagination, and print/export requirements.",
                "Define the premium HTML design brief and asset pipeline late in the release, after runtime facts and report sections are stable: no data reduction, no generic AI look, no large purple gradients, no low-effort color ramps, and room for particles, liquid-glass, skeuomorphic, 3D, and high-resolution visual treatment where it improves comprehension.",
                "Ask the owner to confirm the third output form before implementation starts.",
            ),
            acceptance_gates=(
                "Word output opens as a .docx file with red-head official-document front matter, concise due-diligence result brief, full investigation body, charts, collected images, page numbers, table of contents, and print/binding layout.",
                "HTML output displays the complete investigation result without shortening evidence, report, graph, diagnostics, or next-action content.",
                "HTML output passes a visual QA checklist for premium interaction, immersive presentation, chart/image richness, liquid-glass or 3D treatment where appropriate, and avoids generic AI-style gradients, low-effort purple themes, and data-loss shortcuts.",
                "Third output form has an owner-confirmed specification before engineering starts.",
            ),
            runtime_surfaces=("future report generator", "docx export", "premium html export"),
            tags=("report_delivery", "docx", "html", "visual_design", "p2"),
        ),
        DevelopmentRequirement(
            id="P2.DOCUMENTATION_TRUTH_ALIGNMENT",
            level="P2",
            title="Documentation and public-claim truth alignment",
            lane="docs",
            status="in_progress",
            completion_percent=62,
            current_version_scope=True,
            user_goal="Docs should match what the executable system can actually do today.",
            implemented=(
                "Taskboard, search ledger, release docs, connector catalog, and API docs capture major runtime contracts.",
                "Public-data boundary is documented.",
            ),
            gaps=(
                "Some old checkpoint language and public portal copy can drift behind code.",
                "Docs need final release pass after P0/P1 closure.",
            ),
            next_actions=(
                "Update docs only after code/tests pass for the corresponding feature.",
                "Remove stale or overbroad claims before public release.",
            ),
            acceptance_gates=(
                "Docs mention only executable or explicitly planned capabilities.",
                "Current-release and future-version scopes are separated.",
            ),
            runtime_surfaces=("PROJECT_TASKBOARD.md", "docs/SEARCH_INTEGRATION_LEDGER.md", "README.md"),
            tags=("docs", "release_truth", "p2"),
        ),
        DevelopmentRequirement(
            id="FUTURE.CONTINUOUS_MONITORING",
            level="Future",
            title="Continuous monitoring and alert operations",
            lane="monitoring",
            status="parked",
            completion_percent=20,
            current_version_scope=False,
            user_goal="Later-version continuous watch, alert history, source health, and dashboard behavior.",
            implemented=(
                "Single-run monitor endpoints and run-store primitives exist as supporting infrastructure.",
            ),
            gaps=(
                "Always-on scheduling, alerting, dashboard, retention, and production operations are intentionally out of current release.",
            ),
            next_actions=(
                "Do not spend current-release capacity here unless the user explicitly re-scopes the version.",
                "Promote to P0/P1 only in a later monitoring-focused release.",
            ),
            acceptance_gates=(
                "Current reports describe monitoring as a later-version target.",
                "No current-release surface promises always-on continuous monitoring.",
            ),
            runtime_surfaces=("/api/monitor/*", "RiskMonitor"),
            tags=("monitoring", "future", "parked"),
        ),
        DevelopmentRequirement(
            id="FUTURE.HOSTED_OPERATIONS",
            level="Future",
            title="Hosted production operations",
            lane="deployment",
            status="parked",
            completion_percent=15,
            current_version_scope=False,
            user_goal="Public hosted demo, deployment automation, credentials strategy, and production support model.",
            implemented=(
                "Docker, deployment manifests, and release variant metadata exist.",
            ),
            gaps=(
                "Production hosting, live credentials, SLOs, and ops runbooks are not complete.",
            ),
            next_actions=(
                "Finish current P0/P1 product loop before promoting hosted operations.",
            ),
            acceptance_gates=(
                "Deployment claims require live hosted verification and secret hygiene.",
            ),
            runtime_surfaces=("deploy/", "release/variants.yaml"),
            tags=("deployment", "future", "hosting"),
        ),
    ]


def _qyyjt_requirement_snapshot(qyyjt: dict[str, Any]) -> dict[str, Any]:
    summary = qyyjt["summary"]
    surface = summary["surface_profile"]
    return {
        "module_count": summary["module_count"],
        "coverage_status": summary["coverage_status"],
        "p0_queue_count": summary["p0_queue_count"],
        "p0_queue_head": summary["p0_queue"][:5],
        "surface_lanes": summary["surface_lanes"],
        "surface_profile": surface,
        "parity_priorities": summary["parity_priorities"],
        "current_release_requirement_id": "P0.QYYJT_CURRENT_VERSION_PARITY",
    }


def _weighted_completion(items: list[DevelopmentRequirement]) -> int:
    weighted_total = 0
    weight_sum = 0
    for item in items:
        weight = LEVEL_WEIGHTS.get(item.level)
        if not weight:
            continue
        weighted_total += item.completion_percent * weight
        weight_sum += weight
    if not weight_sum:
        return 0
    return int(round(weighted_total / weight_sum))


def _count_by(items: list[DevelopmentRequirement], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(getattr(item, attr))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (LEVEL_ORDER.get(pair[0], 99), pair[0])))


def _next_focus(items: list[DevelopmentRequirement]) -> list[dict[str, Any]]:
    candidates = [
        item for item in items
        if item.status != "done" and item.level in {"P0", "P1"}
    ]
    candidates.sort(key=lambda item: (LEVEL_ORDER[item.level], item.completion_percent, item.id))
    return [
        {
            "id": item.id,
            "level": item.level,
            "lane": item.lane,
            "title": item.title,
            "completion_percent": item.completion_percent,
            "next_action": item.next_actions[0] if item.next_actions else "",
            "acceptance_gate": item.acceptance_gates[0] if item.acceptance_gates else "",
        }
        for item in candidates[:8]
    ]


def _acceptance_gates(items: list[DevelopmentRequirement]) -> dict[str, list[dict[str, str]]]:
    gates: dict[str, list[dict[str, str]]] = {"P0": [], "P1": [], "P2": []}
    for item in items:
        if item.level not in gates:
            continue
        for gate in item.acceptance_gates:
            gates[item.level].append({"requirement_id": item.id, "gate": gate})
    return gates
