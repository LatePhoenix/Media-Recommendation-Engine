# patch-installed.ps1
# Elevates (UAC) and copies fixed compose/runtime files into an existing install.
# Usage:
#   & Z:\WORKING\Media-Recommendation-Engine\installer\patch-installed.ps1

$ErrorActionPreference = "Stop"
$Src = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dst = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"

function Copy-FixedFiles {
  param([string]$SrcRoot, [string]$DstRoot)
  if (-not (Test-Path $DstRoot)) {
    throw "Install not found at $DstRoot"
  }
  $pairs = @(
    @{ From = "infra\docker-compose.yml"; To = "infra\docker-compose.yml" },
    @{ From = "infra\docker-compose.dev.yml"; To = "infra\docker-compose.dev.yml" },
    @{ From = "infra\Dockerfile.api"; To = "infra\Dockerfile.api" },
    @{ From = "infra\entrypoint-api.sh"; To = "infra\entrypoint-api.sh" },
    @{ From = "installer\Start-MediaRec.ps1"; To = "Start-MediaRec.ps1" },
    @{ From = "installer\setup-env.ps1"; To = "setup-env.ps1" },
    @{ From = "apps\api\alembic\env.py"; To = "apps\api\alembic\env.py" },
    @{ From = "apps\api\app\main.py"; To = "apps\api\app\main.py" },
    @{ From = "apps\api\__main_seed__.py"; To = "apps\api\__main_seed__.py" },
    @{ From = ".gitattributes"; To = ".gitattributes" }
  )
  foreach ($p in $pairs) {
    $from = Join-Path $SrcRoot $p.From
    $to = Join-Path $DstRoot $p.To
    $toDir = Split-Path -Parent $to
    if (-not (Test-Path $toDir)) { New-Item -ItemType Directory -Force -Path $toDir | Out-Null }
    Copy-Item -LiteralPath $from -Destination $to -Force
    Write-Host "Updated $($p.To)"
  }

  # Ensure .env exists with real secrets (Program Files write needs admin).
  $setup = Join-Path $DstRoot "setup-env.ps1"
  if (Test-Path $setup) { & $setup }
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).
  IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  Write-Host "Requesting Administrator privileges to update Program Files..." -ForegroundColor Yellow
  $self = $MyInvocation.MyCommand.Path
  Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $self
  )
  exit $LASTEXITCODE
}

Copy-FixedFiles -SrcRoot $Src -DstRoot $Dst
Write-Host ""
Write-Host "Patched. Start the app from the Start Menu shortcut (rebuilds images)." -ForegroundColor Green
Start-Sleep -Seconds 2
