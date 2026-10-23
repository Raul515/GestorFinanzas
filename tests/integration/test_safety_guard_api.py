from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.domain.models import presupuestos as pres_models


def test_api_safety_status_no_needs(client: TestClient, seed_data: dict[str, int]):
    """If no basic needs budget exists, status indicates unconfigured with can_invest = False."""
    response = client.get("/advisor/safety-status")
    assert response.status_code == 200
    data = response.json()
    assert data["can_invest"] is False
    assert data["monthly_needs_reference"] == 0.0
    assert "no configurado" in data["message"]


def test_api_safety_status_with_base_budget(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Verifies that BASE budget for Needs defines target_amount dynamically."""
    # Add 1000 € to Alquiler (Necesidades Básicas) in BASE
    p = pres_models.PresupuestoMensual(
        mes="BASE",
        subcategoria_id=seed_data["sub_alquiler_id"],
        cantidad=1000.0,
    )
    db_session.add(p)
    db_session.commit()

    response = client.get("/advisor/safety-status?mes=BASE")
    assert response.status_code == 200
    data = response.json()
    assert data["monthly_needs_reference"] == 1000.0
    assert data["target_amount"] == 3000.0  # 3 months default
    assert data["can_invest"] is False
    assert data["gap"] == 3000.0


def test_api_update_emergency_fund_config(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Tests configuring target_months and manual balance update."""
    # Set BASE needs budget = 800 €
    p = pres_models.PresupuestoMensual(
        mes="BASE",
        subcategoria_id=seed_data["sub_alquiler_id"],
        cantidad=800.0,
    )
    db_session.add(p)
    db_session.commit()

    # 1. Update target_months to 6
    res1 = client.post(
        "/advisor/emergency-fund/config?mes=BASE",
        json={"target_months": 6},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["target_months"] == 6
    assert data1["target_amount"] == 4800.0  # 6 * 800
    assert data1["can_invest"] is False

    # 2. Update balance manually to 5000 € (fully covered)
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
    """API must reject target_months < 3 with validation error."""
    response = client.post(
        "/advisor/emergency-fund/config",
        json={"target_months": 2},
    )
    assert response.status_code in (400, 422)
