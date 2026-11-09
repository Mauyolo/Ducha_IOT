from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))  # permite ejecutar "python tools/setup_local.py" desde cualquier carpeta

env = root / ".env"
if not env.exists():
    shutil.copy2(root / ".env.example", env)
    print("Se creó .env a partir de .env.example")

from backend.db import init_db  # noqa: E402  (importar después de crear .env)

init_db()
print("Configuración local lista.")
print("Ejecuta: python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000")
