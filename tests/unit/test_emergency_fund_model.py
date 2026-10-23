import pytest
from sqlalchemy.orm import Session
from backend.database.componentes.sqlite_crud import SQLiteRepository


def test_get_or_create_emergency_fund_defaults(db_session: Session):
    repo = SQLiteRepository(db_session)
    fund = repo.get_or_create_emergency_fund()

    assert fund.id is not None
    assert fund.current_balance == 0.0
    assert fund.target_months == 3
    assert fund.target_amount == 0.0
    assert fund.is_completed is False


def test_update_emergency_fund_valid(db_session: Session):
    repo = SQLiteRepository(db_session)
    fund = repo.update_emergency_fund(target_months=6, current_balance=4500.0)

    assert fund.target_months == 6
    assert fund.current_balance == 4500.0


def test_update_emergency_fund_rejects_under_3_months(db_session: Session):
    repo = SQLiteRepository(db_session)
    with pytest.raises(ValueError, match="no puede ser inferior a 3"):
        repo.update_emergency_fund(target_months=2)


def test_adjust_emergency_fund_balance(db_session: Session):
    repo = SQLiteRepository(db_session)
    # Set initial balance to 1000
    repo.update_emergency_fund(current_balance=1000.0)

    # Monthly contribution: +250
    fund = repo.adjust_emergency_fund_balance(250.0)
    assert fund.current_balance == 1250.0

    # Emergency withdrawal: -500
    fund = repo.adjust_emergency_fund_balance(-500.0)
    assert fund.current_balance == 750.0

    # Large withdrawal: cannot go below 0.0
    fund = repo.adjust_emergency_fund_balance(-2000.0)
    assert fund.current_balance == 0.0
