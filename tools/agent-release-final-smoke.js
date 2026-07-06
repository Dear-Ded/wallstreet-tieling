#!/usr/bin/env node
/**
 * Single-command desktop-agent release gate.
 *
 * This verifies the exact package surfaces desktop agents consume: CLI release
 * contracts, investigation export directory, bundle verifier, report files, and
 * npm package contents. It is intentionally host-neutral and offline-fixture
 * based so Codex, Claude Code, Hermes, OpenClaude, Doubao task mode, and
 * WorkBuddy can all run the same final check before handoff.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NODE = process.execPath;
const OUT_MAX = 32 * 1024 * 1024;
const EXPORT_DIR = path.join(os.tmpdir(), `wallstreet-tieling-agent-release-${process.pid}`);

function run(command, args, label, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1', ...(options.env || {}) },
    encoding: 'utf-8',
    maxBuffer: OUT_MAX,
    shell: Boolean(options.shell),
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (result.status !== 0) {
    throw new Error(`${label} failed: ${result.error?.message || result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function runCli(args, label) {
  return run(NODE, [path.join(ROOT, 'bin', 'cli.js'), ...args], label);
}

function runNpmPackDryRun() {
  if (process.platform === 'win32') {
    return run(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', 'npm pack --dry-run --json'], 'npm pack dry-run');
  }
  return run('npm', ['pack', '--dry-run', '--json'], 'npm pack dry-run');
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

function readJson(filePath, label) {
  return parseJson(fs.readFileSync(filePath, 'utf-8'), label);
}

function assertFile(filePath, label, minBytes = 1) {
  assert(fs.existsSync(filePath), `${label} missing: ${filePath}`);
  const stat = fs.statSync(filePath);
  assert(stat.isFile(), `${label} is not a file: ${filePath}`);
  assert(stat.size >= minBytes, `${label} too small: ${stat.size} bytes`);
}

fs.rmSync(EXPORT_DIR, { recursive: true, force: true });
fs.mkdirSync(EXPORT_DIR, { recursive: true });

const release = parseJson(runCli(['--release'], 'release_readiness'), 'release_readiness');
assert(release.type === 'release_readiness_brief', 'release type mismatch');
assert(release.delivery_decision?.status === 'desktop_agent_alpha_release_candidate', 'desktop-agent release decision is not candidate');
assert(release.delivery_decision?.full_product_status === 'not_final_release_ready', 'final-product boundary missing');
assert(release.runtime_delivery?.release_blocking_surface_count === 0, 'runtime delivery still has blocking surfaces');

const delivery = parseJson(runCli(['--agent-delivery'], 'agent_delivery_packet'), 'agent_delivery_packet');
assert(delivery.type === 'agent_delivery_packet', 'agent delivery packet type mismatch');
assert(delivery.release_candidate === true, 'agent delivery packet is not release candidate');
assert(delivery.host_count === 7, 'agent delivery host count mismatch');
assert(delivery.verification?.required_commands?.includes('npm run release:agent-smoke'), 'final release smoke command missing from delivery packet');
assert(
  delivery.verification?.advanced_autopilot_contract?.interaction_model === 'subject_name_only_after_workspace_preconfiguration',
  'advanced autopilot contract missing from delivery packet'
);
assert(
  delivery.verification?.submission_evidence_contract?.command === 'npm run release:submission-snapshot',
  'submission evidence contract missing from delivery packet'
);

const doctor = parseJson(runCli(['--agent-doctor'], 'agent_delivery_doctor'), 'agent_delivery_doctor');
assert(doctor.type === 'agent_delivery_doctor', 'agent doctor type mismatch');
assert(doctor.status === 'pass', 'agent doctor did not pass');
assert(doctor.checks?.package_files?.missing?.length === 0, 'agent doctor reports missing package files');
assert(
  doctor.checks?.commands?.some((item) => item.command === 'npm run release:agent-smoke'),
  'agent doctor does not list final release smoke'
);

const tools = parseJson(runCli(['--agent-tools'], 'agent_tool_adapters'), 'agent_tool_adapters');
assert(tools.type === 'agent_tool_adapter_manifest', 'agent tool manifest type mismatch');
assert(tools.all_current_release_ready === true, 'not all current release adapters are ready');
assert(tools.required_smoke_commands.includes('npm run release:agent-smoke'), 'agent tools final smoke command missing');

const protocolSmoke = parseJson(
  run(NODE, [path.join(ROOT, 'tools', 'mcp-protocol-smoke.js')], 'MCP protocol smoke'),
  'MCP protocol smoke'
);
assert(protocolSmoke.ok === true, 'MCP protocol smoke failed');

const targets = parseJson(runCli(['--report-targets'], 'report_delivery_targets'), 'report_delivery_targets');
const outputs = new Map(targets.current_release_outputs.map((item) => [item.id, item]));
assert(outputs.get('docx_red_head')?.required === true, 'DOCX red-head output target missing');
assert(outputs.get('portable_html')?.required === true, 'portable HTML output target missing');
assert(targets.persona_interaction_contract?.role_count === 13, 'persona role-count contract missing');

const investigation = parseJson(
  runCli(
    [
      '--investigate',
      'Demo Final Agent Release Smoke Co., Ltd.',
      '--offline-fixture',
      '--export-dir',
      EXPORT_DIR
    ],
    'investigate export-dir'
  ),
  'investigation packet'
);
assert(investigation.type === 'investigation_packet', 'investigation packet type mismatch');
assert(investigation.report_exports?.report_delivery_targets?.type === 'report_delivery_targets', 'packet report targets missing');
assert(investigation.report_exports?.agent_decision_digest?.type === 'agent_decision_digest', 'packet decision digest missing');

const manifestPath = path.join(EXPORT_DIR, 'report-export-manifest.json');
const handoffPath = path.join(EXPORT_DIR, 'agent-handoff.json');
assertFile(manifestPath, 'export manifest', 500);
assertFile(handoffPath, 'agent handoff', 500);

const manifest = readJson(manifestPath, 'export manifest');
const files = manifest.files || {};
for (const role of ['docx', 'portable_html', 'markdown', 'json_packet', 'agent_handoff', 'manifest']) {
  assert(files[role], `manifest file role missing: ${role}`);
}

const docxPath = path.join(EXPORT_DIR, files.docx);
const htmlPath = path.join(EXPORT_DIR, files.portable_html);
const markdownPath = path.join(EXPORT_DIR, files.markdown);
const jsonPath = path.join(EXPORT_DIR, files.json_packet);
assertFile(docxPath, 'DOCX report', 2000);
assertFile(htmlPath, 'portable HTML report', 1000);
assertFile(markdownPath, 'Markdown report', 500);
assertFile(jsonPath, 'JSON packet', 1000);

const html = fs.readFileSync(htmlPath, 'utf-8');
assert(html.startsWith('<!doctype html>'), 'portable HTML doctype missing');
for (const needle of ['Agent decision digest', 'Report delivery targets', 'docx_red_head', 'persona_not_shrunk']) {
  assert(html.includes(needle), `portable HTML missing section marker: ${needle}`);
}

const handoff = readJson(handoffPath, 'agent handoff');
assert(handoff.type === 'report_export_agent_handoff', 'agent handoff type mismatch');
assert(handoff.delivery_decision?.status === 'desktop_agent_alpha_release_candidate', 'handoff delivery decision mismatch');
assert(handoff.decision_digest?.type === 'agent_decision_digest', 'handoff decision digest missing');
assert(handoff.deep_autopilot_execution_plan?.type === 'deep_autopilot_execution_plan', 'handoff deep autopilot plan missing');
assert(handoff.deep_autopilot_source_runbook?.type === 'deep_autopilot_source_runbook', 'handoff deep autopilot source runbook missing');
assert(
  handoff.deep_autopilot_execution_plan?.automation_contract?.operator_work_queue_role ===
    'internal_autopilot_recovery_queue_not_end_user_task_list',
  'handoff deep autopilot internal queue contract missing'
);
assert(
  handoff.deep_autopilot_source_runbook?.automatic_lane_count >= 8 &&
    handoff.deep_autopilot_source_runbook.lanes?.every((item) => item.user_prompt_required === false && item.stop_on_failure === false),
  'handoff deep autopilot source runbook no-prompt/non-stop contract missing'
);
assert(
  handoff.deep_autopilot_execution_plan?.continuation_entrypoints?.some((item) => item.tool === 'investigate_company'),
  'handoff deep autopilot continuation entrypoint missing'
);
assert(Array.isArray(handoff.next_actions), 'handoff next actions missing');

const verifier = parseJson(
  run(NODE, [path.join(ROOT, 'tools', 'run-python.js'), path.join(ROOT, 'bin', 'verify_report_bundle.py'), EXPORT_DIR], 'report bundle verifier'),
  'report bundle verifier'
);
assert(verifier.ok === true, 'report bundle verifier failed');
assert(verifier.agent_handoff?.schema_valid === true, 'agent handoff schema verifier failed');
assert(verifier.agent_handoff?.deep_autopilot_plan_present === true, 'agent handoff deep autopilot verifier missing');
assert(verifier.agent_handoff?.continuation_entrypoints_valid === true, 'agent handoff continuation verifier failed');
assert(verifier.agent_handoff?.deep_autopilot_source_runbook_present === true, 'agent handoff source runbook verifier missing');
assert(verifier.agent_handoff?.source_runbook_valid === true, 'agent handoff source runbook verifier failed');
assert(verifier.checked_count >= 4, 'bundle verifier checked too few files');

const cliVerifier = parseJson(
  runCli(['--verify-report-bundle', EXPORT_DIR], 'CLI report bundle verifier'),
  'CLI report bundle verifier'
);
assert(cliVerifier.ok === true, 'CLI report bundle verifier failed');
assert(cliVerifier.agent_handoff?.schema_valid === true, 'CLI agent handoff schema verifier failed');
assert(cliVerifier.agent_handoff?.deep_autopilot_plan_present === true, 'CLI agent handoff deep autopilot verifier missing');
assert(cliVerifier.agent_handoff?.continuation_entrypoints_valid === true, 'CLI agent handoff continuation verifier failed');
assert(cliVerifier.agent_handoff?.deep_autopilot_source_runbook_present === true, 'CLI agent handoff source runbook verifier missing');
assert(cliVerifier.agent_handoff?.source_runbook_valid === true, 'CLI agent handoff source runbook verifier failed');

const pack = parseJson(runNpmPackDryRun(), 'npm pack dry-run')[0];
const packedPaths = new Set(pack.files.map((item) => item.path));
for (const requiredPath of [
  'SKILL.md',
  'CLAUDE.md',
  'bin/cli.js',
  'bin/investigate.py',
  'bin/verify_report_bundle.py',
  'lib/mcp-server.js',
  'api/server.py',
  'core/agent_delivery_doctor.py',
  'core/agent_tool_adapters.py',
  'core/report_delivery_targets.py',
  'tools/agent-release-final-smoke.js',
  'tools/agent-package-install-smoke.js',
  'tools/release-submission-snapshot.js',
  'tools/agent-host-smoke.js',
  'tools/codex-mcp-smoke.js',
  'tools/mcp-protocol-smoke.js',
  'tools/api-smoke.py',
  'deploy/mcp-server.json',
  'release/variants.yaml'
]) {
  assert(packedPaths.has(requiredPath), `npm package missing required path: ${requiredPath}`);
}
for (const itemPath of packedPaths) {
  assert(!itemPath.startsWith('output/'), 'npm package includes output artifact');
  assert(!itemPath.startsWith('docs/workbuddy/'), 'npm package includes WorkBuddy private docs');
}

const installSmoke = parseJson(
  run(NODE, [path.join(ROOT, 'tools', 'agent-package-install-smoke.js')], 'installed package smoke'),
  'installed package smoke'
);
assert(installSmoke.ok === true, 'installed package smoke failed');
assert(installSmoke.checked?.includes('installed_verify_report_bundle'), 'installed package verifier check missing');

console.log(JSON.stringify({
  ok: true,
  checked: [
    'release_readiness',
    'agent_delivery_packet',
    'agent_delivery_doctor',
    'agent_tool_adapters',
    'mcp_protocol_smoke',
    'report_delivery_targets',
    'investigate_export_dir',
    'report_bundle_verifier',
    'cli_report_bundle_verifier',
    'installed_package_smoke',
    'npm_pack_dry_run'
  ],
  export_dir: EXPORT_DIR,
  version: release.version,
  host_count: delivery.host_count,
  packed_file_count: pack.files.length
}, null, 2));
