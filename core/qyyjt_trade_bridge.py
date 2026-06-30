"""qyyjt_trade_bridge.py — QYYJT trade/import-export/recruiting bridge to goods lane."""
def build_trade_bridge(trade_rows, import_export_rows, recruiting_rows) -> dict:
    tr, ie, rc = trade_rows or [], import_export_rows or [], recruiting_rows or []
    facts, leads = [], []
    for row in (tr + ie + rc):
        if row.get("amount") and row.get("counterparty") and row.get("source"):
            facts.append(row)
        elif row.get("source"):
            leads.append(dict(row, status="lead_only"))
    return {
        "trade_count": len(tr), "import_export_count": len(ie), "recruiting_count": len(rc),
        "facts": facts, "leads": leads,
        "fact_count": len(facts), "lead_count": len(leads),
        "activity_level": "HIGH" if len(facts)>=3 else ("MEDIUM" if facts else "NONE"),
        "bridge_available": True,
        "bridge_operational": len(facts) > 0,
        "operational_basis": "complete_provenance_fact_rows" if facts else "no_complete_fact_rows",
        "source": "qyyjt_api_fixture",
    }
