from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
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
@router.get("/subcategories/{subcategory_id}/usage", response_model=schemas.SubcategoryUsage)
def check_subcategory_usage(subcategory_id: int, repo: ICategoryRepository = Depends(get_repo)):
    """Comprueba el número de transacciones y presupuestos que dependen de una subcategoría."""
    return repo.check_subcategory_usage(subcategory_id)


@router.put("/subcategories/{subcategory_id}", response_model=schemas.Subcategory)
def update_subcategory(
    subcategory_id: int,
    subcat_update: schemas.SubcategoryUpdate,
    repo: ICategoryRepository = Depends(get_repo)
):
    """Actualiza el nombre de una subcategoría existente."""
    try:
        updated = repo.update_subcategory(subcategory_id, subcat_update.name)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subcategoría {subcategory_id} no encontrada.")
    return updated


@router.delete("/subcategories/{subcategory_id}")
def delete_subcategory(subcategory_id: int, repo: ICategoryRepository = Depends(get_repo)):
    """Elimina una subcategoría si no tiene transacciones ni presupuestos asociados."""
    usage = repo.check_subcategory_usage(subcategory_id)
    if not usage.get("can_delete", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar la subcategoría: tiene {usage.get('transactions_count', 0)} "
                f"transacciones y {usage.get('budgets_count', 0)} presupuestos vinculados."
            ),
        )
    try:
        success = repo.delete_subcategory(subcategory_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subcategoría {subcategory_id} no encontrada.")
    return {"deleted": True, "subcategory_id": subcategory_id}
