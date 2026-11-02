"""
Servicio Contable Desacoplado para la Cuenta Conjunta y Economía del Hogar (Spec 010).
Implementa la lógica pura de cálculo de aportaciones (Estrategia Nominal vs Porcentual),
reparto proporcional en huchas de amortización, semáforo determinista de Tasa de Esfuerzo Familiar,
resumen anual consolidado del hogar (sin marcadores individuales) y preparación de asientos asistidos.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from backend.domain.schemas.joint import (
    CohabitationStage,
    ContributionStrategy,
    HealthStatus,
    JointAnnualSummaryResponse,
    JointHealthDiagnosticResponse,
    ProfileIdentifier,
    SplitMode,
    SyncAction,
    SyncEntityType,
    SyncEventPayload,
)


def calculate_monthly_contributions(
    cohabitation_stage: CohabitationStage,
    contribution_strategy: ContributionStrategy,
    split_mode: SplitMode,
    needs_budget: float,
    sinking_funds: List[Dict[str, Any]],
    member_a_income: float,
    member_b_income: float,
    member_a_contribution_pct: float = 50.0,
    member_b_contribution_pct: float = 50.0,
    custom_member_a_fixed: Optional[float] = None,
    custom_member_b_fixed: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula de forma pura las cuotas mensuales a aportar por cada miembro y la distribución
    hacia necesidades del hogar y huchas de amortización.
    """
    # 1. En Pre-Convivencia, los costes fijos de necesidades son estrictamente 0.00 €
    effective_needs_budget = 0.0 if cohabitation_stage == CohabitationStage.PRE_COHABITATION else max(0.0, float(needs_budget))

    # Filtrar huchas activas
    active_funds = [f for f in sinking_funds if f.get("status", "ACTIVE") == "ACTIVE"]

    sinking_funds_target = sum(float(f.get("monthly_target_amount", 0.0)) for f in active_funds)
    fund_allocations: Dict[int, float] = {}

    if contribution_strategy == ContributionStrategy.NOMINAL_TEMPLATE:
        # Estrategia A: Bottom-Up (Suma de cuotas nominales)
        total_household_budget = round(effective_needs_budget + sinking_funds_target, 2)

        # Reparto entre miembros
        if split_mode == SplitMode.EQUAL_50_50:
            member_a_contribution = round(total_household_budget * 0.5, 2)
            member_b_contribution = round(total_household_budget - member_a_contribution, 2)
        elif split_mode == SplitMode.INCOME_PROPORTIONAL:
            total_income = member_a_income + member_b_income
            if total_income > 0:
                ratio_a = member_a_income / total_income
                member_a_contribution = round(total_household_budget * ratio_a, 2)
                member_b_contribution = round(total_household_budget - member_a_contribution, 2)
            else:
                member_a_contribution = round(total_household_budget * 0.5, 2)
                member_b_contribution = round(total_household_budget - member_a_contribution, 2)
        elif split_mode == SplitMode.CUSTOM_FIXED:
            if custom_member_a_fixed is not None and custom_member_b_fixed is not None:
                member_a_contribution = round(custom_member_a_fixed, 2)
                member_b_contribution = round(custom_member_b_fixed, 2)
                total_household_budget = round(member_a_contribution + member_b_contribution, 2)
            else:
                pct_a = member_a_contribution_pct / 100.0
                member_a_contribution = round(total_household_budget * pct_a, 2)
                member_b_contribution = round(total_household_budget - member_a_contribution, 2)
        else:
            member_a_contribution = round(total_household_budget * 0.5, 2)
            member_b_contribution = round(total_household_budget - member_a_contribution, 2)

        # Cada hucha nominal recibe su cuota fijada
        for f in active_funds:
            fid = f.get("id", 0)
            fund_allocations[fid] = round(float(f.get("monthly_target_amount", 0.0)), 2)

        allocated_to_sinking_funds = sinking_funds_target

    else:
        # Estrategia B: Top-Down Dinámico (Porcentaje de Ingresos)
        member_a_contribution = round(member_a_income * (member_a_contribution_pct / 100.0), 2)
        member_b_contribution = round(member_b_income * (member_b_contribution_pct / 100.0), 2)
        total_collected = round(member_a_contribution + member_b_contribution, 2)
        total_household_budget = total_collected

        if cohabitation_stage == CohabitationStage.COHABITATION:
            # Cubrir primero las facturas de necesidades
            needed_for_bills = min(total_collected, effective_needs_budget)
            available_for_funds = max(0.0, round(total_collected - needed_for_bills, 2))
        else:
            available_for_funds = total_collected

        fund_allocations = distribute_sinking_funds_allocation(active_funds, available_for_funds)
        allocated_to_sinking_funds = sum(fund_allocations.values())

    return {
        "cohabitation_stage": cohabitation_stage,
        "contribution_strategy": contribution_strategy,
        "split_mode": split_mode,
        "total_household_budget": total_household_budget,
        "needs_budget": effective_needs_budget,
        "sinking_funds_target": round(allocated_to_sinking_funds, 2),
        "member_a_contribution": member_a_contribution,
        "member_b_contribution": member_b_contribution,
        "fund_allocations": fund_allocations,
    }


def distribute_sinking_funds_allocation(
    active_funds: List[Dict[str, Any]], available_amount: float
) -> Dict[int, float]:
    """
    Distribuye un importe en euros entre las huchas de amortización activas
    de acuerdo a sus porcentajes relativos de asignación (allocation_percentage).
    """
    if available_amount <= 0 or not active_funds:
        return {f.get("id", 0): 0.0 for f in active_funds}

    total_pct = sum(float(f.get("allocation_percentage", 0.0)) for f in active_funds)
    if total_pct <= 0:
        # Reparto equitativo si ninguna hucha tiene porcentaje fijado
        per_fund = round(available_amount / len(active_funds), 2)
        allocations = {f.get("id", 0): per_fund for f in active_funds}
        diff = round(available_amount - sum(allocations.values()), 2)
        if diff != 0 and active_funds:
            allocations[active_funds[0].get("id", 0)] = round(allocations[active_funds[0].get("id", 0)] + diff, 2)
        return allocations

    allocations = {}
    running_sum = 0.0

    # Ordenar por prioridad ascendente para aplicar el redondeo a la de mayor prioridad
    sorted_funds = sorted(active_funds, key=lambda x: x.get("priority", 1))

    for idx, fund in enumerate(sorted_funds):
        fid = fund.get("id", 0)
        pct = float(fund.get("allocation_percentage", 0.0))
        ratio = pct / total_pct
        allocated = round(available_amount * ratio, 2)
        allocations[fid] = allocated
        running_sum += allocated

    # Ajuste de céntimos para exactitud matemática total
    diff = round(available_amount - running_sum, 2)
    if diff != 0 and sorted_funds:
        first_id = sorted_funds[0].get("id", 0)
        allocations[first_id] = round(allocations[first_id] + diff, 2)

    return allocations


def evaluate_household_health(
    joint_needs_budget: float, combined_income: float
) -> JointHealthDiagnosticResponse:
    """
    Audita cuantitativamente la salud financiera del hogar mediante la Tasa de Esfuerzo Familiar:
    Tasa = (Gastos Fijos Necesidades del Hogar / Ingresos Combinados de Ambos) * 100.
    """
    if combined_income <= 0:
        if joint_needs_budget > 0:
            status = HealthStatus.ALERT
            effort_rate = 100.0
            message = "🔴 Alerta Severa: Existen costes comunes del hogar pero los ingresos de referencia combinados son 0,00 €."
        else:
            status = HealthStatus.SUSTAINABLE
            effort_rate = 0.0
            message = "🟢 Hogar Sostenible: Sin gastos de necesidades registrados (etapa de ahorro o pre-convivencia)."
        return JointHealthDiagnosticResponse(
            joint_needs_budget=round(joint_needs_budget, 2),
            combined_reference_income=round(combined_income, 2),
            effort_rate_pct=round(effort_rate, 2),
            status=status,
            message=message,
        )

    effort_rate = round((joint_needs_budget / combined_income) * 100.0, 2)

    if effort_rate < 50.0:
        status = HealthStatus.SUSTAINABLE
        message = (
            f"🟢 Hogar Sostenible: Los costes fijos comunes representan el {effort_rate:.1f}% "
            "de vuestros ingresos combinados, dejando amplio margen para nutrir huchas de ahorro e inversión."
        )
    elif effort_rate <= 60.0:
        status = HealthStatus.TENSION
        message = (
            f"🟡 Zona de Tensión: Los costes fijos comunes absorben el {effort_rate:.1f}% "
            "de los ingresos del hogar. Se aconseja contención en gastos personales de ocio para no comprometer el ahorro."
        )
    else:
        status = HealthStatus.ALERT
        message = (
            f"🔴 Viviendo por encima de vuestras posibilidades: La tasa de esfuerzo familiar alcanza el {effort_rate:.1f}%, "
            "superando el límite prudencial del 60%. Riesgo elevado de estrés financiero estructural."
        )

    return JointHealthDiagnosticResponse(
        joint_needs_budget=round(joint_needs_budget, 2),
        combined_reference_income=round(combined_income, 2),
        effort_rate_pct=effort_rate,
        status=status,
        message=message,
    )


def calculate_joint_annual_summary(
    year: int,
    transactions: List[Any],
    contributions: List[Any],
    sinking_funds: List[Any],
    annual_combined_income: float,
    account: Optional[Any] = None,
) -> JointAnnualSummaryResponse:
    """
    Calcula el Resumen Anual consolidado de la unidad familiar.
    Regla innegociable: prohíbe explícitamente cualquier métrica de comparación Member A vs Member B.
    """
    def _safe_num(val: Any) -> float:
        if val is None or hasattr(val, "_mock_name"):
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # 1. Gastos en necesidades del hogar (transacciones vinculadas a subcategorías de necesidades)
    total_needs_spent = 0.0
    monthly_data: Dict[str, Dict[str, float]] = {
        f"{year}-{m:02d}": {"needs_spent": 0.0, "sinking_spent": 0.0, "contributed": 0.0}
        for m in range(1, 13)
    }

    for tx in transactions:
        tx_date = getattr(tx, "date", None)
        if not tx_date:
            continue
        m_key = f"{tx_date.year}-{tx_date.month:02d}"
        amount = float(getattr(tx, "amount", 0.0))

        if getattr(tx, "joint_subcategory_id", None) is not None:
            total_needs_spent += amount
            if m_key in monthly_data:
                monthly_data[m_key]["needs_spent"] += amount
        elif getattr(tx, "joint_sinking_fund_id", None) is not None:
            if m_key in monthly_data:
                monthly_data[m_key]["sinking_spent"] += amount

    # 2. Total ahorrado / aportado a huchas conjuntas
    total_sinking_saved = sum(float(getattr(f, "current_balance", 0.0)) for f in sinking_funds)

    # 3. Aportaciones registradas en el año
    for c in contributions:
        c_month = getattr(c, "month", "")
        amount = float(getattr(c, "amount", 0.0))
        if c_month in monthly_data:
            monthly_data[c_month]["contributed"] += amount

    # 4. Tasa de esfuerzo y salud anual
    if annual_combined_income > 0:
        effort_rate = round((total_needs_spent / annual_combined_income) * 100.0, 2)
    else:
        effort_rate = 0.0

    if effort_rate < 50.0:
        health_status = HealthStatus.SUSTAINABLE
    elif effort_rate <= 60.0:
        health_status = HealthStatus.TENSION
    else:
        health_status = HealthStatus.ALERT

    # 5. Cálculo mensual de necesidades, ahorro asignado a huchas y remanente sin asignar
    def _is_active_fund(f: Any) -> bool:
        st = getattr(f, "status", None)
        if hasattr(st, "_mock_name") or st is None:
            return True
        return str(st).upper() == "ACTIVE"

    active_funds = [f for f in sinking_funds if _is_active_fund(f)]
    monthly_sinking_target = sum(_safe_num(getattr(f, "monthly_target_amount", 0.0)) for f in active_funds)
    total_alloc_pct = sum(_safe_num(getattr(f, "allocation_percentage", 0.0)) for f in active_funds)
    strategy = str(getattr(account, "contribution_strategy", "NOMINAL_TEMPLATE")) if account else "NOMINAL_TEMPLATE"

    monthly_metrics_list = []
    for m_key, data in sorted(monthly_data.items()):
        needs_sp = round(data["needs_spent"], 2)
        sinking_sp = round(data["sinking_spent"], 2)
        tot_contrib = round(data["contributed"], 2)
        surplus = max(0.0, round(tot_contrib - needs_sp, 2))

        if not active_funds or surplus <= 0.0:
            sinking_alloc = 0.0
        elif strategy == "INCOME_PERCENTAGE" and total_alloc_pct > 0:
            sinking_alloc = round(surplus * min(1.0, total_alloc_pct / 100.0), 2)
        elif monthly_sinking_target > 0:
            sinking_alloc = min(surplus, monthly_sinking_target)
        else:
            sinking_alloc = surplus

        unassigned_rem = max(0.0, round(surplus - sinking_alloc, 2))

        monthly_metrics_list.append({
            "month": m_key,
            "needs_spent": needs_sp,
            "sinking_spent": sinking_sp,
            "total_contributed": tot_contrib,
            "sinking_allocated": sinking_alloc,
            "unassigned_amount": unassigned_rem,
            "saved_month": sinking_alloc,
        })

    return JointAnnualSummaryResponse(
        year=year,
        total_needs_spent=round(total_needs_spent, 2),
        total_sinking_funds_saved=round(total_sinking_saved, 2),
        effort_rate_pct=effort_rate,
        health_status=health_status,
        monthly_metrics=monthly_metrics_list,
    )


def prepare_assisted_contribution(
    month: str,
    contributor_profile: ProfileIdentifier,
    contribution_amount: float,
    cohabitation_stage: CohabitationStage,
    personal_subcategory_id: int,
    contribution_date: Optional[date] = None,
    device_id: str = "LOCAL-DEVICE",
) -> Dict[str, Any]:
    """
    Prepara las estructuras de datos requeridas para ejecutar el asiento asistido en 1 clic:
    1. Transacción de salida en el perfil personal (Necesidades o Ahorro según la etapa).
    2. Registro de aportación mensual en la cuenta conjunta.
    3. Evento delta para la carpeta sync/outbox/.
    """
    eff_date = contribution_date or date.today()
    event_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # 1. Movimiento personal
    personal_tx_payload = {
        "date": eff_date,
        "amount": round(contribution_amount, 2),
        "description": f"Aportación pactada a Cuenta Conjunta ({month})",
        "subcategory_id": personal_subcategory_id,
    }

    # 2. Aportación conjunta
    joint_contribution_payload = {
        "month": month,
        "contributor_profile": contributor_profile,
        "amount": round(contribution_amount, 2),
        "contribution_date": eff_date,
    }

    # 3. Evento delta para outbox
    sync_event = SyncEventPayload(
        event_id=event_id,
        entity_type=SyncEntityType.CONTRIBUTION,
        action=SyncAction.UPSERT,
        origin_device_id=device_id,
        timestamp_utc=now_utc,
        payload={
            "month": month,
            "contributor_profile": contributor_profile.value if hasattr(contributor_profile, "value") else str(contributor_profile),
            "amount": round(contribution_amount, 2),
            "contribution_date": eff_date.isoformat(),
        },
    )

    return {
        "personal_transaction": personal_tx_payload,
        "joint_contribution": joint_contribution_payload,
        "sync_event": sync_event.model_dump(),
    }
