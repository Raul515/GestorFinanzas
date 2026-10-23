"""
Safety Guard Domain Service.
Implements the constitutional protection rule (Principio 5):
No risk-bearing asset allocations are permitted unless the safety fund
covers at least the target number of months (minimum 3) of essential needs.
"""

from backend.domain.models.emergency_fund import EmergencyFund
from backend.domain.schemas.emergency_fund import SafetyStatusResponse


def evaluate_safety_status(
    fund: EmergencyFund,
    monthly_needs: float,
) -> SafetyStatusResponse:
    """
    Evaluates the current coverage of the emergency fund against monthly essential basic needs.
    Returns a structured SafetyStatusResponse with status metrics and diagnostic message.
    """
    monthly_needs = max(0.0, round(monthly_needs, 2))
    target_months = max(3, fund.target_months)
    current_balance = max(0.0, round(fund.current_balance, 2))
    target_amount = round(target_months * monthly_needs, 2)

    if monthly_needs <= 0.0:
        coverage_months = 0.0
        is_completed = False
        can_invest = False
        gap = 0.0
        message = (
            "Presupuesto de necesidades básicas no configurado o en 0 €. "
            "Configure sus gastos de Necesidades Básicas en la plantilla BASE "
            "para calcular su meta de seguridad."
        )
    else:
        coverage_months = round(current_balance / monthly_needs, 2)
        is_completed = current_balance >= target_amount
        can_invest = is_completed
        gap = round(max(0.0, target_amount - current_balance), 2)

        if is_completed:
            message = (
                f"Fondo de seguridad cubierto: {coverage_months:.1f} meses de gastos esenciales "
                f"({current_balance:,.2f} € acumulados frente a meta de {target_amount:,.2f} €). "
                "Habilitado para evaluar inversiones en activos de riesgo."
            )
        else:
            message = (
                f"Fondo de seguridad en construcción: {coverage_months:.1f} / {target_months} meses cubiertos "
                f"({current_balance:,.2f} € de {target_amount:,.2f} €). "
                f"Faltan {gap:,.2f} € para completar la reserva mínima. "
                "Se bloquean recomendaciones de inversión en activos de riesgo."
            )

    return SafetyStatusResponse(
        current_balance=current_balance,
        target_amount=target_amount,
        coverage_months=coverage_months,
        target_months=target_months,
        monthly_needs_reference=monthly_needs,
        is_completed=is_completed,
        can_invest=can_invest,
        gap=gap,
        message=message,
    )


def sync_fund_state(
    fund: EmergencyFund,
    monthly_needs: float,
) -> EmergencyFund:
    """
    Updates the target_amount and is_completed fields of the EmergencyFund entity
    based on the current monthly needs and current balance.
    """
    status = evaluate_safety_status(fund, monthly_needs)
    fund.target_amount = status.target_amount
    fund.is_completed = status.is_completed
    return fund
