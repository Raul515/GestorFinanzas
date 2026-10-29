# Especificación 008: Pautas Deterministas de Gestión y Compensación Presupuestaria (Meses y Resumen Anual)

## 1. Resumen Ejecutivo y Visión

Actualmente, el **Gestor de Finanzas Personales** ofrece un seguimiento cuantitativo de alta precisión en las pestañas mensuales (1 a 12) y en el Resumen Anual: calcula desvíos absolutos en euros, clasifica el gasto bajo la regla 50/30/20, audita la tasa de ahorro y monitoriza la cobertura del Fondo de Emergencia (*Safety Guard*). 

Sin embargo, cuando el usuario detecta una desviación presupuestaria (un excedente en Necesidades, un sobregasto en Deseos, una factura inesperada de suministros o una paga extra), la aplicación se limita a reflejar los números en rojo o verde, sin proporcionar **pautas de actuación claras, inmediatas y aplicadas a sus cifras reales**. Para saber qué hacer, el usuario debe recurrir a asesoramiento externo, consultar modelos de lenguaje o tomar decisiones financieras desestructuradas.

El **objetivo** de esta especificación es incorporar un **sistema determinista de pautas de actuación y compensación presupuestaria**:
- **100% Determinista (Sin llamadas a LLM)**: Reglas contables probadas, predecibles, con tiempo de respuesta de 0 ms y coste cero de tokens.
- **Personalizado con Cifras Reales**: No son consejos genéricos abstractos; las pautas calculan los importes exactos en euros (€) y los porcentajes reales correspondientes al mes activo del usuario.
- **Ubicación Contextual e Integrada**: Presentado mediante un desplegable interactivo (`st.expander`) situado inmediatamente debajo del gráfico 50/30/20 en cada pestaña mensual, y debajo del bloque de Flujo Dinámico en el Resumen Anual.
- **Tabla Sinóptica Visual**: Resumen ejecutivo en formato tabla para una toma de decisiones rápida sin saturación de texto.
- **Arquitectura Desacoplada (Principios 3 y 12 de la Constitución)**: Motor financiero puro en backend (`src/backend/services/guidelines_service.py`), esquemas fuertemente tipados con Pydantic v2 en inglés, y capa de presentación en Streamlit 100% en español.

---

## 2. Usuarios y Casos de Uso

- **Usuario Particular e Inversor en España**:
  - Al revisar el mes en curso y ver un excedente en Necesidades (gasto < 50%), necesita saber de inmediato cómo distribuirlo (Acelerador FIRE, Sinking Fund o Bonus 80/20) sin caer en el error de inflar sus Deseos.
  - Si se ha pasado de gasto en Necesidades (gasto > 50%), necesita saber con exactitud de dónde compensar los euros excedidos (Deseos vs Ahorro) y tener la confirmación tajante de si debe o no recurrir al Fondo de Emergencia.
  - Si ha gastado de más en ocio o Deseos (gasto > 30%), necesita conocer el impacto exacto en su tasa de ahorro y tener una pauta para compensarlo en el mes posterior.
  - En el Resumen Anual, necesita un diagnóstico holístico de si su tasa de ahorro ha sido suficiente o si sufre de rigidez de costes fijos o inflación del estilo de vida (*lifestyle creep*).

---

## 3. Historias de Usuario (HU)

- **HU-1 (Guía de Excedente en Necesidades)**: Como usuario que ha gastado menos del 50% en Necesidades Básicas este mes, quiero ver un desglose con 3 estrategias concretas (Acelerador FIRE, Fondo de Proyectos y Regla 80/20) con mis euros exactos de sobrante para potenciar mi patrimonio.
- **HU-2 (Jerarquía de Compensación por Déficit en Necesidades)**: Como usuario que ha sobrepasado el 50% en Necesidades, quiero conocer la jerarquía estricta de compensación (1º Deseos, 2º Ahorro del mes) y verificar que NO debo tocar el Fondo de Emergencia salvo urgencia grave impredecible.
- **HU-3 (Autocorrección por Exceso en Deseos)**: Como usuario que ha gastado más del 30% en Deseos, quiero ver cuánto se ha reducido mi tasa de ahorro real y disponer de una pauta de ajuste compensatorio para el mes siguiente.
- **HU-4 (Tabla Sinóptica de Consulta Rápida)**: Como usuario ocupado, quiero una tabla resumen visual de una sola mirada que me indique qué ha pasado, de dónde sacar el dinero, si se toca el fondo y qué acción aplicar en el presupuesto.
- **HU-5 (Diagnóstico Estructural Anual)**: Como usuario que planifica a largo plazo, quiero que el Resumen Anual me evalúe si mi tasa de ahorro media ha sido deficitaria, si mis costes fijos son demasiado rígidos o si tengo exceso de liquidez ociosa perdiendo valor frente a la inflación.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Motor de Diagnóstico Determinista Mensual (`guidelines_service.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE evaluar el estado contable de un mes a partir de: ingresos reales, gastos reales en Necesidades, Deseos y Ahorro, meta del Fondo de Emergencia y saldos acumulados.
- **Criterio EARS (State-driven)**: MIENTRAS se evalúe un mes, EL SISTEMA DEBE clasificar y activar uno o varios de los siguientes escenarios:
  1. **Needs Surplus (`NEEDS_SURPLUS`)**: Cuando `real_needs < 0.50 * real_income`.
     - Calcula el excedente exacto: `surplus = (0.50 * real_income) - real_needs`.
     - Genera 3 estrategias con importes reales:
       - **Estrategia FIRE**: Si el Fondo de Emergencia no está lleno (`coverage_months < target_months`), derivar el excedente a completar el fondo; si ya está lleno, 100% a inversión indexada a largo plazo.
       - **Estrategia Sinking Fund**: Provisión a medio plazo (depósito/cuenta remunerada) para metas a 3-5 años.
       - **Estrategia Híbrida 80/20**: 80% a Ahorro/Inversión y 20% a Deseos conscientes.
  2. **Needs Deficit (`NEEDS_DEFICIT`)**: Cuando `real_needs > 0.50 * real_income`.
     - Calcula el exceso exacto: `excess = real_needs - (0.50 * real_income)`.
     - Establece la regla: Fondo de Emergencia = **NO** (salvo catástrofe/fuerza mayor).
     - Jerarquía de compensación:
       - 1ª Línea de defensa: Absorber `min(excess, real_wants)` recortando el presupuesto de Deseos de ese mes.
       - 2ª Línea de defensa: Absorber el remanente reduciendo la aportación al Ahorro de ese mes.
       - Diagnóstico: Si el déficit es recurrente, calibrar Presupuesto Base o crear Sinking Fund anual.
  3. **Wants Deficit (`WANTS_DEFICIT`)**: Cuando `real_wants > 0.30 * real_income`.
     - Calcula el sobregasto: `excess = real_wants - (0.30 * real_income)`.
     - Regla inviolable: Fondo de Emergencia = **NUNCA**.
     - Impacto directo: Se resta íntegramente del Ahorro del propio mes.
     - Pauta de autocorrección: Opción de ajuste compensatorio recortando exactamente esa cantidad en Deseos el mes posterior.
  4. **Income Shortfall (`INCOME_SHORTFALL`)**: Cuando `real_income < budget_income`.
     - Protocolo de contención: Congelar Deseos a mínimos no cancelables, pausar inversión y activar el Fondo de Emergencia solo si el ingreso no cubre las Necesidades Básicas mínimas.
  5. **Extraordinary Income (`EXTRAORDINARY_INCOME`)**: Cuando `real_income > budget_income` (paga extra, bonus).
     - Pauta de distribución de bonus: 100% a Fondo de Emergencia si está incompleto; si está lleno, regla 80/20 (80% inversión/reducción deuda, 20% disfrute).
  6. **High Unassigned (`HIGH_UNASSIGNED`)**: Cuando `unassigned_amount > 0.05 * real_income`.
     - Alerta de liquidez invisible: Dinero en cuenta corriente sin etiquetar en riesgo de dilución.

### RF-2: Motor de Diagnóstico Determinista Anual (`guidelines_service.py`)
- **Criterio EARS (State-driven)**: MIENTRAS se evalúe el Resumen Anual, EL SISTEMA DEBE analizar los 12 meses consolidados y diagnosticar:
  1. **Annual Savings Deficit (`ANNUAL_SAVINGS_DEFICIT`)**: Cuando la tasa de ahorro media anual < 20%. Diagnostica si se debió a meses puntuales de picos de gasto fijo o a sobregasto crónico en Deseos.
  2. **Lifestyle Creep (`LIFESTYLE_CREEP`)**: Cuando el consolidado anual de Deseos supera el 30%.
  3. **Fixed Cost Rigidity (`FIXED_COST_RIGIDITY`)**: Cuando el consolidado anual de Necesidades supera el 50%.
  4. **Idle Cash / Over-liquidity (`IDLE_CASH`)**: Cuando el ahorro acumulado total excede sustancialmente el Fondo de Emergencia (más de 12 meses de necesidades), alertando del coste de oportunidad y pautando compras periódicas (DCA).

### RF-3: Esquemas Fuertemente Tipados (`src/backend/domain/schemas/guidelines.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE modelar las pautas mediante esquemas Pydantic v2:
  - `GuidelineActionStrategy`: Nombre, descripción, asignación en euros y porcentaje.
  - `CompensationStep`: Orden de prioridad, fuente de fondos, importe a compensar y explicación.
  - `MonthlyGuidelineItem`: Tipo de escenario, severidad (`info`, `warning`, `error`), titular, diagnóstico con cifras reales, tabla sinóptica y estrategias sugeridas.
  - `MonthlyGuidelineReport`: Lista de pautas activas, resumen ejecutivo y métricas de soporte.
  - `AnnualGuidelineReport`: Diagnóstico de salud financiera estructural anual y recomendaciones de calibración.

### RF-4: Componentes de Visualización en Streamlit (`src/frontend/app.py`)
- **Criterio EARS (Event-driven)**: CUANDO el usuario visualice una pestaña mensual (Meses 1 a 12), EL SISTEMA DEBE renderizar inmediatamente después del gráfico de metas 50/30/20 un componente `st.expander("💡 Pautas de Actuación y Compensación Presupuestaria")`.
- **Criterio EARS (State-driven)**: MIENTRAS el desplegable esté abierto, EL SISTEMA DEBE mostrar:
  1. **Tarjetas de Alerta Contextual**: Indicando con badges visuales los escenarios detectados con las cifras reales del usuario.
  2. **Tabla Sinóptica de Decisión Rápida**: Columnas: *Escenario*, *¿De dónde se compensa?*, *¿Se toca el Fondo de Emergencia?*, *Acción en el Presupuesto*.
  3. **Estrategias Desglosadas**: Detalle numérico de las opciones disponibles con cálculo del remanente en euros.
- **Criterio EARS (Event-driven)**: CUANDO el usuario visualice la pestaña de Resumen Anual, EL SISTEMA DEBE renderizar bajo el bloque de Flujo Dinámico el expander `💡 Diagnóstico Estructural y Pautas Anuales`.

---

## 5. Requisitos No Funcionales (RNF)

- **RNF-1 (Convenciones de Idioma - Opción 1 de la Constitución)**:
  - Código, modelos, esquemas Pydantic, funciones y variables 100% en inglés (`evaluate_monthly_guidelines`, `MonthlyGuidelineReport`, `GuidelineScenarioEnum`, `excess_amount`, `surplus_amount`).
  - Todo el texto visible para el usuario final en Streamlit, tablas y explicaciones 100% en español.
- **RNF-2 (Determinismo Puro y Rendimiento Instantáneo)**:
  - Tiempo de cálculo < 5 milisegundos por mes.
  - 0 llamadas de red, 0 APIs externas, 0 llamadas a LLM.
- **RNF-3 (Veracidad Cuantitativa y Cobertura de Pruebas)**:
  - Cobertura de pruebas unitarias (`pytest`) al 100% en `tests/unit/test_guidelines_service.py` cubriendo todos los escenarios combinados y casos límite (mes sin ingresos, mes con ingresos normales, déficit extremo, excedente total).
