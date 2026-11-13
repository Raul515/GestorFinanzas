# Plan de Desarrollo: Especificación 016 — Micro-App Móvil Ligera "Quick-Capture" (Gastos Personales)

## 1. Arquitectura y Estrategia de Ejecución

Siguiendo las directrices de `docs/constitution.md` y `AGENTS.md`, la especificación se desarrollará de forma estrictamente secuencial en **6 fases**. Cada fase se verificará con pruebas automatizadas completas antes de solicitar confirmación al usuario para avanzar a la siguiente.

```
Rama de trabajo: feat/spec-016-micro-app-movil-quick-capture
Fase 1: Backend — Esquemas de Datos y Servicio de Sincronización Móvil (MobileSyncService)
Fase 2: Backend — Router REST, Endpoints Móviles y Servidor PWA Estático
Fase 3: Frontend Móvil — Micro-App Quick-Capture (UX en 5 Segundos con Vite + React + Tailwind)
Fase 4: Persistencia Offline Móvil y Motor de Sincronización Wi-Fi (IndexedDB y Auto-Flush)
Fase 5: Empaquetado Android APK con Capacitor y Automatización CI/CD en GitHub Actions
Fase 6: Integración en Streamlit (Código QR, Monitor de Sincronización) y Verificación E2E
Fusión final: Merge en develop tras 100% de tests
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
