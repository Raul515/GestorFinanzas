# Plan de Implementación: Especificación 013 - Reestructuración Integral de UX/UI y Navegación del Frontend

Este plan detalla la ejecución fase a fase de la **Spec 013**, orientada a eliminar la sobrecarga cognitiva en el perfil personal (eliminando la fila infinita de 21 pestañas en favor de un menú lateral modular) y optimizar la usabilidad ergonómica de la cuenta conjunta.

Conforme a la **Directriz 2 de AGENTS.md**, cada fase se implementará de manera estrictamente secuencial, deteniéndose obligatoriamente al finalizar para solicitar la confirmación explícita del usuario antes de avanzar.

---

## Fase 1: Reestructuración Modular de la Cuenta Personal (`src/frontend/app.py`) [COMPLETADA]

### Objetivos:
- Implementar el sub-selector contextual en el sidebar (`st.sidebar.radio`) condicionado estrictamente a `context_mode == "👤 Mi Perfil Personal"`, con persistencia y sincronización mediante `st.session_state["personal_active_module"]` para evitar desajustes visuales al cambiar de espacio.
- Desacoplar las herramientas en 3 áreas especializadas:
  1. `📊 Presupuesto y Meses`: simplificado a 2 pestañas (`📊 Resumen Anual` y `📅 Gestión Mensual`) con navegación ágil `[◀ Mes Anterior] [Selector de Mes] [Mes Siguiente ▶]` sincronizada con `st.session_state["personal_active_month_idx"]`. Carga acelerada 10x al calcular únicamente el mes activo.
  2. `🧠 Inversión y Mercado (IA)`: 5 pestañas (`🌐 Radar Macro y Noticias`, `🔍 Screener y Oportunidades`, `🔬 Análisis Fundamental (Deep Dive)`, `💬 Copiloto Patrimonial`, `🏛️ Comité Asesor Multiagente`).
  3. `⚙️ Ajustes y Sistema`: 3 pestañas (`📝 Presupuesto Base y Fondo de Emergencia`, `💾 Base de Datos y Copias de Seguridad`, `🚀 Actualizaciones del Sistema`).
- Confinar el banner asistido de aportación al hogar exclusivamente a `📊 Presupuesto y Meses`, impidiendo su renderizado en IA o Ajustes.
- Asegurar que cuando el usuario elija `👥 Economía del Hogar (Cuenta Conjunta)`, el sub-selector lateral no se dibuje ni ocupe espacio.

### Archivos Afectados:
- `src/frontend/app.py`

### Verificación de Fase 1:
- `.\venv\Scripts\python -m compileall src/frontend/app.py`
- Ejecución de pruebas unitarias de frontend pertinentes (`tests/unit/test_personal_ux_frontend.py`).
- **Puerta de Control**: Aprobada por el usuario.

---

## Fase 2: Refinamiento Ergonómico de la Cuenta Conjunta (`src/frontend/views/joint_view.py`) [COMPLETADA]

### Objetivos:
- **Navegación mensual ágil (RF-6)**: Añadir en `_render_tab_12_meses` un control de salto rápido de mes en 1 clic (con botones `◀️ Mes Anterior` y `Mes Siguiente ▶️` flanqueando el selector de mes actual), sincronizado con `st.session_state`.
- **Estructuración simétrica de movimientos (RF-7)**: En la pestaña mensual, unificar el registro de gastos comunes y aportaciones en 2 columnas contiguas balanceadas (`[🛒 Registrar Gasto Común]` vs `[💰 Asentar Aportación]`), reduciendo el scroll vertical en un 50%.
- **Elevación de Tasa de Esfuerzo Familiar (RF-8)**: En `_render_tab_resumen_anual`, situar la tarjeta de diagnóstico del esfuerzo familiar constitucional (ratio necesidades / ingresos netos) en el bloque superior junto a las métricas agregadas del año.
- **Separación visual de Configuración (RF-10)**: Inyectar directiva CSS Flexbox (`margin-left: auto`) para fijar la pestaña `⚙️ Configuración del Hogar y Sincronización` al extremo derecho de la barra de pestañas.

### Archivos Afectados:
- `src/frontend/views/joint_view.py`

### Verificación de Fase 2:
- `.\venv\Scripts\python -m compileall src/frontend/views/joint_view.py`
- Ejecución de pruebas de la cuenta conjunta (`tests/unit/test_joint_ux_frontend.py` y `test_joint_frontend.py`).
- **Puerta de Control**: Aprobada por el usuario.

---

## Fase 3: Pruebas Automatizadas de Frontend, Verificación RNF y Cierre [COMPLETADA]

### Objetivos:
- Actualizar o añadir pruebas unitarias para validar la lógica de renderizado condicional de los módulos.
- Validar formato de fechas estricto (`DD/MM/AAAA`) y compatibilidad Streamlit 1.60+.
- Verificación de sintaxis global con `compileall` sobre `src` y `tests`.
- Actualización de memoria persistente (`MEMORY.md`).
- Presentación de resumen final para autorización de merge a `develop`.

