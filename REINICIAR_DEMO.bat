@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Esto borra la base local y vuelve a generar los 18 residentes y 108 sesiones de demostracion.
echo Cierra antes la ventana del servidor si esta abierta.
choice /m "Continuar"
if errorlevel 2 exit /b 0
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta INICIAR_SIMULACION.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\reset_demo.py
pause
