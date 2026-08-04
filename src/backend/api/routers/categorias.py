from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.domain.schemas import categorias as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import ICategoriaRepository

router = APIRouter(prefix="/categorias", tags=["categorias"])

def get_repo(db: Session = Depends(get_db)) -> ICategoriaRepository:
    return SQLiteRepository(db)

@router.get("/", response_model=List[schemas.Categoria])
def read_categorias(repo: ICategoriaRepository = Depends(get_repo)):
    return repo.get_categorias()

@router.post("/", response_model=schemas.Categoria)
def create_categoria(categoria: schemas.CategoriaCreate, repo: ICategoriaRepository = Depends(get_repo)):
    return repo.create_categoria(categoria)

@router.get("/subcategorias/", response_model=List[schemas.Subcategoria])
def read_subcategorias(categoria_id: Optional[int] = None, repo: ICategoriaRepository = Depends(get_repo)):
    return repo.get_subcategorias(categoria_id)

@router.post("/subcategorias/", response_model=schemas.Subcategoria)
def create_subcategoria(subcategoria: schemas.SubcategoriaCreate, repo: ICategoriaRepository = Depends(get_repo)):
    return repo.create_subcategoria(subcategoria)

