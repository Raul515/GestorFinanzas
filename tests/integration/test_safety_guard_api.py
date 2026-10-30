from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.domain.models import budgets as pres_models


def test_api_safety_status_no_needs(client: TestClient, seed_data: dict[str, int]):
    """Si no existe presupuesto para necesidades básicas, el estado indica no configurado con can_invest = False."""
    response = client.get("/advisor/safety-status")
    assert response.status_code == 200
    data = response.json()
    assert data["can_invest"] is False
    assert data["monthly_needs_reference"] == 0.0
    assert "no configurado" in data["message"]


def test_api_safety_status_with_base_budget(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Verifica que el presupuesto en plantilla BASE para Necesidades define la meta target_amount de forma dinámica."""
    # Añadir 1000 € a Alquiler (Necesidades Básicas) en BASE
    p = pres_models.MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=1000.0,
    )

    db_session.add(p)
    db_session.commit()

    response = client.get("/advisor/safety-status?mes=BASE")
    assert response.status_code == 200
    data = response.json()
    assert data["monthly_needs_reference"] == 1000.0
    assert data["target_amount"] == 3000.0  # 3 meses por defecto
    assert data["can_invest"] is False
    assert data["gap"] == 3000.0


def test_api_update_emergency_fund_config(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Prueba la configuración de meses objetivo (target_months) y la actualización manual de saldo."""
    # Establecer presupuesto BASE de necesidades = 800 €
    p = pres_models.MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=800.0,
    )
    db_session.add(p)
    db_session.commit()

    # 1. Actualizar meses objetivo a 6
    res1 = client.post(
        "/advisor/emergency-fund/config?mes=BASE",
        json={"target_months": 6},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["target_months"] == 6
    assert data1["target_amount"] == 4800.0  # 6 * 800
    assert data1["can_invest"] is False

    # 2. Actualizar saldo manualmente a 5000 € (cobertura total alcanzada)
    res2 = client.post(
        "/advisor/emergency-fund/config?mes=BASE",
        json={"current_balance": 5000.0},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["current_balance"] == 5000.0
    assert data2["is_completed"] is True
    assert data2["can_invest"] is True
    assert data2["gap"] == 0.0


def test_api_reject_under_3_months(client: TestClient):
    """La API debe rechazar target_months < 3 con error de validación constitucional."""
    response = client.post(
        "/advisor/emergency-fund/config",
        json={"target_months": 2},
    )
    assert response.status_code in (400, 422)


def test_api_safety_status_fallback_to_recent_month(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Verifica que si un mes no tiene presupuesto (ej. 2026-12) y BASE no está configurado, recurre al mes reciente con datos."""
    # Añadir presupuesto de Necesidades únicamente en 2026-11
    p = pres_models.MonthlyBudget(
        month="2026-11",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=500.0,
    )
    db_session.add(p)
    db_session.commit()

    # Consultar mes vacío 2026-12
    res = client.get("/advisor/safety-status?mes=2026-12")
    assert res.status_code == 200
    data = res.json()
    assert data["monthly_needs_reference"] == 500.0
    assert data["target_amount"] == 1500.0

    # Consultar sin parámetro (herramientas globales como Screener o Deep Dive)
    res_global = client.get("/advisor/safety-status")
    assert res_global.status_code == 200
    data_global = res_global.json()
    assert data_global["monthly_needs_reference"] == 500.0
    assert data_global["target_amount"] == 1500.0


