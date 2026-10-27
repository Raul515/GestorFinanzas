"""
Router REST para la gestión de la Lista de Seguimiento Local (Watchlist) en SQLite.
"""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.watchlist import WatchlistCreate, WatchlistResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio de base de datos."""
    return SQLiteRepository(db)


@router.get("", response_model=List[WatchlistResponse])
def get_watchlist(
    repo: IRepository = Depends(get_repo),
) -> List[WatchlistResponse]:
    """
    Retorna la totalidad de activos guardados en la lista de seguimiento local ordenados cronológicamente.
    """
    items = repo.get_watchlist()
    return [WatchlistResponse.model_validate(item) for item in items]


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    item: WatchlistCreate,
    repo: IRepository = Depends(get_repo),
) -> WatchlistResponse:
    """
    Añade un nuevo activo a la lista de seguimiento o actualiza sus notas y precio si ya existía.
    """
    db_item = repo.add_to_watchlist(item)
    return WatchlistResponse.model_validate(db_item)


@router.delete("/{ticker}", response_model=Dict[str, Any])
def remove_from_watchlist(
    ticker: str,
    repo: IRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """
    Elimina un activo de la lista de seguimiento por su símbolo bursátil.
    """
    clean_ticker = ticker.strip().upper()
    deleted = repo.remove_from_watchlist(clean_ticker)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El activo '{clean_ticker}' no se encuentra en la lista de seguimiento.",
        )
    return {"status": "deleted", "ticker": clean_ticker}
