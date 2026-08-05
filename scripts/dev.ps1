# Local development helpers (Windows PowerShell)
# Usage from repo root: .\scripts\dev.ps1 api | web | migrate | seed

param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("api", "web", "migrate", "seed", "infra")]
  [string]$Target
)

$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
$env:DATABASE_URL = "postgresql+psycopg://mediarec:mediarec@localhost:5432/mediarec"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:PYTHONPATH = "$Root;$Root\packages;$Root\apps\api"

switch ($Target) {
  "infra" {
    docker compose -f (Join-Path $Root "infra\docker-compose.yml") up -d postgres redis
  }
  "migrate" {
    Set-Location (Join-Path $Root "apps\api")
    & (Join-Path $Root ".venv\Scripts\alembic.exe") upgrade head
  }
  "seed" {
    Set-Location (Join-Path $Root "apps\api")
    & $VenvPy -m app.seed
  }
  "api" {
    Set-Location (Join-Path $Root "apps\api")
    & $VenvUvicorn app.main:app --reload --host 127.0.0.1 --port 8000
  }
  "web" {
    Set-Location (Join-Path $Root "apps\web")
    npm run dev
  }
}
