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
  $buf = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buf)
  [Convert]::ToBase64String($buf).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-FernetKey {
  $buf = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buf)
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

if ($changed) {
  Set-Content -Path $EnvFile -Value $content -NoNewline -Encoding UTF8
}
Write-Host "Configuration ready."
