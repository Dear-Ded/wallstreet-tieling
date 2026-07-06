param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$candidates = @()
if ($env:WST_PYTHON) { $candidates += $env:WST_PYTHON }
if ($env:PYTHON) { $candidates += $env:PYTHON }
$candidates += Join-Path $root ".venv\Scripts\python.exe"
$candidates += Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$candidates += "py"
$candidates += "python3"
$candidates += "python"

$python = $null
foreach ($candidate in $candidates) {
    if (-not $candidate) { continue }
    try {
        $check = & $candidate --version 2>$null
        if ($LASTEXITCODE -eq 0 -or $check) {
            $python = $candidate
            break
        }
    } catch {
        if ([System.IO.Path]::IsPathRooted($candidate) -and (Test-Path -LiteralPath $candidate)) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    Write-Error "No usable Python runtime found. Set WST_PYTHON to continue."
    exit 1
}

if (-not $ScriptArgs -or $ScriptArgs.Count -eq 0) {
    Write-Error "Usage: powershell -File tools/run-python.ps1 <script-or-module> [args...]"
    exit 2
}

$env:PYTHONUTF8 = "1"
Push-Location $root
try {
    & $python @ScriptArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
