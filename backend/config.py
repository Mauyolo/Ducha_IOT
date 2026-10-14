from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "ducha.db"))
MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR = BASE_DIR / "web"

APP_HOST = os.getenv("WEB_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("WEB_PORT", "8000"))
SIMULATION = os.getenv("SIMULATION", "1").strip().lower() in {"1", "true", "yes", "on"}
SEED_DEMO = os.getenv("SEED_DEMO", "1").strip().lower() in {"1", "true", "yes", "on"}

MQTT_ENABLED = os.getenv("MQTT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TLS = os.getenv("MQTT_TLS", "0").strip().lower() in {"1", "true", "yes", "on"}
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")
MQTT_TOPIC_ROOT = os.getenv("MQTT_TOPIC_ROOT", "smcdi")

ADMIN_USER = os.getenv("ADMIN_USER", "admin.ucsm")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin2026!")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrador UCSM")

TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "12"))
AI_REDUCTION_PCT = float(os.getenv("AI_REDUCTION_PCT", "15"))
MIN_HISTORY_FOR_AI = int(os.getenv("MIN_HISTORY_FOR_AI", "3"))

DEFAULT_CONFIG = {
    "max_volume_l": ("60", "float", "Volumen máximo por sesión en modo inteligente."),
    "max_temp_c": ("38", "float", "Temperatura máxima de seguridad determinística."),
    "critical_temp_c": ("41", "float", "Temperatura crítica para cierre inmediato del suministro."),
    "default_preferred_temp_c": ("24", "float", "Temperatura preferida por defecto del perfil."),
    "recommended_time_min": ("10", "float", "Tiempo recomendado de referencia."),
    "pause_threshold_s": ("5", "int", "Tiempo sin caudal para registrar una pausa."),
    "end_inactivity_s": ("60", "int", "Tiempo continuo sin caudal para finalizar una sesión."),
    "ai_reduction_pct": (str(AI_REDUCTION_PCT), "float", "Reducción usada para generar el objetivo personalizado."),
    "telemetry_interval_ms": ("1000", "int", "Intervalo recomendado de telemetría del ESP32."),
}
