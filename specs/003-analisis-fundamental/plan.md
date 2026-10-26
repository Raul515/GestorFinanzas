# Plan de Implementación Técnica: Spec 003 — Análisis Fundamental (Deep Dive & Quality Value)

## 1. Resumen Ejecutivo
Este plan detalla la arquitectura técnica para implementar la [Spec 003: Análisis Fundamental en Profundidad — Deep Dive](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/003-analisis-fundamental/spec.md), integrando el marco metodológico **Quality Value**.

El sistema combinará:
1. **Motor Contable Local en Python**: Extracción de estados financieros a 4 años (Balance, Resultados, Cash Flow), cálculo algorítmico del **Piotroski F-Score (0 a 9 puntos)** y métricas de **Flujo de Caja Libre (FCF)**.
2. **Analista Agéntico Quality Value (Google Gemini Pro)**: Síntesis neutral basada en datos cuantitativos verificados, clasificando cuadrantes (*Quality Value*, *Calidad Cara*, *Trampa de Valor*), evaluando los 6 ingredientes, modelo y matriz de riesgos (*"¿Qué puede salir mal?"*), y proyectando valoración a 5 años con TIR del 15% al 20%.
3. **Persistencia Local**: Tabla SQLite `watchlist` para seguimiento de valores preferidos y retención de análisis en caché SQLite de 24h (`MarketCache`).
4. **Salvaguarda de Seguridad (Principio 9 de la Constitución)**: Alerta visible y bloqueo preventivo si el fondo de emergencia del usuario no cubre los 3 meses mínimos esenciales.

El desarrollo se organiza en **6 fases secuenciales estrictas**, requiriendo el 100% de pruebas pasando y autorización explícita tras cada fase antes de iniciar la siguiente.

---

## 2. Arquitectura de Archivos y Componentes

```
GestorFinanzas/
├── tests/
│   ├── unit/
│   │   ├── test_deepdive_schemas.py               [NUEVO] Tests unitarios de schemas de deepdive y watchlist
│   │   ├── test_watchlist_model.py                [NUEVO] Tests unitarios del modelo SQLAlchemy y CRUD de watchlist
│   │   ├── test_equity_deepdive.py                [NUEVO] Tests unitarios de extracción contable, Piotroski (9 pts) y FCF
│   │   └── test_llm_quality_value_analyst.py      [NUEVO] Tests unitarios del prompt Quality Value y degradación elegante
│   └── integration/
│       ├── test_deepdive_api.py                   [NUEVO] Tests de endpoints REST /deepdive/* y caché de 24h
│       └── test_watchlist_api.py                  [NUEVO] Tests de endpoints REST /watchlist/* (CRUD en SQLite)
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── main.py                            [MODIFICADO] Registro de routers deepdive y watchlist
│   │   │   └── routers/
│   │   │       ├── deepdive.py                    [NUEVO] Endpoints /deepdive/{ticker} y /deepdive/refresh/{ticker}
│   │   │       └── watchlist.py                   [NUEVO] Endpoints /watchlist (GET, POST, DELETE)
│   │   ├── database/
│   │   │   ├── componentes/
│   │   │   │   ├── sqlite_db.py                  [MODIFICADO] Registro del modelo WatchlistItem
│   │   │   │   └── sqlite_crud.py                [MODIFICADO] Métodos CRUD para lista de seguimiento (watchlist)
│   │   │   ├── interfaz/
│   │   │   │   └── db_interface.py               [MODIFICADO] Interfaz IWatchlistRepository
│   │   │   └── models/
│   │   │       └── watchlist.py                   [NUEVO] Modelo SQLAlchemy para la tabla watchlist en SQLite
│   │   ├── domain/
│   │   │   └── schemas/
│   │   │       ├── deepdive.py                    [NUEVO] Schemas Pydantic v2 (PiotroskiScore, FinancialYear, DeepDiveResponse)
│   │   │       └── watchlist.py                   [NUEVO] Schemas Pydantic v2 (WatchlistCreate, WatchlistResponse)
│   │   └── services/
│   │       ├── equity_deepdive.py                 [NUEVO] Extracción contable (yfinance), algoritmo Piotroski y cálculo FCF
│   │       └── llm_quality_value_analyst.py       [NUEVO] Orquestación agéntica del informe Quality Value con Gemini Pro
│   └── frontend/
│       ├── api_client.py                          [MODIFICADO] Métodos cliente get_deepdive, refresh_deepdive, watchlist_*
│       └── app.py                                 [MODIFICADO] Pestaña '🔬 Análisis Fundamental (Deep Dive)' en Streamlit
└── specs/
    ├── README.md                                  [MODIFICADO] Actualización de estado de Spec 003
    └── 003-analisis-fundamental/
        ├── spec.md                                [EXISTENTE] Especificación formal aprobada
        └── plan.md                                [NUEVO] Este documento de arquitectura técnica
```

---

## 3. Desglose Fase por Fase

### Fase 1: Modelado de Dominio, Modelo SQLite de Watchlist y Esquemas Pydantic v2
- **Objetivo**: Diseñar los contratos de datos fuertemente tipados en inglés para los estados financieros históricos, el desglose de Piotroski, el informe Quality Value y la persistencia de la Watchlist en SQLite.
- **Archivos a crear/modificar**:
  - `src/backend/domain/models/watchlist.py` [NUEVO]
  - `src/backend/database/componentes/sqlite_db.py` [MODIFICADO]
  - `src/backend/database/interfaz/db_interface.py` [MODIFICADO]
  - `src/backend/database/componentes/sqlite_crud.py` [MODIFICADO]
  - `src/backend/domain/schemas/deepdive.py` [NUEVO]
  - `src/backend/domain/schemas/watchlist.py` [NUEVO]
  - `tests/unit/test_deepdive_schemas.py` [NUEVO]
  - `tests/unit/test_watchlist_model.py` [NUEVO]
- **Componentes**:
  1. Modelo SQLAlchemy `WatchlistItem`:
     - `ticker: str` (clave primaria)
     - `name: str`
     - `sector: Optional[str]`
     - `currency: str`
     - `price_at_addition: float`
     - `notes: Optional[str]`
     - `created_at: datetime`
  2. Métodos CRUD en `sqlite_crud.py`:
     - `get_watchlist() -> list[WatchlistItem]`
     - `add_to_watchlist(item: WatchlistCreate) -> WatchlistItem`
     - `remove_from_watchlist(ticker: str) -> bool`
  3. Schemas en `deepdive.py`:
     - `FinancialStatementYear`: `year: int`, `revenue: float`, `gross_profit: Optional[float]`, `operating_income: Optional[float]`, `net_income: float`, `diluted_eps: Optional[float]`, `total_assets: float`, `current_assets: Optional[float]`, `current_liabilities: Optional[float]`, `long_term_debt: Optional[float]`, `total_debt: Optional[float]`, `cash_and_equivalents: Optional[float]`, `operating_cash_flow: float`, `capital_expenditure: float`, `free_cash_flow: float`, `shares_outstanding: Optional[float]`.
     - `PiotroskiCriterion`: `code: str`, `category: str` ("profitability", "leverage_liquidity", "operating_efficiency"), `description: str`, `points: int` (0 o 1), `current_value: Optional[float]`, `previous_value: Optional[float]`.
     - `PiotroskiScore`: `total_score: int` (0 a 9), `max_score: int` (9 o adaptado para bancos), `rating: str` ("Excelente", "Aceptable", "Riesgo Contable"), `criteria: list[PiotroskiCriterion]`.
     - `QualityValueReport`: `quadrant: str` ("Quality Value", "Calidad Cara", "Trampa de Valor"), `summary_thesis: str`, `six_ingredients: dict[str, str]`, `business_model_and_risks: dict[str, Any]`, `bearish_risks: list[str]` (mínimo 2 riesgos), `valuation_projections: dict[str, Any]`, `target_irr_entry_zone: str`.
     - `DeepDiveResponse`: perfil de la empresa, cotización, `statements: list[FinancialStatementYear]`, `piotroski: PiotroskiScore`, `fcf_metrics: dict[str, Any]`, `quality_value_report: Optional[QualityValueReport]`, `is_financial_institution: bool`, `from_cache: bool`, `updated_at: datetime`.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_deepdive_schemas.py tests/unit/test_watchlist_model.py` al 100%.

---

### Fase 2: Motor Contable Local, Cálculo del Piotroski F-Score y Métricas FCF
- **Objetivo**: Implementar el servicio puro en Python que extrae estados financieros con `yfinance`, ejecuta el algoritmo determinista de Piotroski (9 criterios) y calcula las métricas de Flujo de Caja Libre.
- **Archivos a crear/modificar**:
  - `src/backend/services/equity_deepdive.py` [NUEVO]
  - `tests/unit/test_equity_deepdive.py` [NUEVO]
- **Componentes**:
  1. Extracción con `yfinance`:
     - `fetch_historical_financials(ticker: str) -> tuple[dict, list[FinancialStatementYear]]`
     - Lectura resiliente de `balance_sheet`, `financials` y `cashflow` de los últimos 3-4 ejercicios anuales.
     - Detección automática de instituciones financieras (bancos/aseguradoras) mediante sector (`Financial Services`).
  2. Algoritmo Piotroski F-Score:
     - `calculate_piotroski_score(statements: list[FinancialStatementYear], is_bank: bool = False) -> PiotroskiScore`
     - Evaluación estricta de las 9 reglas contables.
     - En bancos: omisión transparente de Margen Bruto y Current Ratio, ajustando el denominador a 7 criterios o marcando `N/A`.
  3. Métricas de Caja y Fosos:
     - `calculate_fcf_metrics(statements, market_cap)`:
       - Serie anual de $\text{FCF} = \text{CFO} - |\text{CapEx}|$.
       - $\text{FCF Yield} = (\text{FCF actual} / \text{Market Cap}) \times 100$.
       - Conversión de beneficio: $\text{FCF} / \text{Beneficio Neto}$.
       - Ratio de reinversión: $|\text{CapEx}| / \text{CFO}$.
       - Diagnóstico de Moat: ROE sostenido $\ge 15\%$ y estabilidad de márgenes.
  4. Observabilidad: Logging estructurado con `logger.warning` y `logger.error` sin ningún `pass` ciego.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_equity_deepdive.py` al 100% con fixtures mockeadas verificando cada uno de los 9 criterios de Piotroski y casos de empresas en pérdidas o bancos.

---

### Fase 3: Analista Agéntico "Quality Value" con Google Gemini (3.1 Flash / 2.5 Pro)
- **Objetivo**: Conectar con Google Gemini API mediante `google-genai` para sintetizar el informe agéntico estructurado siguiendo la metodología Quality Value, utilizando modelos de alto razonamiento financiero (`gemini-3.1-flash` o `gemini-2.5-pro`).
- **Archivos a crear/modificar**:
  - `src/backend/services/llm_quality_value_analyst.py` [NUEVO]
  - `tests/unit/test_llm_quality_value_analyst.py` [NUEVO]
- **Componentes**:
  1. Configuración Flexible del Modelo:
     - Lectura de `GEMINI_DEEPDIVE_MODEL` desde `.env` (ej. `gemini-3.1-flash` o `gemini-2.5-pro`), con fallback automático a `GEMINI_MODEL` o `gemini-2.5-pro`.
     - Esto permite al usuario elegir en su `.env` entre velocidad óptima con razonamiento avanzado (`gemini-3.1-flash`) o máxima profundidad de análisis institucional (`gemini-2.5-pro`).
  2. Construcción del Prompt Estructurado:
     - *System Instruction*: Rol de analista financiero institucional senior especializado en *Quality Value*.
     - Inyección del paquete contable verificado en Python (Piotroski Score, ingresos, BPA, FCF, CapEx, deuda neta, márgenes de los últimos 4 años).
     - Solicitud de salida en JSON estricto con los 4 bloques metodológicos:
       1. Cuadrante (*Quality Value*, *Calidad Cara*, *Trampa de Valor*).
       2. Los 6 ingredientes clave evaluados individualmente.
       3. Modelo de negocio y matriz de riesgos (mínimo 2 riesgos bajistas obligatorios respondiendo a *"¿Qué puede salir mal y cuánto beneficio destruiría?"*).
       4. Valoración a 5 años (Escenario Base vs Escenario Bajo/Estrés), múltiplo conservador, precio objetivo y Zona de Entrada Ideal (TIR 15%-20%).
  3. Resiliencia y Degradación Elegante:
     - Si `GEMINI_API_KEY` no está presente o la llamada falla (error de red o cuota): retorna `None` sin romper el backend; la respuesta marcará `ai_analysis_available=False`.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_llm_quality_value_analyst.py` verificando respuestas JSON válidas, selección de modelo configurable y fallback ante fallo de API.

---

### Fase 4: Endpoints REST en FastAPI con Caché SQLite de 24 Horas
- **Objetivo**: Exponer los servicios de Deep Dive y Watchlist bajo la API REST desacoplada, con caché de 24h para diagnósticos y CRUD para la lista de seguimiento.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/deepdive.py` [NUEVO]
  - `src/backend/api/routers/watchlist.py` [NUEVO]
  - `src/backend/api/main.py` [MODIFICADO: registro de routers]
  - `tests/integration/test_deepdive_api.py` [NUEVO]
  - `tests/integration/test_watchlist_api.py` [NUEVO]
- **Endpoints**:
  1. Router `/deepdive`:
     - `GET /deepdive/{ticker}`: Consulta caché en SQLite (`deepdive_{ticker}`). Si no existe o expiró (> 24h), extrae estados contables, computa Piotroski, invoca al analista de IA, persiste en caché (24h) y devuelve `DeepDiveResponse`.
     - `POST /deepdive/refresh/{ticker}`: Invalida la entrada de caché, recomputa todo y devuelve el análisis fresco.
  2. Router `/watchlist`:
     - `GET /watchlist`: Devuelve la lista de empresas guardadas con su cotización actual y notas.
     - `POST /watchlist`: Añade un ticker a la lista de seguimiento.
     - `DELETE /watchlist/{ticker}`: Elimina el ticker de la lista.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/integration/test_deepdive_api.py tests/integration/test_watchlist_api.py` al 100%.

---

### Fase 5: Métodos Cliente y Nueva Pestaña en Streamlit
- **Objetivo**: Desarrollar la interfaz visual en Streamlit para el análisis fundamental, visualización de estados contables, desglose interactivo de Piotroski, informe Quality Value y gestión de la Watchlist.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO]
  - `src/frontend/app.py` [MODIFICADO]
  - `src/frontend/style.css` [MODIFICADO]
- **Componentes Visuales**:
  1. Métodos en `api_client.py`:
     - `get_deepdive(ticker: str) -> Optional[dict]`
     - `refresh_deepdive(ticker: str) -> Optional[dict]`
     - `get_watchlist() -> list[dict]`
     - `add_to_watchlist(ticker: str, notes: Optional[str] = None) -> Optional[dict]`
     - `remove_from_watchlist(ticker: str) -> bool`
     - Con logging estructurado exhaustivo sin `pass`.
  2. Pestaña `"🔬 Análisis Fundamental (Deep Dive)"` en `app.py`:
     - **Salvaguarda de Seguridad (Principio 9)**: Banner visible de advertencia si el fondo de emergencia es menor a 3 meses de gastos esenciales.
     - **Barra de Búsqueda y Watchlist**:
       - Input de texto para ingresar cualquier ticker con botón *"🔍 Analizar Empresa"*.
       - Acceso rápido: botones/chips de los tickers guardados en la Watchlist local para cargarlos con 1 clic.
       - Botón *"⭐ Guardar en Watchlist"* y *"🔄 Actualizar Análisis"*.
     - **Cabecera Ejecutiva**: Nombre, sector, país, cotización, capitalización bursátil y badge de cuadrante Quality Value.
     - **Scorecard Piotroski F-Score (0 a 9)**:
       - Métrica principal con color condicional (Verde: 7-9, Ámbar: 4-6, Rojo: 0-3).
       - Desglose visual en 9 filas/tarjetas con semáforos, comparando el año actual vs año anterior y explicando cada criterio.
     - **Evolución Contable a 4 Años**:
       - Gráficos Altair interactivos de barras/líneas: Ingresos vs Beneficio Neto vs FCF, y evolución de márgenes.
       - Tabla compacta con el histórico de balance, resultados y flujos de caja.
     - **Informe Agéntico Quality Value (IA)**:
       - Renderizado estructurado en 4 bloques: Cuadrante, 6 Ingredientes, Modelo y Riesgos (*"¿Qué puede salir mal?"* con mínimo 2 riesgos bajistas obligatorios) y Valoración a 5 años con cálculo de TIR y Zona de Entrada Ideal (15%-20%).
       - Aviso de degradación elegante si el análisis de IA no está disponible.
     - **Disclaimer Legal al pie**: Advertencia explícita sobre la naturaleza formativa de la herramienta.
- **Puerta de Verificación**: Interfaz probada visualmente y navegación fluida entre pestañas.

---

### Fase 6: Pruebas Globales, Control de Regresiones y Cierre
- **Objetivo**: Asegurar la estabilidad integral del proyecto, cero regresiones y cumplimiento de los principios constitucionales.
- **Acciones**:
  1. Ejecución de la suite completa de pruebas:
     ```powershell
     .\venv\Scripts\pytest -v
     ```
     (Se prevé superar las 95 pruebas pasando al 100%).
  2. Comprobación exhaustiva de compilación de sintaxis:
     ```powershell
     .\venv\Scripts\python -m compileall src tests
     ```
  3. Verificación de rutas OpenAPI registradas.
  4. Protocolo Pre-Commit: Auditoría con `git status -u` asegurando que no existan credenciales ni bases de datos locales rastreadas.
  5. Actualización de `specs/README.md` y `MEMORY.md`.
- **Puerta de Verificación**: Cero fallos en pytest y confirmación explícita del usuario.

---

## 4. Matriz de Verificación y Criterios de Aceptación

| Componente | Verificación | Comando / Prueba |
| :--- | :--- | :--- |
| **Modelos y Schemas** | Validación de tipos Pydantic v2 y modelo Watchlist | `tests/unit/test_deepdive_schemas.py` y `test_watchlist_model.py` |
| **Piotroski y FCF** | 9 criterios contables calculados y resiliencia en bancos | `tests/unit/test_equity_deepdive.py` |
| **Analista Agéntico IA** | Prompt Quality Value, 4 bloques y degradación elegante | `tests/unit/test_llm_quality_value_analyst.py` |
| **Endpoints REST y Caché** | Status 200 en `/deepdive/*` y `/watchlist/*`, TTL de 24h | `tests/integration/test_deepdive_api.py` y `test_watchlist_api.py` |
| **Frontend Streamlit** | Carga ágil (<1s en caché), semáforos Piotroski y Watchlist | Verificación en navegador |
| **Suite Global** | 100% pruebas pasando sin regresiones | `.\venv\Scripts\pytest -v` |
