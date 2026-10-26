# Especificación: Análisis Fundamental en Profundidad — Deep Dive (Spec 003)

## 1. Contexto y Objetivo
Tras la puesta en marcha del núcleo presupuestario con salvaguarda patrimonial ([Spec 000](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/000-cimientos-safety-guard/spec.md)), el radar macroeconómico y de noticias ([Spec 001](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/001-radar-macro-noticias/spec.md)) y el screener cuantitativo de acciones y ETFs ([Spec 002](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/002-screener-oportunidades/spec.md)), el usuario requiere una herramienta de **diagnóstico contable individualizado bajo demanda (Deep Dive)** para evaluar en profundidad cualquier empresa cotizada antes de destinar capital de su tramo de ahorro e inversión ("Sin Asignar").

El objetivo de esta especificación es implementar un módulo integral de **Análisis Fundamental bajo la metodología *Quality Value*** que permita:
1. Extraer y modelar los estados contables históricos (Balance, Cuenta de Resultados y Flujo de Caja) de los últimos 3-4 años disponibles.
2. Calcular algorítmicamente el **Piotroski F-Score (0 a 9 puntos)** con desglose interactivo de sus 9 criterios (Rentabilidad, Apalancamiento/Liquidez y Eficiencia Operativa).
3. Analizar la calidad del **Flujo de Caja Libre (FCF)**, CapEx, rendimiento FCF (*FCF Yield*) y tasa de conversión de beneficio a caja real.
4. Generar una **tesis sintética de inversión agéntica con IA (Google Gemini 2.5 Pro / 3.1 Flash)** aplicando el marco *Quality Value*:
   - Clasificación en cuadrante (*Quality Value*, *Calidad Cara*, *Trampa de Valor*).
   - Evaluación de los 6 ingredientes clave (crecimiento a largo plazo, vientos de cola, liderazgo de mercado, foso defensivo, rentabilidad sobre el capital y problemas temporales).
   - Modelo de negocio y matriz de riesgos (*"¿Qué puede salir mal y cuánto beneficio destruiría?"*).
   - Proyección de valoración a 5 años (Escenario Base vs Escenario Bajo/Estrés) y cálculo de Zona de Compra exigiendo una TIR anualizada del 15% al 20%.
5. Gestionar una **Lista de Seguimiento Local (Watchlist)** persistida en SQLite para guardar valores de interés y monitorizarlos con un clic.
6. Aplicar la **Salvaguarda de Seguridad (Principio 9 de la Constitución)** con advertencia prominente si el fondo de emergencia del usuario no cubre los 3 meses mínimos de gastos esenciales.

---

## 2. Usuarios
- **Inversor Particular / Ahorrador Prudente**: Usuario particular que busca evaluar empresas con criterio contable riguroso, evitando comprar acciones mediocres a precio de ganga (*trampas de valor*) o sobrepagar por negocios de calidad (*calidad cara*), y que exige un margen de seguridad cuantificable antes de invertir.

---

## 3. Historias de Usuario
- **HU-1 (Consulta Contable por Ticker)**: Como usuario, quiero buscar una empresa por su símbolo bursátil (ticker) y visualizar su historial financiero consolidado de los últimos 3-4 años para entender la evolución de sus ingresos, deuda y márgenes.
- **HU-2 (Diagnóstico Piotroski F-Score)**: Como usuario, quiero ver la puntuación Piotroski de la empresa (0 a 9) desglosada en sus 9 reglas contables para verificar si su salud financiera está mejorando o deteriorándose.
- **HU-3 (Flujo de Caja Libre y Reinversión)**: Como usuario, quiero analizar el FCF real de la empresa (descontando el CapEx recurrente) y la tasa de conversión de beneficios a caja para detectar si los beneficios contables son reales o fruto de trucos contables.
- **HU-4 (Informe Agéntico Quality Value)**: Como usuario, quiero que un analista de IA sintetice la tesis de inversión evaluando los 6 ingredientes, el foso defensivo (*Moat*), los riesgos bajistas obligatorios y la rentabilidad esperada (TIR) en escenarios base y de estrés.
- **HU-5 (Lista de Seguimiento - Watchlist)**: Como usuario, quiero guardar empresas analizadas en mi Watchlist local en SQLite, agregando notas y precios objetivo para seguirlas sin reintroducir los tickers.
- **HU-6 (Aviso de Salvaguarda y Disclaimer Legal)**: Como usuario, quiero que la herramienta me informe con honestidad si mi fondo de emergencia no cumple con los 3 meses mínimos y me recuerde claramente que la información no constituye asesoramiento financiero regulado.
- **HU-7 (Caché Ágil de 24h y Refresco)**: Como usuario, quiero que el análisis cargue al instante (< 1s) si la empresa ya fue analizada en las últimas 24 horas, disponiendo de un botón para actualizar los datos bajo demanda.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Extracción y Modelado Contable Histórico
- **Criterio EARS (Event-driven)**: CUANDO el usuario solicita el análisis de un ticker (ej. `ITX.MC`, `AAPL`), EL SISTEMA DEBE extraer mediante `yfinance`:
  - **Identificación**: Nombre de la empresa, ticker, sector, industria, país, divisa y descripción de negocio.
  - **Cotización y Múltiplos**: Precio actual, variación diaria, capitalización bursátil, PER (*trailing* y *forward*), EV/EBITDA, P/B, Dividend Yield y Beta.
  - **Series Históricas (3-4 años)**:
    - *Cuenta de Resultados*: Ingresos totales (*Total Revenue*), Margen Bruto (*Gross Profit*), Beneficio Operativo (*Operating Income*), Beneficio Neto (*Net Income*), Beneficio por Acción (*Diluted EPS*).
    - *Balance*: Activo Total (*Total Assets*), Activo Corriente (*Current Assets*), Pasivo Corriente (*Current Liabilities*), Deuda a Largo Plazo (*Long Term Debt*), Deuda Total (*Total Debt*), Efectivo y Equivalentes (*Cash and Equivalents*), Acciones en Circulación (*Ordinary Shares Number*).
    - *Flujo de Caja*: Flujo de Caja Operativo (*Operating Cash Flow / CFO*), Gastos de Capital (*Capital Expenditure / CapEx*), Recompras de Acciones (*Repurchase of Capital Stock*), Dividendos pagados (*Cash Dividends Paid*).

### RF-2: Motor del Piotroski F-Score (0 a 9 Puntos)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE calcular algorítmicamente el Piotroski F-Score evaluando los 9 criterios binarios (1 punto por criterio cumplido, 0 si no cumple):
  - **Bloque A: Rentabilidad (4 puntos)**:
    1. $\text{ROA} > 0$ en el último ejercicio fiscal ($\text{Net Income} / \text{Total Assets} > 0$).
    2. $\text{CFO} > 0$ en el último ejercicio fiscal.
    3. $\Delta\text{ROA} > 0$ ($\text{ROA}_{\text{t}} > \text{ROA}_{\text{t-1}}$).
    4. Calidad del devengo contable: $\text{CFO}_{\text{t}} > \text{Net Income}_{\text{t}}$.
  - **Bloque B: Apalancamiento, Liquidez y Fondos (3 puntos)**:
    5. Reducción del apalancamiento: $(\text{Long Term Debt} / \text{Total Assets})_{\text{t}} \le (\text{Long Term Debt} / \text{Total Assets})_{\text{t-1}}$.
    6. Mejora del *Current Ratio*: $(\text{Current Assets} / \text{Current Liabilities})_{\text{t}} > (\text{Current Assets} / \text{Current Liabilities})_{\text{t-1}}$.
    7. Cero dilución accionarial: $\text{Shares Number}_{\text{t}} \le \text{Shares Number}_{\text{t-1}}$.
  - **Bloque C: Eficiencia Operativa (2 puntos)**:
    8. Mejora del margen bruto: $(\text{Gross Profit} / \text{Revenue})_{\text{t}} > (\text{Gross Profit} / \text{Revenue})_{\text{t-1}}$.
    9. Mejora de la rotación de activos: $(\text{Revenue} / \text{Total Assets})_{\text{t}} > (\text{Revenue} / \text{Total Assets})_{\text{t-1}}$.
- **Criterio EARS (State-driven)**: EL SISTEMA DEBE catalogar el resultado final en 3 niveles cualitativos:
  - $\text{Puntuación } 7 - 9$: **Salud Contable Excelente** (Verde).
  - $\text{Puntuación } 4 - 6$: **Salud Contable Media / Aceptable** (Ámbar).
  - $\text{Puntuación } 0 - 3$: **Riesgo Contable / Debilidad Financiera** (Rojo).

### RF-3: Análisis de Flujo de Caja Libre (FCF) y Fosos Defensivos
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE calcular y presentar:
  - Serie histórica anual de $\text{FCF} = \text{CFO} - |\text{CapEx}|$.
  - Tasa de conversión de beneficio neto a caja: $\text{FCF} / \text{Net Income}$.
  - Rentabilidad de Flujo de Caja Libre: $\text{FCF Yield} = (\text{FCF} / \text{Market Cap}) \times 100$.
  - Retorno sobre fondos propios ($\text{ROE}$) y retorno estimado sobre capital invertido ($\text{ROIC}$).
  - Diagnóstico de Foso Defensivo (*Moat*): $\text{ROE} \ge 15\%$ sostenido y margen operativo estable superior al 12%.

### RF-4: Analista Agéntico "Quality Value" (Google Gemini 2.5 Pro / 3.1 Flash)
- **Criterio EARS (Event-driven)**: CUANDO se completa la carga cuantitativa y existe una clave API de Gemini válida, EL SISTEMA DEBE enviar al modelo los datos contables reales y ejecutar el prompt metodológico estructurado en 4 secciones:
  1. **Filtro Inicial y Cuadrante**:
     - Clasificación fundamentada en: *Quality Value*, *Calidad Cara* o *Trampa de Valor*.
  2. **Evaluación de los 6 Ingredientes Clave**:
     - Crecimiento a largo plazo, vientos de cola del sector, liderazgo de mercado, foso defensivo (ventajas competitivas duraderas), alta rentabilidad sobre el capital (ROIC/ROE) y presencia de problemas temporales/descuento.
  3. **Modelo de Negocio y Matriz de Riesgos (Doble Tesis)**:
     - Cómo entra y circula el dinero (dinámica de clientes, capital circulante).
     - Competencia y riesgos: **Mínimo 2 riesgos bajistas obligatorios** respondiendo a *"¿Qué puede salir mal y cuánto beneficio destruiría?"*.
  4. **Valoración, Escenarios y Rentabilidad Exigida (TIR)**:
     - Proyección a 5 años (Escenario Base vs Escenario de Estrés).
     - Estimación de Múltiplo de Salida conservador y Precio Objetivo intrínseco.
     - Cálculo de la Tasa Interna de Retorno (TIR) proyectada al precio actual y definición de la **Zona de Entrada Ideal con Margen de Seguridad (TIR del 15% al 20%)**.
- **Criterio EARS (State-driven)**: EL SISTEMA DEBE emplear modelos de alto razonamiento financiero (`gemini-2.5-pro` o `gemini-3.1-flash`) configurables mediante `GEMINI_DEEPDIVE_MODEL` en `.env` (con fallback a `GEMINI_MODEL`), asegurando un nivel institucional en el pensamiento crítico y la modelización de riesgos.
- **Criterio EARS (Unwanted Behavior)**: SI `GEMINI_API_KEY` no está configurada o la llamada a la API falla por cuota o red, EL SISTEMA DEBE presentar el análisis cuantitativo completo (Piotroski, FCF, ratios contables) acompañado de una advertencia amigable indicando que la síntesis cualitativa de IA no está disponible temporalmente.

### RF-5: Persistencia de Lista de Seguimiento Local (Watchlist en SQLite)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE implementar la tabla `watchlist` en SQLite con los campos:
  - `ticker` (clave primaria o índice único), `name`, `sector`, `currency`, `price_at_addition`, `notes`, `created_at`.
- **Criterio EARS (Event-driven)**: CUANDO el usuario pulsa *"⭐ Añadir a Watchlist"*, EL SISTEMA DEBE persistir la compañía con su cotización actual y notas del usuario.
- **Criterio EARS (Event-driven)**: CUANDO el usuario visualiza su Watchlist en la interfaz, EL SISTEMA DEBE mostrar la lista de valores seguidos con acceso en 1 clic para cargar su diagnóstico Deep Dive de inmediato.
- **Criterio EARS (Event-driven)**: CUANDO el usuario pulsa *"Eliminar de Watchlist"*, EL SISTEMA DEBE suprimir el registro de la base de datos local.

### RF-6: Caché de Análisis Deep Dive (24 Horas)
- **Criterio EARS (State-driven)**: MIENTRAS exista una entrada en `market_cache` con clave `deepdive_{ticker}` con antigüedad inferior a 24 horas, EL SISTEMA DEBE retornar los datos instantáneamente sin llamadas externas repetitivas.
- **Criterio EARS (Event-driven)**: CUANDO el usuario presiona el botón *"🔄 Actualizar Análisis"*, EL SISTEMA DEBE invalidar la caché de dicho ticker, reconsultar las fuentes externas y regenerar el informe.

### RF-7: Salvaguarda de Seguridad y Descargo Legal
- **Criterio EARS (State-driven)**: MIENTRAS el fondo de emergencia del usuario cubra menos de 3 meses de gastos esenciales según sus datos contables locales, EL SISTEMA DEBE mostrar en la cabecera del Deep Dive el banner de aviso de la Salvaguarda de Seguridad (Principio 9 de la Constitución).
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE incluir al pie del análisis un descargo legal explícito indicando que los cálculos y la síntesis tienen carácter formativo e informativo y no constituyen asesoramiento financiero regulado.

---

## 5. Requisitos No Funcionales (RNF)
- **RNF-1 (Cero Alucinación de Magnitudes Contables)**: Las cifras de ingresos, balance, flujos de caja y múltiplos entregadas a la IA deben proceder obligatoriamente de la extracción matemática local de Python.
- **RNF-2 (Privacidad Local y Protección de Datos)**: En ningún caso se envían saldos, transacciones ni datos personales del usuario a Yahoo Finance ni a Google Gemini.
- **RNF-3 (Resiliencia ante Entidades Financieras y Bancos)**: Para bancos y aseguradoras, el sistema debe adaptar el cálculo del Piotroski omitiendo el margen bruto y el ratio corriente sin provocar fallos de ejecución.
- **RNF-4 (Observabilidad y Prohibición de Fallos Silenciosos)**: Todo fallo de red o parseo contable debe registrarse con `logger.warning` o `logger.error`. Queda estrictamente prohibido el uso de `pass`.

---

## 6. Casos Límite
1. **Ticker inexistente o deslistado**: El sistema debe emitir un mensaje de aviso claro recomendando verificar el símbolo y sufijo de mercado (ej. `.MC`, `.DE`, `.PA`).
2. **Empresas jóvenes con menos de 3 años de cotización**: Si no existen datos contables para los 9 criterios de Piotroski, el sistema debe indicar los puntos evaluables disponibles (ej. 4/5) sin quebrar el cálculo.
3. **Flujo de caja libre negativo recurrente**: El sistema debe reflejar la tasa de quema de caja (*Cash Burn Rate*) y advertir sobre la necesidad potencial de financiación externa.

---

## 7. Criterios de Finalización (Definition of Done)
1. **Motor Contable Validado**: Extracción correcta de balance, cuenta de resultados y cash flow a 3-4 años con tipado Pydantic estricto en inglés.
2. **Piotroski Score al 100%**: Cálculo algorítmico probado con tests unitarios para los 9 criterios discretos y semáforo visual.
3. **Métricas FCF Operativas**: FCF histórico, tasa de conversión y FCF Yield calculados con precisión.
4. **Informe Quality Value Activo**: Prompt agéntico estructurado en los 4 bloques ejecutado con Gemini Pro y degradación elegante si no hay clave API.
5. **Watchlist en SQLite Funcional**: CRUD completo de lista de seguimiento en base de datos local y gestión interactiva desde la interfaz.
6. **Endpoints REST y Caché 24h**: Rutas `/deepdive/*` y `/watchlist/*` operativas con tests de integración.
7. **Pestaña en Streamlit Integrada**: Nueva pestaña `"🔬 Análisis Fundamental (Deep Dive)"` fluida, con aviso de Salvaguarda de Seguridad y descarga del informe en Markdown/PDF o exportación CSV.
8. **Cobertura de Pruebas**: 100% de tests pasando en `pytest` y cero regresiones.
