"""
Agente Presidente y Planificador Patrimonial (Spec 005 - agents).
Implementa BaseAgent y compila su flujo para emitir el veredicto vinculante y plan de asignación.
"""

import logging
from typing import Any, Optional, cast
from google import genai
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent
from backend.components.nodes.synthesis_node import synthesis_node
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


class PortfolioAdvisorAgent(BaseAgent):
    """
    Presidente del Comité Asesor de Inversión y Planificador Patrimonial.
    Emite el veredicto vinculante: aplica el veto constitucional si el fondo < 3 meses
    o determina la asignación gradual prudente sopesando el Bull Case y los Bear Risks.
    """

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        model_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="PortfolioAdvisorAgent",
            description="Presidente del Comité Asesor de Inversión y Planificador Patrimonial.",
            model_name=model_name,
        )
        self.client = client

    def build_graph(self) -> Any:
        """Construye y compila el flujo de trabajo del agente en LangGraph."""
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        def node_fn(state: InvestmentCommitteeState):
            return synthesis_node(state, client=self.client)

        builder.add_node("portfolio_synthesizer", node_fn)
        builder.set_entry_point("portfolio_synthesizer")
        builder.add_edge("portfolio_synthesizer", END)

        return builder.compile()
