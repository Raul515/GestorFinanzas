# 👥 Manual de Usuario: Finanzas Compartidas y Cuenta Conjunta

Bienvenido a la guía completa de **Finanzas Compartidas y Cuenta Conjunta** del Gestor de Finanzas Personales. Este manual está pensado para cualquier usuario (no técnico) que desee compartir gastos, ahorrar en pareja o gestionar la economía de su hogar de forma ordenada, transparente y con **privacidad absoluta**.

---

## 🧭 1. Filosofía: ¿Por qué es diferente este sistema?

La mayoría de aplicaciones para parejas exigen subir todos tus datos bancarios a la nube o obligan a que ambos compartan la totalidad de sus cuentas. Nuestro sistema parte de dos principios fundamentales:

1. **Tu independencia personal es sagrada**: 
   - Tu cuenta personal (tus caprichos, ocio, regalos o ahorros privados) **nunca sale de tu ordenador ni la ve tu pareja**.
   - Solo viajan entre dispositivos los gastos que ambos decidís compartir (facturas comunes o huchas de ahorro conjuntas).
2. **Sin servidores externos ni suscripciones en la nube (Local-First)**:
   - Toda la información vive en tu propio equipo.
   - La sincronización entre tu ordenador y el de tu pareja se realiza de forma directa mediante **Syncthing** (un canal privado y cifrado punto a punto). Nadie más puede acceder a vuestros datos.

---

## 🔄 2. ¿Cómo se relaciona la Cuenta Conjunta con tu Perfil Personal?

Ambos mundos conviven de forma armónica dentro de la misma aplicación mediante un selector situado en la barra lateral:

```
[ Selector en la Barra Lateral ]
  ├── 👤 Mi Perfil Personal   -> Tu presupuesto 50/30/20, transacciones privadas e inversiones.
  └── 👥 Economía del Hogar   -> El espacio común compartido con tu pareja.
```

### Cero Intrusión Inicial
Si no tienes una cuenta conjunta configurada, la aplicación se comporta exactamente como un gestor monousuario: no verás avisos, menús innecesarios ni alertas. Tu experiencia personal permanece 100% limpia.

### El Banner de Aportación Mensual en 1-Clic
Al comenzar cada mes, la aplicación detecta automáticamente si ya has transferido tu parte del presupuesto acordado al hogar:
- Si aún no has aportado, verás un aviso azul discreto en la cabecera de tu perfil personal:
  > 🔔 **Aportación Pendiente al Hogar (Noviembre 2026)**: Aún no has registrado tu aportación mensual para gastos comunes.
- El sistema **calcula automáticamente la cuota exacta** que te corresponde aportar según la modalidad elegida (al 50/50 o según vuestras nóminas).
- Al pulsar **`[💳 Asentar en 1-Clic]`**:
  1. Se descuenta ese dinero de tu cuenta personal (anotándolo limpiamente en tu presupuesto).
  2. Se registra la aportación en la cuenta conjunta como dinero recibido en el hogar.
  3. Se genera la orden de sincronización para que el ordenador de tu pareja refleje que has cumplido con tu aportación.

*(Nota: Si en algún mes tu aportación difiere, el campo es editable: puedes teclear cualquier importe antes de pulsar el botón).*

### ¿Adónde va ese gasto en tu cuenta personal?
El sistema es inteligente según la etapa en la que estéis:
- **En Pre-Convivencia**: Tu aportación se clasifica automáticamente dentro de **Ahorro e Inversión** (*"Aportación Cuenta Conjunta - Ahorro Futuro"*), porque el dinero no se está gastando en alquileres sino guardando para vuestro proyecto de vida.
- **En Convivencia Plena**: Se clasifica dentro de **Necesidades Básicas** (*"Aportación Cuenta Conjunta - Gastos del Hogar"*), computando como parte de tus costes fijos esenciales.

---

## 🏠 3. Cómo Funciona la Economía del Hogar por Dentro

Al cambiar a **`👥 Economía del Hogar`**, accederás a un panel con 4 pestañas diseñadas para dar claridad sin discusiones:

### 1. Resumen Anual del Hogar
- **Métricas Consolidadas**: Total gastado en necesidades del hogar, total ahorrado en huchas y **Tasa de Esfuerzo Familiar** (un semáforo saludable que mide qué porcentaje de los ingresos del hogar absorben los gastos compartidos).
- **Gráfica de 2 Columnas Compuestas**: Compara mes a mes las aportaciones recibidas contra el dinero gastado en necesidades, lo ahorrado en huchas activas y el remanente en tesorería sin asignar.
- **Sin Comparaciones Tóxicas**: La pantalla muestra siempre los números del hogar en su conjunto. **No existen gráficos de "quién gasta más" ni métricas de rivalidad (A vs B)**.

### 2. Los 12 Meses del Hogar
- Desplegable para seleccionar cualquier mes del año.
- **Historial de Aportaciones Recibidas**: Tabla donde se detalla cuándo aportó cada miembro y el total disponible en el fondo común.
- **Facturas y Gastos Comunes**: Registro de supermercado, luz, agua, alquiler o comunidad.
- **Bloqueo Inteligente en Pre-Convivencia**: Si habéis configurado la etapa previa a vivir juntos, el formulario bloquea la inserción de gastos corrientes de vivienda, guiándoos a imputar los gastos exclusivamente a huchas de amortización.
- **Sin Ocio Compartido**: En la cuenta conjunta no hay categorías de salidas con amigos, copas o ropa; esos gastos pertenecen a la cuenta personal de cada miembro, preservando la paz familiar.

### 3. Huchas de Amortización (Sinking Funds)
Las huchas son metas de ahorro compartidas para gastos futuros previsibles o proyectos:
- *Ejemplos*: Vacaciones de verano, Seguro del coche anual, Fianza del alquiler, Muebles o Fondo de Imprevistos.
- Cada hucha tiene su objetivo total, su cuota mensual sugerida y una barra de progreso visual.
- **Eliminación y Reasignación Segura**: Si decidís cancelar una hucha (por ejemplo, canceláis un viaje), el sistema os permite transferir todo el dinero acumulado a otra hucha activa con un solo clic.

### 4. Configuración del Hogar y Syncthing
- Consulta y edición de los parámetros del hogar (nombres de los miembros, sueldos de referencia y reparto).
- Estado de sincronización en tiempo real (bandeja de salida y de entrada).
- **Botón de Emergencia / Desactivación**: Si en algún momento quieres volver a la situación monousuario o probar desde cero, el botón `[🗑️ Desactivar Cuenta Conjunta y Volver al Estado Cero]` limpia los datos compartidos al instante.

---

## 📡 4. ¿Cómo Funciona la Sincronización? (Para no técnicos)

Imagina un **buzón postal privado** entre dos casas:

```
[ TU ORDENADOR ]                                      [ ORDENADOR DE TU PAREJA ]
┌─────────────────────────┐                            ┌─────────────────────────┐
│ Tus gastos personales   │ (Privado)                  │ Sus gastos personales   │ (Privado)
│                         │                            │                         │
│ Buzón Salida (outbox) ──┼─── [ Sobre cerrado ] ─────>│ Buzón Entrada (inbox)   │
│                         │    vía red Wi-Fi segura    │                         │
│ Buzón Entrada (inbox)  <┼─── [ Sobre cerrado ] ──────┼── Buzón Salida (outbox) │
└─────────────────────────┘                            └─────────────────────────┘
```

1. Cuando tú anotas la compra semanal en tu ordenador, el programa redacta un pequeño "sobre digital" (`.json`) con la fecha, el importe y el concepto ("Supermercado 75 €"), y lo deposita en la carpeta `sync/outbox/`.
2. El programa gratuito **Syncthing** detecta ese sobre y se lo envía directamente al ordenador de tu pareja a su carpeta `sync/inbox/`.
3. Cuando tu pareja abre la aplicación (o pulsa *Sincronizar*), la app lee el sobre, anota el gasto en su cuenta conjunta y archiva el sobre.
4. **¿Y si uno está fuera de casa o sin internet?**: Los sobres se quedan guardados pacientemente en la carpeta de salida. En cuanto ambos equipos coincidan con internet o en la Wi-Fi de casa, se entregarán automáticamente sin perder ningún dato.

---

## 🚀 5. Paso a Paso: Cómo empezar a usarla y sincronizarla en 5 minutos

Para empezar a usar la cuenta conjunta con tu pareja, sigue estos sencillos pasos:

### Paso 1: Configurar el Hogar en el Dispositivo 1 (ej. Tu PC)
1. Abre el gestor y en la barra lateral selecciona **`👥 Economía del Hogar`**.
2. Al ser la primera vez, verás el **Asistente de Bienvenida**:
   - Introduce el nombre de vuestro hogar (ej. *"Hogar Raúl y Ana"*).
   - Escribe vuestros nombres (*Miembro A* y *Miembro B*).
   - Elige la etapa: **Pre-Convivencia** (si estáis ahorrando para mudaros) o **Convivencia Plena** (si ya compartís piso).
   - Elige cómo queréis repartir los gastos: **50% / 50%**, **Proporcional según ingresos**, o **Cuota Fija**.
3. Pulsa **`[🚀 Activar Cuenta Conjunta del Hogar]`**. ¡Tu cuenta ya está lista!

### Paso 2: Conectar ambos ordenadores con Syncthing
1. Instala **Syncthing** en ambos equipos (en Windows mediante *SyncTrayzor*; en Mac desde su instalador oficial).
2. Empareja los dos equipos usando el **Device ID** (un identificador que muestra Syncthing, similar a compartir un número de Bluetooth).
3. Conecta las dos carpetas:
   - Haz que la carpeta `sync/outbox` de tu PC apunte a la carpeta `sync/inbox` del Mac de tu pareja.
   - Haz que la carpeta `sync/outbox` del Mac apunte a la carpeta `sync/inbox` de tu PC.
*(Tienes todos los detalles con capturas en la [Guía Detallada de Syncthing](guia_sincronizacion_syncthing.md)).*

### Paso 3: Unirse al Hogar en el Dispositivo 2 (ej. El Mac de tu pareja)
Tu pareja **no necesita volver a rellenar ningún formulario de configuración**:
1. Tu ordenador ya envió automáticamente el sobre de configuración (`ACCOUNT`) a su carpeta `sync/inbox`.
2. Tu pareja abre la aplicación en su Mac y entra a **`👥 Economía del Hogar`**.
3. El sistema detectará la invitación en su buzón y le mostrará una tarjeta destacada:
   > 💌 **¡Invitación de Hogar Detectada!**  
   > Se ha recibido una invitación para unirse a **Hogar Raúl y Ana**, creado por Raúl.
4. Tu pareja solo tiene que pulsar **`[✨ Unirse a este Hogar en 1-Clic]`**.
5. ¡Listo! Automáticamente su perfil se configura como la pareja del hogar de forma simétrica, con los mismos fondos, sueldos de referencia y categorías.

---

## ❓ 6. Preguntas Frecuentes (FAQ)

### ¿Puede mi pareja ver en qué gasto mi dinero personal?
**Rotundamente no.** Tu base de datos personal (`finanzas.db`) nunca se comparte ni se sincroniza. Solo se transmiten los gastos que se introducen explícitamente desde la pestaña *"👥 Economía del Hogar"* y las aportaciones acordadas.

### ¿Qué pasa si este mes gano más o menos dinero?
En el banner de aportación personal al inicio de mes, el sistema te sugerirá tu cuota habitual. Sin embargo, el campo es editable: puedes cambiar el número y asentar exactamente lo que hayas acordado con tu pareja para ese mes concreto.

### ¿Qué pasa si cerramos o desactivamos la cuenta conjunta?
Si pulsas el botón de desactivar cuenta conjunta en la pestaña de Configuración:
- Tu cuenta conjunta se vacía y vuelve al estado inicial de bienvenida.
- **Tu perfil personal no pierde nada**: tus transacciones históricas personales, fondos y presupuestos permanecen intactos.

### ¿Qué ocurre si se va la luz o un ordenador está apagado mientras se anota un gasto?
El sistema está diseñado a prueba de fallos (*Event Sourcing*). El gasto se guarda en tu equipo local y el mensaje de sincronización queda encolado. Cuando el segundo ordenador se encienda y se conecte a la red, Syncthing entregará el mensaje y se actualizará al instante sin generar duplicados.
