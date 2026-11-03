# Especificación 012: Actualizaciones del Sistema en 1 Clic desde Interfaz (In-App OTA Updater)

## 1. Resumen Ejecutivo y Visión

El **Gestor de Finanzas Personales** evoluciona constantemente con nuevas funcionalidades, mejoras de sincronización multiperfil, optimizaciones de interfaz y parches de estabilidad. En la actualidad, para que un usuario (o cotitular del hogar con un segundo ordenador, como un Mac o portátil) reciba las últimas actualizaciones, depende de:
1. **Comandos de Git por terminal** (`git pull`, etc.): Requiere tener Git y herramientas de desarrollo instaladas, conocimientos de consola y resolver posibles conflictos locales manualmente.
2. **Descargas manuales de archivos ZIP desde GitHub**: Requiere descargar el ZIP, descomprimirlo, sobreescribir ficheros a mano teniendo sumo cuidado de no borrar la base de datos local (`finanzas.db`), la configuración de sincronización (`device_id.txt`), ni las variables de entorno (`.env`), un proceso tedioso y de alto riesgo para usuarios no desarrolladores.

El objetivo de esta especificación es implementar un sistema de **Actualización en Caliente en 1 Clic (Over-The-Air Updater)** accesible directamente desde la interfaz de usuario (Streamlit) y gobernado por un servicio desacoplado en FastAPI:
1. **Cero Dependencia de Git (`Git-Free`)**: La comprobación y descarga de actualizaciones se realiza 100% mediante la API HTTP de GitHub y descarga directa del tarball oficial del repositorio, eliminando la necesidad de tener Git instalado en el equipo anfitrión.
2. **Detección Automática de Rutas (Cero Configuración)**: El sistema identifica automáticamente la raíz del proyecto (`PROJECT_ROOT` o `/app` en Docker) sin que el usuario deba escribir ni conocer rutas de carpetas.
3. **Multiplataforma Nativo (macOS, Windows, Linux)**: Basado exclusivamente en módulos estándar de Python (`requests`/`urllib`, `tarfile`, `pathlib`, `shutil`), garantizando un comportamiento idéntico en cualquier sistema operativo.
4. **Protección Patrimonial Incondicional (Lista Negra / Whitelist Blindada)**: Garantía de que bajo ninguna circunstancia se sobrescribirán ni eliminarán los datos del usuario:
   - Base de datos activa y archivos WAL (`src/backend/data/finanzas.db*`).
   - Identificador de dispositivo (`src/backend/data/device_id.txt`).
   - Archivos de secretos y entorno (`.env`, `.env.local`).
   - Carpeta de sincronización local Syncthing (`sync/`).
   - Carpeta de copias de seguridad (`backups/`).
   - Repositorio git existente (`.git/`).
   - Entornos virtuales locales (`venv/`, `.venv/`).
   - Archivo de persistencia de versión (`src/backend/data/version.json`).
5. **Directorio Temporal de Validación (*Staging*), Anti-Tar-Slip y Normalización de Tarball**: Las actualizaciones se descargan y descomprimen primero en una carpeta temporal de staging (`tmp/update_staging/`), normalizando el directorio raíz que GitHub genera automáticamente (`{repo}-{branch}/`), verificando cada entrada con protección estricta anti-Tar-Slip y validando la sintaxis con `compileall` antes de tocar el código de producción.
6. **Doble Red de Seguridad Previa y Rollback Desacoplado en 1 Clic**: Antes de actualizar:
   - Se crea una copia de seguridad atómica de la base de datos mediante la API nativa `sqlite3.backup()` reutilizando el servicio de backups (`backups/pre_update_safety_*.db`).
   - Se crea una instantánea comprimida del código y dependencias previas (`backups/code_snapshot_prev.tar.gz`), permitiendo deshacer la actualización en 1 clic (*Code Rollback*) sin afectar las transacciones que el usuario haya registrado posteriormente.
7. **Limpieza Inteligente de Archivos Obsoletos (*Pruning*)**: Mediante un manifiesto persistente (`src/backend/data/installed_manifest.json`), el sistema elimina ficheros de código antiguos que hayan sido borrados o renombrados en GitHub, evitando acumulación de archivos huérfanos.
8. **Gestión Segura y Determinista de Nuevas Dependencias (`requirements/`)**: Comparación SHA-256 de los requerimientos de backend y frontend (`requirements/backend.txt` y `requirements/frontend.txt`). En lugar de intentar un peligroso `pip install` en caliente dentro de un proceso activo, el sistema marca con precisión `requires_rebuild = True` y presenta un aviso visual claro solicitando reiniciar los contenedores o el entorno.
9. **Caché de Comprobación y Control de Cuota GitHub (Rate Limits)**: Búfer de 15 minutos en memoria y debounce en interfaz para no agotar el límite horario de GitHub API, con envío de cabecera estándar `User-Agent` y soporte transparente de `GITHUB_TOKEN` opcional.
10. **Sincronización en Caliente (*Hot-Reload*) y Purga Defensiva de Bytecode**: Los cambios en código provocan la recarga de módulos y purgan automáticamente la caché `.pyc` de `__pycache__` para evitar inconsistencias de ejecución (manejando bloqueos de ficheros en Windows).
11. **Auto-Migración Defensiva de Base de Datos**: Ejecución de `init_db()` y un hook introspectivo de migración defensiva que inspecciona las tablas existentes en SQLite y aplica `ALTER TABLE ... ADD COLUMN` si los nuevos modelos SQLAlchemy incorporan columnas ausentes.
12. **Aviso Preventivo para Entornos de Desarrollo Git**: Si el sistema detecta que se ejecuta sobre un clon local con `.git/`, muestra una alerta preventiva indicando que la actualización OTA sobreescribe archivos locales.

---

## 2. Usuarios y Casos de Uso

- **Cotitular no técnico / Usuario doméstico (Mac, Windows o Linux)**:
  - No tiene Git instalado ni sabe usar la consola.
  - Abre la aplicación en su navegador, entra a la pestaña «🚀 Actualizaciones del Sistema», ve un mensaje claro: «Hay una nueva versión disponible (v1.X.X - Mejoras en Huchas)», pulsa «Actualizar a la Última Versión», espera unos segundos y continúa usando la app con todas las nuevas mejoras sin fricción.
  - Si por alguna razón la actualización falla o no le convence, dispone de un botón «Deshacer Actualización de Código» para regresar de inmediato a la versión anterior.
- **Desarrollador / Administrador**:
  - Puede definir en el `.env` la rama objetivo (`UPDATE_BRANCH=main` o `UPDATE_BRANCH=develop`) si desea desplegar ramas experimentales en dispositivos secundarios.
  - Dispone de endpoints REST para automatizaciones o comprobaciones programadas.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Consulta Visual de Estado y Versión)**: Como usuario, quiero ver en la interfaz qué versión tengo actualmente instalada (identificador de commit, fecha y rama), y si mi sistema está al día con respecto al repositorio en GitHub.
- **HU-2 (Comprobación Eficiente de Actualizaciones con User-Agent y Caché)**: Como usuario, quiero pulsar «Buscar Actualizaciones» y que el sistema consulte GitHub respetando los límites de tasa y cabeceras obligatorias, mostrándome si hay cambios nuevos, el mensaje del último commit y su fecha.
- **HU-3 (Actualización Segura en 1 Clic con Staging y Normalización)**: Como usuario, quiero pulsar «Actualizar a la Última Versión» y que el sistema normalice el paquete de GitHub, valide el código en una carpeta temporal antes de aplicarlo, garantizando que nunca se corromperá mi entorno de ejecución.
- **HU-4 (Respaldo Automático Preventivo y Rollback de Código Desacoplado)**: Como usuario, quiero tener la certeza de que antes de actualizar se respaldan tanto mi base de datos como mi código previo, con la opción de revertir el código en un solo clic sin perder los datos contables introducidos.
- **HU-5 (Limpieza de Archivos Huérfanos y Detección de Dependencias)**: Como usuario, quiero que la actualización elimine archivos de código viejos que ya no se usan y me avise si se añadieron librerías nuevas en `requirements/` que requieren reiniciar los contenedores.
- **HU-6 (Recarga Transparente)**: Como usuario, quiero que tras completar la actualización la interfaz me indique el éxito de la operación y me invite a recargar la página (`st.rerun()`) para disfrutar de las novedades.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Contratos de Datos Pydantic v2 (`src/backend/domain/schemas/updater.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE tipar todas las operaciones de actualización mediante contratos Pydantic v2 inmutables:
  - `VersionInfo`:
    - `current_commit`: String con el hash SHA (corto, 7 caracteres, o completo). Por defecto `"initial"` si no existe `src/backend/data/version.json`.
    - `branch`: String con la rama configurada (por defecto `"main"`).
    - `last_updated_at`: `datetime` o string ISO-8601 de la última actualización local.
    - `commit_message`: String opcional con el título del commit instalado.
    - `rollback_available`: Booleano (`True` si existe la instantánea previa `backups/code_snapshot_prev.tar.gz`).
    - `is_git_repo`: Booleano (`True` si se detecta la carpeta `.git/` en la raíz).
  - `UpdateCheckResponse`:
    - `update_available`: Booleano (`True` si el commit remoto difiere del commit local).
    - `current_commit`: String con el commit local activo.
    - `remote_commit`: String con el último commit disponible en GitHub.
    - `remote_commit_message`: String con el mensaje descriptivo del commit remoto.
    - `remote_commit_date`: String ISO-8601 con la fecha de publicación en GitHub.
    - `branch`: Rama consultada (ej. `"main"`).
    - `checked_at`: Timestamp ISO-8601 del momento de la consulta.
    - `cached`: Booleano (`True` si la respuesta proviene de la caché en memoria).
    - `rate_limit_remaining`: Entero opcional indicando consultas restantes a GitHub.
    - `error`: String opcional si la consulta falló (ej. sin conexión a Internet o límite agotado).
  - `UpdateApplyResponse`:
    - `success`: Booleano indicando el resultado de la operación.
    - `previous_commit`: Commit previo antes de actualizar.
    - `updated_to_commit`: Commit instalado exitosamente.
    - `files_updated_count`: Número de archivos extraídos y actualizados.
    - `obsolete_files_pruned_count`: Número de archivos antiguos eliminados.
    - `pre_update_backup_path`: Ruta del respaldo de seguridad de base de datos generado.
    - `new_dependencies_detected`: Booleano indicando si cambiaron las dependencias en `requirements/`.
    - `requires_rebuild`: Booleano indicando si se sugiere reiniciar el contenedor Docker o entorno.
    - `message`: Mensaje descriptivo para el usuario (en español).
  - `CodeRollbackResponse`:
    - `success`: Booleano de la reversión.
    - `restored_commit`: Hash del commit restaurado.
    - `message`: Mensaje descriptivo (en español).

### RF-2: Detección Automática de Raíz de Proyecto y Cero Configuración
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE resolver la ruta absoluta de la raíz del proyecto de forma dinámica y sin intervención del usuario:
  - Si la variable de entorno `PROJECT_ROOT` está definida, se utilizará su valor normalizado.
  - En su defecto, se calculará automáticamente mediante introspección:
    `Path(__file__).resolve().parents[3]` (desde `src/backend/services/updater_service.py` hacia la raíz).
  - EL SISTEMA NO requerirá en ningún caso que el usuario escriba rutas de carpetas o directorios.

### RF-3: Comprobación Inteligente Vía API de GitHub con Cabeceras, Caché y Debounce
- **Criterio EARS (Event-Driven)**: CUANDO se solicita comprobar actualizaciones:
  - EL SISTEMA DEBE incluir obligatoriamente la cabecera `User-Agent: GestorFinanzas-OTA-Updater/1.0` en todas las peticiones a GitHub API.
  - EL SISTEMA DEBE mantener una caché en memoria de 15 minutos para evitar agotar la cuota de GitHub API (60 peticiones/hora para clientes anónimos).
  - Si la petición en la UI se realiza con menos de 60 segundos desde la última consulta forzada (debounce), se devolverá el resultado en caché.
  - Al consultar GitHub, se invocará: `GET https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{branch}`
    - Parámetros por defecto: `repo_owner="Raul515"`, `repo_name="GestorFinanzas"`, `branch="main"`.
    - Sobrescribibles vía `.env`: `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`, `UPDATE_BRANCH`.
  - Si existe `GITHUB_TOKEN` en `.env`, se enviará en la cabecera `Authorization: Bearer <token>` (ampliando el límite a 5.000 peticiones/hora).
  - Si GitHub responde con error 403 (Rate Limit), el sistema debe capturarlo amigablemente e informar al usuario de los minutos restantes para reintentar.

### RF-4: Descarga en Staging, Normalización de Tarball de GitHub y Anti-Tar-Slip
- **Criterio EARS (Ubiquitous)**: AL DESCARGAR el paquete de actualización:
  - EL SISTEMA DEBE descargar el tarball mediante `https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.tar.gz` (o endpoint tarball de la API de GitHub si hay token) y descomprimirlo inicialmente en el directorio temporal `tmp/update_staging/`.
  - **Normalización de Directorio Raíz de GitHub**: Dado que GitHub empaqueta todo el contenido dentro de una carpeta raíz `{repo}-{branch}/`, el sistema debe detectar dicha subcarpeta y aplanar o normalizar las rutas de destino relativas a la raíz del staging.
  - **Protección Anti-Tar-Slip**: EL SISTEMA DEBE verificar cada entrada del archivo tar (`tarfile.TarInfo`) impidiendo cualquier ruta absoluta o ruta relativa que contenga `../` o escape del directorio de staging.
  - **Validación Sintáctica Previa**: Antes de transferir ningún archivo a producción, EL SISTEMA DEBE verificar que `src/backend/api/main.py` y `src/frontend/app.py` existen en el staging y pasan la compilación de Python (`compileall.compile_dir(staging_path, quiet=1)`). Si se detecta un error de sintaxis, la actualización se aborta y se limpia el staging.

### RF-5: Blindaje Estricto de Datos Locales y Purga Defensiva de `__pycache__`
- **Criterio EARS (Ubiquitous)**: DURANTE la transferencia de archivos desde el staging al proyecto:
  - EL SISTEMA NUNCA DEBE sobrescribir ni borrar:
    1. `src/backend/data/finanzas.db*` (base de datos activa y archivos WAL).
    2. `src/backend/data/device_id.txt` (ID de nodo de sincronización).
    3. `src/backend/data/version.json` (se actualiza exclusivamente al finalizar la operación exitosa).
    4. `.env*` (secretos y variables locales).
    5. `backups/` (histórico de copias de seguridad e instantáneas).
    6. `sync/` (buzones de sincronización P2P).
    7. `.git/` (control de versiones local si existiera).
    8. `venv/`, `.venv/` (entornos virtuales locales).
  - **Purga de Bytecode**: Tras la copia de los nuevos ficheros, EL SISTEMA DEBE purgar automáticamente todas las carpetas `__pycache__` y ficheros `.pyc` dentro de `src/`, capturando y registrando cualquier `PermissionError` sin interrumpir la actualización (manejo defensivo de bloqueos de archivo en Windows).

### RF-6: Respaldo Doble Preventivo y Rollback de Código Desacoplado
- **Criterio EARS (State-Driven)**: ANTES de modificar el código en producción:
  - EL SISTEMA DEBE generar una copia de seguridad atómica de la base de datos `finanzas.db` invocando `create_backup(backup_type="SAFETY_PREUPDATE")` de `src/backend/services/backup_service.py`.
  - EL SISTEMA DEBE comprimir los directorios `src/` y `requirements/` actuales en `backups/code_snapshot_prev.tar.gz`.
- **Criterio EARS (Event-Driven)**: CUANDO el usuario solicita deshacer la actualización (`POST /api/updater/rollback`):
  - EL SISTEMA DEBE restaurar los directorios `src/` y `requirements/` desde `backups/code_snapshot_prev.tar.gz`, purgar `__pycache__` y actualizar `src/backend/data/version.json` al commit previo.
  - La base de datos no se altera durante el rollback de código para preservar las transacciones recientes registradas por el usuario.

### RF-7: Limpieza de Archivos Huérfanos y Obsoletos (*Pruning*)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE mantener un archivo persistente `src/backend/data/installed_manifest.json` con la lista de ficheros instalados por la aplicación.
- Tras extraer la nueva versión, cualquier archivo que figuraba en el manifiesto anterior pero ya no existe en el nuevo paquete (y no pertenezca a la lista protegida de exclusión) DEBE ser eliminado del disco, evitando archivos huérfanos o colisiones de módulos antiguos.

### RF-8: Detección Determinista de Dependencias (`requirements/`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE comparar el hash SHA-256 de los requerimientos nuevos (`requirements/backend.txt` y `requirements/frontend.txt`) frente a los actuales:
  - Si son idénticos: `new_dependencies_detected = False`, `requires_rebuild = False`.
  - Si difieren: `new_dependencies_detected = True` y `requires_rebuild = True`.
  - EL SISTEMA NO intentará ejecutar `pip install` en caliente dentro de un proceso activo en ejecución para evitar bloqueos de DLLs/wheels en Windows o fallos de contenedor en Docker. En su lugar, informará de manera prominente en la respuesta y en la interfaz la necesidad de reiniciar los contenedores (`docker compose restart` o rebuild) o el entorno virtual.

### RF-9: Hook Introspectivo de Migraciones Defensivas de Base de Datos
- **Criterio EARS (State-Driven)**: TRAS la actualización del código:
  - EL SISTEMA DEBE ejecutar `init_db()` de `src/backend/database/componentes/sqlite_db.py` y un hook introspectivo defensivo que compare las tablas existentes en SQLite con los modelos SQLAlchemy, aplicando sentencias `ALTER TABLE ... ADD COLUMN` si los modelos incorporan nuevas columnas ausentes en la base local del usuario.

### RF-10: Router REST en FastAPI (`src/backend/api/routers/updater.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE exponer 4 endpoints REST fuertemente tipados bajo el prefijo `/api/updater`:
  - `GET /api/updater/version`: Devuelve la versión actual (`VersionInfo`).
  - `GET /api/updater/check`: Comprueba actualizaciones en GitHub con soporte de caché (`UpdateCheckResponse`).
  - `POST /api/updater/apply`: Ejecuta la actualización completa en staging, backups, reemplazo, pruning y purga (`UpdateApplyResponse`).
  - `POST /api/updater/rollback`: Restaura la versión de código previa (`CodeRollbackResponse`).
  - El router debe estar registrado en [src/backend/api/main.py](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/src/backend/api/main.py).

### RF-11: Módulo Visual en Streamlit (`src/frontend/views/updater_view.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE presentar una vista dedicada en Streamlit accesible mediante la pestaña `🚀 Actualizaciones del Sistema` en [src/frontend/app.py](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/src/frontend/app.py):
  - **Tarjeta de Estado de Versión**: Badge con el commit actual (7 caracteres), rama configurada, fecha de instalación y aviso preventivo si se detecta un repositorio Git local (`is_git_repo = True`).
  - **Botón «Buscar Actualizaciones»**: Consulta con debounce y feedback visual de caché o disponibilidad de nueva versión.
  - **Panel Informativo de Novedades**: Título del commit remoto, fecha de publicación y mensaje descriptivo.
  - **Botón «Actualizar a la Última Versión»**: Confirmación mediante checkbox protegido, barra de progreso y notificación de éxito con botón para recargar la aplicación (`st.rerun()`).
  - **Alerta de Reinicio de Contenedores**: Si `requires_rebuild = True`, muestra una advertencia visual destacada explicando que las dependencias cambiaron y recomendando reiniciar el contenedor o servicio.
  - **Banner de Deshacer Actualización**: Si existe la instantánea previa (`rollback_available = True`), muestra un botón «Deshacer Actualización de Código» para revertir de inmediato a la versión anterior.

---

## 5. Requisitos No Funcionales (RNF)

- **RNF-1 (Portabilidad Total Sin Git)**: 100% Python nativo, compatible de forma idéntica en macOS, Windows y Linux sin depender de ejecutables de Git o comandos externos en el anfitrión.
- **RNF-2 (Compatibilidad Docker y Hot-Reload)**: El volumen de backend en `docker_local/docker-compose.yml` debe montar `../src/frontend:/app/src/frontend` (o utilizar `docker-compose.extend.yml` con `../:/app`) para garantizar que las actualizaciones de código en el backend persistan en el anfitrión y el frontend de Streamlit las recargue al refrescar el navegador.
- **RNF-3 (Resiliencia Operativa y Memoria Controlada)**: Descarga en bloques de 64 KB, uso de memoria < 50 MB, y cancelación atómica sin alterar código si la validación sintáctica con `compileall` detecta errores.
- **RNF-4 (Observabilidad y Prohibición de Fallos Silenciosos)**: Uso obligatorio de `logging` estructurado registrando cada etapa del proceso (comprobación GitHub, descarga, extracción en staging, validación sintáctica, pruning, purga pycache y migración).
- **RNF-5 (Idioma y Nomenclatura)**: Backend, contratos Pydantic v2, routers y métodos 100% en inglés; UI, docstrings explicativos y mensajes al usuario 100% en español.

---

## 6. Casos Borde y Manejo de Errores

1. **Pérdida de conexión a Internet a mitad de la descarga**: Ocurre en la carpeta `tmp/update_staging/`. Al detectarse error de red, se purga el directorio temporal y el código de producción permanece 100% intacto.
2. **Error de sintaxis en el commit remoto de GitHub**: El paso de validación con `compileall.compile_dir` detecta el error en el staging y aborta antes de copiar ningún archivo, emitiendo un mensaje descriptivo.
3. **Límite de tasa de GitHub (HTTP 403 Rate Limit)**: El servicio captura el error amigablemente, calcula los minutos restantes según la cabecera `X-RateLimit-Reset` e informa al usuario ofreciendo configurar `GITHUB_TOKEN` en `.env`.
4. **Archivo `.pyc` bloqueado en Windows (`PermissionError`)**: La purga de `__pycache__` maneja excepciones de bloqueo ignorando ficheros retenidos por procesos del sistema sin abortar la actualización de los ficheros de código `.py`.
5. **Nuevas columnas añadidas a la base de datos**: El hook defensivo de migración previene errores de `no such column` añadiendo las columnas ausentes con valor por defecto nulo.
6. **Código nuevo inestable o con regresiones**: El usuario puede pulsar «Deshacer Actualización de Código» en la interfaz para restaurar el código previo desde `code_snapshot_prev.tar.gz` sin perder datos contables.
7. **Detección de clon Git de desarrollo**: La interfaz advierte al desarrollador si detecta `.git/` para evitar que sobreescriba cambios locales no commiteados.

---

## 7. Matriz de Trazabilidad y Aceptación (EARS)

| Requisito | Tipo EARS | Descripción de Aceptación |
| :--- | :--- | :--- |
| **RF-1** | Ubiquitous | Esquemas Pydantic v2 `VersionInfo`, `UpdateCheckResponse`, `UpdateApplyResponse`, `CodeRollbackResponse`. |
| **RF-2** | Ubiquitous | Detección dinámica y automática de `PROJECT_ROOT` sin intervención del usuario. |
| **RF-3** | Event-Driven | Comprobación en GitHub API con cabecera `User-Agent`, caché en RAM de 15 minutos, debounce y soporte `GITHUB_TOKEN`. |
| **RF-4** | Ubiquitous | Descarga en staging, normalización de subcarpeta de GitHub, validación con `compileall` y protección anti-Tar-Slip. |
| **RF-5** | Ubiquitous | Blindaje de `finanzas.db*`, `device_id.txt`, `version.json`, `.env*`, `backups/`, `sync/`, `.git/` y purga defensiva de `__pycache__`. |
| **RF-6** | State-Driven | Doble respaldo previo (`sqlite3.backup()` para DB + tarball de `src/` y `requirements/`) y endpoint de rollback en 1 clic. |
| **RF-7** | Ubiquitous | Manifiesto persistente `installed_manifest.json` y eliminación segura de archivos huérfanos/obsoletos. |
| **RF-8** | Ubiquitous | Detección de cambios en `requirements/backend.txt` y `requirements/frontend.txt` con marcación clara de `requires_rebuild`. |
| **RF-9** | State-Driven | Hook introspectivo de migración defensiva de esquema SQLite post-actualización. |
| **RF-10** | Ubiquitous | Router REST `/api/updater` con `/version`, `/check`, `/apply`, `/rollback` registrado en `src/backend/api/main.py`. |
| **RF-11** | Ubiquitous | Vista en Streamlit `updater_view.py` con tarjeta de versión, comprobación, confirmación protegida, progreso, aviso de rebuild y rollback. |
