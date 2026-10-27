# Plan de Implementación: Especificación 005 — Orquestación Multiagente con LangGraph

El plan se divide en 6 fases secuenciales estrictas, con pruebas automatizadas y puerta de confirmación explícita al final de cada una antes de avanzar a la siguiente.

---

### Fase 1: Dependencias, Arquitectura de Carpetas y Estados de LangGraph
- **Objetivo**: Instalar librerías de LangGraph, establecer la estructura de carpetas solicitada en `src/backend/`, definir la clase base `BaseAgent` y el estado compartido `InvestmentCommitteeState`.
- **Archivos a crear/modificar**:
  - `requirements/backend.txt` [MODIFICADO: añadir `langgraph`, `langchain-core`]
  - `src/backend/agents/base_agent.py` [NUEVO: interfaz abstracta común]
  - `src/backend/domain/states/__init__.py` [NUEVO]
  - `src/backend/domain/states/investment_committee_state.py` [NUEVO: estado compartido de LangGraph]
  - `src/backend/domain/schemas/committee.py` [NUEVO: esquemas Pydantic v2 de entrada y salida]
  - `src/backend/external_components/data_ingestion/local_doc_loader.py` [NUEVO: adaptador de notas locales]
  - `tests/unit/test_committee_state_and_schemas.py` [NUEVO]
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_committee_state_and_schemas.py` al 100%.

---

### Fase 2: Nodos de Procesamiento, Herramientas y Prompts (COMPLETADA)
- **Objetivo**: Desarrollar los nodos individuales de procesamiento del grafo, herramientas deterministas reutilizando servicios existentes y plantillas de prompts parametrizados.
- **Archivos a crear/modificar**:
  - `src/backend/components/prompts/committee_prompts.py` [CREADO: prompts estructurados por rol]
  - `src/backend/components/tools/committee_tools.py` [CREADO: wrappers deterministas de servicios existentes]
  - `src/backend/components/nodes/safety_validator_node.py` [CREADO: validación de fondo de 3 meses]
  - `src/backend/components/nodes/macro_evaluation_node.py` [CREADO: evaluación de entorno monetario/deuda]
  - `src/backend/components/nodes/fundamental_analysis_node.py` [CREADO: auditoría contable y Piotroski]
  - `src/backend/components/nodes/risk_debate_node.py` [CREADO: formulación obligatoria de doble tesis]
  - `src/backend/components/nodes/synthesis_node.py` [CREADO: consolidación y veredicto patrimonial]
  - `tests/unit/test_committee_nodes.py` [CREADO]
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_committee_nodes.py` al 100% (19/19 superadas).

---

### Fase 3: Agentes Cognitivos y Orquestador Principal (`MainInvestmentOrchestrator`)
- **Objetivo**: Implementar los agentes especializados que implementan `BaseAgent` y el orquestador principal que compila el `StateGraph` de LangGraph con bifurcaciones condicionales (veto constitucional si fondo < 3 meses).
- **Archivos a crear/modificar**:
  - `src/backend/agents/safety_guard_agent.py` [NUEVO]
  - `src/backend/agents/macro_agent.py` [NUEVO]
  - `src/backend/agents/fundamental_agent.py` [NUEVO]
  - `src/backend/agents/risk_thesis_agent.py` [NUEVO]
  - `src/backend/agents/portfolio_advisor_agent.py` [NUEVO]
  - `src/backend/components/orchestrator/main_investment_orchestrator.py` [NUEVO: StateGraph de LangGraph]
  - `tests/unit/test_committee_orchestrator.py` [NUEVO]
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/unit/test_committee_orchestrator.py` al 100%.

---

### Fase 4: Endpoints REST en FastAPI
- **Objetivo**: Exponer la ejecución del Comité de Inversión Multiagente a través de la API REST.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/committee.py` [NUEVO: endpoint `/committee/analyze`]
  - `src/backend/api/main.py` [MODIFICADO: inclusión del router `/committee`]
  - `tests/integration/test_committee_api.py` [NUEVO]
- **Puerta de Verificación**:
  - `.\venv\Scripts\pytest tests/integration/test_committee_api.py` al 100%.

---

### Fase 5: Métodos Cliente e Interfaz en Streamlit (`🏛️ Comité Asesor Multiagente`)
- **Objetivo**: Integrar la ejecución y visualización del Comité Asesor en la aplicación web interactiva.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: método `run_investment_committee`]
  - `src/frontend/app.py` [MODIFICADO: sección o pestaña del Comité con visualización del flujo de agentes]
  - `src/frontend/style.css` [MODIFICADO: estilos de tarjetas y timeline de deliberación de agentes]
  - `tests/unit/test_sanity.py` [MODIFICADO: verificación del nuevo método cliente]
- **Puerta de Verificación**:
  - Interfaz visual funcional, navegación fluida y pruebas de sanity pasando al 100%.

---

### Fase 6: Pruebas Globales, Control de Regresiones, Actualización de Docs y Cierre
- **Objetivo**: Garantizar cero fallos, estabilidad completa y cumplimiento de la Constitución.
- **Acciones**:
  1. Ejecución de la suite completa de pruebas (`pytest -v`).
  2. Comprobación exhaustiva de sintaxis (`compileall`).
  3. Verificación de tipado estático con Pyright (`npx pyright src tests`).
  4. Auditoría pre-commit con `git status -u`.
  5. Actualización de `specs/README.md` y `MEMORY.md`.
- **Puerta de Verificación**: Cero fallos en pytest y aprobación final del usuario.
