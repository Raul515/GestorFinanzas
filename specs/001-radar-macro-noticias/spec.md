# Especificación: Radar Macroeconómico y Noticias Financieras

## 1. Contexto y Objetivo
El Gestor de Finanzas Personales cuenta actualmente con una arquitectura 50/30/20 verificada mediante pruebas y una salvaguarda patrimonial activa (Safety Guard). Una vez asegurada la disciplina de ahorro y la reserva para imprevistos, el usuario requiere comprender el entorno económico global y, muy especialmente, el **contexto nacional de España y la Eurozona** antes de tomar decisiones de inversión o asignación de capital.

El objetivo de esta funcionalidad es proporcionar un **Radar Macroeconómico y de Noticias** adaptado a un usuario residente en España que ofrezca:
1. Una panorámica ejecutiva del estado de los mercados con foco prioritario en España y Europa (IBEX 35, EuroStoxx 50, Bono Español a 10 años, Prima de Riesgo y política de tipos del BCE / Euríbor), complementada con las referencias mundiales rectoras (S&P 500, Nasdaq 100, Bono US 10Y).
2. Un canal de noticias financieras depurado mediante inteligencia artificial (Gemini Pro), que priorice la actualidad económica de España y comunitaria, elimine el sensacionalismo y los titulares engañosos (*clickbait*), y traduzca el impacto real de cada evento sobre las finanzas personales (ej. variaciones de Euríbor, inflación nacional, decisiones del Banco de España y el BCE).
3. Una experiencia ágil y económica mediante una política de caché persistente de 24 horas y degradación elegante ante caídas de proveedores externos.

---

## 2. Usuarios
- **Ahorrador / Inversor Particular en España**: Usuario residente en España que busca conocer el pulso de la economía nacional e internacional de forma clara, objetiva y sin alarmismos, evaluando cómo las políticas del BCE, la inflación local o los mercados afectan a su patrimonio.

---

## 3. Historias de Usuario
- **HU-1 (Monitorización Macroeconómica con Foco en España y Europa)**: Como usuario en España, quiero ver en un vistazo el precio actual, variación diaria y tendencia a 30 días del IBEX 35, EuroStoxx 50, el Bono Español a 10 años y la Prima de Riesgo, junto a los índices rectores de EE.UU. (S&P 500, Nasdaq 100).
- **HU-2 (Noticias Nacionales e Internacionales Depuradas por IA)**: Como usuario, quiero leer resúmenes objetivos de 1 o 2 frases redactados por IA sobre la actualidad económica (haciendo énfasis en noticias de España, BCE e impacto en Euríbor/IPC), libres de titulares alarmistas o tendenciosos.
- **HU-3 (Filtrado por Impacto y Temática Contextual)**: Como usuario, quiero poder filtrar las noticias por su nivel de relevancia (Bajo, Medio, Alto) y por temática adaptada a mi entorno (Política Monetaria BCE/Euríbor, Macroeconomía España/Eurozona, Resultados Empresariales, Geopolítica Global).
- **HU-4 (Control de Refresco y Ahorro de Recursos)**: Como usuario, quiero disponer de un botón manual para forzar la actualización de noticias cuando lo desee, sabiendo que mientras no lo pulse los datos se mantendrán almacenados durante 24 horas para no realizar llamadas innecesarias a servicios externos.
- **HU-5 (Resiliencia ante Fallos de Conexión)**: Como usuario, quiero que si falla la conexión a internet o los servidores de noticias, la aplicación siga funcionando mostrando la última captura guardada con una indicación clara de su antigüedad.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Monitor Macroeconómico de Índices, Bonos y Prima de Riesgo
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE presentar un cuadro de mando macroeconómico con los siguientes activos de referencia, organizados con prioridad en España y la Eurozona:
  - **Renta Variable**:
    - **IBEX 35** (`^IBEX`): Índice de referencia del mercado bursátil español.
    - **EuroStoxx 50** (`^STOXX50E`): Índice de las mayores empresas de la Eurozona.
    - **S&P 500** (`^GSPC`): Principal referencia de renta variable estadounidense.
    - **Nasdaq 100** (`^NDX`): Referencia del sector tecnológico global.
  - **Renta Fija Soberana y Diferencial de Deuda**:
    - **Bono Español a 10 Años**: Rendimiento de las Obligaciones del Estado español a 10 años.
    - **Bono Alemán (Bund) a 10 Años**: Rendimiento del activo libre de riesgo de la Eurozona.
    - **Prima de Riesgo de España**: Diferencial en puntos básicos entre el rendimiento del Bono Español 10Y y el Bund Alemán 10Y (`(Rendimiento_España - Rendimiento_Alemania) * 100`).
    - **Bono de EE.UU. a 10 Años**: Referencia de tipos libres de riesgo global.
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE mostrar para cada activo:
  1. Valor o rendimiento actual (en puntos o porcentaje anualizado).
  2. Variación absoluta y porcentual de la última sesión hábil.
  3. Mini-gráfico de tendencia (*sparkline*) que represente la evolución del activo durante los últimos 30 días.

### RF-2: Captura y Agregación de Noticias Financieras con Enfoque Nacional
- **Criterio EARS (Event-driven)**: CUANDO se solicita la carga del Radar y no existan datos en caché vigentes, EL SISTEMA DEBE recuperar las noticias económicas y bursátiles más recientes (entre 10 y 15 elementos), priorizando canales financieros con cobertura de España, el Banco Central Europeo y la economía europea e internacional.
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE almacenar para cada noticia: titular original, enlace web directo a la fuente, fecha/hora de publicación y fuente emisora.

### RF-3: Depuración y Análisis de Noticias con Inteligencia Artificial (Perspectiva España)
- **Criterio EARS (Event-driven)**: CUANDO se procesa una noticia recuperada, EL SISTEMA DEBE someterla a evaluación mediante el modelo de lenguaje de Google (Gemini Pro) adoptando la perspectiva de un ahorrador/inversor en España para obtener:
  1. **Nivel de Impacto**: Clasificación estricta en una de tres categorías: *Alto*, *Medio* o *Bajo* (ponderando especialmente eventos que afecten a tipos de interés del BCE, inflación en España, mercado laboral o empresas nacionales).
  2. **Temática Contextual**: Asignación a una categoría predefinida:
     - *Política Monetaria BCE / Tipos e Hipotecas (Euríbor)*
     - *Macroeconomía España y Eurozona (IPC, Empleo, PIB, Fiscalidad)*
     - *Resultados Empresariales (IBEX 35 e Internacionales)*
     - *Geopolítica y Mercados Globales*
  3. **Síntesis Neutral**: Resumen factual y conciso de 1 a 2 frases redactado en español neutro, omitiendo titulares sensacionalistas, especulaciones o llamadas a la urgencia, explicitando de forma sobria qué significa la noticia para el entorno económico español.

### RF-4: Gestión de Caché Persistente de 24 Horas
- **Criterio EARS (State-driven)**: MIENTRAS la información macroeconómica y las noticias almacenadas en caché local tengan una antigüedad inferior a 24 horas, EL SISTEMA DEBE servir los datos desde la caché local sin invocar APIs externas de mercado ni de inteligencia artificial.
- **Criterio EARS (Event-driven)**: CUANDO el usuario presiona el botón de actualización manual ("Actualizar Radar"), EL SISTEMA DEBE descartar la caché existente, consultar las fuentes externas, solicitar el análisis a la IA y refrescar la visualización con una nueva marca temporal.

### RF-5: Filtrado Interactivo en la Interfaz
- **Criterio EARS (Event-driven)**: CUANDO el usuario selecciona uno o varios filtros de nivel de impacto (ej. solo *Alto* y *Medio*), EL SISTEMA DEBE actualizar instantáneamente el listado visual mostrando únicamente las noticias coincidentes.
- **Criterio EARS (Event-driven)**: CUANDO el usuario selecciona una temática específica (ej. *Política Monetaria BCE / Tipos*), EL SISTEMA DEBE restringir la vista a los acontecimientos asociados a dicha temática.

### RF-6: Resiliencia y Degradación Elegante
- **Criterio EARS (Unwanted Behavior)**: SI se produce un fallo de red o el proveedor de datos de mercado no responde, ENTONCES EL SISTEMA DEBE mostrar la última información válida disponible en la caché local acompañada de una advertencia visible que detalle la fecha y hora de la instantánea.
- **Criterio EARS (Unwanted Behavior)**: SI la clave de API de Gemini no está configurada o se superan las cuotas de procesamiento del modelo, ENTONCES EL SISTEMA DEBE presentar las noticias en su formato original (titular y enlace directo a la fuente) indicando un aviso de que el análisis de IA no está disponible temporalmente, sin interrumpir el funcionamiento del gestor.

---

## 5. Requisitos No Funcionales (RNF)
- **RNF-1 (Privacidad de Datos)**: En ningún momento se enviará información contable, transaccional, presupuestaria ni personal del usuario a las APIs externas de noticias o de Gemini. Solo se procesarán titulares públicos de mercado.
- **RNF-2 (Tiempo de Respuesta y Eficiencia)**: La carga de la vista del Radar cuando los datos residen en caché debe completarse en menos de 1 segundo.
- **RNF-3 (Economía de Consumo)**: El consumo de tokens de Gemini debe estar acotado procesando únicamente el titular y entradilla de las 10-15 noticias seleccionadas por cada ciclo de 24 horas o refresco explícito.
- **RNF-4 (Claridad y Usabilidad)**: Los estados de impacto deben utilizar una codificación cromática homogénea (rojo para impacto alto, ámbar para medio, azul/gris para bajo), manteniendo la coherencia de estilos de la aplicación.

---

## 6. Casos Límite
1. **Mercados Cerrados o Fines de Semana**: Los precios de los índices y bonos no varían durante sábados, domingos o festivos bursátiles. El sistema debe reflejar la última cotización oficial de cierre sin reportar errores ni variaciones inexistentes.
2. **Caché Totalmente Vacía sin Conexión Inicial**: Si un usuario abre por primera vez esta vista sin acceso a internet, no existen datos previos en caché. El sistema debe presentar un mensaje descriptivo indicando que se requiere conexión para la sincronización inicial.
3. **Titular en Idioma Extranjero**: Si la fuente de noticias suministra titulares en inglés, la síntesis neutral generada por Gemini debe redactarse íntegramente en español.
4. **Noticia Duplicada entre Múltiples Fuentes**: Si dos canales informan sobre el mismo hecho con ligeras variaciones de titular, el sistema debe priorizar una sola entrada o mostrar ambas sin bloquear el procesamiento.

---

## 7. Fuera de Alcance (Out of Scope)
- Alertas en tiempo real vía notificaciones push, correo electrónico o mensajería (Telegram/WhatsApp).
- Cotizaciones tick a tick en tiempo real intradía con latencia de milisegundos (la frecuencia estándar de cortesía o cierre es suficiente para contexto macro).
- Ejecución automática de operaciones bursátiles o compra/venta de activos.
- Análisis contable exhaustivo de empresas individuales (corresponde a la Spec 003).

---

## 8. Criterios de Finalización (Definition of Done)
1. **Visualización de Mercado Operativa**: Los activos macroeconómicos con foco en España (IBEX 35, EuroStoxx 50, Bono Español a 10 años, Bund Alemán y Prima de Riesgo de España, junto a S&P 500, Nasdaq 100 y Bono US 10Y) se visualizan con su valor actual, variación porcentual y mini-gráfico de 30 días.
2. **Feed Inteligente en Funcionamiento**: Entre 10 y 15 noticias son analizadas por Gemini Pro, mostrando nivel de impacto, categoría contextual y resumen neutral de 1-2 frases en español enfocado en el impacto sobre la economía y el ahorrador en España.
3. **Caché y Refresco Verificados**: Los datos persisten 24 horas sin llamadas externas redundantes y el botón de refresco manual regenera la información bajo demanda.
4. **Filtros Interactivos Probados**: El usuario puede filtrar dinámicamente por nivel de impacto y categoría temática.
5. **Degradación Elegante Comprobada**: El sistema se comporta de forma estable ante ausencia de conexión o cuota agotada de Gemini, mostrando avisos contextuales claros.
6. **Cumplimiento Constitucional**: Respeto riguroso de la privacidad local (Principio 6) y ausencia de recomendaciones de riesgo (Principio 5).

---

## 9. Dudas Abiertas
- *Ninguna identificada tras la resolución de las 5 preguntas de alcance*.
