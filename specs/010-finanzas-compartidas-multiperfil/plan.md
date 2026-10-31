# Plan de Implementación: Especificación 010 — Arquitectura Multi-Perfil para Parejas y Finanzas Compartidas (Privacidad Real y Cuenta Conjunta Sincronizada)

Este plan técnico desglosa la implementación de la **Especificación 010** en **6 fases secuenciales estrictas**. Siguiendo la metodología SDD (*Spec-Anchored*) y las directrices de [AGENTS.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/AGENTS.md), cada fase requiere el 100% de sus pruebas automatizadas pasando y la confirmación explícita del usuario antes de avanzar a la siguiente.

---

### Fase 1: Modelos de Dominio SQLAlchemy 2.0 y Esquemas Pydantic v2 para el Espacio Conjunto

- **Objetivo**: Desarrollar los modelos ORM de persistencia local en `finanzas.db` y los contratos fuertemente tipados Pydantic v2 para la Cuenta Conjunta, Huchas de Amortización, aportaciones mensuales y metadatos de sincronización.
- **Archivos a crear/modificar**:
  - `src/backend/domain/models/joint.py` [NUEVO: Modelos declarativos SQLAlchemy 2.0 `JointAccount`, `JointCategory`, `JointSubcategory`, `JointSinkingFund`, `JointTransaction`, `JointMonthlyContribution`].
  - `src/backend/domain/models/__init__.py` [MODIFICADO: Exportación de las nuevas entidades].
  - `src/backend/domain/schemas/joint.py` [NUEVO: Enumeraciones `CohabitationStage`, `ContributionStrategy`, `SplitMode`, `SyncAction`, `SyncEntityType` y esquemas Pydantic v2 para request/response de todas las entidades conjuntas].
  - `tests/unit/test_joint_models_and_schemas.py` [NUEVO: Suite unitaria con verificación de claves foráneas, restricciones de no-negatividad, validaciones de Pydantic y mapeo tipado].
- **Casos de Prueba a Verificar**:
  - Validación de campos obligatorios y tipos en `JointAccount` (etapa de convivencia, estrategia y ratios de referencia).
  - Integridad referencial de `JointTransaction` hacia `JointSubcategory` o `JointSinkingFund`.
  - Esquema de evento delta `SyncEventPayload` con validación de UUIDv4 y formato ISO-8601 UTC.
  - Validación de que `allocation_percentage` en huchas sea $\ge 0$ y $\le 100$.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_models_and_schemas.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias de la fase pasando con 0 errores y 0 advertencias de Pyright.

---

### Fase 2: Motor Contable Desacoplado de la Cuenta Conjunta y Diagnóstico de Salud Familiar

- **Objetivo**: Implementar el servicio puro de lógica contable para el cálculo y distribución de aportaciones bajo ambas estrategias (Plantilla Nominal vs Porcentaje de Ingresos), gestión de huchas de amortización, semáforo de esfuerzo familiar y asiento atómico en el perfil personal.
- **Archivos a crear/modificar**:
  - `src/backend/services/joint_accounting_service.py` [NUEVO: Funciones puras de cálculo de cuotas de aportación, reparto porcentual en huchas, auditoría de Tasa de Esfuerzo Familiar, y generación atómica de transacciones de salida personal / entrada conjunta].
  - `src/backend/domain/repositories/` [MODIFICADO: Métodos CRUD de repositorio SQLite para el espacio conjunto en `sqlite_crud.py` o repositorio dedicado].
  - `tests/unit/test_joint_accounting_service.py` [NUEVO: Pruebas unitarias de cálculo con números reales mockeados para 50/50, proporcional y personalizado, tanto en Pre-Convivencia como en Convivencia Plena].
- **Casos de Prueba a Verificar**:
  - Cálculo exacto en Estrategia A (Plantilla Nominal): suma de huchas fijas en Pre-Convivencia y suma de Necesidades + Huchas en Convivencia Plena.
  - Cálculo exacto en Estrategia B (Porcentaje de Ingresos): recaudación combinada y distribución porcentual exacta entre las Huchas de Amortización según `allocation_percentage`.
  - Imputación contable limpia en el perfil personal: salida clasificada como Necesidades (o Ahorro en Pre-Convivencia si se configuró así) sin generar ingresos ficticios.
  - Clasificación correcta del Semáforo de Tasa de Esfuerzo (Verde <50%, Amarillo 50-60%, Rojo >60%).
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_accounting_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando antes de avanzar a la Fase 3.

---

### Fase 3: Motor de Sincronización Asíncrona Desacoplada (Event Sourcing Inbox/Outbox para Syncthing)

- **Objetivo**: Desarrollar el servicio desacoplado de sincronización basado exclusivamente en lectura y escritura de ficheros JSON en disco local (`sync/outbox/` e `sync/inbox/`), garantizando resiliencia ante desconexiones, idempotencia por UUID y resolución determinista de conflictos LWW.
- **Archivos a crear/modificar**:
  - `src/backend/services/joint_sync_service.py` [NUEVO: Emisión de eventos atómicos a `sync/outbox/`, escaneo y procesamiento secuencial de `sync/inbox/`, registro de eventos aplicados para idempotencia, resolución LWW por `timestamp_utc` y emisión de *tombstones* de borrado].
  - `.gitignore` [MODIFICADO: Asegurar que el directorio local `sync/` quede estrictamente excluido del control de versiones (Principio 11)].
  - `tests/unit/test_joint_sync_service.py` [NUEVO: Suite unitaria simulando escritura de outbox, lectura de inbox con fixtures JSON temporales, descartado de duplicados y resolución de conflictos].
- **Casos de Prueba a Verificar**:
  - Emisión correcta de evento `UPSERT` y `DELETE` (*tombstone*) en fichero JSON atómico.
  - Idempotencia: un mismo evento JSON procesado dos veces consecutivas no duplica importes ni altera el saldo de tesorería.
  - Resolución LWW: entre dos eventos con el mismo `uuid` y timestamps distintos, siempre prevalece el de mayor `timestamp_utc`.
  - Aislamiento absoluto: certificar que ningún evento contiene datos de transacciones privadas o categorías personales.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_sync_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando antes de avanzar a la Fase 4.

---

### Fase 4: Endpoints REST en FastAPI con Observabilidad Estructurada

- **Objetivo**: Exponer las capacidades de la Cuenta Conjunta mediante un router REST fuertemente tipado en FastAPI, con middleware de observabilidad, validación Pydantic v2 y control de transacciones atómicas de base de datos.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/joint.py` [NUEVO: Endpoints REST para configuración del hogar, huchas de amortización, aportaciones mensuales, transacciones conjuntas, diagnóstico de salud y triggers de sincronización].
  - `src/backend/main.py` [MODIFICADO: Registro del router `/joint`].
  - `tests/integration/test_joint_api.py` [NUEVO: Pruebas de integración HTTP con SQLite en memoria y cliente `TestClient`].
- **Endpoints a Implementar**:
  - `GET /joint/account` y `PUT /joint/account`: Consulta y actualización de configuración del hogar (etapa, estrategia, porcentajes, ingresos de referencia).
  - `GET /joint/sinking-funds` y `POST /joint/sinking-funds`: Catálogo y alta de Huchas de Amortización.
  - `PUT /joint/sinking-funds/{fund_id}` y `DELETE /joint/sinking-funds/{fund_id}`: Edición y liquidación segura con reasignación de saldo.
  - `POST /joint/contributions/asentar-asistida`: Ejecución atómica del asiento mensual asistido (crea gasto personal, ingreso común y delta en outbox).
  - `GET /joint/transactions` y `POST /joint/transactions`: Listado y registro de gastos del hogar o compras desde huchas.
  - `DELETE /joint/transactions/{transaction_id}`: Eliminación de gasto conjunto con emisión de *tombstone*.
  - `GET /joint/health`: Retorno del semáforo y métricas de Tasa de Esfuerzo Familiar.
  - `POST /joint/sync/process-inbox`: Ejecución manual o programada del escaneo de la bandeja de entrada de deltas.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_joint_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando con códigos de estado HTTP correctos (200, 201, 400, 404).

---

### Fase 5: Integración en Frontend Streamlit (Vistas de Economía del Hogar y Flujo Asistido)

- **Objetivo**: Implementar la capa de presentación interactiva en Streamlit: selector de contexto en la barra lateral (Perfil Personal vs Cuenta Conjunta), banner asistido de aportación en 1 clic el día 1, panel de Huchas de Amortización con barras de progreso, formulario de gastos del hogar y visualización del semáforo de esfuerzo.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos clientes con observabilidad estructurada y sanitización de logs para todos los endpoints `/joint/*`].
  - `src/frontend/views/joint_view.py` [NUEVO: Componentes visuales desacoplados para la Cuenta Conjunta: asistente de configuración, tarjetas de huchas con barras de progreso Altair/Streamlit, diálogo de modificación de aportación, semáforo de salud y formulario sin categorías de ocio].
  - `src/frontend/app.py` [MODIFICADO: Selector de contexto en `st.sidebar`, inyección del banner de aportación asistida en el perfil personal y renderizado condicional de la vista conjunta].
  - `tests/unit/test_joint_frontend.py` [NUEVO: Pruebas unitarias del cliente API y utilidades de presentación].
- **Casos de Prueba a Verificar**:
  - Visualización del selector de contexto y conmutación limpia entre "Mi Perfil Personal" y "Economía del Hogar".
  - Funcionamiento del banner de inicio de mes: clic en `[⚡ Asentar Aportación]` y modal emergente de `[✏️ Modificar Importe]`.
  - Ocultamiento de facturas y necesidades en modo Pre-Convivencia; activación de campos en modo Convivencia Plena.
  - Renderizado fiel de las barras de progreso de las Huchas de Amortización y del semáforo de salud familiar.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_frontend.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de frontend pasando sin errores de renderizado ni advertencias.

---

### Fase 6: Pruebas Integrales E2E, Guía de Syncthing y Consolidación de Memoria

- **Objetivo**: Ejecutar una batería completa de pruebas end-to-end simulando la interacción entre dos dispositivos aislados (PC Windows y Mac), redactar la guía visual de emparejamiento con Syncthing, consolidar la memoria arquitectónica en `MEMORY.md` y preparar la fusión a `develop`.
- **Archivos a crear/modificar**:
  - `tests/integration/test_joint_e2e_flow.py` [NUEVO: Prueba end-to-end simulando: 1) Configuración inicial de pareja en PC y Mac; 2) Asiento asistido de aportación; 3) Intercambio de deltas JSON; 4) Ingesta en el segundo equipo; 5) Liquidación de gasto de hucha; 6) Verificación de saldos idénticos en ambos lados].
  - `docs/guia_sincronizacion_syncthing.md` [NUEVO: Guía clara y paso a paso para instalar y emparejar Syncthing entre Windows y macOS mediante Device ID en 3 minutos].
  - `MEMORY.md` [MODIFICADO: Registrar decisiones técnicas, cierre formal de Spec 010 y actualización del mapa de arquitectura].
  - `specs/README.md` [MODIFICADO: Actualizar índice de especificaciones con Spec 010 Completada].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_* tests/integration/test_joint_*
  ```
- **Criterio de Aceptación**: 100% de todas las pruebas de la especificación pasando, cero advertencias en `compileall` y verificación activa de `.gitignore`.
