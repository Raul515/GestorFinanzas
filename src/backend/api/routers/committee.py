"""
Router REST para el Comité Asesor de Inversión Multiagente con LangGraph (Spec 005 - Fase 4).
Expone el endpoint de deliberación /committee/analyze coordinando los agentes cognitivos
bajo la salvaguarda de seguridad del Principio 9 y la doble tesis obligatoria del Principio 12.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.committee import (
    InvestmentCommitteeRequest,
    InvestmentCommitteeResponse,
)
from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.orchestrator.main_investment_orchestrator import (
    MainInvestmentOrchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/committee", tags=["committee", "advisor"])


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio de base de datos."""
    return SQLiteRepository(db)


@router.post(
    "/analyze",
    response_model=InvestmentCommitteeResponse,
    status_code=status.HTTP_200_OK,
)
def analyze_investment_committee(
    request: InvestmentCommitteeRequest,
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
) -> InvestmentCommitteeResponse:
    """
    Convoca la deliberación del Comité Asesor de Inversión Multiagente orquestado con LangGraph.
    - Valida de forma determinista la salvaguarda patrimonial (Principio 9: mínimo 3 meses de fondo de emergencia).
    - Si el veto constitucional está activo, cortocircuita de inmediato bloqueando cualquier inversión en riesgo.
    - Si la salvaguarda está superada, ejecuta la deliberación con evaluación macroeconómica, auditoría fundamental
      Quality Value, formulación de doble tesis obligatoria (mínimo 2 riesgos bajistas) y veredicto con plan de acción.
    - Devuelve el reporte estructurado con el veredicto, desglose y trazabilidad de los agentes.
    """
    ticker_clean = request.ticker.strip().upper() if request.ticker and request.ticker.strip() else None
    month_target = request.month.strip() if request.month and request.month.strip() else "BASE"

    logger.info(
        "Invocando deliberación del Comité Asesor de Inversión: Ticker='%s', Mes='%s'",
        ticker_clean,
        month_target,
    )

    initial_state: InvestmentCommitteeState = {
        "ticker": ticker_clean,
        "month": month_target,
        "initial_notes": request.initial_notes,
        "agent_logs": [],
    }

    try:
        orchestrator = MainInvestmentOrchestrator(repo=repo, db=db)
        final_state = orchestrator.run(initial_state)

        # Mapeo estructurado al DTO de respuesta
        veto_active = final_state.get("veto_active", False)
        safety_summary = final_state.get("safety_status") or {
            "coverage_months": 0.0,
            "investing_allowed": False,
            "target_3m": 0.0,
            "current_balance": 0.0,
        }
        macro_summary = final_state.get("macro_data")
        fundamental_summary = final_state.get("fundamental_data")
        bull_thesis = final_state.get("bull_thesis")
        bear_risks = final_state.get("bear_risks") or []
        final_verdict = final_state.get("final_verdict") or (
            f"Error en deliberación: {final_state.get('error_message')}"
            if final_state.get("error")
            else "Sin veredicto emitido."
        )
        action_plan = final_state.get("action_plan")
        agent_logs = final_state.get("agent_logs") or []

        return InvestmentCommitteeResponse(
            ticker=final_state.get("ticker") or ticker_clean,
            month=final_state.get("month") or month_target,
            veto_active=veto_active,
            safety_summary=safety_summary,
            macro_summary=macro_summary,
            fundamental_summary=fundamental_summary,
            bull_thesis=bull_thesis,
            bear_risks=bear_risks,
            final_verdict=final_verdict,
            action_plan=action_plan,
            agent_logs=agent_logs,
        )
    except Exception as exc:
        logger.error(
            "Error inesperado al ejecutar la deliberación del Comité Asesor en endpoint /committee/analyze: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la deliberación del Comité Asesor: {str(exc)}",
        )
