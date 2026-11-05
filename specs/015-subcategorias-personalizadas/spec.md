# Especificación 015: Creación y Gestión de Subcategorías Personalizadas desde la Interfaz

## 1. Resumen Ejecutivo y Visión

Actualmente, las categorías contables (Ingresos Netos, Necesidades Básicas 50%, Deseos 30%, Ahorro e Inversión 20%) y sus respectivas subcategorías vienen predeterminadas por el sembrado inicial en SQLite (`init_db_data.py`). Si un usuario necesita clasificar gastos o presupuestos en conceptos no contemplados en la plantilla original (ej. *'Pádel'*, *'Mascotas'*, *'Suscripciones de Software'*, *'Material Escolar'* o *'Mantenimiento de Vehículo'*), se encuentra técnicamente bloqueado al no existir una interfaz gráfica para crearlas, editarlas o administrarlas.

El objetivo de la **Especificación 015** es proporcionar una herramienta integral para la **creación, edición y administración segura de subcategorías personalizadas**, tanto en la **Cuenta Personal** como en la **Economía del Hogar (Cuenta Conjunta)**:

1. **Gestión Desacoplada e Intuitiva**:
   - En la Cuenta Personal (`⚙️ Ajustes y Sistema` -> `📝 Presupuesto Base y Fondo de Emergencia`), incorporar un expander dedicado `🏷️ Administrar Subcategorías Personalizadas` con alta rápida y catálogo visual editable.
   - En la Cuenta Conjunta (`👥 Economía del Hogar` -> `⚙️ Configuración`), incorporar un expander equivalente `🏷️ Administrar Subcategorías del Hogar` con sincronización automática entre miembros.
2. **Protección Patrimonial e Integridad Referencial**:
   - Bloqueo estricto de eliminación física cuando una subcategoría ya posee transacciones o presupuestos históricos vinculados, protegiendo las reglas contables 50/30/20 y la integridad en SQLite (`FOREIGN KEY constraint`).
   - Soporte para renombrar subcategorías en cualquier momento preservando todos los registros asociados.
3. **Idempotencia y Blindaje ante Actualizaciones OTA (Spec 012)**:
   - El sembrado de base de datos (`init_db_data.py`) se transforma en un mecanismo idempotente (`get_or_create`), impidiendo colisiones de IDs autoincrementales o pérdidas de datos ante actualizaciones de versión.
4. **Coherencia con la Sincronización P2P (Syncthing - Spec 010)**:
   - Toda creación, modificación o eliminación de subcategorías del hogar emite eventos delta `SUBCATEGORY UPSERT/DELETE`, asegurando la replicación en el nodo de la pareja.
5. **Máximo Rendimiento y Caching Reactivo (Spec 014)**:
   - Reutilización de sockets HTTP Keep-Alive e invalidación quirúrgica de caché (`clear_categories_cache()`, `clear_annual_cache()`, `clear_joint_cache()`), garantizando que los desplegables de gastos mensuales reflejen los cambios inmediatamente sin llamadas de red redundantes.

---

## 2. Historias de Usuario (HU)

- **HU-1 (Personalización del Presupuesto Personal)**: Como usuario que organiza sus finanzas bajo la regla 50/30/20, quiero dar de alta nuevas subcategorías (ej. *'Pádel'* en Deseos o *'Veterinario'* en Necesidades) para reflejar fielmente mis hábitos de gasto cotidianos.
- **HU-2 (Asignación Automática al Presupuesto Base)**: Al crear una subcategoría, quiero poder definir opcionalmente su dotación base inicial (€) para que todos los meses futuros adopten ese presupuesto por defecto sin tener que configurarlo mes a mes.
- **HU-3 (Edición de Nombres sin Pérdida Histórica)**: Como usuario, quiero poder corregir erratas o renombrar subcategorías existentes manteniendo intacto todo su historial de transacciones pasadas y métricas anuales.
- **HU-4 (Eliminación Segura con Protección Contable)**: Como usuario, quiero poder eliminar subcategorías creadas por error que no tienen uso; pero si ya tienen gastos o presupuestos históricos, quiero que el sistema me informe con claridad y bloquee el borrado accidental para proteger la contabilidad.
- **HU-5 (Subcategorías del Hogar Sincronizadas)**: Como pareja que gestiona los gastos comunes, queremos dar de alta subcategorías específicas del hogar (ej. *'Colegio Niños'*, *'Jardinería'*) y que se repliquen automáticamente en el ordenador de la pareja mediante Syncthing.
- **HU-6 (Actualizaciones sin Pérdida de Datos)**: Como usuario que actualiza la aplicación mediante el actualizador OTA en 1 clic, quiero tener la certeza absoluta de que mis subcategorías personalizadas jamás desaparecerán ni entrarán en conflicto con versiones futuras.

---

## 3. Requerimientos Funcionales (RF)

### 3.1 Capa de Datos y Backend (Fase 1)

- **RF-1 (CRUD y Auditoría de Uso en SQLiteRepository)**:
  - En `src/backend/database/componentes/sqlite_crud.py`:
    - `update_subcategory(subcategory_id: int, name: str) -> Subcategory`: Renombra la subcategoría validando que el nombre no esté vacío.
    - `check_subcategory_usage(subcategory_id: int) -> dict`: Consulta y devuelve `{"transactions_count": int, "budgets_count": int, "can_delete": bool}`.
    - `delete_subcategory(subcategory_id: int) -> bool`: Comprueba el uso mediante `check_subcategory_usage()`. Si tiene transacciones o presupuestos vinculados, rechaza el borrado lanzando una excepción informativa; si no tiene dependencias, ejecuta `db.delete()` y `db.commit()`.
- **RF-2 (Endpoints REST de Subcategorías Personales)**:
  - En `src/backend/api/routers/categories.py`:
    - `GET /categories/subcategories/{subcategory_id}/usage`: Devuelve el conteo de registros vinculados.
    - `PUT /categories/subcategories/{subcategory_id}`: Recibe `SubcategoryUpdate(name=str)` y actualiza el registro.
    - `DELETE /categories/subcategories/{subcategory_id}`: Ejecuta la eliminación segura; si tiene registros vinculados, responde con código `HTTP 409 Conflict` y detalle de uso.
- **RF-3 (Auditoría de Uso y Protección en Subcategorías Conjuntas)**:
  - En `src/backend/database/componentes/sqlite_crud.py` y `src/backend/api/routers/joint.py`:
    - `check_joint_subcategory_usage(joint_subcategory_id: int) -> dict`: Verifica si existen transacciones en `JointTransaction`.
    - `GET /joint/subcategories/{subcategory_id}/usage`: Endpoint de comprobación previa.
    - `DELETE /joint/subcategories/{subcategory_id}`: Bloquea con `HTTP 409 Conflict` si existen gastos comunes registrados bajo dicha subcategoría; en caso contrario emite el delta `SyncEntityType.SUBCATEGORY` con `SyncAction.DELETE`.
- **RF-4 (Sembrado Idempotente y Blindaje OTA)**:
  - En `src/backend/init_db_data.py`:
    - Refactorizar `populate()` para implementar búsqueda y creación idempotente (`get_or_create`) por nombre normalizado para categorías y subcategorías estándar.
    - Prohibido asumir IDs primarios fijos; las subcategorías personalizadas creadas por el usuario conviven con cualquier nuevo concepto oficial sin colisiones.

### 3.2 Cliente Frontend y Estrategia de Caching (Fase 2)

- **RF-5 (Métodos de Cliente e Invalidación de Caché en `api_client.py`)**:
  - Implementar en `src/frontend/api_client.py`:
    - `create_subcategory(category_id: int, name: str) -> Optional[dict]` -> Dispara `clear_categories_cache()` y `clear_annual_cache()`.
    - `update_subcategory(subcategory_id: int, name: str) -> Optional[dict]` -> Dispara `clear_categories_cache()` y `clear_annual_cache()`.
    - `delete_subcategory(subcategory_id: int) -> tuple[bool, str]` -> Dispara `clear_categories_cache()` y `clear_annual_cache()`.
    - `get_subcategory_usage(subcategory_id: int) -> Optional[dict]`.
    - `create_joint_subcategory(name: str, joint_category_id: int) -> Optional[dict]` -> Dispara `clear_joint_cache()`.
    - `update_joint_subcategory(subcategory_id: int, name: str) -> Optional[dict]` -> Dispara `clear_joint_cache()`.
    - `delete_joint_subcategory(subcategory_id: int) -> tuple[bool, str]` -> Dispara `clear_joint_cache()`.
    - `get_joint_subcategory_usage(subcategory_id: int) -> Optional[dict]`.

### 3.3 Presentación e Integración de Usuario en Streamlit (Fase 3)

- **RF-6 (Panel de Subcategorías en la Cuenta Personal)**:
  - En `src/frontend/app.py` (`⚙️ Ajustes y Sistema` -> `📝 Presupuesto Base y Fondo de Emergencia`):
    - Ubicar un expander `🏷️ Administrar Subcategorías Personalizadas` (cerrado por defecto) antes del formulario de importes.
    - **Formulario de Alta**:
      - Campo de texto: *Nombre de la subcategoría*.
      - Selector de categoría padre: *Ingresos Netos*, *Necesidades Básicas (50%)*, *Deseos (30%)*, *Ahorro e Inversión (20%)*.
      - Importe base opcional (€) para asignarlo automáticamente a la plantilla `BASE`.
      - Botón `[➕ Crear Subcategoría]`.
    - **Catálogo y Administración**:
      - Visualización agrupada por categoría con badges de color consistentes.
      - Opción de renombrar in situ.
      - Botón de eliminación protegido con diálogo/popover de confirmación. Si el endpoint devuelve conflicto (409), muestra advertencia detallando las transacciones o meses de presupuesto que dependen de ella.
- **RF-7 (Panel de Subcategorías en la Cuenta Conjunta)**:
  - En `src/frontend/views/joint_view.py` (`👥 Economía del Hogar` -> `⚙️ Configuración`):
    - Ubicar un expander `🏷️ Administrar Subcategorías del Hogar` inmediatamente antes de los parámetros generales de la cuenta.
    - Alta rápida vinculada a las categorías de gastos comunes.
    - Gestión de renombrado y borrado seguro con confirmación y replicación Syncthing.
- **RF-8 (Propagación Inmediata a la Navegación y Formularios)**:
  - Las nuevas subcategorías creadas deben reflejarse de inmediato en los selectores de gasto de `📅 Gestión Mensual`, en el formulario de gastos comunes y en las tablas matriciales de presupuesto sin requerir reinicios del backend ni recargas manuales forzadas.

---

## 4. Requerimientos No Funcionales y Restricciones Técnicas

1. **Rendimiento y Sockets (Spec 014)**: Todas las operaciones consumen el singleton `_session = requests.Session()` y Keep-Alive. Cero llamadas HTTP redundantes.
2. **Convención de Idioma (AGENTS.md Directriz 7)**:
   - Código backend, modelos SQLAlchemy, esquemas Pydantic y endpoints de API 100% en inglés (`Category`, `Subcategory`, `JointSubcategory`, `category_id`, `/categories/subcategories/`).
   - Interfaz de usuario, etiquetas y mensajes de error 100% en español.
3. **Formato de Fechas (AGENTS.md Directriz 12)**: Toda visualización de fechas en el catálogo o advertencias en formato español `DD/MM/AAAA`.
4. **Privacidad (Constitución Principios 10 y 11)**: Ningún dato de categorías o transacciones se comparte con servicios externos o LLMs.

