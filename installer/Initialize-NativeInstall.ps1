#Requires -Version 5.1
<#
.SYNOPSIS
  First-run native Windows install bootstrap (secrets, DB, Redis, WinSW services).

.DESCRIPTION
  Intended to run elevated from Inno Setup [Run]. Idempotent where possible:
  - Writes ProgramData config\.env from .env.example + generated secrets
  - Initializes Postgres cluster / Redis conf if missing
  - Stages WinSW XMLs for this machine
  - Installs and starts mediarec-* services
  - Does not open a visible console for end users when invoked with -Quiet
#>
param(
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [switch]$Quiet,
  [switch]$SkipServices,
  [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
if ($Quiet) {
  $ProgressPreference = "SilentlyContinue"
}

function Write-Info([string]$Message) {
  if (-not $Quiet) { Write-Host $Message }
}

function Write-BootstrapLog([string]$Message) {
  try {
    $logDir = Join-Path $DataRoot "logs"
    if (-not (Test-Path -LiteralPath $logDir)) {
      New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    $line = "{0:o} {1}" -f (Get-Date).ToUniversalTime(), $Message
    Add-Content -LiteralPath (Join-Path $logDir "bootstrap.log") -Value $line -Encoding utf8
  } catch {
    # never fail bootstrap solely because logging failed
  }
}

if (-not $InstallRoot) {
  $InstallRoot = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}
if (-not $DataRoot) {
  $DataRoot = Join-Path $env:ProgramData "MediaRecommendationEngine"
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

$Scripts = Join-Path $InstallRoot "scripts"
$Example = Join-Path $InstallRoot "config\.env.example"
if (-not (Test-Path -LiteralPath $Example)) {
  $Example = Join-Path $InstallRoot ".env.example"
}
$ConfigDir = Join-Path $DataRoot "config"
$EnvFile = Join-Path $ConfigDir ".env"

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function New-UrlSafeToken([int]$bytes) {
  # Windows PowerShell 5.1 / .NET Framework: RandomNumberGenerator.Fill is unavailable.
  $buf = New-Object byte[] $bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($buf)
  } finally {
    $rng.Dispose()
  }
  [Convert]::ToBase64String($buf).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-FernetKey {
  $buf = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($buf)
  } finally {
    $rng.Dispose()
  }
  [Convert]::ToBase64String($buf).Replace('+', '-').Replace('/', '_')
}

function Ensure-NativeEnv {
  Ensure-Dir $ConfigDir
  if (-not (Test-Path -LiteralPath $Example)) {
    throw "Missing env template at $Example"
  }
  $isNew = -not (Test-Path -LiteralPath $EnvFile)
  if ($isNew) {
    Copy-Item -LiteralPath $Example -Destination $EnvFile -Force
    Write-Info "Created $EnvFile"
  }

  # Upgrade-safe: add keys present in the new template but missing from the live .env.
  # Never overwrite an existing non-empty value.
  $exampleLines = Get-Content -LiteralPath $Example
  $live = Get-Content -Raw -Path $EnvFile
  $mergedExtra = @()
  foreach ($line in $exampleLines) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^\s*([A-Za-z0-9_]+)=(.*)$') {
      $key = $Matches[1]
      if ($live -notmatch "(?m)^$key=") {
        $mergedExtra += $line
      }
    }
  }
  if ($mergedExtra.Count -gt 0) {
    $live = $live.TrimEnd() + "`n" + ($mergedExtra -join "`n") + "`n"
    Set-Content -Path $EnvFile -Value $live -NoNewline -Encoding UTF8
    Write-Info ("Merged new env keys: " + (($mergedExtra | ForEach-Object { ($_ -split '=', 2)[0] }) -join ', '))
  }

  $content = Get-Content -Raw -Path $EnvFile
  $changed = $false
  $placeholder = "change-me-in-production-use-long-random-string"

  if ($content -match [regex]::Escape($placeholder)) {
    $secret = New-UrlSafeToken 48
    $content = $content.Replace("API_SECRET_KEY=$placeholder", "API_SECRET_KEY=$secret")
    $changed = $true
  }
  if ($content -match "(?m)^CREDENTIALS_FERNET_KEY=\s*$") {
    $fernet = New-FernetKey
    $content = $content -replace "(?m)^CREDENTIALS_FERNET_KEY=\s*$", "CREDENTIALS_FERNET_KEY=$fernet"
    $changed = $true
  }

  $pgPass = $null
  if ($content -match "(?m)^POSTGRES_PASSWORD=mediarec\s*$") {
    $pgPass = New-UrlSafeToken 24
    $content = $content -replace "(?m)^POSTGRES_PASSWORD=mediarec\s*$", "POSTGRES_PASSWORD=$pgPass"
    $content = $content -replace "(?m)^DATABASE_URL=postgresql\+psycopg://mediarec:mediarec@", "DATABASE_URL=postgresql+psycopg://mediarec:${pgPass}@"
    $changed = $true
  } elseif ($content -match "(?m)^POSTGRES_PASSWORD=(.+)$") {
    $pgPass = $Matches[1].Trim()
  }

  $redisPass = $null
  if ($content -notmatch "(?m)^REDIS_PASSWORD=") {
    $redisPass = New-UrlSafeToken 24
    if ($content -match "(?m)^REDIS_URL=") {
      $content = $content -replace "(?m)^REDIS_URL=.*$", "REDIS_PASSWORD=$redisPass`nREDIS_URL=redis://:${redisPass}@127.0.0.1:6379/0"
    } else {
      $content = $content.TrimEnd() + "`nREDIS_PASSWORD=$redisPass`nREDIS_URL=redis://:${redisPass}@127.0.0.1:6379/0`n"
    }
    $changed = $true
  } elseif ($content -match "(?m)^REDIS_PASSWORD=mediarec-redis\s*$") {
    $redisPass = New-UrlSafeToken 24
    $content = $content -replace "(?m)^REDIS_PASSWORD=mediarec-redis\s*$", "REDIS_PASSWORD=$redisPass"
    $content = $content -replace "(?m)^REDIS_URL=.*$", "REDIS_URL=redis://:${redisPass}@127.0.0.1:6379/0"
    $changed = $true
  } elseif ($content -match "(?m)^REDIS_PASSWORD=(.+)$") {
    $redisPass = $Matches[1].Trim()
  }

  # Force localhost URLs for native services (never Compose DNS names).
  if ($content -match "@postgres:") {
    $content = $content -replace "@postgres:", "@127.0.0.1:"
    $changed = $true
  }
  if ($content -match "@redis:") {
    $content = $content -replace "@redis:", "@127.0.0.1:"
    $changed = $true
  }
  if ($content -match "@localhost:") {
    $content = $content -replace "@localhost:", "@127.0.0.1:"
    $changed = $true
  }

  # Same-origin UI on :8000 (Open-MediaRec.url uses 127.0.0.1).
  $nativeCors = "http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173"
  if ($content -notmatch "(?m)^API_CORS_ORIGINS=") {
    $content = $content.TrimEnd() + "`nAPI_CORS_ORIGINS=$nativeCors`n"
    $changed = $true
  } elseif ($content -match "(?m)^API_CORS_ORIGINS=(.*)$") {
    $cors = $Matches[1]
    if ($cors -notmatch "127\.0\.0\.1:8000") {
      $content = $content -replace "(?m)^API_CORS_ORIGINS=.*$", "API_CORS_ORIGINS=$nativeCors"
      $changed = $true
    }
  }

  $webDist = Join-Path $InstallRoot "app\web"
  if ($content -notmatch "(?m)^WEB_DIST_DIR=") {
    $content = $content.TrimEnd() + "`nWEB_DIST_DIR=$webDist`n"
    $changed = $true
  } elseif ($content -match "(?m)^WEB_DIST_DIR=\s*$") {
    $content = $content -replace "(?m)^WEB_DIST_DIR=\s*$", "WEB_DIST_DIR=$webDist"
    $changed = $true
  }

  if ($changed) {
    Set-Content -Path $EnvFile -Value $content -NoNewline -Encoding UTF8
  }

  return @{
    EnvFile   = $EnvFile
    PgPass    = $pgPass
    RedisPass = $redisPass
    IsNewEnv  = $isNew
  }
}

Write-Info "Native install bootstrap"
Write-Info "  InstallRoot: $InstallRoot"
Write-Info "  DataRoot:    $DataRoot"
Write-BootstrapLog "Bootstrap start InstallRoot=$InstallRoot DataRoot=$DataRoot"

try {

$secrets = Ensure-NativeEnv
$env:MEDIAREC_ENV_FILE = $secrets.EnvFile
$env:MEDIAREC_ROOT = $InstallRoot

# Load passwords for child scripts
$envContent = Get-Content -Raw -Path $secrets.EnvFile
if ($envContent -match "(?m)^POSTGRES_PASSWORD=(.+)$") { $env:POSTGRES_PASSWORD = $Matches[1].Trim() }
if ($envContent -match "(?m)^REDIS_PASSWORD=(.+)$") { $env:REDIS_PASSWORD = $Matches[1].Trim() }
if ($envContent -match "(?m)^API_SECRET_KEY=(.+)$") { $env:API_SECRET_KEY = $Matches[1].Trim() }

$initDb = Join-Path $Scripts "Initialize-MediaRecDatabase.ps1"
$initRedis = Join-Path $Scripts "Initialize-MediaRecRedis.ps1"
$pkgWinsw = Join-Path $Scripts "package_winsw_services.ps1"
$svcMgr = Join-Path $Scripts "Install-MediaRecServices.ps1"

if (-not (Test-Path -LiteralPath $initDb)) {
  throw "Missing $initDb (installer payload incomplete)"
}

Write-Info "Initializing PostgreSQL..."
Write-BootstrapLog "Initializing PostgreSQL"
# First-time only: fail fast if Docker/dev Compose already owns the default ports.
$pgDataMarker = Join-Path $DataRoot "postgres\data\PG_VERSION"
if (-not (Test-Path -LiteralPath $pgDataMarker)) {
  foreach ($probe in @(
    @{ Name = "PostgreSQL"; Port = 5432 },
    @{ Name = "Redis"; Port = 6379 }
  )) {
    try {
      $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port $probe.Port -WarningAction SilentlyContinue
      if ($tcp.TcpTestSucceeded) {
        $msg = "$($probe.Name) port $($probe.Port) is already in use on 127.0.0.1. Stop Docker Compose / start.bat stack (or other local DB/Redis) before finishing the native Windows install, then open the app again from the Start Menu."
        Write-BootstrapLog $msg
        throw $msg
      }
    } catch {
      if ($_.Exception.Message -match "already in use") { throw }
    }
  }
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $initDb `
  -InstallRoot $InstallRoot -DataRoot $DataRoot `
  -Password $env:POSTGRES_PASSWORD -Port 5432
if ($LASTEXITCODE -ne 0) { throw "Database init failed" }

# Stop bootstrap postgres so the Windows service owns the cluster.
$pgCtl = Join-Path $InstallRoot "runtime\postgres\bin\pg_ctl.exe"
$pgData = Join-Path $DataRoot "postgres\data"
if ((Test-Path $pgCtl) -and (Test-Path (Join-Path $pgData "postmaster.pid"))) {
  & $pgCtl -D $pgData stop -m fast 2>$null | Out-Null
}

Write-Info "Initializing Redis config..."
Write-BootstrapLog "Initializing Redis"
& powershell -NoProfile -ExecutionPolicy Bypass -File $initRedis `
  -InstallRoot $InstallRoot -DataRoot $DataRoot `
  -Password $env:REDIS_PASSWORD -Port 6379
if ($LASTEXITCODE -ne 0) { throw "Redis init failed" }

# Running services lock runtime\winsw\mediarec-*.exe; stop before re-staging XMLs/binaries.
if ((Test-Path -LiteralPath $svcMgr) -and -not $SkipServices) {
  Write-Info "Stopping Windows services (if present) before WinSW staging..."
  Write-BootstrapLog "Stopping services before WinSW staging"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $svcMgr -Action stop -InstallRoot $InstallRoot
}

Write-Info "Staging WinSW service definitions..."
Write-BootstrapLog "Staging WinSW"
& powershell -NoProfile -ExecutionPolicy Bypass -File $pkgWinsw `
  -OutDir $InstallRoot -InstallRoot $InstallRoot -DataRoot $DataRoot
if ($LASTEXITCODE -ne 0) { throw "WinSW staging failed" }

if (-not $SkipServices) {
  Write-Info "Installing Windows services..."
  Write-BootstrapLog "Installing services"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $svcMgr -Action install -InstallRoot $InstallRoot -DataRoot $DataRoot
  if ($LASTEXITCODE -ne 0) { throw "Service install failed" }
  if (-not $SkipStart) {
    Write-Info "Starting Windows services..."
    Write-BootstrapLog "Starting services"
    # -Action start health-gates postgres on real 5432 connectivity and self-heals the
    # LocalService account/ACLs, so a non-zero exit here means the DB is genuinely dead.
    & powershell -NoProfile -ExecutionPolicy Bypass -File $svcMgr -Action start -InstallRoot $InstallRoot -DataRoot $DataRoot
    if ($LASTEXITCODE -ne 0) { throw "Service start failed" }

    # Hard gate: the whole reason 'shortcut does nothing' slipped through was that
    # bootstrap reported success while :8000 never came up. Require API health before
    # we are allowed to call the install complete.
    Write-Info "Waiting for API health on http://127.0.0.1:8000/health ..."
    $apiReady = $false
    for ($i = 0; $i -lt 60; $i++) {
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) { $apiReady = $true; break }
      } catch { }
      Start-Sleep -Seconds 2
    }
    Write-BootstrapLog "API health reachable=$apiReady"
    if (-not $apiReady) {
      throw "API did not become healthy on http://127.0.0.1:8000/health within 120s. See $DataRoot\logs\mediarec-api and \logs\mediarec-postgres."
    }

    # Full post-install smoke checks. Advisory (logged, not fatal) so a non-critical
    # check like pgvector warming does not abort an otherwise-working install -- but the
    # result is always recorded so a regression is never silent again.
    $verify = Join-Path $Scripts "Verify-NativeInstall.ps1"
    if (Test-Path -LiteralPath $verify) {
      Write-Info "Running post-install verification..."
      Write-BootstrapLog "Running Verify-NativeInstall"
      $verifyLog = Join-Path (Join-Path $DataRoot "logs") "verify-latest.log"
      & powershell -NoProfile -ExecutionPolicy Bypass -File $verify -InstallRoot $InstallRoot -DataRoot $DataRoot *>&1 |
        Tee-Object -FilePath $verifyLog | Out-Null
      $verifyExit = $LASTEXITCODE
      Write-BootstrapLog "Verify-NativeInstall exit=$verifyExit (full log: $verifyLog)"
      if ($verifyExit -ne 0) {
        Write-Info "WARNING: post-install verification reported failures - see $verifyLog"
        Write-BootstrapLog "WARNING: Verify-NativeInstall reported failures"
      }
    }
  }
}

Write-Info "Bootstrap complete. App URL: http://127.0.0.1:8000/"
Write-BootstrapLog "Bootstrap complete"

# Record install/upgrade state (ProgramData — survives Program Files replacement).
$verFile = Join-Path $InstallRoot "version.txt"
$appVersion = if (Test-Path $verFile) { (Get-Content -LiteralPath $verFile -Raw).Trim() } else { "unknown" }
$statePath = Join-Path $ConfigDir "install-state.json"
$prev = $null
if (Test-Path -LiteralPath $statePath) {
  try { $prev = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch { $prev = $null }
}
$state = [ordered]@{
  app_version     = $appVersion
  install_root    = $InstallRoot
  data_root       = $DataRoot
  last_bootstrap  = (Get-Date).ToUniversalTime().ToString("o")
  first_installed = if ($prev -and $prev.first_installed) { $prev.first_installed } else { (Get-Date).ToUniversalTime().ToString("o") }
  previous_version = if ($prev) { $prev.app_version } else { $null }
  upgrade         = [bool]($prev -and $prev.app_version -and ($prev.app_version -ne $appVersion))
}
($state | ConvertTo-Json) | Set-Content -LiteralPath $statePath -Encoding utf8
Write-Info "Wrote $statePath"
Write-BootstrapLog "Wrote install-state.json"

} catch {
  Write-BootstrapLog ("Bootstrap FAILED: " + $_.Exception.Message)
  throw
}
