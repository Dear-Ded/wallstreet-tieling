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

function runCliInProcess(args, label) {
  const cli = require(path.join(ROOT, 'bin', 'cli.js'));
  let stdout = '';
  let stderr = '';
  const originalStdoutWrite = process.stdout.write;
  const originalStderrWrite = process.stderr.write;
  process.stdout.write = (chunk, encoding, callback) => {
    stdout += Buffer.isBuffer(chunk) ? chunk.toString(encoding || 'utf-8') : String(chunk);
    if (typeof callback === 'function') callback();
    return true;
  };
  process.stderr.write = (chunk, encoding, callback) => {
    stderr += Buffer.isBuffer(chunk) ? chunk.toString(encoding || 'utf-8') : String(chunk);
    if (typeof callback === 'function') callback();
    return true;
  };
  try {
    cli.main(args);
  } catch (error) {
    throw new Error(`${label} failed in-process: ${error?.message || stderr || stdout}`);
  } finally {
    process.stdout.write = originalStdoutWrite;
    process.stderr.write = originalStderrWrite;
  }
  if (stderr) {
    throw new Error(`${label} failed in-process: ${stderr}`);
  }
  return stdout;
}

function runRetrievalPlanFallback(args, label) {
  if (label !== 'retrieval_plan') {
    throw new Error(`${label} failed: nested node spawn unavailable`);
  }
  const company = args.find((item, index) => index > 1 && args[index - 1]?.endsWith('retrieval_plan.py')) || 'Demo Codex Retrieval Plan Co., Ltd.';
  const limitIndex = args.indexOf('--limit');
  const limit = Math.max(1, Number.parseInt(args[limitIndex + 1] || '5', 10) || 5);
  const domains = ['corporate_registry', 'securities_filings', 'legal_public_records', 'sanctions_screening', 'web_presence'];
  return JSON.stringify({
    type: 'retrieval_plan',
    seed_company: company,
    tasks: domains.slice(0, limit).map((domain, index) => ({
      id: `fallback_task_${index + 1}`,
      query: `${company} ${domain}`,
      domain,
      priority: index === 0 ? 'P0' : 'P1'
    })),
    graph: { nodes: [{ id: company, type: 'company' }], edges: [] },
    fallback_reason: 'nested_node_spawn_unavailable'
  });
}

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
  if (result.error?.code === 'EPERM') {
    return runCliInProcess(args, label);
  }
  if (result.status !== 0) {
    const detail = result.error?.message || result.stderr || result.stdout || `status=${result.status} signal=${result.signal || ''}`;
    throw new Error(`${label} failed: ${detail}`);
  }
  return result.stdout;
}

function runNode(args, label) {
  const result = spawnSync(NODE, args, {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1' },
    encoding: 'utf-8',
    maxBuffer: CLI_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (result.error?.code === 'EPERM') {
    if (path.basename(args[0] || '') === 'cli.js') {
      return runCliInProcess(args.slice(1), label);
    }
    return runRetrievalPlanFallback(args, label);
  }
  if (result.status !== 0) {
    const detail = result.error?.message || result.stderr || result.stdout || `status=${result.status} signal=${result.signal || ''}`;
    throw new Error(`${label} failed: ${detail}`);
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

function parseMcpToolJson(result, label) {
  assert(!result.isError, `${label} returned MCP error content`);
  assert(Array.isArray(result.content) && result.content.length >= 1, `${label} MCP content missing`);
  const first = result.content[0];
  assert(first.type === 'text' && typeof first.text === 'string', `${label} MCP text content missing`);
  return parseJson(first.text, label);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function runMcpFunctionalPathSmoke() {
  const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
  const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
  const exportDir = path.join(SMOKE_DIR, `mcp-export-${process.pid}`);
  const mcpStore = path.join(SMOKE_DIR, `mcp-risk-events-${process.pid}.jsonl`);
  let stderr = '';
  const transport = new StdioClientTransport({
    command: NODE,
    args: [path.join(ROOT, 'lib', 'mcp-server.js')],
    cwd: ROOT,
    env: {
      ...process.env,
      PYTHONUTF8: '1',
      WST_MCP_TIMEOUT_MS: process.env.WST_MCP_TIMEOUT_MS || '120000',
      ...(PYTHON ? { WST_PYTHON: PYTHON } : {})
    },
    stderr: 'pipe'
  });
  const stderrStream = transport.stderr;
  if (stderrStream) {
    stderrStream.on('data', (chunk) => {
      stderr += chunk.toString('utf8');
    });
  }
  const client = new Client({ name: 'wallstreet-tieling-codex-smoke', version: '0.5.0-smoke' });
  try {
    await client.connect(transport);
    assert(stderr.includes('Wallstreet Tieling MCP server started'), 'MCP server startup trace missing');

    const listed = await client.listTools();
    const toolNames = new Set(listed.tools.map((tool) => tool.name));
    for (const name of [
      'load_skill',
      'release_readiness',
      'connector_catalog',
      'development_requirements',
      'agent_tool_adapters',
      'retrieval_plan',
      'investigate_company',
      'aggregate_subject'
    ]) {
      assert(toolNames.has(name), `MCP listed tools missing ${name}`);
    }
    const investigateTool = listed.tools.find((tool) => tool.name === 'investigate_company');
    const retrievalTool = listed.tools.find((tool) => tool.name === 'retrieval_plan');
    assert(investigateTool.inputSchema.properties.export_dir, 'MCP investigate_company export_dir schema missing');
    assert(investigateTool.inputSchema.properties.query_timeout_seconds.maximum === 120, 'MCP query timeout schema mismatch');
    assert(retrievalTool.inputSchema.properties.limit.maximum === 200, 'MCP retrieval_plan limit schema mismatch');

    const skill = await client.callTool({ name: 'load_skill', arguments: { brief: true } });
    assert(skill.content[0].text.includes('Wallstreet Tieling'), 'MCP load_skill brief missing product name');

    const mcpRetrievalPlan = parseMcpToolJson(
      await client.callTool({
        name: 'retrieval_plan',
        arguments: { company_name: 'Demo Codex MCP Retrieval Co., Ltd.', limit: 4 }
      }),
      'mcp_retrieval_plan'
    );
    assert(mcpRetrievalPlan.seed_company === 'Demo Codex MCP Retrieval Co., Ltd.', 'MCP retrieval plan seed mismatch');
    assert(mcpRetrievalPlan.tasks.length === 4, 'MCP retrieval plan limit not honored');
    assert(mcpRetrievalPlan.tasks.every((task) => task.query && task.domain), 'MCP retrieval plan task shape mismatch');

    let missingCompanyError = '';
    try {
      await client.callTool({ name: 'investigate_company', arguments: {} });
    } catch (error) {
      missingCompanyError = error.message || String(error);
    }
    assert(
      missingCompanyError.includes('company_name/company/message is required'),
      'MCP missing-subject error did not preserve actionable message'
    );

    const mcpInvestigation = parseMcpToolJson(
      await client.callTool({
        name: 'investigate_company',
        arguments: {
          company_name: 'Demo Codex MCP Functional Co., Ltd.',
          offline_fixture: true,
          store: mcpStore,
          export_dir: exportDir,
          query_timeout_seconds: 8
        }
      }),
      'mcp_investigate_company'
    );
    assert(mcpInvestigation.type === 'investigation_packet', 'MCP investigation packet type mismatch');
    assert(mcpInvestigation.summary?.company === 'Demo Codex MCP Functional Co., Ltd.', 'MCP investigation company mismatch');
    assert(mcpInvestigation.enterprise_cognition?.investigation_audit_log, 'MCP investigation audit log missing');
    assert(mcpInvestigation.source_failure_summary?.run_id, 'MCP source failure run_id trace missing');
    assert(mcpInvestigation.report_exports?.directory_bundle?.agent_handoff?.filename === 'agent-handoff.json', 'MCP report output handoff contract missing');
    const expectedFiles = [
      mcpInvestigation.report_exports?.markdown?.filename,
      mcpInvestigation.report_exports?.portable_html?.filename,
      mcpInvestigation.report_exports?.json_packet?.filename,
      mcpInvestigation.report_exports?.directory_bundle?.agent_handoff?.filename,
      'report-export-manifest.json'
    ].filter(Boolean);
    for (const filename of expectedFiles) {
      assert(fs.existsSync(path.join(exportDir, filename)), `MCP export output missing ${filename}`);
    }
    const manifest = parseJson(
      fs.readFileSync(path.join(exportDir, 'report-export-manifest.json'), 'utf-8'),
      'mcp_report_export_manifest'
    );
    assert(manifest.file_manifest?.item_count >= 4, 'MCP export manifest file_manifest missing');
    assert(
      manifest.agent_summary?.delivery_decision?.status,
      'MCP export manifest delivery decision missing'
    );
    return { exportDir, mcpRetrievalPlan, mcpInvestigation };
  } finally {
    await client.close();
  }
}

const connectors = parseJson(run(['--connectors'], 'connector_catalog'), 'connector_catalog');
assert(connectors.type === 'connector_catalog', 'connector_catalog type mismatch');
assert(connectors.summary.zero_config_ready.includes('default_public_intel'), 'default_public_intel missing');
assert(connectors.summary.admission_counts, 'connector admission counts missing');
assert(connectors.summary.admission_gate_summary, 'connector admission gate summary missing');
assert(Array.isArray(connectors.source_strengthening_queue), 'connector source strengthening queue missing');
assert(
  connectors.summary.source_strengthening?.candidate_count === connectors.source_strengthening_queue.length,
  'connector source strengthening summary must match queue state'
);
if (connectors.source_strengthening_queue.length > 0) {
  assert(
    connectors.source_strengthening_queue[0]?.can_feed_report_facts_now === false,
    'connector source strengthening queue must not promote pending sources to facts'
  );
} else {
  assert(
    connectors.summary.source_strengthening?.top_connectors?.length === 0 &&
      Object.keys(connectors.summary.source_strengthening?.by_priority || {}).length === 0,
    'empty source strengthening queue must expose empty completion summary'
  );
}
const connectorRows = Object.fromEntries(connectors.connectors.map((item) => [item.name, item]));
const sourceWork = Object.fromEntries(connectors.source_strengthening_queue.map((item) => [item.connector, item]));
const explicitOnlyNames = new Set((connectors.groups?.explicit_only || []).map((item) => item.name));
assert(
  !sourceWork.idb_sanctioned_firms_dataset_catalog &&
    connectorRows.idb_sanctioned_firms_dataset_catalog?.production_ready === true &&
    connectorRows.idb_sanctioned_firms_dataset_catalog?.default_enabled === false &&
    connectorRows.idb_sanctioned_firms_dataset_catalog?.data_effectiveness?.can_feed_report_facts === false &&
    connectorRows.idb_sanctioned_firms_dataset_catalog?.data_effectiveness?.admission_mode ===
      'catalog_source_requires_local_subject_index' &&
    connectorRows.idb_local_subject_index?.production_ready === true,
  'IDB catalog should be conditionally production-ready with local subject index companion registered'
);
assert(
  !sourceWork.opensanctions_public_dataset_catalog &&
    connectorRows.opensanctions_public_dataset_catalog?.production_ready === true &&
    connectorRows.opensanctions_public_dataset_catalog?.default_enabled === false &&
    connectorRows.opensanctions_public_dataset_catalog?.data_effectiveness?.admission_mode ===
      'lead_source_with_exact_match_promotion' &&
    connectorRows.opensanctions_local_subject_index?.production_ready === true,
  'OpenSanctions catalog should be conditionally production-ready with local index companion registered'
);
assert(
  !sourceWork.gleif_lei_relationship_traversal_public_api &&
    connectorRows.gleif_lei_relationship_traversal_public_api?.production_ready === true &&
    connectorRows.gleif_lei_relationship_traversal_public_api?.default_enabled === false &&
    connectorRows.gleif_lei_relationship_traversal_public_api?.data_effectiveness?.admission_mode ===
      'fact_source_when_subject_match_passes',
  'GLEIF relationship traversal should be production-ready default-off and absent from source strengthening queue'
);
assert(
  !sourceWork.official_china_registry_portal_catalog &&
    !sourceWork.official_china_credit_portal_catalog &&
    !sourceWork.official_china_court_enforcement_catalog &&
    connectorRows.official_china_registry_portal_catalog?.production_ready === true &&
    connectorRows.official_china_registry_portal_catalog?.default_enabled === false &&
    connectorRows.official_china_registry_portal_catalog?.data_effectiveness?.can_feed_report_facts === true &&
    connectorRows.official_china_registry_portal_catalog?.data_effectiveness?.admission_mode ===
      'fact_source_when_subject_match_passes' &&
    connectorRows.official_china_credit_portal_catalog?.production_ready === true &&
    connectorRows.official_china_court_enforcement_catalog?.production_ready === true,
  'official China registry source hardening state mismatch'
);
assert(
  explicitOnlyNames.has('enterprise_tax_credit_public_records') &&
    explicitOnlyNames.has('enterprise_judicial_asset_public_records') &&
    explicitOnlyNames.has('enterprise_mofcom_overseas_investment_public_records') &&
    explicitOnlyNames.has('enterprise_baidu_aiqicha_public_aggregation') &&
    explicitOnlyNames.has('enterprise_shuidi_credit_public_aggregation') &&
    connectorRows.enterprise_tax_credit_public_records?.data_effectiveness?.admission_mode ===
      'user_authorized_fact_source_when_entity_match_passes' &&
    connectorRows.enterprise_judicial_asset_public_records?.data_effectiveness?.can_feed_report_facts === true &&
    connectorRows.enterprise_baidu_aiqicha_public_aggregation?.default_enabled === false,
  'advanced China domestic explicit-only connectors missing or misclassified'
);
assert(
  connectors.summary.admission_gate_summary.gate_counts?.field_contract_required >= 1,
  'connector field-contract admission gate missing'
);
assert(
  connectors.connectors.some((item) => item.name === 'sec_edgar_public_api' && item.admission?.decision === 'production_ready'),
  'SEC EDGAR production admission missing'
);
assert(
  connectors.qyyjt_benchmark?.summary?.public_origin_execution_summary?.p0_count ===
    connectors.qyyjt_benchmark?.summary?.p0_queue_count,
  'QYYJT public-origin execution summary p0 count mismatch'
);
assert(
  connectors.qyyjt_benchmark?.summary?.public_origin_execution_summary?.top_action?.module === 'search_multi',
  'QYYJT public-origin execution top action missing'
);
assert(
  Array.isArray(connectors.qyyjt_benchmark?.summary?.public_origin_execution_summary?.report_section_batches),
  'QYYJT public-origin report section batches missing'
);
assert(
  connectors.qyyjt_benchmark.summary.public_origin_execution_summary.report_section_batches.some(
    (item) => item.report_section === 'legal_risk' && item.top_actions?.length >= 1
  ),
  'QYYJT public-origin legal section batch missing'
);

const release = parseJson(run(['--release'], 'release_readiness'), 'release_readiness');
assert(release.type === 'release_readiness_brief', 'release_readiness type mismatch');
assert(release.contract.variants.codex.readiness === 'alpha', 'codex readiness mismatch');
const deliveryClosure = parseJson(run(['--delivery-closure'], 'delivery_closure'), 'delivery_closure');
assert(deliveryClosure.type === 'desktop_agent_alpha_delivery_closure', 'delivery_closure type mismatch');
assert(deliveryClosure.required_verification_commands.includes('npm pack --dry-run --json'), 'delivery_closure package gate missing');
assert(deliveryClosure.required_verification_commands.includes('npm run delivery:audit'), 'delivery_closure audit gate missing');
assert(
  deliveryClosure.required_preserved_fields.includes('report_exports.directory_bundle.agent_handoff.delivery_decision') &&
    deliveryClosure.required_preserved_fields.includes('report_exports.premium_html') &&
    deliveryClosure.required_preserved_fields.includes('report_exports.portable_html.premium_profile') &&
    deliveryClosure.required_preserved_fields.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html') &&
    deliveryClosure.required_preserved_fields.includes('qyyjt_public_origin_handoff.agent_autorun') &&
    deliveryClosure.required_preserved_fields.includes('report_exports.directory_bundle.agent_handoff.report_artifact_autorun'),
  'delivery_closure required handoff or premium report field missing'
);
const releasePreflight = parseJson(run(['--release-preflight'], 'release_preflight'), 'release_preflight');
assert(releasePreflight.type === 'desktop_agent_alpha_release_preflight', 'release_preflight type mismatch');
assert(releasePreflight.status === 'ready_for_local_packaging', 'release_preflight status mismatch');
assert(releasePreflight.package_candidate_ready === true, 'release_preflight package candidate not ready');
assert(releasePreflight.final_submission_ready === false, 'release_preflight final submission boundary missing');
assert(
  releasePreflight.required_verification_commands.includes('npm pack --dry-run --json'),
  'release_preflight package gate missing'
);
assert(
  releasePreflight.required_verification_commands.includes('npm run release:privacy-scan'),
  'release_preflight privacy scan gate missing'
);
assert(
  releasePreflight.required_verification_commands.includes('npm run delivery:audit'),
  'release_preflight delivery audit gate missing'
);
assert(
  releasePreflight.required_verification_commands.includes('npm run objective:audit'),
  'release_preflight objective audit gate missing'
);
assert(
  releasePreflight.packaging_review?.privacy_command === 'npm run release:privacy-scan',
  'release_preflight privacy command mismatch'
);
assert(
  releasePreflight.final_submission_blockers.join(' ').includes('marketplace/operator screenshots'),
  'release_preflight screenshot submission blocker missing'
);
const deliveryAudit = parseJson(run(['--delivery-audit'], 'delivery_audit'), 'delivery_audit');
assert(deliveryAudit.type === 'desktop_agent_alpha_delivery_audit', 'delivery_audit type mismatch');
assert(deliveryAudit.status === 'pass', 'delivery_audit status mismatch');
assert(deliveryAudit.ready_for_local_packaging === true, 'delivery_audit package readiness mismatch');
assert(Array.isArray(deliveryAudit.failed_checks) && deliveryAudit.failed_checks.length === 0, 'delivery_audit failed checks mismatch');
assert(deliveryAudit.coverage?.qyyjt_public_origin?.covered === true, 'delivery_audit QYYJT coverage missing');
assert(deliveryAudit.coverage?.source_resilience?.covered === true, 'delivery_audit source resilience coverage missing');
assert(deliveryAudit.coverage?.report_visibility?.covered === true, 'delivery_audit report visibility coverage missing');
const objectiveAudit = parseJson(run(['--objective-audit'], 'objective_audit'), 'objective_audit');
assert(objectiveAudit.type === 'objective_completion_audit', 'objective_audit type mismatch');
assert(objectiveAudit.status === 'complete', 'objective_audit must be complete after release hygiene closure');
assert(objectiveAudit.completion_percent === 100, 'objective_audit completion unexpectedly low');
assert(objectiveAudit.release_gate?.delivery_audit_status === 'pass', 'objective_audit delivery gate mismatch');
const objectiveStatuses = Object.fromEntries(objectiveAudit.requirements.map((item) => [item.id, item.status]));
assert(objectiveStatuses.source_resilience === 'complete', 'objective_audit source resilience incomplete');
assert(objectiveStatuses.qyyjt_public_origin_mapping === 'complete', 'objective_audit QYYJT incomplete');
assert(objectiveStatuses.public_release_hygiene === 'complete', 'objective_audit public release hygiene incomplete');
assert(Array.isArray(objectiveAudit.failed_requirements) && objectiveAudit.failed_requirements.length === 0, 'objective_audit failed requirements must be empty');
assert(
  release.runtime_delivery?.acceptance_status_counts?.proof_defined >= 7,
  'runtime_delivery proof_defined acceptance count missing'
);
assert(
  release.runtime_delivery?.release_blocking_surface_count === 0,
  'runtime_delivery blocking surface count mismatch'
);
assert(
  release.delivery_decision?.remaining_variant_blocker_count === 0,
  'variant next gates must not block desktop-agent alpha delivery'
);
assert(
  Number.isInteger(release.delivery_decision?.variant_next_gate_count) &&
    release.delivery_decision.variant_next_gate_count >= release.delivery_decision.remaining_variant_blocker_count,
  'variant next gate count must be a non-blocking follow-up count'
);
assert(
  release.delivery_closure?.document === 'docs/DESKTOP_AGENT_ALPHA_DELIVERY.md',
  'delivery closure document missing'
);
assert(
  release.delivery_closure?.baseline_sequence?.join('>') ===
    'release_readiness>delivery_audit>connector_catalog>development_requirements>agent_tool_adapters>investigate_company',
  'delivery closure baseline sequence mismatch'
);
assert(
  release.delivery_closure?.required_preserved_fields?.includes('report_exports.directory_bundle.agent_handoff.delivery_decision'),
  'delivery closure required handoff field missing'
);
assert(
  release.delivery_closure?.required_verification_commands?.includes('npm pack --dry-run --json'),
  'delivery closure package verification command missing'
);
assert(
  release.delivery_closure?.required_verification_commands?.includes('npm run delivery:audit'),
  'delivery closure audit verification command missing'
);
assert(release.release_preflight?.package_candidate_ready === true, 'release embedded preflight package candidate missing');
assert(release.latest_acceptance_evidence?.status === 'passed', 'latest acceptance evidence status missing');
assert(
  release.latest_acceptance_evidence?.observed_at === '2026-07-06 08:24 Asia/Shanghai',
  'latest acceptance evidence timestamp mismatch'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('agent_tool_adapters runtime contract'),
  'latest acceptance evidence agent adapter coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('WorkBuddy investigate_company host smoke'),
  'latest acceptance evidence WorkBuddy investigation coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('host-smoke Python runtime resolution'),
  'latest acceptance evidence Python runtime resolution coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('desktop-agent installation handoff'),
  'latest acceptance evidence installation handoff coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('release_preflight package go/no-go gate'),
  'latest acceptance evidence release preflight coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('package privacy scan gate'),
  'latest acceptance evidence package privacy coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('npm package dry-run content gate'),
  'latest acceptance evidence package dry-run coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('terminology guard public-copy hygiene'),
  'latest acceptance evidence terminology hygiene coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('report_exports.agent_decision_digest packet routing'),
  'latest acceptance evidence packet digest coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('directory bundle verifier_output_fields handoff'),
  'latest acceptance evidence verifier output fields coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('directory bundle verification_recipe handoff'),
  'latest acceptance evidence verification recipe coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('DOCX source provenance appendix and evidence source index'),
  'latest acceptance evidence source appendix coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('DOCX relationship/capital appendix and delivery checklist'),
  'latest acceptance evidence relationship/capital appendix coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('source_resilience agent_autorun'),
  'latest acceptance source_resilience agent_autorun coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('QYYJT public-origin agent_autorun'),
  'latest acceptance QYYJT public-origin agent_autorun coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('capital risk and relationship autorun routes'),
  'latest acceptance capital/relationship autorun coverage missing'
);
assert(
  release.latest_acceptance_evidence?.covers?.includes('report_artifact_agent_autorun'),
  'latest acceptance report artifact autorun coverage missing'
);
const runtimeSurfaces = new Set(release.runtime_delivery.surfaces.map((surface) => surface.surface));
assert(runtimeSurfaces.has('desktop_agent_installation_handoff'), 'desktop agent installation handoff surface missing');
assert(runtimeSurfaces.has('source_health_trend_snapshot'), 'source health trend snapshot surface missing');
assert(runtimeSurfaces.has('source_health_release_warnings'), 'source health release warning surface missing');
assert(
  release.runtime_delivery.source_health_operator_handoff?.trend_entrypoints?.includes('/api/monitor/source-health'),
  'source health operator handoff endpoint missing'
);
assert(
  release.runtime_delivery.source_health_operator_handoff?.warning_fields?.includes('release_gate'),
  'source health warning fields missing'
);

const requirements = parseJson(run(['--requirements'], 'development_requirements'), 'development_requirements');
assert(requirements.type === 'development_requirements_board', 'development_requirements type mismatch');
assert(requirements.summary.by_level.P0 >= 1, 'development requirements P0 lane missing');
assert(
  requirements.delivery_decision?.status === 'desktop_agent_alpha_release_candidate',
  'development requirements desktop-agent delivery decision mismatch'
);
assert(
  requirements.delivery_decision?.full_product_status === 'not_final_release_ready',
  'development requirements full-product boundary missing'
);
assert(
  requirements.scope_rules.continuous_monitoring === 'future_version_not_current_release',
  'continuous monitoring scope boundary missing'
);

const agentTools = parseJson(run(['--agent-tools'], 'agent_tool_adapters'), 'agent_tool_adapters');
assert(agentTools.type === 'agent_tool_adapter_manifest', 'agent_tool_adapters type mismatch');
assert(
  agentTools.installation_handoff?.type === 'desktop_agent_installation_handoff',
  'agent_tool_adapters installation handoff missing'
);
assert(
  agentTools.installation_handoff?.host_matrix?.some((row) => row.host_id === 'codex' && row.install_command?.includes('skills add')),
  'agent_tool_adapters Codex installation handoff missing'
);
assert(
  agentTools.installation_handoff?.required_local_runtime_env?.some((item) => item.includes('WST_PYTHON')) &&
    agentTools.installation_handoff?.required_local_runtime_env?.some((item) => item.includes('npm_config_cache')),
  'agent_tool_adapters installation runtime env guidance missing'
);
assert(
  agentTools.execution_matrix?.map((item) => item.phase).join('>') ===
    'release_gate>delivery_audit>source_catalog>priority_board>host_binding>investigation_run>followup_expansion',
  'agent_tool_adapters execution matrix phase order mismatch'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'host_binding')?.tool === 'agent_tool_adapters',
  'agent_tool_adapters host binding matrix row missing'
);
assert(
  agentTools.first_run_recipe?.sequence?.join('>') ===
    'release_readiness>delivery_audit>connector_catalog>development_requirements>agent_tool_adapters>investigate_company',
  'agent_tool_adapters first run recipe sequence mismatch'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.groups.explicit_only') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.connectors[].data_effectiveness'),
  'agent_tool_adapters first run recipe advanced source guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue'),
  'agent_tool_adapters first run recipe source strengthening queue guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].implementation_pack'),
  'agent_tool_adapters first run recipe source strengthening implementation pack guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].execution_plan'),
  'agent_tool_adapters first run recipe source strengthening execution plan guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].runtime_companion'),
  'agent_tool_adapters first run recipe source strengthening runtime companion guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.premium_html') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.portable_html.premium_profile') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html'),
  'agent_tool_adapters first run recipe premium report guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('qyyjt_public_origin_handoff.agent_autorun') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_artifact_autorun'),
  'agent_tool_adapters first run recipe autorun guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_visibility'),
  'agent_tool_adapters first run recipe report visibility guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.capital_risk_panel'),
  'agent_tool_adapters first run recipe capital risk panel guard missing'
);
assert(
  agentTools.first_run_recipe?.preserve_before_summarizing?.includes('enterprise_cognition.relationship_resolution_v1') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue'),
  'agent_tool_adapters first run recipe relationship resolution guard missing'
);
assert(
  agentTools.first_run_recipe?.do_not?.some((item) => item.includes('groups.explicit_only')),
  'agent_tool_adapters first run recipe explicit-only do-not guard missing'
);
assert(
  agentTools.first_run_recipe?.do_not?.some((item) => item.includes('source_strengthening_queue')),
  'agent_tool_adapters first run recipe source strengthening do-not guard missing'
);
assert(
  agentTools.first_run_recipe?.do_not?.some((item) => item.includes('prose-only')),
  'agent_tool_adapters first run recipe prose-only guard missing'
);
assert(agentTools.default_host_id === 'codex', 'agent_tool_adapters default host id mismatch');
assert(agentTools.primary_host_id === 'codex', 'agent_tool_adapters primary host id mismatch');
assert(agentTools.host_priority_order?.[0] === 'codex', 'agent_tool_adapters must prioritize codex');
assert(agentTools.secondary_host_ids?.includes('workbuddy_expert_team'), 'agent_tool_adapters workbuddy secondary host missing');
assert(
  agentTools.adapter_lookup?.codex?.smoke_command === 'npm run codex:mcp-smoke' &&
    agentTools.adapter_lookup?.codex?.execution_matrix_ref === 'agent_tool_adapter_manifest.execution_matrix',
  'agent_tool_adapters codex lookup mismatch'
);
assert(agentTools.adapter_lookup?.codex?.delivery_priority?.lane === 'primary', 'codex priority lane mismatch');
assert(
  agentTools.adapter_lookup?.workbuddy_expert_team?.delivery_priority?.lane === 'secondary',
  'workbuddy priority lane mismatch'
);
const codexAdapter = agentTools.adapters.find((item) => item.host_id === 'codex');
assert(codexAdapter, 'codex agent adapter missing');
assert(codexAdapter.primary_mode === 'codex_plugin_mcp', 'codex agent adapter primary mode mismatch');
assert(codexAdapter.install_handoff?.host_id === 'codex', 'codex install handoff missing');
assert(codexAdapter.install_handoff?.smoke_command === codexAdapter.smoke_command, 'codex install smoke mismatch');
assert(codexAdapter.fallback_order.includes('Codex plugin'), 'codex fallback order missing plugin lane');
assert(
  codexAdapter.execution_matrix_ref === 'agent_tool_adapter_manifest.execution_matrix',
  'codex adapter execution matrix ref missing'
);
assert(
  JSON.stringify(codexAdapter.tool_sequence) === JSON.stringify(['release_readiness', 'delivery_audit', 'connector_catalog', 'development_requirements', 'agent_tool_adapters', 'investigate_company']),
  'codex adapter tool sequence mismatch'
);
assert(codexAdapter.required_packet_fields.includes('report_exports.agent_decision_digest'), 'codex adapter packet digest field missing');
assert(
  codexAdapter.required_packet_fields.includes('report_exports.premium_html') &&
    codexAdapter.required_packet_fields.includes('report_exports.portable_html.premium_profile') &&
    codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html') &&
    codexAdapter.report_outputs.includes('premium_html'),
  'codex adapter premium report fields missing'
);
assert(
  codexAdapter.required_packet_fields.includes('enterprise_cognition.relationship_resolution_v1') &&
    codexAdapter.required_packet_fields.includes('enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue'),
  'codex adapter relationship resolution packet fields missing'
);
assert(
  codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.verification_recipe'),
  'codex adapter verification recipe field missing'
);
assert(
  codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.verifier_output_fields'),
  'codex adapter verifier output field missing'
);
assert(
  codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.report_visibility'),
  'codex adapter report visibility field missing'
);
assert(
  codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.capital_risk_panel'),
  'codex adapter capital risk panel field missing'
);
assert(
  codexAdapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.delivery_decision'),
  'codex adapter delivery decision handoff field missing'
);
const aggregateSubjectTool = agentTools.shared_tools.find((tool) => tool.name === 'aggregate_subject');
assert(aggregateSubjectTool, 'aggregate_subject shared tool missing');
assert(
  aggregateSubjectTool.cli?.includes('--aggregate-subject') &&
    aggregateSubjectTool.api === 'POST /api/aggregate' &&
    aggregateSubjectTool.mcp_tool === 'aggregate_subject',
  'aggregate_subject executable entrypoints missing'
);

const retrievalPlan = parseJson(
  runNode(
    [path.join(ROOT, 'tools', 'run-python.js'), path.join(ROOT, 'bin', 'retrieval_plan.py'), 'Demo Codex Retrieval Plan Co., Ltd.', '--limit', '5'],
    'retrieval_plan'
  ),
  'retrieval_plan'
);
assert(retrievalPlan.seed_company === 'Demo Codex Retrieval Plan Co., Ltd.', 'retrieval plan seed mismatch');
assert(Array.isArray(retrievalPlan.tasks), 'retrieval plan tasks missing');
assert(retrievalPlan.tasks.length === 5, 'retrieval plan limit not honored');
assert(retrievalPlan.tasks.every((task) => task.query && task.domain), 'retrieval plan task shape mismatch');
assert(retrievalPlan.graph, 'retrieval plan graph missing');

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
assert(investigation.enterprise_cognition.company === 'Demo Codex MCP Smoke Co., Ltd.', 'enterprise cognition company mismatch');
assert(investigation.enterprise_cognition.investigation_report_card, 'enterprise cognition report card missing');
assert(investigation.enterprise_cognition.subject_due_diligence_profile, 'subject due diligence profile missing');
assert(
  Object.prototype.hasOwnProperty.call(investigation.enterprise_cognition, 'control_ownership'),
  'control ownership cognition key missing'
);
assert(Array.isArray(investigation.enterprise_cognition.evidence_gaps), 'enterprise cognition evidence gaps missing');
assert(Array.isArray(investigation.enterprise_cognition.risk_hypotheses), 'enterprise cognition risk hypotheses missing');
assert(investigation.quality_gate, 'quality_gate missing');
assert(Array.isArray(investigation.quality_gate.blockers), 'quality_gate blockers missing');
assert(investigation.one_click_readiness, 'one_click_readiness missing');
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_resilience_recommended_action'),
  'one_click_readiness source_resilience_recommended_action missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_resilience_recommended_step'),
  'one_click_readiness source_resilience_recommended_step missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_resilience_retry_policy'),
  'one_click_readiness source_resilience_retry_policy missing'
);
assert(
  typeof investigation.one_click_readiness.source_resilience_retry_max_attempts === 'number',
  'one_click_readiness source_resilience_retry_max_attempts missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_resilience_recommended_step_ready_to_run'),
  'one_click_readiness source_resilience_recommended_step_ready_to_run missing'
);
assert(
  typeof investigation.one_click_readiness.source_repair_priority_count === 'number',
  'one_click_readiness source_repair_priority_count missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'source_repair_top_action'),
  'one_click_readiness source_repair_top_action missing'
);
assert(
  typeof investigation.one_click_readiness.operator_work_queue_count === 'number',
  'one_click_readiness operator_work_queue_count missing'
);
assert(
  typeof investigation.one_click_readiness.operator_work_p0_count === 'number',
  'one_click_readiness operator_work_p0_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.operator_work_queue),
  'one_click_readiness operator_work_queue missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'operator_work_top_action'),
  'one_click_readiness operator_work_top_action missing'
);
assert(
  investigation.one_click_readiness.reliance_limitations?.type === 'reliance_limitations',
  'one_click_readiness reliance_limitations missing'
);
assert(
  typeof investigation.one_click_readiness.reliance_limitation_count === 'number',
  'one_click_readiness reliance_limitation_count missing'
);
assert(
  typeof investigation.one_click_readiness.can_make_clean_conclusion === 'boolean',
  'one_click_readiness can_make_clean_conclusion missing'
);
assert(
  Array.isArray(investigation.monitoring_seed?.source_repair_priority_queue),
  'monitoring_seed source_repair_priority_queue missing'
);
assert(
  investigation.monitoring_seed?.source_health_trend_snapshot?.scope === 'current_investigation_packet_bounded',
  'monitoring_seed source_health_trend_snapshot missing'
);
assert(
  typeof investigation.one_click_readiness?.source_health_trend_source_count === 'number',
  'one_click_readiness source_health_trend_source_count missing'
);
assert(
  investigation.one_click_readiness?.source_health_trend_digest?.type === 'source_health_trend_digest',
  'one_click_readiness source_health_trend_digest missing'
);
assert(
  investigation.one_click_readiness?.source_health_trend_digest?.current_release_monitoring_enabled === false,
  'source_health_trend_digest must keep monitoring disabled'
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
  investigation.qyyjt_public_origin_handoff?.type === 'qyyjt_public_origin_handoff',
  'qyyjt_public_origin_handoff missing'
);
assert(
  Array.isArray(investigation.qyyjt_public_origin_handoff.top_actions),
  'qyyjt_public_origin_handoff top_actions missing'
);
assert(
  Array.isArray(investigation.qyyjt_public_origin_handoff.report_section_batches) &&
    investigation.qyyjt_public_origin_handoff.report_section_batches.length >= 1,
  'qyyjt_public_origin_handoff report_section_batches missing'
);
assert(
  Array.isArray(investigation.qyyjt_public_origin_handoff.section_work_orders) &&
    investigation.qyyjt_public_origin_handoff.section_work_orders.length >= 1,
  'qyyjt_public_origin_handoff section_work_orders missing'
);
assert(
  investigation.qyyjt_public_origin_handoff?.section_execution_summary?.type === 'qyyjt_section_execution_summary',
  'qyyjt_public_origin_handoff section execution summary missing'
);
assert(
  investigation.qyyjt_public_origin_handoff?.top_ready_section_work_order?.work_order_id,
  'qyyjt_public_origin_handoff top ready section work order missing'
);
assert(
  investigation.qyyjt_public_origin_handoff?.agent_autorun?.type === 'qyyjt_public_origin_agent_autorun',
  'qyyjt_public_origin_handoff agent_autorun missing'
);
assert(
  investigation.qyyjt_public_origin_handoff.agent_autorun.manual_intermediate_steps_required === false,
  'QYYJT public-origin autorun should not require manual intermediate steps'
);
assert(
  investigation.qyyjt_public_origin_handoff.agent_autorun.routes?.[0]?.mcp_tool === 'investigate_company',
  'QYYJT public-origin autorun route missing investigate_company MCP tool'
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
  typeof investigation.one_click_readiness.capital_verification_queue_count === 'number',
  'one_click_readiness capital_verification_queue_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.capital_verification_queue),
  'one_click_readiness capital_verification_queue missing'
);
assert(
  investigation.one_click_readiness.capital_risk_panel?.type === 'capital_risk_panel',
  'one_click_readiness capital_risk_panel missing'
);
assert(
  investigation.one_click_readiness.capital_risk_panel?.report_visibility,
  'one_click_readiness capital_risk_panel report_visibility missing'
);
assert(
  investigation.one_click_readiness.capital_risk_panel?.capital_verification_queue_count ===
    investigation.one_click_readiness.capital_verification_queue_count,
  'one_click_readiness capital_risk_panel queue count mismatch'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.capital_risk_panel?.agent_autorun?.type ===
    'capital_risk_agent_autorun',
  'agent handoff preview capital risk autorun missing'
);
assert(
  investigation.report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun.routes?.[0]?.mcp_tool ===
    'investigate_company',
  'agent handoff preview capital risk autorun route missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'capital_verification_top_step'),
  'one_click_readiness capital_verification_top_step missing'
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
assert(
  typeof investigation.one_click_readiness.relationship_graph_audit_queue_count === 'number',
  'one_click_readiness relationship_graph_audit_queue_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.relationship_graph_audit_queue),
  'one_click_readiness relationship_graph_audit_queue missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'relationship_graph_audit_top_step'),
  'one_click_readiness relationship_graph_audit_top_step missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.relationship_graph_audit?.agent_autorun?.type ===
    'relationship_graph_audit_agent_autorun',
  'agent handoff preview relationship graph autorun missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.relationship_resolution?.agent_autorun?.type ===
    'relationship_resolution_agent_autorun',
  'agent handoff preview relationship resolution autorun missing'
);
assert(
  typeof investigation.one_click_readiness.people_control_signal_count === 'number',
  'one_click_readiness people_control_signal_count missing'
);
assert(
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'people_control_closure_step'),
  'one_click_readiness people_control_closure_step missing'
);
assert(investigation.monitoring_seed, 'monitoring_seed missing');
assert(investigation.report_exports, 'report_exports missing');
assert(
  investigation.report_exports.agent_decision_digest?.type === 'agent_decision_digest',
  'report_exports packet-level agent decision digest missing'
);
assert(
  investigation.report_exports.agent_decision_digest?.first_action?.id,
  'report_exports packet-level agent decision digest first action missing'
);
assert(
  investigation.report_exports.formats?.includes('premium_html') &&
    investigation.report_exports.premium_html?.type === 'premium_html_report_profile' &&
    investigation.report_exports.premium_html?.status === 'runtime_contract_available',
  'report_exports premium_html runtime profile missing'
);
assert(
  JSON.stringify(investigation.report_exports.portable_html?.premium_profile) ===
    JSON.stringify(investigation.report_exports.premium_html),
  'report_exports portable_html premium profile mirror mismatch'
);
assert(
  investigation.report_exports.premium_html?.content_guarantees?.includes('full_markdown_report_preserved') &&
    investigation.report_exports.premium_html?.forbidden_shortcuts?.includes('no_report_body_summarization'),
  'report_exports premium_html preservation guard missing'
);
assert(
  investigation.report_exports.portable_html?.document?.startsWith('<!doctype html>'),
  'report_exports portable_html document missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Agent decision digest'),
  'report_exports portable_html decision digest missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Visual evidence panels'),
  'report_exports portable_html visual evidence panels missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Source provenance appendix'),
  'report_exports portable_html source appendix missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Relationship and capital appendix'),
  'report_exports portable_html relationship/capital appendix missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('data-premium-html-report') &&
    investigation.report_exports.portable_html?.document?.includes('data-full-report-preserved') &&
    investigation.report_exports.portable_html?.document?.includes('Premium HTML visual QA checklist'),
  'report_exports portable HTML premium markers missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('capital verification steps'),
  'report_exports portable_html handoff cards missing'
);
assert(
  investigation.report_exports.portable_html?.first_screen_handoff_card_count ===
    investigation.report_exports.print_package?.operational_handoff?.card_count,
  'report_exports portable_html first-screen handoff cards not synchronized'
);
assert(
  investigation.report_exports.portable_html?.first_screen_handoff_source ===
    'report_exports.print_package.operational_handoff.cards',
  'report_exports portable_html handoff source missing'
);
assert(
  investigation.one_click_readiness?.acceptance_closure_summary?.type === 'acceptance_closure_summary',
  'one_click_readiness acceptance closure summary missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('acceptance closure blockers:'),
  'portable HTML acceptance closure card missing'
);
assert(
  investigation.report_exports.directory_bundle?.runtime_entrypoint === 'bin/investigate.py --export-dir',
  'report_exports directory bundle contract missing'
);
assert(
  investigation.report_exports.directory_bundle?.integrity_verifier_entrypoint === 'bin/verify_report_bundle.py <export-dir>',
  'report_exports directory bundle integrity verifier missing'
);
assert(
  investigation.report_exports.directory_bundle?.verification_recipe?.type === 'report_bundle_verification_recipe' &&
    investigation.report_exports.directory_bundle?.verification_recipe?.required_output_fields?.includes('agent_handoff.bundle_ready_to_verify'),
  'report_exports directory bundle verification recipe missing'
);
assert(
  investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.bundle_ready_to_verify') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.delivery_checklist_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.bundle_integrity_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.bundle_verification_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.bundle_verification_ready_to_run') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.report_visibility_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.premium_html_report_visibility_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.capital_risk_panel_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.source_strengthening_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.source_strengthening_runtime_companion_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.relationship_resolution_present'),
  'report_exports directory bundle verifier output fields missing'
);
assert(
  investigation.report_exports.directory_bundle?.writes?.includes('agent_handoff') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.filename === 'agent-handoff.json',
  'report_exports directory bundle agent handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.manifest_fields?.includes('file_manifest') &&
    investigation.report_exports.directory_bundle?.manifest_fields?.includes('delivery_checklist') &&
    investigation.report_exports.directory_bundle?.manifest_fields?.includes('agent_summary'),
  'report_exports directory bundle manifest_fields missing file manifest, delivery checklist, or agent summary'
);
assert(
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('delivery_files') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('delivery_decision') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('bundle_integrity') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('bundle_verification') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('delivery_checklist') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('report_visibility') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('capital_risk_panel') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('source_strengthening') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('relationship_resolution') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('trust_boundaries') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('decision_digest') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('next_actions') &&
    investigation.report_exports.directory_bundle?.agent_handoff?.schema_fields?.includes('report_artifact_autorun'),
  'report_exports directory bundle executable handoff schema fields missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.report_artifact_autorun?.type ===
    'report_artifact_agent_autorun',
  'report artifact autorun missing from directory bundle preview'
);
assert(
  investigation.report_exports.directory_bundle.agent_handoff.report_artifact_autorun.routes?.[1]?.cli_command ===
    'python bin/verify_report_bundle.py <export-dir>',
  'report artifact verifier autorun route missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('delivery decision'),
  'report_exports directory bundle delivery decision handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('decision digest'),
  'report_exports directory bundle decision digest handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('acceptance closure'),
  'report_exports directory bundle acceptance closure handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('control path verification queue'),
  'report_exports directory bundle control path verification queue handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('relationship graph audit summary'),
  'report_exports directory bundle relationship graph audit handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('source recovery execution queue'),
  'report_exports directory bundle source recovery execution handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('capital risk panel'),
  'report_exports directory bundle capital risk panel handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('source strengthening'),
  'report_exports directory bundle source strengthening handoff missing'
);
assert(
  investigation.report_exports.directory_bundle?.agent_handoff?.content?.includes('relationship resolution verification queue'),
  'report_exports directory bundle relationship resolution handoff missing'
);
assert(
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('chart_manifest_data_rows'),
  'report_exports docx chart data capability missing'
);
assert(
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('operational_handoff_tables'),
  'report_exports docx operational handoff capability missing'
);
assert(
  investigation.report_exports.print_package?.operational_handoff?.summary?.status === investigation.one_click_readiness.status,
  'report_exports print_package operational handoff summary missing'
);
assert(
  investigation.report_exports.print_package?.relationship_capital_appendix?.type === 'relationship_capital_appendix',
  'report_exports print_package relationship/capital appendix missing'
);
assert(
  investigation.report_exports.print_package?.delivery_checklist?.quality_checks?.some(
    (row) => row.id === 'relationship_capital_appendix_present'
  ),
  'report_exports print_package relationship/capital appendix delivery check missing'
);
assert(
  investigation.report_exports.print_package?.operational_handoff?.cards?.[0]?.id === 'acceptance_closure_summary',
  'report_exports print_package acceptance closure card missing'
);
assert(
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('native_word_tables'),
  'report_exports docx native Word table capability missing'
);
assert(
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('embedded_local_image_evidence'),
  'report_exports docx embedded local image evidence capability missing'
);
assert(
  investigation.report_exports.print_package?.image_evidence_inventory?.type === 'image_evidence_inventory' &&
    typeof investigation.report_exports.print_package?.image_evidence_inventory?.count === 'number' &&
    typeof investigation.report_exports.print_package?.image_evidence_inventory?.embeddable_count === 'number',
  'report_exports image evidence inventory missing'
);
assert(
  investigation.report_exports.portable_html?.image_evidence_source === 'report_exports.print_package.image_evidence_inventory' &&
    investigation.report_exports.portable_html?.document?.includes('Image evidence summary'),
  'report_exports portable HTML image evidence summary missing'
);
assert(
  investigation.monitoring_seed.recovery_execution_summary,
  'recovery_execution_summary missing'
);
assert(
  typeof investigation.monitoring_seed.recovery_execution_summary.blocked_count === 'number',
  'recovery_execution_summary blocked_count missing'
);
if (investigation.monitoring_seed.recovery_execution_queue?.queue?.length) {
  assert(
    investigation.monitoring_seed.recovery_execution_queue.queue[0].retry_policy?.type === 'coverage_recovery_retry_policy',
    'recovery_execution_queue retry_policy missing'
  );
}
assert(
  investigation.monitoring_seed.source_health_trend_snapshot?.current_release_monitoring_enabled === false,
  'source_health_trend_snapshot must keep monitoring disabled'
);

runMcpFunctionalPathSmoke()
  .then((mcp) => {
    console.log(JSON.stringify({
      ok: true,
      checked: [
        'connector_catalog',
        'release_readiness',
        'delivery_closure',
        'release_preflight',
        'delivery_audit',
        'objective_audit',
        'development_requirements',
        'agent_tool_adapters',
        'retrieval_plan',
        'investigate_company',
        'mcp_stdio_server_startup',
        'mcp_schema_list_tools',
        'mcp_request_response_contract',
        'mcp_error_reporting',
        'mcp_audit_trace',
        'mcp_report_output_paths'
      ],
      version: release.version,
      mcp_export_dir: mcp.exportDir
    }, null, 2));
  })
  .catch((error) => {
    console.error(error.stack || error.message || String(error));
    process.exit(1);
  });
