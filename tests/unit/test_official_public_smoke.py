#!/usr/bin/env python3
"""Tests for explicit official-public datasource smoke configuration."""
from __future__ import annotations

import yaml

from core.official_public_smoke import (
    DEFAULT_OFFICIAL_PUBLIC_SOURCES,
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)


def test_official_public_smoke_config_enables_only_official_public_sources() -> None:
    path = build_official_public_smoke_config()

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = {
        str(source["name"]): bool(source.get("enabled"))
        for source in payload["sources"]
        if isinstance(source, dict) and source.get("name")
    }

    assert {name for name, enabled in sources.items() if enabled} == set(DEFAULT_OFFICIAL_PUBLIC_SOURCES)
    assert sources["gleif_lei_public_api"] is True
    assert sources["sec_edgar_public_api"] is True
    assert sources["opensanctions_public_dataset_catalog"] is True
    assert sources["ofac_consolidated_sanctions_xml"] is True
    assert sources["un_sc_consolidated_sanctions_xml"] is True
    assert sources["world_bank_debarred_firms_public_list"] is True
    assert sources["wikidata_public_entity_graph"] is True
    assert sources["github_public_api"] is False


def test_official_public_smoke_plan_limits_queries_to_official_public_sources() -> None:
    plan = build_official_public_smoke_plan("Apple Inc.")

    assert plan.seed_company == "Apple Inc."
    assert [task.source_hint for task in plan.tasks] == [
        "gleif_lei_public_api",
        "sec_edgar_public_api",
        "opensanctions_public_dataset_catalog",
        "ofac_consolidated_sanctions_xml",
        "un_sc_consolidated_sanctions_xml",
        "world_bank_debarred_firms_public_list",
        "wikidata_public_entity_graph",
    ]
    assert len(plan.tasks) == 7
    assert {task.query for task in plan.tasks} == {"Apple Inc."}
