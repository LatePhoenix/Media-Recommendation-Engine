#Requires -Version 5.1
<#
.SYNOPSIS
  Stage WinSW executables and substituted service XMLs under dist/native-windows/runtime/winsw.

.PARAMETER OutDir
  Native payload root

.PARAMETER InstallRoot
  Value for __INSTALLROOT__ (default: OutDir absolute path — fine for local smoke)

.PARAMETER DataRoot
  Value for __PROGRAMDATA__ (default: <repo>\dist\native-windows-data)
#>
param(
  [string]$OutDir = "",
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [string]$WinSwTag = "v2.12.0"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist\native-windows" }
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
if (-not $InstallRoot) { $InstallRoot = $OutDir }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
if (-not $DataRoot) {
  $candidate = Join-Path $RepoRoot "dist\native-windows-data"
  if (Test-Path (Join-Path $env:ProgramData "MediaRecommendationEngine")) {
    $DataRoot = Join-Path $env:ProgramData "MediaRecommendationEngine"
  } else {
    $DataRoot = $candidate
  }
}
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

# Prefer repo dist\cache when developing; under an installed tree use runtime\winsw as the source of WinSW.
$CacheDir = Join-Path $RepoRoot "dist\cache"
$WinSwCache = Join-Path $CacheDir "WinSW-x64.exe"
$WinSwUrl = "https://github.com/winsw/winsw/releases/download/$WinSwTag/WinSW-x64.exe"
$WinSwRoot = Join-Path $OutDir "runtime\winsw"
$ServicesSrc = Join-Path $RepoRoot "installer\services"
if (-not (Test-Path -LiteralPath $ServicesSrc)) {
  $ServicesSrc = Join-Path $InstallRoot "services"
}

$ServiceIds = @(
  "mediarec-postgres",
  "mediarec-redis",
  "mediarec-api",
  "mediarec-worker",
  "mediarec-scheduler"
)

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

Ensure-Dir $CacheDir
Ensure-Dir $WinSwRoot

$existingWinsw = Join-Path $WinSwRoot "WinSW-x64.exe"
if (-not (Test-Path -LiteralPath $WinSwCache) -and (Test-Path -LiteralPath $existingWinsw)) {
  $WinSwCache = $existingWinsw
}

if (-not (Test-Path -LiteralPath $WinSwCache)) {
  Write-Step "Downloading $WinSwUrl"
  Ensure-Dir $CacheDir
  $WinSwCache = Join-Path $CacheDir "WinSW-x64.exe"
  Invoke-WebRequest -Uri $WinSwUrl -OutFile $WinSwCache -UseBasicParsing
}

Copy-Item -LiteralPath $WinSwCache -Destination (Join-Path $WinSwRoot "WinSW-x64.exe") -Force

foreach ($id in $ServiceIds) {
  $srcXml = Join-Path $ServicesSrc "$id.xml"
  if (-not (Test-Path -LiteralPath $srcXml)) {
    throw "Missing service definition: $srcXml"
  }
  Write-Step "Staging $id"
  Copy-Item -LiteralPath $WinSwCache -Destination (Join-Path $WinSwRoot "$id.exe") -Force
  $xml = Get-Content -LiteralPath $srcXml -Raw
  $xml = $xml.Replace("__INSTALLROOT__", $InstallRoot)
  $xml = $xml.Replace("__PROGRAMDATA__", $DataRoot)
  Set-Content -LiteralPath (Join-Path $WinSwRoot "$id.xml") -Value $xml -Encoding utf8
}

$meta = @"
winsw_tag=$WinSwTag
install_root=$InstallRoot
program_data=$DataRoot
services=$($ServiceIds -join ',')
built_utc=$((Get-Date).ToUniversalTime().ToString("o"))
"@
Set-Content -LiteralPath (Join-Path $OutDir "winsw-services.meta.txt") -Value $meta -Encoding utf8

Write-Host ""
Write-Host "WinSW services staged at $WinSwRoot" -ForegroundColor Green
Write-Host "Next: .\scripts\verify_winsw_services.ps1 -OutDir `"$OutDir`""
