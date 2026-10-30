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

### Fase 3: Ejecución Atómica de Estrategias, Colchón Prudencial y Barrido de Cierre [EN PROGRESO]

- **Objetivo**: Habilitar la ejecución directa y atómica de las estrategias desde Streamlit, incorporando selector de modo (100% Total vs 50% con Colchón Interno en Necesidades), partición configurable del 20% en Deseos (1 a 4 partes de min. 5%), blindaje constitucional del Fondo de Emergencia, acción de "Barrido de Fin de Mes" (a partir del día 26) y correcciones visuales de la tabla sinóptica y tarjetas.
- **Archivos a crear/modificar**:
  - `src/backend/domain/schemas/guidelines.py` [MODIFICADO: Esquemas de request/response para ejecución de estrategia y barrido: `StrategyApplyRequest`, `StrategyApplyResponse`, `AllocationItem`]
  - `src/backend/services/guidelines_service.py` [MODIFICADO: Reconocimiento dinámico de colchón interno y transición de estado a "Óptimo / Colchón Activo"]
  - `src/backend/api/routers/guidelines.py` [MODIFICADO: Endpoints atómicos `POST /guidelines/apply-strategy` y `POST /guidelines/sweep`]
  - `src/frontend/api_client.py` [MODIFICADO: Métodos cliente `apply_guideline_strategy` y `sweep_month_surplus`]
  - `src/frontend/services/guidelines_view.py` [MODIFICADO: Eliminación del bug de sangría de tabla sinóptica, retirada de recomendación en tarjetas, selectores de subcategoría, partición de deseos, botón "Aplicar Estrategia" y banner de barrido]
  - `src/frontend/app.py` [MODIFICADO: Sincronización tras ejecución atómica]
  - `tests/unit/test_guidelines_service.py` [MODIFICADO: Pruebas unitarias de cálculo con colchón y asignaciones]
  - `tests/unit/test_guidelines_view.py` [MODIFICADO: Pruebas unitarias de renderizado de controles y particiones]
  - `tests/integration/test_guidelines_api.py` [MODIFICADO: Pruebas de integración para ejecución atómica y barrido]
- **Casos de Prueba a Verificar**:
  - Erradicación de etiquetas `</tbody>` y `</table>` en la tabla sinóptica.
  - Supresión de recomendación operativa en tarjetas con estrategias y conservación en Dinero Sin Asignar.
  - Ejecución atómica en backend: creación de transacción en Ahorro, actualización de saldo en Fondo de Emergencia (si aplica), incremento de presupuesto en Deseos y confirmación de rollback ante fallos.
  - Validación de particiones del 20% en Deseos (bloqueo si suma != 20%, mínimo 5% por parte).
  - Activación contextual del "Barrido de Fin de Mes" a partir del día 26 del mes natural.
  - Transición del estado del mes a "Óptimo / Colchón Activo" una vez aplicada la estrategia.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_guidelines_service.py tests/unit/test_guidelines_view.py tests/integration/test_guidelines_api.py
  ```
- **Criterio de Aceptación**: 100% de las pruebas pasando sin advertencias ni regresiones.
