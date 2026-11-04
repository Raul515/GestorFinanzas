"""
Pruebas unitarias para el motor contable desacoplado de la Cuenta Conjunta y diagnóstico de salud familiar
(Especificación 010 - Fase 2).
"""

from datetime import date
from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas.joint import (
    CohabitationStage,
    ContributionStrategy,
    HealthStatus,
    JointAccountSetupRequest,
    JointAccountUpdate,
    JointSinkingFundCreate,
    JointSinkingFundUpdate,
    JointTransactionCreate,
    JointMonthlyContributionCreate,
    JointSinkingFundTransferCreate,
    ProfileIdentifier,
    SplitMode,
)
from backend.services.joint_accounting_service import (
    calculate_monthly_contributions,
    calculate_joint_annual_summary,
    distribute_sinking_funds_allocation,
    evaluate_household_health,
    prepare_assisted_contribution,
    calculate_settlement_summary,
)


# ==========================================
# 1. PRUEBAS DE CÁLCULO DE APORTACIONES MENSUALES
# ==========================================

def test_calculate_contributions_nominal_pre_cohabitation():
    """
    En Pre-Convivencia con Estrategia Nominal:
    - Las necesidades son estrictamente 0,00 €.
    - El presupuesto total es la suma de las huchas activas.
    - Reparto 50/50 y proporcional a ingresos.
    """
    funds = [
        {"id": 1, "name": "Entrada Piso", "monthly_target_amount": 400.0, "status": "ACTIVE"},
        {"id": 2, "name": "Vacaciones", "monthly_target_amount": 200.0, "status": "ACTIVE"},
        {"id": 3, "name": "Meta Pausada", "monthly_target_amount": 100.0, "status": "PAUSED"},
    ]

    # Modalidad 50/50
    res_50 = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.PRE_COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.EQUAL_50_50,
        needs_budget=800.0,  # Debe ignorarse y forzarse a 0.00 € en Pre-Convivencia
        sinking_funds=funds,
        member_a_income=2500.0,
        member_b_income=2000.0,
    )
    assert res_50["needs_budget"] == 0.0
    assert res_50["total_household_budget"] == 600.0
    assert res_50["member_a_contribution"] == 300.0
    assert res_50["member_b_contribution"] == 300.0
    assert res_50["fund_allocations"][1] == 400.0
    assert res_50["fund_allocations"][2] == 200.0
    assert 3 not in res_50["fund_allocations"]

    # Modalidad Proporcional a ingresos (2400 € vs 1600 € -> ratio 60% / 40%)
    res_prop = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.PRE_COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.INCOME_PROPORTIONAL,
        needs_budget=0.0,
        sinking_funds=funds,
        member_a_income=2400.0,
        member_b_income=1600.0,
    )
    assert res_prop["total_household_budget"] == 600.0
    assert res_prop["member_a_contribution"] == 360.0
    assert res_prop["member_b_contribution"] == 240.0


def test_calculate_contributions_nominal_cohabitation():
    """
    En Convivencia Plena con Estrategia Nominal:
    - El presupuesto total = Necesidades Básicas + Huchas Activas.
    - Soporte de 50/50, proporcional con redondeo a 2 decimales y personalizada fija.
    """
    funds = [
        {"id": 1, "name": "Fondo Coche", "monthly_target_amount": 300.0, "status": "ACTIVE"},
        {"id": 2, "name": "Emergencia Hogar", "monthly_target_amount": 100.0, "status": "ACTIVE"},
    ]

    # Modalidad Proporcional con ingresos reales que generan decimales (2500 € vs 2000 € -> total 4500 €)
    # Total = 1200 € necesidades + 400 € huchas = 1600.00 €
    # A = 1600 * (2500/4500) = 888.89 €
    # B = 1600 - 888.89 = 711.11 €
    res = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.INCOME_PROPORTIONAL,
        needs_budget=1200.0,
        sinking_funds=funds,
        member_a_income=2500.0,
        member_b_income=2000.0,
    )
    assert res["needs_budget"] == 1200.0
    assert res["total_household_budget"] == 1600.0
    assert res["member_a_contribution"] == 888.89
    assert res["member_b_contribution"] == 711.11
    assert round(res["member_a_contribution"] + res["member_b_contribution"], 2) == 1600.00

    # Modalidad Personalizada pactada (ej. A aporta 1000 € y B aporta 600 €)
    res_custom = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.CUSTOM_FIXED,
        needs_budget=1200.0,
        sinking_funds=funds,
        member_a_income=2500.0,
        member_b_income=2000.0,
        custom_member_a_fixed=1000.0,
        custom_member_b_fixed=600.0,
    )
    assert res_custom["member_a_contribution"] == 1000.0
    assert res_custom["member_b_contribution"] == 600.0
    assert res_custom["total_household_budget"] == 1600.0


def test_calculate_contributions_income_percentage():
    """
    Estrategia B: Porcentaje de Ingresos (Top-Down Dinámico):
    - Cada miembro aporta su porcentaje pactado de su nómina real del mes.
    - En Pre-Convivencia: el 100% de lo recaudado se reparte entre las huchas según su allocation_percentage.
    - En Convivencia Plena: primero se cubren necesidades y el excedente va a las huchas.
    """
    funds = [
        {"id": 1, "name": "Entrada Piso", "allocation_percentage": 60.0, "priority": 1, "status": "ACTIVE"},
        {"id": 2, "name": "Viajes", "allocation_percentage": 40.0, "priority": 2, "status": "ACTIVE"},
    ]

    # Pre-Convivencia:
    # A = 2500 € * 20% = 500 €
    # B = 2000 € * 15% = 300 €
    # Total = 800 € -> Fondo 1 (60% = 480 €), Fondo 2 (40% = 320 €)
    res_pre = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.PRE_COHABITATION,
        contribution_strategy=ContributionStrategy.INCOME_PERCENTAGE,
        split_mode=SplitMode.EQUAL_50_50,
        needs_budget=0.0,
        sinking_funds=funds,
        member_a_income=2500.0,
        member_b_income=2000.0,
        member_a_contribution_pct=20.0,
        member_b_contribution_pct=15.0,
    )
    assert res_pre["member_a_contribution"] == 500.0
    assert res_pre["member_b_contribution"] == 300.0
    assert res_pre["total_household_budget"] == 800.0
    assert res_pre["fund_allocations"][1] == 480.0
    assert res_pre["fund_allocations"][2] == 320.0

    # Convivencia Plena con necesidades de 500 €:
    # Recaudado = 800 € -> Facturas = 500 €, Disponible huchas = 300 €
    # Fondo 1 (60% de 300 = 180 €), Fondo 2 (40% de 300 = 120 €)
    res_cohab = calculate_monthly_contributions(
        cohabitation_stage=CohabitationStage.COHABITATION,
        contribution_strategy=ContributionStrategy.INCOME_PERCENTAGE,
        split_mode=SplitMode.EQUAL_50_50,
        needs_budget=500.0,
        sinking_funds=funds,
        member_a_income=2500.0,
        member_b_income=2000.0,
        member_a_contribution_pct=20.0,
        member_b_contribution_pct=15.0,
    )
    assert res_cohab["fund_allocations"][1] == 180.0
    assert res_cohab["fund_allocations"][2] == 120.0


def test_distribute_sinking_funds_allocation_cents_exactness():
    """Verifica que distribute_sinking_funds_allocation cuadre exactamente al céntimo ante divisiones con decimales."""
    funds = [
        {"id": 1, "allocation_percentage": 33.33, "priority": 1, "status": "ACTIVE"},
        {"id": 2, "allocation_percentage": 33.33, "priority": 2, "status": "ACTIVE"},
        {"id": 3, "allocation_percentage": 33.34, "priority": 3, "status": "ACTIVE"},
    ]
    allocated = distribute_sinking_funds_allocation(funds, 100.00)
    assert sum(allocated.values()) == 100.00


# ==========================================
# 2. PRUEBAS DE DIAGNÓSTICO DE SALUD FAMILIAR
# ==========================================

def test_evaluate_household_health():
    """Verifica el semáforo determinista de la Tasa de Esfuerzo Familiar."""
    # Sostenible (<50%): 1100 € sobre 2600 € = 42.31%
    diag_sust = evaluate_household_health(1100.0, 2600.0)
    assert diag_sust.status == HealthStatus.SUSTAINABLE
    assert diag_sust.effort_rate_pct == 42.31
    assert "Hogar Sostenible" in diag_sust.message

    # Tensión (50% a 60%): 1400 € sobre 2600 € = 53.85%
    diag_tens = evaluate_household_health(1400.0, 2600.0)
    assert diag_tens.status == HealthStatus.TENSION
    assert diag_tens.effort_rate_pct == 53.85
    assert "Zona de Tensión" in diag_tens.message

    # Alerta (>60%): 1700 € sobre 2600 € = 65.38%
    diag_alert = evaluate_household_health(1700.0, 2600.0)
    assert diag_alert.status == HealthStatus.ALERT
    assert diag_alert.effort_rate_pct == 65.38
    assert "Viviendo por encima de vuestras posibilidades" in diag_alert.message

    # Caso borde sin ingresos (0 €)
    diag_zero = evaluate_household_health(0.0, 0.0)
    assert diag_zero.status == HealthStatus.SUSTAINABLE


# ==========================================
# 3. PRUEBAS DE RESUMEN ANUAL SIN DESGLOSE A VS B
# ==========================================

def test_calculate_joint_annual_summary():
    """
    Verifica que el Resumen Anual sume las necesidades y huchas del hogar
    y garantice la ausencia total de campos o métricas de comparación A vs B.
    """
    tx_needs1 = MagicMock(date=date(2026, 1, 15), amount=700.0, joint_subcategory_id=1, joint_sinking_fund_id=None)
    tx_needs2 = MagicMock(date=date(2026, 2, 20), amount=800.0, joint_subcategory_id=1, joint_sinking_fund_id=None)
    tx_sinking = MagicMock(date=date(2026, 2, 28), amount=250.0, joint_subcategory_id=None, joint_sinking_fund_id=2)

    funds = [
        MagicMock(id=1, current_balance=5000.0),
        MagicMock(id=2, current_balance=1200.0),
    ]

    contrib1 = MagicMock(month="2026-01", amount=1000.0)
    contrib2 = MagicMock(month="2026-02", amount=1000.0)

    # Ingreso anual combinado = 4500 €/mes * 12 = 54000 €
    summary = calculate_joint_annual_summary(
        year=2026,
        transactions=[tx_needs1, tx_needs2, tx_sinking],
        contributions=[contrib1, contrib2],
        sinking_funds=funds,
        annual_combined_income=54000.0,
    )

    assert summary.year == 2026
    assert summary.total_needs_spent == 1500.0
    assert summary.total_sinking_funds_saved == 6200.0
    assert summary.health_status == HealthStatus.SUSTAINABLE
    assert len(summary.monthly_metrics) == 12

    # Verificar que el mes de Enero tiene 700 € y Febrero 800 €
    assert summary.monthly_metrics[0]["needs_spent"] == 700.0
    assert summary.monthly_metrics[0]["saved_month"] == 300.0
    assert summary.monthly_metrics[1]["needs_spent"] == 800.0
    assert summary.monthly_metrics[1]["sinking_spent"] == 250.0
    assert summary.monthly_metrics[1]["saved_month"] == 200.0

    # Comprobación de blindaje: CERO marcadores individuales
    dumped = summary.model_dump()
    assert "member_a" not in str(dumped).lower()
    assert "member_b" not in str(dumped).lower()


# ==========================================
# 4. PRUEBAS DE PREPARACIÓN DE ASIENTO ASISTIDO
# ==========================================

def test_prepare_assisted_contribution():
    """Verifica la generación de la transacción personal, la aportación conjunta y el evento de sincronización."""
    res = prepare_assisted_contribution(
        month="2026-11",
        contributor_profile=ProfileIdentifier.MEMBER_A,
        contribution_amount=750.0,
        cohabitation_stage=CohabitationStage.COHABITATION,
        personal_subcategory_id=12,
        contribution_date=date(2026, 11, 1),
        device_id="TEST-PC-DEVICE-1",
    )

    # 1. Transacción personal
    p_tx = res["personal_transaction"]
    assert p_tx["amount"] == 750.0
    assert p_tx["subcategory_id"] == 12
    assert "2026-11" in p_tx["description"]

    # 2. Aportación conjunta
    j_cb = res["joint_contribution"]
    assert j_cb["month"] == "2026-11"
    assert j_cb["amount"] == 750.0
    assert j_cb["contributor_profile"] == ProfileIdentifier.MEMBER_A

    # 3. Evento para outbox
    sync_evt = res["sync_event"]
    assert sync_evt["entity_type"] == "CONTRIBUTION"
    assert sync_evt["action"] == "UPSERT"
    assert sync_evt["origin_device_id"] == "TEST-PC-DEVICE-1"
    assert sync_evt["payload"]["amount"] == 750.0


# ==========================================
# 5. PRUEBAS DE MÉTODOS CRUD EN SQLITEREPOSITORY
# ==========================================

def test_sqlite_repository_joint_crud_lifecycle(db_session: Session):
    """Verifica el ciclo de vida de persistencia en SQLiteRepository para la cuenta conjunta."""
    repo = SQLiteRepository(db_session)

    # 1. Estado Cero inicial: get_joint_account retorna None
    assert repo.get_joint_account() is None

    # 2. Creación mediante Onboarding: siembra las 4 subcategorías de necesidades por defecto
    setup_req = JointAccountSetupRequest(
        household_name="Familia Test",
        cohabitation_stage=CohabitationStage.COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.EQUAL_50_50,
        member_a_reference_income=2500.0,
        member_b_reference_income=2200.0,
        local_profile=ProfileIdentifier.MEMBER_A,
        remote_profile=ProfileIdentifier.MEMBER_B,
    )
    account = repo.create_joint_account(setup_req)
    assert account.id == 1
    assert account.household_name == "Familia Test"

    # Verificar siembra de subcategorías
    subcats = repo.get_joint_subcategories()
    assert len(subcats) == 4
    subcat_names = [s.name for s in subcats]
    assert "Vivienda (Alquiler / Hipoteca)" in subcat_names
    assert "Alimentación y Supermercado" in subcat_names

    # 3. Creación y actualización de Huchas de Amortización
    fund_req = JointSinkingFundCreate(
        name="Viaje Vacaciones",
        target_amount=2500.0,
        current_balance=400.0,
        monthly_target_amount=200.0,
        allocation_percentage=50.0,
    )
    fund1 = repo.create_joint_sinking_fund(fund_req)
    assert fund1.id is not None
    assert fund1.current_balance == 400.0

    # Crear una segunda hucha para recibir el saldo de la primera al borrarla
    fund2_req = JointSinkingFundCreate(
        name="Fondo Imprevistos",
        target_amount=3000.0,
        current_balance=600.0,
    )
    fund2 = repo.create_joint_sinking_fund(fund2_req)

    # Borrado con reasignación de saldo
    success = repo.delete_joint_sinking_fund(fund1.id, reallocate_to_fund_id=fund2.id)
    assert success is True
    db_session.refresh(fund2)
    assert fund2.current_balance == 1000.0  # 600 + 400 reasignados

    # 4. Transacciones conjuntas y afección al saldo de la hucha
    tx_req = JointTransactionCreate(
        date=date(2026, 11, 4),
        amount=150.0,
        description="Reparación caldera",
        joint_sinking_fund_id=fund2.id,
        created_by_profile=ProfileIdentifier.MEMBER_A,
    )
    tx = repo.create_joint_transaction(tx_req)
    assert tx.id is not None
    db_session.refresh(fund2)
    assert fund2.current_balance == 850.0  # 1000 - 150 gastados

    # Borrado de la transacción restaura el saldo de la hucha
    tombstone_uuid = repo.delete_joint_transaction(tx.id)
    assert tombstone_uuid == tx.uuid
    db_session.refresh(fund2)
    assert fund2.current_balance == 1000.0  # 850 + 150 restaurados

    # Caso borde: Gasto imputado a hucha con saldo 0 no crea saldo fantasma al eliminarse
    fund_zero = repo.create_joint_sinking_fund(
        JointSinkingFundCreate(name="Hucha Cero", target_amount=500.0, current_balance=0.0)
    )
    tx_zero = repo.create_joint_transaction(
        JointTransactionCreate(
            date=date(2026, 11, 4),
            amount=100.0,
            description="Gasto hucha vacía",
            joint_sinking_fund_id=fund_zero.id,
            created_by_profile=ProfileIdentifier.MEMBER_A,
        )
    )
    db_session.refresh(fund_zero)
    assert fund_zero.current_balance == 0.0
    repo.delete_joint_transaction(tx_zero.id)
    db_session.refresh(fund_zero)
    assert fund_zero.current_balance == 0.0  # No genera 100€ de la nada

    # 5. Aportación mensual
    contrib_req = JointMonthlyContributionCreate(
        month="2026-11",
        contributor_profile=ProfileIdentifier.MEMBER_A,
        amount=700.0,
        contribution_date=date(2026, 11, 1),
    )
    contrib = repo.create_joint_contribution(contrib_req)
    assert contrib.id is not None
    assert contrib.amount == 700.0

    # Consulta de aportaciones
    contribs = repo.get_joint_contributions(year=2026, month="2026-11")
    assert len(contribs) == 1


def test_generate_household_excel_export(db_session: Session):
    """Verifica que la exportacion Excel binaria genere las 3 pestanas requeridas."""
    import io
    import openpyxl  # type: ignore
    from backend.services.joint_accounting_service import generate_household_excel_export

    repo = SQLiteRepository(db_session)
    setup_req = JointAccountSetupRequest(
        household_name="Hogar Export Test",
        cohabitation_stage=CohabitationStage.COHABITATION,
        split_mode=SplitMode.EQUAL_50_50,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        member_a_reference_income=2500.0,
        member_b_reference_income=2500.0,
    )
    repo.create_joint_account(setup_req)

    fund = repo.create_joint_sinking_fund(
        JointSinkingFundCreate(name="Fondo Vacaciones", target_amount=1200.0, current_balance=500.0)
    )

    repo.create_joint_transaction(
        JointTransactionCreate(
            date=date(2026, 11, 2),
            amount=150.0,
            description="Billetes avion",
            joint_sinking_fund_id=fund.id,
            created_by_profile=ProfileIdentifier.MEMBER_A,
        )
    )

    repo.create_joint_contribution(
        JointMonthlyContributionCreate(
            month="2026-11",
            contributor_profile=ProfileIdentifier.MEMBER_A,
            amount=600.0,
            contribution_date=date(2026, 11, 1),
        )
    )

    excel_bytes = generate_household_excel_export(db_session, household_id=1)
    assert len(excel_bytes) > 0

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert "Gastos Comunes" in sheet_names
    assert "Aportaciones del Hogar" in sheet_names
    assert "Huchas de Amortizacion" in sheet_names

    ws_tx = wb["Gastos Comunes"]
    assert ws_tx.max_row >= 2



# ==========================================
# 6. PRUEBAS DE MOTOR DE LIQUIDACIÓN Y REEMBOLSO (FASE 7.3)
# ==========================================

def test_calculate_settlement_summary_empty():
    """Verifica que con lista vacía de transacciones los saldos pendientes sean 0.0."""
    res = calculate_settlement_summary([], None)
    assert res["unsettled_count"] == 0
    assert res["common_reimbursement"]["total_common_debt"] == 0.0
    assert res["direct_settlement"]["net_amount"] == 0.0
    assert res["direct_settlement"]["net_debtor"] is None


def test_calculate_settlement_summary_common_reimbursement():
    """Verifica el cálculo de deuda del fondo común hacia los miembros que adelantaron pagos."""
    account = MagicMock(split_mode="EQUAL_50_50", member_a_contribution_pct=50.0, member_b_contribution_pct=50.0)
    tx1 = MagicMock(
        amount=120.0,
        paid_by="MEMBER_A",
        settlement_mechanism="COMMON_REIMBURSEMENT",
        settlement_status="PENDING",
    )
    tx2 = MagicMock(
        amount=45.50,
        paid_by="MEMBER_B",
        settlement_mechanism="COMMON_REIMBURSEMENT",
        settlement_status="PENDING",
    )
    tx_settled = MagicMock(
        amount=300.0,
        paid_by="MEMBER_A",
        settlement_mechanism="COMMON_REIMBURSEMENT",
        settlement_status="SETTLED",
    )

    res = calculate_settlement_summary([tx1, tx2, tx_settled], account)
    assert res["unsettled_count"] == 2
    assert res["common_reimbursement"]["owes_member_a"] == 120.0
    assert res["common_reimbursement"]["owes_member_b"] == 45.50
    assert res["common_reimbursement"]["total_common_debt"] == 165.50
    assert res["direct_settlement"]["net_amount"] == 0.0


def test_calculate_settlement_summary_direct_settlement_50_50():
    """Verifica compensación directa estilo Bizum entre miembros con reparto al 50/50."""
    account = MagicMock(split_mode="EQUAL_50_50", member_a_contribution_pct=50.0, member_b_contribution_pct=50.0)
    tx1 = MagicMock(
        amount=100.0,
        paid_by="MEMBER_A",
        settlement_mechanism="DIRECT_MEMBER_SETTLEMENT",
        settlement_status="PENDING",
    )

    res = calculate_settlement_summary([tx1], account)
    assert res["unsettled_count"] == 1
    assert res["direct_settlement"]["member_b_owes_member_a"] == 50.0
    assert res["direct_settlement"]["member_a_owes_member_b"] == 0.0
    assert res["direct_settlement"]["net_debtor"] == "MEMBER_B"
    assert res["direct_settlement"]["net_creditor"] == "MEMBER_A"
    assert res["direct_settlement"]["net_amount"] == 50.0


def test_calculate_settlement_summary_direct_settlement_proportional():
    """Verifica compensación proporcional basada en ingresos (A=3000 -> 60%, B=2000 -> 40%)."""
    account = MagicMock(
        split_mode="PROPORTIONAL_INCOME",
        member_a_reference_income=3000.0,
        member_b_reference_income=2000.0,
    )
    # A paga 100€ -> B le debe 40% = 40€
    tx_a = MagicMock(
        amount=100.0,
        paid_by="MEMBER_A",
        settlement_mechanism="DIRECT_MEMBER_SETTLEMENT",
        settlement_status="PENDING",
    )
    # B paga 50€ -> A le debe 60% = 30€
    tx_b = MagicMock(
        amount=50.0,
        paid_by="MEMBER_B",
        settlement_mechanism="DIRECT_MEMBER_SETTLEMENT",
        settlement_status="PENDING",
    )

    res = calculate_settlement_summary([tx_a, tx_b], account)
    assert res["unsettled_count"] == 2
    assert res["direct_settlement"]["member_b_owes_member_a"] == 40.0
    assert res["direct_settlement"]["member_a_owes_member_b"] == 30.0
    assert res["direct_settlement"]["net_debtor"] == "MEMBER_B"
    assert res["direct_settlement"]["net_creditor"] == "MEMBER_A"
    assert res["direct_settlement"]["net_amount"] == 10.0


def test_excel_export_includes_settlement_columns(db_session: Session):
    """Verifica que el export de Excel estructurado incorpore las columnas de pago y liquidación."""
    import openpyxl  # type: ignore
    import io
    from backend.services.joint_accounting_service import generate_household_excel_export

    repo = SQLiteRepository(db_session)
    repo.create_joint_account(
        JointAccountSetupRequest(
            household_name="Hogar Test Excel Settlement",
            member_a_name="David",
            member_b_name="Raquel",
            cohabitation_stage=CohabitationStage.COHABITATION,
            contribution_strategy=ContributionStrategy.INCOME_PERCENTAGE,
            split_mode=SplitMode.EQUAL_50_50,
            member_a_reference_income=2500.0,
            member_b_reference_income=2000.0,
            local_profile=ProfileIdentifier.MEMBER_A,
        )
    )

    subcat = repo.get_joint_subcategories()[0]
    repo.create_joint_transaction(
        JointTransactionCreate(
            date=date(2026, 11, 2),
            amount=85.0,
            description="Compra Supermercado Adelantada David",
            joint_subcategory_id=subcat.id,
            created_by_profile=ProfileIdentifier.MEMBER_A,
            paid_by="MEMBER_A",
            settlement_mechanism="COMMON_REIMBURSEMENT",
        )
    )

    excel_bytes = generate_household_excel_export(db_session, household_id=1)
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws_tx = wb["Gastos Comunes"]
    headers = [cell.value for cell in ws_tx[1]]

    assert "Medio de Pago" in headers
    assert "Modalidad Liquidacion" in headers
    assert "Estado Reembolso" in headers
    assert "Fecha Liquidacion" in headers


def test_sqlite_repository_sinking_fund_transfer(db_session: Session):
    """Verifica el rebalanceo atómico de saldos entre huchas y el registro de auditoría (Fase 7.4)."""
    repo = SQLiteRepository(db_session)
    repo.create_joint_account(
        JointAccountSetupRequest(
            household_name="Hogar Test Rebalanceo",
            cohabitation_stage=CohabitationStage.COHABITATION,
            contribution_strategy=ContributionStrategy.INCOME_PERCENTAGE,
            split_mode=SplitMode.EQUAL_50_50,
            member_a_reference_income=2500.0,
            member_b_reference_income=2000.0,
            local_profile=ProfileIdentifier.MEMBER_A,
        )
    )

    fund_a = repo.create_joint_sinking_fund(
        JointSinkingFundCreate(name="Vacaciones", target_amount=1500.0, current_balance=500.0)
    )
    fund_b = repo.create_joint_sinking_fund(
        JointSinkingFundCreate(name="Mantenimiento Coche", target_amount=800.0, current_balance=100.0)
    )

    # 1. Traspaso exitoso de 150€ de A a B
    req = JointSinkingFundTransferCreate(
        source_fund_id=fund_a.id,
        target_fund_id=fund_b.id,
        amount=150.0,
        notes="Reasignación viaje a revisión taller",
        created_by_profile=ProfileIdentifier.MEMBER_A,
    )
    transfer = repo.transfer_sinking_fund_balance(req)
    assert transfer.id is not None
    assert transfer.amount == 150.0

    db_session.refresh(fund_a)
    db_session.refresh(fund_b)
    assert fund_a.current_balance == 350.0
    assert fund_b.current_balance == 250.0

    # 2. Consultar historial
    history = repo.get_joint_sinking_fund_transfers()
    assert len(history) == 1
    assert history[0].source_fund_id == fund_a.id
    assert history[0].target_fund_id == fund_b.id
    assert history[0].amount == 150.0

    # 3. Intentar transferir más del saldo disponible arroja ValueError
    with pytest.raises(ValueError, match="Saldo insuficiente"):
        repo.transfer_sinking_fund_balance(
            JointSinkingFundTransferCreate(
                source_fund_id=fund_a.id,
                target_fund_id=fund_b.id,
                amount=400.0,  # Disponible: 350€
            )
        )

    # 4. Intentar transferir a la misma hucha arroja ValueError
    with pytest.raises(ValueError, match="distintas"):
        repo.transfer_sinking_fund_balance(
            JointSinkingFundTransferCreate(
                source_fund_id=fund_a.id,
                target_fund_id=fund_a.id,
                amount=50.0,
            )
        )
