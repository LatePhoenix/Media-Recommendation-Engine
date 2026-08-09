#Requires -Version 5.1
<#
.SYNOPSIS
  Install / start / stop / uninstall all Media Recommendation Engine WinSW services.

.DESCRIPTION
  Requires an elevated PowerShell session. Operates on staged copies under
  <InstallRoot>\runtime\winsw (default: dist\native-windows).
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

# Postgres must not run as LocalSystem (PostgreSQL refuses admin accounts on Windows).
$LocalServiceIds = @("mediarec-postgres")

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

function Get-WinSwStatus([string]$Exe) {
  $raw = (& $Exe status 2>$null | Out-String).Trim()
  if (-not $raw) { return "Unknown" }
  return $raw
}

function Wait-ServiceGone([string]$Id, [int]$Seconds = 20) {
  for ($i = 0; $i -lt $Seconds; $i++) {
    $svc = Get-Service -Name $Id -ErrorAction SilentlyContinue
    if (-not $svc) { return $true }
    Start-Sleep -Seconds 1
  }
  return -not [bool](Get-Service -Name $Id -ErrorAction SilentlyContinue)
}

function Stop-MediaRecService([string]$Exe, [string]$Id) {
  $st = Get-WinSwStatus $Exe
  if ($st -match "NonExistent") { return }

  & $Exe stop 2>$null | Out-Null
  sc.exe stop $Id 2>$null | Out-Null

  for ($i = 0; $i -lt 20; $i++) {
    $svc = Get-Service -Name $Id -ErrorAction SilentlyContinue
    if (-not $svc -or $svc.Status -eq "Stopped") { break }
    Start-Sleep -Seconds 1
  }

  # Clear stuck start/stop pending (1061) and unlock WinSW binaries.
  $svc = Get-Service -Name $Id -ErrorAction SilentlyContinue
  if ($svc -and $svc.Status -ne "Stopped") {
    Write-Host "  force-stop $Id (was $($svc.Status))" -ForegroundColor Yellow
    sc.exe stop $Id 2>$null | Out-Null
    Start-Sleep -Seconds 2
  }
}

function Uninstall-MediaRecService([string]$Exe, [string]$Id) {
  Stop-MediaRecService -Exe $Exe -Id $Id
  & $Exe uninstall 2>$null | Out-Null
  if (-not (Wait-ServiceGone -Id $Id -Seconds 8)) {
    Write-Host "  sc.exe delete $Id (WinSW uninstall incomplete)" -ForegroundColor Yellow
    sc.exe delete $Id 2>$null | Out-Null
    if (-not (Wait-ServiceGone -Id $Id -Seconds 15)) {
      throw "$Id could not be removed from SCM (marked for delete?). Reboot or close services.msc and retry."
    }
  }
}

function Set-LocalServiceAccount([string]$Id) {
  # WinSW XML <serviceaccount> is not reliably applied, and
  # `sc.exe config $Id obj= "..." password= ""` can lose the trailing empty-string
  # argument when Windows PowerShell renders the native command line -- the obj=
  # change then silently no-ops (exit 0) and the service stays LocalSystem, which
  # PostgreSQL refuses. Use WMI (no command-line quoting) and VERIFY it took.
  $svc = Get-CimInstance Win32_Service -Filter "Name='$Id'" -ErrorAction Stop
  $res = Invoke-CimMethod -InputObject $svc -MethodName Change -Arguments @{
    StartName     = "NT AUTHORITY\LocalService"
    StartPassword = ""
  }
  if ($res.ReturnValue -ne 0) {
    throw "$Id could not be set to LocalService (Win32_Service.Change returned $($res.ReturnValue))."
  }
  # Confirm SCM actually recorded the account -- do not trust a silent success.
  $qc = & sc.exe qc $Id 2>&1 | Out-String
  if ($qc -notmatch "LOCAL SERVICE|LocalService") {
    throw "$Id account did not switch to LocalService after Win32_Service.Change. sc qc:`n$qc"
  }
  # Ensure Automatic start (some failed installs leave DISABLED).
  sc.exe config $Id start= auto 2>$null | Out-Null
  Write-Host "  service account -> NT AUTHORITY\LocalService (verified)"
}

function Test-NeedsLocalService([string]$Id) {
  if ($LocalServiceIds -notcontains $Id) { return $false }
  $qc = & sc.exe qc $Id 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) { return $true }
  return ($qc -notmatch "LOCAL SERVICE|LocalService")
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
      "install" {
        $exists = [bool](Get-Service -Name $id -ErrorAction SilentlyContinue)
        $needsAccount = Test-NeedsLocalService -Id $id
        if ($exists -and $needsAccount) {
          Write-Host "  (reinstall: switch $id to LocalService)"
          Uninstall-MediaRecService -Exe $exe -Id $id
          $exists = $false
        }
        if (-not $exists) {
          & $exe install
          if ($LASTEXITCODE -ne 0) {
            # Recover from "already exists" after a half-delete.
            Uninstall-MediaRecService -Exe $exe -Id $id
            & $exe install
          }
          if ($LASTEXITCODE -ne 0) {
            throw "$id install failed (exit $LASTEXITCODE). Run elevated; check WinSW wrapper logs under ProgramData\MediaRecommendationEngine\logs\$id."
          }
        } else {
          Write-Host "  already installed — keeping registration (XML updates apply on next start)"
        }
        if ($LocalServiceIds -contains $id) {
          Set-LocalServiceAccount -Id $id
        }
        # Re-enable if a prior failure left the service DISABLED.
        $qc = & sc.exe qc $id 2>&1 | Out-String
        if ($qc -match "DISABLED") {
          sc.exe config $id start= auto | Out-Null
          Write-Host "  start type was DISABLED — set to AUTO"
        }
      }
      "start" {
        & $exe start
        if ($LASTEXITCODE -ne 0) {
          sc.exe start $id 2>$null | Out-Null
          Start-Sleep -Seconds 2
          $svc = Get-Service -Name $id -ErrorAction SilentlyContinue
          if (-not $svc -or $svc.Status -ne "Running") {
            throw "$id start failed"
          }
        }
      }
      "stop" {
        try {
          Stop-MediaRecService -Exe $exe -Id $id
        } catch {
          Write-Host "warn: $id stop: $($_.Exception.Message)" -ForegroundColor Yellow
        }
      }
      "uninstall" {
        try {
          Uninstall-MediaRecService -Exe $exe -Id $id
        } catch {
          Write-Host "warn: $id uninstall: $($_.Exception.Message)" -ForegroundColor Yellow
        }
      }
      "status" { & $exe status }
    }
  }
} finally {
  Pop-Location
}

if ($Action -eq "status" -or $Action -eq "start" -or $Action -eq "install") {
  Write-Host ""
  Get-Service -Name "mediarec-*" -ErrorAction SilentlyContinue |
    Format-Table Name, Status, StartType -AutoSize
}

Write-Host "Done: $Action" -ForegroundColor Green
