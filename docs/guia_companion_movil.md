# 📱 Guía del Companion Móvil "Quick-Capture" (Spec 016)

El **Companion Móvil** es una micro-aplicación ultra-ligera diseñada exclusivamente para **anotar un gasto cotidiano (café, cena, supermercado, gasolina) en menos de 5 segundos** desde tu teléfono, con **operativa 100% offline** y **sincronización automática desatendida al conectarte a la red Wi-Fi de tu casa**.

---

## 🚀 Método 1: Conexión Rápida e Instalación como PWA (Recomendado - 10 Segundos)

La forma más rápida, limpia y recomendada tanto para **Android** como para **iPhone (iOS)**, sin necesidad de compilar ni descargar archivos `.apk`.

### Emparejamiento Seguro mediante Código PIN de 6 Dígitos
1. En tu ordenador, abre el Gestor de Finanzas en Streamlit y navega a `⚙️ Ajustes y Sistema` -> `📱 Companion Móvil Quick-Capture`.
2. Verás un **código PIN de 6 dígitos** único (ej. `582 914`) generado para tu sesión con validez de 10 minutos y blindaje anti-fuerza bruta (máx. 5 intentos).
3. **Si utilizas Docker en tu PC**:
   - Streamlit detectará automáticamente la subred del contenedor (`172.x`) y abrirá el panel `⚙️ Configuración de IP / Docker Wi-Fi`.
   - Introduce la IP local de tu PC en la Wi-Fi (ej. `192.168.1.35`) y pulsa `[Aplicar IP]`. La dirección y los enlaces se recalcularán al instante.

### En Android (Google Chrome / Brave / Edge)
1. Conecta tu teléfono a la **misma red Wi-Fi** que el ordenador.
2. Abre en tu navegador móvil la dirección mostrada en pantalla: `http://TU_IP:8000/mobile/`.
3. Introduce el **PIN de 6 dígitos** mostrado en tu PC y pulsa **[Vincular]**. El teléfono guardará el token maestro de forma segura e indefinida.
4. Pulsa los **tres puntos verticales (`⋮`)** arriba a la derecha y selecciona **"Instalar aplicación"** o **"Añadir a la pantalla principal"**.
5. ¡Listo! Tendrás el icono en tu pantalla de inicio, se abrirá al instante y funcionará sin cobertura.

> ℹ️ **Nota sobre la barra superior de Google Chrome en Android**:
> Al utilizar una red local privada bajo HTTP (`http://192.168.x.x`), los servicios WebAPK de Google Play no firman la PWA en la nube, por lo que Android muestra una barra de navegación delgada en la parte superior. La aplicación funciona con todas sus capacidades y 100% offline. Si deseas una experiencia de **pantalla completa pura de borde a borde (sin ninguna barra)**, puedes instalar la **📦 App Nativa APK** descrita en el Método 2.
>
> 💡 **Si Chrome muestra «Esta aplicación no se puede instalar»**:
> Por seguridad, Google Chrome exige HTTPS para instalar PWAs independientes. Para autorizar la red local Wi-Fi en 30 segundos:
> 1. En Chrome en tu móvil abre: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
> 2. Cámbialo a **Enabled** y escribe en el cuadro de texto: `http://TU_IP:8000` (ej. `http://192.168.1.35:8000`).
> 3. Pulsa **Relaunch** abajo a la derecha. Al recargar la app, el botón **«Instalar»** se activará de inmediato.

### En iPhone / iOS (Safari)
1. Conecta el iPhone a la **misma red Wi-Fi** que el ordenador.
2. Abre en **Safari** la dirección web: `http://TU_IP:8000/mobile/`.
3. Introduce el **PIN de 6 dígitos** y pulsa **[Vincular]**.
4. Pulsa el botón **Compartir** (icono de un cuadrado con flecha hacia arriba en la barra inferior).
5. Desplázate hacia abajo y selecciona **"Añadir a pantalla de inicio"** (`➕`).
6. Pulsa **Añadir**.
7. ¡Listo! En iOS, Safari no utiliza WebAPK y respeta la directiva `apple-mobile-web-app-capable`: la PWA se abrirá al **100% a pantalla completa nativa sin ninguna barra de navegación ni menús**, incluso en red local.

---

## 📦 Método 2: App Nativa APK de Android (Pantalla Completa Pura y Actualizaciones OTA)

Diseñado para aquellos usuarios de Android que desean **eliminar completamente la barra superior de Chrome** y tener una app 100% nativa con pantalla completa de borde a borde:

1. **Descarga e Instalación Inicial**:
   - En Streamlit (`📱 Companion Móvil` -> sección `📦 Distribución y Actualizaciones`), descarga el binario `app-debug.apk` o la última versión publicada.
   - Instálalo en tu Android activando "Permitir desde esta fuente".
2. **Emparejamiento en el Primer Arranque**:
   - Al abrir la app por primera vez, pulsa el botón de ajustes `[⚙️]` arriba a la derecha.
   - Introduce la IP de tu PC (ej. `http://192.168.1.35:8000`) y el **PIN de 6 dígitos** generado en tu PC. Pulsa `[⚡ Vincular por PIN]`.
   - La app guardará permanentemente tu servidor y tu token maestro.
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
- Abre Streamlit en tu PC y genera un nuevo PIN si fuera necesario.
- En la micro-app en tu móvil, pulsa en el engranaje `[⚙️]` arriba a la derecha, introduce la nueva IP y el nuevo PIN de 6 dígitos.
- La micro-app guardará la nueva dirección y reanudará la sincronización al instante sin perder ningún dato previo.

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

---

## 🔒 Modo HTTPS Opcional (Tailscale Serve — Recomendado para iPhone y 4G/5G)

Si no quieres usar ninguna app externa, puedes seguir utilizando el Companion Móvil exactamente igual por **HTTP Wi-Fi** o mediante la **APK nativa de Android**. Ambos modos conviven a la vez sin conflicto.

Si además quieres **HTTPS válido de fábrica** (imprescindible para que Safari/Chrome en iPhone mantengan el modo *100% offline* incluso tras cerrar la app) junto con una **URL fija** (independiente de si el PC está por cable o Wi-Fi) y **sincronización automática por 4G/5G**:

1. **Instala Tailscale** (plan gratuito personal) en tu PC y en tus teléfonos móviles iniciando sesión con la misma cuenta.
2. En tu PC (PowerShell / Terminal), activa el proxy HTTPS privado sobre el puerto de Docker/FastAPI:
   ```powershell
   tailscale serve --bg 8000
   ```
   Tailscale te mostrará tu dirección HTTPS privada permanente, por ejemplo: `https://mi-pc.tailXXXX.ts.net`.
3. **Configura la URL en el proyecto (opcional, para que Streamlit la muestre en las guías)**:
   - En el archivo `.env` de la raíz del proyecto, define:
     ```env
     MOBILE_PUBLIC_URL=https://mi-pc.tailXXXX.ts.net
     ```
   - O bien introdúcela directamente en Streamlit dentro de `⚙️ Ajustes y Sistema -> 📱 Companion Móvil -> ⚙️ Configuración de IP / HTTPS`.
4. **Vincula tus móviles una única vez** entrando a `https://mi-pc.tailXXXX.ts.net/mobile/` con el **PIN de 6 dígitos**.
   - **Seguridad garantizada (SEC-01)**: aunque el tráfico entre por el proxy HTTPS de Tailscale, el backend bloquea automáticamente con `403` las rutas administrativas (`/api/mobile/admin/*`), manteniéndolas accesibles únicamente desde el PC local / Streamlit.
