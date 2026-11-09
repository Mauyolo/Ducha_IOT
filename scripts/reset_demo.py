from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import reset_demo  # noqa: E402

if __name__ == "__main__":
    reset_demo()
    print("Base de datos de demostración regenerada correctamente.")
