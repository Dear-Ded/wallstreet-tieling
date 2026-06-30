#!/usr/bin/env node
/**
 * Host-neutral desktop-agent smoke for release-facing runtime tools.
 *
 * This is intentionally not a full MCP client handshake. It verifies the local
 * CLI/API-backed contract that desktop agents consume through MCP, shell tools,
 * skill prompts, or copy/paste task-mode workflows.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NODE = process.execPath;
const PYTHON = process.env.WST_PYTHON || process.env.PYTHON || '';
const SMOKE_DIR = path.join(os.tmpdir(), 'wallstreet-tieling-agent-host-smoke');
fs.mkdirSync(SMOKE_DIR, { recursive: true });
const SMOKE_STORE = path.join(SMOKE_DIR, `risk-events-${process.pid}.jsonl`);
const CLI_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;

const REQUIRED_VARIANTS = [
  'universal',
  'codex',
  'claude_code',
  'hermes',
  'doubao_office_task_mode',
  'open_claude_agents',
  'workbuddy_expert_team'
];

function run(args, label) {
  const env = {
    ...process.env,
    PYTHONUTF8: '1'
  };
  if (PYTHON) {
    env.WST_PYTHON = PYTHON;
  }
  const result = spawnSync(NODE, [path.join(ROOT, 'bin', 'cli.js'), ...args], {
    cwd: ROOT,
    env,
    encoding: 'utf-8',
    maxBuffer: CLI_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (result.status !== 0) {
    throw new Error(`${label} failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function parseJson(raw, label) {
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`${label} did not return JSON: ${error.message}`);
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const release = parseJson(run(['--release'], 'release_readiness'), 'release_readiness');
assert(release.type === 'release_readiness_brief', 'release_readiness type mismatch');
assert(release.contract.summary.variant_count === REQUIRED_VARIANTS.length, 'variant count mismatch');
for (const variant of REQUIRED_VARIANTS) {
  assert(release.contract.variants[variant], `release variant missing: ${variant}`);
  assert(release.contract.variants[variant].readiness === 'alpha', `variant is not alpha: ${variant}`);
  assert(release.contract.variants[variant].entrypoints.length > 0, `variant entrypoints missing: ${variant}`);
}
assert(
  release.contract.product.shared_core.includes('core.enterprise_cognition.EnterpriseCognitionEngine'),
  'enterprise cognition shared core missing'
);
assert(
  release.contract.product.shared_core.includes('core.intelligence_retrieval.InvestigativeRetrievalPlanner'),
  'retrieval planner shared core missing'
);

const connectors = parseJson(run(['--connectors'], 'connector_catalog'), 'connector_catalog');
assert(connectors.type === 'connector_catalog', 'connector_catalog type mismatch');
assert(connectors.summary.zero_config_ready.includes('default_public_intel'), 'default_public_intel missing');
assert(connectors.summary.data_effectiveness.fact_capable_sources >= 4, 'fact-capable source coverage missing');
assert(connectors.qyyjt_benchmark.summary.p0_queue_count >= 1, 'QYYJT P0 queue missing');

const requirements = parseJson(run(['--requirements'], 'development_requirements'), 'development_requirements');
assert(requirements.type === 'development_requirements_board', 'development_requirements type mismatch');
assert(requirements.completion_percent >= 80, 'development completion unexpectedly low');
assert(
  requirements.scope_rules.continuous_monitoring === 'future_version_not_current_release',
  'continuous monitoring scope boundary missing'
);

const investigation = parseJson(
  run(
    [
      '--investigate',
      'Demo Desktop Agent Smoke Co., Ltd.',
      '--offline-fixture',
      '--store',
      SMOKE_STORE
    ],
    'investigate_company'
  ),
  'investigate_company'
);
assert(investigation.type === 'investigation_packet', 'investigation packet type mismatch');
assert(investigation.version === '0.5.0', 'investigation packet version mismatch');
assert(investigation.enterprise_cognition, 'enterprise_cognition missing');
assert(investigation.quality_gate, 'quality_gate missing');
assert(Array.isArray(investigation.evidence_ledger), 'evidence_ledger missing');
assert(investigation.evidence_ledger.length >= 1, 'evidence_ledger empty');
assert(investigation.one_click_readiness, 'one_click_readiness missing');
assert(
  typeof investigation.one_click_readiness.coverage_not_searched_count === 'number',
  'one_click_readiness coverage_not_searched_count missing'
);
assert(
  typeof investigation.one_click_readiness.coverage_no_evidence_count === 'number',
  'one_click_readiness coverage_no_evidence_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.coverage_domains_without_evidence),
  'one_click_readiness coverage_domains_without_evidence missing'
);
assert(
  typeof investigation.one_click_readiness.public_origin_next_action_count === 'number',
  'one_click_readiness public_origin_next_action_count missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'public_origin_top_action'),
  'one_click_readiness public_origin_top_action missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_candidate_watch_count === 'number',
  'one_click_readiness relationship_candidate_watch_count missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_candidate_execution_step_count === 'number',
  'one_click_readiness relationship_candidate_execution_step_count missing'
);
assert(
  typeof investigation.one_click_readiness.capital_relationship_status === 'string',
  'one_click_readiness capital_relationship_status missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'capital_relationship_next_action'),
  'one_click_readiness capital_relationship_next_action missing'
);
assert(typeof investigation.report_markdown === 'string', 'report_markdown missing');
assert(investigation.report_markdown.includes('0.5.0'), 'report_markdown lacks version header');
assert(investigation.report_exports, 'report_exports missing');
assert(
  investigation.report_exports.markdown?.content_field === 'report_markdown',
  'report_exports markdown contract missing'
);
assert(
  investigation.report_exports.future_formats?.docx_red_head === 'p2_template_required_not_current_release_blocker',
  'report_exports docx future boundary missing'
);
assert(investigation.monitoring_seed, 'monitoring_seed missing');
assert(
  investigation.monitoring_seed.current_release_monitoring_enabled === false,
  'monitoring must remain later-version only'
);

console.log(JSON.stringify({
  ok: true,
  checked: [
    'release_readiness',
    'connector_catalog',
    'development_requirements',
    'investigate_company'
  ],
  variants: REQUIRED_VARIANTS,
  version: release.version
}, null, 2));
