from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.domain.schemas import categories as schemas
from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import ICategoryRepository

router = APIRouter(prefix="/categories", tags=["categories"])


def get_repo(db: Session = Depends(get_db)) -> ICategoryRepository:
    return SQLiteRepository(db)


@router.get("/", response_model=List[schemas.Category])
def read_categories(repo: ICategoryRepository = Depends(get_repo)):
    """Obtiene el listado completo de categorías contables con sus subcategorías asociadas."""
    return repo.get_categories()


@router.post("/", response_model=schemas.Category)
def create_category(category: schemas.CategoryCreate, repo: ICategoryRepository = Depends(get_repo)):
    """Crea una nueva categoría principal (ingreso, gasto o ahorro)."""
    return repo.create_category(category)


@router.get("/subcategories/", response_model=List[schemas.Subcategory])
def read_subcategories(category_id: Optional[int] = None, repo: ICategoryRepository = Depends(get_repo)):
    """Obtiene subcategorías, permitiendo filtrar opcionalmente por identificador de categoría."""
    return repo.get_subcategories(category_id)


@router.post("/subcategories/", response_model=schemas.Subcategory)
def create_subcategory(subcategory: schemas.SubcategoryCreate, repo: ICategoryRepository = Depends(get_repo)):
    """Crea una nueva subcategoría asignada a una categoría existente."""
    return repo.create_subcategory(subcategory)

