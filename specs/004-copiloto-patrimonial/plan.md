# Plan Técnico de Implementación: Spec 004 — Copiloto Patrimonial

## 1. Resumen de la Especificación
- **Objetivo**: Desarrollar el asistente conversacional asesor de finanzas personales e inversión, con persistencia local en SQLite, arquitectura de herramientas bajo demanda (Function Calling / estilo MCP), cumplimiento estricto del veto a renta variable si el fondo de emergencia es `< 3 meses`, principio de doble tesis y reutilización de datos cacheados de análisis fundamental y macroeconomía.
- **Enfoque Metodológico**: SDD anclado a especificaciones, implementación estrictamente fase a fase con puerta de confirmación del usuario, convenciones de idioma (Backend/API 100% en inglés, Frontend/Docs 100% en español) y observabilidad obligatoria sin fallos silenciosos.

---

## 2. Desglose Secuencial de Fases

### Fase 1: Modelos ORM, Repositorio SQLite y Esquemas Pydantic v2
- **Objetivo**: Implementar la capa de datos para la persistencia local de sesiones y mensajes de conversación en SQLite, junto con los esquemas de validación de Pydantic v2.
- **Archivos a crear/modificar**:
  - `src/backend/domain/models/copilot.py` [NUEVO]
  - `src/backend/domain/schemas/copilot.py` [NUEVO]
  - `src/backend/database/componentes/sqlite_db.py` [MODIFICADO: importar modelo para `create_all`]
  - `src/backend/database/interfaz/db_interface.py` [MODIFICADO: interfaz `ICopilotRepository`]
  - `src/backend/database/componentes/sqlite_crud.py` [MODIFICADO: métodos CRUD para sesiones y mensajes]
  - `tests/unit/test_copilot_models.py` [NUEVO]
  - `tests/unit/test_copilot_schemas.py` [NUEVO]
- **Entregables**:
  - Modelos ORM `CopilotSession` y `CopilotMessage`.
  - Esquemas `CopilotSessionCreate`, `CopilotSessionResponse`, `CopilotMessageCreate`, `CopilotMessageResponse`, `CopilotChatRequest`, `CopilotChatResponse`.
  - Métodos CRUD en repositorio SQLite.
  - Tests unitarios con validaciones y relaciones ORM.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_copilot_models.py tests/unit/test_copilot_schemas.py` al 100%.

---

### Fase 2: Catálogo de Herramientas Desacopladas (Tools under Demand)
- **Objetivo**: Implementar el catálogo de herramientas tipadas que el Copiloto puede invocar de forma modular bajo demanda cuando el usuario lo solicite.
- **Archivos a crear/modificar**:
  - `src/backend/services/copilot_tools.py` [NUEVO]
  - `tests/unit/test_copilot_tools.py` [NUEVO]
- **Herramientas a implementar**:
  1. `get_financial_profile(repo: IRepository)`: Extrae ingresos netos, necesidades básicas, deseos, ahorro/inversión, saldo *"Sin Asignar"*, saldo del fondo de emergencia, meta de 3 meses y meses cubiertos.
  2. `get_watchlist_items(repo: IRepository)`: Extrae los tickers, nombres, precios y notas de la Watchlist local.
  3. `get_cached_deepdive(repo: IRepository, ticker: str)`: Lee el diagnóstico contable, puntuación Piotroski y tesis Quality Value guardados en `MarketCache` (sin llamadas repetidas a LLMs).
  4. `get_cached_macro_overview(repo: IRepository)`: Lee los indicadores macroeconómicos y deuda soberana del BCE guardados en `MarketCache`.
  5. `search_local_knowledge(query: str)`: Busca notas o documentos locales si están configurados en el sistema.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_copilot_tools.py` al 100%.

---

### Fase 3: Servicio de Orquestación del Agente Asesor con Gemini (Function Calling & Doble Tesis)
- **Objetivo**: Implementar el servicio agéntico del Copiloto que gestiona el bucle de herramientas (*tool loop*) con Google Gemini, inyecta las directrices constitucionales y formula respuestas pedagógicas con doble tesis obligatoria.
- **Archivos a crear/modificar**:
  - `src/backend/services/llm_copilot_advisor.py` [NUEVO]
  - `tests/unit/test_llm_copilot_advisor.py` [NUEVO]
- **Capacidades**:
  - System prompt con directrices constitucionales:
    - Veto terminante a inversión en renta variable si el fondo de emergencia es `< 3 meses`.
    - Obligatoriedad de doble tesis con al menos 2 riesgos bajistas severos al analizar oportunidades.
    - Prohibición de inventar o suponer datos contables si no se ha llamado a la herramienta correspondiente.
    - Explicaciones pedagógicas, neutrales y fundamentadas.
  - Declaración formal de herramientas para la API de `google-genai`.
  - Bucle de Function Calling: detección de `function_call`, ejecución local en el backend y retroalimentación para la síntesis final.
  - Manejo de degradación elegante si no hay API Key o falla la conexión.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_llm_copilot_advisor.py` al 100%.

---

### Fase 4: Endpoints REST en FastAPI
- **Objetivo**: Exponer las funcionalidades del Copiloto a través de una API REST desacoplada y tipada.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/copilot.py` [NUEVO]
  - `src/backend/api/main.py` [MODIFICADO: registro de router `/copilot`]
  - `tests/integration/test_copilot_api.py` [NUEVO]
- **Endpoints**:
  - `GET /copilot/sessions`: Lista de sesiones guardadas.
  - `POST /copilot/sessions`: Crear nueva sesión.
  - `GET /copilot/sessions/{session_id}`: Detalle de sesión y mensajes históricos.
  - `DELETE /copilot/sessions/{session_id}`: Eliminar sesión y mensajes.
  - `POST /copilot/chat`: Envío de mensaje, orquestación del agente y persistencia del intercambio.
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/integration/test_copilot_api.py` al 100%.

---

### Fase 5: Métodos Cliente y Nueva Pestaña en Streamlit (`💬 Copiloto Patrimonial`)
- **Objetivo**: Desarrollar la interfaz conversacional interactiva en Streamlit.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: métodos de sesiones y chat]
  - `src/frontend/app.py` [MODIFICADO: nueva pestaña de Copiloto]
  - `src/frontend/style.css` [MODIFICADO: estilos de mensajes, badges de tools y layout de chat]
  - `tests/unit/test_sanity.py` [MODIFICADO: verificación de nuevos métodos cliente]
- **Componentes Visuales**:
  - Sidebar con lista de conversaciones históricas, botón para nueva consulta y botón de borrado.
  - Ventana de chat con `st.chat_message` para usuario y asistente.
  - Bloque expandible en cada respuesta indicando las herramientas internas consultadas (`🔧 Herramientas consultadas: get_financial_profile, get_cached_deepdive`).
  - Banner de advertencia si el fondo de emergencia está incompleto.
  - Disclaimer legal permanente al pie.
- **Puerta de Verificación**:
  - Interfaz probada visualmente y navegación fluida entre pestañas.

---

### Fase 6: Pruebas Globales, Control de Regresiones, Actualización de Docs y Cierre
- **Objetivo**: Asegurar la estabilidad integral, cero regresiones y cumplimiento de la Constitución.
- **Acciones**:
  1. Ejecución de la suite completa de pruebas:
     ```powershell
     .\venv\Scripts\pytest -v
     ```
     (Se prevé superar las 135 pruebas pasando al 100%).
  2. Comprobación exhaustiva de sintaxis:
     ```powershell
     .\venv\Scripts\python -m compileall src tests
  3. Verificación de tipado estático con Pyright.
  4. Auditoría pre-commit con `git status -u`.
  5. Actualización de `specs/README.md` y `MEMORY.md`.
- **Puerta de Verificación**: Cero fallos en pytest y confirmación explícita del usuario.
