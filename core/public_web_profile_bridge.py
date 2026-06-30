#!/usr/bin/env python3
"""Bridge public-web and QYYJT public-plan leads into cognition profiles."""
from __future__ import annotations

import re
from typing import Any

PW_CLAIM_TO_PROFILE: dict[str, str] = {
    "capital-bond": "capital_profile",
    "capital-credit": "credit_profile",
    "commercial-recruiting": "commercial_activity_profile",
    "commercial-tax": "commercial_activity_profile",
    "commercial-trade": "commercial_activity_profile",
    "commercial-procurement": "commercial_activity_profile",
    "financial-annual": "capital_profile",
    "market-structure": "goods_flow_profile",
    "policy-regulatory": "legal_administrative_profile",
    "competitor": "goods_flow_profile",
    "switching-cost": "goods_flow_profile",
    "upstream-power": "supply_chain_profile",
    "downstream-power": "supply_chain_profile",
}

PUBLIC_WEB_SOURCES = {
    "public_web_search",
    "default_public_intel",
}

MONEY_KEYWORDS = {
    "asset",
    "auction",
    "bank",
    "bond",
    "borrow",
    "buyback",
    "capital",
    "cash",
    "credit",
    "debt",
    "default",
    "derivative",
    "equity",
    "financ",
    "freeze",
    "fund",
    "guarantee",
    "investment",
    "ipo",
    "liquid",
    "loan",
    "margin",
    "mortgage",
    "pledge",
    "rating",
    "refinanc",
    "revenue",
    "securit",
    "solvency",
    "working_capital",
}

GOODS_KEYWORDS = {
    "backlog",
    "brand",
    "capacity",
    "channel",
    "contract",
    "customer",
    "export",
    "goods",
    "import",
    "industry",
    "inventory",
    "logistic",
    "market",
    "patent",
    "price",
    "procure",
    "product",
    "recruit",
    "sales",
    "supplier",
    "supply",
    "tax",
    "technology",
    "tender",
    "trade",
    "trademark",
    "upstream",
}

PEOPLE_KEYWORDS = {
    "admin",
    "beneficial",
    "blacklist",
    "board",
    "case",
    "ceo",
    "controller",
    "court",
    "director",
    "dishonest",
    "enforcement",
    "executive",
    "founder",
    "labor",
    "legal",
    "owner",
    "party",
    "penalty",
    "people",
    "person",
    "regulat",
    "related",
    "shareholder",
    "ubo",
    "wage",
}


def build_public_web_profiles(evidence_ledger: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Build investigation profile leads from flat or nested public-web evidence.

    Output intentionally uses public_* profile names consumed by enterprise_cognition.
    All rows remain corroboration-needed leads; this bridge never upgrades public
    snippets into facts.
    """
    profiles: dict[str, dict[str, Any]] = {}
    for item in evidence_ledger or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("source_name") or "")
        if _is_excluded_source(source):
            continue
        records = _claim_records(item)
        if not records:
            continue
        if not _is_public_profile_source(item, source):
            continue
        if source == "qyyjt_websearch_plan" or source.startswith("qyyjt_public_plan:"):
            _merge_qyyjt_public_plan_profile(profiles, item, records)
            continue
        for claim, parsed in records:
            if not parsed:
                parsed = _text_to_public_lead_keys(claim)
            for key, value in parsed.items():
                target = _profile_for_key(key)
                _add_profile_claim(profiles, target, key, value, item)

    for name, profile in profiles.items():
        profile["claims"] = profile["claims"][:20]
        profile["rows"] = profile["rows"][:12]
        if name == "public_capital_profile":
            _enrich_public_capital_profile(profile)
        if name == "public_goods_profile":
            _enrich_public_goods_profile(profile)
        profile["row_count"] = len(profile["claims"])
        profile["verification_status"] = "public_lead_needs_corroboration"
        profile["source"] = "public_web"
        profile["title"] = f"Public web {name} leads (corroboration-needed)"
        profile["quality_notes"] = [
            "Public web claims are leads only; corroborate with official, licensed, or user-authorized sources before relying as facts.",
            f"Public lead claims: {profile['row_count']}",
        ]
    return profiles


def _enrich_public_capital_profile(profile: dict[str, Any]) -> None:
    """Expose public capital leads as structured buckets consumed by money lanes."""
    buckets = {
        "financing_event_claims": {
            "financing_event",
            "financing_amount",
            "financing_round",
            "funding_round",
            "capital_injection",
            "pe_vc_investment",
        },
        "debt_credit_claims": {
            "debt",
            "debt_exposure",
            "debt_or_credit_obligation",
            "loan",
            "credit",
            "credit_facility",
            "credit_profile",
            "bond",
            "bond_default",
            "bond_rating",
        },
        "refinancing_claims": {
            "refinancing_risk",
            "refinancing_difficulty",
            "refinancing_gap",
            "rollover_risk",
            "maturity_wall",
        },
        "liquidity_claims": {
            "cash_or_liquidity_pressure",
            "liquidity_pressure",
            "cash_flow_pressure",
            "working_capital",
            "working_capital_pressure",
            "going_concern",
        },
        "asset_pressure_claims": {
            "asset_or_equity_pressure",
            "pledge",
            "equity_pledge",
            "freeze",
            "auction",
            "asset_freeze",
            "collateral",
            "mortgage",
        },
        "capital_structure_claims": {
            "capital_structure",
            "debt_to_equity",
            "gearing_ratio",
            "leverage",
            "capital_reduction",
            "buyback",
        },
    }
    for claim in [str(item) for item in profile.get("claims", []) if str(item).strip()]:
        if "=" not in claim:
            continue
        raw_key, raw_value = claim.split("=", 1)
        clean_key = _clean_signal_key(raw_key)
        clean_value = _trim_signal_value(raw_value)
        if not clean_key or not clean_value:
            continue
        for bucket, keys in buckets.items():
            if clean_key in keys or any(token in clean_key for token in keys):
                values = profile.setdefault(bucket, [])
                entry = f"{clean_key}={clean_value}"
                if entry not in values:
                    values.append(entry)
    for bucket in buckets:
        if bucket in profile:
            profile[bucket] = profile[bucket][:8]
    profile["structured_summary"] = {
        "financing_events": len(profile.get("financing_event_claims", [])),
        "debt_credit": len(profile.get("debt_credit_claims", [])),
        "refinancing": len(profile.get("refinancing_claims", [])),
        "liquidity": len(profile.get("liquidity_claims", [])),
        "asset_pressure": len(profile.get("asset_pressure_claims", [])),
        "capital_structure": len(profile.get("capital_structure_claims", [])),
    }


def _enrich_public_goods_profile(profile: dict[str, Any]) -> None:
    """Expose goods public leads as structured buckets consumed by report lanes."""
    buckets = {
        "supplier_claims": {"supplier", "supplier_concentration", "supplier_power", "supplier_payment_pressure"},
        "customer_claims": {"customer", "customer_concentration", "customer_value", "customer_churn"},
        "product_claims": {"product", "product_dependency", "core_product", "substitution_risk", "substitute_availability"},
        "upstream_claims": {"upstream", "raw_material_pressure", "upstream_power"},
        "downstream_claims": {"downstream", "downstream_power"},
        "channel_partner_claims": {"channel", "partner", "sales_channel", "value_chain_role"},
        "market_position_claims": {
            "market_position",
            "market_share",
            "market_size",
            "market_concentration",
            "competitive_landscape",
            "entry_barriers",
            "pricing_power",
            "competitor",
            "peer_comparison",
        },
        "business_model_claims": {
            "business_model",
            "sales_model",
            "revenue_model",
            "subscription_model",
            "subscription_revenue_ratio",
            "unit_economics",
            "switching_cost",
            "repeat_purchase",
        },
    }
    for claim in [str(item) for item in profile.get("claims", []) if str(item).strip()]:
        if "=" not in claim:
            continue
        raw_key, raw_value = claim.split("=", 1)
        clean_key = _clean_signal_key(raw_key)
        clean_value = _trim_signal_value(raw_value)
        if not clean_key or not clean_value:
            continue
        for bucket, keys in buckets.items():
            if clean_key in keys or any(token in clean_key for token in keys):
                values = profile.setdefault(bucket, [])
                entry = f"{clean_key}={clean_value}"
                if entry not in values:
                    values.append(entry)
    for bucket in buckets:
        if bucket in profile:
            profile[bucket] = profile[bucket][:8]
    profile["structured_summary"] = {
        "suppliers": len(profile.get("supplier_claims", [])),
        "customers": len(profile.get("customer_claims", [])),
        "products": len(profile.get("product_claims", [])),
        "market_position": len(profile.get("market_position_claims", [])),
        "business_model": len(profile.get("business_model_claims", [])),
    }


def _trim_signal_value(raw: Any, limit: int = 180) -> str:
    value = str(raw or "").strip()
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def classify_public_web_claims(evidence_ledger: list) -> dict[str, list[str]]:
    """Classify extraction claims into legacy public-web profile buckets."""
    classified: dict[str, list[str]] = {}
    for item in evidence_ledger or []:
        for claim, _parsed in _claim_records(item if isinstance(item, dict) else {}):
            for prefix, profile in PW_CLAIM_TO_PROFILE.items():
                if prefix in claim:
                    classified.setdefault(profile, []).append(claim)
    return classified


def merge_into_cognition(classified: dict[str, list[str]], enterprise_cognition: dict) -> dict:
    """Merge legacy classified public-web claims into an enterprise_cognition dict."""
    for profile, claims in (classified or {}).items():
        existing = enterprise_cognition.get(profile) or {}
        if isinstance(existing, dict):
            existing["public_web_leads"] = list(claims or [])
            enterprise_cognition[profile] = existing
    enterprise_cognition["public_web_claim_profiles"] = list((classified or {}).keys())
    return enterprise_cognition


def _is_excluded_source(source: str) -> bool:
    return source.startswith("qyyjt_api:")


def _is_public_profile_source(item: dict[str, Any], source: str) -> bool:
    if source in PUBLIC_WEB_SOURCES or source == "qyyjt_websearch_plan":
        if source == "qyyjt_websearch_plan":
            return item.get("record_kind") in {None, "evidence", "lead"}
        return item.get("record_kind") in {None, "evidence"}
    if source.startswith("qyyjt_public_plan:"):
        return item.get("record_kind") in {None, "evidence", "lead"}
    if item.get("record_kind") == "evidence":
        return True
    return bool(item.get("evidence"))


def _claim_records(item: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    claims: list[str] = []
    for claim in item.get("claims") or []:
        if str(claim).strip():
            claims.append(str(claim))
    if item.get("claim"):
        claims.append(str(item.get("claim")))
    for field in ("title", "summary", "snippet"):
        value = str(item.get(field) or "").strip()
        if value:
            claims.append(value)
    for ev in item.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        value = str(ev.get("claim") or "").strip()
        if value:
            claims.append(value)
    records: list[tuple[str, dict[str, str]]] = []
    for claim in dict.fromkeys(claims):
        parsed = _parse_signal_claims(claim)
        records.append((claim, parsed))
    return records


def _parse_signal_claims(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    chunks: list[str] = []
    for part in re.split(r"[;\n]+", str(text or "")):
        chunks.extend(re.split(r",\s*(?=[A-Za-z_][A-Za-z0-9_\- ]*=)", part))
    for part in chunks:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        clean_key = _clean_signal_key(key)
        clean_value = _clean_signal_value(value)
        if clean_key and clean_value and clean_key not in values:
            values[clean_key] = clean_value
    return values


def _clean_signal_key(raw: Any) -> str:
    token = str(raw or "").strip().lower().replace("-", "_")
    token = token.split()[-1] if token.split() else token
    return re.sub(r"[^a-z0-9_]", "", token)


def _clean_signal_value(raw: Any) -> str:
    value = str(raw or "").strip().strip(" ;")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _text_to_public_lead_keys(text: str) -> dict[str, str]:
    lowered = str(text or "").lower()
    values: dict[str, str] = {}
    for marker, key in (
        ("bond", "debt_or_credit_obligation"),
        ("debt", "debt_or_credit_obligation"),
        ("loan", "debt_or_credit_obligation"),
        ("financing", "financing_event"),
        ("revenue", "revenue_amount"),
        ("supplier", "supplier"),
        ("customer", "customer"),
        ("product", "product"),
        ("market", "market_position"),
        ("recruit", "recruiting_active"),
        ("controller", "actual_controller"),
        ("ubo", "beneficial_owner"),
        ("shareholder", "shareholder"),
        ("court", "court_case"),
        ("penalty", "regulatory_penalty"),
        ("negative", "negative_news"),
    ):
        if marker in lowered:
            values.setdefault(key, "publicly_described")
    return values


def _profile_for_key(key: str) -> str:
    token = key.lower()
    if token in {
        "business_model",
        "revenue_model",
        "sales_model",
        "sales_channel",
        "subscription_model",
        "subscription_revenue_ratio",
        "unit_economics",
        "switching_cost",
        "repeat_purchase",
    }:
        return "public_goods_profile"
    if _contains_any(token, MONEY_KEYWORDS):
        return "public_capital_profile"
    if _contains_any(token, PEOPLE_KEYWORDS):
        return "public_people_profile"
    if _contains_any(token, GOODS_KEYWORDS):
        return "public_goods_profile"
    return "public_goods_profile"


def _contains_any(token: str, keywords: set[str]) -> bool:
    return any(keyword in token for keyword in keywords)


def _add_profile_claim(
    profiles: dict[str, dict[str, Any]],
    target: str,
    key: str,
    value: str,
    item: dict[str, Any],
) -> None:
    profile = profiles.setdefault(target, {"claims": [], "rows": [], "row_count": 0})
    claim = f"{key}={value}"
    if claim not in profile["claims"]:
        profile["claims"].append(claim)
        profile["rows"].append({
            "claim": claim,
            "source": item.get("source") or item.get("source_name") or "public_web_search",
            "url": item.get("url"),
            "confidence": item.get("confidence"),
            "record_kind": item.get("record_kind"),
        })


def _merge_qyyjt_public_plan_profile(
    profiles: dict[str, dict[str, Any]],
    item: dict[str, Any],
    records: list[tuple[str, dict[str, str]]],
) -> None:
    text = " ".join(claim for claim, _parsed in records).lower()
    targets: list[str] = []
    if _contains_any(text, MONEY_KEYWORDS):
        targets.append("public_capital_profile")
    if _contains_any(text, GOODS_KEYWORDS):
        targets.append("public_goods_profile")
    if _contains_any(text, PEOPLE_KEYWORDS) or "risk" in text:
        targets.append("public_people_profile")
    if not targets:
        targets.append("public_people_profile")
    lead = str(item.get("title") or item.get("summary") or item.get("claim") or "qyyjt public-search lead")
    for target in dict.fromkeys(targets):
        _add_profile_claim(profiles, target, "qyyjt_public_plan_lead", lead, item)
