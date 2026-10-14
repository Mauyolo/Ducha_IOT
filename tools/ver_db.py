from backend.db import get_conn, init_db

init_db()
with get_conn() as conn:
    for table in ["users", "residents", "devices", "sessions", "measurements", "alerts", "ai_models", "surveys"]:
        n = conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
        print(f"{table:16s}: {n}")
