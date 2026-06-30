#!/usr/bin/env python3
"""Tests for connector capability registry."""
from __future__ import annotations

from core.connector_registry import ConnectorRegistry, ConnectorStatus
from core.intelligence_retrieval import ConnectorShape, RetrievalDomain, SourceAccess
from core.qyyjt_benchmark import build_qyyjt_benchmark


def test_default_registry_marks_rest_datasource_production_ready() -> None:
    registry = ConnectorRegistry()
    connector = registry.get("multi_datasource_rest_api")

    assert connector is not None
    assert connector.production_ready is True
    assert connector.configurable_endpoint is True
    assert connector.health_check is True
    assert connector.standardized_records is True


def test_default_public_intel_is_product_entrypoint() -> None:
    connector = ConnectorRegistry().get("default_public_intel")

    assert connector is not None
    assert connector.production_ready is True
    assert connector.default_enabled is True
    assert connector.access is SourceAccess.PUBLIC
    assert connector.risk_flags == ()
    assert any("Product-facing default public intelligence" in note for note in connector.notes)


def test_registry_is_delivery_shape_neutral_but_review_aware() -> None:
    registry = ConnectorRegistry()
    telegram = registry.get("telegram_bot_public_service")

    assert telegram is not None
    assert telegram.shape is ConnectorShape.TELEGRAM_BOT
    assert telegram.access is SourceAccess.PUBLIC
    assert telegram.status is ConnectorStatus.CONDITIONALLY_ACTIVE
    assert telegram.health_check is True
    assert telegram.standardized_records is True
    assert telegram.default_enabled is True
    assert telegram.production_ready is True
    assert "credentialed_depth_requires_admission" in telegram.risk_flags
    assert "conditional_source_review_required" not in telegram.risk_flags
    assert "requires_external_transport" not in telegram.risk_flags


def test_qyyjt_connector_has_conditional_production_path() -> None:
    qyyjt = ConnectorRegistry().get("qyyjt_tool")

    assert qyyjt is not None
    assert qyyjt.health_check is True
    assert qyyjt.standardized_records is True
    assert qyyjt.access is SourceAccess.PUBLIC
    assert qyyjt.status is ConnectorStatus.CONDITIONALLY_ACTIVE
    assert qyyjt.default_enabled is True
    assert qyyjt.production_ready is True
    assert "credentialed_depth_requires_admission" in qyyjt.risk_flags


def test_public_web_search_is_zero_config_ready() -> None:
    connector = ConnectorRegistry().get("public_web_search")

    assert connector is not None
    assert connector.default_enabled is True
    assert connector.production_ready is True
    assert "requires_deduplication" not in connector.risk_flags
    assert "requires_fetcher" not in connector.risk_flags
    assert "requires_live_search_provider" not in connector.risk_flags
    assert "requires_live_provider_configuration" not in connector.risk_flags
    assert "requires_user_configured_live_provider" not in connector.risk_flags
    assert any("Zero-config public search" in note for note in connector.notes)


def test_registry_filters_by_domain_shape_and_readiness() -> None:
    registry = ConnectorRegistry()

    court_sources = registry.list(domain=RetrievalDomain.COURT_ENFORCEMENT)
    ownership_sources = registry.list(domain=RetrievalDomain.OWNERSHIP_CONTROL)
    people_sources = registry.list(domain=RetrievalDomain.PEOPLE)
    procurement_sources = registry.list(domain=RetrievalDomain.PROCUREMENT_PROJECTS)
    telegram_sources = registry.list(shape=ConnectorShape.TELEGRAM_BOT)
    production_ready = registry.list(production_ready=True)

    assert {item.name for item in court_sources} >= {
        "default_public_intel",
        "multi_datasource_rest_api",
        "qyyjt_tool",
        "official_china_court_enforcement_catalog",
    }
    assert {item.name for item in ownership_sources} >= {
        "gleif_lei_public_api",
        "sec_edgar_public_api",
        "opensanctions_public_dataset_catalog",
        "opensanctions_local_subject_index",
        "official_china_registry_portal_catalog",
    }
    assert {item.name for item in people_sources} >= {
        "telegram_bot_public_service",
        "opensanctions_public_dataset_catalog",
        "opensanctions_local_subject_index",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "idb_local_subject_index",
        "world_bank_debarred_firms_public_list",
        "wikidata_public_entity_graph",
        "official_china_court_enforcement_catalog",
    }
    assert {item.name for item in procurement_sources} >= {
        "idb_local_subject_index",
        "world_bank_debarred_firms_public_list",
    }
    assert [item.name for item in telegram_sources] == ["telegram_bot_public_service"]
    assert {item.name for item in production_ready} >= {
        "multi_datasource_rest_api",
        "default_public_intel",
        "qyyjt_tool",
        "telegram_bot_public_service",
        "opensanctions_local_subject_index",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "idb_local_subject_index",
        "world_bank_debarred_firms_public_list",
    }


def test_audit_summary_exposes_connector_counts() -> None:
    summary = ConnectorRegistry().audit_summary()

    assert summary["total"] >= 12
    assert summary["production_ready"] >= 3
    assert summary["default_enabled"] >= 4
    assert summary["by_shape"]["telegram_bot"] == 1
    assert summary["by_shape"]["official_platform"] >= 3
    assert summary["by_access"]["public"] >= 8
    assert any(item["name"] == "qyyjt_tool" for item in summary["connectors"])


def test_product_catalog_exposes_zero_config_and_admission_groups() -> None:
    catalog = ConnectorRegistry().product_catalog()

    assert catalog["type"] == "connector_catalog"
    assert catalog["version"] == "0.5.0"
    assert "default_public_intel" in catalog["summary"]["zero_config_ready"]
    assert "public_web_search" in catalog["summary"]["zero_config_ready"]
    assert catalog["groups"]["default_enabled"]
    assert catalog["groups"]["needs_admission"]
    assert catalog["groups"]["explicit_only"]
    assert catalog["summary"]["explicit_only"] >= 1
    assert catalog["summary"]["admission_counts"]
    assert catalog["summary"]["data_effectiveness"]["fact_capable_sources"] >= 4
    assert "qyyjt_tool" in catalog["summary"]["data_effectiveness"]["default_fact_source_names"]
    assert catalog["data_effectiveness"]
    assert catalog["policy"]["empty_result_rule"]
    assert catalog["policy"]["production_route_rule"]

    rows = {item["name"]: item for item in catalog["connectors"]}
    assert rows["sec_edgar_public_api"]["data_effectiveness"]["admission_mode"] == "fact_source_when_subject_match_passes"
    assert "financing_capital_markets" in rows["sec_edgar_public_api"]["data_effectiveness"]["analysis_outputs"]
    assert rows["public_web_search"]["data_effectiveness"]["admission_mode"] == "lead_source_with_exact_match_promotion"
    assert rows["official_china_registry_portal_catalog"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert rows["gleif_lei_public_api"]["admission"]["decision"] == "production_ready"
    assert rows["sec_edgar_public_api"]["admission"]["decision"] == "production_ready"
    assert rows["official_china_registry_portal_catalog"]["admission"]["production_admissible"] is False
    assert rows["enterprise_executive_identity_verification"]["default_enabled"] is False
    assert rows["enterprise_executive_identity_verification"]["access"] == "user_authorized"
    assert rows["enterprise_executive_identity_verification"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "explicit_enable_required" in rows["enterprise_domain_security_assessment"]["risk_flags"]
    assert "authorized_opensanctions_api" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "runtime_aiqicha_session_lookup" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "verified_github_public_profile" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "verified_wikipedia_enterprise_entry" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "verified_crtsh_domain_lookup" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "verified_whois_rdap_domain_lookup" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "verified_cross_platform_profile_check" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "mass_cross_platform_profiler" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "telegram_public_aggregation" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "autonomous_enterprise_registry" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert "autonomous_public_records" in {
        item["name"] for item in catalog["groups"]["explicit_only"]
    }
    assert rows["runtime_visual_challenge_solver"]["default_enabled"] is False
    assert rows["runtime_visual_challenge_solver"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "interactive_challenge_required" in rows["runtime_visual_challenge_solver"]["risk_flags"]
    assert "entity_resolution_required" in rows["runtime_username_cross_platform_verifier"]["risk_flags"]
    assert "user_session_required" in rows["runtime_aiqicha_session_lookup"]["risk_flags"]
    assert rows["verified_github_public_profile"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "cc_by_sa_attribution_required" in rows["verified_wikipedia_enterprise_entry"]["risk_flags"]
    assert "domain_attribution_required" in rows["verified_crtsh_domain_lookup"]["risk_flags"]
    assert rows["verified_whois_rdap_domain_lookup"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "entity_resolution_required" in rows["verified_cross_platform_profile_check"]["risk_flags"]
    assert rows["mass_cross_platform_profiler"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "false_positive_review_required" in rows["mass_cross_platform_profiler"]["risk_flags"]
    assert "user_credentials_required" in rows["telegram_public_aggregation"]["risk_flags"]
    assert rows["autonomous_enterprise_registry"]["default_enabled"] is False
    assert rows["autonomous_enterprise_registry"]["access"] == "user_authorized"
    assert rows["autonomous_enterprise_registry"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "interactive_challenge_required" in rows["autonomous_enterprise_registry"]["risk_flags"]
    assert rows["autonomous_public_records"]["default_enabled"] is False
    assert rows["autonomous_public_records"]["access"] == "user_authorized"
    assert rows["autonomous_public_records"]["data_effectiveness"]["can_feed_report_facts"] is False
    assert "data_minimization_review_required" in rows["autonomous_public_records"]["risk_flags"]
    assert "live_health_pending" in rows["official_china_registry_portal_catalog"]["risk_flags"]
    assert any(
        "Validated browser-handoff snapshot parser" in note
        for note in rows["official_china_registry_portal_catalog"]["notes"]
    )
    assert rows["qyyjt_tool"]["admission"]["decision"] == "conditional_production"
    assert catalog["qyyjt_benchmark"]["type"] == "qyyjt_benchmark"
    assert catalog["qyyjt_benchmark"]["summary"]["module_count"] == 45
    assert catalog["qyyjt_benchmark"]["summary"]["api_modules"] == 4
    assert catalog["qyyjt_benchmark"]["summary"]["query_plan_modules"] == 41
    assert catalog["qyyjt_benchmark"]["summary"]["default_modules"] == 0
    assert catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["concrete_api_or_legacy_modules"] == 4
    assert catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["rich_query_plan_modules"] == 41
    assert catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["concrete_api_or_legacy_module_names"] == [
        "search_multi",
        "bond_profile",
        "region_code",
        "region_economy",
    ]
    assert "actual_controller" in catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["rich_query_plan_module_names"]
    assert catalog["qyyjt_benchmark"]["summary"]["surface_profile"]["generic_fallback_module_names"] == []
    assert catalog["qyyjt_benchmark"]["summary"]["authorization_profile"]["auth_required_modules"] == 4
    assert catalog["qyyjt_benchmark"]["summary"]["authorization_profile"]["public_only_modules"] == 41
    assert catalog["qyyjt_benchmark"]["summary"]["unsupported_profile"]["unsupported_modules"] == 0
    assert catalog["qyyjt_benchmark"]["summary"]["unsupported_profile"]["unknown_semantics_modules"] == 0
    assert catalog["qyyjt_benchmark"]["summary"]["surface_lanes"]["authorized_api"] == 4
    assert catalog["qyyjt_benchmark"]["summary"]["surface_lanes"]["rich_query_plan"] == 41
    assert catalog["qyyjt_benchmark"]["summary"]["surface_lanes"]["generic_fallback"] == 0
    assert "enterprise_due_diligence" in catalog["qyyjt_benchmark"]["summary"]["module_families"]
    assert "risk_resolution" in catalog["qyyjt_benchmark"]["summary"]["module_families"]
    assert "ownership_and_relations" in catalog["qyyjt_benchmark"]["summary"]["module_families"]
    assert catalog["qyyjt_benchmark"]["summary"]["parity_priorities"]["p0_report_critical"] >= 1
    assert catalog["qyyjt_benchmark"]["summary"]["parity_priorities"]["p0_subject_resolution_entrypoint"] == 1
    assert catalog["qyyjt_benchmark"]["summary"]["p0_queue_count"] == 20
    assert catalog["qyyjt_benchmark"]["summary"]["p0_queue"][0]["module"] == "search_multi"
    assert catalog["qyyjt_benchmark"]["summary"]["p0_queue"][0]["priority_rank"] == 0
    assert catalog["qyyjt_benchmark"]["summary"]["field_contracts"]["risk_scan"]["record_type"] == "risk_overview"
    assert "severity" in catalog["qyyjt_benchmark"]["summary"]["field_contracts"]["risk_scan"]["required_fields"]
    assert any(
        item["module"] == "actual_controller"
        and "UBO confidence model" in item["next_action"]
        and item["field_contract"]["record_type"] == "controller_candidate"
        for item in catalog["qyyjt_benchmark"]["summary"]["p0_queue"]
    )
    assert any(
        row["module"] == "risk_scan"
        and row["coverage_class"] in {"api", "query_plan", "default"}
        and row["surface_lane"] in {"authorized_api", "rich_query_plan", "generic_fallback"}
        for row in catalog["qyyjt_benchmark"]["rows"]
    )


def test_qyyjt_benchmark_reports_the_current_45_module_surface() -> None:
    benchmark = build_qyyjt_benchmark()

    assert benchmark["type"] == "qyyjt_benchmark"
    assert benchmark["summary"]["module_count"] == 45
    assert benchmark["summary"]["api_modules"] == 4
    assert benchmark["summary"]["query_plan_modules"] == 41
    assert benchmark["summary"]["default_modules"] == 0
    assert benchmark["summary"]["coverage_status"] == "covered_with_gaps"
    assert benchmark["summary"]["surface_profile"]["concrete_api_or_legacy_modules"] == 4
    assert benchmark["summary"]["surface_profile"]["rich_query_plan_modules"] == 41
    assert benchmark["summary"]["surface_profile"]["generic_fallback_modules"] == 0
    assert benchmark["summary"]["surface_profile"]["concrete_api_or_legacy_module_names"] == [
        "search_multi",
        "bond_profile",
        "region_code",
        "region_economy",
    ]
    assert "risk_scan" in benchmark["summary"]["surface_profile"]["rich_query_plan_module_names"]
    assert benchmark["summary"]["surface_profile"]["generic_fallback_module_names"] == []
    assert benchmark["summary"]["authorization_profile"]["auth_required_modules"] == 4
    assert benchmark["summary"]["authorization_profile"]["public_only_modules"] == 41
    assert benchmark["summary"]["unsupported_profile"]["unsupported_modules"] == 0
    assert benchmark["summary"]["unsupported_profile"]["unknown_semantics_modules"] == 0
    assert benchmark["summary"]["surface_lanes"]["authorized_api"] == 4
    assert benchmark["summary"]["surface_lanes"]["rich_query_plan"] == 41
    assert benchmark["summary"]["surface_lanes"]["generic_fallback"] == 0
    assert benchmark["summary"]["module_families"]["risk_resolution"] >= 1
    assert benchmark["summary"]["parity_priorities"]["p0_report_critical"] >= 1
    assert benchmark["summary"]["parity_priorities"]["p1_domain_depth"] >= 1
    assert benchmark["summary"]["p0_queue_count"] == 20
    assert len(benchmark["summary"]["p0_queue"]) == 20
    assert len(benchmark["summary"]["work_items"]) == 45
    assert len(benchmark["summary"]["field_contracts"]) == 45
    assert benchmark["summary"]["work_items"][0]["module"] == "search_multi"
    assert benchmark["summary"]["work_items"][0]["priority_rank"] == 0
    assert len(benchmark["rows"]) == 45
    assert {row["coverage_class"] for row in benchmark["rows"]} <= {"api", "query_plan", "default"}
    assert {row["surface_lane"] for row in benchmark["rows"]} <= {
        "authorized_api",
        "rich_query_plan",
        "generic_fallback",
    }
    assert all(row["authorization_mode"] for row in benchmark["rows"])
    assert all(row["user_visible_status"] for row in benchmark["rows"])
    assert all(row["evidence_role"] for row in benchmark["rows"])
    assert all(row["report_admissibility"] for row in benchmark["rows"])
    assert all(row["admission_gate"] for row in benchmark["rows"])
    assert all(row["parity_priority"] for row in benchmark["rows"])
    assert all(row["acceptance_gate"] for row in benchmark["rows"])
    assert all(row["next_action"] for row in benchmark["rows"])
    assert all(row["field_contract"]["report_gate"] for row in benchmark["rows"])
    assert all(row["field_contract"]["required_common_fields"] for row in benchmark["rows"])
    assert all(row["operator_work_item"]["done_when"] for row in benchmark["rows"])
    rows = {row["module"]: row for row in benchmark["rows"]}
    assert rows["search_multi"]["evidence_role"] == "candidate_fact_after_authorized_live_validation"
    assert rows["search_multi"]["parity_priority"] == "p0_subject_resolution_entrypoint"
    assert "subject resolution" in rows["search_multi"]["next_action"]
    assert rows["risk_scan"]["evidence_role"] == "lead_only_not_verified_fact"
    assert rows["risk_scan"]["report_admissibility"] == "follow_up_lead_only_until_corroborated_by_public_or_authorized_source"
    assert "normalized alert categories" in rows["risk_scan"]["next_action"]
    assert rows["risk_scan"]["field_contract"]["record_type"] == "risk_overview"
    assert rows["risk_scan"]["field_contract"]["report_section"] == "risk_brief"
    assert rows["actual_controller"]["parity_priority"] == "p0_report_critical"
    assert "UBO confidence model" in rows["actual_controller"]["next_action"]
    assert rows["actual_controller"]["field_contract"]["required_fields"] == [
        "person_name",
        "relation_type",
        "control_path",
        "confidence_basis",
    ]
    assert rows["bond_calendar"]["parity_priority"] == "p1_domain_depth"


def test_public_catalog_connectors_are_registered_but_not_overclaimed() -> None:
    registry = ConnectorRegistry()

    direct_public_apis = {
        "gleif_lei_public_api",
        "sec_edgar_public_api",
    }
    catalog_sources = {
        "opensanctions_public_dataset_catalog",
        "idb_sanctioned_firms_dataset_catalog",
        "official_china_registry_portal_catalog",
        "official_china_credit_portal_catalog",
        "official_china_court_enforcement_catalog",
    }
    production_default_off_sources = {
        "opensanctions_local_subject_index",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "idb_local_subject_index",
        "world_bank_debarred_firms_public_list",
        "wikidata_public_entity_graph",
    }

    for name in direct_public_apis:
        connector = registry.get(name)
        assert connector is not None
        assert connector.default_enabled is False
        assert connector.provenance_required is True
        assert connector.production_ready is True

    for name in catalog_sources:
        connector = registry.get(name)
        assert connector is not None
        assert connector.default_enabled is False
        assert connector.provenance_required is True
        assert connector.production_ready is False

    for name in production_default_off_sources:
        connector = registry.get(name)
        assert connector is not None
        assert connector.default_enabled is False
        assert connector.provenance_required is True
        assert connector.production_ready is True

    assert registry.get("gleif_lei_public_api").status is ConnectorStatus.ACTIVE
    assert registry.get("sec_edgar_public_api").status is ConnectorStatus.ACTIVE
    assert registry.get("opensanctions_local_subject_index").status is ConnectorStatus.CONDITIONALLY_ACTIVE
    assert registry.get("ofac_consolidated_sanctions_xml").status is ConnectorStatus.ACTIVE
    assert registry.get("un_sc_consolidated_sanctions_xml").status is ConnectorStatus.ACTIVE
    assert registry.get("idb_local_subject_index").status is ConnectorStatus.CONDITIONALLY_ACTIVE
    assert registry.get("world_bank_debarred_firms_public_list").status is ConnectorStatus.ACTIVE
    assert registry.get("wikidata_public_entity_graph").status is ConnectorStatus.ACTIVE
    assert registry.get("official_china_registry_portal_catalog").status is ConnectorStatus.NEEDS_REVIEW
    assert "live_health_pending" in registry.get("official_china_credit_portal_catalog").risk_flags
    assert "live_health_pending" in registry.get("official_china_court_enforcement_catalog").risk_flags
