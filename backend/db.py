from __future__ import annotations

import json
import math
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config
from .security import hash_password

ISO = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def dt_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_dict(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def init_db(seed_demo: bool | None = None) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with get_conn() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        for key, (value, value_type, description) in config.DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO configuration(key,value,value_type,description) VALUES(?,?,?,?)",
                (key, value, value_type, description),
            )
        user = conn.execute("SELECT id FROM users WHERE username=?", (config.ADMIN_USER,)).fetchone()
        if not user:
            conn.execute(
                "INSERT INTO users(username,full_name,role,password_hash,is_active) VALUES(?,?,?,?,1)",
                (config.ADMIN_USER, config.ADMIN_NAME, "ADMINISTRADOR", hash_password(config.ADMIN_PASSWORD)),
            )
    if seed_demo if seed_demo is not None else config.SEED_DEMO:
        seed_demo_data()


def get_config_value(key: str, default: Any = None, conn: sqlite3.Connection | None = None) -> Any:
    if conn is None:
        with get_conn() as local_conn:
            row = local_conn.execute("SELECT value,value_type FROM configuration WHERE key=?", (key,)).fetchone()
    else:
        row = conn.execute("SELECT value,value_type FROM configuration WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    value, value_type = row["value"], row["value_type"]
    try:
        if value_type == "int":
            return int(float(value))
        if value_type == "float":
            return float(value)
        if value_type == "bool":
            return str(value).lower() in {"1", "true", "yes", "on"}
    except Exception:
        return default
    return value


def set_config_value(key: str, value: Any, value_type: str | None = None, description: str | None = None) -> None:
    if value_type is None:
        value_type = "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "float" if isinstance(value, float) else "str"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO configuration(key,value,value_type,description,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,value_type=excluded.value_type,"
            "description=COALESCE(excluded.description,configuration.description),updated_at=excluded.updated_at",
            (key, str(value), value_type, description, now_iso()),
        )


def next_code(prefix: str, table: str, width: int = 5, conn: sqlite3.Connection | None = None) -> str:
    year = datetime.now().year
    if conn is None:
        with get_conn() as local_conn:
            n = local_conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] + 1
    else:
        n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] + 1
    return f"{prefix}-{year}-{n:0{width}d}"


def add_audit(user_id: int | None, action: str, entity: str, entity_id: Any = None, data: Any = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log(user_id,action,entity,entity_id,data_json,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, action, entity, None if entity_id is None else str(entity_id), json.dumps(data, ensure_ascii=False) if data is not None else None, now_iso()),
        )


def _seed_residents(conn: sqlite3.Connection) -> None:
    names = [
        ("R-001", "María Quispe", "101", "74210301", "maria.qu@demo.local"),
        ("R-002", "José Rodríguez", "104", "74210302", "jose.ro@demo.local"),
        ("R-003", "Ana Pérez López", "203", "72680413", "ana.perez@demo.local"),
        ("R-004", "Lucía Fernández", "215", "74210304", "lucia.fe@demo.local"),
        ("R-005", "Diego Salazar", "306", "74210305", "diego.sa@demo.local"),
        ("R-006", "Valeria Chávez", "315", "74210306", "valeria.ch@demo.local"),
        ("R-007", "Rosa Huamán", "117", "74210307", "rosa.hu@demo.local"),
        ("R-008", "Carlos Mendoza", "208", "74210308", "carlos.me@demo.local"),
        ("R-009", "Elena Vargas", "312", "74210309", "elena.va@demo.local"),
        ("R-010", "Luis Torres", "109", "74210310", "luis.to@demo.local"),
        ("R-011", "Carmen Flores", "221", "74210311", "carmen.fl@demo.local"),
        ("R-012", "Jorge Medina", "303", "74210312", "jorge.me@demo.local"),
        ("R-013", "Teresa Ramos", "118", "74210313", "teresa.ra@demo.local"),
        ("R-014", "Miguel Condori", "214", "74210314", "miguel.co@demo.local"),
        ("R-015", "Julia Paredes", "310", "74210315", "julia.pa@demo.local"),
        ("R-016", "Alberto Gutiérrez", "120", "74210316", "alberto.gu@demo.local"),
        ("R-017", "Nora Vilca", "216", "74210317", "nora.vi@demo.local"),
        ("R-018", "Pedro Cáceres", "318", "74210318", "pedro.ca@demo.local"),
    ]
    rng = random.Random(2026)
    for i, (code, name, room, dni, email) in enumerate(names):
        pref = [23.0, 24.0, 24.0, 23.0, 24.0, 24.0, 25.0, 25.0][i % 8]
        condition = "INTELIGENTE" if i % 2 else "TRADICIONAL"
        sequence = "T-I" if i % 2 == 0 else "I-T"
        goal = round(rng.uniform(30.0, 36.0), 1)
        conn.execute(
            "INSERT OR IGNORE INTO residents(code,display_name,dni,room,email,preferred_temp,default_goal_l,condition_mode,experiment_sequence,enabled,consent_valid) "
            "VALUES(?,?,?,?,?,?,?,?,?,1,1)",
            (code, name, dni, room, email, pref, goal, condition, sequence),
        )


def _seed_sessions(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE experimental=1").fetchone()["n"] >= 108:
        return
    rng = random.Random(42026)
    residents = conn.execute("SELECT * FROM residents ORDER BY id LIMIT 18").fetchall()
    device = conn.execute("SELECT id FROM devices WHERE device_code='DUCHA-01'").fetchone()
    device_id = device["id"]
    now = datetime.now().replace(microsecond=0)
    serial = 1
    for resident in residents:
        # 3 tradicional + 3 inteligente = 6 por residente.
        modes = ["TRADICIONAL", "INTELIGENTE", "TRADICIONAL", "INTELIGENTE", "TRADICIONAL", "INTELIGENTE"]
        if resident["experiment_sequence"] == "I-T":
            modes = ["INTELIGENTE", "TRADICIONAL", "INTELIGENTE", "TRADICIONAL", "INTELIGENTE", "TRADICIONAL"]
        base = rng.uniform(39.0, 45.0)
        for j, mode in enumerate(modes):
            start = now - timedelta(days=27 - (resident["id"] % 8) * 2 - j * 3, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
            duration = rng.randint(430, 680)
            pause_count = rng.choice([0, 1, 1, 2])
            pause_s = pause_count * rng.randint(18, 55)
            effective = max(240, duration - pause_s)
            if mode == "TRADICIONAL":
                volume = max(26.0, rng.gauss(base, 3.2))
            else:
                volume = max(20.0, rng.gauss(base * 0.78, 2.5))
            avg_flow = volume / (effective / 60)
            max_flow = avg_flow * rng.uniform(1.08, 1.25)
            avg_temp = resident["preferred_temp"] + rng.uniform(-0.8, 0.8)
            max_temp = avg_temp + rng.uniform(0.5, 1.6)
            target = resident["default_goal_l"] if mode == "INTELIGENTE" else None
            code = f"SES-{now.year}-{serial:05d}"
            serial += 1
            conn.execute(
                "INSERT OR IGNORE INTO sessions(code,resident_id,device_id,mode,status,started_at,ended_at,total_duration_s,effective_duration_s,pause_count,pause_duration_s,volume_total_l,avg_flow_lmin,max_flow_lmin,avg_temp_c,max_temp_c,target_l,quality,experimental) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'VALIDA',1)",
                (code, resident["id"], device_id, mode, "FINALIZADA", dt_iso(start), dt_iso(start + timedelta(seconds=duration)), duration, effective, pause_count, pause_s, round(volume, 2), round(avg_flow, 2), round(max_flow, 2), round(avg_temp, 2), round(max_temp, 2), target),
            )
    # Guarantee an exact sample of 108 if an old partially seeded DB existed.
    ids = conn.execute("SELECT id FROM sessions WHERE experimental=1 ORDER BY id").fetchall()
    if len(ids) > 108:
        conn.executemany("DELETE FROM sessions WHERE id=?", [(r["id"],) for r in ids[108:]])


def _seed_alerts(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]:
        return
    rows = [
        ("Consumo excesivo", "ALTA", "PENDIENTE", "Una sesión alcanzó un volumen superior al límite configurado."),
        ("Duración prolongada", "MEDIA", "REVISADA", "Sesión superior al tiempo recomendado; revisar retroalimentación."),
        ("Temperatura elevada", "ALTA", "REVISADA", "Evento térmico registrado y tratado por el control determinístico."),
        ("Patrón inusual", "MEDIA", "REVISADA", "Consumo superior al promedio histórico del residente."),
        ("Ahorro semanal", "BAJA", "RESUELTA", "Reducción semanal observada respecto al periodo previo."),
    ]
    resident_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM residents").fetchall()}
    session_ids = conn.execute("SELECT id,resident_id FROM sessions ORDER BY id DESC LIMIT 10").fetchall()
    for i, (kind, severity, status, description) in enumerate(rows, 1):
        sess = session_ids[i % len(session_ids)]
        conn.execute(
            "INSERT INTO alerts(code,session_id,resident_id,kind,severity,description,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (f"ALR-{datetime.now().year}-{40+i:04d}", sess["id"], sess["resident_id"], kind, severity, description, status, dt_iso(datetime.now() - timedelta(hours=i*5))),
        )


def _seed_users(conn: sqlite3.Connection) -> None:
    demo_users = [
        ("mod.turno1", "Luis Herrera", "MODERADOR", "Moderador2026!", 1),
        ("mod.turno2", "Carla Medina", "MODERADOR", "Moderador2026!", 0),
    ]
    for username, full_name, role, password, active in demo_users:
        if not conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            conn.execute(
                "INSERT INTO users(username,full_name,role,password_hash,is_active) VALUES(?,?,?,?,?)",
                (username, full_name, role, hash_password(password), active),
            )


def seed_demo_data() -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices(device_code,name,room,status,last_seen,firmware_version,ip_address) VALUES('DUCHA-01','Prototipo Ducha IoT','Laboratorio','CONECTADO',?, '1.0.0','192.168.1.80')",
            (now_iso(),),
        )
        _seed_users(conn)
        _seed_residents(conn)
        _seed_sessions(conn)
        _seed_alerts(conn)


def ensure_demo_live_session() -> dict[str, Any] | None:
    with get_conn() as conn:
        active = conn.execute(
            "SELECT s.*,r.code AS resident_code,r.display_name,d.device_code FROM sessions s JOIN residents r ON r.id=s.resident_id LEFT JOIN devices d ON d.id=s.device_id WHERE s.status IN ('PREPARADA','ACTIVA','PAUSADA') ORDER BY s.id DESC LIMIT 1"
        ).fetchone()
        if active:
            return dict(active)
        resident = conn.execute("SELECT * FROM residents WHERE code='R-003'").fetchone()
        device = conn.execute("SELECT * FROM devices WHERE device_code='DUCHA-01'").fetchone()
        if not resident or not device:
            return None
        max_id = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"] + 1
        code = f"SES-{datetime.now().year}-{max_id:05d}"
        target = resident["default_goal_l"] or 30.1
        conn.execute(
            "INSERT INTO sessions(code,resident_id,device_id,mode,status,started_at,target_l,quality,experimental) VALUES(?,?,?,?,?,?,?,?,0)",
            (code, resident["id"], device["id"], "INTELIGENTE", "ACTIVA", now_iso(), target, "DEMO"),
        )
        row = conn.execute(
            "SELECT s.*,r.code AS resident_code,r.display_name,d.device_code FROM sessions s JOIN residents r ON r.id=s.resident_id LEFT JOIN devices d ON d.id=s.device_id WHERE s.code=?",
            (code,),
        ).fetchone()
        return dict(row)


def reset_demo() -> None:
    # Elimina también archivos auxiliares de SQLite WAL y modelos anteriores para
    # que la demostración quede completamente reproducible.
    for candidate in (config.DB_PATH, Path(str(config.DB_PATH) + "-wal"), Path(str(config.DB_PATH) + "-shm")):
        try:
            if candidate.exists():
                candidate.unlink()
        except OSError:
            pass
    if config.MODELS_DIR.exists():
        for model_file in config.MODELS_DIR.glob("*.joblib"):
            try:
                model_file.unlink()
            except OSError:
                pass
    init_db(seed_demo=True)
