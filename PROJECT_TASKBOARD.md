# Wallstreet Tieling Project Taskboard

Scope: desktop-agent-first release roadmap for this repository.

## Operating Rules

- Ultimate goal: implement a public-or-authorized enterprise intelligence and
  risk discovery product with broad retrieval, evidence provenance, entity
  resolution, graph analysis, and printable/exportable reports.
- Current release target: ship the Agent-facing version first. The deliverable
  is a working desktop-agent package for Codex, Claude Code, Hermes-style
  desktop agents, Doubao Office Task Mode, OpenClaude-compatible agents,
  universal CLI/API/MCP hosts, and WorkBuddy-style expert-team workflows.
- Later release targets: polished standalone HTML site, mini-program, mobile
  app, and desktop app. Do not let those tracks displace Agent runtime delivery.
- Work from this board, close tasks one by one, and update status when a task
  starts, lands, or is re-scoped.
- Keep the public-data boundary intact: public, licensed, or user-authorized
  evidence only; preserve provenance, confidence, and human-review boundaries.
- Treat network failures as normal proxy volatility. Retry with backoff, use
  alternate official/public routes when available, and fall back to fixtures for
  local validation.
- Avoid destructive git actions. Preserve unrelated dirty worktree changes.
- A release step is not done until local acceptance passes and the public repo
  has no secrets, cookies, private databases, local paths, private repository
  names, internal handoff notes, or misleading claims.

## Current Status

Done:

- Public GitHub desktop-agent alpha snapshot published to `public/master` and
  `public/main` at `19470c3 chore: publish desktop agent alpha snapshot`.
- Main development branch `codex/security-ci-hardening` synchronized to
  `origin` at `056f15d docs: polish public project homepage`.
- Public homepage standardized with bilingual positioning, badges, quick start,
  capability matrix, verification gates, and project layout.
- One-click investigation packet: CLI/API/MCP path, evidence ledger, quality
  gate, and Markdown report.
- Public-data guardrails: evidence/lead separation, provenance fields, weak web
  clues treated as leads, and release hygiene checks.
- Subject profile: controller candidates, covered dimensions, evidence gaps,
  and bounded fanout controls.
- Official/public connectors in the current alpha path: GLEIF LEI, SEC EDGAR,
  Wikidata EntitySearch/EntityData, UN SC sanctions XML.
- Runtime connector catalog exposed through `/api/connectors`,
  `npx wallstreet-tieling --connectors`, and MCP connector catalog output.
- Runtime release contract exposed through `/api/release`,
  `npx wallstreet-tieling --release`, and MCP release output.
- Runtime requirements board exposed through `/api/requirements`,
  `npx wallstreet-tieling --requirements`, and MCP requirements output.
- Enterprise Warning/QYYJT benchmark coverage tracked behind authorization and
  source-admission gates.
- Query timeout propagation across CLI, API, MCP, Node CLI, and acceptance
  scripts.
- Investigation quality gate separates deliverable evidence from full coverage
  and report renders `Delivery Quality`.
- Minimum viable financial, industry, product, ownership, and risk cognition
  are wired into report generation.

In progress:

- Post-release local hygiene: remove clean stale worktrees, preserve dirty
  auxiliary worktrees for review, and keep runtime artifacts ignored. Current
  queue is tracked in `docs/WORKTREE_REVIEW_QUEUE.md`.
- Formal project management: use `docs/PROJECT_MANAGEMENT.md` as the operating
  cadence for work lanes, release gates, branch rules, and cleanup.
- Requirement intake: use `docs/REQUIREMENT_INTAKE.md` to translate abstract
  product requests into scoped plans, branches, files, and verification.
- Deep commercial due-diligence orchestration across money, goods, people,
  legal, sanctions, ownership, and public-record dimensions.
- Desktop-agent host parity: shared tool discovery, one-click investigation,
  export bundle delivery, agent-handoff routing, decision digest, and verifier
  behavior across CLI, API, MCP, Codex, Claude Code, Hermes, Doubao Office Task
  Mode, OpenClaude-compatible agents, and WorkBuddy.
- Source admission hardening for public, licensed, and user-authorized channels.
- Multi-level related-subject traversal with confidence and provenance.
- Portable report readiness summaries for desktop-agent hosts.
- Public-release hygiene hardening and packaging verification.

Next:

- Review dirty auxiliary worktrees and migrate any still-useful changes into
  narrow branches or archive them outside the active workspace.
- Prepare marketplace/operator screenshots and submission assets for the
  published desktop-agent alpha.
- Review the beautification isolation lane through
  `docs/BEAUTIFICATION_ISOLATION_REVIEW.md`; migrate only the premium HTML
  packet contract, verifier gates, acceptance checklist, and selected final
  screenshots into production work.
- Close Agent delivery gaps first: host-specific setup docs, runnable smoke
  tests, uniform packet/export fields, agent-handoff schemas, decision digest,
  delivery checklist, and report bundle verification.
- Strengthen report exports for Agent consumption: Word document, structured
  Markdown, JSON packet, portable HTML, manifest, agent-handoff, and verifier.
- Add richer charts, tables, image evidence handling, and printable public-style
  report formatting.
- Expand source adapters only through modular, auditable, default-off gates.
- Keep adding product-path tests that prove runtime behavior, not only helper
  functions.

## Definition Of Done

- A feature is not done until code, tests, evidence/provenance behavior,
  report/API/CLI surface, and acceptance impact are checked.
- A datasource is not production-admitted until health semantics, field
  contract, parser validation, timeout/retry behavior, provenance, and
  default-on/default-off status are explicit.
- A report feature is not done until JSON payload, Markdown report, export
  behavior, and quality-gate behavior agree.
- Public package readiness requires passing focused release hygiene tests and
  the relevant desktop-agent smoke tests.
