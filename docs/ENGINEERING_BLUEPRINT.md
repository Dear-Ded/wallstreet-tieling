# Wallstreet Tieling Engineering Blueprint

Scope: public engineering blueprint for `wallstreet-tieling`.

## 1. Product End State

Wallstreet Tieling is an enterprise intelligence and risk investigation system.
It is not a chatbot, a single search wrapper, or a decorative portal.

The user enters a company or organization name. The system should produce an
evidence-backed investigation packet that answers:

- Money: financing, debt, cash flow, solvency, asset pressure, pledges,
  freezes, auctions, and capital stress.
- Goods: products, suppliers, customers, channels, upstream/downstream links,
  market position, business model, concentration, and industry cycle.
- People: actual controller, UBO, legal representative, shareholders,
  directors, executives, related companies, shared addresses, shared projects,
  and relationship-risk transmission.

The expert-team shell is a product feature, not decoration. Persona labels are
useful only when they map to real modules, evidence, gaps, or next questions.

## 2. Current Release Boundary

Current release: `0.5.0 Alpha`.

This release is a single-shot investigation packet:

company input -> retrieval plan -> source routing -> standardized records ->
evidence graph -> subject profile -> enterprise cognition -> report -> quality
gate -> export/API/CLI/MCP/desktop-agent surfaces.

Continuous monitoring, alert push, always-on scheduling, and production ops are
future-version work unless the executable requirement board is explicitly
re-scoped.

## 3. Architecture Spine

- Retrieval planning: `core/intelligence_retrieval.py`
- Pipeline execution: `core/risk_discovery_pipeline.py`
- Public web leads: `adapters/public_web_search_tool.py`
- Multi-source connectors: `adapters/multi_datasource/__init__.py`
- QYYJT benchmark and admission: `adapters/qyyjt_tool.py` and
  `core/qyyjt_benchmark.py`
- Evidence graph and risk events: `core/risk_graph_export.py` and
  `core/risk_event_store.py`
- Subject profile: `core/subject_profile.py`
- Investigation packet: `core/investigation.py`
- Quality gate: `core/investigation_quality.py`
- Release surfaces: CLI, REST API, MCP, skill prompts, Codex plugin,
  Claude Code handoff, Hermes-style agents, Doubao Office Task Mode,
  OpenClaude-compatible agents, WorkBuddy-style expert-team workflows,
  release contract, connector catalog, and requirements board.

## 4. Evidence Rules

- Public, licensed, fixture-backed, or user-authorized evidence only.
- Weak public snippets, query plans, and review rows are leads, not facts.
- Exact, strong, or admitted records may create graph facts only through
  existing admission gates.
- Reports must preserve source, provenance, confidence, access level, match
  level, and verification status.
- Missing data should appear as evidence gaps, not fabricated conclusions.

## 5. Release Quality

A change is release-significant when it affects investigation output, source
admission, report exports, CLI/API/MCP behavior, plugin packaging, or public
claims.

Release-significant work should include:

- Product-path tests, not only helper tests.
- Positive and negative evidence-admission cases.
- Report/API/CLI surface checks when output changes.
- Public hygiene checks for secrets, private paths, internal handoff notes, and
  runtime artifacts.
- Focused tests during development and full acceptance before release tagging.
