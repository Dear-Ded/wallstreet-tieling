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
    delivery_decision = _delivery_decision(current_items)

    return {
        "type": "development_requirements_board",
        "version": VERSION,
        "release": CURRENT_RELEASE,
        "completion_percent": _weighted_completion(current_items),
        "delivery_decision": delivery_decision,
        "summary": {
            "current_release_completion_percent": _weighted_completion(current_items),
            "total_items": len(items),
            "current_scope_items": len(current_items),
            "by_level": _count_by(items, "level"),
            "by_status": _count_by(items, "status"),
            "p0_open_count": sum(1 for item in current_items if item.level == "P0" and item.status != "done"),
            "release_decision": delivery_decision["full_product_status"],
            "desktop_agent_delivery": delivery_decision["status"],
            "next_major_gate": delivery_decision["next_major_gate"],
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


def _delivery_decision(current_items: list[DevelopmentRequirement]) -> dict[str, Any]:
    """Separate desktop-agent alpha delivery from later full-product launch."""
    current_completion = _weighted_completion(current_items)
    p0_open = sum(1 for item in current_items if item.level == "P0" and item.status != "done")
    p0_min_completion = min(
        (item.completion_percent for item in current_items if item.level == "P0"),
        default=0,
    )
    desktop_agent_candidate = current_completion >= 90 and p0_min_completion >= 94
    status = (
        "desktop_agent_alpha_release_candidate"
        if desktop_agent_candidate
        else "desktop_agent_alpha_needs_runtime_closure"
    )
    return {
        "type": "development_delivery_decision",
        "current_target": "desktop_agent_alpha",
        "status": status,
        "desktop_agent_release_candidate": desktop_agent_candidate,
        "full_product_status": "not_final_release_ready",
        "current_release_completion_percent": current_completion,
        "p0_open_count": p0_open,
        "p0_min_completion_percent": p0_min_completion,
        "policy": (
            "The desktop-agent alpha can be treated as a release candidate when current-scope "
            "completion is at least 90% and every P0 lane is at least 94%; full product launch "
            "still requires later Word/HTML polish, hosted operations, and owner-confirmed output forms."
        ),
        "next_major_gate": (
            "finalize desktop-agent release artifacts, screenshots, and public-claim hygiene"
            if desktop_agent_candidate
            else "finish open P0 runtime lanes, then run full acceptance and live/public smoke"
        ),
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
            completion_percent=98,
            current_version_scope=True,
            user_goal="Enter a company and receive a useful evidence-backed investigation packet, not a pile of raw source output.",
            implemented=(
                "CLI/API/MCP one-click investigation packet is executable.",
                "Evidence ledger, graph preview, quality gate, report Markdown, and public/fixture/live modes are wired.",
                "Default public route can produce a packet and expose coverage gaps without pretending gaps are low risk.",
                "Report Markdown now renders run/source failure diagnostics so source failures are visible in the same artifact.",
                "Packet JSON and Markdown now expose one_click_readiness with fact/lead counts, quality status, recovery counts, and loop-section checks.",
                "One-click readiness now exposes coverage execution, coverage-gap count/severity/attempt ratio/next action, public-origin fallback actions, relationship-candidate execution steps, unresolved capital-pressure relationship status, and source resilience without requiring agents to inspect diagnostics.",
                "Investigation packets now include report_exports for Markdown, full JSON packet, portable printable HTML, and a print_package manifest for red-head Word/PDF agent rendering.",
                "Report exports now mark DOCX as available through the runtime CLI renderer (`bin/investigate.py --export-docx`) instead of leaving the Word output contract as renderer-pending.",
                "Acceptance now exercises both default Apple-style public one-click output and a China-style fixture-pack investigation with facts, operator work, money/goods/people cognition profiles, and report export contracts.",
                "Portable HTML report exports now expose machine-readable first_screen_handoff_cards synchronized with the print-package operational handoff, so desktop agents can act on source, capital, relationship, and coverage work without scraping HTML text.",
                "One-click readiness now exposes capital_relationship_closure_step as a machine-readable CAP-REL action when capital pressure is unresolved, and report Markdown mirrors the same closure step for text-only desktop agents.",
                "One-click readiness now exposes goods_economics_closure_step and routes public unit-economics, bargaining-power, and competitive-landscape leads into operator_work_queue, report Markdown, print-package operational handoff, and API contract surfaces.",
                "One-click readiness now exposes people_control_closure_step and routes public controller/UBO, key-person, legal-pressure, ownership-change, and related-party leads into operator_work_queue, report Markdown, print-package operational handoff, and API contract surfaces.",
                "One-click readiness now exposes public_origin_gap_bridge rows and top actions, converting missing coverage domains into executable public-origin reconstruction work.",
            ),
            gaps=(
                "Live public sources can still miss product and hard risk-event facts for some companies.",
                "Report cognition still needs broader real-company product/risk facts from additional source-specific parsers.",
            ),
            next_actions=(
                "Patch the weakest packet section observed in actual output before widening scope.",
                "Add more real-company public-source regression cases as source parsers improve.",
            ),
            acceptance_gates=(
                "bin/investigate.py returns type=investigation_packet with evidence_ledger and report_markdown.",
                "Quality gate distinguishes ready_for_human_review, usable_with_warnings, incomplete_coverage, and source_failure.",
                "Default route must not return all_sources_failed for the acceptance company.",
                "Acceptance covers a China-style fixture-pack packet with facts, operator work, money/goods/people profiles, and report export contract.",
                "Report Markdown includes a One-click Product Loop section before key findings.",
                "Portable HTML exposes first_screen_handoff_cards that match print_package.operational_handoff.cards.",
                "Unresolved capital pressure exposes a capital_relationship_closure_step with priority, target, source, and done condition.",
                "Public goods economics leads expose a goods_economics_closure_step and a matching operator work row without promoting public leads to facts.",
                "Public people/control leads expose a people_control_closure_step and a matching operator work row without promoting public leads to facts.",
                "Coverage gaps expose public_origin_gap_bridge rows and top action fields through one_click_readiness, report Markdown, print handoff, and agent-handoff exports.",
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
            completion_percent=98,
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
                "Admitted bond-credit, regional-credit, asset-solvency, and financial-institution profiles now expose top_exposures, monitoring_queue, field_coverage, stable fingerprints, and report-visible next verification steps.",
                "All 45 QYYJT field-contract record types now have a structured bridge; watchlist and alert-push modules remain visible as lead-only follow-up work rather than verified facts.",
                "QYYJT public-origin fallback diagnostics now carry module field contracts, required fields, record type, admission gate, and acceptance gate into JSON next actions and report Markdown.",
                "QYYJT benchmark now exposes a public_origin_execution_queue that combines module priority, lawful public-origin channels, query families, field contract, record type, admission gate, and done condition for direct agent execution.",
                "QYYJT benchmark now exposes public_origin_execution_summary with P0 counts, lane/channel counts, top action, next batch, and field-contract gap count so agents can schedule public-origin reconstruction without re-parsing all module rows.",
                "QYYJT public-origin execution summary now groups actions into report_section_batches for legal, asset-solvency, financing, relationship, registry, IP, and public-opinion sections so agents can execute report-relevant batches directly.",
                "Investigation packets now mirror QYYJT report_section_batches into qyyjt_public_origin_handoff, with corrected p0_action_count detection for p0_* priority rows and report Markdown section-batch previews.",
                "QYYJT public-origin handoff now exposes per-report-section section_work_orders with query families, required fields, origin channels, top actions, done condition, and admission policy, mirrored into agent-handoff exports and MCP/API contracts.",
                "One-click readiness now bridges coverage gap domains to QYYJT/public-origin reconstruction actions, with module, origin channel, required field, admission gate, and done-condition fields mirrored into report, print handoff, and agent-handoff exports.",
            ),
            gaps=(
                "Some non-P0 contracts still need broader fixture coverage and live-authorized smoke evidence.",
                "Broader live/API field mapping is still needed before all non-P0 modules can be treated as production-depth parity.",
            ),
            next_actions=(
                "Broaden fixture-backed mapping for the next highest-value non-P0 modules that materially improve legal, solvency, industry, or relationship report sections.",
                "Use report_section_batches to target fixture and live-authorized smoke coverage at the thinnest report sections before treating new modules as production-depth parity.",
            ),
            acceptance_gates=(
                "QYYJT rows expose field_contract, report_admission, evidence_role, and acceptance_gate.",
                "Weak or query-plan QYYJT leads never promote graph facts or controller candidates.",
                "Current P0 modules have standardized records with source URL or provenance when admitted.",
                "QYYJT public-origin fallback rows expose required fields, admission gates, and execution summary before an agent can treat follow-up results as report evidence.",
                "QYYJT public-origin execution summary groups top actions by report section with section-level done conditions.",
                "Investigation packets expose qyyjt_public_origin_handoff.report_section_batches without requiring agents to fetch the connector catalog separately.",
                "Coverage gaps expose public_origin_gap_bridge actions so desktop agents can map missing domains to QYYJT/public-origin reconstruction work without scraping report text.",
            ),
            runtime_surfaces=("ConnectorRegistry.product_catalog", "/api/connectors", "/api/investigate", "--connectors", "connector_catalog MCP", "investigate_company MCP"),
            tags=("qyyjt", "enterprise_warning", "retrieval", "current_release"),
        ),
        DevelopmentRequirement(
            id="P0.EVIDENCE_ADMISSION_ENTITY_RESOLUTION",
            level="P0",
            title="Evidence admission and entity-resolution integrity",
            lane="evidence_graph",
            status="in_progress",
            completion_percent=98,
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
                "Connector catalog now exposes per-source admission_gates plus summary.admission_gate_summary so default-on fact/lead sources declare entity-match, field-contract, provenance, and corroboration gates before report reliance.",
                "Evidence admission now requires exact/strong/verified entity matching before official, licensed, QYYJT, or SEC rows can become facts, and query-plan/query-template records stay lead-only even when source and confidence look strong.",
                "Subject-profile relationship edge admission now re-checks entity_match quality, so official/licensed evidence with weak, review, query-plan, or rich-query-plan matches cannot promote relationship edges to facts.",
                "Field-contract and report-admission results now flow from standardized records into EvidenceGraph and the investigation evidence ledger, so licensed or QYYJT rows with missing required/common fields remain leads despite high confidence and exact entity matches.",
            ),
            gaps=(
                "More source-specific exact/strong matching rules are still needed for future licensed feeds and less-structured public sources.",
                "Some older adapters still need source-specific field-contract coverage before they can become fact-capable defaults.",
            ),
            next_actions=(
                "Add source-specific match/admission tests whenever a connector becomes default-on or report-admissible.",
                "Keep query-plan and weak-match regression tests in the acceptance path.",
            ),
            acceptance_gates=(
                "Weak entity_match levels do not create graph entities.",
                "Query-plan and rich-query-plan records remain leads and cannot generate entities, relations, controller candidates, subject-profile signals, risk events, or evidence-classified packet rows by themselves.",
                "Official, licensed, QYYJT, and SEC rows require strong entity matching before fact admission.",
                "Evidence export preserves source, access, authority, confidence, and match basis.",
                "Subject-profile relationship graph edges preserve evidence-derived admission and source-strength metadata.",
                "Official or licensed relationship edges with weak/review entity_match remain leads until source-specific entity resolution is exact or strong.",
                "Default-on connector catalog rows expose admission_gates before they can be treated as fact-capable report sources.",
                "Report-admission failures caused by missing required or common fields are visible in the evidence ledger and block fact promotion.",
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
            completion_percent=98,
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
                "Control-ownership output now exposes controller_conflict_summary with preferred source names and competing-candidate source audit details, so agents can explain why an authorized/official controller outranks public leads.",
                "Quality gate now treats fact/admitted/evidence relationship edges with evidence_ids as auditable strengths, while weak or evidence-less edges remain review warnings.",
                "Multi-layer controller and UBO graph paths now emit structured control_path_summaries with hop count, relation sequence, source strength, admission, minimum confidence, source names, and evidence IDs for packet/report consumption.",
                "Multi-layer controller and UBO paths now expose control_path_verification_queue plus one_click_readiness.control_path_closure_step, operator_work_queue rows, report Markdown, print-package handoff cards, and API/release contract surfaces.",
                "Directory agent-handoff closure_steps now mirrors control_path_verification_queue and control_path_top_step, so desktop agents can review admitted UBO/control-chain paths without parsing the full packet.",
                "Control-path review rows now carry source_families and a control_path_source_family_summary, showing whether UBO/control-chain paths are supported by official, licensed, knowledge-graph, or public-web source families without upgrading weak leads.",
                "Subject-profile controller candidates, control_path_summaries, and relationship graph edges now expose source_families plus source_family_summary directly, with candidate summaries covering the entire multi-hop control path instead of only the terminal person edge.",
            ),
            gaps=(
                "Broader live-source controller/UBO mapping remains incomplete for additional source-specific field aliases and conflict-resolution precedence across more source families.",
                "Recursive key-person follow-up remains bounded and conservative.",
            ),
            next_actions=(
                "Keep adding source-specific live-field aliases as new SEC, GLEIF, QYYJT, Wikidata, registry, and authorized feeds become default-on.",
                "Tune recursive key-person follow-up only when it improves the one-click report without increasing false facts.",
            ),
            acceptance_gates=(
                "Controller candidates exclude query-plan and weak evidence.",
                "Report renders control path, tier, and basis.",
                "Relationship graph includes evidence-backed relation edges.",
                "Quality gate warns when verified controller or UBO claims conflict.",
                "Quality gate warns when relationship graph edges lack fact admission or evidence_ids.",
                "Multi-layer controller or UBO paths expose a control_path_closure_step and matching operator work row before final reliance.",
                "Directory agent-handoff exposes closure_steps.control_path_verification_queue with the same bounded control-chain review rows as enterprise_cognition.control_ownership.",
                "Control-path outputs expose source-family provenance summaries through enterprise_cognition, one_click_readiness, API docs, and release contracts.",
                "Subject-profile controller candidates and relationship graph edges expose source-family provenance without changing admission strength.",
            ),
            runtime_surfaces=("core/subject_profile.py", "core/investigation.py", "one_click_readiness.control_path_closure_step", "report Markdown"),
            tags=("ubo", "controller", "subject_profile"),
        ),
        DevelopmentRequirement(
            id="P0.REPORT_VALUE_COGNITION",
            level="P0",
            title="User-readable report value and enterprise cognition",
            lane="reporting",
            status="in_progress",
            completion_percent=98,
            current_version_scope=True,
            user_goal="The final report should tell a non-technical user what matters, what is known, what is missing, and what to do next.",
            implemented=(
                "Report includes quality, provenance, risk ledger, relationship graph, registry snapshot, financial, credit, legal/admin, operational-event, industry, product, and persona sections.",
                "Source-backed claims feed enterprise cognition instead of only dumping raw JSON.",
                "Evidence-backed customer, supplier, upstream/downstream, partner, value-chain-role, and concentration signals now render as a report-visible supply-chain/business-map section.",
                "Report JSON and Markdown now expose the `case_investigation_lens`, organizing deep-dive work into money, goods, and people tracks without narrowing the broader investigation scope.",
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
                "Risk graph summary now exposes a capital_exposure machine-readable summary with pressure level, signal counts, evidence ids, explicit capital relationship edge status, and next action for plugin/UI quick rendering.",
                "One-click readiness and report Markdown now expose machine-readable reliance_limitations so missing facts, coverage gaps, source recovery, capital relationship gaps, and relationship evidence gaps are explicit non-reliance caveats with next actions.",
                "Print-package operational handoff and directory agent-handoff exports now surface reliance limitation top actions and summaries, so desktop agents can route non-reliance caveats without parsing full report text.",
                "Risk-graph capital_exposure is now mirrored into one_click_readiness, report Markdown, print handoff cards, and directory agent-handoff exports so graph-level capital pressure is visible without opening raw graph JSON.",
                "Acceptance closure is now surfaced through one_click_readiness, report Markdown, print-package operational handoff, chart manifest, directory agent-handoff, API docs, and release runtime_delivery entrypoints.",
                "Directory agent-handoff exports now include a relationship_graph_audit summary with evidence-backed, auditable, missing-evidence, lead-only, queue-count, top-step, and non-reliance policy fields for desktop-agent routing.",
                "One-click readiness and directory agent-handoff exports now expose the bounded capital_verification_queue, so desktop agents can execute multiple capital-risk verification steps without parsing report prose.",
                "Directory agent-handoff source_health now mirrors monitoring_seed.recovery_execution_queue, giving desktop agents ready rows, blocked preview rows, retry policy, and work-order metadata without parsing the full packet.",
                "Capital pressure and graph-capital exposure now expose source_family_summary fields, so desktop agents can distinguish official, licensed, knowledge-graph, and public-web capital-risk provenance without upgrading weak leads.",
            ),
            gaps=(
                "Industry/product extraction is still thin when public sources provide only generic descriptions.",
                "Next-question recommendations still need more real-company tuning after live/public packet review.",
            ),
            next_actions=(
                "Continue tuning limitation wording against live/public packet output.",
                "Use reliance_limitations to drive report export summaries and agent-host handoffs.",
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
                "One-click readiness exposes reliance_limitations and can_make_clean_conclusion so missing data cannot be misread as low risk.",
                "Report export handoffs expose reliance limitation summaries and a top-action card synchronized from one_click_readiness.",
                "Risk-graph capital_exposure is mirrored into one-click, report, print handoff, and agent-handoff surfaces with alignment status and top verification step.",
                "Capital pressure and graph-capital exposure expose source-family provenance summaries through one_click_readiness, API docs, and release contracts.",
                "Acceptance closure summary is visible in packet JSON, Markdown, print handoff cards, chart manifest, API docs, and release runtime_delivery entrypoints.",
                "Directory agent-handoff exposes relationship_graph_audit with edge counts, evidence/audit split, queue count, top step, and task-routing-only policy.",
                "Capital verification exposes both capital_verification_queue_count and bounded capital_verification_queue through one_click_readiness and directory agent-handoff exports.",
                "Directory agent-handoff exposes source_health.recovery_execution_queue with ready rows, blocked preview rows, retry policy, and task-routing metadata.",
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
            completion_percent=98,
            current_version_scope=True,
            user_goal="The package must pass acceptance and not ship secrets, private state, or misleading release claims.",
            implemented=(
                "Acceptance script runs focused Python tests, plugin validator, terminology guard, syntax checks, MCP smoke, and one-click smoke.",
                "Release, connector, and persona contracts are exposed at runtime.",
                "Public-data boundary and packaging file list are explicit.",
                "Node CLI now forwards `--store`, and packaged Codex MCP smoke uses an isolated writable risk-event store instead of relying on user-home write access.",
                "Runtime state paths now support explicit env/config overrides and writable temp fallback for risk-event, monitor-run, and memory stores.",
                "Acceptance now includes storage-path regression tests so restricted execution environments do not silently break local state.",
                "Acceptance now redirects TEMP, state, and pytest cache paths to a writable acceptance state directory with per-run TEMP subdirectories, avoiding Program Files and stale pytest temp permission noise.",
                "`npm run test:focused` now uses the same writable state/cache policy and a fresh TEMP subdirectory for focused regression runs.",
                "Release hygiene now retries `git ls-files` on transient Windows page-file pressure (`WinError 1455`) before treating it as a real failure.",
                "Package variant tests now ensure every local `tools/*` script referenced by npm scripts exists and is included in the npm package file whitelist.",
                "Adapter audit now infers datasource tiers from connector metadata so official-public connectors are not blocked by unknown_source_tier, while user-authorized deep sources remain review-gated and default-off.",
                "Latest full acceptance passed on 2026-07-01 18:55 Asia/Shanghai with 752 Python tests, 9 skipped tests, plugin validation, API smoke, and Apple Inc. default one-click acceptance after source recovery execution queue, control-path verification/source-family handoff, capital source-family handoff, controller source-family provenance, report-admission contract enforcement, relationship graph audit handoff gating, source-resilience retry policy, and DOCX local-image embedding.",
                "API index/docs and plugin prompts now describe monitor execution as explicit baseline re-checks, keeping continuous monitoring in later-version scope.",
                "Full acceptance now gates directory-bundle agent_handoff content for relationship graph audit summary, not only the one_click_readiness relationship queue counter.",
                "Focused investigation/API/release-variant tests plus API, MCP, and agent-host smokes now gate directory-bundle agent_handoff content for the source recovery execution queue.",
                "`npm run test:focused` now passes the resolved Python runtime into Node CLI subprocess tests, forces pytest-asyncio auto mode, and uses a project tmp_path fixture that avoids Windows TempPathFactory ACL failures.",
                "Node CLI metadata and offline-fixture export commands now have a narrow fallback when Python child-process spawning is blocked by the desktop host, preserving desktop-agent read-only surfaces instead of aborting.",
                "Latest full acceptance passed on 2026-07-06 08:24 Asia/Shanghai with 799 Python tests, 9 skipped tests, plugin validation, API smoke, Apple Inc. default one-click acceptance, agent_tool_adapters runtime contract, Codex primary delivery lane and WorkBuddy secondary branch priority, connector_catalog source_strengthening_queue, official China source strengthening implementation_pack, OpenSanctions and IDB public dataset source strengthening implementation_pack, agent_tool_adapters first_run_recipe preserves source_strengthening_queue, source_strengthening risk_enforcement lane routing, source_strengthening execution_plan agent handoff, release_preflight package go/no-go gate, delivery_audit go/no-go gate, objective_audit active-goal completion gate, package privacy scan gate, WorkBuddy investigate_company host smoke, host-smoke Python runtime resolution, aggregate_subject CLI/API/MCP release surface, npm package dry-run content gate, terminology guard public-copy hygiene, productized DOCX official metadata/chart-panel output, DOCX source provenance appendix/evidence source index output, DOCX relationship/capital appendix and delivery checklist output, source_resilience agent_autorun, QYYJT public-origin agent_autorun, capital risk and relationship autorun routes, report_artifact_agent_autorun, executable agent-handoff routing, report_exports.agent_decision_digest packet routing, directory bundle verifier_output_fields handoff, directory bundle verification_recipe handoff, decision_digest handoff, bundle_integrity handoff, delivery checklist handoff, portable HTML checklist rendering, manifest file_manifest/agent_summary, manifest agent_summary deep drift verification, executable report-bundle verifier with tamper and handoff-schema detection, API smoke manifest-field gating, Node fallback export-dir manifest contract alignment, focused-test Windows temp/Python-spawn hardening, source-specific public goods parsing, package privacy scan Windows cache cleanup hardening, and capability-audit blocker classification hardening.",
                "Post-acceptance source-strengthening completion regression passed on 2026-07-05 21:24 Asia/Shanghai with 223 Python tests, 2 skipped tests, validating needs_admission=0, empty source_strengthening_queue completion summaries, Codex/API smoke acceptance, investigation/export handoff completion state, bundle verifier semantics, and WorkBuddy packet compatibility.",
                "Release readiness now exposes delivery_decision, separating desktop-agent alpha release-candidate delivery from full-product final launch readiness.",
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
                "Acceptance script fails if report_exports.directory_bundle.agent_handoff omits the relationship graph audit summary.",
                "API, MCP, and agent-host smokes fail if report_exports.directory_bundle.agent_handoff omits the source recovery execution queue.",
                "`npm run test:focused` passes the default investigation/public-web/default-intel suite without pytest temp ACL or Node Python-spawn failures.",
                "Node CLI read-only metadata and offline-fixture export paths degrade to explicit fallback payloads if Python child process spawning is blocked.",
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
            completion_percent=95,
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
                "Public web provider and fixture paths now enforce max_results after normalization and expose requested_result_limit so per-source retrieval budgets remain bounded even when providers ignore the hint.",
                "Coverage-gap handling now links missing or empty domains to public-origin bridge actions, making public-source fallback executable instead of a separate diagnostics note.",
                "Public people profile now splits controller/UBO, key-person, legal-pressure, ownership-change, related-party, and labor/social public leads into structured runtime buckets consumed by people lane, people-flow profile, subject profile, and report Markdown without promoting public snippets to facts.",
                "Structured public people/control leads now produce a people_control_closure_step, operator-work row, report Markdown section, print/HTML handoff card, API contract fields, and release-contract surface.",
            ),
            gaps=(
                "Some official portals remain manual-gate or default-off.",
                "Live source availability and rate limits still affect coverage.",
                "The capability matrix shows breadth and admission mode, but more sources still need deeper field extraction and cross-source corroboration.",
            ),
            next_actions=(
                "Push source-specific extraction deeper into the next highest-value official/public adapters.",
                "Prioritize sources that materially improve the one-click report.",
                "Keep manual-gate sources out of default-on paths until admission is complete.",
            ),
            acceptance_gates=(
                "Default-enabled connectors are production-ready or conditionally active with explicit policy.",
                "Source failures are visible and do not erase partial evidence.",
                "Coverage gaps are bridged to public-origin actions with domain, module, source/channel, required-field, and admission-gate metadata.",
                "Public people/control leads remain corroboration-needed but are visible in people lane, people-flow profile, subject profile, and report Markdown with structured control, key-person, legal-pressure, ownership-change, and related-party counts.",
                "Public people/control closure is exposed through one_click_readiness, operator_work_queue, print/HTML handoff cards, API docs, and release contract without admitting public snippets as facts.",
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
            completion_percent=95,
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
                "Public goods profile now structures distributor/dealer/reseller/channel partner leads into channel_partner_claims, goods lane channel dependency, goods_flow channel_or_partner_signals, and report-visible goods public lead counts.",
                "Public goods profile now splits explicit public-web unit economics, bargaining-power, and competitive-landscape claims into dedicated runtime fields consumed by goods lane analysis, goods-flow signals, and report Markdown.",
                "Public web source-specific page parsers now route industry-report, annual-report, procurement, and official-company page signals for market size, pricing power, peer comparison, CAC/LTV, revenue model, moat, competitor set, capacity cycle, tender competition, and brand value into public goods runtime profiles.",
            ),
            gaps=(
                "Live/public product facts can remain sparse when descriptions do not mention concrete product or service categories.",
                "Supply-chain, channel, and customer concentration extraction now has a public-web and report path, but still needs source-specific parsers and corroboration logic.",
                "Industry analysis still needs broader source-specific corroboration for policy cycle, upstream/downstream bargaining power, and non-English report templates.",
                "Public web extraction is keyword-based and intentionally conservative until richer source-specific parsers are added.",
            ),
            next_actions=(
                "Add source-specific parsers for policy-cycle, upstream/downstream bargaining-power, and non-English report templates.",
                "Add report cognition that compares market position, upstream/downstream leverage, and competitor/customer concentration from source-backed evidence.",
                "Test that thin public descriptions stay leads unless corroborated.",
            ),
            acceptance_gates=(
                "Industry/product/supply-chain statements cite evidence or are labeled as gaps/leads.",
                "No product detail is invented from generic company descriptions.",
                "Business-scope industry/product extraction is report-visible only as public_description_lead until structured revenue, market, or product signals corroborate it.",
                "Explicit unit-economics, bargaining-power, and competitive-landscape public leads remain lead-labeled but are visible in goods lane, goods-flow profile, and report Markdown.",
                "Source-specific public web page signals for market size, pricing power, CAC/LTV, revenue model, moat, competitor set, and capacity cycle enter public_goods_profile as lead-labeled structured fields.",
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
            completion_percent=94,
            current_version_scope=True,
            user_goal="API, CLI, MCP, skill prompts, WorkBuddy, Hermes, Doubao Office Task Mode, and OpenClaude-style agents should expose the same product truth.",
            implemented=(
                "Connector catalog, release readiness, and investigation packet are shared across surfaces.",
                "Desktop-agent surfaces can consume shared investigation packets, connector metadata, and QYYJT queue data.",
                "/api/docs now declares one_click_readiness source-resilience and relationship-graph readiness fields so desktop-agent hosts can consume the first-screen handoff contract.",
                "MCP and CLI investigation entrypoints now expose and enforce the same bounded execution controls as the API contract: retrieval concurrency 1..20, fanout rounds 0..3, max fanout tasks 0..80, and query timeout 0.1..120 seconds.",
                "Release runtime_delivery, MCP descriptions, and Codex MCP smoke now cover source_repair_priority_queue and one_click_readiness source_repair_* fields.",
                "/api/docs now declares report export directory bundles, print-package operational handoff, and DOCX renderer capabilities as explicit subfields instead of only a coarse report_exports bucket.",
                "/api/docs now declares portable_html first_screen_handoff_cards, card count, and source path so desktop agents can consume report handoff cards without scraping HTML.",
                "CLI export-dir now writes agent-handoff.json and MCP/API/Agent smokes declare report_exports.directory_bundle.agent_handoff so desktop agents can consume task routing without parsing the full packet.",
                "Release readiness now exposes source_health_operator_handoff and source_health_release_warnings so API/MCP/agent hosts can find connector recovery and release warning fields without parsing monitor internals.",
                "API docs, MCP server descriptions, deploy manifest, release contract, and host smokes now declare the agent-handoff relationship graph audit summary as a shared runtime surface.",
                "API docs, release contract, CLI export-dir, Codex MCP smoke, REST smoke, and agent-host smoke now declare one_click_readiness.capital_verification_queue as a shared runtime surface.",
                "API docs and release contract now declare one_click_readiness capital-pressure and graph-capital source-family summaries as shared runtime surfaces.",
                "API docs, release contract, CLI export-dir, REST smoke, Codex MCP smoke, and agent-host smoke now declare report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue as a shared runtime surface.",
                "API docs, release contract, CLI export-dir, REST smoke, Codex MCP smoke, and agent-host smoke now declare report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue as a shared runtime surface.",
                "API docs and release contract now declare subject-profile controller candidate, control-path, and relationship-edge source-family provenance as shared runtime surfaces.",
                "REST/MCP investigation packets now expose report_exports.agent_decision_digest directly, so desktop-agent hosts can route delivery status, blockers, queue counts, and first action without running --export-dir.",
                "Directory agent-handoff now exposes delivery_files, trust_boundaries, decision_digest, and a ranked next_actions queue so desktop agents can open the right files, preserve evidence boundaries, and continue work without re-parsing the full packet.",
                "Node offline-fixture fallback export-dir now writes a Python-compatible manifest plus agent-handoff with delivery_files, trust_boundaries, decision_digest, and next_actions while marking DOCX unavailable instead of emitting a fake Word file.",
                "Runtime MCP tool descriptions and deploy MCP manifest now declare directory_bundle.agent_handoff delivery_files, trust_boundaries, decision_digest, and next_actions so MCP hosts can discover the executable handoff schema.",
                "API smoke, Codex MCP smoke, agent-host smoke, and acceptance now assert directory_bundle manifest_fields plus agent_handoff schema_fields include delivery_files, delivery_checklist, trust_boundaries, decision_digest, and next_actions.",
                "Directory export manifests now expose file_manifest sha256 rows, delivery_checklist, and a bounded agent_summary, plus bin/verify_report_bundle.py for executable bundle verification before desktop agents share or archive outputs.",
                "Report bundle verification now rejects stale or tampered manifest agent_summary rows when delivery_decision, decision_digest, delivery_status, acceptance_closure_status, bundle_verification, report_visibility, capital_risk_panel, source resilience, work-queue counts, or top actions drift from agent-handoff.json.",
                "Report directory bundles now expose verifier_output_fields for ok and agent_handoff verifier booleans, and API/CLI/MCP/agent smokes assert desktop agents can find delivery_checklist_present, bundle_integrity_present, and bundle_ready_to_verify without parsing verifier prose.",
                "Release readiness now exposes latest_acceptance_evidence with npm run acceptance timestamp, passed/skipped test counts, smoke status, default one-click result, and covered runtime surfaces for desktop-agent delivery decisions.",
            ),
            gaps=(
                "New runtime status surfaces must be added everywhere, not just in one UI.",
                "Some host-facing prose docs still lag behind executable contracts.",
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
                "CLI export-dir writes agent-handoff.json with operator work, QYYJT section batches, source-health snapshot, capital/relationship top steps, and report handoff cards.",
                "Release readiness lists source-health warning/recovery handoff fields and focused proof tests.",
                "API, CLI export-dir, MCP descriptions, and host smokes expose report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit.",
                "API, CLI export-dir, release contract, and host smokes expose one_click_readiness.capital_verification_queue.",
                "API docs and release contract expose one_click_readiness.capital_pressure_source_family_summary and graph_capital_exposure_source_family_summary.",
                "API, CLI export-dir, release contract, and host smokes expose report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue.",
                "API, CLI export-dir, release contract, and host smokes expose report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue.",
                "API docs and release contract expose subject-profile controller candidates, control paths, and relationship edges with source-family provenance.",
                "REST/MCP/agent-host smokes fail if report_exports.agent_decision_digest or its first_action is missing from investigation packets.",
                "REST/MCP/agent-host smokes fail if /api/release omits latest_acceptance_evidence or if the latest acceptance timestamp/counts drift from the recorded full run.",
                "Directory agent-handoff and report-export manifest expose delivery_files, bundle_integrity, delivery_checklist, trust_boundaries, decision_digest, agent_summary, and next_actions as machine-readable fields.",
                "bin/verify_report_bundle.py fails if report-export-manifest.json.agent_summary drifts from agent-handoff.json delivery_decision, decision_digest, delivery_status, acceptance_closure_status, bundle_verification, report_visibility, capital_risk_panel, source resilience, work-queue counts, or top actions.",
                "Node fallback export-dir writes agent-handoff.json and an explicit DOCX-unavailable manifest with manifest_fields, decision_digest, and aligned agent-handoff schema fields when Python child processes are unavailable.",
                "Runtime MCP server and deploy MCP manifest descriptions expose agent-handoff delivery_files, trust_boundaries, decision_digest, and next_actions.",
                "Smoke and acceptance gates fail if manifest_fields omit delivery_checklist or agent_summary, or if agent-handoff schema_fields omit delivery_files, bundle_integrity, delivery_checklist, trust_boundaries, decision_digest, or next_actions.",
                "REST/MCP/agent-host smokes fail if report_exports.directory_bundle.verifier_output_fields omits ok, agent_handoff.schema_valid, delivery_checklist_present, bundle_integrity_present, or bundle_ready_to_verify.",
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
            completion_percent=94,
            current_version_scope=True,
            user_goal="Keep the 13-role expert-team identity visible as a real product surface, not only marketing copy.",
            implemented=(
                "Persona surface appears in release metadata, investigation packet, report Markdown, API, CLI/MCP, and skill-prompt surfaces.",
                "Role grouping and routing principles are available in runtime payloads.",
                "Investigation persona roles now carry concrete lane_bindings, packet_fields, report_sections, and handoff_task values so hosts can route work to actual investigation surfaces instead of decorative copy.",
                "Shared persona brief now exposes runtime_lane_bindings for operator work queues, QYYJT public-origin handoff, reliance limitations, capital verification, and relationship audit fields.",
                "Agent-host smoke and release-contract tests now assert persona bindings stay synchronized with product-critical runtime handoffs.",
            ),
            gaps=(
                "Shared persona brief and host-facing prose still need a final wording consistency pass.",
            ),
            next_actions=(
                "Run a final cross-surface wording pass after P0 runtime output stabilizes.",
                "Keep persona display as a support layer under retrieval/report correctness.",
            ),
            acceptance_gates=(
                "Investigation packet exposes persona_surface.",
                "Active persona roles expose packet_fields and lane_bindings tied to real investigation data.",
                "Release/API persona brief exposes runtime_lane_bindings tied to product-critical one_click_readiness fields.",
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
            completion_percent=94,
            current_version_scope=True,
            user_goal="When a source or run fails, the user should know what failed and what can still be trusted.",
            implemented=(
                "Risk pipeline already tracks queried sources, failed sources, diagnostics, and monitor-run stores.",
                "Timeouts and partial coverage are visible in summary paths.",
                "Risk-discovery runs now expose run_id in result, summary, and graph export.",
                "Source diagnostics now carry trace_id and normalized failure_category values.",
                "Investigation packets now expose source_failure_summary and render a report-level runtime diagnostics section.",
                "Source diagnostics now expose coverage_recovery_decision with the next ready or blocked recovery step, blocker reason, key fields, and a report-visible recommended action.",
                "Source diagnostics now expose source_resilience_profile with score, status, failure pressure, coverage pressure, recovery readiness, blockers, and recommended action.",
                "Source diagnostics now aggregate recurring source failure patterns by source, failure category, and domain, then expose operator actions in source_failure_summary, monitoring_seed, and report Markdown.",
                "Quality gate now consumes source_resilience_profile directly, so retrieval health problems remain visible even when legacy summary.failed_sources is empty.",
                "One-click readiness now surfaces source_resilience_profile status, score, operator-recovery flag, and recommended action for desktop-agent hosts.",
                "Source resilience now carries the recommended recovery step with source, domain, priority, status, query family, key fields, ready-to-run flag, and blocked reason so agents can act without re-parsing diagnostics.",
                "Monitor run ledgers now persist bounded source_diagnostics and expose cross-run failure_category_counts plus recurring_failure_patterns through source_health_trends and /api/monitor/source-health.",
                "Recurring source failures now produce monitoring_seed.source_repair_priority_queue and one_click_readiness source_repair_* fields so desktop agents can prioritize connector, authorization, timeout, and recovery work without re-parsing diagnostics.",
                "Investigation packets now expose monitoring_seed.source_health_trend_snapshot plus one_click_readiness source_health_trend_* fields, giving agents a bounded per-packet source-health view without enabling background monitoring.",
                "One-click readiness now exposes a merged operator_work_queue across source repair, recovery, public-origin fallback, capital verification, relationship audit, and coverage gaps.",
                "Persisted source-health trends now produce connector_recovery_queue and release_readiness_warnings for CLI/API operators.",
                "Release readiness now exposes source_health_operator_handoff and a proof-defined source_health_release_warnings runtime surface for on-demand operator review.",
                "One-click readiness, print handoff cards, directory agent-handoff exports, and agent-host smokes now share a source_health_trend_digest so hosts can route top source repair without reconstructing the bounded snapshot.",
                "Directory agent-handoff exports now mirror monitoring_seed.recovery_execution_queue under source_health, so recovery routing carries ready and blocked execution rows into desktop-agent handoffs.",
                "API, WorkBuddy, and report paths inherit the same diagnostics through the shared investigation packet.",
            ),
            gaps=(
                "Metrics aggregation and health dashboard are not production-grade.",
                "Cross-run trend injection into live investigation packets remains additive future hardening beyond the current bounded packet snapshot.",
            ),
            next_actions=(
                "Keep bounded trend snapshots synchronized across API, MCP, agent-host, and report surfaces.",
                "Keep release readiness warnings framed as connector work, not subject-risk verdicts.",
            ),
            acceptance_gates=(
                "Every retrieval run has a stable run identifier and failure category.",
                "Report tail can distinguish timeout, auth, empty result, parser, and source unavailable.",
                "Investigation packet exposes source_failure_summary for API/UI reuse.",
                "Investigation packet and report expose source_resilience_profile without treating retrieval health as a subject risk verdict.",
                "Repeated source/category/domain failures appear in recurring_failure_patterns with concrete operator_action guidance.",
                "Quality gate warnings include source_resilience_needs_operator_recovery when source_resilience_profile requires operator recovery.",
                "One-click readiness exposes source resilience recovery status and the recommended operator action.",
                "One-click readiness and monitoring_seed expose source repair priority counts and top repair action.",
                "Monitoring seed exposes source_health_trend_snapshot and one-click readiness exposes source_health_trend_top_source without enabling current-release background monitoring.",
                "One-click readiness and agent handoffs expose source_health_trend_digest with monitoring disabled and top source repair routing.",
                "Directory agent-handoff exposes source_health.recovery_execution_queue without treating source recovery tasks as subject-risk verdicts.",
                "Source-health trends expose connector_recovery_queue and release_readiness_warnings from persisted monitor runs.",
                "Release readiness exposes source-health trend entrypoints, recovery queue fields, warning fields, and proof tests.",
            ),
            runtime_surfaces=("RiskDiscoveryPipeline.diagnostics", "RiskMonitorRunStore.source_health_trends", "report tail", "/api/investigate", "/api/monitor/source-health", "/api/release"),
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
            status="in_progress",
            completion_percent=44,
            current_version_scope=True,
            user_goal="Deliver investigation results in three productized forms: printable government-style Word documents, full-fidelity premium HTML reports, and a third owner-confirmed package format still to be confirmed.",
            implemented=(
                "The runtime investigation_packet already carries structured JSON, report Markdown, evidence ledger, graph data, diagnostics, and report-visible cognition sections that output generators can consume.",
                "Static workbench export already proves the packet can be converted to portable HTML without dropping core packet data.",
                "Runtime report_exports now include a print_package manifest with red-head front matter, full-body preservation, chart manifest, image-evidence appendix contract, print layout, and acceptance checklist for desktop/office agents.",
                "A minimal stdlib DOCX renderer now consumes the print_package manifest, preserves the full Markdown body, writes a Word-openable .docx file from the CLI via --export-docx, and exposes red-head front matter, chart plan, image appendix inventory, and renderer checklist sections.",
                "The DOCX runtime renderer now includes a table-of-contents section inventory, native Word tables for chart and image evidence manifests, and a Word footer PAGE field, so print/binding output has concrete TOC, table, and page-number structure instead of a text-only package.",
                "The print_package manifest and DOCX renderer now include an operational handoff appendix with source recovery, source repair, capital verification, relationship audit, public-origin, and coverage-gap follow-up cards for desktop agents.",
                "The DOCX renderer now embeds already-collected local or data-uri image evidence into word/media while preserving remote image URLs as safe inventory rows without fetching network assets.",
                "The Python and Node CLIs can now export a report file bundle with DOCX, portable HTML, Markdown, and JSON packet outputs while preserving stdout automation behavior.",
                "The CLI can now write a complete report directory bundle with DOCX, portable HTML, Markdown, JSON packet, and a machine-readable export manifest in one command.",
                "The DOCX print renderer now emits official document metadata, a red-head separator rule, and native chart summary panels, moving the Word output closer to a printable government-style package without reducing the investigation body.",
                "The print_package manifest now includes a machine-readable delivery_checklist with required output files, agent open order, print binding requirements, and quality checks; the DOCX renderer prints this checklist as Word tables for agent and print-operator handoff.",
                "Directory export manifests now mirror delivery_checklist and include file_manifest sha256 rows plus a bounded agent_summary with delivery status, acceptance closure status, trust-boundary clean-conclusion state, source resilience status, QYYJT public-origin work, capital verification, relationship audit status, work-queue counts, and top next actions.",
                "A stdlib bin/verify_report_bundle.py verifier now checks manifest file size and sha256 rows plus agent-handoff decision_digest schema, and fails on tampered report bundle files or broken handoff routing.",
                "The print_package manifest now includes source_provenance_appendix with evidence source index rows plus relationship_capital_appendix with capital exposure, relationship edge evidence status, capital verification queue, and relationship graph audit queue; the DOCX renderer prints both appendices for audit-ready binding.",
                "Runtime report_exports now include a premium_html profile, portable_html.premium_profile mirror, full-report-preservation HTML markers, print/reduced-motion CSS, and a visible premium visual QA checklist so desktop agents can verify the premium HTML contract before final visual polish.",
            ),
            gaps=(
                "Word output still needs final official-layout polish: stricter binding/print styling, richer official-document typography, optional authorized remote image fetching, and template refinement beyond the current TOC/table/chart-panel/page-footer/local-image DOCX renderer.",
                "Premium HTML now has a runtime contract and full-fidelity markers, but still needs final visual asset pipeline, richer interaction, chart/image presentation polish, and production design pass beyond the current portable renderer.",
                "The requested third productized output form is not specified yet.",
            ),
            next_actions=(
                "Refine the Word renderer against the print_package manifest: tighten printable red-head layout, optional authorized remote image fetching, and official-document typography while preserving the current full-body, TOC, native-table, chart-panel, local-image, and page-footer contract.",
                "Deepen the premium HTML renderer from the current runtime contract into a polished screen-review package: keep no data reduction, preserve premium markers, add richer chart/image panels, and build the asset pipeline without generic AI look, large purple gradients, or low-effort color ramps.",
                "Ask the owner to confirm the third output form before implementation starts.",
            ),
            acceptance_gates=(
                "Word output opens as a .docx file with red-head official-document front matter, official metadata, red-head separator rule, concise due-diligence result brief, full investigation body, delivery checklist, source provenance appendix, evidence source index, relationship/capital appendix, chart plan, native chart summary panels, native Word tables for chart/image/operational handoff inventories, table-of-contents section inventory, PAGE footer, and print/binding layout contract; later polish must tighten typography and optional authorized remote image handling.",
                "CLI export commands write DOCX, portable HTML, Markdown, JSON, agent-handoff, manifest file_manifest, delivery_checklist, and manifest agent_summary files without breaking stdout-based automation, and the verifier fails on size/hash mismatches or broken agent-handoff routing schema.",
                "HTML output displays the complete investigation result without shortening evidence, report, graph, diagnostics, or next-action content.",
                "HTML output passes a visual QA checklist for premium interaction, immersive presentation, chart/image richness, liquid-glass or 3D treatment where appropriate, and avoids generic AI-style gradients, low-effort purple themes, and data-loss shortcuts.",
                "Third output form has an owner-confirmed specification before engineering starts.",
            ),
            runtime_surfaces=("core/report_docx.py", "bin/investigate.py --export-docx", "premium html export"),
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
