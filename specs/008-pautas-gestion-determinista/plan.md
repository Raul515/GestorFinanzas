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

### Fase 5: Depuración Visual, Pruebas Integrales y Consolidación [COMPLETADA]

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

---

### Fase 6: Mejoras y Corrección de Bugs (Post-Fase 5) [COMPLETADA]

- **Objetivo**: Corregir problemas detectados en la prueba de uso real: consolidar el Fondo de Emergencia como métrica global persistente compartida entre todas las pantallas y meses, reestructurar las tarjetas superiores del Resumen Anual (5 tarjetas en distribución 3 + 2) y pulir textos informativos del fondo en los meses.
- **Resumen Breve de Problemas y Soluciones**:
  1. **Reparto Dinámico 80/20** (*Completado*):
     - *Problema*: Al seleccionar 3 divisiones se mantenían los valores previos sumando 25% en vez de 20%.
     - *Solución*: Claves de widgets aisladas por `num_splits` y valores por defecto automáticos (2: 10/10; 3: 10/5/5; 4: 5/5/5/5).
  2. **Excedente a Deseos como Transacción Real** (*Completado*):
     - *Problema*: Se incrementaba `MonthlyBudget`, inflando el presupuesto y no registrándose en el historial de transacciones.
     - *Solución*: Se crea una `Transaction` de gasto real con concepto claro sin modificar el presupuesto planificado, apareciendo en el historial.
  3. **Persistencia y Detección de Estrategia Aplicada** (*Completado*):
     - *Problema*: El evaluador volvía a presentar el excedente como pendiente tras haber aplicado una estrategia.
     - *Solución*: Nuevo modelo `AppliedGuidelineStrategy` para persistir la ejecución y transicionar el estado a informativo ("Optimizado" o "Colchón Activo") suprimiendo los botones repetidos.
  4. **Linter @current_problems** (*Completado*):
     - *Problema*: Advertencia de `datetime.utcnow` deprecado en el modelo y error de sintaxis en `summary_headline`.
     - *Solución*: Actualizado a `datetime.datetime.now(datetime.timezone.utc)` y eliminación de coma espuria.
  5. **Fondo de Emergencia como Estado Global Compartido (Screener, Copiloto, Deep Dive y Meses Vacíos)** (*Completado*):
     - *Problema*: En meses sin presupuesto de Necesidades (ej. diciembre o plantilla BASE no rellenada) y en pestañas globales (Screener, Deep Dive, Copiloto), `_resolve_monthly_needs` devolvía 0.0 €, provocando que `evaluate_safety_status` colapsara la cobertura a 0.0 meses y marcara el fondo como "En Construcción", deshabilitando la inversión a pesar de tener 730 € acumulados.
     - *Solución*:
       - `_resolve_monthly_needs` implementa una cadena de fallback robusta: si el mes solicitado o BASE tienen 0.0 €, busca el gasto en Necesidades del mes más reciente con datos o transacciones reales.
       - `sync_fund_state` y `evaluate_safety_status` infieren la meta de referencia y no degradan `is_completed` a `False` si las necesidades son 0.0 € y el fondo ya tenía saldo suficiente.
  6. **Reestructuración de Tarjetas en Resumen Anual (5 Tarjetas en Distribución 3 + 2)** (*Completado*):
     - *Problema*: El Resumen Anual solo tenía 4 tarjetas en 1 fila y no mostraba el estado del Fondo de Emergencia ni los meses de cobertura.
     - *Solución*:
       - Fila 1 (3 tarjetas): Ingresos Netos Anuales, Gasto Corriente Consolidado, Tasa de Ahorro Media Real.
       - Fila 2 (2 tarjetas): Ahorro Acumulado Total, Estado del Fondo de Emergencia (Saldo actual en € y meses cubiertos).
  7. **Limpieza del Texto Informativo del Fondo Completo en los Meses** (*Completado*):
     - *Problema*: En meses donde el fondo está completo se mostraba la frase redundante: *"Asignación sugerida este mes a 'Fondo de emergencia': 0,00 €."*.
     - *Solución*: Omitida esa frase cuando `is_completed` es `True`, manteniendo el titular positivo: `Fondo Completo (X meses cubiertos): Capacidad de inversión autorizada.`.
  8. **Sincronización de Salvaguarda en Comité Asesor y Copiloto Patrimonial** (*Completado*):
     - *Problema*: En `app.py` ambas pestañas consultaban claves inexistentes (`investing_allowed`, `target_3m`) en vez de las propiedades de `SafetyStatusResponse` (`can_invest`, `target_amount`), evaluando permanentemente el fondo como incompleto y mostrando el veto constitucional. Además, las herramientas de backend (`copilot_tools.py` y `committee_tools.py`) no utilizaban el fallback histórico de necesidades.
     - *Solución*: Corregir las claves en `app.py` (`can_invest`, `is_completed`, `target_amount`) y asegurar que las herramientas de IA utilicen la resolución de necesidades con fallback histórico.
  9. **Coherencia y Concurrencia de Transacciones vs Estrategias Aplicadas (Opción A con Cascada)** (*Completado*):
     - *Problema*: Al eliminar transacciones creadas por una estrategia de excedente desde el historial, el registro `applied_guideline_strategies` permanecía intacto, marcando falsamente el mes como optimizado y dejando dinero huérfano o asimetrías patrimoniales (ej. 80/20 parcial).
     - *Solución*:
       - Añadir `applied_strategy_id` con clave foránea en `Transaction` vinculada a `AppliedGuidelineStrategy`.
       - Implementar endpoint `POST /guidelines/revert-strategy` y botón `↩️ Deshacer Estrategia` en la tarjeta de Pautas Operativas para revertir atómicamente el paquete completo (elimina transacciones, revierte saldo del fondo y restablece el excedente y tarjetas interactivas).
  10. **Refinamiento Visual y UX de Pautas Operativas** (*Completado*):
      - *Problema*:
        - El botón de revertir estrategia estaba flotando abajo a la derecha de forma asimétrica y no tenía protección ante pulsaciones accidentales.
        - Se mostraba un emoji duplicado de bombilla (`💡 💡 Colchón Prudencial...`) en el banner azul.
        - El texto de *Recomendación Operativa* en la tarjeta naranja de Dinero Sin Asignar comenzaba a 0px a la izquierda, desalineado con el icono `⚠️` superior (desfase de 24px).
      - *Solución*:
        - Centrado del botón `↩️ Deshacer Estrategia` bajo el banner y encapsulado en un `st.popover` con advertencia explícita y botón primario de confirmación (`Sí, deshacer estrategia`).
        - Eliminación del emoji redundante en el título del backend y control defensivo en frontend para no duplicar iconos.
  11. **Barrido de Fin de Mes Inteligente con Continuidad de Estrategia (Colchón Prudencial)** (*Completado*):
      - *Problema*: Al llegar fin de mes habiendo elegido una estrategia con Colchón Prudencial (ej. Enfoque Híbrido 80/20), el remanente no gastado en cuenta corriente se transfería al 100% a una sola subcategoría de ahorro, ignorando la asignación del 20% a deseos/amortización que el usuario había planificado para ese mes.
      - *Solución*:
        - Ampliar el esquema `SweepRequest` para admitir `mode: Literal["DEFAULT_SAVINGS", "INHERIT_STRATEGY"]` (o lista de asignaciones resultantes).
        - En backend (`/guidelines/sweep`), si `mode == "INHERIT_STRATEGY"`:
          - Reutiliza la configuración de la estrategia activa (`AppliedGuidelineStrategy`) para distribuir el remanente proporcionalmente entre Ahorro (ej. 80%) y Deseos (ej. 20%).
          - Vincula las transacciones generadas con `applied_strategy_id`, actualiza el Fondo de Emergencia y liquida el colchón (`cushion_amount = 0.0`, `is_partial = False`).
          - Si el modo es `DEFAULT_SAVINGS` (o no hubo estrategia previa), canaliza el 100% a la subcategoría de ahorro seleccionada.
        - En frontend (`guidelines_view.py`), en la tarjeta de Cierre de Mes (día >= 26):
          - Si hay colchón activo en el mes, presenta la elección clara:
            - **Opción A (Recomendada)**: Completar la estrategia del mes (muestra el reparto exacto en € a Ahorro y Deseos).
            - **Opción B**: Barrer 100% a Ahorro tradicional.
          - Si no hubo estrategia previa en el mes, muestra directamente el selector tradicional de 100% a Ahorro.
  12. **Supresión de Recomendaciones Redundantes a Fin de Mes cuando el Barrido está Activo** (*Completado*):
      - *Problema*: Al llegar a fin de mes (día >= 26 o meses pasados) con remanente en cuenta corriente, se mostraban simultáneamente las estrategias no aplicadas de *Excedente Positivo en Necesidades Básicas* (FIRE, Sinking Fund, 80/20) y la advertencia de *Dinero Sin Asignar Elevado*, compitiendo con la tarjeta de *Barrido de Fin de Mes* cuando la única acción que corresponde ejecutar a cierre contable es dicho barrido.
      - *Solución*:
        - En `guidelines_view.py`, determinar si el barrido está activo (`is_sweep_active = is_month_end_window and unassigned_cash > 5.0 and bool(savings_subcats)`).
        - Si está activo, filtrar la lista de pautas visibles suprimiendo `HIGH_UNASSIGNED`, `OPTIMAL` y `NEEDS_SURPLUS` no aplicado (preservando únicamente estados ya ejecutados como *Colchón Prudencial Activo* con su opción de deshacer, o alertas de déficit real).
  13. **Manejo de Meses Vacíos sin Información Financiera** (*Completado*):
      - *Problema*: En meses donde no se han registrado ingresos ni gastos (ej. meses pasados antes de usar la app o meses futuros sin rellenar), el evaluador consideraba que no había desviaciones y lo marcaba falsamente como "Cumplimiento Presupuestario Óptimo" con cifras en 0.00 €, mostrando tablas sinópticas vacías y felicitando por una disciplina inexistente.
      - *Solución*:
        - En backend (`guidelines_service.py`), detectar si `real_income <= 0.0` y `total_spent <= 0.0` sin estrategia aplicada. En tal caso, fijar `is_empty_month = True`, `overall_status = "Mes sin Información Financiera"`, y dejar `guidelines` y `synoptic_table` vacías.
        - En esquema `MonthlyGuidelineReport`, añadir `is_empty_month: bool = False`.
        - En frontend (`guidelines_view.py`), si `is_empty_month` es `True`, mostrar un desplegable informativo limpio con aviso: *"ℹ️ Mes sin información financiera. No hay registros de ingresos ni gastos para este período"*, omitiendo tablas sinópticas, métricas 50/30/20 engañosas y tarjetas de estrategia. Asimismo, se implementó control homólogo para años sin actividad en `evaluate_annual_guidelines` y `render_annual_guidelines_expander`.
  14. **Reset Selectivo de Campos y Formato de Fecha en Nueva Transacción** (*Completado*):
      - *Problema*: Al registrar una transacción, los campos de cantidad y concepto conservaban los valores previos obligando a borrarlos manualmente para la siguiente transacción. Además, la fecha se mostraba en formato anglosajón `AAAA/MM/DD` en vez del estándar español `DD/MM/AAAA`.
      - *Solución*:
        - En `app.py`, resetear automáticamente `st.session_state` de concepto (`""`) y cantidad (`0.0`) tras inserción exitosa, conservando los valores seleccionados de fecha, categoría y subcategoría para agilizar cargas consecutivas.
        - Configurar `format="DD/MM/YYYY"` en `st.date_input` para presentar la fecha en formato día/mes/año (`DD/MM/AAAA`) y formatear de forma análoga la fecha mostrada en la tabla del historial de transacciones.
  15. **Paridad Total de Coherencia, Persistencia, Deshacer y Cascada en Ingreso Extraordinario / Bonus (`EXTRAORDINARY_INCOME`)** (*Completado*):
      - *Problema*: `EXTRAORDINARY_INCOME` guardaba su estrategia con `scenario_type = 'NEEDS_SURPLUS'` hardcodeado en el backend, provocando colisión con la estrategia de necesidades, impidiendo que el evaluador reconociera el bonus como ya asignado y omitiendo el botón `↩️ Deshacer Estrategia` en la vista.
      - *Solución*:
        - En `guidelines.py` (`apply_guideline_strategy_endpoint`), desacoplar y parametrizar `target_scenario = 'EXTRAORDINARY_INCOME'` cuando `request.strategy_type == 'EXTRAORDINARY_INCOME'` y guardar el registro `AppliedGuidelineStrategy` con aislamiento total.
        - Generar transacciones vinculadas con `applied_strategy_id` y descripciones distintivas (`[Pauta EXTRAORDINARY_INCOME] Bonus Extraordinario`).
        - En `guidelines_view.py`, habilitar la visualización del icono `✅` y el botón central `↩️ Deshacer Estrategia` con popover de confirmación para estados con 'Asignado'.
        - Asegurar soporte de coexistencia multi-estrategia (`applied_strategies_map`) para meses con excedente en necesidades y bonus extraordinario concurrente.
        - Cobertura 100% probada con tests unitarios e integrados de aplicación, reporte informativo sin formularios redundantes, reversión atómica vía API y reversión en cascada al borrar una transacción vinculada desde el historial.



