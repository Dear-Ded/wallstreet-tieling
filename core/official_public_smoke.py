#!/usr/bin/env python3
"""Temporary config builder for official-public datasource smoke runs."""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Iterable

import yaml

from .intelligence_retrieval import (
    ConnectorShape,
    EvidenceGraph,
    EvidenceType,
    EntityKind,
    InvestigativeRetrievalPlanner,
    InvestigationEntity,
    RetrievalDomain,
    RetrievalPlan,
    SearchTask,
    SourceAccess,
    SourceAuthority,
    SourceProfile,
)


DEFAULT_OFFICIAL_PUBLIC_SOURCES = (
    "gleif_lei_public_api",
    "sec_edgar_public_api",
    "opensanctions_public_dataset_catalog",
    "ofac_consolidated_sanctions_xml",
    "un_sc_consolidated_sanctions_xml",
    "world_bank_debarred_firms_public_list",
    "wikidata_public_entity_graph",
)


def build_official_public_smoke_config(
    *,
    template_path: str | Path | None = None,
    source_names: Iterable[str] = DEFAULT_OFFICIAL_PUBLIC_SOURCES,
) -> Path:
    """Create a temporary config that enables only selected official public sources.

    This keeps the product default-safe while still giving developers and
    advanced users a one-command way to verify live official public connectors.
    """
    root = Path(__file__).resolve().parent.parent
    template = Path(template_path) if template_path else root / "adapters" / "multi_datasource" / "datasources.yaml"
    payload = yaml.safe_load(template.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError(f"invalid datasource template: {template}")

    enabled = {str(item) for item in source_names}
    found: set[str] = set()
    for source in payload["sources"]:
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or "")
        if name in enabled:
            source["enabled"] = True
            source["ping"] = True
            found.add(name)
        else:
            source["enabled"] = False

    missing = sorted(enabled - found)
    if missing:
        raise ValueError("official public smoke source not found: " + ", ".join(missing))

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".official-public-smoke.yaml",
        prefix="wallstreet-tieling-",
        delete=False,
    )
    with handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    return Path(handle.name)


def build_official_public_smoke_plan(company: str) -> RetrievalPlan:
    """Build a minimal plan that queries only official public smoke sources."""
    seed = InvestigativeRetrievalPlanner._normalize_seed(company)
    seed_id = InvestigativeRetrievalPlanner._entity_id(EntityKind.COMPANY, seed)
    graph = EvidenceGraph()
    graph.add_entity(
        InvestigationEntity(
            id=seed_id,
            kind=EntityKind.COMPANY,
            name=seed,
            confidence=1.0,
            attributes={"seed": True},
        )
    )
    tasks = [
        SearchTask(
            domain=RetrievalDomain.CORPORATE_REGISTRY,
            query=seed,
            source_hint="gleif_lei_public_api",
            objective="Verify live GLEIF public LEI identity lookup.",
            priority=5,
            expected_evidence=(EvidenceType.REGISTRY_RECORD, EvidenceType.DATABASE_RESULT),
            fanout_entities=(EntityKind.COMPANY, EntityKind.ADDRESS),
            source_profile=SourceProfile(
                "gleif_lei_public_api",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Official public smoke query for GLEIF LEI records.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            query=seed,
            source_hint="sec_edgar_public_api",
            objective="Verify live SEC EDGAR public disclosure lookup.",
            priority=6,
            expected_evidence=(EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON),
            source_profile=SourceProfile(
                "sec_edgar_public_api",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Official public smoke query for SEC EDGAR records.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.ADMINISTRATIVE_RISK,
            query=seed,
            source_hint="opensanctions_public_dataset_catalog",
            objective="Verify live OpenSanctions public dataset catalog lookup.",
            priority=7,
            expected_evidence=(EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON),
            source_profile=SourceProfile(
                "opensanctions_public_dataset_catalog",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.PUBLIC_WEB,
                notes=("Official public smoke query for OpenSanctions dataset metadata.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.ADMINISTRATIVE_RISK,
            query=seed,
            source_hint="ofac_consolidated_sanctions_xml",
            objective="Verify live OFAC public consolidated-list lookup.",
            priority=8,
            expected_evidence=(EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON),
            source_profile=SourceProfile(
                "ofac_consolidated_sanctions_xml",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Official public smoke query for OFAC consolidated list records.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.ADMINISTRATIVE_RISK,
            query=seed,
            source_hint="un_sc_consolidated_sanctions_xml",
            objective="Verify live UN Security Council public consolidated-list lookup.",
            priority=9,
            expected_evidence=(EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON),
            source_profile=SourceProfile(
                "un_sc_consolidated_sanctions_xml",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Official public smoke query for UN Security Council consolidated list records.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.RELATED_ENTITIES,
            query=seed,
            source_hint="world_bank_debarred_firms_public_list",
            objective="Verify live World Bank public debarred-firms lookup.",
            priority=10,
            expected_evidence=(EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON),
            source_profile=SourceProfile(
                "world_bank_debarred_firms_public_list",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Official public smoke query for World Bank debarred-firms records.",),
            ),
        ),
        SearchTask(
            domain=RetrievalDomain.RELATED_ENTITIES,
            query=seed,
            source_hint="wikidata_public_entity_graph",
            objective="Verify live Wikidata public knowledge-graph lookup.",
            priority=11,
            expected_evidence=(EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
            fanout_entities=(EntityKind.COMPANY, EntityKind.PERSON, EntityKind.DOMAIN),
            source_profile=SourceProfile(
                "wikidata_public_entity_graph",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.PUBLIC_WEB,
                notes=("Official public smoke query for Wikidata entity graph records.",),
            ),
        ),
    ]
    return RetrievalPlan(
        seed_company=seed,
        tasks=tasks,
        graph=graph,
        compliance_notes=[
            "Official public smoke uses only selected public APIs.",
            "Output verifies connector behavior; it is not complete due diligence coverage.",
        ],
        coverage_domains={task.domain for task in tasks},
    )
