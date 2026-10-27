"""
Agente Auditor de Riesgos y Debate (Spec 005 - agents).
Implementa BaseAgent y compila su flujo para la doble tesis obligatoria (Red Team).
"""

import logging
from typing import Any, Optional, cast
from google import genai
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent
from backend.components.nodes.risk_debate_node import risk_debate_node
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


class RiskThesisAgent(BaseAgent):
    """
    Agente auditor de riesgos (Red Team). Desafía la complacencia y sesgos de confirmación
    del Comité formulando obligatoriamente al menos 2 riesgos bajistas severos (Principio 12).
    """

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        model_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="RiskThesisAgent",
            description="Auditor de riesgos bajistas, abogado del diablo y garante de la doble tesis obligatoria.",
            model_name=model_name,
        )
        self.client = client

    def build_graph(self) -> Any:
        """Construye y compila el flujo de trabajo del agente en LangGraph."""
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        def node_fn(state: InvestmentCommitteeState):
            return risk_debate_node(state, client=self.client)

        builder.add_node("risk_debater", node_fn)
        builder.set_entry_point("risk_debater")
        builder.add_edge("risk_debater", END)

        return builder.compile()
