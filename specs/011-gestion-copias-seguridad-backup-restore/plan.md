# Plan de Implementación: Especificación 011 — Gestión y Copias de Seguridad de Base de Datos en Interfaz (Backup & Restore)

El presente plan establece el desglose técnico y la secuencia de ejecución estricta, **fase a fase**, de acuerdo con la metodología SDD (*Spec-Driven Development*) y la Constitución del proyecto.

---

## Desglose Secuencial de Fases

### Fase 1: Contratos Fuertemente Tipados, Entidad ORM y Servicio Desacoplado con Purga WAL y SHA-256 (`backup_service.py`) [COMPLETADA]

- **Objetivo**: Desarrollar la entidad ORM `BackupScheduleConfig`, los contratos Pydantic v2 (incluyendo hashes SHA-256 y rollback), y el servicio desacoplado en Python con copia caliente atómica (`sqlite3.backup`), validación defensiva de archivos SQLite, purga obligatoria de archivos `-wal` y `-shm` en restauración, deduplicación de copias automáticas sin cambios por SHA-256, auto-migración con `init_db()` y función de reversión atómica `rollback_last_restore()`.
- **Archivos creados/modificados**:
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

### Fase 2: Router REST en FastAPI, Endpoints de Rollback, Programación y Persistencia Docker [COMPLETADA]

- **Objetivo**: Exponer las capacidades del servicio de copias mediante un router REST fuertemente tipado en FastAPI bajo `/backup` (salud, creación, descarga binaria stream, restauración, endpoint `POST /backup/restore/rollback` para reversión en 1-clic y `GET/PUT /backup/schedule`), junto con el worker horario en segundo plano no bloqueante y la declaración del volumen persistente `backups/` en Docker Compose.
- **Archivos creados/modificados**:
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

### Fase 3: Métodos de Cliente y Pestaña Interactiva en Streamlit con Rollback en 1-Clic (`💾 Base de Datos y Copias de Seguridad`) [COMPLETADA]

- **Objetivo**: Implementar la capa de cliente en `api_client.py` con observabilidad estructurada y desarrollar la nueva pestaña principal en Streamlit estructurada en 5 tarjetas con diseño visual premium: Diagnóstico de Salud con hash SHA-256, Descarga Directa, Programación Periódica, Restauración Guiada con Inspección Previa y Banner de Rollback en 1-Clic, y Catálogo de Instantáneas Locales.
- **Archivos creados/modificados**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `get_database_health()`, `create_backup()`, `download_backup_bytes()`, `list_backups()`, `restore_backup_upload()`, `restore_backup_local()`, `rollback_restore()`, `delete_backup_local()`, `get_backup_schedule()`, `update_backup_schedule()` con logging descriptivo].
  - `src/frontend/views/backup_view.py` [NUEVO: Vista interactiva desacoplada para la pestaña de copias: tarjetas métricas de salud con badges `🟢`/`🔴`, hash SHA-256 corto y aviso preventivo si han transcurrido más de N días sin respaldo, botón de descarga directa `.db`, panel interactivo de programación periódica con selector de frecuencia y retención, componente `st.file_uploader`, banner de Rollback para deshacer la última restauración en 1 clic y tabla interactiva de instantáneas locales con botones de restauración/borrado].
  - `src/frontend/app.py` [MODIFICADO: Inclusión de la pestaña `💾 Base de Datos y Copias de Seguridad` en el selector principal].
  - `tests/unit/test_backup_frontend.py` [NUEVO: Pruebas unitarias de los métodos cliente y verificación de renderizado defensivo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_frontend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas pasando, confirmación obligatoria antes de restaurar, botón de rollback operativo y recarga inmediata de la interfaz tras cualquier cambio.

---

### Fase 4: Blindaje de Seguridad en `.gitignore`, Consolidación de Memoria y Pruebas E2E [COMPLETADA]

- **Objetivo**: Asegurar que ningún archivo de backup ni la carpeta `backups/` se registren en el repositorio Git, verificar la suite completa de la especificación, registrar las decisiones en `MEMORY.md`, actualizar el índice en `specs/README.md` y preparar la fusión limpia a `develop`.
- **Archivos creados/modificados**:
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
- **Criterio de Aceptación**: 100% de las pruebas de la especificación pasando, cero advertencias en `compileall`, árbol de trabajo limpio sin archivos sensibles.

---

### Fase 5: Mejoras, Auditoría de Resiliencia y Corrección de Bugs [COMPLETADA]

- **Objetivo**: Corregir los 5 hallazgos críticos detectados durante la auditoría técnica previa al commit final, optimizando el consumo de red, eliminando la creación involuntaria de copias por re-renderizado en Streamlit, resolviendo la paradoja del observador en la deduplicación SHA-256, implementando la pre-inspección de archivos antes de restaurar y blindando las acciones del catálogo local mediante popovers de confirmación:
  1. **BUG-1 (Descarga Innecesaria en Cada Render de Streamlit)**:
     - En `src/frontend/views/backup_view.py`, desacoplar la generación de la descarga mediante `st.session_state`. El usuario pulsa `📥 Generar Copia Descargable`, se ejecuta la petición al backend una única vez, se cachean los bytes y el nombre en sesión, y se renderiza `st.download_button`. Esto elimina llamadas HTTP continuas, creación masiva de copias en disco y rotación indebida al interactuar con cualquier elemento de la interfaz.
  2. **BUG-2 (Paradoja del Observador en Hash SHA-256 de Copias Periódicas)**:
     - En `src/backend/services/backup_service.py: check_and_run_scheduled_backup`, calcular el hash determinista basándose en el contenido de las tablas de datos de usuario (o persistir el timestamp de ejecución antes de la instantánea), evitando que la actualización interna del registro en `backup_schedule_configs` altere el hash del archivo y provoque falsos positivos de modificación en cada ciclo.
  3. **BUG-3 (Endpoint y Botón de Pre-Inspección de Archivos antes de Restaurar)**:
     - Crear el endpoint `POST /backup/validate` en `src/backend/api/routers/backup.py` y el método `validate_backup_upload(file_bytes, filename)` en `src/frontend/api_client.py`.
     - En la Tarjeta 4 de `backup_view.py`, tras seleccionar un archivo `.db`, añadir el botón `🔍 Inspeccionar y Validar Copia`, mostrando una tarjeta informativa detallada con el estado de integridad (`ok`), hash SHA-256 y desglose del recuento de filas por tabla antes de habilitar la confirmación de restauración.
  4. **BUG-4 (Bucle Persistente del Banner de Rollback tras Revertir)**:
     - En `src/backend/services/backup_service.py: rollback_last_restore`, renombrar la instantánea de seguridad aplicada a `archived_prerestore_<timestamp>.db`. De este modo se preserva el archivo físico histórico para auditoría, pero `list_backups()` deja de identificarla como instantánea pendiente de reversión, ocultando limpiamente el banner amarillo al haber concluido el rollback.
  5. **BUG-5 (Confirmación Protegida en Catálogo Local mediante Popovers)**:
     - En la Tarjeta 5 de `backup_view.py`, reemplazar los botones directos de acción por componentes `st.popover` ("🔄 Restaurar" y "🗑️ Borrar") que exijan una confirmación explícita secundaria con advertencia de impacto antes de ejecutar la sobrescritura de la base o la eliminación definitiva del archivo.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/backup.py` [MODIFICADO: Endpoint `POST /backup/validate`].
  - `src/backend/services/backup_service.py` [MODIFICADO: Corrección de cálculo de hash en deduplicación programada y renombrado a archivo archivado en rollback].
  - `src/frontend/api_client.py` [MODIFICADO: Método `validate_backup_upload()`].
  - `src/frontend/views/backup_view.py` [MODIFICADO: Flujo de descarga con `st.session_state`, pre-inspección de archivos subidos y popovers de confirmación en catálogo local].
  - `tests/unit/test_backup_frontend.py` [MODIFICADO: Pruebas unitarias para `validate_backup_upload` y nuevos flujos].
  - `tests/integration/test_backup_api.py` [MODIFICADO: Pruebas de integración para `POST /backup/validate` y persistencia post-rollback].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_* tests/integration/test_backup_*
  .\venv\Scripts\python -m compileall src tests
  git status -u
  ```
- **Criterio de Aceptación**: 100% de las pruebas pasando, descarga bajo demanda sin fugas de rendimiento en Streamlit, previsualización de datos previa a la restauración y eliminación del banner de rollback tras revertir.

---

### Registro de Mejoras Futuras (Post-Spec)

- **Compresión Automática de Copias (`.db.gz` / `.zip`)**: Ofrecer descargas y almacenamiento comprimido de instantáneas, reduciendo el consumo de disco y ancho de banda entre un 70% y un 85% para bases con miles de movimientos contables.
- **Cifrado Simétrico de Copias con Contraseña Maestra (AES-256-GCM / SQLCipher)**: Posibilidad de proteger la copia descargada con una clave secreta introducida por el usuario, evitando que información contable y saldos queden expuestos en texto plano en caso de extravío del archivo o respaldo en nubes comerciales.
- **Sincronización Externa de Respaldos (WebDAV / Nextcloud / S3 / Google Drive)**: Conector desacoplado en segundo plano para enviar automáticamente copias programadas a una nube privada o almacenamiento de objetos compatible con S3.
- **Alertas Proactivas de Integridad y Backup Vencido**: Notificación visual tipo *toast* en la barra lateral o al inicio de sesión si la base supera los 30 días sin respaldo o si `PRAGMA integrity_check` detecta anomalías estructurales.
- **Visor de Instantáneas Históricas en Modo Solo Lectura**: Posibilidad de cargar temporalmente un archivo de respaldo en una vista de consulta sin sobrescribir la base activa, para consultar movimientos o saldos de ejercicios pasados.
