from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .db import get_conn, get_config_value, next_code, now_iso
from .realtime import hub


def _alert_exists(conn, session_id: int | None, kind: str) -> bool:
    if session_id is None:
        return False
    return bool(conn.execute(
        "SELECT 1 FROM alerts WHERE session_id=? AND kind=? AND status!='RESUELTA' LIMIT 1",
        (session_id, kind),
    ).fetchone())


def create_alert(kind: str, severity: str, description: str, session_id: int | None = None, resident_id: int | None = None, device_id: int | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        code = next_code("ALR", "alerts", 4, conn=conn)
        conn.execute(
            "INSERT INTO alerts(code,session_id,resident_id,device_id,kind,severity,description,status,created_at) VALUES(?,?,?,?,?,?,?,'PENDIENTE',?)",
            (code, session_id, resident_id, device_id, kind, severity, description, now_iso()),
        )
        row = conn.execute("SELECT * FROM alerts WHERE code=?", (code,)).fetchone()
    data = dict(row)
    hub.broadcast_threadsafe({"type": "alert", "data": data})
    return data


def process_device_status(payload: dict[str, Any]) -> None:
    device_code = payload.get("device_id") or payload.get("device_code") or "DUCHA-01"
    with get_conn() as conn:
        device = conn.execute("SELECT id FROM devices WHERE device_code=?", (device_code,)).fetchone()
        if device:
            conn.execute(
                "UPDATE devices SET status=?,last_seen=?,firmware_version=COALESCE(?,firmware_version),ip_address=COALESCE(?,ip_address) WHERE id=?",
                (payload.get("status", "CONECTADO"), now_iso(), payload.get("firmware"), payload.get("ip"), device["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO devices(device_code,name,status,last_seen,firmware_version,ip_address) VALUES(?,?,?, ?,?,?)",
                (device_code, f"Prototipo {device_code}", payload.get("status", "CONECTADO"), now_iso(), payload.get("firmware"), payload.get("ip")),
            )
    hub.broadcast_threadsafe({"type": "device_status", "data": payload})


def _resolve_session(conn, payload: dict[str, Any]):
    session_code = payload.get("session_id") or payload.get("session_code")
    if session_code:
        row = conn.execute("SELECT * FROM sessions WHERE code=?", (session_code,)).fetchone()
        if row:
            return row
    device_code = payload.get("device_id") or payload.get("device_code")
    if device_code:
        row = conn.execute(
            "SELECT s.* FROM sessions s JOIN devices d ON d.id=s.device_id WHERE d.device_code=? AND s.status IN ('PREPARADA','ACTIVA','PAUSADA') ORDER BY s.id DESC LIMIT 1",
            (device_code,),
        ).fetchone()
        if row:
            return row
    return conn.execute("SELECT * FROM sessions WHERE status IN ('PREPARADA','ACTIVA','PAUSADA') ORDER BY id DESC LIMIT 1").fetchone()


def process_telemetry(payload: dict[str, Any], source: str = "MQTT") -> dict[str, Any] | None:
    flow = float(payload.get("flow_lmin", payload.get("flow", 0)) or 0)
    volume = float(payload.get("volume_l", payload.get("volume", 0)) or 0)
    temp = payload.get("temperature_c", payload.get("temperature"))
    temp = float(temp) if temp is not None else None
    state = str(payload.get("state", "ACTIVE")).upper()
    ts = payload.get("timestamp") or now_iso()
    rssi = payload.get("rssi")

    with get_conn() as conn:
        session = _resolve_session(conn, payload)
        if not session:
            return None
        sid = session["id"]
        status = "ACTIVA"
        if state in {"PAUSE", "PAUSED", "PAUSA"}:
            status = "PAUSADA"
        elif state in {"ENDED", "FINALIZADA", "STOPPED"}:
            status = "FINALIZADA"
        elif state in {"PREPARED", "PREPARADA"}:
            status = "PREPARADA"

        conn.execute(
            "INSERT INTO measurements(session_id,ts,flow_lmin,volume_l,temp_c,state,rssi,source) VALUES(?,?,?,?,?,?,?,?)",
            (sid, ts, flow, volume, temp, state, rssi, source),
        )

        started_at = session["started_at"] or (ts if status in {"ACTIVA", "PAUSADA", "FINALIZADA"} else None)
        ended_at = ts if status == "FINALIZADA" else session["ended_at"]
        elapsed_s = int(payload.get("elapsed_s", session["total_duration_s"] or 0) or 0)
        effective_s = int(payload.get("effective_s", session["effective_duration_s"] or 0) or 0)
        pause_count = int(payload.get("pause_count", session["pause_count"] or 0) or 0)
        pause_duration_s = int(payload.get("pause_duration_s", session["pause_duration_s"] or 0) or 0)

        conn.execute(
            "UPDATE sessions SET status=?,started_at=COALESCE(started_at,?),ended_at=?,total_duration_s=?,effective_duration_s=?,pause_count=?,pause_duration_s=?,volume_total_l=? WHERE id=?",
            (status, started_at, ended_at, elapsed_s, effective_s, pause_count, pause_duration_s, volume, sid),
        )

        max_volume = float(get_config_value("max_volume_l", 60, conn=conn))
        max_temp = float(get_config_value("max_temp_c", 38, conn=conn))
        if volume > max_volume and not _alert_exists(conn, sid, "Consumo excesivo"):
            code = next_code("ALR", "alerts", 4, conn=conn)
            conn.execute(
                "INSERT INTO alerts(code,session_id,resident_id,device_id,kind,severity,description,status,created_at) VALUES(?,?,?,?,?,'ALTA',?,'PENDIENTE',?)",
                (code, sid, session["resident_id"], session["device_id"], "Consumo excesivo", f"La sesión {session['code']} superó {max_volume:.1f} L (lectura actual {volume:.1f} L).", now_iso()),
            )
        if temp is not None and temp > max_temp and not _alert_exists(conn, sid, "Temperatura elevada"):
            code = next_code("ALR", "alerts", 4, conn=conn)
            conn.execute(
                "INSERT INTO alerts(code,session_id,resident_id,device_id,kind,severity,description,status,created_at) VALUES(?,?,?,?,?,'ALTA',?,'PENDIENTE',?)",
                (code, sid, session["resident_id"], session["device_id"], "Temperatura elevada", f"Temperatura {temp:.1f} °C por encima del límite {max_temp:.1f} °C. La seguridad se ejecuta localmente en el ESP32.", now_iso()),
            )

        if status == "FINALIZADA":
            stats = conn.execute(
                "SELECT AVG(flow_lmin) avg_flow,MAX(flow_lmin) max_flow,AVG(temp_c) avg_temp,MAX(temp_c) max_temp FROM measurements WHERE session_id=?",
                (sid,),
            ).fetchone()
            conn.execute(
                "UPDATE sessions SET avg_flow_lmin=?,max_flow_lmin=?,avg_temp_c=?,max_temp_c=? WHERE id=?",
                (stats["avg_flow"], stats["max_flow"], stats["avg_temp"], stats["max_temp"], sid),
            )

        row = conn.execute(
            "SELECT s.*,r.code resident_code,r.display_name,r.room,d.device_code FROM sessions s JOIN residents r ON r.id=s.resident_id LEFT JOIN devices d ON d.id=s.device_id WHERE s.id=?",
            (sid,),
        ).fetchone()

    data = dict(row)
    data.update({"flow_lmin": flow, "volume_l": volume, "temperature_c": temp, "state": state, "timestamp": ts, "rssi": rssi})
    hub.broadcast_threadsafe({"type": "telemetry", "data": data})
    return data


def process_event(payload: dict[str, Any]) -> None:
    event_type = str(payload.get("event", payload.get("type", "EVENT"))).upper()
    with get_conn() as conn:
        session = _resolve_session(conn, payload)
        sid = session["id"] if session else None
        conn.execute(
            "INSERT INTO session_events(session_id,ts,event_type,data_json) VALUES(?,?,?,?)",
            (sid, payload.get("timestamp") or now_iso(), event_type, json.dumps(payload, ensure_ascii=False)),
        )
        if sid and event_type in {"STOP_CONFIRMED", "SESSION_ENDED", "ENDED"}:
            stats = conn.execute(
                "SELECT AVG(flow_lmin) avg_flow,MAX(flow_lmin) max_flow,AVG(temp_c) avg_temp,MAX(temp_c) max_temp,MAX(volume_l) final_volume FROM measurements WHERE session_id=?",
                (sid,),
            ).fetchone()
            conn.execute(
                "UPDATE sessions SET status='FINALIZADA',ended_at=COALESCE(ended_at,?),volume_total_l=COALESCE(?,volume_total_l),avg_flow_lmin=?,max_flow_lmin=?,avg_temp_c=?,max_temp_c=? WHERE id=?",
                (now_iso(), stats["final_volume"], stats["avg_flow"], stats["max_flow"], stats["avg_temp"], stats["max_temp"], sid),
            )
        if sid and event_type in {"SENSOR_ERROR", "SAFETY_SHUTDOWN", "OVER_TEMPERATURE"}:
            sev = "CRITICA" if event_type in {"SAFETY_SHUTDOWN", "OVER_TEMPERATURE"} else "ALTA"
            kind = "Fallo de sensor" if event_type == "SENSOR_ERROR" else "Cierre de seguridad"
            if not _alert_exists(conn, sid, kind):
                code = next_code("ALR", "alerts", 4, conn=conn)
                conn.execute(
                    "INSERT INTO alerts(code,session_id,resident_id,device_id,kind,severity,description,status,created_at) VALUES(?,?,?,?,?,?,?,'PENDIENTE',?)",
                    (code, sid, session["resident_id"], session["device_id"], kind, sev, payload.get("message", event_type), now_iso()),
                )
    hub.broadcast_threadsafe({"type": "event", "data": payload})
