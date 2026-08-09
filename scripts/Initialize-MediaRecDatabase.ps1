#Requires -Version 5.1
<#
.SYNOPSIS
  First-install / upgrade-safe database bootstrap for native Windows packaging.

.DESCRIPTION
  Idempotent steps:
    1. initdb if PGDATA missing
    2. ensure postgres listens on 127.0.0.1
    3. start server (pg_ctl) if not running
    4. create role + database when missing
    5. CREATE EXTENSION vector + uuid-ossp
    6. optional Alembic migrate + seed via packaged python launchers

  Does not overwrite an existing cluster. Secrets/password should come from
  -Password / env or an existing ProgramData .env.

.PARAMETER InstallRoot
  Program Files-style root (contains runtime\postgres and optionally runtime\python + app)

.PARAMETER DataRoot
  ProgramData-style root (postgres\data will be created under it)

.PARAMETER Port
  Listen port (default 5432)

.PARAMETER DbName / DbUser / Password
  Application database credentials

.PARAMETER SkipMigrate / SkipSeed
  Skip Alembic / seed steps

.EXAMPLE
  .\scripts\Initialize-MediaRecDatabase.ps1 `
    -InstallRoot "$env:ProgramFiles\Media Recommendation Engine" `
    -DataRoot "$env:ProgramData\MediaRecommendationEngine" `
    -Password (ConvertTo-SecureString '...' -AsPlainText -Force)
#>
param(
  [string]$InstallRoot = "",
  [string]$DataRoot = "",
  [int]$Port = 5432,
  [string]$DbName = "mediarec",
  [string]$DbUser = "mediarec",
  [string]$Password = "",
  [switch]$SkipMigrate,
  [switch]$SkipSeed,
  [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $InstallRoot) {
  $InstallRoot = Join-Path $RepoRoot "dist\native-windows"
}
if (-not $DataRoot) {
  $DataRoot = Join-Path $RepoRoot "dist\native-windows-data"
}

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

$PgRoot = Join-Path $InstallRoot "runtime\postgres"
$Bin = Join-Path $PgRoot "bin"
$Initdb = Join-Path $Bin "initdb.exe"
$PgCtl = Join-Path $Bin "pg_ctl.exe"
$Psql = Join-Path $Bin "psql.exe"
$PgIsReady = Join-Path $Bin "pg_isready.exe"
$DataDir = Join-Path $DataRoot "postgres\data"
$LogDir = Join-Path $DataRoot "logs\mediarec-postgres"
$LogFile = Join-Path $LogDir "postgres.log"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-PlainPassword {
  if ($Password) { return $Password }
  if ($env:POSTGRES_PASSWORD) { return $env:POSTGRES_PASSWORD }
  if ($env:MEDIAREC_DB_PASSWORD) { return $env:MEDIAREC_DB_PASSWORD }
  # Dev-friendly default for local packaging smoke tests only.
  return "mediarec"
}

function Invoke-Psql([string]$Database, [string]$Sql) {
  & $Psql -h 127.0.0.1 -p $Port -U postgres -d $Database -v ON_ERROR_STOP=1 -c $Sql
  if ($LASTEXITCODE -ne 0) {
    throw "psql failed against $Database"
  }
}

foreach ($p in @($Initdb, $PgCtl, $Psql, $PgIsReady)) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Missing $p - package Postgres first (scripts\package_postgres_windows.ps1)"
  }
}

Ensure-Dir $DataRoot
Ensure-Dir $LogDir
Ensure-Dir (Split-Path -Parent $DataDir)

$plainPw = Get-PlainPassword

if (-not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
  Write-Step "Initializing new cluster at $DataDir"
  # Local sockets/trust for bootstrap; host auth tightened after role creation via pg_hba.
  & $Initdb -D $DataDir -U postgres --locale=C --encoding=UTF8 --auth-local=trust --auth-host=trust | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "initdb failed" }

  $conf = Join-Path $DataDir "postgresql.conf"
  Add-Content -LiteralPath $conf -Value @"

# Media Recommendation Engine native defaults
listen_addresses = '127.0.0.1'
port = $Port
logging_collector = on
log_directory = '$($LogDir.Replace('\', '/'))'
log_filename = 'postgresql-%Y-%m-%d.log'
"@

  $hba = Join-Path $DataDir "pg_hba.conf"
  # Loopback-only trust for local-first single-machine installs (port bound to 127.0.0.1).
  # Windows clients use TCP even for local connections, so "local" lines alone are insufficient.
  Set-Content -LiteralPath $hba -Value @"
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
"@ -Encoding ascii
} else {
  Write-Step "Existing cluster found at $DataDir (skipping initdb)"
}

$running = $false
if (Test-Path -LiteralPath (Join-Path $DataDir "postmaster.pid")) {
  & $PgCtl -D $DataDir status | Out-Null
  if ($LASTEXITCODE -eq 0) { $running = $true }
}

if (-not $SkipStart) {
  if (-not $running) {
    Write-Step "Starting PostgreSQL ($DataDir) on 127.0.0.1:$Port"
    & $PgCtl -D $DataDir -l $LogFile -o "-p$Port" start
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed; see $LogFile" }
  } else {
    Write-Step "PostgreSQL already running"
  }

  for ($i = 0; $i -lt 45; $i++) {
    & $PgIsReady -h 127.0.0.1 -p $Port -U postgres | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
  }
  & $PgIsReady -h 127.0.0.1 -p $Port -U postgres | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become ready on port $Port" }
}

# Role + database (idempotent)
Write-Step "Ensuring role '$DbUser' and database '$DbName'"
$escaped = $plainPw.Replace("'", "''")
$roleSql = Join-Path $DataRoot "postgres\ensure-role.sql"
Ensure-Dir (Split-Path -Parent $roleSql)
Set-Content -LiteralPath $roleSql -Value @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DbUser') THEN
    CREATE ROLE $DbUser LOGIN PASSWORD '$escaped';
  ELSE
    ALTER ROLE $DbUser WITH LOGIN PASSWORD '$escaped';
  END IF;
END
`$`$;
SELECT 1 FROM pg_database WHERE datname = '$DbName';
"@ -Encoding ascii
& $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -f $roleSql
if ($LASTEXITCODE -ne 0) { throw "ensure role failed" }

$dbCount = (& $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT COUNT(*) FROM pg_database WHERE datname='$DbName';").ToString().Trim()
if ($dbCount -eq "0") {
  Invoke-Psql "postgres" "CREATE DATABASE $DbName OWNER $DbUser;"
}

Write-Step "Ensuring extensions (vector, uuid-ossp)"
$extSql = Join-Path $DataRoot "postgres\ensure-extensions.sql"
Ensure-Dir (Split-Path -Parent $extSql)
Set-Content -LiteralPath $extSql -Value @"
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"@ -Encoding ascii
& $Psql -h 127.0.0.1 -p $Port -U postgres -d $DbName -v ON_ERROR_STOP=1 -f $extSql
if ($LASTEXITCODE -ne 0) { throw "CREATE EXTENSION failed" }

$databaseUrl = "postgresql+psycopg://${DbUser}:$plainPw@127.0.0.1:${Port}/${DbName}"
$env:DATABASE_URL = $databaseUrl
$env:POSTGRES_USER = $DbUser
$env:POSTGRES_PASSWORD = $plainPw
$env:POSTGRES_DB = $DbName

$python = Join-Path $InstallRoot "runtime\python\python.exe"
$apiRoot = Join-Path $InstallRoot "app\api"
if (-not $SkipMigrate) {
  if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $apiRoot)) {
    Write-Step "Running Alembic migrations via app.launch"
    if (-not $env:API_SECRET_KEY) {
      $env:API_SECRET_KEY = "bootstrap-only-secret-key-replace-in-programdata-0123456789"
    }
    $env:MEDIAREC_ROOT = $InstallRoot
    Push-Location $apiRoot
    try {
      & $python -m app.launch migrate
      if ($LASTEXITCODE -ne 0) { throw "migrate failed" }
      if (-not $SkipSeed) {
        Write-Step "Seeding catalog"
        & $python -m app.launch seed
        if ($LASTEXITCODE -ne 0) { throw "seed failed" }
      }
    } finally {
      Pop-Location
    }
  } else {
    Write-Host "Packaged Python/API not found under $InstallRoot - skipped migrate/seed." -ForegroundColor Yellow
    Write-Host "Run scripts\package_python_runtime.ps1 then re-run this script." -ForegroundColor Yellow
  }
}

# Write a non-secret pointer file for operators (password stays in ProgramData .env separately).
$info = @"
database_url_template=postgresql+psycopg://${DbUser}:***@127.0.0.1:${Port}/${DbName}
data_dir=$DataDir
port=$Port
initialized_utc=$((Get-Date).ToUniversalTime().ToString("o"))
"@
Ensure-Dir (Join-Path $DataRoot "config")
Set-Content -LiteralPath (Join-Path $DataRoot "config\database-init.meta.txt") -Value $info -Encoding utf8

Write-Host ""
Write-Host "Database bootstrap complete." -ForegroundColor Green
Write-Host "  Data: $DataDir"
Write-Host "  URL:  postgresql+psycopg://${DbUser}:***@127.0.0.1:${Port}/${DbName}"
Write-Host "Set MEDIAREC_ENV_FILE / ProgramData config\.env with DATABASE_URL before starting the API service."
