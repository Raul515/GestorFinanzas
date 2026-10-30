"""Servicio de profiling y monitorización de latencia en llamadas a APIs externas.

Implementa un búfer circular en memoria RAM de alta velocidad (thread-safe) para
retener las métricas de red recientes, clasificar severidad según umbrales por proveedor,
calcular percentiles estadísticos y emitir alertas estructuradas en logs/backend.log.
"""

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import functools
import inspect
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from backend.domain.schemas.latency_metrics import (
    CallMetricItem,
    ExternalProviderEnum,
    LatencyMetricsReport,
    LatencyStatusEnum,
    ProviderLatencyStats,
)

logger = logging.getLogger(__name__)

# Umbrales por defecto en milisegundos (ms)
DEFAULT_BUFFER_CAPACITY = 1000

DEFAULT_THRESHOLDS = {
    ExternalProviderEnum.YAHOO_FINANCE.value: {
        "warn": 2000.0,
        "crit": 4000.0,
    },
    ExternalProviderEnum.ECB.value: {
        "warn": 1500.0,
        "crit": 3000.0,
    },
    ExternalProviderEnum.GEMINI.value: {
        "warn": 4000.0,
        "crit": 8000.0,
    },
    ExternalProviderEnum.OTHER.value: {
        "warn": 2000.0,
        "crit": 5000.0,
    },
}


def _load_env_threshold(var_name: str, default_val: float) -> float:
    """Carga un umbral numérico desde las variables de entorno de forma defensiva."""
    val = os.getenv(var_name)
    if val:
        try:
            return float(val)
        except ValueError:
            logger.warning("Variable %s tiene un valor no numérico: %s. Usando default %.1f", var_name, val, default_val)
    return default_val


def calculate_percentiles(durations: List[float]) -> Dict[str, float]:
    """Calcula p50, p90, p95 y p99 de una lista de duraciones mediante interpolación lineal pura."""
    if not durations:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

    sorted_d = sorted(durations)
    n = len(sorted_d)

    def _calc_p(p: float) -> float:
        if n == 1:
            return sorted_d[0]
        k = (n - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, n - 1)
        d = k - f
        return sorted_d[f] + d * (sorted_d[c] - sorted_d[f])

    return {
        "p50": round(_calc_p(50.0), 2),
        "p90": round(_calc_p(90.0), 2),
        "p95": round(_calc_p(95.0), 2),
        "p99": round(_calc_p(99.0), 2),
    }


class LatencyContext:
    """Contexto mutable para enriquecer una llamada medida dentro de un context manager."""

    def __init__(self, target: Optional[str] = None):
        self.target = target
        self.status_code: Optional[int] = None
        self.operation_override: Optional[str] = None


class LatencyTracker:
    """Gestor thread-safe de métricas de red y profiling de latencia con búfer circular."""

    def __init__(self, buffer_capacity: int = DEFAULT_BUFFER_CAPACITY):
        self._buffer_capacity = buffer_capacity
        self._buffer: deque[CallMetricItem] = deque(maxlen=buffer_capacity)
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._total_calls_counter = 0

        # Cargar umbrales desde variables de entorno
        self._thresholds: Dict[str, Dict[str, float]] = {
            ExternalProviderEnum.YAHOO_FINANCE.value: {
                "warn": _load_env_threshold("LATENCY_THRESHOLD_YAHOO_WARN_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.YAHOO_FINANCE.value]["warn"]),
                "crit": _load_env_threshold("LATENCY_THRESHOLD_YAHOO_CRIT_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.YAHOO_FINANCE.value]["crit"]),
            },
            ExternalProviderEnum.ECB.value: {
                "warn": _load_env_threshold("LATENCY_THRESHOLD_ECB_WARN_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.ECB.value]["warn"]),
                "crit": _load_env_threshold("LATENCY_THRESHOLD_ECB_CRIT_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.ECB.value]["crit"]),
            },
            ExternalProviderEnum.GEMINI.value: {
                "warn": _load_env_threshold("LATENCY_THRESHOLD_GEMINI_WARN_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.GEMINI.value]["warn"]),
                "crit": _load_env_threshold("LATENCY_THRESHOLD_GEMINI_CRIT_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.GEMINI.value]["crit"]),
            },
            ExternalProviderEnum.OTHER.value: {
                "warn": _load_env_threshold("LATENCY_THRESHOLD_OTHER_WARN_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.OTHER.value]["warn"]),
                "crit": _load_env_threshold("LATENCY_THRESHOLD_OTHER_CRIT_MS", DEFAULT_THRESHOLDS[ExternalProviderEnum.OTHER.value]["crit"]),
            },
        }

    def get_thresholds(self, provider: Union[ExternalProviderEnum, str]) -> Dict[str, float]:
        """Obtiene los umbrales configurados para un proveedor determinado."""
        prov_key = provider.value if isinstance(provider, ExternalProviderEnum) else str(provider).lower()
        return self._thresholds.get(prov_key, self._thresholds[ExternalProviderEnum.OTHER.value])

    def classify_status(
        self,
        provider: Union[ExternalProviderEnum, str],
        duration_ms: float,
        error_message: Optional[str] = None,
    ) -> LatencyStatusEnum:
        """Determina la clasificación de severidad de la latencia según los umbrales."""
        if error_message is not None:
            return LatencyStatusEnum.ERROR

        thresholds = self.get_thresholds(provider)
        if duration_ms >= thresholds["crit"]:
            return LatencyStatusEnum.CRITICAL
        if duration_ms >= thresholds["warn"]:
            return LatencyStatusEnum.SLOW
        return LatencyStatusEnum.OK

    def record_call(
        self,
        provider: Union[ExternalProviderEnum, str],
        operation: str,
        duration_ms: float,
        target: Optional[str] = None,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        status: Optional[LatencyStatusEnum] = None,
    ) -> CallMetricItem:
        """Registra una llamada a API externa en el búfer circular y emite logs según severidad."""
        # Normalizar proveedor
        if isinstance(provider, str):
            try:
                prov_enum = ExternalProviderEnum(provider.lower())
            except ValueError:
                prov_enum = ExternalProviderEnum.OTHER
        else:
            prov_enum = provider

        resolved_duration = max(0.0, round(float(duration_ms), 2))
        resolved_status = status or self.classify_status(prov_enum, resolved_duration, error_message)

        # Logging estructurado condicional según severidad
        target_display = target or "-"
        thresholds = self.get_thresholds(prov_enum)

        if resolved_status in (LatencyStatusEnum.SLOW, LatencyStatusEnum.CRITICAL):
            logger.warning(
                "EXTERNAL_API_LATENCY_ALERT provider=%s op=%s target=%s duration=%.2fms threshold=%.2fms status=%s",
                prov_enum.value,
                operation,
                target_display,
                resolved_duration,
                thresholds["warn"],
                resolved_status.value,
            )
        elif resolved_status == LatencyStatusEnum.ERROR:
            logger.error(
                "EXTERNAL_API_CALL_ERROR provider=%s op=%s target=%s duration=%.2fms error=%s",
                prov_enum.value,
                operation,
                target_display,
                resolved_duration,
                error_message or "Unknown Error",
            )
        else:
            logger.debug(
                "EXTERNAL_API_CALL_SUCCESS provider=%s op=%s target=%s duration=%.2fms",
                prov_enum.value,
                operation,
                target_display,
                resolved_duration,
            )

        item = CallMetricItem(
            provider=prov_enum,
            operation=operation,
            target=target,
            duration_ms=resolved_duration,
            status=resolved_status,
            status_code=status_code,
            error_message=error_message,
            timestamp=datetime.now(timezone.utc),
        )

        with self._lock:
            self._buffer.append(item)
            self._total_calls_counter += 1

        return item

    def get_metrics_report(
        self,
        limit_recent: int = 50,
        provider: Optional[Union[ExternalProviderEnum, str]] = None,
    ) -> LatencyMetricsReport:
        """Genera el informe global con estadísticas, percentiles y llamadas recientes."""
        target_prov = None
        if provider:
            target_prov = provider.value if isinstance(provider, ExternalProviderEnum) else str(provider).lower()

        with self._lock:
            raw_items = list(self._buffer)
            total_recorded = self._total_calls_counter
            uptime = max(0.0, round(time.time() - self._start_time, 2))

        # Filtrar llamadas para el cálculo si se especificó proveedor
        filtered_items = [
            item for item in raw_items
            if target_prov is None or item.provider.value == target_prov
        ]

        # Agrupar por proveedor
        grouped: Dict[str, List[CallMetricItem]] = {}
        for item in filtered_items:
            grouped.setdefault(item.provider.value, []).append(item)

        # Si se pidió un proveedor específico que aún no tiene llamadas, inicializar entrada vacía
        if target_prov and target_prov not in grouped:
            grouped[target_prov] = []

        providers_stats: Dict[str, ProviderLatencyStats] = {}
        for prov_key, items in grouped.items():
            try:
                p_enum = ExternalProviderEnum(prov_key)
            except ValueError:
                p_enum = ExternalProviderEnum.OTHER

            durations = [it.duration_ms for it in items]
            percentiles = calculate_percentiles(durations)
            total_c = len(items)
            failed_c = sum(1 for it in items if it.status == LatencyStatusEnum.ERROR)
            slow_c = sum(1 for it in items if it.status == LatencyStatusEnum.SLOW)
            crit_c = sum(1 for it in items if it.status == LatencyStatusEnum.CRITICAL)
            success_c = total_c - failed_c
            avg_d = round(sum(durations) / total_c, 2) if total_c > 0 else 0.0
            min_d = round(min(durations), 2) if total_c > 0 else 0.0
            max_d = round(max(durations), 2) if total_c > 0 else 0.0
            last_ts = items[-1].timestamp if total_c > 0 else None

            providers_stats[prov_key] = ProviderLatencyStats(
                provider=p_enum,
                total_calls=total_c,
                successful_calls=success_c,
                failed_calls=failed_c,
                slow_calls=slow_c,
                critical_calls=crit_c,
                avg_duration_ms=avg_d,
                min_duration_ms=min_d,
                max_duration_ms=max_d,
                p50_duration_ms=percentiles["p50"],
                p90_duration_ms=percentiles["p90"],
                p95_duration_ms=percentiles["p95"],
                p99_duration_ms=percentiles["p99"],
                last_call_timestamp=last_ts,
                thresholds=self.get_thresholds(p_enum),
            )

        # Obtener las llamadas más recientes (ordenadas de más reciente a más antigua)
        clamped_limit = max(1, min(limit_recent, 200))
        recent_slice = list(reversed(filtered_items))[:clamped_limit]

        return LatencyMetricsReport(
            uptime_seconds=uptime,
            total_calls_recorded=total_recorded,
            buffer_capacity=self._buffer_capacity,
            providers=providers_stats,
            recent_calls=recent_slice,
        )

    def reset(self) -> None:
        """Vacía el búfer de métricas y reinicia los contadores de forma atómica."""
        with self._lock:
            self._buffer.clear()
            self._total_calls_counter = 0
            self._start_time = time.time()


# Singleton del gestor de latencia
_TRACKER_INSTANCE: Optional[LatencyTracker] = None
_TRACKER_LOCK = threading.Lock()


def get_latency_tracker() -> LatencyTracker:
    """Devuelve la instancia global (singleton) de LatencyTracker."""
    global _TRACKER_INSTANCE
    if _TRACKER_INSTANCE is None:
        with _TRACKER_LOCK:
            if _TRACKER_INSTANCE is None:
                _TRACKER_INSTANCE = LatencyTracker()
    return _TRACKER_INSTANCE


def reset_latency_tracker() -> None:
    """Reinicia el singleton del gestor de latencia (útil para pruebas y reinicios)."""
    tracker = get_latency_tracker()
    tracker.reset()


@contextmanager
def track_external_latency(
    provider: Union[ExternalProviderEnum, str],
    operation: str,
    target: Optional[str] = None,
):
    """Context manager para instrumentar de forma precisa y failsafe la duración de una llamada de red.

    Uso:
        with track_external_latency(ExternalProviderEnum.YAHOO_FINANCE, "fetch_ticker", target="AAPL") as ctx:
            data = yf.Ticker("AAPL").history(...)
            ctx.status_code = 200
    """
    ctx = LatencyContext(target=target)
    start_time = time.perf_counter()
    err_msg: Optional[str] = None

    try:
        yield ctx
    except Exception as exc:
        err_msg = str(exc)
        raise
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        try:
            tracker = get_latency_tracker()
            op = ctx.operation_override or operation
            tgt = ctx.target
            sc = ctx.status_code
            tracker.record_call(
                provider=provider,
                operation=op,
                duration_ms=duration_ms,
                target=tgt,
                status_code=sc,
                error_message=err_msg,
            )
        except Exception as track_err:
            logger.debug("Fallo interno en track_external_latency ignorado defensivamente: %s", track_err)


def profile_external_call(
    provider: Union[ExternalProviderEnum, str],
    operation: str,
    target_extractor: Optional[Callable[..., Optional[str]]] = None,
):
    """Decorador síncrono y asíncrono para envolver funciones que ejecutan llamadas a APIs externas.

    Uso:
        @profile_external_call(ExternalProviderEnum.YAHOO_FINANCE, "get_info", target_extractor=lambda ticker, *a, **k: ticker)
        def fetch_ticker_info(ticker: str):
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                extracted_target = None
                if target_extractor:
                    try:
                        extracted_target = target_extractor(*args, **kwargs)
                    except Exception as ext_err:
                        logger.debug("Fallo al extraer target en decorador: %s", ext_err)

                with track_external_latency(provider, operation, target=extracted_target):
                    return await func(*args, **kwargs)

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                extracted_target = None
                if target_extractor:
                    try:
                        extracted_target = target_extractor(*args, **kwargs)
                    except Exception as ext_err:
                        logger.debug("Fallo al extraer target en decorador: %s", ext_err)

                with track_external_latency(provider, operation, target=extracted_target):
                    return func(*args, **kwargs)

            return sync_wrapper

    return decorator
