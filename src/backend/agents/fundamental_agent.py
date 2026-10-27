"""
Agente Analista Fundamental y de Calidad (Spec 005 - agents).
Implementa BaseAgent y compila su flujo para evaluar estados contables, Piotroski (0-9) y Quality Value.
"""

import logging
from typing import Any, Optional, cast
from google import genai
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent
from backend.components.nodes.fundamental_analysis_node import fundamental_analysis_node
from backend.database.interfaz.db_interface import IRepository
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


class FundamentalAgent(BaseAgent):
    """
    Agente responsable de la auditoría contable profunda y formulación de la tesis favorable (Bull Case).
    Analiza la conversión a caja libre (FCF), retorno sobre el capital y solidez de balance.
    """

    def __init__(
        self,
        repo: Optional[IRepository] = None,
        client: Optional[genai.Client] = None,
        model_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="FundamentalAgent",
            description="Analista fundamental y de calidad contable bajo metodología Quality Value.",
            model_name=model_name,
        )
        self.repo = repo
        self.client = client

    def build_graph(self) -> Any:
        """Construye y compila el flujo de trabajo del agente en LangGraph."""
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        def node_fn(state: InvestmentCommitteeState):
            return fundamental_analysis_node(state, repo=self.repo, client=self.client)

        builder.add_node("fundamental_analyst", node_fn)
        builder.set_entry_point("fundamental_analyst")
        builder.add_edge("fundamental_analyst", END)

        return builder.compile()
