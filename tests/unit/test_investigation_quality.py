#!/usr/bin/env python3
"""Tests for product-facing investigation quality gate."""
from __future__ import annotations

from core.investigation_quality import evaluate_investigation_packet


def test_quality_gate_penalizes_coverage_gaps_without_blocking_review() -> None:
    gate = evaluate_investigation_packet(
        summary={
            "execution_state": "evidence_found",
            "evidence_count": 2,
            "failed_sources": ["ofac_consolidated_sanctions_xml"],
            "coverage": {
                "domains_without_evidence": ["administrative_risk"],
                "missing_domains": [],
            },
        },
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {
                "record_kind": "evidence",
                "authority": "official",
                "access": "public",
            }
        ],
        enterprise_cognition={
            "financial": {"revenue": 100},
            "evidence_gaps": ["industry and product evidence missing"],
        },
        report_markdown="## 财务认知\nrevenue=100",
    )

    payload = gate.to_dict()
    assert payload["ok"] is True
    assert payload["score"] < 100
    assert payload["status"] == "usable_with_warnings"
    assert "source_failures_present" in payload["warnings"]
    assert "coverage_gaps_present" in payload["warnings"]
    assert "enterprise_cognition_gaps_present" in payload["warnings"]
    assert payload["next_actions"]


def test_source_diagnostics_route_administrative_gaps_to_creditchina() -> None:
    from core.investigation_diagnostics import build_source_failure_summary

    source_summary = build_source_failure_summary(
        {"execution_state": "partial_coverage"},
        {
            "retrieval_summary": {
                "coverage": {
                    "missing_domains": ["administrative_risk"],
                    "domains_without_evidence": [],
                }
            },
            "source_diagnostics": [],
        },
    )

    action = source_summary["coverage_recovery_actions"][0]
    assert action["domain"] == "administrative_risk"
    assert action["suggested_source"] == "creditchina_public"
    assert source_summary["coverage_recovery_summary"]["top_next_action"]["suggested_source"] == "creditchina_public"


def test_source_diagnostics_marks_recovery_steps_ready_when_connector_available() -> None:
    from core.investigation_diagnostics import build_source_failure_summary

    source_summary = build_source_failure_summary(
        {"execution_state": "partial_coverage"},
        {
            "retrieval_summary": {
                "coverage": {
                    "missing_domains": ["administrative_risk"],
                    "domains_without_evidence": [],
                },
                "source_routing": {
                    "configured_sources": ["creditchina_public"],
                    "available_sources": ["creditchina_public"],
                    "smoke_tested_sources": ["creditchina_public"],
                    "explicit_only_sources": [],
                    "health_reports": {
                        "creditchina_public": {"ok": True, "status": "up"},
                    },
                },
            },
            "source_diagnostics": [],
        },
    )

    readiness = source_summary["coverage_recovery_execution_readiness"]
    assert readiness["ready_count"] >= 1
    assert readiness["ready_steps"][0]["source"] == "creditchina_public"
    assert readiness["ready_steps"][0]["status"] == "ready"
    assert readiness["ready_steps"][0]["priority"] == "P0"
    decision = source_summary["coverage_recovery_decision"]
    assert decision["decision"] == "run_ready_recovery_step"
    assert decision["ready_to_run"] is True
    assert decision["recommended_step"]["source"] == "creditchina_public"
    assert decision["recommended_step"]["status"] == "ready"
    assert decision["retry_policy"]["retryable"] is True
    assert decision["retry_policy"]["max_attempts"] == 3
    assert decision["retry_policy"]["backoff"] == "exponential_jitter"
    assert decision["retry_policy"]["timeout_seconds"] > 0
    assert "Capture" in decision["next_action"] or "capture" in decision["next_action"]
    resilience = source_summary["source_resilience_profile"]
    assert resilience["recommended_step"]["source"] == "creditchina_public"
    assert resilience["recommended_step"]["status"] == "ready"
    assert resilience["retry_policy"] == decision["retry_policy"]
    assert resilience["recommended_step_ready_to_run"] is True
    assert resilience["recommended_step_blocked_reason"] == ""

    from core.investigation import _recovery_execution_queue

    queue = _recovery_execution_queue(readiness)
    assert queue["ready_to_run"] is True
    assert queue["queued_count"] >= 1
    assert queue["queue"][0]["source"] == "creditchina_public"
    assert queue["queue"][0]["priority"] == "P0"
    assert queue["queue"][0]["status"] == "queued"
    assert queue["queue"][0]["retry_policy"]["retryable"] is True


def test_source_diagnostics_decision_explains_blocked_recovery_step() -> None:
    from core.investigation_diagnostics import build_source_failure_summary

    source_summary = build_source_failure_summary(
        {"execution_state": "partial_coverage"},
        {
            "retrieval_summary": {
                "coverage": {
                    "missing_domains": ["ownership_control"],
                    "domains_without_evidence": [],
                },
                "source_routing": {
                    "configured_sources": ["qyyjt"],
                    "available_sources": [],
                    "explicit_only_sources": ["qyyjt"],
                    "health_reports": {"qyyjt": {"ok": True, "enabled": False}},
                },
            },
            "source_diagnostics": [],
        },
    )

    decision = source_summary["coverage_recovery_decision"]

    assert decision["decision"] == "enable_or_add_connector_before_retry"
    assert decision["ready_to_run"] is False
    assert decision["blocked_count"] > 0
    assert decision["recommended_step"]["status"] in {
        "connector_required",
        "explicit_enable_required",
        "configured_unavailable",
    }
    assert decision["retry_policy"]["retryable"] is False
    assert decision["retry_policy"]["max_attempts"] == 0
    assert decision["retry_policy"]["backoff"] == "blocked_until_source_enabled"
    assert "before retrying ownership_control" in decision["next_action"]
    resilience = source_summary["source_resilience_profile"]
    assert resilience["recommended_step"]["domain"] == "ownership_control"
    assert resilience["retry_policy"] == decision["retry_policy"]
    assert resilience["recommended_step_ready_to_run"] is False
    assert resilience["recommended_step_blocked_reason"] in {
        "connector_required",
        "explicit_enable_required",
        "configured_unavailable",
    }


def test_source_diagnostics_routes_supply_chain_to_public_contract_sources() -> None:
    from core.investigation_diagnostics import build_source_failure_summary

    source_summary = build_source_failure_summary(
        {"execution_state": "partial_coverage"},
        {
            "retrieval_summary": {
                "coverage": {
                    "missing_domains": ["trade_supply_chain"],
                    "domains_without_evidence": [],
                }
            },
            "source_diagnostics": [],
        },
    )

    action = source_summary["coverage_recovery_actions"][0]
    assert action["domain"] == "trade_supply_chain"
    assert "sam_gov_public" in action["fallback_sources"]
    assert "usaspending_public" in action["fallback_sources"]
    assert "contract_award_id" in action["key_fields"]
    assert action["origin_priority"][0]["tier"] == "official_public"
    assert "sam_gov_public" in action["origin_priority"][0]["sources"]
    assert action["origin_priority"][2]["tier"] == "global_public_procurement"
    assert "ungm_public" in action["origin_priority"][2]["sources"]


def test_recovery_execution_queue_prioritizes_p0_ready_steps() -> None:
    from core.investigation import _recovery_execution_queue

    queue = _recovery_execution_queue(
        {
            "blocked_count": 0,
            "ready_steps": [
                {
                    "step_id": "REC-P1",
                    "domain": "trade_supply_chain",
                    "priority": "P1",
                    "tier": "official_public",
                    "source": "government_procurement_public",
                    "status": "ready",
                },
                {
                    "step_id": "REC-P0",
                    "domain": "financing_capital_markets",
                    "priority": "P0",
                    "tier": "official_public",
                    "source": "chinamoney_public",
                    "status": "ready",
                },
            ],
        }
    )

    assert queue["queue"][0]["step_id"] == "REC-P0"
    assert queue["queue"][0]["priority"] == "P0"


def test_recovery_execution_queue_builds_actionable_work_order() -> None:
    from core.investigation import _recovery_execution_queue

    queue = _recovery_execution_queue(
        {
            "blocked_count": 0,
            "ready_steps": [
                {
                    "step_id": "COVERAGE-MISSING-ADMINISTRATIVE_RISK-STEP-1",
                    "domain": "administrative_risk",
                    "priority": "P0",
                    "tier": "official_public",
                    "source": "creditchina_public",
                    "status": "ready",
                }
            ],
        },
        [
            {
                "step_id": "COVERAGE-MISSING-ADMINISTRATIVE_RISK-STEP-1",
                "action_id": "COVERAGE-MISSING-ADMINISTRATIVE_RISK",
                "domain": "administrative_risk",
                "priority": "P0",
                "tier": "official_public",
                "source": "creditchina_public",
                "query_family": "company + administrative penalty/regulatory notice",
                "key_fields": ["penalty_date", "issuing_authority", "penalty_amount"],
                "admission_rule": "official_public can become evidence after provenance/entity-match gates.",
            }
        ],
        subject="Demo Recovery Co.",
    )

    first = queue["queue"][0]
    assert first["query"] == "Demo Recovery Co. + administrative penalty/regulatory notice"
    assert first["key_fields"] == ["penalty_date", "issuing_authority", "penalty_amount"]
    assert first["admission_rule"].startswith("official_public")
    assert first["replay_route"]["type"] == "source_recovery_replay_route"
    assert first["replay_route"]["tool"] == "investigate_company"
    assert first["replay_route"]["tool_arguments"]["company"] == "Demo Recovery Co."
    assert first["replay_route"]["tool_arguments"]["target_recovery"]["source"] == "creditchina_public"
    assert first["replay_route"]["command"].startswith('npx wallstreet-tieling --investigate "Demo Recovery Co."')
    assert first["retry_limit"] == first["replay_route"]["retry_limit"]
    assert first["done_condition"] == first["replay_route"]["done_condition"]
    assert "low-risk conclusion" in first["non_reliance_caveat"]
    assert queue["work_order"]["subject"] == "Demo Recovery Co."
    assert queue["work_order"]["ready_queries"][0]["query"] == first["query"]
    assert queue["work_order"]["ready_queries"][0]["replay_route"] == first["replay_route"]
    assert queue["work_order"]["ready_queries"][0]["non_reliance_caveat"] == first["non_reliance_caveat"]


def test_quality_gate_still_blocks_when_no_factual_evidence() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "all_sources_failed", "evidence_count": 0},
        risk_brief={"verdict": "no_material_risk_found_from_available_evidence"},
        profile_brief={"controller_candidate_count": 0},
        evidence_ledger=[],
        enterprise_cognition={},
        report_markdown="",
    )

    payload = gate.to_dict()
    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert "no_factual_evidence" in payload["blockers"]
    assert "clean_verdict_with_blockers" in payload["blockers"]


def test_quality_gate_warns_when_public_leads_have_no_factual_evidence() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 3},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {"record_kind": "lead", "authority": "public_web", "access": "public"},
            {"record_kind": "lead", "authority": "public_web", "access": "public"},
        ],
        enterprise_cognition={
            "public_capital_profile": {"row_count": 2},
            "public_goods_profile": {"row_count": 1},
        },
        report_markdown="## Public Lead Profiles\ncorroboration-needed leads",
    )

    payload = gate.to_dict()
    assert payload["ok"] is False
    assert "no_factual_evidence" in payload["blockers"]
    assert "public_leads_need_corroboration" in payload["warnings"]
    assert any("upgrade public leads" in action for action in payload["next_actions"])


def test_quality_gate_treats_licensed_evidence_as_official_or_licensed() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 1},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 0},
        evidence_ledger=[
            {
                "record_kind": "evidence",
                "authority": "commercial",
                "access": "licensed",
            }
        ],
        enterprise_cognition={},
        report_markdown="",
    )

    payload = gate.to_dict()
    assert payload["ok"] is True
    assert "official_or_licensed_evidence_present" in payload["strengths"]
    assert "no_official_or_licensed_evidence" not in payload["warnings"]


def test_quality_gate_warns_on_single_source_supply_chain_profile() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 3},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {
                "record_kind": "evidence",
                "authority": "official",
                "access": "public",
            }
        ],
        enterprise_cognition={
            "supply_chain_profile": {
                "corroboration_status": "single_source_needs_corroboration",
                "customer_count": 1,
                "supplier_count": 1,
            },
            "evidence_gaps": [],
        },
        report_markdown="## 供应链与商业版图\nsingle_source_needs_corroboration",
    )

    payload = gate.to_dict()
    assert payload["ok"] is True
    assert "supply_chain_single_source_needs_corroboration" in payload["warnings"]
    assert any("corroborate customer" in action for action in payload["next_actions"])


def test_quality_gate_strengthens_multi_source_supply_chain_profile() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 4},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {
                "record_kind": "evidence",
                "authority": "official",
                "access": "public",
            }
        ],
        enterprise_cognition={
            "supply_chain_profile": {
                "corroboration_status": "multi_source_supported",
                "source_count": 2,
            },
            "evidence_gaps": [],
        },
        report_markdown="## 供应链与商业版图\nmulti_source_supported",
    )

    payload = gate.to_dict()
    assert "supply_chain_corroborated" in payload["strengths"]
    assert "supply_chain_single_source_needs_corroboration" not in payload["warnings"]


def test_quality_gate_strengthens_auditable_relationship_edges() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 2},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {"admission": "fact", "authority": "official", "source": "registry", "id": "ev-rel-1"},
        ],
        enterprise_cognition={
            "relationship_network": {
                "relation_count": 1,
                "top_edges": [
                    {
                        "from_name": "Demo Co.",
                        "to_name": "Owner A",
                        "relation_type": "shareholder",
                        "admission": "fact",
                        "evidence_ids": ["ev-rel-1"],
                    }
                ],
            },
            "evidence_gaps": [],
        },
        report_markdown="## relationship network\nedge_audit: admission=fact | evidence=ev-rel-1",
    )

    payload = gate.to_dict()
    assert "relationship_edges_auditable" in payload["strengths"]
    assert "relationship_edges_missing_evidence_ids" not in payload["warnings"]
    assert "relationship_edges_need_fact_admission" not in payload["warnings"]


def test_quality_gate_warns_on_weak_or_unaudited_relationship_edges() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 2},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {"admission": "fact", "authority": "official", "source": "registry", "id": "ev-1"},
        ],
        enterprise_cognition={
            "relationship_network": {
                "relation_count": 2,
                "top_edges": [
                    {
                        "from_name": "Demo Co.",
                        "to_name": "Lead A",
                        "relation_type": "related",
                        "admission": "lead",
                        "evidence_ids": [],
                    }
                ],
            },
            "evidence_gaps": [],
        },
        report_markdown="## relationship network\nedge_audit: admission=lead",
    )

    payload = gate.to_dict()
    assert "relationship_edges_need_fact_admission" in payload["warnings"]
    assert "relationship_edges_missing_evidence_ids" in payload["warnings"]
    assert any("fact-admitted" in action for action in payload["next_actions"])
    assert any("evidence_ids" in action for action in payload["next_actions"])


def test_quality_gate_warns_on_claim_corroboration_conflicts() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 3},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[
            {"admission": "fact", "authority": "official", "source": "official_registry_public"},
            {"admission": "fact", "access": "licensed", "source": "licensed_trade_database"},
        ],
        enterprise_cognition={
            "claim_corroboration": {
                "multi_source_supported_count": 1,
                "conflict_field_count": 1,
            },
            "evidence_gaps": [],
        },
        report_markdown="## 来源出处\nclaim corroboration: multi_source_supported=1 | conflicts=1",
    )

    payload = gate.to_dict()
    assert payload["ok"] is True
    assert "claim_conflicts_need_review" in payload["warnings"]
    assert "multi_source_claims_present" in payload["strengths"]
    assert any("conflicting claim fields" in action for action in payload["next_actions"])


def test_quality_gate_warns_on_verified_controller_conflicts() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 3},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 2},
        evidence_ledger=[
            {"admission": "fact", "authority": "official", "source": "official_registry_public"},
            {"admission": "fact", "access": "licensed", "source": "qyyjt_api:ubo_path"},
        ],
        enterprise_cognition={
            "investigation_report_card": {
                "dd_summary": {
                    "people_lane_summary": {
                        "controller_conflict_summary": {
                            "status": "conflicting_verified_controller_claims",
                            "verified_count": 2,
                            "preferred_controller": "Licensed Owner A",
                            "competing_candidates": ["Official Owner B"],
                            "review_required": True,
                        }
                    }
                }
            },
            "evidence_gaps": [],
        },
        report_markdown="## 控制权画像\ncontroller review: status=conflicting_verified_controller_claims",
    )

    payload = gate.to_dict()
    assert payload["ok"] is True
    assert "verified_controller_conflicts_need_review" in payload["warnings"]
    assert any("competing verified controller" in action for action in payload["next_actions"])


def test_quality_gate_keeps_competing_public_controller_lead_as_review_only() -> None:
    gate = evaluate_investigation_packet(
        summary={"execution_state": "evidence_found", "evidence_count": 2},
        risk_brief={"verdict": "risk_review_required"},
        profile_brief={"controller_candidate_count": 2},
        evidence_ledger=[
            {"admission": "fact", "access": "licensed", "source": "qyyjt_api:ubo_path"},
        ],
        enterprise_cognition={
            "investigation_report_card": {
                "dd_summary": {
                    "people_lane_summary": {
                        "controller_conflict_summary": {
                            "status": "verified_controller_with_competing_leads",
                            "verified_count": 1,
                            "preferred_controller": "Licensed Owner",
                            "competing_candidates": ["Public Executive Lead"],
                            "review_required": True,
                        }
                    }
                }
            },
            "evidence_gaps": [],
        },
        report_markdown="## 控制权画像\ncontroller review: status=verified_controller_with_competing_leads",
    )

    payload = gate.to_dict()
    assert "controller_leads_need_review" in payload["warnings"]
    assert "verified_controller_conflicts_need_review" not in payload["warnings"]
    assert any("competing controller leads" in action for action in payload["next_actions"])


def test_quality_gate_reports_source_failures() -> None:
    from core.investigation_quality import evaluate_investigation_packet
    gate = evaluate_investigation_packet(
        summary={"evidence_count": 1, "execution_state": "partial_coverage", "failed_sources": ["public_web_search"]},
        risk_brief={"verdict": "needs_review"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[{"record_kind": "evidence", "authority": "official", "source": "test"}],
        enterprise_cognition={"evidence_gaps": []},
        report_markdown="## 行业认知\nindustry=tech\n",
    )
    assert "source_failures_present" in gate.warnings, f"Expected source_failures_present warning, got {gate.warnings}"


def test_quality_gate_consumes_source_resilience_profile_without_summary_failed_sources() -> None:
    from core.investigation_quality import evaluate_investigation_packet

    gate = evaluate_investigation_packet(
        summary={"evidence_count": 1, "execution_state": "partial_coverage"},
        risk_brief={"verdict": "needs_review"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[{"record_kind": "evidence", "authority": "official", "source": "registry"}],
        enterprise_cognition={"evidence_gaps": []},
        report_markdown="## 行业认知\nindustry=technology\n",
        source_failure_summary={
            "source_resilience_profile": {
                "status": "needs_operator_recovery",
                "failure_count": 2,
                "recommended_action": "Enable or add connector for gsxt_shareholder_tabs before retrying ownership_control.",
            }
        },
    )

    payload = gate.to_dict()
    assert "source_resilience_needs_operator_recovery" in payload["warnings"]
    assert "source_failures_present" not in payload["warnings"]
    assert any("gsxt_shareholder_tabs" in action for action in payload["next_actions"])


def test_quality_gate_surfaces_ready_coverage_recovery_decision() -> None:
    gate = evaluate_investigation_packet(
        summary={"evidence_count": 1, "execution_state": "partial_coverage"},
        risk_brief={"verdict": "needs_review"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[{"record_kind": "evidence", "authority": "official", "source": "test"}],
        enterprise_cognition={"evidence_gaps": []},
        report_markdown="## 琛屼笟璁ょ煡\nindustry=tech\n",
        source_failure_summary={
            "coverage_recovery_decision": {
                "decision": "run_ready_recovery_step",
                "ready_to_run": True,
                "next_action": "execute connector-ready source with bounded fanout",
                "recommended_step": {
                    "domain": "ownership_control",
                    "source": "gsxt_shareholder_tabs",
                },
            }
        },
    )

    payload = gate.to_dict()
    assert "coverage_recovery_ready" in payload["strengths"]
    assert any("ownership_control" in action and "gsxt_shareholder_tabs" in action for action in payload["next_actions"])


def test_quality_gate_surfaces_blocked_coverage_recovery_decision() -> None:
    gate = evaluate_investigation_packet(
        summary={"evidence_count": 1, "execution_state": "partial_coverage"},
        risk_brief={"verdict": "needs_review"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[{"record_kind": "evidence", "authority": "official", "source": "test"}],
        enterprise_cognition={"evidence_gaps": []},
        report_markdown="## 琛屼笟璁ょ煡\nindustry=tech\n",
        source_failure_summary={
            "coverage_recovery_decision": {
                "decision": "blocked_recovery_step",
                "ready_to_run": False,
                "next_action": "enable licensed source or configure parser",
                "recommended_step": {
                    "domain": "financing_capital_markets",
                    "suggested_source": "qyyjt_authorized_api",
                },
            }
        },
    )

    payload = gate.to_dict()
    assert "coverage_recovery_blocked" in payload["warnings"]
    assert any("financing_capital_markets" in action and "qyyjt_authorized_api" in action for action in payload["next_actions"])


def test_source_timeout_visible_in_diagnostics() -> None:
    from core.investigation import build_investigation_packet
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        md=pk.get("report_markdown","")
        # should not crash
        assert isinstance(md,str)
    asyncio.run(run())

def test_empty_source_visible_not_risky() -> None:
    from core.investigation_quality import InvestigationQualityGate
    gate=InvestigationQualityGate(
        evidence_ledger=[{"record_kind":"evidence","authority":"official","source":"test"}],
        enterprise_cognition={"source_statuses":[{"source_name":"qyyjt_bond","status":"empty"}]},
        report_markdown="## 数据源状态\n- qyyjt_bond: 搜索无结果",
    )
    result=gate.inspect()
    assert "数据源状态" in result.report_markdown

def test_blocked_source_creates_coverage_gap() -> None:
    from core.investigation_quality import InvestigationQualityGate
    gate=InvestigationQualityGate(
        evidence_ledger=[{"record_kind":"evidence","authority":"official","source":"test"}],
        enterprise_cognition={"source_statuses":[{"source_name":"qyyjt_bond","status":"blocked"}]},
        report_markdown="## 数据源状态\n- qyyjt_bond: 受限",
    )
    result=gate.inspect()
    assert result.score<100


def test_empty_source_visible_not_risky() -> None:
    from core.investigation import build_investigation_packet

    graph = {
        "company": "Demo Empty Source Co.",
        "summary": {"execution_state": "evidence_found", "evidence_count": 1, "risk_event_count": 0},
        "risk_events": [],
        "evidence": [{
            "source": "official_fixture",
            "title": "Official record",
            "claims": ["Registry fact: status=active"],
            "confidence": 0.8,
            "source_profile": {"authority": "official", "access": "public"},
            "entity_match": {"level": "exact", "score": 1.0},
        }],
        "diagnostics": {
            "source_diagnostics": [{
                "source": "qyyjt_bond",
                "status": "empty",
                "failure_category": "empty_result",
            }],
            "subject_profile": {},
        },
    }
    packet = build_investigation_packet(graph, input_text="Demo Empty Source Co.").to_dict()
    assert packet["source_failure_summary"]["by_failure_category"] == {"empty_result": 1}
    assert "clean_verdict_with_blockers" not in packet["quality_gate"]["blockers"]


def test_blocked_source_creates_coverage_gap() -> None:
    from core.investigation_quality import evaluate_investigation_packet

    gate = evaluate_investigation_packet(
        summary={"evidence_count": 1, "execution_state": "partial_coverage", "failed_sources": ["qyyjt_bond"]},
        risk_brief={"verdict": "needs_review"},
        profile_brief={"controller_candidate_count": 1},
        evidence_ledger=[{"record_kind": "evidence", "authority": "official", "source": "test"}],
        enterprise_cognition={"evidence_gaps": []},
        report_markdown="## Data Source Status\n- qyyjt_bond: blocked",
    )
    assert "source_failures_present" in gate.warnings
    assert gate.score < 100


def test_classify_source_type_official():
    from core.investigation import _classify_source_type
    assert _classify_source_type("gsxt_gov") == "official_registry"
    assert _classify_source_type("court_wenshu") == "official_registry"

def test_classify_source_type_commercial():
    from core.investigation import _classify_source_type
    assert _classify_source_type("qyyjt_api") == "commercial_registry"

def test_classify_source_type_financial():
    from core.investigation import _classify_source_type
    assert _classify_source_type("bond_calendar") == "financial_data"

def test_negative_gate_blocked():
    from core.investigation_quality import _negative_source_gate
    r = _negative_source_gate([{"source_name":"qyyjt_bond","status":"blocked"}])
    assert r["source_blocked_count"] == 1

def test_negative_gate_clean():
    from core.investigation_quality import _negative_source_gate
    r = _negative_source_gate([{"source_name":"gsxt","status":"retrieved"}])
    assert r["source_blocked_count"] == 0 and r["source_empty_count"] == 0
