#Requires -Version 5.1
<#
.SYNOPSIS
  Download EDB PostgreSQL 16 Windows binaries and stage them under dist/native-windows/runtime/postgres.

.DESCRIPTION
  Fetches the pinned EDB binaries zip, extracts the pgsql tree, strips unused UI packs,
  then installs pinned pgvector via build_pgvector_windows.ps1.

.PARAMETER OutDir
  Native payload root (default: <repo>\dist\native-windows)

.PARAMETER EdBVersion
  Version segment in the EDB zip name (default: 16.14-1)

.PARAMETER SkipDownload
  Reuse existing runtime\postgres (still re-runs pgvector install)

.EXAMPLE
  .\scripts\package_postgres_windows.ps1
  .\scripts\verify_pgvector_windows.ps1
#>
param(
  [string]$OutDir = "",
  [string]$EdBVersion = "16.14-1",
  [switch]$SkipDownload,
  [switch]$SkipPgvector
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$CacheDir = Join-Path $RepoRoot "dist\cache"
$PgRoot = Join-Path $OutDir "runtime\postgres"
$ZipName = "postgresql-$EdBVersion-windows-x64-binaries.zip"
$ZipUrl = "https://get.enterprisedb.com/postgresql/$ZipName"
$ZipPath = Join-Path $CacheDir $ZipName

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

Ensure-Dir $CacheDir
Ensure-Dir $OutDir

Write-Step "Output Postgres root: $PgRoot"

if ($SkipDownload) {
  if (-not (Test-Path -LiteralPath (Join-Path $PgRoot "bin\postgres.exe"))) {
    throw "SkipDownload set but missing postgres.exe under $PgRoot"
  }
  Write-Step "Skipping EDB download; reusing $PgRoot"
} else {
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    Write-Step "Downloading $ZipUrl"
    Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
  } else {
    Write-Step "Using cached $ZipPath"
  }

  $extractRoot = Join-Path $CacheDir "pgsql-edb-extract"
  if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
  }
  Ensure-Dir $extractRoot
  Write-Step "Extracting EDB binaries (large archive; may take a minute)"
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $extractRoot -Force

  $pgsql = Join-Path $extractRoot "pgsql"
  if (-not (Test-Path -LiteralPath $pgsql)) {
    $pgsql = Get-ChildItem -LiteralPath $extractRoot -Directory | Where-Object {
      Test-Path (Join-Path $_.FullName "bin\postgres.exe")
    } | Select-Object -First 1 -ExpandProperty FullName
  }
  if (-not $pgsql -or -not (Test-Path -LiteralPath (Join-Path $pgsql "bin\postgres.exe"))) {
    throw "EDB zip did not contain bin\postgres.exe"
  }

  if (Test-Path -LiteralPath $PgRoot) {
    Remove-Item -LiteralPath $PgRoot -Recurse -Force
  }
  Ensure-Dir (Split-Path -Parent $PgRoot)
  Write-Step "Staging Postgres tree to $PgRoot"
  & robocopy $pgsql $PgRoot /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed staging Postgres (exit $LASTEXITCODE)"
  }

  foreach ($junk in @("doc", "pgAdmin 4", "pgAdmin4", "StackBuilder", "pgAdmin")) {
    $p = Join-Path $PgRoot $junk
    if (Test-Path -LiteralPath $p) {
      Write-Step "Removing unused $junk"
      Remove-Item -LiteralPath $p -Recurse -Force
    }
  }
}

if (-not $SkipPgvector) {
  Write-Step "Installing pgvector into staged Postgres"
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_pgvector_windows.ps1") -PgRoot $PgRoot
  if ($LASTEXITCODE -ne 0) {
    throw "build_pgvector_windows.ps1 failed"
  }
}

$meta = @"
edb_version=$EdBVersion
edb_url=$ZipUrl
built_utc=$((Get-Date).ToUniversalTime().ToString("o"))
pg_root=$PgRoot
"@
Set-Content -LiteralPath (Join-Path $OutDir "postgres-runtime.meta.txt") -Value $meta -Encoding utf8

Write-Host ""
Write-Host "PostgreSQL runtime packaged successfully." -ForegroundColor Green
Write-Host "  Postgres: $PgRoot"
Write-Host "Next:      .\scripts\verify_pgvector_windows.ps1 -OutDir `"$OutDir`""
