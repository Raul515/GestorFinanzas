# Especificación 009: Métricas de Rendimiento y Profiling de Latencia en APIs Externas (Yahoo Finance, BCE y Gemini)

## 1. Resumen Ejecutivo y Visión

Actualmente, el **Gestor de Finanzas Personales** se integra con tres proveedores externos clave para enriquecer la experiencia de usuario y el análisis patrimonial:
1. **Yahoo Finance (`yfinance`)**: Extracción de cotizaciones de mercado, variación diaria, series históricas a 30 días, noticias financieras de índices/empresas y métricas cuantitativas para el Screener y Deep Dive.
2. **Banco Central Europeo (BCE / ECB API REST y RSS)**: Tipos de interés de referencia (Bund alemán a 10 años, Bono español a 10 años, Euríbor e inflación) y comunicados oficiales de política monetaria.
3. **Google Gemini (API de Google AI)**: Modelos LLM para síntesis cualitativa de noticias, informes agénticos de inversión *Quality Value* y asesoría interactiva del Copiloto Patrimonial.

A pesar de que el sistema cuenta con middleware de observabilidad para las peticiones HTTP del servidor FastAPI y persistencia rotativa con filtro de privacidad (`specs/007-sistema-logs-rotativos`), **las llamadas hacia estas APIs externas carecen de métricas granulares de latencia de red y profiling de rendimiento**. Cuando una consulta de mercado o un análisis agéntico experimenta retrasos, no es posible determinar de forma inmediata si el cuello de botella reside en la conexión de red local, en la saturación de los servidores del proveedor externo (Yahoo Finance / BCE) o en el tiempo de inferencia del LLM (Gemini).

El **objetivo** de esta especificación es dotar al sistema de una arquitectura de profiling y monitorización de latencia en milisegundos para todas las llamadas a APIs externas:
- **Almacenamiento en Memoria RAM con Búfer Circular**: Búfer de alta velocidad (`collections.deque(maxlen=1000)`) thread-safe en el backend que retiene las últimas 1.000 llamadas sin generar contención ni bloqueos de escritura en SQLite.
- **Cálculo de Percentiles y Estadísticas Agregadas**: Disponibilidad inmediata de métricas agregadas por proveedor: total de peticiones, tasa de éxito/error, media aritmética, mínimo, máximo y percentiles p50, p90, p95 y p99.
- **Detección Determinista de Cuellos de Botella y Umbrales de Alerta**: Clasificación automática del estado de cada llamada en `OK`, `SLOW` o `CRITICAL` según umbrales configurables por proveedor (ej. Yahoo Finance > 2.000 ms, BCE > 1.500 ms, Gemini > 4.000 ms), emitiendo avisos estructurados en `logs/backend.log`.
- **API REST Desacoplada (`/metrics/latency`)**: Endpoints dedicados para consultar el reporte de métricas en formato JSON o resetear el búfer bajo demanda, sin saturar la interfaz de Streamlit ni sobrecargar la experiencia del usuario final.
- **Instrumentación Failsafe con Cero Sobrecarga**: Patrón decorador y context manager con gestión defensiva absoluta (`try-finally`); el profiler jamás interrumpirá ni modificará el resultado funcional de las llamadas de negocio en caso de error interno de telemetría.

---

## 2. Usuarios y Casos de Uso

- **Desarrollador y Operador del Sistema**:
  - Necesita identificar con exactitud qué proveedor externo está degradando los tiempos de respuesta de la aplicación (`GET /metrics/latency`).
  - Necesita analizar la variabilidad de red mediante percentiles (p95 y p99) para ajustar timeouts y políticas de reintento o caché.
  - Necesita trazas de advertencia automáticas en `logs/backend.log` cuando una llamada externa supere los umbrales de latencia tolerables.
- **Usuario del Sistema**:
  - Se beneficia de una aplicación más ágil gracias a la detección temprana y resolución de cuellos de botella de red y optimización de cachés.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Medición Granular de Latencia por Llamada)**: Como desarrollador, quiero que cada llamada saliente a Yahoo Finance, BCE o Gemini registre su duración exacta en milisegundos, operación, objetivo, código de estado y resultado.
- **HU-2 (Búfer Circular en Memoria sin Impacto en Disco)**: Como operador, quiero que las métricas se almacenen en un búfer circular en RAM acotado a 1.000 entradas para evitar sobrecarga de E/S y contención en la base de datos local SQLite.
- **HU-3 (Detección de Cuellos de Botella y Logs de Alerta)**: Como desarrollador, quiero que las llamadas que excedan los umbrales de advertencia queden etiquetadas como `SLOW` o `CRITICAL` y se registren en `logs/backend.log` para diagnosticar caídas o saturaciones de proveedores.
- **HU-4 (Consulta de Métricas y Percentiles vía API REST)**: Como desarrollador o herramienta de monitorización, quiero un endpoint `GET /metrics/latency` que proporcione estadísticas agregadas (p50, p90, p95, tasa de error) desglosadas por proveedor y un listado de las llamadas más recientes.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Esquemas de Datos de Métricas (`src/backend/domain/schemas/latency_metrics.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE modelar las métricas de profiling mediante esquemas Pydantic v2:
  - `ExternalProviderEnum`: Enumeración con valores `"yahoo_finance"`, `"ecb"`, `"gemini"`, `"other"`.
  - `LatencyStatusEnum`: Enumeración con valores `"OK"`, `"SLOW"`, `"CRITICAL"`, `"ERROR"`.
  - `CallMetricItem`: Registro individual de una llamada: `provider`, `operation`, `target` (opcional: ticker, endpoint, modelo), `duration_ms` (milisegundos con 2 decimales), `status`, `status_code` (opcional), `error_message` (opcional) y `timestamp` (UTC).
  - `ProviderLatencyStats`: Resumen estadístico por proveedor con `total_calls`, `successful_calls`, `failed_calls`, `slow_calls`, `avg_duration_ms`, `min_duration_ms`, `max_duration_ms`, `p50_duration_ms`, `p90_duration_ms`, `p95_duration_ms`, `p99_duration_ms`, `last_call_timestamp` y `thresholds` configurados.
  - `LatencyMetricsReport`: Informe global con `uptime_seconds`, `total_calls_recorded`, `buffer_capacity`, mapa de proveedores (`providers`) y lista de llamadas recientes (`recent_calls`).

### RF-2: Motor Central de Profiling y Búfer Circular (`src/backend/services/latency_profiler.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE proveer la clase `LatencyTracker` gestionando un `collections.deque(maxlen=1000)` protegido mediante `threading.Lock` para garantizar seguridad multihilo.
- **Criterio EARS (Event-driven)**: CUANDO se registre una llamada en `record_call(...)`, EL SISTEMA DEBE clasificar su estado:
  - Si finalizó con excepción no recuperada: estado `ERROR`.
  - Si `duration_ms >= critical_threshold`: estado `CRITICAL`.
  - Si `duration_ms >= warning_threshold`: estado `SLOW`.
  - En cualquier otro caso: estado `OK`.
- **Criterio EARS (Event-driven)**: CUANDO el estado de la llamada sea `SLOW`, `CRITICAL` o `ERROR`, EL SISTEMA DEBE emitir un registro estructurado en `logs/backend.log`:
  - `logger.warning("EXTERNAL_API_LATENCY_ALERT provider=%s op=%s target=%s duration=%.2fms threshold=%.2fms status=%s", ...)` para `SLOW` o `CRITICAL`.
  - `logger.error("EXTERNAL_API_CALL_ERROR provider=%s op=%s target=%s duration=%.2fms error=%s", ...)` para `ERROR`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `get_metrics_report(limit_recent: int = 50, provider: Optional[str] = None)`, EL SISTEMA DEBE calcular de forma determinista los percentiles (p50, p90, p95, p99) y agregados matemáticos para cada proveedor filtrado o activo.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `reset()`, EL SISTEMA DEBE vaciar el búfer de métricas de forma atómica.

### RF-3: Utilidades de Instrumentación Decorador y Context Manager
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE proveer utilidades limpias y reutilizables para envolver llamadas de red:
  - Context Manager: `track_external_latency(provider: ExternalProviderEnum, operation: str, target: Optional[str] = None)`
  - Decorador: `@profile_external_call(provider: ExternalProviderEnum, operation: str, target_extractor: Optional[Callable] = None)`
- **Criterio EARS (State-driven)**: MIENTRAS se mida una llamada saliente, el medidor DEBE emplear `time.perf_counter()` para máxima precisión en microsegundos y conversión a milisegundos (`ms`).
- **Criterio EARS (Unwanted Behaviour)**: SI el propio mecanismo de tracking o registro de métricas genera una excepción interna, EL SISTEMA DEBE capturarla y registrarla en silencio defensivo sin alterar ni abortar la ejecución del flujo de negocio principal.

### RF-4: Configuración de Umbrales por Variables de Entorno
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE soportar la personalización de umbrales mediante `.env` con valores predeterminados seguros:
  - Yahoo Finance:
    - `LATENCY_THRESHOLD_YAHOO_WARN_MS`: 2000 ms (2.0s)
    - `LATENCY_THRESHOLD_YAHOO_CRIT_MS`: 4000 ms (4.0s)
  - Banco Central Europeo:
    - `LATENCY_THRESHOLD_ECB_WARN_MS`: 1500 ms (1.5s)
    - `LATENCY_THRESHOLD_ECB_CRIT_MS`: 3000 ms (3.0s)
  - Google Gemini (Inferencia LLM):
    - `LATENCY_THRESHOLD_GEMINI_WARN_MS`: 4000 ms (4.0s)
    - `LATENCY_THRESHOLD_GEMINI_CRIT_MS`: 8000 ms (8.0s)

### RF-5: Endpoints REST en FastAPI (`src/backend/api/routers/metrics.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE exponer las siguientes rutas REST bajo el prefijo `/metrics`:
  - `GET /metrics/latency`: Devuelve el reporte completo `LatencyMetricsReport`. Parámetros opcionales:
    - `provider`: Filtro por proveedor (`yahoo_finance`, `ecb`, `gemini`).
    - `limit_recent`: Número máximo de llamadas individuales a incluir (por defecto 50, máx 200).
  - `DELETE /metrics/latency`: Reinicia el búfer circular en memoria (código HTTP 200 con confirmación JSON).
- **Criterio EARS (Event-driven)**: CUANDO arranque el servidor backend (`src/backend/api/main.py`), EL SISTEMA DEBE registrar el router de métricas junto a los routers existentes.

### RF-6: Instrumentación de Clientes y Servicios Existentes
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE instrumentar los puntos clave de salida a red:
  1. **Yahoo Finance**:
     - `src/backend/services/market_data.py`: `_fetch_yahoo_ticker` (operación: `ticker_history`) y `fetch_market_snapshot`.
     - `src/backend/services/screener_service.py`: llamadas de descarga de universos (operación: `screener_download`).
     - `src/backend/services/news_service.py`: `fetch_yahoo_finance_news` (operación: `news_feed`).
     - `src/backend/services/deepdive_service.py`: consultas de ratios e info contable (operación: `fundamental_data`).
  2. **Banco Central Europeo (BCE)**:
     - `src/backend/services/market_data.py`: `_fetch_ecb_series` (operación: `yield_series`).
     - `src/backend/services/news_service.py`: feed RSS del BCE (operación: `ecb_rss`).
  3. **Google Gemini**:
     - `src/backend/services/llm_quality_value_analyst.py`: llamada `generate_content` (operación: `quality_value_report`).
     - `src/backend/services/llm_news_analyst.py`: llamada `generate_content` (operación: `news_sentiment_analysis`).
     - `src/backend/services/llm_copilot_advisor.py`: llamada `generate_content` (operación: `copilot_chat`).

---

## 5. Requisitos No Funcionales (RNF)

- **RNF-1 (Convenciones de Idioma - Opción 1 de la Constitución)**:
  - Todo el código backend, esquemas Pydantic, nombres de métodos, variables y endpoints 100% en inglés (`LatencyTracker`, `ExternalProviderEnum`, `duration_ms`, `record_call`, `get_metrics_report`, `/metrics/latency`).
  - Especificación, documentación y mensajes en logs de usuario en español.
- **RNF-2 (Rendimiento y Cero Sobrecarga)**:
  - El impacto de medición por llamada debe ser inferior a 0.1 ms (sobrecarga despreciable).
  - La lectura de reportes agregados y percentiles sobre un búfer de 1.000 llamadas debe resolverse en < 5 ms.
- **RNF-3 (Concurrencia y Thread-Safety)**:
  - Las operaciones de inserción y lectura en el búfer circular deben ser atómicas y seguras frente a accesos concurrentes de hilos o corrutinas de FastAPI.
- **RNF-4 (Privacidad y Sanitización - Principios 10 y 11)**:
  - Ningún parámetro sensible (claves de API de Gemini, tokens o cabeceras Bearer) debe incluirse en los campos `target` o `error_message` de las métricas.
  - El `PrivacyFilter` de la Spec 007 se aplicará automáticamente a cualquier traza emitida a `logs/backend.log`.
- **RNF-5 (Cobertura de Pruebas Automatizadas)**:
  - Cobertura completa con `pytest` al 100% en pruebas unitarias (`tests/unit/test_latency_profiler.py`, `tests/unit/test_external_instrumentation.py`) y de integración API (`tests/integration/test_metrics_api.py`).
