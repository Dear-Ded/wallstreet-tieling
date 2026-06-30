#!/usr/bin/env node
/**
 * Wallstreet Tieling CLI.
 *
 * Small public entry point for Skill loading, MCP startup, and one-click local
 * investigation smoke tests.
 */

const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const skillPath = path.join(ROOT, 'SKILL.md');
const pkg = require(path.join(ROOT, 'package.json'));
const PYTHON_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;

function showHelp() {
  console.log(`
Wallstreet Tieling Office / 华尔街驻铁岭办事处 v${pkg.version}
Open-source enterprise intelligence and risk discovery.

Usage:
  npx wallstreet-tieling
      Print the full SKILL.md.

  npx wallstreet-tieling --brief
      Print a compact Skill brief for small-context models.

  npx wallstreet-tieling --copy
      Copy SKILL.md to clipboard.

  npx wallstreet-tieling --mcp
      Start the MCP server for Codex, Claude Code, Hermes, OpenClaude, WorkBuddy, Doubao Office Task Mode, or other hosts.

  npx wallstreet-tieling --connectors
      Print datasource catalog, default-enabled sources, and readiness groups.

  npx wallstreet-tieling --release
      Print desktop-agent release readiness for Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy.

  npx wallstreet-tieling --requirements
      Print P0/P1/P2/Future development requirement levels and current completion.

  npx wallstreet-tieling --investigate "Company Name"
      Run zero-config one-click investigation and print the JSON packet.

  npx wallstreet-tieling --investigate "Company Name" --offline-fixture
      Run a deterministic local smoke report without network access.

  npx wallstreet-tieling --investigate "Company Name" --report-only
      Print the Markdown report only.

  npx wallstreet-tieling --investigate "Company Name" --official-public-smoke
      Run explicit official/public connector smoke.

  npx wallstreet-tieling --investigate "Company Name" --query-timeout-seconds 8
      Bound each retrieval task and return diagnostics for slow sources.

  npx wallstreet-tieling --investigate "Company Name" --store ./risk-events.jsonl
      Write the risk-event ledger to an explicit JSONL path.

Install:
  npm install -g wallstreet-tieling
  npx wallstreet-tieling --help
`);
}

function readSkill() {
  if (!fs.existsSync(skillPath)) {
    console.error('SKILL.md not found');
    process.exit(1);
  }
  return fs.readFileSync(skillPath, 'utf-8');
}

function outputSkill(brief = false) {
  const content = readSkill();
  if (!brief) {
    console.log(content);
    return;
  }
  const frontmatterEnd = content.indexOf('\n---', 4);
  const frontmatter = frontmatterEnd >= 0 ? content.slice(0, frontmatterEnd + 4) : '';
  const lines = content.split(/\r?\n/);
  const compact = lines
    .filter((line) => /^#{1,3} /.test(line) || /v0\.5\.0|一句话|尽调|风险|证据|开源|信息平权/.test(line))
    .slice(0, 80)
    .join('\n');
  console.log(`${frontmatter}\n\n${compact}`.trim());
}

function copyToClipboard() {
  const content = readSkill();
  const command = clipboardCommand();
  if (!command) {
    console.error('Clipboard command not found; printing SKILL.md instead.');
    outputSkill(false);
    return;
  }
  try {
    execFileSync(command.command, command.args, { input: content });
    console.log('SKILL.md copied to clipboard.');
  } catch (error) {
    console.error(`Clipboard copy failed: ${error.message}`);
    outputSkill(false);
  }
}

function clipboardCommand() {
  if (process.platform === 'darwin') {
    return { command: 'pbcopy', args: [] };
  }
  if (process.platform === 'win32') {
    return { command: 'clip', args: [] };
  }
  return { command: 'xclip', args: ['-selection', 'clipboard'] };
}

function runInvestigation(args) {
  const index = args.indexOf('--investigate');
  const company = args[index + 1];
  if (!company || company.startsWith('--')) {
    console.error('--investigate requires a company name.');
    process.exit(2);
  }

  const scriptArgs = [path.join(ROOT, 'bin', 'investigate.py'), company];
  for (const flag of ['--fixture-pack', '--offline-fixture', '--official-public-smoke', '--report-only']) {
    if (args.includes(flag)) {
      scriptArgs.push(flag);
    }
  }
  const configIndex = args.indexOf('--config');
  if (configIndex >= 0 && args[configIndex + 1]) {
    scriptArgs.push('--config', args[configIndex + 1]);
  }
  const modeIndex = args.indexOf('--mode');
  if (modeIndex >= 0 && args[modeIndex + 1]) {
    scriptArgs.push('--mode', args[modeIndex + 1]);
  }
  for (const option of ['--query-timeout-seconds', '--fanout-rounds', '--max-fanout-tasks', '--retrieval-concurrency', '--store']) {
    const optionIndex = args.indexOf(option);
    if (optionIndex >= 0 && args[optionIndex + 1]) {
      scriptArgs.push(option, args[optionIndex + 1]);
    }
  }

  const result = spawnSync(resolvePython(), scriptArgs, {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1' },
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  if (result.status !== 0) {
    process.stderr.write(result.stderr || result.stdout || 'investigation failed');
    process.exit(result.status || 1);
  }
  process.stdout.write(result.stdout);
}

function printPythonJson(moduleExpr) {
  const result = spawnSync(resolvePython(), ['-c', moduleExpr], {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1' },
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  if (result.status !== 0) {
    process.stderr.write(result.stderr || result.stdout || 'command failed');
    process.exit(result.status || 1);
  }
  process.stdout.write(result.stdout);
}

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
  }
  console.error('No usable Python runtime found. Set WST_PYTHON to continue.');
  process.exit(1);
}

const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  showHelp();
} else if (args.includes('--copy') || args.includes('-c')) {
  copyToClipboard();
} else if (args.includes('--brief') || args.includes('-b')) {
  outputSkill(true);
} else if (args.includes('--mcp')) {
  require('../lib/mcp-server.js');
} else if (args.includes('--connectors')) {
  printPythonJson([
    'import json',
    'from core.connector_registry import ConnectorRegistry',
    'print(json.dumps(ConnectorRegistry().product_catalog(), ensure_ascii=False, indent=2, sort_keys=True))'
  ].join('; '));
} else if (args.includes('--release')) {
  printPythonJson([
    'import json',
    'from core.release_contract import release_readiness_brief',
    'print(json.dumps(release_readiness_brief(), ensure_ascii=False, indent=2, sort_keys=True))'
  ].join('; '));
} else if (args.includes('--requirements')) {
  printPythonJson([
    'import json',
    'from core.development_requirements import build_development_requirements_board',
    'print(json.dumps(build_development_requirements_board(), ensure_ascii=False, indent=2, sort_keys=True))'
  ].join('; '));
} else if (args.includes('--investigate')) {
  runInvestigation(args);
} else {
  outputSkill(false);
}
