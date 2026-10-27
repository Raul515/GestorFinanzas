"""
Orquestador Principal del Comité Asesor de Inversión (Spec 005 - components/orchestrator).
Construye, compila y ejecuta el StateGraph maestro en LangGraph coordinando todos los agentes.
Implementa el cortocircuito condicional de salvaguarda patrimonial (Principio 9 de la Constitución).
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, cast
from google import genai
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from backend.agents.safety_guard_agent import SafetyGuardAgent
from backend.agents.macro_agent import MacroAgent
from backend.agents.fundamental_agent import FundamentalAgent
from backend.agents.risk_thesis_agent import RiskThesisAgent
from backend.agents.portfolio_advisor_agent import PortfolioAdvisorAgent
from backend.components.nodes.safety_validator_node import safety_validator_node
from backend.components.nodes.macro_evaluation_node import macro_evaluation_node
from backend.components.nodes.fundamental_analysis_node import fundamental_analysis_node
from backend.components.nodes.risk_debate_node import risk_debate_node
from backend.components.nodes.synthesis_node import synthesis_node
from backend.database.interfaz.db_interface import IRepository
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


def should_continue_after_safety(state: InvestmentCommitteeState) -> str:
    """
    Función de enrutamiento condicional para LangGraph (Principio 9).
    Si el fondo de emergencia no cubre 3 meses (veto activo), deriva inmediatamente
    al supervisor (portfolio_advisor) para emitir veredicto vinculante de veto,
    sin consultar datos macro ni llamar a análisis de renta variable.
    """
    if state.get("veto_active", False):
        logger.warning(
            "MainInvestmentOrchestrator: Cortocircuito condicional activado por veto constitucional. "
            "Derivando directamente al supervisor (PortfolioAdvisorAgent)."
        )
        return "portfolio_advisor"
    return "macro_evaluation"


class MainInvestmentOrchestrator:
    """
    Orquestador maestro del Comité Asesor de Inversión basado en LangGraph.
    Coordina la ejecución secuencial y condicional de los agentes cognitivos.
    """

    def __init__(
        self,
        repo: Optional[IRepository] = None,
        db: Optional[Session] = None,
        client: Optional[genai.Client] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.repo = repo
        self.db = db
        self.client = client
        self.model_name = model_name

        # Instancias de agentes especializados
        self.safety_agent = SafetyGuardAgent(repo=self.repo, db=self.db)
        self.macro_agent = MacroAgent()
        self.fundamental_agent = FundamentalAgent(
            repo=self.repo, client=self.client, model_name=self.model_name
        )
        self.risk_agent = RiskThesisAgent(
            client=self.client, model_name=self.model_name
        )
        self.advisor_agent = PortfolioAdvisorAgent(
            client=self.client, model_name=self.model_name
        )

        self._graph: Optional[Any] = None

    def build_graph(self) -> Any:
        """
        Construye el grafo maestro en LangGraph con nodos, bifurcaciones condicionales y dependencias.
        """
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        # 1. Definición de Nodos de procesamiento
        builder.add_node("safety_guard", self._step_safety)
        builder.add_node("macro_evaluation", self._step_macro)
        builder.add_node("fundamental_analysis", self._step_fundamental)
        builder.add_node("risk_debate", self._step_risk)
        builder.add_node("portfolio_advisor", self._step_advisor)

        # 2. Punto de Entrada
        builder.set_entry_point("safety_guard")

        # 3. Bifurcación Condicional de Salvaguarda Patrimonial (Principio 9)
        builder.add_conditional_edges(
            "safety_guard",
            should_continue_after_safety,
            {
                "portfolio_advisor": "portfolio_advisor",
                "macro_evaluation": "macro_evaluation",
            },
        )

        # 4. Flujo Secuencial si la Salvaguarda está Superada
        builder.add_edge("macro_evaluation", "fundamental_analysis")
        builder.add_edge("fundamental_analysis", "risk_debate")
        builder.add_edge("risk_debate", "portfolio_advisor")
        builder.add_edge("portfolio_advisor", END)

        logger.info("MainInvestmentOrchestrator: Grafo maestro compilado exitosamente.")
        return builder.compile()

    def compile(self) -> Any:
        """Compila y cachea el grafo maestro si no ha sido compilado previamente."""
        if self._graph is None:
            self._graph = self.build_graph()
        return self._graph

    def run(self, initial_state: InvestmentCommitteeState) -> InvestmentCommitteeState:
        """
        Ejecuta la deliberación del Comité Asesor en LangGraph de principio a fin.
        Garantiza degradación elegante y captura de excepciones.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        state_copy: InvestmentCommitteeState = dict(initial_state)  # type: ignore[assignment]
        if "agent_logs" not in state_copy or state_copy["agent_logs"] is None:
            state_copy["agent_logs"] = []

        try:
            compiled = self.compile()
            logger.info(
                "Iniciando deliberación del Comité Asesor con ticker '%s' y mes '%s'...",
                state_copy.get("ticker"),
                state_copy.get("month"),
            )
            final_output = compiled.invoke(state_copy)
            return final_output
        except Exception as exc:
            logger.error("Error crítico en ejecución del orquestador LangGraph: %s", exc, exc_info=True)
            error_log = {
                "agent": "MainInvestmentOrchestrator",
                "timestamp": now_iso,
                "message": f"Fallo en la orquestación del Comité Asesor: {str(exc)}",
                "data_keys": ["error", "error_message"],
            }
            state_copy["error"] = True
            state_copy["error_message"] = str(exc)
            state_copy["agent_logs"] = list(state_copy.get("agent_logs", [])) + [error_log]
            return state_copy

    # Métodos privados de paso intermedio que retornan deltas para el StateGraph maestro
    def _step_safety(self, state: InvestmentCommitteeState) -> Dict[str, Any]:
        return safety_validator_node(state, repo=self.repo, db=self.db)

    def _step_macro(self, state: InvestmentCommitteeState) -> Dict[str, Any]:
        return macro_evaluation_node(state)

    def _step_fundamental(self, state: InvestmentCommitteeState) -> Dict[str, Any]:
        return fundamental_analysis_node(state, repo=self.repo, client=self.client)

    def _step_risk(self, state: InvestmentCommitteeState) -> Dict[str, Any]:
        return risk_debate_node(state, client=self.client)

    def _step_advisor(self, state: InvestmentCommitteeState) -> Dict[str, Any]:
        return synthesis_node(state, client=self.client)
