from backend.domain.models.emergency_fund import EmergencyFund
from backend.services.safety_guard import evaluate_safety_status, sync_fund_state


def test_evaluate_safety_status_zero_balance():
    """Verifica el diagnóstico de salvaguarda cuando el saldo acumulado es 0 €."""
    fund = EmergencyFund(current_balance=0.0, target_months=3)
    status = evaluate_safety_status(fund, monthly_needs=1000.0)

    assert status.current_balance == 0.0
    assert status.target_amount == 3000.0
    assert status.coverage_months == 0.0
    assert status.is_completed is False
    assert status.can_invest is False
    assert status.gap == 3000.0
    assert "Fondo de seguridad en construcción" in status.message


def test_evaluate_safety_status_partial_coverage():
    """Verifica el estado cuando la reserva cubre parcialmente los meses objetivo."""
    fund = EmergencyFund(current_balance=1500.0, target_months=3)
    status = evaluate_safety_status(fund, monthly_needs=1000.0)

    assert status.current_balance == 1500.0
    assert status.target_amount == 3000.0
    assert status.coverage_months == 1.5
    assert status.is_completed is False
    assert status.can_invest is False
    assert status.gap == 1500.0


def test_evaluate_safety_status_fully_covered():
    """Verifica que al alcanzar o superar el objetivo se habiliten las inversiones en activos de riesgo."""
    fund = EmergencyFund(current_balance=3000.0, target_months=3)
    status = evaluate_safety_status(fund, monthly_needs=1000.0)

    assert status.current_balance == 3000.0
    assert status.target_amount == 3000.0
    assert status.coverage_months == 3.0
    assert status.is_completed is True
    assert status.can_invest is True
    assert status.gap == 0.0
    assert "Fondo de seguridad cubierto" in status.message


def test_evaluate_safety_status_needs_increase_dynamic_gap():
    """
    Simula el escenario dinámico del usuario:
    1. El usuario completa 3000 € (3 meses a 1000 €/mes).
    2. Las necesidades básicas aumentan a 1400 €/mes (subida de alquiler, inflación).
    3. La meta salta dinámicamente a 4200 €, abriendo una brecha de 1200 € y bloqueando de inmediato inversiones de riesgo.
    """
    fund = EmergencyFund(current_balance=3000.0, target_months=3)

    # Estado inicial: necesidades de 1000 €
    status_initial = evaluate_safety_status(fund, monthly_needs=1000.0)
    assert status_initial.is_completed is True
    assert status_initial.can_invest is True

    # Aumento de necesidades a 1400 €
    status_after_increase = evaluate_safety_status(fund, monthly_needs=1400.0)
    assert status_after_increase.target_amount == 4200.0
    assert status_after_increase.gap == 1200.0
    assert status_after_increase.coverage_months == 2.14
    assert status_after_increase.is_completed is False
    assert status_after_increase.can_invest is False


def test_evaluate_safety_status_zero_monthly_needs():
    """Verifica que ante necesidades básicas en 0 € se indique no configurado y se bloqueen inversiones."""
    fund = EmergencyFund(current_balance=2000.0, target_months=3)
    status = evaluate_safety_status(fund, monthly_needs=0.0)

    assert status.can_invest is False
    assert status.is_completed is False
    assert "no configurado" in status.message


def test_sync_fund_state():
    """Verifica la persistencia de target_amount e is_completed en la entidad de base de datos."""
    fund = EmergencyFund(current_balance=3500.0, target_months=3)
    sync_fund_state(fund, monthly_needs=1000.0)

    assert fund.target_amount == 3000.0
    assert fund.is_completed is True

