"""Esquemas Pydantic v2 para métricas de profiling y latencia de APIs externas.

Define modelos para el registro de llamadas, resúmenes estadísticos con percentiles
y el reporte integral de telemetría de red.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExternalProviderEnum(str, Enum):
    """Proveedores externos integrados en el sistema."""
    YAHOO_FINANCE = "yahoo_finance"
    ECB = "ecb"
    GEMINI = "gemini"
    OTHER = "other"


class LatencyStatusEnum(str, Enum):
    """Clasificación de estado y severidad de la latencia de una llamada."""
    OK = "OK"
    SLOW = "SLOW"
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"


class CallMetricItem(BaseModel):
    """Métrica individual de una llamada saliente a un servicio externo."""
    model_config = ConfigDict(from_attributes=True)

    provider: ExternalProviderEnum
    operation: str
    target: Optional[str] = None
    duration_ms: float
    status: LatencyStatusEnum
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderLatencyStats(BaseModel):
    """Estadísticas agregadas y percentiles de latencia para un proveedor específico."""
    model_config = ConfigDict(from_attributes=True)

    provider: ExternalProviderEnum
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    slow_calls: int = 0
    critical_calls: int = 0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p90_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    last_call_timestamp: Optional[datetime] = None
    thresholds: Dict[str, float] = Field(default_factory=dict)


class LatencyMetricsReport(BaseModel):
    """Informe global consolidado de rendimiento y profiling de APIs externas."""
    model_config = ConfigDict(from_attributes=True)

    uptime_seconds: float = 0.0
    total_calls_recorded: int = 0
    buffer_capacity: int = 1000
    providers: Dict[str, ProviderLatencyStats] = Field(default_factory=dict)
    recent_calls: List[CallMetricItem] = Field(default_factory=list)
