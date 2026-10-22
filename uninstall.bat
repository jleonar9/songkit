@echo off
title Remove Songkit
echo.
echo   This removes Songkit from this PC.
echo   Your songs and files in Documents\Songkit are kept.
echo.
choice /m "  Remove Songkit now"
if errorlevel 2 exit /b
powershell -NoProfile -Command "Remove-Item -Recurse -Force 'HKCU:\Software\Classes\songkit' -ErrorAction SilentlyContinue; Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Songkit.lnk') -ErrorAction SilentlyContinue; Remove-Item -Recurse (Join-Path ([Environment]::GetFolderPath('Programs')) 'Songkit') -ErrorAction SilentlyContinue"
echo   Songkit removed.
timeout /t 3 >nul
cd /d "%TEMP%"
(goto) 2>nul & rd /s /q "%~dp0"
