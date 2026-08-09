#Requires -Version 5.1
<#
.SYNOPSIS
  Validate staged WinSW service definitions (no admin / no SCM mutation).

.PARAMETER OutDir
  Native payload root containing runtime\winsw
#>
param(
  [string]$OutDir = "",
  # Installer payloads must keep __INSTALLROOT__/__PROGRAMDATA__ until first-run bootstrap.
  [switch]$ExpectPlaceholders
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist\native-windows" }
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
$WinSwRoot = Join-Path $OutDir "runtime\winsw"

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

if (-not (Test-Path -LiteralPath (Join-Path $WinSwRoot "WinSW-x64.exe"))) {
  throw "Missing WinSW staging - run scripts\package_winsw_services.ps1"
}

$expectedDepends = @{
  "mediarec-api"        = @("mediarec-postgres", "mediarec-redis")
  "mediarec-worker"     = @("mediarec-postgres", "mediarec-redis")
  "mediarec-scheduler"  = @("mediarec-redis", "mediarec-worker")
}

foreach ($id in $ServiceIds) {
  Write-Step "Checking $id"
  $exe = Join-Path $WinSwRoot "$id.exe"
  $xmlPath = Join-Path $WinSwRoot "$id.xml"
  if (-not (Test-Path -LiteralPath $exe)) { throw "Missing $exe" }
  if (-not (Test-Path -LiteralPath $xmlPath)) { throw "Missing $xmlPath" }

  $raw = Get-Content -LiteralPath $xmlPath -Raw
  $hasPlaceholders = ($raw -match "__INSTALLROOT__" -or $raw -match "__PROGRAMDATA__")
  if ($ExpectPlaceholders) {
    if (-not $hasPlaceholders) {
      throw "$id.xml must keep __INSTALLROOT__/__PROGRAMDATA__ placeholders for installer payloads"
    }
  } elseif ($hasPlaceholders) {
    throw "$id.xml still contains unsubstituted placeholders"
  }

  try {
    [xml]$doc = $raw
  } catch {
    throw "$id.xml is not well-formed XML: $_"
  }

  $sid = $doc.service.id
  if ($sid -ne $id) {
    throw "$id.xml service id mismatch: $sid"
  }

  # Recovery hooks present
  $failures = @($doc.service.onfailure)
  if ($failures.Count -lt 1) {
    throw "$id.xml missing onfailure recovery"
  }

  if ($expectedDepends.ContainsKey($id)) {
    $deps = @($doc.service.depend) | ForEach-Object { "$_" }
    foreach ($need in $expectedDepends[$id]) {
      if ($deps -notcontains $need) {
        throw "$id.xml missing depend: $need (have: $($deps -join ', '))"
      }
    }
  }
}

# Source repo XMLs should still exist and parse
Write-Step "Checking repo templates under installer\services"
Get-ChildItem (Join-Path $RepoRoot "installer\services\*.xml") | ForEach-Object {
  [xml]$null = Get-Content -LiteralPath $_.FullName -Raw
}

Write-Host ""
Write-Host "WinSW service verification passed ($($ServiceIds.Count) services)." -ForegroundColor Green
Write-Host "  Staged: $WinSwRoot"
