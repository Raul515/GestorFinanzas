# Plan de Implementación Técnica: Spec 001 — Radar Macroeconómico y Noticias

## 1. Resumen Ejecutivo
Este plan detalla la arquitectura técnica para implementar la [Spec 001: Radar Macroeconómico y Noticias](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/001-radar-macro-noticias/spec.md), con foco prioritario en España y la Eurozona.

El desarrollo se organiza en 6 fases secuenciales, respetando la Constitución (privacidad local, datos contables protegidos) y garantizando la cobertura de pruebas automatizadas mediante mocks de APIs externas.

---

## 2. Arquitectura de Archivos y Componentes

```
GestorFinanzas/
├── requirements/
│   └── backend.txt                                 [MODIFICADO] Añadir yfinance, google-genai, feedparser
├── tests/
│   ├── unit/
│   │   ├── test_market_data_service.py            [NUEVO] Tests unitarios de métricas macro y prima de riesgo
│   │   ├── test_news_service.py                   [NUEVO] Tests unitarios de extracción de noticias
│   │   └── test_llm_news_analyst.py               [NUEVO] Tests unitarios de análisis de impacto con Gemini
│   └── integration/
│       └── test_market_api.py                     [NUEVO] Tests de endpoints /market/* y caché de 24h
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── main.py                             [MODIFICADO] Registro de router market
│   │   │   └── routers/
│   │   │       └── market.py                       [NUEVO] Endpoints /market/macro-indicators, /market/news y /market/refresh
│   │   ├── database/
│   │   │   ├── componentes/
│   │   │   │   ├── sqlite_db.py                    [MODIFICADO] Registro de modelo MarketCache
│   │   │   │   └── sqlite_crud.py                  [MODIFICADO] Métodos get/set de caché de mercado con TTL
│   │   │   ├── interfaz/
│   │   │   │   └── db_interface.py                 [MODIFICADO] Interfaz IMarketCacheRepository
│   │   │   └── models/
│   │   │       └── market_cache.py                 [NUEVO] Modelo SQLAlchemy para persistir caché 24h en SQLite
│   │   ├── domain/
│   │   │   └── schemas/
│   │   │       └── market.py                       [NUEVO] Schemas Pydantic v2 (MacroIndicator, NewsItem, MarketSnapshot)
│   │   └── services/
│   │       ├── market_data.py                      [NUEVO] Servicio de extracción de cotizaciones e histórico con yfinance
│   │       ├── news_service.py                     [NUEVO] Agregador de noticias financieras con foco en España/Europa
│   │       └── llm_news_analyst.py                 [NUEVO] Analizador de impacto y síntesis neutral vía Gemini Pro API
│   └── frontend/
│       ├── api_client.py                           [MODIFICADO] Métodos get_macro_indicators, get_market_news, refresh_radar
│       └── app.py                                  [MODIFICADO] Pestaña '🌐 Radar Macro y Noticias' con sparklines y filtros
```

---

## 3. Desglose Fase por Fase

### Fase 1: Dependencias y Modelo de Caché Persistente en SQLite
- **Objetivo**: Añadir librerías externas y crear la tabla `market_cache` en SQLite para garantizar la retención de 24 horas entre sesiones sin llamadas redundantes.
- **Acciones**:
  1. Actualizar `requirements/backend.txt`:
     ```
     yfinance>=0.2.40
     google-genai>=1.0.0
     feedparser>=6.0.10
     ```
  2. Instalar dependencias en el entorno virtual `venv`.
  3. Crear `src/backend/domain/models/market_cache.py`:
     ```python
     class MarketCache(Base):
         __tablename__ = "market_cache"

         key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
         data_json: Mapped[str] = mapped_column(Text)
         updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
         expires_at: Mapped[datetime] = mapped_column(DateTime)
     ```
  4. Extender `db_interface.py` y `sqlite_crud.py`:
     - `get_market_cache(key: str) -> Optional[dict]` (comprueba que `now < expires_at`).
     - `set_market_cache(key: str, data: dict, ttl_hours: int = 24)`
     - `invalidate_market_cache(key: Optional[str] = None)`
- **Puerta de Verificación**: Tests unitarios de almacenamiento y expiración de caché pasando al 100%.

---

### Fase 2: Schemas Pydantic y Servicio de Datos Macroeconómicos (`yfinance`)
- **Objetivo**: Modelar y extraer los 4 índices bursátiles, 2 bonos y el cálculo de la prima de riesgo española con su tendencia a 30 días.
- **Acciones**:
  1. Crear `src/backend/domain/schemas/market.py`:
     - `SparklinePoint`: `{"date": str, "value": float}`
     - `MacroIndicator`: `name`, `symbol`, `current_value`, `change_pct`, `change_abs`, `unit`, `sparkline_30d: list[float]`, `region` ("España", "Eurozona", "EE.UU.")
     - `MacroOverviewResponse`: Lista de indicadores macro + timestamp de captura.
  2. Crear `src/backend/services/market_data.py`:
     - Tickers de mercado:
       - IBEX 35: `^IBEX`
       - EuroStoxx 50: `^STOXX50E`
       - S&P 500: `^GSPC`
       - Nasdaq 100: `^NDX`
       - Bono US 10Y: `^TNX`
       - Rendimiento Bono España 10Y y Bund Alemán 10Y (extraídos vía proxies de bonos de yfinance o cálculo diferencial).
     - Fórmula de la Prima de Riesgo:
       $$\text{Prima de Riesgo (pb)} = (\text{Bono España 10Y} - \text{Bund Alemán 10Y}) \times 100$$
     - Extracción de últimos 30 días de cierre diario para alimentar los sparklines.
- **Puerta de Verificación**: `tests/unit/test_market_data_service.py` con fixtures mockeadas de yfinance verificando cálculos y manejo de fines de semana.

---

### Fase 3: Agregación de Noticias y Análisis con Gemini Pro
- **Objetivo**: Recuperar noticias económicas con foco en España/Europa y analizarlas con Gemini Pro para catalogar impacto y redactar el resumen neutral sin sesgos.
- **Acciones**:
  1. Crear `src/backend/services/news_service.py`:
     - Extracción de noticias vía Yahoo Finance España (`^IBEX`) y canales RSS fiables (BCE, elEconomista, Reuters España).
     - Normalización a lista de 10-15 noticias: `title`, `link`, `source`, `published_at`.
  2. Crear `src/backend/services/llm_news_analyst.py`:
     - Conexión con `google-genai` usando `os.getenv("GEMINI_API_KEY")`.
     - Prompt estructurado con *System Instruction* de analista financiero sobrio:
       - Evaluar impacto considerando la perspectiva de un residente en España (BCE, Euríbor, inflación, IBEX).
       - Clasificar en: *Alto*, *Medio*, *Bajo*.
       - Clasificar temática: *Política Monetaria BCE / Tipos e Hipotecas*, *Macroeconomía España y Eurozona*, *Resultados Empresariales*, *Geopolítica y Mercados Globales*.
       - Redactar resumen neutral de 1-2 frases en español libre de sensacionalismo.
     - **Degradación elegante**: Si `GEMINI_API_KEY` no está configurada o la API falla, devolver las noticias originales con aviso de *"Análisis de IA no disponible temporalmente"*.
- **Puerta de Verificación**: `tests/unit/test_llm_news_analyst.py` probando respuestas estructuradas y fallback ante fallo de API.

---

### Fase 4: Endpoints REST en FastAPI
- **Objetivo**: Exponer los datos agregados bajo el router `/market` con soporte para caché persistente de 24 horas y refresco forzado.
- **Acciones**:
  1. Crear `src/backend/api/routers/market.py`:
     - `GET /market/macro-indicators`: Consulta caché SQLite (`"macro_indicators"`). Si no existe o expiró, ejecuta `market_data.py`, guarda en caché (24h) y retorna.
     - `GET /market/news`: Consulta caché SQLite (`"macro_news"`). Si no existe o expiró, ejecuta `news_service.py` + `llm_news_analyst.py`, guarda en caché (24h) y retorna.
     - `POST /market/refresh`: Invalida las claves en caché de SQLite, fuerza la llamada a los proveedores externos e IA, y devuelve el nuevo estado sincronizado.
  2. Registrar `market.router` en `src/backend/api/main.py`.
- **Puerta de Verificación**: `tests/integration/test_market_api.py` probando las respuestas JSON y el comportamiento del TTL de caché.

---

### Fase 5: Métodos Cliente y Nueva Pestaña en Streamlit
- **Objetivo**: Presentar el Radar Macroeconómico en la interfaz de usuario con controles interactivos y sparklines dinámicos.
- **Acciones**:
  1. Actualizar `src/frontend/api_client.py`:
     - `get_macro_indicators() -> Optional[dict]`
     - `get_market_news() -> Optional[list]`
     - `refresh_market_radar() -> bool`
  2. Modificar `src/frontend/app.py`:
     - Incorporar la nueva pestaña `"🌐 Radar Macro y Noticias"` en `tabs_list`.
     - **Cabecera**: Título, fecha/hora de la captura en caché y botón `"🔄 Actualizar Radar"`.
     - **Bloque Macroeconómico**:
       - 2 filas de tarjetas métricas con Altair *sparklines* incrustados (30 días).
       - Columna prioritaria para España: IBEX 35, Bono Español 10Y y Prima de Riesgo.
       - Columna Eurozona y Global: EuroStoxx 50, S&P 500, Nasdaq 100, Bund Alemán y Bono US 10Y.
     - **Bloque de Noticias Filtradas**:
       - Selectores desplegables: `Filtro por Impacto` (Todos / Alto / Medio / Bajo) y `Filtro por Temática`.
       - Tarjetas visuales de noticias:
         - Badge de impacto: Rojo (Alto), Ámbar (Medio), Gris/Azul (Bajo).
         - Etiqueta de temática (ej. *Política Monetaria BCE / Tipos e Hipotecas*).
         - Resumen neutral de 1-2 frases generado por la IA.
         - Enlace `"Leer noticia completa ↗"` hacia la fuente original con fecha y medio emisor.
- **Puerta de Verificación**: La aplicación arranca sin regresiones en las pestañas existentes de presupuestos 50/30/20.

---

### Fase 6: Pruebas Globales, Control de Regresiones y Calidad
- **Objetivo**: Validar el 100% de la suite de pruebas del proyecto y verificar el cumplimiento de los principios constitucionales.
- **Acciones**:
  1. Ejecución de suite completa con `.\venv\Scripts\pytest -v`.
  2. Comprobación de compilación limpia de sintaxis en `src` y `tests`.
  3. Verificación de que ningún dato personal/bancario del usuario se envía en las llamadas a Gemini ni APIs externas (Principio 6: *Local Privacy*).
- **Puerta de Verificación**: Cero fallos en pytest y cero regresiones.

---

## 4. Matriz de Verificación y Criterios de Aceptación

| Componente | Verificación | Comando / Prueba |
| :--- | :--- | :--- |
| **Caché SQLite (24h)** | Persistencia de clave y respeto a TTL | `tests/unit/test_market_data_service.py` |
| **Indicadores y Prima de Riesgo** | Cálculo correcto de diferencial España-Alemania y series de 30 días | `tests/unit/test_market_data_service.py` |
| **Análisis Gemini Pro** | Clasificación tipada y degradación elegante si no hay API key | `tests/unit/test_llm_news_analyst.py` |
| **Endpoints REST** | Status 200 en `/market/*` y funcionamiento de `/market/refresh` | `tests/integration/test_market_api.py` |
| **Frontend Streamlit** | Carga ágil (<1s en caché), sparklines visuales y filtros operativos | `.\venv\Scripts\streamlit run src/frontend/app.py` |
| **Suite Global** | 100% de pruebas pasando sin regresiones | `.\venv\Scripts\pytest` |
