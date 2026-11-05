# Especificación 014: Optimización Integral de Rendimiento, Reducción de Redundancias y Escalabilidad

## 1. Resumen Ejecutivo y Visión

Tras la auditoría técnica global de rendimiento de la aplicación, se han detectado cuellos de botella significativos que degradan la experiencia de usuario a medida que el sistema escala:
1. **Sobrecarga de Renderizado en Streamlit**: En `📊 Presupuesto y Meses`, el bucle de cálculo del Resumen Anual (24 llamadas HTTP para consultar presupuestos y transacciones de los 12 meses) se ejecuta en **cada interacción del usuario**, incluso cuando se encuentra en la pestaña de `📅 Gestión Mensual` anotando un gasto simple.
2. **Carga Impaciente en Módulos de IA**: En `🧠 Inversión y Mercado (IA)`, las 5 pestañas se evalúan a la vez en segundo plano, forzando la descarga del universo de 35 activos del Screener y el análisis contable de `ITX.MC` al acceder a la sección.
3. **Ausencia de Caching en Frontend**: Las categorías, subcategorías, versiones y datos casi estáticos se consultan a la API en cada interacción de usuario sin aprovechar `@st.cache_data`.
4. **Falta de Reutilización de Sockets TCP**: `api_client.py` realiza 164 llamadas directas sin `requests.Session()`, abriendo y destruyendo decenas de conexiones TCP por recarga en Windows.
5. **Ineficiencias Críticas de Base de Datos**: `save_budgets_bulk` ejecuta 40 transacciones físicas a disco (`fsync`) en bucle; las consultas filtran fechas con `extract()` inhabilitando el índice B-Tree; faltan índices en claves foráneas de alto volumen; y SQLite carece de modo `WAL` y memoria extendida.
6. **Generación Incondicional del Informe Excel**: En la Cuenta Conjunta, el archivo `.xlsx` se genera en memoria en cada recarga mediante consultas N+1 en lugar de hacerlo bajo demanda.

El objetivo de esta especificación es **erradicar todas las llamadas redundantes a la API, optimizar el acceso a base de datos en SQLite, reutilizar conexiones HTTP e incorporar una estrategia robusta de caching y carga diferida (lazy load)**.

---

## 2. Historias de Usuario (HU)

- **HU-1 (Fluidez en la Gestión Mensual)**: Como usuario que anota sus gastos cotidianos en la pestaña mensual, quiero que la interfaz responda al instante sin ejecutar peticiones innecesarias de cálculo del año completo.
- **HU-2 (Consultas de Mercado e IA Inmediatas)**: Como usuario que utiliza el Screener o consulta el análisis fundamental, quiero que tras la primera carga los datos se sirvan al instante desde memoria RAM durante 30 minutos sin llamadas redundantes a la API.
- **HU-3 (Conexiones HTTP Ligeras y Persistentes)**: Como aplicación que realiza múltiples consultas a la API local, quiero reutilizar las conexiones TCP mediante Keep-Alive para reducir la latencia de transporte y evitar saturar sockets en Windows.
- **HU-4 (Guardado de Presupuesto Atómico y Rápido)**: Como usuario que guarda su presupuesto base o mensual, quiero que la operación se complete en milisegundos en 1 sola transacción a disco sin bloqueos.
- **HU-5 (Base de Datos Concurrente y Sin Bloqueos)**: Como usuario de la app, quiero que las lecturas y escrituras en SQLite no se bloqueen mutuamente mediante el modo Write-Ahead Logging (WAL) y que toda la base contable resida en memoria RAM.
- **HU-6 (Exportación Eficiente en la Cuenta Conjunta)**: Como pareja que revisa la economía familiar, quiero que la cuenta conjunta cargue con total ligereza y que el Excel estructurado se genere únicamente cuando pulsemos deliberadamente el botón de descarga.

---

## 3. Requerimientos Funcionales (RF)

### 3.1 Capa de Red y Base de Datos SQLite (Fase 1)

- **RF-1 (Pool de Conexiones TCP con Keep-Alive)**:
  - En `src/frontend/api_client.py`, todas las peticiones HTTP (`GET`, `POST`, `DELETE`, etc.) deben ejecutarse a través de una instancia singleton `_session = requests.Session()` configurada con un `HTTPAdapter` con tamaño de pool y Keep-Alive.
- **RF-2 (PRAGMAs de Alto Rendimiento en SQLite)**:
  - En `src/backend/database/componentes/sqlite_db.py`, al establecer cualquier conexión SQLite se deben activar obligatoriamente:
    - `PRAGMA foreign_keys = ON`
    - `PRAGMA journal_mode = WAL` (Write-Ahead Logging)
    - `PRAGMA synchronous = NORMAL`
    - `PRAGMA cache_size = -64000` (64 MB de memoria RAM)
    - `PRAGMA temp_store = MEMORY`
- **RF-3 (Transacción Atómica Única en `save_budgets_bulk`)**:
  - En `src/backend/database/componentes/sqlite_crud.py`, `save_budgets_bulk` debe consultar los presupuestos existentes del mes en una sola lectura agrupada y ejecutar **un único `self.db.commit()`** al final del procesamiento de todos los elementos, eliminando los commits individuales en bucle.
- **RF-4 (Optimización de Filtros de Fecha con Índices B-Tree)**:
  - En `get_transactions()` y `get_joint_transactions()`, se debe reemplazar el filtrado por función `extract('year', date)` y `extract('month', date)` por filtrado por rango directo `Transaction.date.between(start_date, end_date)`.
- **RF-5 (Índices en Modelos ORM y Migración Introspectiva)**:
  - Se debe declarar `index=True` en `Transaction.subcategory_id`, `JointTransaction.joint_account_id`, `JointTransaction.settlement_status` y `JointMonthlyContribution.personal_transaction_id`.
  - Se debe declarar un índice compuesto único en `MonthlyBudget`: `Index('idx_budget_month_subcat', 'month', 'subcategory_id', unique=True)`.
  - En `init_db()` de `sqlite_db.py`, se deben crear defensivamente estos índices mediante `CREATE INDEX IF NOT EXISTS`.

### 3.2 Estrategia de Caching en Frontend (Fase 2)

- **RF-6 (Caché de Metadatos Estáticos y Configuración)**:
  - `get_categorias()` y `get_subcategorias()` deben decorarse con `@st.cache_data(ttl=600)` (10 minutos).
  - `get_screener_universes()` y `get_app_version()` deben decorarse con `@st.cache_data`.
- **RF-7 (Caché de Datos de Mercado e IA)**:
  - `get_macro_indicators()` y `get_market_news()` con `@st.cache_data(ttl=300)` (5 minutos).
  - `get_screener_universe()` y `get_deepdive_analysis()` con `@st.cache_data(ttl=1800)` (30 minutos).
- **RF-8 (Caché de Entidades del Hogar)**:
  - `get_joint_subcategories()` (`ttl=600`) y `get_joint_sinking_funds()` (`ttl=60`).
- **RF-9 (Invalidación Selectiva de Caché)**:
  - Crear mecanismos de limpieza controlada (`clear_frontend_cache()`) ante inserciones, actualizaciones o eliminaciones que requieran refresco visual inmediato.

### 3.3 Optimización del Ciclo de Vida Streamlit y Lazy Loading (Fase 3)

- **RF-10 (Aislamiento de Ejecución en Presupuesto y Meses)**:
  - En `src/frontend/app.py`, el bucle de recolección de los 12 meses del Resumen Anual **solo debe ejecutarse cuando la pestaña activa sea "📊 Resumen Anual"**, apoyándose además en `@st.cache_data(ttl=120)`.
  - Cuando el usuario se encuentre en "📅 Gestión Mensual", las 24 llamadas a la API del año completo quedan estrictamente suprimidas.
- **RF-11 (Carga Bajo Demanda en Módulos de IA)**:
  - En Deep Dive, suprimir el auto-análisis forzado de `ITX.MC`. El análisis solo se dispara si el usuario pulsa deliberadamente `[🔍 Analizar]`.
- **RF-12 (Generación de Excel del Hogar Bajo Demanda y Carga Eager)**:
  - En `joint_view.py`, el archivo Excel solo debe generarse cuando el usuario pulse el botón de exportación o mediante caché de sesión.
  - En `generate_household_excel_export` (`joint_accounting_service.py`), la consulta de transacciones debe incorporar `joinedload()` para resolver relaciones en 1 sola consulta SQL.
---

## 4. Mejoras Técnicas Futuras de Rendimiento (Post-Spec 014)

1. **Streaming en el Copiloto Patrimonial y Comité Asesor (Percepción de Latencia en IA)**:
   - Implementar Server-Sent Events (SSE) en los endpoints de agentes en FastAPI y renderizado progresivo mediante `st.write_stream()` en Streamlit.
   - Reduce el tiempo hasta el primer token (*Time-to-First-Token*) de ~5 segundos a < 500 ms, transformando la percepción de fluidez durante las respuestas extensas de Google Gemini.
2. **Paginación y Virtualización en el Buscador Global de Gastos (`/joint/transactions/search`)**:
   - Incorporar parámetros `limit` y `offset` (o paginación por cursor) en backend y controles de página en la vista de Streamlit.
   - Previene la saturación de memoria y tiempos de transferencia ante históricos acumulados de más de 5.000 transacciones multianuales.
3. **Pre-agregación y Downsampling de Series Temporales en Gráficos Altair**:
   - En vistas analíticas y sparklines de cotizaciones o evolución multianual, pre-procesar y muestrear los datos en Python/Pandas antes de serializarlos al JSON de especificación Vega-Lite de Altair.
   - Evita la sobrecarga del DOM del navegador y aligera drásticamente el renderizado interactivo en el cliente.
