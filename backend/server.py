from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .ai_service import ai_dashboard, list_models, predict_for_resident, train_models
from .db import (
    add_audit,
    get_config_value,
    get_conn,
    init_db,
    next_code,
    now_iso,
    reset_demo,
    rows_dict,
    set_config_value,
)
from .mqtt_service import mqtt_service
from .realtime import hub
from .security import AuthSession, create_token, get_session, revoke_token, verify_password, hash_password
from .simulator import simulator
from .telemetry import process_event, process_telemetry

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    hub.bind_loop(asyncio.get_running_loop())
    mqtt_service.start()
    if config.SIMULATION:
        simulator.start()
    try:
        yield
    finally:
        simulator.stop()
        mqtt_service.stop()


app = FastAPI(
    title="SMCDI – Sistema de Monitoreo y Control de Ducha Inteligente",
    version="1.0.0",
    description="Backend IoT, monitoreo en tiempo real, persistencia y analítica del PFC UCSM 2026.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Modelos de entrada
# -----------------------------
class LoginBody(BaseModel):
    username: str
    password: str


class ResidentBody(BaseModel):
    code: str | None = None
    display_name: str
    dni: str | None = None
    room: str | None = None
    email: str | None = None
    preferred_temp: float = 24.0
    default_goal_l: float | None = None
    condition_mode: str = "INTELIGENTE"
    experiment_sequence: str = "T-I"
    enabled: bool = True
    consent_valid: bool = True


class PrepareSessionBody(BaseModel):
    programacion_id: int | None = None
    resident_id: int | None = None
    device_id: int | None = None
    mode: str | None = None


class StopSessionBody(BaseModel):
    request_id: str | None = None
    motivo: str = "Detención solicitada por personal autorizado"


class AlertPatchBody(BaseModel):
    status: str
    note: str | None = None


class ConfigPatchBody(BaseModel):
    values: dict[str, Any]


class SurveyBody(BaseModel):
    resident_id: int
    session_id: int | None = None
    moment: str
    answers: list[int] = Field(min_length=20, max_length=20)


class UserCreateBody(BaseModel):
    username: str
    full_name: str
    role: str
    password: str
    is_active: bool = True


class UserPatchBody(BaseModel):
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: bool | None = None


class PredictionBody(BaseModel):
    programacion_id: int | None = None
    resident_id: int | None = None
    reduction_pct: float | None = None


# -----------------------------
# Autenticación y permisos
# -----------------------------
def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token inválido")
    return parts[1].strip()


def current_session(authorization: str | None = Header(default=None)) -> AuthSession:
    token = _extract_token(authorization)
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o inválida")
    return session


def admin_only(session: AuthSession = Depends(current_session)) -> AuthSession:
    if session.role != "ADMINISTRADOR":
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    return session


def staff_only(session: AuthSession = Depends(current_session)) -> AuthSession:
    if session.role not in {"ADMINISTRADOR", "MODERADOR"}:
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    return session


# -----------------------------
# Utilidades
# -----------------------------
def _session_detail(session_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*, r.code resident_code, r.display_name, r.room, r.preferred_temp,
                   d.device_code, d.name device_name, d.status device_status
            FROM sessions s
            JOIN residents r ON r.id=s.resident_id
            LEFT JOIN devices d ON d.id=s.device_id
            WHERE s.id=?
            """,
            (session_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        latest = conn.execute(
            "SELECT * FROM measurements WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)
        ).fetchone()
        events = conn.execute(
            "SELECT * FROM session_events WHERE session_id=? ORDER BY id DESC LIMIT 25", (session_id,)
        ).fetchall()
    result = dict(row)
    result["latest"] = dict(latest) if latest else None
    result["events"] = [dict(x) for x in events]
    return result


def _build_dashboard() -> dict[str, Any]:
    today = datetime.now().date().isoformat()
    with get_conn() as conn:
        today_rows = conn.execute(
            "SELECT * FROM sessions WHERE substr(started_at,1,10)=?", (today,)
        ).fetchall()
        # En presentación local puede no haber 12 sesiones en la fecha actual; la interfaz refleja la BD real.
        consumption_today = sum(float(r["volume_total_l"] or 0) for r in today_rows)
        active_count = conn.execute(
            "SELECT COUNT(*) n FROM sessions WHERE status IN ('PREPARADA','ACTIVA','PAUSADA')"
        ).fetchone()["n"]
        alerts_active = conn.execute(
            "SELECT COUNT(*) n FROM alerts WHERE status='PENDIENTE'"
        ).fetchone()["n"]

        comp = conn.execute(
            """
            SELECT mode, COUNT(*) n, AVG(volume_total_l) avg_l, AVG(total_duration_s) avg_s
            FROM sessions
            WHERE status='FINALIZADA' AND quality='VALIDA' AND experimental=1
            GROUP BY mode
            """
        ).fetchall()
        by_mode = {r["mode"]: dict(r) for r in comp}
        trad = float(by_mode.get("TRADICIONAL", {}).get("avg_l") or 0)
        intel = float(by_mode.get("INTELIGENTE", {}).get("avg_l") or 0)
        reduction = ((trad - intel) / trad * 100) if trad else 0

        recent = conn.execute(
            """
            SELECT s.id,s.code,s.started_at,s.mode,s.status,s.volume_total_l,s.total_duration_s,
                   r.code resident_code,r.display_name,r.room
            FROM sessions s JOIN residents r ON r.id=s.resident_id
            ORDER BY COALESCE(s.started_at,s.created_at) DESC LIMIT 8
            """
        ).fetchall()

        daily = conn.execute(
            """
            SELECT substr(started_at,1,10) day, ROUND(SUM(volume_total_l),2) liters,
                   COUNT(*) sessions
            FROM sessions
            WHERE started_at IS NOT NULL
            GROUP BY substr(started_at,1,10)
            ORDER BY day DESC LIMIT 7
            """
        ).fetchall()

        device = conn.execute("SELECT * FROM devices ORDER BY id LIMIT 1").fetchone()
    return {
        "date": today,
        "consumption_today_l": round(consumption_today, 2),
        "sessions_today": len(today_rows),
        "active_sessions": active_count,
        "reduction_pct": round(reduction, 1),
        "active_alerts": alerts_active,
        "comparison": {
            "traditional_avg_l": round(trad, 2),
            "intelligent_avg_l": round(intel, 2),
            "traditional_n": int(by_mode.get("TRADICIONAL", {}).get("n") or 0),
            "intelligent_n": int(by_mode.get("INTELIGENTE", {}).get("n") or 0),
        },
        "daily": [dict(x) for x in reversed(daily)],
        "recent": [dict(x) for x in recent],
        "device": dict(device) if device else None,
    }


# -----------------------------
# API: autenticación
# -----------------------------
@app.post("/api/v1/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (body.username.strip(),)).fetchone()
        if not user or not user["is_active"] or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), user["id"]))
    token = create_token(user["id"], user["username"], user["role"], config.TOKEN_TTL_HOURS)
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]},
    }


@app.post("/api/v1/auth/logout")
def logout(authorization: str | None = Header(default=None), session: AuthSession = Depends(current_session)) -> dict[str, bool]:
    token = _extract_token(authorization)
    revoke_token(token)
    return {"ok": True}


@app.get("/api/v1/auth/me")
def auth_me(session: AuthSession = Depends(current_session)) -> dict[str, Any]:
    with get_conn() as conn:
        user = conn.execute("SELECT id,username,full_name,role,is_active,last_login FROM users WHERE id=?", (session.user_id,)).fetchone()
    return dict(user) if user else {"username": session.username, "role": session.role}


# -----------------------------
# API: estado general / dashboard
# -----------------------------
@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    with get_conn() as conn:
        db_ok = conn.execute("SELECT 1 ok").fetchone()["ok"] == 1
        device = conn.execute("SELECT * FROM devices ORDER BY id LIMIT 1").fetchone()
    return {
        "ok": True,
        "database": db_ok,
        "mqtt": mqtt_service.status(),
        "simulation": config.SIMULATION,
        "device": dict(device) if device else None,
        "time": now_iso(),
    }


@app.get("/api/v1/dashboard")
def dashboard(_: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    return _build_dashboard()


@app.get("/api/v1/dispositivos")
def devices(_: AuthSession = Depends(staff_only)) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
    return [dict(x) for x in rows]


# -----------------------------
# API: residentes
# -----------------------------
@app.get("/api/v1/residentes")
def residents(
    q: str | None = None,
    estado: str | None = None,
    _: AuthSession = Depends(staff_only),
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if q:
        clauses.append("(r.code LIKE ? OR r.display_name LIKE ? OR r.dni LIKE ? OR r.room LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term, term])
    if estado:
        enabled = 1 if estado.upper() in {"ACTIVO", "HABILITADO", "1"} else 0
        clauses.append("r.enabled=?")
        params.append(enabled)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, COUNT(s.id) session_count,
                   ROUND(AVG(CASE WHEN s.status='FINALIZADA' THEN s.volume_total_l END),2) avg_volume_l,
                   ROUND(AVG(CASE WHEN s.status='FINALIZADA' THEN s.total_duration_s END),0) avg_duration_s
            FROM residents r
            LEFT JOIN sessions s ON s.resident_id=r.id AND s.experimental=1
            WHERE {' AND '.join(clauses)}
            GROUP BY r.id ORDER BY r.code
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/v1/residentes", status_code=201)
def create_resident(body: ResidentBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    mode = body.condition_mode.upper()
    if mode not in {"TRADICIONAL", "INTELIGENTE"}:
        raise HTTPException(status_code=400, detail="Modo inválido")
    with get_conn() as conn:
        if body.code:
            code = body.code.strip().upper()
        else:
            n = conn.execute("SELECT COUNT(*) n FROM residents").fetchone()["n"] + 1
            code = f"R-{n:03d}"
        try:
            conn.execute(
                """
                INSERT INTO residents(code,display_name,dni,room,email,preferred_temp,default_goal_l,condition_mode,experiment_sequence,enabled,consent_valid)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    code, body.display_name.strip(), body.dni, body.room, body.email,
                    body.preferred_temp, body.default_goal_l, mode, body.experiment_sequence,
                    int(body.enabled), int(body.consent_valid),
                ),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"No se pudo registrar el residente: {exc}") from exc
        row = conn.execute("SELECT * FROM residents WHERE code=?", (code,)).fetchone()
    add_audit(session.user_id, "CREATE", "resident", row["id"], {"code": code})
    return dict(row)


@app.get("/api/v1/residentes/{resident_id}")
def resident_detail(resident_id: int, _: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    with get_conn() as conn:
        resident = conn.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
        if not resident:
            raise HTTPException(status_code=404, detail="Residente no encontrado")
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE resident_id=? ORDER BY COALESCE(started_at,created_at) DESC LIMIT 30", (resident_id,)
        ).fetchall()
        stats = conn.execute(
            """
            SELECT COUNT(*) n, ROUND(AVG(volume_total_l),2) avg_volume_l,
                   ROUND(AVG(total_duration_s),0) avg_duration_s,
                   ROUND(AVG(avg_temp_c),2) avg_temp_c
            FROM sessions WHERE resident_id=? AND status='FINALIZADA' AND experimental=1 AND quality='VALIDA'
            """,
            (resident_id,),
        ).fetchone()
        target = conn.execute(
            "SELECT * FROM consumption_targets WHERE resident_id=? AND active=1 ORDER BY id DESC LIMIT 1", (resident_id,)
        ).fetchone()
    return {"resident": dict(resident), "stats": dict(stats), "sessions": [dict(s) for s in sessions], "target": dict(target) if target else None}


@app.patch("/api/v1/residentes/{resident_id}")
def update_resident(resident_id: int, body: dict[str, Any], session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    allowed = {
        "display_name", "dni", "room", "email", "preferred_temp", "default_goal_l", "condition_mode",
        "experiment_sequence", "enabled", "consent_valid",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")
    if "enabled" in updates:
        updates["enabled"] = int(bool(updates["enabled"]))
    if "consent_valid" in updates:
        updates["consent_valid"] = int(bool(updates["consent_valid"]))
    sets = ",".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM residents WHERE id=?", (resident_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Residente no encontrado")
        conn.execute(f"UPDATE residents SET {sets} WHERE id=?", (*updates.values(), resident_id))
        row = conn.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
    add_audit(session.user_id, "UPDATE", "resident", resident_id, updates)
    return dict(row)


# -----------------------------
# API: sesiones y telemetría
# -----------------------------
@app.get("/api/v1/sesiones/activa")
def active_session(_: AuthSession = Depends(staff_only)) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE status IN ('PREPARADA','ACTIVA','PAUSADA') ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _session_detail(row["id"]) if row else None


@app.post("/api/v1/sesiones/preparar", status_code=201)
def prepare_session(body: PrepareSessionBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    # 1) Validación/lectura sin mantener una transacción abierta mientras se ejecuta IA.
    with get_conn() as conn:
        active = conn.execute("SELECT id FROM sessions WHERE status IN ('PREPARADA','ACTIVA','PAUSADA') LIMIT 1").fetchone()
        if active:
            raise HTTPException(status_code=409, detail="Ya existe una sesión activa o preparada")

        program = None
        if body.programacion_id:
            program = conn.execute("SELECT * FROM session_programs WHERE id=?", (body.programacion_id,)).fetchone()
            if not program:
                raise HTTPException(status_code=404, detail="Programación no encontrada")
            resident_id = program["resident_id"]
            device_id = body.device_id or program["device_id"]
            mode = (body.mode or program["planned_mode"]).upper()
        else:
            resident_id = body.resident_id
            device_id = body.device_id
            mode = (body.mode or "INTELIGENTE").upper()

        if not resident_id:
            raise HTTPException(status_code=400, detail="resident_id es obligatorio")
        if mode not in {"TRADICIONAL", "INTELIGENTE"}:
            raise HTTPException(status_code=400, detail="Modo inválido")

        resident_row = conn.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
        if not resident_row:
            raise HTTPException(status_code=404, detail="Residente no encontrado")
        if not resident_row["enabled"]:
            raise HTTPException(status_code=409, detail="Participante no habilitado para iniciar una sesión")
        if not resident_row["consent_valid"]:
            raise HTTPException(status_code=409, detail="Consentimiento no vigente")

        if device_id:
            device_row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        else:
            device_row = conn.execute("SELECT * FROM devices ORDER BY id LIMIT 1").fetchone()
        if not device_row:
            raise HTTPException(status_code=503, detail="No existe dispositivo registrado")

        resident = dict(resident_row)
        device = dict(device_row)
        program_data = dict(program) if program else None

    # 2) La inferencia puede entrenar/persistir modelos; se ejecuta fuera de otra transacción SQLite.
    target_l = resident["default_goal_l"]
    prediction = None
    if mode == "INTELIGENTE":
        prediction = predict_for_resident(resident_id, freeze=True)
        if prediction.get("ok"):
            target_l = prediction["target_l"]

    # 3) Persistencia atómica de programación y sesión.
    with get_conn() as conn:
        active = conn.execute("SELECT id FROM sessions WHERE status IN ('PREPARADA','ACTIVA','PAUSADA') LIMIT 1").fetchone()
        if active:
            raise HTTPException(status_code=409, detail="Ya existe una sesión activa o preparada")

        if program_data is None:
            conn.execute(
                "INSERT INTO session_programs(resident_id,device_id,planned_mode,scheduled_at,status) VALUES(?,?,?,?, 'PREPARADA')",
                (resident_id, device["id"], mode, now_iso()),
            )
            program_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        else:
            program_id = program_data["id"]
            conn.execute("UPDATE session_programs SET status='PREPARADA' WHERE id=?", (program_id,))

        code = next_code("SES", "sessions", 5, conn=conn)
        conn.execute(
            """
            INSERT INTO sessions(code,resident_id,device_id,program_id,mode,status,target_l,quality,experimental)
            VALUES(?,?,?,?,?,'PREPARADA',?,'VALIDA',1)
            """,
            (code, resident_id, device["id"], program_id, mode, target_l),
        )
        session_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]

    command = {
        "command": "prepare",
        "session_id": code,
        "resident_code": resident["code"],
        "mode": mode,
        "target_l": target_l,
        "preferred_temp_c": resident["preferred_temp"],
        "pause_threshold_s": int(get_config_value("pause_threshold_s", 5)),
        "end_inactivity_s": int(get_config_value("end_inactivity_s", 60)),
    }
    sent = mqtt_service.publish_command(device["device_code"], command)
    process_event({"event": "SESSION_PREPARED", "session_id": code, "device_id": device["device_code"], "mqtt_sent": sent})
    add_audit(session.user_id, "PREPARE", "session", session_id, command)
    detail = _session_detail(session_id)
    detail["prediction"] = prediction
    detail["command_sent"] = sent
    return detail


@app.get("/api/v1/sesiones/{session_id}")
def session_by_id(session_id: int, _: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    return _session_detail(session_id)


@app.get("/api/v1/sesiones/{session_id}/lecturas")
def session_readings(
    session_id: int,
    limit: int = Query(default=300, ge=1, le=2000),
    _: AuthSession = Depends(staff_only),
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM measurements WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)
        ).fetchall()
    return [dict(x) for x in reversed(rows)]


@app.post("/api/v1/sesiones/{session_id}/detener", status_code=202)
def stop_session(session_id: int, body: StopSessionBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    command_id = body.request_id or str(uuid.uuid4())
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*,d.device_code FROM sessions s LEFT JOIN devices d ON d.id=s.device_id WHERE s.id=?
            """,
            (session_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        if row["status"] == "FINALIZADA":
            raise HTTPException(status_code=409, detail="La sesión ya finalizó")
        conn.execute("UPDATE sessions SET stop_requested=1 WHERE id=?", (session_id,))
        conn.execute(
            "INSERT INTO session_events(session_id,ts,event_type,data_json) VALUES(?,?,?,?)",
            (session_id, now_iso(), "STOP_REQUESTED", json.dumps({"command_id": command_id, "motivo": body.motivo}, ensure_ascii=False)),
        )
    sent = mqtt_service.publish_command(row["device_code"] or "DUCHA-01", {"command": "stop", "session_id": row["code"], "command_id": command_id, "reason": body.motivo})
    # En simulación local se confirma inmediatamente para que la demo pueda continuar.
    if config.SIMULATION:
        with get_conn() as conn:
            conn.execute("UPDATE sessions SET status='FINALIZADA',ended_at=COALESCE(ended_at,?) WHERE id=?", (now_iso(), session_id))
        process_event({"event": "STOP_CONFIRMED", "session_id": row["code"], "command_id": command_id, "source": "SIMULATION"})
    add_audit(session.user_id, "STOP_REQUEST", "session", session_id, {"command_id": command_id, "motivo": body.motivo})
    return {"ok": True, "command_id": command_id, "mqtt_sent": sent, "message": "Detención solicitada. Esperando confirmación."}


@app.get("/api/v1/historial")
def history(
    resident_id: int | None = None,
    mode: str | None = None,
    quality: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=250, ge=1, le=2000),
    _: AuthSession = Depends(staff_only),
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if resident_id:
        clauses.append("s.resident_id=?"); params.append(resident_id)
    if mode:
        clauses.append("s.mode=?"); params.append(mode.upper())
    if quality:
        clauses.append("s.quality=?"); params.append(quality.upper())
    if status:
        clauses.append("s.status=?"); params.append(status.upper())
    if date_from:
        clauses.append("substr(s.started_at,1,10)>=?"); params.append(date_from)
    if date_to:
        clauses.append("substr(s.started_at,1,10)<=?"); params.append(date_to)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT s.*,r.code resident_code,r.display_name,r.room,d.device_code
            FROM sessions s JOIN residents r ON r.id=s.resident_id
            LEFT JOIN devices d ON d.id=s.device_id
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(s.started_at,s.created_at) DESC LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [dict(x) for x in rows]


# Endpoint de inyección sólo para laboratorio/simulador de integración.
@app.post("/api/v1/lab/telemetry")
def lab_telemetry(payload: dict[str, Any], session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    if not config.SIMULATION:
        raise HTTPException(status_code=403, detail="Endpoint disponible únicamente en modo simulación")
    result = process_telemetry(payload, source="LAB")
    if not result:
        raise HTTPException(status_code=409, detail="No existe sesión activa para asociar la lectura")
    add_audit(session.user_id, "LAB_TELEMETRY", "session", result["id"], payload)
    return result


# -----------------------------
# API: reportes y exportación
# -----------------------------
@app.get("/api/v1/reportes/comparacion")
def comparison_report(
    resident_id: int | None = None,
    _: AuthSession = Depends(staff_only),
) -> dict[str, Any]:
    where = "AND resident_id=?" if resident_id else ""
    params = (resident_id,) if resident_id else ()
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT mode, COUNT(*) n, AVG(volume_total_l) avg_l, AVG(total_duration_s) avg_duration_s,
                   AVG(avg_temp_c) avg_temp_c
            FROM sessions
            WHERE status='FINALIZADA' AND quality='VALIDA' AND experimental=1 {where}
            GROUP BY mode
            """,
            params,
        ).fetchall()
    result = {r["mode"]: dict(r) for r in rows}
    trad = float(result.get("TRADICIONAL", {}).get("avg_l") or 0)
    intel = float(result.get("INTELIGENTE", {}).get("avg_l") or 0)
    reduction = ((trad - intel) / trad * 100) if trad else 0
    return {"modes": result, "reduction_pct": round(reduction, 2)}


def _export_rows() -> tuple[list[str], list[list[Any]]]:
    headers = [
        "codigo_sesion", "codigo_residente", "modo", "inicio", "fin", "volumen_l", "duracion_s",
        "duracion_efectiva_s", "pausas", "caudal_promedio_lmin", "temp_promedio_c", "temp_max_c", "calidad",
    ]
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.code,r.code resident_code,s.mode,s.started_at,s.ended_at,s.volume_total_l,
                   s.total_duration_s,s.effective_duration_s,s.pause_count,s.avg_flow_lmin,s.avg_temp_c,s.max_temp_c,s.quality
            FROM sessions s JOIN residents r ON r.id=s.resident_id
            WHERE s.experimental=1 ORDER BY s.started_at
            """
        ).fetchall()
    data = [
        [r["code"], r["resident_code"], r["mode"], r["started_at"], r["ended_at"], r["volume_total_l"],
         r["total_duration_s"], r["effective_duration_s"], r["pause_count"], r["avg_flow_lmin"], r["avg_temp_c"], r["max_temp_c"], r["quality"]]
        for r in rows
    ]
    return headers, data


@app.get("/api/v1/exportaciones")
def export_data(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    session: AuthSession = Depends(staff_only),
):
    headers, data = _export_rows()
    add_audit(session.user_id, "EXPORT", "sessions", None, {"format": format, "rows": len(data)})
    if format == "csv":
        sio = io.StringIO()
        writer = csv.writer(sio)
        writer.writerow(headers)
        writer.writerows(data)
        content = "\ufeff" + sio.getvalue()
        return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=sesiones_smcdI.csv"})

    try:
        from openpyxl import Workbook
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"openpyxl no disponible: {exc}") from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "Sesiones"
    ws.append(headers)
    for row in data:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sesiones_smcdi.xlsx"},
    )


# -----------------------------
# API: alertas
# -----------------------------
@app.get("/api/v1/alertas")
def alerts(status: str | None = None, _: AuthSession = Depends(staff_only)) -> list[dict[str, Any]]:
    clause = "WHERE a.status=?" if status else ""
    params = (status.upper(),) if status else ()
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT a.*,r.code resident_code,r.display_name,r.room,s.code session_code,d.device_code
            FROM alerts a
            LEFT JOIN residents r ON r.id=a.resident_id
            LEFT JOIN sessions s ON s.id=a.session_id
            LEFT JOIN devices d ON d.id=a.device_id
            {clause}
            ORDER BY CASE a.status WHEN 'PENDIENTE' THEN 0 WHEN 'REVISADA' THEN 1 ELSE 2 END, a.created_at DESC
            """,
            params,
        ).fetchall()
    return [dict(x) for x in rows]


@app.patch("/api/v1/alertas/{alert_id}")
def update_alert(alert_id: int, body: AlertPatchBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    status = body.status.upper()
    if status not in {"PENDIENTE", "REVISADA", "RESUELTA"}:
        raise HTTPException(status_code=400, detail="Estado de alerta inválido")
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM alerts WHERE id=?", (alert_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Alerta no encontrada")
        resolved_at = now_iso() if status == "RESUELTA" else None
        conn.execute(
            "UPDATE alerts SET status=?,note=?,handled_by=?,resolved_at=? WHERE id=?",
            (status, body.note, session.user_id, resolved_at, alert_id),
        )
        row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    add_audit(session.user_id, "UPDATE", "alert", alert_id, {"status": status, "note": body.note})
    return dict(row)


# -----------------------------
# API: IA
# -----------------------------
@app.get("/api/v1/ia")
def ia_view(resident_id: int | None = None, _: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    return ai_dashboard(resident_id)


@app.post("/api/v1/ia/entrenar")
def train_ai(session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    result = train_models()
    add_audit(session.user_id, "TRAIN", "ai_model", None, result)
    return result


@app.post("/api/v1/predicciones")
def predictions(body: PredictionBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    resident_id = body.resident_id
    if body.programacion_id:
        with get_conn() as conn:
            program = conn.execute("SELECT resident_id FROM session_programs WHERE id=?", (body.programacion_id,)).fetchone()
        if not program:
            raise HTTPException(status_code=404, detail="Programación no encontrada")
        resident_id = program["resident_id"]
    if not resident_id:
        raise HTTPException(status_code=400, detail="resident_id o programacion_id es obligatorio")
    result = predict_for_resident(resident_id, body.reduction_pct, freeze=True)
    add_audit(session.user_id, "PREDICT", "resident", resident_id, result)
    return result


@app.get("/api/v1/modelos")
def models(_: AuthSession = Depends(staff_only)) -> list[dict[str, Any]]:
    return list_models()


@app.get("/api/v1/modelos/{model_id}/metricas")
def model_metrics(model_id: int, _: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ai_models WHERE id=?", (model_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Modelo no encontrado")
    result = dict(row)
    if result.get("metadata_json"):
        try:
            result["metadata"] = json.loads(result["metadata_json"])
        except Exception:
            result["metadata"] = None
    return result


# -----------------------------
# API: encuesta TAM
# -----------------------------
@app.get("/api/v1/encuestas")
def surveys(resident_id: int | None = None, _: AuthSession = Depends(staff_only)) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if resident_id:
            rows = conn.execute(
                "SELECT * FROM surveys WHERE resident_id=? ORDER BY id DESC", (resident_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM surveys ORDER BY id DESC LIMIT 100").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["answers"] = json.loads(d.pop("answers_json"))
        result.append(d)
    return result


@app.post("/api/v1/encuestas", status_code=201)
def create_survey(body: SurveyBody, session: AuthSession = Depends(staff_only)) -> dict[str, Any]:
    if any(v < 1 or v > 5 for v in body.answers):
        raise HTTPException(status_code=400, detail="Cada respuesta Likert debe estar entre 1 y 5")
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM residents WHERE id=?", (body.resident_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Residente no encontrado")
        avg = round(sum(body.answers) / 20, 2)
        conn.execute(
            "INSERT INTO surveys(resident_id,session_id,moment,survey_date,answers_json,score_avg,completed) VALUES(?,?,?,?,?,?,1)",
            (body.resident_id, body.session_id, body.moment, datetime.now().date().isoformat(), json.dumps(body.answers), avg),
        )
        survey_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        row = conn.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
    add_audit(session.user_id, "CREATE", "survey", survey_id, {"resident_id": body.resident_id, "score_avg": avg})
    data = dict(row)
    data["answers"] = json.loads(data.pop("answers_json"))
    return data


# -----------------------------
# API: configuración y usuarios
# -----------------------------
@app.get("/api/v1/configuracion")
def get_configuration(_: AuthSession = Depends(admin_only)) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM configuration ORDER BY key").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["typed_value"] = get_config_value(d["key"], d["value"])
        result.append(d)
    return result


@app.patch("/api/v1/configuracion")
def patch_configuration(body: ConfigPatchBody, session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    allowed = set(config.DEFAULT_CONFIG.keys())
    unknown = [k for k in body.values if k not in allowed]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Parámetros no autorizados: {', '.join(unknown)}")
    for key, value in body.values.items():
        default_type = config.DEFAULT_CONFIG[key][1]
        set_config_value(key, value, default_type)
    # Sincroniza límites con el prototipo; la lógica de seguridad continúa ejecutándose localmente.
    with get_conn() as conn:
        devices_rows = conn.execute("SELECT device_code FROM devices").fetchall()
    if any(k in body.values for k in {"max_temp_c", "critical_temp_c", "pause_threshold_s", "end_inactivity_s", "max_volume_l"}):
        payload = {"command": "config", **body.values}
        for d in devices_rows:
            mqtt_service.publish_command(d["device_code"], payload)
    add_audit(session.user_id, "UPDATE", "configuration", None, body.values)
    return {"ok": True, "values": {k: get_config_value(k) for k in body.values}}


@app.get("/api/v1/usuarios")
def users(_: AuthSession = Depends(admin_only)) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id,username,full_name,role,is_active,last_login,created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/v1/usuarios", status_code=201)
def create_user(body: UserCreateBody, session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    role = body.role.upper()
    if role not in {"ADMINISTRADOR", "MODERADOR"}:
        raise HTTPException(status_code=400, detail="Rol inválido")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO users(username,full_name,role,password_hash,is_active) VALUES(?,?,?,?,?)",
                (body.username.strip(), body.full_name.strip(), role, hash_password(body.password), int(body.is_active)),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"No se pudo crear la cuenta: {exc}") from exc
        user_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        row = conn.execute("SELECT id,username,full_name,role,is_active,last_login,created_at FROM users WHERE id=?", (user_id,)).fetchone()
    add_audit(session.user_id, "CREATE", "user", user_id, {"username": body.username, "role": role})
    return dict(row)


@app.patch("/api/v1/usuarios/{user_id}")
def update_user(user_id: int, body: UserPatchBody, session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.full_name is not None: updates["full_name"] = body.full_name.strip()
    if body.role is not None:
        role = body.role.upper()
        if role not in {"ADMINISTRADOR", "MODERADOR"}: raise HTTPException(status_code=400, detail="Rol inválido")
        updates["role"] = role
    if body.password:
        if len(body.password) < 8: raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
        updates["password_hash"] = hash_password(body.password)
    if body.is_active is not None: updates["is_active"] = int(body.is_active)
    if not updates: raise HTTPException(status_code=400, detail="No hay cambios")
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        sets = ",".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", (*updates.values(), user_id))
        row = conn.execute("SELECT id,username,full_name,role,is_active,last_login,created_at FROM users WHERE id=?", (user_id,)).fetchone()
    add_audit(session.user_id, "UPDATE", "user", user_id, {k: v for k, v in updates.items() if k != "password_hash"})
    return dict(row)


# -----------------------------
# API: demo local
# -----------------------------
@app.post("/api/v1/demo/reset")
def demo_reset(session: AuthSession = Depends(admin_only)) -> dict[str, Any]:
    if not config.SIMULATION:
        raise HTTPException(status_code=403, detail="Disponible sólo en modo simulación")
    simulator.stop()
    reset_demo()
    simulator.reset_bootstrap()
    simulator.start()
    add_audit(session.user_id, "RESET", "demo")
    return {"ok": True, "message": "Datos de demostración regenerados"}


# -----------------------------
# WebSocket de tiempo real
# -----------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    auth = get_session(token)
    if not auth:
        await ws.close(code=4401)
        return
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "hello", "data": {"role": auth.role, "time": now_iso()}})
        while True:
            # Mantiene la conexión y permite ping opcional desde el navegador.
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"type": "pong", "data": {"time": now_iso()}}))
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception:
        hub.disconnect(ws)


# Errores uniformes sin exponer internals.
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"HTTP_{exc.status_code}", "message": exc.detail, "request_id": str(uuid.uuid4())}},
    )


# El frontend se monta al final para no interceptar /api ni /ws.
if config.WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host=config.APP_HOST, port=config.APP_PORT, reload=False)
