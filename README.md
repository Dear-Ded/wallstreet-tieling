# Wallstreet Tieling

> 华尔街驻铁岭办事处：把一个主体名称，变成一份可追溯、可交接、可复核的深度商业尽调包。

[![Release](https://img.shields.io/badge/release-0.5.0_alpha-0f766e)](#current-release)
[![Desktop Agents](https://img.shields.io/badge/desktop_agents-Codex%20%7C%20Claude%20Code%20%7C%20Hermes%20%7C%20OpenClaude-1f2937)](#desktop-agent-surfaces)
[![MCP](https://img.shields.io/badge/MCP-compatible-2563eb)](deploy/mcp-server.json)
[![License](https://img.shields.io/badge/license-MIT-111827)](LICENSE)

Evidence-first enterprise intelligence, due-diligence, and risk-discovery
toolkit for desktop agents, local operators, and MCP-compatible workflows.

Wallstreet Tieling turns a company name into a provenance-preserving
investigation packet: source routing, evidence ledger, relationship graph,
capital-risk panel, report exports, and a 13-role anthropomorphic expert-team
handoff surface.

中文 | [English](#english-overview)

## 中文简介

Wallstreet Tieling / 华尔街驻铁岭办事处 是一个面向专业用户和桌面 Agent 的
企业尽调与风险发现工具。它不是“查一下公司简介”的轻量玩具，而是围绕证据、
来源、置信度、关系、资本风险、报告交付和 Agent 接力设计的调查工作台。

输入一个主体名称后，系统会生成结构化调查包：

- 公开、授权或许可来源的查询计划与证据链。
- 主体画像、风险事件、关系图谱、资本风险和后续核验队列。
- Markdown、JSON、便携 HTML、DOCX 元数据、目录包和 `agent-handoff.json`。
- Codex、Claude Code、Hermes、豆包办公任务模式、OpenClaude 类开源 Agent、
  WorkBuddy 分支和通用 MCP/CLI/API 的交付面。

品牌定位很简单：**铁岭的外壳，华尔街的尽调标准；东北式不装，证据链要硬。**

## English Overview

Wallstreet Tieling is an open-source due-diligence runtime for agentic
workflows. It helps desktop agents and local operators collect public or
user-authorized signals, separate facts from leads, preserve evidence, and
deliver machine-readable investigation artifacts instead of prose-only answers.

It is designed for professional workflows where the output must be inspectable,
repeatable, and handoff-ready.

## Why It Exists

Most investigation tools stop at a readable summary. Wallstreet Tieling focuses
on the harder operational layer:

- **Evidence over vibes**: claims are tied to source, confidence, and follow-up
  status.
- **Agent-native delivery**: CLI, REST, MCP, Codex plugin, skill prompt, and
  host adapters expose the same runtime contract.
- **Deep handoff, not chat collapse**: report exports preserve graphs,
  verifier recipes, source-health state, and agent-autorun fields.
- **Professional defaults**: safe public-mode behavior first; advanced or
  credentialed sources stay explicit and auditable.
- **Personality without sloppiness**: 13 anthropomorphic expert roles can help
  route work while preserving machine-readable fields.

## Current Release

Status: `0.5.0 Alpha` desktop-agent release candidate.

This release is ready for local desktop-agent packaging and public GitHub
review. It is not a claim of marketplace approval, hosted SaaS readiness,
mini-program/app delivery, or guaranteed live access to every advertised source.

Latest local evidence:

- `npm run acceptance`: `799 passed, 9 skipped` on `2026-07-06 08:24 Asia/Shanghai`
- `npm run api:smoke`: passed
- `npm run codex:mcp-smoke`: passed
- `npm run agent:host-smoke`: passed for all seven alpha desktop-agent variants
- `npm run release:preflight`: `ready_for_local_packaging`
- `npm run delivery:audit`: `pass`
- `npm run objective:audit`: `complete`
- `npm run release:privacy-scan`: `issue_count=0`
- `npm pack --dry-run --json`: passed

## Quick Start

```bash
npx wallstreet-tieling --help
npx wallstreet-tieling --release
npx wallstreet-tieling --connectors
npx wallstreet-tieling --agent-tools
npx wallstreet-tieling --investigate "Apple Inc." --report-only
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
```

Python entrypoints are also available:

```bash
python bin/investigate.py "Apple Inc." --report-only
python bin/risk_discovery.py "Apple Inc." --summary
python bin/investigate.py "Demo Technology Co., Ltd." --offline-fixture --report-only
```

Run the local API:

```bash
npm run api
```

Useful endpoints:

- `GET /api/health`
- `GET /api/release`
- `GET /api/release-preflight`
- `GET /api/delivery-audit`
- `GET /api/objective-audit`
- `GET /api/connectors`
- `GET /api/agent-tools`
- `POST /api/investigate`

## Desktop-Agent Surfaces

The alpha contract covers seven host variants:

- Universal CLI/API/MCP host
- Codex plugin and MCP host
- Claude Code repository workflow
- Hermes-style local agent workflow
- Doubao Office Task Mode
- OpenClaude / open-source agent hosts
- WorkBuddy expert-team branch

Machine-readable adapter metadata:

```bash
npx wallstreet-tieling --agent-tools
npx wallstreet-tieling --delivery-audit
npx wallstreet-tieling --objective-audit
```

Baseline host sequence:

```text
release_readiness -> delivery_audit -> connector_catalog -> development_requirements -> agent_tool_adapters -> investigate_company
```

## Capability Matrix

| Area | What is included | Runtime evidence |
| --- | --- | --- |
| Investigation packet | Evidence ledger, quality gate, report Markdown, JSON, portable HTML, bundle metadata | `core/investigation.py` |
| Source resilience | Source-health digest, recovery queue, autorun handoff fields | `core/connector_registry.py` |
| Public-origin mapping | QYYJT/commercial concepts mapped to public-origin work orders | `docs/SEARCH_INTEGRATION_LEDGER.md` |
| Relationship graph | Auditable nodes, edges, verification queues, relationship resolution | `core/relationship_resolution.py` |
| Capital risk | Capital exposure and verification queues preserved in reports | `core/risk_graph_export.py` |
| Agent delivery | CLI, REST, MCP, Codex, Claude Code, Hermes, OpenClaude, WorkBuddy | `core/agent_tool_adapters.py` |
| Release gates | Preflight, delivery audit, objective audit, privacy scan, package dry-run | `core/release_contract.py` |

## Public Boundaries

Allowed source categories:

- Public sources
- Licensed sources
- User-authorized sources
- Offline fixtures for local validation

Not allowed in this repository:

- API keys, cookies, browser profiles, tokens, private reports, local databases,
  runtime state, or generated investigation outputs.
- Claims that the tool bypasses account authorization, CAPTCHA, payment,
  platform permissions, or source terms.
- Claims that every live source is always reachable or that inferred
  relationships are confirmed facts.

## Verification

Run these before making a release or delivery claim:

```bash
npm run acceptance
npm run api:smoke
npm run codex:mcp-smoke
npm run agent:host-smoke
npm run release:preflight
npm run delivery:audit
npm run objective:audit
npm run release:privacy-scan
npm pack --dry-run --json
```

Useful focused checks:

```bash
npm run test:focused
node --check bin/cli.js
node --check lib/mcp-server.js
python -m json.tool package.json
python -m json.tool .codex-plugin/plugin.json
```

## Documentation

- [Project map](docs/PROJECT_MAP.md)
- [Project management system](docs/PROJECT_MANAGEMENT.md)
- [Release portal](docs/RELEASE_PORTAL.md)
- [API contracts](docs/API_CONTRACTS.md)
- [Desktop Agent Alpha delivery](docs/DESKTOP_AGENT_ALPHA_DELIVERY.md)
- [Agent host smoke checklist](docs/AGENT_HOST_SMOKE_CHECKLIST.md)
- [Codex marketplace notes](docs/CODEX_MARKETPLACE_SUBMISSION_NOTES.md)
- [MCP config](deploy/mcp-server.json)
- [Codex plugin manifest](.codex-plugin/plugin.json)

## Repository Layout

```text
adapters/     Source adapters and public/authorized lookup modules
api/          Local REST API
bin/          CLI entrypoints and report verifier
core/         Investigation runtime, release contract, graph and report logic
deploy/       MCP and deployment manifests
docs/         Public operator documentation
release/      Desktop-agent release variant contract
skills/       Agent skill package
sub-skills/   Anthropomorphic expert role prompts
tools/        Smoke tests, acceptance runner, package privacy scanner
```

## License

MIT License.

Built in Tieling, with Wall Street standards.
