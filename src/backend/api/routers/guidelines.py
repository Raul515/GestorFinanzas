"""
Router REST fino para Pautas Deterministas de Gestión y Compensación Presupuestaria (Spec 008).
Delega la lógica de persistencia y cálculo al servicio `guidelines_application_service`.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
    CompensateDeficitRequest,
    CompensateDeficitResponse,
    MonthlyGuidelineReport,
    StrategyApplyRequest,
    StrategyApplyResponse,
    StrategyRevertRequest,
    StrategyRevertResponse,
    SweepRequest,
    SweepResponse,
)
from backend.services.guidelines_application_service import (
    apply_guideline_strategy,
    compensate_guideline_deficit,
    get_monthly_guidelines_report,
    revert_guideline_strategy,
    sweep_month_surplus,
)
from backend.services.guidelines_service import evaluate_annual_guidelines

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guidelines", tags=["guidelines"])


class MonthlyGuidelineRequest(BaseModel):
    month_key: str = Field(..., description="Identificador del mes en formato YYYY-MM")
    month_name: str = Field(..., description="Nombre del mes en español (ej. Enero)")
    real_income: float = Field(0.0, description="Ingresos reales del mes en euros")
    budget_income: float = Field(0.0, description="Ingresos presupuestados en euros")
    real_needs: float = Field(0.0, description="Gasto real en Necesidades Básicas")
    real_wants: float = Field(0.0, description="Gasto real en Deseos / Ocio")
    real_savings: float = Field(0.0, description="Ahorro real asignado en el mes")
    safety_status: Optional[Dict[str, Any]] = Field(
        None, description="Estado del Fondo de Emergencia (Safety Guard) si está disponible"
    )


class AnnualGuidelineRequest(BaseModel):
    metrics: Dict[str, Any] = Field(
        ..., description="Diccionario con métricas anuales calculadas por financial_calculator"
    )


@router.post("/monthly", response_model=MonthlyGuidelineReport)
def get_monthly_guidelines_endpoint(
    request: MonthlyGuidelineRequest,
    db: Session = Depends(get_db),
) -> MonthlyGuidelineReport:
    """Evalúa las pautas y compensaciones deterministas para un mes específico."""
    try:
        return get_monthly_guidelines_report(
            db=db,
            month_key=request.month_key,
            month_name=request.month_name,
            real_income=request.real_income,
            budget_income=request.budget_income,
            real_needs=request.real_needs,
            real_wants=request.real_wants,
            real_savings=request.real_savings,
            safety_status=request.safety_status,
        )
    except Exception as exc:
        logger.error("Error evaluando pautas mensuales para mes %s: %s", request.month_key, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno evaluando pautas mensuales: {exc}") from exc


@router.post("/annual", response_model=AnnualGuidelineReport)
def get_annual_guidelines_endpoint(request: AnnualGuidelineRequest) -> AnnualGuidelineReport:
    """Evalúa el diagnóstico estructural y pautas anuales consolidadas."""
    try:
        return evaluate_annual_guidelines(request.metrics)
    except Exception as exc:
        logger.error("Error evaluando pautas anuales: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno evaluando pautas anuales: {exc}") from exc


@router.post("/apply-strategy", response_model=StrategyApplyResponse)
def apply_guideline_strategy_endpoint(
    request: StrategyApplyRequest,
    db: Session = Depends(get_db),
) -> StrategyApplyResponse:
    """Ejecuta de forma atómica la estrategia de asignación de capital."""
    try:
        return apply_guideline_strategy(db, request)
    except Exception as exc:
        db.rollback()
        logger.error("Error aplicando estrategia %s en mes %s: %s", request.strategy_type, request.month_key, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno aplicando la estrategia: {exc}") from exc


@router.post("/revert-strategy", response_model=StrategyRevertResponse)
def revert_guideline_strategy_endpoint(
    request: StrategyRevertRequest,
    db: Session = Depends(get_db),
) -> StrategyRevertResponse:
    """Revierte atómicamente una estrategia de asignación de capital aplicada."""
    try:
        return revert_guideline_strategy(db, request)
    except Exception as exc:
        db.rollback()
        logger.error("Error al revertir estrategia en mes %s: %s", request.month_key, exc)
        raise HTTPException(status_code=500, detail=f"Error interno al revertir la estrategia: {exc}") from exc


@router.post("/sweep", response_model=SweepResponse)
def sweep_month_surplus_endpoint(
    request: SweepRequest,
    db: Session = Depends(get_db),
) -> SweepResponse:
    """Ejecuta el barrido de fin de mes."""
    try:
        return sweep_month_surplus(db, request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Error ejecutando barrido en mes %s: %s", request.month_key, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno ejecutando el barrido: {exc}") from exc


@router.post("/compensate-deficit", response_model=CompensateDeficitResponse)
def compensate_guideline_deficit_endpoint(
    request: CompensateDeficitRequest,
    db: Session = Depends(get_db),
) -> CompensateDeficitResponse:
    """Ejecuta de forma atómica acciones de compensación y contención presupuestaria."""
    try:
        return compensate_guideline_deficit(db, request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Error ejecutando acción de compensación %s en mes %s: %s", request.action_type, request.month_key, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno en compensación presupuestaria: {exc}") from exc
