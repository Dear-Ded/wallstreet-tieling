param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Assert-InRepo {
  param([string]$Path)
  $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue)
  if (-not $resolved) { return $null }
  $fullPath = $resolved.Path
  if ($fullPath -ne $root -and -not $fullPath.StartsWith($root + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to clean outside repository: $fullPath"
  }
  return $fullPath
}

function Remove-ManagedPath {
  param([string]$Path)
  $fullPath = Assert-InRepo $Path
  if (-not $fullPath) { return }
  if ($DryRun) {
    [pscustomobject]@{ action = "would_remove"; path = $Path; resolved = $fullPath }
    return
  }
  Remove-Item -LiteralPath $fullPath -Recurse -Force -ErrorAction Stop
  [pscustomobject]@{ action = "removed"; path = $Path; resolved = $fullPath }
}

function Get-RepoRelativePath {
  param([string]$FullPath)
  if ($FullPath -eq $root) { return "." }
  if (-not $FullPath.StartsWith($root + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to relativize outside repository: $FullPath"
  }
  return $FullPath.Substring($root.Length + 1)
}

function Test-ExcludedRecursivePath {
  param([string]$FullPath)
  $relative = Get-RepoRelativePath $FullPath
  $first = ($relative -split "[/\\]")[0]
  return $first -in @(
    ".codex-autonomous",
    ".workbuddy",
    ".colab",
    "deliverables",
    "audit_reports",
    "node_modules"
  )
}

$safeTopLevelPaths = @(
  ".tmp",
  ".pytest_cache",
  ".coverage",
  ".mypy_cache",
  ".ruff_cache",
  ".cache",
  "output",
  "outputs",
  "logs",
  "tmp-events.jsonl"
)

$results = @()
foreach ($path in $safeTopLevelPaths) {
  $results += Remove-ManagedPath $path
}

$generatedDirs = Get-ChildItem -LiteralPath $root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -in @("__pycache__") -or $_.Name -like ".pytest-*") -and
    -not (Test-ExcludedRecursivePath $_.FullName)
  }

foreach ($dir in $generatedDirs) {
  $relative = Get-RepoRelativePath $dir.FullName
  $results += Remove-ManagedPath $relative
}

$logFiles = Get-ChildItem -LiteralPath $root -Force -File -Filter "*.log" -ErrorAction SilentlyContinue
foreach ($file in $logFiles) {
  $relative = Get-RepoRelativePath $file.FullName
  $results += Remove-ManagedPath $relative
}

$results | Where-Object { $_ -ne $null }
