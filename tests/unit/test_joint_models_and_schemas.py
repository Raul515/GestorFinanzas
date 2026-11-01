"""
Pruebas unitarias para los modelos de dominio SQLAlchemy 2.0 y esquemas Pydantic v2
del Espacio Conjunto (Especificación 010 - Fase 1).
"""

from datetime import date, datetime, timezone
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.domain.models.joint import (
    JointAccount,
    JointCategory,
    JointSubcategory,
    JointSinkingFund,
    JointTransaction,
    JointMonthlyContribution,
)
from backend.domain.schemas.joint import (
    CohabitationStage,
    ContributionStrategy,
    SplitMode,
    ProfileIdentifier,
    SinkingFundStatus,
    SyncAction,
    SyncEntityType,
    HealthStatus,
    JointStatusResponse,
    JointAccountSetupRequest,
    JointAccountResponse,
    JointSubcategoryCreate,
    JointSubcategoryResponse,
    JointCategoryResponse,
    JointSinkingFundCreate,
    JointSinkingFundResponse,
    JointTransactionCreate,
    JointTransactionResponse,
    JointMonthlyContributionCreate,
    JointMonthlyContributionResponse,
    SyncEventPayload,
    JointAnnualSummaryResponse,
)


# ==========================================
# PRUEBAS DE MODELOS ORM Y RESTRICCIONES SQLITE
# ==========================================

def test_joint_account_singleton_and_constraints(db_session: Session):
    """Verifica que JointAccount permita exactamente un registro (id=1) y rechace un segundo registro."""
    account = JointAccount(
        id=1,
        household_name="Hogar de Prueba",
        cohabitation_stage="PRE_COHABITATION",
        contribution_strategy="NOMINAL_TEMPLATE",
        split_mode="EQUAL_50_50",
        member_a_reference_income=2500.0,
        member_b_reference_income=2000.0,
        member_a_contribution_pct=50.0,
        member_b_contribution_pct=50.0,
        local_profile="MEMBER_A",
        remote_profile="MEMBER_B",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    assert account.id == 1
    assert account.household_name == "Hogar de Prueba"
    assert account.local_profile == "MEMBER_A"

    # Intento de insertar una segunda cuenta con id=2 debe fallar por CheckConstraint (id = 1)
    second_account = JointAccount(
        id=2,
        household_name="Segundo Hogar No Permitido",
        cohabitation_stage="COHABITATION",
        contribution_strategy="INCOME_PERCENTAGE",
        split_mode="INCOME_PROPORTIONAL",
    )
    db_session.add(second_account)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_joint_account_income_non_negative_constraint(db_session: Session):
    """Verifica que los ingresos de referencia y porcentajes no admitan valores negativos o inválidos."""
    invalid_account = JointAccount(
        id=1,
        household_name="Hogar Negativo",
        member_a_reference_income=-500.0,  # Violación
    )
    db_session.add(invalid_account)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_joint_category_and_subcategory_cascade(db_session: Session):
    """Verifica la creación de categorías, subcategorías y el borrado en cascada al eliminar la cuenta."""
    account = JointAccount(
        id=1,
        household_name="Hogar Cascada",
    )
    db_session.add(account)
    db_session.commit()

    cat = JointCategory(
        joint_account_id=1,
        name="Necesidades Básicas del Hogar",
        type="JOINT_NEEDS",
    )
    db_session.add(cat)
    db_session.commit()

    subcat = JointSubcategory(
        joint_category_id=cat.id,
        name="Alquiler / Hipoteca",
        monthly_budget=900.0,
    )
    db_session.add(subcat)
    db_session.commit()

    # Comprobar relaciones navegables
    assert len(account.categories) == 1
    assert len(cat.subcategories) == 1
    assert cat.subcategories[0].name == "Alquiler / Hipoteca"

    # Borrado de la cuenta conjunta debe eliminar en cascada categorías y subcategorías
    db_session.delete(account)
    db_session.commit()

    assert db_session.query(JointCategory).count() == 0
    assert db_session.query(JointSubcategory).count() == 0


def test_joint_sinking_fund_constraints(db_session: Session):
    """Verifica restricciones de Huchas de Amortización (saldo no negativo, objetivo > 0, porcentajes válidos)."""
    account = JointAccount(id=1, household_name="Hogar Huchas")
    db_session.add(account)
    db_session.commit()

    fund = JointSinkingFund(
        joint_account_id=1,
        name="Entrada Piso",
        target_amount=30000.0,
        current_balance=5000.0,
        monthly_target_amount=500.0,
        allocation_percentage=50.0,
        status="ACTIVE",
        priority=1,
    )
    db_session.add(fund)
    db_session.commit()
    assert fund.id is not None
    assert fund.current_balance == 5000.0

    # Fallo por target_amount negativo o cero
    invalid_fund = JointSinkingFund(
        joint_account_id=1,
        name="Meta Inválida",
        target_amount=0.0,  # Violación
    )
    db_session.add(invalid_fund)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_joint_transaction_and_contribution_orm(db_session: Session):
    """Verifica transacciones del hogar con UUIDv4 y aportaciones mensuales."""
    account = JointAccount(id=1, household_name="Hogar Movimientos")
    db_session.add(account)
    db_session.commit()

    cat = JointCategory(joint_account_id=1, name="Necesidades Básicas", type="JOINT_NEEDS")
    db_session.add(cat)
    db_session.commit()

    subcat = JointSubcategory(joint_category_id=cat.id, name="Supermercado", monthly_budget=400.0)
    db_session.add(subcat)
    db_session.commit()

    tx_uuid = str(uuid.uuid4())
    tx = JointTransaction(
        uuid=tx_uuid,
        joint_account_id=1,
        date=date(2026, 11, 2),
        amount=65.50,
        description="Compra semanal Mercadona",
        joint_subcategory_id=subcat.id,
        created_by_profile="MEMBER_A",
    )
    db_session.add(tx)
    db_session.commit()

    assert tx.id is not None
    assert tx.uuid == tx_uuid
    assert tx.subcategory.name == "Supermercado"

    # Aportación mensual
    contribution = JointMonthlyContribution(
        joint_account_id=1,
        month="2026-11",
        contributor_profile="MEMBER_A",
        amount=750.0,
        contribution_date=date(2026, 11, 1),
    )
    db_session.add(contribution)
    db_session.commit()

    assert contribution.id is not None
    assert contribution.amount == 750.0
    assert contribution.month == "2026-11"


# ==========================================
# PRUEBAS DE ESQUEMAS PYDANTIC V2
# ==========================================

def test_pydantic_setup_request_validation():
    """Verifica validaciones del esquema de onboarding JointAccountSetupRequest."""
    # Caso válido
    valid_setup = JointAccountSetupRequest(
        household_name="Nuestro Hogar",
        cohabitation_stage=CohabitationStage.PRE_COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.EQUAL_50_50,
        member_a_reference_income=2400.0,
        member_b_reference_income=2100.0,
        local_profile=ProfileIdentifier.MEMBER_A,
        remote_profile=ProfileIdentifier.MEMBER_B,
    )
    assert valid_setup.household_name == "Nuestro Hogar"

    # Error si local_profile y remote_profile son idénticos
    with pytest.raises(ValidationError) as exc_info:
        JointAccountSetupRequest(
            household_name="Hogar Conflicto",
            local_profile=ProfileIdentifier.MEMBER_A,
            remote_profile=ProfileIdentifier.MEMBER_A,
        )
    assert "local_profile y remote_profile deben ser distintos" in str(exc_info.value)

    # Error si el porcentaje supera el 100%
    with pytest.raises(ValidationError):
        JointAccountSetupRequest(
            household_name="Hogar Porcentaje Excesivo",
            member_a_contribution_pct=120.0,
        )


def test_pydantic_sinking_fund_validation():
    """Verifica validación de cuotas y porcentajes en Huchas de Amortización."""
    # Caso válido
    fund = JointSinkingFundCreate(
        name="Vacaciones Japón",
        target_amount=4000.0,
        current_balance=1200.0,
        monthly_target_amount=300.0,
        allocation_percentage=30.0,
        status=SinkingFundStatus.ACTIVE,
        priority=2,
    )
    assert fund.allocation_percentage == 30.0

    # Error si target_amount <= 0
    with pytest.raises(ValidationError):
        JointSinkingFundCreate(
            name="Meta Cero",
            target_amount=0.0,
        )

    # Error si allocation_percentage > 100
    with pytest.raises(ValidationError):
        JointSinkingFundCreate(
            name="Meta Excedida",
            target_amount=1000.0,
            allocation_percentage=105.0,
        )


def test_pydantic_transaction_create_validation():
    """Verifica que la transacción conjunta exija subcategoría o hucha y genere UUID si falta."""
    # Válida con subcategoría
    tx1 = JointTransactionCreate(
        date=date(2026, 11, 5),
        amount=45.0,
        description="Factura de Internet",
        joint_subcategory_id=1,
        created_by_profile=ProfileIdentifier.MEMBER_A,
    )
    assert tx1.uuid is not None  # Auto-generado

    # Error si no tiene ni subcategoría ni hucha
    with pytest.raises(ValidationError) as exc_info:
        JointTransactionCreate(
            date=date(2026, 11, 5),
            amount=50.0,
            description="Gasto Huérfano",
            created_by_profile=ProfileIdentifier.MEMBER_B,
        )
    assert "La transacción debe asignarse a una subcategoría de necesidades o a una hucha" in str(exc_info.value)


def test_pydantic_sync_event_payload_validation():
    """Verifica el contrato de eventos delta para sincronización P2P por Syncthing."""
    valid_event_id = str(uuid.uuid4())
    valid_timestamp = "2026-11-01T19:30:00Z"

    payload = SyncEventPayload(
        event_id=valid_event_id,
        entity_type=SyncEntityType.TRANSACTION,
        action=SyncAction.UPSERT,
        origin_device_id="SYNCTHING-DEVICE-ABC1234567890",
        timestamp_utc=valid_timestamp,
        payload={"amount": 80.0, "description": "Luz y Gas"},
    )
    assert payload.event_id == valid_event_id

    # Fallo si event_id no es UUIDv4
    with pytest.raises(ValidationError):
        SyncEventPayload(
            event_id="no-es-un-uuid",
            entity_type=SyncEntityType.TRANSACTION,
            action=SyncAction.UPSERT,
            origin_device_id="DEVICE-1",
            timestamp_utc=valid_timestamp,
            payload={},
        )

    # Fallo si timestamp_utc carece de zona horaria o es inválido
    with pytest.raises(ValidationError):
        SyncEventPayload(
            event_id=str(uuid.uuid4()),
            entity_type=SyncEntityType.TRANSACTION,
            action=SyncAction.UPSERT,
            origin_device_id="DEVICE-1",
            timestamp_utc="2026-11-01 19:30:00",  # Sin indicador UTC 'Z' o offset
            payload={},
        )


def test_pydantic_annual_summary_schema_no_member_comparison():
    """Verifica que JointAnnualSummaryResponse contenga métricas globales familiares y carezca de marcadores A vs B."""
    summary = JointAnnualSummaryResponse(
        year=2026,
        total_needs_spent=14500.0,
        total_sinking_funds_saved=6000.0,
        effort_rate_pct=42.5,
        health_status=HealthStatus.SUSTAINABLE,
        monthly_metrics=[{"month": "2026-01", "needs_spent": 1200.0}],
    )
    dumped = summary.model_dump()
    assert "total_needs_spent" in dumped
    assert "total_sinking_funds_saved" in dumped
    assert "effort_rate_pct" in dumped
    # Asegurar que NO existen campos de comparación A vs B
    assert "member_a_contributed" not in dumped
    assert "member_b_contributed" not in dumped
    assert "member_a_vs_b" not in dumped
