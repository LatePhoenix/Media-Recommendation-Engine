#Requires -Version 5.1
<#
.SYNOPSIS
  Download pinned Redis for Windows + WinSW and stage under dist/native-windows.

.DESCRIPTION
  Fetches Redis 7.4.10 (msys2 zip) and WinSW x64, verifies Redis SHA256, stages:

    <OutDir>\runtime\redis\          # redis-server, redis-cli, …
    <OutDir>\runtime\winsw\          # WinSW-x64.exe + mediarec-redis.exe/.xml
    <OutDir>\installer-payload\…     # copies of templates for the installer tree

.PARAMETER OutDir
  Native payload root (default: <repo>\dist\native-windows)

.EXAMPLE
  .\scripts\package_redis_windows.ps1
  .\scripts\verify_redis_windows.ps1
#>
param(
  [string]$OutDir = "",
  [string]$RedisTag = "7.4.10",
  [string]$RedisAsset = "Redis-7.4.10-Windows-x64-msys2.zip",
  [string]$RedisSha256 = "3cfa2fa4e85e61d633f5d13971a559bb7961ebc3dd647718bfa8cf9ec7717912",
  [string]$WinSwTag = "v2.12.0",
  [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$CacheDir = Join-Path $RepoRoot "dist\cache"
$RedisRoot = Join-Path $OutDir "runtime\redis"
$WinSwRoot = Join-Path $OutDir "runtime\winsw"
$RedisUrl = "https://github.com/redis-windows/redis-windows/releases/download/$RedisTag/$RedisAsset"
$RedisZip = Join-Path $CacheDir $RedisAsset
$WinSwUrl = "https://github.com/winsw/winsw/releases/download/$WinSwTag/WinSW-x64.exe"
$WinSwCache = Join-Path $CacheDir "WinSW-x64.exe"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-FileSha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Ensure-Dir $CacheDir
Ensure-Dir $OutDir

if (-not $SkipDownload) {
  if (-not (Test-Path -LiteralPath $RedisZip)) {
    Write-Step "Downloading $RedisUrl"
    Invoke-WebRequest -Uri $RedisUrl -OutFile $RedisZip -UseBasicParsing
  } else {
    Write-Step "Using cached $RedisZip"
  }
  if (-not (Test-Path -LiteralPath $WinSwCache)) {
    Write-Step "Downloading $WinSwUrl"
    Invoke-WebRequest -Uri $WinSwUrl -OutFile $WinSwCache -UseBasicParsing
  } else {
    Write-Step "Using cached WinSW"
  }
} else {
  if (-not (Test-Path -LiteralPath $RedisZip)) { throw "SkipDownload set but missing $RedisZip" }
  if (-not (Test-Path -LiteralPath $WinSwCache)) { throw "SkipDownload set but missing $WinSwCache" }
}

$actual = Get-FileSha256 $RedisZip
if ($actual -ne $RedisSha256.ToLowerInvariant()) {
  throw "SHA256 mismatch for $RedisAsset. expected=$RedisSha256 actual=$actual"
}
Write-Step "Redis SHA256 OK ($actual)"

$extract = Join-Path $CacheDir "redis-extract"
if (Test-Path -LiteralPath $extract) {
  Remove-Item -LiteralPath $extract -Recurse -Force
}
Ensure-Dir $extract
Write-Step "Extracting Redis"
Expand-Archive -LiteralPath $RedisZip -DestinationPath $extract -Force

$server = Get-ChildItem -LiteralPath $extract -Recurse -Filter "redis-server.exe" | Select-Object -First 1
if (-not $server) {
  throw "redis-server.exe not found in $RedisAsset"
}
$srcRedisDir = $server.Directory.FullName

if (Test-Path -LiteralPath $RedisRoot) {
  Remove-Item -LiteralPath $RedisRoot -Recurse -Force
}
Ensure-Dir (Split-Path -Parent $RedisRoot)
Write-Step "Staging Redis to $RedisRoot"
& robocopy $srcRedisDir $RedisRoot /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy redis failed (exit $LASTEXITCODE)" }

# Ship our template (not any default conf from the zip) next to binaries for reference.
Copy-Item -LiteralPath (Join-Path $RepoRoot "installer\redis\redis.conf.template") `
  -Destination (Join-Path $RedisRoot "redis.conf.template") -Force

Ensure-Dir $WinSwRoot
Copy-Item -LiteralPath $WinSwCache -Destination (Join-Path $WinSwRoot "WinSW-x64.exe") -Force
Copy-Item -LiteralPath $WinSwCache -Destination (Join-Path $WinSwRoot "mediarec-redis.exe") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "installer\services\mediarec-redis.xml") `
  -Destination (Join-Path $WinSwRoot "mediarec-redis.xml") -Force

$meta = @"
redis_tag=$RedisTag
redis_asset=$RedisAsset
redis_url=$RedisUrl
redis_sha256=$RedisSha256
winsw_tag=$WinSwTag
built_utc=$((Get-Date).ToUniversalTime().ToString("o"))
"@
Set-Content -LiteralPath (Join-Path $OutDir "redis-runtime.meta.txt") -Value $meta -Encoding utf8

Write-Host ""
Write-Host "Redis runtime packaged successfully." -ForegroundColor Green
Write-Host "  Redis: $RedisRoot"
Write-Host "  WinSW: $WinSwRoot"
Write-Host "Next:   .\scripts\verify_redis_windows.ps1 -OutDir `"$OutDir`""
