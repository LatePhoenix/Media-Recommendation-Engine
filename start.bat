@echo off
setlocal
cd /d "%~dp0"

REM One-click start for the full Media Recommendation Engine stack
REM (Docker Compose: Postgres, Redis, API, workers, web).

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-MediaRec.ps1"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo.
  echo Start failed with exit code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
