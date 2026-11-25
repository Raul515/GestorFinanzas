"""
Servicio del Dominio: Salvaguarda de Seguridad Patrimonial (Safety Guard).
Implementa la regla constitucional de protección (Principio 5):
Queda terminantemente prohibido sugerir, asignar o permitir inversiones con riesgo si el fondo
de emergencia no cubre al menos el número de meses objetivo (mínimo 3 meses) de necesidades esenciales.
"""

import calendar
import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from backend.domain.constants import CategoryBlock, classify_category_block
from backend.domain.models import budgets as pres_models
from backend.domain.models import categories as cat_models
from backend.domain.models import transactions as tx_models
from backend.domain.models.emergency_fund import EmergencyFund
from backend.domain.schemas.emergency_fund import SafetyStatusResponse


def get_effective_monthly_budgets(db: Session, month: str) -> List[pres_models.MonthlyBudget]:
    """
    Retorna los presupuestos efectivos del mes indicado fusionando por subcategoría
    las asignaciones específicas de `month` sobre la plantilla predeterminada `BASE`.
    """
    base_list = (
        db.query(pres_models.MonthlyBudget)
        .filter(pres_models.MonthlyBudget.month == "BASE")
        .all()
    )
    if month == "BASE":
        return base_list

    specific_list = (
        db.query(pres_models.MonthlyBudget)
        .filter(pres_models.MonthlyBudget.month == month)
        .all()
    )
    if not specific_list:
        return [
            pres_models.MonthlyBudget(
                id=0, month=month, subcategory_id=b.subcategory_id, amount=b.amount
            )
            for b in base_list
        ]

    merged: Dict[int, pres_models.MonthlyBudget] = {}
    for b in base_list:
        merged[b.subcategory_id] = pres_models.MonthlyBudget(
            id=0, month=month, subcategory_id=b.subcategory_id, amount=b.amount
        )
    for s in specific_list:
        merged[s.subcategory_id] = s
    return list(merged.values())


def resolve_monthly_needs(db: Session, mes: Optional[str] = None) -> float:
    """
    Calcula el gasto mensual de referencia presupuestado en Necesidades Básicas
    para un mes, su fusión con BASE o el fallback histórico más reciente.
    """
    categories = db.query(cat_models.Category).all()
    cat_nec = next(
        (c for c in categories if classify_category_block(c) == CategoryBlock.NEEDS),
        None,
    )
    if not cat_nec:
        return 0.0

    subcats = (
        db.query(cat_models.Subcategory)
        .filter(cat_models.Subcategory.category_id == cat_nec.id)
        .all()
    )
    subcat_ids = {s.id for s in subcats}
    if not subcat_ids:
        return 0.0

    target_mes = mes or datetime.date.today().strftime("%Y-%m")
    effective = get_effective_monthly_budgets(db, target_mes)
    val = sum(float(p.amount or 0.0) for p in effective if p.subcategory_id in subcat_ids)
    if val > 0:
        return round(val, 2)

    # Fallback 1: Mes más reciente con presupuesto de Necesidades configurado (> 0)
    recent_budget_rows = (
        db.query(pres_models.MonthlyBudget)
        .filter(
            pres_models.MonthlyBudget.subcategory_id.in_(subcat_ids),
            pres_models.MonthlyBudget.amount > 0,
            pres_models.MonthlyBudget.month != "BASE",
        )
        .order_by(pres_models.MonthlyBudget.month.desc())
        .all()
    )
    seen_months: List[str] = []
    for row in recent_budget_rows:
        if row.month not in seen_months:
            seen_months.append(row.month)
    for m_str in seen_months:
        m_pres = (
            db.query(pres_models.MonthlyBudget)
            .filter(
                pres_models.MonthlyBudget.month == m_str,
                pres_models.MonthlyBudget.subcategory_id.in_(subcat_ids),
            )
            .all()
        )
        m_val = sum(float(p.amount or 0.0) for p in m_pres)
        if m_val > 0:
            return round(m_val, 2)

    # Fallback 2: Transacciones de Necesidades registradas en el mes más reciente (rango Date exacto)
    recent_tx = (
        db.query(tx_models.Transaction)
        .filter(
            tx_models.Transaction.subcategory_id.in_(subcat_ids),
            tx_models.Transaction.amount > 0,
        )
        .order_by(tx_models.Transaction.date.desc())
        .first()
    )
    if recent_tx and recent_tx.date:
        tx_date = recent_tx.date
        last_day = calendar.monthrange(tx_date.year, tx_date.month)[1]
        start_d = datetime.date(tx_date.year, tx_date.month, 1)
        end_d = datetime.date(tx_date.year, tx_date.month, last_day)
        month_txs = (
            db.query(tx_models.Transaction)
            .filter(
                tx_models.Transaction.subcategory_id.in_(subcat_ids),
                tx_models.Transaction.date.between(start_d, end_d),
            )
            .all()
        )
        tx_sum = sum(float(t.amount or 0.0) for t in month_txs)
        if tx_sum > 0:
            return round(tx_sum, 2)

    return 0.0


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
    prev_target = fund.target_amount if fund.target_amount is not None else 0.0

    # Si no hay necesidades en el mes pero el fondo ya tiene una meta previa (> 0),
    # inferir las necesidades de referencia para mantener la consistencia global del estado
    if monthly_needs <= 0.0 and prev_target > 0:
        monthly_needs = round(prev_target / target_months, 2)

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
        investing_allowed=can_invest,
        target_3m=target_amount,
    )


def sync_fund_state(
    fund: EmergencyFund,
    monthly_needs: float,
) -> EmergencyFund:
    """
    Actualiza los campos target_amount e is_completed de la entidad EmergencyFund
    en función de las necesidades mensuales vigentes y el saldo actual.
    """
    prev_target = fund.target_amount if fund.target_amount is not None else 0.0
    status = evaluate_safety_status(fund, monthly_needs)
    if status.target_amount > 0:
        fund.target_amount = status.target_amount
        fund.is_completed = status.is_completed
    elif prev_target > 0 and fund.current_balance >= prev_target:
        fund.is_completed = True
    return fund

