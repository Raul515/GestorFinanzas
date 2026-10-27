import pytest
from sqlalchemy.orm import Session
from pydantic import ValidationError

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas.watchlist import WatchlistCreate, WatchlistResponse


def test_add_and_get_watchlist_item(db_session: Session):
    """Verifica la adición y recuperación de un activo en la lista de seguimiento."""
    repo = SQLiteRepository(db_session)

    item = WatchlistCreate(
        ticker="ITX.MC",
        name="Inditex",
        sector="Consumer Cyclical",
        currency="EUR",
        price_at_addition=45.50,
        notes="Comprar si corrige a zona de 40€ con TIR > 15%",
    )

    created = repo.add_to_watchlist(item)
    assert created.ticker == "ITX.MC"
    assert created.name == "Inditex"
    assert created.sector == "Consumer Cyclical"
    assert created.currency == "EUR"
    assert created.price_at_addition == 45.50
    assert created.notes is not None
    assert "TIR > 15%" in created.notes
    assert created.created_at is not None

    watchlist = repo.get_watchlist()
    assert len(watchlist) == 1
    assert watchlist[0].ticker == "ITX.MC"


def test_watchlist_ticker_case_normalization(db_session: Session):
    """Verifica que el ticker se normalice a mayúsculas y sin espacios al persistir."""
    repo = SQLiteRepository(db_session)

    item = WatchlistCreate(
        ticker="  aapl  ",
        name="Apple Inc.",
        sector="Technology",
        currency="USD",
        price_at_addition=220.0,
    )

    created = repo.add_to_watchlist(item)
    assert created.ticker == "AAPL"

    watchlist = repo.get_watchlist()
    assert len(watchlist) == 1
    assert watchlist[0].ticker == "AAPL"


def test_add_existing_ticker_updates_record(db_session: Session):
    """Verifica que añadir un ticker existente actualice sus datos sin duplicar la fila."""
    repo = SQLiteRepository(db_session)

    item_v1 = WatchlistCreate(
        ticker="SAN.MC",
        name="Santander",
        currency="EUR",
        price_at_addition=4.20,
        notes="Primera nota",
    )
    repo.add_to_watchlist(item_v1)

    item_v2 = WatchlistCreate(
        ticker="san.mc",
        name="Banco Santander S.A.",
        sector="Financial Services",
        currency="EUR",
        price_at_addition=4.50,
        notes="Nota actualizada con nuevo precio",
    )
    updated = repo.add_to_watchlist(item_v2)

    assert updated.ticker == "SAN.MC"
    assert updated.name == "Banco Santander S.A."
    assert updated.sector == "Financial Services"
    assert updated.price_at_addition == 4.50
    assert updated.notes == "Nota actualizada con nuevo precio"

    watchlist = repo.get_watchlist()
    assert len(watchlist) == 1


def test_remove_from_watchlist_success_and_missing(db_session: Session):
    """Verifica la eliminación correcta de un activo y el manejo cuando el ticker no existe."""
    repo = SQLiteRepository(db_session)

    item = WatchlistCreate(
        ticker="IBE.MC",
        name="Iberdrola",
        price_at_addition=13.10,
    )
    repo.add_to_watchlist(item)
    assert len(repo.get_watchlist()) == 1

    # Eliminación con éxito (case-insensitive)
    removed = repo.remove_from_watchlist("ibe.mc")
    assert removed is True
    assert len(repo.get_watchlist()) == 0

    # Intento de eliminar ticker que no existe
    removed_missing = repo.remove_from_watchlist("NO_EXISTE")
    assert removed_missing is False


def test_watchlist_create_schema_validations():
    """Verifica las validaciones de datos en WatchlistCreate."""
    # Precio negativo rechazado
    with pytest.raises(ValidationError):
        WatchlistCreate(
            ticker="ITX.MC",
            name="Inditex",
            price_at_addition=-5.0,
        )

    # Ticker vacío rechazado
    with pytest.raises(ValidationError):
        WatchlistCreate(
            ticker="",
            name="Inditex",
            price_at_addition=45.0,
        )


def test_watchlist_response_from_orm(db_session: Session):
    """Verifica que WatchlistResponse serialice correctamente instancias ORM de WatchlistItem."""
    repo = SQLiteRepository(db_session)
    item = WatchlistCreate(
        ticker="MSFT",
        name="Microsoft Corp",
        sector="Technology",
        currency="USD",
        price_at_addition=425.0,
        notes="Líder en nube empresarial e IA",
    )
    db_item = repo.add_to_watchlist(item)

    response = WatchlistResponse.model_validate(db_item)
    assert response.ticker == "MSFT"
    assert response.price_at_addition == 425.0
    assert response.created_at is not None
