#Requires -Version 5.1
<#
.SYNOPSIS
  Best-effort repair used by Open-MediaRec.vbs when :8000 is not responding.

.DESCRIPTION
  Re-stages WinSW XMLs for this machine, ensures ProgramData bootstrap pieces exist,
  then installs/starts mediarec-* services. Intended to run elevated (UAC).
#>
param(
  [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $InstallRoot) {
  $InstallRoot = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = Join-Path $env:ProgramData "MediaRecommendationEngine"
$Scripts = Join-Path $InstallRoot "scripts"
$LogDir = Join-Path $DataRoot "logs"
$LogFile = Join-Path $LogDir "launch-repair.log"

function Write-Log([string]$Message) {
  $line = "{0:o} {1}" -f (Get-Date).ToUniversalTime(), $Message
  try {
    if (-not (Test-Path -LiteralPath $LogDir)) {
      New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    }
    Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8
  } catch {
    # ignore logging failures
  }
}

function Test-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($id)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Log "Repair launch starting InstallRoot=$InstallRoot"

if (-not (Test-Admin)) {
  Write-Log "Not elevated — relaunching with UAC"
  $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -InstallRoot `"$InstallRoot`""
  Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arg -Wait
  exit $LASTEXITCODE
}

$init = Join-Path $Scripts "Initialize-NativeInstall.ps1"
$svc = Join-Path $Scripts "Install-MediaRecServices.ps1"
$pkg = Join-Path $Scripts "package_winsw_services.ps1"

try {
  if (Test-Path -LiteralPath $init) {
    Write-Log "Running Initialize-NativeInstall.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $init `
      -InstallRoot $InstallRoot -DataRoot $DataRoot -Quiet
    if ($LASTEXITCODE -ne 0) { throw "Initialize-NativeInstall failed exit $LASTEXITCODE" }
  } else {
    if (-not (Test-Path -LiteralPath $pkg)) { throw "Missing $pkg" }
    if (-not (Test-Path -LiteralPath $svc)) { throw "Missing $svc" }
    Write-Log "Staging WinSW then install/start services"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $pkg `
      -OutDir $InstallRoot -InstallRoot $InstallRoot -DataRoot $DataRoot
    if ($LASTEXITCODE -ne 0) { throw "package_winsw_services failed" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $svc `
      -Action install -InstallRoot $InstallRoot
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $svc `
      -Action start -InstallRoot $InstallRoot
  }
  Write-Log "Repair launch completed OK"
  exit 0
} catch {
  Write-Log ("Repair launch FAILED: " + $_.Exception.Message)
  exit 1
}
