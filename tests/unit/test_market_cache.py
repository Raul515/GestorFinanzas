import datetime
from sqlalchemy.orm import Session
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models import market_cache as cache_model


def test_set_and_get_market_cache(db_session: Session):
    """Verifica el almacenamiento y recuperación correcta de datos cacheados con TTL de 24h."""
    repo = SQLiteRepository(db_session)
    data = {
        "indices": [{"name": "IBEX 35", "value": 11850.5}],
        "timestamp": "2026-10-23T12:00:00",
    }

    # Guardar en caché con TTL de 24 horas por defecto
    entry = repo.set_market_cache("test_key", data, ttl_hours=24)
    assert entry.key == "test_key"
    assert entry.expires_at > datetime.datetime.now()

    # Recuperar datos antes de su expiración
    retrieved = repo.get_market_cache("test_key")
    assert retrieved is not None
    assert retrieved["indices"][0]["name"] == "IBEX 35"
    assert retrieved["indices"][0]["value"] == 11850.5


def test_get_market_cache_expired(db_session: Session):
    """Verifica que entradas con fecha de expiración superada retornen None de forma transparente."""
    repo = SQLiteRepository(db_session)
    data = {"news": ["Noticia 1"]}

    # Crear una entrada ya caducada
    now = datetime.datetime.now()
    expired_entry = cache_model.MarketCache(
        key="expired_key",
        data_json='{"news": ["Noticia 1"]}',
        updated_at=now - datetime.timedelta(hours=25),
        expires_at=now - datetime.timedelta(hours=1),
    )
    db_session.add(expired_entry)
    db_session.commit()

    # Verificar que la entrada expirada retorna None
    assert repo.get_market_cache("expired_key") is None


def test_invalidate_market_cache(db_session: Session):
    """Verifica la invalidación selectiva de una clave y la invalidación global de la caché."""
    repo = SQLiteRepository(db_session)
    repo.set_market_cache("key1", {"data": 1}, ttl_hours=24)
    repo.set_market_cache("key2", {"data": 2}, ttl_hours=24)

    # Invalidar una única clave
    repo.invalidate_market_cache("key1")
    assert repo.get_market_cache("key1") is None
    assert repo.get_market_cache("key2") is not None

    # Invalidar todas las claves
    repo.invalidate_market_cache()
    assert repo.get_market_cache("key2") is None

