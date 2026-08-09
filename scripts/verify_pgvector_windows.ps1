#Requires -Version 5.1
<#
.SYNOPSIS
  Verify packaged PostgreSQL + pgvector by creating a temp cluster and CREATE EXTENSION vector.

.PARAMETER OutDir
  Native payload root containing runtime\postgres

.PARAMETER Port
  Ephemeral listen port (default 55432 to avoid clashing with Docker/dev 5432)
#>
param(
  [string]$OutDir = "",
  [int]$Port = 55432
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$PgRoot = Join-Path $OutDir "runtime\postgres"
$Bin = Join-Path $PgRoot "bin"
$Postgres = Join-Path $Bin "postgres.exe"
$Initdb = Join-Path $Bin "initdb.exe"
$PgCtl = Join-Path $Bin "pg_ctl.exe"
$Psql = Join-Path $Bin "psql.exe"
$PgIsReady = Join-Path $Bin "pg_isready.exe"
$DataDir = Join-Path $OutDir "verify-pgdata"
$LogFile = Join-Path $OutDir "verify-postgres.log"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

foreach ($p in @($Postgres, $Initdb, $PgCtl, $Psql, $PgIsReady)) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Missing $p - run scripts\package_postgres_windows.ps1 first"
  }
}
foreach ($p in @(
    (Join-Path $PgRoot "lib\vector.dll"),
    (Join-Path $PgRoot "share\extension\vector.control")
  )) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Missing pgvector file $p - run build_pgvector_windows.ps1"
  }
}

if (Test-Path -LiteralPath $DataDir) {
  if (Test-Path -LiteralPath (Join-Path $DataDir "postmaster.pid")) {
    Write-Step "Stopping previous verify instance"
    & $PgCtl -D $DataDir stop -m fast
  }
  Remove-Item -LiteralPath $DataDir -Recurse -Force
}

Write-Step "initdb at $DataDir"
& $Initdb -D $DataDir -U postgres --locale=C --encoding=UTF8 --auth-local=trust --auth-host=trust
if ($LASTEXITCODE -ne 0) { throw "initdb failed (exit $LASTEXITCODE)" }

$conf = Join-Path $DataDir "postgresql.conf"
Add-Content -LiteralPath $conf -Value @"

listen_addresses = '127.0.0.1'
port = $Port
logging_collector = off
"@

Write-Step "Starting postgres on 127.0.0.1:$Port"
# Keep -o value as one token (-pPORT) so shells do not split it.
& $PgCtl -D $DataDir -l $LogFile -o "-p$Port" start
if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed (exit $LASTEXITCODE); see $LogFile" }

$ok = $false
try {
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    & $PgIsReady -h 127.0.0.1 -p $Port -U postgres
    if ($LASTEXITCODE -eq 0) {
      $ready = $true
      break
    }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw "server did not become ready" }

  Write-Step "CREATE EXTENSION vector + uuid-ossp"
  $sqlFile = Join-Path $OutDir "verify-extensions.sql"
  Set-Content -LiteralPath $sqlFile -Value @"
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp') ORDER BY 1;
"@ -Encoding ascii
  & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -f $sqlFile
  if ($LASTEXITCODE -ne 0) { throw "CREATE EXTENSION failed (exit $LASTEXITCODE)" }
  $ok = $true
} finally {
  Write-Step "Stopping verify instance"
  & $PgCtl -D $DataDir stop -m fast
}

if (-not $ok) { throw "Verification failed" }

Write-Host ""
Write-Host "pgvector verification passed on packaged PostgreSQL." -ForegroundColor Green
Write-Host "  Data dir (can delete): $DataDir"
