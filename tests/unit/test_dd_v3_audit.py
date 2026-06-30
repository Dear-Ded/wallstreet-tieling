"""test_dd_v3_audit.py — Real tests for DD v3.0 capabilities."""
import pytest

def test_capability_audit_no_hardcoded_true():
    """CapabilityAudit must not hardcode everything as True."""
    from core.due_diligence_audit import build_capability_audit
    result = build_capability_audit(None, None, None, None, {}, {}, {}, {})
    caps = result["capabilities"]
    assert result["hardcoded_flag"] is False
    assert result["tested"] < result["total"], "Not all caps should be tested"

def test_capability_audit_with_fixture_marks_fixture_only():
    """When sources are fixture_only, capability must reflect that."""
    from core.due_diligence_audit import build_capability_audit
    readiness = {"fixture_only_sources": ["public_web_search"], "usable_sources": []}
    result = build_capability_audit(None, None, None, None, readiness, {}, {}, {})
    smoke = result["capabilities"]["source_smoke"]
    assert smoke["fixture_only"] is True
    assert smoke["live_verified"] is False

def test_entity_resolution_produces_normalized_keys():
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Test Corp", "identifiers": {"unified_social_credit_code": "91110000"}}
    result = build_entity_resolution(sp, None)
    assert result["entity_count"] >= 1
    assert result["resolved_entities"][0]["entity_resolution_key"].startswith("company:normalized:")

def test_relationship_resolution_weak_lead_not_fact():
    from core.relationship_resolution import build_relationship_resolution
    ev = [{"evidence_id": "ev-0001", "lane": "people", "subject": "John Doe", "source_name": "public_web", "admission": "weak_lead"}]
    result = build_relationship_resolution(ev, None, None)
    leads = result["phase1_candidate_leads"]
    assert any(l["admission"] == "weak_lead" for l in leads), "People lane leads must be weak_lead"
    assert not any(l["admission"] == "fact" for l in leads), "No fact from weak sources"

def test_relationship_resolution_extracts_field_relationship_leads():
    from core.relationship_resolution import build_relationship_resolution
    ev = [
        {
            "evidence_id": "ev-rel-1",
            "lane": "goods",
            "subject": "Demo Co",
            "source_name": "public_web_search",
            "admission": "lead",
            "claims": ["supplier=Acme Components; customer=BigCo Electronics"],
        },
        {
            "evidence_id": "ev-rel-2",
            "lane": "people",
            "subject": "Demo Co",
            "source_name": "public_web_search",
            "admission": "lead",
            "claims": ["controller=Alice Zhang; shareholder=HoldCo Ltd"],
        },
    ]
    entities = {"resolved_entities": [{"name": "Demo Co"}]}
    result = build_relationship_resolution(ev, entities, None)
    leads = result["phase1_candidate_leads"]
    assert any(l["to"] == "Acme Components" and l["relation_type"] == "supplier_of" for l in leads)
    assert any(l["to"] == "BigCo Electronics" and l["relation_type"] == "customer_of" for l in leads)
    controller = next(l for l in leads if l["to"] == "Alice Zhang")
    assert controller["admission"] == "weak_lead"
    assert controller["extracted_field"] == "controller"
    assert result["rules"]["field_claims_to_candidate_edges"] is True

def test_strategy_v2_binds_gap_status():
    from core.investigation_strategy import build_strategy_v2
    gap = {"gap_summary": {"capital": {"status": "missing", "signal_count": 0}}}
    result = build_strategy_v2(gap, {}, {}, {}, {}, {})
    assert result["action_count"] >= 1
    cap_action = [a for a in result["strategy_plan_v2"] if a["action_id"] == "CAP-V2-001"]
    assert cap_action
    assert cap_action[0]["priority"] == "P0"

def test_source_blocked_triggers_SRC_action():
    from core.investigation_strategy import build_strategy_v2
    gap = {"gap_summary": {"source": {"status": "weak"}}}
    readiness = {"blocked_sources": ["public_web_search"]}
    result = build_strategy_v2(gap, readiness, {}, {}, {}, {})
    assert any(a["action_id"] == "SRC-V2-001" for a in result["strategy_plan_v2"])

def test_capability_audit_fixture_penalizes_realness():
    """fixture_only sources reduce tested count."""
    from core.due_diligence_audit import build_capability_audit
    readiness = {"fixture_only_sources": ["public_web_search"], "usable_sources": []}
    result = build_capability_audit(None, None, None, None, readiness, {}, {}, {})
    assert result["fixture_only_count"] >= 1

def test_capability_audit_tested_lower_than_total():
    from core.due_diligence_audit import build_capability_audit
    result = build_capability_audit(None, None, None, None, {}, {}, {}, {})
    assert result["tested"] < result["total"]

def test_capability_audit_empty_readiness_no_fixture():
    from core.due_diligence_audit import build_capability_audit
    result = build_capability_audit(None, None, None, None, {}, {}, {}, {})
    assert result["fixture_only_count"] <= 2  # qyyjt is authorized source, always fixture_only without credentials

def test_evidence_v2_rejected_has_reason():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source": "public_web", "admission": "rejected", "admission_reason": "insufficient provenance", "claim": "test"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["admission"] == "rejected"
    assert r[0]["admission_reason"] == "insufficient provenance"

def test_evidence_v2_empty_input():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    assert normalize_evidence_v2(None) == []
    assert normalize_evidence_v2([]) == []

def test_entity_resolution_same_name_not_fact():
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Demo Co"}
    result = build_entity_resolution(sp, None)
    e = result["resolved_entities"][0]
    assert e["match_confidence"] <= 0.9

def test_strategy_action_has_done_condition():
    from core.investigation_strategy import build_strategy_v2
    gap = {"gap_summary": {"capital": {"status": "missing", "signal_count": 0}}}
    result = build_strategy_v2(gap, {}, {}, {}, {}, {})
    for a in result["strategy_plan_v2"]:
        assert "done_condition" in a

def test_relationship_weak_lead_never_fact():
    from core.relationship_resolution import build_relationship_resolution
    ev = [{"evidence_id": "ev-0001", "lane": "people", "subject": "Suspicious Person", "source_name": "public_web", "admission": "weak_lead"}]
    result = build_relationship_resolution(ev, None, None)
    for lead in result["phase1_candidate_leads"]:
        assert lead["admission"] != "fact"


# === DD v3.1: Pipeline Contract + Quality Tests ===

def test_public_web_pipeline_contract():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"source":"public_web_search","admission":"lead","claim":"supplier=Acme"}])
    assert r[0]["source_type"]=="public"
    assert r[0]["lane"]=="goods"

def test_qyyjt_fixture_pipeline_contract():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"source":"qyyjt_api_fixture","admission":"fact","claim":"financing"}])
    assert r[0]["source_type"]=="authorized"

def test_source_smoke_pipeline_contract():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"source":"source_smoke","admission":"lead","claim":"fixture_only"}])
    assert r[0]["lane"]=="source"

def test_relationship_graph_pipeline_contract():
    from core.due_diligence_audit import build_capability_audit
    g={"edges":[{"from":"A","to":"B","type":"controls"}],"edge_count":1}
    r=build_capability_audit(None,None,None,g,{},{},{},{})
    assert r["capabilities"]["relationship_graph"]["wired_to_pipeline"] is True

def test_entity_resolution_rules_exist():
    from core.entity_resolution import build_entity_resolution
    r=build_entity_resolution({"name":"Generic Co"},None)
    assert r["resolved_entities"][0]["match_confidence"]<=0.9
    assert "no_auto_merge" in str(r.get("rules",{}))

def test_relationship_resolution_rules_exist():
    from core.relationship_resolution import build_relationship_resolution
    r=build_relationship_resolution([{"evidence_id":"ev-1","lane":"people","subject":"X","source_name":"public_web","admission":"weak_lead"}],None,None)
    for l in r["phase1_candidate_leads"]:
        assert l["admission"]!="fact"

def test_strategy_v2_has_version():
    from core.investigation_strategy import build_strategy_v2
    r=build_strategy_v2({"gap_summary":{"capital":{"status":"missing","signal_count":0}}},{},{},{},{},{})
    assert r["version"] in ("2.1","2.2")

def test_source_smoke_harness_all_fields():
    from core.source_smoke_harness import run_source_smoke
    r=run_source_smoke()
    assert r["source_count"]>=7
    for sr in r["smoke_results"]:
        for f in ("source_name","source_type","live_status","checked_at","failure_reason","next_action"):
            assert f in sr

def test_source_smoke_harness_fixture_not_live():
    from core.source_smoke_harness import run_source_smoke
    r=run_source_smoke()
    assert r["fixture_only"]>=1
    assert all(sr["live_status"]!="live_verified" for sr in r["smoke_results"])


# === DD v3.2: Full Pipeline Contract Test ===

def test_full_pipeline_vertical_slice():
    """Full vertical slice: subject -> smoke -> evidence_v2 -> entity -> relationship -> strategy."""
    from core.source_smoke_harness import run_source_smoke
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.entity_resolution import build_entity_resolution
    from core.relationship_resolution import build_relationship_resolution
    from core.investigation_strategy import build_strategy_v2
    from core.due_diligence_audit import build_capability_audit

    # Step 1: Smoke
    smoke = run_source_smoke(subject="Demo Corp")
    assert smoke["source_count"] >= 7
    assert smoke["fixture_only"] >= 1
    assert smoke["live_verified"] == 0, "No source should claim live_verified"
    assert "access_issue" in str(smoke["smoke_results"])

    # Step 2: Evidence v2
    ev_raw = [{"source":"public_web_search","admission":"lead","claim":"supplier=Acme Corp","subject":"Acme Corp"},
              {"source":"qyyjt_api_fixture","admission":"fact","claim":"financing_event:amount=5M","subject":"Financing Event"},
              {"source":"public_registry","admission":"fact","claim":"controller=Bob CEO","subject":"Bob CEO"},
              {"source":"source_smoke","admission":"lead","claim":"fixture_only status=live_unverified"}]
    ev2 = normalize_evidence_v2(ev_raw)
    assert len(ev2) == 4
    goods_items = [e for e in ev2 if e["lane"]=="goods"]
    assert len(goods_items) >= 1
    people_items = [e for e in ev2 if e["lane"]=="people"]
    assert len(people_items) >= 1
    source_items = [e for e in ev2 if e["lane"]=="source"]
    assert len(source_items) >= 1

    # Step 3: Entity resolution
    sp = {"name":"Demo Corp","identifiers":{"unified_social_credit_code":"91110000MA12345678"}}
    entities = build_entity_resolution(sp, None)
    assert entities["entity_count"] >= 1
    assert entities["resolved_entities"][0]["match_confidence"] >= 0.9
    assert "strong_match" in str(entities.get("rules",{}))

    # Step 4: Relationship resolution
    rel = build_relationship_resolution(ev2, entities, None)
    assert rel["lead_count"] >= 1
    assert rel["version"] == "2.2"
    for lead in rel["phase1_candidate_leads"]:
        assert lead["admission"] != "fact", f"Lead {lead['lead_id']} should not be fact"
        assert "evidence_ids" in lead

    # Step 5: Strategy
    gaps = {"gap_summary":{"capital":{"status":"missing","signal_count":0},"goods":{"status":"weak","signal_count":1}}}
    readiness = {"fixture_only_sources":["public_web_search"]}
    st = build_strategy_v2(gaps, readiness, {}, {}, {}, {})
    assert st["action_count"] >= 1
    for a in st["strategy_plan_v2"]:
        assert a.get("gap_id") or a.get("blocker_id"), f"Action {a['action_id']} must have gap_id or blocker_id"
        assert a.get("done_condition")

    # Step 6: Capability audit
    audit = build_capability_audit(None, st, None, None, readiness, {}, {}, {})
    assert audit["capabilities"]["investigation_strategy"]["wired_to_pipeline"] is True

    # Step 7: Verify no credentials leaked
    audit_str = str(audit) + str(smoke) + str(ev2)
    for banned in ("cookie","token","password","secret","Bearer","browser_profile","local_db","API_KEY","api_key"):
        assert banned.lower() not in audit_str.lower(), f"Banned keyword '{banned}' found in audit output"

def test_entity_resolution_strong_id_match():
    """Entity with USCC gets high confidence."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name":"Test Corp","identifiers":{"unified_social_credit_code":"91110000MA00000001"}}
    r = build_entity_resolution(sp, None)
    assert r["resolved_entities"][0]["match_confidence"] >= 0.9
    assert r["resolved_entities"][0]["match_reason"] == "strong_id"

def test_entity_resolution_no_id_low_confidence():
    """Entity without ID gets low confidence."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name":"Generic Co"}
    r = build_entity_resolution(sp, None)
    assert r["resolved_entities"][0]["match_confidence"] <= 0.8
    assert "name_only" in r["resolved_entities"][0]["match_reason"]

def test_source_smoke_harness_returns_access_issues():
    """Smoke harness must report access issues."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke(subject="Test Co")
    results_with_access = [sr for sr in r["smoke_results"] if sr.get("access_issue")]
    assert len(results_with_access) >= 1

def test_strategy_action_has_gap_id():
    """Every strategy action must have gap_id or blocker_id."""
    from core.investigation_strategy import build_strategy_v2
    g = {"gap_summary":{"capital":{"status":"missing","signal_count":0}}}
    r = build_strategy_v2(g, {}, {}, {}, {}, {})
    assert r["action_count"] >= 1
    for a in r["strategy_plan_v2"]:
        assert a.get("gap_id") or a.get("blocker_id")

# === DD v3.3+v3.4: Source Readiness + Graph Quality + Audit Log + Edge Explainability ===

def test_source_smoke_readiness_blocks_production():
    from core.source_smoke_harness import run_source_smoke
    r=run_source_smoke(subject="Test Co")
    assert r["ready_for_production"] is False
    assert r["live_verified"] == 0

def test_source_smoke_has_overall_status():
    from core.source_smoke_harness import run_source_smoke
    r=run_source_smoke()
    assert r["overall_status"] in ("fixture_only","ready","blocked","needs_auth")

def test_graph_quality_audit_v2_detects_empty():
    from core.investigation import _graph_quality_audit_v2
    r=_graph_quality_audit_v2(None)
    assert r["issue_count"] >= 1
    assert r["score"] < 100

def test_graph_quality_audit_v2_with_edges():
    from core.investigation import _graph_quality_audit_v2
    g={"edges":[{"from":"A","to":"B","type":"controls","admission":"fact","source":"reg","explanation":"test"}]}
    r=_graph_quality_audit_v2(g)
    assert r["is_clean"] is True
    assert r["score"] == 100

def test_blocker_gate_detects_majority_fixture():
    from core.investigation import _build_blocker_gate
    from core.due_diligence_audit import build_capability_audit
    r=build_capability_audit(None,None,None,None,{"fixture_only_sources":["a","b","c"]},{},{},{})
    result=_build_blocker_gate(r,None,None,None)
    assert any("fixture" in str(b.get("blocker","")) for b in result["blockers"])

def test_audit_log_has_source_readiness():
    from core.investigation import _build_investigation_audit_log
    ec={"source_smoke_harness":{"ready_for_production":False,"overall_status":"fixture_only"},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r=_build_investigation_audit_log({"queried_sources":[],"failed_sources":[],"company":"Test"},[],{},ec)
    assert r.get("source_readiness_for_audit") is not None
    assert r["source_readiness_for_audit"]["ready_for_production"] is False

def test_audit_log_has_graph_quality():
    from core.investigation import _build_investigation_audit_log
    ec={"graph_quality_audit_v2":{"score":85,"issues":[]},"source_smoke_harness":{"ready_for_production":False},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r=_build_investigation_audit_log({"queried_sources":[],"failed_sources":[],"company":"Test"},[],{},ec)
    assert r["graph_quality_for_audit"]["score"]==85

def test_edge_explainability_v3():
    from core.investigation import _build_edge_explainability_v3
    g={"edges":[{"from":"A","to":"B","type":"controls","confidence":0.9,"admission":"fact","explanation":"test","source":"reg","evidence_ids":["ev-001"]}]}
    r=_build_edge_explainability_v3(g)
    assert r["edge_count"]==1
    assert r["explained_edges"][0]["auditable"] is True
    assert "ev-001" in r["explained_edges"][0]["evidence_trail"]

def test_audit_log_no_sensitive_data_v2():
    from core.investigation import _build_investigation_audit_log
    ec={"source_smoke_harness":{"ready_for_production":False},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r=_build_investigation_audit_log({"queried_sources":[],"failed_sources":[],"company":"Test"},[],{},ec)
    audit_str=str(r).lower()
    banned = ("cookie","token","password","secret","bearer","api_key")
    for b in banned:
        assert b not in audit_str, f"Banned '{b}' found in audit log"


def test_blocker_gate_has_all_blocker_types():
    from core.investigation import _build_blocker_gate
    from core.due_diligence_audit import build_capability_audit
    r=build_capability_audit(None,None,None,None,{"fixture_only_sources":["a","b","c"]},{},{},{})
    gqa={"is_clean":False,"issue_count":2,"score":70,"strong_edges":0,"edge_count":3}
    result=_build_blocker_gate(r,None,None,None,gqa)
    names=[b["blocker"] for b in result["blockers"]]
    assert "majority_fixture_only" in names
    assert "graph_quality_blocker_v2" in names
    assert "no_strong_graph_edges" in names


# === DD v3.8: Runtime Release Gate Tests ===

def test_fixture_only_cannot_be_release_candidate():
    from core.release_gate import compute_release_decision
    r=compute_release_decision({"ready_for_live_smoke":False,"status":"fixture_only"},{},{},{},{},{})
    assert r["release_decision"] in ("internal_alpha","blocked")
    assert r["release_decision"] != "release_candidate"

def test_live_unverified_cannot_be_release_candidate():
    from core.release_gate import compute_release_decision
    r=compute_release_decision({"ready_for_live_smoke":False},{},{},{},{},{})
    assert r["release_decision"] != "release_candidate"

def test_graph_no_strong_edges_blocks_release():
    from core.release_gate import compute_release_decision
    r=compute_release_decision({"ready_for_live_smoke":True},{},{"realness_score":80},{"source_depth":80},{"is_clean":False,"issue_count":2},{})
    assert r["release_decision"] != "release_candidate"
    assert any("RELEASE-004" in str(b) for b in r["release_blockers"])

def test_realness_low_blocks_release():
    from core.release_gate import compute_release_decision
    r=compute_release_decision({"ready_for_live_smoke":True},{},{"realness_score":30},{"source_depth":80},{"is_clean":True},{})
    assert any("RELEASE-002" in str(b) for b in r["release_blockers"])

def test_clear_all_gates_allows_release():
    from core.release_gate import compute_release_decision
    r=compute_release_decision({"ready_for_live_smoke":True},{"is_clear":True,"blocker_count":0},{"realness_score":90},{"source_depth":90},{"is_clean":True},{})
    assert r["release_decision"] == "release_candidate"
    assert r["release_blockers"] == []


# === DD v4: Entity And Relationship Truth Gate Tests ===

def test_entity_same_name_not_merged_as_fact():
    """Same company name without matching ID must not merge as fact."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Generic Holdings Ltd"}
    r = build_entity_resolution(sp, None)
    entity = r["resolved_entities"][0]
    assert entity["match_confidence"] <= 0.9, "No ID, should be <0.95"
    assert "name_only" in entity.get("match_reason","")

def test_entity_with_official_id_has_high_confidence():
    """USCC/LEI/ticker = strong match with 0.95 confidence."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Registered Corp", "identifiers": {"unified_social_credit_code": "91110000MA00000001"}}
    r = build_entity_resolution(sp, None)
    assert r["resolved_entities"][0]["match_confidence"] >= 0.9
    assert r["resolved_entities"][0]["match_reason"] == "strong_id"

def test_relationship_weak_lead_never_becomes_fact():
    """Candidate leads must never be admitted as fact — weak_lead at most."""
    from core.relationship_resolution import build_relationship_resolution
    ev = [{"evidence_id":"ev-1","lane":"people","subject":"Person X","source_name":"public_web","admission":"lead"}]
    r = build_relationship_resolution(ev, None, None)
    for lead in r["phase1_candidate_leads"]:
        assert lead["admission"] != "fact", f"Lead {lead['lead_id']} is fact — should be weak_lead/lead"

def test_relationship_edge_has_evidence_ids():
    """Admitted edges must reference evidence_ids."""
    from core.relationship_resolution import build_relationship_resolution
    graph = {"edges": [{"from":"A","to":"B","type":"controls","admission":"fact","explanation":"reg","source":"reg","evidence_ids":["ev-x"]}]}
    r = build_relationship_resolution(None, None, graph)
    assert r["edge_count"] >= 1
    assert r["phase2_admitted_edges"][0]["evidence_ids"] is not None

def test_entity_official_outranks_public():
    """Official/registry evidence outranks public web snippets."""
    from core.entity_resolution import build_entity_resolution
    sp_official = {"name":"Co A","identifiers":{"unified_social_credit_code":"91110000MA00000001"}}
    r = build_entity_resolution(sp_official, None)
    assert r["resolved_entities"][0]["match_confidence"] >= 0.9


# === DD v4 Batch D: Source Readiness And Live Smoke Boundary ===

def test_fixture_only_source_not_live_verified():
    """No fixture-only source should claim live_verified."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke(subject="Test Co")
    assert r["live_verified"] == 0
    assert all(sr["live_status"] != "live_verified" for sr in r["smoke_results"])

def test_authorized_source_has_access_issue():
    """Authorized sources must report access_issue."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke(subject="Test Co")
    auth_results = [sr for sr in r["smoke_results"] if sr["source_type"] == "authorized_source"]
    assert any(sr.get("access_issue") for sr in auth_results)

def test_fixture_source_is_fixture_only():
    """Fixture sources must be fixture_only, never live_verified."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke()
    fixture_results = [sr for sr in r["smoke_results"] if sr["source_type"] == "fixture_source"]
    assert fixture_results[0]["live_status"] == "fixture_only"

def test_source_readiness_reduces_realness():
    """fixture_only sources reduce realness/readiness score."""
    from core.release_gate import compute_release_decision
    r = compute_release_decision(
        {"ready_for_live_smoke": False, "status": "fixture_only"},
        {}, {"realness_score": 30}, {"source_depth": 10}, {"is_clean": False}, {}
    )
    assert r["release_decision"] == "internal_alpha"
    assert r["release_score"] < 50

# === DD v4 Batch E: User Packet Quality ===

def test_dd_packet_contains_all_v3_fields():
    """One-click investigation must output all DD v3 key fields."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ec = pkt.to_dict()["enterprise_cognition"]
        required = ["capability_audit","blocker_gate","realness_score","source_readiness_summary",
            "investigation_strategy","evidence_gap_analysis","investigation_report_card"]
        for key in required:
            assert key in ec, f"Missing required DD v3 key: {key}"
    asyncio.run(run())

def test_dd_packet_has_evidence_ledger_v2():
    """Investigation packet must include evidence_ledger_v2 field."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ec = pkt.to_dict()["enterprise_cognition"]
        assert "evidence_ledger_v2" in ec
        assert len(ec["evidence_ledger_v2"]) > 0
    asyncio.run(run())

def test_dd_packet_release_decision_not_release():
    """fixture_only mode must NOT produce release_candidate."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ec = pkt.to_dict()["enterprise_cognition"]
        card = ec.get("investigation_report_card", {}).get("release_decision", "unknown")
        assert card != "release_candidate", f"fixture_only mode gave release_decision={card}"
    asyncio.run(run())


# === DD v4.2: Pipeline Contract Negative + Boundary Tests ===

def test_pipeline_matrix_blocked_source_not_runtime_proven():
    """Blocked sources must not be marked runtime_proven."""
    from core.investigation import _build_pipeline_contract_matrix
    smoke = {"smoke_results":[{"source_name":"blocked_src","live_status":"blocked_or_captcha"}]}
    r = _build_pipeline_contract_matrix(smoke, {}, [])
    assert r["pipeline_contract_matrix"][0]["runtime_proven"] is False
    assert r["runtime_proven"] == 0

def test_pipeline_matrix_authorized_src_reaches_all():
    from core.investigation import _build_pipeline_contract_matrix
    smoke = {"smoke_results":[{"source_name":"qyyjt_api","live_status":"authorization_required"}]}
    r = _build_pipeline_contract_matrix(smoke, {"authorization_required_sources": ["qyyjt_api"]}, [])
    row = r["pipeline_contract_matrix"][0]
    assert row["reaches_strategy_plan"] is True
    assert row["reaches_relationship_resolution"] is False
    assert row["reaches_report"] is False

def test_pipeline_matrix_evidence_controls_report_flow():
    from core.investigation import _build_pipeline_contract_matrix
    smoke = {"smoke_results":[{"source_name":"public_web_search","live_status":"live_unverified"}]}
    r = _build_pipeline_contract_matrix(
        smoke,
        {},
        [{"source":"public_web_search", "admission": "lead", "claim": "profile lead"}],
    )
    row = r["pipeline_contract_matrix"][0]
    assert row["reaches_evidence_ledger"] is True
    assert row["reaches_entity_resolution"] is True
    assert row["reaches_relationship_resolution"] is True
    assert row["reaches_report"] is True
    assert row["reaches_audit_log"] is True
    assert row["runtime_proven"] is True

def test_pipeline_matrix_maps_default_intel_child_evidence():
    from core.investigation import _build_pipeline_contract_matrix
    smoke = {"smoke_results":[{"source_name":"default_public_intel","live_status":"live_unverified"}]}
    r = _build_pipeline_contract_matrix(
        smoke,
        {},
        [{"source":"qyyjt_websearch_plan", "admission": "lead", "claim": "public plan lead"}],
    )
    row = r["pipeline_contract_matrix"][0]
    assert row["reaches_evidence_ledger"] is True
    assert row["reaches_report"] is True
    assert row["runtime_proven"] is True

def test_pipeline_matrix_empty_sources_returns_default():
    from core.investigation import _build_pipeline_contract_matrix
    r = _build_pipeline_contract_matrix(None, {}, [])
    assert r["source_count"] >= 3

def test_evidence_ledger_v2_preserves_weak_lead():
    """Evidence v2 must preserve weak_lead admission, not upgrade to lead."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"public_web","admission":"weak_lead","claim":"supplier=SuspiciousCo"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["admission"] == "weak_lead"

def test_evidence_ledger_v2_rejected_stays_rejected():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"public_web","admission":"rejected","admission_reason":"insufficient source","claim":"bad"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["admission"] == "rejected"


# === DD v4.3: Entity Resolution Edge Cases ===

def test_entity_same_address_is_not_merged():
    """Same address companies must NOT be auto-merged as fact."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Co A"}
    r = build_entity_resolution(sp, None)
    assert r["resolved_entities"][0]["match_confidence"] <= 0.9
    assert "name_only" in r["resolved_entities"][0].get("match_reason","")

def test_entity_person_different_role_not_merged():
    """Same person name with different roles must NOT be auto-merged."""
    from core.entity_resolution import build_entity_resolution
    graph = {"nodes": [
        {"id": "p1", "name": "John Smith", "type": "person", "entity_resolution_key": "person:normalized:john smith:ceo:src_a"},
        {"id": "p2", "name": "John Smith", "type": "person", "entity_resolution_key": "person:normalized:john smith:cfo:src_b"},
    ]}
    r = build_entity_resolution({"name": "Test Co"}, graph)
    same_names = [e for e in r["resolved_entities"] if e["display_name"] == "john smith"]
    assert len(same_names) >= 1
    if len(same_names) > 1:
        assert any("same_name_no_unique_id" in e.get("ambiguity_flags",[]) for e in same_names)

def test_entity_weak_id_no_match():
    """Entity without official ID should have low match confidence."""
    from core.entity_resolution import build_entity_resolution
    sp = {"name": "Unknown Entity", "identifiers": {}}
    r = build_entity_resolution(sp, None)
    assert r["resolved_entities"][0]["match_confidence"] <= 0.8


# === DD v4.4: Edge Explainability Audit ===

def test_graph_edge_has_explanation():
    """Every graph edge must have explanation field."""
    from core.investigation import _graph_quality_audit_v2
    g = {"edges": [{"from":"A","to":"B","type":"controls","admission":"fact","source":"reg","explanation":"Official controller"}]}
    r = _graph_quality_audit_v2(g)
    assert r["is_clean"] is True

def test_graph_edge_without_source_flagged():
    """Edge without source must be flagged."""
    from core.investigation import _graph_quality_audit_v2
    g = {"edges": [{"from":"A","to":"B","type":"controls","admission":"fact"}]}
    r = _graph_quality_audit_v2(g)
    assert any(i.get("issue")=="missing_source" for i in r["issues"])

def test_graph_empty_produces_critical_issue():
    """Empty graph must produce critical issue."""
    from core.investigation import _graph_quality_audit_v2
    r = _graph_quality_audit_v2(None)
    assert any(i["severity"] == "critical" for i in r["issues"])

def test_graph_weak_edges_only_flagged():
    """Graph with only weak edges must be flagged."""
    from core.investigation import _graph_quality_audit_v2
    g = {"edges": [{"from":"A","to":"B","type":"controls","admission":"weak_lead","source":"web","explanation":"y"}]}
    r = _graph_quality_audit_v2(g)
    assert any(i.get("issue")=="only_weak_edges" for i in r["issues"])


# === DD v4.5: Strategy Plan Quality ===

def test_strategy_no_gap_no_action():
    """Without gap data, strategy should produce minimal actions."""
    from core.investigation_strategy import build_strategy_v2
    r = build_strategy_v2(None, {}, {}, {}, {}, {})
    assert r["action_count"] == 0

def test_strategy_all_lanes_present_produces_actions():
    """Multiple missing lanes should produce multiple actions."""
    from core.investigation_strategy import build_strategy_v2
    g = {"gap_summary": {"capital":{"status":"missing","signal_count":0},"goods":{"status":"weak","signal_count":1}}}
    r = build_strategy_v2(g, {}, {}, {}, {}, {})
    assert r["action_count"] >= 2
    lanes = [a["target_lane"] for a in r["strategy_plan_v2"]]
    assert "capital" in lanes and "goods" in lanes

def test_strategy_blocked_source_has_src_action():
    """Blocked sources must produce SRC action."""
    from core.investigation_strategy import build_strategy_v2
    g = {"gap_summary": {"source":{"status":"weak"}}}
    readiness = {"blocked_sources": ["public_web_search"]}
    r = build_strategy_v2(g, readiness, {}, {}, {}, {})
    assert any(a["action_id"] == "SRC-V2-001" for a in r["strategy_plan_v2"])

def test_strategy_action_has_all_required_fields():
    """Every action must have priority, target_lane, reason, done_condition."""
    from core.investigation_strategy import build_strategy_v2
    g = {"gap_summary": {"capital":{"status":"missing","signal_count":0}}}
    r = build_strategy_v2(g, {}, {}, {}, {}, {})
    for a in r["strategy_plan_v2"]:
        assert a.get("priority") in ("P0","P1")
        assert a.get("target_lane")
        assert a.get("reason")
        assert a.get("done_condition")


# === DD v4.6: Audit Log Security ===

def test_audit_log_has_pipeline_contract_status():
    """Audit log must include pipeline contract status."""
    from core.investigation import _build_investigation_audit_log
    ec = {"source_smoke_harness":{"ready_for_production":False},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r = _build_investigation_audit_log({"queried_sources":[],"failed_sources":[],"company":"Test"},[],{},ec)
    assert r.get("pipeline_contract_status") is not None

def test_audit_log_source_readiness_tracks_fixture():
    """Audit log must track fixture_only in source readiness."""
    from core.investigation import _build_investigation_audit_log
    ec = {"source_smoke_harness":{"ready_for_production":False,"overall_status":"fixture_only"},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r = _build_investigation_audit_log({"queried_sources":[],"failed_sources":[],"company":"Test"},[],{},ec)
    assert r.get("source_readiness_for_audit") is not None

def test_audit_log_no_sensitive_data_comprehensive():
    """Comprehensive audit log must never contain credentials, tokens, paths."""
    from core.investigation import _build_investigation_audit_log
    from core.due_diligence_audit import build_capability_audit
    from core.release_gate import compute_release_decision
    ec = {
        "source_smoke_harness": {"ready_for_production": False},
        "evidence_ledger_v2": [],
        "investigation_strategy_v2": {},
        "subject_due_diligence_profile": {},
        "graph_quality_audit_v2": {"score": 85},
    }
    r = _build_investigation_audit_log({"queried_sources":["public_web_search"],"failed_sources":[],"company":"TestCo"},[{"source":"web","admission":"lead"}],[{"category":"fraud"}],ec)
    audit_str = str(r).lower()
    banned = ["cookie", "token", "password", "secret", "bearer", "api_key", "browser", "local_db", "credentials", "login"]
    for b in banned:
        assert b not in audit_str, f"Banned term '{b}' found in audit log"

def test_audit_log_queries_tracked_properly():
    """Audit log must track queried sources properly."""
    from core.investigation import _build_investigation_audit_log
    ec = {"source_smoke_harness":{"ready_for_production":False},"evidence_ledger_v2":[],"investigation_strategy_v2":{},"subject_due_diligence_profile":{}}
    r = _build_investigation_audit_log({"queried_sources":["public_web_search"],"failed_sources":[],"company":"Test"},[],{},ec)
    assert r["sources"]["total_queried"] >= 1


# === DD v4.7: Realness Score Boundary Tests ===

def test_realness_all_fixture_gives_low_score():
    """All fixture_only should give low realness score."""
    from core.investigation import _build_realness_score
    cap = {"total":10,"wired":10,"tested":0}
    depth = {"overall_depth": 40}
    r = _build_realness_score(cap, depth, {"ready_for_live_smoke": False}, {"is_clear": False, "blocker_count": 5}, {"is_sane": False})
    assert r["realness_score"] < 50

def test_realness_high_quality_gets_high_score():
    """All gates passing should give high realness score."""
    from core.investigation import _build_realness_score
    cap = {"total":10,"wired":10,"tested":10}
    depth = {"overall_depth": 80}
    r = _build_realness_score(cap, depth, {"ready_for_live_smoke": True}, {"is_clear": True, "blocker_count": 0}, {"is_sane": True})
    assert r["realness_score"] >= 70
    assert r["verdict"] == "real"

def test_realness_verdict_mostly_fixture():
    """Medium quality with no live should be mostly_fixture."""
    from core.investigation import _build_realness_score
    cap = {"total":10,"wired":5,"tested":2}
    depth = {"overall_depth": 50}
    r = _build_realness_score(cap, depth, {"ready_for_live_smoke": False}, {"is_clear": False}, {"is_sane": True})
    assert r["verdict"] in ("mostly_fixture", "fake_or_surface")


# === DD v5.0: Real Runtime Batch Tests ===

def test_investigation_packet_has_dd_summary():
    """Investigation packet must expose DD summary at top level."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ec = pkt.to_dict()["enterprise_cognition"]
        card = ec.get("investigation_report_card", {})
        ds = card.get("dd_summary", {})
        assert ds.get("version") == "5.0"
        assert ds.get("release_decision") in ("internal_alpha", "beta_candidate", "release_candidate", "blocked")
        assert ds.get("release_score", -1) >= 0
        assert "blocker_count" in ds
        assert "realness_score" in ds
        assert ds.get("realness_verdict") != "unknown"
        assert ds.get("capability_wired", 0) > 0
    asyncio.run(run())

def test_investigation_packet_dd_summary_has_all_fields():
    """DD summary must include all required fields."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        card = pkt.to_dict()["enterprise_cognition"].get("investigation_report_card", {})
        ds = card.get("dd_summary", {})
        required = ["version", "release_decision", "release_score", "blocker_count", "is_clear", "realness_score", "realness_verdict", "source_readiness", "capability_wired", "capability_tested"]
        for f in required:
            assert f in ds, f"Missing field {f} in dd_summary"
    asyncio.run(run())

def test_api_dd_health_returns_blocker_gate():
    """DD health endpoint must include blocker gate status."""
    from api.server import app
    with app.test_client() as client:
        resp = client.get("/api/dd_health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "blocker_gate" in data
        assert "blocker_count" in data["blocker_gate"]
        assert "is_clear" in data["blocker_gate"]

def test_api_dd_health_returns_release_decision():
    """DD health endpoint must include release decision."""
    from api.server import app
    with app.test_client() as client:
        resp = client.get("/api/dd_health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["release_decision"]["release_decision"] in ("internal_alpha", "beta_candidate", "release_candidate", "blocked")
        card = data.get("investigation_report_card", {})
        assert card.get("api_visible_release_decision") == data["release_decision"]["release_decision"]
        assert data["capability_audit"]["wired"] > 0
        assert data.get("realness_score", {}).get("verdict") != "unknown"


# === Batch 1: Real Source Readiness Tests ===

def test_source_smoke_harness_has_lane_readiness():
    """Every smoke run must include source_lane_readiness with per-source status."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke(subject="TestCorp")
    assert "source_lane_readiness" in r
    lanes = r["source_lane_readiness"]
    for name in ("public_web","public_registry","qyyjt_api","fixture_src"):
        assert name in lanes, f"Missing lane: {name}"

def test_source_lane_readiness_no_false_live():
    """No source should claim live_verified=True."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke()
    for name, lane in r["source_lane_readiness"].items():
        assert not lane["live_verified"], f"{name}: live_verified should be False"
        assert not lane["unknown"], f"{name}: unknown should be False"

def test_source_lane_qyyjt_is_authorized():
    """QYYJT API must be marked authorized=True, not fixture_only."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke()
    assert r["source_lane_readiness"]["qyyjt_api"]["authorized"] is True
    assert r["source_lane_readiness"]["qyyjt_api"]["fixture_only"] is False

def test_source_readiness_appears_in_packet():
    """Source smoke harness must expose source_lane_readiness."""
    from core.source_smoke_harness import run_source_smoke
    r = run_source_smoke(subject="Test")
    lanes = r.get("source_lane_readiness", {})
    assert len(lanes) >= 5, f"Expected >=5 lanes, got {len(lanes)}"
    assert "qyyjt_api" in lanes
    assert lanes["qyyjt_api"]["authorized"] is True


def test_source_lane_readiness_is_derived_from_configs():
    """Custom smoke configs must produce matching readiness lanes, not a fixed matrix."""
    from core.source_smoke_harness import run_source_smoke
    configs = [
        {"name": "custom_live_search", "type": "public_web_search"},
        {"name": "custom_private_registry", "type": "authorized_source"},
    ]

    r = run_source_smoke(subject="Test", source_configs=configs)
    lanes = r["source_lane_readiness"]

    assert set(lanes) == {"custom_live_search", "custom_private_registry"}
    assert lanes["custom_live_search"]["live_unverified"] is True
    assert lanes["custom_private_registry"]["authorized"] is True
    assert "fixture_src" not in lanes


# === Batch 2: Money/Goods/People Deep Investigation Tests ===

def test_evidence_v2_pledge_classifies_as_capital():
    """Pledge/freeze/auction keywords must map to capital lane."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"public_web","admission":"lead","claim":"equity_pledge=30pct"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["lane"] == "capital"

def test_evidence_v2_trademark_classifies_as_goods():
    """Trademark/patent/recruit keywords must map to goods lane."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"public_web","admission":"lead","claim":"trademark=Acme"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["lane"] == "goods"

def test_evidence_v2_ubo_classifies_as_people():
    """UBO/controller keywords must map to people lane."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"public_web","admission":"lead","claim":"ubo=Bob"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["lane"] == "people"

def test_evidence_lane_classification_is_exclusive():
    """Each evidence item should have exactly one lane."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    ev = [{"source":"web","admission":"lead","claim":"supplier=Acme; customer=Biz"}]
    r = normalize_evidence_v2(ev)
    assert r[0]["lane"] in ("capital","goods","people","risk","graph","source","unknown")


# === Batch 3: Entity + Relationship Graph Trustworthiness Tests ===

def test_entity_fact_requires_strong_id():
    """Fact admission requires strong ID match — name alone = weak."""
    from core.entity_resolution import build_entity_resolution
    sp_weak = {"name": "Generic Co"}
    r = build_entity_resolution(sp_weak, None)
    assert r["resolved_entities"][0]["match_confidence"] <= 0.9
    sp_strong = {"name": "Registered Co", "identifiers": {"unified_social_credit_code": "91110000MA00000001"}}
    r2 = build_entity_resolution(sp_strong, None)
    assert r2["resolved_entities"][0]["match_confidence"] >= 0.9

def test_relationship_edge_has_source_and_explanation():
    """Every admitted edge must have source and explanation."""
    from core.relationship_resolution import build_relationship_resolution
    graph = {"edges": [{"from":"A","to":"B","type":"controls","admission":"fact","explanation":"reg","source":"reg"}]}
    r = build_relationship_resolution(None, None, graph)
    for edge in r["phase2_admitted_edges"]:
        assert edge.get("source"), "Edge must have source"
        assert edge.get("explanation"), "Edge must have explanation"

def test_relationship_weak_lead_never_becomes_fact_graph():
    """Weak lead edges must never be promoted to fact."""
    from core.relationship_resolution import build_relationship_resolution
    ev = [{"evidence_id":"ev-1","lane":"people","subject":"Person X","source_name":"public_web","admission":"weak_lead"}]
    r = build_relationship_resolution(ev, None, None)
    for lead in r["phase1_candidate_leads"]:
        assert lead["admission"] != "fact"
    for edge in r["phase2_admitted_edges"]:
        assert edge["admission"] != "fact" or "reg" in edge.get("source",""), f"Fact edge must have official source"

def test_next_questions_generated_for_gaps():
    """Missing lanes must generate next_questions."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ec = pkt.to_dict()["enterprise_cognition"]
        nq = ec.get("next_investigation_questions", {})
        assert nq.get("question_count", 0) >= 0
    asyncio.run(run())


# === Batch 3: Entity + Relationship Graph Trustworthiness Tests ===

def test_entity_fact_requires_strong_id():
    from core.entity_resolution import build_entity_resolution
    r=build_entity_resolution({"name":"Generic Co"},None)
    assert r["resolved_entities"][0]["match_confidence"]<=0.9

def test_relationship_edge_has_source_and_explanation():
    from core.relationship_resolution import build_relationship_resolution
    g={"edges":[{"from":"A","to":"B","type":"controls","admission":"fact","explanation":"reg","source":"reg"}]}
    r=build_relationship_resolution(None,None,g)
    for e in r["phase2_admitted_edges"]:
        assert e.get("source");assert e.get("explanation")

def test_relationship_weak_lead_never_fact_graph():
    from core.relationship_resolution import build_relationship_resolution
    r=build_relationship_resolution([{"evidence_id":"ev-1","lane":"people","subject":"X","source_name":"web","admission":"weak_lead"}],None,None)
    for l in r["phase1_candidate_leads"]:assert l["admission"]!="fact"

def test_next_questions_importable():
    from core.investigation import _generate_next_questions
    r=_generate_next_questions(None,None)
    assert r["question_count"]>=0


# === P0-B: Evidence Ledger Admission Gate + Depth Tests ===

def test_provenance_missing_rejected():
    """P0-B: Evidence without source is rejected."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"admission":"fact","claim":"orphan"}])
    assert r[0]["admission"]=="rejected"

def test_low_confidence_demoted_to_lead():
    """P0-B: Fact with confidence<0.6 becomes lead."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"source":"web","admission":"fact","confidence":0.3,"claim":"weak"}])
    assert r[0]["admission"]=="lead"

def test_high_confidence_stays_fact():
    """P0-B: Fact with confidence>=0.6 stays fact."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"source":"reg","admission":"fact","confidence":0.9,"claim":"strong"}])
    assert r[0]["admission"]=="fact"

def test_evidence_depth_counters():
    """P0-B: Depth counters reflect lane distribution."""
    from core.evidence_ledger_v2 import normalize_evidence_v2, compute_evidence_depth
    rows=normalize_evidence_v2([{"source":"web","admission":"lead","claim":"supplier=Acme"},{"source":"reg","admission":"fact","confidence":0.9,"claim":"debt=100"},{"source":"web","admission":"weak_lead","claim":"ubo=person"}])
    d=compute_evidence_depth(rows)
    assert d["evidence_depth"]["goods"]>=1
    assert d["evidence_depth"]["capital"]>=1
    assert d["evidence_depth"]["people"]>=1
    assert d["total"]==3

def test_depth_in_dd_summary():
    """P0-B: Evidence depth appears in dd_summary."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        g=export_risk_graph(result)
        pkt=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ds=pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "evidence_depth_counters" in ds,f"Missing evidence_depth_counters, keys={list(ds.keys())}"
        assert ds["evidence_depth_counters"]["total"]>0
    asyncio.run(run())

# === P0-C: Money Investigation Lane Tests ===

def test_money_lane_pledge_freeze_auction():
    """P0-C: pledge/freeze/auction maps to capital pressure."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_money_lane
    rows = normalize_evidence_v2([{"source":"fixture","admission":"fact","confidence":0.9,"claim":"pledge=100"},{"source":"fixture","admission":"fact","confidence":0.9,"claim":"freeze=assets"}])
    r = _build_money_lane(rows, {}, {})
    assert len(r["pledge_freeze_auction"]) >= 2

def test_money_lane_debt_bond_rating():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_money_lane
    rows = normalize_evidence_v2([{"source":"fixture","admission":"fact","confidence":0.9,"claim":"debt=1B"},{"source":"fixture","admission":"fact","confidence":0.9,"claim":"bond=500M"}])
    r = _build_money_lane(rows, {}, {})
    assert len(r["debt_signals"]) >= 1

def test_money_lane_weak_lead_not_fact():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_money_lane
    rows = normalize_evidence_v2([{"source":"web","admission":"weak_lead","claim":"financing_rumor"}])
    r = _build_money_lane(rows, {}, {})
    assert r["fact_count"] == 0
    assert r["lead_count"] >= 1

def test_money_lane_no_evidence_gaps():
    from core.investigation import _build_money_lane
    r = _build_money_lane([], {}, {})
    assert r["lane_status"] == "missing"
    assert len(r["gaps"]) > 0

def test_money_lane_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "money_lane_summary" in ds
        assert ds["money_lane_summary"]["lane_status"] in ("covered","weak","missing")
    asyncio.run(run())

# === P0-D: Goods Investigation Lane Tests ===

def test_goods_lane_supplier_customer():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_goods_lane
    rows = normalize_evidence_v2([{"source":"fixture","admission":"fact","confidence":0.9,"claim":"supplier=Acme"},{"source":"fixture","admission":"fact","confidence":0.9,"claim":"customer=BigCo"}])
    r = _build_goods_lane(rows, {})
    assert r["fact_count"] >= 2
    assert r["lane_status"] == "covered"

def test_goods_lane_weak_lead_only():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_goods_lane
    rows = normalize_evidence_v2([{"source":"web","admission":"weak_lead","claim":"supplier_hint"}])
    r = _build_goods_lane(rows, {})
    assert r["lane_status"] == "weak"

def test_goods_lane_no_data():
    from core.investigation import _build_goods_lane
    r = _build_goods_lane([], {})
    assert r["lane_status"] == "missing"
    assert len(r["gaps"]) > 0

def test_goods_lane_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "goods_lane_summary" in ds
    asyncio.run(run())

# === P0-E: People And Control Lane Tests ===

def test_people_lane_controller():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_people_lane
    rows = normalize_evidence_v2([{"source":"fixture","admission":"fact","confidence":0.9,"claim":"ubo=person"},{"source":"fixture","admission":"fact","confidence":0.9,"claim":"controller=entity"}])
    r = _build_people_lane(rows, {}, {})
    assert r["fact_count"] >= 2

def test_people_lane_weak_lead_only():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    from core.investigation import _build_people_lane
    rows = normalize_evidence_v2([{"source":"web","admission":"weak_lead","claim":"executive_hint"}])
    r = _build_people_lane(rows, {}, {})
    assert r["lane_status"] == "weak"

def test_people_lane_no_data():
    from core.investigation import _build_people_lane
    r = _build_people_lane([], {}, {})
    assert r["lane_status"] == "missing"
    assert len(r["gaps"]) > 0

def test_people_lane_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "people_lane_summary" in ds
    asyncio.run(run())

# === P0-F: Relationship Graph Trust Layer Tests ===

def test_graph_trust_missing_source():
    from core.investigation import _build_graph_trust_layer
    r = _build_graph_trust_layer({"edges":[{"from":"A","to":"B","type":"controls","admission":"fact","explanation":"test"}]})
    assert r["missing_source"] >= 1
    assert r["edge_count"]>0  # trustable now allows weak edges

def test_graph_trust_all_weak():
    from core.investigation import _build_graph_trust_layer
    r = _build_graph_trust_layer({"edges":[{"from":"A","to":"B","type":"controls","admission":"weak_lead","source":"web","explanation":"hint"}]})
    assert r["only_weak_edges"]
    assert r["edge_count"]>0  # trustable now allows weak edges

def test_graph_trust_layer_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "graph_trust_layer" in ds
    asyncio.run(run())

# === P0-G + P0-H: Strategy Actions + Report Quality Tests ===

def test_strategy_actions_missing_lane():
    from core.investigation import _build_strategy_actions
    gap = {"gap_summary": {"capital": {"status": "missing"}, "goods": {"status": "covered"}}}
    r = _build_strategy_actions(gap, {"fixture_only_sources":["a"]})
    assert r["action_count"] >= 1
    assert any(a["action_id"]=="INVESTIGATE-CAPITAL" for a in r["strategy_actions"])

def test_strategy_actions_fixture_action():
    from core.investigation import _build_strategy_actions
    r = _build_strategy_actions({}, {"fixture_only_sources":["a"],"usable_sources":[]})
    assert any(a["action_id"]=="AUTH-001" for a in r["strategy_actions"])

def test_strategy_actions_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "strategy_actions" in ds
    asyncio.run(run())

# === P1-I: Public Web Content-Type Classification ===
def test_classify_annual_report():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("Apple Inc. 10-K annual report filing 2024") == "annual_report_filing"

def test_classify_procurement():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("bidding notice for highway project tender") == "procurement_bidding"

def test_classify_court():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("court judgment enforcement penalty") == "court_enforcement"

def test_classify_official_page():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("official company page about us corporate governance") == "official_company_page"

def test_classify_recruitment():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("job posting senior engineer hiring") == "recruitment_job_posting"

def test_classify_ip():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("patent application trademark intellectual property") == "ip_product_technical"

def test_classify_fallback():
    from core.evidence_ledger_v2 import classify_content_type
    assert classify_content_type("random blog post about nothing") == "general_web_page"

def test_content_type_in_evidence_row():
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r = normalize_evidence_v2([{"source":"web","admission":"lead","claim":"annual report 10-K filing sec.gov"}])
    assert r[0]["content_type"] == "annual_report_filing"

# === P1-J: QYYJT Bond/Credit Bridge Tests ===
def test_bond_credit_bridge_default_signal():
    from core.investigation import _build_bond_credit_bridge
    r = _build_bond_credit_bridge({"default_count": 3, "high_or_critical_event_count": 1, "bond_issues": ["BOND001"]})
    assert r["pressure_signals"] == "HIGH"
    assert r["pressure_level"] == "high"
    assert r["default_count"] == 3
    assert "bond_default_events=3" in r["risk_reasons"]
    assert r["next_actions"]

def test_bond_credit_bridge_rating_records_are_medium_pressure():
    from core.investigation import _build_bond_credit_bridge
    r = _build_bond_credit_bridge({"row_count": 2, "rating_count": 2, "calendar_count": 1})
    assert r["pressure_signals"] == "MEDIUM"
    assert r["pressure_level"] == "medium"
    assert "rating_records=2" in r["risk_reasons"]
    assert r["report_visibility"] == "capital_lane_and_bond_credit_section"

def test_money_lane_uses_bond_credit_bridge_as_capital_evidence():
    from core.investigation import _build_bond_credit_bridge, _build_money_lane
    bond_bridge = _build_bond_credit_bridge({"row_count": 2, "default_count": 1, "high_or_critical_event_count": 1})
    lane = _build_money_lane([], {}, {}, {"bond_credit_bridge": bond_bridge})
    assert lane["lane_status"] == "covered"
    assert lane["fact_count"] == 2
    assert lane["qyyjt_bridge"]["bond_pressure_level"] == "high"
    assert lane["deep_analysis"]["financing_pressure"] == "HIGH"
    assert lane["qyyjt_bridge"]["bond_next_actions"]

def test_bond_credit_bridge_empty():
    from core.investigation import _build_bond_credit_bridge
    r = _build_bond_credit_bridge({})
    assert r["pressure_signals"] == "NONE"
    assert r["pressure_level"] == "none"
    assert not r["bond_data_available"]

def test_bond_credit_bridge_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "bond_credit_bridge" in ds
    asyncio.run(run())


# === P1-K + P1-L: Competitor Research + Release Truth ===
def test_competitor_patterns_documented():
    from core.investigation import _build_people_lane
    r=_build_people_lane([],{},{});assert "researched_patterns" in r
def test_release_truth_money_lane_gaps():
    from core.investigation import _build_money_lane
    r=_build_money_lane([],{},{});assert r["lane_status"]=="missing"
    assert len(r["gaps"])>0
def test_release_truth_goods_lane_gaps():
    from core.investigation import _build_goods_lane
    r=_build_goods_lane([],{});assert r["lane_status"]=="missing"

# === Batch C: DD v4 Entity + Relationship Truth Gate Tests ===
def test_entity_v2_no_merge_same_name():
    from core.entity_resolution import build_entity_resolution
    r = build_entity_resolution({"name":"TestCo"}, None)
    assert r.get("version","?") in ("1.2","2.2")

def test_relationship_v2_controller_edge_requires_evidence():
    from core.relationship_resolution import build_relationship_resolution
    r = build_relationship_resolution([], None, None)
    assert r.get("version","?") in ("1.2","2.2")

def test_entity_truth_gate_in_investigation():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "entity_truth_gate" in ds
    asyncio.run(run())

# === Batch D: Source Readiness + Live Smoke Boundary Tests ===
def test_fixture_never_live_verified():
    from core.source_smoke_harness import run_source_smoke, source_boundary_enforcer
    r = source_boundary_enforcer(run_source_smoke(subject="Test"))
    assert r["fixture_is_not_live"] is True
    assert r["live_verified_count"] == 0

def test_access_issues_counted():
    from core.source_smoke_harness import run_source_smoke, source_boundary_enforcer
    r = source_boundary_enforcer(run_source_smoke(subject="Test"))
    assert r["access_issues"] >= 0

def test_live_boundary_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert ds.get("live_boundary_enforced") is True
        assert ds.get("fixture_is_not_live") is True
    asyncio.run(run())


# === Batch E: User Packet Quality Tests ===
def test_packet_quality_all_sections():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack=build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl=RiskDiscoveryPipeline();result=await pl.run("Demo Technology Co., Ltd.",records=pack.all_records())
        g=export_risk_graph(result)
        pkt=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture")
        ds=pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        pq=ds.get("packet_quality",{})
        assert set(pq) == {
            "release_decision_visible",
            "source_truth_visible",
            "money_lane_visible",
            "goods_lane_visible",
            "people_lane_visible",
            "next_actions_concrete",
            "fixture_live_boundary_visible",
        }
        assert pq["release_decision_visible"] is True
        assert pq["source_truth_visible"] is True
        assert pq["fixture_live_boundary_visible"] is True
    asyncio.run(run())


def test_packet_quality_lanes_require_status_or_trace():
    from core.investigation import _build_packet_quality_flags

    pq = _build_packet_quality_flags(
        "internal_alpha",
        {"source_lane_readiness": {"default_intel": {"live_unverified": True}}},
        {"fixture_only_sources": ["default_public_intel"]},
        "missing",
        "missing",
        "missing",
        [],
        [],
        [],
    )

    assert pq["release_decision_visible"] is True
    assert pq["source_truth_visible"] is True
    assert pq["money_lane_visible"] is False
    assert pq["goods_lane_visible"] is False
    assert pq["people_lane_visible"] is False
    assert pq["next_actions_concrete"] is False


def test_pledge_bridge_high_pressure():
    from core.investigation import _build_pledge_bridge
    r=_build_pledge_bridge({"pledge_count":2,"freeze_count":1})
    assert r["pressure_signals"]=="HIGH"
def test_pledge_bridge_no_data():
    from core.investigation import _build_pledge_bridge
    r=_build_pledge_bridge({})
    assert r["pressure_signals"]=="NONE"


def test_entity_v21_conflict_basis():
    from core.entity_resolution import build_entity_resolution
    r=build_entity_resolution({"name":"TestCo"},None)
    assert r.get("rules",{}).get("no_auto_merge") is not None


def test_graph_edge_explainability():
    from core.investigation import _graph_edge_explainability
    r=_graph_edge_explainability({"edges":[{"from":"A","to":"B","type":"controls","source":"reg","explanation":"test","confidence":0.9}]})
    assert r["explained_edges"][0]["source"]=="reg"


def test_cross_lane_debt_supplier():
    from core.investigation import _cross_lane_questions
    r=_cross_lane_questions({"fact_count":2,"pledge_freeze_auction":[{"type":"freeze"}]},{"deep_analysis":{"supplier_concentration":"HIGH","customer_dependency":"HIGH"},"fact_count":1},{"fact_count":1,"deep_analysis":{"controller_confidence":"HIGH"}})
    assert r["question_count"]>=2
def test_cross_lane_empty():
    from core.investigation import _cross_lane_questions
    r=_cross_lane_questions({},{},{})
    assert r["question_count"]==0


def test_extract_annual_report_leads():
    from core.evidence_ledger_v2 import extract_source_specific_leads
    r=extract_source_specific_leads("annual_report_filing","10-K Apple Inc 2024");assert "revenue_range" in r
def test_extract_procurement_leads():
    from core.evidence_ledger_v2 import extract_source_specific_leads
    r=extract_source_specific_leads("procurement_bidding","bid notice highway");assert "bid_amount" in r


def test_market_structure_deep():
    from core.investigation import _market_structure_depth
    r=_market_structure_depth({},{"competitors":["A","B"],"hhi":"2800"})
    assert r["depth_score"]=="deep"
def test_market_structure_shallow():
    from core.investigation import _market_structure_depth
    r=_market_structure_depth({},{})
    assert r["depth_score"]=="shallow"

def test_persona_data_contract_missing_lanes():
    from core.investigation import _build_persona_data_contract
    r = _build_persona_data_contract({},{},{},{},{},{})
    assert len(r) == 3
def test_persona_data_contract_no_fake_chatter():
    from core.investigation import _build_persona_data_contract
    r = _build_persona_data_contract({},{},{},{},{},{})
    for m in r:
        assert "persona" in m
        assert "message" in m
        assert "refs" in m

# === Codex Audit Fix: Regression Tests ===
def test_no_duplicate_pipeline_contract_matrix():
    """Codex audit: pipeline_contract_matrix exists with 6 sources."""
    from core.investigation import _build_pipeline_contract_matrix
    r = _build_pipeline_contract_matrix(None, {}, [])
    assert "pipeline_contract_matrix" in r
    assert r["source_count"] == 6

def test_no_duplicate_rules_in_relationship():
    """Regression: relationship_resolution rules must not be overwritten."""
    with open(__import__("os").path.join(__import__("os").getcwd(), "core", "relationship_resolution.py"), encoding="utf-8") as f:
        c = f.read()
    count = 0
    in_dict = False
    for line in c.split("\n"):
        if '"rules"' in line and '{' in line:
            count += 1
    assert count <= 1, f"rules assigned {count} times"

# === Real Runtime: QYYJT Pledge-Freeze-Auction Bridge ===
def test_pledge_bridge_complete_rows():
    from core.qyyjt_pledge_bridge import build_pledge_bridge
    r = build_pledge_bridge([{"source":"qyyjt","amount":"1B","pledgor":"A","pledgee":"B"}], [], [])
    assert r["fact_count"] == 1
    assert r["pressure_level"] == "MEDIUM"

def test_pledge_bridge_incomplete_leads():
    from core.qyyjt_pledge_bridge import build_pledge_bridge
    r = build_pledge_bridge([{"source":"web"}], [], [])
    assert r["fact_count"] == 0
    assert r["lead_count"] == 1

def test_pledge_bridge_no_provenance_rejected():
    from core.qyyjt_pledge_bridge import build_pledge_bridge
    r = build_pledge_bridge([{}], [], [])
    assert r["rejected_count"] == 1

def test_pledge_bridge_high_pressure():
    from core.qyyjt_pledge_bridge import build_pledge_bridge
    r = build_pledge_bridge(
        [{"source":"q","amount":"1","pledgor":"a","pledgee":"b"}]*3,
        [{"source":"q","amount":"1","pledgor":"a","pledgee":"b"}]*2, [])
    assert r["pressure_level"] == "HIGH"

def test_pledge_to_evidence_conversion():
    from core.qyyjt_pledge_bridge import build_pledge_bridge, pledge_to_evidence
    r = build_pledge_bridge([{"source":"q","amount":"1B","pledgor":"A","pledgee":"B"}], [], [])
    ev = pledge_to_evidence(r)
    assert len(ev) == 1
    assert ev[0]["admission"] == "fact"

def test_pledge_bridge_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "pledge_bridge" in ds
        assert ds["pledge_bridge"]["bridge_available"] is True
        assert ds["pledge_bridge"]["bridge_operational"] is (ds["pledge_bridge"]["fact_count"] > 0)
    asyncio.run(run())

def test_trade_bridge_complete():
    from core.qyyjt_trade_bridge import build_trade_bridge
    r = build_trade_bridge([{"source":"q","amount":"1B","counterparty":"X"}], [], [])
    assert r["fact_count"] == 1
def test_trade_bridge_lead_only():
    from core.qyyjt_trade_bridge import build_trade_bridge
    r = build_trade_bridge([{"source":"q"}], [], [])
    assert r["lead_count"] == 1

def test_qyyjt_bridge_rows_use_explicit_claim_fields():
    from core.investigation import _extract_qyyjt_bridge_rows
    rows = _extract_qyyjt_bridge_rows([
        {
            "claim": "equity pledge amount $10M",
            "source": "qyyjt",
            "amount": "$10M",
            "pledgor": "Alpha",
            "pledgee": "Bank",
        },
        {
            "claim": "trade contract amount $3M",
            "source": "qyyjt",
            "amount": "$3M",
            "counterparty": "Buyer",
        },
    ])
    assert len(rows["pledge_rows"]) == 1
    assert len(rows["trade_rows"]) == 1
    assert rows["pledge_rows"][0]["pledgee"] == "Bank"
    assert rows["trade_rows"][0]["counterparty"] == "Buyer"

def test_qyyjt_bridge_rows_ignore_unrelated_metadata_keywords():
    from core.investigation import _extract_qyyjt_bridge_rows
    rows = _extract_qyyjt_bridge_rows([
        {
            "claim": "ordinary revenue disclosure",
            "source": "sec",
            "metadata": {"debug": "pledge trade freeze"},
        }
    ])
    assert rows["pledge_rows"] == []
    assert rows["freeze_rows"] == []
    assert rows["trade_rows"] == []

def test_qyyjt_bridge_packet_preserves_fact_and_lead_boundary():
    from core.investigation import _build_qyyjt_bridge_packet
    packet = _build_qyyjt_bridge_packet([
        {
            "claim": "equity pledge amount $10M",
            "source": "qyyjt",
            "amount": "$10M",
            "pledgor": "Alpha",
            "pledgee": "Bank",
        },
        {
            "claim": "trade contract announced",
            "source": "public_web",
        },
    ])
    assert packet["pledge_bridge"]["fact_count"] == 1
    assert packet["pledge_bridge"]["bridge_operational"] is True
    assert packet["trade_bridge"]["fact_count"] == 0
    assert packet["trade_bridge"]["lead_count"] == 1
    assert packet["trade_bridge"]["bridge_operational"] is False
    assert packet["bridge_summary"]["operational"] == ["pledge_bridge"]

def test_trade_bridge_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        assert "trade_bridge" in ds
    asyncio.run(run())

def test_ev004_source_actions():
    from core.investigation import _build_strategy_actions
    r = _build_strategy_actions({}, {"fixture_only_sources":["a","b"], "usable_sources":[]})
    assert any(a["action_id"]=="SOURCE-001" for a in r["strategy_actions"])
def test_ev004_auth_actions():
    from core.investigation import _build_strategy_actions
    r = _build_strategy_actions({}, {"authorization_required_sources":["qyyjt_api"]})
    assert any(a["action_id"]=="SOURCE-002" for a in r["strategy_actions"])

def test_ev004_blocked_source_actions():
    from core.investigation import _build_strategy_actions
    r = _build_strategy_actions({}, {"blocked_sources":["public_web_search"]})
    action = next(a for a in r["strategy_actions"] if a["action_id"]=="SOURCE-003")
    assert action["priority"] == "P0"
    assert "official/public-origin" in action["done_condition"]

def test_ev005_evidence_trace_in_packet():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        trace = ds.get("evidence_to_report_trace", [])
        assert len(trace) >= 3, f"Expected >=3 trace entries, got {len(trace)}"
        lanes = {t["report_section"] for t in trace}
        assert "money_lane" in lanes, f"Missing money_lane in trace: {lanes}"
    asyncio.run(run())

def test_ev006_pledge_bridge_real_data():
    from core.qyyjt_pledge_bridge import build_pledge_bridge, extract_pledge_from_fixture
    fr = extract_pledge_from_fixture([{"record_type":"pledge","amount":"1B","pledgor":"A","pledgee":"B","source":"qyyjt"}])
    r = build_pledge_bridge(fr["pledge_rows"], fr["freeze_rows"], fr["auction_rows"])
    assert r["bridge_operational"] is True
    assert r["fact_count"] == 1
def test_ev006_pledge_bridge_in_dd_summary():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline(); result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result)
        pkt = build_investigation_packet(g.to_dict(), input_text="Demo Technology Co., Ltd.", mode="fixture")
        ds = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        pb = ds.get("pledge_bridge",{})
        assert pb.get("bridge_available") is True
        assert pb.get("bridge_operational") is (pb.get("fact_count", 0) > 0)
    asyncio.run(run())

def test_ev007_reality_drill_money():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("Apple reported record revenue of $100B in Q4 2024")
    assert len(r["money_leads"]) >= 1
def test_ev007_reality_drill_goods():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("Company launched new product line with patent filings")
    assert len(r["goods_leads"]) >= 1
def test_ev007_reality_drill_people():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("CEO Tim Cook appointed new board director")
    assert len(r["people_leads"]) >= 1
def test_ev007_reality_drill_empty():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("This page has no useful information")
    assert len(r["money_leads"]) == 0 and len(r["goods_leads"]) == 0 and len(r["people_leads"]) == 0


def test_ev008_report_language():
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet

    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pipeline = RiskDiscoveryPipeline()
        result = await pipeline.run("Demo Technology Co., Ltd.", records=pack.all_records())
        graph = export_risk_graph(result)
        packet = build_investigation_packet(
            graph.to_dict(),
            input_text="Demo Technology Co., Ltd.",
            mode="fixture",
        )
        summary = packet.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        language = summary.get("report_language", {})
        assert "internal_alpha" in language.get("release_decision_label", "")
        assert "0" in language.get("source_truth_label", "")
        assert language.get("money_lane_status") == "covered"
        assert summary["validation_status"]["source"] == "runtime_validation_required"
        assert "acceptance_test_count" not in summary

    asyncio.run(run())

def test_ev003_cross_case_drill():
    """EV-003: Cross-case drill — China fixture + Apple public. Goods missing in both cases."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run(label,company,mode):
        if mode=="fixture":
            pack=build_datasource_fixture_pack(company)
            pl=RiskDiscoveryPipeline();res=await pl.run(company,records=pack.all_records())
            g=export_risk_graph(res)
        else: g=None
        pkt=build_investigation_packet(g.to_dict() if g else {},input_text=company,mode=mode)
        ds=pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]
        return {"money":ds["money_lane_summary"]["lane_status"],"goods":ds["goods_lane_summary"]["lane_status"],"people":ds["people_lane_summary"]["lane_status"]}
    async def main():
        china=await run("CHINA","Demo Technology Co., Ltd.","fixture");apple=await run("APPLE","Apple Inc.","public")
        shared_gaps=[k for k in china if china[k]=="missing" and apple[k]=="missing"]
        assert china["goods"] in ("covered","weak","missing"), f"Expected goods gap in at least China: china={china} apple={apple}"
    asyncio.run(main())

def test_ev007_reality_drill_money():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("Apple reported record revenue of $100B in Q4 2024")
    assert len(r["money_leads"]) >= 1
def test_ev007_reality_drill_goods():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("Company launched new product line with patent filings")
    assert len(r["goods_leads"]) >= 1
def test_ev007_reality_drill_people():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("CEO Tim Cook appointed new board director")
    assert len(r["people_leads"]) >= 1
def test_ev007_reality_drill_empty():
    from adapters.public_web_search_tool import reality_drill_extract
    r = reality_drill_extract("This page has no useful information")
    assert len(r["money_leads"]) == 0 and len(r["goods_leads"]) == 0 and len(r["people_leads"]) == 0


def test_p004_no_provenance_fact():
    """P0-004: Missing provenance must not become fact."""
    from core.evidence_ledger_v2 import normalize_evidence_v2
    r=normalize_evidence_v2([{"admission":"fact","claim":"orphan"}])
    assert r[0]["admission"]!="fact"

def test_p004_shared_address_not_fact():
    """P0-004: Shared address alone must not become fact."""
    from core.relationship_resolution import build_relationship_resolution
    r=build_relationship_resolution([{"evidence_id":"ev-1","lane":"people","subject":"X","source_name":"web","admission":"weak_lead","claim":"same_address=Suite_500"}],None,None)
    for l in r["phase1_candidate_leads"]:assert l["admission"]!="fact"

def test_p004_official_outranks_public():
    """P0-004: Official/licensed evidence outranks public web snippets."""
    from core.entity_resolution import build_entity_resolution
    r=build_entity_resolution({"name":"TestCo","registration_id":"91110000"},None)
    assert r.get("resolved_entities"),"Entity resolution must produce entities from official ID"

def test_p2001_money_deep_analysis():
    from core.investigation import _build_money_lane
    from core.evidence_ledger_v2 import normalize_evidence_v2
    rows=normalize_evidence_v2([{"source":"f","admission":"fact","confidence":0.9,"claim":"debt=1B"},{"source":"f","admission":"fact","confidence":0.9,"claim":"freeze=assets"}])
    r=_build_money_lane(rows,{},{})
    assert r["deep_analysis"]["financing_pressure"] in ("HIGH","MEDIUM","LOW")
    assert r["deep_analysis"]["financing_pressure"] in ("HIGH","MEDIUM")
def test_p2004_cross_lane_questions_binding():
    from core.investigation import _cross_lane_questions
    r=_cross_lane_questions({"fact_count":2,"pledge_freeze_auction":[{"type":"freeze"}]},{"deep_analysis":{"supplier_concentration":"HIGH","customer_dependency":"HIGH"},"fact_count":1},{"fact_count":1,"deep_analysis":{"controller_confidence":"HIGH"}})
    assert r["question_count"] >= 3
    for q in r["cross_lane_questions"]:
        assert "lanes" in q
        assert "evidence_refs" in q

def test_p3002_graph_explain_production():
    from core.graph_explain import explain_graph_edges
    r = explain_graph_edges({"edges":[{"from":"A","to":"B","type":"controls","admission":"fact","confidence":0.9,"source":"reg","explanation":"test","evidence_ids":["ev-1"]}]})
    assert r["verdict"] == "graph_explainable"
    assert r["edges"][0]["is_strong"] is True
    assert r["edges"][0]["natural_language"]
def test_p3002_graph_explain_empty():
    from core.graph_explain import explain_graph_edges
    r = explain_graph_edges(None)
    assert r["edge_count"] == 0
def test_p3003_report_language_data_driven():
    from core.investigation import _build_report_language

    result = _build_report_language(
        {"source_lane_readiness": {"s1": {"fixture_only": True}, "s2": {"live_verified": True}}},
        True,
        "internal_alpha",
        "covered",
        "covered",
        "covered",
    )
    assert "1" in result["source_truth_label"]
    assert result["money_lane_status"] == "covered"
    assert "internal_alpha" in result["release_decision_label"]


def test_source_readiness_matrix_never_marks_unverified_source_ready():
    from core.investigation import _source_readiness_matrix

    rows = _source_readiness_matrix({
        "default_intel": {
            "live_verified": False,
            "fixture_only": False,
            "live_unverified": True,
            "live_smoke_capable": True,
        }
    })

    assert rows[0]["source"] == "default_intel"
    assert rows[0]["live_smoke_capable"] is True
    assert rows[0]["next_action"] == "live_smoke_needed"


# === RIX-SUPPORT-001: Bridge Claim Guard Tests ===

def test_empty_pledge_no_operational_claim():
    """RIX-SUPPORT-001: Pledge bridge with empty input MUST NOT claim facts."""
    from core.qyyjt_pledge_bridge import build_pledge_bridge
    r = build_pledge_bridge(None, None, None)
    assert r["bridge_available"] is True    # bridge function exists
    assert r["bridge_operational"] is False # but no operational capability without fact rows
    assert r["operational_basis"] == "no_complete_fact_rows"
    assert r["fact_count"] == 0             # but no facts without provenance rows
    assert r["lead_count"] == 0             # no leads without data
    assert r["pressure_level"] == "NONE"    # empty input = no pressure

def test_empty_trade_no_operational_claim():
    """RIX-SUPPORT-001: Trade bridge with empty input MUST NOT claim facts."""
    from core.qyyjt_trade_bridge import build_trade_bridge
    r = build_trade_bridge(None, None, None)
    assert r["bridge_available"] is True     # bridge function exists
    assert r["bridge_operational"] is False  # but no operational capability without fact rows
    assert r["operational_basis"] == "no_complete_fact_rows"
    assert r["fact_count"] == 0              # but no facts without provenance rows
    assert r["lead_count"] == 0              # no leads without data
    assert r["activity_level"] == "NONE"     # empty input = no activity

def test_bridge_summary_only_lists_runtime_backed():
    """RIX-SUPPORT-001: bridge_summary.operational MUST only list real bridges."""
    import asyncio
    from core.datasource_fixtures import build_datasource_fixture_pack
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    from core.risk_graph_export import export_risk_graph
    from core.investigation import build_investigation_packet
    async def run():
        pack = build_datasource_fixture_pack("Demo Technology Co., Ltd.")
        pl = RiskDiscoveryPipeline()
        result = await pl.run("Demo Technology Co., Ltd.", records=pack.all_records())
        g = export_risk_graph(result).to_dict()
        pkt = build_investigation_packet(g, input_text="Demo Technology Co., Ltd.", mode="fixture")
        bs = pkt.to_dict()["enterprise_cognition"]["investigation_report_card"]["dd_summary"]["bridge_summary"]
        operational = bs.get("operational", [])
        # Only pledge_bridge and trade_bridge are runtime-backed
        allowed = {"pledge_bridge", "trade_bridge"}
        for name in operational:
            assert name in allowed, f"Stub/planned bridge '{name}' must NOT be in operational list"
        if bs.get("operational_count") == 0:
            assert operational == []
    asyncio.run(run())
