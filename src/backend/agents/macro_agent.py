"""
Agente Evaluador del Entorno Macroeconómico (Spec 005 - agents).
Implementa BaseAgent y compila su flujo para evaluar política monetaria y tipos de interés.
"""

import logging
from typing import Any, cast
from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent
from backend.components.nodes.macro_evaluation_node import macro_evaluation_node
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


class MacroAgent(BaseAgent):
    """
    Agente responsable de contextualizar la deliberación del Comité Asesor con indicadores
    macroeconómicos clave (tipos del BCE, deuda soberana española/alemana y prima de riesgo).
    """

    def __init__(self) -> None:
        super().__init__(
            name="MacroAgent",
            description="Evaluador del entorno macroeconómico, tipos de interés y deuda soberana.",
        )

    def build_graph(self) -> Any:
        """Construye y compila el flujo de trabajo del agente en LangGraph."""
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        builder.add_node("macro_evaluator", macro_evaluation_node)
        builder.set_entry_point("macro_evaluator")
        builder.add_edge("macro_evaluator", END)

        return builder.compile()
