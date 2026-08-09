# DEPRECATED for Windows product installs — native Setup.exe + WinSW replaced this.
# Kept only as a local Compose convenience if you still use Docker Desktop for development.
# Start-MediaRec.ps1
# Launches the full stack via Docker Compose, waits for the web UI, opens it.
# Uses the base compose file only (image contents, no host bind mounts) so
# installs under Program Files do not hit ACL-denied node_modules mountpoints.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Install layout: script next to apps/ + infra/. Repo layout: script under installer/.
if (Test-Path (Join-Path $ScriptDir "infra\docker-compose.yml")) {
  $Root = $ScriptDir
} elseif (Test-Path (Join-Path $ScriptDir "..\infra\docker-compose.yml")) {
  $Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path
} else {
  $Root = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}
$Compose = Join-Path $Root "infra\docker-compose.yml"
$WebUrl = "http://localhost:5173"

# If an older install still has Program Files bind mounts, run from a writable
# sanitized compose copy so /app/node_modules mountpoint mkdir cannot fail.
function Get-SanitizedComposePath {
  param([string]$ComposePath, [string]$RootPath)
  if (-not (Test-Path $ComposePath)) { return $ComposePath }
  $raw = Get-Content -LiteralPath $ComposePath -Raw
  if ($raw -notmatch '(?m)^\s*-\s*/app/node_modules\s*$' -and $raw -notmatch '(?m)^\s*-\s*\.\./apps/web:/app\s*$') {
    return $ComposePath
  }
  $outDir = Join-Path $env:LOCALAPPDATA "MediaRecommendationEngine"
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $out = Join-Path $outDir "docker-compose.yml"
  # Prefer the fixed compose shipped next to this script (repo or patched install).
  $candidates = @(
    (Join-Path $ScriptDir "..\infra\docker-compose.yml"),
    (Join-Path $ScriptDir "infra\docker-compose.yml"),
    (Join-Path $RootPath "infra\docker-compose.dev.yml")
  )
  foreach ($c in $candidates) {
    if (-not (Test-Path $c)) { continue }
    $candRaw = Get-Content -LiteralPath $c -Raw
    if ($candRaw -match '(?m)^\s*-\s*/app/node_modules\s*$') { continue }
    if ($c -like '*.dev.yml') { continue }
    Copy-Item -LiteralPath $c -Destination $out -Force
    return $out
  }
  # Last resort: strip app bind mounts / anonymous node_modules from the installed file.
  $lines = Get-Content -LiteralPath $ComposePath
  $filtered = foreach ($line in $lines) {
    if ($line -match '^\s*-\s*\.\./apps/(web|api):') { continue }
    if ($line -match '^\s*-\s*\.\./(packages|workers):') { continue }
    if ($line -match '^\s*-\s*/app/node_modules\s*$') { continue }
    $line
  }
  Set-Content -LiteralPath $out -Value $filtered -Encoding utf8
  return $out
}
$Compose = Get-SanitizedComposePath -ComposePath $Compose -RootPath $Root

function Test-Docker {
  try { docker version --format '{{.Server.Version}}' | Out-Null; return $true }
  catch { return $false }
}

Write-Host "Media Recommendation Engine" -ForegroundColor Cyan
Write-Host "==========================="

$setupScript = Join-Path $Root "setup-env.ps1"
if (-not (Test-Path $setupScript)) { $setupScript = Join-Path $ScriptDir "setup-env.ps1" }
if (Test-Path $setupScript) {
  try { & $setupScript } catch { Write-Warning "setup-env.ps1: $($_.Exception.Message)" }
}
if (-not (Test-Path (Join-Path $Root ".env"))) {
  Write-Warning "Missing .env in $Root. Copy .env.example to .env and set API_SECRET_KEY, or re-run setup-env.ps1."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Warning "Docker was not found on PATH. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and try again."
  Read-Host "Press Enter to close"
  exit 1
}

if (-not (Test-Docker)) {
  Write-Host "Docker Desktop is not running. Attempting to start it..." -ForegroundColor Yellow
  $dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  if (Test-Path $dockerDesktop) { Start-Process $dockerDesktop | Out-Null }
  Write-Host "Waiting for the Docker engine to become ready..."
  $tries = 0
  while (-not (Test-Docker)) {
    Start-Sleep -Seconds 3
    $tries++
    if ($tries -ge 40) {
      Write-Warning "Docker engine did not start in time. Start Docker Desktop manually, then retry."
      Read-Host "Press Enter to close"
      exit 1
    }
  }
}

Write-Host "Building and starting containers (first run may take several minutes)..." -ForegroundColor Green
# Recreate so old bind-mount containers (from prior installs) are replaced.
docker compose -f $Compose up -d --build --force-recreate
if ($LASTEXITCODE -ne 0) {
  Write-Warning "docker compose failed. Review the output above."
  Read-Host "Press Enter to close"
  exit 1
}

Write-Host "Waiting for the web UI at $WebUrl ..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 3
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $ready = $true; break }
  } catch { Start-Sleep -Seconds 2 }
}

# API must be up for login/register; web HTML alone is not enough.
$ApiHealth = "http://localhost:8000/health"
Write-Host "Waiting for the API at $ApiHealth ..."
$apiReady = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri $ApiHealth -UseBasicParsing -TimeoutSec 3
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $apiReady = $true; break }
  } catch { Start-Sleep -Seconds 2 }
}

if ($ready -and $apiReady) {
  Write-Host "Ready. Opening $WebUrl" -ForegroundColor Green
  Start-Process $WebUrl
} elseif ($ready -and -not $apiReady) {
  Write-Warning "Web UI responded but the API at $ApiHealth did not. Login/register will fail until the API is healthy."
  Start-Process $WebUrl
} else {
  Write-Warning "The web UI did not respond yet. It may still be starting - open $WebUrl in your browser shortly."
}

Write-Host ""
Write-Host "  Web UI:   $WebUrl"
Write-Host "  API docs: http://localhost:8000/docs"
Write-Host "  Stop it:  use the 'Stop Media Recommendation Engine' shortcut"
