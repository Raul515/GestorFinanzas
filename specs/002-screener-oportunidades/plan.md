# Plan de Implementación Técnica: Spec 002 — Screener Fundamental de Acciones y ETFs

## 1. Resumen Ejecutivo
Este plan detalla la arquitectura técnica para implementar la [Spec 002: Screener Fundamental de Acciones y ETFs](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/002-screener-oportunidades/spec.md).

El objetivo es dotar al usuario de una herramienta de análisis cuantitativo con universos modulares bajo demanda (IBEX 35, EuroStoxx 50, Top 50 EE.UU., ETFs UCITS y Tickers personalizados), ratios financieros clave, presets de inversión y caché persistente de 24h en SQLite (`MarketCache`), respetando el **Principio 9 de la Constitución (Salvaguarda de Seguridad)** y con **0 consumo de tokens de IA**.

El desarrollo se organiza en **5 fases secuenciales estrictas**. Siguiendo la regla de implementación fase a fase con puerta de confirmación, cada fase requerirá que el 100% de sus pruebas pasen y la autorización explícita del usuario antes de proceder a la siguiente.

---

## 2. Arquitectura de Archivos y Componentes

```
GestorFinanzas/
├── tests/
│   ├── unit/
│   │   ├── test_screener_schemas.py             [NUEVO] Tests unitarios de validación de schemas de screener
│   │   └── test_screener_service.py             [NUEVO] Tests unitarios de extracción de ratios, resiliencia y presets
│   └── integration/
│       └── test_screener_api.py                 [NUEVO] Tests de endpoints REST /screener/* y ciclo de vida de caché
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── main.py                          [MODIFICADO] Registro del router screener
│   │   │   └── routers/
│   │   │       └── screener.py                  [NUEVO] Endpoints /screener/universes, /screener/universe/{name}, etc.
│   │   ├── domain/
│   │   │   └── schemas/
│   │   │       └── screener.py                  [NUEVO] Schemas Pydantic v2 (StockScreenerItem, ETFScreenerItem, etc.)
│   │   └── services/
│   │       └── screener_service.py              [NUEVO] Extracción y normalización con yfinance, presets y filtrado puro
│   └── frontend/
│       ├── api_client.py                        [MODIFICADO] Métodos cliente get_screener_*, refresh_screener_* con logging
│       └── app.py                               [MODIFICADO] Nueva pestaña '🔍 Screener y Oportunidades' en Streamlit
└── specs/
    ├── README.md                                [MODIFICADO] Actualización del índice de specs
    └── 002-screener-oportunidades/
        ├── spec.md                              [EXISTENTE] Especificación formal aprobada
        └── plan.md                              [NUEVO] Este documento de arquitectura técnica
```

---

## 3. Desglose Fase por Fase

### Fase 1: Modelado de Dominio y Esquemas Pydantic v2
- **Objetivo**: Diseñar los contratos de datos y validadores estrictos en Pydantic v2 para acciones, ETFs, filtros y respuestas del screener.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/screener.py`
  - `tests/unit/test_screener_schemas.py`
- **Componentes**:
  1. `ScreenerPresetEnum`: Enumeración con valores `all`, `quality`, `high_dividend`, `value`, `growth`, `low_cost_etf`.
  2. `StockScreenerItem`:
     - Identificación: `ticker: str`, `name: str`, `sector: Optional[str]`, `country: Optional[str]`, `currency: str`.
     - Cotización: `price: float`, `change_pct: float`, `market_cap: Optional[float]`, `beta: Optional[float]`.
     - Valoración: `pe_trailing: Optional[float]`, `pe_forward: Optional[float]`, `pb_ratio: Optional[float]`, `ev_to_ebitda: Optional[float]`.
     - Rentabilidad: `dividend_yield: Optional[float]` (en %), `roe: Optional[float]` (en %), `operating_margin: Optional[float]` (en %), `net_margin: Optional[float]` (en %).
     - Solvencia: `debt_to_equity: Optional[float]` (en %), `current_ratio: Optional[float]`.
  3. `ETFScreenerItem`:
     - Identificación: `ticker: str`, `name: str`, `category: Optional[str]`, `currency: str`.
     - Cotización y Métricas: `price: float`, `change_pct: float`, `expense_ratio: Optional[float]` (TER en %), `dividend_yield: Optional[float]` (en %), `total_assets: Optional[float]`, `avg_volume: Optional[float]`, `beta: Optional[float]`.
  4. `ScreenerFilterParams`:
     - Umbrales opcionales: `preset: Optional[ScreenerPresetEnum]`, `max_pe: Optional[float]`, `min_dividend_yield: Optional[float]`, `min_roe: Optional[float]`, `max_debt_to_equity: Optional[float]`, `max_expense_ratio: Optional[float]`, `search_query: Optional[str]`.
  5. `UniverseInfo`: `id: str`, `name: str`, `description: str`, `asset_type: str` ("stock" o "etf"), `ticker_count: int`.
  6. `ScreenerResponse`: `universe: str`, `asset_type: str`, `updated_at: datetime`, `from_cache: bool`, `total_count: int`, `filtered_count: int`, `items: list[Union[StockScreenerItem, ETFScreenerItem]]`.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_screener_schemas.py` pasando al 100%.
  - `.\venv\Scripts\python -m compileall src tests` sin errores.

---

### Fase 2: Servicio de Screener, Universos y Motor de Presets
- **Objetivo**: Implementar la lógica pura de extracción resiliente con `yfinance`, las listas maestras de universos y el motor de filtrado en memoria.
- **Archivos a crear/modificar**:
  - `src/backend/services/screener_service.py`
  - `tests/unit/test_screener_service.py`
- **Componentes**:
  1. **Universos Modulares Predefinidos**:
     - `IBEX_35_TICKERS`: Los 35 valores del selectivo español (`ITX.MC`, `SAN.MC`, `IBE.MC`, `BBVA.MC`, etc.).
     - `EUROSTOXX_50_TICKERS`: 50 mayores empresas europeas (`ASML.AS`, `MC.PA`, `SAP.DE`, `TTE.PA`, etc.).
     - `SP500_TOP50_TICKERS`: Top 50 mega-caps de EE.UU. (`AAPL`, `MSFT`, `NVDA`, `AMZN`, `GOOGL`, etc.).
     - `UCITS_ETFS_TICKERS`: 15-20 ETFs de referencia negociables en Europa (`VWCE.DE`, `CSPX.AS`, `IWDA.AS`, `MEUD.PA`, etc.).
  2. **Extracción Resiliente con Yahoo Finance**:
     - Función `fetch_stock_item(ticker: str) -> Optional[StockScreenerItem]` con extracción segura de campos de `yf.Ticker(t).info` y conversión segura de ratios a porcentajes legibles (ej. `0.045 -> 4.5%`).
     - Función `fetch_etf_item(ticker: str) -> Optional[ETFScreenerItem]` extrayendo TER, AUM y rendimiento.
     - Manejo exhaustivo de datos no disponibles (`None`) para entidades bancarias (sin EBITDA) o valores sin dividendos.
     - Función por lotes `fetch_universe_data(universe_id: str) -> list[Union[StockScreenerItem, ETFScreenerItem]]`.
     - Función `fetch_custom_tickers(tickers: list[str])` que autodetecta si el ticker es ETF o acción y devuelve la lista consolidada.
  3. **Motor de Filtrado y Presets (Funciones Puras)**:
     - `apply_screener_filters(items, filter_params)`:
       - Filtro por Preset:
         - **💎 Calidad y Solvencia**: $\text{ROE} \ge 15\%$, $\text{Margen Neto} \ge 10\%$, $\text{Deuda/Equity} \le 120\%$.
         - **💰 Alto Dividendo**: $\text{Dividend Yield} \ge 3.5\%$, $\text{Forward PER} \le 18$, $\text{Deuda/Equity} \le 150\%$.
         - **🏷️ Valoración Atractiva (Value)**: $\text{Trailing PER} \le 15$, $\text{P/B} \le 2.0$, $\text{Dividend Yield} \ge 2.0\%$.
         - **🚀 Crecimiento y Rentabilidad**: $\text{Margen Operativo} \ge 15\%$, $\text{ROE} \ge 12\%$, $\text{Beta} \ge 0.9$.
         - **🛡️ ETFs de Bajo Coste**: $\text{TER} \le 0.25\%$, $\text{AUM} \ge 500\text{M €}$.
       - Filtro por texto: Coincidencia en `ticker` o `name` (case-insensitive).
       - Filtros por rangos numéricos individuales.
  4. **Observabilidad**: Logging estructurado con `logger.info`, `logger.warning` y `logger.error` ante anomalías o tickers inaccesibles. Prohibido el uso de `pass` silenciosos.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_screener_service.py` con 100% fixtures mockeadas verificando extracción, presets y filtrado.

---

### Fase 3: Endpoints REST en FastAPI con Caché Persistente en SQLite
- **Objetivo**: Exponer el servicio de screener mediante API REST desacoplada, utilizando `MarketCache` para retención de 24 horas y soporte de actualización manual.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/screener.py`
  - `src/backend/api/main.py`
  - `tests/integration/test_screener_api.py`
- **Endpoints**:
  1. `GET /screener/universes`: Devuelve la lista y metadatos de los universos soportados (`UniverseInfo`).
  2. `GET /screener/universe/{universe_id}`:
     - Comprueba si existe caché válida en `market_cache` con clave `screener_{universe_id}` (< 24h).
     - Si está en caché, la recupera y aplica los filtros solicitados (`preset`, rangos numéricos, búsqueda).
     - Si expiró o no existe, invoca `fetch_universe_data`, almacena en SQLite con TTL de 24 horas y retorna el resultado.
  3. `POST /screener/custom`: Recibe `{ "tickers": ["ITX.MC", "BMW.DE", "TSLA"] }`, extrae los datos y aplica los filtros.
  4. `POST /screener/refresh/{universe_id}`: Invalida la entrada específica de `market_cache` y refresca inmediatamente los datos desde Yahoo Finance.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/integration/test_screener_api.py` verificando respuestas 200, serialización Pydantic, TTL de caché y comportamiento de invalidación.

---

### Fase 4: Integración en Frontend (Streamlit) y Salvaguarda de Seguridad
- **Objetivo**: Construir una interfaz visual intuitiva, profesional y de alta densidad de información en Streamlit para filtrar y comparar activos.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py`
  - `src/frontend/app.py`
- **Componentes Visuales**:
  1. **Métodos en `api_client.py`**:
     - `get_screener_universes() -> list[dict]`
     - `get_screener_universe(universe_id: str, ...) -> Optional[dict]`
     - `get_screener_custom(tickers: list[str], ...) -> Optional[dict]`
     - `refresh_screener_universe(universe_id: str) -> bool`
     - Logging exhaustivo en todos los manejadores de excepciones HTTP y de red.
  2. **Pestaña `"🔍 Screener y Oportunidades"` en `app.py`**:
     - **Salvaguarda de Seguridad (Principio 9 de la Constitución)**:
       - Consulta `api_client.get_safety_status()`.
       - Si el fondo de emergencia es insuficiente (< 3 meses de gastos fijos), muestra un banner visible de advertencia:
         > ⚠️ **Aviso de Salvaguarda Patrimonial (Constitución)**: Tu fondo de emergencia actual no cubre los 3 meses mínimos de gastos esenciales. La asignación de capital a activos de renta variable está bloqueada. Esta herramienta tiene fines exclusivamente formativos y de seguimiento.
     - **Barra Superior de Control**:
       - Selector de Universo (pestañas o radio buttons con badges descriptivos).
       - Timestamp de última actualización de datos en caché.
       - Botón `"🔄 Actualizar Universo"` para forzar descarga.
       - Selector de Universo Personalizado con input de texto para ingresar tickers separados por comas.
     - **Barra de Presets Rápidos**:
       - Botones/chips interactivos: *Todos los valores*, *💎 Calidad y Solvencia*, *💰 Alto Dividendo*, *🏷️ Valoración Atractiva*, *🚀 Crecimiento* (o *🛡️ ETFs Bajo Coste* en vista ETFs).
     - **Filtros Manuales Desplegables**:
       - Buscador en tiempo real por ticker o nombre.
       - Sliders numéricos: PER máximo, Dividend Yield mínimo, ROE mínimo, Deuda/Patrimonio máxima.
     - **Tabla Interactiva de Datos**:
       - Renderizado con `st.dataframe` interactivo ordenable por cualquier métrica.
       - Formateo enriquecido:
         - Precios y capitalización con divisas correspondientes (€, $).
         - Variación diaria con formato condicional o signo (+/- %).
         - Ratios contables redondeados a 2 decimales.
         - Celdas con datos no disponibles mostradas limpiamente como `N/D` o `-`.
     - **Exportación de Datos**:
       - Botón para descargar el conjunto filtrado en formato CSV (`st.download_button`).
- **Puerta de Verificación**:
  - Interfaz gráfica probada localmente.
  - Navegación fluida entre pestañas de presupuestos, radar macro y screener.

---

### Fase 5: Pruebas Globales, Control de Regresiones y Cierre
- **Objetivo**: Verificar la estabilidad absoluta del sistema, asegurar que no existan regresiones en fases anteriores y validar el cumplimiento de las directrices de `AGENTS.md` y la `Constitución`.
- **Acciones**:
  1. Ejecución completa de la suite de pruebas:
     ```powershell
     .\venv\Scripts\pytest -v
     ```
     (Se espera alcanzar > 65 pruebas pasando al 100%).
  2. Comprobación exhaustiva de sintaxis Python:
     ```powershell
     .\venv\Scripts\python -m compileall src tests
     ```
  3. Inspección de rutas registradas en OpenAPI para confirmar la consistencia de contratos de API.
  4. Protocolo Pre-Commit:
     - Inspección con `git status -u`.
     - Comprobación de que ningún archivo sensible o local (`.env`, `finanzas.db`) esté rastreado.
  5. Actualización de la Memoria Persistente (`MEMORY.md`) y del índice de especificaciones (`specs/README.md`).
- **Puerta de Verificación**: Cero fallos en pytest, cero regresiones y confirmación final del usuario.

---

## 4. Matriz de Verificación y Criterios de Aceptación

| Componente | Verificación | Comando / Prueba |
| :--- | :--- | :--- |
| **Modelos y Schemas** | Validación de tipos Pydantic y serialización | `tests/unit/test_screener_schemas.py` |
| **Servicio y Presets** | Extracción resiliente y filtros contables precisos | `tests/unit/test_screener_service.py` |
| **Endpoints REST** | Status 200, TTL de 24h en SQLite y refresco forzado | `tests/integration/test_screener_api.py` |
| **Salvaguarda de Seguridad** | Alerta visible si el fondo de emergencia no cubre 3 meses | Verificación en UI de Streamlit |
| **Frontend Streamlit** | Carga inmediata (<1s en caché), formateo y filtros | Verificación en navegador |
| **Suite Completa** | 100% tests pasando sin regresiones | `.\venv\Scripts\pytest -v` |
