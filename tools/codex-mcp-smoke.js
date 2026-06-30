#!/usr/bin/env node
/**
 * Packaged Codex smoke for the executable MCP backing tools.
 *
 * This avoids a host-specific MCP client handshake and verifies the same
 * runtime surfaces the MCP server exposes: investigation packet, datasource
 * catalog, and release readiness.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NODE = process.execPath;
const PYTHON = process.env.WST_PYTHON || process.env.PYTHON || '';
const SMOKE_DIR = path.join(os.tmpdir(), 'wallstreet-tieling-smoke');
fs.mkdirSync(SMOKE_DIR, { recursive: true });
const SMOKE_STORE = path.join(SMOKE_DIR, `risk-events-${process.pid}.jsonl`);
const CLI_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;

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

const connectors = parseJson(run(['--connectors'], 'connector_catalog'), 'connector_catalog');
assert(connectors.type === 'connector_catalog', 'connector_catalog type mismatch');
assert(connectors.summary.zero_config_ready.includes('default_public_intel'), 'default_public_intel missing');
assert(connectors.summary.admission_counts, 'connector admission counts missing');
assert(
  connectors.connectors.some((item) => item.name === 'sec_edgar_public_api' && item.admission?.decision === 'production_ready'),
  'SEC EDGAR production admission missing'
);

const release = parseJson(run(['--release'], 'release_readiness'), 'release_readiness');
assert(release.type === 'release_readiness_brief', 'release_readiness type mismatch');
assert(release.contract.variants.codex.readiness === 'alpha', 'codex readiness mismatch');

const requirements = parseJson(run(['--requirements'], 'development_requirements'), 'development_requirements');
assert(requirements.type === 'development_requirements_board', 'development_requirements type mismatch');
assert(requirements.summary.by_level.P0 >= 1, 'development requirements P0 lane missing');
assert(
  requirements.scope_rules.continuous_monitoring === 'future_version_not_current_release',
  'continuous monitoring scope boundary missing'
);

const investigation = parseJson(
  run(
    [
      '--investigate',
      'Demo Codex MCP Smoke Co., Ltd.',
      '--offline-fixture',
      '--store',
      SMOKE_STORE
    ],
    'investigate_company'
  ),
  'investigate_company'
);
assert(investigation.type === 'investigation_packet', 'investigation packet type mismatch');
assert(investigation.enterprise_cognition, 'enterprise_cognition missing');
assert(investigation.quality_gate, 'quality_gate missing');
assert(Array.isArray(investigation.quality_gate.blockers), 'quality_gate blockers missing');
assert(investigation.one_click_readiness, 'one_click_readiness missing');
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_resilience_recommended_action'),
  'one_click_readiness source_resilience_recommended_action missing'
);
assert(
  typeof investigation.one_click_readiness.coverage_not_searched_count === 'number',
  'one_click_readiness coverage_not_searched_count missing'
);
assert(
  typeof investigation.one_click_readiness.coverage_no_evidence_count === 'number',
  'one_click_readiness coverage_no_evidence_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.coverage_missing_domains),
  'one_click_readiness coverage_missing_domains missing'
);
assert(
  typeof investigation.one_click_readiness.public_origin_next_action_count === 'number',
  'one_click_readiness public_origin_next_action_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.public_origin_modules),
  'one_click_readiness public_origin_modules missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_candidate_execution_step_count === 'number',
  'one_click_readiness relationship_candidate_execution_step_count missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'relationship_candidate_top_step'),
  'one_click_readiness relationship_candidate_top_step missing'
);
assert(
  typeof investigation.one_click_readiness.capital_relationship_status === 'string',
  'one_click_readiness capital_relationship_status missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'capital_relationship_unresolved_reason'),
  'one_click_readiness capital_relationship_unresolved_reason missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_edge_count === 'number',
  'one_click_readiness relationship_edge_count missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_evidence_backed_edge_count === 'number',
  'one_click_readiness relationship_evidence_backed_edge_count missing'
);
assert(
  typeof investigation.one_click_readiness.relationship_auditable_edge_count === 'number',
  'one_click_readiness relationship_auditable_edge_count missing'
);
assert(investigation.monitoring_seed, 'monitoring_seed missing');
assert(investigation.report_exports, 'report_exports missing');
assert(
  investigation.report_exports.portable_html?.document?.startsWith('<!doctype html>'),
  'report_exports portable_html document missing'
);
assert(
  investigation.monitoring_seed.recovery_execution_summary,
  'recovery_execution_summary missing'
);
assert(
  typeof investigation.monitoring_seed.recovery_execution_summary.blocked_count === 'number',
  'recovery_execution_summary blocked_count missing'
);

console.log(JSON.stringify({
  ok: true,
  checked: ['connector_catalog', 'release_readiness', 'development_requirements', 'investigate_company'],
  version: release.version
}, null, 2));
