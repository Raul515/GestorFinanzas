"""
Prueba de integración End-to-End (E2E) para la Cuenta Conjunta (Especificación 010 - Fase 6).
Simula la interacción completa y sincronización descentralizada entre dos dispositivos aislados
(Dispositivo A: Raúl en PC Windows, Dispositivo B: Ana en Mac) mediante buzones locales de Syncthing.
"""

from datetime import date
import os
from pathlib import Path
import shutil
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.domain.models.base import Base
from backend.domain.models import joint as joint_models
from backend.domain.models import categories as cat_models
from backend.domain.models import transactions as trans_models
from backend.domain.schemas import joint as joint_schemas
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.services.joint_sync_service import JointSyncService
from backend.services.joint_accounting_service import (
    calculate_joint_annual_summary,
    prepare_assisted_contribution,
)


@pytest.fixture
def e2e_environment():
    """Configura dos bases de datos SQLite físicamente aisladas y sus carpetas de sincronización Syncthing."""
    temp_dir = tempfile.mkdtemp(prefix="test_joint_e2e_")

    # 1. Rutas de bases de datos
    db_file_a = os.path.join(temp_dir, "finanzas_device_a.db")
    db_file_b = os.path.join(temp_dir, "finanzas_device_b.db")

    engine_a = create_engine(f"sqlite:///{db_file_a}", connect_args={"check_same_thread": False})
    engine_b = create_engine(f"sqlite:///{db_file_b}", connect_args={"check_same_thread": False})

    Base.metadata.create_all(bind=engine_a)
    Base.metadata.create_all(bind=engine_b)

    SessionLocalA = sessionmaker(autocommit=False, autoflush=False, bind=engine_a)
    SessionLocalB = sessionmaker(autocommit=False, autoflush=False, bind=engine_b)

    session_a = SessionLocalA()
    session_b = SessionLocalB()

    # Pre-poblar categorías estándar individuales en ambos dispositivos
    for sess in (session_a, session_b):
        cat_nec = cat_models.Category(id=1, name="Necesidades Básicas", type="gasto")
        sub_alq = cat_models.Subcategory(id=1, category_id=1, name="Aportación a Cuenta Conjunta")
        sub_sup = cat_models.Subcategory(id=2, category_id=1, name="Supermercado Personal")
        sess.add_all([cat_nec, sub_alq, sub_sup])
        sess.commit()

    # 2. Carpetas de sincronización
    sync_dir_a = os.path.join(temp_dir, "syncthing_device_a")
    sync_dir_b = os.path.join(temp_dir, "syncthing_device_b")

    sync_service_a = JointSyncService(base_sync_dir=sync_dir_a, local_device_id="WIN_DEVICE_RAUL")
    sync_service_b = JointSyncService(base_sync_dir=sync_dir_b, local_device_id="MAC_DEVICE_ANA")

    repo_a = SQLiteRepository(session_a)
    repo_b = SQLiteRepository(session_b)

    yield {
        "repo_a": repo_a,
        "repo_b": repo_b,
        "session_a": session_a,
        "session_b": session_b,
        "sync_service_a": sync_service_a,
        "sync_service_b": sync_service_b,
        "sync_dir_a": sync_dir_a,
        "sync_dir_b": sync_dir_b,
    }

    session_a.close()
    session_b.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def simulate_syncthing_transfer(source_sync_dir: str, target_sync_dir: str) -> int:
    """Simula la transferencia P2P de Syncthing copiando archivos delta de outbox a inbox."""
    src_outbox = Path(source_sync_dir) / "outbox"
    tgt_inbox = Path(target_sync_dir) / "inbox"
    tgt_inbox.mkdir(parents=True, exist_ok=True)

    transferred = 0
    if src_outbox.exists():
        for file in src_outbox.glob("*.json"):
            target_path = tgt_inbox / file.name
            if not target_path.exists():
                shutil.copy2(file, target_path)
                transferred += 1
    return transferred


def test_full_joint_lifecycle_e2e(e2e_environment):
    """
    Escenario End-to-End completo:
    1. Verificación de Estado Cero sin cuenta configurada (cero intrusión).
    2. Onboarding guiado en Dispositivo A y Dispositivo B.
    3. Creación de hucha de amortización en Dispositivo A.
    4. Sincronización A -> B e ingesta con LWW.
    5. Asiento asistido de aportación en 1-clic en Dispositivo A.
    6. Registro de gasto de necesidades en Dispositivo B (Supermercado).
    7. Liquidación de gasto con cargo a hucha en Dispositivo A.
    8. Sincronización bidireccional completa (A <-> B).
    9. Verificación de convergencia de saldos, huchas y Resumen Anual sin métricas A vs B.
    """
    repo_a = e2e_environment["repo_a"]
    repo_b = e2e_environment["repo_b"]
    sync_a = e2e_environment["sync_service_a"]
    sync_b = e2e_environment["sync_service_b"]
    dir_a = e2e_environment["sync_dir_a"]
    dir_b = e2e_environment["sync_dir_b"]

    # =================================================================
    # 1. ESTADO CERO: CERO INTRUSIÓN
    # =================================================================
    assert repo_a.get_joint_account() is None
    assert repo_b.get_joint_account() is None
    assert repo_a.get_joint_transactions() == []
    assert repo_b.get_joint_transactions() == []

    # =================================================================
    # 2. ONBOARDING GUIADO EN AMBOS DISPOSITIVOS
    # =================================================================
    setup_req_a = joint_schemas.JointAccountSetupRequest(
        household_name="Hogar Raúl y Ana",
        cohabitation_stage=joint_schemas.CohabitationStage.PRE_COHABITATION,
        contribution_strategy=joint_schemas.ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=joint_schemas.SplitMode.EQUAL_50_50,
        member_a_reference_income=2500.0,
        member_b_reference_income=2000.0,
        member_a_contribution_pct=50.0,
        member_b_contribution_pct=50.0,
        local_profile=joint_schemas.ProfileIdentifier.MEMBER_A,
        remote_profile=joint_schemas.ProfileIdentifier.MEMBER_B,
    )
    setup_req_b = joint_schemas.JointAccountSetupRequest(
        household_name="Hogar Raúl y Ana",
        cohabitation_stage=joint_schemas.CohabitationStage.PRE_COHABITATION,
        contribution_strategy=joint_schemas.ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=joint_schemas.SplitMode.EQUAL_50_50,
        member_a_reference_income=2500.0,
        member_b_reference_income=2000.0,
        member_a_contribution_pct=50.0,
        member_b_contribution_pct=50.0,
        local_profile=joint_schemas.ProfileIdentifier.MEMBER_B,
        remote_profile=joint_schemas.ProfileIdentifier.MEMBER_A,
    )

    account_a = repo_a.create_joint_account(setup_req_a)
    account_b = repo_b.create_joint_account(setup_req_b)
    assert account_a.id == 1
    assert account_b.id == 1

    # Obtener subcategoría de supermercado autosembrada en B
    subcats_b = repo_b.get_joint_subcategories()
    sub_sup_b = next(s for s in subcats_b if "Alimentación" in s.name)

    # =================================================================
    # 3. CREACIÓN DE HUCHA DE AMORTIZACIÓN EN DISPOSITIVO A
    # =================================================================
    fund_req = joint_schemas.JointSinkingFundCreate(
        name="Vacaciones de Verano",
        target_amount=1200.0,
        current_balance=300.0,
        monthly_target_amount=100.0,
    )
    fund_a = repo_a.create_joint_sinking_fund(fund_req)
    assert fund_a.current_balance == 300.0

    # Emitir evento delta en A
    sync_a.emit_event(
        entity_type=joint_schemas.SyncEntityType.SINKING_FUND,
        action=joint_schemas.SyncAction.UPSERT,
        payload={"name": "Vacaciones de Verano", "target_amount": 1200.0, "current_balance": 300.0, "monthly_target_amount": 100.0},
        origin_device_id=sync_a.local_device_id,
    )

    # En B aún no existe la hucha antes de sincronizar
    assert len(repo_b.get_joint_sinking_funds()) == 0

    # =================================================================
    # 4. SINCRONIZACIÓN A -> B (SYNCTHING)
    # =================================================================
    transferred = simulate_syncthing_transfer(dir_a, dir_b)
    assert transferred >= 1

    # Ingesta en Dispositivo B
    session_b = e2e_environment["session_b"]
    session_a = e2e_environment["session_a"]
    stats_b = sync_b.process_inbox(session_b)
    assert stats_b["processed_count"] >= 1

    # Verificar que B tiene ahora la hucha con saldo sincronizado
    funds_b = repo_b.get_joint_sinking_funds()
    assert len(funds_b) == 1
    assert funds_b[0].name == "Vacaciones de Verano"
    assert funds_b[0].current_balance == 300.0

    # =================================================================
    # 5. ASIENTO ASISTIDO DE INICIO DE MES EN DISPOSITIVO A
    # =================================================================
    plan = prepare_assisted_contribution(
        month="2026-11",
        contributor_profile=joint_schemas.ProfileIdentifier.MEMBER_A,
        contribution_amount=600.0,
        cohabitation_stage=joint_schemas.CohabitationStage.PRE_COHABITATION,
        personal_subcategory_id=1,
        contribution_date=date(2026, 11, 1),
        device_id=sync_a.local_device_id,
    )
    # Registrar en perfil personal de A y en cuenta conjunta de A
    from backend.domain.schemas import transactions as trans_schemas
    repo_a.create_transaction(
        trans_schemas.TransactionCreate(
            date=plan["personal_transaction"]["date"],
            amount=plan["personal_transaction"]["amount"],
            description=plan["personal_transaction"]["description"],
            subcategory_id=plan["personal_transaction"]["subcategory_id"],
        )
    )
    repo_a.create_joint_contribution(
        joint_schemas.JointMonthlyContributionCreate(
            month=plan["joint_contribution"]["month"],
            contributor_profile=plan["joint_contribution"]["contributor_profile"],
            amount=plan["joint_contribution"]["amount"],
            contribution_date=plan["joint_contribution"]["contribution_date"],
        )
    )
    # Emitir delta de la aportación
    sync_a.emit_event(
        entity_type=joint_schemas.SyncEntityType.CONTRIBUTION,
        action=joint_schemas.SyncAction.UPSERT,
        payload=plan["sync_event"]["payload"],
        origin_device_id=sync_a.local_device_id,
    )

    # =================================================================
    # 6. GASTO REGISTRADO EN DISPOSITIVO B (SUPERMERCADO COMÚN)
    # =================================================================
    tx_b = repo_b.create_joint_transaction(
        joint_schemas.JointTransactionCreate(
            amount=85.50,
            description="Compra Mercadona",
            date=date(2026, 11, 3),
            joint_subcategory_id=sub_sup_b.id,
            created_by_profile=joint_schemas.ProfileIdentifier.MEMBER_B,
        )
    )
    assert tx_b.amount == 85.50

    # Emitir delta desde Dispositivo B
    sync_b.emit_event(
        entity_type=joint_schemas.SyncEntityType.TRANSACTION,
        action=joint_schemas.SyncAction.UPSERT,
        payload={
            "uuid": tx_b.uuid,
            "amount": 85.50,
            "description": "Compra Mercadona",
            "date": "2026-11-03",
            "joint_subcategory_id": sub_sup_b.id,
            "subcategory_name": sub_sup_b.name,
            "created_by_profile": "MEMBER_B",
        },
        origin_device_id=sync_b.local_device_id,
    )

    # =================================================================
    # 7. LIQUIDACIÓN DE GASTO IMPUTADO A HUCHA EN DISPOSITIVO A
    # =================================================================
    # Raúl paga reserva hotel (150 €) imputada a la hucha "Vacaciones de Verano"
    tx_vac_a = repo_a.create_joint_transaction(
        joint_schemas.JointTransactionCreate(
            amount=150.0,
            description="Reserva Hotel Playa",
            date=date(2026, 11, 4),
            joint_sinking_fund_id=fund_a.id,
            created_by_profile=joint_schemas.ProfileIdentifier.MEMBER_A,
        )
    )
    # El saldo de la hucha en A se reduce automáticamente de 300 € a 150 €
    fund_a_updated = repo_a.get_joint_sinking_fund(fund_a.id)
    assert fund_a_updated.current_balance == 150.0

    # Emitir delta de transacción con cargo a hucha
    sync_a.emit_event(
        entity_type=joint_schemas.SyncEntityType.TRANSACTION,
        action=joint_schemas.SyncAction.UPSERT,
        payload={
            "uuid": tx_vac_a.uuid,
            "amount": 150.0,
            "description": "Reserva Hotel Playa",
            "date": "2026-11-04",
            "joint_sinking_fund_id": fund_a.id,
            "sinking_fund_name": "Vacaciones de Verano",
            "created_by_profile": "MEMBER_A",
        },
        origin_device_id=sync_a.local_device_id,
    )

    # =================================================================
    # 8. SINCRONIZACIÓN BIDIRECCIONAL COMPLETA (A <-> B)
    # =================================================================
    simulate_syncthing_transfer(dir_a, dir_b)
    simulate_syncthing_transfer(dir_b, dir_a)

    sync_a.process_inbox(session_a)
    sync_b.process_inbox(session_b)


    # =================================================================
    # 9. VERIFICACIÓN DE CONVERGENCIA Y RESUMEN ANUAL SIN MÉTRICAS A vs B
    # =================================================================
    # 1. Mismo número de transacciones en ambos equipos
    txs_a = repo_a.get_joint_transactions(year=2026)
    txs_b = repo_b.get_joint_transactions(year=2026)
    assert len(txs_a) == 2
    assert len(txs_b) == 2

    # 2. Huchas convergen al mismo saldo (150 €)
    f_a = repo_a.get_joint_sinking_funds()[0]
    f_b = repo_b.get_joint_sinking_funds()[0]
    assert f_a.current_balance == 150.0
    assert f_b.current_balance == 150.0

    # 3. Resumen Anual Consolidado
    contribs_a = repo_a.get_joint_contributions(year=2026)
    contribs_b = repo_b.get_joint_contributions(year=2026)
    annual_income_combined = (2500.0 + 2000.0) * 12

    summary_a = calculate_joint_annual_summary(
        year=2026,
        transactions=txs_a,
        contributions=contribs_a,
        sinking_funds=[f_a],
        annual_combined_income=annual_income_combined,
    )
    summary_b = calculate_joint_annual_summary(
        year=2026,
        transactions=txs_b,
        contributions=contribs_b,
        sinking_funds=[f_b],
        annual_combined_income=annual_income_combined,
    )

    # Ambos dispositivos obtienen exactamente las mismas cifras
    assert summary_a.total_needs_spent == summary_b.total_needs_spent == 85.50
    assert summary_a.total_sinking_funds_saved == summary_b.total_sinking_funds_saved == 150.0
    assert summary_a.effort_rate_pct == summary_b.effort_rate_pct
    assert summary_a.health_status == joint_schemas.HealthStatus.SUSTAINABLE

    # Regla innegociable: el modelo y resumen NO contienen campos de desglose A vs B
    summary_dict = summary_a.model_dump()
    forbidden_keys = ["member_a_contributed", "member_b_contributed", "member_a_total", "member_b_total"]
    for key in forbidden_keys:
        assert key not in summary_dict
