from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime

from .db import ensure_demo_live_session, get_conn, now_iso
from .telemetry import process_telemetry


class InternalSimulator:
    """Simulador local de presentación.

    Genera telemetría por la misma ruta de procesamiento que MQTT. No reemplaza
    al ESP32: se desactiva con SIMULATION=0 cuando el prototipo físico está conectado.
    """

    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.rng = random.Random(20261014)
        self._bootstrapped = False

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        # Sólo crea una sesión demo al arrancar. Si luego se detiene, espera a que
        # el usuario prepare otra desde la interfaz; así la detención es observable.
        if not self._bootstrapped:
            ensure_demo_live_session()
            self._bootstrapped = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="smcdi-simulator")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None

    def reset_bootstrap(self) -> None:
        self._bootstrapped = False

    def _current_session(self):
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT s.*,r.code AS resident_code,r.display_name,d.device_code
                FROM sessions s
                JOIN residents r ON r.id=s.resident_id
                LEFT JOIN devices d ON d.id=s.device_id
                WHERE s.status IN ('PREPARADA','ACTIVA','PAUSADA')
                ORDER BY s.id DESC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def _run(self) -> None:
        while not self.stop_event.is_set():
            session = self._current_session()
            if not session:
                time.sleep(1)
                continue

            if not session.get("started_at"):
                with get_conn() as conn:
                    conn.execute("UPDATE sessions SET started_at=?,status='ACTIVA' WHERE id=?", (now_iso(), session["id"]))
                session["started_at"] = now_iso()
                session["status"] = "ACTIVA"

            started = datetime.fromisoformat(session["started_at"])
            elapsed = max(1, int((datetime.now() - started).total_seconds()))

            # Reinicia la curva tras 10 minutos sólo para que una demo abierta por mucho
            # tiempo siga siendo visual. No crea otra sesión ni modifica sesiones finales.
            if elapsed > 600:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE sessions SET started_at=?,volume_total_l=0,total_duration_s=0,effective_duration_s=0,pause_count=0,pause_duration_s=0,status='ACTIVA' WHERE id=?",
                        (now_iso(), session["id"]),
                    )
                    conn.execute("DELETE FROM measurements WHERE session_id=?", (session["id"],))
                elapsed = 1

            # Pausa automática corta cada ~95 s para mostrar segmentación inicio/pausa/reanudación.
            in_pause = elapsed % 95 in range(70, 77)
            flow = 0.0 if in_pause else 8.1 + math.sin(elapsed / 13.0) * 0.55 + self.rng.uniform(-0.12, 0.12)
            flow = max(0.0, flow)
            prior_volume = float(session.get("volume_total_l") or 0)
            volume = prior_volume + flow / 60.0
            preferred = float(session.get("preferred_temp") or 24.0) if "preferred_temp" in session else 24.0
            temp = preferred + math.sin(elapsed / 30.0) * 0.35 + self.rng.uniform(-0.08, 0.08)
            pause_count = max(int(session.get("pause_count") or 0), elapsed // 95)
            pause_duration = int(session.get("pause_duration_s") or 0) + (1 if in_pause else 0)
            effective = int(session.get("effective_duration_s") or 0) + (0 if in_pause else 1)

            payload = {
                "device_id": session.get("device_code") or "DUCHA-01",
                "session_id": session["code"],
                "flow_lmin": round(flow, 2),
                "volume_l": round(volume, 2),
                "temperature_c": round(temp, 2),
                "elapsed_s": elapsed,
                "effective_s": effective,
                "pause_count": pause_count,
                "pause_duration_s": pause_duration,
                "state": "PAUSED" if in_pause else "ACTIVE",
                "rssi": -48,
                "timestamp": now_iso(),
            }
            process_telemetry(payload, source="SIMULACION")
            time.sleep(1)


simulator = InternalSimulator()
