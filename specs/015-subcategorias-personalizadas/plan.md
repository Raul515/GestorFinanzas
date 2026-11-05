# Plan de Desarrollo: Especificación 015 — Creación y Gestión de Subcategorías Personalizadas

## 1. Arquitectura y Estrategia de Ejecución

Siguiendo las directrices de `docs/constitution.md` y `AGENTS.md`, la especificación se desarrollará de forma estrictamente secuencial en **5 fases**. Cada fase se verificará con pruebas automatizadas completas antes de solicitar confirmación al usuario para avanzar a la siguiente.

```
Rama de trabajo: feat/spec-015-subcategorias-personalizadas
Fase 1: Capa Backend y API REST de Subcategorías (Personal y Hogar)
Fase 2: Métodos de Cliente y Caching en Frontend (api_client.py)
Fase 3: Interfaz de Usuario en Streamlit (app.py y joint_view.py)
Fase 4: Robustecimiento, Corrección de Errores de UI y Resiliencia Concurrente P2P
Fase 5: Mejoras de Usabilidad, Propagación Temporal Acotada y Perfeccionamiento de Huchas y Cuotas
Fusión final: Merge en develop tras 100% de tests
```

---

## 2. Desglose de Fases

### Fase 1: Capa Backend y API REST de Subcategorías (Personal y Hogar)
- **Objetivo**: Desarrollar la lógica de persistencia, auditoría de dependencias, protección referencial y endpoints REST tanto en el perfil personal como en el hogar.
- **Entregables**:
  1. `src/backend/domain/schemas/categories.py`:
     - Esquema `SubcategoryUpdate(name=str)`.
     - Esquema `SubcategoryUsage(transactions_count=int, budgets_count=int, can_delete=bool)`.
  2. `src/backend/database/componentes/sqlite_crud.py`:
     - `update_subcategory(subcategory_id: int, name: str) -> Subcategory`.
     - `check_subcategory_usage(subcategory_id: int) -> dict`.
     - `delete_subcategory(subcategory_id: int) -> bool` (bloquea con error si `can_delete=False`).
     - `check_joint_subcategory_usage(joint_subcategory_id: int) -> dict`.
  3. `src/backend/api/routers/categories.py`:
     - `PUT /categories/subcategories/{subcategory_id}`.
     - `DELETE /categories/subcategories/{subcategory_id}` (retorna HTTP 409 si tiene dependencias).
     - `GET /categories/subcategories/{subcategory_id}/usage`.
  4. `src/backend/api/routers/joint.py`:
     - `GET /joint/subcategories/{subcategory_id}/usage`.
     - Protección en `DELETE /joint/subcategories/{subcategory_id}` con verificación de uso y HTTP 409.
  5. `src/backend/init_db_data.py`:
     - Refactorización a `get_or_create` idempotente para blindaje ante actualizaciones OTA.
  6. Pruebas: Batería de pruebas unitarias y de integración en `tests/unit/test_categories_crud.py` y `tests/integration/test_categories_api.py`.

### Fase 2: Métodos de Cliente y Caching en Frontend (`api_client.py`)
- **Objetivo**: Conectar el frontend con los endpoints del backend, asegurando Keep-Alive e invalidación de caché reactiva en RAM.
- **Entregables**:
  1. `src/frontend/api_client.py`:
     - Métodos personales: `create_subcategory`, `update_subcategory`, `delete_subcategory`, `get_subcategory_usage`.
     - Métodos del hogar: `create_joint_subcategory`, `update_joint_subcategory`, `delete_joint_subcategory`, `get_joint_subcategory_usage`.
     - Invalidación de caché: `clear_categories_cache()`, `clear_annual_cache()`, `clear_joint_cache()`.
  2. Pruebas unitarias en `tests/unit/test_categories_client.py`.

### Fase 3: Interfaz de Usuario en Streamlit (app.py y joint_view.py)
- **Objetivo**: Renderizar los componentes visuales para administrar las subcategorías con feedback inmediato al usuario.
- **Entregables**:
  1. `src/frontend/app.py`:
     - Expander `🏷️ Administrar Subcategorías Personalizadas` en `⚙️ Ajustes y Sistema` -> `📝 Presupuesto Base y Fondo de Emergencia`.
     - Formulario de alta rápida con asignación de presupuesto base inicial opcional.
     - Catálogo visual por categorías con acciones de renombrar y borrar con confirmación.
  2. `src/frontend/views/joint_view.py`:
     - Expander `🏷️ Administrar Subcategorías del Hogar` en `👥 Economía del Hogar` -> `⚙️ Configuración`.
     - Formulario de alta para necesidades comunes y listado con acciones protegidas.
  3. Pruebas de interfaz y no regresión: `tests/unit/test_personal_ux_frontend.py` y `tests/unit/test_joint_ux_frontend.py`.

### Fase 4: Robustecimiento, Corrección de Errores de UI, Protección de Conceptos Base y Resiliencia P2P
- **Objetivo**: Corregir errores de ciclo de vida de widgets de Streamlit, reordenar los expanders de configuración, proteger subcategorías base, permitir borrado con presupuestos huérfanos y blindar la concurrencia asíncrona de Syncthing.
- **Entregables**:
  1. `src/frontend/app.py`:
     - **Reordenación de expanders**: `⚙️ Formulario de Configuración del Presupuesto Base` colocado arriba; frase explicativa intermedia; y `🏷️ Administrar Subcategorías Personalizadas` situado debajo.
     - **Persistencia de categoría seleccionada**: Preservación del índice de la categoría principal seleccionada tras guardar mediante `st.session_state["last_selected_personal_cat_id"]`.
     - **Formularios limpios**: Sustitución de manipulación directa de `st.session_state` por `st.form("form_alta_subcat_personal", clear_on_submit=True)` eliminando `StreamlitWidgetAlreadyInstantiatedError`.
     - **Protección visual de subcategorías base**: Las subcategorías oficiales del sistema no muestran botón ni popover de renombrar ni de borrar. Solo las añadidas por el usuario son editables y eliminables.
  2. `src/frontend/views/joint_view.py`:
     - **Anidación del catálogo**: Anidación completa de las subcategorías registradas dentro del expander `🏷️ Administrar Subcategorías del Hogar`.
     - **Protección de subcategorías base del hogar**: No se permite borrar conceptos base ni renombrarlos (solo modificar su presupuesto mensual estimado).
     - Formulario nativo `st.form("form_alta_subcat_hogar", clear_on_submit=True)`.
     - Exclusión total del bloque en fase Pre-Convivencia (`PRE_COHABITATION`).
  3. `src/backend/database/componentes/sqlite_crud.py` y Routers REST:
     - Constantes oficiales `DEFAULT_PERSONAL_SUBCATEGORIES` y `DEFAULT_JOINT_SUBCATEGORIES` en `src/backend/domain/constants.py`.
     - Bloqueo en backend (`HTTP 409 Conflict` / `HTTP 400 Bad Request`) si se intenta renombrar o eliminar cualquier subcategoría base.
     - **Flexibilidad de borrado con presupuestos**: Eliminación permitida si `transactions_count == 0`, eliminando en cascada los registros huérfanos de `MonthlyBudget`.
  4. `src/backend/services/joint_sync_service.py` (Alternativa B - Resurrección y Veto Automático):
     - **Veto en recepción de borrado**: Si llega un delta `DELETE SUBCATEGORY` pero en el nodo local existen transacciones vinculadas, se veta e ignora el borrado, re-emitiendo un evento `UPSERT`.
     - **Resurrección automática ante transacciones huérfanas**: Si llega una transacción remota para una subcategoría eliminada localmente, se recrea automáticamente bajo su categoría para que la transacción no quede huérfana.
  5. Pruebas automatizadas: Suite ampliada a 67 pruebas pasando al 100% sin regresiones.

### Fase 5: Mejoras de Usabilidad, Propagación Temporal Acotada y Perfeccionamiento de Huchas y Cuotas
- **Objetivo**: Implementar las 6 mejoras y correcciones identificadas en pruebas reales del usuario respecto a propagación temporal de presupuestos, auto-ocultación de avisos de cuota 0,00 €, vaciado de formularios de huchas, tratamiento visual y contable de metas cumplidas y blindaje de transferencias.
- **Entregables**:
  1. `src/backend/services/joint_accounting_service.py`:
     - Exclusión dinámica de cuota mensual sugerida en huchas de amortización completadas (`current_balance >= target_amount`), fijando su aporte a `sinking_funds_target` en 0,00 € y su asignación en `fund_allocations` en 0,00 €.
  2. `src/backend/api/routers/joint.py`:
     - Paso de `current_balance` y `target_amount` en diccionarios para el servicio contable en `GET /joint/contribution-calculation` y `POST /joint/contributions/asentar-asistida`.
     - Validación preventiva en `POST /joint/sinking-funds/transfer`: rechazo con `HTTP 400 Bad Request` si `source_fund_id == target_fund_id`.
  3. `src/frontend/app.py`:
     - Incorporación del selector `"A partir de (AAAA)"` con los 12 meses de serie, seleccionando por defecto el mes del reloj natural del sistema (`date.today().month - 1`).
     - Propagación acotada del presupuesto inicial: se guarda en `BASE`, se asigna a los meses activos y posteriores del año natural, y se fijan explícitamente en `0,00 €` los meses anteriores para blindar el histórico contable.
     - Envío consolidado en un único lote atómico mediante `api_client.save_presupuestos_bulk`.
  4. `src/frontend/views/joint_view.py`:
     - Auto-ocultación del banner de aportación asistida en perfil personal cuando la cuota requerida es 0,00 € (o si `target_local <= 0.0` y `target_remote <= 0.0`).
     - Vaciado automático de todos los campos al dar de alta una hucha de amortización mediante `clear_on_submit=True` en `st.form("create_sinking_fund_form", clear_on_submit=True)`.
     - Visualización distintiva de huchas completadas: badge `[✅ Completada]`, barra de progreso en verde esmeralda (`#10b981`) y texto de meta cumplida.
     - Bloqueo en la UI para impedir seleccionar la misma hucha en origen y destino en traspasos de saldo.
  5. Batería de pruebas automatizadas:
     - `test_completed_sinking_fund_excluded_from_contributions` y `test_transfer_sinking_fund_same_source_and_target_rejected` en `tests/unit/test_joint_accounting_service.py`.
     - `test_app_py_subcategory_start_month_and_budget_propagation` en `tests/unit/test_personal_ux_frontend.py`.

---

## 3. Plan de Verificación

```powershell
# Fase 1
.\venv\Scripts\pytest -v tests/unit/test_categories_crud.py tests/integration/test_categories_api.py

# Fase 2
.\venv\Scripts\pytest -v tests/unit/test_categories_client.py

# Fase 3
.\venv\Scripts\pytest -v tests/unit/test_personal_ux_frontend.py tests/unit/test_joint_ux_frontend.py

# Fase 4 y suite consolidada de subcategorías
.\venv\Scripts\pytest -v tests/unit/test_categories_crud.py tests/integration/test_categories_api.py tests/unit/test_categories_client.py tests/unit/test_personal_ux_frontend.py tests/unit/test_joint_ux_frontend.py tests/unit/test_joint_sync_service.py

# Fase 5 y suite contable ampliada
.\venv\Scripts\pytest -v tests/unit/test_joint_accounting_service.py tests/unit/test_personal_ux_frontend.py
```
