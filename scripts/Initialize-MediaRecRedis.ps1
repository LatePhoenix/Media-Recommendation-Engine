#Requires -Version 5.1
<#
.SYNOPSIS
  Write ProgramData-style redis.conf from the template (first-install / upgrade-safe).

.DESCRIPTION
  Config is written to <DataRoot>\redis\redis.conf with paths relative to that
  working directory (required for MSYS-built redis-server on Windows).

.PARAMETER InstallRoot
  Program Files-style root containing runtime\redis

.PARAMETER DataRoot
  ProgramData-style root (redis\, logs\, config\)

.PARAMETER Password
  requirepass value (defaults to env REDIS_PASSWORD / mediarec-redis)

.PARAMETER Port
  Listen port (default 6379)

.PARAMETER InstallService
  If set, runs mediarec-redis.exe install/start (requires elevation)

.PARAMETER Force
  Rewrite redis.conf even if it already exists (default: preserve on upgrades)
#>
param(
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [string]$Password = "",
  [int]$Port = 6379,
  [switch]$InstallService,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $InstallRoot) { $InstallRoot = Join-Path $RepoRoot "dist\native-windows" }
if (-not $DataRoot) { $DataRoot = Join-Path $RepoRoot "dist\native-windows-data" }

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

$RedisBin = Join-Path $InstallRoot "runtime\redis"
$Template = Join-Path $RedisBin "redis.conf.template"
if (-not (Test-Path -LiteralPath $Template)) {
  $Template = Join-Path $RepoRoot "installer\redis\redis.conf.template"
}
$Server = Join-Path $RedisBin "redis-server.exe"
$WorkDir = Join-Path $DataRoot "redis"
$DataDir = Join-Path $WorkDir "data"
$LogDir = Join-Path $DataRoot "logs\mediarec-redis"
$ConfigFile = Join-Path $WorkDir "redis.conf"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

if (-not (Test-Path -LiteralPath $Server)) {
  throw "Missing $Server - run scripts\package_redis_windows.ps1 first"
}
if (-not (Test-Path -LiteralPath $Template)) {
  throw "Missing redis.conf.template"
}

if (-not $Password) {
  if ($env:REDIS_PASSWORD) { $Password = $env:REDIS_PASSWORD }
  else { $Password = "mediarec-redis" }
}

Ensure-Dir $DataDir
Ensure-Dir $LogDir
Ensure-Dir $WorkDir
Ensure-Dir (Join-Path $DataRoot "config")

if ((Test-Path -LiteralPath $ConfigFile) -and -not $Force) {
  Write-Step "Preserving existing $ConfigFile (use -Force to regenerate)"
} else {
  Write-Step "Writing $ConfigFile"
  $raw = Get-Content -LiteralPath $Template -Raw
  $raw = $raw.Replace("{{REDIS_PASSWORD}}", $Password)
  $raw = $raw.Replace("{{PORT}}", "$Port")
  Set-Content -LiteralPath $ConfigFile -Value $raw -Encoding ascii
}

# Pointer for operators (absolute path); Redis itself uses WorkDir\redis.conf.
Set-Content -LiteralPath (Join-Path $DataRoot "config\redis.conf.path.txt") -Value $ConfigFile -Encoding utf8

$WinSwDir = Join-Path $InstallRoot "runtime\winsw"
$XmlSrc = Join-Path $WinSwDir "mediarec-redis.xml"
if (-not (Test-Path -LiteralPath $XmlSrc)) {
  $XmlSrc = Join-Path $RepoRoot "installer\services\mediarec-redis.xml"
}
if (Test-Path -LiteralPath $XmlSrc) {
  Ensure-Dir $WinSwDir
  $xml = Get-Content -LiteralPath $XmlSrc -Raw
  $xml = $xml.Replace("__PROGRAMDATA__", $DataRoot)
  Set-Content -LiteralPath (Join-Path $WinSwDir "mediarec-redis.xml") -Value $xml -Encoding utf8
}

if ($InstallService) {
  $svcExe = Join-Path $WinSwDir "mediarec-redis.exe"
  if (-not (Test-Path -LiteralPath $svcExe)) {
    throw "Missing $svcExe - package Redis/WinSW first"
  }
  Write-Step "Installing Windows service mediarec-redis (requires admin)"
  Push-Location $WinSwDir
  try {
    & $svcExe install
    if ($LASTEXITCODE -ne 0) { throw "WinSW install failed (exit $LASTEXITCODE)" }
    & $svcExe start
    if ($LASTEXITCODE -ne 0) { throw "WinSW start failed (exit $LASTEXITCODE)" }
  } finally {
    Pop-Location
  }
}

Write-Host "Redis config ready: $ConfigFile" -ForegroundColor Green
Write-Host "Start: `"$Server`" redis.conf   (WorkingDirectory=$WorkDir)"
