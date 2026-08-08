@echo off
setlocal
cd /d "%~dp0"

REM Stops the Media Recommendation Engine Docker Compose stack.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Stop-MediaRec.ps1"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo.
  echo Stop failed with exit code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
