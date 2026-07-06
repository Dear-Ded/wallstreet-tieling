# Release Asset Checklist

Status: operator-facing capture checklist for `wallstreet-tieling 0.5.0 Alpha`.

This document defines the minimum screenshot and submission asset set for the
desktop-agent-first public release. It is intentionally practical: what to
capture, where to capture it, how to name it, and what claims the images are
allowed to support.

## Current Scope

This checklist is for:

- GitHub public presentation refresh
- Codex/plugin marketplace pre-submission package
- Operator handoff packets for desktop-agent hosts

This checklist is not for:

- final hosted HTML launch assets
- mini-program/mobile/app-store assets
- sales/marketing claims beyond the current alpha scope

## Required Asset Set

Capture these assets after the latest acceptance pass and before any stronger
release claim:

| Asset ID | Required content | Recommended filename |
|---|---|---|
| `listing-overview` | public repo header or listing preview showing project name, short description, and alpha positioning | `listing-overview.png` |
| `codex-skill-entry` | Codex skill/plugin load surface | `codex-skill-entry.png` |
| `release-readiness` | `npx wallstreet-tieling --release` output | `release-readiness.png` |
| `connector-catalog` | `npx wallstreet-tieling --connectors` output | `connector-catalog.png` |
| `agent-tool-adapters` | `npx wallstreet-tieling --agent-tools` output | `agent-tool-adapters.png` |
| `retrieval-plan` | `python bin/retrieval_plan.py "<company>" --limit 5` or MCP retrieval-plan equivalent | `retrieval-plan.png` |
| `offline-fixture-report` | offline fixture investigation packet or exported report bundle summary | `offline-fixture-report.png` |
| `portable-html-report` | portable HTML report opened locally with visible evidence/report structure | `portable-html-report.png` |
| `docx-print-package` | Word-openable report view or generated DOCX file + metadata panel | `docx-print-package.png` |
| `mcp-smoke-pass` | `npm run codex:mcp-smoke` success output | `mcp-smoke-pass.png` |

## Optional But High-Value Assets

- `persona-surface.png`: 13-role anthropomorphic expert-team overview
- `report-bundle-files.png`: exported `agent-handoff.json`, manifest, Markdown,
  HTML, and JSON packet in one directory view
- `api-health-and-release.png`: `/api/health` and `/api/release` responses
- `host-smoke-pass.png`: `npm run agent:host-smoke` success output

## Capture Rules

1. Use real local product surfaces, not mocked slides.
2. Prefer crisp terminal or app captures at native scale.
3. Keep timestamps and filenames visible when that improves auditability.
4. Do not show secrets, cookies, browser profiles, local private notes, or
   user-specific local paths.
5. If a path is visible, prefer package-relative or neutral paths over
   user-home/private workspace paths.
6. Do not include internal collaboration panes, runtime state, or abandoned
   worktree directories in release captures.

## Capture Sequence

Run and capture in this order:

```powershell
npm run acceptance
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --agent-tools
python bin/retrieval_plan.py "Demo Technology Co., Ltd." --limit 5
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --export-dir output/release-asset-demo
npm run codex:mcp-smoke
```

Recommended follow-up:

```powershell
npm run agent:host-smoke
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-python.ps1 tools/api-smoke.py
```

## Storage Convention

Store human-captured release assets outside tracked source by default.

Recommended local layout:

```text
deliverables/release-assets/
  2026-07-06/
    listing-overview.png
    codex-skill-entry.png
    release-readiness.png
    connector-catalog.png
    agent-tool-adapters.png
    retrieval-plan.png
    offline-fixture-report.png
    portable-html-report.png
    docx-print-package.png
    mcp-smoke-pass.png
```

These files are review artifacts, not package contents.

## Allowed Claims

Assets may support these claims:

- desktop-agent alpha release candidate
- evidence-first due-diligence workflow
- public/licensed/user-authorized source model
- report bundle with Markdown, HTML, JSON, DOCX metadata, and agent handoff
- Codex/Claude/Hermes/Doubao/Open-agent/WorkBuddy host compatibility in alpha

Assets must not be used to support these claims:

- marketplace approval
- final polished product launch readiness
- guaranteed live coverage for every datasource
- unauthorized access or bypass capability
- complete replacement for human legal, credit, compliance, or investment review

## Sign-Off Gate

Do not mark screenshot/submission assets complete until:

- the required asset set is captured;
- filenames are normalized;
- no secrets or private paths are visible;
- the latest acceptance evidence still matches the release surfaces shown.
