from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.domain.schemas import transacciones as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository

router = APIRouter(prefix="/transacciones", tags=["transacciones"])

def get_repo(db: Session = Depends(get_db)):
    return SQLiteRepository(db)

@router.get("/", response_model=List[schemas.Transaccion])
def read_transacciones(mes: Optional[str] = None, repo: SQLiteRepository = Depends(get_repo)):
    return repo.get_transacciones(mes)

@router.post("/", response_model=schemas.Transaccion)
def create_transaccion(transaccion: schemas.TransaccionCreate, repo: SQLiteRepository = Depends(get_repo)):
    return repo.create_transaccion(transaccion)
