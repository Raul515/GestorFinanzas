# 📱 Guía del Companion Móvil "Quick-Capture" (Spec 016)

El **Companion Móvil** es una micro-aplicación ultra-ligera diseñada exclusivamente para **anotar un gasto cotidiano (café, cena, supermercado, gasolina) en menos de 5 segundos** desde tu teléfono, con **operativa 100% offline** y **sincronización automática desatendida al conectarte a la red Wi-Fi de tu casa**.

---

## 🚀 Método 1: Instalación Inmediata como PWA (Recomendado - 10 Segundos)

La forma más rápida, limpia y recomendada tanto para **Android** como para **iPhone (iOS)**, sin necesidad de compilar ni descargar archivos `.apk`.

### En Android (Chrome, Brave, Edge)
1. Con tu teléfono conectado a la misma red Wi-Fi que el ordenador, abre el navegador y accede a:
   ```text
   http://<IP_DE_TU_PC>:8000/mobile/
   ```
   *(Puedes consultar tu IP o escanear el código QR directamente desde `⚙️ Ajustes y Sistema` -> `Companion Móvil` en la aplicación de Streamlit).*
2. Pulsa el botón de menú del navegador (los **tres puntos** arriba a la derecha).
3. Selecciona **"Añadir a la pantalla de inicio"** o **"Instalar aplicación"**.
4. ¡Listo! Se creará un icono de app en tu móvil que se abre a pantalla completa, funciona sin barras de navegador y almacena gastos sin conexión.

### En iPhone / iOS (Safari)
1. Abre **Safari** y navega a `http://<IP_DE_TU_PC>:8000/mobile/`.
2. Pulsa el botón **Compartir** (el icono de un cuadrado con una flecha hacia arriba en la barra inferior).
3. Desplázate hacia abajo y selecciona **"Añadir a pantalla de inicio"**.
4. Pulsa **Añadir**. La aplicación se comportará como una app nativa con icono propio y almacenamiento offline.

---

## 📦 Método 2: Descarga e Instalación del APK de Android (GitHub Actions)

Si prefieres tener un archivo `.apk` binario tradicional instalado en tu teléfono Android:

1. **Compilación Automática en la Nube**:
   - Accede a tu repositorio en GitHub y ve a la pestaña **Actions**.
   - En el menú lateral izquierdo, selecciona el flujo de trabajo **"Build Mobile Android APK"**.
   - Haz clic en **"Run workflow"** y pulsa el botón verde.
   - En unos 2 minutos, la máquina virtual de GitHub compilará el APK con el SDK de Android y Gradle.
2. **Descarga del APK**:
   - Entra en la ejecución completada y, en la sección **Artifacts**, descarga el archivo `gestor-finanzas-debug-apk.zip`.
   - Descomprímelo en tu teléfono para obtener `app-debug.apk`.
3. **Instalación (Sideloading)**:
   - Abre el archivo `.apk` en tu móvil Android.
   - Si Android te avisa de que proviene de una fuente desconocida, pulsa **Ajustes** y activa **"Permitir desde esta fuente"**.
   - Pulsa **Instalar**.

---

## 🔄 ¿Cómo Funciona la Sincronización?

### 1. En la Calle (100% Offline)
- Abres la micro-app en tu teléfono.
- Tecleas el importe (ej. `2.50`), tocas el chip de la categoría (ej. `☕ Café`) y pulsas `[⚡ Guardar Gasto]`.
- El gasto se guarda instantáneamente en la cola interna de tu teléfono (`status: PENDING_SYNC`) con un identificador único UUIDv4 que impide duplicados.
- El formulario se resetea en menos de 50 ms para el siguiente apunte.

### 2. Al Llegar a Casa (Wi-Fi Doméstica)
- Tu teléfono se conecta a la red Wi-Fi de tu casa.
- La micro-app detecta automáticamente que el ordenador está en línea (`🟢 En línea`).
- Vuelca todos los gastos acumulados contra la API del backend (`POST /api/mobile/sync`).
- Las transacciones se insertan directamente en tu base de datos SQLite (`Transaction`) sin que tengas que encender la pantalla del ordenador ni abrir Streamlit.

### 3. Opción Alternativa con Syncthing (Por Carpetas)
Si eres usuario habitual de Syncthing y prefieres transferir mediante archivos físicos:
- En la pestaña `📋 Historial` de la app móvil, pulsa el botón **"📥 Descargar JSON"**.
- Guarda el archivo `evt_mob_*.json` en la carpeta compartida de Syncthing de tu teléfono.
- Syncthing lo trasladará a la carpeta `sync/mobile/inbox/` de tu ordenador, donde el backend lo ingestará y archivará automáticamente.
