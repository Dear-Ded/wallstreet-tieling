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
const PYTHON = resolvePython();
const SMOKE_DIR = path.join(os.tmpdir(), 'wallstreet-tieling-agent-host-smoke');
fs.mkdirSync(SMOKE_DIR, { recursive: true });
const SMOKE_STORE = path.join(SMOKE_DIR, `risk-events-${process.pid}.jsonl`);
const WORKBUDDY_SMOKE_STORE = path.join(SMOKE_DIR, `workbuddy-risk-events-${process.pid}.jsonl`);
const CLI_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;

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
  return '';
}

const REQUIRED_VARIANTS = [
  'universal',
  'codex',
  'claude_code',
  'hermes',
  'doubao_office_task_mode',
  'open_claude_agents',
  'workbuddy_expert_team'
];

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

function runWorkBuddyCliFallback(label) {
  if (label !== 'workbuddy_investigate_company') {
    throw new Error(`${label} failed: python runtime unavailable`);
  }
  const packetText = runCliInProcess(
    [
      '--investigate',
      'Demo WorkBuddy Host Smoke Co., Ltd.',
      '--offline-fixture',
      '--store',
      WORKBUDDY_SMOKE_STORE
    ],
    `${label}_cli_fallback`
  );
  const packet = JSON.parse(packetText);
  return JSON.stringify({
    ok: packet.type === 'investigation_packet',
    sources: ['workbuddy:investigate_company', 'cli:offline_fixture_fallback'],
    type: packet.type,
    input: packet.input,
    has_quality_gate: Boolean(packet.quality_gate),
    evidence_count: (packet.evidence_ledger || []).length,
    has_qyyjt_handoff: packet.qyyjt_public_origin_handoff?.type === 'qyyjt_public_origin_handoff',
    has_decision_digest: packet.report_exports?.agent_decision_digest?.type === 'agent_decision_digest',
    fallback_reason: 'python_spawn_unavailable'
  });
}

function runPython(code, label) {
  if (!PYTHON) {
    return runWorkBuddyCliFallback(label);
  }
  const env = {
    ...process.env,
    PYTHONUTF8: '1',
    WST_PYTHON: PYTHON
  };
  const result = spawnSync(PYTHON, ['-c', code], {
    cwd: ROOT,
    env,
    encoding: 'utf-8',
    maxBuffer: CLI_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  if (result.error?.code === 'EPERM') {
    return runWorkBuddyCliFallback(label);
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

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const release = parseJson(run(['--release'], 'release_readiness'), 'release_readiness');
assert(release.type === 'release_readiness_brief', 'release_readiness type mismatch');
assert(release.contract.summary.variant_count === REQUIRED_VARIANTS.length, 'variant count mismatch');
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
  releasePreflight.required_preserved_fields?.includes('qyyjt_public_origin_handoff.agent_autorun') &&
    releasePreflight.required_preserved_fields?.includes('report_exports.directory_bundle.agent_handoff.report_artifact_autorun'),
  'release_preflight autorun preserved fields missing'
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
  release.runtime_delivery.source_health_operator_handoff?.recovery_queue_fields?.includes('operator_action'),
  'source health operator recovery fields missing'
);
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
const personaLaneFields = Object.fromEntries(
  release.persona_surface.runtime_lane_bindings.map((binding) => [
    binding.lane,
    new Set(binding.packet_fields),
  ])
);
assert(
  personaLaneFields.data_sources.has('one_click_readiness.operator_work_queue'),
  'persona data_sources operator work binding missing'
);
assert(
  personaLaneFields.data_sources.has('qyyjt_public_origin_handoff'),
  'persona data_sources qyyjt handoff binding missing'
);
assert(
  personaLaneFields.verification.has('one_click_readiness.reliance_limitations'),
  'persona verification reliance limitation binding missing'
);
assert(
  personaLaneFields.finance.has('one_click_readiness.capital_verification_top_step'),
  'persona finance capital verification binding missing'
);
assert(
  personaLaneFields.people.has('one_click_readiness.relationship_graph_audit_top_step'),
  'persona people relationship audit binding missing'
);

const connectors = parseJson(run(['--connectors'], 'connector_catalog'), 'connector_catalog');
assert(connectors.type === 'connector_catalog', 'connector_catalog type mismatch');
assert(connectors.summary.zero_config_ready.includes('default_public_intel'), 'default_public_intel missing');
assert(connectors.summary.data_effectiveness.fact_capable_sources >= 4, 'fact-capable source coverage missing');
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
assert(connectors.qyyjt_benchmark.summary.p0_queue_count >= 1, 'QYYJT P0 queue missing');
assert(
  connectors.qyyjt_benchmark.summary.public_origin_execution_summary.p0_count ===
    connectors.qyyjt_benchmark.summary.p0_queue_count,
  'QYYJT public-origin execution summary p0 count mismatch'
);
assert(
  connectors.qyyjt_benchmark.summary.public_origin_execution_summary.top_action.module === 'search_multi',
  'QYYJT public-origin execution top action missing'
);
assert(
  connectors.qyyjt_benchmark.summary.public_origin_execution_summary.report_section_batches.some(
    (item) => item.report_section === 'asset_solvency' && item.top_actions?.length >= 1
  ),
  'QYYJT public-origin asset solvency section batch missing'
);

const requirements = parseJson(run(['--requirements'], 'development_requirements'), 'development_requirements');
assert(requirements.type === 'development_requirements_board', 'development_requirements type mismatch');
assert(requirements.completion_percent >= 80, 'development completion unexpectedly low');
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
assert(agentTools.release_target === 'desktop_agent_alpha', 'agent_tool_adapters release target mismatch');
assert(agentTools.adapter_count === REQUIRED_VARIANTS.length, 'agent_tool_adapters adapter count mismatch');
assert(agentTools.all_current_release_ready === true, 'agent_tool_adapters current-release readiness mismatch');
assert(
  agentTools.installation_handoff?.type === 'desktop_agent_installation_handoff',
  'agent_tool_adapters installation handoff missing'
);
assert(
  agentTools.installation_handoff?.host_matrix?.length === REQUIRED_VARIANTS.length,
  'agent_tool_adapters installation host matrix mismatch'
);
assert(
    agentTools.installation_handoff?.default_mcp_command === 'npx -y wallstreet-tieling --mcp' &&
    agentTools.installation_handoff?.verification_commands?.includes('npm run agent:host-smoke') &&
    agentTools.installation_handoff?.verification_commands?.includes('npm run delivery:audit') &&
    agentTools.installation_handoff?.verification_commands?.includes('npm run objective:audit') &&
    agentTools.installation_handoff?.verification_commands?.includes('npm pack --dry-run --json'),
  'agent_tool_adapters installation verification commands missing'
);
assert(
  agentTools.installation_handoff?.required_local_runtime_env?.some((item) => item.includes('WST_PYTHON')) &&
    agentTools.installation_handoff?.required_local_runtime_env?.some((item) => item.includes('npm_config_cache')),
  'agent_tool_adapters installation runtime env guidance missing'
);
assert(
  agentTools.installation_handoff?.failure_routing?.some((item) => item.symptom === 'Python child process unavailable'),
  'agent_tool_adapters installation failure routing missing'
);
assert(
  agentTools.execution_matrix?.map((item) => item.phase).join('>') ===
    'release_gate>delivery_audit>source_catalog>priority_board>host_binding>investigation_run>followup_expansion',
  'agent_tool_adapters execution matrix phase order mismatch'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'delivery_audit')?.tool === 'delivery_audit',
  'agent_tool_adapters delivery audit matrix row missing'
);
assert(
  agentTools.shared_tools?.find((item) => item.name === 'connector_catalog')?.required_output_fields?.includes('groups.explicit_only') &&
    agentTools.shared_tools?.find((item) => item.name === 'connector_catalog')?.required_output_fields?.includes('connectors[].data_effectiveness'),
  'agent_tool_adapters connector_catalog advanced source fields missing'
);
assert(
  agentTools.shared_tools?.find((item) => item.name === 'connector_catalog')?.required_output_fields?.includes('source_strengthening_queue'),
  'agent_tool_adapters connector_catalog source strengthening field missing'
);
assert(
  agentTools.shared_tools?.find((item) => item.name === 'connector_catalog')?.required_output_fields?.includes('source_strengthening_queue[].execution_plan'),
  'agent_tool_adapters connector_catalog source strengthening execution plan field missing'
);
assert(
  agentTools.shared_tools?.find((item) => item.name === 'connector_catalog')?.required_output_fields?.includes('source_strengthening_queue[].runtime_companion'),
  'agent_tool_adapters connector_catalog source strengthening runtime companion field missing'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'source_catalog')?.required_fields?.includes('groups.explicit_only') &&
    agentTools.execution_matrix?.find((item) => item.phase === 'source_catalog')?.required_fields?.includes('connectors[].data_effectiveness'),
  'agent_tool_adapters source_catalog advanced source fields missing'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'source_catalog')?.required_fields?.includes('source_strengthening_queue'),
  'agent_tool_adapters source_catalog source strengthening field missing'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'source_catalog')?.required_fields?.includes('source_strengthening_queue[].execution_plan'),
  'agent_tool_adapters source_catalog source strengthening execution plan field missing'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'source_catalog')?.required_fields?.includes('source_strengthening_queue[].runtime_companion'),
  'agent_tool_adapters source_catalog source strengthening runtime companion field missing'
);
assert(
  agentTools.execution_matrix?.find((item) => item.phase === 'investigation_run')?.failure_routing?.includes('operator_work_queue'),
  'agent_tool_adapters investigation failure routing missing'
);
assert(
  agentTools.one_input_autorun_contract?.type === 'one_input_autorun_contract' &&
    agentTools.one_input_autorun_contract?.subject_input?.manual_intermediate_steps_required === false &&
    agentTools.one_input_autorun_contract?.subject_input?.accepted_fields?.includes('company_name') &&
    agentTools.one_input_autorun_contract?.autorun_sequence?.at(-1)?.step === 'investigate_company' &&
    agentTools.one_input_autorun_contract?.required_packet_fields?.includes('report_exports.directory_bundle.agent_handoff') &&
    agentTools.one_input_autorun_contract?.required_packet_fields?.includes('one_click_readiness.capital_risk_panel') &&
    agentTools.one_input_autorun_contract?.do_not?.some((item) => item.includes('extra clicks')),
  'agent_tool_adapters one-input autorun contract missing'
);
assert(
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.groups.explicit_only') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.connectors[].data_effectiveness') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].implementation_pack') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].execution_plan') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('connector_catalog.source_strengthening_queue[].runtime_companion') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.premium_html') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.portable_html.premium_profile') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_visibility') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.capital_risk_panel') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('qyyjt_public_origin_handoff.agent_autorun') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('report_exports.directory_bundle.agent_handoff.report_artifact_autorun') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('enterprise_cognition.relationship_resolution_v1') &&
    agentTools.first_run_recipe?.preserve_before_summarizing?.includes('enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue') &&
    agentTools.first_run_recipe?.do_not?.some((item) => item.includes('groups.explicit_only')) &&
    agentTools.first_run_recipe?.do_not?.some((item) => item.includes('source_strengthening_queue')) &&
    agentTools.first_run_recipe?.do_not?.some((item) => item.includes('prose-only')),
  'agent_tool_adapters first run recipe missing preservation or do-not guard'
);
assert(agentTools.default_host_id === 'codex', 'agent_tool_adapters default host id mismatch');
assert(agentTools.primary_host_id === 'codex', 'agent_tool_adapters primary host id mismatch');
assert(agentTools.host_priority_order?.[0] === 'codex', 'agent_tool_adapters must prioritize codex');
assert(agentTools.secondary_host_ids?.includes('workbuddy_expert_team'), 'agent_tool_adapters workbuddy secondary host missing');
assert(
  REQUIRED_VARIANTS.every((variant) => agentTools.adapter_lookup?.[variant]),
  'agent_tool_adapters adapter lookup missing host'
);
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
for (const variant of REQUIRED_VARIANTS) {
  const adapter = agentTools.adapters.find((item) => item.host_id === variant);
  assert(adapter, `agent adapter missing: ${variant}`);
  assert(adapter.current_release_supported === true, `agent adapter not current-release supported: ${variant}`);
  assert(adapter.install_handoff?.host_id === variant, `agent adapter install handoff missing: ${variant}`);
  assert(adapter.install_handoff?.config_files?.length >= 1, `agent adapter install config files missing: ${variant}`);
  assert(adapter.install_handoff?.smoke_command === adapter.smoke_command, `agent adapter install smoke mismatch: ${variant}`);
  assert(
    adapter.execution_matrix_ref === 'agent_tool_adapter_manifest.execution_matrix',
    `agent adapter execution matrix ref missing: ${variant}`
  );
  assert(
    JSON.stringify(adapter.tool_sequence) === JSON.stringify(['release_readiness', 'delivery_audit', 'connector_catalog', 'development_requirements', 'agent_tool_adapters', 'investigate_company']),
    `agent adapter tool sequence mismatch: ${variant}`
  );
  assert(adapter.fallback_order.length >= 3, `agent adapter fallback order too short: ${variant}`);
  assert(adapter.smoke_command, `agent adapter smoke command missing: ${variant}`);
  assert(
      adapter.required_packet_fields.includes('report_exports.agent_decision_digest') &&
      adapter.required_packet_fields.includes('report_exports.premium_html') &&
      adapter.required_packet_fields.includes('report_exports.portable_html.premium_profile') &&
      adapter.required_packet_fields.includes('enterprise_cognition.relationship_resolution_v1') &&
      adapter.required_packet_fields.includes('enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.verification_recipe') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.verifier_output_fields') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.report_visibility') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.capital_risk_panel') &&
      adapter.required_packet_fields.includes('report_exports.directory_bundle.agent_handoff.delivery_decision') &&
      adapter.report_outputs.includes('premium_html'),
    `agent adapter packet fields missing: ${variant}`
  );
}
assert(
  agentTools.required_smoke_commands.includes('npm run agent:host-smoke') &&
    agentTools.required_smoke_commands.includes('npm run codex:mcp-smoke') &&
    agentTools.required_smoke_commands.includes('npm run api:smoke'),
  'agent_tool_adapters required smoke commands missing'
);
const aggregateSubjectTool = agentTools.shared_tools.find((tool) => tool.name === 'aggregate_subject');
assert(aggregateSubjectTool, 'aggregate_subject shared tool missing');
assert(
  aggregateSubjectTool.cli?.includes('--aggregate-subject') &&
    aggregateSubjectTool.api === 'POST /api/aggregate' &&
    aggregateSubjectTool.mcp_tool === 'aggregate_subject',
  'aggregate_subject executable entrypoints missing'
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
  investigation.qyyjt_public_origin_handoff?.type === 'qyyjt_public_origin_handoff',
  'qyyjt_public_origin_handoff missing'
);
assert(
  Array.isArray(investigation.qyyjt_public_origin_handoff?.report_section_batches) &&
    investigation.qyyjt_public_origin_handoff.report_section_batches.length >= 1,
  'qyyjt_public_origin_handoff report_section_batches missing'
);
assert(
  Array.isArray(investigation.qyyjt_public_origin_handoff?.section_work_orders) &&
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
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'public_origin_top_action'),
  'one_click_readiness public_origin_top_action missing'
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
  typeof investigation.one_click_readiness.operator_work_queue_count === 'number',
  'one_click_readiness operator_work_queue_count missing'
);
assert(
  typeof investigation.one_click_readiness.operator_work_ready_count === 'number',
  'one_click_readiness operator_work_ready_count missing'
);
assert(
  Array.isArray(investigation.one_click_readiness.operator_work_queue),
  'one_click_readiness operator_work_queue missing'
);
assert(
  investigation.one_click_readiness.reliance_limitations?.type === 'reliance_limitations',
  'one_click_readiness reliance_limitations missing'
);
assert(
  typeof investigation.one_click_readiness.can_make_clean_conclusion === 'boolean',
  'one_click_readiness can_make_clean_conclusion missing'
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
  Object.prototype.hasOwnProperty.call(investigation.one_click_readiness, 'capital_relationship_next_action'),
  'one_click_readiness capital_relationship_next_action missing'
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
assert(typeof investigation.report_markdown === 'string', 'report_markdown missing');
assert(investigation.report_markdown.includes('0.5.0'), 'report_markdown lacks version header');
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
  investigation.report_exports.markdown?.content_field === 'report_markdown',
  'report_exports markdown contract missing'
);
assert(
  investigation.report_exports.future_formats?.docx_red_head === 'runtime_cli_renderer_available_via_export_docx',
  'report_exports docx runtime availability missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('relationship audit steps'),
  'report_exports portable_html relationship handoff card missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Agent decision digest'),
  'report_exports portable HTML decision digest missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Visual evidence panels'),
  'report_exports portable HTML visual evidence panels missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Source provenance appendix'),
  'report_exports portable HTML source appendix missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('Relationship and capital appendix'),
  'report_exports portable HTML relationship/capital appendix missing'
);
assert(
  investigation.report_exports.portable_html?.document?.includes('data-premium-html-report') &&
    investigation.report_exports.portable_html?.document?.includes('data-full-report-preserved') &&
    investigation.report_exports.portable_html?.document?.includes('Premium HTML visual QA checklist'),
  'report_exports portable HTML premium markers missing'
);
assert(
  investigation.report_exports.portable_html?.first_screen_handoff_card_count ===
    investigation.report_exports.print_package?.operational_handoff?.card_count,
  'report_exports portable_html first-screen handoff cards not synchronized'
);
assert(
  investigation.one_click_readiness?.acceptance_closure_summary?.type === 'acceptance_closure_summary',
  'one_click_readiness acceptance closure summary missing'
);
assert(
  Array.isArray(investigation.report_exports.portable_html?.first_screen_handoff_cards) &&
    investigation.report_exports.portable_html.first_screen_handoff_cards.length >= 1,
  'report_exports portable_html machine-readable handoff cards missing'
);
assert(
  investigation.report_exports.portable_html.first_screen_handoff_cards[0]?.id === 'acceptance_closure_summary',
  'report_exports portable HTML acceptance closure handoff card missing'
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
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.relationship_resolution_present') &&
    investigation.report_exports.directory_bundle?.verifier_output_fields?.includes('agent_handoff.capital_relationship_crosswalk_present'),
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
  'report_exports directory bundle agent_handoff delivery decision content missing'
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
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('image_evidence_inventory_items'),
  'report_exports docx image evidence capability missing'
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
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('operational_handoff_tables'),
  'report_exports docx operational handoff capability missing'
);
assert(
  investigation.report_exports.print_package?.operational_handoff?.card_count >= 1,
  'report_exports operational handoff cards missing'
);
assert(
  investigation.report_exports.print_package?.relationship_capital_appendix?.type === 'relationship_capital_appendix',
  'report_exports relationship/capital appendix missing'
);
assert(
  investigation.report_exports.print_package?.delivery_checklist?.quality_checks?.some(
    (row) => row.id === 'relationship_capital_appendix_present'
  ),
  'report_exports relationship/capital appendix delivery check missing'
);
assert(
  investigation.report_exports.print_package?.operational_handoff?.cards?.[0]?.id === 'acceptance_closure_summary',
  'report_exports operational handoff acceptance closure card missing'
);
assert(
  investigation.report_exports.print_package?.docx?.renderer_capabilities?.includes('native_word_tables'),
  'report_exports docx native Word table capability missing'
);
assert(investigation.monitoring_seed, 'monitoring_seed missing');
assert(
  investigation.monitoring_seed.current_release_monitoring_enabled === false,
  'monitoring must remain later-version only'
);
assert(
  investigation.monitoring_seed.source_health_trend_snapshot?.current_release_monitoring_enabled === false,
  'monitoring_seed source_health_trend_snapshot must not enable background monitoring'
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
  'source_health_trend_digest must not enable background monitoring'
);

const workbuddySmoke = parseJson(
  runPython(`
import asyncio, json
from adapters.workbuddy import WorkBuddyTools

async def main():
    result = await WorkBuddyTools().search(
        "",
        "investigate_company",
        company_name="Demo WorkBuddy Host Smoke Co., Ltd.",
        offline_fixture=True,
        store=${JSON.stringify(WORKBUDDY_SMOKE_STORE)}
    )
    print(json.dumps({
        "ok": result.ok,
        "sources": result.sources,
        "type": result.data.get("type"),
        "input": result.data.get("input"),
        "has_quality_gate": bool(result.data.get("quality_gate")),
        "evidence_count": len(result.data.get("evidence_ledger") or []),
        "has_qyyjt_handoff": result.data.get("qyyjt_public_origin_handoff", {}).get("type") == "qyyjt_public_origin_handoff",
        "has_decision_digest": result.data.get("report_exports", {}).get("agent_decision_digest", {}).get("type") == "agent_decision_digest",
    }, ensure_ascii=False))

asyncio.run(main())
  `,
  'workbuddy_investigate_company'
  ),
  'workbuddy_investigate_company'
);
assert(workbuddySmoke.ok === true, 'WorkBuddy investigate_company smoke failed');
assert(workbuddySmoke.type === 'investigation_packet', 'WorkBuddy packet type mismatch');
assert(workbuddySmoke.has_quality_gate === true, 'WorkBuddy quality gate missing');
assert(workbuddySmoke.evidence_count >= 1, 'WorkBuddy evidence ledger empty');
assert(workbuddySmoke.has_qyyjt_handoff === true, 'WorkBuddy QYYJT handoff missing');
assert(workbuddySmoke.has_decision_digest === true, 'WorkBuddy agent decision digest missing');
assert(
  Array.isArray(workbuddySmoke.sources) && workbuddySmoke.sources.includes('workbuddy:investigate_company'),
  'WorkBuddy smoke source marker missing'
);

console.log(JSON.stringify({
  ok: true,
  checked: [
    'release_readiness',
    'delivery_closure',
    'release_preflight',
    'delivery_audit',
    'objective_audit',
    'connector_catalog',
    'development_requirements',
    'agent_tool_adapters',
    'investigate_company',
    'workbuddy_investigate_company'
  ],
  variants: REQUIRED_VARIANTS,
  version: release.version
}, null, 2));
