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
    """Verifica la aplicación de la regla 80/20 con aporte a ahorro y transacción real en deseos (sin tocar presupuesto)."""
    from backend.domain.models import guidelines as guideline_models

    payload = {
        "month_key": "2026-10",
        "strategy_type": "HYBRID_80_20",
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
    assert data["transactions_created"] == 2
    assert data["budgets_updated"] == 0

    # Verificar persistencia en AppliedGuidelineStrategy
    applied = (
        db_session.query(guideline_models.AppliedGuidelineStrategy)
        .filter(
            guideline_models.AppliedGuidelineStrategy.month == "2026-10",
            guideline_models.AppliedGuidelineStrategy.scenario_type == "NEEDS_SURPLUS",
        )
        .first()
    )
    assert applied is not None
    assert applied.is_partial is True
    assert applied.allocated_amount == 500.0

    # Verificar que /guidelines/monthly reconoce la estrategia aplicada y suprime las tarjetas interactivas
    m_req = {
        "month_key": "2026-10",
        "month_name": "Octubre",
        "real_income": 2000.0,
        "budget_income": 2000.0,
        "real_needs": 500.0,
        "real_wants": 300.0,
        "real_savings": 400.0,
    }
    m_res = client.post("/guidelines/monthly", json=m_req)
    assert m_res.status_code == 200
    m_data = m_res.json()
    surplus_items = [g for g in m_data["guidelines"] if g["scenario_type"] == "NEEDS_SURPLUS"]
    assert len(surplus_items) == 1
    assert "Colchón Prudencial Activo" in surplus_items[0]["title"]
    assert len(surplus_items[0]["strategies"]) == 0


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


def test_api_revert_strategy(client: TestClient, db_session, seed_data):
    """Verifica que el endpoint /revert-strategy elimine transacciones vinculadas y desaplique la estrategia."""
    from backend.domain.models import guidelines as guideline_models, transactions as tx_models, emergency_fund as ef_models

    fund = ef_models.EmergencyFund(current_balance=500.0, target_months=3, target_amount=1500.0, is_completed=False)
    db_session.add(fund)
    db_session.commit()

    # 1. Aplicar estrategia híbrida
    payload_apply = {
        "month_key": "2026-10",
        "strategy_type": "HYBRID_80_20",
        "is_partial": False,
        "savings_allocations": [{"subcategory_id": seed_data["sub_emergencia_id"], "amount": 400.0}],
        "wants_allocations": [{"subcategory_id": seed_data["sub_ocio_id"], "amount": 100.0}],
    }
    res_apply = client.post("/guidelines/apply-strategy", json=payload_apply)
    assert res_apply.status_code == 200
    assert fund.current_balance == 900.0

    # Comprobar que las transacciones tienen applied_strategy_id asignado
    txs = db_session.query(tx_models.Transaction).all()
    assert len(txs) == 2
    strat_id = txs[0].applied_strategy_id
    assert strat_id is not None
    assert txs[1].applied_strategy_id == strat_id

    # 2. Revertir la estrategia
    res_revert = client.post("/guidelines/revert-strategy", json={"month_key": "2026-10", "scenario_type": "NEEDS_SURPLUS"})
    assert res_revert.status_code == 200
    rev_data = res_revert.json()
    assert rev_data["success"] is True
    assert rev_data["transactions_reverted"] == 2
    assert rev_data["emergency_fund_reverted"] == 400.0

    # 3. Validar estado en base de datos
    db_session.refresh(fund)
    assert fund.current_balance == 500.0
    assert db_session.query(tx_models.Transaction).count() == 0
    assert db_session.query(guideline_models.AppliedGuidelineStrategy).count() == 0


def test_cascade_revert_on_single_transaction_deletion(client: TestClient, db_session, seed_data):
    """Verifica que al eliminar una transacción vinculada a una estrategia desde /transactions, se revierta todo el lote en cascada."""
    from backend.domain.models import guidelines as guideline_models, transactions as tx_models, emergency_fund as ef_models

    fund = ef_models.EmergencyFund(current_balance=200.0, target_months=3, target_amount=1500.0, is_completed=False)
    db_session.add(fund)
    db_session.commit()

    # 1. Aplicar estrategia híbrida
    payload_apply = {
        "month_key": "2026-10",
        "strategy_type": "HYBRID_80_20",
        "is_partial": False,
        "savings_allocations": [{"subcategory_id": seed_data["sub_emergencia_id"], "amount": 400.0}],
        "wants_allocations": [{"subcategory_id": seed_data["sub_ocio_id"], "amount": 100.0}],
    }
    res_apply = client.post("/guidelines/apply-strategy", json=payload_apply)
    assert res_apply.status_code == 200
    assert fund.current_balance == 600.0

    # Localizar la transacción de Deseos
    wants_tx = (
        db_session.query(tx_models.Transaction)
        .filter(tx_models.Transaction.subcategory_id == seed_data["sub_ocio_id"])
        .first()
    )
    assert wants_tx is not None

    # 2. Eliminar la transacción de Deseos directamente por su ID
    res_del = client.delete(f"/transactions/{wants_tx.id}")
    assert res_del.status_code == 200

    # 3. Validar que la transacción de ahorro también se eliminó en cascada y se restó el saldo del fondo
    db_session.refresh(fund)
    assert fund.current_balance == 200.0
    assert db_session.query(tx_models.Transaction).count() == 0
    assert db_session.query(guideline_models.AppliedGuidelineStrategy).count() == 0


def test_api_sweep_month_surplus_inherit_strategy(client: TestClient, db_session, seed_data):
    """Verifica que el barrido con modo INHERIT_STRATEGY distribuya proporcionalmente el remanente."""
    from backend.domain.models import emergency_fund as ef_models, guidelines as guideline_models, transactions as tx_models

    fund = ef_models.EmergencyFund(current_balance=500.0, target_months=3, target_amount=1500.0, is_completed=False)
    db_session.add(fund)
    db_session.commit()

    # 1. Aplicar estrategia 80/20 con colchón (250 € aplicados, 250 € colchón)
    payload_apply = {
        "month_key": "2026-11",
        "strategy_type": "HYBRID_80_20",
        "is_partial": True,
        "savings_allocations": [{"subcategory_id": seed_data["sub_emergencia_id"], "amount": 200.0}],
        "wants_allocations": [{"subcategory_id": seed_data["sub_ocio_id"], "amount": 50.0}],
    }
    res_apply = client.post("/guidelines/apply-strategy", json=payload_apply)
    assert res_apply.status_code == 200
    assert fund.current_balance == 700.0

    # 2. Ejecutar barrido inteligente heredando la estrategia para un remanente de 100 €
    payload_sweep = {
        "month_key": "2026-11",
        "amount": 100.0,
        "mode": "INHERIT_STRATEGY",
    }
    res_sweep = client.post("/guidelines/sweep", json=payload_sweep)
    assert res_sweep.status_code == 200
    data_sweep = res_sweep.json()
    assert data_sweep["success"] is True
    assert data_sweep["mode_applied"] == "INHERIT_STRATEGY"
    assert data_sweep["amount_swept"] == 100.0
    assert data_sweep["transactions_created"] == 2

    # El fondo de emergencia debe haber recibido el 80% (80 €) de los 100 €
    db_session.refresh(fund)
    assert fund.current_balance == 780.0

    # Comprobar que la estrategia aplicada se actualizó (cushion reducido)
    strat = db_session.query(guideline_models.AppliedGuidelineStrategy).filter_by(month="2026-11").first()
    assert strat is not None
    assert strat.cushion_amount == 150.0  # 250 - 100 = 150


def test_api_apply_and_revert_extraordinary_income_strategy(client: TestClient, db_session, seed_data):
    """Verifica el ciclo de vida completo de la estrategia de ingreso extraordinario (aplicación, informe y reversión)."""
    from backend.domain.models import emergency_fund as ef_models, guidelines as guideline_models, transactions as tx_models

    fund = ef_models.EmergencyFund(current_balance=100.0, target_months=3, target_amount=1500.0, is_completed=False)
    db_session.add(fund)
    db_session.commit()

    # 1. Aplicar estrategia de ingreso extraordinario (400 € a fondo de emergencia, 100 € a ocio)
    payload_apply = {
        "month_key": "2026-12",
        "strategy_type": "EXTRAORDINARY_INCOME",
        "is_partial": False,
        "savings_allocations": [{"subcategory_id": seed_data["sub_emergencia_id"], "amount": 400.0}],
        "wants_allocations": [{"subcategory_id": seed_data["sub_ocio_id"], "amount": 100.0}],
    }
    res_apply = client.post("/guidelines/apply-strategy", json=payload_apply)
    assert res_apply.status_code == 200
    data_apply = res_apply.json()
    assert data_apply["success"] is True
    assert data_apply["transactions_created"] == 2
    assert data_apply["emergency_fund_updated"] is True
    assert data_apply["new_emergency_fund_balance"] == 500.0

    # Verificar AppliedGuidelineStrategy con scenario_type == "EXTRAORDINARY_INCOME"
    strat = (
        db_session.query(guideline_models.AppliedGuidelineStrategy)
        .filter_by(month="2026-12", scenario_type="EXTRAORDINARY_INCOME")
        .first()
    )
    assert strat is not None
    assert strat.strategy_type == "EXTRAORDINARY_INCOME"
    assert strat.allocated_amount == 500.0

    # Verificar transacciones vinculadas y descripciones
    txs = db_session.query(tx_models.Transaction).filter_by(applied_strategy_id=strat.id).all()
    assert len(txs) == 2
    assert any("[Pauta EXTRAORDINARY_INCOME] Bonus Extraordinario" in t.description for t in txs)
    assert any("[Pauta EXTRAORDINARY_INCOME] Bonus Extraordinario a Deseos" in t.description for t in txs)

    # 2. Consultar pautas mensuales y verificar que muestra el estado asignado
    req_monthly = {
        "month_key": "2026-12",
        "month_name": "Diciembre",
        "real_income": 2500.0,
        "budget_income": 2000.0,
        "real_needs": 1000.0,
        "real_wants": 600.0,
        "real_savings": 900.0,
        "safety_status": {
            "current_balance": 500.0,
            "target_amount": 1500.0,
            "coverage_months": 1.0,
            "is_emergency_fund_completed": False,
        },
    }
    res_monthly = client.post("/guidelines/monthly", json=req_monthly)
    assert res_monthly.status_code == 200
    data_monthly = res_monthly.json()
    bonus_guidelines = [g for g in data_monthly["guidelines"] if g["scenario_type"] == "EXTRAORDINARY_INCOME"]
    assert len(bonus_guidelines) == 1
    assert "Ingreso Extraordinario Asignado" in bonus_guidelines[0]["title"]
    assert len(bonus_guidelines[0]["strategies"]) == 0

    # 3. Revertir la estrategia atómicamente
    payload_revert = {
        "month_key": "2026-12",
        "scenario_type": "EXTRAORDINARY_INCOME",
    }
    res_revert = client.post("/guidelines/revert-strategy", json=payload_revert)
    assert res_revert.status_code == 200
    data_revert = res_revert.json()
    assert data_revert["success"] is True
    assert data_revert["transactions_reverted"] == 2
    assert data_revert["emergency_fund_reverted"] == 400.0

    # Verificar que el fondo de emergencia se restauró y la estrategia y transacciones se borraron
    db_session.refresh(fund)
    assert fund.current_balance == 100.0
    assert db_session.query(tx_models.Transaction).filter_by(applied_strategy_id=strat.id).count() == 0
    assert (
        db_session.query(guideline_models.AppliedGuidelineStrategy)
        .filter_by(month="2026-12", scenario_type="EXTRAORDINARY_INCOME")
        .count()
        == 0
    )


def test_cascade_revert_on_bonus_transaction_deletion(client: TestClient, db_session, seed_data):
    """Verifica que la eliminación individual de una transacción de bonus revierta en cascada toda la estrategia."""
    from backend.domain.models import emergency_fund as ef_models, guidelines as guideline_models, transactions as tx_models

    fund = ef_models.EmergencyFund(current_balance=200.0, target_months=3, target_amount=1500.0, is_completed=False)
    db_session.add(fund)
    db_session.commit()

    # 1. Aplicar estrategia de bonus
    payload_apply = {
        "month_key": "2026-12",
        "strategy_type": "EXTRAORDINARY_INCOME",
        "is_partial": False,
        "savings_allocations": [{"subcategory_id": seed_data["sub_emergencia_id"], "amount": 300.0}],
        "wants_allocations": [{"subcategory_id": seed_data["sub_ocio_id"], "amount": 100.0}],
    }
    res = client.post("/guidelines/apply-strategy", json=payload_apply)
    assert res.status_code == 200
    assert fund.current_balance == 500.0

    # 2. Localizar una de las transacciones creadas (por ejemplo la de ocio) y borrarla mediante endpoint DELETE
    strat = (
        db_session.query(guideline_models.AppliedGuidelineStrategy)
        .filter_by(month="2026-12", scenario_type="EXTRAORDINARY_INCOME")
        .first()
    )
    assert strat is not None
    tx_wants = (
        db_session.query(tx_models.Transaction)
        .filter_by(applied_strategy_id=strat.id, subcategory_id=seed_data["sub_ocio_id"])
        .first()
    )
    assert tx_wants is not None

    res_del = client.delete(f"/transactions/{tx_wants.id}")
    assert res_del.status_code == 200

    # 3. Validar reversión en cascada: fondo restaurado a 200, transacciones y estrategia borradas
    db_session.refresh(fund)
    assert fund.current_balance == 200.0
    assert db_session.query(tx_models.Transaction).filter_by(applied_strategy_id=strat.id).count() == 0
    assert (
        db_session.query(guideline_models.AppliedGuidelineStrategy)
        .filter_by(month="2026-12", scenario_type="EXTRAORDINARY_INCOME")
        .count()
        == 0
    )




