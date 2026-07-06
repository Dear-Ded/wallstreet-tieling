param(
  [switch]$Json
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Normalize-PathForCompare {
  param([string]$Path)
  return ([IO.Path]::GetFullPath($Path)).TrimEnd("\", "/").Replace("\", "/")
}

$normalizedRoot = Normalize-PathForCompare $root

function Get-WorktreePaths {
  git worktree list --porcelain | ForEach-Object {
    if ($_ -like "worktree *") { $_.Substring(9) }
  }
}

function Get-Classification {
  param([string]$Path, [string]$Name, [int]$DirtyCount, [string]$Files)

  if ((Normalize-PathForCompare $Path) -eq $normalizedRoot) { return "primary-worktree" }
  if ($DirtyCount -eq 0) { return "remove-candidate-clean" }
  if ($Path -like "*deliverables/beautification-helper-codex-worktrees*" -or $Name -like "beautification-*") {
    return "beautification-artifact-review"
  }
  if ($Name -in @("contract-preservation-sweep", "p0-agent-delivery-contract-audit", "runtime-contract-drift-audit-p0", "runtime-agent-release-closure-p0", "runtime-acceptance-closure-p0")) {
    return "migration-candidate-runtime-contract"
  }
  if ($Name -like "release-*"-or $Name -like "runtime-release-*"-or $Files -match "(^|; )package\.json|README\.md|release|privacy|preflight") {
    return "migration-candidate-release-hygiene"
  }
  if ($Name -like "verifier-*" -or $Files -match "verify_report_bundle|test_investigation") {
    return "migration-candidate-verifier"
  }
  return "needs-manual-review"
}

function Get-RecommendedAction {
  param([string]$Classification, [int]$DirtyCount)

  switch ($Classification) {
    "primary-worktree" { return "keep-primary-clean" }
    "remove-candidate-clean" { return "remove-worktree" }
    "beautification-artifact-review" { return "review-for-report-ui-ideas-only" }
    "migration-candidate-runtime-contract" { return "diff-and-merge-runtime-contract-changes" }
    "migration-candidate-release-hygiene" { return "diff-and-merge-release-hygiene-changes" }
    "migration-candidate-verifier" { return "diff-and-merge-verifier-changes" }
    default {
      if ($DirtyCount -gt 0) { return "manual-review-before-delete" }
      return "remove-worktree"
    }
  }
}

$rows = foreach ($path in Get-WorktreePaths) {
  $branch = (git -C $path branch --show-current 2>$null)
  if (-not $branch) { $branch = "(detached)" }
  $status = @(git -C $path status --porcelain 2>$null)
  $files = @($status | ForEach-Object { $_.Substring(3) })
  $name = Split-Path $path -Leaf
  $filesText = $files -join "; "
  [pscustomobject]@{
    name = $name
    path = $path
    branch = $branch
    dirty_count = $status.Count
    classification = Get-Classification $path $name $status.Count $filesText
    recommended_action = Get-RecommendedAction (Get-Classification $path $name $status.Count $filesText) $status.Count
    files = $files
  }
}

if ($Json) {
  $rows | ConvertTo-Json -Depth 5
} else {
  $rows | Format-Table name, branch, dirty_count, classification, recommended_action -AutoSize
}
