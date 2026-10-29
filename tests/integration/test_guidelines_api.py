"""
Pruebas de integración para los endpoints de la API de pautas deterministas (/guidelines).
Verifica los contratos REST para evaluación mensual y diagnóstico anual.
"""

import pytest
from fastapi.testclient import TestClient


def test_api_monthly_guidelines_surplus(client: TestClient):
    """Verifica que el endpoint /guidelines/monthly evalúe correctamente un escenario de excedente."""
    payload = {
        "month_key": "2026-05",
        "month_name": "Mayo",
        "real_income": 3000.0,
        "budget_income": 3000.0,
        "real_needs": 1200.0,  # 40% vs 50% meta -> 300 € excedente
        "real_wants": 700.0,
        "real_savings": 1100.0,
        "safety_status": {
            "is_configured": True,
            "coverage_months": 2.5,
            "target_months": 3.0,
            "gap": 500.0,
        },
    }

    response = client.post("/guidelines/monthly", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["month_key"] == "2026-05"
    assert data["real_income"] == 3000.0
    assert data["savings_rate"] == pytest.approx(36.67, 0.01)
    assert len(data["guidelines"]) >= 1

    # Escenario detectado debe ser NEEDS_SURPLUS
    scenarios = [g["scenario_type"] for g in data["guidelines"]]
    assert "NEEDS_SURPLUS" in scenarios

    # Tabla sinóptica presente
    assert len(data["synoptic_table"]) >= 1


def test_api_monthly_guidelines_deficit(client: TestClient):
    """Verifica que el endpoint /guidelines/monthly gestione jerarquía de absorción en déficit."""
    payload = {
        "month_key": "2026-06",
        "month_name": "Junio",
        "real_income": 2000.0,
        "budget_income": 2000.0,
        "real_needs": 1200.0,  # 60% vs 50% meta -> 200 € exceso
        "real_wants": 500.0,
        "real_savings": 300.0,
    }

    response = client.post("/guidelines/monthly", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["month_key"] == "2026-06"
    assert data["status_severity"] == "alert"
    scenarios = [g["scenario_type"] for g in data["guidelines"]]
    assert "NEEDS_DEFICIT" in scenarios


def test_api_annual_guidelines(client: TestClient):
    """Verifica que el endpoint /guidelines/annual evalúe correctamente métricas consolidadas."""
    metrics = {
        "ingresos_anual_real": 36000.0,
        "nec_anual_real": 18000.0,
        "des_anual_real": 9000.0,
        "aho_anual_real": 8000.0,
        "pct_nec_real": 50.0,
        "pct_des_real": 25.0,
        "pct_aho_real": 22.22,
        "ahorro_acumulado_total": 8000.0,
    }

    response = client.post("/guidelines/annual", json={"metrics": metrics})
    assert response.status_code == 200
    data = response.json()

    assert "overall_health" in data
    assert data["average_savings_rate"] == pytest.approx(22.22, 0.01)
    assert len(data["guidelines"]) >= 1
