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
[x] Fase 12: Captura Rápida con Foto del Ticket de Compra (Cámara del Teléfono)
[x] Fase 13: Captura Rápida de Ingresos Extraordinarios y Bizums Recibidos
[x] Fase 14: Atajos Rápidos de Importe y Presets Frecuentes (1-Tap y Modo Híbrido)
[x] Fase 15: Hardening de Seguridad Integral y Blindaje de Acceso (Post-Auditoría)
[x] Fase 16: Optimización de Rendimiento, Desacoplamiento de Polling y Carga Ansiosa SQL
[x] Fase 17: Configuración Dinámica de Servidor Backend y Soporte Nativo APK
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

### Fase 13: Captura Rápida de Ingresos Extraordinarios y Bizums Recibidos (Completada)
- **Objetivo**: Registrar entradas puntuales de dinero desde el móvil (bizums de amigos, ventas de segunda mano, etc.) con asignación directa al mes contable.
- **Entregables**:
  1. Frontend (React + PWA monolítica):
     - Conmutador táctil `[🔴 Gasto | 🟢 Ingreso / Bizum]` en la cabecera de captura rápida (`QuickCaptureView.tsx` y `dist/index.html`).
     - Filtrado contextual de subcategorías según el modo seleccionado (subcategorías de ingresos con emojis dinámicos 💰 Nómina, 📲 Bizum, 🔄 Reembolso, 🏷️ Ventas).
     - Desactivación inteligente del semáforo predictivo de Deseos al estar en modo Ingreso.
     - Indicador y botones con importe positivo `+X,XX €` en verde esmeralda y botón `Guardar Ingreso (+X,XX €)`.
     - Visualización diferenciada en Historial y Buscador con importes en verde `+X,XX €`.
  2. Backend:
     - Soporte para `type: Optional[str] = "EXPENSE"` (o `"INCOME"`) y `category_type: str` en contratos Pydantic v2 (`MobileCatalogSubcategory`, `MobileTransactionPayload`, `MobileHistoricalTransactionItem`).
     - Detección unificada y robusta de categorías de ingreso (`is_income_category`) en `MobileSyncService`.
     - Cómputo exacto de ingresos y flujo de caja en `get_mobile_monthly_summary()` y asignación contable al mes correspondiente.
  3. Pruebas: `test_mobile_income_transaction_capture_and_summary` y `test_mobile_income_sync_and_summary_api` pasando al 100% (31/31 tests).

### Fase 14: Atajos Rápidos de Importe y Presets Frecuentes (1-Tap y Modo Híbrido) (Completada)
- **Objetivo**: Permitir capturar gastos super-frecuentes en menos de 1 segundo mediante botones preconfigurados con comportamiento híbrido (tap para rellenar, pulsación larga para guardar directo) y protección de presupuesto.
- **Entregables**:
  1. Tipos y almacenamiento en `src/mobile/src/types.ts` y `src/mobile/src/services/storage.ts`:
     - Interfaz `QuickPresetItem`: `id`, `name`, `amount`, `subcategoryId`, `subcategoryName`, `concept`, `icon`.
     - Presets preconfigurados por defecto: *☕ Café (1,50 €)*, *🍽️ Cena (20,00 €)*, *🎬 Cine (5,50 €)*.
     - Persistencia offline y utilidades `loadStoredQuickPresets()`, `saveStoredQuickPresets(presets)`, `resetStoredQuickPresets()`.
  2. Componentes UI en `src/mobile/src/components/`:
     - `QuickPresetChips.tsx`: Carrusel táctil con barra horizontal deslizable, feedback táctil/visual de pulsación continua (long-press >= 500 ms) y micro-guía informativa *"💡 Toca para rellenar · Mantén pulsado para guardar directo"*.
     - Modal `ManagePresetsModal.tsx`: Edición de importe, nombre y subcategoría, creación de nuevos atajos o eliminación.
  3. Integración en `QuickCaptureView.tsx`:
     - Renderizado de atajos rápidos ergonómicos sobre el display de importe.
     - Lógica de tap corto (precarga inmediata de campos).
     - Lógica de pulsación larga (guardado directo 1-Tap con toast de confirmación y opción [Deshacer]).
     - Salvaguarda: si el preset es de Deseos y supera el presupuesto mensual, la pulsación larga desactiva el guardado directo y abre el formulario alertando con el semáforo rojo.
  4. Sincronización en la PWA estática (`src/mobile/dist/index.html`):
     - Soporte completo offline-first con eventos touch/mouse para long-press, modal de ajustes de atajos y botón flotante de Deshacer.
  5. Pruebas automatizadas:
     - Batería de pruebas en `test_mobile_quick_presets_and_wants_safeguard_contract` y `test_mobile_quick_presets_and_hybrid_1tap_pwa_bundle` pasando al 100% (33/33 tests).

### Fase 15: Hardening de Seguridad Integral y Blindaje de Acceso (Post-Auditoría) (Completada)
- **Objetivo**: Corregir de forma integral las vulnerabilidades detectadas en la auditoría de seguridad ([spec_016_security_audit_report.md](file:///C:/Users/Raul_515/.gemini/antigravity/brain/d8cbd724-334d-4de0-8fa7-b60fc2e87789/spec_016_security_audit_report.md)), erradicando la fuga pública del token en `GET /api/mobile/status`, autenticando los endpoints de subida de APK y procesado, protegiendo nombres de archivo contra colisiones y blindando la PWA contra ataques de XSS almacenado.
- **Entregables Implementados y Validados**:
  1. Remedición SEC-01 (Blindaje de `GET /api/mobile/status`):
     - Eliminación del campo `pairing_token` de la respuesta pública `MobileSyncStatusResponse` (marcado deprecado y forzado a `None`).
     - `GET /api/mobile/status` ahora solo evalúa si el cliente que llama está autenticado (`authenticated: True/False`) sin revelar jamás el secreto.
     - Endpoint interno dedicado `GET /api/mobile/admin/pairing-token` protegido con comprobación estricta de loopback local (`127.0.0.1`, `::1`, `localhost`, `testclient`) para la generación de QR en Streamlit, denegando con HTTP 403 a cualquier IP externa de la red.
     - Actualización de `src/frontend/api_client.py` (`get_mobile_pairing_token()`) y `src/frontend/views/mobile_view.py`.
  2. Remedición SEC-02 y SEC-05 (Autenticación de Endpoints Críticos):
     - Exigencia de `_auth: str = Depends(verify_mobile_token)` en `POST /api/mobile/upload-apk` y `POST /api/mobile/process-folder`.
  3. Remedición SEC-07 (Prevención Defensiva de Colisiones en Comprobantes):
     - Asignación de identificador aleatorio único seguro mediante `secrets.token_hex(8)` en `save_receipt_file()` y `save_receipt_base64()` si `event_id` no contiene caracteres alfanuméricos válidos.
  4. Remedición SEC-03 (Sanitización XSS en la PWA Monolítica `dist/index.html`):
     - Implementación de la función `escapeHtml()` y sanitización rigurosa de todas las cadenas de texto del usuario (`description`, `subcategory_name`, `concept`, `presets`, `searchQueryHist`, `token`) y desacoplamiento de eventos `onclick` a selectores por índice/atributo para prevenir inyecciones de script.
  5. Pruebas automatizadas:
     - 41/41 pruebas automatizadas pasando al 100% en `tests/unit/test_mobile_sync_service.py`, `tests/unit/test_mobile_quick_presets.py` y `tests/integration/test_mobile_api.py`.

### Fase 16: Optimización de Rendimiento, Desacoplamiento de Polling y Carga Ansiosa SQL (Completada)
- **Objetivo**: Implementar de forma integral las soluciones a los 6 hallazgos de la auditoría de rendimiento integral, desacoplando el sondeo de la PWA móvil, eliminando consultas N+1 en SQLite, delegando agregaciones al motor SQL, optimizando los ciclos del worker en segundo plano y memoizando tokens.
- **Entregables Implementados y Validados**:
  1. Backend (`src/backend/services/mobile_sync_service.py`):
     - Eliminación de consultas N+1 en `get_historical_cache()` y `search_transactions()` mediante carga ansiosa `joinedload(Transaction.subcategory).joinedload(Subcategory.category)`, reduciendo el tráfico SQL a una única consulta unificada con `LEFT OUTER JOIN`.
     - Delegación de agregaciones de frecuencia de subcategorías y conceptos recurrentes directamente al motor SQL SQLite en `get_mobile_catalog()` usando `func.count()` y `GROUP BY`, erradicando la instanciación de cientos de objetos ORM en la RAM de Python.
  2. Worker en segundo plano (`src/backend/api/main.py`):
     - Verificación ligera de existencia en sistema de archivos (`any(f.suffix == '.json')` en `sync/mobile/inbox/`) antes de abrir sesiones y transacciones con `SessionLocal()` en `run_periodic_mobile_sync_checker()`.
  3. Cliente de API en Streamlit (`src/frontend/api_client.py`):
     - Memoización en memoria del token de emparejamiento con `get_cached_pairing_token()`, eliminando peticiones HTTP redundantes a `/api/mobile/status` antes de cada consulta de catálogo o resumen.
  4. Micro-App Móvil (`src/mobile/src/App.tsx` y `src/mobile/dist/index.html`):
     - Sondeo adaptativo: ciclo de polling ampliado de 15s a 60s, con suspensión automática en segundo plano mediante `document.visibilityState !== "visible"`.
     - Desacoplamiento de caché pesada: la descarga de catálogo, resumen mensual y caché histórica de 12 meses ya no se ejecuta en cada tick de 15s, sino en el arranque inicial, al navegar voluntariamente a pestañas dependientes o reactivamente tras una mutación exitosa (`POST /sync` o `DELETE`).
  5. Pruebas automatizadas:
     - 41/41 pruebas automatizadas pasando al 100% en `tests/unit/test_mobile_sync_service.py`, `tests/unit/test_mobile_quick_presets.py` y `tests/integration/test_mobile_api.py`.

### Fase 17: Configuración Dinámica de Servidor Backend y Soporte Nativo APK (Completada)
- **Objetivo**: Dotar a la aplicación móvil (React y PWA autónoma) de persistencia y resolución dinámica de la URL del backend, permitiendo operar tanto empaquetada como APK nativa de Android (Capacitor) como en redes variables o Hotspot móvil, manteniendo el alto rendimiento de sondeo adaptativo.
- **Entregables Implementados y Validados**:
  1. Servicios de persistencia y red móvil (`src/mobile/src/services/`):
     - `storage.ts`: clave `gestor_mobile_server_url`, `getStoredServerUrl()`, `saveStoredServerUrl()` con sanitización estricta y auto-captura en arranque (`extractAndSaveServerUrlFromUrl()`).
     - `api.ts`: resolución jerárquica en `getBaseApiUrl()` (URL guardada > origin web > localhost) y utilidad ligera `testServerConnection()` para validación de conectividad a 3s con AbortController.
  2. Componentes e Interfaz (`src/mobile/src/components/` y `App.tsx`):
     - `ServerConfigModal.tsx`: modal táctil oscuro con inputs de Servidor Backend y Token de Emparejamiento, botón `[⚡ Probar Conexión]` con feedback visual y guardado atómico.
     - `App.tsx`: botón de ajustes `[⚙️]` en la cabecera unificado con el indicador de estado de red y auto-detección desatendida desde la URL del QR.
  3. Paridad total en PWA monolítica estática (`src/mobile/dist/index.html`):
     - Replicación de la resolución dinámica de URL base en todas las llamadas fetch, modal táctil de ajustes de conexión y preservación rigurosa de las optimizaciones de rendimiento (sondeo a 60s, pausa por `visibilityState` y desacoplamiento de datos pesados).
  4. Pruebas y verificación:
     - 0 errores estáticos en TypeScript (`npx tsc --noEmit`) y 100% de tests pasando en pytest (39/39 tests).

### Fase 18: Resiliencia de Integración y Casos Límite (Completada)
- **Objetivo**: Resolver de forma integral los casos límite detectados en la auditoría general de integración, blindando la asignación horaria local sin desfase UTC, asegurando que ingresos al vuelo no se categoricen en Deseos, previniendo desbordamientos de `localStorage` (`QuotaExceededError`), garantizando la propagación de borrados offline, eliminando físicamente archivos de comprobantes huérfanos y mitigando colas envenenadas.
- **Entregables Implementados y Validados**:
  1. Corrección de Desfase Horario Local (00:00 - 02:00 CET):
     - Sustitución de `toISOString().split("T")[0]` por funciones helper de fecha local (`getLocalDateString()` y `getLocalMonthString()`) en `src/mobile/dist/index.html` y `src/mobile/src/components/QuickCaptureView.tsx`, garantizando que gastos capturados de noche o en cambios de mes se imputen a la fecha local real de España (CET/CEST).
  2. Categorización Correcta de Ingresos al Vuelo:
     - En `src/backend/services/mobile_sync_service.py` (`process_mobile_sync()`), asignación automática a `category_name="Ingresos Netos"` cuando `item.type == "INCOME"`, evitando que ingresos se registren como gastos en `Deseos (30%)`.
  3. Protección contra `QuotaExceededError` en Almacenamiento Local:
     - En `saveTransactions()` de `src/mobile/dist/index.html` y `saveStoredTransactions()` de `src/mobile/src/services/storage.ts`, captura preventiva de la excepción de cuota con purgado automático de `receipt_base64` en transacciones ya sincronizadas (`status === "SYNCED"`), liberando hasta varios megabytes sin perder histórico ni comprobantes (almacenados en disco en el servidor).
  4. Cola de Borrados Offline (`PENDING_DELETES`) en PWA Monolítica:
     - Implementación de `STORAGE_KEYS.PENDING_DELETES` (`gestor_mobile_pending_deletes`), `queuePendingDelete()` y `processPendingDeletes()` en `src/mobile/dist/index.html` para persistir los borrados ejecutados sin conexión y aplicarlos atómicamente contra el servidor en la siguiente reconexión.
  5. Mitigación de Cola Envenenada (*Poisoned Queue*):
     - Ante errores HTTP 422 en la sincronización por lotes, marcado automático de los ítems en conflicto como `status = "SYNC_ERROR"` para no reintentar en bucle infinito cada 15/60s agotando la batería del dispositivo.
  6. Limpieza Física Directa de Archivos Huérfanos de Tickets:
     - Implementación de `delete_receipt_file()` en `MobileSyncService` y llamada en `SQLiteRepository.delete_transaction()` y `delete_mobile_transaction()`, eliminando físicamente el archivo `receipt_filename` del disco en `sync/mobile/receipts/` al borrar transacciones (sin dejar residuos en el sistema de archivos).
  7. Inclusión de Gastos con `subcategory_id = None` en Resumen Mensual:
     - Cómputo de transacciones sin subcategoría en `get_mobile_monthly_summary()` bajo `unassigned_spent`, reflejándolas en el gasto total del mes `total_spent` y agregando una entrada representativa "Sin Subcategoría" en `subcategories`.
  8. Paridad de Contratos y Batería de Pruebas Automatizadas:
     - Inclusión de campos `type`, `receipt_base64` y `receipt_filename` en `syncTransactionsWithBackend()` de `src/mobile/src/services/api.ts`.
     - Restauración de pruebas de hardening de token y saneamiento de recibos, y adición de pruebas específicas para los casos límite de la Fase 18 en `tests/unit/test_mobile_sync_service.py`.
     - 44/44 pruebas pasando al 100% en la suite de la Spec 016 (`test_mobile_sync_service.py`, `test_mobile_quick_presets.py`, `test_mobile_api.py`).
  9. Blindaje de Integración y Casos de Uso Detectados en Segunda Auditoría:
     - Reparación del temporizador de auto-sincronización tras 1-Tap directo en `src/mobile/dist/index.html` (`syncPendingTransactions` corregido a `syncTransactions`).
     - Consistencia bidireccional en `undoDirectSave()`: si el usuario deshace un 1-Tap cuando la transacción ya se sincronizó, se envía `DELETE` al servidor de inmediato.
     - Resolución canónica de imágenes de comprobantes con token de emparejamiento (`getReceiptImageUrl()`) en `HistoryView.tsx` y `SearchView.tsx` para compatibilidad nativa en Android APK (Capacitor) y redes externas.
     - Preservación del tipo `type: "INCOME"` y comprobantes en el buscador táctil sobre transacciones locales recientes tanto en React (`SearchView.tsx`) como en la PWA estática (`src/mobile/dist/index.html`).

### Fase 19: Compatibilidad Completa y Despliegue en Contenedores Docker (Completada)
- **Objetivo**: Garantizar el correcto funcionamiento, emparejamiento y sincronización del Companion Móvil cuando el sistema se ejecuta en contenedores Docker locales (`docker-compose up`), blindando CORS, propagación de URL de servidor y aislamiento de subredes.
- **Entregables Implementados y Validados**:
  1. Montaje y Despliegue de la PWA en Contenedores:
     - Configuración de volumen `- ../src/mobile:/app/src/mobile` en `docker_local/docker-compose.yml` e instrucción `COPY src/mobile /app/src/mobile` en `images/backend/Dockerfile` para que FastAPI sirva la PWA real compilada en `/mobile` en lugar del placeholder dummy.
  2. Soporte Integral de CORS para APK Nativa de Android y Clientes Móviles:
     - En `src/backend/api/main.py`, incorporación de `CORSMiddleware` con `allow_origins=["*"]` y `allow_headers=["*"]`, resolviendo peticiones OPTIONS preflight para Capacitor (`capacitor://localhost` / `http://localhost`) con cabeceras `X-Mobile-Pairing-Token`.
  3. Propagación de Servidor en QR y Auto-Sincronización de Origen en PWA:
     - En `src/frontend/views/mobile_view.py`, inclusión del parámetro `server=http://{local_ip}:8000` en la URL del código QR y enlaces para sobreescribir URLs obsoletas en `localStorage` al cambiar de Wi-Fi.
     - En `src/mobile/dist/index.html` y `src/mobile/src/services/storage.ts`, sincronización automática del servidor activo con `window.location.origin` cuando la PWA se carga desde una IP de red real.
  4. Aislamiento de Subred Docker y Exclusión Estricta de Hotspot Móvil:
     - Configuración de subred fija dedicada `172.28.199.0/24` para `app-network` en `docker_local/docker-compose.yml` y paridad de variable `HOST_IP` en `docker_local/docker-compose.extend.yml`.
     - En `src/backend/api/routers/mobile.py` (`get_admin_pairing_token`), autorización de red interna Docker excluyendo explícitamente el rango Hotspot / Punto de Acceso de iPhone (`172.20.10.0/24`) para evitar falsos positivos de seguridad (`SEC-01`).
  5. Detección Dinámica de IP del Host y Ajuste Interactivo en Streamlit:
     - En `src/frontend/views/mobile_view.py`, integración de variable de entorno `HOST_IP` en `get_local_ip()`.
     - Panel expandible en la vista Streamlit (`⚙️ Configuración de IP / Docker Wi-Fi`) con alerta automática si se detecta una IP interna de contenedor (`172.x`) y campo interactivo para ingresar la IP local del PC en la Wi-Fi (`st.session_state["custom_mobile_host_ip"]`), actualizando al instante el código QR y los enlaces móviles.
  6. Batería de Pruebas Automatizadas:
     - Pruebas de integración `test_admin_pairing_token_access_control` (con validación de rechazo a Hotspot y aceptación de subred Docker) y `test_mobile_cors_preflight_and_headers` en `tests/integration/test_mobile_api.py`.
     - 46/46 pruebas pasando al 100% en la suite acotada de la Spec 016 (`test_mobile_sync_service.py`, `test_mobile_quick_presets.py`, `test_mobile_api.py`).

### Incidencias Detectadas en Pruebas Reales con Xiaomi / Android (HyperOS/MIUI) — Plan para Próxima Sesión
- **Fecha**: 2026-11-23.
- **Contexto**: Pruebas de campo con usuario en dispositivo Xiaomi real (Android con HyperOS/MIUI) conectado vía red local Wi-Fi al servidor FastAPI.
- **Incidencia 1: PWA instalada se abre con barra de navegación de Chrome**:
  - *Síntoma*: Tras activar el flag `#unsafely-treat-insecure-origin-as-secure` y pulsar el icono en el escritorio, la aplicación sigue abriendo Google Chrome con la barra de navegación superior visible (`media_1795470193243_48f5560e.jpg`).
  - *Diagnóstico técnico*: El motor de WebAPK de Android (Google Play Services) degrada a Chrome Custom Tab cuando el origen es HTTP sin certificado TLS de confianza, y los lanzadores de MIUI/HyperOS conservan bookmarks antiguos.
  - *Líneas de solución para mañana*:
    1. Proveer la compilación directa del instalador APK nativo (`app-debug.apk`) con Capacitor y GitHub Actions, garantizando una app 100% nativa sin barras de navegador.
    2. O evaluar HTTPS local (mkcert / túnel local) para habilitar WebAPK de primer nivel en Chrome.
- **Incidencia 2: El código QR no es detectado por la cámara del teléfono**:
  - *Síntoma*: Al apuntar la cámara del teléfono Xiaomi al código QR en el monitor del PC, no se detecta el enlace.
  - *Diagnóstico técnico*: Densidad de versión del QR debido a la longitud del token criptográfico (64 caracteres), reflejos del panel LCD del monitor y posible desactivación del lector QR en los ajustes de la cámara nativa de HyperOS.
  - *Líneas de solución para mañana*:
    1. Implementar emparejamiento alternativo por **código PIN de 6 dígitos** (ej. `382-910`) de un solo uso generado en Streamlit.
    2. Código QR ultra-simplificado sin parámetros query extensos.

---

## 3. Mejoras Archivadas para Futuras Especificaciones (Post-Spec 016)
- **Aportaciones Móviles a Huchas Conjuntas y Metas del Hogar (Spec 010)**: Conexión con fondos de amortización compartidos.
