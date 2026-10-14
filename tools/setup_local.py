from pathlib import Path
import shutil
from backend.db import init_db

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if not env.exists():
    shutil.copy2(root / ".env.example", env)
init_db()
print("Configuración local lista.")
print("Ejecuta: python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000")
