"""qyyjt_pledge_bridge.py — Real QYYJT pledge/freeze/auction bridge to evidence ledger + report."""
from typing import Any

def build_pledge_bridge(pledge_rows: list | None, freeze_rows: list | None, auction_rows: list | None) -> dict:
    """Build pledge/freeze/auction bridge from QYYJT fixture rows.
    Complete rows admitted. Missing provenance: lead-only. No rows: missing.
    """
    pl = pledge_rows or []; fr = freeze_rows or []; au = auction_rows or []
    facts, leads, rejected = [], [], []
    for row in pl:
        if _is_complete(row): facts.append({"type": "pledge", **row})
        elif row.get("source"): leads.append({"type": "pledge", "status": "lead_only", **row})
        else: rejected.append({"type": "pledge", "reason": "missing_provenance", **row})
    for row in fr:
        if _is_complete(row): facts.append({"type": "freeze", **row})
        elif row.get("source"): leads.append({"type": "freeze", "status": "lead_only", **row})
        else: rejected.append({"type": "freeze", "reason": "missing_provenance", **row})
    for row in au:
        if _is_complete(row): facts.append({"type": "auction", **row})
        elif row.get("source"): leads.append({"type": "auction", "status": "lead_only", **row})
        else: rejected.append({"type": "auction", "reason": "missing_provenance", **row})
    return {
        "pledge_count": len(pl), "freeze_count": len(fr), "auction_count": len(au),
        "facts": facts, "leads": leads, "rejected": rejected,
        "fact_count": len(facts), "lead_count": len(leads), "rejected_count": len(rejected),
        "pressure_level": "HIGH" if len(facts) >= 3 or len(pl) + len(fr) >= 5 else ("MEDIUM" if facts or leads else "NONE"),
        "bridge_available": True,
        "bridge_operational": len(facts) > 0,
        "operational_basis": "complete_provenance_fact_rows" if facts else "no_complete_fact_rows",
        "source": "qyyjt_api_fixture",
    }

def _is_complete(row: dict) -> bool:
    return bool(row.get("source") and row.get("amount") and row.get("pledgor") and row.get("pledgee"))

def pledge_to_evidence(pledge_result: dict) -> list:
    """Convert pledge bridge result to evidence ledger rows."""
    rows = []
    for f in pledge_result.get("facts", []):
        rows.append({"source": "qyyjt_api_fixture", "admission": "fact", "confidence": 0.9,
            "claim": f"pledge:{f.get('amount','?')};pledgor:{f.get('pledgor','?')};pledgee:{f.get('pledgee','?')}",
            "provenance": "QYYJT fixture", "lane": "capital"})
    for l in pledge_result.get("leads", []):
        rows.append({"source": "qyyjt_api_fixture", "admission": "lead", "confidence": 0.4,
            "claim": f"pledge_lead:{l.get('type','?')}", "provenance": "QYYJT fixture incomplete", "lane": "capital"})
    return rows

def extract_pledge_from_fixture(fixture_records) -> dict:
    """EV-006: Extract pledge/freeze/auction data from QYYJT fixture records."""
    pledge_rows, freeze_rows, auction_rows = [], [], []
    for rec in (fixture_records or []):
        rec_type = rec.get("record_type", rec.get("type", ""))
        if "pledge" in str(rec_type).lower():
            pledge_rows.append(rec)
        elif "freeze" in str(rec_type).lower():
            freeze_rows.append(rec)
        elif "auction" in str(rec_type).lower():
            auction_rows.append(rec)
    return {"pledge_rows": pledge_rows, "freeze_rows": freeze_rows, "auction_rows": auction_rows}
