from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.domain.schemas import budgets as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IBudgetRepository

router = APIRouter(prefix="/budgets", tags=["budgets"])


def get_repo(db: Session = Depends(get_db)) -> IBudgetRepository:
    return SQLiteRepository(db)


@router.get("/{month}", response_model=List[schemas.MonthlyBudget])
def read_budgets(month: str, repo: IBudgetRepository = Depends(get_repo)):
    """Obtiene los presupuestos para el mes especificado o la plantilla BASE."""
    return repo.get_budgets(month)


@router.post("/", response_model=schemas.MonthlyBudget)
def create_budget(budget: schemas.MonthlyBudgetCreate, repo: IBudgetRepository = Depends(get_repo)):
    """Crea o actualiza una asignación presupuestaria individual."""
    return repo.create_budget(budget)


@router.post("/bulk", response_model=List[schemas.MonthlyBudget])
def create_budgets_bulk(budgets: List[schemas.MonthlyBudgetCreate], repo: IBudgetRepository = Depends(get_repo)):
    """Guarda o actualiza un lote masivo de presupuestos mensuales."""
    return repo.save_budgets_bulk(budgets)

