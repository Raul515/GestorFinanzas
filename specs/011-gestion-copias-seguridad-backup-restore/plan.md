# Plan de Implementación: Especificación 011 — Gestión y Copias de Seguridad de Base de Datos en Interfaz (Backup & Restore)

El presente plan establece el desglose técnico y la secuencia de ejecución estricta, **fase a fase**, de acuerdo con la metodología SDD (*Spec-Driven Development*) y la Constitución del proyecto.

---

## Desglose Secuencial de Fases

### Fase 1: Contratos Fuertemente Tipados Pydantic v2 y Servicio Desacoplado de Backup (`backup_service.py`)

- **Objetivo**: Desarrollar los modelos de datos tipados Pydantic v2 para diagnóstico y gestión de copias, y el servicio desacoplado en Python con la lógica pura de copia caliente atómica (`sqlite3.backup`), validación de integridad de archivos SQLite, rotación de las 5 instantáneas locales más recientes y restauración segura con snapshot previo de protección.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/backup.py` [NUEVO: Contratos Pydantic v2 `DatabaseHealthResponse`, `BackupMetadata`, `BackupListResponse`, `BackupValidationResult`, `RestoreResponse`].
  - `src/backend/services/backup_service.py` [NUEVO: Lógica desacoplada de copia caliente con `sqlite3.Connection.backup()`, validación defensiva con `PRAGMA integrity_check`, comprobación de tablas maestras, rotación de las 5 copias en `backups/`, snapshot automático previo pre-restauración y sustitución atómica con liberación de conexiones SQLAlchemy].
  - `tests/unit/test_backup_service.py` [NUEVO: Suite unitaria cubriendo creación de copias en caliente, rotación a 5 archivos, detección de archivos corruptos o texto plano, validación de esquemas discordantes y ciclo completo de restauración con verificación de snapshot previo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando, cero contención en SQLite y aislamiento completo respecto a la base de datos de producción.

---

### Fase 2: Router REST en FastAPI y Endpoints de Descarga y Restauración

- **Objetivo**: Exponer las capacidades del servicio de copias mediante un router REST fuertemente tipado en FastAPI bajo `/backup`, soportando descarga directa como fichero binario stream (`.db`), subida con multipart `UploadFile`, restauración local y listado de instantáneas.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/backup.py` [NUEVO: Endpoints `GET /backup/health`, `POST /backup/create`, `GET /backup/download`, `GET /backup/list`, `POST /backup/restore/upload`, `POST /backup/restore/local/{filename}`, `DELETE /backup/local/{filename}`].
  - `src/backend/api/main.py` [MODIFICADO: Registro del router `backup.router`].
  - `tests/integration/test_backup_api.py` [NUEVO: Pruebas de integración con `TestClient` validando códigos HTTP 200, 400 (archivos corruptos), 404 (backup no encontrado), headers de descarga `application/x-sqlite3` y respuesta de restauración].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_backup_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando y gestión de errores defensiva sin caída del servidor ante ficheros malformados.

---

### Fase 3: Métodos de Cliente y Pestaña Interactiva en Streamlit (`💾 Base de Datos y Copias de Seguridad`)

- **Objetivo**: Implementar la capa de cliente en `api_client.py` con observabilidad estructurada y desarrollar la nueva pestaña principal en Streamlit con un diseño visual premium compuesto por 4 tarjetas: Diagnóstico de Salud, Descarga Directa, Restauración Guiada con Inspección Previa y Catálogo de Instantáneas Locales.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `get_database_health()`, `create_backup()`, `download_backup_bytes()`, `list_backups()`, `restore_backup_upload()`, `restore_backup_local()`, `delete_backup_local()` con logging descriptivo].
  - `src/frontend/views/backup_view.py` [NUEVO: Vista interactiva desacoplada para la pestaña de copias: tarjetas métricas de salud con badges `🟢`/`🔴`, botón de descarga directa `.db`, componente `st.file_uploader` con inspección previa de contenido y popover de confirmación protegida, y tabla interactiva de instantáneas locales con botones de restauración/borrado en 1-clic].
  - `src/frontend/app.py` [MODIFICADO: Inclusión de la pestaña `💾 Base de Datos y Copias de Seguridad` en el selector principal].
  - `tests/unit/test_backup_frontend.py` [NUEVO: Pruebas unitarias de los métodos cliente y verificación de renderizado defensivo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_frontend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas pasando, confirmación obligatoria antes de restaurar y recarga inmediata de la interfaz tras cualquier cambio.

---

### Fase 4: Blindaje de Seguridad en `.gitignore`, Consolidación de Memoria y Pruebas E2E

- **Objetivo**: Asegurar que ningún archivo de backup ni la carpeta `backups/` se registren en el repositorio Git, verificar la suite completa de la especificación, registrar las decisiones en `MEMORY.md`, actualizar el índice en `specs/README.md` y preparar la fusión limpia a `develop`.
- **Archivos a crear/modificar**:
  - `.gitignore` [MODIFICADO: Registro de `backups/`, `*.backup`, `*.db.bak`].
  - `tests/integration/test_backup_e2e_flow.py` [NUEVO: Prueba end-to-end simulando ciclo completo: creación de datos contables -> copia caliente -> simulación de alteración/error contable -> restauración desde archivo -> verificación de datos idénticos recuperados y preservación del snapshot de seguridad previo].
  - `MEMORY.md` [MODIFICADO: Registro del cierre de la Spec 011 y decisiones arquitectónicas].
  - `specs/README.md` [MODIFICADO: Inclusión de la Spec 011 en el catálogo oficial].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_backup_* tests/integration/test_backup_*
  .\venv\Scripts\python -m compileall src tests
  git status -u
  ```
- **Criterio de Aceptación**: 100% de las pruebas de la especificación pasando, cero advertencias en `compileall`, árbol de trabajo limpio sin archivos sensibles y solicitud de confirmación al usuario para fusionar en `develop`.
