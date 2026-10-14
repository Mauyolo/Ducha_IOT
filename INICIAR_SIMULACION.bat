@echo off
cd /d "%~dp0"
py tools\setup_local.py --simular
if errorlevel 1 exit /b 1
py -m backend.server
pause
