# 📱 Guía del Companion Móvil "Quick-Capture" (Spec 016)

El **Companion Móvil** es una micro-aplicación ultra-ligera diseñada exclusivamente para **anotar un gasto cotidiano (café, cena, supermercado, gasolina) en menos de 5 segundos** desde tu teléfono, con **operativa 100% offline** y **sincronización automática desatendida al conectarte a la red Wi-Fi de tu casa**.

---

## 🚀 Método 1: Conexión Rápida e Instalación como PWA (Recomendado - 10 Segundos)

La forma más rápida, limpia y recomendada tanto para **Android** como para **iPhone (iOS)**, sin necesidad de compilar ni descargar archivos `.apk`.

### Emparejamiento Seguro con Código QR
1. En tu ordenador, abre el Gestor de Finanzas en Streamlit y navega a `⚙️ Ajustes y Sistema` -> `📱 Companion Móvil Quick-Capture`.
2. Verás un **código QR único** que incorpora automáticamente tu **Token Secreto de Emparejamiento** y la **Dirección del Servidor**.
3. **Si utilizas Docker en tu PC**:
   - Streamlit detectará automáticamente la subred del contenedor (`172.x`) y abrirá el panel `⚙️ Configuración de IP / Docker Wi-Fi`.
   - Introduce la IP local de tu PC en la Wi-Fi (ej. `192.168.1.35`) y pulsa `[Aplicar IP]`. El código QR y los enlaces se recalcularán al instante.

### En Android (Google Chrome / Brave / Edge)
1. Conecta tu teléfono a la **misma red Wi-Fi** que el ordenador.
2. Escanea el código QR con la cámara de tu móvil o abre el enlace mostrado en **Google Chrome**.
3. La aplicación guardará tu token y servidor automáticamente.
4. Pulsa los **tres puntos verticales (`⋮`)** arriba a la derecha y selecciona **"Añadir a la pantalla principal"** o **"Instalar aplicación"**.
5. ¡Listo! Tendrás el icono en tu pantalla de inicio, se abrirá a pantalla completa y funcionará sin cobertura.

### En iPhone / iOS (Safari)
1. Conecta el iPhone a la **misma red Wi-Fi** que el ordenador.
2. Escanea el código QR con la cámara del iPhone o abre el enlace en **Safari**.
3. Pulsa el botón **Compartir** (icono de un cuadrado con flecha hacia arriba en la barra inferior).
4. Desplázate hacia abajo y selecciona **"Añadir a pantalla de inicio"** (`➕`).
5. Pulsa **Añadir**. Se creará el acceso directo con icono propio y almacenamiento offline.

---

## 📦 Método 2: App Nativa APK de Android (OTA y Capacitor)

Si prefieres tener una app Android nativa empaquetada:

1. **Descarga e Instalación Inicial**:
   - En Streamlit (`📱 Companion Móvil` -> sección `📦 Distribución y Actualizaciones`), descarga el binario `app-debug.apk` o compílalo mediante el workflow `.github/workflows/build-mobile-apk.yml`.
   - Instálalo en tu Android activando "Permitir desde esta fuente".
2. **Emparejamiento en el Primer Arranque**:
   - Al abrir la app por primera vez, pulsa el botón de ajustes `[⚙️]` arriba a la derecha.
   - Introduce la URL de tu servidor (ej. `http://192.168.1.35:8000`) y tu Token de Emparejamiento, o escanea el código QR desde la cámara. Pulsa `[⚡ Probar Conexión]` y guarda.
3. **Actualizaciones Automáticas In-App (OTA)**:
   - Cuando publiques una nueva versión del APK desde el panel de Streamlit en tu PC, la app móvil detectará automáticamente la actualización al abrirse y te ofrecerá instalarla en 1 tap sin cables ni pasos manuales.

---

## ✨ Funcionalidades Clave del Companion Móvil

- **⚡ Captura en Menos de 5 Segundos**: Display táctil con teclado numérico, fila de importes rápidos (`+1€`, `+2€`, `+5€`, `+10€`, `+20€`) y carrusel de subcategorías frecuentes.
- **☕ Atajos Frecuentes 1-Tap con Modo Híbrido**:
  - **Tap corto**: Rellena el formulario para que puedas añadir notas o adjuntar ticket antes de guardar.
  - **Pulsación larga (long-press >= 500 ms)**: Guardado directo e instantáneo con vibración háptica y aviso emergente con botón `[Deshacer]`.
  - **Salvaguarda de Deseos (30%)**: Si un atajo de ocio supera el límite mensual de Deseos, bloquea el guardado directo y pide confirmación para proteger tu salud financiera.
- **📷 Foto del Ticket de Compra**: Pulsa `[📷 Foto Ticket]` para fotografiar recibos físicos. Se comprimen en el móvil (< 200 KB) y se envían de forma segura al PC.
- **🔄 Conmutador Gasto / Ingreso**: Registra cobros de Bizum o devoluciones al vuelo seleccionando `[🟢 Ingreso]`.
- **📊 Vista "Mi Mes"**: Consulta en tiempo real la ejecución del presupuesto 50/30/20 y edita asignaciones sobre la marcha.
- **🔍 Buscador Instantáneo "¿Cuánto me costó...?"**: Busca cualquier compra pasada en 0 ms sobre el histórico local de 12 meses.
- **🗑️ Historial con Borrado Seguro**: Borra transacciones erróneas; si estás sin conexión, se encolan y se eliminan físicamente en el servidor al llegar a casa.

---

## 🌐 Cambio de Wi-Fi o Reinicio del Router

Si cambias de red Wi-Fi o el router asigna una nueva IP a tu PC (ej. pasa de `192.168.1.35` a `192.168.1.42`):
- Abre Streamlit en tu PC y escanea el nuevo código QR.
- La micro-app capturará automáticamente la nueva dirección del servidor (`?server=...`) y actualizará su memoria local al instante, volviendo a conectar de inmediato sin necesidad de reconfigurar nada a mano.

---

## 🔄 ¿Cómo Funciona la Sincronización?

### 1. En la Calle (100% Offline)
- Abres la micro-app en tu teléfono sin importar si tienes cobertura o datos móviles.
- Registras el gasto: se almacena en la memoria interna (`status: PENDING_SYNC`) con un identificador único UUIDv4 que impide duplicados.

### 2. Al Llegar a Casa (Wi-Fi Doméstica o Docker)
- Al conectarte a la misma Wi-Fi que el PC (o tener el servidor Docker encendido), la app detecta automáticamente el ordenador (`🟢 En línea`).
- Sube todas las transacciones acumuladas en un único lote atómico (`POST /api/mobile/sync`).
- Quedan registradas de inmediato en tu base de datos SQLite y reflejadas en tus gráficos de Streamlit.

### 3. Sincronización Manual por Archivos (Syncthing Opcional)
- En la app móvil puedes pulsar **"Exportar Lote JSON"** para descargar los apuntes en un fichero `.json`.
- Si utilizas Syncthing, deposítalo en la carpeta compartida `sync/mobile/inbox/`: el backend de tu PC lo procesará automáticamente al arrancar.
