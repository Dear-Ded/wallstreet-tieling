#!/usr/bin/env node
/**
 * Build a local desktop-agent submission evidence folder.
 *
 * This is not a publish step. It collects the machine-readable outputs a
 * marketplace/operator reviewer needs after the release gates pass.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NODE = process.execPath;
const OUT_MAX = 32 * 1024 * 1024;

function argValue(name) {
  const index = process.argv.indexOf(name);
  if (index === -1) {
    return null;
  }
  return process.argv[index + 1] || null;
}

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

const outDir = path.resolve(
  ROOT,
  argValue('--out-dir') || path.join('.tmp', 'release-submission', timestampSlug())
);
const bundleDir = path.join(outDir, 'report-bundle');

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

function writeJson(name, value) {
  fs.writeFileSync(path.join(outDir, name), `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function writeText(name, value) {
  fs.writeFileSync(path.join(outDir, name), value, 'utf-8');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

const release = parseJson(runCli(['--release'], 'release readiness'), 'release readiness');
assert(release.delivery_decision?.status === 'desktop_agent_alpha_release_candidate', 'release is not a desktop-agent alpha candidate');
assert(release.delivery_decision?.remaining_variant_blocker_count === 0, 'release readiness still reports blocking variants');
assert(
  String(release.delivery_decision?.variant_next_gate_policy || '').includes('do not block desktop-agent alpha delivery'),
  'release readiness variant next-gate policy missing'
);
writeJson('release-readiness.json', release);

const closure = parseJson(runCli(['--delivery-closure'], 'delivery closure'), 'delivery closure');
const evidenceContract = closure.submission_evidence_contract || {};
assert(evidenceContract.command === 'npm run release:submission-snapshot', 'submission evidence command missing from closure');
writeJson('delivery-closure.json', closure);

const delivery = parseJson(runCli(['--agent-delivery'], 'agent delivery packet'), 'agent delivery packet');
assert(delivery.release_candidate === true, 'agent delivery packet is not a release candidate');
writeJson('agent-delivery-packet.json', delivery);

const doctor = parseJson(runCli(['--agent-doctor'], 'agent doctor'), 'agent doctor');
assert(doctor.status === 'pass', 'agent doctor did not pass');
writeJson('agent-doctor.json', doctor);

const tools = parseJson(runCli(['--agent-tools'], 'agent tools'), 'agent tools');
assert(tools.all_current_release_ready === true, 'not all current-release agent tools are ready');
writeJson('agent-tools.json', tools);

const connectors = parseJson(runCli(['--connectors'], 'connector catalog'), 'connector catalog');
writeJson('connector-catalog.json', connectors);

const targets = parseJson(runCli(['--report-targets'], 'report delivery targets'), 'report delivery targets');
writeJson('report-delivery-targets.json', targets);

const protocolSmoke = parseJson(
  run(NODE, [path.join(ROOT, 'tools', 'mcp-protocol-smoke.js')], 'MCP protocol smoke'),
  'MCP protocol smoke'
);
assert(protocolSmoke.ok === true, 'MCP protocol smoke failed');
writeJson('mcp-protocol-smoke.json', protocolSmoke);

const pack = parseJson(runNpmPackDryRun(), 'npm pack dry-run');
writeJson('npm-pack-dry-run.json', pack);

const investigation = parseJson(
  runCli(
    [
      '--investigate',
      'Demo Submission Snapshot Co., Ltd.',
      '--offline-fixture',
      '--export-dir',
      bundleDir
    ],
    'investigation report bundle'
  ),
  'investigation report bundle'
);
assert(investigation.type === 'investigation_packet', 'investigation did not return an investigation packet');
writeJson('investigation-packet.json', investigation);

const verifier = parseJson(
  runCli(['--verify-report-bundle', bundleDir], 'report bundle verifier'),
  'report bundle verifier'
);
assert(verifier.ok === true, 'report bundle verifier failed');
writeJson('report-bundle-verifier.json', verifier);

const summary = {
  ok: true,
  type: 'release_submission_snapshot',
  version: release.version,
  release_status: release.delivery_decision.status,
  generated_at: new Date().toISOString(),
  out_dir: outDir,
  report_bundle: bundleDir,
  checked: [
    'release_readiness',
    'delivery_closure',
    'agent_delivery_packet',
    'agent_delivery_doctor',
    'agent_tool_adapters',
    'connector_catalog',
    'report_delivery_targets',
    'mcp_protocol_smoke',
    'npm_pack_dry_run',
    'investigation_export_dir',
    'report_bundle_verifier'
  ],
  evidence_contract: evidenceContract,
  submission_open_items: closure.open_submission_items || []
};
writeJson('summary.json', summary);

for (const requiredCheck of evidenceContract.required_checks || []) {
  assert(summary.checked.includes(requiredCheck), `summary missing required evidence check: ${requiredCheck}`);
}

writeText(
  'README.txt',
  [
    'Wallstreet Tieling desktop-agent submission evidence snapshot',
    '',
    `Version: ${summary.version}`,
    `Release status: ${summary.release_status}`,
    `Generated at: ${summary.generated_at}`,
    `Evidence contract: ${evidenceContract.type || 'missing'}`,
    '',
    'Primary files:',
    '- release-readiness.json',
    '- delivery-closure.json',
    '- agent-delivery-packet.json',
    '- agent-doctor.json',
    '- agent-tools.json',
    '- connector-catalog.json',
    '- report-delivery-targets.json',
    '- mcp-protocol-smoke.json',
    '- npm-pack-dry-run.json',
    '- report-bundle/',
    '- report-bundle-verifier.json',
    '',
    'Not included:',
    '- marketplace approval',
    '- human-captured screenshots',
    '- credentials, cookies, browser profiles, or runtime state',
    ''
  ].join('\n')
);

console.log(JSON.stringify(summary, null, 2));
