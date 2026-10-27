"""
Nodo de Validación de Salvaguarda Patrimonial (Spec 005 - components/nodes).
Nodo 100% determinista (Python puro): verifica el Fondo de Emergencia y aplica el veto constitucional.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.database.interfaz.db_interface import IRepository
from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.tools.committee_tools import fetch_safety_status

logger = logging.getLogger(__name__)


def safety_validator_node(
    state: InvestmentCommitteeState,
    repo: Optional[IRepository] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Evalúa la salvaguarda de seguridad del usuario de forma determinista (0 tokens de IA).
    Si el fondo cubre menos de 3 meses, activa inmediatamente el veto constitucional (Principio 9).
    """
    # Si ya se proporcionó un safety_status en el estado inicial, utilizarlo
    current_safety = state.get("safety_status")
    if not current_safety and repo is not None and db is not None:
        target_month = state.get("month")
        current_safety = fetch_safety_status(repo=repo, db=db, month=target_month)
    elif not current_safety:
        # Fallback defensivo si se ejecuta en modo aislado sin BD
        current_safety = {
            "coverage_months": 0.0,
            "investing_allowed": False,
            "current_balance": 0.0,
            "target_3m": 3000.0,
            "unassigned_balance": 0.0,
        }

    coverage_months = current_safety.get("coverage_months", 0.0)
    investing_allowed = current_safety.get("investing_allowed", False)
    veto_active = not investing_allowed or coverage_months < 3.0

    now_iso = datetime.now(timezone.utc).isoformat()
    if veto_active:
        msg = (
            f"Veto Constitucional Activado: El Fondo de Emergencia cubre {coverage_months:.1f} meses "
            f"(mínimo requerido: 3.0 meses). Se prohíbe cualquier recomendación de inversión en renta variable."
        )
        logger.warning("SafetyValidatorNode: %s", msg)
    else:
        msg = (
            f"Salvaguarda Superada: El Fondo de Emergencia cubre {coverage_months:.1f} meses "
            f"(objetivo constitucional cumplido). Autorizada la deliberación de activos de inversión."
        )
        logger.info("SafetyValidatorNode: %s", msg)

    log_entry = {
        "agent": "SafetyValidatorNode",
        "timestamp": now_iso,
        "message": msg,
        "data_keys": ["safety_status", "veto_active"],
    }

    return {
        "safety_status": current_safety,
        "veto_active": veto_active,
        "agent_logs": [log_entry],
    }
