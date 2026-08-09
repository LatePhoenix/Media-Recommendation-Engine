#Requires -Version 5.1
<#
.SYNOPSIS
  Install / start / stop / uninstall all Media Recommendation Engine WinSW services.

.DESCRIPTION
  Requires an elevated PowerShell session. Operates on staged copies under
  <InstallRoot>\runtime\winsw (default: dist\native-windows).

.PARAMETER Action
  install | start | stop | uninstall | status

.PARAMETER InstallRoot
  Root containing runtime\winsw
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("install", "start", "stop", "uninstall", "status")]
  [string]$Action,

  [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $InstallRoot) { $InstallRoot = Join-Path $RepoRoot "dist\native-windows" }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$WinSwRoot = Join-Path $InstallRoot "runtime\winsw"

# Order matters for start/stop.
$StartOrder = @(
  "mediarec-postgres",
  "mediarec-redis",
  "mediarec-api",
  "mediarec-worker",
  "mediarec-scheduler"
)
$StopOrder = [System.Collections.ArrayList]@($StartOrder)
$StopOrder.Reverse()

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Action '$Action' requires an elevated PowerShell (Run as administrator)."
  }
}

if ($Action -ne "status") {
  Assert-Admin
}

if (-not (Test-Path -LiteralPath $WinSwRoot)) {
  throw "Missing $WinSwRoot - run scripts\package_winsw_services.ps1 first"
}

$order = if ($Action -eq "stop" -or $Action -eq "uninstall") { @($StopOrder) } else { $StartOrder }

Push-Location $WinSwRoot
try {
  foreach ($id in $order) {
    $exe = Join-Path $WinSwRoot "$id.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
      throw "Missing $exe"
    }
    Write-Step "$Action $id"
    switch ($Action) {
      "install"   { & $exe install; if ($LASTEXITCODE -ne 0) { throw "$id install failed" } }
      "start"     { & $exe start; if ($LASTEXITCODE -ne 0) { throw "$id start failed" } }
      "stop"      { & $exe stop; if ($LASTEXITCODE -ne 0) { Write-Host "warn: $id stop exit $LASTEXITCODE" -ForegroundColor Yellow } }
      "uninstall" {
        & $exe stop 2>$null | Out-Null
        & $exe uninstall
        if ($LASTEXITCODE -ne 0) { Write-Host "warn: $id uninstall exit $LASTEXITCODE" -ForegroundColor Yellow }
      }
      "status"    { & $exe status }
    }
  }
} finally {
  Pop-Location
}

if ($Action -eq "status" -or $Action -eq "start") {
  Write-Host ""
  Get-Service -Name "mediarec-*" -ErrorAction SilentlyContinue |
    Format-Table Name, Status, StartType -AutoSize
}

Write-Host "Done: $Action" -ForegroundColor Green
