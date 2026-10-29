"""
Router de API FastAPI para Pautas Deterministas de Gestión Presupuestaria (Spec 008).
Expone endpoints REST fuertemente tipados para evaluar desvíos mensuales y diagnósticos anuales,
garantizando el desacoplamiento total entre frontend y backend.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
    MonthlyGuidelineReport,
)
from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)

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
def get_monthly_guidelines_endpoint(request: MonthlyGuidelineRequest) -> MonthlyGuidelineReport:
    """Evalúa las pautas y compensaciones deterministas para un mes específico."""
    try:
        report = evaluate_monthly_guidelines(
            month_key=request.month_key,
            month_name=request.month_name,
            real_income=request.real_income,
            budget_income=request.budget_income,
            real_needs=request.real_needs,
            real_wants=request.real_wants,
            real_savings=request.real_savings,
            safety_status=request.safety_status,
        )
        return report
    except Exception as exc:
        logger.error(
            "Error evaluando pautas mensuales para mes %s: %s",
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno evaluando pautas mensuales: {str(exc)}",
        ) from exc


@router.post("/annual", response_model=AnnualGuidelineReport)
def get_annual_guidelines_endpoint(request: AnnualGuidelineRequest) -> AnnualGuidelineReport:
    """Evalúa el diagnóstico estructural y pautas anuales consolidadas."""
    try:
        report = evaluate_annual_guidelines(request.metrics)
        return report
    except Exception as exc:
        logger.error(
            "Error evaluando pautas anuales: %s",
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno evaluando pautas anuales: {str(exc)}",
        ) from exc
