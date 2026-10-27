"""
Nodo de Evaluación Macroeconómica (Spec 005 - components/nodes).
Recopila deterministamente tipos del BCE, rendimientos soberanos y primas de riesgo.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict
from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.tools.committee_tools import fetch_macro_overview

logger = logging.getLogger(__name__)


def macro_evaluation_node(state: InvestmentCommitteeState) -> Dict[str, Any]:
    """
    Recopila los indicadores macroeconómicos clave del mercado.
    Si el veto constitucional está activo, cortocircuita la ejecución para ahorrar recursos.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if state.get("veto_active", False):
        logger.info("MacroEvaluationNode: Omitido debido a veto constitucional activo.")
        return {
            "agent_logs": [
                {
                    "agent": "MacroEvaluationNode",
                    "timestamp": now_iso,
                    "message": "Evaluación macroeconómica omitida por veto constitucional activo.",
                    "data_keys": [],
                }
            ]
        }

    # Si ya se suministraron datos macro en el estado, reutilizarlos
    macro_data = state.get("macro_data")
    if not macro_data:
        macro_data = fetch_macro_overview()

    indicators_count = macro_data.get("total_indicators", len(macro_data.get("indicators", [])))
    msg = f"Entorno macroeconómico evaluado: {indicators_count} indicadores analizados (BCE, bonos soberanos y primas de riesgo)."
    logger.info("MacroEvaluationNode: %s", msg)

    return {
        "macro_data": macro_data,
        "agent_logs": [
            {
                "agent": "MacroEvaluationNode",
                "timestamp": now_iso,
                "message": msg,
                "data_keys": ["macro_data"],
            }
        ],
    }
