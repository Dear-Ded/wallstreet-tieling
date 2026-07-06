param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stateDir = $env:WST_TEST_STATE_DIR
if (-not $stateDir -or -not $stateDir.Trim()) {
    $stateDir = Join-Path $env:TEMP "wallstreet-tieling-focused-tests"
}
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$stateDir = (Resolve-Path -LiteralPath $stateDir).Path
$runTemp = Join-Path $stateDir ("run-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $runTemp | Out-Null
$env:TEMP = $runTemp
$env:TMP = $runTemp
if (-not $env:WST_STATE_DIR -or -not $env:WST_STATE_DIR.Trim()) {
    $env:WST_STATE_DIR = Join-Path $stateDir "state"
}
New-Item -ItemType Directory -Force -Path $env:WST_STATE_DIR | Out-Null
$pytestCache = Join-Path $stateDir "pytest-cache"
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
$env:WST_PYTHON = $python

if (-not $PytestArgs -or $PytestArgs.Count -eq 0) {
    $PytestArgs = @("tests\unit\test_investigation.py", "tests\unit\test_default_public_intel_tool.py", "tests\unit\test_public_web_search_tool.py")
}

& $python -m pytest @PytestArgs -q -o "cache_dir=$pytestCache"
if ($LASTEXITCODE -ne 0) {
    throw "Focused tests failed with exit code $LASTEXITCODE."
}
