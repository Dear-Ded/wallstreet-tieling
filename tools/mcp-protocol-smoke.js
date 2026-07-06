#!/usr/bin/env node
/**
 * Real MCP stdio protocol smoke.
 *
 * codex:mcp-smoke verifies the same runtime payloads through the CLI backend.
 * This script verifies the MCP transport itself by speaking JSON-RPC over
 * stdio to lib/mcp-server.js: initialize, tools/list, and tools/call.
 */
const { spawn } = require('child_process');
const path = require('path');
const readline = require('readline');

const ROOT = path.join(__dirname, '..');
const SERVER = path.join(ROOT, 'lib', 'mcp-server.js');
const TIMEOUT_MS = Number(process.env.WST_MCP_PROTOCOL_SMOKE_TIMEOUT_MS || 60000);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function textFromToolResult(result) {
  const item = Array.isArray(result?.content) ? result.content.find((entry) => entry?.type === 'text') : null;
  assert(item?.text, 'tool result did not include text content');
  return item.text;
}

function parseToolJson(result, label) {
  try {
    return JSON.parse(textFromToolResult(result));
  } catch (error) {
    throw new Error(`${label} did not return JSON text: ${error.message}`);
  }
}

class JsonRpcClient {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
    this.stderr = [];
    this.child = spawn(process.execPath, [SERVER], {
      cwd: ROOT,
      env: {
        ...process.env,
        PYTHONUTF8: '1',
        WST_MCP_TIMEOUT_MS: process.env.WST_MCP_TIMEOUT_MS || '120000'
      },
      stdio: ['pipe', 'pipe', 'pipe']
    });
    this.child.stderr.on('data', (chunk) => this.stderr.push(chunk.toString()));
    this.child.on('exit', (code, signal) => {
      for (const { reject, timer } of this.pending.values()) {
        clearTimeout(timer);
        reject(new Error(`MCP server exited before response: code=${code} signal=${signal}`));
      }
      this.pending.clear();
    });

    const lines = readline.createInterface({ input: this.child.stdout });
    lines.on('line', (line) => this._onLine(line));
  }

  _onLine(line) {
    if (!line.trim()) {
      return;
    }
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      this._rejectAll(new Error(`invalid JSON-RPC line: ${error.message}; line=${line.slice(0, 200)}`));
      return;
    }
    if (!Object.prototype.hasOwnProperty.call(message, 'id')) {
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) {
      return;
    }
    clearTimeout(pending.timer);
    this.pending.delete(message.id);
    if (message.error) {
      pending.reject(new Error(`JSON-RPC error for id=${message.id}: ${JSON.stringify(message.error)}`));
      return;
    }
    pending.resolve(message.result);
  }

  _rejectAll(error) {
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    this.pending.clear();
  }

  request(method, params = {}) {
    const id = this.nextId++;
    const payload = { jsonrpc: '2.0', id, method, params };
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        const stderr = this.stderr.join('').trim();
        reject(new Error(`timeout waiting for ${method}${stderr ? `; stderr=${stderr}` : ''}`));
      }, TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timer });
    });
    this.child.stdin.write(`${JSON.stringify(payload)}\n`);
    return promise;
  }

  notify(method, params = {}) {
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`);
  }

  close() {
    this.child.stdin.end();
    this.child.kill();
  }
}

async function main() {
  const client = new JsonRpcClient();
  try {
    const init = await client.request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'wallstreet-tieling-protocol-smoke', version: '0.5.0' }
    });
    assert(init.protocolVersion, 'initialize response missing protocolVersion');
    client.notify('notifications/initialized');

    const toolsResult = await client.request('tools/list');
    const toolNames = new Set((toolsResult.tools || []).map((tool) => tool.name));
    for (const name of ['load_skill', 'release_readiness', 'agent_delivery_packet', 'verify_report_bundle']) {
      assert(toolNames.has(name), `MCP tools/list missing ${name}`);
    }

    const skill = await client.request('tools/call', {
      name: 'load_skill',
      arguments: { brief: true }
    });
    assert(textFromToolResult(skill).includes('Wallstreet Tieling'), 'load_skill did not return skill content');

    const release = parseToolJson(
      await client.request('tools/call', { name: 'release_readiness', arguments: {} }),
      'release_readiness'
    );
    assert(release.type === 'release_readiness_brief', 'release_readiness type mismatch');
    assert(
      release.delivery_decision?.status === 'desktop_agent_alpha_release_candidate',
      'release_readiness delivery decision mismatch'
    );
    assert(release.delivery_decision?.status === 'desktop_agent_alpha_release_candidate', 'release_readiness is not a desktop-agent alpha candidate');
    assert(
      release.runtime_delivery?.release_blocking_surface_count === 0,
      'release_readiness still has runtime blocking surfaces'
    );
    assert(
      Number(release.delivery_decision?.variant_next_gate_count || 0) >= 7,
      'variant next gates missing'
    );
    assert(
      release.latest_acceptance_evidence?.supporting_commands?.includes('npm run release:agent-smoke'),
      'latest acceptance supporting command missing'
    );

    const delivery = parseToolJson(
      await client.request('tools/call', { name: 'agent_delivery_packet', arguments: { host_id: 'codex' } }),
      'agent_delivery_packet'
    );
    assert(delivery.type === 'agent_delivery_packet', 'agent_delivery_packet type mismatch');
    assert(delivery.host_count === 1, 'agent_delivery_packet host filter mismatch');
    assert(delivery.hosts?.[0]?.host_id === 'codex', 'agent_delivery_packet codex host missing');

    console.log(JSON.stringify({
      ok: true,
      checked: ['stdio_initialize', 'tools_list', 'load_skill', 'release_readiness', 'agent_delivery_packet'],
      protocol_version: init.protocolVersion,
      tool_count: toolNames.size,
      version: release.version
    }, null, 2));
  } catch (error) {
    const stderr = client.stderr.join('').trim();
    if (stderr) {
      console.error(stderr);
    }
    throw error;
  } finally {
    client.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
