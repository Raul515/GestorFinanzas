"""Pruebas de integración para los endpoints REST de métricas de profiling y latencia (Spec 009)."""

from fastapi.testclient import TestClient
from backend.domain.schemas.latency_metrics import ExternalProviderEnum
from backend.services.latency_profiler import get_latency_tracker, reset_latency_tracker


def test_get_latency_metrics_initially_empty(client: TestClient):
    """Verifica que el endpoint /metrics/latency responda 200 con reporte vacío tras reseteo."""
    reset_latency_tracker()

    response = client.get("/metrics/latency")
    assert response.status_code == 200
    data = response.json()
    assert data["total_calls_recorded"] == 0
    assert data["buffer_capacity"] == 1000
    assert data["providers"] == {}
    assert data["recent_calls"] == []


def test_get_latency_metrics_with_data(client: TestClient):
    """Verifica la recuperación de estadísticas, percentiles y llamadas recientes."""
    reset_latency_tracker()
    tracker = get_latency_tracker()

    tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "history", 150.0, target="SAN.MC")
    tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "history", 250.0, target="BBVA.MC")
    tracker.record_call(ExternalProviderEnum.ECB, "yield_series", 80.0, target="bund_10y")

    response = client.get("/metrics/latency")
    assert response.status_code == 200
    data = response.json()

    assert data["total_calls_recorded"] == 3
    assert len(data["recent_calls"]) == 3
    assert "yahoo_finance" in data["providers"]
    assert "ecb" in data["providers"]

    yahoo = data["providers"]["yahoo_finance"]
    assert yahoo["total_calls"] == 2
    assert yahoo["avg_duration_ms"] == 200.0
    assert yahoo["min_duration_ms"] == 150.0
    assert yahoo["max_duration_ms"] == 250.0
    assert "p50_duration_ms" in yahoo
    assert "p95_duration_ms" in yahoo


def test_get_latency_metrics_provider_filter_and_limit(client: TestClient):
    """Verifica el filtrado por proveedor y la limitación de llamadas recientes."""
    reset_latency_tracker()
    tracker = get_latency_tracker()

    for i in range(10):
        tracker.record_call(ExternalProviderEnum.YAHOO_FINANCE, "op", 100.0 + i, target=f"YF_{i}")
    for i in range(5):
        tracker.record_call(ExternalProviderEnum.GEMINI, "infer", 800.0 + i, target=f"GEM_{i}")

    # Filtrar solo por Gemini y limitar a 2
    response = client.get("/metrics/latency?provider=gemini&limit_recent=2")
    assert response.status_code == 200
    data = response.json()

    assert len(data["providers"]) == 1
    assert "gemini" in data["providers"]
    assert len(data["recent_calls"]) == 2
    assert all(it["provider"] == "gemini" for it in data["recent_calls"])


def test_delete_latency_metrics_resets_buffer(client: TestClient):
    """Verifica que DELETE /metrics/latency limpie el búfer circular en memoria."""
    reset_latency_tracker()
    tracker = get_latency_tracker()
    tracker.record_call(ExternalProviderEnum.OTHER, "test", 42.0)

    # Verificar que existe 1 llamada
    res1 = client.get("/metrics/latency")
    assert res1.json()["total_calls_recorded"] == 1

    # Ejecutar DELETE
    del_res = client.delete("/metrics/latency")
    assert del_res.status_code == 200
    assert "reiniciado" in del_res.json()["message"]

    # Verificar que ahora está vacío
    res2 = client.get("/metrics/latency")
    assert res2.json()["total_calls_recorded"] == 0
    assert res2.json()["recent_calls"] == []
