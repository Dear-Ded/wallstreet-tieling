# Architecture Scorecard - 2026-06-17

## Current Level

Overall: **good prototype, partial production readiness**

This project is stronger than a normal prompt demo because it already has:

- role-based orchestration
- quality gates against fabrication
- structured session bus
- multi-source adapter boundaries
- targeted security tests
- a retrieval planner and evidence graph skeleton

It is still not fully production-grade because:

- the retrieval planner was not originally wired into the main engine
- evidence ingestion and conflict resolution are still lightweight
- many real data connectors remain partial or placeholder-driven
- plugin-market polish still needs assets, public policy pages, and deeper end-to-end execution

## What Is Working Well

1. Clear separation between orchestration, role logic, quality rules, and adapters.
2. The system is honest about missing data instead of pretending coverage.
3. The new investigative retrieval planner gives the project a real OSINT-style shape.
4. Security boundaries in the multi-data-source adapter are well-tested.
5. The codebase is already test-driven enough to support controlled iteration.

## Main Gaps

1. Retrieval planning was not originally part of the main execution loop.
2. Evidence graph population is still mostly a planning skeleton.
3. External source coverage is uneven.
4. Some repo text still contains legacy encoding damage.
5. Marketplace submission assets and policy pages are incomplete.

## Target Status

- Implemented: role orchestration, quality gates, adapter hardening, broad retrieval planning skeleton.
- Partially implemented: real source execution, evidence chaining, source conflict resolution, report synthesis from evidence graphs.
- Not yet implemented: full end-to-end company-to-controller-to-activity-to-social footprint pipeline with durable evidence store.
