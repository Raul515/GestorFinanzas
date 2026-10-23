import datetime
from sqlalchemy.orm import Session
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models import market_cache as cache_model


def test_set_and_get_market_cache(db_session: Session):
    repo = SQLiteRepository(db_session)
    data = {
        "indices": [{"name": "IBEX 35", "value": 11850.5}],
        "timestamp": "2026-10-23T12:00:00",
    }

    # Set cache with default 24h TTL
    entry = repo.set_market_cache("test_key", data, ttl_hours=24)
    assert entry.key == "test_key"
    assert entry.expires_at > datetime.datetime.now()

    # Get cache before expiry
    retrieved = repo.get_market_cache("test_key")
    assert retrieved is not None
    assert retrieved["indices"][0]["name"] == "IBEX 35"
    assert retrieved["indices"][0]["value"] == 11850.5


def test_get_market_cache_expired(db_session: Session):
    repo = SQLiteRepository(db_session)
    data = {"news": ["Noticia 1"]}

    # Create an already expired entry
    now = datetime.datetime.now()
    expired_entry = cache_model.MarketCache(
        key="expired_key",
        data_json='{"news": ["Noticia 1"]}',
        updated_at=now - datetime.timedelta(hours=25),
        expires_at=now - datetime.timedelta(hours=1),
    )
    db_session.add(expired_entry)
    db_session.commit()

    # Verify expired cache returns None
    assert repo.get_market_cache("expired_key") is None


def test_invalidate_market_cache(db_session: Session):
    repo = SQLiteRepository(db_session)
    repo.set_market_cache("key1", {"data": 1}, ttl_hours=24)
    repo.set_market_cache("key2", {"data": 2}, ttl_hours=24)

    # Invalidate single key
    repo.invalidate_market_cache("key1")
    assert repo.get_market_cache("key1") is None
    assert repo.get_market_cache("key2") is not None

    # Invalidate all keys
    repo.invalidate_market_cache()
    assert repo.get_market_cache("key2") is None
