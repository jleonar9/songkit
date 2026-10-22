@echo off
title Songkit - keep this window open while you use Songkit
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Songkit isn't set up here yet. Double-click Install-Songkit.bat first.
  pause
  exit /b 1
)
rem Already running? Just open it in the browser.
powershell -NoProfile -Command "try { Invoke-WebRequest http://127.0.0.1:7860/config -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
  start "" http://127.0.0.1:7860
  exit /b 0
)
echo.
echo   Songkit is starting... (first start can take about 20 seconds)
echo   Keep this window open while you use Songkit. Close it to quit.
echo.
".venv\Scripts\python.exe" app.py
