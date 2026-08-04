from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.domain.schemas import presupuestos as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository

router = APIRouter(prefix="/presupuestos", tags=["presupuestos"])

def get_repo(db: Session = Depends(get_db)):
    return SQLiteRepository(db)

@router.get("/{mes}", response_model=List[schemas.PresupuestoMensual])
def read_presupuestos(mes: str, repo: SQLiteRepository = Depends(get_repo)):
    return repo.get_presupuestos(mes)

@router.post("/", response_model=schemas.PresupuestoMensual)
def create_presupuesto(presupuesto: schemas.PresupuestoMensualCreate, repo: SQLiteRepository = Depends(get_repo)):
    return repo.create_presupuesto(presupuesto)
