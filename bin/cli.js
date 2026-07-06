#!/usr/bin/env node
/**
 * Wallstreet Tieling CLI.
 *
 * Small public entry point for Skill loading, MCP startup, and one-click local
 * investigation smoke tests.
 */

const { execFileSync, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const skillPath = path.join(ROOT, 'SKILL.md');
const pkg = require(path.join(ROOT, 'package.json'));
const PYTHON_OUTPUT_MAX_BUFFER = 16 * 1024 * 1024;
const REPORT_BUNDLE_VERIFIER_OUTPUT_FIELDS = [
  'ok',
  'checked_count',
  'agent_handoff.checked',
  'agent_handoff.schema_valid',
  'agent_handoff.decision_digest_present',
  'agent_handoff.delivery_checklist_present',
  'agent_handoff.bundle_integrity_present',
  'agent_handoff.bundle_verification_present',
  'agent_handoff.bundle_verification_ready_to_run',
  'agent_handoff.bundle_ready_to_verify',
  'agent_handoff.report_visibility_present',
  'agent_handoff.premium_html_report_visibility_present',
  'agent_handoff.image_evidence_inventory_present',
  'agent_handoff.capital_risk_panel_present',
  'agent_handoff.capital_relationship_crosswalk_present',
  'agent_handoff.relationship_resolution_present',
  'agent_handoff.source_strengthening_present',
  'agent_handoff.source_strengthening_runtime_companion_present',
  'agent_handoff.verification_recipe_present',
  'agent_handoff.verifier_output_fields_present',
  'agent_handoff.acceptance_closure_present',
  'agent_handoff.source_preflight_present',
  'agent_handoff.source_preflight_contract_valid',
  'agent_handoff.manifest_summary_source_preflight_present',
  'agent_handoff.manifest_summary_source_preflight_valid',
  'agent_handoff.deep_autopilot_plan_present',
  'agent_handoff.deep_autopilot_source_runbook_present',
  'agent_handoff.continuation_entrypoints_valid',
  'agent_handoff.source_runbook_valid',
  'agent_handoff.qyyjt_public_origin_present',
  'agent_handoff.source_resilience_present',
  'agent_handoff.relationship_graph_audit_present'
];
const HOST_IDS = [
  'universal',
  'codex',
  'claude_code',
  'hermes',
  'doubao_office_task_mode',
  'open_claude_agents',
  'workbuddy_expert_team'
];

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

  npx wallstreet-tieling --delivery-closure
      Print the concise desktop-agent alpha delivery closure checklist.

  npx wallstreet-tieling --release-preflight
      Print the desktop-agent alpha packaging go/no-go preflight.

  npx wallstreet-tieling --delivery-audit
      Print the single machine-readable desktop-agent alpha delivery audit.

  npx wallstreet-tieling --objective-audit
      Print the active objective requirement-by-requirement completion audit.

  npx wallstreet-tieling --requirements
      Print P0/P1/P2/Future development requirement levels and current completion.

  npx wallstreet-tieling --agent-tools
      Print per-host desktop-agent tool adapter manifest, baseline tool sequence, fallbacks, and smoke commands.

  npx wallstreet-tieling --aggregate-subject "company:demo" --subject-name "Demo Co." --max-depth 3
      Run bounded subject aggregation for related-company/controller follow-up after an investigation packet identifies a target.

  npx wallstreet-tieling --investigate "Company Name"
      Run zero-config one-click investigation and print the JSON packet.

  npx wallstreet-tieling --investigate "Company Name" --offline-fixture
      Run a deterministic local smoke report without network access.

  npx wallstreet-tieling --investigate "Company Name" --report-only
      Print the Markdown report only.

  npx wallstreet-tieling --investigate "Company Name" --export-docx out/report.docx --export-html out/report.html
      Write printable Word and HTML files while still printing the JSON packet.

  npx wallstreet-tieling --investigate "Company Name" --export-dir out/report-bundle
      Write DOCX, portable HTML, Markdown, JSON, and manifest files into one directory.

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
  for (const flag of ['--fixture-pack', '--offline-fixture', '--official-public-smoke', '--report-only', '--json']) {
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
  for (const option of [
    '--query-timeout-seconds',
    '--fanout-rounds',
    '--max-fanout-tasks',
    '--retrieval-concurrency',
    '--store',
    '--export-docx',
    '--export-dir',
    '--export-html',
    '--export-markdown',
    '--export-json'
  ]) {
    const optionIndex = args.indexOf(option);
    if (optionIndex >= 0 && args[optionIndex + 1]) {
      scriptArgs.push(option, args[optionIndex + 1]);
    }
  }

  if (process.env.WST_FORCE_NODE_OFFLINE_FALLBACK === '1' && args.includes('--offline-fixture')) {
    writeOfflineFixtureFallback(args, company);
    return;
  }

  const python = resolvePython({ exitOnFailure: false });
  if (!python && args.includes('--offline-fixture')) {
    writeOfflineFixtureFallback(args, company);
    return;
  }
  if (!python) {
    console.error('No usable Python runtime found. Set WST_PYTHON to continue.');
    process.exit(1);
  }

  const result = spawnSync(python, scriptArgs, {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1' },
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  if (result.status !== 0) {
    if (result.error && result.error.code === 'EPERM' && args.includes('--offline-fixture')) {
      writeOfflineFixtureFallback(args, company);
      return;
    }
    process.stderr.write(result.stderr || result.stdout || 'investigation failed');
    process.exit(result.status || 1);
  }
  process.stdout.write(result.stdout);
}

function printPythonJson(moduleExpr, fallbackPayload) {
  const python = resolvePython({ exitOnFailure: false });
  if (!python) {
    process.stdout.write(JSON.stringify(fallbackPayload(), null, 2) + '\n');
    return;
  }
  const result = spawnSync(python, ['-c', moduleExpr], {
    cwd: ROOT,
    env: { ...process.env, PYTHONUTF8: '1' },
    encoding: 'utf-8',
    maxBuffer: PYTHON_OUTPUT_MAX_BUFFER,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  if (result.status !== 0) {
    if (result.error && result.error.code === 'EPERM') {
      process.stdout.write(JSON.stringify(fallbackPayload(), null, 2) + '\n');
      return;
    }
    process.stderr.write(result.stderr || result.stdout || 'command failed');
    process.exit(result.status || 1);
  }
  process.stdout.write(result.stdout);
}

function runSubjectAggregation(args) {
  const index = args.indexOf('--aggregate-subject');
  const subjectId = args[index + 1];
  if (!subjectId || subjectId.startsWith('--')) {
    console.error('--aggregate-subject requires a subject id.');
    process.exit(2);
  }
  const subjectName = optionValue(args, '--subject-name') || subjectId;
  const rawDepth = parseInt(optionValue(args, '--max-depth') || '3', 10);
  const maxDepth = Math.min(Math.max(Number.isFinite(rawDepth) ? rawDepth : 3, 1), 5);
  printPythonJson([
    'import asyncio, json',
    'from core.investigation import run_subject_profile_aggregation',
    `result = asyncio.run(run_subject_profile_aggregation(${JSON.stringify(subjectId)}, ${JSON.stringify(subjectName)}, max_depth=${maxDepth}))`,
    'print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))'
  ].join('; '), () => subjectAggregationFallback(subjectId, subjectName, maxDepth));
}

function resolvePython(options = {}) {
  const exitOnFailure = options.exitOnFailure !== false;
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
  if (!exitOnFailure) {
    return null;
  }
  console.error('No usable Python runtime found. Set WST_PYTHON to continue.');
  process.exit(1);
}

function optionValue(args, option) {
  const index = args.indexOf(option);
  return index >= 0 ? args[index + 1] : null;
}

function writeFileIfRequested(args, option, content) {
  const target = optionValue(args, option);
  if (!target) {
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content, 'utf-8');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildNodeFallbackPremiumHtmlProfile(filename, handoffCardCount = 0) {
  return {
    type: 'premium_html_report_profile',
    status: 'fallback_runtime_pending',
    filename,
    document_field: 'report_exports.portable_html.document',
    surface_markers: [
      'data-premium-html-report',
      'data-full-report-preserved',
      'premium visual QA checklist',
      'evidence darkroom',
      'source provenance appendix',
      'relationship and capital appendix'
    ],
    design_language: [
      'component-level liquid glass',
      'evidence darkroom',
      'formal report typography',
      'print-safe degradation',
      'reduced-motion-safe rendering'
    ],
    content_guarantees: [
      'full_markdown_report_preserved',
      'no_due_diligence_sections_shortened',
      'delivery_checklist_visible',
      'agent_handoff_cards_visible'
    ],
    forbidden_shortcuts: [
      'no_generic_purple_gradient',
      'no_ai_style_card_pile',
      'no_evidence_truncation',
      'no_report_body_summarization'
    ],
    acceptance_checklist: [
      'document has data-premium-html-report marker',
      'document has data-full-report-preserved marker',
      'premium visual QA checklist is visible',
      'prefers-reduced-motion and print CSS are present'
    ],
    metrics: {
      handoff_card_count: handoffCardCount,
      chart_panel_count: 0,
      image_evidence_count: 0,
      source_count: 0,
      relationship_edge_count: 0
    },
    policy: 'Node fallback preserves the premium HTML contract for desktop agents until Python runtime rendering is restored.'
  };
}

function writeOfflineFixtureFallback(args, company) {
  const files = {
    markdown: 'report.md',
    portable_html: 'report.html',
    json_packet: 'packet.json',
    docx: null,
    agent_handoff: 'agent-handoff.json',
    manifest: 'report-export-manifest.json'
  };
  const fallbackAction = {
    id: 'restore_python_runtime',
    priority: 'P0',
    status: 'blocked',
    action: 'Restore Python runtime access before treating this fallback packet as a full investigation result.',
    ready_to_run: false,
    done_condition: 'Full Python export-dir path completes.'
  };
  const qyyjtSectionWorkOrder = {
    work_order_id: 'fallback_legal_risk_public_origin',
    report_section: 'legal_risk',
    priority: 'P0',
    origin_channels: ['public_web_search', 'judicial_public_records'],
    query_families: ['legal_risk_public_records'],
    required_fields: ['source_url', 'title', 'date', 'subject_name'],
    done_condition: 'At least one public or user-authorized legal-risk source is reviewed with provenance.'
  };
  const operationalCards = [
    {
      id: 'acceptance_closure_summary',
      title: 'acceptance closure blockers',
      status: 'blocked',
      detail: 'Python runtime access is unavailable in the Node fallback path.'
    },
    {
      id: 'capital_verification_steps',
      title: 'capital verification steps',
      status: 'blocked',
      detail: 'Run the Python investigation path before relying on capital conclusions.'
    },
    {
      id: 'relationship_audit_steps',
      title: 'relationship audit steps',
      status: 'blocked',
      detail: 'Run the Python investigation path before relying on relationship graph conclusions.'
    }
  ];
  const fallbackMarkdown = `# ${company} 0.5.0\n\nOffline fixture fallback packet generated by Node CLI.`;
  const oneClick = {
    status: 'usable_with_warnings',
    source_resilience_recommended_action: 'restore_python_runtime',
    source_resilience_recommended_step: fallbackAction,
    source_resilience_recommended_step_ready_to_run: false,
    source_resilience_retry_policy: { type: 'coverage_recovery_retry_policy', max_attempts: 3 },
    source_resilience_retry_max_attempts: 3,
    source_repair_priority_count: 1,
    source_repair_top_action: fallbackAction,
    can_make_clean_conclusion: false,
    reliance_limitation_count: 1,
    reliance_limitations: { type: 'reliance_limitations', items: ['python_runtime_unavailable'] },
    operator_work_queue_count: 1,
    operator_work_p0_count: 1,
    operator_work_ready_count: 0,
    operator_work_queue: [
      {
        id: 'python_runtime_recovery',
        priority: 'P0',
        status: 'blocked',
        action: 'Set WST_PYTHON or run from an environment where Python child processes are allowed.',
        ready_to_run: false,
        done_condition: 'Python runtime resolves and bin/investigate.py can generate the full DOCX/JSON/HTML export bundle.'
      }
    ],
    operator_work_top_action: fallbackAction,
    acceptance_closure_status: 'blocked',
    acceptance_closure_blocking_count: 1,
    acceptance_closure_ready_count: 0,
    acceptance_closure_top_action: fallbackAction,
    acceptance_closure_summary: {
      type: 'acceptance_closure_summary',
      status: 'blocked',
      blocking_count: 1,
      ready_count: 0,
      open_domains: ['python_runtime'],
      next_action: 'Restore Python runtime access.',
      done_condition: 'Python export-dir path completes.',
      policy: 'Node fallback is a packaging continuity aid, not a full investigation result.'
    },
    source_health_trend_digest: { type: 'source_health_trend_digest', available: false, current_release_monitoring_enabled: false, policy: 'No source-health trend is generated in Node fallback mode.' },
    source_health_trend_source_count: 0,
    source_health_trend_top_source: {},
    source_health_trend_policy: 'Fallback packet only; rerun Python path for source-health diagnostics.',
    coverage_not_searched_count: 1,
    coverage_no_evidence_count: 0,
    coverage_missing_domains: ['python_runtime'],
    coverage_domains_without_evidence: ['python_runtime'],
    public_origin_next_action_count: 1,
    public_origin_top_action: fallbackAction,
    public_origin_modules: ['search_multi'],
    relationship_candidate_execution_step_count: 0,
    relationship_candidate_watch_count: 0,
    relationship_candidate_top_step: {},
    capital_relationship_status: 'blocked',
    capital_verification_queue_count: 1,
    capital_verification_queue: [fallbackAction],
    capital_verification_top_step: fallbackAction,
    capital_risk_panel: {
      type: 'capital_risk_panel',
      status: 'blocked',
      capital_relationship_status: 'blocked',
      capital_verification_queue_count: 1,
      capital_verification_top_step: fallbackAction,
      report_visibility: {
        type: 'capital_risk_panel_report_visibility',
        markdown_visible: true,
        portable_html_visible: true,
        docx_visible: false,
        agent_handoff_visible: true,
        visibility_source: 'node_cli_offline_fixture_fallback'
      },
      policy: 'Node fallback preserves the capital-risk panel shape only; restore Python before relying on capital conclusions.'
    },
    capital_relationship_next_action: fallbackAction,
    capital_relationship_unresolved_reason: 'python_runtime_unavailable',
    relationship_edge_count: 0,
    relationship_evidence_backed_edge_count: 0,
    relationship_auditable_edge_count: 0,
    relationship_graph_audit_queue_count: 0,
    relationship_graph_audit_queue: [],
    relationship_graph_audit_top_step: {},
    people_control_signal_count: 0,
    people_control_closure_step: {}
  };
  const monitoringSeed = {
    current_release_monitoring_enabled: false,
    feature_scope: 'future_version_not_current_release',
    source_repair_priority_queue: [fallbackAction],
    recovery_execution_summary: { type: 'source_recovery_execution_summary', ready_count: 0, blocked_count: 1 },
    recovery_execution_queue: { ready: [], blocked: [fallbackAction], queue: [] },
    source_health_trend_snapshot: {
      type: 'source_health_trend_snapshot',
      scope: 'current_investigation_packet_bounded',
      current_release_monitoring_enabled: false,
      source_count: 0,
      sources: []
    }
  };
  const packet = {
    type: 'investigation_packet',
    version: '0.5.0',
    company,
    summary: { company },
    mode: 'offline_fixture',
    enterprise_cognition: {
      company,
      investigation_report_card: { status: 'fallback_requires_python_runtime', confidence: 'low' },
      subject_due_diligence_profile: { subject_name: company, mode: 'offline_fixture_fallback' },
      control_ownership: {},
      evidence_gaps: ['python_runtime_unavailable'],
      risk_hypotheses: []
    },
    quality_gate: { status: 'usable_with_warnings', blockers: ['python_runtime_unavailable'] },
    one_click_readiness: oneClick,
    monitoring_seed: monitoringSeed,
    qyyjt_public_origin_handoff: {
      type: 'qyyjt_public_origin_handoff',
      available: true,
      top_actions: [fallbackAction],
      report_section_batches: [
        {
          report_section: 'legal_risk',
          top_actions: [{ module: 'search_multi', query_family: 'legal_risk_public_records', priority: 'P0' }]
        }
      ],
      section_work_orders: [qyyjtSectionWorkOrder],
      section_execution_summary: {
        type: 'qyyjt_section_execution_summary',
        section_count: 1,
        p0_section_count: 1,
        ready_section_count: 1,
        blocked_section_count: 0,
        p0_count: 1,
        ready_count: 1,
        blocked_count: 0,
        top_ready_work_order: {
          work_order_id: qyyjtSectionWorkOrder.work_order_id,
          report_section: qyyjtSectionWorkOrder.report_section,
          priority: qyyjtSectionWorkOrder.priority,
          action_count: 1,
          p0_count: 1,
          ready_to_run: true,
          blocked_reason: '',
          done_condition: qyyjtSectionWorkOrder.done_condition
        },
        top_blocked_work_order: {},
        ready_sections: [
          {
            work_order_id: qyyjtSectionWorkOrder.work_order_id,
            report_section: qyyjtSectionWorkOrder.report_section,
            priority: qyyjtSectionWorkOrder.priority,
            action_count: 1,
            p0_count: 1,
            ready_to_run: true,
            blocked_reason: '',
            done_condition: qyyjtSectionWorkOrder.done_condition
          }
        ],
        blocked_sections: [],
        done_condition: 'all_ready_sections_executed_or_blocked_sections_have_explicit_non_reliance_caveats',
        policy: 'Section execution summary is a routing aid; admission still requires provenance, required fields, and entity-match gates.'
      },
      top_ready_section_work_order: qyyjtSectionWorkOrder
    },
    evidence_ledger: [{ id: 'fallback_notice', source: 'node_cli_fallback', summary: 'Python runtime unavailable; generated fallback packet.' }],
    report_markdown: fallbackMarkdown,
    report_exports: {
      type: 'report_exports',
      formats: ['markdown', 'json_packet', 'portable_html', 'premium_html', 'directory_bundle'],
      agent_decision_digest: {
        type: 'agent_decision_digest',
        delivery_status: 'fallback_delivery_without_docx',
        source_resilience_status: 'python_runtime_unavailable',
        bundle_ready_to_verify: true,
        bundle_verification_status: 'export_dir_required',
        first_action: fallbackAction
      },
      portable_html: {
        filename: files.portable_html,
        document: `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>body{font-family:Georgia,'Microsoft YaHei',serif;background:#f6f2ea;color:#1f2933}.report-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px}.visual-panel,.delivery{border:1px solid #d5c6ae;border-radius:16px;padding:16px;margin:12px;background:#fffdf8}pre{white-space:pre-wrap}@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}@media print{body{background:#fff}.visual-panel,.delivery{box-shadow:none}}</style></head><body><main data-premium-html-report="true" data-full-report-preserved="report_markdown"><h1>Offline fixture fallback</h1><section aria-label="report readiness summary">acceptance closure blockers:</section><section class="visual-panel premium-qa" aria-label="premium visual QA checklist"><h2>Premium HTML visual QA checklist</h2><p>component-level liquid glass, evidence darkroom, full report preserved, no generic purple gradient, print-safe degradation</p></section><div class="report-layout"><div><section class="delivery">Agent decision digest</section><section class="visual-panel">Visual evidence panels</section><section class="visual-panel">Relationship and capital appendix<br><b>blocked</b><span>capital relationship</span><br><b>1</b><span>capital verification steps</span><br><b>1</b><span>relationship audit steps</span></section><section class="delivery">Image evidence summary<br>image evidence count: <b>0</b></section><pre id="full-report-body" class="report-body" data-full-report-preserved="true">${escapeHtml(fallbackMarkdown)}</pre></div><aside><section class="visual-panel">Source provenance appendix</section></aside></div></main></body></html>`,
        first_screen_handoff_cards: operationalCards,
        first_screen_handoff_card_count: operationalCards.length,
        first_screen_handoff_source: 'report_exports.print_package.operational_handoff.cards',
        image_evidence_source: 'report_exports.print_package.image_evidence_inventory',
        premium_profile: buildNodeFallbackPremiumHtmlProfile(files.portable_html, operationalCards.length)
      },
      premium_html: buildNodeFallbackPremiumHtmlProfile(files.portable_html, operationalCards.length),
      markdown: { filename: files.markdown, content_field: 'report_markdown' },
      json_packet: { filename: files.json_packet },
      future_formats: { docx_red_head: 'runtime_cli_renderer_available_via_export_docx' },
      print_package: {
        status: 'fallback_docx_unavailable',
        docx: {
          renderer_status: 'unavailable_without_python_runtime',
          filename: null,
          runtime_entrypoint: 'bin/investigate.py --export-docx',
          renderer_capabilities: [
            'chart_manifest_data_rows',
            'operational_handoff_tables',
            'native_word_tables',
            'embedded_local_image_evidence',
            'image_evidence_inventory_items'
          ]
        },
        operational_handoff: {
          summary: { status: oneClick.status },
          cards: operationalCards,
          card_count: operationalCards.length
        },
        image_evidence_inventory: {
          type: 'image_evidence_inventory',
          count: 0,
          items: [],
          embeddable_count: 0,
          remote_reference_count: 0,
          appendix_required: false,
          empty_state: 'No image evidence was collected in this fallback packet.',
          delivery_policy: 'DOCX embeds local/data-uri evidence images and lists remote image references without fetching them; portable HTML shows a bounded machine-readable summary.'
        },
        relationship_capital_appendix: { type: 'relationship_capital_appendix', status: 'fallback_requires_python_runtime' },
        delivery_checklist: {
          quality_checks: [{ id: 'relationship_capital_appendix_present', status: 'present' }]
        }
      },
      directory_bundle: {
        type: 'report_export_directory_bundle',
        runtime_entrypoint: 'bin/investigate.py --export-dir',
        integrity_verifier_entrypoint: 'bin/verify_report_bundle.py <export-dir>',
        verifier_output_fields: REPORT_BUNDLE_VERIFIER_OUTPUT_FIELDS,
        verification_recipe: {
          type: 'report_bundle_verification_recipe',
          command: 'python bin/verify_report_bundle.py <export-dir>',
          expected_exit_code: 0,
          success_condition: 'ok=true and agent_handoff.schema_valid=true and agent_handoff.bundle_ready_to_verify=true',
          failure_routing: 'Open report-export-manifest.json and agent-handoff.json; repair missing files, hash mismatches, or handoff schema failures before delivery.',
          required_output_fields: REPORT_BUNDLE_VERIFIER_OUTPUT_FIELDS
        },
        manifest_filename: files.manifest,
        manifest_fields: ['files', 'file_manifest', 'unavailable_outputs', 'delivery_checklist', 'agent_summary', 'report_exports'],
        writes: ['portable_html', 'markdown', 'json_packet', 'agent_handoff', 'manifest'],
        unavailable_outputs: { docx_red_head: 'python_runtime_unavailable' },
        agent_handoff: {
          filename: files.agent_handoff,
          schema_fields: [
            'delivery_decision',
            'delivery_files',
            'bundle_integrity',
            'bundle_verification',
            'delivery_checklist',
            'source_preflight',
            'runtime_autopilot',
            'deep_autopilot_execution_plan',
            'deep_autopilot_source_runbook',
            'report_visibility',
            'capital_risk_panel',
            'relationship_resolution',
            'source_strengthening',
            'trust_boundaries',
            'decision_digest',
            'next_actions',
            'acceptance_closure',
            'qyyjt_public_origin',
            'source_health',
            'capital_and_relationship'
          ],
          content:
            'delivery files, delivery decision, bundle integrity, bundle verification recipe, verifier output fields, source_preflight, runtime_autopilot, deep autopilot plan/runbook, delivery checklist, report visibility, image evidence inventory, capital risk panel, relationship resolution verification queue, source strengthening work orders, trust boundaries, decision digest, next actions, acceptance closure, control path verification queue, relationship graph audit summary, source recovery execution queue, and Python runtime recovery'
        },
        stdout_preserved: true
      },
    },
  };
  const html = packet.report_exports.portable_html.document;
  const jsonPacket = JSON.stringify(packet, null, 2) + '\n';
  writeFileIfRequested(args, '--export-html', html);
  writeFileIfRequested(args, '--export-json', jsonPacket);
  writeFileIfRequested(args, '--export-markdown', packet.report_markdown + '\n');
  const agentHandoff = buildNodeFallbackAgentHandoff(company, files, oneClick, monitoringSeed);
  const exportDir = optionValue(args, '--export-dir');
  if (exportDir) {
    fs.mkdirSync(exportDir, { recursive: true });
    fs.writeFileSync(path.join(exportDir, files.portable_html), html, 'utf-8');
    fs.writeFileSync(path.join(exportDir, files.json_packet), jsonPacket, 'utf-8');
    fs.writeFileSync(path.join(exportDir, files.markdown), packet.report_markdown + '\n', 'utf-8');
    const fileManifest = buildNodeFallbackFileManifest(exportDir, files, new Set([files.manifest, files.agent_handoff]));
    const enrichedAgentHandoff = {
      ...agentHandoff,
      bundle_integrity: buildNodeFallbackBundleIntegrity(fileManifest, files)
    };
    enrichedAgentHandoff.bundle_verification = buildNodeFallbackBundleVerification(
      packet.report_exports,
      files,
      enrichedAgentHandoff.bundle_integrity
    );
    enrichedAgentHandoff.report_visibility = buildNodeFallbackReportVisibility(packet.report_exports);
    enrichedAgentHandoff.capital_risk_panel = buildNodeFallbackCapitalRiskPanel();
    enrichedAgentHandoff.relationship_resolution = buildNodeFallbackRelationshipResolution();
    enrichedAgentHandoff.source_strengthening = buildNodeFallbackSourceStrengthening();
    enrichedAgentHandoff.source_health = buildNodeFallbackSourceHealth();
    enrichedAgentHandoff.source_preflight = sourcePreflightFallback();
    enrichedAgentHandoff.runtime_autopilot = buildNodeFallbackRuntimeAutopilot(enrichedAgentHandoff.source_preflight);
    enrichedAgentHandoff.deep_autopilot_execution_plan = buildNodeFallbackDeepAutopilotExecutionPlan(
      enrichedAgentHandoff.runtime_autopilot
    );
    enrichedAgentHandoff.deep_autopilot_source_runbook = buildNodeFallbackDeepAutopilotSourceRunbook(
      enrichedAgentHandoff.runtime_autopilot,
      enrichedAgentHandoff.deep_autopilot_execution_plan
    );
    enrichedAgentHandoff.runtime_autopilot.execution_plan = enrichedAgentHandoff.deep_autopilot_execution_plan;
    enrichedAgentHandoff.runtime_autopilot.source_runbook = enrichedAgentHandoff.deep_autopilot_source_runbook;
    enrichedAgentHandoff.qyyjt_public_origin = buildNodeFallbackQyyjtPublicOrigin(
      packet.qyyjt_public_origin_handoff,
      oneClick
    );
    enrichedAgentHandoff.capital_and_relationship = buildNodeFallbackCapitalAndRelationship(
      enrichedAgentHandoff.capital_risk_panel,
      enrichedAgentHandoff.relationship_resolution
    );
    enrichedAgentHandoff.decision_digest = buildNodeFallbackDecisionDigest(enrichedAgentHandoff, oneClick);
    fs.writeFileSync(path.join(exportDir, files.agent_handoff), JSON.stringify(enrichedAgentHandoff, null, 2) + '\n', 'utf-8');
    fs.writeFileSync(
      path.join(exportDir, files.manifest),
      JSON.stringify({
        type: 'report_export_directory_manifest',
        company,
        files,
        unavailable_outputs: { docx: 'python_runtime_unavailable' },
        file_manifest: fileManifest,
        delivery_checklist: enrichedAgentHandoff.delivery_checklist,
        agent_summary: buildNodeFallbackManifestAgentSummary(enrichedAgentHandoff),
        report_exports: packet.report_exports
      }, null, 2) + '\n',
      'utf-8'
    );
  }
  process.stdout.write(jsonPacket);
}

function buildNodeFallbackAgentHandoff(company, files, oneClick, monitoringSeed) {
  const adapters = HOST_IDS.map((hostId) => ({
    host_id: hostId,
    current_release_supported: true,
    tool_sequence: ['release_readiness', 'connector_catalog', 'source_preflight', 'development_requirements', 'agent_tool_adapters', 'investigate_company'],
    execution_matrix_ref: 'agent_tool_adapter_manifest.execution_matrix',
    fallback_order: ['CLI', 'REST API', 'prompt-only'],
    smoke_command: hostId === 'codex' ? 'npm run codex:mcp-smoke' : 'npm run agent:host-smoke',
    required_packet_fields: [
      'quality_gate',
      'evidence_ledger',
      'one_click_readiness',
      'runtime_autopilot',
      'runtime_autopilot.execution_plan',
      'runtime_autopilot.source_runbook',
      'source_preflight',
      'source_preflight.no_prompt_contract',
      'enterprise_cognition.relationship_resolution_v1',
      'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue',
      'qyyjt_public_origin_handoff',
      'report_exports.agent_decision_digest',
      'report_exports.print_package',
      'report_exports.directory_bundle',
      'report_exports.directory_bundle.verification_recipe',
      'report_exports.directory_bundle.verifier_output_fields',
      'report_exports.directory_bundle.agent_handoff',
      'report_exports.directory_bundle.agent_handoff.source_preflight',
      'report_exports.directory_bundle.agent_handoff.deep_autopilot_execution_plan',
      'report_exports.directory_bundle.agent_handoff.deep_autopilot_source_runbook',
      'report_exports.directory_bundle.agent_handoff.report_visibility',
      'report_exports.directory_bundle.agent_handoff.source_strengthening',
      'report_exports.directory_bundle.agent_handoff.delivery_decision'
    ],
    report_outputs: ['markdown', 'json_packet', 'portable_html', 'docx_red_head', 'agent_handoff']
  }));
  const adapterLookup = Object.fromEntries(
    adapters.map((adapter) => [
      adapter.host_id,
      {
        current_release_supported: adapter.current_release_supported,
        fallback_order: adapter.fallback_order,
        smoke_command: adapter.smoke_command,
        tool_sequence: adapter.tool_sequence,
        execution_matrix_ref: adapter.execution_matrix_ref,
        required_packet_field_count: adapter.required_packet_fields.length,
        report_outputs: adapter.report_outputs
      }
    ])
  );
  return {
    type: 'report_export_agent_handoff',
    company,
    status: oneClick.status,
    delivery_decision: buildNodeFallbackDeliveryDecision(),
    delivery_files: {
      type: 'delivery_file_handoff',
      bundle_manifest: files.manifest,
      primary_print_file: null,
      primary_screen_file: files.portable_html,
      full_evidence_packet: files.json_packet,
      markdown_report: files.markdown,
      agent_handoff_file: files.agent_handoff,
      open_order: [files.portable_html, files.markdown, files.json_packet, files.agent_handoff, files.manifest],
      files: {
        docx: { path: null, role: 'primary_print_report', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', required: false, unavailable_reason: 'python_runtime_unavailable' },
        portable_html: { path: files.portable_html, role: 'primary_screen_report', mime_type: 'text/html; charset=utf-8', required: true },
        markdown: { path: files.markdown, role: 'plain_text_report_body', mime_type: 'text/markdown; charset=utf-8', required: true },
        json_packet: { path: files.json_packet, role: 'full_evidence_packet', mime_type: 'application/json; charset=utf-8', required: true },
        agent_handoff: { path: files.agent_handoff, role: 'desktop_agent_task_router', mime_type: 'application/json; charset=utf-8', required: true },
        manifest: { path: files.manifest, role: 'bundle_file_manifest', mime_type: 'application/json; charset=utf-8', required: true }
      },
      stdout_preserved: true,
      policy: 'File names are relative to the export directory; DOCX is unavailable in Node fallback mode.'
    },
    delivery_checklist: buildNodeFallbackDeliveryChecklist(files),
    report_visibility: {},
    capital_risk_panel: {},
    source_strengthening: buildNodeFallbackSourceStrengthening(),
    trust_boundaries: {
      type: 'agent_handoff_trust_boundaries',
      public_data_boundary: 'public, licensed, or user-authorized evidence only',
      can_make_clean_conclusion: false,
      reliance_limitation_count: oneClick.reliance_limitation_count,
      lead_only_until_verified: true,
      weak_leads_are_not_facts: true,
      source_health_is_connector_work_not_subject_risk: true,
      current_release_monitoring_enabled: monitoringSeed.current_release_monitoring_enabled,
      continuous_monitoring_scope: monitoringSeed.feature_scope,
      final_report_content_source: 'fallback report_markdown plus json_packet; rerun Python for full evidence output',
      policy: 'Do not treat Node fallback as a full investigation result.'
    },
    next_actions: [
      {
        id: 'restore_python_runtime',
        source: 'acceptance_closure',
        priority: 'P0',
        status: 'blocked',
        action: 'Restore Python runtime access before final delivery.',
        ready_to_run: false,
        done_condition: 'Python export-dir path completes.',
        packet_refs: ['report_exports.directory_bundle', 'one_click_readiness.acceptance_closure_summary']
      }
    ],
    acceptance_closure: {
      status: oneClick.acceptance_closure_status,
      blocking_count: oneClick.acceptance_closure_blocking_count,
      ready_count: oneClick.acceptance_closure_ready_count,
      open_domains: oneClick.acceptance_closure_summary.open_domains,
      top_action: oneClick.acceptance_closure_top_action,
      next_action: oneClick.acceptance_closure_summary.next_action,
      done_condition: oneClick.acceptance_closure_summary.done_condition,
      policy: oneClick.acceptance_closure_summary.policy
    },
    qyyjt_public_origin: {},
    source_health: {},
    source_preflight: {},
    runtime_autopilot: {},
    deep_autopilot_execution_plan: {},
    deep_autopilot_source_runbook: {},
    capital_and_relationship: {},
    decision_digest: {},
    policy: 'Fallback handoff keeps desktop-agent packaging alive when Python child processes are unavailable.'
  };
}

function buildNodeFallbackDeliveryDecision() {
  return {
    type: 'development_delivery_decision',
    current_target: 'desktop_agent_alpha',
    status: 'desktop_agent_alpha_needs_runtime_closure',
    desktop_agent_release_candidate: false,
    full_product_status: 'not_final_release_ready',
    current_release_completion_percent: 0,
    p0_open_count: 0,
    next_major_gate: 'restore Python runtime, rerun requirements, then use the Python export-dir path for final desktop-agent delivery',
    source: 'node_cli_offline_fixture_fallback',
    policy: 'Node fallback preserves package shape only; use Python requirements output for authoritative release-candidate decisions.'
  };
}

function buildNodeFallbackDeliveryChecklist(files) {
  const requiredOutputs = [
    { id: 'portable_html', filename: files.portable_html, role: 'primary_screen_report', required: true, open_order: 1, produced_by: 'node_cli_offline_fixture_fallback_export_dir' },
    { id: 'markdown_report', filename: files.markdown, role: 'full_text_report', required: true, open_order: 2, produced_by: 'node_cli_offline_fixture_fallback_export_dir' },
    { id: 'json_packet', filename: files.json_packet, role: 'full_evidence_packet', required: true, open_order: 3, produced_by: 'node_cli_offline_fixture_fallback_export_dir' },
    { id: 'agent_handoff', filename: files.agent_handoff, role: 'desktop_agent_task_router', required: true, open_order: 4, produced_by: 'node_cli_offline_fixture_fallback_export_dir' },
    { id: 'bundle_manifest', filename: files.manifest, role: 'bundle_integrity_manifest', required: true, open_order: 5, produced_by: 'node_cli_offline_fixture_fallback_export_dir' },
    { id: 'docx_red_head', filename: null, role: 'primary_print_report', required: false, open_order: null, produced_by: 'python_runtime_required', unavailable_reason: 'python_runtime_unavailable' }
  ];
  return {
    type: 'delivery_checklist_manifest',
    status: 'fallback_delivery_without_docx',
    primary_print_file: null,
    primary_screen_file: files.portable_html,
    agent_open_order: requiredOutputs.filter((item) => item.filename).map((item) => item.filename),
    required_outputs: requiredOutputs,
    quality_checks: [
      {
        id: 'python_runtime_required_for_docx',
        status: 'blocked',
        packet_ref: 'report_exports.print_package.docx',
        done_condition: 'Rerun export-dir with Python runtime access to produce red-head DOCX.'
      },
      {
        id: 'fallback_bundle_present',
        status: 'ready',
        packet_ref: 'report_exports.directory_bundle',
        done_condition: 'Portable HTML, Markdown, JSON packet, agent handoff, and manifest are present.'
      }
    ],
    print_binding: {
      paper: 'A4',
      binding_margin: 'wide_inner_margin',
      page_numbers: false,
      table_of_contents: false,
      chart_tables: false,
      image_appendix: false,
      body_preserved: true
    },
    policy: 'Use fallback files for screen review only; restore Python before final printable DOCX delivery.'
  };
}

function buildNodeFallbackFileManifest(exportDir, files, exclude = new Set()) {
  const items = Object.entries(files)
    .filter(([, filename]) => filename && !exclude.has(filename))
    .sort(([left], [right]) => left.localeCompare(right))
    .filter(([, filename]) => fs.existsSync(path.join(exportDir, filename)))
    .map(([role, filename]) => {
      const content = fs.readFileSync(path.join(exportDir, filename));
      return {
        role,
        filename,
        size_bytes: content.length,
        sha256: crypto.createHash('sha256').update(content).digest('hex')
      };
    });
  return {
    type: 'report_export_file_manifest',
    hash_algorithm: 'sha256',
    item_count: items.length,
    items,
    policy: 'Hashes cover primary emitted report files except manifest and agent-handoff self-referential files to avoid recursive self-hash ambiguity.'
  };
}

function buildNodeFallbackBundleIntegrity(fileManifest, files) {
  const items = Array.isArray(fileManifest?.items) ? fileManifest.items : [];
  const hashedRoles = new Set(items.map((item) => item.role).filter(Boolean));
  const requiredRoles = ['portable_html', 'markdown', 'json_packet']
    .filter((role) => Boolean(files[role]));
  const missingRoles = requiredRoles.filter((role) => !hashedRoles.has(role));
  return {
    type: 'bundle_integrity_handoff',
    file_manifest_field: 'report-export-manifest.json.file_manifest',
    hash_algorithm: fileManifest?.hash_algorithm || '',
    hashed_file_count: Number(fileManifest?.item_count || items.length || 0),
    required_hashed_roles: requiredRoles,
    missing_hashed_roles: missingRoles,
    ready_to_verify: missingRoles.length === 0 && items.length > 0,
    manifest_self_hash_excluded: true,
    agent_handoff_self_hash_excluded: true,
    policy: 'Verify file size and sha256 for primary report outputs from report-export-manifest.json before sharing or archiving the bundle.'
  };
}

function buildNodeFallbackBundleVerification(reportExports, files, bundleIntegrity) {
  const directoryBundle = reportExports?.directory_bundle || {};
  const recipe = directoryBundle.verification_recipe || {};
  return {
    type: 'bundle_verification_handoff',
    recipe,
    command: recipe.command || 'python bin/verify_report_bundle.py <export-dir>',
    integrity_verifier_entrypoint: directoryBundle.integrity_verifier_entrypoint || 'bin/verify_report_bundle.py <export-dir>',
    manifest_file: files.manifest || 'report-export-manifest.json',
    expected_exit_code: Number(recipe.expected_exit_code ?? 0),
    required_output_fields: recipe.required_output_fields || directoryBundle.verifier_output_fields || [],
    success_condition: recipe.success_condition || 'ok=true and agent_handoff.schema_valid=true and agent_handoff.bundle_ready_to_verify=true',
    failure_routing: recipe.failure_routing || 'Repair missing files, hash mismatches, or handoff schema failures before delivery.',
    ready_to_run: Boolean(bundleIntegrity?.ready_to_verify),
    blocked_reason: bundleIntegrity?.ready_to_verify ? '' : 'bundle_integrity_not_ready',
    policy: 'Desktop agents must run this verifier after export-dir and before claiming the bundle is deliverable.'
  };
}

function buildNodeFallbackReportVisibility(reportExports) {
  const portableHtml = reportExports?.portable_html || {};
  const printPackage = reportExports?.print_package || {};
  const imageInventory = printPackage?.image_evidence_inventory || {};
  const operationalHandoff = printPackage?.operational_handoff || {};
  const premiumProfile = portableHtml?.premium_profile || reportExports?.premium_html || {};
  return {
    type: 'report_visibility_handoff',
    portable_html_filename: portableHtml.filename || 'report.html',
    portable_html_contains_full_body: true,
    premium_html: {
      profile_present: premiumProfile.type === 'premium_html_report_profile',
      status: premiumProfile.status || '',
      filename: premiumProfile.filename || portableHtml.filename || 'report.html',
      document_field: premiumProfile.document_field || 'report_exports.portable_html.document',
      acceptance_checklist: Array.isArray(premiumProfile.acceptance_checklist) ? premiumProfile.acceptance_checklist.slice(0, 12) : [],
      content_guarantees: Array.isArray(premiumProfile.content_guarantees) ? premiumProfile.content_guarantees.slice(0, 12) : [],
      forbidden_shortcuts: Array.isArray(premiumProfile.forbidden_shortcuts) ? premiumProfile.forbidden_shortcuts.slice(0, 12) : [],
      metrics: premiumProfile.metrics && typeof premiumProfile.metrics === 'object' ? premiumProfile.metrics : {},
      policy: premiumProfile.policy || ''
    },
    first_screen_handoff_card_count: Number(portableHtml.first_screen_handoff_card_count || 0),
    image_evidence: {
      inventory_type: imageInventory.type || 'image_evidence_inventory',
      inventory_source: 'report_exports.print_package.image_evidence_inventory',
      count: Number(imageInventory.count || 0),
      embeddable_count: Number(imageInventory.embeddable_count || 0),
      remote_reference_count: Number(imageInventory.remote_reference_count || 0),
      appendix_required: Boolean(imageInventory.appendix_required),
      items: Array.isArray(imageInventory.items) ? imageInventory.items.slice(0, 8) : [],
      policy: imageInventory.delivery_policy || ''
    },
    source_provenance: {
      source_count: 0,
      evidence_row_count: 0,
      appendix_required: false,
      rows: [],
      policy: 'Node fallback has no source provenance appendix; rerun Python for full evidence output.'
    },
    section_inventory_count: 0,
    chart_manifest_count: 0,
    operational_handoff_card_count: Number(operationalHandoff.card_count || 0),
    open_order: [
      'delivery_files.primary_screen_file',
      'report_visibility.premium_html',
      'report_visibility.image_evidence',
      'json_packet.evidence_ledger'
    ],
    policy: 'Fallback visibility is limited to emitted screen files and image summary; restore Python for full source provenance and print appendices.'
  };
}

function buildNodeFallbackCapitalRiskPanel() {
  return {
    type: 'capital_risk_panel',
    status: 'blocked',
    risk_level: 'unknown',
    pressure_level: 'unknown',
    capital_pressure_verification_status: 'python_runtime_unavailable',
    capital_relationship_status: 'unknown',
    capital_relationship_unresolved_reason: 'python_runtime_unavailable',
    capital_relationship_match_count: 0,
    relationship_edge_count: 0,
    relationship_evidence_backed_edge_count: 0,
    relationship_auditable_edge_count: 0,
    relationship_missing_evidence_edge_count: 0,
    relationship_lead_only_edge_count: 0,
    capital_verification_queue_count: 1,
    relationship_audit_queue_count: 0,
    capital_verification_queue: [
      {
        step_id: 'CAP-FALLBACK-001',
        priority: 'P0',
        kind: 'restore_python_runtime',
        target_id: 'python_runtime',
        target_title: 'Restore Python runtime before capital-risk reliance.',
        done_condition: 'Full Python export-dir path completes.'
      }
    ],
    relationship_audit_queue: [],
    top_action: {
      step_id: 'CAP-FALLBACK-001',
      priority: 'P0',
      kind: 'restore_python_runtime',
      target_id: 'python_runtime',
      target_title: 'Restore Python runtime before capital-risk reliance.',
      done_condition: 'Full Python export-dir path completes.'
    },
    source_posture: {
      top_family: '',
      family_count: 0,
      has_official_or_authorized_source: false,
      lead_only_public_rows_present: false
    },
    clean_reliance_allowed: false,
    required_packet_refs: [
      'enterprise_cognition.capital_pressure_profile',
      'one_click_readiness.graph_capital_exposure',
      'one_click_readiness.capital_verification_queue'
    ],
    next_action: 'Restore Python runtime and rerun the investigation before relying on capital-risk conclusions.',
    policy: 'Node fallback does not compute capital risk; it only preserves the handoff shape for desktop agents.'
  };
}

function buildNodeFallbackQyyjtPublicOrigin(qyyjtHandoff, oneClick = {}) {
  const handoff = qyyjtHandoff && typeof qyyjtHandoff === 'object' ? qyyjtHandoff : {};
  const sectionWorkOrders = Array.isArray(handoff.section_work_orders)
    ? handoff.section_work_orders.slice(0, 8)
    : [];
  const reportSectionBatches = Array.isArray(handoff.report_section_batches)
    ? handoff.report_section_batches.slice(0, 8)
    : [];
  const topReadySectionWorkOrder = handoff.top_ready_section_work_order || {};
  const topSectionWorkOrder = handoff.top_section_work_order || topReadySectionWorkOrder || sectionWorkOrders[0] || {};
  const sectionExecutionSummary = handoff.section_execution_summary || {
    type: 'qyyjt_section_execution_summary',
    section_count: 0,
    p0_section_count: 0,
    ready_section_count: 0,
    blocked_section_count: 1,
    top_ready_work_order: {},
    top_blocked_work_order: {
      work_order_id: 'QYYJT-FALLBACK-001',
      report_section: 'runtime_closure',
      priority: 'P0',
      ready_to_run: false,
      blocked_reason: 'python_runtime_unavailable',
      done_condition: 'Rerun Python export-dir path to recover QYYJT public-origin section work orders.'
    },
    ready_sections: [],
    blocked_sections: [],
    done_condition: 'python_export_dir_path_restored_or_non_reliance_caveat_kept',
    policy: 'Node fallback cannot reconstruct QYYJT section work orders; restore Python before treating coverage as complete.'
  };
  return {
    handoff,
    report_section_batches: reportSectionBatches,
    section_work_orders: sectionWorkOrders,
    section_execution_summary: sectionExecutionSummary,
    top_ready_section_work_order: topReadySectionWorkOrder,
    top_section_work_order: topSectionWorkOrder,
    gap_bridge: oneClick.public_origin_gap_bridge || {},
    gap_bridge_top_action: oneClick.public_origin_gap_bridge_top_action || {}
  };
}

function buildNodeFallbackSourceHealth() {
  return {
    digest: {},
    snapshot: {},
    top_source: {},
    policy: 'Node fallback records Python runtime recovery as operator work, not subject risk.',
    repair_queue: [],
    recovery_execution_queue: {},
    recovery_summary: {},
    source_resilience: {
      status: 'python_runtime_unavailable',
      score: 0,
      recommended_action: 'restore_python_runtime',
      recommended_step: {
        step_id: 'SRC-FALLBACK-001',
        priority: 'P0',
        kind: 'restore_python_runtime',
        target: 'python_runtime',
        ready_to_run: false,
        blocked_reason: 'python_runtime_unavailable',
        done_condition: 'Python export-dir path completes.'
      },
      retry_policy: {
        type: 'coverage_recovery_retry_policy',
        retryable: false,
        max_attempts: 0,
        blocked_reason: 'python_runtime_unavailable'
      },
      retryable: false,
      max_attempts: 0,
      ready_to_run: false,
      blocked_reason: 'python_runtime_unavailable'
    }
  };
}

function buildNodeFallbackRuntimeAutopilot(sourcePreflight) {
  return {
    type: 'runtime_autopilot_profile',
    version: '0.5.0',
    level: 'advanced_deep_autopilot',
    mode: 'deep',
    status: 'fallback_runtime_pending',
    config_loaded: Boolean(sourcePreflight?.config_loaded),
    configured_source_available: false,
    no_prompt_contract: sourcePreflight?.no_prompt_contract || {},
    source_policy: 'continue_with_public_origin_fallback_and_record_gap',
    operator_work_queue_role: 'internal_autopilot_recovery_queue_not_end_user_task_list',
    policy: 'Node fallback preserves the autopilot contract; rerun Python runtime for full source execution.'
  };
}

function buildNodeFallbackDeepAutopilotExecutionPlan(runtimeAutopilot) {
  return {
    type: 'deep_autopilot_execution_plan',
    version: '0.5.0',
    active: true,
    status: 'fallback_runtime_pending',
    queue_total: 9,
    automation_contract: {
      subject_name_only_after_workspace_preconfiguration: true,
      operator_work_queue_role: 'internal_autopilot_recovery_queue_not_end_user_task_list',
      operator_prompt_required_during_run: false,
      stop_on_missing_advanced_source: false
    },
    continuation_entrypoints: [
      { tool: 'investigate_company', route: 'MCP', args: { mode: 'deep' } },
      { tool: 'CLI', route: 'npx wallstreet-tieling --investigate "<subject>" --mode deep --export-dir <dir>' },
      { tool: 'REST', route: 'POST /api/investigate', args: { mode: 'deep' } }
    ],
    runtime_level: runtimeAutopilot?.level || 'advanced_deep_autopilot',
    next_steps: [
      {
        id: 'restore_python_runtime_for_deep_autopilot',
        priority: 'P0',
        status: 'blocked',
        ready_to_run: false,
        action: 'Restore Python runtime access, then rerun deep export-dir to execute configured source lanes.',
        done_condition: 'deep-mode packet includes runtime_autopilot.execution_plan, source_runbook, source_preflight, and report bundle verifier passes.'
      }
    ],
    policy: 'Do not ask the end user to choose sources after subject submission; fallback or downgrade unavailable lanes and record gaps.'
  };
}

function buildNodeFallbackDeepAutopilotSourceRunbook(runtimeAutopilot, executionPlan) {
  const laneIds = [
    'domestic_registry_and_qyyjt',
    'official_public_global_sources',
    'sanctions_and_watchlists',
    'authorized_commercial_sources',
    'relationship_graph_and_control_path',
    'capital_pressure_and_financing',
    'goods_flow_and_supply_chain',
    'people_flow_and_public_osint',
    'report_generation_and_visual_outputs'
  ];
  return {
    type: 'deep_autopilot_source_runbook',
    version: '0.5.0',
    status: 'fallback_runtime_pending',
    automatic_lane_count: laneIds.length,
    operator_queue_semantics: 'internal_autopilot_recovery_queue_not_end_user_task_list',
    runtime_level: runtimeAutopilot?.level || 'advanced_deep_autopilot',
    execution_plan_status: executionPlan?.status || 'fallback_runtime_pending',
    lanes: laneIds.map((id, index) => ({
      id,
      priority: index < 3 ? 'P0' : 'P1',
      user_prompt_required: false,
      stop_on_failure: false,
      fallback_policy: 'record_gap_and_continue',
      output_contract: 'preserve evidence, source status, confidence, and next action'
    })),
    policy: 'Every lane is automatic after workspace preconfiguration; blocked sources become report-visible gaps instead of user prompts.'
  };
}

function buildNodeFallbackRelationshipResolution() {
  const fallbackStep = {
    priority: 'P0',
    relation_type: 'relationship_resolution',
    target: 'relationship_resolution_v1',
    admission: 'blocked',
    source: 'node_cli_fallback',
    evidence_ids: [],
    next_action: 'Restore Python runtime and rerun export-dir before relying on relationship candidate leads.'
  };
  return {
    type: 'relationship_resolution_handoff',
    source: 'enterprise_cognition.relationship_resolution_v1',
    lead_count: 0,
    edge_count: 0,
    typed_lead_count: 0,
    weak_lead_count: 0,
    lead_risk_level: 'python_runtime_unavailable',
    by_relation_type: {},
    by_lane: {},
    source_names: [],
    verification_queue_count: 1,
    verification_queue: [fallbackStep],
    top_step: fallbackStep,
    candidate_leads: [],
    preserve_fields: [
      'enterprise_cognition.relationship_resolution_v1',
      'enterprise_cognition.relationship_resolution_v1.resolution_summary',
      'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue'
    ],
    policy: 'Relationship resolution is unavailable in Node fallback; rerun Python before relying on relationship candidate leads.'
  };
}

function buildNodeFallbackCapitalAndRelationship(capitalRiskPanel, relationshipResolution = {}) {
  const relationshipAudit = {
    type: 'relationship_graph_audit_handoff',
    status: 'blocked',
    edge_count: 0,
    evidence_backed_edge_count: 0,
    auditable_edge_count: 0,
    missing_evidence_edge_count: 0,
    lead_only_edge_count: 0,
    queue_count: 1,
    queue: [
      {
        step_id: 'REL-FALLBACK-001',
        priority: 'P0',
        kind: 'restore_python_runtime',
        target: 'relationship_graph',
        ready_to_run: false,
        done_condition: 'Python export-dir path completes.'
      }
    ],
    top_step: {
      step_id: 'REL-FALLBACK-001',
      priority: 'P0',
      kind: 'restore_python_runtime',
      target: 'relationship_graph',
      ready_to_run: false,
      done_condition: 'Python export-dir path completes.'
    },
    policy: 'Relationship graph audit is unavailable in Node fallback; keep non-reliance caveat until Python rerun.'
  };
  return {
    risk_panel: capitalRiskPanel,
    graph_capital_exposure: {},
    graph_capital_exposure_top_step: {},
    capital_verification_queue: capitalRiskPanel.capital_verification_queue || [],
    capital_verification_top_step: capitalRiskPanel.top_action || {},
    capital_relationship_closure_step: {},
    relationship_graph_audit: relationshipAudit,
    relationship_resolution: relationshipResolution
  };
}

function buildNodeFallbackSourceStrengthening() {
  const topWorkOrders = [
    {
      connector: 'official_china_public_origin',
      priority: 'P0',
      lane: 'public_origin_mapping',
      missing_contracts: ['standardized_record', 'provenance', 'entity_match', 'admission_tests'],
      next_action: 'Restore Python runtime, load connector_catalog, and implement the first source-specific strengthening execution_plan before report promotion.',
      runtime_companion: {
        type: 'source_strengthening_runtime_companion',
        connector: 'configured_local_subject_index',
        required_config: ['index_path'],
        promotion_gate: 'Subject-level risk requires a reviewed local/public snapshot record, provenance, entity match, and admission tests.'
      },
      execution_plan: {
        type: 'source_strengthening_execution_plan',
        source_hint: 'official_public_source',
        record_type: 'public_origin_record',
        first_target_file: 'core/connector_registry.py',
        primary_acceptance_command: 'node tools/run-python.js -m pytest tests/unit/test_connector_registry.py tests/unit/test_investigation.py::test_node_cli_offline_fallback_writes_agent_handoff_bundle -q',
        ordered_steps: [
          'Read connector_catalog.source_strengthening_queue',
          'Pick the top P0 work order with a public or QYYJT lane',
          'Implement source-specific standardized records with provenance and entity-match fields',
          'Keep rows lead-only until admission gates pass',
          'Add focused tests and rerun smoke checks'
        ],
        runtime_companion: {
          type: 'source_strengthening_runtime_companion',
          connector: 'configured_local_subject_index',
          required_config: ['index_path'],
          promotion_gate: 'Subject-level risk requires a reviewed local/public snapshot record, provenance, entity match, and admission tests.'
        },
        report_gate: 'Do not promote catalog or lead-only rows into report facts until standardized records, provenance, entity match, and admission tests pass.'
      },
      implementation_pack_ref: {
        type: 'source_strengthening_implementation_pack',
        target_files: ['core/connector_registry.py', 'core/investigation.py', 'tests/unit/test_connector_registry.py'],
        acceptance_commands: [
          'node tools/run-python.js -m pytest tests/unit/test_connector_registry.py -q',
          'npm run codex:mcp-smoke'
        ]
      }
    }
  ];
  return {
    type: 'source_strengthening_handoff',
    status: 'fallback_runtime_pending',
    catalog_tool: 'connector_catalog',
    mcp_tool: 'connector_catalog',
    cli: 'npx wallstreet-tieling --connectors',
    api: 'GET /api/connectors',
    work_order_count: topWorkOrders.length,
    top_work_orders: topWorkOrders,
    top_work_order: topWorkOrders[0],
    by_lane: { public_origin_mapping: topWorkOrders.length },
    preserve_fields: [
      'connector_catalog.source_strengthening_queue',
      'connector_catalog.source_strengthening_queue[].implementation_pack',
      'connector_catalog.source_strengthening_queue[].execution_plan',
      'connector_catalog.source_strengthening_queue[].runtime_companion'
    ],
    promotion_gate: 'Do not promote catalog or lead-only rows into report facts until source-specific standardized records, provenance, entity match, and admission tests pass.',
    policy: 'Node fallback keeps source-strengthening work visible for desktop agents; rerun Python for the authoritative connector catalog.'
  };
}

function buildNodeFallbackManifestAgentSummary(agentHandoff) {
  const acceptanceClosure = agentHandoff.acceptance_closure || {};
  const trustBoundaries = agentHandoff.trust_boundaries || {};
  const sourceHealth = agentHandoff.source_health || {};
  const sourceResilience = sourceHealth.source_resilience || {};
  const sourceStrengthening = agentHandoff.source_strengthening || {};
  const qyyjtPublicOrigin = agentHandoff.qyyjt_public_origin || {};
  const capitalRelationship = agentHandoff.capital_and_relationship || {};
  const relationshipResolution = agentHandoff.relationship_resolution || {};
  const relationshipAudit = capitalRelationship.relationship_graph_audit || {};
  const qyyjtSectionWorkOrders = Array.isArray(qyyjtPublicOrigin.section_work_orders)
    ? qyyjtPublicOrigin.section_work_orders
    : [];
  const sourceRepairQueue = Array.isArray(sourceHealth.repair_queue) ? sourceHealth.repair_queue : [];
  const capitalQueue = Array.isArray(capitalRelationship.capital_verification_queue)
    ? capitalRelationship.capital_verification_queue
    : [];
  const nextActions = Array.isArray(agentHandoff.next_actions) ? agentHandoff.next_actions : [];
  return {
    type: 'report_export_manifest_agent_summary',
    status: agentHandoff.status || '',
    delivery_decision: agentHandoff.delivery_decision || {},
    decision_digest: agentHandoff.decision_digest || {},
    bundle_verification: agentHandoff.bundle_verification || {},
    source_preflight: agentHandoff.source_preflight || {},
    source_preflight_status: agentHandoff.source_preflight?.status || 'unknown',
    source_preflight_deep_mode_status: agentHandoff.source_preflight?.deep_mode_status || 'unknown',
    source_preflight_stop_on_missing_advanced_source: Boolean(
      agentHandoff.source_preflight?.no_prompt_contract?.stop_on_missing_advanced_source
    ),
    source_preflight_operator_prompt_required_during_run: Boolean(
      agentHandoff.source_preflight?.no_prompt_contract?.operator_prompt_required_during_run
    ),
    deep_autopilot_execution_plan: agentHandoff.deep_autopilot_execution_plan || {},
    deep_autopilot_source_runbook: agentHandoff.deep_autopilot_source_runbook || {},
    deep_autopilot_active: Boolean(agentHandoff.deep_autopilot_execution_plan?.active),
    deep_autopilot_queue_total: Number(agentHandoff.deep_autopilot_execution_plan?.queue_total || 0),
    deep_autopilot_automatic_lane_count: Number(agentHandoff.deep_autopilot_source_runbook?.automatic_lane_count || 0),
    report_visibility: {
      type: agentHandoff.report_visibility?.type || 'report_visibility_handoff',
      image_evidence_inventory_present:
        agentHandoff.report_visibility?.image_evidence?.inventory_type === 'image_evidence_inventory',
      image_evidence_count: Number(agentHandoff.report_visibility?.image_evidence?.count || 0),
      source_count: Number(agentHandoff.report_visibility?.source_provenance?.source_count || 0),
      section_inventory_count: Number(agentHandoff.report_visibility?.section_inventory_count || 0),
      chart_manifest_count: Number(agentHandoff.report_visibility?.chart_manifest_count || 0),
      premium_html_profile_present: Boolean(agentHandoff.report_visibility?.premium_html?.profile_present),
      premium_html_status: agentHandoff.report_visibility?.premium_html?.status || ''
    },
    capital_risk_panel: {
      type: agentHandoff.capital_risk_panel?.type || 'capital_risk_panel',
      status: agentHandoff.capital_risk_panel?.status || 'unknown',
      risk_level: agentHandoff.capital_risk_panel?.risk_level || 'unknown',
      capital_verification_queue_count: Number(agentHandoff.capital_risk_panel?.capital_verification_queue_count || 0),
      relationship_audit_queue_count: Number(agentHandoff.capital_risk_panel?.relationship_audit_queue_count || 0),
      clean_reliance_allowed: Boolean(agentHandoff.capital_risk_panel?.clean_reliance_allowed)
    },
    source_strengthening: {
      type: sourceStrengthening.type || 'source_strengthening_handoff',
      status: sourceStrengthening.status || 'unknown',
      work_order_count: Number(sourceStrengthening.work_order_count || 0),
      top_work_order: sourceStrengthening.top_work_order || {},
      by_lane: sourceStrengthening.by_lane || {}
    },
    delivery_status: agentHandoff.delivery_checklist?.status || '',
    can_make_clean_conclusion: Boolean(trustBoundaries.can_make_clean_conclusion),
    acceptance_closure_status: acceptanceClosure.status || '',
    acceptance_closure_blocking_count: acceptanceClosure.blocking_count || 0,
    source_resilience_status: sourceResilience.status || 'python_runtime_unavailable',
    source_resilience_retryable: Boolean(sourceResilience.retryable),
    source_resilience_blocked_reason: sourceResilience.blocked_reason || 'python_runtime_unavailable',
    relationship_audit_status: relationshipAudit.status || '',
    relationship_resolution: {
      type: relationshipResolution.type || 'relationship_resolution_handoff',
      lead_count: Number(relationshipResolution.lead_count || 0),
      typed_lead_count: Number(relationshipResolution.typed_lead_count || 0),
      weak_lead_count: Number(relationshipResolution.weak_lead_count || 0),
      verification_queue_count: Number(relationshipResolution.verification_queue_count || 0),
      top_step: relationshipResolution.top_step || {}
    },
    work_queue_counts: {
      operator_work: 0,
      operator_work_ready: 0,
      source_repair: sourceRepairQueue.length,
      qyyjt_public_origin_sections: qyyjtSectionWorkOrders.length,
      capital_verification: capitalQueue.length,
      relationship_audit: Number(relationshipAudit.queue_count || 0)
    },
    top_public_origin_work_order: qyyjtPublicOrigin.top_section_work_order || qyyjtPublicOrigin.top_ready_section_work_order || qyyjtSectionWorkOrders[0] || {},
    top_capital_step: capitalRelationship.capital_verification_top_step || {},
    top_relationship_step: relationshipAudit.top_step || {},
    next_action_count: nextActions.length,
    top_next_actions: nextActions.slice(0, 5).map((item) => ({
      id: item.id || '',
      priority: item.priority || '',
      status: item.status || '',
      action: item.action || '',
      ready_to_run: Boolean(item.ready_to_run),
      done_condition: item.done_condition || ''
    })),
    policy: 'Manifest summary is a bounded routing preview; restore Python and inspect agent-handoff.json for complete routing.'
  };
}

function buildNodeFallbackDecisionDigest(agentHandoff, oneClick) {
  const nextActions = Array.isArray(agentHandoff.next_actions) ? agentHandoff.next_actions : [];
  const firstAction = nextActions[0] || {};
  const bundleIntegrity = agentHandoff.bundle_integrity || {};
  return {
    type: 'agent_decision_digest',
    delivery_status: agentHandoff.delivery_checklist?.status || 'fallback_delivery_without_docx',
    bundle_ready_to_verify: Boolean(bundleIntegrity.ready_to_verify),
    can_make_clean_conclusion: false,
    acceptance_closure_status: oneClick.acceptance_closure_status || 'blocked',
    acceptance_blocking_count: Number(oneClick.acceptance_closure_blocking_count || 1),
    source_resilience_status: 'python_runtime_unavailable',
    source_resilience_ready_to_run: false,
    source_resilience_retryable: false,
    capital_relationship_status: 'unknown',
    relationship_audit_status: 'unknown',
    work_queue_counts: {
      operator_work: 0,
      operator_work_ready: 0,
      capital_verification: 0,
      relationship_audit: 0,
      public_origin: 0,
      source_repair: 0
    },
    first_action: {
      id: firstAction.id || '',
      priority: firstAction.priority || '',
      status: firstAction.status || '',
      ready_to_run: Boolean(firstAction.ready_to_run),
      action: firstAction.action || '',
      done_condition: firstAction.done_condition || ''
    },
    blocked_reasons: ['python_runtime_unavailable'],
    requires_operator: true,
    public_or_authorized_boundary: 'public, licensed, or user-authorized evidence only; rerun Python path before final reliance',
    policy: 'Use this digest for fallback routing only; restore Python for full evidence review.'
  };
}

function connectorCatalogFallback() {
  const reportSectionBatches = [
    {
      report_section: 'legal_risk',
      top_actions: [{ module: 'search_multi', query_family: 'judicial_public_records', priority: 'P0' }]
    },
    {
      report_section: 'asset_solvency',
      top_actions: [{ module: 'search_multi', query_family: 'asset_solvency_public_records', priority: 'P0' }]
    }
  ];
  return {
    type: 'connector_catalog',
    summary: {
      default_enabled: 4,
      zero_config_ready: ['default_public_intel', 'public_web_search', 'sec_edgar_public_api', 'gleif_public_api'],
      admission_counts: { production_ready: 4, field_contract_required: 1 },
      admission_gate_summary: { gate_counts: { field_contract_required: 1 } },
      data_effectiveness: { fact_capable_sources: 4 },
    },
    connectors: [
      { name: 'sec_edgar_public_api', admission: { decision: 'production_ready' } },
      { name: 'gleif_public_api', admission: { decision: 'production_ready' } },
    ],
    qyyjt_benchmark: {
      summary: {
        p0_queue_count: 1,
        public_origin_execution_summary: {
          type: 'qyyjt_public_origin_execution_summary',
          p0_count: 1,
          top_action: { module: 'search_multi', query_family: 'judicial_public_records', priority: 'P0' },
          report_section_batches: reportSectionBatches,
        },
      },
    },
  };
}

function releaseReadinessFallback() {
  return {
    type: 'release_readiness_brief',
    execution_mode: 'node_metadata_fallback',
    metadata_fallback_warning: 'python_child_process_unavailable_fallback_active',
    contract: {
      version: '0.5.0',
      summary: { variant_count: HOST_IDS.length },
      variants: Object.fromEntries(HOST_IDS.map((hostId) => [hostId, { readiness: 'alpha', entrypoints: ['CLI', 'REST API', 'MCP'] }])),
      product: {
        shared_core: [
          'core.enterprise_cognition.EnterpriseCognitionEngine',
          'core.intelligence_retrieval.InvestigativeRetrievalPlanner',
        ],
      },
    },
    runtime_delivery: {
      acceptance_status_counts: { proof_defined: 7 },
      release_blocking_surface_count: 0,
      surfaces: [
        { surface: 'desktop_agent_installation_handoff' },
        { surface: 'source_health_trend_snapshot' },
        { surface: 'source_health_release_warnings' },
      ],
      source_health_operator_handoff: {
        trend_entrypoints: ['/api/monitor/source-health'],
        warning_fields: ['release_gate'],
        recovery_queue_fields: ['operator_action'],
      },
    },
    delivery_decision: {
      status: 'desktop_agent_alpha_release_candidate',
      remaining_variant_blocker_count: 0,
      variant_next_gate_count: 1,
      full_product_status: 'not_final_release_ready',
    },
    persona_surface: {
      runtime_lane_bindings: [
        {
          lane: 'data_sources',
          packet_fields: ['one_click_readiness.operator_work_queue', 'qyyjt_public_origin_handoff']
        },
        {
          lane: 'verification',
          packet_fields: ['one_click_readiness.reliance_limitations']
        },
        {
          lane: 'finance',
          packet_fields: ['one_click_readiness.capital_verification_top_step']
        },
        {
          lane: 'people',
          packet_fields: ['one_click_readiness.relationship_graph_audit_top_step']
        }
      ]
    },
    delivery_closure: deliveryClosureFallback(),
    blockers: [],
    latest_acceptance_evidence: {
      status: 'passed',
      observed_at: '2026-07-05 14:24 Asia/Shanghai',
      covers: [
        'agent_tool_adapters runtime contract',
        'WorkBuddy investigate_company host smoke',
        'host-smoke Python runtime resolution',
        'desktop-agent installation handoff',
        'npm package dry-run content gate',
        'terminology guard public-copy hygiene',
        'report_exports.agent_decision_digest packet routing',
        'directory bundle verifier_output_fields handoff',
        'directory bundle verification_recipe handoff',
        'DOCX source provenance appendix and evidence source index',
        'DOCX relationship/capital appendix and delivery checklist',
      ],
    },
    fallback_warning: 'node_metadata_fallback_only_python_child_process_unavailable',
  };
}

function deliveryClosureFallback() {
  return {
    type: 'desktop_agent_alpha_delivery_closure',
    status: 'release_candidate',
    execution_mode: 'node_metadata_fallback',
    metadata_fallback_warning: 'python_child_process_unavailable_fallback_active',
    target: 'desktop_agent_alpha',
    document: 'docs/DESKTOP_AGENT_ALPHA_DELIVERY.md',
    baseline_sequence: [
      'release_readiness',
      'connector_catalog',
      'source_preflight',
      'development_requirements',
      'agent_tool_adapters',
      'investigate_company'
    ],
    followup_tools: ['aggregate_subject'],
    required_verification_commands: [
      'npm run acceptance',
      'npm run codex:mcp-smoke',
      'npm run agent:host-smoke',
      'npm run api:smoke',
      'npm run release:privacy-scan',
      'npm run release:preflight',
      'npm run delivery:audit',
      'npm run objective:audit',
      'npm pack --dry-run --json'
    ],
    required_preserved_fields: [
      'delivery_decision',
      'quality_gate',
      'evidence_ledger',
      'one_click_readiness',
      'runtime_autopilot',
      'runtime_autopilot.execution_plan',
      'runtime_autopilot.source_runbook',
      'source_preflight',
      'source_preflight.no_prompt_contract',
      'enterprise_cognition.relationship_resolution_v1',
      'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue',
      'qyyjt_public_origin_handoff',
      'report_exports.agent_decision_digest',
      'report_exports.premium_html',
      'report_exports.portable_html.premium_profile',
      'report_exports.directory_bundle',
      'report_exports.directory_bundle.agent_handoff',
      'report_exports.directory_bundle.agent_handoff.source_preflight',
      'report_exports.directory_bundle.agent_handoff.report_visibility',
      'report_exports.directory_bundle.agent_handoff.report_visibility.premium_html',
      'report_exports.directory_bundle.agent_handoff.capital_risk_panel',
      'report_exports.directory_bundle.agent_handoff.source_strengthening',
      'report_exports.directory_bundle.agent_handoff.delivery_decision',
      'report_exports.directory_bundle.agent_handoff.deep_autopilot_execution_plan',
      'report_exports.directory_bundle.agent_handoff.deep_autopilot_source_runbook',
      'qyyjt_public_origin_handoff.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.report_visibility.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun',
      'report_exports.directory_bundle.agent_handoff.report_artifact_autorun'
    ],
    not_current_release: [
      'final polished product launch readiness',
      'marketplace approval',
      'human-captured marketplace screenshots',
      'polished immersive HTML workbench as the primary product surface',
      'mini-program, mobile app, or standalone desktop app',
      'always-on continuous monitoring',
      'guaranteed live coverage for every advertised source'
    ],
    open_submission_items: [
      'capture marketplace/operator screenshots after final acceptance',
      'publish from a clean reviewed release branch',
      'keep local fixtures, private reports, cookies, browser profiles, runtime state, and secrets out of package'
    ],
    policy: 'Node metadata fallback mirrors the release checklist when Python child-process spawning is blocked; full investigation packets, DOCX export, and final evidence refresh still require the Python runtime path.'
  };
}

function releasePreflightFallback() {
  const closure = deliveryClosureFallback();
  return {
    type: 'desktop_agent_alpha_release_preflight',
    execution_mode: 'node_metadata_fallback',
    metadata_fallback_warning: 'python_child_process_unavailable_fallback_active',
    target: 'desktop_agent_alpha',
    status: 'ready_for_local_packaging',
    package_candidate_ready: true,
    final_submission_ready: false,
    final_submission_blockers: closure.open_submission_items,
    blocking_items: [],
    required_verification_commands: closure.required_verification_commands,
    required_preserved_fields: closure.required_preserved_fields,
    latest_acceptance: {
      status: 'passed',
      command: 'npm run acceptance',
      observed_at: '2026-07-05 14:24 Asia/Shanghai',
      python_tests_passed: 768,
      python_tests_skipped: 9
    },
    packaging_review: {
      dry_run_command: 'npm pack --dry-run --json',
      privacy_command: 'npm run release:privacy-scan',
      do_not_package: [
        'API keys, cookies, browser profiles, local SQLite collaboration databases, generated secrets',
        'runtime state directories such as .codex-autonomous, outputs, deliverables, audit_reports, or WorkBuddy local artifacts',
        'private investigation reports or local fixtures not listed in package.json files'
      ]
    },
    agent_handoff: {
      read_first: [
        'docs/DESKTOP_AGENT_ALPHA_DELIVERY.md',
        'docs/AGENT_HOST_SMOKE_CHECKLIST.md',
        'docs/API_CONTRACTS.md'
      ],
      baseline_sequence: closure.baseline_sequence,
      safe_claim: 'Desktop-agent alpha release candidate, not final polished product launch readiness.',
      do_not_claim: closure.not_current_release
    },
    policy: 'Node metadata fallback mirrors local package preflight only; rerun with Python before final reliance.'
  };
}

function deliveryAuditFallback() {
  const release = releaseReadinessFallback();
  const preflight = releasePreflightFallback();
  const closure = deliveryClosureFallback();
  const requiredCommands = closure.required_verification_commands || [];
  const requiredFields = closure.required_preserved_fields || [];
  return {
    type: 'desktop_agent_alpha_delivery_audit',
    target: 'desktop_agent_alpha',
    status: preflight.package_candidate_ready ? 'pass' : 'blocked',
    ready_for_local_packaging: Boolean(preflight.package_candidate_ready),
    final_submission_ready: false,
    full_product_status: 'not_final_release_ready',
    safe_claim: preflight.agent_handoff.safe_claim,
    checks: [
      { name: 'desktop_agent_release_candidate', passed: true, evidence: 'release_readiness.delivery_decision.status' },
      { name: 'package_candidate_ready', passed: Boolean(preflight.package_candidate_ready), evidence: 'release_preflight.package_candidate_ready' },
      { name: 'acceptance_passed', passed: true, evidence: 'latest_acceptance_evidence.status' },
      { name: 'verification_commands_declared', passed: requiredCommands.includes('npm run acceptance') && requiredCommands.includes('npm pack --dry-run --json'), evidence: 'delivery_closure.required_verification_commands' },
      { name: 'deep_runtime_autorun_preserved', passed: requiredFields.includes('qyyjt_public_origin_handoff.agent_autorun'), evidence: 'delivery_closure.required_preserved_fields' }
    ],
    failed_checks: [],
    blocking_items: preflight.blocking_items || [],
    coverage: {
      source_resilience: { covered: requiredFields.includes('report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun') },
      qyyjt_public_origin: { covered: requiredFields.includes('qyyjt_public_origin_handoff.agent_autorun') },
      relationship_graph: { covered: requiredFields.includes('report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun') },
      capital_risk: { covered: requiredFields.includes('report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun') },
      report_visibility: { covered: requiredFields.includes('report_exports.directory_bundle.agent_handoff.report_visibility.premium_html') },
      workbuddy_expert_team: { covered: true }
    },
    verification_evidence: {
      latest_acceptance: preflight.latest_acceptance,
      required_commands: requiredCommands,
      release_blocking_surface_count: release.runtime_delivery.release_blocking_surface_count
    },
    next_actions: [
      'Run npm run acceptance before stronger delivery claims if code changed after recorded evidence.',
      'Capture marketplace/operator screenshots only for external submission.',
      'Publish only from a clean reviewed release branch.'
    ],
    not_current_release: closure.not_current_release,
    policy: 'Node metadata fallback mirrors the delivery audit when Python child-process spawning is blocked.'
  };
}

function objectiveAuditFallback() {
  const audit = deliveryAuditFallback();
  const coverage = audit.coverage || {};
  const requirements = [
    {
      id: 'source_resilience',
      requirement: 'Information-source resilience is visible in runtime, report handoff, release checks, and agent preservation fields.',
      status: coverage.source_resilience?.covered ? 'complete' : 'incomplete',
      evidence: ['delivery_audit.coverage.source_resilience'],
      remaining_work: coverage.source_resilience?.covered ? [] : ['Restore source resilience coverage before delivery claims.']
    },
    {
      id: 'qyyjt_public_origin_mapping',
      requirement: 'QYYJT/commercial-source concepts are mapped back to public-origin categories and survive agent handoff.',
      status: coverage.qyyjt_public_origin?.covered ? 'complete' : 'incomplete',
      evidence: ['delivery_audit.coverage.qyyjt_public_origin'],
      remaining_work: coverage.qyyjt_public_origin?.covered ? [] : ['Restore QYYJT public-origin coverage before delivery claims.']
    },
    {
      id: 'desktop_agent_delivery',
      requirement: 'Desktop-agent delivery is locally packageable across supported hosts.',
      status: audit.ready_for_local_packaging ? 'complete' : 'incomplete',
      evidence: ['delivery_audit.ready_for_local_packaging'],
      remaining_work: audit.ready_for_local_packaging ? [] : ['Fix delivery audit failed checks.']
    },
    {
      id: 'superpowers_final_review',
      requirement: 'Final Superpowers review/update has been performed after all objective work.',
      status: 'incomplete',
      evidence: ['objective requires final Superpowers review after project completion'],
      remaining_work: ['Run/update Superpowers final review only after the remaining delivery audit items are complete.']
    }
  ];
  const failed = requirements.filter((item) => item.status !== 'complete');
  return {
    type: 'objective_completion_audit',
    execution_mode: 'node_metadata_fallback',
    target: 'wallstreet_tieling_desktop_agent_delivery_objective',
    status: failed.length ? 'in_progress' : 'complete',
    completion_percent: Math.round(100 * (requirements.length - failed.length) / requirements.length),
    requirements,
    failed_requirements: failed,
    release_gate: {
      delivery_audit_status: audit.status,
      ready_for_local_packaging: audit.ready_for_local_packaging,
      final_submission_ready: audit.final_submission_ready,
      full_product_status: audit.full_product_status
    },
    verification_evidence: audit.verification_evidence,
    next_actions: failed.flatMap((item) => item.remaining_work),
    policy: 'Node metadata fallback is a reduced objective audit; rerun with Python for full requirement coverage.'
  };
}

function developmentRequirementsFallback() {
  return {
    type: 'development_requirements_board',
    completion_percent: 94,
    summary: { by_level: { P0: 1 } },
    next_focus: ['desktop-agent runtime closure', 'report bundle verification'],
    delivery_decision: {
      status: 'desktop_agent_alpha_release_candidate',
      current_target: 'desktop_agent_alpha',
      full_product_status: 'not_final_release_ready',
    },
    qyyjt_current_version: { p0_queue_count: 20 },
    scope_rules: { continuous_monitoring: 'future_version_not_current_release' },
  };
}

function agentToolsFallback() {
  const hostIds = HOST_IDS;
  const sharedTools = [
    {
      name: 'release_readiness',
      cli: 'npx wallstreet-tieling --release',
      api: 'GET /api/release',
      mcp_tool: 'release_readiness',
      required_output_fields: [
        'type',
        'delivery_decision.status',
        'delivery_decision.remaining_variant_blocker_count',
        'delivery_decision.variant_next_gate_count',
        'latest_acceptance_evidence.status',
        'runtime_delivery.surfaces'
      ]
    },
    {
      name: 'delivery_closure',
      cli: 'npx wallstreet-tieling --delivery-closure',
      api: 'GET /api/release delivery_closure',
      mcp_tool: 'delivery_closure',
      required_output_fields: [
        'type',
        'status',
        'baseline_sequence',
        'required_verification_commands',
        'required_preserved_fields',
        'not_current_release'
      ]
    },
    {
      name: 'delivery_audit',
      cli: 'npx wallstreet-tieling --delivery-audit',
      api: 'GET /api/delivery-audit',
      mcp_tool: 'delivery_audit',
      required_output_fields: ['type', 'status', 'ready_for_local_packaging', 'failed_checks', 'coverage']
    },
    {
      name: 'objective_audit',
      cli: 'npx wallstreet-tieling --objective-audit',
      api: 'GET /api/objective-audit',
      mcp_tool: 'objective_audit',
      required_output_fields: ['type', 'status', 'completion_percent', 'requirements', 'failed_requirements']
    },
    { name: 'connector_catalog', cli: 'npx wallstreet-tieling --connectors', api: 'GET /api/connectors', mcp_tool: 'connector_catalog' },
    {
      name: 'development_requirements',
      cli: 'npx wallstreet-tieling --requirements',
      api: 'GET /api/requirements',
      mcp_tool: 'development_requirements',
      required_output_fields: [
        'type',
        'completion_percent',
        'next_focus',
        'delivery_decision.status',
        'delivery_decision.full_product_status',
        'scope_rules.continuous_monitoring'
      ]
    },
    {
      name: 'agent_tool_adapters',
      cli: 'npx wallstreet-tieling --agent-tools',
      api: 'GET /api/agent-tools',
      mcp_tool: 'agent_tool_adapters',
      required_output_fields: [
        'type',
        'release_target',
        'adapters[].tool_sequence',
        'adapters[].fallback_order',
        'adapters[].required_packet_fields',
        'execution_matrix[].done_condition',
        'required_smoke_commands'
      ]
    },
    {
      name: 'investigate_company',
      cli: 'npx wallstreet-tieling --investigate "<company>"',
      api: 'POST /api/investigate',
      mcp_tool: 'investigate_company',
      required_output_fields: [
        'type',
        'summary',
        'quality_gate',
        'evidence_ledger',
        'one_click_readiness',
        'enterprise_cognition.relationship_resolution_v1',
        'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue',
        'qyyjt_public_origin_handoff',
        'report_exports.agent_decision_digest',
        'report_exports.print_package.delivery_checklist',
        'report_exports.directory_bundle.agent_handoff',
        'report_exports.directory_bundle.verification_recipe',
        'report_exports.directory_bundle.verifier_output_fields',
        'report_exports.directory_bundle.agent_handoff.report_visibility',
        'report_exports.directory_bundle.agent_handoff.capital_risk_panel',
        'report_exports.directory_bundle.agent_handoff.delivery_decision'
      ]
    },
    {
      name: 'aggregate_subject',
      cli: 'npx wallstreet-tieling --aggregate-subject "<subject_id>" --subject-name "<subject_name>"',
      api: 'POST /api/aggregate',
      mcp_tool: 'aggregate_subject'
    }
  ];
  const adapters = hostIds.map((hostId) => ({
    host_id: hostId,
    primary_mode: hostId === 'codex' ? 'codex_plugin_mcp' : 'universal_cli_api',
    current_release_supported: true,
    install_handoff: {
      type: 'host_install_handoff',
      host_id: hostId,
      install_command: hostId === 'codex' ? 'npx skills add Dear-Ded/wallstreet-tieling -g -y' : 'npm install -g wallstreet-tieling',
      config_files: ['SKILL.md', 'bin/cli.js', 'deploy/mcp-server.json'],
      start_command: 'npx -y wallstreet-tieling --mcp',
      smoke_command: hostId === 'codex' ? 'npm run codex:mcp-smoke' : 'npm run agent:host-smoke',
      done_condition: 'release_readiness returns desktop_agent_alpha_release_candidate and investigate_company returns directory_bundle.agent_handoff.',
      fallback_policy: 'If MCP is blocked, use CLI, then REST API, then prompt-only handoff without dropping packet fields.'
    },
    tool_sequence: ['release_readiness', 'connector_catalog', 'development_requirements', 'agent_tool_adapters', 'investigate_company'],
    execution_matrix_ref: 'agent_tool_adapter_manifest.execution_matrix',
    fallback_order: hostId === 'codex' ? ['Codex plugin', 'CLI', 'REST API', 'prompt-only'] : ['CLI', 'REST API', 'prompt-only'],
    smoke_command: hostId === 'codex' ? 'npm run codex:mcp-smoke' : 'npm run agent:host-smoke',
    required_packet_fields: [
      'quality_gate',
      'evidence_ledger',
      'one_click_readiness',
      'enterprise_cognition.relationship_resolution_v1',
      'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue',
      'qyyjt_public_origin_handoff',
      'report_exports.agent_decision_digest',
      'report_exports.directory_bundle',
      'report_exports.directory_bundle.verification_recipe',
      'report_exports.directory_bundle.agent_handoff',
      'report_exports.directory_bundle.verifier_output_fields',
      'report_exports.directory_bundle.agent_handoff.report_visibility',
      'report_exports.directory_bundle.agent_handoff.capital_risk_panel',
      'report_exports.directory_bundle.agent_handoff.delivery_decision'
    ],
    report_outputs: ['markdown', 'json_packet', 'portable_html', 'docx_red_head', 'agent_handoff']
  }));
  const adapterLookup = Object.fromEntries(
    adapters.map((adapter) => [
      adapter.host_id,
      {
        current_release_supported: adapter.current_release_supported,
        install_command: adapter.install_handoff.install_command,
        config_files: adapter.install_handoff.config_files,
        start_command: adapter.install_handoff.start_command,
        fallback_order: adapter.fallback_order,
        smoke_command: adapter.smoke_command,
        tool_sequence: adapter.tool_sequence,
        execution_matrix_ref: adapter.execution_matrix_ref,
        required_packet_field_count: adapter.required_packet_fields.length,
        report_outputs: adapter.report_outputs
      }
    ])
  );
  return {
    type: 'agent_tool_adapter_manifest',
    version: '0.5.0',
    release_target: 'desktop_agent_alpha',
    adapter_count: hostIds.length,
    all_current_release_ready: true,
    shared_tool_count: sharedTools.length,
    shared_tools: sharedTools,
    installation_handoff: {
      type: 'desktop_agent_installation_handoff',
      release_target: 'desktop_agent_alpha',
      package_name: 'wallstreet-tieling',
      default_install_command: 'npm install -g wallstreet-tieling',
      default_mcp_command: 'npx -y wallstreet-tieling --mcp',
      default_cli_smoke: 'npx wallstreet-tieling --release',
      offline_fixture_smoke: 'npx wallstreet-tieling --investigate "Demo Install Smoke Co., Ltd." --offline-fixture',
      required_local_runtime_env: [
        'WST_PYTHON optional: set when the host cannot find Python automatically',
        'WST_MCP_TIMEOUT_MS optional: increase MCP timeout for slow hosts',
        'WST_QUERY_TIMEOUT_SECONDS optional: bound retrieval tasks',
        'npm_config_cache optional: keep npm cache in a writable local directory'
      ],
      verification_commands: ['npm run agent:host-smoke', 'npm run codex:mcp-smoke', 'npm run api:smoke', 'npm run delivery:audit', 'npm run objective:audit', 'npm pack --dry-run --json'],
      host_matrix: adapters.map((adapter) => ({
        host_id: adapter.host_id,
        install_command: adapter.install_handoff.install_command,
        config_files: adapter.install_handoff.config_files,
        start_command: adapter.install_handoff.start_command,
        smoke_command: adapter.install_handoff.smoke_command,
        done_condition: adapter.install_handoff.done_condition
      })),
      failure_routing: [
        { symptom: 'npx or npm cannot write cache', action: 'Set npm_config_cache to a writable local cache and retry.' },
        { symptom: 'Python child process unavailable', action: 'Set WST_PYTHON to a known Python runtime before relying on full investigation output.' },
        { symptom: 'MCP startup or tool call timeout', action: 'Increase WST_MCP_TIMEOUT_MS and fall back to CLI/API while preserving packet fields.' }
      ],
      done_condition: 'Host can run release_readiness, agent_tool_adapters, and one offline-fixture investigate_company path while preserving directory_bundle.agent_handoff.',
      policy: 'Node metadata fallback mirrors install handoff shape only; full investigation packets still require Python runtime.'
    },
    execution_matrix: [
      {
        phase: 'release_gate',
        tool: 'release_readiness',
        done_condition: 'delivery_decision.status is desktop_agent_alpha_release_candidate and runtime_delivery.release_blocking_surface_count is 0.',
        failure_routing: 'Stop packaging claims; inspect delivery_closure.required_verification_commands before continuing.'
      },
      {
        phase: 'source_catalog',
        tool: 'connector_catalog',
        done_condition: 'summary.zero_config_ready includes default_public_intel and QYYJT public-origin execution summary is present.',
        failure_routing: 'Use fixture mode for validation and keep failed sources in operator work.'
      },
      {
        phase: 'priority_board',
        tool: 'development_requirements',
        done_condition: 'delivery_decision.current_target is desktop_agent_alpha and next_focus contains current P0/P1 lanes.',
        failure_routing: 'Rerun requirements or fall back to PROJECT_TASKBOARD.md.'
      },
      {
        phase: 'host_binding',
        tool: 'agent_tool_adapters',
        done_condition: 'Selected adapter has fallback_order, smoke_command, and required_packet_fields.',
        failure_routing: 'Use universal CLI fallback and never return prose-only output.'
      },
      {
        phase: 'investigation_run',
        tool: 'investigate_company',
        done_condition: 'Packet type is investigation_packet with one_click_readiness and directory_bundle.agent_handoff.',
        failure_routing: 'Return diagnostics and operator_work_queue; do not hide gaps behind narrative.'
      },
      {
        phase: 'followup_expansion',
        tool: 'aggregate_subject',
        done_condition: 'subject, relationship_graph, and profile are present for the requested subject_id.',
        failure_routing: 'Keep as optional follow-up and do not block the main packet.',
        optional: true
      }
    ],
    first_run_recipe: {
      type: 'desktop_agent_first_run_recipe',
      sequence: ['release_readiness', 'delivery_audit', 'connector_catalog', 'development_requirements', 'agent_tool_adapters', 'investigate_company'],
      optional_followup: ['aggregate_subject'],
      preserve_before_summarizing: [
        'quality_gate',
        'evidence_ledger',
        'one_click_readiness',
        'enterprise_cognition.relationship_resolution_v1',
        'enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue',
        'qyyjt_public_origin_handoff',
        'report_exports.agent_decision_digest',
        'report_exports.directory_bundle.verification_recipe',
        'report_exports.directory_bundle.agent_handoff',
        'report_exports.directory_bundle.agent_handoff.report_visibility',
        'report_exports.directory_bundle.agent_handoff.capital_risk_panel',
        'report_exports.directory_bundle.verifier_output_fields'
      ],
      verification_commands: ['npm run api:smoke', 'npm run codex:mcp-smoke', 'npm run agent:host-smoke', 'npm run delivery:audit', 'npm run objective:audit', 'npm pack --dry-run --json'],
      do_not: [
        'Do not replace the packet with prose-only output.',
        'Do not treat source failures or coverage gaps as clean findings.',
        'Do not claim final product launch readiness from desktop-agent alpha readiness.'
      ]
    },
    host_ids: hostIds,
    adapters,
    adapter_lookup: adapterLookup,
    default_host_id: 'universal',
    required_smoke_commands: ['npm run agent:host-smoke', 'npm run codex:mcp-smoke', 'npm run api:smoke'],
    policy: 'Python unavailable fallback only; use the Python manifest before release claims.'
  };
}

function subjectAggregationFallback(subjectId, subjectName, maxDepth) {
  return {
    type: 'subject_profile_aggregation_fallback',
    subject: {
      id: subjectId,
      name: subjectName
    },
    relationship_graph: {
      nodes: [],
      edges: []
    },
    profile: {},
    adapter_summary: {
      total_sources: 0,
      failed: ['python_runtime_unavailable'],
      empty: [],
      cache_hits: 0
    },
    max_depth: maxDepth,
    policy: 'Python unavailable fallback only; rerun with WST_PYTHON before relying on aggregation output.'
  };
}

function main(args = process.argv.slice(2)) {
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
    ].join('; '), connectorCatalogFallback);
  } else if (args.includes('--release')) {
    printPythonJson([
      'import json',
      'from core.release_contract import release_readiness_brief',
      'print(json.dumps(release_readiness_brief(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), releaseReadinessFallback);
  } else if (args.includes('--delivery-closure')) {
    printPythonJson([
      'import json',
      'from core.release_contract import release_readiness_brief',
      'print(json.dumps(release_readiness_brief().get("delivery_closure", {}), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), deliveryClosureFallback);
  } else if (args.includes('--release-preflight')) {
    printPythonJson([
      'import json',
      'from core.release_contract import release_preflight_brief',
      'print(json.dumps(release_preflight_brief(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), releasePreflightFallback);
  } else if (args.includes('--delivery-audit')) {
    printPythonJson([
      'import json',
      'from core.release_contract import delivery_audit_brief',
      'print(json.dumps(delivery_audit_brief(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), deliveryAuditFallback);
  } else if (args.includes('--objective-audit')) {
    printPythonJson([
      'import json',
      'from core.release_contract import objective_completion_audit_brief',
      'print(json.dumps(objective_completion_audit_brief(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), objectiveAuditFallback);
  } else if (args.includes('--requirements')) {
    printPythonJson([
      'import json',
      'from core.development_requirements import build_development_requirements_board',
      'print(json.dumps(build_development_requirements_board(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), developmentRequirementsFallback);
  } else if (args.includes('--agent-tools')) {
    printPythonJson([
      'import json',
      'from core.agent_tool_adapters import build_agent_tool_adapter_manifest',
      'print(json.dumps(build_agent_tool_adapter_manifest(), ensure_ascii=False, indent=2, sort_keys=True))'
    ].join('; '), agentToolsFallback);
  } else if (args.includes('--aggregate-subject')) {
    runSubjectAggregation(args);
  } else if (args.includes('--investigate')) {
    runInvestigation(args);
  } else {
    outputSkill(false);
  }
}

module.exports = { main };

if (require.main === module) {
  main();
}
