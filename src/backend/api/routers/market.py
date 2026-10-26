import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.market import (
    MacroOverviewResponse,
    MarketNewsResponse,
    MarketRefreshResponse,
)
from backend.services.market_data import get_macro_overview_response
from backend.services.llm_news_analyst import get_analyzed_market_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])

CACHE_KEY_INDICATORS = "macro_indicators"
CACHE_KEY_NEWS = "macro_news"
DEFAULT_TTL_HOURS = 24


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio de datos y caché."""
    return SQLiteRepository(db)


@router.get("/macro-indicators", response_model=MacroOverviewResponse)
def get_macro_indicators(
    repo: IRepository = Depends(get_repo),
) -> MacroOverviewResponse:
    """
    Retorna el resumen de indicadores macroeconómicos y deuda soberana (IBEX 35, EuroStoxx, Bonos, Prima de Riesgo).
    Utiliza una política de caché persistente de 24 horas en SQLite.
    """
    cached_data = repo.get_market_cache(CACHE_KEY_INDICATORS)
    if cached_data:
        try:
            cached_data["is_cached"] = True
            return MacroOverviewResponse(**cached_data)
        except Exception as e:
            logger.warning(f"Error deserializando caché de '{CACHE_KEY_INDICATORS}': {e}. Regenerando datos.")

    fresh_overview = get_macro_overview_response(is_cached=False)
    repo.set_market_cache(
        key=CACHE_KEY_INDICATORS,
        data=fresh_overview.model_dump(mode="json"),
        ttl_hours=DEFAULT_TTL_HOURS,
    )
    return fresh_overview


@router.get("/news", response_model=MarketNewsResponse)
def get_market_news(
    limit: int = Query(15, ge=1, le=50, description="Cantidad máxima de noticias a recuperar"),
    repo: IRepository = Depends(get_repo),
) -> MarketNewsResponse:
    """
    Retorna las noticias financieras más recientes con análisis de IA (impacto, temática contextual y síntesis).
    Aplica caché de 24 horas y degradación elegante si no hay conexión o cuota de IA disponible.
    """
    cached_data = repo.get_market_cache(CACHE_KEY_NEWS)
    if cached_data:
        try:
            cached_data["is_cached"] = True
            return MarketNewsResponse(**cached_data)
        except Exception as e:
            logger.warning(f"Error deserializando caché de '{CACHE_KEY_NEWS}': {e}. Regenerando datos.")

    fresh_news = get_analyzed_market_news(limit=limit)
    repo.set_market_cache(
        key=CACHE_KEY_NEWS,
        data=fresh_news.model_dump(mode="json"),
        ttl_hours=DEFAULT_TTL_HOURS,
    )
    return fresh_news


@router.post("/refresh", response_model=MarketRefreshResponse)
def refresh_market_radar(
    repo: IRepository = Depends(get_repo),
) -> MarketRefreshResponse:
    """
    Fuerza la actualización manual del Radar: invalida la caché de indicadores y noticias,
    consulta nuevamente los proveedores externos e IA, y persiste una nueva instantánea de 24 horas.
    """
    # 1. Invalidar entradas en caché
    repo.invalidate_market_cache(CACHE_KEY_INDICATORS)
    repo.invalidate_market_cache(CACHE_KEY_NEWS)

    # 2. Obtener datos macroeconómicos frescos
    fresh_indicators = get_macro_overview_response(is_cached=False)
    repo.set_market_cache(
        key=CACHE_KEY_INDICATORS,
        data=fresh_indicators.model_dump(mode="json"),
        ttl_hours=DEFAULT_TTL_HOURS,
    )

    # 3. Obtener noticias y análisis de IA frescos
    fresh_news = get_analyzed_market_news(limit=15)
    repo.set_market_cache(
        key=CACHE_KEY_NEWS,
        data=fresh_news.model_dump(mode="json"),
        ttl_hours=DEFAULT_TTL_HOURS,
    )

    return MarketRefreshResponse(
        message="Radar de mercado y noticias actualizado con éxito",
        macro_indicators=fresh_indicators,
        news=fresh_news,
    )
