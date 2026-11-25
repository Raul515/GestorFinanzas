# Especificación 017: Unificación SSOT, Corrección de Divergencias y Modularización Integral

## 1. Resumen Ejecutivo y Visión

Tras el crecimiento incremental de las especificaciones **000 a 016**, la auditoría estática transversal del repositorio (`src/backend/`, `src/frontend/` y `src/mobile/src/`) ha identificado monolitos de 1.000 a 2.600 líneas, lógica financiera duplicada en interfaz, routers HTTP acoplados directamente a persistencia SQLAlchemy y **6 bugs funcionales activos** derivados de la ruptura del principio de Fuente Única de Verdad (SSOT).

El objetivo de la **Especificación 017** es consolidar la arquitectura limpia y mantenible del sistema sin romper ninguna funcionalidad existente ni sus contratos con los tests automatizados:

1. **SSOT Contable y Corrección de Bugs Activos**: Unificar la clasificación de bloques 50/30/20/Ingresos/Fondo de Emergencia, la fusión de presupuestos (`YYYY-MM` sobre `BASE`), el reparto proporcional entre miembros y el catálogo fallback móvil.
2. **Desacoplamiento de Capas (Backend)**: Dejar los routers FastAPI como capa HTTP fina delegando en servicios de aplicación y dividir el repositorio monolítico (`SQLiteRepository`) por dominios.
3. **Infraestructura Compartida (Sync, LLM, Utilidades)**: Extraer helpers comunes de sincronización, fechas, hashes y cliente Gemini/LangGraph con telemetría uniforme.
4. **Cliente HTTP Unificado y Estándar de Idioma/Fechas en PC**: Centralizar las peticiones HTTP de Streamlit, corregir invalidaciones de caché, eliminar silenciamientos `except Exception: pass` (Principio 13) y garantizar formato español `DD/MM/AAAA` (Regla 12).
5. **Cero Cálculos Contables en UI y Modularización de Vistas**: Dividir `app.py` y `joint_view.py` en vistas limpias de presentación (Principio 3) y retirar código QR obsoleto (`qrcodegen.py`), manteniendo intactas las funciones públicas de `api_client.py` cubiertas por tests.
6. **Modularización y Consistencia Offline/Online en Móvil**: Unificar utilidades, estado de resúmenes y endurecimiento de red/validación en `src/mobile/src/`.

---

## 2. Convenciones de Idioma, Compatibilidad y Alcance

- **Estándar Internacional (Constitución Principio 12 / `AGENTS.md` Regla 7)**:
  - Todo el código backend, esquemas Pydantic, modelos SQLAlchemy, endpoints REST, funciones y variables internas deben mantenerse **100% en inglés** (`name`, `type`, `amount`, `date`, `category_id`, `subcategory_id`, `description`, `month`).
  - Toda la interfaz de usuario (PC Streamlit y Móvil React/APK), documentación, docstrings explicativos y mensajes visibles deben permanecer **100% en español**, con fechas renderizadas estrictamente en `DD/MM/AAAA` (Regla 12).
  - La normalización de claves heredadas en español/inglés (`nombre`/`name`, `cantidad`/`amount`, etc.) se centraliza en una única frontera adaptadora en `src/frontend/` propagando de forma coherente el contrato a todos sus llamadores sin romper compatibilidad ni pruebas existentes.
- **Preservación de API pública de `api_client.py`**: Se conservan todas las funciones públicas actuales de `src/frontend/api_client.py` (incluidas las validadas únicamente en tests unitarios), respaldadas internamente por la capa unificada `_request()`.
- **Retirada de Código QR Obsoleto**: Tras la adopción del emparejamiento por PIN de 6 dígitos en Spec 016, se elimina `src/frontend/qrcodegen.py` y los helpers `generate_qr_png_bytes` / `generate_qr_svg_base64` en `src/frontend/views/mobile_view.py`, actualizando `tests/unit/test_mobile_frontend_view.py`.

---

## 3. Requerimientos Funcionales (RF)

- **RF-01 (Clasificación Canónica de Categorías y Catálogo Semilla Único)**:
  - Definir `CategoryBlock` (`INCOME`, `NEEDS`, `WANTS`, `SAVINGS`), nombres canónicos, subcategorías semilla personales (28) y conjuntas (4) en `src/backend/domain/constants.py`, junto a funciones puras `classify_category_block()`, `is_income_category()` e `is_emergency_fund_subcategory()`.
  - Eliminar las duplicaciones en `init_db_data.py`, `sqlite_crud.py`, `sqlite_db.py`, `mobile_sync_service.py`, `joint_sync_service.py`, `copilot_tools.py` y `committee_tools.py`.
  - Corregir el bug `"Deseos"` vs `"Deseos y Estilo de vida"` en Copiloto y Comité.
- **RF-02 (Fusión Única de Presupuestos `YYYY-MM` + `BASE` y Salvaguarda de Emergencia)**:
  - Implementar `get_effective_monthly_budgets(db, month)` con fusión por subcategoría (`YYYY-MM` sobre `BASE`) usada uniformemente por `SQLiteRepository`, `mobile_sync_service.py`, `guidelines`, `copilot_tools.py` y `committee_tools.py`.
  - Trasladar `_resolve_monthly_needs()` desde `api/routers/safety_guard.py` a `services/safety_guard.py`, distinguiendo el presupuesto real de necesidades esenciales (base del Fondo de Emergencia) del tope teórico del 50% de ingresos reales en `calculate_category_totals()`.
  - Unificar redondeo (`round(..., 2)`), respeto a `target_months` y eliminación del fallback fijo `1000.0` en `mobile_sync_service.py`.
- **RF-03 (Corrección de Caché Macro, Reparto Proporcional Conjunto y Catálogo Móvil)**:
  - Unificar la clave de caché macro `"macro_indicators"` entre `market.py` y `copilot_tools.py`.
  - Corregir `"PROPORTIONAL_INCOME"` -> `SplitMode.INCOME_PROPORTIONAL.value` en `joint_accounting_service.py` y unificar `calculate_member_shares()` entre cálculo mensual, liquidación y reembolso por cierre de huchas.
  - Usar IDs temporales negativos (`-1..-13`) en `DEFAULT_FALLBACK_SUBCATEGORIES` (`storage.ts`) y resolver subcategorías creadas desde móvil por `classify_category_block()` sin caer erróneamente al fallback `%deseo%`.
- **RF-04 (Desacoplamiento de Routers y Repositorios Backend)**:
  - Extraer toda la persistencia, cálculos y mutaciones de `EmergencyFund`/`MonthlyBudget` desde `api/routers/guidelines.py` hacia `services/guidelines_application_service.py`.
  - Dividir `api/routers/joint.py` en sub-routers especializados y trasladar la orquestación contable y constructores de eventos delta a `joint_accounting_service.py` / `joint_sync_service.py`.
  - Dividir `sqlite_crud.py` en repositorios por dominio manteniendo fachada `SQLiteRepository`, completando `IJointRepository` y sacando la lógica de disco/sync de `delete_transaction` hacia un servicio de aplicación.
- **RF-05 (Servicios Modulares, Cliente LLM Único y Utilidades Comunes)**:
  - Centralizar utilidades de fechas (`utils/dates.py`), ficheros/hashes (`utils/files.py`), almacenamiento común de sync (`services/sync_storage.py`), dividir `mobile_sync_service.py` en 5 servicios cohesivos (validando tamaño/MIME de `receipt_base64` en `/sync`), y crear `services/llm_client.py` único con telemetría `track_external_latency` para los 3 servicios `llm_*.py` y los 3 nodos LangGraph.
- **RF-06 (Desacoplamiento HTTP, Cachés y Helpers UI en Frontend PC)**:
  - Modularizar `src/frontend/api_client.py` en `src/frontend/api/` manteniendo `api_client.py` como fachada pública compatible, con `_request()` único, invalidaciones reactivas completas, eliminación de fallos silenciosos (`except Exception: pass`) y normalización única en frontera.
  - Centralizar formateo `DD/MM/AAAA` (`utils/formatting.py`) corrigiendo todas las salidas ISO residuales, y extraer componentes UI reutilizables (`components/ui_cards.py`) estandarizando `width="stretch"`.
- **RF-07 (Eliminación de Cálculos Financieros en Streamlit y Modularización de Vistas PC)**:
  - Dividir `src/frontend/app.py` y `src/frontend/views/joint_view.py` en vistas especializadas por dominio, eliminando `importlib.reload(_jv_mod)`, imports privados y cálculos contables en UI (tasas, desviaciones, dobles bucles `pval + rval_trans`, repartos y heurísticas fallback).
  - Retirar `qrcodegen.py`, helpers QR de `mobile_view.py`, reglas CSS huérfanas y variables/imports sin uso.
- **RF-08 (Modularización y Consistencia Offline/Online en Móvil)**:
  - Centralizar clasificación/emojis (`utils/categories.ts`) y formateo/red (`utils/formatters.ts`), dividir `storage.ts` y `App.tsx`, unificar el store reactivo de resúmenes mensuales, endurecer `api.ts` (manejo `401`/`403`, parsing de `422`, timeouts y logs), deduplicar `SearchView`, extraer `ReceiptViewerModal` y unificar el origen de versión desde `package.json`.

---

## 4. Requerimientos No Funcionales (RNF)

- **RNF-01 (Cero Regresiones)**: Cada fase debe ejecutarse secuencialmente con puerta de confirmación explícita y superar el 100% de su batería acotada de pruebas y comprobación sintáctica (`compileall`, `tsc --noEmit`, `vite build`, `vite build --mode pwa`).
- **RNF-02 (Observabilidad y Privacidad)**: Ningún bloque `catch`/`except` puede silenciar excepciones sin `logging` estructurado ni exponer claves/tokens (Principios 10 y 13).
- **RNF-03 (Paridad de Dependencias)**: Sin añadir dependencias externas salvo necesidad justificada y registrada en `requirements/` o `package.json` (Principio 14).
