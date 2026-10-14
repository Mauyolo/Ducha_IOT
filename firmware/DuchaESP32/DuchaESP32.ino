/*
 * SMCDI - Ducha Inteligente UCSM 2026
 * ESP32: sensado YF-S201 + DS18B20, MQTT y seguridad determinística local.
 *
 * IMPORTANTE:
 * - Las electroválvulas NO se conectan directamente a los GPIO del ESP32.
 *   Use relé/MOSFET apropiado, fuente separada y protección flyback.
 * - Calibre FLOW_CALIBRATION_FACTOR con el sensor instalado.
 * - La seguridad térmica se ejecuta localmente aunque MQTT/Internet fallen.
 */

#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "config.h"

volatile uint32_t flowPulses = 0;
portMUX_TYPE pulseMux = portMUX_INITIALIZER_UNLOCKED;

OneWire oneWire(PIN_TEMP_SENSOR);
DallasTemperature tempSensors(&oneWire);
WiFiClient plainClient;
WiFiClientSecure secureClient;
PubSubClient mqtt;

String sessionId = "";
String residentCode = "";
String operationMode = "TRADICIONAL";
float targetLiters = 0.0f;
float preferredTempC = 24.0f;
float runtimeMaxTempC = LOCAL_MAX_TEMP_C;
float runtimeCriticalTempC = LOCAL_CRITICAL_TEMP_C;
float runtimeMaxVolumeL = 60.0f;
uint32_t runtimePauseThresholdMs = PAUSE_THRESHOLD_MS;
uint32_t runtimeEndInactivityMs = SESSION_END_INACTIVITY_MS;

bool prepared = false;
bool sessionActive = false;
bool inPause = false;
bool safetyLock = false;

uint32_t sessionStartedMs = 0;
uint32_t lastFlowMs = 0;
uint32_t pauseStartedMs = 0;
uint32_t totalPauseMs = 0;
uint32_t pauseCount = 0;
uint32_t lastTelemetryMs = 0;
uint32_t lastStatusMs = 0;
uint32_t lastPulseSampleMs = 0;
uint32_t lastPulseSampleCount = 0;

float flowLMin = 0.0f;
float volumeLiters = 0.0f;
float temperatureC = NAN;

// Cola breve en RAM para eventos/telemetría cuando MQTT cae.
// En una versión de campo puede reemplazarse por LittleFS/NVS para persistir tras reinicio.
struct PendingMessage {
  String topic;
  String payload;
};
constexpr uint8_t QUEUE_SIZE = 24;
PendingMessage queueBuf[QUEUE_SIZE];
uint8_t queueHead = 0, queueTail = 0, queueCount = 0;

void IRAM_ATTR onFlowPulse() {
  portENTER_CRITICAL_ISR(&pulseMux);
  flowPulses++;
  portEXIT_CRITICAL_ISR(&pulseMux);
}

String topic(const char* suffix) {
  return String("smcdi/device/") + DEVICE_CODE + "/" + suffix;
}

void setValve(uint8_t pin, bool open) {
  digitalWrite(pin, open ? HIGH : LOW);
}

void closeAllValves() {
  setValve(PIN_VALVE_COLD, false);
  setValve(PIN_VALVE_HOT, false);
}

void openForMode() {
  if (safetyLock || !prepared) {
    closeAllValves();
    return;
  }
  // La regulación hidráulica final depende del circuito real. Para el prototipo
  // se habilitan ambas líneas y la seguridad local puede cerrarlas inmediatamente.
  setValve(PIN_VALVE_COLD, true);
  setValve(PIN_VALVE_HOT, true);
}

void enqueueMessage(const String& t, const String& p) {
  if (queueCount == QUEUE_SIZE) {
    queueHead = (queueHead + 1) % QUEUE_SIZE;
    queueCount--;
  }
  queueBuf[queueTail] = {t, p};
  queueTail = (queueTail + 1) % QUEUE_SIZE;
  queueCount++;
}

bool publishJson(const String& t, const String& payload, bool queueIfOffline = true) {
  if (mqtt.connected() && mqtt.publish(t.c_str(), payload.c_str(), false)) return true;
  if (queueIfOffline) enqueueMessage(t, payload);
  return false;
}

void flushQueue() {
  while (mqtt.connected() && queueCount > 0) {
    PendingMessage &m = queueBuf[queueHead];
    if (!mqtt.publish(m.topic.c_str(), m.payload.c_str(), false)) return;
    queueHead = (queueHead + 1) % QUEUE_SIZE;
    queueCount--;
    delay(5);
  }
}

void publishEvent(const char* eventName, const char* message = "") {
  JsonDocument doc;
  doc["device_id"] = DEVICE_CODE;
  if (sessionId.length()) doc["session_id"] = sessionId;
  doc["event"] = eventName;
  doc["message"] = message;
  doc["millis"] = millis();
  String out;
  serializeJson(doc, out);
  publishJson(topic("events"), out);
}

void publishStatus(const char* status = "CONECTADO") {
  JsonDocument doc;
  doc["device_id"] = DEVICE_CODE;
  doc["status"] = status;
  doc["firmware"] = "1.0.0";
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["safety_lock"] = safetyLock;
  String out;
  serializeJson(doc, out);
  publishJson(topic("status"), out, false);
}

void resetSessionState() {
  sessionId = "";
  residentCode = "";
  operationMode = "TRADICIONAL";
  targetLiters = 0;
  prepared = false;
  sessionActive = false;
  inPause = false;
  safetyLock = false;
  sessionStartedMs = 0;
  lastFlowMs = 0;
  pauseStartedMs = 0;
  totalPauseMs = 0;
  pauseCount = 0;
  volumeLiters = 0;
  flowLMin = 0;
  digitalWrite(PIN_LED, LOW);
  noTone(PIN_BUZZER);
  closeAllValves();
}

void finishSession(const char* reason) {
  if (!prepared && !sessionActive) return;
  closeAllValves();
  publishEvent("SESSION_ENDED", reason);
  prepared = false;
  sessionActive = false;
  inPause = false;
  digitalWrite(PIN_LED, LOW);
}

void safetyShutdown(const char* reason, const char* eventName) {
  safetyLock = true;
  closeAllValves();
  digitalWrite(PIN_LED, HIGH);
  tone(PIN_BUZZER, 2200, 1000);
  publishEvent(eventName, reason);
}

void mqttCallback(char* topicName, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;

  String command = doc["command"] | "";
  if (command == "prepare") {
    resetSessionState();
    sessionId = String((const char*)doc["session_id"]);
    residentCode = String((const char*)doc["resident_code"]);
    operationMode = String((const char*)doc["mode"]);
    targetLiters = doc["target_l"] | 0.0f;
    preferredTempC = doc["preferred_temp_c"] | 24.0f;
    runtimePauseThresholdMs = (uint32_t)(doc["pause_threshold_s"] | (PAUSE_THRESHOLD_MS / 1000UL)) * 1000UL;
    runtimeEndInactivityMs = (uint32_t)(doc["end_inactivity_s"] | (SESSION_END_INACTIVITY_MS / 1000UL)) * 1000UL;
    prepared = true;
    openForMode();
    publishEvent("PREPARED", "Sesión preparada por el backend");
  } else if (command == "stop") {
    closeAllValves();
    publishEvent("STOP_CONFIRMED", "Detención confirmada por el ESP32");
    prepared = false;
    sessionActive = false;
  } else if (command == "config") {
    if (doc["max_temp_c"].is<float>() || doc["max_temp_c"].is<int>()) runtimeMaxTempC = doc["max_temp_c"].as<float>();
    if (doc["critical_temp_c"].is<float>() || doc["critical_temp_c"].is<int>()) runtimeCriticalTempC = doc["critical_temp_c"].as<float>();
    if (doc["max_volume_l"].is<float>() || doc["max_volume_l"].is<int>()) runtimeMaxVolumeL = doc["max_volume_l"].as<float>();
    if (doc["pause_threshold_s"].is<int>()) runtimePauseThresholdMs = doc["pause_threshold_s"].as<uint32_t>() * 1000UL;
    if (doc["end_inactivity_s"].is<int>()) runtimeEndInactivityMs = doc["end_inactivity_s"].as<uint32_t>() * 1000UL;
    publishEvent("CONFIG_APPLIED", "Parámetros determinísticos actualizados localmente");
  } else if (command == "clear_safety") {
    // Sólo se libera si la temperatura actual ya es válida y segura.
    if (!isnan(temperatureC) && temperatureC <= runtimeMaxTempC) {
      safetyLock = false;
      publishEvent("SAFETY_CLEARED", "Bloqueo de seguridad restablecido");
      if (prepared) openForMode();
    }
  }
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(250);
  }
}

void connectMQTT() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  String clientId = String("smcdi-") + DEVICE_CODE + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  bool ok;
  if (strlen(MQTT_USERNAME) > 0) ok = mqtt.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD);
  else ok = mqtt.connect(clientId.c_str());
  if (ok) {
    mqtt.subscribe(topic("commands").c_str(), 1);
    publishStatus();
    flushQueue();
  }
}

void sampleFlow() {
  uint32_t now = millis();
  uint32_t dt = now - lastPulseSampleMs;
  if (dt < 1000) return;

  uint32_t pulses;
  portENTER_CRITICAL(&pulseMux);
  pulses = flowPulses;
  portEXIT_CRITICAL(&pulseMux);
  uint32_t delta = pulses - lastPulseSampleCount;
  lastPulseSampleCount = pulses;
  lastPulseSampleMs = now;

  float hz = (delta * 1000.0f) / dt;
  flowLMin = hz / FLOW_CALIBRATION_FACTOR;
  if (flowLMin < 0.05f) flowLMin = 0.0f;
  volumeLiters += flowLMin * (dt / 60000.0f);

  if (operationMode == "INTELIGENTE" && runtimeMaxVolumeL > 0 && volumeLiters >= runtimeMaxVolumeL && !safetyLock) {
    safetyShutdown("Volumen máximo de seguridad alcanzado", "MAX_VOLUME_SHUTDOWN");
  }

  if (flowLMin > 0.0f) {
    lastFlowMs = now;
    if (prepared && !sessionActive) {
      sessionActive = true;
      sessionStartedMs = now;
      publishEvent("SESSION_STARTED", "Caudal detectado");
    }
    if (inPause) {
      totalPauseMs += now - pauseStartedMs;
      inPause = false;
      publishEvent("SESSION_RESUMED", "Caudal restablecido");
    }
  } else if (sessionActive) {
    uint32_t idle = now - lastFlowMs;
    if (!inPause && idle >= runtimePauseThresholdMs) {
      inPause = true;
      pauseStartedMs = now;
      pauseCount++;
      publishEvent("SESSION_PAUSED", "Caudal interrumpido");
    }
    if (idle >= runtimeEndInactivityMs) {
      finishSession("Fin por inactividad de caudal");
    }
  }
}

void sampleTemperatureAndSafety() {
  tempSensors.requestTemperatures();
  temperatureC = tempSensors.getTempCByIndex(0);

  bool invalid = temperatureC == DEVICE_DISCONNECTED_C || isnan(temperatureC) ||
                 temperatureC < SENSOR_MIN_TEMP_C || temperatureC > SENSOR_MAX_VALID_TEMP_C;
  if (invalid) {
    if (!safetyLock) safetyShutdown("Sensor térmico inválido", "SENSOR_ERROR");
    return;
  }
  if (temperatureC >= runtimeCriticalTempC) {
    if (!safetyLock) safetyShutdown("Temperatura crítica: cierre inmediato", "OVER_TEMPERATURE");
    return;
  }
  if (temperatureC > runtimeMaxTempC) {
    // Protección preventiva: se corta la línea caliente y se mantiene la fría.
    setValve(PIN_VALVE_HOT, false);
    setValve(PIN_VALVE_COLD, true);
    tone(PIN_BUZZER, 1800, 250);
  }
}

void updateFeedback() {
  if (!sessionActive || operationMode != "INTELIGENTE" || targetLiters <= 0) return;
  float ratio = volumeLiters / targetLiters;
  if (ratio >= 1.0f) {
    digitalWrite(PIN_LED, HIGH);
    tone(PIN_BUZZER, 1600, 150);
  } else if (ratio >= 0.8f) {
    // Pulso visual no crítico al acercarse al objetivo.
    digitalWrite(PIN_LED, (millis() / 350) % 2);
  } else {
    digitalWrite(PIN_LED, LOW);
  }
}

void publishTelemetry() {
  if (!prepared && !sessionActive) return;
  uint32_t now = millis();
  if (now - lastTelemetryMs < TELEMETRY_INTERVAL_MS) return;
  lastTelemetryMs = now;

  uint32_t elapsed = sessionActive ? (now - sessionStartedMs) / 1000 : 0;
  uint32_t currentPauseMs = inPause ? now - pauseStartedMs : 0;
  uint32_t pauseMs = totalPauseMs + currentPauseMs;
  uint32_t effective = elapsed > pauseMs / 1000 ? elapsed - pauseMs / 1000 : 0;

  JsonDocument doc;
  doc["device_id"] = DEVICE_CODE;
  doc["session_id"] = sessionId;
  doc["resident_code"] = residentCode;
  doc["mode"] = operationMode;
  doc["flow_lmin"] = roundf(flowLMin * 100) / 100.0f;
  doc["volume_l"] = roundf(volumeLiters * 100) / 100.0f;
  if (!isnan(temperatureC)) doc["temperature_c"] = roundf(temperatureC * 100) / 100.0f;
  doc["elapsed_s"] = elapsed;
  doc["effective_s"] = effective;
  doc["pause_count"] = pauseCount;
  doc["pause_duration_s"] = pauseMs / 1000;
  doc["state"] = inPause ? "PAUSED" : (sessionActive ? "ACTIVE" : "PREPARED");
  doc["rssi"] = WiFi.RSSI();
  doc["target_l"] = targetLiters;
  doc["safety_lock"] = safetyLock;

  String out;
  serializeJson(doc, out);
  publishJson(topic("telemetry"), out);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FLOW_SENSOR, INPUT_PULLUP);
  pinMode(PIN_VALVE_COLD, OUTPUT);
  pinMode(PIN_VALVE_HOT, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  closeAllValves();

  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_SENSOR), onFlowPulse, FALLING);
  tempSensors.begin();
  tempSensors.setWaitForConversion(false);

  connectWiFi();
#if MQTT_USE_TLS
  secureClient.setCACert(MQTT_CA_CERT);
  mqtt.setClient(secureClient);
#else
  mqtt.setClient(plainClient);
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(1024);
  lastPulseSampleMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  sampleFlow();
  sampleTemperatureAndSafety();
  updateFeedback();
  publishTelemetry();

  if (millis() - lastStatusMs >= STATUS_INTERVAL_MS) {
    lastStatusMs = millis();
    if (mqtt.connected()) publishStatus();
  }
  if (mqtt.connected()) flushQueue();
  delay(20);
}
