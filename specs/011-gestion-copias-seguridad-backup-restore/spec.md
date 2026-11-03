# Especificación 011: Gestión y Copias de Seguridad de Base de Datos en Interfaz (Backup & Restore)

## 1. Resumen Ejecutivo y Visión

El **Gestor de Finanzas Personales** almacena la totalidad de los datos contables y patrimoniales del usuario (transacciones mensuales, categorías 50/30/20, presupuestos base, fondo de emergencia, estrategias compensatorias, lista de seguimiento de valores y configuración del hogar multiperfil) en una base de datos local SQLite (`src/backend/data/finanzas.db`).

Actualmente, **no existe ningún mecanismo visual e interactivo dentro de la aplicación para respaldar o restaurar esta información**. Los usuarios que desean poner a salvo sus datos, cambiar de equipo o recuperarse de un fallo deben acceder manualmente a los archivos del sistema operativo o a los volúmenes de Docker, lo cual supone una fricción considerable y un riesgo evidente de corrupción de datos por copia en caliente sin bloqueo. Asimismo, el usuario debe recordar respaldar manualmente sus finanzas, sin contar con la posibilidad de programar respaldos periódicos automáticos ni con una red de seguridad si comete un error al restaurar.

El **objetivo** de esta especificación es implementar un sistema completo, robusto, defensivo y desacoplado de **Copia de Seguridad y Restauración (Backup & Restore)** accesible directamente desde la interfaz gráfica de Streamlit y soportado por una API REST en FastAPI:
1. **Copias en Caliente Consistentes (Online Backup API)**: Generación de backups consistentes y sin corrupción mediante la API nativa `sqlite3.Connection.backup()`, garantizando atomicidad y checkpoint del WAL incluso si el sistema se encuentra en ejecución.
2. **Descarga Directa en 1 Clic**: Capacidad de exportar y descargar el archivo de base de datos `.db` directamente al ordenador del usuario a través del navegador.
3. **Restauración Segura con Validación de Integridad**: Subida de archivos `.db` con validación estricta previa (`PRAGMA integrity_check == 'ok'` y presencia de tablas esenciales).
4. **Protección contra Corrupción WAL (`-wal` y `-shm`)**: Purga obligatoria de cualquier archivo residual de Write-Ahead Logging antes de la sobrescritura del fichero `.db`, evitando corrupciones catastróficas al arrancar la nueva base de datos.
5. **Instantánea Automática de Seguridad Pre-Restauración (*Rollback Safety Net*)**: Antes de sobrescribir la base de datos activa con una restauración, el sistema crea automáticamente una copia instantánea de seguridad (`safety_prerestore_*.db`).
6. **Deshacer Restauración en 1 Clic (*One-Click Rollback*)**: Banner destacado en la interfaz tras una restauración permitiendo revertir al estado previo en un clic si el usuario restauró un archivo por error.
7. **Auto-Migración Retrocompatible Inmediata**: Ejecución automática de `init_db()` tras la restauración para aplicar migraciones pendientes si se restaura un backup de versiones anteriores del esquema.
8. **Programación Periódica Inteligente (Frecuencia en Días/Semanas/Meses)**: Configuración personalizada de la periodicidad (ej. semanal / 7 días, quincenal / 14 días, mensual / 30 días o N días personalizados) con ejecución en segundo plano y visualización de la próxima fecha estimada.
9. **Detección de Duplicados por Hash SHA-256**: Comprobación del hash de la base de datos para no malgastar ranuras de rotación si la base no ha experimentado cambios desde la última copia automática.
10. **Historial de Instantáneas Locales Rotativas**: Directorio `backups/` gestionado por el servidor que retiene un número configurable de instantáneas locales (por defecto 5, configurable entre 3 y 20).
11. **Persistencia Docker Garantizada**: Mapeo explícito del volumen `backups/` en Docker Compose para que los respaldos sobrevivan a reinicios y rebuilds.
12. **Diagnóstico de Salud e Integridad en Interfaz**: Visualización del tamaño de la base de datos, fecha de modificación, estado de integridad de SQLite y recuento de registros por tabla.
13. **Privacidad Absoluta**: Cero consumo de tokens de IA, almacenamiento 100% local y blindaje en `.gitignore` para evitar cualquier fuga de datos patrimoniales al repositorio.

---

## 2. Usuarios y Casos de Uso

- **Usuario Personal / Cotitular del Hogar**:
  - Desea descargar una copia de seguridad periódica de sus finanzas en su disco personal o nube privada.
  - Necesita programar que la aplicación genere copias de seguridad automáticas cada X días/semanas sin tener que recordarlo.
  - Desea restaurar un estado contable previo si cometió errores graves, contando con un botón de deshacer inmediato si la restauración no era la deseada.
  - Necesita migrar sus datos financieros a un nuevo ordenador sin manipular manualmente carpetas del sistema.
  - Desea verificar visualmente que su base de datos está sana e íntegra.
- **Operador del Sistema / Desarrollador**:
  - Cuenta con endpoints REST dedicados en FastAPI para programar copias de seguridad automáticas, rollbacks o auditorías de integridad.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Diagnóstico de Salud de la Base de Datos)**: Como usuario, quiero ver en la interfaz el tamaño actual de mi base de datos, cuándo fue modificada por última vez, el número de transacciones y registros almacenados, y si el archivo pasa el test de integridad de SQLite.
- **HU-2 (Creación y Descarga de Copia de Seguridad)**: Como usuario, quiero poder pulsar un botón para generar y descargar inmediatamente a mi ordenador un archivo de copia de seguridad `.db` con nombre descriptivo y fecha (ej. `finanzas_backup_20261103_093000.db`).
- **HU-3 (Restauración Guiada y Segura)**: Como usuario, quiero poder subir un archivo `.db` de copia de seguridad previa, ver su contenido/validación antes de aplicar y, tras confirmar, que el sistema lo aplique de forma segura creando automáticamente un respaldo previo por si me arrepiento.
- **HU-4 (Deshacer Restauración en 1 Clic / Rollback)**: Como usuario, si me he equivocado de archivo al restaurar, quiero poder pulsar un botón de «Deshacer Restauración» para volver de inmediato al estado anterior sin perder nada.
- **HU-5 (Historial de Instantáneas Locales)**: Como usuario, quiero tener un listado de las últimas copias guardadas en el sistema para poder regresar a cualquiera de ellas con un solo clic.
- **HU-6 (Programación y Frecuencia de Copias Automáticas)**: Como usuario, quiero configurar la periodicidad de las copias automáticas (cada semana, cada 2 semanas, cada mes, o cada N días) y el límite de copias a retener, viendo cuándo se hizo la última copia y cuándo se generará la próxima.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Modelado de Contratos Pydantic v2 y Entidad ORM (`src/backend/domain/schemas/backup.py` y `src/backend/domain/models/backup.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE estructurar la información mediante contratos Pydantic v2 y una entidad SQLAlchemy:
  - Entidad ORM `BackupScheduleConfig`:
    - `id`: Entero (clave primaria singleton `id=1`).
    - `enabled`: Booleano (por defecto `True`).
    - `frequency_days`: Entero (por defecto `14` días, quincenal; configurable).
    - `keep_max_copies`: Entero (por defecto `5`, rango permitido `3` a `20`).
    - `last_automated_backup_at`: `DateTime` en UTC (opcional, `None` al inicio).
    - `last_backup_sha256`: String (hash SHA-256 de la base en la última copia automática, para evitar duplicados).
    - `updated_at`: `DateTime` en UTC.
  - Esquema `DatabaseHealthResponse`:
    - `status`: Literal `"HEALTHY"`, `"DEGRADED"`, `"CORRUPTED"`.
    - `database_path`: Ruta normalizada del fichero activo.
    - `file_size_bytes`: Tamaño exacto en bytes.
    - `file_size_formatted`: Tamaño legible para humanos (ej. `"1.25 MB"`).
    - `sha256`: Hash SHA-256 de la base activa.
    - `last_modified`: Timestamp ISO-8601 de última escritura.
    - `integrity_check_passed`: Booleano resultante de ejecutar `PRAGMA integrity_check`.
    - `table_counts`: Diccionario con el conteo de filas de tablas clave (`transactions`, `categories`, `subcategories`, `monthly_budgets`, `emergency_fund`, `joint_accounts`, `joint_transactions`, `watchlist`).
  - Esquema `BackupMetadata`:
    - `filename`: Nombre del archivo de respaldo (ej. `manual_backup_20261103_093000.db`).
    - `created_at`: Fecha y hora de creación ISO-8601.
    - `file_size_bytes`: Tamaño en bytes.
    - `file_size_formatted`: Tamaño legible.
    - `sha256`: Hash SHA-256 del fichero de copia.
    - `backup_type`: Literal `"MANUAL"`, `"AUTOMATIC"`, `"SAFETY_PRERESTORE"`.
  - Esquema `BackupListResponse`:
    - `backups`: Lista de `BackupMetadata` ordenados cronológicamente descendente.
    - `total_count`: Número total de instantáneas conservadas.
    - `latest_safety_snapshot`: Nombre del último snapshot pre-restauración disponible para rollback (si existe).
  - Esquema `BackupValidationResult`:
    - `is_valid`: Booleano de validación.
    - `integrity_status`: Resultado de `PRAGMA integrity_check`.
    - `table_counts`: Conteo de tablas detectadas en el archivo inspeccionado.
    - `sha256`: Hash SHA-256 del archivo subido.
    - `error_message`: Detalle del fallo en caso de invalidez.
  - Esquema `RestoreResponse`:
    - `success`: Booleano de éxito.
    - `message`: Mensaje descriptivo en español.
    - `safety_snapshot_filename`: Nombre del respaldo automático previo generado antes de sobrescribir.
    - `can_rollback`: Booleano indicando si es posible deshacer la restauración.
    - `restored_table_counts`: Conteo de filas de las tablas tras la restauración y auto-migración.
  - Esquema `BackupScheduleResponse`:
    - `enabled`: Booleano.
    - `frequency_days`: Entero.
    - `keep_max_copies`: Entero.
    - `last_automated_backup_at`: Timestamp ISO-8601 o `None`.
    - `next_backup_estimated_at`: Timestamp ISO-8601 o `None`.
  - Esquema `BackupScheduleUpdate`:
    - `enabled`: Booleano.
    - `frequency_days`: Entero con validación `ge=1, le=365`.
    - `keep_max_copies`: Entero con validación `ge=3, le=20`.

### RF-2: Servicio Desacoplado de Backup y Seguridad Antiorrupción (`src/backend/services/backup_service.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE gestionar las copias en un directorio dedicado `backups/` en la raíz del proyecto (o ruta configurable vía `BACKUP_DIR`), creándolo automáticamente si no existe.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `create_backup(backup_type: str = "MANUAL", custom_name: Optional[str] = None)`, EL SISTEMA DEBE:
  1. Conectar a la base de datos activa mediante `sqlite3.connect`.
  2. Abrir una conexión destino hacia el nuevo archivo `backups/<nombre>.db` (usando prefijos distintivos: `auto_backup_*` para automáticas, `safety_prerestore_*` para pre-restauraciones, `manual_backup_*` para manuales).
  3. Ejecutar `source_con.backup(target_con)` para realizar una copia atómica, consistente y con checkpoint del WAL sin bloquear lecturas ni escrituras concurrentes.
  4. Rotar el directorio de backups locales para conservar como máximo las `keep_max_copies` instantáneas más recientes, eliminando físicamente las más antiguas.
  5. Retornar la ruta del archivo generado y sus metadatos.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `validate_backup_file(file_path: Path)`, EL SISTEMA DEBE:
  1. Verificar que el archivo existe y no está vacío.
  2. Conectar en modo solo lectura (`file:...mode=ro`) mediante `sqlite3.connect`.
  3. Ejecutar `PRAGMA integrity_check` y certificar que retorne `"ok"`.
  4. Comprobar que existen las tablas maestras mínimas (`transactions`, `categories`, `monthly_budgets`, `emergency_fund`).
  5. Calcular y retornar el hash SHA-256 junto con el conteo de tablas en `BackupValidationResult`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `restore_backup(backup_file_path: Path)`, EL SISTEMA DEBE ejecutar el protocolo estricto de seguridad:
  1. Validar rigurosamente el archivo a restaurar mediante `validate_backup_file`. Si falla, abortar lanzando `ValueError`.
  2. Generar automáticamente una instantánea de seguridad previa (*Pre-restore Safety Snapshot*) con el prefijo `safety_prerestore_*.db` de la base de datos activa antes de tocar nada.
  3. Desconectar y liberar el pool de conexiones de SQLAlchemy invocando `engine.dispose()`.
  4. **Purga defensiva de WAL**: Eliminar del disco los archivos residuales de Write-Ahead Log (`finanzas.db-wal` y `finanzas.db-shm`) si existen, para evitar desajustes o corrupción al arrancar la nueva base.
  5. Copiar atómicamente el archivo validado sobre `src/backend/data/finanzas.db` mediante `shutil.copy2`.
  6. Ejecutar `init_db()` para reconectar el motor y aplicar automáticamente migraciones de esquema pendientes (compatibilidad hacia atrás total con backups antiguos).
  7. Retornar `RestoreResponse`.
- **Criterio EARS (Event-driven)**: CUANDO se invoque `rollback_last_restore()`, EL SISTEMA DEBE buscar la última instantánea `safety_prerestore_*.db` en `backups/` y ejecutar la restauración sobre ella, devolviendo el sistema al estado inmediatamente anterior.
- **Criterio EARS (Event-driven)**: CUANDO se ejecute el chequeo periódico `check_and_run_scheduled_backup(db: Session)`, EL SISTEMA DEBE:
  1. Consultar la configuración `BackupScheduleConfig`. Si `enabled == False`, no hacer nada.
  2. Comprobar si `last_automated_backup_at` es `None` o si `now - last_automated_backup_at >= timedelta(days=frequency_days)`.
  3. Si corresponde por fecha, calcular el hash SHA-256 de la base activa. Si coincide con `last_backup_sha256`, actualizar la fecha de comprobación sin generar un archivo duplicado idéntico.
  4. Si hay cambios, ejecutar `create_backup(backup_type="AUTOMATIC")`, actualizar `last_automated_backup_at = now` y `last_backup_sha256 = hash` en SQLite y registrar el evento en `logs/backend.log`.

### RF-3: Router REST en FastAPI (`src/backend/api/routers/backup.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE exponer las siguientes rutas REST bajo el prefijo `/backup`:
  - `GET /backup/health`: Retorna `DatabaseHealthResponse` con el estado, integridad y hash de la base de datos.
  - `POST /backup/create`: Genera una nueva instantánea local en `backups/` y retorna sus metadatos.
  - `GET /backup/download`: Genera una copia atómica caliente al vuelo y la devuelve como stream binario (`FileResponse` con `Content-Disposition: attachment; filename="finanzas_backup_YYYYMMDD_HHMMSS.db"` y media-type `application/x-sqlite3`).
  - `GET /backup/list`: Retorna `BackupListResponse` con las instantáneas locales existentes y el nombre del snapshot disponible para rollback.
  - `POST /backup/restore/upload`: Acepta un `UploadFile` (.db), valida su integridad, purga WAL, crea el snapshot previo, ejecuta la restauración, aplica `init_db()` y retorna `RestoreResponse`.
  - `POST /backup/restore/local/{filename}`: Restaura una de las instantáneas locales guardadas en `backups/`.
  - `POST /backup/restore/rollback`: Deshace la última restauración aplicando el snapshot previo de seguridad en 1 clic.
  - `DELETE /backup/local/{filename}`: Elimina un backup local específico.
  - `GET /backup/schedule`: Retorna `BackupScheduleResponse` con la configuración de periodicidad y la próxima fecha estimada.
  - `PUT /backup/schedule`: Recibe `BackupScheduleUpdate`, actualiza la configuración y retorna la programación actualizada.
- **Criterio EARS (Event-driven)**: Al arrancar FastAPI (`lifespan`), EL SISTEMA DEBE invocar de forma no bloqueante una verificación inicial de copia programada vencida y lanzar una tarea periódica en segundo plano (`asyncio.create_task`) que revise cada 1 hora si corresponde ejecutar un respaldo automático.

### RF-4: Cliente API y Capa de Presentación en Streamlit (`src/frontend/views/backup_view.py` y `app.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE añadir la pestaña principal **`💾 Base de Datos y Copias de Seguridad`** en el menú de navegación de Streamlit.
- **Criterio EARS (State-driven)**: MIENTRAS se visualice la pestaña de copias de seguridad, EL SISTEMA DEBE estructurar la interfaz en tarjetas visuales premium con diseño responsivo:
  1. **Tarjeta 1: Diagnóstico de Salud de la Base de Datos**:
     - Badges de estado: `🟢 Base de Datos Saludable` o `🔴 Requiere Atención`.
     - Métricas en columnas: Tamaño del fichero en MB, fecha de última modificación, estado de integridad de SQLite (`PRAGMA integrity_check`) y Hash SHA-256 corto.
     - Desplegable con el conteo de registros por tabla (Transacciones, Presupuestos, Categorías, Metas de Ahorro, etc.).
  2. **Tarjeta 2: Descargar y Crear Copias de Seguridad**:
     - Botón destacado `📥 Descargar Copia de Seguridad (.db)` que descarga directamente el archivo SQLite consistente en el navegador del usuario.
     - Botón secundario `📸 Crear Instantánea Local Ahora` para guardar una copia en el historial del servidor sin descargarla.
  3. **Tarjeta 3: Programación de Copias Automáticas Periódicas**:
     - Switch interactivo: `Habilitar copias automáticas periódicas`.
     - Selector de Frecuencia:
       - *"Semanal (cada 7 días)"*
       - *"Quincenal (cada 14 días)"*
       - *"Mensual (cada 30 días)"*
       - *"Personalizada (cada N días)"* con input numérico (1 a 365 días).
     - Selector de Retención: Máximo de instantáneas a conservar (3 a 20 copias).
     - Información en tiempo real:
       - *"Última copia automática:"* `DD/MM/AAAA HH:MM` (o *"Ninguna todavía"*).
       - *"Próxima copia estimada:"* `DD/MM/AAAA`.
     - Botón `💾 Guardar Configuración de Programación`.
  4. **Tarjeta 4: Restaurar desde Archivo y Deshacer**:
     - Banner de Rollback (si hubo una restauración reciente): *«¿La última restauración no era la esperada? [↩️ Deshacer y Volver al Estado Anterior en 1 Clic]»*.
     - Widget `st.file_uploader` para subir un archivo `.db`.
     - Al seleccionar un archivo, botón *"Inspeccionar y Validar Copia"*, que muestra un resumen de las transacciones y tablas contenidas antes de aplicar nada.
     - Botón de confirmación protegido con advertencia clara (`st.popover` o confirmación explícita) indicando que se creará un snapshot previo automático y se sobrescribirá la base activa.
     - Notificación de éxito y recarga inmediata (`st.rerun()`).
  5. **Tarjeta 5: Historial de Instantáneas Locales**:
     - Tabla con las últimas instantáneas almacenadas en el servidor/contenedor (`backups/`), indicando fecha, tamaño, hash SHA-256 y tipo de copia (Manual, Automática o Snapshot Pre-Restauración).
     - Acciones por fila: Botón `🔄 Restaurar Esta Copia` (con confirmación protegida) y botón `🗑️ Eliminar`.

### RF-5: Seguridad, Privacidad y Persistencia Docker
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE registrar la carpeta de copias de seguridad locales en `.gitignore`:
  - `backups/`
  - `*.backup`
  - `*.db.bak`
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE declarar el volumen persistente en `docker_local/docker-compose.yml`:
  - `- ../backups:/app/backups` para el servicio `backend`.
- **Criterio EARS (Unwanted Behaviour)**: EL SISTEMA DEBE rechazar cualquier archivo subido para restaurar que no sea un archivo SQLite válido o cuyo `PRAGMA integrity_check` no devuelva `"ok"`, retornando HTTP 400 Bad Request descriptivo sin modificar en absoluto la base activa.

---

## 5. Casos Límite y Criterios de Aceptación (EARS)

1. **Subida de Archivo Corrupto o No-SQLite**:
   - CUANDO un usuario suba un archivo de texto, una imagen o un archivo binario dañado con extensión `.db`, EL SISTEMA DEBE detectarlo en la fase de validación previa (`validate_backup_file`), rechazar la restauración y mostrar una alerta descriptiva en la UI sin tocar la base activa.
2. **Subida de Base de Datos SQLite Válida pero con Esquema Incorrecto**:
   - CUANDO se suba un archivo SQLite válido pero correspondiente a otra aplicación (sin tablas `transactions` o `categories`), EL SISTEMA DEBE rechazar la restauración indicando qué tablas obligatorias faltan.
3. **Existencia de Archivos WAL (`-wal`, `-shm`) durante la Restauración**:
   - CUANDO se ejecute una restauración sobre una base activa en modo WAL, EL SISTEMA DEBE purgar físicamente los ficheros `finanzas.db-wal` y `finanzas.db-shm` antes de copiar el nuevo fichero, garantizando que SQLite no intente aplicar un registro incompatible.
4. **Restauración de Copias de Seguridad Antiguas (Auto-Migración)**:
   - CUANDO se restaure una copia de seguridad generada en versiones anteriores del software (sin columnas añadidas posteriormente), EL SISTEMA DEBE ejecutar automáticamente `init_db()` inmediatamente tras la sustitución del fichero, aplicando las migraciones necesarias sin requerir intervención manual.
5. **Escrituras Concurrentes durante la Creación de Copia**:
   - CUANDO se cree un backup mientras FastAPI está procesando transacciones, EL SISTEMA DEBE emplear `source_con.backup(target_con)` garantizando una instantánea atómica, consistente y con checkpoint del WAL sin bloqueos de lectura ni escrituras incompletas.
6. **Servidor Apagado durante el Vencimiento de una Copia Programada**:
   - CUANDO el servidor arranque tras haber estado apagado durante más días que el intervalo configurado (ej. apagado 20 días con frecuencia semanal de 7 días), EL SISTEMA DEBE detectar inmediatamente en el hook de inicio que la copia está vencida y generar el respaldo automático pendiente sin demoras.
7. **Base de Datos sin Modificaciones durante Intervalos Programados**:
   - SI transcurre el intervalo configurado pero el hash SHA-256 de la base de datos coincide exactamente con `last_backup_sha256`, EL SISTEMA DEBE omitir la creación de un fichero duplicado idéntico, reteniendo las ranuras de rotación para estados con cambios reales.
8. **Deshacer una Restauración Errónea (Rollback Seguro)**:
   - CUANDO el usuario pulse `[↩️ Deshacer Restauración]`, EL SISTEMA DEBE restaurar de forma atómica el snapshot previo `safety_prerestore_*.db`, devolviendo la base de datos con éxito al estado previo a la restauración.
9. **Rotación de Instantáneas Locales**:
   - EL SISTEMA DEBE limitar el catálogo de instantáneas locales en `backups/` a la cantidad configurada en `keep_max_copies`, eliminando las más antiguas ordenadas por timestamp.
