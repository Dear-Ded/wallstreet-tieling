#!/usr/bin/env node
/**
 * Wallstreet Tieling MCP server.
 *
 * The market-facing plugin should be able to do real work, not only return a
 * prompt. Company investigation tools therefore execute the local one-click
 * investigation pipeline and return the product-facing investigation_packet
 * JSON as text.
 */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');

const ROOT = path.join(__dirname, '..');
const skillPath = path.join(ROOT, 'SKILL.md');
const skillContent = fs.existsSync(skillPath)
  ? fs.readFileSync(skillPath, 'utf-8')
  : '# Wallstreet Tieling\n\nSKILL.md not found in package root.';

const companyInputSchema = {
  type: 'object',
  properties: {
    company_name: {
      type: 'string',
      description: 'Company name or unified social credit identifier.'
    },
    company: {
      type: 'string',
      description: 'Alias of company_name for API-style callers.'
    },
    message: {
      type: 'string',
      description: 'Natural one-line request; used when company_name/company is omitted.'
    },
    depth: {
      type: 'string',
      enum: ['quick', 'standard', 'deep'],
      description: 'Investigation depth label. The executable graph pipeline uses bounded fan-out controls.',
      default: 'standard'
    },
    config: {
      type: 'string',
      description: 'Optional datasource YAML path for live retrieval routing.'
    },
    offline_fixture: {
      type: 'boolean',
      description: 'Use deterministic local public-record fixture for smoke tests and demos.',
      default: false
    },
    fixture_pack: {
      type: 'boolean',
      description: 'Use the multi-source datasource fixture pack for connector demos.',
      default: false
    },
    official_public_smoke: {
      type: 'boolean',
      description: 'Run live official/public datasource smoke with selected public sources.',
      default: false
    },
    store: {
      type: 'string',
      description: 'Optional JSONL risk-event store path.'
    },
    retrieval_concurrency: {
      type: 'number',
      description: 'Maximum concurrent retrieval tasks, clamped to 1..20 by the Python CLI.',
      minimum: 1,
      maximum: 20,
      default: 4
    },
    fanout_rounds: {
      type: 'number',
      description: 'Bounded associative expansion rounds, clamped to 0..3 by the Python CLI.',
      minimum: 0,
      maximum: 3,
      default: 1
    },
    max_fanout_tasks: {
      type: 'number',
      description: 'Maximum generated fan-out tasks, clamped to 0..80 by the Python CLI.',
      minimum: 0,
      maximum: 80,
      default: 24
    },
    query_timeout_seconds: {
      type: 'number',
      description: 'Maximum seconds per retrieval task before returning a timeout diagnostic, clamped to 0.1..120.',
      minimum: 0.1,
      maximum: 120,
      default: 20
    }
  }
};

const TOOLS = [
  {
    name: 'investigate_company',
    description: 'One-click enterprise intelligence packet: one_click_readiness including acceptance_closure_summary, public_origin_gap_bridge, graph_capital_exposure, and source_health_trend_digest, report_exports including packet-level agent_decision_digest, directory_bundle verifier_output_fields and verification_recipe for bundle verifier booleans, directory_bundle manifest_fields with file_manifest, delivery_checklist, and agent_summary plus directory_bundle.agent_handoff with delivery_files, bundle_integrity, bundle_verification, delivery_checklist, report_visibility, capital_risk_panel, source_strengthening, trust_boundaries, decision_digest, next_actions, acceptance_closure, reliance_limitations, graph capital exposure, relationship graph audit summary, source-health digest, qyyjt_public_origin.gap_bridge, and qyyjt_public_origin.section_work_orders, qyyjt_public_origin_handoff with report_section_batches and section_work_orders, source-health snapshot, source-resilience recovery step, source repair priority queue, capital verification queue, relationship graph audit queue, quality gate, evidence graph, risk events, timeline, subject profile, monitoring delta.',
    inputSchema: {
      ...companyInputSchema,
      required: ['company_name']
    }
  },
  {
    name: 'due_diligence',
    description: 'Compatibility alias for investigate_company. Runs the executable risk-discovery graph pipeline and returns the same one_click_readiness acceptance_closure_summary, public_origin_gap_bridge, graph_capital_exposure, and source_health_trend_digest, report_exports packet-level agent_decision_digest, directory_bundle verifier_output_fields and verification_recipe for bundle verifier booleans, directory_bundle manifest_fields with file_manifest, delivery_checklist, and agent_summary plus directory_bundle.agent_handoff with delivery_files, bundle_integrity, bundle_verification, delivery_checklist, report_visibility, capital_risk_panel, source_strengthening, trust_boundaries, decision_digest, next_actions, acceptance_closure, reliance_limitations, graph capital exposure, relationship graph audit summary, source-health digest, qyyjt_public_origin.gap_bridge, and qyyjt_public_origin.section_work_orders, qyyjt_public_origin_handoff report_section_batches and section_work_orders, source repair, capital verification, and relationship audit fields.',
    inputSchema: {
      ...companyInputSchema,
      required: ['company_name']
    }
  },
  {
    name: 'people_investigation',
    description: 'Prepare a public/authorized person-background investigation brief for controller or key-person follow-up.',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Person name.' },
        known_public_identifier: {
          type: 'string',
          description: 'Publicly verifiable or user-authorized identifier, when available.'
        },
        authorized_context: {
          type: 'string',
          description: 'User authorization or business context for the investigation.'
        }
      },
      required: ['name']
    }
  },
  {
    name: 'financial_analysis',
    description: 'Return the Financial Intelligence Engine checklist for profitability, cash-flow quality, receivables, inventory, capex, related-party and fraud-signal analysis.',
    inputSchema: {
      type: 'object',
      properties: {
        company_name: { type: 'string' },
        years: { type: 'number', default: 3 }
      },
      required: ['company_name']
    }
  },
  {
    name: 'anti_nominee_detection',
    description: 'Return an evidence-first anti-nominee / beneficial-owner penetration checklist.',
    inputSchema: {
      type: 'object',
      properties: {
        company_name: { type: 'string' }
      },
      required: ['company_name']
    }
  },
  {
    name: 'connector_catalog',
    description: 'Return datasource catalog, default-enabled connectors, production/admission decisions, routing blockers, and source policy.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'release_readiness',
    description: 'Return desktop-agent release contract, remaining gates, runtime_delivery surfaces, latest_acceptance_evidence from npm run acceptance, acceptance_status_counts, release_blocking_surface_count, proof tests, and focused_test_command for Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'delivery_closure',
    description: 'Return the concise desktop-agent alpha delivery closure checklist: baseline tool sequence, required verification commands, required preserved packet fields, not-current-release boundaries, and final submission open items.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'release_preflight',
    description: 'Return the desktop-agent alpha local packaging go/no-go preflight with package_candidate_ready, final_submission_blockers, package privacy review checklist, required verification commands, and the safe release claim for desktop-agent hosts.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'delivery_audit',
    description: 'Return the single machine-readable desktop-agent alpha delivery audit with checks, coverage, blockers, verification evidence, safe claim, and final-submission boundaries.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'objective_audit',
    description: 'Return the active objective requirement-by-requirement completion audit with evidence, incomplete items, release gate status, and next actions.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'development_requirements',
    description: 'Return P0/P1/P2/Future development requirement levels, current completion, QYYJT current-version scope, and next focus.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'agent_tool_adapters',
    description: 'Return per-host desktop-agent tool adapter manifest with baseline tool sequence, installation_handoff install/start/smoke contract, execution_matrix done conditions, first_run_recipe preservation guards, host fallback order, smoke commands, required packet fields, report outputs, and current-release boundaries for Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, WorkBuddy, and Universal hosts.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'aggregate_subject',
    description: 'Run bounded subject-profile aggregation for a company, controller, or related entity and return relationship graph/profile details.',
    inputSchema: {
      type: 'object',
      properties: {
        subject_id: {
          type: 'string',
          description: 'Subject entity id to aggregate, such as company:demo_co or a known profile id.'
        },
        subject_name: {
          type: 'string',
          description: 'Optional readable subject name for report labels.'
        },
        max_depth: {
          type: 'number',
          description: 'Bounded association depth, clamped to 1..5.',
          default: 3
        }
      },
      required: ['subject_id']
    }
  },
  {
    name: 'load_skill',
    description: 'Load Wallstreet Tieling skill instructions and role system.',
    inputSchema: {
      type: 'object',
      properties: {
        brief: {
          type: 'boolean',
          description: 'Return a compact token-friendly version.',
          default: false
        }
      }
    }
  }
];

const server = new Server(
  { name: 'wallstreet-tieling', version: '0.5.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  switch (name) {
    case 'load_skill':
      return textContent(loadSkill(Boolean(args.brief)));
    case 'investigate_company':
    case 'due_diligence':
      return textContent(await runInvestigation(args));
    case 'people_investigation':
      return textContent(buildPeopleInvestigationBrief(args));
    case 'financial_analysis':
      return textContent(buildFinancialBrief(args));
    case 'anti_nominee_detection':
      return textContent(buildAntiNomineeBrief(args));
    case 'connector_catalog':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.connector_registry import ConnectorRegistry',
        'print(json.dumps(ConnectorRegistry().product_catalog(), ensure_ascii=False))'
      ].join('; ')]));
    case 'release_readiness':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.release_contract import release_readiness_brief',
        'print(json.dumps(release_readiness_brief(), ensure_ascii=False))'
      ].join('; ')]));
    case 'delivery_closure':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.release_contract import release_readiness_brief',
        'print(json.dumps(release_readiness_brief().get("delivery_closure", {}), ensure_ascii=False))'
      ].join('; ')]));
    case 'release_preflight':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.release_contract import release_preflight_brief',
        'print(json.dumps(release_preflight_brief(), ensure_ascii=False))'
      ].join('; ')]));
    case 'delivery_audit':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.release_contract import delivery_audit_brief',
        'print(json.dumps(delivery_audit_brief(), ensure_ascii=False))'
      ].join('; ')]));
    case 'objective_audit':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.release_contract import objective_completion_audit_brief',
        'print(json.dumps(objective_completion_audit_brief(), ensure_ascii=False))'
      ].join('; ')]));
    case 'development_requirements':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.development_requirements import build_development_requirements_board',
        'print(json.dumps(build_development_requirements_board(), ensure_ascii=False))'
      ].join('; ')]));
    case 'agent_tool_adapters':
      return textContent(await runPythonJson(['-c', [
        'import json',
        'from core.agent_tool_adapters import build_agent_tool_adapter_manifest',
        'print(json.dumps(build_agent_tool_adapter_manifest(), ensure_ascii=False))'
      ].join('; ')]));
    case 'aggregate_subject':
      return textContent(JSON.stringify(await runSubjectAggregation(args), null, 2));
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function runSubjectAggregation(args) {
  const subjectId = String(args.subject_id || '').trim();
  const subjectName = String(args.subject_name || args.subject_id || '').trim();
  const maxDepth = Math.min(Math.max(parseInt(args.max_depth, 10) || 3, 1), 5);
  if (!subjectId) throw new Error('subject_id is required');

  const code = [
    'import asyncio, json, sys',
    `sys.path.insert(0, ${JSON.stringify(process.cwd())})`,
    'from core.investigation import run_subject_profile_aggregation',
    `report = asyncio.run(run_subject_profile_aggregation(${JSON.stringify(subjectId)}, ${JSON.stringify(subjectName)}, max_depth=${maxDepth}))`,
    'print(json.dumps(report, ensure_ascii=False))'
  ].join('; ');
  return await runPythonJson(['-c', code]);
}

function textContent(text) {
  return {
    content: [{ type: 'text', text }]
  };
}

function loadSkill(brief) {
  if (!brief) {
    return skillContent;
  }
  return `${skillContent.substring(0, 3000)}\n\n[...compact load: request brief=false for the full skill...]`;
}

function resolveCompany(args) {
  const value = args.company_name || args.company || args.message || args.name || '';
  return String(value).trim();
}

async function runInvestigation(args) {
  const company = resolveCompany(args);
  if (!company) {
    throw new Error('company_name/company/message is required');
  }

  const script = path.join(ROOT, 'bin', 'investigate.py');
  const argv = [script, company];

  if (args.depth || args.mode) {
    argv.push('--mode', String(args.depth || args.mode));
  }
  if (args.config) {
    argv.push('--config', String(args.config));
  }
  if (args.offline_fixture === true) {
    argv.push('--offline-fixture');
  }
  if (args.fixture_pack === true) {
    argv.push('--fixture-pack');
  }
  if (args.official_public_smoke === true) {
    argv.push('--official-public-smoke');
  }
  if (args.store) {
    argv.push('--store', String(args.store));
  }
  if (args.retrieval_concurrency !== undefined) {
    argv.push('--retrieval-concurrency', String(args.retrieval_concurrency));
  }
  if (args.fanout_rounds !== undefined) {
    argv.push('--fanout-rounds', String(args.fanout_rounds));
  }
  if (args.max_fanout_tasks !== undefined) {
    argv.push('--max-fanout-tasks', String(args.max_fanout_tasks));
  }
  if (args.query_timeout_seconds !== undefined) {
    argv.push('--query-timeout-seconds', String(args.query_timeout_seconds));
  }

  const output = await runPython(argv, {
    cwd: ROOT,
    timeoutMs: Number(process.env.WST_MCP_TIMEOUT_MS || 120000)
  });
  const stdout = output.stdout.trim();
  if (!stdout) {
    return JSON.stringify({
      ok: false,
      error: 'investigate.py produced no output',
      stderr: output.stderr.trim()
    }, null, 2);
  }
  try {
    return JSON.stringify(JSON.parse(stdout), null, 2);
  } catch (error) {
    return stdout;
  }
}

async function runPython(argv, options) {
  const candidates = pythonCandidates();
  const failures = [];
  for (const candidate of candidates) {
    try {
      return await runProcess(candidate, argv, options);
    } catch (error) {
      failures.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(`No usable Python runtime found. Tried: ${failures.join(' | ')}`);
}

async function runPythonJson(argv) {
  const output = await runPython(argv, {
    cwd: ROOT,
    timeoutMs: Number(process.env.WST_MCP_TIMEOUT_MS || 120000)
  });
  const stdout = output.stdout.trim();
  if (!stdout) {
    return JSON.stringify({
      ok: false,
      error: 'python command produced no output',
      stderr: output.stderr.trim()
    }, null, 2);
  }
  return JSON.stringify(JSON.parse(stdout), null, 2);
}

function pythonCandidates() {
  const candidates = [
    process.env.WST_PYTHON,
    process.env.PYTHON,
    path.join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(ROOT, 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(
      os.homedir(),
      '.cache',
      'codex-runtimes',
      'codex-primary-runtime',
      'dependencies',
      'python',
      process.platform === 'win32' ? 'python.exe' : 'bin/python'
    ),
    'python3',
    'python',
    'py'
  ].filter(Boolean);
  return Array.from(new Set(candidates.map(String)));
}

function runProcess(command, argv, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, argv, {
      cwd: options.cwd,
      env: {
        ...process.env,
        PYTHONUTF8: '1'
      }
    });

    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`Timed out after ${options.timeoutMs}ms: ${command} ${argv.join(' ')}`));
    }, options.timeoutMs);

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8');
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8');
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(`Command failed with exit ${code}: ${stderr || stdout}`));
      }
    });
  });
}

function buildPeopleInvestigationBrief(args) {
  const name = String(args.name || '').trim();
  if (!name) {
    throw new Error('name is required');
  }
  return [
    `Person investigation target: ${name}`,
    `Known public/user-authorized identifier: ${args.known_public_identifier || 'not provided'}`,
    `Authorized context: ${args.authorized_context || 'not provided'}`,
    '',
    'Recommended execution path:',
    '1. Establish public identity and business relevance.',
    '2. Corroborate roles, investments, appointments, litigation, administrative records, public accounts, and related entities.',
    '3. Mark every claim with source, confidence, verification status, and sensitivity.',
    '4. Feed controller and relationship leads back into the company evidence graph.'
  ].join('\n');
}

function buildFinancialBrief(args) {
  const company = resolveCompany(args);
  if (!company) {
    throw new Error('company_name is required');
  }
  return [
    `Financial Intelligence Engine target: ${company}`,
    `Years: ${args.years || 3}`,
    '',
    'Core questions:',
    '- Why does this company make money?',
    '- Is profit converting into real cash?',
    '- Are receivables, inventory, capex, customer concentration, related-party transactions, or debt signals abnormal?',
    '- Can the company keep making money under the next industry cycle?'
  ].join('\n');
}

function buildAntiNomineeBrief(args) {
  const company = resolveCompany(args);
  if (!company) {
    throw new Error('company_name is required');
  }
  return [
    `Anti-nominee / UBO penetration target: ${company}`,
    '',
    'Evidence-first checklist:',
    '- Compare registry roles, shareholder paths, executive overlap, address reuse, contact reuse, project counterparties, and public statements.',
    '- Treat weak co-occurrence as leads, not verified facts.',
    '- Escalate controller candidates into recursive public/authorized subject profiling.',
    '- Preserve provenance and confidence for every relationship edge.'
  ].join('\n');
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Wallstreet Tieling MCP server started');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
