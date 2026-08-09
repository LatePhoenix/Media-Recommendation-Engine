# DEPRECATED for Windows product installs — native Setup.exe + WinSW replaced this.
# Kept only as a local Compose convenience if you still use Docker Desktop for development.
# Stop-MediaRec.ps1
# Stops the full stack via Docker Compose (mirrors Start-MediaRec.ps1 root discovery).

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

# Prefer a sanitized LOCALAPPDATA compose copy if Start created one.
$sanitized = Join-Path $env:LOCALAPPDATA "MediaRecommendationEngine\docker-compose.yml"
if (Test-Path $sanitized) {
  $Compose = $sanitized
}

Write-Host "Media Recommendation Engine — Stop" -ForegroundColor Cyan
Write-Host "=================================="

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Warning "Docker was not found on PATH."
  Read-Host "Press Enter to close"
  exit 1
}

if (-not (Test-Path $Compose)) {
  Write-Warning "Compose file not found at $Compose"
  Read-Host "Press Enter to close"
  exit 1
}

Write-Host "Stopping containers..." -ForegroundColor Yellow
docker compose -f $Compose down
if ($LASTEXITCODE -ne 0) {
  Write-Warning "docker compose down failed. Review the output above."
  Read-Host "Press Enter to close"
  exit 1
}

Write-Host "Stopped." -ForegroundColor Green
