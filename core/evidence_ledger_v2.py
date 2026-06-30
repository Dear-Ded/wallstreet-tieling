"""evidence_ledger_v2.py — DD v3.0 Evidence normalizer."""


def compute_evidence_depth(rows: list) -> dict:
    """P0-B: Compute evidence depth counters by lane."""
    depth = {"capital":0,"goods":0,"people":0,"risk":0,"graph":0,"source":0,"unknown":0}
    for r in (rows or []):
        lane = r.get("lane","unknown")
        if lane in depth: depth[lane] += 1
    return {
        "evidence_depth": depth,
        "total": len(rows or []),
        "fact_count": sum(1 for r in (rows or []) if r.get("admission")=="fact"),
        "lead_count": sum(1 for r in (rows or []) if r.get("admission")=="lead"),
        "weak_lead_count": sum(1 for r in (rows or []) if r.get("admission")=="weak_lead"),
        "rejected_count": sum(1 for r in (rows or []) if r.get("admission")=="rejected"),
    }

def extract_source_specific_leads(content_type, text) -> list:
    t=str(text).lower()
    if content_type=="annual_report_filing": return ["filing_type","fiscal_year","revenue_range"]
    if content_type=="procurement_bidding": return ["project_name","bid_amount","bidding_entity"]
    if content_type=="court_enforcement": return ["case_type","court_name","penalty_amount"]
    if content_type=="official_company_page": return ["company_description","established_year","industry_sector"]
    if content_type=="recruitment_job_posting": return ["job_title","department","location"]
    if content_type=="ip_product_technical": return ["ip_type","patent_number","trademark_class"]
    return ["title","snippet"]

def classify_content_type(text: str) -> str:
    """P1-I: Classify public web content by source type."""
    t = str(text).lower()
    if any(k in t for k in ("annual report","filing","10-k","10-q","sec.gov","annual report")):
        return "annual_report_filing"
    if any(k in t for k in ("procurement","bidding","tender","bid notice","投标","招标")):
        return "procurement_bidding"
    if any(k in t for k in ("court","enforcement","penalty","判决","处罚","notice of violation")):
        return "court_enforcement"
    if any(k in t for k in ("official company page","about us","company profile","corporate governance")):
        return "official_company_page"
    if any(k in t for k in ("industry report","market analysis","market report","sector outlook")):
        return "industry_report"
    if any(k in t for k in ("recruiting","job posting","career","hiring","招聘","jobs")):
        return "recruitment_job_posting"
    if any(k in t for k in ("patent","trademark","ip","intellectual property","专利","商标")):
        return "ip_product_technical"
    return "general_web_page"
def normalize_evidence_v2(raw: list | None) -> list:
    if not raw: return []
    result = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict): continue
        # P0-B: enforce provenance + confidence gate
        if not item.get("source") and item.get("admission") in ("fact","lead"):
            item["admission"]="rejected";item["admission_reason"]="missing_provenance"
        if item.get("admission")=="fact" and float(item.get("confidence",0.5))<0.6 and str(item.get("source","")) in ("public_web_search","web","public"):
            item["admission"]="lead";item["admission_reason"]="low_confidence"
        src = str(item.get("source", "unknown"))
        st = "fixture"
        if "qyyjt" in src.lower(): st = "authorized"
        elif src in ("public_web_search", "public_registry", "sec_edgar_public_api", "gleif_lei_public_api"): st = "public"
        adm = str(item.get("admission", "lead"))
        if adm not in ("fact", "lead", "weak_lead", "rejected"): adm = "lead"
        claims = item.get("claims", item.get("claim", []))
        claims = claims if isinstance(claims, list) else ([claims] if claims else [])
        ct = " ".join(str(c) for c in claims).lower()
        lane = "unknown"
        if any(k in ct for k in ("capital", "financ", "debt", "bond", "rating", "pledge", "freeze", "auction", "revenue", "cash", "融资", "债务", "贷款", "质押", "冻结", "拍卖", "偿付", "现金流")): lane = "capital"
        elif any(k in ct for k in ("product", "supplier", "customer", "market", "supply", "goods", "trademark", "patent", "产品", "供应", "客户", "渠道", "市场", "商标", "专利", "技术")): lane = "goods"
        elif any(k in ct for k in ("people", "controller", "ubo", "executive", "legal", "person", "shareholder", "director", "法人", "股东", "高管", "董事", "监事", "控制人", "实控")): lane = "people"
        elif any(k in ct for k in ("risk", "court", "enforcement", "penalty", "dishonesty", "fraud")): lane = "risk"
        elif any(k in ct for k in ("address", "relation", "graph", "edge", "node")): lane = "graph"
        elif any(k in ct for k in ("source", "fixture", "smoke", "live_verified", "live_unverified")): lane = "source"
        elif any(k in ct for k in ("pledge", "freeze", "auction", "seal", "查封", "冻结", "拍卖")): lane = "capital"
        elif any(k in ct for k in ("trademark", "patent", "ip", "brand", "recruit", "bid", "tender", "投标", "招聘")): lane = "goods"
        elif any(k in ct for k in ("ubo", "controller", "executive", "director", "shareholder", "关联", "任职")): lane = "people"
        elif any(k in ct for k in ("source", "fixture", "smoke", "live_verified", "live_unverified")): lane = "source"
        content_type = classify_content_type(ct)
        result.append({"content_type": content_type, "evidence_id": f"ev-{i:04d}", "subject": str(item.get("subject", item.get("company", ""))),
            "lane": lane, "source_name": src, "source_type": st, "admission": adm,
            "admission_reason": str(item.get("admission_reason", "")),
            "confidence": float(item.get("confidence", 0.5))})
    return result
