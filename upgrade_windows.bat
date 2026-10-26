@echo off
setlocal
cd /d "%~dp0"
title SmearSight upgrade
if not exist ".venv\Scripts\python.exe" (
  echo  No .venv folder here. If this is a new install, run install_windows.bat instead.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" upgrade.py
pause
