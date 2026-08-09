# setup-env.ps1
# Runs once at install time (and safely on Start if .env is missing).
# Copies .env.example → .env and fills strong secrets so the API will boot.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $ScriptDir ".env.example")) {
  $Root = $ScriptDir
} elseif (Test-Path (Join-Path $ScriptDir "..\.env.example")) {
  $Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path
} else {
  $Root = Join-Path ${env:ProgramFiles} "Media Recommendation Engine"
}

$Example = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $Example)) {
  Write-Host "No .env.example found at $Example - skipping secret generation."
  exit 0
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

if (-not (Test-Path $EnvFile)) {
  Copy-Item -LiteralPath $Example -Destination $EnvFile -Force
  Write-Host "Created .env from .env.example."
}

$content = Get-Content -Raw -Path $EnvFile
$changed = $false

$placeholder = "change-me-in-production-use-long-random-string"
if ($content -match [regex]::Escape($placeholder)) {
  $secret = New-UrlSafeToken 48
  $content = $content.Replace("API_SECRET_KEY=$placeholder", "API_SECRET_KEY=$secret")
  Write-Host "Generated API_SECRET_KEY."
  $changed = $true
}

if ($content -match "(?m)^CREDENTIALS_FERNET_KEY=\s*$") {
  $fernet = New-FernetKey
  $content = $content -replace "(?m)^CREDENTIALS_FERNET_KEY=\s*$", "CREDENTIALS_FERNET_KEY=$fernet"
  Write-Host "Generated CREDENTIALS_FERNET_KEY."
  $changed = $true
}

# Rotate default weak DB/Redis passwords when still at example defaults.
if ($content -match "(?m)^POSTGRES_PASSWORD=mediarec\s*$") {
  $pgPass = New-UrlSafeToken 24
  $content = $content -replace "(?m)^POSTGRES_PASSWORD=mediarec\s*$", "POSTGRES_PASSWORD=$pgPass"
  $content = $content -replace "(?m)^DATABASE_URL=postgresql\+psycopg://mediarec:mediarec@", "DATABASE_URL=postgresql+psycopg://mediarec:${pgPass}@"
  Write-Host "Generated POSTGRES_PASSWORD."
  $changed = $true
}

if ($content -notmatch "(?m)^REDIS_PASSWORD=") {
  $redisPass = New-UrlSafeToken 24
  if ($content -match "(?m)^REDIS_URL=") {
    $content = $content -replace "(?m)^REDIS_URL=.*$", "REDIS_PASSWORD=$redisPass`nREDIS_URL=redis://:${redisPass}@localhost:6379/0"
  } else {
    $content = $content.TrimEnd() + "`nREDIS_PASSWORD=$redisPass`nREDIS_URL=redis://:${redisPass}@localhost:6379/0`n"
  }
  Write-Host "Generated REDIS_PASSWORD."
  $changed = $true
} elseif ($content -match "(?m)^REDIS_PASSWORD=mediarec-redis\s*$") {
  $redisPass = New-UrlSafeToken 24
  $content = $content -replace "(?m)^REDIS_PASSWORD=mediarec-redis\s*$", "REDIS_PASSWORD=$redisPass"
  $content = $content -replace "(?m)^REDIS_URL=.*$", "REDIS_URL=redis://:${redisPass}@localhost:6379/0"
  Write-Host "Rotated REDIS_PASSWORD."
  $changed = $true
}

if ($changed) {
  Set-Content -Path $EnvFile -Value $content -NoNewline -Encoding UTF8
}
Write-Host "Configuration ready."
