#Requires -Version 5.1
<#
.SYNOPSIS
  Build the Vite web UI and stage it into the native Windows payload (app\web).

.DESCRIPTION
  Production build uses an empty VITE_API_BASE_URL so the UI talks same-origin to
  FastAPI on :8000 (docs/packaging/adr-serve-web.md).

.PARAMETER OutDir
  Payload root. Default: <repo>\dist\native-windows

.PARAMETER SkipInstall
  Skip npm ci (reuse existing node_modules).
#>
param(
  [string]$OutDir = "",
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$WebDir = Join-Path $RepoRoot "apps\web"
$Dest = Join-Path $OutDir "app\web"
$Dist = Join-Path $WebDir "dist"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm not found on PATH. Install Node.js 20+ to build the web UI."
}

Push-Location $WebDir
try {
  if (-not $SkipInstall) {
    Write-Step "npm ci (apps/web)"
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
  }

  Write-Step "vite build (same-origin API base)"
  # Explicit empty string — do not omit the var (undefined would bake localhost:8000).
  $env:VITE_API_BASE_URL = ""
  # Use npm exec so local node_modules/.bin is used even if PATH is thin.
  npm exec -- tsc -b
  if ($LASTEXITCODE -ne 0) { throw "tsc -b failed (run without -SkipInstall if deps are incomplete)" }
  npm exec -- vite build
  if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
}
finally {
  Pop-Location
}

if (-not (Test-Path -LiteralPath (Join-Path $Dist "index.html"))) {
  throw "Web build missing index.html under $Dist"
}

Write-Step "Stage $Dest"
if (Test-Path -LiteralPath $Dest) {
  Remove-Item -LiteralPath $Dest -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
Copy-Item -LiteralPath $Dist -Destination $Dest -Recurse -Force

Write-Host "Web UI staged: $Dest" -ForegroundColor Green
