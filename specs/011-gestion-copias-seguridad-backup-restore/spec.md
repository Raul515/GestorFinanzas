# Especificación 011: Gestión y Copias de Seguridad de Base de Datos en Interfaz (Backup & Restore)

## 1. Resumen Ejecutivo y Visión

El **Gestor de Finanzas Personales** almacena la totalidad de los datos contables y patrimoniales del usuario (transacciones mensuales, categorías 50/30/20, presupuestos base, fondo de emergencia, estrategias compensatorias, lista de seguimiento de valores y configuración del hogar multiperfil) en una base de datos local SQLite (`src/backend/data/finanzas.db`).

Actualmente, **no existe ningún mecanismo visual e interactivo dentro de la aplicación para respaldar o restaurar esta información**. Los usuarios que desean poner a salvo sus datos, cambiar de equipo o recuperarse de un fallo deben acceder manualmente a los archivos del sistema operativo o a los volúmenes de Docker, lo cual supone una fricción considerable y un riesgo evidente de corrupción de datos por copia en caliente sin bloqueo.

El **objetivo** de esta especificación es implementar un sistema completo, robusto y desacoplado de **Copia de Seguridad y Restauración (Backup & Restore)** accesible directamente desde la interfaz gráfica de Streamlit y soportado por una API REST en FastAPI:
1. **Copias en Caliente Consistentes (Online Backup API)**: Generación de backups consistentes y sin corrupción mediante la API nativa `sqlite3.Connection.backup()`, garantizando atomicidad incluso si el sistema se encuentra en ejecución.
2. **Descarga Directa en 1 Clic**: Capacidad de exportar y descargar el archivo de base de datos `.db` directamente al ordenador del usuario a través del navegador.
3. **Restauración Segura con Validación de Integridad**: Subida de archivos `.db` con validación estricta previa (`PRAGMA integrity_check == 'ok'` y presencia de tablas esenciales).
4. **Instantánea Automática de Seguridad Pre-Restauración (*Rollback Safety Net*)**: Antes de sobrescribir la base de datos activa con una restauración, el sistema crea automáticamente una copia instantánea de seguridad para garantizar reversibilidad total ante errores del usuario.
5. **Historial de Instantáneas Locales Rotativas**: Directorio `backups/` gestionado por el servidor que retiene las últimas 5 instantáneas locales, permitiendo restaurar estados anteriores con un solo clic.
6. **Diagnóstico de Salud e Integridad en Interfaz**: Visualización del tamaño de la base de datos, fecha de modificación, estado de integridad de SQLite y recuento de registros por tabla.
7. **Privacidad Absoluta**: Cero consumo de tokens de IA, almacenamiento 100% local y blindaje en `.gitignore` para evitar cualquier fuga de datos patrimoniales al repositorio.

---

## 2. Usuarios y Casos de Uso

- **Usuario Personal / Cotitular del Hogar**:
  - Desea descargar una copia de seguridad mensual de sus finanzas en su disco personal o nube privada.
  - Necesita migrar sus datos financieros a un nuevo ordenador sin manipular manualmente carpetas del sistema.
  - Desea restaurar un estado contable previo si cometió errores graves en la asignación de transacciones o meses anteriores.
  - Desea verificar visualmente que su base de datos está sana e íntegra.
- **Operador del Sistema / Desarrollador**:
  - Cuenta con endpoints REST dedicados en FastAPI para programar copias de seguridad automáticas o auditorías de integridad.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Diagnóstico de Salud de la Base de Datos)**: Como usuario, quiero ver en la interfaz el tamaño actual de mi base de datos, cuándo fue modificada por última vez, el número de transacciones y registros almacenados, y si el archivo pasa el test de integridad de SQLite.
- **HU-2 (Creación y Descarga de Copia de Seguridad)**: Como usuario, quiero poder pulsar un botón para generar y descargar inmediatamente a mi ordenador un archivo de copia de seguridad `.db` con nombre descriptivo y fecha (ej. `finanzas_backup_20261103_093000.db`).
- **HU-3 (Restauración Guiada y Segura)**: Como usuario, quiero poder subir un archivo `.db` de copia de seguridad previa, ver su contenido/validación antes de aplicar y, tras confirmar, que el sistema lo aplique de forma segura creando automáticamente un respaldo previo por si me arrepiento.
- **HU-4 (Historial de Instantáneas Locales)**: Como usuario, quiero tener un listado de las últimas 5 copias automáticas guardadas en el sistema para poder regresar a cualquiera de ellas con un solo clic.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Modelado de Contratos Pydantic v2 (`src/backend/domain/schemas/backup.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE estructurar la información de diagnóstico y copias mediante esquemas fuertemente tipados:
  - `DatabaseHealthResponse`:
    - `status`: Literal `"HEALTHY"`, `"DEGRADED"`, `"CORRUPTED"`.
    - `database_path`: Ruta normalizada del fichero activo.
    - `file_size_bytes`: Tamaño exacto en bytes.
    - `file_size_formatted`: Tamaño legible para humanos (ej. `"1.25 MB"`).
    - `last_modified`: Timestamp ISO-8601 de última escritura.
    - `integrity_check_passed`: Booleano resultante de ejecutar `PRAGMA integrity_check`.
    - `table_counts`: Diccionario con el conteo de filas de tablas clave (`transactions`, `categories`, `subcategories`, `monthly_budgets`, `emergency_fund`, `joint_accounts`, `joint_transactions`, `watchlist`).
  - `BackupMetadata`:
    - `filename`: Nombre del archivo de respaldo (ej. `backup_20261103_093000.db`).
    - `created_at`: Fecha y hora de creación ISO-8601.
    - `file_size_bytes`: Tamaño en bytes.
    - `file_size_formatted`: Tamaño legible.
    - `is_safety_snapshot`: Booleano indicando si fue generado automáticamente antes de una restauración.
  - `BackupListResponse`:
    - `backups`: Lista de `BackupMetadata` ordenados cronológicamente descendente.
    - `total_count`: Número total de instantáneas conservadas.
  - `BackupValidationResult`:
    - `is_valid`: Booleano de validación.
    - `integrity_status`: Resultado de `PRAGMA integrity_check`.
    - `table_counts`: Conteo de tablas detectadas en el archivo inspeccionado.
    - `error_message`: Detalle del fallo en caso de invalidez.
  - `RestoreResponse`:
    - `success`: Booleano de éxito.
    - `message`: Mensaje descriptivo en español.
    - `safety_snapshot_filename`: Nombre del respaldo automático previo generado antes de sobrescribir.
    - `restored_table_counts`: Conteo de filas de las tablas tras la restauración.

### RF-2: Servicio Desacoplado de Backup (`src/backend/services/backup_service.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE gestionar las copias en un directorio dedicado `backups/` en la raíz del proyecto (o ruta configurable vía `BACKUP_DIR`), creándolo automáticamente si no existe.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `create_backup(is_safety_snapshot: bool = False, custom_name: Optional[str] = None)`, EL SISTEMA DEBE:
  1. Conectar a la base de datos activa mediante `sqlite3.connect`.
  2. Abrir una conexión destino hacia el nuevo archivo `backups/<nombre>.db`.
  3. Ejecutar `source_con.backup(target_con)` para realizar una copia atómica y consistente sin bloquear lecturas ni escrituras concurrentes.
  4. Rotar el directorio de backups locales para conservar como máximo las **5 instantáneas más recientes**, eliminando físicamente las más antiguas.
  5. Retornar la ruta del archivo generado.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `validate_backup_file(file_path: Path)`, EL SISTEMA DEBE:
  1. Verificar que el archivo existe y no está vacío.
  2. Conectar en modo solo lectura (`file:...mode=ro`) mediante `sqlite3.connect`.
  3. Ejecutar `PRAGMA integrity_check` y certificar que retorne `"ok"`.
  4. Comprobar que existen las tablas maestras mínimas (`transactions`, `categories`, `monthly_budgets`, `emergency_fund`).
  5. Retornar `BackupValidationResult`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `restore_backup(backup_file_path: Path)`, EL SISTEMA DEBE:
  1. Validar rigurosamente el archivo a restaurar mediante `validate_backup_file`. Si falla, abortar lanzando `ValueError`.
  2. Generar automáticamente una instantánea de seguridad previa (*Pre-restore Safety Snapshot*) con el prefijo `safety_prerestore_*.db` de la base de datos activa.
  3. Desconectar y liberar el pool de conexiones de SQLAlchemy invocando `engine.dispose()`.
  4. Copiar atómicamente el archivo validado sobre `src/backend/data/finanzas.db` mediante `shutil.copy2`.
  5. Ejecutar `init_db()` para reconectar el motor y aplicar migraciones pendientes si las hubiera.
  6. Retornar `RestoreResponse`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `get_database_health()`, EL SISTEMA DEBE inspeccionar el fichero SQLite en disco, ejecutar `PRAGMA integrity_check` y contar las filas de las tablas principales, retornando `DatabaseHealthResponse`.

### RF-3: Router REST en FastAPI (`src/backend/api/routers/backup.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE exponer las siguientes rutas REST bajo el prefijo `/backup`:
  - `GET /backup/health`: Retorna `DatabaseHealthResponse` con el estado y métricas de la base de datos.
  - `POST /backup/create`: Genera una nueva instantánea local en `backups/` y retorna sus metadatos.
  - `GET /backup/download`: Genera una copia atómica caliente al vuelo y la devuelve como stream binario (`FileResponse` con `Content-Disposition: attachment; filename="finanzas_backup_YYYYMMDD_HHMMSS.db"` y media-type `application/x-sqlite3`).
  - `GET /backup/list`: Retorna `BackupListResponse` con las instantáneas locales existentes.
  - `POST /backup/restore/upload`: Acepta un `UploadFile` (.db), valida su integridad, crea el snapshot previo, ejecuta la restauración y retorna `RestoreResponse`.
  - `POST /backup/restore/local/{filename}`: Restaura una de las instantáneas locales guardadas en `backups/`.
  - `DELETE /backup/local/{filename}`: Elimina un backup local específico.

### RF-4: Cliente API y Capa de Presentación en Streamlit (`src/frontend/views/backup_view.py` y `app.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE añadir la pestaña principal **`💾 Base de Datos y Copias de Seguridad`** en el menú de navegación de Streamlit.
- **Criterio EARS (State-driven)**: MIENTRAS se visualice la pestaña de copias de seguridad, EL SISTEMA DEBE estructurar la interfaz en 4 tarjetas visuales premium con diseño responsivo:
  1. **Tarjeta 1: Diagnóstico de Salud de la Base de Datos**:
     - Badges de estado: `🟢 Base de Datos Saludable` o `🔴 Requiere Atención`.
     - Métricas en columnas: Tamaño del fichero en MB, fecha de última modificación, estado de integridad de SQLite (`PRAGMA integrity_check`).
     - Tabla desplegable con el conteo de registros por tabla (Transacciones, Presupuestos, Categorías, Metas de Ahorro, etc.).
  2. **Tarjeta 2: Descargar Copia de Seguridad**:
     - Botón destacado `📥 Descargar Copia de Seguridad (.db)` que descarga directamente el archivo SQLite consistente en el navegador del usuario.
     - Botón secundario `📸 Crear Instantánea Local` para guardar una copia en el historial del servidor sin descargarla.
  3. **Tarjeta 3: Restaurar desde Archivo**:
     - Widget `st.file_uploader` para subir un archivo `.db`.
     - Al seleccionar un archivo, botón *"Inspeccionar y Validar Copia"*, que muestra un resumen de las transacciones y tablas contenidas antes de aplicar nada.
     - Botón de confirmación protegido con advertencia clara (`st.popover` o confirmación explícita) indicando que se creará un snapshot previo automático y se sobrescribirá la base activa.
     - Notificación de éxito y recarga inmediata (`st.rerun()`).
  4. **Tarjeta 4: Historial de Instantáneas Locales**:
     - Tabla con las últimas instantáneas almacenadas en el servidor/contenedor (`backups/`), indicando fecha, tamaño y si fue generada manualmente o por snapshot automático pre-restauración.
     - Acciones por fila: Botón `🔄 Restaurar Esta Copia` (con confirmación) y botón `🗑️ Eliminar`.

### RF-5: Seguridad, Privacidad y Registro en `.gitignore`
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE registrar la carpeta de copias de seguridad locales en `.gitignore`:
  - `backups/`
  - `*.backup`
  - `*.db.bak`
- **Criterio EARS (Unwanted Behaviour)**: EL SISTEMA DEBE rechazar cualquier archivo subido para restaurar que no sea un archivo SQLite válido o cuyo `PRAGMA integrity_check` no devuelva `"ok"`, retornando HTTP 400 Bad Request descriptivo sin modificar en absoluto la base activa.

---

## 5. Casos Límite y Criterios de Aceptación (EARS)

1. **Subida de Archivo Corrupto o No-SQLite**:
   - CUANDO un usuario suba un archivo de texto, una imagen o un archivo binario dañado con extensión `.db`, EL SISTEMA DEBE detectarlo en la fase de validación previa (`validate_backup_file`), rechazar la restauración y mostrar una alerta descriptiva en la UI sin tocar la base activa.
2. **Subida de Base de Datos SQLite Válida pero con Esquema Incorrecto**:
   - CUANDO se suba un archivo SQLite válido pero correspondiente a otra aplicación (sin tablas `transactions` o `categories`), EL SISTEMA DEBE rechazar la restauración indicando qué tablas obligatorias faltan.
3. **Escrituras Concurrentes durante la Creación de Copia**:
   - CUANDO se cree un backup mientras FastAPI está procesando transacciones, EL SISTEMA DEBE emplear `source_con.backup(target_con)` garantizando una instantánea atómica y consistente sin bloqueos de lectura ni escrituras incompletas.
4. **Fallo Inesperado durante el Proceso de Restauración**:
   - SI ocurre un fallo de E/S durante la sustitución del fichero, el snapshot previo generado en `backups/safety_prerestore_*.db` DEBE permanecer intacto para permitir una recuperación manual inmediata.
5. **Rotación de Instantáneas Locales**:
   - EL SISTEMA DEBE limitar el catálogo de instantáneas locales en `backups/` a un máximo de 5, eliminando las más antiguas ordenadas por timestamp.
