#Requires -Version 5.1
<#
.SYNOPSIS
  Verify a packaged native Windows Python runtime (imports + launcher help).

.DESCRIPTION
  Does not require Postgres/Redis. Sets a throwaway API_SECRET_KEY for import-time
  settings validation. Expects output from package_python_runtime.ps1.

.PARAMETER OutDir
  Packaged root (default: <repo>\dist\native-windows)

.EXAMPLE
  .\scripts\package_python_runtime.ps1
  .\scripts\verify_python_runtime.ps1
#>
param(
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$PythonExe = Join-Path $OutDir "runtime\python\python.exe"
$ApiRoot = Join-Path $OutDir "app\api"
$Packages = Join-Path $OutDir "app\packages"
$AppPayload = Join-Path $OutDir "app"

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw "Missing packaged python: $PythonExe - run scripts\package_python_runtime.ps1 first"
}
if (-not (Test-Path -LiteralPath $ApiRoot)) {
  throw "Missing staged API tree: $ApiRoot"
}

# Throwaway secret - verification only; never ship this as a real install secret.
$env:API_SECRET_KEY = "verify-only-secret-key-not-for-production-use-0123456789"
$env:MEDIAREC_ROOT = $OutDir
# Clear dotenv interference from a developer checkout.
$env:MEDIAREC_ENV_FILE = ""
Remove-Item Env:CREDENTIALS_FERNET_KEY -ErrorAction SilentlyContinue

$env:PYTHONPATH = "$ApiRoot;$Packages;$AppPayload"

Write-Host "==> Verifying third-party imports" -ForegroundColor Cyan
& $PythonExe -c @"
import fastapi, sqlalchemy, alembic, psycopg, redis, rq, uvicorn, pydantic, pydantic_settings
print('ok: fastapi', fastapi.__version__)
print('ok: sqlalchemy', sqlalchemy.__version__)
print('ok: alembic', alembic.__version__)
print('ok: psycopg', psycopg.__version__)
print('ok: redis', redis.__version__)
print('ok: rq', rq.__version__)
print('ok: uvicorn', uvicorn.__version__)
"@
if ($LASTEXITCODE -ne 0) { throw "Third-party import check failed" }

Write-Host "==> Verifying project imports (app, workers, enrichment)" -ForegroundColor Cyan
& $PythonExe -c @"
import sys
from pathlib import Path
api = Path(r'$ApiRoot')
shared = Path(r'$AppPayload')
for p in (api, shared / 'packages', shared):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.paths import ensure_sys_path, resolve_shared_root, resolve_env_files
ensure_sys_path()
print('shared_root', resolve_shared_root())
print('env_files', resolve_env_files())

import app.main
import workers.importers.runner
import workers.recommender.jobs
import enrichment.factory
print('ok: app.main', app.main.app.title)
print('ok: workers + enrichment')
"@
if ($LASTEXITCODE -ne 0) { throw "Project import check failed" }

Write-Host "==> Verifying launcher CLI" -ForegroundColor Cyan
Push-Location $ApiRoot
try {
  & $PythonExe -m app.launch --help
  if ($LASTEXITCODE -ne 0) { throw "app.launch --help failed" }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Verification passed for $OutDir" -ForegroundColor Green
