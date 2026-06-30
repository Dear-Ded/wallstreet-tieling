# Codex Plugin Readiness - 2026-06-17

## Current Status

The repository now includes a Codex plugin scaffold:

- `.codex-plugin/plugin.json`
- `skills/wallstreet-tieling/SKILL.md`
- `skills/wallstreet-tieling/agents/openai.yaml`

This makes the project structurally adaptable as a Codex plugin while preserving the existing
`SKILL.md`, `sub-skills/`, Python package, adapters, and tests.

## Implemented Capabilities

- Due-diligence project operating workflow for Codex.
- Broad investigative retrieval planning through `core/intelligence_retrieval.py`.
- Evidence graph data structures for entities, evidence, and relations.
- Security-hardened multi-data-source adapter boundaries:
  - outbound URL validation
  - unsafe query-shape rejection
  - header injection rejection
  - response-size limit
  - JSON parse error wrapping
  - empty YAML rejection
- Tests covering the new retrieval planner and adapter security contracts.

## Verification

Commands run on 2026-06-17:

```powershell
python -m pytest tests\unit\test_intelligence_retrieval.py -q
```

Result: `4 passed`.

```powershell
python -m pytest -q
```

Result: `518 passed, 13 warnings`.

## Marketplace Gaps

The scaffold is plugin-shaped, but not yet final marketplace quality:

- Public privacy and terms URLs in `.codex-plugin/plugin.json` are placeholders on the project site path and need real published pages before submission.
- No plugin logo, composer icon, screenshots, or short demo recording are included yet.
- No MCP server is bundled; current functionality is skill-guided plus repository Python modules.
- QYYJT authenticated modules remain partial. `config/api_endpoints.yaml` correctly marks only `search` and `notices` as verified.
- Existing root `SKILL.md` and README contain mojibake in this checkout and should be UTF-8 repaired before public marketplace review.
- More end-to-end examples are needed for company-name to report workflows.

## Recommended Next Milestones

1. Add a small CLI script that runs `InvestigativeRetrievalPlanner` and emits JSON for a company seed.
2. Connect the planner to `Engine` or `api/orchestrator.py` so company investigation requests use the plan by default.
3. Add real connector execution adapters for public registry, court/enforcement, news, procurement, social-web, and capital-market sources.
4. Add evidence persistence and deduplication.
5. Add plugin assets and real policy pages.
6. Run official plugin validation before every marketplace submission candidate.
