from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import categorias as cat_models
from backend.domain.models import presupuestos as pres_models
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
    """Helper to calculate total budgeted basic needs for a given month or fallback to BASE."""
    # 1. Find category for 'Necesidades Básicas'
    cat_nec = (
        db.query(cat_models.Categoria)
        .filter(cat_models.Categoria.nombre.ilike("%necesidades b%"))
        .first()
    )
    if not cat_nec:
        return 0.0

    # 2. Get subcategories belonging to this category
    subcats = (
        db.query(cat_models.Subcategoria)
        .filter(cat_models.Subcategoria.categoria_id == cat_nec.id)
        .all()
    )
    subcat_ids = {s.id for s in subcats}
    if not subcat_ids:
        return 0.0

    # 3. Query budgets for specified month, or fallback to 'BASE'
    target_mes = mes or datetime.date.today().strftime("%Y-%m")
    presupuestos = (
        db.query(pres_models.PresupuestoMensual)
        .filter(
            pres_models.PresupuestoMensual.mes == target_mes,
            pres_models.PresupuestoMensual.subcategoria_id.in_(subcat_ids),
        )
        .all()
    )

    if not presupuestos and target_mes != "BASE":
        presupuestos = (
            db.query(pres_models.PresupuestoMensual)
            .filter(
                pres_models.PresupuestoMensual.mes == "BASE",
                pres_models.PresupuestoMensual.subcategoria_id.in_(subcat_ids),
            )
            .all()
        )

    return sum(p.cantidad for p in presupuestos)


@router.get("/safety-status", response_model=SafetyStatusResponse)
def get_safety_status(
    mes: Optional[str] = Query(None, description="Mes a evaluar en formato YYYY-MM o BASE"),
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
):
    """
    Returns the comprehensive Safety Guard diagnosis.
    Compares the current emergency fund balance against the budgeted essential needs.
    """
    fund = repo.get_or_create_emergency_fund()
    monthly_needs = _resolve_monthly_needs(db, mes)

    # Sync and persist target_amount and is_completed state
    fund = sync_fund_state(fund, monthly_needs)
    db.commit()
    db.refresh(fund)

    return evaluate_safety_status(fund, monthly_needs)


@router.get("/emergency-fund", response_model=EmergencyFundResponse)
def get_emergency_fund(repo: IRepository = Depends(get_repo)):
    """Returns the raw emergency fund configuration and current balance."""
    return repo.get_or_create_emergency_fund()


@router.post("/emergency-fund/config", response_model=SafetyStatusResponse)
def update_emergency_fund_config(
    config: EmergencyFundConfigUpdate,
    mes: Optional[str] = Query(None, description="Mes a evaluar en formato YYYY-MM o BASE"),
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
):
    """
    Updates the emergency fund configuration: target months (min 3) or manual balance adjustment.
    Returns the refreshed SafetyStatus diagnosis.
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
