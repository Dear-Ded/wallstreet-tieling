param(
  [string]$FailOn = "error",
  [switch]$Fix
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
  $env:WST_PYTHON,
  (Join-Path $root ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
  "python"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
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

$args = @("bin\terminology_guard.py", "--fail-on", $FailOn)
if ($Fix) {
  $args += "--fix"
}
& $python @args
