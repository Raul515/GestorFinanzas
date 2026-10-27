"""
Agente Validador de Salvaguarda Patrimonial (Spec 005 - agents).
Implementa BaseAgent y compila su flujo para verificar la solvencia del Fondo de Emergencia (Principio 9).
"""

import logging
from typing import Any, Optional, cast
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from backend.agents.base_agent import BaseAgent
from backend.components.nodes.safety_validator_node import safety_validator_node
from backend.database.interfaz.db_interface import IRepository
from backend.domain.states.investment_committee_state import InvestmentCommitteeState

logger = logging.getLogger(__name__)


class SafetyGuardAgent(BaseAgent):
    """
    Agente responsable de salvaguardar el patrimonio del usuario.
    Verifica deterministamente que el Fondo de Emergencia cubra al menos 3 meses de gastos fijos
    antes de autorizar la deliberación de activos de inversión en renta variable.
    """

    def __init__(
        self,
        repo: Optional[IRepository] = None,
        db: Optional[Session] = None,
    ) -> None:
        super().__init__(
            name="SafetyGuardAgent",
            description="Auditor de salvaguarda patrimonial y cumplimiento del Fondo de Emergencia (Principio 9).",
        )
        self.repo = repo
        self.db = db

    def build_graph(self) -> Any:
        """Construye y compila el flujo de trabajo del agente en LangGraph."""
        builder = StateGraph(cast(Any, InvestmentCommitteeState))

        def node_fn(state: InvestmentCommitteeState):
            return safety_validator_node(state, repo=self.repo, db=self.db)

        builder.add_node("safety_validator", node_fn)
        builder.set_entry_point("safety_validator")
        builder.add_edge("safety_validator", END)

        return builder.compile()
