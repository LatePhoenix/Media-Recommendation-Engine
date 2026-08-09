#Requires -Version 5.1
<#
.SYNOPSIS
  Fetch pinned Windows pgvector bits and install them into a PostgreSQL root (or build from source).

.DESCRIPTION
  Default mode downloads a pinned community Windows build that matches PostgreSQL 16 and
  verifies SHA256, then copies:
    lib\vector.dll
    share\extension\vector.control
    share\extension\vector*.sql

  -FromSource builds pgvector against -PgRoot using Visual Studio (x64) + Makefile.win.

.PARAMETER PgRoot
  PostgreSQL installation root containing bin\, lib\, share\.

.PARAMETER FromSource
  Build from the official pgvector git tag instead of using the pinned Windows zip.

.PARAMETER PgvectorVersion
  Upstream pgvector tag without leading 'v' when using -FromSource. Default: 0.8.6

.EXAMPLE
  .\scripts\build_pgvector_windows.ps1 -PgRoot .\dist\native-windows\runtime\postgres
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$PgRoot,
  [switch]$FromSource,
  [string]$PgvectorVersion = "0.8.6",
  [string]$PrebuiltTag = "0.8.6_16",
  [string]$PrebuiltAsset = "vector.v0.8.6-pg16.zip",
  [string]$PrebuiltSha256 = "faeaecb100488397ce5d38424b8c931be0f29e1668be7d4e75c26fe2eb056522"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CacheDir = Join-Path $RepoRoot "dist\cache"
$PgRoot = (Resolve-Path -LiteralPath $PgRoot).Path

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Assert-PgRoot([string]$Root) {
  foreach ($rel in @("bin\postgres.exe", "lib", "share\extension")) {
    $p = Join-Path $Root $rel
    if (-not (Test-Path -LiteralPath $p)) {
      throw "PostgreSQL root incomplete; missing $p"
    }
  }
}

function Get-FileSha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Assert-PgRoot $PgRoot
Ensure-Dir $CacheDir

$libDir = Join-Path $PgRoot "lib"
$extDir = Join-Path $PgRoot "share\extension"

if ($FromSource) {
  Write-Step "Building pgvector $PgvectorVersion from source against $PgRoot"
  $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  if (-not (Test-Path -LiteralPath $vswhere)) {
    throw "Visual Studio Build Tools not found (vswhere missing). Install VS C++ tools or omit -FromSource."
  }
  $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
  if (-not $vsPath) {
    throw "No VS install with VC Tools x64 found. Install Build Tools or omit -FromSource."
  }
  $vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
  if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "vcvars64.bat not found at $vcvars"
  }

  $srcRoot = Join-Path $CacheDir "pgvector-src"
  $srcDir = Join-Path $srcRoot "pgvector-$PgvectorVersion"
  if (Test-Path -LiteralPath $srcDir) {
    Remove-Item -LiteralPath $srcDir -Recurse -Force
  }
  Ensure-Dir $srcRoot
  $tarUrl = "https://github.com/pgvector/pgvector/archive/refs/tags/v$PgvectorVersion.zip"
  $tarZip = Join-Path $CacheDir "pgvector-v$PgvectorVersion-src.zip"
  if (-not (Test-Path -LiteralPath $tarZip)) {
    Write-Step "Downloading $tarUrl"
    Invoke-WebRequest -Uri $tarUrl -OutFile $tarZip -UseBasicParsing
  }
  Expand-Archive -LiteralPath $tarZip -DestinationPath $srcRoot -Force
  $extracted = Get-ChildItem -LiteralPath $srcRoot -Directory | Where-Object { $_.Name -like "pgvector-*" } | Select-Object -First 1
  if (-not $extracted) { throw "pgvector source extract failed" }
  if ($extracted.FullName -ne $srcDir) {
    Rename-Item -LiteralPath $extracted.FullName -NewName (Split-Path $srcDir -Leaf)
  }

  $buildCmd = @"
call `"$vcvars`" && set `"PGROOT=$PgRoot`" && cd /d `"$srcDir`" && nmake /F Makefile.win && nmake /F Makefile.win install
"@
  $cmdFile = Join-Path $CacheDir "build-pgvector.cmd"
  Set-Content -LiteralPath $cmdFile -Value $buildCmd -Encoding ascii
  Write-Step "Running nmake via vcvars64"
  & cmd.exe /c $cmdFile
  if ($LASTEXITCODE -ne 0) {
    throw "pgvector source build failed with exit $LASTEXITCODE"
  }
} else {
  $url = "https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/$PrebuiltTag/$PrebuiltAsset"
  $zip = Join-Path $CacheDir $PrebuiltAsset
  if (-not (Test-Path -LiteralPath $zip)) {
    Write-Step "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  } else {
    Write-Step "Using cached $zip"
  }

  $actual = Get-FileSha256 $zip
  if ($actual -ne $PrebuiltSha256.ToLowerInvariant()) {
    throw "SHA256 mismatch for $PrebuiltAsset. expected=$PrebuiltSha256 actual=$actual"
  }
  Write-Step "SHA256 OK ($actual)"

  $stage = Join-Path $CacheDir "pgvector-prebuilt-stage"
  if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
  }
  Ensure-Dir $stage
  Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force

  # Archives vary: flat, lib/, share/extension/, or nested folder.
  $dll = Get-ChildItem -LiteralPath $stage -Recurse -Filter "vector.dll" | Select-Object -First 1
  $control = Get-ChildItem -LiteralPath $stage -Recurse -Filter "vector.control" | Select-Object -First 1
  if (-not $dll -or -not $control) {
    throw "Prebuilt zip missing vector.dll or vector.control"
  }
  $sqlFiles = Get-ChildItem -LiteralPath $control.Directory.FullName -Filter "vector*.sql"

  Write-Step "Installing extension files into $PgRoot"
  Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $libDir "vector.dll") -Force
  Copy-Item -LiteralPath $control.FullName -Destination (Join-Path $extDir "vector.control") -Force
  foreach ($sql in $sqlFiles) {
    Copy-Item -LiteralPath $sql.FullName -Destination (Join-Path $extDir $sql.Name) -Force
  }
}

foreach ($must in @(
    (Join-Path $libDir "vector.dll"),
    (Join-Path $extDir "vector.control")
  )) {
  if (-not (Test-Path -LiteralPath $must)) {
    throw "pgvector install incomplete; missing $must"
  }
}

Write-Host "pgvector installed into $PgRoot" -ForegroundColor Green
