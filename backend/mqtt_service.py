from __future__ import annotations

import json
import ssl
import threading
import time
from typing import Any

from . import config
from .realtime import hub
from .telemetry import process_device_status, process_event, process_telemetry


class MQTTService:
    def __init__(self) -> None:
        self.client = None
        self.connected = False
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def start(self) -> None:
        if not config.MQTT_ENABLED:
            self.last_error = "MQTT deshabilitado por configuración"
            return
        try:
            import paho.mqtt.client as mqtt
        except Exception as exc:
            self.last_error = f"paho-mqtt no disponible: {exc}"
            return

        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smcdi-backend", clean_session=True)
        except Exception:
            client = mqtt.Client(client_id="smcdi-backend", clean_session=True)
        if config.MQTT_USERNAME:
            client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
        if config.MQTT_TLS:
            kwargs: dict[str, Any] = {"tls_version": ssl.PROTOCOL_TLS_CLIENT}
            if config.MQTT_CA_CERT:
                kwargs["ca_certs"] = config.MQTT_CA_CERT
            client.tls_set(**kwargs)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self.client = client
        try:
            client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
            client.loop_start()
        except Exception as exc:
            self.last_error = str(exc)

    def stop(self) -> None:
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        ok = int(reason_code) == 0 if hasattr(reason_code, "__int__") else reason_code == 0
        self.connected = bool(ok)
        if not self.connected:
            self.last_error = f"MQTT connect rc={reason_code}"
            return
        root = config.MQTT_TOPIC_ROOT
        for topic in (f"{root}/device/+/telemetry", f"{root}/device/+/events", f"{root}/device/+/status"):
            client.subscribe(topic, qos=1)
        hub.broadcast_threadsafe({"type": "mqtt_status", "data": {"connected": True}})

    def _on_disconnect(self, client, userdata, disconnect_flags=None, reason_code=None, properties=None):
        self.connected = False
        hub.broadcast_threadsafe({"type": "mqtt_status", "data": {"connected": False}})

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic
            if topic.endswith("/telemetry"):
                process_telemetry(payload, source="MQTT")
            elif topic.endswith("/events"):
                process_event(payload)
            elif topic.endswith("/status"):
                process_device_status(payload)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"

    def publish_command(self, device_code: str, payload: dict[str, Any]) -> bool:
        if not self.client or not self.connected:
            return False
        topic = f"{config.MQTT_TOPIC_ROOT}/device/{device_code}/commands"
        body = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            info = self.client.publish(topic, body, qos=1, retain=False)
        try:
            return int(info.rc) == 0
        except Exception:
            return True

    def status(self) -> dict[str, Any]:
        return {
            "enabled": config.MQTT_ENABLED,
            "connected": self.connected,
            "host": config.MQTT_HOST,
            "port": config.MQTT_PORT,
            "tls": config.MQTT_TLS,
            "last_error": self.last_error,
        }


mqtt_service = MQTTService()
