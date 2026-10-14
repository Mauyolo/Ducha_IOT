# VERSION ESP32 EN UN SOLO ARCHIVO .INO

Puedes cargar en Arduino IDE solo `firmware/DuchaESP32_UnSoloArchivo/DuchaESP32_UnSoloArchivo.ino`.
No necesita el archivo `config.h`. Las bibliotecas Arduino requeridas siguen siendo:
**PubSubClient (Nick O'Leary), ArduinoJson 7, OneWire y DallasTemperature**.

**Configuracion recomendada para conectarlo al dashboard real:**

1. En la carpeta raiz del proyecto, ejecuta `py tools/setup_local.py --host TU_IP_PC`, usando la IPv4 de tu PC (obtenla con `ipconfig`).
2. Ese comando genera certificados, contrasenas y **reescribe el archivo `.ino` autocontenido** con `MQTT_HOST`, `MQTT_PASSWORD` y `ROOT_CA` correctos. Necesitas `openssl` en PATH para ejecutarlo.
3. Abre el archivo generado `firmware/DuchaESP32_UnSoloArchivo/DuchaESP32_UnSoloArchivo.ino` y modifica **solo** `WIFI_SSID` y `WIFI_PASSWORD` con los de tu Wi-Fi de 2.4 GHz. No pegues aquí tus claves reales.
4. Abre ese `.ino` en Arduino IDE e instala las bibliotecas. No abras el firmware anterior que aún tiene `#include "config.h"`.
5. Inicia el broker y backend como se explica más abajo; prepara una sesión desde el dashboard. Sin sesión preparada, las lecturas de sensores solo aparecen por puerto serie.

**Si descargas el `.ino` suelto** en vez del ZIP, podrás compilarlo instalando las bibliotecas, pero **no conectará al servidor** hasta sustituir `MQTT_HOST`, `MQTT_PASSWORD` y `ROOT_CA` por los generados para el broker real. La aplicación web y base de datos siguen ejecutándose fuera del ESP32, en la computadora.

No subas el archivo generado (con contraseñas) a repositorios públicos, ni lo compartas sin borrar claves. El actuador permanece desactivado (`ENABLE_ACTUATORS=false`) para las pruebas.

---

# Conectar ESP32, base de datos y dashboard (ducha IoT)

Este proyecto **ya implementa** la integración de mediciones y sesiones. Se ha actualizado `firmware/DuchaESP32/DuchaESP32.ino` y se ha agregado al inicio del dashboard un resumen de las lecturas que llegaron al backend.

## Qué hace cada parte

```text
YF-S201 GPIO18 ─┐
                ├── ESP32 ── Wi-Fi 2.4 GHz ── MQTT/TLS:8883 ── Broker Mosquitto
DS18B20 GPIO4 ──┘                                            │
                                               Backend Python / MQTT
                                                        │
                                              Valida / deduplica / guarda
                                                        │
                                              SQLite: data/ducha.db
                                                (o MySQL opcional)
                                                        │
                                         API /api/v1/sesiones/{id}/lecturas
                                                        │
                                             Dashboard http://localhost:8000
```

**El ESP32 no escribe directamente en SQLite/MySQL.** El backend recibe y guarda cada muestra. Se envía una muestra cada segundo durante las sesiones. El navegador consulta el backend aproximadamente cada dos segundos.

## 1. Cableado

| Sensor | Terminal | ESP32 |
|---|---|---|
| YF-S201 | señal de pulsos | GPIO18 (nivel máximo **3.3 V**) |
| YF-S201 | GND | GND común |
| YF-S201 | alimentación | consultar ficha del módulo concreto |
| DS18B20 | DQ | GPIO4 |
| DS18B20 | VDD | 3V3 |
| DS18B20 | GND | GND |
| Resistencia de 4.7 kΩ | entre DQ y 3V3 | necesaria para 1-Wire |

No suponer los colores de una sonda impermeable DS18B20 sin verificar su ficha técnica. Si el sensor de flujo recibe 5 V, **garantizar** que su salida eléctrica hacia GPIO18 no exceda 3.3 V; adaptar el nivel si es necesario. Mantener electrónica fuera de la zona mojada y no realizar pruebas con personas sin verificación técnica de seguridad. `ENABLE_ACTUATORS=false` debe mantenerse durante pruebas iniciales.

## 2. Preparar el equipo Windows

1. Descomprimir el proyecto y abrir PowerShell/CMD dentro de `ducha_iot`.
2. Instalar Python 3.12 con opción «Add Python to PATH» y Docker Desktop. Usar Git Bash para disponer de OpenSSL.
3. Ejecutar `ipconfig` y anotar la IPv4 LAN de la computadora; por ejemplo, `192.168.1.50` (**ejemplo**, no es una IP universal).
4. Ejecutar `py tools/setup_local.py --host 192.168.1.50` sustituyendo por tu IPv4 real. Esto genera `.env`, certificados TLS, contraseñas y `firmware/DuchaESP32/config.h`. Si anteriormente tenías `SIMULATION=1`, esta operación lo cambia a `0`.
5. Abrir `firmware/DuchaESP32/config.h`, y colocar `WIFI_SSID` y `WIFI_PASSWORD` de tu Wi-Fi de 2.4 GHz. Confirmar que `MQTT_HOST` corresponde a la IPv4 de la PC. **No publicar** `config.h` ni `.env`.
6. Ejecutar `docker compose up -d broker`; comprobar `docker compose logs broker`.
7. Ejecutar `py -m pip install -r requirements.txt` y luego `py -m backend.server`.
8. Abrir `http://localhost:8000` desde la misma PC. Usuario `admin`; ver la contraseña generada `ADMIN_PASSWORD` en `.env`.

El ESP32 y la PC deben conectarse a la misma LAN. Permitir TCP **8883** entrante en la PC para la red privada. No publicar este puerto en internet.

## 3. Cargar el firmware

1. Abrir Arduino IDE 2 y el archivo `firmware/DuchaESP32/DuchaESP32.ino`.
2. Instalar la placa **ESP32 Dev Module** y bibliotecas `PubSubClient 2.8`, `ArduinoJson 7`, `OneWire`, `DallasTemperature`.
3. Comprobar que `config.h` está junto al `.ino` y que contiene la CA generada.
4. Cargar el sketch y abrir **Monitor Serie a 115200**.
5. Verificar mensajes `[DS18B20] Detectado`, `[MQTT] Conectado` y lecturas de pulsos/caudal/temperatura. El ESP32 necesita hora NTP válida para verificar el certificado TLS.

Si aparece **`[DS18B20] NO DETECTADO`**: comprobar GND común, VDD=3V3, DQ=GPIO4 y la resistencia pull-up de **4.7 kΩ entre DQ y 3V3**. El firmware vuelve a buscar el DS18B20 aproximadamente cada 10 segundos cuando falta una lectura válida. Esto ayuda a diagnosticar, pero no arregla un cableado defectuoso.

## 4. Registrar una ducha real en la BD

1. En el dashboard, ir a **Residentes** y crear `R001` (o el código del participante).
2. Pulsar **Nueva sesión** o **Preparar sesión**. Seleccionar `R001`, `tradicional` o `inteligente` y un objetivo en litros.
3. Verificar que el comando pasó de `preparando` a **`preparada`**. Si no, comprobar los logs MQTT y Monitor Serie.
4. **Abrir el agua** para que el YF-S201 emita pulsos. Desde la primera detección de flujo se enviarán lecturas una vez por segundo.
5. Revisar **Dashboard → Lecturas en vivo del ESP32** y **Monitoreo → parámetros y gráfica**. Se actualizan aproximadamente cada dos segundos.
6. Cerrar físicamente el agua. Después de 60 s sin flujo la sesión termina (configurable); también puede pulsarse «Detener», lo que no sustituye el cierre manual si no hay actuador.
7. Ver **Historial** y **Reportes**. Para consultar la BD SQLite, ejecutar `py tools/ver_db.py` o abrir `data/ducha.db` mediante SQLite Browser.

### Columnas guardadas en SQLite

- `medicion.sesion_id`: sesión asociada al residente.
- `medicion.seq`: secuencia para deduplicar reenvíos.
- `medicion.recibido`: hora de recepción.
- `medicion.caudal_l_min`: caudal en litros/minuto.
- `medicion.volumen_l`: litros acumulados.
- `medicion.temperatura_c`: °C o `NULL` si no se pudo leer el sensor.
- `medicion.elapsed_s`: segundos desde inicio de la sesión.
- `sesion`: totales, duración, pausas, estado y calidad de datos.

## 5. Comprobaciones rápidas

| Síntoma | Comprobación |
|---|---|
| Caudal sí, temperatura ERROR | cableado DS18B20 y pull-up 4.7 kΩ |
| ESP32 lee sensores, pero nada en BD | `SIMULATION=0`, broker, `MQTT_HOST`, Wi-Fi, hora NTP, certificado y preparar sesión |
| Dashboard muestra «Esperando que pase agua» | sesión preparada, pero YF-S201 aún sin pulsos |
| «MQTT desconectado» | Docker/broker, firewall TCP 8883 y credenciales/certificado |
| Lecturas en Monitor Serie, pero sesión no preparada | el backend no ha confirmado la orden; revisar broker y el estado de la sesión |
| Valor de litros incorrecto | calibrar `PULSES_PER_LITER` (450 inicial, no universal) con recipiente graduado |

Para verificar el software sin hardware ejecutar `py -m unittest discover -s tests -v`. También se puede usar `py tools/setup_local.py --simular` y probar el dashboard con registros **simulados**, siempre separados de las mediciones reales.

**Limitaciones:** no se puede verificar desde este entorno la instalación física del ESP32, el broker Docker real, las lecturas auténticas de los sensores o la compilación en una placa. El firmware implementa una cola RAM, no almacenamiento local permanente en el dispositivo. No regula mezcla de agua fría/caliente ni constituye protección certificada contra quemaduras. La base de datos, por defecto, es SQLite; MySQL 8.4 es una configuración opcional descrita en el README.
