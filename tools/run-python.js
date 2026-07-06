#!/usr/bin/env node
/**
 * Resolve a usable Python runtime for npm scripts.
 *
 * Windows desktop-agent hosts often lack `python` on PATH even when a bundled
 * Codex/Python runtime exists. Keep npm scripts host-neutral by resolving the
 * runtime here instead of hard-coding `python`.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const PYTHON_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;

function resolvePython() {
  const candidates = [
    process.env.WST_PYTHON,
    process.env.PYTHON,
    path.join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(
      os.homedir(),
      '.cache',
      'codex-runtimes',
      'codex-primary-runtime',
      'dependencies',
      'python',
      process.platform === 'win32' ? 'python.exe' : 'bin/python'
    ),
    process.platform === 'win32' ? 'py' : 'python3',
    'python'
  ].filter(Boolean);

  for (const candidate of candidates) {
    const check = spawnSync(candidate, ['--version'], { encoding: 'utf-8' });
    if (check.status === 0) {
      return candidate;
    }
    if (check.error?.code === 'EPERM' && path.isAbsolute(candidate) && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  console.error('No usable Python runtime found. Set WST_PYTHON to continue.');
  process.exit(1);
}

function psQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function runPython(python, args) {
  const env = { ...process.env, PYTHONUTF8: '1' };
  const direct = spawnSync(python, args, {
    cwd: ROOT,
    env,
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (direct.error?.code !== 'EPERM' || process.platform !== 'win32' || !path.isAbsolute(python)) {
    return direct;
  }

  const command = `& ${psQuote(python)} ${args.map(psQuote).join(' ')}`;
  return spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command], {
    cwd: ROOT,
    env,
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });
}

const scriptArgs = process.argv.slice(2);
if (scriptArgs.length === 0) {
  console.error('Usage: node tools/run-python.js <script-or-module> [args...]');
  process.exit(2);
}

const result = runPython(resolvePython(), scriptArgs);

if (result.stdout) {
  process.stdout.write(result.stdout);
}
if (result.stderr) {
  process.stderr.write(result.stderr);
}
if (result.error) {
  process.stderr.write(`${result.error.message}\n`);
}
process.exit(result.error ? 1 : (result.status || 0));
