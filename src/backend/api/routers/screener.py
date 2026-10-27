import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.screener import (
    CustomScreenerRequest,
    ETFScreenerItem,
    ScreenerFilterParams,
    ScreenerItem,
    ScreenerPresetEnum,
    ScreenerResponse,
    StockScreenerItem,
    UniverseInfo,
)
from backend.services.screener_service import (
    UNIVERSES_METADATA,
    apply_screener_filters,
    fetch_custom_tickers,
    fetch_universe_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screener", tags=["screener"])

CACHE_KEY_PREFIX = "screener_"
DEFAULT_TTL_HOURS = 24


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio de base de datos y caché."""
    return SQLiteRepository(db)


def _reconstitute_screener_items(raw_items: List[dict]) -> List[ScreenerItem]:
    """Reconstruye instancias tipadas de StockScreenerItem o ETFScreenerItem a partir de diccionarios en caché."""
    items: List[ScreenerItem] = []
    for raw in raw_items:
        try:
            if raw.get("asset_type") == "etf":
                items.append(ETFScreenerItem(**raw))
            else:
                items.append(StockScreenerItem(**raw))
        except Exception as exc:
            logger.warning("Fallo al deserializar item de screener desde caché: %s (error: %s)", raw.get("ticker"), exc)
    return items


@router.get("/universes", response_model=List[UniverseInfo])
def get_universes() -> List[UniverseInfo]:
    """
    Retorna la lista de universos predefinidos disponibles con su descripción y tipo de activo.
    """
    return list(UNIVERSES_METADATA.values())


@router.get("/universe/{universe_id}", response_model=ScreenerResponse)
def get_universe_screener(
    universe_id: str,
    preset: Optional[ScreenerPresetEnum] = Query(None, description="Estrategia rápida predefinida"),
    max_pe: Optional[float] = Query(None, description="PER máximo"),
    min_dividend_yield: Optional[float] = Query(None, description="Rentabilidad por dividendo mínima (%)"),
    min_roe: Optional[float] = Query(None, description="ROE mínimo (%)"),
    max_debt_to_equity: Optional[float] = Query(None, description="Ratio Deuda/Patrimonio máximo (%)"),
    max_expense_ratio: Optional[float] = Query(None, description="TER máximo para ETFs (%)"),
    search_query: Optional[str] = Query(None, description="Búsqueda por ticker, nombre o sector"),
    repo: IRepository = Depends(get_repo),
) -> ScreenerResponse:
    """
    Retorna los datos cuantitativos y fundamentales del universo solicitado.
    Aplica política de caché de 24 horas en SQLite y filtra los resultados en memoria según los parámetros recibidos.
    """
    clean_id = universe_id.strip().lower()
    if clean_id not in UNIVERSES_METADATA or clean_id == "custom":
        raise HTTPException(
            status_code=404,
            detail=f"Universo '{universe_id}' no encontrado. Universos válidos: {list(UNIVERSES_METADATA.keys())}",
        )

    cache_key = f"{CACHE_KEY_PREFIX}{clean_id}"
    cached_data = repo.get_market_cache(cache_key)

    items: List[ScreenerItem] = []
    from_cache = False
    updated_at: datetime = datetime.now(timezone.utc)

    if cached_data and "items" in cached_data:
        try:
            items = _reconstitute_screener_items(cached_data.get("items", []))
            from_cache = True
            raw_updated = cached_data.get("updated_at")
            if raw_updated:
                updated_at = datetime.fromisoformat(raw_updated)
            else:
                updated_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.warning("Error deserializando caché para '%s': %s. Regenerando datos.", cache_key, exc)
            items = []

    if not from_cache or not items:
        items = fetch_universe_data(clean_id)
        updated_at = datetime.now(timezone.utc)
        from_cache = False
        repo.set_market_cache(
            key=cache_key,
            data={
                "items": [item.model_dump(mode="json") for item in items],
                "updated_at": updated_at.isoformat(),
            },
            ttl_hours=DEFAULT_TTL_HOURS,
        )

    filter_params = ScreenerFilterParams(
        preset=preset,
        max_pe=max_pe,
        min_dividend_yield=min_dividend_yield,
        min_roe=min_roe,
        max_debt_to_equity=max_debt_to_equity,
        max_expense_ratio=max_expense_ratio,
        search_query=search_query,
    )

    filtered_items = apply_screener_filters(items, filter_params)

    return ScreenerResponse(
        universe=clean_id,
        asset_type=UNIVERSES_METADATA[clean_id].asset_type,
        updated_at=updated_at,
        from_cache=from_cache,
        total_count=len(items),
        filtered_count=len(filtered_items),
        items=filtered_items,
    )


@router.post("/custom", response_model=ScreenerResponse)
def get_custom_screener(
    request: CustomScreenerRequest,
) -> ScreenerResponse:
    """
    Evalúa una lista arbitraria de tickers personalizada (máximo 50 tickers)
    autodetectando acciones y ETFs, y aplicando los filtros solicitados.
    """
    items = fetch_custom_tickers(request.tickers)
    filtered_items = apply_screener_filters(items, request.filter_params)
    now = datetime.now(timezone.utc)

    return ScreenerResponse(
        universe="custom",
        asset_type="mixed",
        updated_at=now,
        from_cache=False,
        total_count=len(items),
        filtered_count=len(filtered_items),
        items=filtered_items,
    )


@router.post("/refresh/{universe_id}", response_model=ScreenerResponse)
def refresh_universe_screener(
    universe_id: str,
    repo: IRepository = Depends(get_repo),
) -> ScreenerResponse:
    """
    Fuerza la invalidación de la caché de un universo en SQLite, descarga los datos
    actualizados desde Yahoo Finance y persiste una nueva instantánea de 24 horas.
    """
    clean_id = universe_id.strip().lower()
    if clean_id not in UNIVERSES_METADATA or clean_id == "custom":
        raise HTTPException(
            status_code=404,
            detail=f"Universo '{universe_id}' no encontrado. Universos válidos: {list(UNIVERSES_METADATA.keys())}",
        )

    cache_key = f"{CACHE_KEY_PREFIX}{clean_id}"
    repo.invalidate_market_cache(cache_key)

    items = fetch_universe_data(clean_id)
    updated_at = datetime.now(timezone.utc)

    repo.set_market_cache(
        key=cache_key,
        data={
            "items": [item.model_dump(mode="json") for item in items],
            "updated_at": updated_at.isoformat(),
        },
        ttl_hours=DEFAULT_TTL_HOURS,
    )

    return ScreenerResponse(
        universe=clean_id,
        asset_type=UNIVERSES_METADATA[clean_id].asset_type,
        updated_at=updated_at,
        from_cache=False,
        total_count=len(items),
        filtered_count=len(items),
        items=items,
        notes="Universo actualizado correctamente desde fuentes externas",
    )
