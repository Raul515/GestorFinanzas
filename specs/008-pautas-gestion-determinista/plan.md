# Plan de Implementación: Especificación 008 — Pautas Deterministas de Gestión y Compensación Presupuestaria

Este plan técnico desglosa la implementación de la **Especificación 008** en 2 fases secuenciales estrictas. Siguiendo la metodología SDD (*Spec-Anchored*), cada fase requiere el 100% de sus pruebas automatizadas pasando y la confirmación explícita del usuario antes de avanzar a la siguiente.

---

### Fase 1: Esquemas de Dominio Pydantic y Motor de Reglas Deterministas en Backend [COMPLETADA]

- **Objetivo**: Desarrollar los modelos de datos tipados y el motor puro de cálculo determinista para evaluar las desviaciones presupuestarias y emitir planes de acción en cifras reales (euros y porcentajes).
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/guidelines.py` [NUEVO: Esquemas Pydantic v2 `GuidelineActionStrategy`, `CompensationStep`, `MonthlyGuidelineItem`, `MonthlyGuidelineReport`, `AnnualGuidelineReport`]
  - `src/backend/services/guidelines_service.py` [NUEVO: Funciones puras `evaluate_monthly_guidelines` y `evaluate_annual_guidelines`]
  - `tests/unit/test_guidelines_service.py` [NUEVO: Suite unitaria completa para los 6 escenarios mensuales y 4 anuales]
- **Casos de Prueba a Verificar**:
  - `NEEDS_SURPLUS`: Cálculo exacto del excedente y generación de las 3 estrategias con números reales (FIRE condicional al Fondo de Emergencia, Sinking Fund y Bonus 80/20).
  - `NEEDS_DEFICIT`: Jerarquía de absorción presupuestaria (1º Deseos, 2º Ahorro del mes) y prohibición explícita de recurrir al Fondo de Emergencia.
  - `WANTS_DEFICIT`: Deducción íntegra sobre el Ahorro del mes, confirmación innegociable de no tocar Fondo de Emergencia y pauta de recorte compensatorio en el mes siguiente.
  - `INCOME_SHORTFALL`: Protocolo de contingencia y congelación de Deseos.
  - `EXTRAORDINARY_INCOME`: Distribución de paga extra/bonus según estado del Fondo de Emergencia.
  - `HIGH_UNASSIGNED`: Detección de liquidez invisible superior al 5% de los ingresos.
  - Escenarios Anuales: Detección de tasa de ahorro deficitaria, *lifestyle creep*, rigidez de costes fijos y exceso de liquidez ociosa.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py
  ```
- **Criterio de Aceptación**: 100% de pruebas unitarias pasando (14/14 tests pasando).

---

### Fase 2: Integración en Frontend Streamlit (Pestañas Mensuales y Resumen Anual) [COMPLETADA]

- **Objetivo**: Integrar los componentes visuales interactivos en Streamlit: desplegables (`st.expander`) debajo del gráfico 50/30/20 en cada mes (1 a 12) y debajo del Flujo Dinámico en el Resumen Anual, con tablas sinópticas y estrategias personalizadas con cifras reales.
- **Archivos a crear/modificar**:
  - `src/frontend/services/guidelines_view.py` [NUEVO: Utilidades de formateo HTML/UI para la tabla sinóptica y bloques de estrategia]
  - `src/frontend/style.css` [MODIFICADO: Clases CSS para tarjetas de información, aviso y alerta]
  - `src/frontend/app.py` [MODIFICADO: Inserción del `st.expander` contextual en las pestañas de los meses 1-12 y en el Resumen Anual]
  - `tests/unit/test_guidelines_view.py` [NUEVO: Verificación de renderizado de tablas, tarjetas y reexportación]
  - `MEMORY.md` [MODIFICADO: Registrar cierre de Spec 008]
  - `specs/README.md` [MODIFICADO: Actualizar estado de Spec 008 a Completada]
- **Casos de Prueba a Verificar**:
  - Visualización del desplegable bajo el gráfico 50/30/20 con badges de severidad según el estado contable de cada mes.
  - Renderizado de la tabla sinóptica de decisión rápida y las tarjetas de estrategia con los importes reales del mes en euros.
  - Diagnóstico estructural anual integrado en la Pestaña 0.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py tests/unit/test_guidelines_view.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas asociadas pasando sin errores ni advertencias de tipo (19/19 tests pasando).

---

### Fase 3: Asignaciones Positivas de Capital (Manejo de Excedentes y Barrido de Cierre) [COMPLETADA]

- **Objetivo**: Desarrollar los contratos y la ejecución atómica interactiva para la asignación de capital positivo: excedente en Necesidades (`NEEDS_SURPLUS`) con selector de modo (100% Total vs 50% con Colchón Interno), partición configurable del 20% a Deseos (hasta 4 partes de min. 5%), distribución de bonus/paga extra (`EXTRAORDINARY_INCOME`), y acción de "Barrido de Fin de Mes" (a partir del día 26) para remanentes.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/guidelines.py` [MODIFICADO: Esquemas `AllocationItem`, `StrategyApplyRequest`, `StrategyApplyResponse`, `SweepRequest`]
  - `src/backend/api/routers/guidelines.py` [MODIFICADO: Endpoints atómicos `POST /guidelines/apply-strategy` y `POST /guidelines/sweep`]
  - `src/frontend/api_client.py` [MODIFICADO: Métodos `apply_guideline_strategy` y `sweep_month_surplus`]
  - `src/frontend/services/guidelines_view.py` [MODIFICADO: Controles de modo 100%/50%, selector de subcategorías, selector/validador de división de deseos 80/20, botones de aplicar para `NEEDS_SURPLUS` y `EXTRAORDINARY_INCOME`, y banner interactivo de barrido a fin de mes]
  - `tests/integration/test_guidelines_api.py` [MODIFICADO: Pruebas de integración para `apply-strategy` y `sweep`]
  - `tests/unit/test_guidelines_view.py` [MODIFICADO: Pruebas unitarias para controles de asignación positiva y validadores de suma del 20%]
- **Casos de Prueba a Verificar**:
  - Traspaso del 100% vs 50% con colchón interno en Necesidades Básicas sin crear subcategorías ficticias.
  - Creación atómica de transacciones en Ahorro e incremento de presupuestos en Deseos.
  - Blindaje constitucional del Fondo de Emergencia: forzado al fondo si `coverage_months < target_months` en FIRE y 80% en la regla 80/20.
  - Validación de particiones en Deseos: inhabilitación si la suma difiere del 20% o si algún bloque < 5%.
  - Activación del botón de Barrido de Fin de Mes exclusivamente a partir del día 26 o en meses pasados.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py tests/unit/test_guidelines_view.py tests/integration/test_guidelines_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas pasando antes de avanzar a la Fase 4.

---

### Fase 4: Compensación y Contención Negativa (Protección Presupuestaria y Disciplina) [COMPLETADA]

- **Objetivo**: Desarrollar la lógica y los botones interactivos para escenarios de desviación adversa: ajuste compensatorio intermensual para sobregasto en Deseos (`WANTS_DEFICIT`), amortiguación de picos de Necesidades desde Deseos del mes (`NEEDS_DEFICIT`) y congelación de ocio ante caídas de ingresos (`INCOME_SHORTFALL`).
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/guidelines.py` [MODIFICADO: Esquemas de request/response para compensación `CompensateDeficitRequest`]
  - `src/backend/api/routers/guidelines.py` [MODIFICADO: Endpoints atómicos `POST /guidelines/compensate-deficit`]
  - `src/frontend/api_client.py` [MODIFICADO: Método cliente `compensate_guideline_deficit`]
  - `src/frontend/services/guidelines_view.py` [MODIFICADO: Botones interactivos para ajuste compensatorio al mes siguiente en `WANTS_DEFICIT`, amortiguación en `NEEDS_DEFICIT` y congelación en `INCOME_SHORTFALL`]
  - `tests/integration/test_guidelines_api.py` [MODIFICADO: Pruebas de integración para compensación y ajuste intermensual]
- **Casos de Prueba a Verificar**:
  - Ajuste compensatorio de `WANTS_DEFICIT`: reducción del presupuesto de Deseos del mes siguiente en el importe exacto del exceso.
  - Amortiguación de `NEEDS_DEFICIT`: reducción del presupuesto de Deseos del propio mes sin tocar Fondo de Emergencia.
  - Congelación de ocio en `INCOME_SHORTFALL`: ajuste temporal de partidas de ocio a cero.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py tests/unit/test_guidelines_view.py tests/integration/test_guidelines_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas pasando antes de avanzar a la Fase 5.

---

### Fase 5: Depuración Visual, Pruebas Integrales y Consolidación [PENDIENTE]

- **Objetivo**: Corregir definitivamente los fallos visuales de la interfaz de Streamlit (erradicación de `</tbody> </table>` por indentación markdown y supresión de `st.caption` en tarjetas con estrategias preservándolo en `HIGH_UNASSIGNED`), realizar una batería integral de pruebas unitarias y de integración, y consolidar la documentación en `MEMORY.md` y `specs/README.md`.
- **Archivos a crear/modificar**:
  - `src/frontend/services/guidelines_view.py` [MODIFICADO: Limpieza de indentación HTML con formato compacto y supresión de pies de recomendación en tarjetas estratégicas]
  - `tests/unit/test_guidelines_view.py` [MODIFICADO: Verificación de ausencia de etiquetas HTML literales y visualización selectiva de recomendaciones]
  - `MEMORY.md` [MODIFICADO: Registrar cierre de las Fases 3, 4 y 5 de la Spec 008]
  - `specs/README.md` [MODIFICADO: Marcar Spec 008 como Completada]
- **Casos de Prueba a Verificar**:
  - Tabla sinóptica 100% limpia sin etiquetas HTML visibles en el navegador.
  - Ausencia de texto de recomendación operativa al pie de las tarjetas con estrategias, manteniéndolo únicamente en Dinero Sin Asignar.
  - Comprobación de tipos y sintaxis con `compileall`.
  - Suite completa de pruebas de la especificación pasando al 100%.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py tests/unit/test_guidelines_view.py tests/integration/test_guidelines_api.py
  .\venv\Scripts\python -m compileall src tests
  ```
- **Criterio de Aceptación**: 100% de las pruebas pasando y cero errores de sintaxis.
