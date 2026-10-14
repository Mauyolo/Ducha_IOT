# Guía corta para la presentación

## Antes de exponer

Ejecuta `INICIAR_MAC.command`. Con `SIMULATION=1` el proyecto carga 18 residentes, 108 sesiones experimentales y una sesión demostrativa en tiempo real. Abre `http://127.0.0.1:8000` e ingresa con `admin.ucsm` / `Admin2026!`.

## Recorrido recomendado

1. **Dashboard:** muestra consumo, sesiones, reducción Tradicional vs. Inteligente y alertas.
2. **Residentes:** abre R-003 y enseña su historial individual.
3. **Sesiones de ducha:** muestra caudal, volumen, temperatura y tiempo actualizándose sin recargar la página. Explica que el simulador entra por la misma función que MQTT; al conectar el ESP32 se desactiva `SIMULATION`.
4. **Estadísticas:** filtra y exporta CSV/XLSX.
5. **IA:** entrena/compara Regresión Lineal, Random Forest y Gradient Boosting; luego genera predicción y objetivo personalizado.
6. **Alertas:** enseña trazabilidad y estados pendiente/revisada/resuelta.
7. **Encuesta TAM:** la estructura de 20 respuestas Likert está implementada, pero los enunciados se mantienen como marcadores porque el PFC no contiene el cuestionario aprobado.
8. **Configuración/Usuarios:** sólo visibles para Administrador.

## Idea clave para la defensa

El navegador no gobierna la seguridad. Si se pierde Internet, el ESP32 sigue midiendo y puede cerrar las electroválvulas por temperatura o fallo del sensor. MQTT y la web son para monitoreo, trazabilidad, órdenes autorizadas y análisis.
