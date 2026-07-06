# Wallstreet Tieling

> 华尔街驻铁岭办事处：把一个主体名称，变成一份可追溯、可交接、可复核的深度商业尽调包。

![Wallstreet Tieling brand card](docs/assets/brand-card.svg)

[![Release](https://img.shields.io/badge/release-0.5.0_alpha-0f766e)](#current-release)
[![Desktop Agents](https://img.shields.io/badge/desktop_agents-Codex%20%7C%20Claude%20Code%20%7C%20Hermes%20%7C%20OpenClaude-1f2937)](#desktop-agent-surfaces)
[![MCP](https://img.shields.io/badge/MCP-compatible-2563eb)](deploy/mcp-server.json)
[![License](https://img.shields.io/badge/license-MIT-111827)](LICENSE)

**中文** | [English](#english-overview)

Wallstreet Tieling is an evidence-first enterprise intelligence, due-diligence,
and risk-discovery toolkit for desktop agents, local operators, and
MCP-compatible workflows.

It turns a company name into a provenance-preserving investigation packet:
source routing, evidence ledger, relationship graph, capital-risk panel, report
exports, and a 13-role anthropomorphic expert-team handoff surface.

## 中文简介

Wallstreet Tieling / 华尔街驻铁岭办事处，是一个面向专业用户、桌面 Agent
和本地工作流的企业尽调与风险发现运行时。它不做“查一下公司简介”的轻量回答，
而是把一次调查拆成可执行、可复核、可交接的工作包：先找线索，再验来源，再建关系，
最后输出报告和下一步核验队列。

我们的产品气质不是“万能搜索框”，而是一个会干活的尽调班子。用户输入主体名称后，
系统会围绕公开来源、授权来源和本地验证数据，自动组织调查路径，并把结果整理成：

- 主体画像、证据台账、风险事件、关系图谱、资本风险和核验队列。
- Markdown、JSON、便携 HTML、DOCX 元数据、目录包和 `agent-handoff.json`。
- Codex、Claude Code、Hermes、OpenClaude、豆包办公任务模式、WorkBuddy 和通用 MCP/CLI/API 的交付面。
- 可被下一个 Agent 继续接力的结构化上下文，而不是一段看完就断的聊天记录。

品牌定位很简单：**铁岭的外壳，华尔街的尽调标准；东北式不装，证据链要硬。**

## 核心竞争力：拟人化专家团

拟人化不是皮肤，也不是几个角色名。它是 Wallstreet Tieling 的核心生产力设计。
系统内置 13 个专家角色，把复杂尽调拆成不同工种协同推进：有人盯来源，有人看资本，
有人拆关系，有人查异常，有人负责把证据讲清楚。它的目标不是“更会聊天”，而是让
Agent 像一个小型尽调团队一样分工、接力、复盘。

这套机制解决三个真实问题：

- **不丢上下文**：每个角色接手时都有结构化证据、待核验事项和下一步动作。
- **不混淆判断**：事实、线索、推断、风险提示分层展示，避免把“像是”写成“就是”。
- **不止会输出**：报告之外还保留关系图、来源健康度、验证配方和后续任务队列。

一句话：不是让 AI 装成人，而是让 AI 像专业团队一样工作。

## 网感版理解

传统工具像“截图发群里问一句有没有懂的”，Wallstreet Tieling 更像“把人拉进作战室，
白板、证据袋、关系网、会议纪要和下一步分工都摆好”。它保留了开源项目该有的严谨，
但不想长成一份冷冰冰的说明书。

如果说普通企业查询是“查个底”，Wallstreet Tieling 想做的是“把底稿铺开”：
来源从哪来、关系怎么连、风险为什么被标记、哪些结论还需要人复核，都要能看见。
我们要的是可打印、可交付、可被追问的调查成果，不是漂亮但空心的总结。

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
- **Personality without sloppiness**: 13 anthropomorphic expert roles route work
  like a due-diligence desk while preserving machine-readable fields.

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
- [Requirement intake](docs/REQUIREMENT_INTAKE.md)
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

Local hygiene audit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/local-hygiene-audit.ps1
```

## License

MIT License.

Built in Tieling, with Wall Street standards.
