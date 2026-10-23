# [ARCHIVADO] Especificación: Radar de Mercado y Análisis Fundamental de Empresas

> **Nota de Archivo (2026-10-23)**: Este borrador ha sido archivado tras el diseño del mapa global de descomposición arquitectónica.
> Su alcance será reescrito de forma ampliada (incluyendo Piotroski Score, Flujo de Caja Libre, Moat y Gestión de Riesgos) en **`specs/003-analisis-fundamental/`** una vez completados los cimientos de la **Spec 000** y el motor de filtrado de la **Spec 002**.

---

## 1. Contexto y Objetivo
El gestor de finanzas personales actualmente permite planificar y registrar ingresos y gastos bajo la metodología 50/30/20, ayudando al usuario a consolidar su ahorro mensual. No obstante, para los usuarios que logran cumplir sus metas de ahorro y cuentan con una posición de estabilidad financiera, surge la necesidad de evaluar oportunidades de inversión informadas en empresas cotizadas.

El objetivo de esta funcionalidad es proporcionar un **Radar de Mercado y Análisis Fundamental** que permita consultar de manera autónoma, estructurada y comprensible los datos económico-financieros de empresas cotizadas, evaluando su salud financiera, múltiplos de valoración y rentabilidad histórica. Asimismo, busca salvaguardar la prudencia patrimonial del usuario mediante la integración de la regla constitucional del Fondo de Seguridad, impidiendo recomendaciones de asignación a activos de riesgo si no existe una reserva de emergencia previa suficiente.

---

## 2. Usuarios
- **Ahorrador / Inversor Prudente**: Usuario particular con conocimientos financieros básicos o intermedios que busca evaluar si una empresa concreta posee solidez fundamental y un precio razonable antes de destinar capital de su tramo de ahorro e inversión.

---

## 3. Historias de Usuario
- **HU-1**: Como usuario interesado en una empresa, quiero buscarla por su símbolo bursátil (ticker) para consultar un desglose completo de sus principales métricas fundamentales y comprender su situación financiera.
- **HU-2**: Como usuario, quiero guardar empresas analizadas en una lista de seguimiento local (Watchlist) para monitorizar su evolución a lo largo del tiempo sin tener que reintroducir su ticker manualmente.
- **HU-3**: Como usuario que busca preservar su seguridad financiera, quiero saber con claridad si mi fondo de emergencia cumple con los requisitos mínimos de cobertura antes de considerar destinar excedentes a renta variable.
- **HU-4**: Como usuario, quiero que el sistema me ofrezca un diagnóstico sintético y objetivo basado en datos cuantitativos (solvencia, rentabilidad, valoración) para identificar fortalezas y riesgos de la empresa rápidamente sin saturarme de información técnica dispersa.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Búsqueda y Extracción de Datos por Ticker
- **Criterio EARS (Event-driven)**: CUANDO el usuario introduce un símbolo bursátil (ticker) válido y solicita su consulta, EL SISTEMA DEBE recuperar los datos de cotización y magnitudes fundamentales correspondientes a la empresa.
- **Criterio EARS (Unwanted Behavior)**: SI el símbolo introducido no corresponde a ninguna entidad cotizada conocida, ENTONCES EL SISTEMA DEBE informar al usuario de que el ticker no ha sido encontrado, sugiriendo revisar el código bursátil o el mercado de cotización.

### RF-2: Cuadro Integral de Métricas Fundamentales
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE estructurar la visualización de la empresa analizada en cuatro dimensiones fundamentales:
  1. **Magnitudes de Mercado y Tamaño**: Precio actual, capitalización bursátil y volumen medio.
  2. **Múltiplos de Valoración**: Relación Precio-Beneficio (PER), Ratio Valor Empresa / EBITDA (EV/EBITDA) y Precio sobre Valor Contable (P/B).
  3. **Salud Financiera y Endeudamiento**: Deuda Neta sobre EBITDA y Ratio de Liquidez (Current Ratio).
  4. **Rentabilidad y Retorno al Accionista**: Rentabilidad sobre Fondos Propios (ROE), Márgenes Operativo y Neto, y Rentabilidad por Dividendo (Dividend Yield).
- **Criterio EARS (Unwanted Behavior)**: SI una métrica no es aplicable a la naturaleza de la entidad (por ejemplo, EV/EBITDA o Deuda Neta en entidades bancarias o financieras) o no se puede calcular matemáticamente (por ejemplo, PER cuando existen pérdidas netas), ENTONCES EL SISTEMA DEBE mostrar la indicación "No Aplicable" (N/A) o "Pérdidas Netas" acompañada de una breve nota contextual explicativa.

### RF-3: Diagnóstico Cuantitativo y Resumen de Estado
- **Criterio EARS (Event-driven)**: CUANDO se completa la carga de las métricas de una empresa, EL SISTEMA DEBE emitir un resumen sintético objetivo que contraste los valores obtenidos frente a referencias cuantitativas estándar de valoración y solvencia (ej. nivel de endeudamiento moderado/alto, márgenes saludables o compresión de múltiplos).
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE basar cualquier conclusión diagnóstica exclusivamente en magnitudes empíricas demostrables, absteniéndose de emitir juicios arbitrarios sin soporte cuantitativo.

### RF-4: Salvaguarda del Fondo de Seguridad (Safety Guard)
- **Criterio EARS (State-driven)**: MIENTRAS el fondo de seguridad del usuario cubra menos de 3 meses de gastos fijos esenciales según sus datos contables, EL SISTEMA DEBE:
  1. Mostrar una advertencia prominente informando que la capacidad financiera actual no cumple con el colchón mínimo de seguridad.
  2. Bloquear y deshabilitar cualquier recomendación activa de compra, sugerencia de asignación patrimonial o vinculación con el ahorro mensual hacia dicho activo de riesgo.
- **Criterio EARS (State-driven)**: MIENTRAS el fondo de seguridad cubra igual o más de 3 meses de gastos fijos esenciales, EL SISTEMA DEBE mostrar el indicador de fondo cubierto y permitir la evaluación de capacidad de inversión del tramo de ahorro.

### RF-5: Gestión de Lista de Seguimiento Local (Watchlist)
- **Criterio EARS (Event-driven)**: CUANDO el usuario solicita añadir una empresa consultada a su lista de seguimiento, EL SISTEMA DEBE registrar dicho ticker localmente para permitir su acceso rápido en futuras sesiones.
- **Criterio EARS (Event-driven)**: CUANDO el usuario visualiza su lista de seguimiento, EL SISTEMA DEBE mostrar el resumen actualizado de cotización y múltiplos clave de cada entidad guardada.
- **Criterio EARS (Event-driven)**: CUANDO el usuario solicita eliminar una empresa de su lista de seguimiento, EL SISTEMA DEBE retirarla de la lista de forma inmediata.

### RF-6: Resiliencia ante Fallos de Proveedor y Caché Local
- **Criterio EARS (Unwanted Behavior)**: SI la conexión con el proveedor externo de datos financieros no responde, presenta latencia excesiva o supera las cuotas de peticiones, ENTONCES EL SISTEMA DEBE presentar un mensaje de indisponibilidad temporal sin comprometer la estabilidad de la aplicación ni la integridad de los datos locales existentes.
- **Criterio EARS (State-driven)**: MIENTRAS existan datos recuperados recientemente para un ticker, EL SISTEMA DEBE permitir reutilizar la última instantánea válida para optimizar el tiempo de respuesta y evitar peticiones externas redundantes.

---

## 5. Requisitos No Funcionales (RNF)
- **RNF-1 (Privacidad Local)**: Ningún dato personal contable, transaccional o financiero del usuario se enviará a proveedores de datos externos durante las consultas de mercado. Únicamente se transmitirán los símbolos bursátiles solicitados.
- **RNF-2 (Rendimiento y Tiempos de Respuesta)**: La consulta de datos y presentación del cuadro fundamental no debe superar los 3 segundos en condiciones normales de conectividad.
- **RNF-3 (Usabilidad y Claridad)**: Las métricas deben expresarse con etiquetas normalizadas en español, indicando claramente las unidades (porcentaje, ratio o moneda) y tooltips explicativos breves.

---

## 6. Casos Límite
1. **Empresas con Pérdidas Netas Continuadas**: El cálculo del PER resulta negativo o indefinido. El sistema debe categorizarlo como beneficio negativo sin generar errores de cálculo.
2. **Entidades Financieras, Bancos y Aseguradoras**: Su balance no responde a la estructura clásica de Deuda Neta / EBITDA. El sistema debe evitar ratios inválidos e indicar "Estructura Financiera Especial".
3. **Pérdida de Conexión a Internet**: El usuario realiza una consulta estando sin red. El sistema debe reportar el estado fuera de línea de forma amigable.
4. **Tickers Duplicados en Distintas Bolsas**: Tickers idénticos en diferentes mercados (ej. ticker cotizado en EE.UU. vs. mercado europeo). El usuario debe poder especificar el sufijo de mercado o recibir orientación al respecto.
5. **Usuario sin Historial de Gastos**: Si el usuario no ha registrado gastos fijos en la aplicación, el fondo de seguridad no puede ser calculado con certeza; el sistema debe asumir por defecto que el fondo de seguridad no está verificado y mantener la salvaguarda activa.

---

## 7. Fuera de Alcance (Out of Scope)
- Integración con brokers o plataformas de inversión para la compra/venta real de acciones.
- Gestión y seguimiento de carteras reales o simuladas (paper trading, registro de transacciones de compra/venta de títulos y cálculo de plusvalías/minusvalías).
- Alertas automatizadas por correo electrónico, SMS o notificaciones push ante variaciones de precio.
- Análisis técnico complejo (osciladores intradía tipo RSI, MACD, bandas de Bollinger o velas en tiempo real).
- Datos en tiempo real tick a tick con latencia milimétrica (las cotizaciones de cierre o con cortesía habitual de 15 minutos son suficientes para el propósito de análisis fundamental).

---

## 8. Criterios de Finalización (Definition of Done)
- Un usuario puede buscar cualquier ticker estándar y visualizar sus 4 dimensiones de métricas fundamentales sin bloqueos ni errores.
- La regla del Fondo de Seguridad se evalúa dinámicamente y bloquea cualquier sugerencia de asignación si la reserva no alcanza los 3 meses de gastos fijos.
- Se gestiona correctamente el guardado, consulta y borrado de empresas en la lista de seguimiento local.
- Las empresas en pérdidas o entidades financieras muestran estados coherentes sin provocar anomalías en la presentación de métricas.
- La experiencia se mantiene consistente con los 7 principios de la Constitución del proyecto.

---

## 9. Dudas Abiertas
- [NECESITA ACLARACIÓN]: Definir en la fase técnica/plan si el umbral de refresco de la información en caché será configurable por el usuario o establecido en un estándar fijo (ej. 24 horas).
