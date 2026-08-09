#Requires -Version 5.1
<#
.SYNOPSIS
  Post-install smoke checks for a native Windows Media Recommendation Engine install.

.DESCRIPTION
  Implements the automated subset of docs/packaging/test-matrix.md (services, payload,
  health, pgvector when possible). Does not reboot, upgrade, or uninstall.

.PARAMETER InstallRoot
  Program Files install root

.PARAMETER DataRoot
  ProgramData root

.PARAMETER FailFast
  Exit on first failure (default: collect all failures)

.EXAMPLE
  .\scripts\Verify-NativeInstall.ps1
  .\scripts\Verify-NativeInstall.ps1 -InstallRoot "C:\Program Files\Media Recommendation Engine"
#>
param(
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [switch]$FailFast
)

$ErrorActionPreference = "Continue"
$failures = New-Object System.Collections.Generic.List[string]
$passes = 0

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
  if ($Ok) {
    $script:passes++
    Write-Host "[PASS] $Name$(if ($Detail) { " - $Detail" })" -ForegroundColor Green
  } else {
    $script:failures.Add($Name)
    Write-Host "[FAIL] $Name$(if ($Detail) { " - $Detail" })" -ForegroundColor Red
    if ($FailFast) { throw "Verify failed: $Name" }
  }
}

if (-not $InstallRoot) {
  $InstallRoot = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}
if (-not $DataRoot) {
  $DataRoot = Join-Path $env:ProgramData "MediaRecommendationEngine"
}

Write-Host "InstallRoot: $InstallRoot"
Write-Host "DataRoot:    $DataRoot"
Write-Host ""

# Payload
$payload = @(
  "runtime\python\python.exe",
  "runtime\postgres\bin\postgres.exe",
  "runtime\postgres\lib\vector.dll",
  "runtime\redis\redis-server.exe",
  "runtime\winsw\mediarec-api.exe",
  "app\api\app\launch.py",
  "app\web\index.html",
  "version.txt",
  "Open-MediaRec.url"
)
foreach ($rel in $payload) {
  $p = Join-Path $InstallRoot $rel
  Write-Check "payload:$rel" (Test-Path -LiteralPath $p) $p
}

# ProgramData essentials
Write-Check "data:config\.env" (Test-Path -LiteralPath (Join-Path $DataRoot "config\.env"))
Write-Check "data:postgres\data" (Test-Path -LiteralPath (Join-Path $DataRoot "postgres\data\PG_VERSION"))
Write-Check "data:redis\redis.conf" (Test-Path -LiteralPath (Join-Path $DataRoot "redis\redis.conf"))

# Services
$expected = @(
  "mediarec-postgres",
  "mediarec-redis",
  "mediarec-api",
  "mediarec-worker",
  "mediarec-scheduler"
)
foreach ($name in $expected) {
  $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
  if (-not $svc) {
    Write-Check "service:$name" $false "not registered"
  } else {
    Write-Check "service:$name" ($svc.Status -eq "Running") "$($svc.Status) / $($svc.StartType)"
  }
}

# PostgreSQL refuses to run under an admin account. Assert the service logon is
# LocalService explicitly so the LocalSystem regression is caught by name, not just
# as a downstream "postgres not Running" symptom.
$pgSvc = Get-CimInstance Win32_Service -Filter "Name='mediarec-postgres'" -ErrorAction SilentlyContinue
if ($pgSvc) {
  Write-Check "service:mediarec-postgres:account" ($pgSvc.StartName -match "LOCAL SERVICE|LocalService") $pgSvc.StartName
}

# HTTP
function Test-Http([string]$Name, [string]$Url, [scriptblock]$Assert) {
  try {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
    $ok = & $Assert $resp
    Write-Check $Name $ok "HTTP $($resp.StatusCode)"
  } catch {
    Write-Check $Name $false "$_"
  }
}

Test-Http "http:/health" "http://127.0.0.1:8000/health" {
  param($r)
  ($r.StatusCode -eq 200) -and ($r.Content -match '"status"\s*:\s*"ok"')
}

Test-Http "http:/health/ready" "http://127.0.0.1:8000/health/ready" {
  param($r)
  ($r.StatusCode -eq 200) -and ($r.Content -match '"status"\s*:\s*"ready"')
}

Test-Http "http:ui-index" "http://127.0.0.1:8000/" {
  param($r)
  ($r.StatusCode -eq 200) -and ($r.Content -match '(?i)<html|<!doctype')
}

# pg_isready
$pgIsReady = Join-Path $InstallRoot "runtime\postgres\bin\pg_isready.exe"
if (Test-Path -LiteralPath $pgIsReady) {
  & $pgIsReady -h 127.0.0.1 -p 5432 | Out-Null
  Write-Check "postgres:pg_isready" ($LASTEXITCODE -eq 0) "exit=$LASTEXITCODE"
} else {
  Write-Check "postgres:pg_isready" $false "binary missing"
}

# pgvector (best-effort)
$psql = Join-Path $InstallRoot "runtime\postgres\bin\psql.exe"
$envFile = Join-Path $DataRoot "config\.env"
if ((Test-Path -LiteralPath $psql) -and (Test-Path -LiteralPath $envFile)) {
  $pgPass = $null
  if ((Get-Content -LiteralPath $envFile -Raw) -match "(?m)^POSTGRES_PASSWORD=(.+)$") {
    $pgPass = $Matches[1].Trim()
  }
  if ($pgPass) {
    $prev = $env:PGPASSWORD
    $env:PGPASSWORD = $pgPass
    try {
      $out = & $psql -h 127.0.0.1 -p 5432 -U mediarec -d mediarec -tAc "SELECT extname FROM pg_extension WHERE extname='vector';" 2>&1
      Write-Check "postgres:pgvector" (($LASTEXITCODE -eq 0) -and (($out | Out-String) -match "vector")) ("$out".Trim())
    } finally {
      if ($null -eq $prev) { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
      else { $env:PGPASSWORD = $prev }
    }
  } else {
    Write-Check "postgres:pgvector" $false "POSTGRES_PASSWORD not found in .env"
  }
} else {
  Write-Host "[SKIP] postgres:pgvector (psql or .env missing)" -ForegroundColor Yellow
}

# install-state / version alignment
$verFile = Join-Path $InstallRoot "version.txt"
$stateFile = Join-Path $DataRoot "config\install-state.json"
if ((Test-Path $verFile) -and (Test-Path $stateFile)) {
  $ver = (Get-Content -LiteralPath $verFile -Raw).Trim()
  try {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    Write-Check "install-state:version" ($state.app_version -eq $ver) "file=$ver state=$($state.app_version)"
  } catch {
    Write-Check "install-state:version" $false "$_"
  }
}

Write-Host ""
if ($failures.Count -eq 0) {
  Write-Host "Verify-NativeInstall: ALL PASS ($passes checks)" -ForegroundColor Green
  exit 0
}

Write-Host "Verify-NativeInstall: $($failures.Count) FAIL / $passes PASS" -ForegroundColor Red
Write-Host ("Failed: " + ($failures -join ", "))
Write-Host "See docs/packaging/test-matrix.md for full manual coverage."
exit 1
