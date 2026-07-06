---
name: wallstreet-tieling
description: "Use for the Wallstreet Tieling due-diligence project: company investigation, credit/risk research, financial analysis, broad OSINT-style retrieval planning, evidence graph construction, report generation, plugin-market readiness work, and ongoing development inside this repository."
---

# Wallstreet Tieling

Act as the continuing developer and operator for the `wallstreet-tieling` project.

## Operating Rules

- Interpret non-technical user requests as product goals, then convert them into concrete code, tests, and documentation.
- Prefer public, licensed, or user-authorized sources. Do not bypass access controls or invent private personal activity.
- Never fabricate facts. Every factual claim in an investigation output needs source, query/context, timestamp when available, and confidence.
- Treat social-web and associative clues as leads until corroborated by higher-authority evidence.
- Preserve unrelated local changes. Stage and commit only files intentionally touched for the current task.
- Do not store tokens, cookies, local message databases, browser profiles, or generated secret material in the plugin or repository.

## Project Map

- Core engine: `core/engine.py`, `api/orchestrator.py`, `core/session_bus.py`
- Broad investigative retrieval planner: `core/intelligence_retrieval.py`
- Evidence graph primitives: `core/deep_graph.py`
- Multi-source adapter: `adapters/multi_datasource/__init__.py`
- QYYJT adapter and public fallback queries: `adapters/qyyjt_adapter.py`
- Endpoint status registry: `config/api_endpoints.yaml`
- Role prompts and domain experts: `sub-skills/`
- Public release and runtime notes: `PROJECT_TASKBOARD.md`, `docs/RELEASE_PORTAL.md`, `docs/PROJECT_MAP.md`

## Default Workflow

1. Inspect the current task context, `git status --short`, and relevant tests before editing.
2. For desktop-agent host work, run `npx wallstreet-tieling --agent-tools` or call MCP `agent_tool_adapters` before making host-specific claims.
3. Use the canonical baseline tool sequence: `release_readiness`, `connector_catalog`, `development_requirements`, `agent_tool_adapters`, then `investigate_company`.
4. For Codex/MCP hosts, a single `investigate_company` call with `company_name` is sufficient for a due-diligence run; pass `export_dir` when the host needs DOCX, portable HTML, Markdown, JSON packet, `agent-handoff.json`, and `report-export-manifest.json` files written to disk.
5. Use MCP `retrieval_plan` only when the agent needs to inspect or explain the evidence plan before a full run; do not require users to wire it manually between prompt and investigation.
6. For company-name investigation requests, start with `InvestigativeRetrievalPlanner.build_company_plan(company)` and use its tasks as the retrieval checklist.
7. Execute available connectors in this order: official/public records, configured commercial APIs, multi-data-source adapters, web search, model reasoning only as a final synthesis layer.
8. Store results as evidence items before adding graph relations or conclusions.
9. Add or update focused tests for every behavior change.
10. Run focused tests first, then full `pytest -q` when the touched surface is shared.
11. Update the public taskboard or release docs when the implementation changes project readiness or known gaps.

## Validation Commands

Use the bundled Codex runtime Python when available:

```powershell
python -m pytest -q
```

Focused checks commonly used for retrieval and adapter work:

```powershell
python -m pytest tests\unit\test_intelligence_retrieval.py -q
python -m pytest tests\unit\test_multi_datasource.py adapters\multi_datasource\test_security.py -q
```

Agent host contract smoke:

```powershell
npx wallstreet-tieling --agent-tools
npm run agent:host-smoke
```

## Plugin-Market Readiness

Before claiming marketplace readiness:

- Validate `.codex-plugin/plugin.json` with the official plugin validator.
- Confirm `skills/wallstreet-tieling/SKILL.md` has concise trigger metadata and no TODO placeholders.
- Confirm `agent_tool_adapters` is exposed through MCP and `--agent-tools` is documented for desktop-agent hosts.
- Confirm tests pass and no secrets are tracked.
- Keep `PROJECT_TASKBOARD.md` and `docs/RELEASE_PORTAL.md` aligned with what is implemented, what is still planned, and what still requires user-provided credentials or browser authentication.
