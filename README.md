# SMCDI – Sistema de Monitoreo y Control de Ducha Inteligente

Proyecto funcional para el PFC **“Monitoreo y reducción del consumo de agua en duchas mediante un sistema basado en IoT e Inteligencia Artificial en una casa de reposo de la ciudad de Arequipa – 2026”**. La implementación convierte los mockups del Capítulo 6 en una aplicación operativa: ESP32 → MQTT → backend → base de datos → API/WebSocket → interfaz web.

## Qué incluye

- Aplicación web responsive basada en los mockups de Figma: inicio de sesión, dashboard, residentes, detalle individual, monitoreo en tiempo real, historial/reportes, IA, alertas, Encuesta TAM, configuración y usuarios.
- Backend FastAPI con autenticación y roles **Administrador / Moderador**.
- Comunicación IoT con **MQTT** y actualización del navegador mediante **WebSocket**.
- Base de datos relacional SQLite para demostración local, con 18 residentes y 108 observaciones experimentales de ejemplo.
- Firmware ESP32 para YF-S201, DS18B20, electroválvulas, LED y buzzer.
- Seguridad térmica determinística local en el ESP32, independiente de IA, web e Internet.
- Módulo IA que compara **Regresión Lineal, Random Forest Regressor y Gradient Boosting Regressor** mediante MAE, RMSE y R² y genera un objetivo personalizado.
- Exportación CSV/XLSX, auditoría, alertas y simulador integrado para presentar el sistema incluso sin el hardware conectado.
- Configuración Docker/Mosquitto, scripts para macOS y pruebas automáticas.

## Inicio rápido en MacBook

La forma más simple es hacer doble clic en `INICIAR_MAC.command`. En el primer inicio se crea `.venv`, se instalan las dependencias, se copia `.env.example` a `.env` y se abre la aplicación en el navegador.

También puedes ejecutarlo desde Terminal:

```bash
cd ducha_iot_completo
./scripts/start_mac.sh
```

La URL local es `http://127.0.0.1:8000`. Si macOS bloquea el archivo `.command`, ejecuta una sola vez `chmod +x INICIAR_MAC.command scripts/start_mac.sh` desde Terminal.

Credenciales de demostración:

```text
Administrador: admin.ucsm / Admin2026!
Moderador:     mod.turno1 / Moderador2026!
```

Estas cuentas son sólo para laboratorio/presentación. Cambia las contraseñas antes de cualquier despliegue real.

## Dos formas de trabajar

### Presentación sin hardware

Deja en `.env`:

```text
SIMULATION=1
```

El simulador genera telemetría cada segundo a través del mismo procesador utilizado por MQTT, por lo que la pantalla de monitoreo se actualiza realmente mediante WebSocket y los datos se almacenan en la base.

### ESP32 físico

Cambia:

```text
SIMULATION=0
MQTT_ENABLED=1
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
```

Arranca un broker Mosquitto y configura el firmware con la **IP LAN del Mac**, no `127.0.0.1`, porque para el ESP32 `localhost` sería el propio microcontrolador. Si no usas Docker, en macOS puedes ejecutar `brew install mosquitto` y después `mosquitto -c mosquitto/mosquitto.conf -v`. Copia:

```bash
cp firmware/DuchaESP32/config.example.h firmware/DuchaESP32/config.h
```

Edita Wi‑Fi, IP del broker y pines, y luego con PlatformIO:

```bash
pio run
pio run -t upload
pio device monitor
```

## Docker

Para levantar backend y Mosquitto juntos:

```bash
docker compose up --build
```

Después abre `http://127.0.0.1:8000`.

`mosquitto/mosquitto.conf` está preparado para una demostración local. Para el esquema de seguridad planteado en el PFC se incluye `mosquitto-secure.conf.example`, con TLS, archivo de contraseñas y ACL por tópicos.

## Estructura

```text
ducha_iot_completo/
├── backend/
│   ├── server.py            # API REST + WebSocket
│   ├── db.py                # persistencia y datos de demo
│   ├── schema.sql           # esquema relacional
│   ├── mqtt_service.py      # broker ↔ backend
│   ├── telemetry.py         # persistencia de telemetría/eventos
│   ├── ai_service.py        # entrenamiento/predicción
│   ├── simulator.py         # telemetría para presentación
│   └── security.py          # autenticación
├── firmware/DuchaESP32/
│   ├── DuchaESP32.ino
│   └── config.example.h
├── web/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── mosquitto/
├── docs/
├── scripts/
├── tests/
├── platformio.ini
├── compose.yaml
└── requirements.txt
```

## Datos en tiempo real

El ESP32 publica:

```text
smcdi/device/DUCHA-01/telemetry
smcdi/device/DUCHA-01/events
smcdi/device/DUCHA-01/status
```

El backend publica órdenes en:

```text
smcdi/device/DUCHA-01/commands
```

La web **no se conecta directamente al ESP32 ni a la base de datos**. Consume la API del backend y recibe telemetría por WebSocket.

## Base de datos

Las entidades principales implementadas son usuarios, residentes, dispositivos, programaciones, sesiones, mediciones, eventos, alertas, modelos IA, predicciones, objetivos de consumo, encuestas TAM, configuración y auditoría. SQLite se usa para que la presentación local sea autocontenida; el diseño sigue siendo relacional y mantiene claves foráneas e índices.

Puedes revisar los conteos con:

```bash
python tools/ver_db.py
```

## IA

Los históricos válidos se convierten en características de consumo, duración, caudal, pausas, temperatura, hora y día. Se evalúan tres regresores con validación cruzada. El modelo seleccionado se persiste en `data/models/` y se utiliza para obtener el consumo esperado; el objetivo personalizado aplica el porcentaje de reducción configurado.

La IA tiene una función **predictiva y de personalización**. No controla límites de seguridad, cierre de emergencia ni fallos de sensores.

## Encuesta TAM

La interfaz y la base de datos admiten exactamente 20 respuestas Likert de 1 a 5. El PFC y los mockups revisados no contienen los enunciados definitivos del cuestionario aprobado; por esa razón el proyecto conserva marcadores “Ítem pendiente del cuestionario aprobado” en vez de inventar preguntas. Deben sustituirse cuando se disponga del instrumento validado.

## Pruebas

```bash
pytest -q
```

Las pruebas cubren autenticación, dashboard, residentes, comparación, preparación de sesión, exportación y control de permisos por rol.

## Documentación adicional

- `docs/ARQUITECTURA.md`: flujo completo ESP32–MQTT–backend–BD–web.
- `docs/MQTT_Y_ESP32.md`: tópicos, configuración y conexión física.
- `docs/API.md`: rutas implementadas.
- `docs/DEMO_PRESENTACION.md`: recorrido sugerido para exponer.
- `docs/TRAZABILIDAD_IMPLEMENTACION.md`: relación RF-001 a RF-016 con código y pendientes de validación física.

## Nota de seguridad del prototipo

El código incluye lógica de seguridad, pero sigue siendo un **prototipo académico**. La instalación hidráulica, aislamiento eléctrico, tensión de electroválvulas, etapa de potencia, protección contra cargas inductivas y límites térmicos deben verificarse físicamente antes de probarlo con personas. Las electroválvulas no deben conectarse directamente a los GPIO del ESP32.
