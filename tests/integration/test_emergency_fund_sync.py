import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.domain.models import budgets as pres_models


def test_transaction_auto_syncs_emergency_fund(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """
    Verifica que la creación de transacciones en la subcategoría 'Fondo de emergencia'
    actualiza automáticamente el saldo acumulado (current_balance) y estado de la salvaguarda.
    """
    # 1. Establecer presupuesto de Necesidades Básicas en BASE = 1000 € (meta objetivo = 3000 €)
    p = pres_models.MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=1000.0,
    )
    db_session.add(p)
    db_session.commit()

    # Comprobación de diagnóstico inicial de seguridad
    res_init = client.get("/advisor/safety-status?mes=BASE")
    assert res_init.json()["current_balance"] == 0.0
    assert res_init.json()["can_invest"] is False

    # 2. Registrar primera aportación: 1200 € al 'Fondo de emergencia'
    res_tx1 = client.post(
        "/transactions/",
        json={
            "date": str(datetime.date.today()),
            "subcategory_id": seed_data["sub_emergencia_id"],
            "amount": 1200.0,
            "description": "Aportación mensual enero",
        },
    )
    assert res_tx1.status_code == 200

    # Verificar que el saldo acumulado se actualizó a 1200 €
    res_check1 = client.get("/advisor/safety-status?mes=BASE")
    data1 = res_check1.json()
    assert data1["current_balance"] == 1200.0
    assert data1["coverage_months"] == 1.2
    assert data1["can_invest"] is False
    assert data1["gap"] == 1800.0

    # 3. Registrar segunda aportación: 1800 € al 'Fondo de emergencia'
    res_tx2 = client.post(
        "/transactions/",
        json={
            "date": str(datetime.date.today()),
            "subcategory_id": seed_data["sub_emergencia_id"],
            "amount": 1800.0,
            "description": "Aportación mensual febrero",
        },
    )
    assert res_tx2.status_code == 200

    # Verificar que el saldo acumulado alcanzó 3000 € y se habilitaron las inversiones
    res_check2 = client.get("/advisor/safety-status?mes=BASE")
    data2 = res_check2.json()
    assert data2["current_balance"] == 3000.0
    assert data2["coverage_months"] == 3.0
    assert data2["is_completed"] is True
    assert data2["can_invest"] is True
    assert data2["gap"] == 0.0

