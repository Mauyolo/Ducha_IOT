#pragma once

// Copia este archivo como config.h y completa los valores.
#define WIFI_SSID "TU_WIFI"
#define WIFI_PASSWORD "TU_CLAVE_WIFI"

#define DEVICE_CODE "DUCHA-01"
#define MQTT_HOST "192.168.1.100"   // IP del Mac/servidor en la misma red
#define MQTT_PORT 1883
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#define MQTT_USE_TLS 0

// Para TLS real, cambia MQTT_PORT a 8883 y MQTT_USE_TLS a 1.
// Coloca aquí la CA del broker si se utiliza TLS.
static const char MQTT_CA_CERT[] = R"EOF(
-----BEGIN CERTIFICATE-----
PEGA_AQUI_LA_CA_DEL_BROKER
-----END CERTIFICATE-----
)EOF";

// Pines de referencia. AJUSTAR a la placa y circuito realmente construidos.
#define PIN_FLOW_SENSOR 27
#define PIN_TEMP_SENSOR 4
#define PIN_VALVE_COLD 25
#define PIN_VALVE_HOT 26
#define PIN_LED 2
#define PIN_BUZZER 14

// YF-S201 típico: frecuencia (Hz) ≈ 7.5 × caudal (L/min).
// Debe calibrarse experimentalmente con el sensor físico.
#define FLOW_CALIBRATION_FACTOR 7.5f

// Reglas locales de seguridad. No dependen de la IA ni del backend.
#define LOCAL_MAX_TEMP_C 38.0f
#define LOCAL_CRITICAL_TEMP_C 41.0f
#define SENSOR_MIN_TEMP_C 5.0f
#define SENSOR_MAX_VALID_TEMP_C 60.0f

#define TELEMETRY_INTERVAL_MS 1000UL
#define STATUS_INTERVAL_MS 10000UL
#define PAUSE_THRESHOLD_MS 5000UL
#define SESSION_END_INACTIVITY_MS 60000UL
