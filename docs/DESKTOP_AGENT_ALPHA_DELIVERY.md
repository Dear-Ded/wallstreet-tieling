# Desktop Agent Alpha Delivery Closure

Status: `0.5.0 Alpha` desktop-agent release candidate.

This page is the operator-facing closure checklist for the current release.
It separates what is ready for desktop-agent delivery from what remains later
product work.

## Current Release Target

Target: desktop-agent alpha for Codex, Claude Code, Hermes, Doubao Office Task
Mode, OpenClaude/open-source agents, WorkBuddy, CLI, REST API, and MCP.

Release decision source:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --delivery-closure
npx wallstreet-tieling --release-preflight
npx wallstreet-tieling --delivery-audit
npx wallstreet-tieling --objective-audit
```

The machine-readable field of record is:

```text
delivery_decision.status == desktop_agent_alpha_release_candidate
delivery_decision.full_product_status == not_final_release_ready
delivery_decision.remaining_variant_blocker_count == 0
delivery_closure.status == release_candidate
delivery_closure.required_verification_commands includes npm pack --dry-run --json
release_preflight.package_candidate_ready == true
release_preflight.final_submission_ready == false
delivery_audit.status == pass
delivery_audit.failed_checks == []
objective_audit.status == complete
objective_audit.failed_requirements == []
```

If a desktop-agent host blocks nested Node -> Python child processes, the Node
CLI may return `execution_mode == node_metadata_fallback` for `--release` or
`--delivery-closure` or `--release-preflight` or `--delivery-audit`. Treat that as valid release metadata only; full
investigation packets, DOCX export, and refreshed acceptance evidence still
require the Python runtime path.

## Ready In This Release

- `release_readiness` exposes runtime surfaces, latest acceptance evidence, and
  the desktop-agent alpha decision.
- `connector_catalog` exposes default public source metadata and QYYJT/public
  origin execution planning.
- `development_requirements` exposes executable P0/P1/P2/Future boundaries and
  the same desktop-agent delivery decision.
- `agent_tool_adapters` exposes host-specific sequences, fallback order,
  smoke commands, install/start handoff, required output fields, and required
  packet fields.
- `investigate_company` returns the investigation packet with evidence ledger,
  quality gate, report Markdown, portable HTML metadata, DOCX renderer
  metadata, QYYJT handoff, source resilience work, relationship graph work, and
  capital risk work.
- `aggregate_subject` gives desktop agents a bounded follow-up path for related
  companies, controllers, addresses, or other subjects.
- Directory exports include `agent-handoff.json`; hosts must preserve
  `report_exports.directory_bundle.agent_handoff.delivery_decision`,
  `report_exports.directory_bundle.agent_handoff.report_visibility`, and
  `report_exports.directory_bundle.agent_handoff.capital_risk_panel`, and
  `report_exports.directory_bundle.agent_handoff.source_strengthening`, plus
  `enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue`.

## Delivery Readiness Matrix

| Capability lane | Current alpha status | Proof source | Remaining boundary |
| --- | --- | --- | --- |
| Desktop-agent runtime entrypoints | Ready for local packaging | `release_preflight.package_candidate_ready == true`; `npm run agent:host-smoke`; `npm run codex:mcp-smoke`; `npm run api:smoke` | Marketplace/operator screenshots and clean release publication are still separate submission work |
| Codex primary adapter | Ready | `agent_tool_adapter_manifest.primary_host_id == codex`; packaged MCP smoke covers `release_readiness -> delivery_audit -> connector_catalog -> development_requirements -> agent_tool_adapters -> investigate_company` | Keep Codex as primary lane before WorkBuddy secondary changes |
| WorkBuddy expert-team branch | Ready as secondary adapter | `tests/unit/test_workbuddy.py`; WorkBuddy host smoke; `workbuddy_expert_team` delivery priority is secondary | Must not rewrite core runtime architecture or source admission policy |
| Information-source resilience | Ready as executable handoff | `source_resilience agent_autorun`; recovery execution queue; source-health digest | Live source availability is not guaranteed; blocked sources stay gap/next-action items |
| QYYJT/public-origin mapping | Ready as executable handoff | `qyyjt_public_origin_handoff.agent_autorun`; QYYJT section work orders; public-origin execution summary | Origin tracing is evidence work, not a claim that all portals are live |
| Relationship graph and capital risk | Ready as executable handoff | `capital_risk_agent_autorun`; `relationship_graph_audit_agent_autorun`; `relationship_resolution_agent_autorun` | Relationship and capital findings remain source-bound and confidence-tagged |
| Report visibility and artifacts | Ready for agent delivery | `report_artifact_agent_autorun`; `report_exports.premium_html`; `report_exports.portable_html.premium_profile`; DOCX renderer metadata | Fully polished public HTML workbench remains later-version product work |
| Release hygiene | Ready for local packaging | `npm run release:privacy-scan`; `npm pack --dry-run --json`; `npm run terminology:check` | Do not package runtime state, cookies, browser profiles, private reports, or local fixtures outside package allowlist |

## Required Verification

Run from the repository root before making a delivery claim:

```powershell
npm run acceptance
npm run codex:mcp-smoke
npm run agent:host-smoke
npm run api:smoke
npm run release:privacy-scan
npm run release:preflight
npm run delivery:audit
npm run objective:audit
npm pack --dry-run --json
```

Latest accepted evidence:

```text
npm run acceptance
799 passed, 9 skipped
2026-07-06 08:24 Asia/Shanghai
Plugin validation passed
API smoke passed
Apple Inc. default one-click acceptance passed
npm run terminology:check
0 findings
npm run agent:host-smoke
ok for universal, codex, claude_code, hermes, doubao_office_task_mode, open_claude_agents, workbuddy_expert_team
npm run codex:mcp-smoke
ok for connector_catalog, release_readiness, delivery_closure, release_preflight, delivery_audit, development_requirements, agent_tool_adapters, retrieval_plan, investigate_company
npm run release:preflight
ready_for_local_packaging; final_submission_ready=false until screenshots and clean release publication
npm run delivery:audit
pass; failed_checks=[]
npm run objective:audit
complete; runtime/source/QYYJT/relationship/capital/report/agent lanes and public release hygiene complete
npm run release:privacy-scan
ok; scanned npm package payload with 0 privacy findings
npm pack --dry-run --json
ok; package manifest includes desktop-agent delivery files
```

Post-acceptance focused source-strengthening completion regression:

```text
node tools/run-python.js -m pytest tests/unit/test_runtime_deep.py tests/unit/test_telegram_agg.py tests/unit/test_autonomous.py tests/unit/test_connector_registry.py tests/unit/test_release_variants.py tests/unit/test_api_server.py tests/unit/test_investigation.py tests/unit/test_workbuddy.py -q
223 passed, 2 skipped
2026-07-05 21:24 Asia/Shanghai
source_strengthening_queue empty completion state accepted by connector catalog, Codex/API smoke, investigation handoffs, bundle verifier, and WorkBuddy packet compatibility
```

## Host Operating Sequence

Every desktop-agent host should follow this baseline:

```text
release_readiness -> delivery_audit -> connector_catalog -> development_requirements -> agent_tool_adapters -> investigate_company
```

When the packet identifies a related subject worth expanding, run:

```text
aggregate_subject
```

Installation handoff is machine-readable in:

```text
agent_tool_adapter_manifest.installation_handoff
agent_tool_adapter_manifest.adapters[].install_handoff
agent_tool_adapter_manifest.adapter_lookup.<host_id>.install_command
```

Minimum local install smoke:

```bash
npm install -g wallstreet-tieling
npx wallstreet-tieling --release
npx wallstreet-tieling --agent-tools
npx wallstreet-tieling --investigate "Demo Install Smoke Co., Ltd." --offline-fixture
```

Hosts must preserve these machine-readable fields:

```text
delivery_decision
quality_gate
evidence_ledger
one_click_readiness
qyyjt_public_origin_handoff
enterprise_cognition.relationship_resolution_v1
enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue
report_exports.agent_decision_digest
report_exports.premium_html
report_exports.portable_html.premium_profile
report_exports.directory_bundle
report_exports.directory_bundle.agent_handoff
report_exports.directory_bundle.agent_handoff.report_visibility
report_exports.directory_bundle.agent_handoff.report_visibility.premium_html
report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun
report_exports.directory_bundle.agent_handoff.capital_risk_panel
report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun
report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun
report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun
report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun
report_exports.directory_bundle.agent_handoff.report_artifact_autorun
report_exports.directory_bundle.agent_handoff.source_strengthening
report_exports.directory_bundle.agent_handoff.delivery_decision
```

## Not Current Release

Do not claim these as delivered in `0.5.0 Alpha`:

- Final polished product launch readiness.
- Marketplace approval.
- Human-captured marketplace screenshots.
- Polished immersive HTML workbench as the primary product surface.
- Mini-program, mobile app, or standalone desktop app.
- Always-on continuous monitoring.
- Guaranteed live coverage for every advertised source.
- Legal, credit, investment, or compliance replacement.

## Final Submission Open Items

- Capture marketplace/operator screenshots after the final acceptance pass.
- Push or publish the reviewed package from a clean release branch.
- Keep local WorkBuddy fixtures, private collaboration files, generated
  reports, cookies, browser profiles, runtime state, and secrets out of the
  package.
