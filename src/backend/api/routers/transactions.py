from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.domain.schemas import transactions as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import ITransactionRepository

router = APIRouter(prefix="/transactions", tags=["transactions"])


def get_repo(db: Session = Depends(get_db)) -> ITransactionRepository:
    return SQLiteRepository(db)


@router.get("/", response_model=List[schemas.Transaction])
def read_transactions(month: Optional[str] = None, repo: ITransactionRepository = Depends(get_repo)):
    """Obtiene el listado de transacciones, filtrando opcionalmente por mes (YYYY-MM)."""
    return repo.get_transactions(month)


@router.post("/", response_model=schemas.Transaction)
def create_transaction(transaction: schemas.TransactionCreate, repo: ITransactionRepository = Depends(get_repo)):
    """Registra una nueva transacción y sincroniza automáticamente el fondo de emergencia si corresponde."""
    return repo.create_transaction(transaction)

