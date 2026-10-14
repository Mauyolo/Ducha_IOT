# Trazabilidad de implementación RF-001 a RF-016

Esta matriz relaciona los requerimientos funcionales del PFC con los archivos concretos de esta entrega. “Implementado” significa que existe soporte de software/firmware; los criterios que dependen de magnitudes físicas (precisión del sensor, tiempo real de actuación, calibración hidráulica) deben validarse con el prototipo montado.

| RF | Función | Implementación principal | Estado de esta entrega |
|---|---|---|---|
| RF-001 | Registrar sesión de ducha: inicio, pausas y fin | `DuchaESP32.ino`, `telemetry.py`, tabla `sessions/session_events` | Implementado; umbrales configurables |
| RF-002 | Medir caudal y volumen con YF-S201 | Interrupción por pulsos, cálculo L/min y volumen; `measurements` | Implementado; requiere calibración física ≤5% |
| RF-003 | Controlar suministro de agua | GPIO de válvula fría/caliente y comandos MQTT | Implementado en firmware; requiere etapa de potencia y validación <2 s |
| RF-004 | Controlar/monitorear temperatura DS18B20 | DallasTemperature + límites locales y cierre térmico | Implementado; requiere validación experimental <3 s |
| RF-005 | Retroalimentación luminosa/sonora | LED y buzzer según progreso del objetivo inteligente | Implementado |
| RF-006 | Registrar datos vía IoT | MQTT, cola temporal, FastAPI y SQLite | Implementado |
| RF-007 | Comparar modos | `/api/v1/reportes/comparacion`, Dashboard/Estadísticas | Implementado por residente/agregado |
| RF-008 | Configurar perfiles de residente | CRUD de residentes; temperatura, objetivo, secuencia y condición | Implementado |
| RF-009 | Generar alertas | Temperatura, consumo, sensor/seguridad, trazabilidad y estados | Implementado |
| RF-010 | Administrar usuarios | Administrador/Moderador, alta/edición/desactivación y permisos | Implementado |
| RF-011 | Reportes estadísticos | Exportación CSV y XLSX compatible con análisis posterior | Implementado |
| RF-012 | Encuestas TAM | Formulario Likert 20 ítems + tabla `surveys` | Estructura implementada; enunciados pendientes del instrumento aprobado |
| RF-013 | Analizar patrones | Panel IA y características históricas por residente | Implementado |
| RF-014 | Predecir consumo esperado | Regresión Lineal, Random Forest y Gradient Boosting | Implementado |
| RF-015 | Generar objetivo personalizado | Predicción × criterio de reducción; `consumption_targets` | Implementado |
| RF-016 | Evaluar modelo IA | MAE, RMSE, R², validación cruzada y versión de modelo | Implementado |

## Aspectos que no pueden darse por validados sólo con software

La entrega deja preparados los mecanismos, pero la aceptación física de RF-002, RF-003 y RF-004 exige el montaje real: calibrar el YF-S201 con un volumen patrón, medir con cronómetro la respuesta de las electroválvulas y provocar desviaciones térmicas controladas para comprobar el tiempo de corrección. Del mismo modo, el cuestionario TAM debe reemplazar los marcadores por los 20 enunciados del instrumento finalmente validado antes de recolectar datos reales.
