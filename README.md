# 华尔街驻铁岭办事处 / Wallstreet Tieling

0.5.0 Alpha open-source enterprise cognition and risk discovery system with a 13-role anthropomorphic expert team, anthropomorphic shell, and broad evidence-first retrieval.
0.5.0 Alpha 开源、免费的企业认知与风险发现系统，带 13 角色拟人化专家团和广域证据检索。

[在线体验 / Online demo](https://dear-ded.github.io/wallstreet-tieling/) · [Codex plugin manifest](.codex-plugin/plugin.json) · [MCP config](deploy/mcp-server.json) · [Data protocol](references/data-protocol.md)
· [Project map](docs/PROJECT_MAP.md) · [Private dev handoff](docs/PRIVATE_DEV_HANDOFF.md)

---

## 一句话

用一句人话输入企业名，系统会把公开或授权的数据源、实控人线索、关系图谱、风险事件、证据台账和报告草稿串起来。

Give it a company name in plain language. It routes the request through a 13-role expert team, then builds a broad public-or-authorized evidence graph, controller leads, risk events, an evidence ledger, and a due-diligence draft.

```bash
npx wallstreet-tieling --investigate "Apple Inc." --report-only
```

0.5.0 Alpha 已经不是纯 Prompt 外壳。它包含可执行的 Python 风险发现流水线、REST API、MCP 入口、CLI 入口、证据图谱导出、风险事件账本和一句话调查包草稿。它不是最终事实裁判，所有结论都必须回到来源、置信度和人工核验。

It is not a final-verdict engine. Every useful output should preserve provenance, confidence, and human review boundaries.
The 13-role persona surface and its anthropomorphic shell are core product features. Current release scope focuses on broad evidence retrieval and single-shot investigation; monitoring baselines are reserved for later versions.

---

## 产品定位

它不是聊天机器人，也不只是搜索工具。

目标形态是 Enterprise Intelligence & Risk Discovery System:

- 识别企业是谁、谁控制它、和谁有关联。
- 聚合公开经营、司法、舆情、资产、项目、知识产权和公开账号线索。
- 建立企业、人员、地址、项目、案卷、账户、资产之间的证据图谱。
- 发现风险事件，而不只是生成更长的报告。
- 为后续版本保留监控基线和观察维度。

---

## 0.5.0 Alpha 已具备 / Available in 0.5.0 Alpha

- Plain-language investigation packet draft: `/api/investigate` and `bin/investigate.py`.
- Static web workbench: `index.html` can run a case, inspect quality/evidence/QYYJT status,
  and download Markdown, JSON, or portable HTML report exports.
- Risk graph export: nodes, edges, evidence, risk events, timeline, diagnostics.
- Subject profile: controller candidates, dimensions, evidence gaps, recursive policy.
- Runtime catalog APIs: `/api/connectors` exposes datasource readiness; `/api/release` exposes Universal/Codex/Claude Code/WorkBuddy release contracts; `/api/requirements` exposes executable P0/P1/P2/Future development priority, current completion, next focus, and scope boundaries.
- Development requirement board: `npx wallstreet-tieling --requirements` returns the same machine-readable P0/P1/P2/Future board used by API/MCP/WorkBuddy. QYYJT parity is current-version P0/P1 work; continuous monitoring is parked as Future scope for later versions.
- Enterprise Warning (QYYJT) benchmark: `/api/connectors` and `npx wallstreet-tieling --connectors` expose the 45-module parity matrix, currently split into 4 API/legacy modules, 41 query-plan modules, and 0 generic fallback modules. Each row now carries evidence role, report admissibility, admission gate, acceptance gate, parity priority, field contract, and an operator work item. The summary also exposes concrete module names, authorization/public-only split, and unsupported/unknown semantics so the catalog is honest instead of count-only. The P0 queue still has 16 items: 1 subject-resolution entrypoint plus 15 report-critical modules, each with required fields and report-admission gates.
- Datasource fixture pack: public registry, public web, Telegram-style public delivery, licensed API fixture.
- MCP tool: `investigate_company` executes the local investigation pipeline.
- CLI: `npx wallstreet-tieling --investigate "Company" --report-only`.
- Default one-click public path: zero-config public fan-out plus selected official/public sources including GLEIF LEI, SEC EDGAR, and Wikidata when reachable.
- Evidence/lead separation: verified-looking records stay in the evidence ledger; query-plan leads stay in the follow-up lead section.
- API auth boundary: localhost by default, Bearer token when exposed.
- Public release guardrails: no secrets, cookies, browser profiles, PATs, or local collaboration databases in the repo.

---

## 正在开发 / In Progress

- More live datasource providers and production readiness reports.
- Public web search zero-config experience.
- Hosted demo refresh and browser-smoke automation for the static workbench.
- Enterprise Warning (QYYJT) live/API field mapping backlog and contract maintenance.
- Marketplace submission hardening for Codex, Claude Code, and WorkBuddy expert-team variants.

---

## 公开边界 / Public Boundary

Public release policy:

- Use public, licensed, or user-authorized sources.
- Keep provenance for every claim.
- Treat weak social or web clues as leads, not verified facts.
- Do not present inferred relationships as confirmed facts.
- Do not store secrets, cookies, browser profiles, PATs, or local collaboration databases in the repo.

---

## 快速开始

```bash
npx wallstreet-tieling --help
npx wallstreet-tieling --connectors
npx wallstreet-tieling --release
npx wallstreet-tieling --requirements
npx wallstreet-tieling --investigate "Apple Inc." --report-only
npx wallstreet-tieling --investigate "Demo Technology Co., Ltd." --offline-fixture --report-only
```

```bash
python bin/investigate.py "Apple Inc." --report-only
python bin/risk_discovery.py "Apple Inc." --summary
python bin/investigate.py "Demo Technology Co., Ltd." --offline-fixture --report-only
```

---

## 架构

```text
Company name
  -> datasource routing / fixture pack / live providers
  -> standardized records
  -> evidence graph
  -> risk event detector
  -> subject profile builder
  -> investigation packet
  -> API / CLI / MCP / UI
```

主要模块：

- `core/intelligence_retrieval.py`
- `core/risk_discovery_pipeline.py`
- `core/risk_graph_export.py`
- `core/subject_profile.py`
- `core/investigation.py`
- `adapters/multi_datasource/`
- `lib/mcp-server.js`
- `api/server.py`

---

## 发布形态

All four distribution variants are alpha in 0.5.0 / 四种适配版在 0.5.0 均为 alpha：

- Universal alpha: CLI, REST API, Docker, Skill prompt.
- Codex alpha: plugin manifest and executable MCP tool.
- Claude Code alpha: repository handoff, Project knowledge pack, and MCP-friendly assets.
- WorkBuddy Expert Team alpha: 13-role expert-team workflow.

See [`release/variants.yaml`](release/variants.yaml).

---

## 开发与测试

For private-repo onboarding and the current development route, read
[`docs/PRIVATE_DEV_HANDOFF.md`](docs/PRIVATE_DEV_HANDOFF.md) first. It records
the project boundary, current goal, progress, technical route, task board,
validation commands, and development rules for handoff.

```bash
npm run acceptance
python -m pytest tests/unit -q
node --check lib/mcp-server.js
node --check bin/cli.js
python -m json.tool package.json
python -m json.tool .codex-plugin/plugin.json
```

Current focused local verification: default public path and acceptance checks pass locally, but host-level marketplace validation is still in progress.

---

## License

MIT License.
Built in Tieling, with Wall Street standards.
