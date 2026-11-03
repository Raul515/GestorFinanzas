# Plan de Implementación: Especificación 012 — Actualizaciones del Sistema en 1 Clic desde Interfaz (In-App OTA Updater)

El presente plan establece el desglose técnico y la secuencia de ejecución estricta, **fase a fase**, de acuerdo con la metodología SDD (*Spec-Driven Development*), los hallazgos de la auditoría técnica aprobada y la Constitución del proyecto.

---

## Desglose Secuencial de Fases

### Fase 1: Contratos Tipados Pydantic v2 y Servicio Desacoplado con Staging, Pruning, Anti-Tar-Slip y Doble Respaldo (`updater_service.py`)

- **Objetivo**: Desarrollar los contratos Pydantic v2 para el ciclo de actualización y rollback, y el servicio desacoplado `updater_service.py` incorporando todas las salvaguardas y soluciones técnicas auditadas:
  1. Detección automática de `PROJECT_ROOT` y detección de repositorios Git locales (`is_git_repo`).
  2. Consulta a GitHub API enviando cabecera obligatoria `User-Agent: GestorFinanzas-OTA-Updater/1.0`, soporte de `GITHUB_TOKEN` y caché en memoria de 15 minutos con debounce.
  3. Descarga y extracción en directorio temporal de staging (`tmp/update_staging/`) con **normalización de la subcarpeta raíz de GitHub** (`{repo}-{branch}/`) y protección estricta anti-Tar-Slip.
  4. Validación sintáctica previa con `compileall.compile_dir` en staging (`src/backend/api/main.py` y `src/frontend/app.py`) antes de transferir archivos.
  5. Doble respaldo preventivo:
     - Respaldo atómico de la base de datos `finanzas.db` reutilizando `create_backup(backup_type="SAFETY_PREUPDATE")` de `src/backend/services/backup_service.py`.
     - Snapshot comprimido de código y dependencias previas en `backups/code_snapshot_prev.tar.gz` (`src/` y `requirements/`).
  6. Blindaje incondicional de la lista protegida (`finanzas.db*`, `device_id.txt`, `version.json`, `.env*`, `backups/`, `sync/`, `.git/`, `venv/`).
  7. Manifiesto persistente de ficheros instalados (`src/backend/data/installed_manifest.json`) y eliminación segura de archivos obsoletos (*pruning*).
  8. Detección determinista de cambios de dependencias comparando hashes SHA-256 de `requirements/backend.txt` y `requirements/frontend.txt`, marcando `requires_rebuild = True` (sin forzar peligrosos `pip install` en caliente).
  9. Purga defensiva de bytecode residual (`__pycache__` y `.pyc`) en `src/`, capturando `PermissionError` en Windows.
  10. Función de reversión de código desacoplada en 1 clic (`rollback_code()`), restaurando `src/` y `requirements/` sin alterar transacciones de la base de datos.
  11. Hook introspectivo de migración defensiva de base de datos (`init_db()` y chequeo de columnas).
  12. Persistencia atómica de versión en `src/backend/data/version.json`.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/updater.py` [NUEVO: Contratos Pydantic v2 `VersionInfo`, `UpdateCheckResponse`, `UpdateApplyResponse`, `CodeRollbackResponse`].
  - `src/backend/services/updater_service.py` [NUEVO: Lógica desacoplada completa con staging, strip de subcarpeta GitHub, anti-tar-slip, pre-validación sintáctica, llamada a `create_backup()`, snapshot de `src/` y `requirements/`, pruning de huérfanos, diff de `requirements/`, purga defensiva de pycache, hook de migración, rollback y persistencia de `version.json`].
  - `tests/unit/test_updater_service.py` [NUEVO: Suite unitaria cubriendo detección de versión, mock de API de GitHub (200, 403 rate-limit con cálculo de reset, 404), caché de consultas, extracción en staging con tarball simulado que incluye prefijo de GitHub, rechazo de rutas con `../` (anti-tar-slip), rechazo de código con error de sintaxis, preservación de lista negra, eliminación de obsoletos, ciclo de rollback de código y persistencia de `version.json`].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando, cero dependencias de Git en el sistema operativo y validación defensiva probada.

---

### Fase 2: Router REST en FastAPI (`src/backend/api/routers/updater.py`), Endpoints y Pruebas de Integración

- **Objetivo**: Exponer las capacidades del actualizador mediante un router REST fuertemente tipado en FastAPI bajo `/api/updater` (`/version`, `/check`, `/apply`, `/rollback`), con manejo estructurado de excepciones HTTP, inyección del servicio desacoplado y registro en `src/backend/api/main.py`.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/updater.py` [NUEVO: Endpoints `GET /api/updater/version`, `GET /api/updater/check`, `POST /api/updater/apply`, `POST /api/updater/rollback`].
  - `src/backend/api/main.py` [MODIFICADO: Inclusión del router `updater.router` en la aplicación FastAPI bajo el prefijo `/api/updater`].
  - `tests/integration/test_updater_api.py` [NUEVO: Pruebas de integración con `TestClient` simulando respuestas de GitHub, verificando códigos HTTP 200, contratos JSON Pydantic v2, comportamiento ante errores de red, actualización exitosa y ejecución de rollback].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_updater_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando, respuestas consistentes y sin excepciones no capturadas.

---

### Fase 3: Métodos de Cliente y Módulo Visual de Actualizaciones en Streamlit (`api_client.py`, `updater_view.py` y `app.py`)

- **Objetivo**: Implementar los métodos de cliente en `api_client.py` con logging descriptivo y crear el módulo visual interactivo en Streamlit en una vista dedicada `src/frontend/views/updater_view.py` accesible desde la pestaña `🚀 Actualizaciones del Sistema` en `src/frontend/app.py`:
  - Badge de versión actual y commit de 7 caracteres.
  - Alerta preventiva informativa si se detecta un repositorio Git local (`is_git_repo = True`).
  - Botón de comprobación con debounce y caché.
  - Tarjeta informativa de actualización disponible con diff de commit y fecha.
  - Checkbox de confirmación protegida.
  - Barra de progreso interactiva durante la descarga y aplicación.
  - Advertencia destacada si se detectan nuevas dependencias (`requires_rebuild = True`) indicando la necesidad de reiniciar Docker Compose o el entorno.
  - Botón de recarga de página `st.rerun()`.
  - Banner de «Deshacer Actualización de Código» cuando existe un snapshot previo.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `get_app_version()`, `check_for_updates()`, `apply_system_update()`, `rollback_system_update()` con logging adecuado y captura de errores de conexión].
  - `src/frontend/views/updater_view.py` [NUEVO: Vista completa de actualizaciones de sistema].
  - `src/frontend/views/__init__.py` [MODIFICADO: Exportar `render_updater_view`].
  - `src/frontend/app.py` [MODIFICADO: Añadir la pestaña `🚀 Actualizaciones del Sistema` a `tabs_list` y renderizar `render_updater_view()`].
  - `tests/unit/test_updater_frontend.py` [NUEVO: Pruebas unitarias de los métodos cliente y verificación de renderizado defensivo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_frontend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas pasando, flujo visual intuitivo, advertencias claras de rebuild y botón de rollback operativo.

---

### Fase 4: Pruebas E2E, Configuración Docker, Blindaje Pre-Commit y Documentación

- **Objetivo**: Verificar el ciclo completo de actualización y rollback en una prueba end-to-end, asegurar el montaje bidireccional en Docker para persistencia en el anfitrión, verificar `.gitignore`, registrar las decisiones arquitectónicas en `MEMORY.md`, actualizar el catálogo en `specs/README.md` y preparar la fusión limpia a `develop`.
- **Archivos a crear/modificar**:
  - `tests/integration/test_updater_e2e_flow.py` [NUEVO: Prueba end-to-end simulando: estado inicial de versión -> comprobación con commit más reciente -> aplicación de actualización con reemplazo de código y pruning -> verificación de integridad de `finanzas.db` intacta -> verificación de versión actualizada -> ejecución de rollback de código -> verificación de restauración íntegra de la versión previa].
  - `docker_local/docker-compose.yml` [MODIFICADO: Añadir montaje `- ../src/frontend:/app/src/frontend` en el servicio `backend` para permitir la propagación de actualizaciones de interfaz al anfitrión].
  - `.gitignore` [MODIFICADO: Asegurar que `tmp/`, `tmp/update_staging/`, `backups/code_snapshot_prev.tar.gz` queden debidamente ignorados].
  - `MEMORY.md` [MODIFICADO: Registro del cierre de la Spec 012 y arquitectura final].
  - `specs/README.md` [MODIFICADO: Actualización del estado de la Spec 012 a COMPLETADA].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_* tests/integration/test_updater_*
  .\venv\Scripts\python -m compileall src tests
  git status -u
  ```
- **Criterio de Aceptación**: 100% de las pruebas de la especificación pasando, cero advertencias en `compileall`, árbol de trabajo limpio y confirmación del usuario para fusionar en `develop`.
