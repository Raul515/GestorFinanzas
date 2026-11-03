# Plan de Implementación: Especificación 011 — Gestión y Copias de Seguridad de Base de Datos en Interfaz (Backup & Restore)

El presente plan establece el desglose técnico y la secuencia de ejecución estricta, **fase a fase**, de acuerdo con la metodología SDD (*Spec-Driven Development*) y la Constitución del proyecto.

---

## Desglose Secuencial de Fases

### Fase 1: Contratos Fuertemente Tipados, Entidad ORM y Servicio Desacoplado con Purga WAL y SHA-256 (`backup_service.py`)

- **Objetivo**: Desarrollar la entidad ORM `BackupScheduleConfig`, los contratos Pydantic v2 (incluyendo hashes SHA-256 y rollback), y el servicio desacoplado en Python con copia caliente atómica (`sqlite3.backup`), validación defensiva de archivos SQLite, purga obligatoria de archivos `-wal` y `-shm` en restauración, deduplicación de copias automáticas sin cambios por SHA-256, auto-migración con `init_db()` y función de reversión atómica `rollback_last_restore()`.
- **Archivos a crear/modificar**:
  - `src/backend/domain/models/backup.py` [NUEVO: Entidad ORM SQLAlchemy `BackupScheduleConfig` para persistir estado, frecuencia en días, límite de retención, fecha de última ejecución y último hash SHA-256].
  - `src/backend/domain/models/__init__.py` [MODIFICADO: Exportar `BackupScheduleConfig`].
  - `src/backend/domain/schemas/backup.py` [NUEVO: Contratos Pydantic v2 `DatabaseHealthResponse`, `BackupMetadata`, `BackupListResponse`, `BackupValidationResult`, `RestoreResponse`, `BackupScheduleResponse`, `BackupScheduleUpdate`].
  - `src/backend/services/backup_service.py` [NUEVO: Lógica desacoplada de copia caliente con `sqlite3.Connection.backup()`, cálculo de hash SHA-256, validación defensiva con `PRAGMA integrity_check`, comprobación de tablas maestras, rotación configurable en `backups/`, snapshot previo `safety_prerestore_*.db`, purga de residuales WAL (`-wal`, `-shm`), sustitución atómica con liberación de conexiones SQLAlchemy (`engine.dispose()`), auto-migración inmediata mediante `init_db()`, función de rollback `rollback_last_restore()` y verificación de copias programadas con detección de duplicados].
  - `tests/unit/test_backup_service.py` [NUEVO: Suite unitaria cubriendo creación de copias en caliente, cálculo SHA-256, rotación de archivos, detección de archivos corruptos o texto plano, validación de esquemas discordantes, purga verificada de WAL, ciclo completo de restauración con snapshot previo, reversión atómica de rollback y omisión de duplicados sin cambios].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando, cero contención en SQLite y aislamiento completo respecto a la base de datos de producción.

---

### Fase 2: Router REST en FastAPI, Endpoints de Rollback, Programación y Persistencia Docker

- **Objetivo**: Exponer las capacidades del servicio de copias mediante un router REST fuertemente tipado en FastAPI bajo `/backup` (salud, creación, descarga binaria stream, restauración, endpoint `POST /backup/restore/rollback` para reversión en 1-clic y `GET/PUT /backup/schedule`), junto con el worker horario en segundo plano no bloqueante y la declaración del volumen persistente `backups/` en Docker Compose.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/backup.py` [NUEVO: Endpoints `GET /backup/health`, `POST /backup/create`, `GET /backup/download`, `GET /backup/list`, `POST /backup/restore/upload`, `POST /backup/restore/local/{filename}`, `POST /backup/restore/rollback`, `DELETE /backup/local/{filename}`, `GET /backup/schedule`, `PUT /backup/schedule`].
  - `src/backend/api/main.py` [MODIFICADO: Registro del router `backup.router`, verificación al inicio en `lifespan` y tarea periódica en segundo plano no bloqueante].
  - `docker_local/docker-compose.yml` [MODIFICADO: Mapeo de volumen persistente `- ../backups:/app/backups` para el servicio backend].
  - `tests/integration/test_backup_api.py` [NUEVO: Pruebas de integración con `TestClient` validando códigos HTTP 200, 400 (archivos corruptos), 404 (backup no encontrado), headers de descarga `application/x-sqlite3`, actualización de programación, respuesta de restauración y endpoint de rollback].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_backup_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando y gestión de errores defensiva sin caída del servidor ante ficheros malformados o peticiones concurrentes.

---

### Fase 3: Métodos de Cliente y Pestaña Interactiva en Streamlit con Rollback en 1-Clic (`💾 Base de Datos y Copias de Seguridad`)

- **Objetivo**: Implementar la capa de cliente en `api_client.py` con observabilidad estructurada y desarrollar la nueva pestaña principal en Streamlit estructurada en 5 tarjetas con diseño visual premium: Diagnóstico de Salud con hash SHA-256, Descarga Directa, Programación Periódica, Restauración Guiada con Inspección Previa y Banner de Rollback en 1-Clic, y Catálogo de Instantáneas Locales.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `get_database_health()`, `create_backup()`, `download_backup_bytes()`, `list_backups()`, `restore_backup_upload()`, `restore_backup_local()`, `rollback_restore()`, `delete_backup_local()`, `get_backup_schedule()`, `update_backup_schedule()` con logging descriptivo].
  - `src/frontend/views/backup_view.py` [NUEVO: Vista interactiva desacoplada para la pestaña de copias: tarjetas métricas de salud con badges `🟢`/`🔴`, hash SHA-256 corto y aviso preventivo si han transcurrido más de N días sin respaldo, botón de descarga directa `.db`, panel interactivo de programación periódica con selector de frecuencia (semanal, quincenal, mensual o personalizada) y retención, componente `st.file_uploader` con inspección previa de contenido y popover de confirmación protegida, banner de Rollback para deshacer la última restauración en 1 clic si no era la deseada, y tabla interactiva de instantáneas locales con botones de restauración/borrado en 1-clic].
  - `src/frontend/app.py` [MODIFICADO: Inclusión de la pestaña `💾 Base de Datos y Copias de Seguridad` en el selector principal].
  - `tests/unit/test_backup_frontend.py` [NUEVO: Pruebas unitarias de los métodos cliente y verificación de renderizado defensivo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_frontend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas pasando, confirmación obligatoria antes de restaurar, botón de rollback operativo y recarga inmediata de la interfaz tras cualquier cambio.

---

### Fase 4: Blindaje de Seguridad en `.gitignore`, Consolidación de Memoria y Pruebas E2E

- **Objetivo**: Asegurar que ningún archivo de backup ni la carpeta `backups/` se registren en el repositorio Git, verificar la suite completa de la especificación, registrar las decisiones en `MEMORY.md`, actualizar el índice en `specs/README.md` y preparar la fusión limpia a `develop`.
- **Archivos a crear/modificar**:
  - `.gitignore` [MODIFICADO: Registro de `backups/`, `*.backup`, `*.db.bak`].
  - `tests/integration/test_backup_e2e_flow.py` [NUEVO: Prueba end-to-end simulando ciclo completo: creación de datos contables -> programación periódica -> copia caliente automática -> simulación de alteración contable -> restauración desde archivo con purga WAL -> verificación de datos idénticos -> ejecución de rollback a estado original -> verificación de recuperación íntegra].
  - `MEMORY.md` [MODIFICADO: Registro del cierre de la Spec 011 y decisiones arquitectónicas].
  - `specs/README.md` [MODIFICADO: Actualización de estado de la Spec 011 en el catálogo oficial].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_* tests/integration/test_backup_*
  .\venv\Scripts\python -m compileall src tests
  git status -u
  ```
- **Criterio de Aceptación**: 100% de las pruebas de la especificación pasando, cero advertencias en `compileall`, árbol de trabajo limpio sin archivos sensibles y solicitud de confirmación al usuario para fusionar en `develop`.
