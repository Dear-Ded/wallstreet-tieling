# Data Source Catalog

Wallstreet Tieling uses one connector contract for public, licensed, and
user-authorized sources. A source is only default-enabled when it can provide
public or configured data with provenance and a stable standard-record mapping.

## Default Enabled

| Source | Role | Status |
|---|---|---|
| `default_public_intel` | Product entrypoint that fans out to public web, configured public delivery services, and built-in fixture flows. | Production ready |
| `multi_datasource_rest_api` | Generic HTTP connector with endpoint configuration, health checks, auth handlers, retries, rate limits, and standard records. | Production ready |
| `public_web_search` | Zero-config starter web-search provider with optional advanced provider injection. | Production ready |
| `qyyjt_tool` | Public-service lead bridge for enterprise registry, ownership, court, administrative, opinion, and capital-market signals. | Conditional production |
| `telegram_bot_public_service` | Public delivery bridge that preserves bot/source metadata and standardizes returned public leads. | Conditional production |

## Built In But Default Off

These sources are present in `adapters/multi_datasource/datasources.yaml` and
`core/connector_registry.py`, but remain disabled by default so deployments can
choose jurisdiction, rate limits, and source policy deliberately.

| Source | Coverage | Implementation status |
|---|---|---|
| `gleif_lei_public_api` | Global LEI identity, registration authority, parent and relationship leads. | Basic company-name query and standardized records implemented |
| `sec_edgar_public_api` | US public issuer submissions, ticker/CIK lookup, ownership and capital-market disclosure leads. | CIK submissions lookup, ticker-catalog filtering, and standardized records implemented |
| `opensanctions_public_dataset_catalog` | Public dataset catalog for watchlist, sanctions, PEP, and related-entity coverage. | Catalog registered; license/indexing/entity-resolution review pending |
| `ofac_consolidated_sanctions_xml` | Official U.S. Treasury consolidated public list for watchlist screening. | XML download, subject matching, provenance, and standardized records implemented; default off because it is a heavy screening source |
| `un_sc_consolidated_sanctions_xml` | Official UN Security Council consolidated public list for watchlist screening. | XML download, alias-aware subject matching, provenance, and standardized records implemented; default off and included in official-public smoke |
| `world_bank_debarred_firms_public_list` | Official World Bank public debarred firms list for procurement and supplier exclusion screening. | HTML list parser and exact/strong subject matching implemented; default off pending latency/stability validation |
| `wikidata_public_entity_graph` | Public entity graph enrichment, aliases, websites, key people, and identifier corroboration. | EntitySearch and EntityData follow-up mapping implemented; related QIDs are label-enriched before profile/graph ingestion |
| `official_china_registry_portal_catalog` | Official registry identity, ownership, and controller leads. | Catalog registered; validated browser-handoff snapshot parser available; live health/capture workflow pending |
| `official_china_credit_portal_catalog` | Official credit-publicity and administrative-risk records. | Catalog registered; validated snapshot parser available for visible notice/penalty fields; live health/capture workflow pending |
| `official_china_court_enforcement_catalog` | Official court-enforcement and judicial-risk leads. | Catalog registered; validated browser-handoff snapshot parser available for visible enforcement fields; live health/capture workflow pending |

## Entity Resolution Gate

Every evidence item now carries an optional `entity_match` assessment when the
connector output names a candidate subject. The assessment is deliberately
explainable:

- `exact` / `strong`: normalized legal-name match, high similarity, or official
  identifiers such as LEI, CIK, ticker, or registry number are present.
- `review`: plausible name overlap that should be retained as a lead but checked
  before a material conclusion.
- `weak`: low-confidence co-occurrence or partial match; useful for discovery,
  not enough for final judgment.

The current implementation is a lightweight in-repo scorer inspired by the
entity-first practices used by OpenSanctions/FollowTheMoney and the transparent
record-linkage approach used by Splink, dedupe, and Python Record Linkage. The
upgrade path is to swap the scorer behind the same `entity_match` contract when
we introduce larger training data or probabilistic matching.

## Official Public Smoke

The normal template keeps official public APIs disabled until a deployment
chooses them. For connector verification, the CLIs support an explicit live
smoke mode:

```bash
python bin/investigate.py "Apple Inc." --official-public-smoke
python bin/risk_graph.py "Apple Inc." --official-public-smoke
python bin/risk_discovery.py "Apple Inc." --official-public-smoke
```

This creates a temporary datasource config that enables only:

- `gleif_lei_public_api`
- `sec_edgar_public_api`
- `opensanctions_public_dataset_catalog`
- `ofac_consolidated_sanctions_xml`
- `un_sc_consolidated_sanctions_xml`
- `world_bank_debarred_firms_public_list`
- `wikidata_public_entity_graph`

It does not enable licensed sources or user-authorized sources. Treat the
output as connector verification and public-source leads, not as complete due
diligence coverage.

## Authorized Or Licensed Enhancements

| Source family | Examples | Admission rule |
|---|---|---|
| Financial terminals | Wind, Bloomberg, Refinitiv, Choice, iFinD | User or institution supplies authorization and terms |
| Commercial registry APIs | Licensed KYB/KYC providers | Requires source admission, credential handling, provenance, and audit logging |
| Advanced web collection | User-authorized sessions, challenge-response providers, self-hosted search | Default off; deployment owner configures and accepts local compliance obligations |
| Local open-source tools | Sherlock, Maigret, theHarvester, SpiderFoot-style modules | Optional enhancement; outputs must map into standard records and confidence levels |

## Local Subject Index Contract

OpenSanctions-compatible and IDB-style local indexes are the bridge from
dataset coverage to subject-level evidence. They must remain local,
reviewed, and deployment-owned until the project ships a managed index.

Supported formats:

- JSON object with `records`, `data`, `items`, or `results`
- JSON array
- JSONL / NDJSON
- CSV with headers

Recommended fields:

- Matchable name: `name`, `entity`, `caption`, `legal_name`, `firm_name`,
  `subject`, or `title`
- Provenance: `url`, `source_url`, `reference_url`, or `dataset`
- Risk context: `category`, `schema`, `type`, `severity`, `summary`

Validate before enabling:

```bash
python bin/local_index_audit.py path/to/subjects.jsonl --fail-on-review
```

The audit returns record counts, matchable-name coverage, provenance coverage,
field coverage, category counts, severity counts, and warnings. A production
deployment should only enable an index after the audit returns `ok=true`.

## External Design References

The datasource roadmap follows proven OSINT patterns without copying their
unsafe edges into the default product path:

- SpiderFoot-style module fan-out: many connectors, one normalized evidence
  contract, and explicit module health.
- BBOT-style recursive discovery: bounded fan-out from entities, domains,
  people, and identifiers, with source-specific confidence.
- OpenSanctions / FollowTheMoney-style entity thinking: people, companies,
  addresses, identifiers, events, and relationships should become graph facts
  with provenance, not loose report text.
- Sherlock/Maigret-style account discovery remains an optional enhancement
  family, not a default enterprise-risk source, because business relevance and
  entity resolution need stricter gates.

## Connector Gate

Every production source should answer these questions:

- Is the source public, licensed, or user-authorized?
- Does the connector keep source URL, retrieval time, confidence, and raw evidence?
- Does it emit `standardized_records`?
- Does it have a health check or a clear manual-catalog status?
- Is it default-enabled only when the access model and mapper are stable?

Run:

```bash
python bin/connector_audit.py
python bin/terminology_guard.py --fail-on error
python -m pytest tests/unit/test_multi_datasource.py tests/unit/test_connector_registry.py -q
```
