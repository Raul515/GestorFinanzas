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

---

## Auditoría Técnica Post-Implementación y Resolución de Riesgos Operativos

A raíz de la auditoría técnica realizada tras completar las fases 1 a 4, se identificaron y resolvieron los siguientes riesgos operativos:

1. **Riesgo 1: Recarga de Procesos / Contenedores en Caliente**
   - **Diagnóstico**: En entornos Docker de producción donde Uvicorn se ejecuta sin el flag `--reload`, actualizar los archivos de código en disco no recarga automáticamente el proceso Python en memoria.
   - **Resolución aprobada**: Siguiendo las directrices del diseño inicial y la Constitución, no se intenta reiniciar en caliente procesos de sistema dentro de contenedores (evitando inestabilidades o caídas irreversibles). En su lugar, el sistema detecta de forma determinista si hay cambios en dependencias o código, emite una advertencia destacada en la interfaz recomendando el reinicio del servicio (`docker compose restart`), y ofrece un botón de recarga de vista `st.rerun()`.

2. **Riesgo 2: Condición de Carrera y Concurrencia en `apply_update` y `rollback_code`**
   - **Diagnóstico**: Solicitudes concurrentes o múltiples clics simultáneos en «Actualizar Sistema» o «Deshacer Actualización» podían provocar escrituras solapadas en `tmp/update_staging/` o sobreescritura corrupta de snapshots.
   - **Resolución técnica implementada**: Se introdujo un cerrojo de exclusión mutua a nivel de proceso (`_update_lock = threading.Lock()`) con adquisición no bloqueante (`acquire(blocking=False)`). En caso de detectarse una operación activa, se lanza un `RuntimeError` capturado en FastAPI para responder con código HTTP `409 Conflict`.

3. **Riesgo 3: Reversión Manual vs Automática en Caso de Fallo Durante la Copia**
   - **Diagnóstico**: Si ocurre un fallo durante la transferencia de archivos desde staging al directorio del proyecto, evaluar si se requiere un rollback automático inmediato.
   - **Resolución aprobada**: Debido a que la fase de staging pre-valida la integridad y la sintaxis (`compileall`) antes de mover un solo fichero, la probabilidad de error durante la copia es mínima. En caso de incidencia, la reversión manual en 1 clic está garantizada y protegida por el snapshot previo `code_snapshot_prev.tar.gz` y el respaldo de base de datos `SAFETY_PREUPDATE`.

4. **Riesgo 4: Blindaje Anti-Tar-Slip frente a Symlinks y Hardlinks**
   - **Diagnóstico**: Un archivo tarball descargado de GitHub podría contener enlaces simbólicos (`issym()`) o duros (`islnk()`) manipulados para escribir fuera del directorio de staging en Python 3.11.
   - **Resolución técnica implementada**: La función `_is_safe_tar_member()` fue ampliada para rechazar de forma estricta cualquier miembro que sea symlink (`member.issym()`) o hardlink (`member.islnk()`), garantizando que solo se extraigan archivos regulares y directorios legítimos.

5. **Riesgo 5: Tipado e Identificación Formal de Respaldos `SAFETY_PREUPDATE`**
   - **Diagnóstico**: El esquema `BackupMetadata` en `schemas/backup.py` solo contemplaba los tipos literales `MANUAL`, `AUTOMATIC` y `SAFETY_PRERESTORE`. Al generar respaldos automáticos previos a una actualización OTA, se producía un fallo de validación Pydantic o inconsistencia en el catálogo.
   - **Resolución técnica implementada**: Se amplió formalmente el contrato Pydantic v2 incorporando `"SAFETY_PREUPDATE"` al tipo literal `backup_type`, se registró el prefijo `safety_preupdate_` en `backup_service.py` y se actualizó `updater_service.py` para utilizar formalmente esta categoría.

---

## Mejoras Clave Futuras (Backlog Técnico Post-Spec 012)

Las siguientes mejoras técnicas quedan documentadas para su futura priorización en especificaciones dedicadas:

- **Pre-flight Check de Espacio en Disco**: Validar con `shutil.disk_usage()` que el volumen anfitrión cuenta con al menos 100 MB libres (o 2.5x el tamaño estimado del tarball) antes de iniciar la descarga.
- **Soporte de SemVer y GitHub Releases**: Ampliar el servicio para consultar lanzamientos formales (`/releases/latest`) permitiendo actualizaciones por etiquetas de versión semántica (v1.2.0) además del modo commit SHA actual.
- **Soporte para Repositorios Privados vía Tarball API**: Para organizaciones con repositorios privados, soportar la descarga vía endpoint autenticado `/repos/{owner}/{repo}/tarball/{ref}` con cabecera `Authorization: Bearer <GITHUB_TOKEN>`.
- **Limpieza Proactiva de Cachés de Streamlit**: Ejecutar una purga selectiva de `st.session_state` y cachés en memoria de Streamlit tras una actualización exitosa para evitar conflictos de esquemas.
- **Canary Health Check Post-Actualización**: Implementar una llamada de sondeo interno al endpoint `/health` tras la actualización antes de marcar la operación como completada exitosamente.

