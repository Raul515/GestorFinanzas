# Plan de Desarrollo: Especificación 016 — Micro-App Móvil Ligera "Quick-Capture" (Gastos Personales)

## 1. Arquitectura y Estrategia de Ejecución

Siguiendo las directrices de `docs/constitution.md` y `AGENTS.md`, la especificación se desarrolla de forma estrictamente secuencial en **13 fases** (MVP inicial en Fases 1 a 6 + Mejoras de Productividad y Ergonomía Móvil en Fases 7 a 13). Cada fase se verifica con pruebas automatizadas completas antes de solicitar confirmación al usuario para avanzar a la siguiente.

```
Rama de trabajo: feat/spec-016-micro-app-movil-quick-capture
[x] Fase 1: Backend — Esquemas de Datos y Servicio de Sincronización Móvil (MobileSyncService)
[x] Fase 2: Backend — Router REST, Endpoints Móviles y Servidor PWA Estático
[x] Fase 3: Frontend Móvil — Micro-App Quick-Capture (UX en 5 Segundos con Vite + React + Tailwind)
[x] Fase 4: Persistencia Offline Móvil y Motor de Sincronización Wi-Fi (IndexedDB y Auto-Flush)
[x] Fase 5: Empaquetado Android APK con Capacitor y Automatización CI/CD en GitHub Actions
[x] Fase 6: Integración en Streamlit (Código QR, Monitor de Sincronización) y Verificación E2E
[x] Fase 7: Pestaña "Mi Mes" con Ejecución Presupuestaria 50/30/20, Fondo de Emergencia y Ajuste Rápido
[x] Fase 8: Auto-Actualizador In-App OTA para APK y Panel de Distribución
[x] Fase 9: Historial del Mes con Borrado Seguro Offline/Online y Endpoints de Eliminación
[x] Fase 10: Semáforo y Alerta Preventiva en Vivo para Techo de Presupuesto de Deseos (30%)
[x] Fase 11: Buscador Instantáneo de Gastos Históricos ("¿Cuánto me costó...?") y Caché Offline
[ ] Fase 12: Captura Rápida con Foto del Ticket de Compra (Cámara del Teléfono)
[ ] Fase 13: Captura Rápida de Ingresos Extraordinarios y Bizums Recibidos
Fusión final: Merge en develop tras 100% de tests y validación completa
```

---

## 2. Desglose de Fases

### Fase 1: Backend — Esquemas de Datos y Servicio de Sincronización Móvil (`MobileSyncService`)
- **Objetivo**: Crear los contratos fuertemente tipados con Pydantic v2 y la lógica de negocio desacoplada para la ingesta de transacciones personales y el catálogo de subcategorías frecuentes.
- **Entregables**:
  1. `src/backend/domain/schemas/mobile.py`:
     - Esquemas: `MobileTransactionPayload`, `MobileSyncRequest`, `MobileSyncResponse`, `MobileCatalogSubcategory`, `MobileCatalogResponse`.
  2. `src/backend/services/mobile_sync_service.py`:
     - `get_mobile_catalog(db: Session)`: Análisis de frecuencia en los últimos 90 días para subcategorías top y conceptos recurrentes.
     - `process_mobile_sync(db: Session, request: MobileSyncRequest)`: Ingesta atómica en `transactions` con deduplicación por UUID e idempotencia.
     - `process_mobile_inbox_folder(db: Session, inbox_dir: Path)`: Ingesta complementaria de archivos JSON en `sync/mobile/inbox/` para Syncthing.
  3. Pruebas: Batería de pruebas unitarias en `tests/unit/test_mobile_sync_service.py`.

### Fase 2: Backend — Router REST, Endpoints Móviles y Servidor PWA Estático
- **Objetivo**: Exponer los endpoints HTTP en FastAPI para la comunicación con la app móvil y configurar el montaje de la PWA estática.
- **Entregables**:
  1. `src/backend/api/routers/mobile.py`:
     - `GET /api/mobile/catalog`: Descarga del catálogo para inicialización offline.
     - `POST /api/mobile/sync`: Ingesta de lote de gastos pendientes desde el teléfono.
     - `GET /api/mobile/status`: Estado de conectividad y métricas rápidas.
     - `POST /api/mobile/process-folder`: Disparador de ingesta de carpetas Syncthing.
  2. `src/backend/api/main.py`:
     - Registro del router `mobile`.
     - Montaje de archivos estáticos de la PWA en `/mobile`.
     - Worker en lifespan `run_mobile_sync_checker()` con sondeo no bloqueante.
  3. Pruebas: Pruebas de integración de API en `tests/integration/test_mobile_api.py`.

### Fase 3: Frontend Móvil — Micro-App Quick-Capture (UX en 5 Segundos)
- **Objetivo**: Desarrollar la aplicación cliente web ultra-rápida y táctil en `src/mobile/`.
- **Entregables**:
  1. Proyecto base en `src/mobile/`:
     - `package.json` configurado con dependencias ligeras (Vite, React 19, TypeScript, Tailwind CSS, Lucide Icons).
     - `index.html` optimizado para viewport móvil (`viewport-fit=cover`, meta tags PWA).
  2. Componentes principales en `src/mobile/src/`:
     - `NumericKeypad.tsx`: Teclado numérico grande táctil con importes rápidos (`+1€`, `+2€`, etc.).
     - `CategoryChips.tsx`: Carrusel táctil con las 5-6 subcategorías más frecuentes y buscador modal para el resto.
     - `ConceptInput.tsx`: Campo de concepto rápido con chips de autocompletado.
     - `QuickCaptureView.tsx`: Formulario unificado con botón prominente `[⚡ Guardar Gasto]` y feedback háptico.
     - `HistoryView.tsx`: Vista secundaria con la cola de gastos pendientes y gastos del mes.
     - Barra de navegación inferior minimalista (`⚡ Captura` y `📋 Historial`).

### Fase 4: Persistencia Offline Móvil y Motor de Sincronización Wi-Fi
- **Objetivo**: Asegurar el funcionamiento 100% offline y la sincronización automática al conectarse a la red Wi-Fi de casa.
- **Entregables**:
  1. `src/mobile/src/services/storage.ts`:
     - Persistencia de transacciones en `IndexedDB` con estados (`PENDING_SYNC`, `SYNCED`).
     - Almacenamiento local del catálogo de subcategorías para uso offline sin red.
  2. `src/mobile/src/services/sync.ts`:
     - Detección de red y sondeo suave al backend local.
     - Función `flushPendingTransactions()` que vuelca la cola local contra `/api/mobile/sync`.
     - Botón manual `[🔄 Sincronizar Ahora]`.
     - Exportador de copia de seguridad local en JSON.
  3. Manifiesto y Service Worker de PWA (`public/manifest.json`, iconos y registro de SW).

### Fase 5: Empaquetado Android APK con Capacitor y Pipeline CI/CD en GitHub Actions
- **Objetivo**: Habilitar la compilación automática del archivo `.apk` instalable sin recargar el ordenador del usuario.
- **Entregables**:
  1. `src/mobile/capacitor.config.ts`: Configuración para Android (`appId: "com.gestorfinanzas.mobile"`).
  2. Inicialización de la carpeta del proyecto Android en `src/mobile/android/`.
  3. `.github/workflows/build-mobile-apk.yml`:
     - Flujo de GitHub Actions con Java 17, Android SDK y Gradle.
     - Tarea `assembleDebug` que compila el APK y lo publica como artefacto descargable.
  4. Guía ilustrada en `docs/guia_companion_movil.md`:
     - Paso a paso para instalación como PWA en 10 segundos (iOS y Android).
     - Paso a paso para descarga e instalación directa del APK (Android sideloading).
     - Configuración opcional con Syncthing.

### Fase 6: Integración en Streamlit (Código QR y Monitor) y Verificación E2E
- **Objetivo**: Conectar la micro-app con el panel de ajustes de escritorio en Streamlit y validar el flujo completo.
- **Entregables**:
  1. En `src/frontend/app.py` (`⚙️ Ajustes y Sistema` -> `📱 Companion Móvil Quick-Capture`):
     - Detección de IP local en la red Wi-Fi.
     - Renderizado de código QR para escanear y abrir la app al instante.
     - Enlace de descarga del APK e instrucciones rápidas.
     - Monitor con las últimas transacciones recibidas desde el móvil.
  2. Batería de pruebas E2E automatizada en `tests/integration/test_mobile_e2e_flow.py`:
     - Simulación de creación de gastos móviles offline -> envío de lote HTTP -> inserción en SQLite -> verificación contable.

---

### Fase 7: Pestaña "Mi Mes" con Ejecución Presupuestaria 50/30/20, Fondo de Emergencia y Ajuste Rápido (Completada)
- **Objetivo**: Dar visibilidad presupuestaria instantánea al usuario directamente en el móvil para que sepa cuánto puede gastar antes de tomar decisiones.
- **Entregables**:
  1. `src/backend/domain/schemas/mobile.py`: Esquemas `MobileMonthlySummaryResponse`, `MobileCategorySummary`, `MobileEmergencyFundSummary`, `MobileBudgetUpdate`.
  2. `src/backend/services/mobile_sync_service.py`: Cálculo de ejecución 50/30/20, fondo de emergencia en meses y actualización de partidas en `MonthlyBudget`.
  3. `src/backend/api/routers/mobile.py`: Endpoints `GET /api/mobile/summary` y `POST /api/mobile/budget`.
  4. `src/mobile/`: Nueva pestaña táctil `[📊 Mi Mes]` en navegación, con barras de progreso, tarjeta de Fondo de Seguridad y edición in-situ de límites presupuestarios.
  5. Pruebas: Batería de pruebas en `tests/unit/test_mobile_sync_service.py` y `tests/integration/test_mobile_api.py`.

### Fase 8: Auto-Actualizador In-App OTA para APK y Panel de Distribución (Completada)
- **Objetivo**: Permitir que los dispositivos Android actualicen la app con 1 tap al publicar nuevas versiones sin reinstalar manualmente.
- **Entregables**:
  1. `src/backend/domain/schemas/mobile.py`: Esquema `MobileVersionResponse` (`version_code`, `version_name`, `apk_available`, etc.).
  2. `src/backend/services/mobile_sync_service.py`: Gestión de metadatos de versión y repositorio de APKs en `sync/mobile/releases/`.
  3. `src/backend/api/routers/mobile.py`: Endpoints `GET /api/mobile/version`, `GET /api/mobile/download-apk` y `POST /api/mobile/upload-apk`.
  4. `src/mobile/`: Banner táctil superior `[🚀 Nueva versión vX.Y.Z -> Actualizar]` que descarga e instala el APK.
  5. `src/frontend/`: Panel de gestión y publicación de APK en Streamlit (`⚙️ Ajustes > Companion Móvil`).
  6. Pruebas: Verificación de descarga y versionado OTA en `test_mobile_ota_version_and_download_flow`.

### Fase 9: Historial del Mes con Borrado Seguro Offline/Online y Endpoints de Eliminación (Completada)
- **Objetivo**: Permitir corregir errores de captura eliminando transacciones locales y remotas de forma segura.
- **Entregables**:
  1. `src/backend/services/mobile_sync_service.py`: Método `delete_mobile_transaction(identifier)` resolviendo por `mobile_event_id` o ID de transacción.
  2. `src/backend/api/routers/mobile.py`: Endpoint `DELETE /api/mobile/transactions/{identifier}` protegido con token.
  3. `src/mobile/src/services/storage.ts` y `HistoryView.tsx`: Soporte para borrado inmediato de cola local y encolado de borrados remotos si está offline (`gestor_mobile_pending_deletes`).
  4. Pruebas: `test_delete_mobile_transaction_by_id_and_by_event_id` y `test_delete_mobile_transaction_api_flow`.

### Fase 10: Semáforo y Alerta Preventiva en Vivo para Techo de Presupuesto de Deseos (Completada)
- **Objetivo**: Avisar proactivamente antes de pagar si un gasto de ocio/deseo va a superar el límite constitucional del 30%.
- **Entregables**:
  1. `src/mobile/src/components/QuickCaptureView.tsx`: Cálculo predictivo en tiempo real `projectedSpent = wants.spent + inputAmount`.
  2. Semáforo dinámico en 3 estados:
     - 🟢 *Óptimo* (< 80% del presupuesto).
     - 🟡 *Advertencia* (80% - 99.9%): Aviso preventivo en amarillo.
     - 🔴 *Límite Superado* (>= 100%): Banner rojo con alerta de sobrecoste exacto en euros.
  3. Pruebas: `test_wants_traffic_light_prediction_and_thresholds`.

### Fase 11: Buscador Instantáneo de Gastos Históricos ("¿Cuánto me costó...?") y Caché Offline (Completada)
- **Objetivo**: Responder en 0 ms en la calle a preguntas como "¿cuánto pagué la última vez por este servicio/producto?".
- **Entregables**:
  1. `src/backend/domain/schemas/mobile.py`: Esquemas `MobileHistoricalTransactionItem` y `MobileSearchResponse`.
  2. `src/backend/services/mobile_sync_service.py`: `search_transactions(query)` y `get_historical_cache(months=12)`.
  3. `src/backend/api/routers/mobile.py`: `GET /api/mobile/transactions/search` y `GET /api/mobile/transactions/history-cache`.
  4. `src/mobile/src/components/SearchView.tsx`: Filtrado en memoria instantáneo sobre cola local + caché de 12 meses, sugerencias de tags y búsqueda profunda en servidor.
  5. `src/mobile/src/components/NavigationBar.tsx`: Pestaña dedicada `[🔍 Buscar]`.
  6. Pruebas: `test_search_historical_transactions_and_cache` y `test_search_mobile_transactions_and_cache_api`.

### Fase 12: Captura Rápida con Foto del Ticket de Compra (Cámara del Teléfono) (Completada)
- **Objetivo**: Adjuntar fotos de recibos o tickets de compra desde la cámara nativa del móvil con compresión en cliente para no saturar almacenamiento.
- **Entregables**:
  1. Base de datos y migración: Columna `receipt_filename` en tabla `transactions` y modelo SQLAlchemy.
  2. Backend:
     - Endpoints protegidos `POST /api/mobile/receipts` y `GET /api/mobile/receipts/{filename}` en `src/backend/api/routers/mobile.py`.
     - Guardado seguro en disco en `sync/mobile/receipts/receipt_{event_id}.jpg` con prevención de path traversal y decodificación base64 en `MobileSyncService`.
  3. Frontend:
     - Botón táctil `[📷 Foto Ticket]` en `QuickCaptureView` y `dist/index.html`.
     - Compresión en HTML5 Canvas client-side (máx. 1280px, JPEG 0.70, < 200 KB) garantizando transferencias rápidas y legibilidad.
     - Visor modal de comprobantes táctil en la vista de Historial y en el Buscador.
  4. Pruebas: `test_mobile_receipt_saving_and_sync` y `test_mobile_receipts_api_flow` pasando al 100%.

### Fase 13: Captura Rápida de Ingresos Extraordinarios y Bizums Recibidos (Pendiente)
- **Objetivo**: Registrar entradas puntuales de dinero desde el móvil (bizums de amigos, ventas de segunda mano, etc.) con asignación directa al mes contable.
- **Entregables**:
  1. Frontend: Conmutador táctil `[🔴 Gasto | 🟢 Ingreso]` en la cabecera de captura rápida.
  2. Backend: Soporte de transacciones de tipo ingreso en `MobileSyncService`.
  3. Pruebas: Verificación contable de imputación de ingresos en el presupuesto mensual.

---

## 3. Mejoras Archivadas para Futuras Especificaciones (Post-Spec 016)
- **Atajos Rápidos de Importe y Presets Frecuentes (1-Tap)**: Botones directos con combinaciones predefinidas (ej. "Café 1,50 €", "Menú 12,00 €").
- **Aportaciones Móviles a Huchas Conjuntas y Metas del Hogar (Spec 010)**: Conexión con fondos de amortización compartidos.
