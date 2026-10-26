# Especificación: Screener Fundamental de Acciones y ETFs (Spec 002)

## 1. Contexto y Objetivo
Tras la consolidación del núcleo presupuestario 50/30/20 con salvaguarda patrimonial ([Spec 000](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/000-cimientos-safety-guard/spec.md)) y del radar macroeconómico y de noticias ([Spec 001](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/001-radar-macro-noticias/spec.md)), el inversor particular necesita una herramienta cuantitativa para **identificar, filtrar y comparar oportunidades de inversión en renta variable y fondos indexados (ETFs)**.

El objetivo de esta especificación es implementar un **Screener Fundamental y de Oportunidades** que permita:
1. Analizar universos modulares bajo demanda relevantes para un residente en España (IBEX 35, EuroStoxx 50, Top 50 de EE.UU., ETFs de referencia accesibles en Europa y tickers personalizados).
2. Extraer y estructurar ratios contables clave (valoración, rentabilidad, solvencia, dividendos y gastos de gestión en ETFs).
3. Aplicar filtros interactivos con rangos personalizables y estrategias predefinidas (*Value*, *Calidad*, *Alto Dividendo*, *Crecimiento*).
4. Garantizar una experiencia de usuario rápida y eficiente mediante la caché persistente de 24 horas en SQLite (`MarketCache`), evitando bloqueos por tasa de llamadas en Yahoo Finance.
5. Respetar la **Salvaguarda de Seguridad (Principio 9 de la Constitución)** mediante un aviso preventivo visible si el fondo de emergencia del usuario no cubre los 3 meses mínimos de gastos esenciales.

---

## 2. Usuarios
- **Inversor Particular en España**: Usuario que desea evaluar activos con rigor fundamental antes de comprometer su ahorro ("Sin Asignar"), buscando empresas solventes y ETFs indexados de bajo coste con datos limpios y sin sobrecostes de APIs financieras.

---

## 3. Historias de Usuario
- **HU-1 (Selección Modular de Universos)**: Como usuario, quiero seleccionar el universo de activos a inspeccionar (IBEX 35, EuroStoxx 50, Top 50 EE.UU., ETFs de Referencia o Tickers Propios) para no saturar la conexión ni esperar descargas innecesarias.
- **HU-2 (Filtrado por Ratios Contables y de Solvencia)**: Como usuario, quiero filtrar las empresas por múltiplos de valoración (PER, EV/EBITDA, P/B), solvencia (Deuda Neta/EBITDA, Deuda/Patrimonio) y rentabilidad (Dividend Yield, ROE, márgenes) para encontrar compañías financieramente sólidas.
- **HU-3 (Estrategias Rápidas o Presets)**: Como usuario, quiero aplicar con un solo clic estrategias predefinidas (*Calidad y Solvencia*, *Alto Dividendo*, *Valoración Atractiva*, *Crecimiento*) para acelerar el cribado de valores.
- **HU-4 (Screener Especializado de ETFs)**: Como usuario, quiero consultar los principales ETFs indexados negociables en Europa analizando su Ratio de Gastos Totales (TER), política de dividendos (acumulación/distribución) y volumen.
- **HU-5 (Caché Ágil y Refresco Forzado)**: Como usuario, quiero que la tabla cargue en menos de 1 segundo si los datos se descargaron en las últimas 24 horas, disponiendo de un botón para forzar la actualización cuando lo desee.
- **HU-6 (Aviso de Salvaguarda Patrimonial)**: Como usuario, quiero que la interfaz me recuerde claramente si mi fondo de emergencia no cubre los 3 meses mínimos, señalando que la asignación a activos de riesgo está bloqueada por la Constitución.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Universos Modulares de Activos
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE soportar los siguientes universos predefinidos, descargados y cacheados de manera independiente:
  1. `ibex35`: Los 35 valores del índice selectivo español (`ITX.MC`, `SAN.MC`, `IBE.MC`, `BBVA.MC`, `TEF.MC`, etc.).
  2. `eurostoxx50`: Las 50 mayores empresas de la Eurozona (`ASML.AS`, `MC.PA`, `SAP.DE`, `TTE.PA`, `SIE.DE`, etc.).
  3. `sp500_top50`: Las 50 mayores empresas de EE.UU. por capitalización bursátil (`AAPL`, `MSFT`, `NVDA`, `AMZN`, `GOOGL`, `META`, `BRK-B`, etc.).
  4. `etfs_referencia`: Cesta de 15-20 ETFs UCITS de referencia negociables en Europa (ej. `VWCE.DE`, `CSPX.AS`, `IWDA.AS`, `EUNL.DE`, `MEUD.PA`, `VAGF.DE`).
  5. `custom`: Lista de tickers personalizada introducida por el usuario separada por comas (ej. `REP.MC, BMW.DE, TSLA`).

### RF-2: Extracción y Modelado de Ratios Financieros
- **Criterio EARS (Ubiquitous)**: Para empresas de renta variable, EL SISTEMA DEBE extraer y normalizar:
  - **Identificación**: Ticker, nombre de la compañía, sector económico, país, divisa.
  - **Cotización y Mercado**: Precio actual, variación diaria (%), capitalización bursátil (*Market Cap*), Beta.
  - **Valoración**: PER (*Trailing P/E*), PER Adelantado (*Forward P/E*), Ratio Precio/Valor en Libros (*P/B*), EV/EBITDA.
  - **Rentabilidad y Retorno**: Rentabilidad por Dividendo (*Dividend Yield* %), ROE (*Return on Equity* %), Margen Operativo (%), Margen Neto (%).
  - **Solvencia**: Ratio Deuda Total/Patrimonio (*Total Debt/Equity* %), Deuda Neta/EBITDA (si está disponible), *Current Ratio*.
- **Criterio EARS (Ubiquitous)**: Para ETFs, EL SISTEMA DEBE extraer y normalizar:
  - Ticker, nombre, índice de referencia, divisa, precio actual, variación diaria (%).
  - Ratio de Gastos Totales (*TER* / *Expense Ratio* %), Rentabilidad por Dividendo (%), Patrimonio gestionado (*Total Assets / AUM*) y volumen promedio.

### RF-3: Motor de Filtrado y Estrategias Predefinidas (Presets)
- **Criterio EARS (Event-driven)**: CUANDO el usuario define rangos numéricos en los filtros (ej. PER máximo = 15, Dividend Yield mínimo = 3.5%), EL SISTEMA DEBE filtrar en memoria el universo activo retornando las filas coincidentes.
- **Criterio EARS (Event-driven)**: CUANDO el usuario selecciona una estrategia predefinida (*Preset*), EL SISTEMA DEBE aplicar los siguientes umbrales:
  - **💎 Calidad y Solvencia**: $\text{ROE} \ge 15\%$, $\text{Margen Neto} \ge 10\%$, $\text{Debt/Equity} \le 120\%$.
  - **💰 Alto Dividendo**: $\text{Dividend Yield} \ge 3.5\%$, $\text{Forward PER} \le 18$, $\text{Debt/Equity} \le 150\%$.
  - **🏷️ Valoración Atractiva (Value)**: $\text{Trailing PER} \le 15$, $\text{Price/Book} \le 2.0$, $\text{Dividend Yield} \ge 2.0\%$.
  - **🚀 Crecimiento y Rentabilidad**: $\text{Margen Operativo} \ge 15\%$, $\text{ROE} \ge 12\%$, $\text{Beta} \ge 0.9$.
  - **🛡️ ETFs de Bajo Coste**: $\text{TER} \le 0.25\%$, $\text{AUM} \ge 500\text{M €}$.

### RF-4: Caché Persistente de 24 Horas en SQLite
- **Criterio EARS (State-driven)**: MIENTRAS la información del universo solicitado resida en la tabla `market_cache` con antigüedad menor a 24 horas, EL SISTEMA DEBE servir los datos instantáneamente sin invocar las APIs externas.
- **Criterio EARS (Event-driven)**: CUANDO el usuario presiona el botón "Actualizar Universo", EL SISTEMA DEBE invalidar la clave específica (`screener_{universo}`), consultar nuevamente `yfinance`, recomputar los ratios y persistir la nueva instantánea.

### RF-5: Interfaz de Usuario y Presentación Tabular
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE presentar una nueva pestaña `"🔍 Screener y Oportunidades"` en Streamlit conteniendo:
  1. Selector de Universo y botón de refresco forzado con marca temporal de la caché.
  2. Bloque de filtros (desplegables de presets rápidos + sliders de métricas clave + búsqueda por texto).
  3. Banner preventivo de la Salvaguarda de Seguridad (Safety Guard) según el estado del fondo de emergencia.
  4. Tabla interactiva ordenable por cualquier ratio con formato numérico localizado (€, $, %, múltiplos con 2 decimales).
  5. Botón de exportación de los resultados filtrados a CSV.

### RF-6: Resiliencia y Manejo de Ratios Nulos
- **Criterio EARS (Unwanted Behavior)**: SI una métrica contable no está disponible en Yahoo Finance para una empresa concreta (ej. empresas de reciente salida a bolsa sin PER o sector bancario sin EBITDA tradicional), EL SISTEMA DEBE manejar el valor como `None` / `N/D` sin quebrar el cálculo del screener ni el renderizado de la tabla.

---

## 5. Requisitos No Funcionales (RNF)
- **RNF-1 (Cero Consumo de Tokens de IA)**: El procesamiento del Screener es 100% numérico y se ejecuta en backend local; no utiliza llamadas a Google Gemini ni consume cuota de tokens.
- **RNF-2 (Tiempo de Respuesta en Caché)**: La visualización y filtrado de la tabla para cualquier universo en caché debe resolverse en **menos de 1 segundo**.
- **RNF-3 (Protección contra Rate-Limit)**: Las descargas externas se organizan en lotes pequeños (máximo 50 tickers por llamada de universo) con caché individual para evitar bloqueos por parte de Yahoo Finance.
- **RNF-4 (Privacidad Local)**: En ningún momento se asocian los tickers del screener con las transacciones o el saldo real del usuario.

---

## 6. Casos Límite
1. **Ticker personalizado inválido o inexistente**: Si el usuario introduce un ticker erróneo (ej. `XYZ123`), el sistema debe ignorarlo o marcarlo como no disponible sin interrumpir la extracción del resto de tickers.
2. **Entidades bancarias y financieras**: Los bancos y aseguradoras no presentan métricas de EBITDA ni deuda neta tradicional. El screener debe mostrar `N/D` en dichas columnas y permitir filtrar por PER, P/B y ROE.
3. **Fondo de emergencia incompleto**: Si el usuario no cubre los 3 meses de gastos fijos esenciales, la tabla y los filtros permanecen 100% interactivos y educativos, pero encabezados por una advertencia de la Salvaguarda de Seguridad recordando el Principio 9 de la Constitución.

---

## 7. Fuera de Alcance (Out of Scope)
- Análisis contable cualitativo profundo de balances históricos y cálculo del Piotroski F-Score (corresponde a la **Spec 003: Deep Dive**).
- Envío automático de órdenes de compra/venta a brokers (Degiro, Interactive Brokers, MyInvestor, etc.).
- Gráficos intradía con latencia tick-a-tick.

---

## 8. Criterios de Finalización (Definition of Done)
1. **Universos Verificados**: Los 4 universos predefinidos (IBEX 35, EuroStoxx 50, Top 50 EE.UU. y ETFs de Referencia) y el modo personalizado se extraen y formatean correctamente.
2. **Ratios Contables Validados**: PER, Forward PER, P/B, EV/EBITDA, Dividend Yield, ROE, márgenes y deuda/patrimonio se calculan con tipado Pydantic estricto.
3. **Presets y Filtros Interactivos**: Los 4 presets rápidos y los filtros manuales filtran con precisión la tabla en Streamlit.
4. **Caché SQLite Operativa**: Los universos persisten 24 horas en SQLite y el botón de actualización manual renueva los datos bajo demanda.
5. **Observabilidad y Tests**: 100% de cobertura de pruebas unitarias e integración pasando con `pytest` y logging descriptivo sin `pass` silenciosos.
