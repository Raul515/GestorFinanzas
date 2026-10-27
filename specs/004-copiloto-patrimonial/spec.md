# Especificación 004: Copiloto Patrimonial (Asistente Asesor con Function Calling & Doble Tesis)

## 1. Resumen Ejecutivo y Visión

El **Copiloto Patrimonial** es un asistente conversacional avanzado de inteligencia financiera integrado en la plataforma. Su misión es orientar al usuario en la toma de decisiones financieras, asignación de excedentes patrimoniales (saldo *"Sin Asignar"*) y evaluación de activos de inversión, respetando de manera estricta e innegociable la Constitución del proyecto.

A diferencia de un chatbot genérico que recibe toda la información del usuario en cada mensaje, el Copiloto opera bajo el **patrón de herramientas bajo demanda (Function Calling / estilo MCP)**:
1. **Privacidad por Diseño (Principio 10)**: El prompt inicial del modelo **no contiene datos contables ni personales**.
2. **Acceso Instrumental**: El asistente únicamente accede a la base de datos local (`finanzas.db`), a la lista de seguimiento (`watchlist`) o a los datos macro/contables cacheados **cuando el usuario lo solicita explícitamente o la consulta lo requiere**, invocando funciones tipadas de consulta.
3. **Reutilización Eficiente de Caché**: Las consultas sobre análisis fundamental y contexto macroeconómico leen los diagnósticos **ya computados y cacheados en SQLite**, evitando llamadas redundantes a otros modelos o recomputaciones innecesarias de tokens.
4. **Salvaguarda de Seguridad (Principio 9)**: Veto programático e ineludible a sugerencias de renta variable o activos con riesgo si el fondo de emergencia no cubre al menos 3 meses de gastos fijos esenciales.
5. **Doble Tesis Obligatoria**: Toda tesis o análisis de oportunidad debe explicitar obligatoriamente al menos 2 riesgos bajistas cuantitativos o cualitativos (*"¿Qué puede salir mal y cuánto capital o rentabilidad destruiría?"*).
6. **Persistencia Local de Conversaciones**: El historial de chats y sesiones se guarda en SQLite local (`copilot_sessions` y `copilot_messages`) para permitir recuperar consultas pasadas y retomar el hilo analítico.

---

## 2. Pregunta Arquitectónica: Conexión con NotebookLM vs Fuentes Locales / MCP

### Análisis de Viabilidad de Google NotebookLM
- **Estado Actual de NotebookLM**: Google NotebookLM es un servicio web experimental de Google Labs. A la fecha actual, **Google no ofrece una API pública oficial ni un servidor MCP oficial** para acceder programáticamente a las libretas de NotebookLM.
- **Riesgos de integraciones no oficiales**: Existen librerías comunitarias basadas en cookies de sesión web o scraping, pero están prohibidas en este entorno debido a su extrema fragilidad ante cambios de la interfaz web, riesgo de revocación de credenciales y vulneración de los principios de robustez y resiliencia.
- **Solución Arquitectónica Oficial y Extensible (Estilo MCP)**:
  - Diseñamos la arquitectura de herramientas (*Tools*) del Copiloto desacoplada e interoperable bajo la especificación estándar de Function Calling (compatible con la especificación de herramientas MCP).
  - El Copiloto incorporará una herramienta de **Fuentes de Documentación / Tesis Financieras** (`read_knowledge_source`) que podrá leer archivos locales (PDFs, Markdown, notas exportadas de NotebookLM o informes bursátiles) ubicados en una carpeta designada `src/backend/data/knowledge/` o similar.
  - Cuando Google publique una API oficial o conector para NotebookLM, el sistema podrá conectarse de forma nativa a través de una herramienta adicional sin requerir modificaciones en la arquitectura del copiloto.

---

## 3. Requisitos Funcionales (RF)

- **RF-1 (Gestión de Sesiones y Persistencia en SQLite)**:
  - Crear, listar, renombrar y eliminar sesiones de conversación persistentes en SQLite local.
  - Almacenar los mensajes con sus roles (`user`, `assistant`, `system`, `tool`) y las llamadas a herramientas registradas.
- **RF-2 (Herramientas bajo Demanda - Function Calling)**:
  El modelo tendrá acceso exclusivo mediante llamadas a herramientas a los siguientes métodos:
  1. `get_financial_profile()`: Obtiene el resumen consolidado del último mes cerrado y mes en curso: ingresos netos, necesidades básicas (gastos fijos), deseos, ahorro/inversión, saldo *"Sin Asignar"* y cobertura del Fondo de Emergencia (saldo actual, meta de 3 meses, meses cubiertos y estado de seguridad).
  2. `get_watchlist_items()`: Lista los activos guardados por el usuario en su lista de seguimiento local con sus precios actuales y notas.
  3. `get_cached_deepdive(ticker: str)`: Obtiene el informe de análisis fundamental, puntuación Piotroski y tesis Quality Value **ya almacenados en la caché SQLite de 24 horas**. Si el activo no está en caché, informa educadamente que el usuario debe analizarlo previamente desde la pestaña de Deep Dive.
  4. `get_cached_macro_overview()`: Consulta los indicadores macroeconómicos y deuda soberana del BCE **ya cacheados** en SQLite.
  5. `search_local_notes(query: str)`: Consulta notas de inversión o documentos locales si se encuentran configurados.
- **RF-3 (Salvaguarda de Seguridad Patrimonial - Principio 9)**:
  - Si el fondo de emergencia es `< 3 meses`, cualquier recomendación de renta variable o activo de riesgo queda terminantemente bloqueada.
  - El asistente debe explicar con claridad pedagógica que la prioridad patrimonial absoluta es blindar el fondo de emergencia antes de asumir volatilidad de mercado.
- **RF-4 (Doble Tesis y Evaluación de Riesgos)**:
  - Cuando se discuta una oportunidad de inversión, el Copiloto debe presentar una doble tesis: motivos favorables y obligatoriamente un mínimo de 2 riesgos bajistas severos (*bearish risks*), desaconsejando el sesgo de confirmación.
- **RF-5 (Selector de Modelo y Fallback Resiliente)**:
  - Soporte de configuración jerárquica mediante `.env` (`GEMINI_COPILOT_MODEL`, `GEMINI_MODEL`, con fallback a `gemini-2.5-pro` o `gemini-3.1-flash`).
  - Degradación elegante con mensaje informativo ante ausencia de `GEMINI_API_KEY` o límite de cuota alcanzado.
- **RF-6 (Interfaz Conversacional en Streamlit)**:
  - Pestaña *"💬 Copiloto Patrimonial"*.
  - Barra lateral (*sidebar*) para navegar entre sesiones anteriores o crear una nueva conversación.
  - Componente de chat con `st.chat_message`, caja de entrada interactiva `st.chat_input`.
  - Visualización colapsable (*expander*) que muestra qué herramientas internas fueron consultadas para generar la respuesta, garantizando máxima transparencia sobre los datos leídos.
  - Descargo legal visible (*disclaimer*) de no-asesoramiento financiero regulado.

---

## 4. Requisitos No Funcionales (RNF)

- **RNF-1 (Privacidad Local Absoluta - Principio 10)**:
  - Nunca se transmiten transacciones individuales ni datos sensibles al LLM; únicamente resúmenes numéricos disociados cuando el usuario autoriza la consulta mediante su pregunta.
- **RNF-2 (Convención de Idioma - Opción 1)**:
  - Código Backend, base de datos y esquemas Pydantic 100% en inglés: `CopilotSession`, `CopilotMessage`, `/copilot/*`, `get_financial_profile`.
  - Interfaz de usuario, mensajes del asistente, docstrings y explicaciones 100% en español.
- **RNF-3 (Observabilidad y Prohibición de Fallos Silenciosos)**:
  - Toda llamada al LLM, ejecución de tool y persistencia en base de datos debe contar con logging estructurado (`logger.info`, `logger.warning`, `logger.error`), sin `pass` ciego.
- **RNF-4 (Pruebas Automatizadas con Pytest)**:
  - Cobertura de pruebas unitarias para modelos, herramientas, servicios y pruebas de integración para los endpoints REST de la API. Mantenimiento del 100% de tests pasando en la suite global.

---

## 5. Modelos de Base de Datos y Esquemas

### Modelo ORM SQLAlchemy (`src/backend/domain/models/copilot.py`)
- `CopilotSession`:
  - `id`: `Integer`, Primary Key, autoincremental.
  - `title`: `String(150)`, título de la conversación (ej. *"Consulta asignación nómina octubre"*).
  - `created_at`: `DateTime(timezone=True)`.
  - `updated_at`: `DateTime(timezone=True)`.
  - Relación: `messages` (cascada `all, delete-orphan`).
- `CopilotMessage`:
  - `id`: `Integer`, Primary Key, autoincremental.
  - `session_id`: `Integer`, Foreign Key a `copilot_sessions.id`.
  - `role`: `String(20)` (`user`, `assistant`, `system`, `tool`).
  - `content`: `Text`, contenido textual del mensaje.
  - `tool_calls`: `JSON` / `Text` (opcional, lista de llamadas a herramientas ejecutadas).
  - `created_at`: `DateTime(timezone=True)`.

### Esquemas Pydantic v2 (`src/backend/domain/schemas/copilot.py`)
- `CopilotMessageCreate`: Esquema para nuevo mensaje de usuario.
- `CopilotMessageResponse`: Respuesta con rol, contenido, fecha y herramientas invocadas.
- `CopilotSessionCreate`: Creación de sesión con título opcional.
- `CopilotSessionResponse`: Metadatos de la sesión y contador de mensajes.
- `CopilotChatRequest`: `session_id` (opcional), `message: str`.
- `CopilotChatResponse`: `session_id`, `message: CopilotMessageResponse`, `tools_used: List[str]`.

---

## 6. Endpoints REST de la API (`src/backend/api/routers/copilot.py`)

- `GET /copilot/sessions`: Lista las sesiones ordenadas por fecha de actualización descendente.
- `POST /copilot/sessions`: Crea una nueva sesión de conversación vacía.
- `GET /copilot/sessions/{session_id}`: Obtiene el detalle de la sesión y todos sus mensajes históricos.
- `DELETE /copilot/sessions/{session_id}`: Elimina la sesión y todos sus mensajes asociados.
- `POST /copilot/chat`: Procesa un mensaje de usuario en una sesión, ejecuta el bucle de Function Calling con Google Gemini y persiste el intercambio en SQLite.

---

## 7. Criterios de Aceptación

1. El asistente no revela datos contables del usuario si no se invoca una herramienta explícita.
2. Si el fondo de emergencia es inferior a 3 meses de gastos fijos, el Copiloto rechaza explícitamente cualquier inversión en renta variable o activos con volatilidad.
3. Las conversaciones se guardan en SQLite local y pueden recuperarse al navegar entre sesiones o recargar la aplicación.
4. Las consultas de análisis fundamental y macro leen exclusivamente la caché SQLite existente sin coste de reejecución de IA.
5. Cero regresiones en la suite de pruebas existente y 100% de tests unitarios e integración pasando.
