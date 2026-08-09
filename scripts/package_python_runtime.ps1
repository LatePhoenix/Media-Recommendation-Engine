#Requires -Version 5.1
<#
.SYNOPSIS
  Assemble an app-local Python 3.12 runtime and stage API/workers/packages for native Windows packaging.

.DESCRIPTION
  Downloads the official CPython 3.12 embeddable amd64 build, enables site-packages + pip,
  installs apps/api/requirements.txt, and copies application trees into:

    <OutDir>\
      runtime\python\     # embeddable interpreter + site-packages
      app\api\
      app\packages\
      app\workers\

  Matches docs/packaging/windows-layout.md (Program Files payload shape).

.PARAMETER OutDir
  Output root. Default: <repo>\dist\native-windows

.PARAMETER PythonVersion
  CPython version for the embeddable zip. Default: 3.12.10

.PARAMETER SkipDownload
  Reuse an existing runtime\python if present (still refreshes pip packages + app trees).

.EXAMPLE
  .\scripts\package_python_runtime.ps1
  .\scripts\verify_python_runtime.ps1
#>
param(
  [string]$OutDir = "",
  [string]$PythonVersion = "3.12.10",
  [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = Join-Path $RepoRoot "dist\native-windows"
}

$PythonRoot = Join-Path $OutDir "runtime\python"
$AppRoot = Join-Path $OutDir "app"
$CacheDir = Join-Path $RepoRoot "dist\cache"
$EmbedZipName = "python-$PythonVersion-embed-amd64.zip"
$EmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/$EmbedZipName"
$EmbedZip = Join-Path $CacheDir $EmbedZipName
$GetPip = Join-Path $CacheDir "get-pip.py"
$Requirements = Join-Path $RepoRoot "apps\api\requirements.txt"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Copy-Tree([string]$Source, [string]$Destination) {
  Ensure-Dir (Split-Path -Parent $Destination)
  if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
  }
  # Robocopy exit codes 0-7 are success-ish; >=8 is failure.
  & robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /nc /ns /np `
    /XD __pycache__ .pytest_cache .mypy_cache .ruff_cache .venv node_modules `
    /XF *.pyc *.pyo | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) {
    throw "robocopy failed copying '$Source' -> '$Destination' (exit $code)"
  }
}

Ensure-Dir $CacheDir
Ensure-Dir $OutDir

Write-Step "Output: $OutDir"

if (-not (Test-Path -LiteralPath $Requirements)) {
  throw "Missing requirements file: $Requirements"
}

$pythonExe = Join-Path $PythonRoot "python.exe"

if ($SkipDownload) {
  if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "SkipDownload set but missing $pythonExe - run without -SkipDownload first"
  }
  Write-Step "Skipping download; reusing $PythonRoot"
} else {
  if (-not (Test-Path -LiteralPath $EmbedZip)) {
    Write-Step "Downloading $EmbedUrl"
    Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip -UseBasicParsing
  } else {
    Write-Step "Using cached embed zip: $EmbedZip"
  }

  if (Test-Path -LiteralPath $PythonRoot) {
    Remove-Item -LiteralPath $PythonRoot -Recurse -Force
  }
  Ensure-Dir $PythonRoot
  Write-Step "Extracting embeddable Python to $PythonRoot"
  Expand-Archive -LiteralPath $EmbedZip -DestinationPath $PythonRoot -Force

  # Enable site-packages for pip (embed ._pth disables site by default).
  $pth = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*._pth" | Select-Object -First 1
  if (-not $pth) {
    throw "python*._pth not found under $PythonRoot"
  }
  $zipLib = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*.zip" |
    Where-Object { $_.Name -match '^python\d+\.zip$' } |
    Select-Object -First 1
  if (-not $zipLib) {
    $zipLib = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*.zip" | Select-Object -First 1
  }
  if (-not $zipLib) {
    throw "pythonXY.zip not found under $PythonRoot"
  }
  $pthLines = @(
    $zipLib.Name
    "."
    "Lib\site-packages"
    "import site"
  )
  Set-Content -LiteralPath $pth.FullName -Value ($pthLines -join "`r`n") -Encoding ascii
  Write-Step "Updated $($pth.Name) for site-packages"

  if (-not (Test-Path -LiteralPath $GetPip)) {
    Write-Step "Downloading get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
  }
  Write-Step "Installing pip into embeddable runtime"
  & $pythonExe $GetPip --no-warn-script-location
  if ($LASTEXITCODE -ne 0) {
    throw "get-pip.py failed with exit $LASTEXITCODE"
  }
}

Write-Step "Installing Python dependencies from requirements.txt"
& $pythonExe -m pip install --upgrade pip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $pythonExe -m pip install -r $Requirements --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed" }

Write-Step "Staging application trees under $AppRoot"
Copy-Tree (Join-Path $RepoRoot "apps\api") (Join-Path $AppRoot "api")
Copy-Tree (Join-Path $RepoRoot "packages") (Join-Path $AppRoot "packages")
Copy-Tree (Join-Path $RepoRoot "workers") (Join-Path $AppRoot "workers")

# Embeddable builds honor pythonXY._pth and ignore cwd / PYTHONPATH. Point at staged app trees
# (paths relative to runtime\python).
$pth = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) {
  throw "python*._pth not found under $PythonRoot after staging"
}
$zipLib = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*.zip" |
  Where-Object { $_.Name -match '^python\d+\.zip$' } |
  Select-Object -First 1
if (-not $zipLib) {
  $zipLib = Get-ChildItem -LiteralPath $PythonRoot -Filter "python*.zip" | Select-Object -First 1
}
$pthLines = @(
  $zipLib.Name
  "."
  "Lib\site-packages"
  "..\..\app\api"
  "..\..\app\packages"
  "..\..\app"
  "import site"
)
Set-Content -LiteralPath $pth.FullName -Value ($pthLines -join "`r`n") -Encoding ascii
Write-Step "Pinned app import paths in $($pth.Name)"

$meta = @"
python_version=$PythonVersion
embed_url=$EmbedUrl
built_utc=$((Get-Date).ToUniversalTime().ToString("o"))
repo=$RepoRoot
"@
Set-Content -LiteralPath (Join-Path $OutDir "python-runtime.meta.txt") -Value $meta -Encoding utf8

Write-Host ""
Write-Host "Python runtime packaged successfully." -ForegroundColor Green
Write-Host "  Python:  $pythonExe"
Write-Host "  App:     $AppRoot"
Write-Host "Next:      .\scripts\verify_python_runtime.ps1 -OutDir `"$OutDir`""
