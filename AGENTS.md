# Agent Operating Guide

This repository is `wallstreet-tieling` only. Do not mix it with sibling
projects or local automation workspaces.

Before taking implementation work, read:

- `README.md`
- `CLAUDE.md`
- `PROJECT_TASKBOARD.md`
- `docs/PROJECT_MANAGEMENT.md`
- `docs/REQUIREMENT_INTAKE.md`
- `docs/PROJECT_MAP.md`
- `docs/SEARCH_INTEGRATION_LEDGER.md`
- `docs/API_CONTRACTS.md`
- `release/variants.yaml`
- `core/development_requirements.py`

Core rules:

- Translate product-language requests into scoped engineering tasks and tests.
- The user may describe needs with abstract, non-technical language. Agents are
  responsible for product interpretation, planning, file selection, and
  verification strategy.
- Do not require the user to provide schemas, class names, endpoint names,
  branch names, or test commands.
- Substantial development should use a narrow branch/worktree lane unless the
  change is documentation-only or a small follow-up.
- Current release is desktop-agent first: Codex plugin/skill, Claude Code,
  Hermes-style desktop agents, Doubao Office Task Mode, OpenClaude-compatible
  agents, and WorkBuddy-style expert-team surfaces.
- Information retrieval depth, source admission, evidence provenance, entity
  resolution, graph explainability, and report usefulness are central product
  requirements.
- Query plans and weak clues are leads, not facts.
- Use public, licensed, or user-authorized evidence only.
- Keep default behavior safe. Advanced or credentialed sources must stay
  disabled until the user explicitly authorizes them.
- Never stage credentials, cookies, browser profiles, local databases, `.tmp/`,
  `outputs/`, `tmp-events.jsonl`, or local scratch reports.
- Do not stage the whole dirty tree. Review `git status --short` and stage only
  intentional files.

Definition of done:

- Runtime behavior is implemented, not only documented.
- Focused tests pass; full acceptance is required for release-significant
  changes.
- Relevant public docs and the executable requirements board are updated when
  priority, behavior, or release status changes.
- Public release checks confirm no secrets, private paths, private repository
  names, runtime artifacts, or internal handoff notes are tracked.
