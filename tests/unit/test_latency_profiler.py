"""Pruebas unitarias para el motor de profiling de latencia y búfer circular (Spec 009)."""

import asyncio
import logging
import time
import pytest

from backend.domain.schemas.latency_metrics import (
    CallMetricItem,
    ExternalProviderEnum,
    LatencyStatusEnum,
)
from backend.services.latency_profiler import (
    DEFAULT_BUFFER_CAPACITY,
    LatencyTracker,
    calculate_percentiles,
    get_latency_tracker,
    profile_external_call,
    reset_latency_tracker,
    track_external_latency,
)


def test_calculate_percentiles_empty():
    """Verifica que calcular percentiles sobre una lista vacía retorne ceros de forma segura."""
    result = calculate_percentiles([])
    assert result == {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}


def test_calculate_percentiles_single_element():
    """Verifica el cálculo de percentiles con un único elemento."""
    result = calculate_percentiles([150.0])
    assert result == {"p50": 150.0, "p90": 150.0, "p95": 150.0, "p99": 150.0}


def test_calculate_percentiles_multi_element():
    """Verifica la interpolación lineal determinista sobre un rango conocido."""
    # 10 valores: 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
    data = [float(x) for x in range(10, 110, 10)]
    result = calculate_percentiles(data)
    assert result["p50"] == 55.0  # Mediana entre 50 y 60
    assert result["p90"] == 91.0
    assert result["p95"] == 95.5
    assert result["p99"] == 99.1


def test_latency_tracker_buffer_capacity_fifo():
    """Verifica que el búfer circular respete la capacidad máxima y descarte según FIFO."""
    small_capacity = 5
    tracker = LatencyTracker(buffer_capacity=small_capacity)

    for i in range(8):
        tracker.record_call(
            provider=ExternalProviderEnum.YAHOO_FINANCE,
            operation="test_op",
            duration_ms=100.0 + i,
            target=f"TICKER_{i}",
        )

    report = tracker.get_metrics_report(limit_recent=10)
    assert report.total_calls_recorded == 8
    # El búfer solo debe contener las últimas 5 llamadas
    assert len(report.recent_calls) == small_capacity
    # La llamada más reciente debe ser TICKER_7 y la más antigua en el búfer TICKER_3
    assert report.recent_calls[0].target == "TICKER_7"
    assert report.recent_calls[-1].target == "TICKER_3"


def test_latency_tracker_classification_and_logging(caplog):
    """Verifica la clasificación por severidad (OK, SLOW, CRITICAL, ERROR) y avisos a log."""
    tracker = LatencyTracker()

    with caplog.at_level(logging.DEBUG):
        # 1. Llamada OK (Yahoo warn es 2000ms)
        item_ok = tracker.record_call(
            provider=ExternalProviderEnum.YAHOO_FINANCE,
            operation="history",
            duration_ms=350.0,
            target="AAPL",
        )
        assert item_ok.status == LatencyStatusEnum.OK

        # 2. Llamada SLOW (duración >= 2000 y < 4000)
        item_slow = tracker.record_call(
            provider=ExternalProviderEnum.YAHOO_FINANCE,
            operation="history",
            duration_ms=2500.0,
            target="MSFT",
        )
        assert item_slow.status == LatencyStatusEnum.SLOW
        assert "EXTERNAL_API_LATENCY_ALERT" in caplog.text
        assert "status=SLOW" in caplog.text

        # 3. Llamada CRITICAL (duración >= 4000)
        item_crit = tracker.record_call(
            provider=ExternalProviderEnum.YAHOO_FINANCE,
            operation="history",
            duration_ms=4500.0,
            target="GOOGL",
        )
        assert item_crit.status == LatencyStatusEnum.CRITICAL
        assert "status=CRITICAL" in caplog.text

        # 4. Llamada ERROR
        item_err = tracker.record_call(
            provider=ExternalProviderEnum.ECB,
            operation="yield_curve",
            duration_ms=500.0,
            target="bund_10y",
            error_message="Connection timed out",
        )
        assert item_err.status == LatencyStatusEnum.ERROR
        assert "EXTERNAL_API_CALL_ERROR" in caplog.text
        assert "Connection timed out" in caplog.text


def test_latency_tracker_report_stats_and_filtering():
    """Verifica el cálculo de estadísticas agrupadas y el filtrado por proveedor."""
    tracker = LatencyTracker()

    # Inyectar 3 llamadas de Yahoo y 2 de BCE
    tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "op1", 100.0)
    tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "op2", 200.0)
    tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "op3", 300.0)

    tracker.record_call(ExternalProviderEnum.ECB, "ecb_op", 50.0)
    tracker.record_call(ExternalProviderEnum.ECB, "ecb_op", 150.0, error_message="HTTP 500")

    # Reporte global
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 5
    assert len(report.providers) == 2

    yahoo_stats = report.providers["yahoo_finance"]
    assert yahoo_stats.total_calls == 3
    assert yahoo_stats.successful_calls == 3
    assert yahoo_stats.failed_calls == 0
    assert yahoo_stats.avg_duration_ms == 200.0
    assert yahoo_stats.min_duration_ms == 100.0
    assert yahoo_stats.max_duration_ms == 300.0

    ecb_stats = report.providers["ecb"]
    assert ecb_stats.total_calls == 2
    assert ecb_stats.successful_calls == 1
    assert ecb_stats.failed_calls == 1

    # Reporte con filtro por proveedor
    filtered_report = tracker.get_metrics_report(provider=ExternalProviderEnum.YAHOO_FINANCE)
    assert len(filtered_report.providers) == 1
    assert "yahoo_finance" in filtered_report.providers
    assert all(it.provider == ExternalProviderEnum.YAHOO_FINANCE for it in filtered_report.recent_calls)


def test_track_external_latency_context_manager_success():
    """Verifica que el context manager registre con éxito duración, target y status_code."""
    reset_latency_tracker()

    with track_external_latency(ExternalProviderEnum.GEMINI, "generate_content", target="gemini-3.5-flash-lite") as ctx:
        time.sleep(0.01)  # Simular 10ms
        ctx.status_code = 200

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.GEMINI
    assert call.operation == "generate_content"
    assert call.target == "gemini-3.5-flash-lite"
    assert call.duration_ms >= 10.0
    assert call.status_code == 200
    assert call.status == LatencyStatusEnum.OK


def test_track_external_latency_context_manager_exception():
    """Verifica que el context manager capture excepciones, registre status ERROR y relance la excepción."""
    reset_latency_tracker()

    with pytest.raises(ValueError, match="Simulated Network Crash"):
        with track_external_latency(ExternalProviderEnum.YAHOO_FINANCE, "fetch_ticker", target="IBEX"):
            time.sleep(0.005)
            raise ValueError("Simulated Network Crash")

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.status == LatencyStatusEnum.ERROR
    assert "Simulated Network Crash" in (call.error_message or "")


def test_profile_external_call_decorator_sync():
    """Verifica el funcionamiento del decorador síncrono con extractor de target."""
    reset_latency_tracker()

    @profile_external_call(
        provider=ExternalProviderEnum.YAHOO_FINANCE,
        operation="download_quote",
        target_extractor=lambda symbol, **kw: symbol,
    )
    def fetch_quote(symbol: str) -> dict:
        time.sleep(0.005)
        return {"symbol": symbol, "price": 42.0}

    res = fetch_quote("SAN.MC")
    assert res["price"] == 42.0

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.target == "SAN.MC"
    assert call.operation == "download_quote"


def test_profile_external_call_decorator_async():
    """Verifica el funcionamiento del decorador asíncrono."""
    reset_latency_tracker()

    @profile_external_call(
        provider=ExternalProviderEnum.GEMINI,
        operation="async_infer",
        target_extractor=lambda model, *a, **kw: model,
    )
    async def async_generate(model: str, prompt: str) -> str:
        await asyncio.sleep(0.01)
        return f"Response from {model}"

    res = asyncio.run(async_generate("gemini-2.5-pro", "hello"))
    assert "gemini-2.5-pro" in res

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.target == "gemini-2.5-pro"
    assert call.operation == "async_infer"


def test_latency_tracker_reset():
    """Verifica que el método reset vacíe el búfer circular y contadores."""
    tracker = LatencyTracker()
    tracker.record_call(ExternalProviderEnum.OTHER, "op", 100.0)
    assert tracker.get_metrics_report().total_calls_recorded == 1

    tracker.reset()
    clean_report = tracker.get_metrics_report()
    assert clean_report.total_calls_recorded == 0
    assert len(clean_report.recent_calls) == 0
    assert len(clean_report.providers) == 0
