# Especificación 005: Orquestación Multiagente con LangGraph (Comité Asesor de Inversión)

## 1. Resumen Ejecutivo y Visión

La **Especificación 005** consolida la cúspide de inteligencia analítica del Gestor de Finanzas Personales. Transforma los diagnósticos y servicios aislados desarrollados en las especificaciones 000 a 004 (Salvaguarda de Seguridad, Radar Macro, Screener, Deep Dive Fundamental Quality Value y Copiloto con Function Calling) en un **Comité Asesor de Inversión Multiagente** orquestado mediante **LangGraph**.

El sistema se estructura bajo una arquitectura cognitiva desacoplada y modular en `src/backend/`:
1. **`agents/` (Motor Cognitivo)**: Agentes especializados que heredan de una interfaz abstracta común `BaseAgent`, compilando sus propios subgrafos o flujos de trabajo.
2. **`components/` (Orquestación, Nodos y Herramientas)**:
   - `orchestrator/`: `MainInvestmentOrchestrator` (el "CEO"), que dirige el grafo principal y coordina la deliberación del comité.
   - `nodes/`: Nodos de procesamiento de LangGraph (validación de salvaguarda, análisis macro, auditoría contable fundamental, debate de riesgos y síntesis).
   - `tools/`: Herramientas deterministas e instrumentales (cálculo de ratios, consultas a SQLite, extracción de mercado).
   - `prompts/`: Plantillas estructuradas de prompts parametrizados por rol.
3. **`domain/` (Modelos y Estados)**:
   - Estados compartidos de LangGraph (`InvestmentCommitteeState`) y esquemas Pydantic v2 tipados.
4. **`external_components/` (Persistencia e Ingesta)**:
   - Base de datos desacoplada e ingesta de fuentes de notas locales.
5. **`api/` (Servidor REST FastAPI)**:
   - Endpoints para ejecutar y consultar deliberaciones del Comité Asesor.
6. **`frontend/` (Interfaz Streamlit)**:
   - Visualización transparente del proceso de deliberación paso a paso de los agentes, doble tesis y veredicto patrimonial unificado.

---

## 2. Requisitos Funcionales (RF)

### RF-1: Motor Cognitivo y Agentes (`src/backend/agents/`)
- Todos los agentes implementan la clase abstracta `BaseAgent` (`base_agent.py`), que define el método abstracto `build_graph()` retornando un grafo compilado de LangGraph (`CompiledStateGraph`).
- **Agentes Especializados**:
  1. `SafetyGuardAgent` (`safety_guard_agent.py`): Audita la liquidez disponible, los porcentajes 50/30/20 y la cobertura del Fondo de Emergencia. Si cubre `< 3 meses`, levanta el **veto constitucional innegociable (Principio 9)**.
  2. `MacroAnalystAgent` (`macro_agent.py`): Contextualiza el entorno monetario del BCE, rendimientos de bonos soberanos (España, Alemania, EE.UU.), prima de riesgo y tendencia de índices.
  3. `FundamentalAnalystAgent` (`fundamental_agent.py`): Extrae y audita los estados financieros a 4 años, computa el Piotroski F-Score determinista (0-9) y las métricas FCF/Moat bajo metodología Quality Value.
  4. `RiskThesisAgent` (`risk_thesis_agent.py`): Agente de debate ("Red Team") encargado de formular la **doble tesis obligatoria**: exige un mínimo de 2 riesgos bajistas severos (*bearish risks*) respondiendo a: *"¿Qué puede salir mal y cuánto beneficio destruiría?"*.
  5. `PortfolioAdvisorAgent` (`portfolio_advisor_agent.py`): Genera la síntesis patrimonial unificada, asignación sugerida del saldo *"Sin Asignar"* y zona de entrada por valoración (TIR 15%-20%), supeditada al veredicto de la salvaguarda de seguridad.

### RF-2: Componentes de Orquestación, Nodos y Herramientas (`src/backend/components/`)
- 📁 **`orchestrator/`**:
  - `MainInvestmentOrchestrator` (`main_investment_orchestrator.py`): Define el `StateGraph` global que coordina la secuencia de deliberación:
    1. Nodo de Salvaguarda Patrimonial.
    2. Si hay veto activo: transición directa a síntesis con bloqueo explícito de inversión en riesgo.
    3. Si salvaguarda superada: ejecución paralela/secuencial de análisis Macro y Fundamental.
    4. Nodo de Debate y Doble Tesis (Red Team).
    5. Nodo de Síntesis y Veredicto Final.
- 📁 **`nodes/`**:
  - `SafetyValidatorNode` (`safety_validator_node.py`)
  - `MacroEvaluationNode` (`macro_evaluation_node.py`)
  - `FundamentalAnalysisNode` (`fundamental_analysis_node.py`)
  - `RiskDebateNode` (`risk_debate_node.py`)
  - `SynthesisNode` (`synthesis_node.py`)
- 📁 **`tools/`**:
  - Reutilización de herramientas y servicios matemáticos puros ya testeados (`safety_guard`, `market_data_service`, `equity_deepdive`, `copilot_tools`).
- 📁 **`prompts/`**:
  - Prompts estructurados con delimitadores semánticos claros para cada rol cognitivo.

### RF-3: Estados Compartidos de LangGraph (`src/backend/domain/states/`)
- `InvestmentCommitteeState`:
  - `ticker`: Símbolo bursátil analizado (opcional si es consulta patrimonial general).
  - `month`: Mes contable de referencia.
  - `safety_status`: Cobertura del fondo, meses cubiertos y bandera de veto.
  - `macro_overview`: Indicadores macroeconómicos y primas de riesgo.
  - `fundamental_data`: Ratios contables, Piotroski y cuadrante Quality Value.
  - `bull_thesis`: Argumentos cuantitativos y cualitativos favorables.
  - `bear_risks`: Lista obligatoria de al menos 2 riesgos bajistas severos.
  - `final_verdict`: Veredicto formal del Comité, porcentaje de asignación y valoración por TIR.
  - `agent_logs`: Registro cronológico de las intervenciones de cada agente en la deliberación.
  - `error`: Bandera e información de degradación elegante.

### RF-4: Componentes Externos Desacoplados (`src/backend/external_components/`)
- 📁 **`database/`**:
  - Repositorio y cliente SQLite local (`sqlite_crud.py`, `sqlite_db.py`, interfaz `IRepository`).
- 📁 **`data_ingestion/`**:
  - Conector local para notas personales y documentos de inversión en `data/knowledge/` (`local_doc_loader.py`).

### RF-5: API REST (`src/backend/api/routers/committee.py`)
- `POST /committee/analyze`: Inicia la deliberación del Comité Asesor Multiagente recibiendo `ticker` (opcional) y `month`.
- Devuelve el reporte estructurado `InvestmentCommitteeResponse` con el veredicto, deliberación paso a paso de cada agente y estado de la salvaguarda.

### RF-6: Interfaz en Streamlit (`src/frontend/`)
- Nueva sección interactiva en la interfaz visual:
  - Formulario de solicitud al Comité (análisis de empresa de la Watchlist o asignación general).
  - Visualización del flujo de deliberación de los agentes mediante componentes de estado (paso a paso: Salvaguarda -> Macro -> Fundamental -> Debate de Riesgos -> Veredicto).
  - Tarjeta de Veredicto Final con badge de Salvaguarda Patrimonial y desglose de la doble tesis.
  - Descargo legal permanente.

---

## 3. Requisitos No Funcionales (RNF)

- **RNF-1 (Privacidad Local - Principio 10)**: Ningún dato del libro diario ni transacciones personales se transmiten en prompts iniciales; sólo agregados numéricos calculados localmente.
- **RNF-2 (Convención de Idioma - Opción 1)**: Todo el código backend, agentes, estados de LangGraph, modelos y endpoints 100% en inglés. Documentación, interfaz de usuario y explicaciones 100% en español.
- **RNF-3 (Observabilidad y Prohibición de Fallos Silenciosos)**: Registro estructurado con `logging` en cada nodo del grafo, sin `pass` silenciosos.
- **RNF-4 (Veracidad Cuantitativa y Pruebas)**: 100% de pruebas pasando en `pytest` con mocks de LLM para garantizar determinismo en integración continua.
