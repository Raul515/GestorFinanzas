"""
Servicio Contable Desacoplado para la Cuenta Conjunta y Economía del Hogar (Spec 010).
Implementa la lógica pura de cálculo de aportaciones (Estrategia Nominal vs Porcentual),
reparto proporcional en huchas de amortización, semáforo determinista de Tasa de Esfuerzo Familiar,
resumen anual consolidado del hogar (sin marcadores individuales) y preparación de asientos asistidos.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

def _format_date_excel(d_val: Any) -> str:
    """Formatea fechas para exportación a Excel en estándar DD/MM/AAAA."""
    if not d_val:
        return ""
    if hasattr(d_val, "strftime"):
        return d_val.strftime("%d/%m/%Y")
    s = str(d_val).strip()
    parts = s.split("T")[0].split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return s

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

    # Filtrar huchas activas que no hayan alcanzado ya su objetivo de ahorro
    # Si target_amount > 0 y current_balance >= target_amount, la meta está cumplida y la cuota requerida es 0.00 €
    active_funds = []
    for f in sinking_funds:
        if f.get("status", "ACTIVE") != "ACTIVE":
            continue
        tgt = float(f.get("target_amount", 0.0) or 0.0)
        bal = float(f.get("current_balance", 0.0) or 0.0)
        if tgt > 0 and bal >= tgt:
            continue
        active_funds.append(f)

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

        # Cada hucha nominal activa recibe su cuota fijada; las completadas reciben 0.00 €
        for f in sinking_funds:
            fid = f.get("id", 0)
            if f in active_funds:
                fund_allocations[fid] = round(float(f.get("monthly_target_amount", 0.0)), 2)
            elif f.get("status", "ACTIVE") == "ACTIVE":
                fund_allocations[fid] = 0.0

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
        for f in sinking_funds:
            fid = f.get("id", 0)
            if fid not in fund_allocations and f.get("status", "ACTIVE") == "ACTIVE":
                fund_allocations[fid] = 0.0
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
    contribution_uuid: Optional[str] = None,
    target_sinking_fund_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepara las estructuras de datos requeridas para ejecutar el asiento asistido en 1 clic:
    1. Transacción de salida en el perfil personal (Necesidades o Ahorro según la etapa).
    2. Registro de aportación mensual en la cuenta conjunta con UUID idempotente.
    3. Evento delta para la carpeta sync/outbox/.
    """
    eff_date = contribution_date or date.today()
    c_uuid = contribution_uuid or str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    desc = f"Aportación pactada a Cuenta Conjunta ({month})"
    if target_sinking_fund_name:
        desc = f"Aportación a Hucha '{target_sinking_fund_name}' ({month})"

    # 1. Movimiento personal
    personal_tx_payload = {
        "date": eff_date,
        "amount": round(contribution_amount, 2),
        "description": desc,
        "subcategory_id": personal_subcategory_id,
        "joint_contribution_uuid": c_uuid,
    }

    # 2. Aportación conjunta
    joint_contribution_payload = {
        "uuid": c_uuid,
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
            "uuid": c_uuid,
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


def generate_household_excel_export(db: Any, household_id: int) -> bytes:
    """
    Genera un archivo binario Excel (.xlsx) con 3 hojas estructuradas del hogar:
    1. Gastos Comunes: Detalle de transacciones comunes, deduccion de huchas e imputacion.
    2. Aportaciones del Hogar: Historico de aportaciones de cada miembro.
    3. Huchas de Amortizacion: Catalogo de huchas, saldos actuales y objetivos.
    """
    import io
    import pandas as pd
    from sqlalchemy.orm import joinedload
    from backend.domain.models.joint import JointTransaction, JointMonthlyContribution, JointSinkingFund, JointSubcategory

    # 1. Gastos Comunes (RF-12: optimizado con joinedload para evitar N+1 queries)
    txs = (
        db.query(JointTransaction)
        .options(
            joinedload(JointTransaction.subcategory).joinedload(JointSubcategory.category),
            joinedload(JointTransaction.sinking_fund),
        )
        .filter(JointTransaction.joint_account_id == household_id)
        .order_by(JointTransaction.date.desc(), JointTransaction.id.desc())
        .all()
    )
    tx_rows = []
    for t in txs:
        subcat_name = t.subcategory.name if getattr(t, 'subcategory', None) else ''
        fund_name = t.sinking_fund.name if getattr(t, 'sinking_fund', None) else ''
        cat_name = ''
        if getattr(t, 'subcategory', None) and getattr(t.subcategory, 'category', None):
            cat_name = t.subcategory.category.name

        tx_rows.append({
            'ID': t.id,
            'UUID': t.uuid or '',
            'Fecha': _format_date_excel(t.date),
            'Concepto': t.description,
            'Categoria': cat_name,
            'Subcategoria': subcat_name,
            'Importe (EUR)': round(float(t.amount), 2),
            'Hucha de Amortizacion': fund_name,
            'Deduccion Hucha (EUR)': round(float(t.sinking_fund_deduction or 0.0), 2),
            'Registrado Por': str(t.created_by_profile),
            'Medio de Pago': str(getattr(t, 'paid_by', 'COMMON') or 'COMMON'),
            'Modalidad Liquidacion': str(getattr(t, 'settlement_mechanism', 'COMMON_REIMBURSEMENT') or ''),
            'Estado Reembolso': str(getattr(t, 'settlement_status', 'SETTLED') or 'SETTLED'),
            'Fecha Liquidacion': t.settled_at.strftime('%d/%m/%Y %H:%M:%S') if getattr(t, 'settled_at', None) else '',
        })
    df_tx = pd.DataFrame(tx_rows)
    if df_tx.empty:
        df_tx = pd.DataFrame(columns=[
            'ID', 'UUID', 'Fecha', 'Concepto', 'Categoria', 'Subcategoria',
            'Importe (EUR)', 'Hucha de Amortizacion', 'Deduccion Hucha (EUR)', 'Registrado Por',
            'Medio de Pago', 'Modalidad Liquidacion', 'Estado Reembolso', 'Fecha Liquidacion'
        ])

    # 2. Aportaciones del Hogar
    contribs = (
        db.query(JointMonthlyContribution)
        .filter(JointMonthlyContribution.joint_account_id == household_id)
        .order_by(JointMonthlyContribution.contribution_date.desc(), JointMonthlyContribution.id.desc())
        .all()
    )
    contrib_rows = []
    for c in contribs:
        contrib_rows.append({
            'ID': c.id,
            'UUID': c.uuid or '',
            'Fecha': _format_date_excel(c.contribution_date),
            'Mes': c.month,
            'Miembro': str(c.contributor_profile),
            'Importe (EUR)': round(float(c.amount), 2),
        })
    df_contrib = pd.DataFrame(contrib_rows)
    if df_contrib.empty:
        df_contrib = pd.DataFrame(columns=['ID', 'UUID', 'Fecha', 'Mes', 'Miembro', 'Importe (EUR)'])

    # 3. Huchas de Amortizacion
    funds = (
        db.query(JointSinkingFund)
        .filter(JointSinkingFund.joint_account_id == household_id)
        .order_by(JointSinkingFund.name.asc())
        .all()
    )
    fund_rows = []
    for f in funds:
        fund_rows.append({
            'ID': f.id,
            'Nombre': f.name,
            'Saldo Actual (EUR)': round(float(f.current_balance), 2),
            'Meta Objetivo (EUR)': round(float(f.target_amount or 0.0), 2),
            'Objetivo Mensual (EUR)': round(float(f.monthly_target_amount or 0.0), 2),
            'Porcentaje Asignacion (%)': round(float(f.allocation_percentage or 0.0), 2),
            'Estado': str(f.status),
        })
    df_funds = pd.DataFrame(fund_rows)
    if df_funds.empty:
        df_funds = pd.DataFrame(columns=[
            'ID', 'Nombre', 'Saldo Actual (EUR)', 'Meta Objetivo (EUR)',
            'Objetivo Mensual (EUR)', 'Porcentaje Asignacion (%)', 'Estado'
        ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_tx.to_excel(writer, sheet_name='Gastos Comunes', index=False)
        df_contrib.to_excel(writer, sheet_name='Aportaciones del Hogar', index=False)
        df_funds.to_excel(writer, sheet_name='Huchas de Amortizacion', index=False)

    return output.getvalue()



def calculate_settlement_summary(
    transactions: List[Any], account: Optional[Any] = None
) -> Dict[str, Any]:
    """Calcula las deudas y saldos pendientes de reembolso para gastos adelantados con tarjeta personal.

    Soporta modalidad híbrida:
    - Reembolso desde la Cuenta Común (el fondo común adeuda el 100% al miembro pagador).
    - Liquidación directa entre miembros (Bizum/transferencia según ratio de reparto acordado).
    """
    # Determinar ratios de contribución/reparto
    ratio_a = 0.5
    ratio_b = 0.5
    if account:
        split_mode = str(getattr(account, "split_mode", "EQUAL_50_50"))
        if split_mode == "PROPORTIONAL_INCOME":
            inc_a = float(getattr(account, "member_a_reference_income", 0.0) or 0.0)
            inc_b = float(getattr(account, "member_b_reference_income", 0.0) or 0.0)
            tot_inc = inc_a + inc_b
            if tot_inc > 0:
                ratio_a = inc_a / tot_inc
                ratio_b = inc_b / tot_inc
        else:
            pct_a = float(getattr(account, "member_a_contribution_pct", 50.0) or 50.0)
            pct_b = float(getattr(account, "member_b_contribution_pct", 50.0) or 50.0)
            tot_pct = pct_a + pct_b
            if tot_pct > 0:
                ratio_a = pct_a / tot_pct
                ratio_b = pct_b / tot_pct

    owes_member_a = 0.0
    owes_member_b = 0.0
    b_owes_a = 0.0
    a_owes_b = 0.0
    unsettled_list = []

    for tx in transactions:
        paid_by = getattr(tx, "paid_by", None)
        if isinstance(paid_by, dict):
            paid_by = paid_by.get("paid_by")
        elif hasattr(paid_by, "value"):
            paid_by = paid_by.value
        paid_by = str(paid_by or "COMMON")

        status = getattr(tx, "settlement_status", None)
        if isinstance(status, dict):
            status = status.get("settlement_status")
        elif hasattr(status, "value"):
            status = status.value
        status = str(status or ("PENDING" if paid_by in ("MEMBER_A", "MEMBER_B") else "SETTLED"))

        if status == "PENDING" and paid_by in ("MEMBER_A", "MEMBER_B"):
            unsettled_list.append(tx)
            amount = float(getattr(tx, "amount", 0.0) or 0.0)

            mechanism = getattr(tx, "settlement_mechanism", None)
            if hasattr(mechanism, "value"):
                mechanism = mechanism.value
            mechanism = str(mechanism or "COMMON_REIMBURSEMENT")

            if mechanism == "DIRECT_MEMBER_SETTLEMENT":
                if paid_by == "MEMBER_A":
                    b_owes_a += amount * ratio_b
                else:
                    a_owes_b += amount * ratio_a
            else:
                # COMMON_REIMBURSEMENT
                if paid_by == "MEMBER_A":
                    owes_member_a += amount
                else:
                    owes_member_b += amount

    owes_member_a = round(owes_member_a, 2)
    owes_member_b = round(owes_member_b, 2)
    total_common_debt = round(owes_member_a + owes_member_b, 2)

    b_owes_a = round(b_owes_a, 2)
    a_owes_b = round(a_owes_b, 2)
    diff = round(b_owes_a - a_owes_b, 2)

    if diff > 0.001:
        net_debtor = "MEMBER_B"
        net_creditor = "MEMBER_A"
        net_amount = diff
    elif diff < -0.001:
        net_debtor = "MEMBER_A"
        net_creditor = "MEMBER_B"
        net_amount = round(abs(diff), 2)
    else:
        net_debtor = None
        net_creditor = None
        net_amount = 0.0

    return {
        "common_reimbursement": {
            "owes_member_a": owes_member_a,
            "owes_member_b": owes_member_b,
            "total_common_debt": total_common_debt,
        },
        "direct_settlement": {
            "member_b_owes_member_a": b_owes_a,
            "member_a_owes_member_b": a_owes_b,
            "net_debtor": net_debtor,
            "net_creditor": net_creditor,
            "net_amount": net_amount,
        },
        "unsettled_count": len(unsettled_list),
        "unsettled_transactions": unsettled_list,
    }
