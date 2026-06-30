"""entity_resolution.py — DD v3.2 Enhanced Entity Resolution with strong match rules."""
def build_entity_resolution(sp=None, rg=None):
    res = []; sp2 = sp or {}; rg2 = rg or {}
    n = str(sp2.get("name","")).strip().lower()
    ids = sp2.get("identifiers") or {}
    uscc = ids.get("unified_social_credit_code",""); lei = ids.get("lei",""); ticker = ids.get("ticker","")
    has_strong_id = bool(uscc or lei or ticker)
    if n:
        res.append({"entity_id":f"company:normalized:{n}","entity_type":"company","display_name":n,
            "entity_resolution_key":f"company:normalized:{n}",
            "match_confidence":0.95 if has_strong_id else 0.7,
            "match_reason":"strong_id" if has_strong_id else "name_only",
            "ambiguity_flags":[] if has_strong_id else ["name_only_no_id"]})
        if has_strong_id:
            if uscc: res[-1]["identifiers"]={"uscc":uscc}
            if lei: res[-1].setdefault("identifiers",{})["lei"]=lei
            if ticker: res[-1].setdefault("identifiers",{})["ticker"]=ticker
    for nd in (rg2.get("nodes") or []):
        nn = str(nd.get("name","")).strip().lower(); nt = nd.get("type","company")
        if not nn: continue
        key = nd.get("entity_resolution_key",f"{nt}:normalized:{nn}")
        existing = [e for e in res if e["display_name"]==nn]
        is_dup = len(existing)>0 and not any(e.get("match_reason")=="strong_id" for e in existing)
        res.append({"entity_id":nd.get("id",key),"entity_type":nt,"display_name":nn,"entity_resolution_key":key,
            "match_confidence":0.3 if is_dup else 0.9,"match_reason":"duplicate_name" if is_dup else "graph_node",
            "ambiguity_flags":["same_name_no_unique_id"] if is_dup else []})
    return {"resolved_entities":res,"entity_count":len(res),"version":"1.2",
        "rules":{"strong_match":"USCC/LEI/ticker = high confidence (0.95)",
            "no_auto_merge":"Same name without unique ID NOT merged (confidence 0.3)",
            "same_address":"weak_lead only","same_name_different_role":"NOT merged"}}
