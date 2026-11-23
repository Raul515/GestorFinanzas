# Especificación 016: Micro-App Móvil Ligera "Quick-Capture" para Gastos Personales

## 1. Resumen Ejecutivo y Visión

Actualmente, el Gestor de Finanzas Personales se opera principalmente desde la interfaz web de escritorio en Streamlit (`http://localhost:8501`). Si bien Streamlit es excelente para el análisis patrimonial profundo, visualización anual y toma de decisiones estratégicas, resulta poco práctico cuando el usuario se encuentra fuera de casa (en un bar, restaurante, supermercado o gasolinera) y necesita registrar un gasto cotidiano de 2,50 € o 35,00 € en menos de 5 segundos.

El objetivo de la **Especificación 016** es desarrollar una **micro-aplicación móvil ultra-ligera y autónoma (*Quick-Capture*)**, diseñada con los siguientes pilares fundamentales:

1. **Ergonomía Transaccional Móvil (Captura en 5 Segundos)**:
   - Pantalla optimizada para uso con una sola mano en teléfonos móviles (360px - 450px de ancho).
   - Teclado numérico táctil de gran tamaño con botones de importes rápidos (`+1€`, `+2€`, `+5€`, `+10€`, `+20€`).
   - Carrusel de chips de acceso inmediato con las subcategorías de gasto más frecuentes del usuario (ej. *"☕ Café"*, *"🛒 Supermercado"*, *"🍽️ Restaurante"*, *"⛽ Gasolina"*, *"💊 Farmacia"*) más buscador predictivo instantáneo.
   - Guardado inmediato con feedback háptico (vibración corta) y reseteo del formulario en < 100 ms.
2. **Funcionamiento 100% Offline-First en la Calle**:
   - Operativa autónoma en la memoria local del teléfono (IndexedDB / LocalStorage) sin requerir conexión a internet ni acceso al servidor doméstico.
   - Cola interna de salida (*Outbox Queue*) que almacena las transacciones con identificadores únicos UUIDv4 idempotentes (`event_id`).
3. **Sincronización Directa por Wi-Fi Doméstica (Zero-Apps en el Móvil)**:
   - **Sin necesidad de instalar Syncthing en el móvil**: Al llegar a casa y conectarse a la red Wi-Fi local, la micro-app detecta automáticamente el backend en el PC (`http://<ip-pc>:8000`) y vuelca los gastos pendientes en un único lote atómico (`POST /api/mobile/sync`).
   - **Compatibilidad con Syncthing opcional**: Para entornos o usuarios que prefieran sincronización basada en carpetas compartidas, la app mantiene la capacidad de exportar e importar archivos JSON delta (`evt_mob_*.json`) en `sync/mobile/`.
4. **Despliegue Dual: PWA Instantánea + APK de Android**:
   - **Vía PWA (Instantánea en 1 clic)**: El backend FastAPI sirve la aplicación compilada en `http://<ip-pc>:8000/mobile/`. Se instala en la pantalla de inicio de Android (Chrome) o iPhone (Safari) con soporte offline total mediante Service Worker y Web Manifest.
   - **Vía APK de Android (GitHub Actions)**: Pipeline de integración continua en `.github/workflows/build-mobile-apk.yml` que compila el archivo `.apk` nativo mediante Capacitor en la nube y lo entrega listo para sideloading sin exigir la instalación de SDKs pesados en el ordenador local.
5. **Ámbito Acotado a Gastos Personales (MVP) con Arquitectura Extensible**:
   - Para este MVP se capturan exclusivamente **Gastos Personales** (`👤 Personal`), eliminando sobrecargas cognitivas.
   - El código se estructura de forma modular, preparando el soporte futuro para la **Economía del Hogar** (`👥 Hogar / Conjunto`) y vistas analíticas ligeras (`📊 Resumen`, `💬 Copiloto`) sin rehacer el núcleo.

---

## 2. Historias de Usuario (HU)

- **HU-1 (Anotar Gasto en 5 Segundos)**: Como usuario que acaba de pagar un café o el menú del día, quiero abrir la app en mi teléfono, teclear el importe, tocar el chip de la categoría y pulsar "Guardar" en menos de 5 segundos para no postergar ni olvidar el registro contable.
- **HU-2 (Captura Offline en la Calle)**: Como usuario que está en un comercio sin cobertura o fuera de la red de mi casa, quiero poder registrar gastos con normalidad, teniendo la certeza de que quedan guardados de forma segura en la memoria de mi teléfono.
- **HU-3 (Sincronización Automática al Llegar a Casa)**: Como usuario, quiero que al llegar a casa y conectarme a la Wi-Fi doméstica, la app detecte el ordenador y vuelque todos mis gastos pendientes a la base de datos sin tener que instalar aplicaciones secundarias en el móvil ni abrir la web del ordenador.
- **HU-4 (Instalación Inmediata como PWA)**: Como usuario con iPhone o Android, quiero poder escanear un código QR en la pantalla de mi ordenador y añadir la app a mi pantalla de inicio como una aplicación nativa en 10 segundos.
- **HU-5 (Descarga Directa de APK Android)**: Como usuario de Android que prefiere una app empaquetada, quiero poder descargar un archivo `.apk` compilado limpiamente desde GitHub Actions para instalarlo directamente en mi teléfono.
- **HU-6 (Protección contra Duplicados)**: Como usuario, quiero que si por un fallo de red un lote de gastos se reintenta varias veces, el sistema garantice que ninguna transacción se duplique en mi contabilidad.

---

## 3. Requerimientos Funcionales (RF)

### 3.1 Contratos y Esquemas Backend (`src/backend/domain/schemas/mobile.py`)

- **RF-1 (Esquemas Pydantic v2 de Transacción Móvil)**:
  - `MobileTransactionPayload`:
    - `event_id`: str (UUIDv4 obligatorio para deduplicación e idempotencia).
    - `scope`: str (por defecto `"PERSONAL"`, preparado para `"JOINT"` a futuro).
    - `amount`: float (estrictamente > 0).
    - `description`: str (concepto del gasto, 1-200 caracteres).
    - `date`: date (fecha contable, por defecto fecha local).
    - `subcategory_id`: int (ID de la subcategoría en la base de datos local).
    - `subcategory_name`: str (nombre descriptivo de la subcategoría para resiliencia).
    - `created_at_utc`: str (marca de tiempo ISO 8601 UTC de creación en el móvil).
  - `MobileSyncRequest`:
    - `device_id`: str (identificador del teléfono móvil emisor).
    - `transactions`: List[MobileTransactionPayload].
  - `MobileSyncResponse`:
    - `success`: bool.
    - `processed_count`: int.
    - `ignored_duplicates_count`: int.
    - `server_timestamp_utc`: str.
  - `MobileCatalogResponse`:
    - `device_id`: str (ID del host local).
    - `last_updated_utc`: str.
    - `personal_subcategories`: List[dict] (con id, name, category_id, category_name e `is_frequent` booleano).
    - `frequent_concepts`: List[str] (los 15 conceptos más repetidos en los últimos 3 meses).

### 3.2 Capa de Servicio Backend (`src/backend/services/mobile_sync_service.py`)

- **RF-2 (Generador y Caché del Catálogo Móvil)**:
  - Método `get_mobile_catalog(db: Session) -> MobileCatalogResponse`:
    - Recupera todas las subcategorías activas agrupadas por Necesidades Básicas (50%), Deseos (30%) y Ahorro e Inversión (20%).
    - Consulta las transacciones de los últimos 90 días para identificar las 6 subcategorías con mayor número de operaciones y marcarlas con `is_frequent = True` (para los chips rápidos del móvil).
    - Extrae los 15 conceptos más recurrentes para sugerencias de texto en el formulario móvil.
- **RF-3 (Ingesta Atómica y Deduplicación Idempotente)**:
  - Método `process_mobile_sync(db: Session, request: MobileSyncRequest) -> MobileSyncResponse`:
    - Inicia una transacción atómica en SQLite.
    - Para cada `item` en `request.transactions`:
      - Comprueba si el `event_id` ya fue procesado o si existe una transacción con idéntica fecha, subcategoría, importe y concepto exacto creado en la misma ventana temporal.
      - Si ya existe, se incrementa `ignored_duplicates_count` y se omite.
      - Si es nueva, se inserta una entidad `Transaction` (con fecha, subcategoría, importe, concepto).
    - Ejecuta `db.commit()` garantizando persistencia atómica.
    - Si ocurre un error, ejecuta `db.rollback()` e informa en los logs estructurados con nivel `logger.error` (Principio 13).
- **RF-4 (Soporte Opcional de Ingesta por Ficheros para Syncthing)**:
  - Método `process_mobile_inbox_folder(db: Session, inbox_dir: Path) -> int`:
    - Examina la carpeta `sync/mobile/inbox/`.
    - Lee e ingesta ficheros `evt_mob_*.json`, archivándolos tras su procesamiento en `sync/mobile/processed/` o `sync/mobile/error/`.

### 3.3 Endpoints REST de FastAPI (`src/backend/api/routers/mobile.py`)

- **RF-5 (Endpoints Móviles en `/api/mobile`)**:
  - `GET /api/mobile/catalog`: Retorna el catálogo completo con cabeceras de caché `ETag` / `Cache-Control`.
  - `POST /api/mobile/sync`: Recibe `MobileSyncRequest` y devuelve `MobileSyncResponse`.
  - `GET /api/mobile/status`: Retorna estado de salud del backend, fecha/hora del servidor y total de transacciones registradas hoy.
  - `POST /api/mobile/process-folder`: Disparador administrativo para forzar la lectura de la carpeta de sincronización física.

### 3.4 Interfaz de Usuario Móvil en `src/mobile/` (Vite + React 19 + TypeScript + Tailwind)

- **RF-6 (Pantalla de Captura Rápida de Gastos)**:
  - Formulario ultra-rápido:
    - Display de importe prominente en euros (`0,00 €`).
    - Teclado numérico táctil en pantalla optimizado para pulgares.
    - Fila de importes rápidos (`+1€`, `+2€`, `+5€`, `+10€`, `+20€`).
    - Chips horizontales táctiles con las subcategorías frecuentes (`☕ Café`, `🛒 Súper`, `🍽️ Menú`, `⛽ Gasolina`, `💊 Farmacia`).
    - Buscador desplegable modal para seleccionar cualquier otra subcategoría del catálogo.
    - Campo de concepto opcional con sugerencias rápidas.
    - Selector de fecha nativo (por defecto `Hoy`).
    - Botón de guardado grande `[⚡ Guardar Gasto]` que almacena en cola local y limpia el formulario inmediatamente (< 100 ms).
- **RF-7 (Persistencia Offline en el Teléfono)**:
  - Motor de almacenamiento en `IndexedDB` (con fallback transparente a `localStorage`).
  - Cada gasto guardado se encola con estado `PENDING_SYNC` y un UUIDv4 propio.
- **RF-8 (Motor de Sincronización Wi-Fi en el Móvil)**:
  - Comprobador periódico de conectividad (Network Information API / ping suave a `/api/mobile/status`).
  - Al detectar conexión con el backend doméstico, envía automáticamente el lote de gastos pendientes.
  - Indicador visual discreto de estado en la cabecera: `🟢 Sincronizado` o `🟠 3 pendientes`.
  - Botón manual de reintento `[🔄 Sincronizar Ahora]` para forzar el volcado en cualquier momento.
  - Opción de exportar los gastos en un archivo `.json` para copia de seguridad o transferencia manual.

### 3.5 Servidor Web PWA y Panel en Streamlit

- **RF-9 (Alojamiento PWA en FastAPI)**:
  - En `src/backend/api/main.py`: Montar la carpeta `src/mobile/dist` bajo `/mobile` utilizando `StaticFiles(directory=..., html=True)`.
  - Service Worker registrado para funcionamiento sin conexión y `manifest.json` con iconos y colores de tema (`#0f172a`).
- **RF-10 (Tarjeta del Companion Móvil en Streamlit)**:
  - En `src/frontend/app.py` (`⚙️ Ajustes y Sistema` -> `📱 Companion Móvil Quick-Capture`):
    - Detección de la IP local del ordenador en la red Wi-Fi (ej. `http://192.168.1.45:8000/mobile`).
    - Código QR renderizado en pantalla para escanear con la cámara del teléfono y abrir la micro-app en 1 segundo.
    - Enlace a la guía de instalación y enlace de descarga del APK compilado.
    - Visor con las últimas transacciones recibidas desde el móvil.

### 3.6 Mejoras de Productividad y Ergonomía Móvil (Fases 7 a 13)

- **RF-11 (Vista "Mi Mes" y Ejecución Presupuestaria 50/30/20)**:
  - Endpoint `GET /api/mobile/summary` que calcula en tiempo real el presupuesto del mes seleccionado, el gasto total, disponible y progreso en Necesidades (50%), Deseos (30%) y Ahorro (20%), junto con el estado del Fondo de Emergencia en meses cubiertos.
  - Endpoint `POST /api/mobile/budget` que permite reasignar importes presupuestarios por subcategoría desde el teléfono.
  - Pestaña `[📊 Mi Mes]` con interfaz interactiva y edición in-situ.

- **RF-12 (Auto-Actualizador In-App OTA para APK Android)**:
  - Endpoints `GET /api/mobile/version`, `GET /api/mobile/download-apk` y `POST /api/mobile/upload-apk`.
  - Detección automática al abrir la micro-app de nuevas versiones mediante comparación de `version_code`.
  - Banner táctil superior que permite actualizar el APK con 1 tap sin necesidad de reinstalar manualmente.
  - Panel de distribución en Streamlit para publicar nuevos APKs compilados.

- **RF-13 (Historial del Mes con Borrado Seguro Offline/Online)**:
  - Endpoint `DELETE /api/mobile/transactions/{identifier}` que resuelve tanto por `mobile_event_id` como por ID numérico de transacción.
  - Interfaz en `HistoryView` con botón `[🗑️]` y confirmación antes de eliminar.
  - Soporte offline: si no hay conexión con el servidor, el apunte se elimina inmediatamente de la pantalla y el borrado remoto se encola en `gestor_mobile_pending_deletes` para ejecutarse en el siguiente reintento.

- **RF-14 (Semáforo y Alerta Preventiva en Vivo para Techo de Presupuesto de Deseos)**:
  - Cálculo instantáneo en `QuickCaptureView` mientras el usuario teclea el importe: `projectedSpent = wants.spent + inputAmount`.
  - Semáforo reactivo: Verde (< 80%), Amarillo de advertencia (80% - 99.9%) y Rojo de límite superado (>= 100%) con cálculo del sobrecoste en euros antes de guardar.

- **RF-15 (Buscador Instantáneo de Gastos Históricos y Caché Offline)**:
  - Endpoints `GET /api/mobile/transactions/search` y `GET /api/mobile/transactions/history-cache`.
  - Búsqueda táctil a 0 ms sobre las transacciones locales y una caché histórica de 12 meses guardada en el dispositivo.
  - Posibilidad de extender la búsqueda a todo el histórico en el servidor con 1 tap si se está conectado.
  - Píldora `[ÚLTIMO]` para el pago más reciente y formato de fechas estrictamente en `DD/MM/AAAA`.

- **RF-16 (Captura con Foto del Ticket de Compra)**:
  - Botón `[📷 Foto Ticket]` en el formulario de captura.
  - Captura desde la cámara nativa del teléfono con compresión client-side en canvas (< 250 KB en formato JPEG/WebP).
  - Almacenamiento seguro en el servidor bajo `sync/mobile/receipts/` vinculado al `event_id`.

- **RF-17 (Captura de Ingresos Extraordinarios y Bizums)**:
  - Conmutador táctil `[🔴 Gasto | 🟢 Ingreso]` en el formulario de captura rápida.
  - Asignación directa como ingreso contable en el mes activo para registrar bizums recibidos o reembolsos en segundos.

---

## 4. Requerimientos No Funcionales y Restricciones Técnicas

1. **Rendimiento de la App Móvil**:
   - Tiempo de carga inicial (Time-to-Interactive) inferior a 300 ms.
   - Tiempo total para registrar un gasto habitual: < 5 segundos.
2. **Privacidad y Soberanía de Datos (Constitución Principio 10)**:
   - Todo el flujo de datos transcurre de forma 100% local dentro de la red Wi-Fi de la vivienda o mediante archivos cifrados. Ningún dato viaja a servidores externos o nubes de terceros.
3. **Paridad de Código e Idioma (AGENTS.md Directriz 7)**:
   - Todo el código backend, contratos, endpoints y variables en inglés (`MobileTransactionPayload`, `MobileSyncService`, `/api/mobile/sync`).
   - Toda la interfaz móvil, documentación y mensajes al usuario 100% en español.
4. **Idempotencia Absoluta**:
   - Cada movimiento emitido por el teléfono cuenta con un UUIDv4 generado en el momento del guardado. Ningún fallo o reintento de sincronización puede provocar un doble apunte contable.
