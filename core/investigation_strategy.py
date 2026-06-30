"""investigation_strategy.py — DD v3.2: Actions bound to specific gap_ids and blocker_ids."""
def build_strategy_v2(gap_summary=None, readiness=None, blocker_gate=None, graph=None, realness=None, live=None):
    plan = []; gs = gap_summary or {}; gaps = gs.get("gap_summary",{})
    rd = readiness or {}; bl = blocker_gate or {}; blockers = bl.get("blockers",[])
    blocked_src = rd.get("blocked_sources",[]); needs_auth = rd.get("authorization_required_sources",[])

    def _gap_id(lane, idx): return f"gap-{lane}-{idx:03d}"
    def _blocker_id(name): return f"blocker-{name}"

    cap = gaps.get("capital",{})
    if cap.get("status") in ("missing","weak"):
        bid = _blocker_id("capital_untested") if any("capital_untested" in str(b) for b in blockers) else None
        plan.append({"action_id":"CAP-V2-001","gap_id":_gap_id("capital",1),"blocker_id":bid,
            "priority":"P0" if cap.get("status")=="missing" or blocked_src else "P1",
            "target_lane":"capital","reason":f"Capital status={cap.get('status')}, signals={cap.get('signal_count',0)}",
            "blocker_addressed":bid,"suggested_source":"qyyjt_api:fin_inst,pledge,freeze" if needs_auth else "public_web_search:capital",
            "required_authorization":bool(needs_auth),
            "expected_evidence":"Financing history, debt structure, equity pledge/freeze/auction records",
            "done_condition":"capital_status=covered","status":"pending"})

    goods = gaps.get("goods",{})
    if goods.get("status") in ("missing","weak"):
        plan.append({"action_id":"GOODS-V2-001","gap_id":_gap_id("goods",1),"blocker_id":None,
            "priority":"P0" if goods.get("status")=="missing" else "P1","target_lane":"goods",
            "reason":f"Goods status={goods.get('status')}, signals={goods.get('signal_count',0)}",
            "done_condition":"goods_status=covered","status":"pending"})

    ppl = gaps.get("people",{})
    if ppl.get("status") in ("missing","weak"):
        plan.append({"action_id":"PEOPLE-V2-001","gap_id":_gap_id("people",1),"blocker_id":None,
            "priority":"P0" if ppl.get("status")=="missing" else "P1","target_lane":"people",
            "reason":f"People status={ppl.get('status')}, signals={ppl.get('signal_count',0)}",
            "done_condition":"people_status=covered","status":"pending"})

    src = gaps.get("source",{})
    if src.get("status") in ("missing","weak") or blocked_src:
        plan.append({"action_id":"SRC-V2-001","gap_id":_gap_id("source",1),
            "blocker_id":_blocker_id("source_access") if blocked_src else None,
            "priority":"P0","target_lane":"source",
            "reason":f"Source blocked={len(blocked_src)}, auth_needed={bool(needs_auth)}",
            "blocker_addressed":_blocker_id("source_access") if blocked_src else None,
            "suggested_source":"manual_upload or credential_provision",
            "required_authorization":True,"done_condition":"source_status=covered"})

    # Filter: remove actions without gap_id OR blocker_id
    filtered = [a for a in plan if a.get("gap_id") or a.get("blocker_id")]
    return {"strategy_plan_v2":filtered,"action_count":len(filtered),"version":"2.2",
        "source_driven":True,"note":"DD v3.2: Every action bound to gap_id or blocker_id."}
