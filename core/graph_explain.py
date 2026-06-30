"""graph_explain.py — P3-002: Real graph edge explainability with evidence tracing."""
def explain_graph_edges(relationship_graph: dict | None) -> dict:
    """Produce natural-language explanations for each graph edge."""
    g = relationship_graph or {}
    edges = g.get("edges", [])
    explained = []
    for i, e in enumerate(edges):
        frm = e.get("from", "?")
        to = e.get("to", "?")
        etype = e.get("type", "?")
        adm = e.get("admission", "?")
        src = e.get("source", "?")
        expl = e.get("explanation", "")
        confidence = e.get("confidence", 0)
        ev_ids = e.get("evidence_ids", [])
        severity = "strong" if adm == "fact" and confidence >= 0.8 else ("moderate" if adm in ("fact","lead") and confidence >= 0.5 else "weak")
        text = f"{frm} -> {to}: {etype} (confidence={confidence}, admission={adm}, source={src})"
        explained.append({
            "edge_id": f"edge-{i:03d}",
            "from_node": frm, "to_node": to, "relation_type": etype,
            "confidence": confidence, "admission": adm,
            "source_name": src, "explanation": expl,
            "evidence_ids": ev_ids, "severity": severity,
            "natural_language": text,
            "is_strong": severity == "strong",
        })
    return {
        "edge_count": len(explained),
        "strong_edges": sum(1 for e in explained if e["is_strong"]),
        "moderate_edges": sum(1 for e in explained if e["severity"] == "moderate"),
        "weak_edges": sum(1 for e in explained if e["severity"] == "weak"),
        "edges": explained,
        "verdict": "graph_explainable" if explained else "no_edges_present",
    }
