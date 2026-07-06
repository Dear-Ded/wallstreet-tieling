param(
    [string]$Company = "Apple Inc."
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$acceptanceState = $env:WST_ACCEPTANCE_STATE_DIR
if (-not $acceptanceState -or -not $acceptanceState.Trim()) {
    $acceptanceState = Join-Path $root ".tmp\acceptance"
}
try {
    New-Item -ItemType Directory -Force -Path $acceptanceState | Out-Null
} catch {
    $acceptanceState = Join-Path $env:TEMP "wallstreet-tieling-acceptance"
    New-Item -ItemType Directory -Force -Path $acceptanceState | Out-Null
}
$acceptanceState = (Resolve-Path -LiteralPath $acceptanceState).Path
$runTemp = Join-Path $acceptanceState ("run-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $runTemp | Out-Null
$env:TMP = $runTemp
$env:TEMP = $runTemp
if (-not $env:WST_STATE_DIR -or -not $env:WST_STATE_DIR.Trim()) {
    $env:WST_STATE_DIR = Join-Path $acceptanceState "state"
}
New-Item -ItemType Directory -Force -Path $env:WST_STATE_DIR | Out-Null
$pytestCache = Join-Path $acceptanceState "pytest-cache"
New-Item -ItemType Directory -Force -Path $pytestCache | Out-Null

$pythonCandidates = @(
    $env:WST_PYTHON,
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
    "python"
) | Where-Object { $_ -and $_.Trim() }

$python = $null
foreach ($candidate in $pythonCandidates) {
    try {
        & $candidate --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $python) {
    throw "No usable Python runtime found. Set WST_PYTHON to continue."
}

$nodeCandidates = @(
    $env:WST_NODE,
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"),
    "node"
) | Where-Object { $_ -and $_.Trim() }

$node = $null
foreach ($candidate in $nodeCandidates) {
    try {
        & $candidate --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $node = $candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $node) {
    throw "No usable Node.js runtime found. Set WST_NODE to continue."
}

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Invoke-CheckedOutput {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    $output = & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
    return $output
}

Write-Host "== Wallstreet Tieling 0.5.0 acceptance =="
Write-Host "Python: $python"
Write-Host "Node: $node"

$validatorCandidates = @(
    $env:WST_PLUGIN_VALIDATOR,
    (Join-Path $env:USERPROFILE ".codex\skills\.system\plugin-creator\scripts\validate_plugin.py")
) | Where-Object { $_ -and $_.Trim() }

$pluginValidator = $null
foreach ($candidate in $validatorCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $pluginValidator = $candidate
        break
    }
}

if (-not $pluginValidator) {
    throw "No Codex plugin validator found. Set WST_PLUGIN_VALIDATOR to validate_plugin.py."
}

Invoke-Checked "Focused Python tests" {
    & $python -m pytest `
    tests\unit\test_investigation.py `
    tests\unit\test_investigation_quality.py `
    tests\unit\test_dd_v3_audit.py `
    tests\unit\test_api_server.py `
    tests\unit\test_development_requirements.py `
    tests\unit\test_default_public_intel_tool.py `
    tests\unit\test_connector_registry.py `
    tests\unit\test_auth_gate.py `
    tests\unit\test_autonomous.py `
    tests\unit\test_mass_profiler.py `
    tests\unit\test_enterprise_profiling.py `
    tests\unit\test_enterprise_logistics.py `
    tests\unit\test_china_domestic.py `
    tests\unit\test_deep_osint.py `
    tests\unit\test_deep_data.py `
    tests\unit\test_record_quality.py `
    tests\unit\test_source_admission.py `
    tests\unit\test_risk_graph_export.py `
    tests\unit\test_intelligence_retrieval.py `
    tests\unit\test_safe_research_boundaries.py `
    tests\unit\test_runtime_deep.py `
    tests\unit\test_subject_dd_profiler.py `
    tests\unit\test_verified_sources.py `
    tests\unit\test_deep_profile.py `
    tests\unit\test_telegram_agg.py `
    tests\unit\test_advanced_source_guardrail.py `
    tests\unit\test_one_click_defaults.py `
    tests\unit\test_subject_profile.py `
    tests\unit\test_risk_discovery_cli.py `
    tests\unit\test_official_public_smoke.py `
    tests\unit\test_source_smoke.py `
    tests\unit\test_local_index_audit.py `
    tests\unit\test_qyyjt_tool.py `
    tests\unit\test_runtime_adapters.py `
    tests\unit\test_release_variants.py `
    tests\unit\test_encoding_integrity.py `
    tests\unit\test_release_hygiene.py `
    tests\unit\test_storage_paths.py `
    tests\unit\test_workbuddy.py `
    tests\unit\test_enterprise_cognition.py `
    -q `
    -o "cache_dir=$pytestCache"
}

Invoke-Checked "Codex plugin validator" { & $python $pluginValidator . }
Invoke-Checked "Terminology guard" { & $python bin\terminology_guard.py --format json --fail-on error | Out-Null }
Invoke-Checked "CLI syntax check" { & $node --check bin\cli.js }
Invoke-Checked "MCP server syntax check" { & $node --check lib\mcp-server.js }
Invoke-Checked "Codex MCP smoke syntax check" { & $node --check tools\codex-mcp-smoke.js }
Invoke-Checked "Desktop agent host smoke syntax check" { & $node --check tools\agent-host-smoke.js }
$env:WST_PYTHON = $python
Invoke-Checked "Codex MCP smoke" { & $node tools\codex-mcp-smoke.js | Out-Null }
Invoke-Checked "REST API smoke" { & $python tools\api-smoke.py | Out-Null }
Invoke-Checked "Desktop agent host smoke" { & $node tools\agent-host-smoke.js | Out-Null }
Invoke-Checked "Package privacy scan" { & $python tools\package-privacy-scan.py --json | Out-Null }
$preflightText = (Invoke-CheckedOutput "Release preflight" {
    & $node bin\cli.js --release-preflight
}) -join "`n"
$preflight = $preflightText | ConvertFrom-Json
if ($preflight.type -ne "desktop_agent_alpha_release_preflight") {
    throw "Release preflight returned unexpected type: $($preflight.type)"
}
if ($preflight.package_candidate_ready -ne $true) {
    throw "Release preflight did not mark the desktop-agent alpha package candidate ready."
}
if ($preflight.final_submission_ready -ne $false) {
    throw "Release preflight must keep final submission readiness separate from local package readiness."
}
$deliveryAuditText = (Invoke-CheckedOutput "Delivery audit" {
    & $node bin\cli.js --delivery-audit
}) -join "`n"
$deliveryAudit = $deliveryAuditText | ConvertFrom-Json
if ($deliveryAudit.type -ne "desktop_agent_alpha_delivery_audit") {
    throw "Delivery audit returned unexpected type: $($deliveryAudit.type)"
}
if ($deliveryAudit.status -ne "pass") {
    throw "Delivery audit did not pass: $($deliveryAudit.status)"
}
if ($deliveryAudit.ready_for_local_packaging -ne $true) {
    throw "Delivery audit did not mark the desktop-agent alpha package ready."
}
if ($deliveryAudit.failed_checks.Count -ne 0) {
    throw "Delivery audit has failed checks: $($deliveryAudit.failed_checks | ConvertTo-Json -Compress)"
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    throw "No npm runtime found; package dry-run content gate cannot run."
}
$env:npm_config_cache = Join-Path $acceptanceState "npm-cache"
$packText = (Invoke-CheckedOutput "npm package dry-run" {
    & $npm.Source pack --dry-run --json
}) -join "`n"
$pack = $packText | ConvertFrom-Json
if (-not $pack -or -not $pack[0].files) {
    throw "npm package dry-run did not return a package file list."
}
$packPaths = @($pack[0].files | ForEach-Object { $_.path })
$requiredPackPaths = @(
    ".codex-plugin/plugin.json",
    "bin/cli.js",
    "bin/verify_report_bundle.py",
    "lib/mcp-server.js",
    "tools/codex-mcp-smoke.js",
    "tools/agent-host-smoke.js",
    "tools/api-smoke.py",
    "tools/run-acceptance.ps1",
    "docs/API_CONTRACTS.md",
    "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
    "skills/wallstreet-tieling/SKILL.md"
)
foreach ($path in $requiredPackPaths) {
    if ($packPaths -notcontains $path) {
        throw "npm package dry-run missing required release file: $path"
    }
}
$forbiddenExactPackPaths = @(
    "AGENT_COORDINATION_BOARD.md",
    "docs/COMPREHENSIVE_AUDIT_REPORT_2026-06-16.md",
    "docs/FINAL_DELIVERY_REPORT_2026-06-16.md",
    "gen_ci.py",
    "overview.md",
    "package-lock.json",
    "send_message_to_product_ai.py"
)
foreach ($path in $forbiddenExactPackPaths) {
    if ($packPaths -contains $path) {
        throw "npm package dry-run includes forbidden local artifact: $path"
    }
}
$forbiddenPackPatterns = @(
    "^\.(git|pytest_cache|tmp)/",
    "^audit_reports/",
    "^deliverables/",
    "^docs/deepseek/",
    "^docs/workbuddy/",
    "^output/",
    "\.(cookie|cookies|db|db\.backup|jsonl|sqlite|sqlite3)$"
)
foreach ($path in $packPaths) {
    foreach ($pattern in $forbiddenPackPatterns) {
        if ($path -match $pattern) {
            throw "npm package dry-run includes forbidden path: $path"
        }
    }
}

$summary = (Invoke-CheckedOutput "Default one-click risk_discovery" {
    & $python bin\risk_discovery.py $Company --summary --query-timeout-seconds 8
}) -join "`n"
if ($summary -notmatch "Evidence:") {
    throw "Default one-click risk_discovery summary did not include evidence count."
}
if ($summary -match "all_sources_failed") {
    throw "Default one-click risk_discovery reported all sources failed."
}

$packetText = (Invoke-CheckedOutput "Default one-click investigate" {
    & $python bin\investigate.py $Company --query-timeout-seconds 8
}) -join "`n"
$packet = $packetText | ConvertFrom-Json
if ($packet.type -ne "investigation_packet") {
    throw "Default one-click investigate command did not return an investigation_packet."
}
if ($packet.version -ne "0.5.0") {
    throw "Default one-click investigate command did not return version 0.5.0."
}
if (-not $packet.evidence_ledger -or $packet.evidence_ledger.Count -lt 1) {
    throw "Default one-click investigation did not return an evidence ledger."
}
if (-not $packet.report_markdown -or $packet.report_markdown -notmatch "0\.5\.0") {
    throw "Default one-click report did not include the 0.5.0 product header."
}
if ($packet.report_markdown -notmatch "operator work queue") {
    throw "Default one-click report did not include operator work queue visibility."
}
if (-not $packet.qyyjt_public_origin_handoff -or $packet.qyyjt_public_origin_handoff.type -ne "qyyjt_public_origin_handoff") {
    throw "Default one-click investigation did not expose qyyjt_public_origin_handoff."
}
if (-not $packet.qyyjt_public_origin_handoff.section_work_orders -or -not $packet.qyyjt_public_origin_handoff.top_section_work_order.work_order_id) {
    throw "Default one-click investigation did not expose QYYJT public-origin section work orders."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "source_resilience_recommended_step")) {
    throw "Default one-click investigation did not expose source_resilience_recommended_step."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "operator_work_queue")) {
    throw "Default one-click investigation did not expose operator_work_queue."
}
if ($packet.one_click_readiness.operator_work_queue_count -lt 1 -or -not $packet.one_click_readiness.operator_work_top_action.work_id) {
    throw "Default one-click investigation did not expose an actionable operator work top action."
}
if (-not ($packet.one_click_readiness.operator_work_top_action.PSObject.Properties.Name -contains "ready_to_run")) {
    throw "Default one-click operator work top action did not expose ready_to_run."
}
if (-not $packet.one_click_readiness.operator_work_top_action.done_condition) {
    throw "Default one-click operator work top action did not expose done_condition."
}
if (-not $packet.one_click_readiness.reliance_limitations -or $packet.one_click_readiness.reliance_limitations.type -ne "reliance_limitations") {
    throw "Default one-click investigation did not expose reliance_limitations."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "can_make_clean_conclusion")) {
    throw "Default one-click investigation did not expose can_make_clean_conclusion."
}
if (-not $packet.one_click_readiness.acceptance_closure_summary -or $packet.one_click_readiness.acceptance_closure_summary.type -ne "acceptance_closure_summary") {
    throw "Default one-click investigation did not expose acceptance_closure_summary."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "acceptance_closure_status")) {
    throw "Default one-click investigation did not expose acceptance_closure_status."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "capital_verification_queue_count")) {
    throw "Default one-click investigation did not expose capital_verification_queue_count."
}
if (-not ($packet.one_click_readiness.PSObject.Properties.Name -contains "relationship_graph_audit_queue_count")) {
    throw "Default one-click investigation did not expose relationship_graph_audit_queue_count."
}
if (-not $packet.report_exports.portable_html.document -or $packet.report_exports.portable_html.document -notmatch "capital verification steps") {
    throw "Default one-click portable HTML did not include handoff cards."
}
if ($packet.report_exports.portable_html.document -notmatch "acceptance closure blockers:") {
    throw "Default one-click portable HTML did not include acceptance closure card."
}
if ($packet.report_exports.directory_bundle.runtime_entrypoint -ne "bin/investigate.py --export-dir") {
    throw "Default one-click report exports did not include directory bundle contract."
}
if (
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "ok" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.schema_valid" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.delivery_checklist_present" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_integrity_present" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_verification_present" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_verification_ready_to_run" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_ready_to_verify" -or
    $packet.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.report_visibility_present"
) {
    throw "Default one-click directory bundle did not expose verifier output fields."
}
if (
    $packet.report_exports.directory_bundle.verification_recipe.type -ne "report_bundle_verification_recipe" -or
    $packet.report_exports.directory_bundle.verification_recipe.required_output_fields -notcontains "agent_handoff.bundle_ready_to_verify"
) {
    throw "Default one-click directory bundle did not expose verification recipe."
}
if (
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "delivery_decision" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "delivery_files" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "bundle_verification" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "report_visibility" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "trust_boundaries" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "decision_digest" -or
    $packet.report_exports.directory_bundle.agent_handoff.schema_fields -notcontains "next_actions"
) {
    throw "Default one-click directory bundle did not include executable handoff schema fields."
}
if ($packet.report_exports.directory_bundle.agent_handoff.content -notmatch "acceptance closure") {
    throw "Default one-click directory bundle did not include acceptance closure handoff content."
}
if ($packet.report_exports.directory_bundle.agent_handoff.content -notmatch "relationship graph audit summary") {
    throw "Default one-click directory bundle did not include relationship graph audit handoff content."
}
if (-not $packet.report_exports.print_package.docx.renderer_capabilities -or $packet.report_exports.print_package.docx.renderer_capabilities -notcontains "chart_manifest_data_rows") {
    throw "Default one-click DOCX manifest did not include chart_manifest_data_rows capability."
}
if ($packet.report_exports.print_package.docx.renderer_capabilities -notcontains "operational_handoff_tables") {
    throw "Default one-click DOCX manifest did not include operational_handoff_tables capability."
}
if ($packet.report_exports.print_package.docx.renderer_capabilities -notcontains "embedded_local_image_evidence") {
    throw "Default one-click DOCX manifest did not include embedded_local_image_evidence capability."
}
if (-not $packet.report_exports.print_package.operational_handoff.summary.status) {
    throw "Default one-click print package did not include operational handoff summary."
}
if ($packet.report_exports.print_package.operational_handoff.cards[0].id -ne "acceptance_closure_summary") {
    throw "Default one-click print package did not expose acceptance closure as the first handoff card."
}
if ($packet.report_exports.print_package.relationship_capital_appendix.type -ne "relationship_capital_appendix") {
    throw "Default one-click print package did not include relationship/capital appendix."
}
if (
    -not (
        $packet.report_exports.print_package.delivery_checklist.quality_checks |
        Where-Object { $_.id -eq "relationship_capital_appendix_present" }
    )
) {
    throw "Default one-click delivery checklist did not include relationship/capital appendix check."
}
if ($packet.report_exports.print_package.docx.renderer_capabilities -notcontains "native_word_tables") {
    throw "Default one-click DOCX manifest did not include native_word_tables capability."
}

$fixturePacketText = (Invoke-CheckedOutput "China-style fixture-pack investigate" {
    & $python bin\investigate.py "Demo Technology Co., Ltd." --fixture-pack --query-timeout-seconds 8
}) -join "`n"
$fixturePacket = $fixturePacketText | ConvertFrom-Json
if ($fixturePacket.type -ne "investigation_packet") {
    throw "Fixture-pack investigate command did not return an investigation_packet."
}
if ($fixturePacket.one_click_readiness.fact_count -lt 1 -or $fixturePacket.one_click_readiness.operator_work_queue_count -lt 1) {
    throw "Fixture-pack one-click investigation did not expose facts and operator work."
}
if (-not $fixturePacket.enterprise_cognition.capital_pressure_profile -or -not $fixturePacket.enterprise_cognition.goods_flow_profile -or -not $fixturePacket.enterprise_cognition.people_flow_profile) {
    throw "Fixture-pack one-click investigation did not expose money/goods/people cognition profiles."
}
if ($fixturePacket.report_exports.directory_bundle.runtime_entrypoint -ne "bin/investigate.py --export-dir") {
    throw "Fixture-pack one-click report exports did not include directory bundle contract."
}
if (
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "ok" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.schema_valid" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.delivery_checklist_present" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_integrity_present" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_verification_present" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_verification_ready_to_run" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.bundle_ready_to_verify" -or
    $fixturePacket.report_exports.directory_bundle.verifier_output_fields -notcontains "agent_handoff.report_visibility_present"
) {
    throw "Fixture-pack one-click directory bundle did not expose verifier output fields."
}
if (
    $fixturePacket.report_exports.directory_bundle.verification_recipe.type -ne "report_bundle_verification_recipe" -or
    $fixturePacket.report_exports.directory_bundle.verification_recipe.required_output_fields -notcontains "agent_handoff.bundle_ready_to_verify"
) {
    throw "Fixture-pack one-click directory bundle did not expose verification recipe."
}

Write-Host ""
Write-Host "Acceptance passed for $Company"
