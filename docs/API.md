# API REST del SMCDI

La aplicación usa Bearer Token luego de `POST /api/v1/auth/login`. Las rutas principales implementadas son:

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/v1/auth/login` | Autenticación |
| GET | `/api/v1/dashboard` | KPIs, comparación y actividad |
| GET/POST | `/api/v1/residentes` | Consulta/registro de residentes |
| GET/PATCH | `/api/v1/residentes/{id}` | Detalle/actualización |
| POST | `/api/v1/sesiones/preparar` | Preparar sesión y referencia IA |
| GET | `/api/v1/sesiones/activa` | Sesión actual |
| GET | `/api/v1/sesiones/{id}` | Resumen de sesión |
| GET | `/api/v1/sesiones/{id}/lecturas` | Serie de telemetría |
| POST | `/api/v1/sesiones/{id}/detener` | Solicitud de detención |
| GET | `/api/v1/historial` | Historial filtrable |
| GET | `/api/v1/reportes/comparacion` | Tradicional vs. inteligente |
| GET | `/api/v1/exportaciones?format=csv|xlsx` | Exportación seudonimizada |
| GET/PATCH | `/api/v1/alertas` / `/api/v1/alertas/{id}` | Gestión de alertas |
| GET | `/api/v1/ia` | Panel de IA |
| POST | `/api/v1/ia/entrenar` | Evalúa modelos de regresión |
| POST | `/api/v1/predicciones` | Predicción/objetivo personalizado |
| GET | `/api/v1/modelos/{id}/metricas` | MAE, RMSE y R² |
| GET/POST | `/api/v1/encuestas` | Encuesta TAM |
| GET/PATCH | `/api/v1/configuracion` | Parámetros autorizados |
| GET/POST/PATCH | `/api/v1/usuarios` | Gestión de cuentas (administrador) |
| GET | `/api/v1/health` | Estado de servicios |
| WS | `/ws?token=...` | Telemetría en tiempo real |

FastAPI expone documentación interactiva en `/docs` mientras el servidor está activo.
