# MQTT y conexión del ESP32

## Tópicos

```text
smcdi/device/DUCHA-01/telemetry   ESP32 → backend
smcdi/device/DUCHA-01/events      ESP32 → backend
smcdi/device/DUCHA-01/status      ESP32 → backend
smcdi/device/DUCHA-01/commands    backend → ESP32
```

La telemetría usa QoS 1 en la suscripción del backend. El firmware mantiene una cola breve en RAM cuando el broker no está disponible y la vacía al reconectar. Para una instalación permanente debe reemplazarse o complementarse con LittleFS/NVS si se requiere sobrevivir a un reinicio eléctrico.

## Ejemplo de telemetría

```json
{
  "device_id": "DUCHA-01",
  "session_id": "SES-2026-00109",
  "resident_code": "R-003",
  "mode": "INTELIGENTE",
  "flow_lmin": 8.12,
  "volume_l": 23.44,
  "temperature_c": 24.31,
  "elapsed_s": 188,
  "effective_s": 177,
  "pause_count": 1,
  "pause_duration_s": 11,
  "state": "ACTIVE",
  "rssi": -51,
  "target_l": 30.1,
  "safety_lock": false
}
```

## Configuración física

1. Copia `firmware/DuchaESP32/config.example.h` como `config.h`.
2. Coloca SSID, clave Wi‑Fi y la IP LAN del Mac/servidor en `MQTT_HOST`.
3. Ajusta los GPIO a tu placa y circuito.
4. Calibra el YF-S201 midiendo un volumen conocido; el factor 7.5 es sólo un valor inicial típico.
5. Compila y carga con PlatformIO: `pio run -t upload`.

## Seguridad eléctrica

Las electroválvulas requieren una etapa de potencia. No deben alimentarse desde los GPIO del ESP32. Utiliza MOSFET/relé adecuado, fuente compatible, aislamiento cuando corresponda y diodo flyback en cargas inductivas. Verifica el circuito con el docente/técnico antes de conectar agua y energía.

## TLS

El archivo `mosquitto-secure.conf.example` deja preparado MQTT sobre TLS (puerto 8883), usuario/contraseña y ACL. El archivo `mosquitto.conf` incluido es deliberadamente local para facilitar la demostración y no debe exponerse a Internet.
