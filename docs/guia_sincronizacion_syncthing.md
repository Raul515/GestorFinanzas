# 🔄 Guía de Sincronización Descentralizada P2P con Syncthing

Esta guía explica cómo conectar dos ordenadores (ej. un PC con **Windows** y un **Mac**) para que la **Cuenta Conjunta** del Gestor de Finanzas se mantenga sincronizada en tiempo real, garantizando **privacidad total**:
- **Sin servidores centrales** ni bases de datos en la nube.
- **Sin compartir tu base de datos personal** (`finanzas.db`).
- Solo viajan pequeños archivos delta `.json` con los movimientos comunes a través de carpetas locales cifradas mediante TLS punto a punto (P2P).

---

## 🏗️ 1. Cómo Funciona la Arquitectura de Sincronización

Cada dispositivo tiene su propia base de datos SQLite independiente y su propio buzón de intercambio local:

```
+------------------------------------+                  +------------------------------------+
|        DISPOSITIVO A (PC)          |                  |        DISPOSITIVO B (Mac)         |
|                                    |                  |                                    |
| [Perfil Personal] (100% Privado)   |                  | [Perfil Personal] (100% Privado)   |
| [Cuenta Conjunta] (SQLite Local)   |                  | [Cuenta Conjunta] (SQLite Local)   |
|                                    |                  |                                    |
|   Carpeta: sync/outbox/  --------> | === Syncthing ===> |   Carpeta: sync/inbox/             |
|                                    |    (Cifrado TLS)   |                                    |
|   Carpeta: sync/inbox/   <-------- | <== Syncthing ===  |   Carpeta: sync/outbox/            |
+------------------------------------+                  +------------------------------------+
```

1. Cuando registras un gasto común o dotas una hucha en el **Dispositivo A**, la aplicación genera atómicamente un archivo delta `.json` en `sync/outbox/`.
2. **Syncthing** detecta el archivo y lo transfiere automáticamente por la red local o internet a la carpeta `sync/inbox/` del **Dispositivo B**.
3. El **Dispositivo B** ingesta el evento de forma idempotente (sin duplicados, resolviendo conflictos por marca de tiempo UTC *Last-Write-Wins*).

---

## ⏱️ 2. Guía Rápida de Configuración (3 Minutos)

### Paso 1: Instalar Syncthing en Ambos Equipos

- **En Windows**:
  - Descarga e instala [SyncTrayzor](https://github.com/canton7/SyncTrayzor/releases) (la interfaz gráfica más cómoda para Windows) o el ejecutable oficial desde [syncthing.net](https://syncthing.net/).
- **En macOS**:
  - Descarga [Syncthing macOS](https://github.com/syncthing/syncthing-macos/releases) o instálalo por terminal con Homebrew:
    ```bash
    brew install --cask syncthing
    ```

Una vez iniciado, Syncthing abrirá la interfaz web en tu navegador: `http://127.0.0.1:8384`.

---

### Paso 2: Obtener el `Device ID` y Emparejar Equipos

1. En el **Dispositivo A (Windows)**:
   - Haz clic en **Acciones** (arriba a la derecha) > **Mostrar ID**.
   - Copia la clave alfanumérica de 50-60 caracteres (o escanea el código QR).
2. En el **Dispositivo B (Mac)**:
   - Haz clic abajo a la derecha en **Añadir Dispositivo Remoto**.
   - Pega el ID del Dispositivo A, asígnale un nombre identificativo (ej. *"PC Raúl"*) y pulsa **Guardar**.
3. Vuelve al **Dispositivo A**:
   - Aparecerá una notificación amarilla indicando que un nuevo dispositivo desea conectarse. Pulsa **Añadir Dispositivo**.

---

### Paso 3: Configurar las Carpetas Compartidas Cruzadas

Configuraremos **dos carpetas** para que el flujo de salida de uno sea la entrada del otro:

#### Canal 1: De PC Raúl (A) hacia Mac Ana (B)
1. En el **Dispositivo A**:
   - Haz clic en **Añadir Carpeta**.
   - **Etiqueta**: `Hogar - De Raúl a Ana`
   - **ID de la Carpeta**: `hogar-outbox-raul` *(debe ser idéntico en ambos)*
   - **Ruta de la Carpeta**: Selecciona `...\GestorFinanzas\sync\outbox`
   - En la pestaña **Compartir**, marca la casilla de *"Mac Ana"*.
   - Pulsa **Guardar**.
2. En el **Dispositivo B**:
   - Acepta la solicitud que aparecerá en pantalla.
   - En **Ruta de la Carpeta**, selecciona la carpeta de entrada de Ana: `.../GestorFinanzas/sync/inbox`.
   - Pulsa **Guardar**.

#### Canal 2: De Mac Ana (B) hacia PC Raúl (A)
1. En el **Dispositivo B**:
   - Haz clic en **Añadir Carpeta**.
   - **Etiqueta**: `Hogar - De Ana a Raúl`
   - **ID de la Carpeta**: `hogar-outbox-ana`
   - **Ruta de la Carpeta**: Selecciona `.../GestorFinanzas/sync/outbox`
   - En la pestaña **Compartir**, marca la casilla de *"PC Raúl"*.
   - Pulsa **Guardar**.
2. En el **Dispositivo A**:
   - Acepta la solicitud en pantalla.
   - En **Ruta de la Carpeta**, selecciona la carpeta de entrada de Raúl: `...\GestorFinanzas\sync\inbox`.
   - Pulsa **Guardar**.

---

## ✅ 3. Verificación en la Aplicación

1. Inicia la aplicación en ambos ordenadores:
   ```powershell
   .\venv\Scripts\streamlit run src/frontend/app.py
   ```
2. En el menú lateral, selecciona **👥 Economía del Hogar (Cuenta Conjunta)**.
3. Dirígete a la pestaña **⚙️ Configuración del Hogar y Sincronización**:
   - Verás el indicador **🟢 Sincronizado**.
   - Registra un gasto en un ordenador y pulsa **🔄 Procesar Bandeja de Entrada Ahora (Inbox)** en el otro para ver cómo aparece inmediatamente.
   - *(El backend también procesa automáticamente la bandeja periódicamente)*.

---

## 🛡️ 4. Seguridad, Idempotencia y Privacidad

- **Bases de datos no compartidas**: Cada miembro conserva su propia base de datos SQLite en disco local. Si un ordenador se formatea o se pierde, no se comprometen los datos bancarios individuales.
- **Idempotencia Garantizada**: Cada evento delta tiene un identificador único `UUIDv4`. Si Syncthing retransmite un archivo o se produce un reinicio, el motor del Gestor de Finanzas detecta el evento en la tabla `joint_applied_sync_events` y lo descarta sin duplicar saldos.
- **Tolerancia a Conexiones Intermitentes**: Si uno de los dos equipos está apagado o sin internet (ej. en un viaje), los deltas se acumulan ordenadamente en `outbox` y se transfieren automáticamente tan pronto como ambos dispositivos vuelvan a tener conexión.

---

## 🔧 5. Preguntas Frecuentes y Solución de Problemas

### ¿Qué ocurre si ambos miembros editan la misma hucha a la vez?
El motor de sincronización aplica la regla determinista **LWW (Last-Write-Wins)** comparando la marca de tiempo `timestamp_utc`. El evento emitido más recientemente en tiempo universal prevalece de forma consistente en ambos dispositivos.

### ¿Se pueden sincronizar transacciones eliminadas?
Sí. Cuando se elimina un gasto común, el sistema genera un **Tombstone** (evento de borrado). Al recibirse, el gasto se elimina en el equipo remoto y, si estaba imputado a una hucha de amortización, el saldo correspondiente se restaura de forma automática.

### El estado muestra "Deltas en Outbox" pero no llegan al otro equipo
1. Comprueba en `http://127.0.0.1:8384` que ambos dispositivos figuren como **Conectado**.
2. Si estás en una red Wi-Fi pública o corporativa con aislamiento de clientes, asegúrate de que Syncthing tenga activada la opción **Relaying** y **Global Discovery** en *Ajustes > Conexiones*.
