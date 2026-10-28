import datetime
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas.transactions import TransactionCreate


def test_delete_standard_transaction(db_session: Session, seed_data: dict[str, int]):
    """Verifica que una transacción estándar se elimine correctamente y no afecte al fondo de emergencia."""
    repo = SQLiteRepository(db_session)
    fund = repo.get_or_create_emergency_fund()
    initial_fund_balance = fund.current_balance

    tx_create = TransactionCreate(
        date=datetime.date(2026, 10, 15),
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=850.0,
        description="Pago mensual de alquiler",
    )
    tx = repo.create_transaction(tx_create)
    assert tx.id is not None
    assert len(repo.get_transactions(month="2026-10")) == 1

    # Eliminar la transacción
    deleted = repo.delete_transaction(tx.id)
    assert deleted is True

    # Verificar que ya no existe en el repositorio
    assert len(repo.get_transactions(month="2026-10")) == 0
    refreshed_fund = repo.get_or_create_emergency_fund()
    assert refreshed_fund.current_balance == initial_fund_balance


def test_delete_emergency_fund_transaction_reverts_balance(db_session: Session, seed_data: dict[str, int]):
    """Verifica que al eliminar una aportación al Fondo de Emergencia, se descuente atómicamente del saldo acumulado."""
    repo = SQLiteRepository(db_session)
    repo.update_emergency_fund(target_months=3, current_balance=1000.0)

    # Registrar aportación de 300 €
    tx_create = TransactionCreate(
        date=datetime.date(2026, 10, 20),
        subcategory_id=seed_data["sub_emergencia_id"],
        amount=300.0,
        description="Aportación extraordinaria a fondo",
    )
    tx = repo.create_transaction(tx_create)

    # El saldo acumulado debe haberse incrementado a 1300 €
    fund_after_creation = repo.get_or_create_emergency_fund()
    assert fund_after_creation.current_balance == 1300.0

    # Eliminar la transacción
    deleted = repo.delete_transaction(tx.id)
    assert deleted is True

    # El saldo debe revertirse exactamente a 1000 €
    fund_after_deletion = repo.get_or_create_emergency_fund()
    assert fund_after_deletion.current_balance == 1000.0
    assert len(repo.get_transactions(month="2026-10")) == 0


def test_delete_emergency_fund_transaction_balance_never_negative(db_session: Session, seed_data: dict[str, int]):
    """Verifica que si la deducción excede el saldo acumulado actual, el saldo quede acotado a 0.0."""
    repo = SQLiteRepository(db_session)
    repo.update_emergency_fund(target_months=3, current_balance=50.0)

    # Creamos transacción con amount 100.0 (al crearse sube a 150.0)
    tx_create = TransactionCreate(
        date=datetime.date(2026, 10, 22),
        subcategory_id=seed_data["sub_emergencia_id"],
        amount=100.0,
        description="Aportación previa",
    )
    tx = repo.create_transaction(tx_create)

    # Forzamos manualmente el saldo a 20.0 para probar el límite inferior de seguridad
    repo.update_emergency_fund(current_balance=20.0)

    # Al eliminar 100.0, 20.0 - 100.0 no debe ser -80.0 sino 0.0
    deleted = repo.delete_transaction(tx.id)
    assert deleted is True

    fund = repo.get_or_create_emergency_fund()
    assert fund.current_balance == 0.0


def test_delete_non_existent_transaction(db_session: Session):
    """Verifica que intentar eliminar una transacción inexistente retorne False de forma segura."""
    repo = SQLiteRepository(db_session)
    result = repo.delete_transaction(999999)
    assert result is False


def test_delete_transaccion_alias(db_session: Session, seed_data: dict[str, int]):
    """Verifica que el método alias delete_transaccion funcione idénticamente."""
    repo = SQLiteRepository(db_session)
    tx_create = TransactionCreate(
        date=datetime.date(2026, 10, 10),
        subcategory_id=seed_data["sub_ocio_id"],
        amount=45.0,
        description="Cena con amigos",
    )
    tx = repo.create_transaction(tx_create)

    deleted = repo.delete_transaccion(tx.id)
    assert deleted is True
    assert len(repo.get_transactions(month="2026-10")) == 0
