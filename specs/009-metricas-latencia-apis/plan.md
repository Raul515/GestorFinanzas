# Plan de Implementación: Especificación 009 — Métricas de Rendimiento y Profiling de Latencia en APIs Externas

Este plan técnico desglosa la implementación de la **Especificación 009** en 2 fases secuenciales estrictas. Siguiendo la metodología SDD (*Spec-Anchored*), cada fase requiere el 100% de sus pruebas automatizadas pasando y la confirmación explícita del usuario antes de avanzar a la siguiente.

---

### Fase 1: Esquemas Pydantic, Motor `LatencyTracker`, Utilidades de Profiling y Endpoint REST

- **Objetivo**: Desarrollar los modelos de datos tipados, el gestor de memoria con búfer circular (`collections.deque(maxlen=1000)`), el decorador y context manager de medición, el cálculo determinista de estadísticas/percentiles (p50, p90, p95, p99), las alertas en `logs/backend.log` y el endpoint REST `GET /metrics/latency`.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/latency_metrics.py` [NUEVO: Esquemas Pydantic v2 `ExternalProviderEnum`, `LatencyStatusEnum`, `CallMetricItem`, `ProviderLatencyStats`, `LatencyMetricsReport`]
  - `src/backend/services/latency_profiler.py` [NUEVO: Clase `LatencyTracker`, función de cálculo de percentiles, context manager `track_external_latency`, decorador `@profile_external_call` y singleton `get_latency_tracker()`]
  - `src/backend/api/routers/metrics.py` [NUEVO: Endpoints `GET /metrics/latency` y `DELETE /metrics/latency`]
  - `src/backend/api/main.py` [MODIFICADO: Registro del router `metrics.router`]
  - `tests/unit/test_latency_profiler.py` [NUEVO: Pruebas unitarias para el búfer circular, cálculo de percentiles, umbrales y manejo defensivo]
  - `tests/integration/test_metrics_api.py` [NUEVO: Pruebas de integración para los endpoints REST]
- **Casos de Prueba a Verificar**:
  - Inserción en búfer circular: retención máxima de 1.000 elementos con descarte FIFO del más antiguo.
  - Cálculo estadístico: verificación de media, min, max y percentiles (p50, p90, p95, p99) con muestras sintéticas.
  - Clasificación de severidad: `OK`, `SLOW` y `CRITICAL` según umbrales configurables y emisión de advertencias a log.
  - Manejo de excepciones en llamadas externas: asignación de estado `ERROR` y preservación de la excepción original hacia el llamador.
  - Resiliencia defensiva: simulación de fallo en el tracker sin afectar a la función medida.
  - API REST: respuesta 200 con `LatencyMetricsReport` en `GET /metrics/latency` y vaciado de memoria en `DELETE /metrics/latency`.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_latency_profiler.py tests/integration/test_metrics_api.py
  ```
- **Criterio de Aceptación**: 100% de pruebas unitarias y de integración pasando.

---

### Fase 2: Instrumentación de Proveedores Externos (Yahoo Finance, BCE, Gemini)

- **Objetivo**: Integrar las utilidades de profiling (`track_external_latency` / `@profile_external_call`) en todas las llamadas salientes a Yahoo Finance, BCE y Google Gemini en el backend, verificando la ausencia de regresiones y la captura real de métricas.
- **Archivos a crear/modificar**:
  - `src/backend/services/market_data.py` [MODIFICADO: Instrumentación de `_fetch_yahoo_ticker` y `_fetch_ecb_series`]
  - `src/backend/services/screener_service.py` [MODIFICADO: Instrumentación de descargas cuantitativas de Yahoo Finance]
  - `src/backend/services/news_service.py` [MODIFICADO: Instrumentación de Yahoo Finance News y RSS del BCE]
  - `src/backend/services/deepdive_service.py` [MODIFICADO: Instrumentación de consultas fundamentales de Yahoo Finance]
  - `src/backend/services/llm_quality_value_analyst.py` [MODIFICADO: Instrumentación de inferencia Gemini]
  - `src/backend/services/llm_news_analyst.py` [MODIFICADO: Instrumentación de inferencia Gemini]
  - `src/backend/services/llm_copilot_advisor.py` [MODIFICADO: Instrumentación de inferencia Gemini]
  - `tests/unit/test_external_instrumentation.py` [NUEVO: Pruebas con mocks verificando que cada servicio invoca el tracker con sus parámetros correspondientes]
  - `MEMORY.md` [MODIFICADO: Registro de la conclusión de la Spec 009]
  - `specs/README.md` [MODIFICADO: Actualizar índice con Spec 009 completada]
- **Casos de Prueba a Verificar**:
  - Verificación de que una llamada a cotización de Yahoo Finance registra la métrica correspondiente en el tracker.
  - Verificación de que una consulta de series del BCE registra la métrica con el target y duración correctos.
  - Verificación de que una llamada a Gemini registra el modelo utilizado y su latencia.
  - Verificación de que errores de red (timeout, fallo de conexión) se capturan con status `ERROR` y duration en ms.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_latency_profiler.py tests/integration/test_metrics_api.py tests/unit/test_external_instrumentation.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas asociadas a la especificación pasando.
