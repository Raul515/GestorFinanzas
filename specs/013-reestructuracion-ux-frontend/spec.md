# Especificación 013: Reestructuración Integral de UX/UI y Arquitectura de Navegación del Frontend

## 1. Resumen Ejecutivo y Visión

A medida que el **Gestor de Finanzas Personales y del Hogar** ha crecido incorporando capacidades avanzadas (Comité Asesor LangGraph, Screener, Deep Dive, Copiloto, Copias de Seguridad y Actualizador OTA), la interfaz de usuario en Streamlit ha alcanzado un punto crítico de sobrecarga cognitiva y desbordamiento horizontal:
- **La "Fila Infinita"**: El perfil personal acumulaba **21 pestañas en una sola barra horizontal** (`st.tabs()`), obligando al usuario a pulsar flechas diminutas de desplazamiento para acceder a herramientas vitales de administración.
- **Mezcla Caótica de Dominios**: En el mismo carril visual convivían la contabilidad diaria determinista (mes a mes), los agentes cognitivos basados en IA (que consumen tokens y requieren Gemini API Key) y los paneles administrativos de bajo nivel (backups SQLite y actualizador OTA).
- **Fricciones en la Cuenta Conjunta**: Aunque la cuenta conjunta está mucho mejor acotada (5 pestañas), la navegación mensual mediante un desplegable largo de 12 elementos ralentiza el salto entre meses inmediatos, los formularios de entrada de gastos y aportaciones acumulan scroll vertical excesivo y el semáforo constitucional de salud financiera familiar quedaba relegado al final de la página.

El objetivo de esta especificación es **reestructurar radicalmente la arquitectura de información y usabilidad de la aplicación**:
1. **Cuenta Personal Modular**: Desacoplar la experiencia en **3 áreas funcionales** mediante un submenú en el menú lateral (`st.sidebar`):
   - `📊 Presupuesto y Meses` (13 pestañas limpias sin desbordamiento horizontal).
   - `🧠 Inversión y Mercado (IA)` (5 pestañas analíticas bajo demanda).
   - `⚙️ Ajustes y Sistema` (3 pestañas de administración del sistema y copias de seguridad).
2. **Visibilidad Condicional Estricta**: El selector de sub-módulos del menú lateral **solo se muestra y opera cuando el usuario está en `👤 Mi Perfil Personal`**. Al conmutar a `👥 Economía del Hogar`, el sub-selector desaparece por completo del sidebar.
3. **Ergonomía en Cuenta Conjunta**: Incorporar navegación mensual ágil en 1 clic, agrupar las acciones de registro de movimientos (gastos comunes vs aportaciones) y elevar el semáforo de Esfuerzo Familiar a la cabecera del Resumen Anual.

---

## 2. Historias de Usuario (HU)

- **HU-1 (Contabilidad Mensual sin Fricción)**: Como usuario que solo desea anotar sus gastos diarios y consultar el estado de su presupuesto 50/30/20 y fondo de emergencia, quiero ver una barra de pestañas que contenga exclusivamente el Resumen Anual y los 12 meses, sin flechas de scroll horizontal ni herramientas de IA estorbando.
- **HU-2 (Acceso Deliberado a Herramientas de IA)**: Como usuario inversor, quiero acceder a los análisis fundamentales, screener, macro y comités asesores en un espacio propio dedicado, sabiendo que ahí se concentran las herramientas analíticas sin mezclar registros de facturas domésticas.
- **HU-3 (Gestión del Sistema Aislada)**: Como usuario que necesita hacer una copia de seguridad o buscar actualizaciones OTA, quiero acceder a un módulo específico de Ajustes y Sistema en 1 clic desde el menú lateral, sin tener que buscar entre meses contables.
- **HU-4 (Menú Lateral Inteligente y Contextual)**: Como usuario que alterna entre su economía personal y la del hogar, quiero que el menú lateral solo me muestre opciones relevantes a mi espacio actual: si entro a la Cuenta Conjunta, no quiero ver sub-secciones personales.
- **HU-5 (Navegación Mensual Ágil en el Hogar)**: Como pareja que revisa los gastos comunes, quiero cambiar entre meses contiguos con un control directo en 1 clic sin tener que abrir desplegables largos de 12 opciones.
- **HU-6 (Diagnóstico Inmediato de Esfuerzo Familiar)**: Como pareja que abre el Resumen Anual del hogar, queremos ver de inmediato si nuestra tasa de esfuerzo familiar está en zona óptima (<=50%) o en sobreesfuerzo, sin necesidad de hacer scroll hasta el final.

---

## 3. Requerimientos Funcionales (RF)

### 3.1 Módulo Cuenta Personal (`src/frontend/app.py`)

- **RF-1 (Sub-selector Modular en Sidebar con Persistencia de Estado)**:
  - Cuando `context_mode == "👤 Mi Perfil Personal"`, el `st.sidebar` debe renderizar un control `st.sidebar.radio` titulado `"Módulo Personal"` con 3 opciones:
    1. `📊 Presupuesto y Meses`
    2. `🧠 Inversión y Mercado (IA)`
    3. `⚙️ Ajustes y Sistema`
  - Debe sincronizarse con `st.session_state["personal_active_module"]` para garantizar que al conmutar entre espacios el indicador visual del radio button y la vista renderizada se mantengan 100% coherentes.
- **RF-2 (Visibilidad Condicional Estricta)**:
  - Cuando `context_mode == "👥 Economía del Hogar (Cuenta Conjunta)"`, el sub-selector de `"Módulo Personal"` **no debe renderizarse en el sidebar bajo ninguna circunstancia**.
- **RF-3 (Espacio `📊 Presupuesto y Meses` con 2 Pestañas y Navegación Ágil)**:
  - Debe renderizar exactamente **2 pestañas**:
    1. `📊 Resumen Anual`
    2. `📅 Gestión Mensual`
  - En `📅 Gestión Mensual`, la navegación se realiza mediante botonera rápida `[◀ Mes Anterior] [Selector de Mes] [Mes Siguiente ▶]` sincronizada con `st.session_state["personal_active_month_idx"]`.
  - Solo se consultan a la API y se calculan las métricas del mes seleccionado, erradicando el bucle de 12 meses simultáneos y acelerando 10x la carga del frontend.
- **RF-4 (Espacio `🧠 Inversión y Mercado (IA)`)**:
  - Debe renderizar exactamente **5 pestañas**:
    1. `🌐 Radar Macro y Noticias`
    2. `🔍 Screener y Oportunidades`
    3. `🔬 Análisis Fundamental (Deep Dive)`
    4. `💬 Copiloto Patrimonial`
    5. `🏛️ Comité Asesor Multiagente`
  - Si no hay `GEMINI_API_KEY` configurada, estas herramientas deben degradar de forma elegante sin emitir excepciones que afecten al resto del sistema.
- **RF-5 (Espacio `⚙️ Ajustes y Sistema`)**:
  - Debe renderizar exactamente **3 pestañas**:
    1. `📝 Presupuesto Base y Fondo de Emergencia` (con el formulario en expander para visualizar de inmediato el Safety Guard).
    2. `💾 Base de Datos y Copias de Seguridad` (`render_backup_view`).
    3. `🚀 Actualizaciones del Sistema` (`render_updater_view`).
- **RF-9 (Confinamiento del Banner de Aportación al Hogar)**:
  - El banner asistido de aportación al hogar solo debe ejecutarse y mostrarse en el módulo `📊 Presupuesto y Meses`. Queda estrictamente prohibido que aparezca en `🧠 Inversión y Mercado (IA)` o en `⚙️ Ajustes y Sistema`.

### 3.2 Módulo Cuenta Conjunta (`src/frontend/views/joint_view.py`)

- **RF-6 (Navegación Mensual Ágil)**:
  - En `_render_tab_12_meses`, incorporar un selector rápido de meses en 1 clic (utilizando controles de paso inmediato `[◀ Mes Anterior] [Mes a Gestionar] [Mes Siguiente ▶]`) manteniendo la selección sincronizada con `st.session_state["joint_active_month"]`.
- **RF-7 (Acciones de Movimientos del Hogar Simétricas)**:
  - En la pestaña mensual, estructurar el registro de movimientos en 2 columnas contiguas y equilibradas:
    - `[🛒 Registrar Gasto Común]` (operación cotidiana de compras compartidas).
    - `[💰 Asentar Aportación]` (operación mensual de nómina).
- **RF-8 (Visibilidad Inmediata de Tasa de Esfuerzo Familiar)**:
  - En `_render_tab_resumen_anual`, situar la tarjeta del semáforo de salud financiera y tasa de esfuerzo familiar (Principio Constitucional: gasto en necesidades vs ingresos netos combinados) al bloque superior de métricas del año, inmediatamente junto al balance de tesorería y exportación a Excel.
- **RF-10 (Separación Visual de Configuración del Hogar)**:
  - En la fila de pestañas principales de la Cuenta Conjunta, desplazar la pestaña `⚙️ Configuración del Hogar y Sincronización` al extremo derecho de la pantalla mediante directiva CSS Flexbox (`margin-left: auto`), dejando un espacio visual limpio que diferencie la operativa de la administración.

---

## 4. Requerimientos No Funcionales (RNF)

- **RNF-1 (Cero Regresiones Lógicas y Contables)**: Ningún cambio de interfaz debe alterar llamadas a la API, fórmulas contables ni persistencia en SQLite.
- **RNF-2 (Compatibilidad Streamlit 1.60+)**: Todos los componentes deben respetar la nueva API de ancho (`width="stretch"` y `width="content"`).
- **RNF-3 (Formato de Fechas Obligatorio `DD/MM/AAAA`)**: Toda fecha visualizada en tablas, selectores, tooltips y descargas debe cumplir con la Directriz 12 de `AGENTS.md`.
- **RNF-4 (Rendimiento y Respuesta)**: La navegación entre módulos del sidebar debe ser instantánea sin recomputar llamadas pesadas del backend innecesariamente.

---

## 5. Criterios de Aceptación (DoD - Definition of Done)

1. El perfil personal ya no contiene 21 pestañas en una fila; muestra 13 pestañas en contabilidad, 5 en inversión y 3 en ajustes.
2. El sub-selector del sidebar solo es visible en el perfil personal y se oculta al pasar a la cuenta conjunta.
3. La cuenta conjunta cuenta con navegación mensual rápida y semáforo de esfuerzo familiar en cabecera.
4. `compileall` finaliza con 0 errores de sintaxis en `src` y `tests`.
5. La totalidad de las pruebas unitarias y de integración de frontend pasan al 100%.

