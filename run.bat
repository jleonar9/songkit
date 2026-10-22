@echo off
title Songkit - The Solid Ground
cd /d "%~dp0"
where ffmpeg >nul 2>nul || echo [!] ffmpeg not found. Install it with: winget install ffmpeg
if not exist .venv (
  echo First run: setting up... this takes a few minutes.
  python -m venv .venv || (echo Python not found. Install Python 3.10+ from python.org & pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python app.py
pause
