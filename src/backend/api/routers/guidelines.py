import datetime
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.models import (
    budgets as pres_models,
    categories as cat_models,
    emergency_fund as ef_models,
    transactions as tx_models,
)
from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
    MonthlyGuidelineReport,
    StrategyApplyRequest,
    StrategyApplyResponse,
    SweepRequest,
    SweepResponse,
)
from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guidelines", tags=["guidelines"])


def _resolve_tx_date(month_key: str) -> datetime.date:
    """Calcula una fecha válida dentro del mes indicado."""
    try:
        parts = month_key.split("-")
        year, month = int(parts[0]), int(parts[1])
        today = datetime.date.today()
        if today.year == year and today.month == month:
            return today
        return datetime.date(year, month, 28)
    except Exception:
        return datetime.date.today()


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


@router.post("/apply-strategy", response_model=StrategyApplyResponse)
def apply_guideline_strategy_endpoint(
    request: StrategyApplyRequest,
    db: Session = Depends(get_db),
) -> StrategyApplyResponse:
    """
    Ejecuta de forma atómica la estrategia de asignación de capital:
    - Crea transacciones de aporte en las subcategorías de Ahorro.
    - Sincroniza el saldo del Fondo de Emergencia si alguna asignación apunta a él.
    - Incrementa el presupuesto de las subcategorías de Deseos seleccionadas.
    """
    tx_date = _resolve_tx_date(request.month_key)
    created_txs = 0
    updated_budgets = 0
    ef_updated = False
    new_ef_balance = None

    try:
        # 1. Procesar asignaciones a Ahorro/Inversión (Transacciones de gasto/aporte)
        for item in request.savings_allocations:
            if item.amount <= 0:
                continue

            sub = (
                db.query(cat_models.Subcategory)
                .filter(cat_models.Subcategory.id == item.subcategory_id)
                .first()
            )
            sub_name = sub.name.lower() if sub else ""

            # Verificar si corresponde al Fondo de Emergencia para actualizar saldo
            if "emergencia" in sub_name:
                ef = db.query(ef_models.EmergencyFund).first()
                if ef:
                    ef.current_balance += item.amount
                    if ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
                        ef.is_completed = True
                    ef_updated = True
                    new_ef_balance = ef.current_balance

            tx = tx_models.Transaction(
                date=tx_date,
                subcategory_id=item.subcategory_id,
                amount=item.amount,
                description=f"[Pauta {request.strategy_type}] Asignación de Excedente",
            )
            db.add(tx)
            created_txs += 1

        # 2. Procesar asignaciones a Deseos (Incremento de Presupuesto)
        for item in request.wants_allocations:
            if item.amount <= 0:
                continue

            b = (
                db.query(pres_models.MonthlyBudget)
                .filter(
                    pres_models.MonthlyBudget.month == request.month_key,
                    pres_models.MonthlyBudget.subcategory_id == item.subcategory_id,
                )
                .first()
            )
            if b:
                b.amount += item.amount
            else:
                base_b = (
                    db.query(pres_models.MonthlyBudget)
                    .filter(
                        pres_models.MonthlyBudget.month == "BASE",
                        pres_models.MonthlyBudget.subcategory_id == item.subcategory_id,
                    )
                    .first()
                )
                init_amount = (base_b.amount if base_b else 0.0) + item.amount
                new_b = pres_models.MonthlyBudget(
                    month=request.month_key,
                    subcategory_id=item.subcategory_id,
                    amount=init_amount,
                )
                db.add(new_b)
            updated_budgets += 1

        db.commit()
        logger.info(
            "Estrategia %s aplicada con éxito en mes %s: %d transacciones creadas, %d presupuestos actualizados.",
            request.strategy_type,
            request.month_key,
            created_txs,
            updated_budgets,
        )
        return StrategyApplyResponse(
            success=True,
            message=f"Estrategia {request.strategy_type} aplicada exitosamente.",
            month_key=request.month_key,
            transactions_created=created_txs,
            budgets_updated=updated_budgets,
            emergency_fund_updated=ef_updated,
            new_emergency_fund_balance=new_ef_balance,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error aplicando estrategia %s en mes %s: %s",
            request.strategy_type,
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno aplicando estrategia: {str(exc)}",
        ) from exc


@router.post("/sweep", response_model=SweepResponse)
def sweep_month_surplus_endpoint(
    request: SweepRequest,
    db: Session = Depends(get_db),
) -> SweepResponse:
    """
    Ejecuta el barrido de fin de mes:
    - Transfiere el remanente de liquidez ociosa/colchón hacia la subcategoría de Ahorro destino.
    - Sincroniza el Fondo de Emergencia si la subcategoría seleccionada es el fondo.
    """
    tx_date = _resolve_tx_date(request.month_key)
    ef_updated = False
    new_ef_balance = None

    try:
        sub = (
            db.query(cat_models.Subcategory)
            .filter(cat_models.Subcategory.id == request.target_subcategory_id)
            .first()
        )
        sub_name = sub.name.lower() if sub else ""

        if "emergencia" in sub_name:
            ef = db.query(ef_models.EmergencyFund).first()
            if ef:
                ef.current_balance += request.amount
                if ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
                    ef.is_completed = True
                ef_updated = True
                new_ef_balance = ef.current_balance

        tx = tx_models.Transaction(
            date=tx_date,
            subcategory_id=request.target_subcategory_id,
            amount=request.amount,
            description="[Pauta] Barrido Cierre de Mes",
        )
        db.add(tx)
        db.commit()

        logger.info(
            "Barrido de fin de mes ejecutado en %s: %.2f € hacia subcategoría %d",
            request.month_key,
            request.amount,
            request.target_subcategory_id,
        )
        return SweepResponse(
            success=True,
            message="Barrido de fin de mes ejecutado exitosamente.",
            amount_swept=request.amount,
            emergency_fund_updated=ef_updated,
            new_emergency_fund_balance=new_ef_balance,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error ejecutando barrido en mes %s: %s",
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno ejecutando barrido de fin de mes: {str(exc)}",
        ) from exc

