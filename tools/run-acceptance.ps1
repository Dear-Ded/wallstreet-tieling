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
Invoke-Checked "Desktop agent host smoke" { & $node tools\agent-host-smoke.js | Out-Null }

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

Write-Host ""
Write-Host "Acceptance passed for $Company"
