import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.domain.models import presupuestos as pres_models


def test_transaction_auto_syncs_emergency_fund(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """
    Verifies that creating transactions in subcategory 'Fondo de emergencia'
    automatically updates the EmergencyFund current_balance and status.
    """
    # 1. Set Needs budget in BASE = 1000 € (target = 3000 €)
    p = pres_models.PresupuestoMensual(
        mes="BASE",
        subcategoria_id=seed_data["sub_alquiler_id"],
        cantidad=1000.0,
    )
    db_session.add(p)
    db_session.commit()

    # Initial safety status check
    res_init = client.get("/advisor/safety-status?mes=BASE")
    assert res_init.json()["current_balance"] == 0.0
    assert res_init.json()["can_invest"] is False

    # 2. Add first transaction: 1200 € into 'Fondo de emergencia'
    res_tx1 = client.post(
        "/transacciones/",
        json={
            "fecha": str(datetime.date.today()),
            "subcategoria_id": seed_data["sub_emergencia_id"],
            "cantidad": 1200.0,
            "concepto": "Aportación mensual enero",
        },
    )
    assert res_tx1.status_code == 200

    # Verify balance updated to 1200 €
    res_check1 = client.get("/advisor/safety-status?mes=BASE")
    data1 = res_check1.json()
    assert data1["current_balance"] == 1200.0
    assert data1["coverage_months"] == 1.2
    assert data1["can_invest"] is False
    assert data1["gap"] == 1800.0

    # 3. Add second transaction: 1800 € into 'Fondo de emergencia'
    res_tx2 = client.post(
        "/transacciones/",
        json={
            "fecha": str(datetime.date.today()),
            "subcategoria_id": seed_data["sub_emergencia_id"],
            "cantidad": 1800.0,
            "concepto": "Aportación mensual febrero",
        },
    )
    assert res_tx2.status_code == 200

    # Verify balance updated to 3000 € and investment unlocked!
    res_check2 = client.get("/advisor/safety-status?mes=BASE")
    data2 = res_check2.json()
    assert data2["current_balance"] == 3000.0
    assert data2["coverage_months"] == 3.0
    assert data2["is_completed"] is True
    assert data2["can_invest"] is True
    assert data2["gap"] == 0.0
