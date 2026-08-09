#Requires -Version 5.1
<#
.SYNOPSIS
  Collect a redacted support bundle for native Windows installs.

.PARAMETER InstallRoot
  Program Files install root

.PARAMETER DataRoot
  ProgramData root

.PARAMETER OutDir
  Where to write the zip (default: DataRoot\diagnostics)

.PARAMETER NonInteractive
  Do not prompt; print the zip path and exit (used by Start Menu VBS)
#>
param(
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [string]$OutDir = "",
  [switch]$NonInteractive
)

$ErrorActionPreference = "Continue"

if (-not $InstallRoot) {
  $InstallRoot = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}
if (-not $DataRoot) {
  $DataRoot = Join-Path $env:ProgramData "MediaRecommendationEngine"
}
if (-not $OutDir) {
  $OutDir = Join-Path $DataRoot "diagnostics"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stage = Join-Path $OutDir "bundle-$stamp"
New-Item -ItemType Directory -Force -Path $stage | Out-Null

function Write-File([string]$Name, [string]$Content) {
  if ($null -eq $Content) { $Content = "" }
  Set-Content -LiteralPath (Join-Path $stage $Name) -Value $Content -Encoding utf8
}

# Manifest / versions
$statePath = Join-Path $DataRoot "config\install-state.json"
$verPath = Join-Path $InstallRoot "version.txt"
$manifest = @(
  "collected_utc=$((Get-Date).ToUniversalTime().ToString('o'))",
  "install_root=$InstallRoot",
  "data_root=$DataRoot",
  "computer=$env:COMPUTERNAME",
  "user=$env:USERNAME",
  "os=$([System.Environment]::OSVersion.VersionString)"
)
if (Test-Path -LiteralPath $verPath) {
  $manifest += "app_version=$((Get-Content -LiteralPath $verPath -Raw).Trim())"
}
if (Test-Path -LiteralPath $statePath) {
  $manifest += "install_state:"
  $manifest += Get-Content -LiteralPath $statePath -Raw
}
Write-File "manifest.txt" ($manifest -join "`n")

# Service status (+ WinSW status when available)
try {
  $svc = Get-Service -Name "mediarec-*" -ErrorAction SilentlyContinue |
    Format-Table Name, Status, StartType -AutoSize |
    Out-String
} catch { $svc = "$_" }
$winsw = Join-Path $InstallRoot "runtime\winsw"
if (Test-Path $winsw) {
  $lines = @($svc, "", "WinSW status:")
  Get-ChildItem $winsw -Filter "mediarec-*.exe" | ForEach-Object {
    try {
      Push-Location $winsw
      $out = & $_.FullName status 2>&1 | Out-String
      Pop-Location
      $lines += "----- $($_.BaseName) -----"
      $lines += $out
    } catch {
      $lines += "$($_.BaseName): $_"
    }
  }
  $svc = $lines -join "`n"
}
Write-File "services.txt" $svc

# Ports
try {
  $ports = netstat -ano | Select-String ":5432 |:6379 |:8000 "
  Write-File "ports.txt" ($ports | Out-String)
} catch {
  Write-File "ports.txt" "$_"
}

# HTTP health
foreach ($pair in @(
    @{ Name = "health.json"; Url = "http://127.0.0.1:8000/health" },
    @{ Name = "health-ready.json"; Url = "http://127.0.0.1:8000/health/ready" }
  )) {
  try {
    $resp = Invoke-WebRequest -Uri $pair.Url -UseBasicParsing -TimeoutSec 5
    Write-File $pair.Name ("status=$($resp.StatusCode)`n$($resp.Content)")
  } catch {
    Write-File $pair.Name "error: $_"
  }
}

# DB readiness (pg_isready) when binaries exist
$pgIsReady = Join-Path $InstallRoot "runtime\postgres\bin\pg_isready.exe"
if (Test-Path -LiteralPath $pgIsReady) {
  try {
    $out = & $pgIsReady -h 127.0.0.1 -p 5432 2>&1 | Out-String
    Write-File "pg_isready.txt" ("exit=$LASTEXITCODE`n$out")
  } catch {
    Write-File "pg_isready.txt" "error: $_"
  }
} else {
  Write-File "pg_isready.txt" "pg_isready.exe not found under install root"
}

# Redis ping (best-effort; password from env file is not read into the bundle)
$redisCli = Join-Path $InstallRoot "runtime\redis\redis-cli.exe"
if (Test-Path -LiteralPath $redisCli) {
  try {
    # AUTH from ProgramData conf is not echoed; attempt unauthenticated ping for presence only.
    $out = & $redisCli -h 127.0.0.1 -p 6379 PING 2>&1 | Out-String
    Write-File "redis-ping.txt" ("exit=$LASTEXITCODE`n$out`n(note: NOAUTH expected if requirepass is set)")
  } catch {
    Write-File "redis-ping.txt" "error: $_"
  }
}

# Redacted config summary
$envFile = Join-Path $DataRoot "config\.env"
if (Test-Path -LiteralPath $envFile) {
  $redacted = Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match "^(API_SECRET_KEY|CREDENTIALS_FERNET_KEY|CREDENTIALS_FERNET_KEYS_OLD|POSTGRES_PASSWORD|REDIS_PASSWORD|DATABASE_URL|REDIS_URL)=") {
      $k = ($_ -split "=", 2)[0]
      "$k=***REDACTED***"
    } else { $_ }
  }
  Write-File "config-redacted.env" ($redacted -join "`n")
} else {
  Write-File "config-redacted.env" "missing: $envFile"
}

# Payload presence checklist
$checks = @(
  "runtime\python\python.exe",
  "runtime\postgres\bin\postgres.exe",
  "runtime\redis\redis-server.exe",
  "runtime\winsw\mediarec-api.exe",
  "app\api\app\launch.py",
  "app\web\index.html",
  "scripts\Initialize-NativeInstall.ps1"
) | ForEach-Object {
  $p = Join-Path $InstallRoot $_
  "$((Test-Path -LiteralPath $p))`t$_"
}
Write-File "payload-check.txt" ($checks -join "`n")

# Recent logs (last 200 lines from newest files per service folder)
$logRoot = Join-Path $DataRoot "logs"
if (Test-Path $logRoot) {
  Get-ChildItem $logRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $target = Join-Path $stage "logs-$($_.Name).txt"
    $files = Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    $chunks = @()
    foreach ($f in $files | Select-Object -First 3) {
      $chunks += "----- $($f.FullName) -----"
      $chunks += (Get-Content -LiteralPath $f.FullName -Tail 200 -ErrorAction SilentlyContinue)
    }
    Set-Content -LiteralPath $target -Value ($chunks -join "`n") -Encoding utf8
  }
}
# Redis workdir log (often under redis\data)
$redisLog = Join-Path $DataRoot "redis\data\redis.log"
if (Test-Path -LiteralPath $redisLog) {
  Write-File "logs-redis-data.txt" ((Get-Content -LiteralPath $redisLog -Tail 200) -join "`n")
}

$zip = Join-Path $OutDir "MediaRec-Diagnostics-$stamp.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
Remove-Item -LiteralPath $stage -Recurse -Force

Write-Host "Diagnostics written to:" -ForegroundColor Green
Write-Host "  $zip"

# Always record last path for Start Menu / support tools
$lastPath = Join-Path $OutDir "last-diagnostics-path.txt"
Set-Content -LiteralPath $lastPath -Value $zip -Encoding utf8

if (-not $NonInteractive) {
  Write-Host "Open that folder? (Y/N)"
  $ans = Read-Host
  if ($ans -match '^[Yy]') {
    Start-Process explorer.exe -ArgumentList "/select,`"$zip`""
  }
}
# NonInteractive: no prompts; Collect-Diagnostics.vbs opens Explorer via last-diagnostics-path.txt

