from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import categories as cat_models
from backend.domain.models import budgets as pres_models
from backend.domain.schemas.emergency_fund import (
    EmergencyFundResponse,
    EmergencyFundConfigUpdate,
    SafetyStatusResponse,
)
from backend.services.safety_guard import evaluate_safety_status, sync_fund_state
from backend.services.financial_calculator import get_monthly_needs_budget

router = APIRouter(prefix="/advisor", tags=["advisor", "safety-guard"])


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    return SQLiteRepository(db)


def _resolve_monthly_needs(db: Session, mes: Optional[str] = None) -> float:
    """Función auxiliar para calcular el gasto total presupuestado en Necesidades Básicas para un mes o plantilla BASE."""
    # 1. Buscar la categoría de 'Necesidades Básicas'
    cat_nec = (
        db.query(cat_models.Category)
        .filter(cat_models.Category.name.ilike("%necesidades b%"))
        .first()
    )
    if not cat_nec:
        return 0.0

    # 2. Obtener las subcategorías que pertenecen a esta categoría
    subcats = (
        db.query(cat_models.Subcategory)
        .filter(cat_models.Subcategory.category_id == cat_nec.id)
        .all()
    )
    subcat_ids = {s.id for s in subcats}
    if not subcat_ids:
        return 0.0

    # 3. Consultar presupuestos para el mes especificado o recurrir a la plantilla 'BASE'
    target_mes = mes or datetime.date.today().strftime("%Y-%m")
    presupuestos = (
        db.query(pres_models.MonthlyBudget)
        .filter(
            pres_models.MonthlyBudget.month == target_mes,
            pres_models.MonthlyBudget.subcategory_id.in_(subcat_ids),
        )
        .all()
    )

    if not presupuestos and target_mes != "BASE":
        presupuestos = (
            db.query(pres_models.MonthlyBudget)
            .filter(
                pres_models.MonthlyBudget.month == "BASE",
                pres_models.MonthlyBudget.subcategory_id.in_(subcat_ids),
            )
            .all()
        )

    return sum(p.amount for p in presupuestos)


@router.get("/safety-status", response_model=SafetyStatusResponse)
def get_safety_status(
    mes: Optional[str] = Query(None, description="Mes a evaluar en formato YYYY-MM o BASE"),
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
):
    """
    Retorna el diagnóstico integral de la Salvaguarda de Seguridad.
    Compara el saldo acumulado en el fondo de emergencia con las necesidades esenciales presupuestadas.
    """
    fund = repo.get_or_create_emergency_fund()
    monthly_needs = _resolve_monthly_needs(db, mes)

    # Sincroniza y persiste el objetivo y el estado completado del fondo
    fund = sync_fund_state(fund, monthly_needs)
    db.commit()
    db.refresh(fund)

    return evaluate_safety_status(fund, monthly_needs)


@router.get("/emergency-fund", response_model=EmergencyFundResponse)
def get_emergency_fund(repo: IRepository = Depends(get_repo)):
    """Retorna la configuración pura y saldo actual del fondo de emergencia."""
    return repo.get_or_create_emergency_fund()


@router.post("/emergency-fund/config", response_model=SafetyStatusResponse)
def update_emergency_fund_config(
    config: EmergencyFundConfigUpdate,
    mes: Optional[str] = Query(None, description="Mes a evaluar en formato YYYY-MM o BASE"),
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
):
    """
    Actualiza la configuración del fondo de emergencia: meses objetivo (mínimo 3) o ajuste manual de saldo.
    Retorna el diagnóstico actualizado de la salvaguarda (SafetyStatus).
    """
    try:
        fund = repo.update_emergency_fund(
            target_months=config.target_months,
            current_balance=config.current_balance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    monthly_needs = _resolve_monthly_needs(db, mes)
    fund = sync_fund_state(fund, monthly_needs)
    db.commit()
    db.refresh(fund)

    return evaluate_safety_status(fund, monthly_needs)

