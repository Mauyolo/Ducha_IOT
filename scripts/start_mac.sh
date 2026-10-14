#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "No se encontró Python 3. Instálalo con Homebrew: brew install python"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "[1/4] Creando entorno virtual..."
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
printf '[2/4] Verificando dependencias...\n'
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[3/4] Se creó .env a partir de .env.example"
else
  echo "[3/4] Usando .env existente"
fi

# Carga variables simples KEY=VALUE ignorando comentarios.
set -a
source .env
set +a

HOST="${WEB_HOST:-127.0.0.1}"
PORT="${WEB_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

echo "[4/4] Iniciando SMCDI en ${URL}"
echo "Usuario demo: ${ADMIN_USER:-admin.ucsm}"
echo "Ctrl+C para detener."
(sleep 2; open "$URL" >/dev/null 2>&1 || true) &
exec python -m uvicorn backend.server:app --host "$HOST" --port "$PORT" --reload
