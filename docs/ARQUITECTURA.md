# Arquitectura SMCDI

El sistema implementa la separación definida en el PFC: el ESP32 es responsable del sensado, segmentación de la sesión, actuación y seguridad determinística; el backend concentra persistencia, autorización, reportes e inteligencia artificial; y la web consume exclusivamente servicios del backend.

```text
YF-S201 + DS18B20 + electroválvulas + LED/buzzer
                      │
                      ▼
                    ESP32
            seguridad local / sesión
                      │
           MQTT (TLS en despliegue)
                      ▼
               Broker Mosquitto
                      │
                      ▼
              Backend FastAPI
            ┌─────────┼───────────┐
            ▼         ▼           ▼
         SQLite   Módulo IA    WebSocket
       (local)   scikit-learn      │
            │         │            │
            └────┬────┘            │
                 ▼                 ▼
              API REST ───────► Aplicación Web
```

## Flujo de una sesión

1. El moderador selecciona un residente y prepara la sesión desde la web.
2. El backend valida habilitación, consentimiento, dispositivo y modo; si corresponde, calcula la referencia de IA antes de iniciar.
3. El backend publica el comando `prepare` por MQTT.
4. El ESP32 espera flujo. El primer caudal válido marca el inicio de sesión.
5. Cada segundo el ESP32 publica caudal, volumen acumulado, temperatura, tiempo, pausas, RSSI y estado.
6. El backend valida y persiste cada lectura y la reenvía por WebSocket al navegador.
7. Una interrupción de flujo mayor al umbral registra una pausa; una inactividad continua de 60 s finaliza la sesión.
8. Al finalizar, quedan disponibles resumen, historial, comparación por modo, alertas y exportación.

## Principio de seguridad

La IA nunca controla el límite térmico, el cierre de emergencia ni la respuesta ante sensores inválidos. Esas decisiones se ejecutan en el ESP32. La web puede solicitar una detención, pero el prototipo conserva la autoridad de seguridad local. Una pérdida de red no debe impedir el cierre de electroválvulas.

## Modos

- **SIMULATION=1:** genera telemetría internamente y permite presentar todas las pantallas sin hardware.
- **SIMULATION=0:** espera el ESP32 real a través de MQTT. En este modo debe configurarse el broker y la IP accesible desde el dispositivo.
