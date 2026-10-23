"""
Servicio del Dominio: Salvaguarda de Seguridad Patrimonial (Safety Guard).
Implementa la regla constitucional de protección (Principio 5):
Queda terminantemente prohibido sugerir, asignar o permitir inversiones con riesgo si el fondo
de emergencia no cubre al menos el número de meses objetivo (mínimo 3 meses) de necesidades esenciales.
"""

from backend.domain.models.emergency_fund import EmergencyFund
from backend.domain.schemas.emergency_fund import SafetyStatusResponse


def evaluate_safety_status(
    fund: EmergencyFund,
    monthly_needs: float,
) -> SafetyStatusResponse:
    """
    Evalúa la cobertura actual del fondo de emergencia frente al gasto mensual en necesidades básicas.
    Retorna un objeto estructurado SafetyStatusResponse con métricas cuantitativas y mensaje diagnóstico.
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
    Actualiza los campos target_amount e is_completed de la entidad EmergencyFund
    en función de las necesidades mensuales vigentes y el saldo actual.
    """
    status = evaluate_safety_status(fund, monthly_needs)
    fund.target_amount = status.target_amount
    fund.is_completed = status.is_completed
    return fund

