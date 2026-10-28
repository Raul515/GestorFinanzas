"""
Router REST para el Análisis Fundamental en Profundidad (Deep Dive) con caché de 24 horas en SQLite.
"""

import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.deepdive import DeepDiveResponse
from backend.services.equity_deepdive import get_equity_deepdive_data
from backend.services.llm_quality_value_analyst import analyze_quality_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deepdive", tags=["deepdive"])

CACHE_KEY_PREFIX = "deepdive_"
DEFAULT_CACHE_TTL_DAYS = int(os.getenv("DEEPDIVE_CACHE_TTL_DAYS", "14"))
DEFAULT_TTL_HOURS = DEFAULT_CACHE_TTL_DAYS * 24


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio desacoplado de base de datos y caché."""
    return SQLiteRepository(db)


@router.get("/{ticker}", response_model=DeepDiveResponse)
def get_deepdive_analysis(
    ticker: str,
    repo: IRepository = Depends(get_repo),
) -> DeepDiveResponse:
    """
    Retorna el diagnóstico contable en profundidad de una empresa cotizada bajo metodología Quality Value.
    Aplica política de caché de 24 horas en SQLite; si los datos no existen o expiraron, extrae la información
    contable, evalúa el Piotroski Score, genera la síntesis agéntica y persiste el resultado.
    """
    clean_ticker = ticker.strip().upper()
    cache_key = f"{CACHE_KEY_PREFIX}{clean_ticker}"

    cached_data = repo.get_market_cache(cache_key)
    if cached_data:
        try:
            response = DeepDiveResponse.model_validate(cached_data)
            response.from_cache = True
            return response
        except Exception as exc:
            logger.warning(
                "Error deserializando análisis en caché para '%s': %s. Regenerando datos.",
                clean_ticker,
                exc,
            )

    # Extracción contable cuantitativa
    deepdive_data = get_equity_deepdive_data(clean_ticker)
    if not deepdive_data:
        raise HTTPException(
            status_code=404,
            detail=f"No se pudieron encontrar o extraer datos financieros para el símbolo bursátil '{clean_ticker}'.",
        )

    # Generación de tesis agéntica Quality Value
    report = analyze_quality_value(deepdive_data)
    deepdive_data.quality_value_report = report
    deepdive_data.from_cache = False
    deepdive_data.updated_at = datetime.now(timezone.utc)

    # Persistencia en caché de 24 horas
    try:
        repo.set_market_cache(
            key=cache_key,
            data=deepdive_data.model_dump(mode="json"),
            ttl_hours=DEFAULT_TTL_HOURS,
        )
    except Exception as exc:
        logger.warning("Fallo al persistir en caché SQLite para '%s': %s", cache_key, exc)

    return deepdive_data


@router.post("/refresh/{ticker}", response_model=DeepDiveResponse)
def refresh_deepdive_analysis(
    ticker: str,
    repo: IRepository = Depends(get_repo),
) -> DeepDiveResponse:
    """
    Fuerza la invalidación de la caché local para el ticker solicitado y regenera íntegramente
    el análisis cuantitativo y la tesis agéntica Quality Value.
    """
    clean_ticker = ticker.strip().upper()
    cache_key = f"{CACHE_KEY_PREFIX}{clean_ticker}"

    # Invalidar caché previa
    repo.invalidate_market_cache(cache_key)

    # Recomputar análisis
    deepdive_data = get_equity_deepdive_data(clean_ticker)
    if not deepdive_data:
        raise HTTPException(
            status_code=404,
            detail=f"No se pudieron refrescar los datos financieros para el símbolo bursátil '{clean_ticker}'.",
        )

    report = analyze_quality_value(deepdive_data)
    deepdive_data.quality_value_report = report
    deepdive_data.from_cache = False
    deepdive_data.updated_at = datetime.now(timezone.utc)

    # Persistir datos frescos en caché
    try:
        repo.set_market_cache(
            key=cache_key,
            data=deepdive_data.model_dump(mode="json"),
            ttl_hours=DEFAULT_TTL_HOURS,
        )
    except Exception as exc:
        logger.warning("Fallo al actualizar caché SQLite para '%s': %s", cache_key, exc)

    return deepdive_data
