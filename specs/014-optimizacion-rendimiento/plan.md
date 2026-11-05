# Plan de Desarrollo: Especificación 014 — Optimización Integral de Rendimiento

## 1. Arquitectura y Estrategia de Ejecución

Siguiendo las directrices de `docs/constitution.md` y `AGENTS.md`, la especificación se desarrollará de forma estrictamente secuencial en **3 fases**. Cada fase se verificará con pruebas automatizadas completas antes de solicitar confirmación al usuario para avanzar a la siguiente.

```
Rama de trabajo: feat/spec-014-optimizacion-rendimiento
Fase 1: Capa de Red y Base de Datos SQLite (Backend & sqlite_db)
Fase 2: Estrategia de Caching Frontend (@st.cache_data)
Fase 3: Optimización del Ciclo de Vida Streamlit y Lazy Loading
Fusión final: Merge en develop tras 100% de tests
```

---

## 2. Desglose de Fases

### Fase 1: Capa de Red y Base de Datos SQLite
- **Objetivo**: Establecer los cimientos de alto rendimiento a nivel de transporte HTTP y motor de base de datos.
- **Entregables**:
  1. `src/frontend/api_client.py`: Singleton `_session = requests.Session()` con `HTTPAdapter`, pool de conexiones (10 a 20) y Keep-Alive. Migración de llamadas directas a `_session`.
  2. `src/backend/database/componentes/sqlite_db.py`: Activación de PRAGMAs `WAL`, `synchronous=NORMAL`, `cache_size=-64000`, `temp_store=MEMORY`.
  3. `src/backend/database/componentes/sqlite_crud.py`:
     - Refactorización de `save_budgets_bulk` a commit atómico único.
     - Sustitución de `extract('year', date)` y `extract('month', date)` por `date.between(start_date, end_date)`.
  4. Modelos ORM e Índices:
     - `src/backend/domain/models/transactions.py`: `subcategory_id` con `index=True`.
     - `src/backend/domain/models/budgets.py`: Índice compuesto en `(month, subcategory_id)`.
     - `src/backend/domain/models/joint.py`: Índices en `joint_account_id`, `settlement_status` y `personal_transaction_id`.
     - `sqlite_db.py`: Migraciones defensivas `CREATE INDEX IF NOT EXISTS`.
  5. Pruebas: Batería de tests unitarios y de integración para validar persistencia atómica, consultas por fecha y modelos.

### Fase 2: Estrategia de Caching Frontend (`@st.cache_data`)
- **Objetivo**: Erradicar peticiones repetidas a datos estáticos, cotizaciones de mercado y catálogos de cuentas.
- **Entregables**:
  1. Envoltorios de caché en `api_client.py` con TTLs optimizados:
     - Metadatos: `get_categorias` (10m), `get_subcategorias` (10m), `get_screener_universes` (1h), `get_app_version` (5m).
     - Mercado e IA: `get_macro_indicators` (5m), `get_market_news` (5m), `get_screener_universe` (30m), `get_deepdive_analysis` (30m).
     - Cuenta Conjunta: `get_joint_subcategories` (10m), `get_joint_sinking_funds` (1m).
  2. Funciones de invalidación de caché (`clear_frontend_cache()`) ante mutaciones.
  3. Pruebas unitarias para validar comportamiento de caching y expiración.

### Fase 3: Optimización del Ciclo de Vida Streamlit y Lazy Loading
- **Objetivo**: Eliminar ejecuciones invisibles de pestañas pesadas en Streamlit y optimizar el rendimiento interactivo.
- **Entregables**:
  1. `src/frontend/app.py`: Sincronización de pestañas en `📊 Presupuesto y Meses`. El bucle de 12 meses solo se ejecuta si la pestaña activa es `📊 Resumen Anual`.
  2. Carga bajo demanda en `🧠 Inversión y Mercado (IA)`: Desactivar auto-análisis forzado de `ITX.MC`.
  3. `src/frontend/views/joint_view.py` y `src/backend/services/joint_accounting_service.py`: Generación de Excel bajo demanda y optimización con `joinedload()`.
  4. Pruebas unitarias de frontend (`test_personal_ux_frontend.py`, `test_joint_ux_frontend.py`).
  5. Verificación de no regresión en la suite de pruebas.
---

## 3. Registro de Mejoras Futuras Identificadas (Post-Spec 014)

- **Streaming de Respuestas IA**: SSE y `st.write_stream()` para Copiloto y Comité Asesor (TTFT < 500 ms).
- **Paginación en Buscador de Gastos**: Parámetros `limit` y `offset` para tablas masivas multianuales.
- **Downsampling en Gráficos**: Agregación previa de puntos de datos en Python para series temporales de Altair/Vega-Lite.
