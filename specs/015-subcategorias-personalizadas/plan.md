# Plan de Desarrollo: Especificación 015 — Creación y Gestión de Subcategorías Personalizadas

## 1. Arquitectura y Estrategia de Ejecución

Siguiendo las directrices de `docs/constitution.md` y `AGENTS.md`, la especificación se desarrollará de forma estrictamente secuencial en **3 fases**. Cada fase se verificará con pruebas automatizadas completas antes de solicitar confirmación al usuario para avanzar a la siguiente.

```
Rama de trabajo: feat/spec-015-subcategorias-personalizadas
Fase 1: Capa Backend y API REST de Subcategorías (Personal y Hogar)
Fase 2: Métodos de Cliente y Caching en Frontend (api_client.py)
Fase 3: Interfaz de Usuario en Streamlit (app.py y joint_view.py)
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

---

## 3. Plan de Verificación

```powershell
# Fase 1
.\venv\Scripts\pytest -v tests/unit/test_categories_crud.py tests/integration/test_categories_api.py

# Fase 2
.\venv\Scripts\pytest -v tests/unit/test_categories_client.py

# Fase 3 y suite completa de la spec
.\venv\Scripts\pytest -v tests/unit/test_categories_crud.py tests/integration/test_categories_api.py tests/unit/test_categories_client.py tests/unit/test_personal_ux_frontend.py tests/unit/test_joint_ux_frontend.py
```

