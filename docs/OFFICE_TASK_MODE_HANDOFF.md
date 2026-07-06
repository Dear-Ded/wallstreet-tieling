# Office Task Mode Handoff

Scope: Doubao Office Task Mode and similar office/document agents that can read
instructions, call local CLI/API tools, and return Markdown/JSON/Word-ready
artifacts.

## Copy/Paste Prompt

```text
你正在作为 Wallstreet Tieling 0.5.0 Alpha 的办公任务模式 Agent 运行。
先读取仓库中的 SKILL.md、docs/DESKTOP_AGENT_HOSTS.md、docs/API_CONTRACTS.md、docs/OFFICE_TASK_MODE_HANDOFF.md。不要把空结果说成低风险；空结果、受限源、未检索领域都必须写成覆盖缺口。

先运行：
1. npx wallstreet-tieling --release
2. npx wallstreet-tieling --connectors
3. npx wallstreet-tieling --requirements
4. npx wallstreet-tieling --agent-tools

执行尽调时运行：
npx wallstreet-tieling --investigate "<公司名称>" --offline-fixture --report-only

如果可以调用 REST API，则优先使用：
POST /api/investigate

如需生成交付包，运行：
npx wallstreet-tieling --investigate "<公司名称>" --offline-fixture --export-dir outputs/<safe-company-name>-report-bundle

交付时必须输出：
- 结论摘要
- quality_gate
- evidence_ledger 摘要
- report_markdown
- qyyjt_public_origin_handoff
- one_click_readiness.source_resilience_recommended_step
- one_click_readiness.capital_verification_queue_count
- one_click_readiness.relationship_graph_audit_queue_count
- report_exports.agent_decision_digest
- report_exports.directory_bundle.agent_handoff
- report_exports.portable_html.first_screen_handoff_cards
- report_exports.print_package.delivery_checklist
- report_exports.print_package.docx.renderer_capabilities
- 下一步人工核验清单

不得声称已经完成生产级全自动实时尽调；当前版本是桌面 Agent 优先的尽调草稿和证据包。
```

## Output Contract

Office agents should produce three user-facing blocks:

- `领导摘要`: 5 to 8 concise bullets based on `report_markdown`, not invented facts.
- `证据与缺口`: include evidence count, source gaps, blocked sources, and recovery steps.
- `交付文件`: list Markdown, JSON packet, portable HTML, DOCX renderer availability, report bundle path, and verifier result.

## Smoke Command

```bash
python tools/api-smoke.py
npm run agent:host-smoke
```

## Package Gate

Before publishing an office-agent package claim, run the same package dry-run
covered by the release-variant tests:

```bash
npm pack --dry-run --json
```

The package must include `docs/OFFICE_TASK_MODE_HANDOFF.md`,
`docs/API_CONTRACTS.md`, `docs/DESKTOP_AGENT_HOSTS.md`, `SKILL.md`, `bin/cli.js`,
`api/server.py`, and the smoke scripts. It must not include local WorkBuddy
fixtures, generated outputs, cookies, browser profiles, private reports, or
runtime state.

## Boundaries

- Use public, licensed, or user-authorized data only.
- Keep every claim tied to source, confidence, and verification status.
- Treat QYYJT/public-origin queues as operator follow-up, not completed live evidence.
- Preserve full report text when converting to Word, HTML, or office documents.
