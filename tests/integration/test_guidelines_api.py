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


def test_api_apply_strategy_fire_incomplete_fund(client: TestClient, db_session, seed_data):
    """Verifica la ejecución atómica de la estrategia FIRE con sincronización del Fondo de Emergencia."""
    from backend.domain.models import emergency_fund as ef_models

    ef = ef_models.EmergencyFund(
        target_amount=3000.0,
        current_balance=1000.0,
        target_months=3,
        is_completed=False,
    )
    db_session.add(ef)
    db_session.commit()

    payload = {
        "month_key": "2026-10",
        "strategy_type": "FIRE",
        "is_partial": False,
        "savings_allocations": [
            {"subcategory_id": seed_data["sub_emergencia_id"], "amount": 500.0}
        ],
        "wants_allocations": [],
    }

    response = client.post("/guidelines/apply-strategy", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["transactions_created"] == 1
    assert data["budgets_updated"] == 0
    assert data["emergency_fund_updated"] is True
    assert data["new_emergency_fund_balance"] == 1500.0


def test_api_apply_strategy_80_20(client: TestClient, db_session, seed_data):
    """Verifica la aplicación de la regla 80/20 con aporte a ahorro e incremento de presupuesto en deseos."""
    payload = {
        "month_key": "2026-10",
        "strategy_type": "EIGHTY_TWENTY",
        "is_partial": True,
        "savings_allocations": [
            {"subcategory_id": seed_data["sub_emergencia_id"], "amount": 400.0}
        ],
        "wants_allocations": [
            {"subcategory_id": seed_data["sub_ocio_id"], "amount": 100.0}
        ],
    }

    response = client.post("/guidelines/apply-strategy", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["transactions_created"] == 1
    assert data["budgets_updated"] == 1


def test_api_sweep_month_surplus(client: TestClient, db_session, seed_data):
    """Verifica que el barrido de fin de mes cree la transacción y actualice el saldo del fondo."""
    from backend.domain.models import emergency_fund as ef_models

    ef = ef_models.EmergencyFund(
        target_amount=2000.0,
        current_balance=1800.0,
        target_months=2,
        is_completed=False,
    )
    db_session.add(ef)
    db_session.commit()

    payload = {
        "month_key": "2026-10",
        "amount": 250.0,
        "target_subcategory_id": seed_data["sub_emergencia_id"],
    }

    response = client.post("/guidelines/sweep", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["amount_swept"] == 250.0
    assert data["emergency_fund_updated"] is True
    assert data["new_emergency_fund_balance"] == 2050.0


def test_api_compensate_wants_deficit_next_month(client: TestClient, db_session, seed_data):
    """Verifica que el ajuste compensatorio por exceso en deseos reduzca el presupuesto del mes siguiente."""
    from backend.domain.models import budgets as pres_models

    base_budget = pres_models.MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_ocio_id"],
        amount=400.0,
    )
    db_session.add(base_budget)
    db_session.commit()

    payload = {
        "month_key": "2026-10",
        "action_type": "WANTS_COMPENSATION_NEXT_MONTH",
        "amount": 150.0,
        "target_subcategory_id": seed_data["sub_ocio_id"],
    }

    response = client.post("/guidelines/compensate-deficit", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["target_month"] == "2026-11"
    assert data["budgets_updated"] == 1
    assert data["new_budget_amount"] == 250.0

    # Comprobar persistencia en base de datos
    saved_budget = (
        db_session.query(pres_models.MonthlyBudget)
        .filter(
            pres_models.MonthlyBudget.month == "2026-11",
            pres_models.MonthlyBudget.subcategory_id == seed_data["sub_ocio_id"],
        )
        .first()
    )
    assert saved_budget is not None
    assert saved_budget.amount == 250.0


def test_api_compensate_needs_absorption_current_month(client: TestClient, db_session, seed_data):
    """Verifica la amortiguación de un déficit de necesidades desde el presupuesto de deseos del mes en curso."""
    from backend.domain.models import budgets as pres_models

    curr_budget = pres_models.MonthlyBudget(
        month="2026-10",
        subcategory_id=seed_data["sub_ocio_id"],
        amount=300.0,
    )
    db_session.add(curr_budget)
    db_session.commit()

    payload = {
        "month_key": "2026-10",
        "action_type": "NEEDS_ABSORPTION_CURRENT_WANTS",
        "amount": 100.0,
        "target_subcategory_id": seed_data["sub_ocio_id"],
    }

    response = client.post("/guidelines/compensate-deficit", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["target_month"] == "2026-10"
    assert data["budgets_updated"] == 1
    assert data["new_budget_amount"] == 200.0


def test_api_compensate_freeze_wants(client: TestClient, db_session, seed_data):
    """Verifica que la congelación de deseos ante caída de ingresos fije las partidas de ocio a 0.00 €."""
    from backend.domain.models import budgets as pres_models

    curr_budget = pres_models.MonthlyBudget(
        month="2026-10",
        subcategory_id=seed_data["sub_ocio_id"],
        amount=350.0,
    )
    db_session.add(curr_budget)
    db_session.commit()

    payload = {
        "month_key": "2026-10",
        "action_type": "FREEZE_WANTS",
        "target_subcategory_ids": [seed_data["sub_ocio_id"]],
    }

    response = client.post("/guidelines/compensate-deficit", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["target_month"] == "2026-10"
    assert data["budgets_updated"] == 1
    assert data["new_budget_amount"] == 0.0


