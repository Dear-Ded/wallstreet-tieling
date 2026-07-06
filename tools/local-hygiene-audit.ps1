param(
  [switch]$Json
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Get-PathSizeMb {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return 0 }
  $item = Get-Item -LiteralPath $Path -Force
  if (-not $item.PSIsContainer) {
    return [math]::Round($item.Length / 1MB, 2)
  }
  $sum = (Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum
  return [math]::Round(($sum / 1MB), 2)
}

$managedLocalPaths = @(
  ".tmp",
  ".pytest_cache",
  ".coverage",
  ".mypy_cache",
  ".ruff_cache",
  "output",
  "outputs",
  "logs",
  "tmp-events.jsonl",
  ".cache",
  ".codex-autonomous",
  ".workbuddy",
  ".colab",
  "config/datasources_qyyjt.yaml",
  "node_modules",
  "package-lock.json",
  "deliverables",
  "audit_reports"
)

$pathRows = foreach ($path in $managedLocalPaths) {
  [pscustomobject]@{
    path = $path
    exists = Test-Path -LiteralPath $path
    size_mb = Get-PathSizeMb $path
  }
}

$gitStatus = @(git status --short)
$ignoredStatus = @(git status --ignored --short | Where-Object { $_ -like "!! *" })
$worktreeRows = @()
$worktreePaths = git worktree list --porcelain | ForEach-Object {
  if ($_ -like "worktree *") { $_.Substring(9) }
}
foreach ($worktreePath in $worktreePaths) {
  $status = @(git -C $worktreePath status --porcelain 2>$null)
  $worktreeRows += [pscustomobject]@{
    path = $worktreePath
    dirty = $status.Count -gt 0
    dirty_count = $status.Count
  }
}

$payload = [pscustomobject]@{
  type = "local_hygiene_audit"
  root = $root
  git_clean = $gitStatus.Count -eq 0
  git_status_count = $gitStatus.Count
  ignored_count = $ignoredStatus.Count
  managed_paths = $pathRows
  worktrees = $worktreeRows
  dirty_worktree_count = @($worktreeRows | Where-Object { $_.dirty }).Count
  clean_aux_worktree_count = @($worktreeRows | Where-Object { -not $_.dirty -and $_.path -ne $root }).Count
}

if ($Json) {
  $payload | ConvertTo-Json -Depth 6
} else {
  $payload
}
