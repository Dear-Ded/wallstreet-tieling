# Codex Marketplace Submission Notes

Status: ready for pre-submission review after the latest local acceptance pass.

Latest local evidence: `npm run acceptance` passed on 2026-07-06 08:24
Asia/Shanghai with `799 passed, 9 skipped`; `npm run terminology:check`
reported `0 findings`; `npm run codex:mcp-smoke`, `npm run agent:host-smoke`,
`npm run api:smoke`, `npm run release:privacy-scan`, `npm run release:preflight`, and
`npm pack --dry-run --json` passed.

## Reviewer Summary

Wallstreet Tieling `0.5.0 Alpha` is a desktop-agent first investigation
toolkit. The Codex package provides a plugin manifest, skill prompt, CLI, MCP
server, release-readiness metadata, connector catalog, retrieval-plan smoke, and
offline fixture investigation packet.

## Final Review Checklist

- `.codex-plugin/plugin.json` has name, version, author, repository, homepage,
  license, keywords, skill path, display copy, category, capabilities, and
  default prompts.
- `skills/wallstreet-tieling/SKILL.md` loads without requiring secrets.
- `npm run codex:mcp-smoke` passes and checks connector catalog,
  release-readiness, development requirements, retrieval plan, and investigation
  packet output.
- `npm run agent:host-smoke` passes for all seven alpha desktop-agent variants.
- `npm run api:smoke` passes through `tools/run-python.ps1`, so Windows hosts do
  not depend on `python` being present on PATH.
- `npm pack --dry-run --json` includes the agent delivery files and excludes
  local WorkBuddy fixtures, generated outputs, private reports, browser
  profiles, cookies, and runtime state.
- `npm run acceptance` passes before any release submission claim is made.
- `npm run terminology:check` reports `0 findings` before public copy is used.
- `tests/unit/test_release_hygiene.py` passes with no public secrets, local
  paths, private contacts, or stale version markers.

## Screenshot Capture List

Capture these manually in the target host or package review UI:

- Plugin manifest or marketplace listing preview.
- Skill prompt load screen.
- `npx wallstreet-tieling --release` output.
- `npx wallstreet-tieling --connectors` output.
- `npm run codex:mcp-smoke` success output.
- Offline fixture investigation packet showing `report_markdown`,
  `evidence_ledger`, `quality_gate`, `enterprise_cognition`, and
  `report_exports`.

## Copy Boundaries

Allowed:

- "Evidence-first enterprise risk discovery and due-diligence workflow."
- "Desktop-agent first alpha for Codex, Claude Code, Hermes, Doubao Office Task
  Mode, OpenClaude/open-source agents, WorkBuddy, CLI, API, and MCP."
- "Uses public, licensed, or user-authorized sources and preserves provenance."

Not allowed:

- "Approved by the marketplace."
- "Fully automated live investigation of all sources."
- "Guaranteed UBO/controller discovery."
- "Replaces human legal, credit, investment, or compliance review."
- "Current-release polished immersive HTML, app, mini-program, or always-on
  monitoring."
