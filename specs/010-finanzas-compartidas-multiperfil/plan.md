# Plan de Implementación: Especificación 010 — Arquitectura Multi-Perfil para Parejas y Finanzas Compartidas (Privacidad Real y Cuenta Conjunta Sincronizada)

Este plan técnico desglosa la implementación de la **Especificación 010** en **6 fases secuenciales estrictas**. Siguiendo la metodología SDD (*Spec-Anchored*) y las directrices de [AGENTS.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/AGENTS.md), cada fase requiere el 100% de sus pruebas automatizadas pasando y la confirmación explícita del usuario antes de avanzar a la siguiente.

---

### Fase 1: Modelos de Dominio SQLAlchemy 2.0 y Esquemas Pydantic v2 para el Espacio Conjunto

- **Objetivo**: Desarrollar los modelos ORM de persistencia local en `finanzas.db` y los contratos fuertemente tipados Pydantic v2 para la Cuenta Conjunta (restricción Singleton Household), Huchas de Amortización, aportaciones mensuales, esquema de Onboarding Inicial y metadatos de sincronización.
- **Archivos a crear/modificar**:
  - `src/backend/domain/models/joint.py` [NUEVO: Modelos declarativos SQLAlchemy 2.0 `JointAccount`, `JointCategory`, `JointSubcategory`, `JointSinkingFund`, `JointTransaction`, `JointMonthlyContribution`].
  - `src/backend/domain/models/__init__.py` [MODIFICADO: Exportación de las nuevas entidades].
  - `src/backend/domain/schemas/joint.py` [NUEVO: Enumeraciones `CohabitationStage`, `ContributionStrategy`, `SplitMode`, `SyncAction`, `SyncEntityType`, esquemas Pydantic v2 de setup/onboarding `JointAccountSetupRequest`, respuesta de estado `JointStatusResponse`, resumen anual `JointAnnualSummaryResponse` y request/response de todas las entidades conjuntas].
  - `tests/unit/test_joint_models_and_schemas.py` [NUEVO: Suite unitaria con verificación de claves foráneas, restricciones de no-negatividad, unicidad de cuenta conjunta (singleton), validaciones de Pydantic y mapeo tipado].
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

- **Objetivo**: Implementar el servicio puro de lógica contable para el cálculo y distribución de aportaciones bajo ambas estrategias (Plantilla Nominal vs Porcentaje de Ingresos), gestión de huchas de amortización, semáforo de esfuerzo familiar, asiento atómico en el perfil personal y cálculo de métricas anuales del hogar (sin desglose individual A vs B).
- **Archivos a crear/modificar**:
  - `src/backend/services/joint_accounting_service.py` [NUEVO: Funciones puras de cálculo de cuotas de aportación, reparto porcentual en huchas, auditoría de Tasa de Esfuerzo Familiar, cálculo de resumen anual consolidado del hogar —Total necesidades, Total ahorrado en huchas, Semáforo anual— y generación atómica de transacciones de salida personal / entrada conjunta].
  - `src/backend/domain/repositories/` [MODIFICADO: Métodos CRUD de repositorio SQLite para el espacio conjunto en `sqlite_crud.py` o repositorio dedicado].
  - `tests/unit/test_joint_accounting_service.py` [NUEVO: Pruebas unitarias de cálculo con números reales mockeados para 50/50, proporcional y personalizado, tanto en Pre-Convivencia como en Convivencia Plena, y métricas anuales familiares].
- **Casos de Prueba a Verificar**:
  - Cálculo exacto en Estrategia A (Plantilla Nominal): suma de huchas fijas en Pre-Convivencia y suma de Necesidades + Huchas en Convivencia Plena.
  - Cálculo exacto en Estrategia B (Porcentaje de Ingresos): recaudación combinada y distribución porcentual exacta entre las Huchas de Amortización según `allocation_percentage`.
  - Imputación contable limpia en el perfil personal: salida clasificada como Necesidades (o Ahorro en Pre-Convivencia si se configuró así) sin generar ingresos ficticios.
  - Clasificación correcta del Semáforo de Tasa de Esfuerzo (Verde <50%, Amarillo 50-60%, Rojo >60%).
  - Cálculo consolidado del Resumen Anual del Hogar certificando la ausencia de campos de comparación A vs B.
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

- **Objetivo**: Exponer las capacidades de la Cuenta Conjunta mediante un router REST fuertemente tipado en FastAPI, con endpoints para estado y onboarding inicial, configuración del hogar, huchas de amortización, aportaciones mensuales, transacciones conjuntas, diagnóstico anual y triggers de sincronización.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/joint.py` [NUEVO: Endpoints REST para estado/onboarding inicial, configuración del hogar, huchas de amortización, aportaciones mensuales, transacciones conjuntas, diagnóstico anual del hogar y triggers de sincronización].
  - `src/backend/main.py` [MODIFICADO: Registro del router `/joint`].
  - `tests/integration/test_joint_api.py` [NUEVO: Pruebas de integración HTTP con SQLite en memoria y cliente `TestClient`].
- **Endpoints a Implementar**:
  - `GET /joint/status`: Retorna si la cuenta conjunta está configurada (`is_configured: bool`).
  - `POST /joint/setup`: Endpoint de onboarding que crea `JointAccount` y siembra el catálogo base de categorías comunes.
  - `GET /joint/account` y `PUT /joint/account`: Consulta y actualización de configuración del hogar (etapa, estrategia, porcentajes, ingresos de referencia).
  - `GET /joint/annual-summary`: Retorna las métricas anuales del hogar (total necesidades, total huchas, tasa de esfuerzo) sin desglose A vs B.
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
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando con códigos de estado HTTP correctos (200, 201, 400, 404, 409).

---

### Fase 5: Integración en Frontend Streamlit (Arquitectura de Dos Pantallas 100% Independientes)

- **Objetivo**: Implementar la capa de presentación interactiva desacoplada: selector de contexto raíz en `st.sidebar` (Perfil Personal vs Economía del Hogar), guarda de no-intrusión en el perfil personal, Asistente de Bienvenida para el estado inicial cero, y pantalla independiente del hogar con sus 4 pestañas dedicadas (Resumen Anual con gráficas Altair y sin comparativas A vs B, 12 Meses del Hogar, Huchas de Amortización y Configuración/Syncthing).
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos clientes con observabilidad estructurada y sanitización de logs para todos los endpoints `/joint/*`].
  - `src/frontend/views/joint_view.py` [NUEVO: Componente visual desacoplado para la Economía del Hogar: Asistente de Bienvenida (onboarding), navegación por 4 pestañas (Resumen Anual con gráficas Altair y métricas del hogar sin desglose A vs B, 12 Meses del Hogar con tabla de facturas sin ocio, Tarjetas de Huchas de Amortización con barras de progreso, y Panel de Configuración/Syncthing)].
  - `src/frontend/app.py` [MODIFICADO: Conmutador de contexto raíz en la cabecera de `st.sidebar`, guarda condicional para el banner mensual en el perfil personal solo si la cuenta está configurada, y renderizado condicional entre la vista personal y `joint_view.py`].
  - `tests/unit/test_joint_frontend.py` [NUEVO: Pruebas unitarias del cliente API y utilidades de presentación].
- **Casos de Prueba a Verificar**:
  - Conmutación limpia y completa entre "Mi Perfil Personal" y "Economía del Hogar".
  - Estado Inicial Cero: al entrar a Economía del Hogar sin cuenta previa, se renderiza el Asistente de Bienvenida y el perfil personal no muestra ningún banner.
  - Funcionamiento del banner de inicio de mes en perfil personal exclusivamente cuando la cuenta conjunta está configurada.
  - Renderizado fiel de las 4 pestañas del hogar:
    - Resumen Anual del Hogar: visualización de Total Necesidades, Total Ahorrado en Huchas, Tasa de Esfuerzo y gráficas Altair, certificando la ausencia de marcadores A vs B.
    - 12 Meses del Hogar con gastos comunes de necesidades.
    - Huchas de Amortización y semáforo familiar.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_frontend.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de frontend pasando sin errores de renderizado ni advertencias.

---

### Fase 6: Pruebas Integrales E2E, Guía de Syncthing y Consolidación de Memoria [COMPLETADA]

- **Objetivo**: Ejecutar una batería completa de pruebas end-to-end simulando la interacción entre dos dispositivos aislados (PC Windows y Mac), redactar la guía visual de emparejamiento con Syncthing, consolidar la memoria arquitectónica en `MEMORY.md` y preparar la fusión a `develop`.
- **Archivos a crear/modificar**:
  - `tests/integration/test_joint_e2e_flow.py` [NUEVO: Prueba end-to-end simulando: 1) Estado Cero inicial sin cuenta configurada y verificación de no-intrusión en perfil personal; 2) Configuración guiada vía onboarding en PC y Mac; 3) Asiento asistido de aportación con banner; 4) Intercambio de deltas JSON vía carpetas mockeadas; 5) Ingesta en el segundo equipo; 6) Liquidación de gasto de hucha; 7) Verificación de saldos idénticos y métricas del Resumen Anual sin desglose A vs B].
  - `docs/guia_sincronizacion_syncthing.md` [NUEVO: Guía clara y paso a paso para instalar y emparejar Syncthing entre Windows y macOS mediante Device ID en 3 minutos].
  - `MEMORY.md` [MODIFICADO: Registrar decisiones técnicas, cierre formal de Spec 010 y actualización del mapa de arquitectura].
  - `specs/README.md` [MODIFICADO: Actualizar índice de especificaciones con Spec 010 Completada].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_* tests/integration/test_joint_*
  ```
- **Criterio de Aceptación**: 100% de todas las pruebas de la especificación pasando, cero advertencias en `compileall` y verificación activa de `.gitignore`.

---

### Fase 7: Mejoras, Auditoría de Resiliencia y Corrección de Bugs [EN PROCESO DE CORRECCIÓN DE AUDITORÍA]

- **Objetivo**: Implementar capacidades clave de usabilidad, corregir los 4 bugs identificados en la auditoría previa al cierre de la especificación e incorporar la Mejora 1 para el cálculo dinámico de cuotas:
  1. **Restablecimiento y Regreso al Estado Cero en 1 Clic**: Endpoint `POST /joint/reset` y botón en la interfaz Streamlit para desactivar/purgar la cuenta conjunta y volver al estado inicial sin cuenta configurada (cero intrusión) de forma inmediata y segura sin tocar la consola.
  2. **Onboarding Único con Detección Automática de Invitación (Opción A)**: Detección en el segundo dispositivo del delta `ACCOUNT` emitido por la pareja vía Syncthing (`sync/inbox/`), ofreciendo la opción *"Unirse al Hogar en 1-Clic"* con asignación automática de perfiles complementarios (`local_profile = MEMBER_B`, `remote_profile = MEMBER_A`), eliminando el riesgo de discrepancias o configuraciones asimétricas.
  3. **Corrección de Bugs de Auditoría**:
     - **BUG-1 (Preservación de Nombres de Miembros en Invitación)**: `accept_joint_invitation` propaga explícitamente `member_a_name` y `member_b_name` al configurar el hogar en el dispositivo de la pareja.
     - **BUG-2 (Perfil Dinámico en Banner de Aportación)**: `_render_personal_assisted_contribution_banner` en `app.py` resuelve dinámicamente `local_profile` y el nombre del miembro local, eliminando el valor estático `MEMBER_A`.
     - **BUG-3 (Resiliencia ante IDs Discordantes en Deltas)**: Inclusión de `subcategory_name` y `sinking_fund_name` en el payload JSON de deltas de transacciones emitidas para tolerancia a discordancias de autoincrementales entre bases de datos independientes.
     - **BUG-4 (Sincronización de Hucha Receptora)**: Emisión de delta `UPSERT` para la hucha receptora tras eliminar una hucha con reasignación de saldo remanente (`reallocate_to_fund_id`).
  4. **Mejora 1 (Cálculo Dinámico en Banner Mensual Personal)**:
     - Nuevo endpoint `GET /joint/contributions/calculation` en FastAPI que evalúa la cuota exacta según la estrategia contable del hogar (fija 50/50 o porcentaje de nómina), consumido por `app.py` para pre-rellenar el importe exacto a transferir.
- **Archivos creados/modificados**:
  - `src/backend/database/componentes/sqlite_crud.py` [MODIFICADO: Métodos `reset_joint_account()` y `get_joint_subcategory()`].
  - `src/backend/database/interfaz/db_interface.py` [MODIFICADO: Firma abstracta `get_joint_subcategory()`].
  - `src/backend/services/joint_sync_service.py` [MODIFICADO: Detección de invitaciones de cuenta en buzón inbox y limpieza de carpetas locales en reset].
  - `src/backend/api/routers/joint.py` [MODIFICADO: Endpoints `POST /joint/reset`, `GET /joint/invitation`, `POST /joint/accept-invitation`, `GET /joint/contributions/calculation`, propagación de nombres en invitación, inclusión de nombres en deltas y sincronización de hucha receptora].
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `reset_joint_account()`, `get_joint_invitation()`, `accept_joint_invitation()` y `get_joint_contribution_calculation()`].
  - `src/frontend/views/joint_view.py` [MODIFICADO: Tarjeta interactiva *"Unirse al Hogar creado por tu pareja"* en el asistente Zero-State y botón `[🗑️ Desactivar Cuenta Conjunta y Volver al Estado Cero]`].
  - `src/frontend/app.py` [MODIFICADO: Banner de aportación asistida personal con resolución dinámica de `local_profile` y prellenado con cuota matemática calculada].
  - `tests/unit/test_joint_frontend.py` [MODIFICADO: Pruebas unitarias para reset, invitación y cálculo de cuota].
  - `tests/integration/test_joint_api.py` [MODIFICADO: Pruebas de integración para `/joint/reset`, `/joint/invitation`, `/joint/contributions/calculation` y comprobación de nombres de miembros].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_joint_* tests/integration/test_joint_*
  ```
- **Criterio de Aceptación**: 100% de las 48 pruebas de la especificación pasando, reversibilidad garantizada a Estado Cero y tolerancia cross-device sin discrepancias.

---

### Fase 7.1: Auditoría Técnica Exhaustiva de Sincronización, Integridad y Despliegue Multi-SO (Docker / Syncthing)

A raíz de la auditoría técnica exhaustiva del motor de sincronización asíncrona, concurrencia en Docker y coherencia contable cross-device, se identificaron los siguientes 11 hallazgos estructurados por severidad:

#### 🔴 Bloque Crítico: Riesgos de Pérdida y Descuadre Contable Silencioso
1. **Hallazgo 1 (CRÍTICO): Bug de Doble Deducción en Huchas de Amortización (*Double Deduction Bug*)**
   - **Diagnóstico**: Al registrar un gasto vinculado a una hucha en el Dispositivo A, `joint.py` emite dos deltas: `SINKING_FUND (UPSERT)` con el `current_balance` ya descontado, y `TRANSACTION (UPSERT)` con el gasto. Al procesar en el Dispositivo B en orden cronológico, primero se asigna el saldo ya descontado de A y luego `_apply_transaction_event` vuelve a restar el importe (`fund.current_balance -= deducted`).
   - **Impacto**: Un gasto de 200 € resta 400 € en el receptor; los saldos de las huchas divergen de forma permanente entre ambos ordenadores.
2. **Hallazgo 2 (CRÍTICO): Inversión y Colisión de IDs Autoincrementales por Fallo en Resolución por Nombre**
   - **Diagnóstico**: En `joint_sync_service.py`, la condición `if sinking_name and not sinking_id:` (y para `subcat_id`) nunca se cumple porque el emisor siempre incluye el ID numérico local en el payload. Como resultado, la resolución tolerante por nombre nunca se ejecuta y se aplica directamente el ID del emisor.
   - **Impacto**: Si la hucha 1 en A es *'Vacaciones'* y la hucha 1 en B es *'Coche'*, un gasto de Vacaciones en A se imputa y descuenta de Coche en B.
3. **Hallazgo 3 (CRÍTICO): Ausencia de `PRAGMA foreign_keys = ON` en SQLite y Corrupción Relacional**
   - **Diagnóstico**: `sqlite_db.py` crea el motor SQLite sin el listener `@event.listens_for(Engine, "connect")` que active `PRAGMA foreign_keys = ON`. En SQLite vienen desactivadas por defecto.
   - **Impacto**: Al borrar una hucha, las transacciones que la referencian no reciben `ON DELETE SET NULL`. Si posteriormente se crea una nueva hucha y SQLite le asigna el mismo ID autoincremental, todas las transacciones históricas de la hucha eliminada se reasignan erróneamente a la nueva.

#### 🟠 Bloque Alto: Inconsistencias de Lógica Contable y Aportaciones
4. **Hallazgo 4 (ALTO): Desconexión entre Aportaciones Mensuales y Saldo de Huchas (*Zero Growth Bug*)**
   - **Diagnóstico**: `calculate_monthly_contributions()` calcula la cuota que debe distribuirse a cada hucha (`fund_allocations`), pero el endpoint `POST /joint/contributions/asentar-asistida` solo guarda la fila en `JointMonthlyContribution`, ignorando `fund_allocations`.
   - **Impacto**: El saldo de las huchas jamás aumenta con las aportaciones; permanecen a 0,00 € indefinidamente salvo edición manual en la UI.
5. **Hallazgo 5 (ALTO): Falta de UUID en Aportaciones y Sobrescritura de Extras (*Lost Extraordinary Contributions*)**
   - **Diagnóstico**: `JointMonthlyContribution` carece de UUID y de clave única. Localmente permite insertar varias aportaciones en un mes (ej. cuota regular de 500 € + extra de 200 € = 700 €), pero `_apply_contribution_event` busca por `(month, profile)` y sobrescribe el importe (`existing_c.amount = amount`).
   - **Impacto**: En el receptor la segunda aportación machaca a la primera, reduciendo el total a 200 € y perdiendo 500 € en el camino.
6. **Hallazgo 6 (ALTO): Imposibilidad de Reversión de Aportaciones en UI y Desconexión con el Perfil Personal**
   - **Diagnóstico**: No existe endpoint ni botón en la interfaz para eliminar o deshacer una aportación común (`DELETE /joint/contributions/{id}`). Si el usuario borra la transacción de aportación en su perfil personal, la aportación en la cuenta conjunta queda intacta y jamás se notifica a la pareja.

#### 🟡 Bloque Medio: Resiliencia de Transporte y Ciclo de Vida
7. **Hallazgo 7 (MEDIO): Acumulación Indefinida en `sync/outbox/` y Falso Estado "No Sincronizado"**
   - **Diagnóstico**: Los deltas emitidos en `sync/outbox/` nunca se archivan ni eliminan por la app. Como `is_synchronized` requiere `outbox_pending_count == 0`, la aplicación muestra permanentemente `🟡 Sin conexión / Pendiente` o `🟡 0 Delta(s) Pendiente(s)`.
8. **Hallazgo 8 (MEDIO): Pérdida de Repartos Personalizados al Aceptar Invitación (Opción A)**
   - **Diagnóstico**: `accept_joint_invitation` hardcodea `member_a_contribution_pct=50.0` y `member_b_contribution_pct=50.0` en vez de extraer los porcentajes del payload de la invitación.
   - **Impacto**: Si la pareja pactó 60/40, el segundo equipo adopta 50/50, calculando cuotas distintas en cada máquina.
9. **Hallazgo 9 (MEDIO): Falta de Propagación Remota de `reset_joint_account`**
   - **Diagnóstico**: Al desactivar la cuenta conjunta en un dispositivo, solo se purga la base y carpetas locales. No se emite ningún evento `ACCOUNT DELETE` a Syncthing, permitiendo que el otro equipo siga enviando eventos huérfanos.
10. **Hallazgo 10 (MEDIO): Ausencia de Sincronización Reactiva en el Perfil Personal**
    - **Diagnóstico**: `process_inbox()` solo se dispara al navegar a "Economía del Hogar". Si el usuario permanece en su "Perfil Personal", la app no procesa el buzón de entrada y el banner de inicio de mes no detecta si la pareja ya aportó.

#### 🔵 Bloque Bajo: Extensibilidad de Catálogo
11. **Hallazgo 11 (BAJO): Ausencia de Entidad Sincronizable para Subcategorías del Hogar**
    - **Diagnóstico**: `SyncEntityType` no contempla subcategorías. Modificaciones o altas de conceptos comunes en una máquina no se propagan a la otra, dejando transacciones sin clasificar (`subcategory_id = None`).

---

### Plan de Trabajo Correctivo (Secuencia de Mayor a Menor Criticidad)

El presente plan correctivo se ejecutará estrictamente por fases de severidad tras la clarificación de decisiones de diseño con el usuario:

#### Paso 1: Erradicación de Fallos Críticos (R-1, R-2, R-3)
1. **R-1 (Doble Deducción de Huchas)**:
   - Desacoplar la mutación de saldo en transacciones sincronizadas: en `_apply_transaction_event`, no deducir del saldo de la hucha si el estado del saldo se sincroniza autoritativamente mediante el evento `SINKING_FUND`, o adoptar un modelo determinista libre de carreras.
2. **R-2 (Resolución Prioritaria por Nombre de Huchas y Subcategorías)**:
   - Modificar `_apply_transaction_event` en `joint_sync_service.py` para resolver **siempre y prioritariamente por nombre** (`sinking_fund_name` y `subcategory_name`), descartando el ID numérico local del emisor para inmunidad total ante autoincrementales desfasados.
3. **R-3 (Activación de Foreign Keys en SQLite)**:
   - Añadir en `src/backend/database/componentes/sqlite_db.py` el listener `@event.listens_for(engine, "connect")` ejecutando `PRAGMA foreign_keys = ON;` para garantizar que `ON DELETE SET NULL` y `CASCADE` se cumplan estrictamente a nivel de motor.

#### Paso 2: Integridad Contable y Aportaciones (R-4, R-5, R-6)
4. **R-4 (Incremento Automático de Huchas por Aportaciones)**:
   - En `record_assisted_contribution()`, aplicar las cuotas de `fund_allocations` a las huchas activas incrementando su `current_balance` y emitiendo los deltas correspondientes a outbox.
5. **R-5 (UUID en Aportaciones y Múltiples Aportaciones por Mes)**:
   - Añadir campo `uuid` (UUIDv4) a `JointMonthlyContribution` y actualizar `_apply_contribution_event` para gestionar idempotencia y mutaciones por UUID en vez de por tupla `(month, profile)`.
6. **R-6 (Reversión y Eliminación de Aportaciones)**:
   - Crear endpoint `DELETE /joint/contributions/{contribution_id}` en FastAPI con botón en Streamlit y reversión bidireccional coherente con el apunte del perfil personal y emisión de tombstone.

#### Paso 3: Resiliencia de Transporte y Ciclo de Vida (R-7, R-8, R-9, R-10)
7. **R-7 (Gestión de Outbox y Estado de Sincronización)**:
   - Ajustar el cálculo de `is_synchronized` para evaluar la frescura y ausencia de errores en `inbox`, e implementar un archivado/rotación limpia de deltas de outbox.
8. **R-8 (Preservación de Porcentajes de Aportación en Invitación)**:
   - Extraer `member_a_contribution_pct` y `member_b_contribution_pct` de la invitación en `accept_joint_invitation()`.
9. **R-9 (Propagación Remota de Reset de Hogar)**:
   - Emitir evento `ACCOUNT (DELETE)` antes de vaciar las carpetas locales en `reset_joint_account()`.
10. **R-10 (Sincronización en Inicio de Aplicación)**:
    - Ejecutar `trigger_process_inbox()` al inicializar `app.py` en cualquier contexto de perfil.

#### Paso 4: Robustez de Catálogo (R-11)
11. **R-11 (Sincronización de Subcategorías)**:
    - Añadir `SUBCATEGORY` a `SyncEntityType` y soportar su replicación básica ante altas o modificaciones del catálogo común.


---

### Registro de Mejoras Futuras (Post-Spec)

- **Alerta de Sobregasto en Huchas de Amortización**: Emisión de aviso informativo (`st.warning`) en la UI si un cargo a una hucha supera el saldo disponible acumulado, indicando que la hucha ha quedado a 0 € y el remanente ha sido absorbido por la tesorería común del hogar.
- **Exportación Consolidada del Hogar a Excel / CSV**: Generación y descarga de archivos tabulares con el histórico de gastos comunes, aportaciones mensuales y estado de huchas para justificaciones de alquiler o control anual.
- **Visor de Sincronización Avanzado en UI**: En el panel de configuración, visualización de deltas archivados en `sync/processed/` y funcionalidad para inspeccionar o reintentar eventos fallidos en `sync/error/` directamente desde la interfaz gráfica.


