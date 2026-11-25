"""Helper reutilizable para el patrón cache-aside en SQLite (Spec 017 - Fase 3)."""

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from backend.database.interfaz.db_interface import IRepository

logger = logging.getLogger(__name__)


def get_or_compute_cached(
    repo: IRepository,
    *,
    cache_key: str,
    ttl_hours: int,
    compute_fn: Callable[[], Dict[str, Any]],
    validate_cached_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    should_cache_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Recupera datos desde market_cache si son válidos; en caso contrario ejecuta compute_fn
    y persiste el resultado si should_cache_fn lo permite.
    Devuelve (payload_dict, from_cache).
    """
    cached_data = repo.get_market_cache(cache_key)
    if cached_data:
        try:
            if validate_cached_fn is None or validate_cached_fn(cached_data):
                return cached_data, True
        except Exception as exc:
            logger.warning("Error validando caché para '%s': %s. Regenerando datos.", cache_key, exc)

    fresh_data = compute_fn()
    if should_cache_fn is None or should_cache_fn(fresh_data):
        try:
            repo.set_market_cache(
                key=cache_key,
                data=fresh_data,
                ttl_hours=ttl_hours,
            )
        except Exception as exc:
            logger.warning("Fallo al persistir en caché SQLite para '%s': %s", cache_key, exc)

    return fresh_data, False
