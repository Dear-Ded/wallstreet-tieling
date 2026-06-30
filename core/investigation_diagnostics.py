#!/usr/bin/env python3
"""Diagnostics builders for product-facing investigation packets."""
from __future__ import annotations

from typing import Any

from .qyyjt_benchmark import build_qyyjt_benchmark


NON_FAILURE_STATUSES = {"success", "ok", "skipped_unsupported_source"}
NON_FAILURE_CATEGORIES = {"", "none", "success", "skipped_unsupported_source"}
COVERAGE_STATUSES = {
    "skipped_unsupported_source",
    "empty",
    "empty_result",
    "no_results",
    "not_searched",
}


def build_source_failure_summary(
    summary: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Build source diagnostics without treating coverage gaps as low risk."""
    retrieval_summary = _dict(diagnostics.get("retrieval_summary"))
    raw_diagnostics = diagnostics.get("source_diagnostics")
    if not isinstance(raw_diagnostics, list):
        raw_diagnostics = []

    rows = [_dict(item) for item in raw_diagnostics if isinstance(item, dict)]
    attempted_count = len(rows)
    status_counts = _dict(retrieval_summary.get("status_counts"))
    if not status_counts:
        status_counts = _dict(summary.get("status_counts"))

    by_failure_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status") or "unknown").lower()
        category = str(row.get("failure_category") or _failure_category_from_status(status, row)).lower()
        if status and status != "unknown":
            by_status[status] = by_status.get(status, 0) + 1
        if status in NON_FAILURE_STATUSES or category in NON_FAILURE_CATEGORIES:
            continue
        is_failure = category not in NON_FAILURE_CATEGORIES or status in {
            "empty",
            "failed",
            "timeout",
            "no_results",
            "error",
        }
        if not is_failure:
            continue
        failure_category = category or "connector_error"
        by_failure_category[failure_category] = by_failure_category.get(failure_category, 0) + 1
        failures.append(_failure_row(row, status=status, category=failure_category))

    failures = sorted(
        failures,
        key=lambda item: (
            _failure_rank(item.get("failure_category")),
            str(item.get("source") or item.get("source_name") or item.get("source_hint") or ""),
        ),
    )
    run_id = (
        str(retrieval_summary.get("run_id") or diagnostics.get("run_id") or summary.get("run_id") or "")
        .strip()
    )
    execution_state = str(
        retrieval_summary.get("execution_state") or summary.get("execution_state") or "unknown"
    )
    visible_status_counts = status_counts or by_status
    coverage = _dict(retrieval_summary.get("coverage")) or _dict(summary.get("coverage"))
    missing_domains = [
        str(item)
        for item in coverage.get("missing_domains", [])
        if str(item).strip()
    ]
    domains_without_evidence = [
        str(item)
        for item in coverage.get("domains_without_evidence", [])
        if str(item).strip()
    ]
    public_origin_fallbacks = _public_origin_fallbacks(failures)
    public_origin_next_actions = _public_origin_next_actions(public_origin_fallbacks)
    recurring_failure_patterns = _recurring_failure_patterns(failures)
    coverage_recovery_actions = _coverage_recovery_actions(
        missing_domains=missing_domains,
        domains_without_evidence=domains_without_evidence,
    )
    source_routing_summary = _source_routing_summary(_dict(retrieval_summary.get("source_routing")))
    coverage_recovery_execution_plan = _coverage_recovery_execution_plan(coverage_recovery_actions)
    coverage_recovery_execution_readiness = _coverage_recovery_execution_readiness(
        coverage_recovery_execution_plan,
        source_routing_summary,
    )
    coverage_interpretation = {
        "not_searched_count": len(missing_domains),
        "no_evidence_count": len(domains_without_evidence),
        "policy": "not_searched means coverage was not attempted; no_evidence means attempted sources returned no usable evidence.",
    }
    coverage_recovery_decision = _coverage_recovery_decision(
        coverage_recovery_actions,
        coverage_recovery_execution_plan,
        coverage_recovery_execution_readiness,
    )
    source_resilience_profile = _source_resilience_profile(
        attempted_source_count=attempted_count,
        failure_count=len(failures),
        by_failure_category=by_failure_category,
        missing_domains=missing_domains,
        domains_without_evidence=domains_without_evidence,
        source_routing_summary=source_routing_summary,
        coverage_recovery_execution_readiness=coverage_recovery_execution_readiness,
        coverage_recovery_decision=coverage_recovery_decision,
        coverage_interpretation=coverage_interpretation,
    )
    return {
        "run_id": run_id,
        "execution_state": execution_state,
        "attempted_source_count": attempted_count,
        "status_counts": visible_status_counts,
        "by_status": by_status,
        "coverage_status_counts": {
            key: count for key, count in visible_status_counts.items() if key in COVERAGE_STATUSES
        },
        "failure_count": len(failures),
        "by_failure_category": by_failure_category,
        "top_failures": failures[:8],
        "recurring_failure_patterns": recurring_failure_patterns,
        "public_origin_fallbacks": public_origin_fallbacks,
        "public_origin_next_actions": public_origin_next_actions,
        "coverage_recovery_actions": coverage_recovery_actions,
        "coverage_recovery_execution_plan": coverage_recovery_execution_plan,
        "coverage_recovery_execution_readiness": coverage_recovery_execution_readiness,
        "coverage_recovery_decision": coverage_recovery_decision,
        "coverage_recovery_summary": _coverage_recovery_summary(coverage_recovery_actions),
        "source_routing_summary": source_routing_summary,
        "source_resilience_profile": source_resilience_profile,
        "has_failures": bool(failures),
        "missing_domains": missing_domains[:12],
        "domains_without_evidence": domains_without_evidence[:12],
        "coverage_interpretation": coverage_interpretation,
        "policy": "Source diagnostics explain retrieval health only; failures and empty results must not be interpreted as low risk.",
    }


def _recurring_failure_patterns(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate repeated source failures into operator-facing repair patterns."""
    if not failures:
        return []
    patterns: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in failures:
        category = str(item.get("failure_category") or "connector_error").strip() or "connector_error"
        source = str(item.get("source") or item.get("source_name") or item.get("source_hint") or "unknown").strip() or "unknown"
        domain = _failure_domain(item)
        key = (category, source, domain)
        row = patterns.setdefault(
            key,
            {
                "failure_category": category,
                "source": source,
                "domain": domain,
                "count": 0,
                "trace_ids": [],
                "objectives": [],
                "operator_action": _recurring_failure_action(category, source, domain),
            },
        )
        row["count"] += 1
        trace_id = str(item.get("trace_id") or "").strip()
        if trace_id and trace_id not in row["trace_ids"]:
            row["trace_ids"].append(trace_id)
        objective = str(item.get("objective") or "").strip()
        if objective and objective not in row["objectives"]:
            row["objectives"].append(_short_text(objective, 120))

    rows = [
        {
            **row,
            "trace_ids": row["trace_ids"][:5],
            "objectives": row["objectives"][:3],
        }
        for row in patterns.values()
        if int(row.get("count") or 0) >= 2
    ]
    rows.sort(key=lambda row: (-int(row.get("count") or 0), str(row.get("failure_category")), str(row.get("source"))))
    return rows[:8]


def _failure_domain(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("objective", "source", "source_name", "source_hint", "error")
    ).lower()
    if any(key in text for key in ("bond", "financ", "credit", "debt", "pledge", "freeze", "auction", "capital")):
        return "financing_capital_markets"
    if any(key in text for key in ("shareholder", "ubo", "controller", "owner", "related", "group")):
        return "ownership_control"
    if any(key in text for key in ("court", "case", "judgment", "enforcement", "penalty", "dishonesty", "legal")):
        return "legal_admin"
    if any(key in text for key in ("supplier", "customer", "procurement", "trade", "import", "export")):
        return "trade_supply_chain"
    if any(key in text for key in ("patent", "trademark", "copyright", "ip")):
        return "ip_assets"
    if any(key in text for key in ("news", "negative", "media", "opinion")):
        return "public_opinion"
    return "general_retrieval"


def _recurring_failure_action(category: str, source: str, domain: str) -> str:
    if category == "authorization":
        return f"Confirm credentials or explicit user authorization for {source} before retrying {domain}."
    if category == "timeout":
        return f"Reduce query fan-out or raise timeout for {source}; keep {domain} recovery queued until a bounded retry succeeds."
    if category == "rate_limit":
        return f"Back off and retry {source} with lower concurrency; preserve {domain} as partial coverage until recovered."
    if category == "empty_result":
        return f"Try official/public fallback sources for {domain}; keep empty {source} rows as coverage gaps, not low-risk evidence."
    if category == "network":
        return f"Retry {source} after network health check; do not treat missing {domain} evidence as a clean result."
    return f"Repair or replace {source} connector for {domain}; keep affected findings as incomplete coverage."


def _source_resilience_profile(
    *,
    attempted_source_count: int,
    failure_count: int,
    by_failure_category: dict[str, int],
    missing_domains: list[str],
    domains_without_evidence: list[str],
    source_routing_summary: dict[str, Any],
    coverage_recovery_execution_readiness: dict[str, Any],
    coverage_recovery_decision: dict[str, Any],
    coverage_interpretation: dict[str, Any],
) -> dict[str, Any]:
    """Collapse retrieval health into a product-facing resilience profile."""
    attempted = max(int(attempted_source_count or 0), 0)
    configured = int(source_routing_summary.get("configured_count") or 0)
    available = int(source_routing_summary.get("available_count") or 0)
    health_report_count = int(source_routing_summary.get("health_report_count") or 0)
    ready_recovery = int(coverage_recovery_execution_readiness.get("ready_count") or 0)
    blocked_recovery = int(coverage_recovery_execution_readiness.get("blocked_count") or 0)
    not_searched = int(coverage_interpretation.get("not_searched_count") or len(missing_domains))
    no_evidence = int(coverage_interpretation.get("no_evidence_count") or len(domains_without_evidence))

    score = 100
    score -= min(35, failure_count * 10)
    score -= min(25, not_searched * 8)
    score -= min(18, no_evidence * 5)
    if configured:
        unavailable = max(configured - available, 0)
        score -= min(15, unavailable * 5)
    if blocked_recovery and not ready_recovery:
        score -= 10
    if attempted == 0 and health_report_count == 0:
        score -= 12
    score = max(0, min(100, score))

    if score >= 85 and failure_count == 0 and not_searched == 0:
        status = "resilient"
    elif ready_recovery > 0:
        status = "recoverable_now"
    elif failure_count or not_searched or blocked_recovery:
        status = "needs_operator_recovery"
    else:
        status = "partial_visibility"

    blocker_counts = dict(coverage_recovery_decision.get("blocker_counts") or {})
    top_blockers = sorted(
        [
            {"blocker": key, "count": value}
            for key, value in {**by_failure_category, **blocker_counts}.items()
            if int(value or 0) > 0
        ],
        key=lambda item: (-int(item["count"]), str(item["blocker"])),
    )
    return {
        "type": "source_resilience_profile",
        "status": status,
        "score": score,
        "attempted_source_count": attempted,
        "configured_source_count": configured,
        "available_source_count": available,
        "failure_count": failure_count,
        "not_searched_count": not_searched,
        "no_evidence_count": no_evidence,
        "recovery_ready_count": ready_recovery,
        "recovery_blocked_count": blocked_recovery,
        "top_blockers": top_blockers[:6],
        "recommended_action": coverage_recovery_decision.get("next_action") or "",
        "ready_to_recover_now": bool(ready_recovery),
        "policy": "Source resilience is retrieval/recovery health only; it is not a subject risk verdict.",
    }


def _source_routing_summary(source_routing: dict[str, Any]) -> dict[str, Any]:
    health_reports = _dict(source_routing.get("health_reports"))
    configured_sources = [
        str(item) for item in source_routing.get("configured_sources", [])
        if str(item).strip()
    ]
    available_sources = [
        str(item) for item in source_routing.get("available_sources", [])
        if str(item).strip()
    ]
    unavailable_sources = [
        str(item) for item in source_routing.get("unavailable_sources", [])
        if str(item).strip()
    ]
    smoke_tested_sources = sorted(
        str(name)
        for name, report in health_reports.items()
        if isinstance(report, dict) and report.get("smoke_tested") is True
    )
    explicit_only_sources = sorted(
        str(name)
        for name, report in health_reports.items()
        if isinstance(report, dict)
        and report.get("ok") is True
        and report.get("enabled") is False
    )
    return {
        "configured_count": int(source_routing.get("configured_count") or len(configured_sources)),
        "available_count": int(source_routing.get("available_count") or len(available_sources)),
        "configured_sources": configured_sources[:12],
        "available_sources": available_sources[:12],
        "unavailable_sources": unavailable_sources[:12],
        "smoke_tested_sources": smoke_tested_sources[:12],
        "explicit_only_sources": explicit_only_sources[:12],
        "health_report_count": len(health_reports),
        "policy": "Routing health describes source availability and smoke coverage; it is not evidence about the subject.",
    }


def _coverage_recovery_actions(
    *,
    missing_domains: list[str],
    domains_without_evidence: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    domain_map = {
        "corporate_registry": {
            "source": "official_company_registry",
            "query": "legal name + registration id",
            "lane": "subject_resolution",
            "fallback_sources": ["gsxt_public", "provincial_registry_portals", "codata_org_cn", "opencorporates_public"],
            "key_fields": ["uscc", "legal_person", "registered_capital", "business_status", "business_scope"],
        },
        "ownership_control": {
            "source": "registry_shareholder_filings",
            "query": "company + shareholder/controller/UBO",
            "lane": "people",
            "fallback_sources": ["gsxt_shareholder_tabs", "cninfo_disclosures", "gleif_relationships"],
            "key_fields": ["shareholder_name", "share_ratio", "equity_pledge", "ubo_candidate", "parent_company"],
        },
        "related_entities": {
            "source": "annual_reports_and_company_announcements",
            "query": "company + subsidiary/affiliate/related party",
            "lane": "people",
            "fallback_sources": ["cninfo_disclosures", "sec_edgar_public_api", "gleif_relationships"],
            "key_fields": ["subsidiary", "affiliate", "related_party", "external_investment"],
        },
        "financing_capital_markets": {
            "source": "exchange_disclosures_and_bond_portals",
            "query": "company + bond/financing/guarantee/default/rating",
            "lane": "capital",
            "fallback_sources": ["chinabond_public", "chinamoney_public", "cninfo_bond_announcements", "shclearing_public", "northdata_public"],
            "key_fields": ["bond_name", "issue_amount", "coupon_rate", "maturity_date", "credit_rating", "default_history", "business_credit_score"],
        },
        "legal_admin": {
            "source": "court_and_enforcement_publicity",
            "query": "company + court/enforcement/penalty/dishonesty",
            "lane": "legal",
            "fallback_sources": ["wenshu_public", "zxgk_court_public", "court_hearing_public", "authorized_legal_database"],
            "key_fields": ["case_number", "court", "judgment_date", "case_type", "enforcement_amount", "dishonesty_reason"],
        },
        "administrative_risk": {
            "source": "creditchina_public",
            "query": "company + administrative penalty/regulatory notice",
            "lane": "legal",
            "fallback_sources": ["provincial_creditchina_portals", "csrc_penalty_public", "sector_regulator_notices"],
            "key_fields": ["penalty_decision_number", "penalty_date", "issuing_authority", "violation_type", "penalty_amount"],
        },
        "public_opinion": {
            "source": "public_news_search",
            "query": "company + negative news/product/channel/partnership",
            "lane": "reputation",
            "fallback_sources": ["baidu_news_public", "public_web_search", "authorized_media_database"],
            "key_fields": ["title", "publisher", "published_at", "url", "summary"],
        },
        "social_web": {
            "source": "public_social_and_news_search",
            "query": "company + public complaint/recruiting/public account",
            "lane": "reputation",
            "fallback_sources": ["public_web_search", "public_account_search", "authorized_social_monitoring"],
            "key_fields": ["post_title", "publisher", "published_at", "engagement", "url"],
        },
        "sanctions_watchlist": {
            "source": "public_sanctions_dataset_catalogs",
            "query": "company/person + sanctions/debarment/watchlist",
            "lane": "risk",
            "fallback_sources": ["ofac_sdn_public", "eu_sanctions_map", "world_bank_debarment", "un_sanctions_public"],
            "key_fields": ["listed_name", "program", "listed_at", "identifier", "source_url"],
        },
        "ip_assets": {
            "source": "ip_public_search",
            "query": "company + patent/trademark/software copyright",
            "lane": "goods",
            "fallback_sources": ["cnipa_public", "trademark_office_public", "wipo_patentscope", "google_patents_public"],
            "key_fields": ["asset_type", "application_number", "owner", "status", "application_date"],
        },
        "ip_tech": {
            "source": "ip_public_search",
            "query": "company + patent/trademark/software copyright",
            "lane": "goods",
            "fallback_sources": ["cnipa_public", "trademark_office_public", "wipo_patentscope", "google_patents_public"],
            "key_fields": ["asset_type", "application_number", "owner", "status", "application_date"],
        },
        "trade_supply_chain": {
            "source": "customs_trade_publications_and_procurement",
            "query": "company + import/export/procurement/customer/supplier",
            "lane": "goods",
            "fallback_sources": ["customs_publications", "government_procurement_public", "sec_customer_supplier_disclosures", "sam_gov_public", "usaspending_public"],
            "key_fields": ["supplier", "customer", "amount", "product", "shipment_or_contract_date", "contract_award_id"],
        },
    }
    origin_priority_map = {
        "corporate_registry": [
            {"tier": "official_public", "sources": ["gsxt_public", "provincial_registry_portals", "codata_org_cn"]},
            {"tier": "global_public_registry", "sources": ["opencorporates_public", "companies_house_public", "openownership_public"]},
            {"tier": "public_fallback", "sources": ["commercial_platform_public_pages"]},
            {"tier": "authorized_aggregator", "sources": ["licensed_registry_api"]},
        ],
        "ownership_control": [
            {"tier": "official_public", "sources": ["gsxt_shareholder_tabs", "cninfo_disclosures", "gleif_relationships"]},
            {"tier": "global_public_registry", "sources": ["openownership_public", "opencorporates_public"]},
            {"tier": "public_fallback", "sources": ["commercial_platform_public_pages"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "licensed_registry_api"]},
        ],
        "related_entities": [
            {"tier": "official_public", "sources": ["gsxt_external_investment", "cninfo_disclosures", "gleif_relationships"]},
            {"tier": "global_public_registry", "sources": ["opencorporates_public", "openownership_public"]},
            {"tier": "public_fallback", "sources": ["commercial_platform_public_pages"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "licensed_registry_api"]},
        ],
        "financing_capital_markets": [
            {"tier": "official_public", "sources": ["chinabond_public", "chinamoney_public", "cninfo_bond_announcements", "shclearing_public"]},
            {"tier": "global_public_business_credit", "sources": ["northdata_public", "duns_lookup_public"]},
            {"tier": "public_fallback", "sources": ["exchange_disclosure_search"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "licensed_rating_feed", "creditsafe_authorized", "dnb_authorized"]},
        ],
        "legal_admin": [
            {"tier": "official_public", "sources": ["wenshu_public", "zxgk_court_public", "court_hearing_public"]},
            {"tier": "global_public_court", "sources": ["courtlistener_public", "uk_judgments_public", "curia_public"]},
            {"tier": "public_fallback", "sources": ["public_web_search"]},
            {"tier": "authorized_aggregator", "sources": ["authorized_legal_database"]},
        ],
        "administrative_risk": [
            {"tier": "official_public", "sources": ["creditchina_public", "provincial_creditchina_portals", "sector_regulator_notices"]},
            {"tier": "public_fallback", "sources": ["public_web_search"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "licensed_registry_api"]},
        ],
        "public_opinion": [
            {"tier": "official_public", "sources": ["baidu_news_public", "google_news_rss"]},
            {"tier": "global_public_archive", "sources": ["gdelt_public_api", "wayback_cdx_public"]},
            {"tier": "public_fallback", "sources": ["public_web_search"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "authorized_media_database"]},
        ],
        "social_web": [
            {"tier": "official_public", "sources": ["public_account_search"]},
            {"tier": "public_fallback", "sources": ["public_web_search"]},
            {"tier": "authorized_aggregator", "sources": ["authorized_social_monitoring"]},
        ],
        "sanctions_watchlist": [
            {"tier": "official_public", "sources": ["ofac_sdn_public", "eu_sanctions_map", "world_bank_debarment", "un_sanctions_public"]},
            {"tier": "public_fallback", "sources": ["public_sanctions_dataset_catalogs"]},
            {"tier": "authorized_aggregator", "sources": ["licensed_screening_feed"]},
        ],
        "ip_assets": [
            {"tier": "official_public", "sources": ["cnipa_public", "trademark_office_public", "wipo_patentscope"]},
            {"tier": "public_fallback", "sources": ["google_patents_public"]},
            {"tier": "authorized_aggregator", "sources": ["licensed_patent_database"]},
        ],
        "ip_tech": [
            {"tier": "official_public", "sources": ["cnipa_public", "trademark_office_public", "wipo_patentscope"]},
            {"tier": "public_fallback", "sources": ["google_patents_public"]},
            {"tier": "authorized_aggregator", "sources": ["licensed_patent_database"]},
        ],
        "trade_supply_chain": [
            {"tier": "official_public", "sources": ["government_procurement_public", "customs_publications", "sam_gov_public", "usaspending_public"]},
            {"tier": "global_public_trade", "sources": ["un_comtrade_public", "importyeti_public"]},
            {"tier": "global_public_procurement", "sources": ["ted_public", "ungm_public"]},
            {"tier": "public_fallback", "sources": ["sec_customer_supplier_disclosures"]},
            {"tier": "authorized_aggregator", "sources": ["qyyjt_authorized_api", "licensed_trade_database"]},
        ],
    }

    def add(domain: str, gap_type: str) -> None:
        config = domain_map.get(
            domain,
            {
                "source": "public_web_search",
                "query": f"{domain} + subject name",
                "lane": "source",
                "fallback_sources": ["public_web_search"],
                "key_fields": ["title", "url", "observed_at"],
            },
        )
        actions.append({
            "action_id": f"COVERAGE-{gap_type.upper()}-{_action_token(domain)}",
            "priority": "P0" if gap_type == "missing" else "P1",
            "gap_type": gap_type,
            "domain": domain,
            "target_lane": config["lane"],
            "suggested_source": config["source"],
            "fallback_sources": config["fallback_sources"],
            "origin_priority": origin_priority_map.get(
                domain,
                [
                    {"tier": "public_fallback", "sources": ["public_web_search"]},
                    {"tier": "authorized_aggregator", "sources": ["user_authorized_source"]},
                ],
            ),
            "query_family": config["query"],
            "key_fields": config["key_fields"],
            "done_condition": "Capture source URL, observed time, field provenance, and mark empty results as coverage gaps.",
            "evidence_boundary": "public or user-authorized channels only; unverified rows stay lead-only until corroborated.",
        })

    for domain in missing_domains[:8]:
        add(domain, "missing")
    for domain in domains_without_evidence[:8]:
        add(domain, "empty")
    return actions[:12]


def _coverage_recovery_summary(actions: list[dict[str, Any]]) -> dict[str, Any]:
    by_priority: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for item in actions:
        priority = str(item.get("priority") or "unknown")
        lane = str(item.get("target_lane") or "source")
        domain = str(item.get("domain") or "unknown")
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_lane[lane] = by_lane.get(lane, 0) + 1
        by_domain[domain] = by_domain.get(domain, 0) + 1

    first_action = actions[0] if actions else {}
    return {
        "action_count": len(actions),
        "p0_count": by_priority.get("P0", 0),
        "p1_count": by_priority.get("P1", 0),
        "by_priority": by_priority,
        "by_lane": by_lane,
        "by_domain": by_domain,
        "top_next_action": {
            "action_id": first_action.get("action_id"),
            "domain": first_action.get("domain"),
            "target_lane": first_action.get("target_lane"),
            "suggested_source": first_action.get("suggested_source"),
            "query_family": first_action.get("query_family"),
        } if first_action else {},
        "policy": "Summarizes coverage recovery actions for UI routing; it is not a risk verdict.",
    }


def _coverage_recovery_execution_plan(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        domain = str(action.get("domain") or "").strip()
        action_id = str(action.get("action_id") or "").strip()
        priority = str(action.get("priority") or "").strip() or "P1"
        query_family = str(action.get("query_family") or "").strip()
        key_fields = [
            str(value).strip()
            for value in action.get("key_fields", [])
            if str(value).strip()
        ] if isinstance(action.get("key_fields"), list) else []
        origin_priority = [
            item for item in action.get("origin_priority", [])
            if isinstance(item, dict)
        ] if isinstance(action.get("origin_priority"), list) else []
        step_index = 1
        for origin in origin_priority:
            tier = str(origin.get("tier") or "").strip()
            sources = [
                str(value).strip()
                for value in origin.get("sources", [])
                if str(value).strip()
            ] if isinstance(origin.get("sources"), list) else []
            for source in sources[:4]:
                plan.append(
                    {
                        "step_id": f"{action_id}-STEP-{step_index}",
                        "action_id": action_id,
                        "domain": domain,
                        "priority": priority,
                        "tier": tier,
                        "source": source,
                        "query_family": query_family,
                        "key_fields": key_fields[:6],
                        "admission_rule": "official_public can become evidence after provenance/entity-match gates; public_fallback and authorized_aggregator remain lead-only until corroborated.",
                    }
                )
                step_index += 1
        if step_index == 1:
            plan.append(
                {
                    "step_id": f"{action_id}-STEP-1",
                    "action_id": action_id,
                    "domain": domain,
                    "priority": priority,
                    "tier": "public_fallback",
                    "source": str(action.get("suggested_source") or "public_web_search"),
                    "query_family": query_family,
                    "key_fields": key_fields[:6],
                    "admission_rule": "lead-only until corroborated by public or user-authorized source records.",
                }
            )
    return plan[:40]


def _coverage_recovery_execution_readiness(
    plan: list[dict[str, Any]],
    source_routing_summary: dict[str, Any],
) -> dict[str, Any]:
    available = {
        str(item)
        for item in source_routing_summary.get("available_sources", [])
        if str(item).strip()
    }
    configured = {
        str(item)
        for item in source_routing_summary.get("configured_sources", [])
        if str(item).strip()
    }
    explicit_only = {
        str(item)
        for item in source_routing_summary.get("explicit_only_sources", [])
        if str(item).strip()
    }
    smoke_tested = {
        str(item)
        for item in source_routing_summary.get("smoke_tested_sources", [])
        if str(item).strip()
    }
    by_status: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    ready_steps: list[dict[str, Any]] = []
    blocked_steps: list[dict[str, Any]] = []

    for step in plan:
        if not isinstance(step, dict):
            continue
        source = str(step.get("source") or "").strip()
        tier = str(step.get("tier") or "unknown").strip()
        status = "connector_required"
        if source in available:
            status = "ready"
        elif source in explicit_only:
            status = "explicit_enable_required"
        elif source in configured:
            status = "configured_unavailable"
        elif source in smoke_tested:
            status = "smoke_tested_not_enabled"

        by_status[status] = by_status.get(status, 0) + 1
        by_tier[tier] = by_tier.get(tier, 0) + 1
        row = {
            "step_id": step.get("step_id"),
            "domain": step.get("domain"),
            "priority": step.get("priority"),
            "tier": tier,
            "source": source,
            "status": status,
            "query_family": step.get("query_family"),
            "key_fields": list(step.get("key_fields") or [])[:6],
            "required_action": _coverage_recovery_step_required_action(status, source),
        }
        if status == "ready":
            ready_steps.append(row)
        else:
            blocked_steps.append(row)

    return {
        "step_count": len([step for step in plan if isinstance(step, dict)]),
        "ready_count": by_status.get("ready", 0),
        "blocked_count": sum(count for status, count in by_status.items() if status != "ready"),
        "by_status": by_status,
        "by_tier": by_tier,
        "ready_steps": ready_steps[:8],
        "blocked_steps": blocked_steps[:8],
        "policy": "Readiness is connector availability only; it does not prove evidence exists or clear a coverage gap.",
    }


def _coverage_recovery_step_required_action(status: str, source: str) -> str:
    if status == "ready":
        return f"Run {source}; capture URL, observed time, entity match, and required fields before admission."
    if status == "explicit_enable_required":
        return f"Obtain explicit user confirmation or credentials before enabling {source}."
    if status == "configured_unavailable":
        return f"Repair health, credentials, or routing for configured source {source}."
    if status == "smoke_tested_not_enabled":
        return f"Enable smoke-tested source {source} for this run before retrying."
    return f"Add or map a connector for {source} before retrying this recovery step."


def _coverage_recovery_decision(
    actions: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Pick the next executable recovery move and explain why other steps block."""
    ready_steps = [
        item for item in readiness.get("ready_steps", [])
        if isinstance(item, dict)
    ]
    blocked_steps = [
        item for item in readiness.get("blocked_steps", [])
        if isinstance(item, dict)
    ]
    plan_by_step = {
        str(item.get("step_id")): item
        for item in plan
        if isinstance(item, dict) and item.get("step_id")
    }

    next_step = ready_steps[0] if ready_steps else blocked_steps[0] if blocked_steps else {}
    next_plan = plan_by_step.get(str(next_step.get("step_id")), {}) if next_step else {}
    blocker_counts: dict[str, int] = {}
    for item in blocked_steps:
        status = str(item.get("status") or "unknown")
        blocker_counts[status] = blocker_counts.get(status, 0) + 1

    if ready_steps:
        decision = "run_ready_recovery_step"
        blocker = None
    elif blocked_steps:
        decision = "enable_or_add_connector_before_retry"
        blocker = str(next_step.get("status") or "connector_required")
    elif actions:
        decision = "define_execution_plan"
        blocker = "no_execution_plan"
    else:
        decision = "no_recovery_needed"
        blocker = None

    return {
        "decision": decision,
        "ready_to_run": bool(ready_steps),
        "recommended_step": {
            "step_id": next_step.get("step_id"),
            "action_id": next_plan.get("action_id"),
            "domain": next_step.get("domain"),
            "priority": next_step.get("priority"),
            "tier": next_step.get("tier"),
            "source": next_step.get("source"),
            "status": next_step.get("status"),
            "query_family": next_plan.get("query_family"),
            "key_fields": list(next_plan.get("key_fields") or [])[:6],
        } if next_step else {},
        "blocked_reason": blocker,
        "blocker_counts": blocker_counts,
        "ready_count": len(ready_steps),
        "blocked_count": len(blocked_steps),
        "next_action": _coverage_recovery_decision_text(decision, next_step, next_plan, blocker),
        "policy": "This is an execution routing decision for coverage recovery, not a claim that evidence exists.",
    }


def _coverage_recovery_decision_text(
    decision: str,
    step: dict[str, Any],
    plan: dict[str, Any],
    blocker: str | None,
) -> str:
    source = step.get("source") or plan.get("source") or "source"
    domain = step.get("domain") or plan.get("domain") or "coverage"
    if decision == "run_ready_recovery_step":
        return f"Run {source} for {domain}; capture URL, observed time, entity match, and required fields before admission."
    if decision == "enable_or_add_connector_before_retry":
        return f"Enable or add connector for {source} before retrying {domain}; current blocker={blocker}."
    if decision == "define_execution_plan":
        return "Define a source-specific execution plan before attempting coverage recovery."
    return "No coverage recovery action is currently required."


def _action_token(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value).upper()).strip("_") or "UNKNOWN"


def _public_origin_fallbacks(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not failures:
        return []
    qyyjt_failures = [
        item for item in failures
        if "qyyjt" in " ".join(
            str(item.get(key) or "")
            for key in ("source", "source_name", "source_hint", "objective")
        ).lower()
    ]
    if not qyyjt_failures:
        return []
    benchmark = build_qyyjt_benchmark()
    plans = _dict(benchmark.get("summary")).get("public_origin_plans")
    if not isinstance(plans, dict):
        return []
    selected_modules = _select_public_origin_modules(qyyjt_failures, plans)
    rows_by_module = {
        str(row.get("module")): row
        for row in benchmark.get("rows", [])
        if isinstance(row, dict) and row.get("module")
    }
    fallbacks: list[dict[str, Any]] = []
    for module in selected_modules:
        plan = _dict(plans.get(module))
        if not plan:
            continue
        benchmark_row = _dict(rows_by_module.get(module))
        field_contract = _dict(benchmark_row.get("field_contract"))
        fallbacks.append(
            {
                "blocked_source": "qyyjt",
                "module": module,
                "fallback_mode": plan.get("fallback_mode"),
                "origin_channels": list(plan.get("origin_channels") or [])[:4],
                "query_families": list(plan.get("query_families") or [])[:4],
                "evidence_boundary": plan.get("evidence_boundary"),
                "compliance_rule": plan.get("compliance_rule"),
                "field_contract": field_contract,
                "required_fields": list(field_contract.get("required_fields") or [])[:8],
                "record_type": field_contract.get("record_type"),
                "admission_gate": benchmark_row.get("admission_gate"),
                "acceptance_gate": benchmark_row.get("acceptance_gate"),
            }
        )
    return fallbacks


def _select_public_origin_modules(
    qyyjt_failures: list[dict[str, Any]],
    plans: dict[str, Any],
) -> tuple[str, ...]:
    text = " ".join(
        " ".join(str(item.get(key) or "") for key in ("source", "source_name", "source_hint", "objective", "error"))
        for item in qyyjt_failures
    ).lower()
    selected: list[str] = []

    def add(*modules: str) -> None:
        for module in modules:
            if module in plans and module not in selected:
                selected.append(module)

    add("ent_basic")
    if any(key in text for key in ("controller", "ubo", "beneficial", "shareholder", "relation", "related", "group")):
        add("actual_controller")
    if any(key in text for key in ("court", "case", "judgment", "wenshu", "execution", "dishonesty", "penalty", "legal")):
        add("court_cases", "execution", "dishonesty", "ent_penalty")
    if any(key in text for key in ("finance", "financing", "bond", "debt", "credit", "pledge", "default", "rating")):
        add("ent_financing", "bond_profile", "bond_credit", "bond_default")
    if any(key in text for key in ("news", "negative", "opinion", "reputation", "media")):
        add("news_negative")
    if len(selected) == 1:
        add("actual_controller", "ent_financing", "court_cases", "news_negative")
    return tuple(selected[:8])


def _public_origin_next_actions(fallbacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    lane_by_module = {
        "ent_basic": "subject_resolution",
        "actual_controller": "people",
        "ent_financing": "capital",
        "bond_profile": "capital",
        "bond_credit": "capital",
        "bond_default": "capital",
        "court_cases": "legal",
        "execution": "legal",
        "dishonesty": "legal",
        "ent_penalty": "legal",
        "news_negative": "reputation",
    }
    for item in fallbacks:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or "").strip()
        channels = [str(value) for value in item.get("origin_channels", []) if str(value).strip()]
        queries = [str(value) for value in item.get("query_families", []) if str(value).strip()]
        if not module or not channels:
            continue
        actions.append(
            {
                "action_id": f"PUBLIC-ORIGIN-{module.upper()}",
                "priority": "P0" if module in {"ent_basic", "actual_controller", "ent_financing"} else "P1",
                "target_lane": lane_by_module.get(module, "source"),
                "blocked_source": item.get("blocked_source") or "qyyjt",
                "module": module,
                "suggested_source": channels[0],
                "query_family": queries[0] if queries else "",
                "reason": f"Authorized aggregator unavailable; continue {module} via official/public origin channel.",
                "done_condition": item.get("acceptance_gate") or "Capture source URL, observed time, field provenance, and keep rows lead-only until corroborated.",
                "evidence_boundary": item.get("evidence_boundary"),
                "compliance_rule": item.get("compliance_rule"),
                "required_fields": list(item.get("required_fields") or [])[:8],
                "record_type": item.get("record_type"),
                "admission_gate": item.get("admission_gate"),
            }
        )
    return actions


def _failure_row(row: dict[str, Any], *, status: str, category: str) -> dict[str, Any]:
    return {
        "source": row.get("source") or row.get("source_name"),
        "source_name": row.get("source_name"),
        "source_hint": row.get("source_hint"),
        "source_type": row.get("source_type"),
        "status": status,
        "failure_category": category,
        "trace_id": row.get("trace_id"),
        "run_id": row.get("run_id"),
        "timeout_seconds": row.get("timeout_seconds"),
        "objective": row.get("objective"),
        "error": _short_text(row.get("error") or row.get("message") or row.get("error_type"), 160),
    }


def _failure_category_from_status(status: str, row: dict[str, Any]) -> str:
    if status in {"success", "ok"}:
        return "none"
    if status == "skipped_unsupported_source":
        return "skipped_unsupported_source"
    if status in {"empty", "no_results"}:
        return "empty_result"
    if status == "timeout":
        return "timeout"
    text = " ".join(
        str(row.get(key) or "")
        for key in ("error", "message", "error_type", "objective", "source_hint")
    ).lower()
    if "403" in text or "401" in text or "auth" in text or "permission" in text:
        return "authorization"
    if "429" in text or "rate" in text or "limit" in text:
        return "rate_limit"
    if "network" in text or "connection" in text or "dns" in text:
        return "network"
    return "connector_error"


def _failure_rank(category: Any) -> int:
    order = {
        "timeout": 0,
        "authorization": 1,
        "rate_limit": 2,
        "network": 3,
        "connector_error": 4,
        "empty_result": 5,
        "skipped_unsupported_source": 6,
        "unknown": 7,
        "none": 8,
    }
    return order.get(str(category), 8)


def _short_text(raw: Any, limit: int) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
