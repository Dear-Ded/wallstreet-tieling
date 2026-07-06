#!/usr/bin/env node
/**
 * Install the packed npm artifact into a temporary project and execute the
 * packaged CLI from node_modules. This catches package.json/files mistakes that
 * a dry-run content check cannot prove.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NODE = process.execPath;
const OUT_MAX = 32 * 1024 * 1024;
const SMOKE_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'wallstreet-tieling-install-smoke-'));
const PACK_DIR = path.join(SMOKE_ROOT, 'pack');
const INSTALL_DIR = path.join(SMOKE_ROOT, 'project');
fs.mkdirSync(PACK_DIR, { recursive: true });
fs.mkdirSync(INSTALL_DIR, { recursive: true });

function run(command, args, label, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || ROOT,
    env: { ...process.env, PYTHONUTF8: '1', ...(options.env || {}) },
    encoding: 'utf-8',
    maxBuffer: OUT_MAX,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (result.status !== 0) {
    throw new Error(`${label} failed: ${result.error?.message || result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function runNpm(args, label, cwd = ROOT) {
  if (process.platform === 'win32') {
    return run(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', ['npm', ...args.map(quoteCmdArg)].join(' ')], label, { cwd });
  }
  return run('npm', args, label, { cwd });
}

function quoteCmdArg(value) {
  const raw = String(value);
  if (!/[ \t"&|<>^]/.test(raw)) {
    return raw;
  }
  return `"${raw.replace(/"/g, '\\"')}"`;
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

const packPayload = parseJson(
  runNpm(['pack', '--json', '--pack-destination', PACK_DIR], 'npm pack'),
  'npm pack'
)[0];
const tarball = path.join(PACK_DIR, packPayload.filename);
assert(fs.existsSync(tarball), `packed tarball missing: ${tarball}`);

runNpm(['init', '-y'], 'npm init', INSTALL_DIR);
runNpm(['install', tarball, '--ignore-scripts', '--no-audit', '--no-fund'], 'npm install packed tarball', INSTALL_DIR);

const packageRoot = path.join(INSTALL_DIR, 'node_modules', 'wallstreet-tieling');
const cli = path.join(packageRoot, 'bin', 'cli.js');
assert(fs.existsSync(cli), 'installed CLI missing');

function runInstalledCli(args, label) {
  return run(NODE, [cli, ...args], label, { cwd: packageRoot });
}

const doctor = parseJson(runInstalledCli(['--agent-doctor'], 'installed agent doctor'), 'installed agent doctor');
assert(doctor.type === 'agent_delivery_doctor', 'installed agent doctor type mismatch');
assert(doctor.status === 'pass', 'installed agent doctor did not pass');
assert(doctor.release_candidate === true, 'installed agent doctor release candidate missing');

const tools = parseJson(runInstalledCli(['--agent-tools'], 'installed agent tools'), 'installed agent tools');
assert(tools.type === 'agent_tool_adapter_manifest', 'installed agent tools type mismatch');
assert(tools.all_current_release_ready === true, 'installed agent tools readiness mismatch');
assert(tools.shared_tools.some((tool) => tool.name === 'verify_report_bundle'), 'installed verify_report_bundle tool missing');

const exportDir = path.join(SMOKE_ROOT, 'report-bundle');
const packet = parseJson(
  runInstalledCli(
    [
      '--investigate',
      'Demo Installed Package Smoke Co., Ltd.',
      '--offline-fixture',
      '--export-dir',
      exportDir
    ],
    'installed investigate export-dir'
  ),
  'installed investigation packet'
);
assert(packet.type === 'investigation_packet', 'installed investigation packet type mismatch');
assert(packet.report_exports?.agent_decision_digest?.type === 'agent_decision_digest', 'installed packet decision digest missing');

const bundle = parseJson(
  runInstalledCli(['--verify-report-bundle', exportDir], 'installed verify report bundle'),
  'installed verify report bundle'
);
assert(bundle.ok === true, 'installed report bundle verifier failed');
assert(bundle.agent_handoff?.schema_valid === true, 'installed report bundle handoff schema invalid');
assert(bundle.agent_handoff?.deep_autopilot_plan_present === true, 'installed report bundle deep autopilot verifier missing');
assert(bundle.agent_handoff?.continuation_entrypoints_valid === true, 'installed report bundle continuation verifier failed');

console.log(JSON.stringify({
  ok: true,
  checked: [
    'npm_pack_real_tarball',
    'npm_install_packed_tarball',
    'installed_agent_doctor',
    'installed_agent_tools',
    'installed_investigate_export_dir',
    'installed_verify_report_bundle'
  ],
  package_root: packageRoot,
  tarball,
  version: doctor.version,
  packed_file_count: packPayload.files.length
}, null, 2));
