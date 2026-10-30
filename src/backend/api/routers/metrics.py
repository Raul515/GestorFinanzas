"""Router REST para la consulta y gestión de métricas de profiling de APIs externas.

Expone endpoints bajo /metrics para obtener el reporte consolidado de latencia,
estadísticas y percentiles (p50, p90, p95, p99), así como el reseteo del búfer en memoria.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, status

from backend.domain.schemas.latency_metrics import (
    ExternalProviderEnum,
    LatencyMetricsReport,
)
from backend.services.latency_profiler import get_latency_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/latency", response_model=LatencyMetricsReport, status_code=status.HTTP_200_OK)
def get_latency_metrics(
    provider: Optional[ExternalProviderEnum] = Query(
        None,
        description="Filtro opcional por proveedor externo (yahoo_finance, ecb, gemini, other)",
    ),
    limit_recent: int = Query(
        50,
        ge=1,
        le=200,
        description="Número máximo de llamadas recientes a incluir en el reporte (1 a 200)",
    ),
) -> LatencyMetricsReport:
    """Devuelve el reporte consolidado de profiling de latencia y llamadas recientes."""
    tracker = get_latency_tracker()
    return tracker.get_metrics_report(limit_recent=limit_recent, provider=provider)


@router.delete("/latency", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
def reset_latency_metrics() -> Dict[str, Any]:
    """Reinicia el búfer circular en memoria RAM y restablece los contadores de llamadas."""
    tracker = get_latency_tracker()
    tracker.reset()
    logger.info("Búfer circular de métricas de latencia reiniciado por petición de API")
    return {"message": "Búfer de métricas de latencia reiniciado exitosamente"}
