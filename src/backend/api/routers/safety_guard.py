from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.emergency_fund import (
    EmergencyFundResponse,
    EmergencyFundConfigUpdate,
    SafetyStatusResponse,
)
from backend.services.safety_guard import (
    evaluate_safety_status,
    resolve_monthly_needs as _resolve_monthly_needs,
    sync_fund_state,
)

router = APIRouter(prefix="/advisor", tags=["advisor", "safety-guard"])


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    return SQLiteRepository(db)


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

