#Requires -Version 5.1
<#
.SYNOPSIS
  Verify packaged Redis: start with ProgramData-style paths, PING, persist to disk.

.PARAMETER OutDir
  Native payload root

.PARAMETER DataRoot
  Mutable root for verify data/logs/config

.PARAMETER Port
  Ephemeral port (default 56379) to avoid clashing with Docker/dev 6379

.PARAMETER Password
  requirepass for the verify instance
#>
param(
  [string]$OutDir = "",
  [string]$DataRoot = "",
  [int]$Port = 56379,
  [string]$Password = "mediarec-redis-verify"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist\native-windows" }
if (-not $DataRoot) { $DataRoot = Join-Path $OutDir "verify-redis-data" }

$OutDir = [System.IO.Path]::GetFullPath($OutDir)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

$RedisRoot = Join-Path $OutDir "runtime\redis"
$Server = Join-Path $RedisRoot "redis-server.exe"
$Cli = Join-Path $RedisRoot "redis-cli.exe"
$WorkDir = Join-Path $DataRoot "redis"
$DataDir = Join-Path $WorkDir "data"
$ConfigFile = Join-Path $WorkDir "redis.conf"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

foreach ($p in @($Server, $Cli)) {
  if (-not (Test-Path -LiteralPath $p)) {
    throw "Missing $p - run scripts\package_redis_windows.ps1 first"
  }
}

# Stop any leftover verify instance.
Get-Process redis-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (Test-Path -LiteralPath $DataRoot) {
  Remove-Item -LiteralPath $DataRoot -Recurse -Force
}

Write-Step "Generating verify redis.conf under $DataRoot"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Initialize-MediaRecRedis.ps1") `
  -InstallRoot $OutDir -DataRoot $DataRoot -Password $Password -Port $Port
if ($LASTEXITCODE -ne 0) { throw "Initialize-MediaRecRedis.ps1 failed" }

Write-Step "Starting redis-server on 127.0.0.1:$Port (cwd=$WorkDir)"
$proc = Start-Process -FilePath $Server -ArgumentList @("redis.conf") -PassThru -WindowStyle Hidden -WorkingDirectory $WorkDir
Start-Sleep -Seconds 2
if ($proc.HasExited) {
  $logPath = Join-Path $DataRoot "logs\mediarec-redis\redis.log"
  $tail = if (Test-Path $logPath) { Get-Content $logPath -Tail 30 | Out-String } else { "(no logfile yet)" }
  throw "redis-server exited early (code $($proc.ExitCode)); log:`n$tail"
}

$ok = $false
try {
  Write-Step "PING"
  $pong = & $Cli -h 127.0.0.1 -p $Port -a $Password --no-auth-warning PING
  if ($LASTEXITCODE -ne 0 -or "$pong".Trim() -ne "PONG") {
    throw "PING failed: $pong (exit $LASTEXITCODE)"
  }
  Write-Host "PONG"

  Write-Step "SET/GET + BGSAVE"
  & $Cli -h 127.0.0.1 -p $Port -a $Password --no-auth-warning SET mediarec:verify "ok" | Out-Null
  $got = & $Cli -h 127.0.0.1 -p $Port -a $Password --no-auth-warning GET mediarec:verify
  if ("$got".Trim() -ne "ok") { throw "GET mismatch: $got" }
  & $Cli -h 127.0.0.1 -p $Port -a $Password --no-auth-warning BGSAVE | Out-Null
  Start-Sleep -Seconds 2

  $rdb = Join-Path $DataDir "dump.rdb"
  $aof = Join-Path $DataDir "appendonly.aof"
  $aofDir = Join-Path $DataDir "appendonlydir"
  $persisted = (Test-Path -LiteralPath $rdb) -or (Test-Path -LiteralPath $aof) -or (Test-Path -LiteralPath $aofDir)
  if (-not $persisted) {
    throw "No RDB/AOF under $DataDir after BGSAVE"
  }
  Write-Step "Persistence files present under $DataDir"
  Get-ChildItem -LiteralPath $DataDir | ForEach-Object { Write-Host "  $($_.Name)" }

  $runtimeFull = [System.IO.Path]::GetFullPath((Join-Path $OutDir "runtime\redis"))
  if ($DataDir.StartsWith($runtimeFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Data dir must not live under runtime\redis"
  }

  $ok = $true
} finally {
  Write-Step "Stopping redis-server"
  try {
    & $Cli -h 127.0.0.1 -p $Port -a $Password --no-auth-warning SHUTDOWN NOSAVE 2>$null | Out-Null
  } catch { }
  Start-Sleep -Seconds 1
  if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
}

if (-not $ok) { throw "Redis verification failed" }

Write-Host ""
Write-Host "Redis verification passed." -ForegroundColor Green
Write-Host "  Config: $ConfigFile"
Write-Host "  Data:   $DataDir"
Write-Host "  WinSW:  $(Join-Path $OutDir 'runtime\winsw\mediarec-redis.xml')"
