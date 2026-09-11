@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\python.exe (
  echo Run scripts\vps\setup.ps1 first
  exit /b 1
)
.venv\Scripts\python.exe main.py
