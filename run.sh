#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || echo "[!] ffmpeg not found - install it first."
if [ ! -d .venv ]; then
  echo "First run: setting up..."
  python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python app.py
