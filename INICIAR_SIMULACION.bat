@echo off
chcp 65001 >nul
title SMCDI - Ducha Inteligente (simulacion)
cd /d "%~dp0"

echo ==============================================
echo   SMCDI - Sistema de Monitoreo de Ducha IoT
echo ==============================================

rem --- 1. Entorno virtual ---
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creando entorno virtual .venv ...
    py -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo No se encontro Python. Instalalo desde python.org y marca "Add to PATH".
        pause
        exit /b 1
    )
) else (
    echo [1/4] Entorno virtual encontrado.
)
set "PY=.venv\Scripts\python.exe"

rem --- 2. Dependencias ---
echo [2/4] Verificando dependencias (la primera vez tarda unos minutos)...
"%PY%" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Error instalando dependencias. Revisa tu conexion a Internet.
    pause
    exit /b 1
)

rem --- 3. Configuracion y base de datos ---
echo [3/4] Preparando .env y base de datos...
"%PY%" tools\setup_local.py
if errorlevel 1 (
    pause
    exit /b 1
)

rem --- 4. Servidor ---
echo [4/4] Iniciando servidor en http://127.0.0.1:8000
echo.
echo   Administrador: admin.ucsm / Admin2026!
echo   Moderador:     mod.turno1 / Moderador2026!
echo.
echo   Cierra esta ventana o presiona Ctrl+C para detenerlo.
echo.
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8000"
"%PY%" -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
pause
