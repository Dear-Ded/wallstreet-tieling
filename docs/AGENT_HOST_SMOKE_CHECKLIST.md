# Agent Host Smoke Checklist

Scope: release-facing smoke checklist for desktop-agent hosts in `0.5.0 Alpha`.
The current release is agent-first and must not depend on the polished HTML
workbench, mini-program, mobile app, or standalone desktop app.

## Shared Baseline

Run these checks before host-specific packaging claims are upgraded:

```bash
npm run agent:host-smoke
npm run api:smoke
node tools/codex-mcp-smoke.js
```

The shared smoke must confirm:

- `release_readiness` returns all seven alpha variants.
- `connector_catalog` exposes default-safe public connectors, QYYJT source
  metadata, `groups.explicit_only`, `connectors[].data_effectiveness`,
  `summary.source_strengthening`, and either
  `source_strengthening_queue[].implementation_pack` for pending source
  hardening follow-up or an empty queue completion state when all source
  contracts are strengthened.
- `development_requirements` returns the executable priority board.
- `delivery_closure` returns the desktop-agent alpha release-closure contract,
  required verification commands, preserved packet fields, and open submission
  items.
- `release_preflight` returns the desktop-agent alpha package go/no-go status,
  final submission blockers, privacy/package review checklist, and safe release
  claim.
- `delivery_audit` returns the single desktop-agent alpha go/no-go audit with
  `status=pass`, empty `failed_checks`, coverage flags, verification evidence,
  and the safe release claim.
- `objective_audit` returns the active objective completion audit; hosts must
  treat non-empty `failed_requirements` as remaining work and must not mark the
  NightPilot/thread goal complete.
- `release_readiness` and `delivery_closure` may return
  `execution_mode=node_metadata_fallback` when the host blocks nested Python
  child processes; this is acceptable for release metadata, but not for full
  investigation packets, DOCX output, or refreshed acceptance evidence.
- `agent_tool_adapters` returns all seven host adapters with the canonical
  `release_readiness -> delivery_audit -> connector_catalog -> development_requirements ->
  agent_tool_adapters -> investigate_company` sequence, fallback order, smoke
  command, and packet preservation fields.
- `agent_tool_adapters.first_run_recipe.preserve_before_summarizing` includes
  `connector_catalog.groups.explicit_only` and
  `connector_catalog.connectors[].data_effectiveness` so advanced authorized
  sources such as China tax-credit, judicial-asset, MOFCOM overseas-investment,
  Aiqicha, and Shuidi connectors remain visible without becoming default-on.
- `agent_tool_adapters.first_run_recipe.preserve_before_summarizing` includes
  `connector_catalog.source_strengthening_queue` so host summaries do not drop
  source-hardening work orders before they can be assigned; if the queue is
  empty, hosts must preserve the completion summary rather than inventing work.
- `agent_tool_adapters.first_run_recipe.preserve_before_summarizing` also
  includes `report_exports.premium_html`,
  `report_exports.portable_html.premium_profile`, and
  `report_exports.directory_bundle.agent_handoff.report_visibility.premium_html`
  so host summaries keep the premium report visibility contract instead of
  reducing the report package to prose or plain portable HTML.
- `agent_tool_adapters.adapters[].required_packet_fields` includes
  `qyyjt_public_origin_handoff.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun`,
  and `report_exports.directory_bundle.agent_handoff.report_artifact_autorun`
  so hosts can continue deep lanes without manual intermediate steps.
- `agent_tool_adapters.installation_handoff` returns the package install
  command, MCP start command, local runtime environment hints, verification
  commands, and one install row per current desktop-agent host.
- Each `adapters[].install_handoff` returns a host-specific install command,
  config file list, start command, smoke command, and done condition.
- `aggregate_subject` is available as a follow-up tool through MCP, REST
  `/api/aggregate`, and CLI `--aggregate-subject` after an investigation packet
  identifies a related company, controller, or other subject worth expanding.
- `investigate_company` returns a `0.5.0` `investigation_packet`.
- The packet includes `report_markdown`, `quality_gate`, `evidence_ledger`,
  `enterprise_cognition`, `one_click_readiness`, `qyyjt_public_origin_handoff`,
  `report_exports`, `report_exports.premium_html`,
  `report_exports.portable_html.premium_profile`,
  `report_exports.directory_bundle.agent_handoff`,
  `report_exports.directory_bundle.agent_handoff.report_visibility`,
  `report_exports.directory_bundle.agent_handoff.report_visibility.premium_html`, and
  `report_exports.directory_bundle.agent_handoff.capital_risk_panel`,
  `report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun`,
  `report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun`, and
  `report_exports.directory_bundle.agent_handoff.report_artifact_autorun`, and
  `report_exports.directory_bundle.agent_handoff.relationship_resolution`, and
  `report_exports.directory_bundle.agent_handoff.source_strengthening`, and
  `report_exports.directory_bundle.agent_handoff.delivery_decision`.
- Current-release monitoring remains disabled; continuous monitoring is a later
  version target.

## Claude Code

Entrypoints:

- `CLAUDE.md`
- `SKILL.md`
- `docs/CLAUDE_CODE_ADAPTER.md`
- `docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md`
- `deploy/mcp-server.json`

Smoke sequence:

1. Load the repo instructions and project knowledge pack.
2. Call MCP `release_readiness`.
3. Call MCP `delivery_audit`.
4. Call MCP `connector_catalog`.
5. Call MCP `delivery_closure`.
6. Call MCP `release_preflight`.
7. Run one offline-fixture `investigate_company` smoke.
8. Confirm the answer preserves runtime handoff fields instead of replacing the
   packet, `delivery_decision`, or `agent_handoff` with a prose-only summary.

Expected command fallback:

```bash
npx wallstreet-tieling --release
npx wallstreet-tieling --delivery-closure
npx wallstreet-tieling --release-preflight
npx wallstreet-tieling --delivery-audit
npx wallstreet-tieling --connectors
npx wallstreet-tieling --agent-tools
npx wallstreet-tieling --investigate "Demo Claude Code Smoke Co., Ltd." --offline-fixture
npx wallstreet-tieling --aggregate-subject "company:demo-claude-related" --subject-name "Demo Claude Related Co." --max-depth 1
```

## Hermes

Entrypoints:

- `SKILL.md`
- `bin/cli.js`
- `deploy/mcp-server.json`
- `docs/API_CONTRACTS.md`
- `docs/HERMES_AGENT_SETUP.md`

Smoke sequence:

1. Load `SKILL.md` as the host instruction prompt.
2. Use `docs/HERMES_AGENT_SETUP.md` for timeout and local runtime defaults.
3. Call `release_readiness`, `delivery_audit`, `connector_catalog`, `delivery_closure`, and
   `investigate_company`.
4. Confirm `WST_MCP_TIMEOUT_MS`, `WST_QUERY_TIMEOUT_SECONDS`, and
   `WST_ACCEPTANCE_STATE_DIR` are documented as environment-controlled values.

Expected command fallback:

```bash
WST_MCP_TIMEOUT_MS=120000 npx wallstreet-tieling --mcp
npx wallstreet-tieling --requirements
npx wallstreet-tieling --delivery-closure
npx wallstreet-tieling --delivery-audit
```

## Doubao Office Task Mode

Entrypoints:

- `SKILL.md`
- `bin/cli.js`
- `api/server.py`
- `docs/OFFICE_TASK_MODE_HANDOFF.md`

Smoke sequence:

1. Use the Chinese one-line operator handoff.
2. Run default public investigation output through CLI or REST API.
3. Confirm office-readable Markdown is returned without dropping
   `evidence_ledger`, `quality_gate`, `delivery_closure`, `report_exports`, or
   `report_exports.directory_bundle.agent_handoff.delivery_decision` and
   `report_exports.directory_bundle.agent_handoff.report_visibility` and
   `report_exports.directory_bundle.agent_handoff.capital_risk_panel` and
   `report_exports.directory_bundle.agent_handoff.relationship_resolution` and
   `report_exports.directory_bundle.agent_handoff.source_strengthening`.
4. Confirm the handoff exposes `one_click_readiness.source_resilience_recommended_step`
   and `report_exports.print_package.docx.renderer_capabilities`.

Expected command fallback:

```bash
npx wallstreet-tieling --investigate "Demo Office Task Smoke Co., Ltd." --offline-fixture
npx wallstreet-tieling --delivery-closure
python api/server.py
```

## OpenClaude And Open-Source Agents

Entrypoints:

- `CLAUDE.md`
- `SKILL.md`
- `docs/API_CONTRACTS.md`
- `docs/OPEN_AGENT_COMPATIBILITY.md`
- `deploy/mcp-server.json`

Smoke sequence:

1. Follow the fallback order in `docs/OPEN_AGENT_COMPATIBILITY.md`.
2. Prefer MCP with `npx wallstreet-tieling --mcp`.
3. Fall back to CLI, then REST API, then prompt-only mode.
4. Preserve the full JSON investigation packet when converting to local
   Markdown, HTML, or office artifacts.
5. Preserve `delivery_closure` as the release decision source instead of
   inferring readiness from prose documentation.

Expected command fallback:

```bash
npx wallstreet-tieling --mcp
npx wallstreet-tieling --delivery-closure
npx wallstreet-tieling --investigate "Demo Open Agent Smoke Co., Ltd." --offline-fixture
npm run api:smoke
```

## WorkBuddy Expert Team

Entrypoints:

- `adapters/workbuddy.py`
- `SKILL.md`
- `sub-skills/`

Smoke sequence:

1. Call WorkBuddy tool routing for `connector_catalog`.
2. Call WorkBuddy tool routing for `release_readiness`.
3. Call WorkBuddy tool routing for `development_requirements`.
4. Call WorkBuddy tool routing for `agent_tool_adapters`.
5. Call WorkBuddy tool routing for `delivery_closure`.
6. Call WorkBuddy tool routing for `investigate_company` with
   `offline_fixture=True` and confirm it returns an `investigation_packet`.
7. Confirm the packet preserves `quality_gate`, `evidence_ledger`,
   `qyyjt_public_origin_handoff`, `report_exports.agent_decision_digest`, and
   `report_exports.directory_bundle.agent_handoff.delivery_decision` and
   `report_exports.directory_bundle.agent_handoff.report_visibility` and
   `report_exports.directory_bundle.agent_handoff.capital_risk_panel` and
   `qyyjt_public_origin_handoff.agent_autorun` and
   `report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun` and
   `report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun` and
   `report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun` and
   `report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun` and
   `report_exports.directory_bundle.agent_handoff.report_artifact_autorun` and
   `report_exports.directory_bundle.agent_handoff.relationship_resolution` and
   `report_exports.directory_bundle.agent_handoff.source_strengthening`.
8. Confirm expert-team output remains a host adapter surface and does not
   rewrite backend architecture.

Expected focused test:

```bash
python -m pytest tests/unit/test_workbuddy.py -q
```

## Pass Criteria

- Host claims remain alpha unless the host-specific smoke and shared baseline
  are both green.
- The smoke output is machine-readable enough for CI or a desktop agent to
  decide pass/fail without manual interpretation.
- Installation handoff is machine-readable enough for a host to install, start,
  smoke, and route common runtime failures without reading prose docs first.
- Missing public evidence is reported as a gap or next action, never fabricated.
- `delivery_decision`, `agent_handoff`, `report_visibility`, and
  `capital_risk_panel` survive every host formatting path.
- `delivery_closure` survives every release-facing handoff path.
- Unauthorized cookies, private browser profiles, API keys, and local secrets
  are not required for current-release smoke.
