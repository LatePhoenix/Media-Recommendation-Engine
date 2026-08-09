#Requires -Version 5.1
<#
.SYNOPSIS
  Build the dist\native-windows payload required by the native Inno Setup installer.

.DESCRIPTION
  Runs Python / Postgres / Redis / WinSW / web packaging scripts, then verifies critical paths.
  Does not compile the .iss (run ISCC separately).

.PARAMETER SkipDownload
  Pass through to package scripts that support it (reuse caches).

.PARAMETER SkipPostgres
  Skip the large Postgres download/extract (use existing staged tree).
#>
param(
  [switch]$SkipDownload,
  [switch]$SkipPostgres,
  [switch]$SkipPython,
  [switch]$SkipRedis,
  [switch]$SkipWeb
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $RepoRoot "dist\native-windows"
$DataRoot = Join-Path $RepoRoot "dist\native-windows-data"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

Set-Location $RepoRoot

if (-not $SkipWeb) {
  Write-Step "Web UI (Vite production dist)"
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_web_dist.ps1 -OutDir $OutDir
  if ($LASTEXITCODE -ne 0) { throw "package_web_dist.ps1 failed" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_web_dist.ps1 -OutDir $OutDir
  if ($LASTEXITCODE -ne 0) { throw "verify_web_dist.ps1 failed" }
}

if (-not $SkipPython) {
  Write-Step "Python runtime"
  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\package_python_runtime.ps1", "-OutDir", $OutDir)
  if ($SkipDownload) { $args += "-SkipDownload" }
  & powershell @args
  if ($LASTEXITCODE -ne 0) { throw "package_python_runtime.ps1 failed" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_python_runtime.ps1 -OutDir $OutDir
  if ($LASTEXITCODE -ne 0) { throw "verify_python_runtime.ps1 failed" }
}

if (-not $SkipPostgres) {
  Write-Step "PostgreSQL + pgvector"
  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\package_postgres_windows.ps1", "-OutDir", $OutDir)
  if ($SkipDownload) { $args += "-SkipDownload" }
  & powershell @args
  if ($LASTEXITCODE -ne 0) { throw "package_postgres_windows.ps1 failed" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_pgvector_windows.ps1 -OutDir $OutDir
  if ($LASTEXITCODE -ne 0) { throw "verify_pgvector_windows.ps1 failed" }
}

if (-not $SkipRedis) {
  Write-Step "Redis + WinSW binary"
  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\package_redis_windows.ps1", "-OutDir", $OutDir)
  if ($SkipDownload) { $args += "-SkipDownload" }
  & powershell @args
  if ($LASTEXITCODE -ne 0) { throw "package_redis_windows.ps1 failed" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_redis_windows.ps1 -OutDir $OutDir
  if ($LASTEXITCODE -ne 0) { throw "verify_redis_windows.ps1 failed" }
}

Write-Step "WinSW service definitions"
& powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package_winsw_services.ps1 `
  -OutDir $OutDir -InstallRoot $OutDir -DataRoot $DataRoot
if ($LASTEXITCODE -ne 0) { throw "package_winsw_services.ps1 failed" }
& powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_winsw_services.ps1 -OutDir $OutDir
if ($LASTEXITCODE -ne 0) { throw "verify_winsw_services.ps1 failed" }

$required = @(
  "runtime\python\python.exe",
  "runtime\postgres\bin\postgres.exe",
  "runtime\postgres\lib\vector.dll",
  "runtime\redis\redis-server.exe",
  "runtime\winsw\mediarec-api.exe",
  "runtime\winsw\mediarec-api.xml",
  "app\api\app\launch.py",
  "app\packages",
  "app\workers",
  "app\web\index.html"
)
foreach ($rel in $required) {
  $p = Join-Path $OutDir $rel
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Payload incomplete: missing $p"
  }
}

Write-Host ""
Write-Host "Native installer payload ready: $OutDir" -ForegroundColor Green
Write-Host "Compile with:"
Write-Host "  & `"`$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe`" `"/DMyAppVersion=`$((Get-Content installer\VERSION -Raw).Trim())`" installer\MediaRecommendationEngine.iss"
