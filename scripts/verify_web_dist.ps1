#Requires -Version 5.1
<#
.SYNOPSIS
  Verify staged native web UI payload (app\web\index.html).
#>
param(
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$index = Join-Path $OutDir "app\web\index.html"
if (-not (Test-Path -LiteralPath $index)) {
  Write-Error "Missing $index - run scripts\package_web_dist.ps1"
  exit 1
}

$assets = Join-Path $OutDir "app\web\assets"
if (-not (Test-Path -LiteralPath $assets)) {
  Write-Warning "No assets/ folder under app\web (unexpected for Vite builds)"
}

Write-Host "OK: web UI present at $index" -ForegroundColor Green
exit 0
