# Plan Técnico Spec 017: Unificación SSOT y Modularización en 6 Fases

Este documento define el plan técnico aprobado para ejecutar la [Especificación 017](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/017-unificacion-modularidad-ssot/spec.md) de forma estrictamente secuencial (**una fase a la vez**, con puerta de confirmación del usuario tras verificar cada fase).

---

## Fase 1 — SSOT Contable, Clasificación Canónica y Corrección de Bugs Activos

**Objetivo**: Erradicar los 6 bugs de negocio/SSOT detectados en la auditoría manteniendo intactas las interfaces externas.

### Cambios Planificados
1. **`src/backend/domain/constants.py`, `src/backend/init_db_data.py`, `src/backend/database/componentes/sqlite_db.py`**:
   - Definir `CategoryBlock` (`INCOME`, `NEEDS`, `WANTS`, `SAVINGS`), nombres canónicos de categorías padre, las 28 subcategorías personales y las 4 conjuntas como única fuente de verdad.
   - Exportar `classify_category_block(category)`, `is_income_category(category)` y `is_emergency_fund_subcategory(subcategory)`.
   - Hacer que `init_db_data.py` y `sqlite_db.py` consuman `domain/constants.py` en lugar de redefinir listas.
2. **`src/backend/services/safety_guard.py`, `src/backend/api/routers/safety_guard.py`, `src/backend/services/financial_calculator.py`, `src/backend/database/componentes/sqlite_crud.py`**:
   - Implementar `get_effective_monthly_budgets(db, month)` con fusión por subcategoría (`YYYY-MM` sobre `"BASE"`).
   - Mover `_resolve_monthly_needs()` desde `api/routers/safety_guard.py` a `services/safety_guard.py` reutilizando `get_monthly_needs_budget()` y rangos `Date` exactos.
   - Exponer detalle por subcategoría y distinguir presupuesto real de necesidades esenciales frente al tope 50% en `calculate_category_totals()`.
3. **`src/backend/services/copilot_tools.py`, `src/backend/components/tools/committee_tools.py`, `src/backend/services/joint_accounting_service.py`, `src/backend/api/routers/market.py`**:
   - Usar `CategoryBlock` / `"Deseos y Estilo de vida"` en `copilot_tools.py` y `committee_tools.py` y corregir `monthly_needs_ref` para el Fondo de Emergencia.
   - Alinear la constante `CACHE_KEY_MACRO_INDICATORS = "macro_indicators"` entre `market.py` y `copilot_tools.py`.
   - Corregir `"PROPORTIONAL_INCOME"` -> `SplitMode.INCOME_PROPORTIONAL.value` en `joint_accounting_service.py` y extraer `calculate_member_shares()` reutilizado por aportaciones, liquidaciones y reembolsos.
4. **`src/backend/services/mobile_sync_service.py`, `src/mobile/src/services/storage.ts`, `src/mobile/src/components/CategoryChips.tsx`**:
   - Cambiar IDs de `DEFAULT_FALLBACK_SUBCATEGORIES` en `storage.ts` a IDs negativos (`-1..-13`) para evitar colisiones con SQLite.
   - Clasificar por `classify_category_block()` en `mobile_sync_service.py` evitando que subcategorías nuevas de Necesidades/Ahorro caigan al fallback `%deseo%`, y unificar evaluación del Fondo de Emergencia móvil con `services/safety_guard.py`.

### Verificación Fase 1
- `.\venv\Scripts\python -m compileall -q src tests`
- `.\venv\Scripts\pytest -v tests/unit/test_financial_calculator.py tests/unit/test_safety_guard_service.py tests/unit/test_copilot_tools.py tests/unit/test_committee_nodes.py tests/unit/test_joint_accounting_service.py tests/unit/test_mobile_sync_service.py tests/integration/test_safety_guard_api.py tests/integration/test_mobile_api.py`
- `cd src/mobile && npx tsc --noEmit && npm run build && npm run build:pwa`

---

## Fase 2 — Desacoplamiento de Routers Fat y Repositorio Dios (Backend)

**Objetivo**: Convertir los routers en capa HTTP delgada y segregar el repositorio por dominios.

### Cambios Planificados
1. **`src/backend/services/guidelines_application_service.py` [NEW] + `src/backend/api/routers/guidelines.py`**:
   - Mover toda la lógica transaccional (`get_monthly_guidelines`, `apply_strategy`, `revert_strategy`, `sweep_month_surplus`, `compensate_deficit`), construcción de `split_config`, redondeos `round(..., 2)` de `EmergencyFund` y upserts de presupuesto al nuevo servicio.
2. **Sub-routers `src/backend/api/routers/joint/` [NEW] + `joint_accounting_service.py` + `joint_sync_service.py`**:
   - Dividir `joint.py` en módulos cohesivos (`account.py`, `sinking_funds.py`, `transactions.py`, `contributions.py`, `sync.py`) manteniendo el router agregado `/joint`.
   - Mover `delete_joint_sinking_fund`, `record_assisted_contribution` y `get_joint_health` a servicios, y centralizar `build_joint_transaction_sync_payload()` / `build_sinking_fund_sync_payload()`.
3. **`src/backend/database/interfaz/db_interface.py` + `src/backend/database/componentes/`**:
   - Completar `IJointRepository`.
   - Dividir `sqlite_crud.py` en repositorios especializados (`personal_repo.py`, `joint_repo.py`, `market_repo.py`, `copilot_repo.py`) conservando `SQLiteRepository` como fachada compuesta.
   - Desacoplar `delete_transaction`: extraer las llamadas a disco/sync (`MobileSyncService`, `JointSyncService`) hacia un servicio de aplicación (`transaction_service.py`).

### Verificación Fase 2
- `.\venv\Scripts\python -m compileall -q src tests`
- `.\venv\Scripts\pytest -v tests/unit/test_transactions_repository.py tests/unit/test_joint_accounting_service.py tests/unit/test_joint_sync_service.py tests/integration/test_guidelines_api.py tests/integration/test_joint_api.py tests/integration/test_transactions_api.py`

---

## Fase 3 — Modularización de Servicios Backend, Infraestructura LLM y Utilidades Comunes

**Objetivo**: Unificar utilidades transversales (fechas, ficheros atómicos, sync común y cliente Gemini/LangGraph).

### Cambios Planificados
1. **`src/backend/utils/dates.py` [NEW], `src/backend/utils/files.py` [NEW], `src/backend/services/sync_storage.py` [NEW]**:
   - Centralizar `month_date_range()`, `parse_utc_iso()`, `format_utc_iso()`, `get_next_month_key()`, `atomic_write_json()`, `calculate_file_sha256()`, `resolve_sync_dir()`, `get_or_create_device_id()`, `is_sync_event_file()`, `archive_processed_file()`, `quarantine_error_file()`.
2. **Paquete `src/backend/services/mobile/` [NEW] (`pairing_service.py`, `ingestion_service.py`, `summary_service.py`, `ota_service.py`, `receipt_storage.py`)**:
   - Dividir `mobile_sync_service.py` manteniendo la fachada `MobileSyncService` para compatibilidad de tests e imports.
   - Reutilizar `_to_historical_transaction_item()`, retirar `outbox_dir` no usado y validar tamaño (`<= 5 MB`) y tipo MIME de `receipt_base64` en `/api/mobile/sync`.
3. **`src/backend/services/llm_client.py` [NEW] + Servicios `llm_*.py` + Nodos LangGraph (`components/nodes/`) + `main_investment_orchestrator.py`**:
   - Centralizar `load_dotenv()`, sanitización de `GEMINI_API_KEY`, resolución jerárquica de modelos y `track_external_latency(ExternalProviderEnum.GEMINI, ...)` para los 6 consumidores, propagando `model_name` en `MainInvestmentOrchestrator`.
   - Reutilizar `LocalDocLoader` en `copilot_tools.py:search_local_knowledge` y unificar el patrón cache-aside en `deepdive.py`, `market.py` y `screener.py`.

### Verificación Fase 3
- `.\venv\Scripts\python -m compileall -q src tests`
- `.\venv\Scripts\pytest -v tests/unit/test_mobile_sync_service.py tests/unit/test_joint_sync_service.py tests/unit/test_backup_service.py tests/unit/test_updater_service.py tests/unit/test_llm_copilot_advisor.py tests/unit/test_llm_quality_value_analyst.py tests/unit/test_llm_news_analyst.py tests/unit/test_committee_orchestrator.py tests/integration/test_deepdive_api.py tests/integration/test_market_api.py tests/integration/test_screener_api.py`

---

## Fase 4 — Refactorización de `api_client.py`, Helpers UI Comunes, Idioma y Fechas en PC

**Objetivo**: Eliminar las 104 peticiones duplicadas, los fallos silenciosos (`except: pass`), fugas ISO y duplicación de tarjetas/helpers en `src/frontend/`.

### Cambios Planificados
1. **Paquete `src/frontend/api/` [NEW] (`http.py`, `personal.py`, `market.py`, `ai.py`, `joint.py`, `system.py`, `mobile.py`) + Fachada `src/frontend/api_client.py`**:
   - Implementar `_request()` único con gestión centralizada de sesión, timeouts, códigos HTTP, parsing JSON seguro y logging estructurado.
   - Mantener **todas** las funciones públicas actuales de `api_client.py` (incluidas las cubiertas por tests unitarios) delegando al paquete modular.
   - Centralizar la adaptación controlada de claves en una única frontera respetando el estándar inglés interno (`AGENTS.md` Regla 7) y español en UI, propagando cualquier cambio a todos sus llamadores sin romper compatibilidad.
   - Corregir el borrado accidental de cachés dentro de `get_safety_status()`, completar invalidaciones de caché en mutaciones de `guidelines` y `joint`, y eliminar los 7 `except Exception: pass` de `api_client.py`.
2. **`src/frontend/utils/formatting.py` [NEW] y `src/frontend/components/ui_cards.py` [NEW]**:
   - Unificar los 5 formateadores de fecha en `format_date_es()` / `format_datetime_es()`, corrigiendo las 4 fugas ISO de `app.py` (`L1301, L1499, L1501, L2285`) y añadiendo `format="DD/MM/YYYY"` en `joint_view.py:1383-1393` (Regla 12).
   - Extraer `render_safety_guard_banner()`, `render_month_navigator()`, `render_section_header()` y tarjetas HTML reutilizables, unificando `width="stretch"` en `mobile_view.py` y `joint_view.py`.

### Verificación Fase 4
- `.\venv\Scripts\python -m compileall -q src tests`
- `.\venv\Scripts\pytest -v tests/unit/test_categories_client.py tests/unit/test_frontend_caching.py tests/unit/test_performance_phase1.py tests/unit/test_performance_phase3.py tests/unit/test_sanity.py tests/unit/test_joint_frontend.py tests/unit/test_backup_frontend.py tests/unit/test_updater_frontend.py`

---

## Fase 5 — Modularización de `app.py`, `joint_view.py`, Cero Cálculos en UI y Limpieza de Código QR

**Objetivo**: Cumplir al 100% el Principio 3 de la Constitución y dividir los dos grandes monolitos visuales de Streamlit.

### Cambios Planificados
1. **Traslado a Backend de Cálculos Residuales en UI**:
   - Consumir subtotales de subcategoría desde `calculate_category_totals()` eliminando el doble bucle `pval + rval_trans` de `app.py`.
   - Mover agregaciones anuales/mensuales, upside scenarios Deep Dive, agregaciones/reembolsos de `joint_view.py` (eliminando la fórmula heurística `* 0.4` de `L2054`), repartos porcentuales de `guidelines_view.py` y `total_gastado_movil` de `mobile_view.py` al backend.
2. **Modularización de Vistas bajo `src/frontend/views/`**:
   - Descomponer `app.py` en `personal_annual_view.py`, `personal_monthly_view.py`, `market_radar_view.py`, `screener_view.py`, `deepdive_view.py`, `copilot_view.py`, `committee_view.py` y `settings_view.py`, dejando `app.py` como enrutador/shell limpio.
   - Dividir `joint_view.py` en `joint_setup_view.py`, `joint_dashboard_view.py`, `joint_sinking_funds_view.py`, `joint_search_view.py` y `joint_settlement_view.py`, retirando `importlib.reload(_jv_mod)` y el import privado `_render_personal_assisted_contribution_banner`.
3. **Limpieza de Código Muerto Aprobada**:
   - Eliminar `src/frontend/qrcodegen.py` y las funciones `generate_qr_png_bytes` / `generate_qr_svg_base64` de `mobile_view.py`, actualizando `tests/unit/test_mobile_frontend_view.py`.
   - Limpiar clases CSS huérfanas de `style.css`, variables/imports sin uso, `pass` huérfano, y doble llamada a `get_mobile_status()` en `mobile_view.py`.

### Verificación Fase 5
- `.\venv\Scripts\python -m compileall -q src tests`
- `.\venv\Scripts\pytest -v tests/unit/test_personal_ux_frontend.py tests/unit/test_joint_ux_frontend.py tests/unit/test_joint_frontend.py tests/unit/test_guidelines_view.py tests/unit/test_mobile_frontend_view.py tests/unit/test_sanity.py`

---

## Fase 6 — Unificación de Estado, Utilidades y Modularización en Móvil (`src/mobile/src/`)

**Objetivo**: Modularizar `storage.ts` y `App.tsx`, corregir desincronizaciones optimistas, endurecer `api.ts` y recompilar PWA/APK.

### Cambios Planificados
1. **`src/mobile/src/utils/categories.ts` [NEW] y `src/mobile/src/utils/formatters.ts` [NEW]**:
   - Centralizar `classifyBudgetBlock()`, `isIncomeSubcategory()`, `buildTempSubcategory()` y `getSubcategoryEmoji()` (desacoplando `CategoryChips.tsx`).
   - Unificar `formatDateDisplay()` (con guarda de vacío), `formatEuro()` consistente (`es-ES`), `parseDecimalInput()`, `triggerHaptic()`, `normalizeServerUrl()`, `isNativeOrLocalOrigin()` y helpers de mes.
2. **Modularización de `storage.ts` y `App.tsx`**:
   - Dividir `storage.ts` en `storage/config.ts`, `storage/transactions.ts`, `storage/cache.ts`, `storage/presets.ts`, `services/exporter.ts` y `services/offlineEngine.ts` (función pura sin acceso directo a `localStorage`).
   - Unificar `monthlySummary` y `monthlySummariesMap` en un solo store reactivo en `App.tsx` (incluyendo suma de `PENDING_SYNC` locales sobre cachés offline) y extraer `hooks/useConnectivity.ts` / `hooks/useMobileSync.ts`.
3. **Endurecimiento de `api.ts` y Componentes**:
   - Reemplazar los 3 `AbortController` manuales por `fetchWithTimeout()`, gestionar HTTP `401` y `403` globalmente, parsear el detalle HTTP `422` por transacción en `/sync`, añadir logging en `catch` y unificar campo `amount` en `/api/mobile/budget`.
   - Extraer `ReceiptViewerModal.tsx` compartido entre `HistoryView` y `SearchView`, deduplicar `SearchView` por `mobile_event_id`, validar fecha no vacía en `QuickCaptureView.tsx` y preset `> 0` en `ManagePresetsModal.tsx`, y leer la versión de `package.json` vía Vite `define` para reducir duplicación.
   - Recompilar ambos bundles (`npm run build` y `npm run build:pwa`).

### Verificación Fase 6
- `cd src/mobile && npx tsc --noEmit && npm run build && npm run build:pwa`
- `.\venv\Scripts\pytest -v tests/unit/test_mobile_quick_presets.py tests/unit/test_mobile_offline_engine.py tests/unit/test_mobile_sync_service.py tests/integration/test_mobile_api.py tests/integration/test_mobile_e2e_flow.py`
