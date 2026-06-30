# Datasource Admission and Zero-Config Search

wallstreet-tieling treats data access as a product capability, not a pile of
one-off scrapers. A source can enter production routing only when the system can
explain what it is, why it is legitimate for the deployment, how evidence is
standardized, and how users can audit the result later.

## Admission Tiers

| Tier | Typical source | Default | Production path |
| --- | --- | --- | --- |
| `official_public` | Government or official public APIs | Can be enabled when configured | Health check, provenance, standardized records |
| `public_web` | Public search and public webpages | Enabled for zero-config search | Provider health, URL provenance, record-quality audit |
| `licensed_commercial` | Licensed business-data services such as QYYJT | Public entry enabled when no credentials are needed | User authorization, terms review, live validation for credentialed/API depth |
| `user_authorized_service` | User-owned accounts or approved endpoints | Disabled by default | User authorization, audit trail, live validation |
| `community_delivery` | Telegram-style public-service delivery | Public entry enabled when no credentials are needed | Underlying source review, service metadata, transport validation for credentialed/private depth |
| `internal_private` | User-owned private internal systems | Disabled by default | Deployment-specific authorization and retention policy |

## Machine-Readable Decisions

The admission evaluator returns:

- `production_ready`: source can be routed in reviewed deployments.
- `conditional_production`: source is production-capable but requires user
  configuration or deployment review before use.
- `review_required`: source is not blocked, but lacks required evidence.
- `rejected`: source lacks public/user-authorized basis or minimum controls.

Every report includes `blockers`, `controls`, `next_actions`, score, tier, and
`production_route`. Product surfaces and CLI audits should use these fields
instead of hard-coded source lists.

## P0 Source Decisions

### QYYJT

QYYJT is classified as `licensed_commercial` and `conditionally_active`.
Its public-service entry is default-on when it can be used without user
credentials. Credentialed/API depth is production-capable only when the
deployment supplies authorization evidence, reviews the service scope,
preserves provenance, keeps audit logging enabled, and passes live validation.

The `QYYJTTool.authorization_report()` method now exposes cookie validity,
optional API smoke status, next action, and an admission report. With valid
authorization evidence, reviewed terms, and successful live validation, QYYJT
can promote from `conditional_production` to `production_ready`.

### Telegram Public Service

Telegram is treated as a delivery shape, not as a source of truth by itself.
Public Telegram services are default-on when they are publicly reachable
without credentials. Each configured service must declare bot/endpoint
metadata, authorization scope, and the underlying public or user-authorized
source description.

`TelegramPublicServiceTool.source_review_report()` returns one row per service
with missing metadata, review readiness, and admission status. Complete public
metadata allows `conditional_production`; terms review, authorization evidence,
and live validation promote credentialed or private service depth to
`production_ready`.

## Zero-Config Public Web Search

Public web search is enabled by default through `provider_type="auto"`.
The built-in DuckDuckGo Instant Answer provider is a starter provider for
installation smoke tests and first-run user experience. It is intentionally not
positioned as a deep search replacement.

Advanced deployments can replace the default with:

- an injected provider object or callable,
- a self-hosted SearXNG JSON endpoint,
- fixture results for deterministic offline tests.

All provider outputs are normalized into standardized records with URL
normalization, deduplication, provenance, and record-quality reporting before
they enter risk discovery.

## Deep Subject Profile

Risk discovery now builds a deep subject profile from the same evidence graph.
The profile is not a second unverified search report; it is a structured view
over retained public or user-authorized evidence.

The default profile dimensions are:

- identity and base attributes,
- controller, beneficial-owner, shareholder, and management leads,
- public contacts and network accounts,
- public location and activity leads,
- asset, collateral, and solvency leads,
- administrative, court, traffic, and behavioral-risk leads,
- public consumption or preference leads when business-relevant,
- relationship network and multi-hop associated subjects,
- public statements and account behavior,
- risk events produced by the monitoring pipeline.

High-sensitivity public leads are visible by default because users need to see
what the system found. They are labeled with sensitivity, source names,
evidence ids, confidence, verification status, and business relevance. Product
surfaces should distinguish a visible lead from a verified fact.

Recursive association expansion defaults to three hops and is capped by subject
and signal limits. Advanced deployments can tune the recursion policy, but the
framework should never expand without provenance, confidence, and auditability.
