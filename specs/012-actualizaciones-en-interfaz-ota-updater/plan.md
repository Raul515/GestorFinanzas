# Plan de Implementación: Especificación 012 — Actualizaciones del Sistema en 1 Clic desde Interfaz (In-App OTA Updater)

El presente plan establece el desglose técnico y la secuencia de ejecución estricta, **fase a fase**, de acuerdo con la metodología SDD (*Spec-Driven Development*), los hallazgos de la auditoría técnica y la Constitución del proyecto.

---

## Desglose Secuencial de Fases

### Fase 1: Contratos Tipados Pydantic v2 y Servicio Desacoplado con Staging, Pruning y Doble Respaldo (`updater_service.py`)

- **Objetivo**: Desarrollar los contratos Pydantic v2 para el ciclo de actualización y rollback, y el servicio desacoplado `updater_service.py` incorporando:
  1. Detección automática de `PROJECT_ROOT` sin intervención del usuario.
  2. Caché en memoria de 15 minutos para consultas a GitHub API y soporte de `GITHUB_TOKEN`.
  3. Descarga y extracción en directorio temporal de staging (`tmp/update_staging/`) con protección estricta anti-Tar-Slip.
  4. Validación sintáctica previa con `compileall.compile_dir` en staging antes de aplicar cambios.
  5. Doble respaldo preventivo: copia de seguridad de la base de datos `finanzas.db` y snapshot comprimido del código previo en `backups/code_snapshot_prev.tar.gz`.
  6. Blindaje incondicional de la lista negra de ficheros protegidos (`finanzas.db*`, `device_id.txt`, `.env*`, `backups/`, `sync/`, `.git/`, `venv/`).
  7. Manifiesto de ficheros instalados (`installed_manifest.json`) y eliminación segura de archivos obsoletos (*pruning*).
  8. Detección de cambios de dependencias en `requirements.txt` y marcación de `requires_rebuild`.
  9. Purga de bytecode residual (`__pycache__` y `.pyc`) en `src/`.
  10. Función de reversión de código en 1 clic (`rollback_code()`).
  11. Hook de migración defensiva de base de datos (`init_db()` y `ALTER TABLE ... ADD COLUMN`).
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/updater.py` [NUEVO: Contratos Pydantic v2 `VersionInfo`, `UpdateCheckResponse`, `UpdateApplyResponse`, `CodeRollbackResponse`].
  - `src/backend/services/updater_service.py` [NUEVO: Lógica desacoplada completa con staging, anti-tar-slip, pre-validación sintáctica, doble backup, pruning de huérfanos, diff de requirements, purga de pycache, hook de migración y rollback].
  - `tests/unit/test_updater_service.py` [NUEVO: Suite unitaria cubriendo detección de versión, mock de API de GitHub (200, 403 rate-limit, 404), caché de consultas, extracción en staging con tarball simulado, rechazo de rutas con `../` (anti-tar-slip), rechazo de código con error de sintaxis, preservación de lista negra, eliminación de obsoletos, ciclo de rollback de código y persistencia de `version.json`].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_service.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas unitarias pasando, cero dependencias de Git en el sistema operativo y validación defensiva probada.

---

### Fase 2: Router REST en FastAPI (`/api/updater`), Endpoints y Pruebas de Integración

- **Objetivo**: Exponer las capacidades del actualizador mediante un router REST fuertemente tipado en FastAPI bajo `/api/updater` (`/version`, `/check`, `/apply`, `/rollback`), con manejo de excepciones HTTP, inyección del servicio desacoplado y registro en `main.py`.
- **Archivos a crear/modificar**:
  - `src/backend/routers/updater.py` [NUEVO: Endpoints `GET /api/updater/version`, `GET /api/updater/check`, `POST /api/updater/apply`, `POST /api/updater/rollback`].
  - `src/backend/main.py` [MODIFICADO: Inclusión del router `updater.router` en la aplicación FastAPI].
  - `tests/integration/test_updater_api.py` [NUEVO: Pruebas de integración con `TestClient` simulando respuestas de GitHub, verificando códigos HTTP 200, contratos JSON Pydantic v2, comportamiento ante errores de red, actualización exitosa y ejecución de rollback].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_updater_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas de integración pasando, respuestas consistentes y sin excepciones no capturadas.

---

### Fase 3: Métodos de Cliente y Módulo Visual de Actualizaciones en Streamlit (`api_client.py` y Vista de Mantenimiento)

- **Objetivo**: Implementar los métodos de cliente en `api_client.py` con logging descriptivo y crear el módulo visual e interactivo en Streamlit dentro de la pestaña de Configuración/Mantenimiento: visualización del commit actual y rama, botón de comprobación con debounce y caché, tarjeta informativa de actualización disponible con diff de commit y fecha, checkbox de confirmación protegida, barra de progreso, advertencia clara si se requieren nuevas dependencias (`requires_rebuild`), botón de recarga `st.rerun()`, y banner de «Deshacer Actualización de Código» cuando existe un snapshot previo.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `get_app_version()`, `check_for_updates()`, `apply_system_update()`, `rollback_system_update()` con logging adecuado y captura de errores de conexión].
  - `src/frontend/views/settings_view.py` (o tarjeta dedicada en la vista de Mantenimiento) [NUEVO/MODIFICADO: Card visual premium con badge de versión, botón de búsqueda con debounce, panel de novedades del commit, confirmación, progreso, aviso de reinicio de contenedor si cambiaron dependencias, y botón de Rollback en 1 clic].
  - `tests/unit/test_updater_frontend.py` [NUEVO: Pruebas unitarias de los métodos cliente y verificación de renderizado defensivo].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_frontend.py
  ```
- **Criterio de Aceptación**: 100% de pruebas pasando, flujo visual intuitivo, advertencias claras de rebuild y botón de rollback operativo.

---

### Fase 4: Pruebas E2E, Blindaje Pre-Commit y Documentación

- **Objetivo**: Verificar el ciclo completo de actualización y rollback en una prueba end-to-end, asegurar que ningún fichero temporal ni de snapshot altere `.gitignore`, registrar las decisiones arquitectónicas en `MEMORY.md`, actualizar el catálogo en `specs/README.md` y preparar la fusión limpia a `develop`.
- **Archivos a crear/modificar**:
  - `tests/integration/test_updater_e2e_flow.py` [NUEVO: Prueba end-to-end simulando: estado inicial de versión -> comprobación con commit más reciente -> aplicación de actualización con reemplazo de código y pruning -> verificación de integridad de `finanzas.db` intacta -> verificación de versión actualizada -> ejecución de rollback de código -> verificación de restauración íntegra de la versión previa].
  - `.gitignore` [MODIFICADO: Asegurar que `tmp/`, `tmp/update_staging/`, `backups/code_snapshot_prev.tar.gz` queden debidamente ignorados].
  - `MEMORY.md` [MODIFICADO: Registro del cierre de la Spec 012 y arquitectura final].
  - `specs/README.md` [MODIFICADO: Actualización del estado de la Spec 012].
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_updater_* tests/integration/test_updater_*
  .\venv\Scripts\python -m compileall src tests
  git status -u
  ```
- **Criterio de Aceptación**: 100% de las pruebas de la especificación pasando, cero advertencias en `compileall`, árbol de trabajo limpio y confirmación del usuario para fusionar en `develop`.
