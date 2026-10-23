import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.domain.models.base import Base
from backend.domain.models import categorias as cat_models
from backend.domain.models import presupuestos as pres_models
from backend.domain.models import transacciones as trans_models
from backend.database.componentes.sqlite_db import get_db
from backend.api.main import app

# In-memory SQLite engine for tests with StaticPool to keep schema in memory across threads
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a clean in-memory database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient that uses the test database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def seed_data(db_session: Session) -> dict[str, int]:
    """Seeds the standard 50/30/20 categories and essential subcategories."""
    cats = [
        {"nombre": "Ingresos Netos", "tipo": "ingreso"},
        {"nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"nombre": "Deseos", "tipo": "gasto"},
        {"nombre": "Ahorro e Inversión", "tipo": "ahorro"},
    ]
    created_cats = {}
    for c in cats:
        cat_obj = cat_models.Categoria(nombre=c["nombre"], tipo=c["tipo"])
        db_session.add(cat_obj)
        db_session.flush()
        created_cats[c["nombre"]] = cat_obj.id

    # Essential subcategories
    sub_emergencia = cat_models.Subcategoria(
        nombre="Fondo de emergencia",
        categoria_id=created_cats["Ahorro e Inversión"]
    )
    sub_alquiler = cat_models.Subcategoria(
        nombre="Alquiler / Hipoteca",
        categoria_id=created_cats["Necesidades Básicas"]
    )
    sub_ocio = cat_models.Subcategoria(
        nombre="Ocio y Salidas",
        categoria_id=created_cats["Deseos"]
    )
    sub_salario = cat_models.Subcategoria(
        nombre="Nómina",
        categoria_id=created_cats["Ingresos Netos"]
    )

    db_session.add_all([sub_emergencia, sub_alquiler, sub_ocio, sub_salario])
    db_session.commit()

    return {
        "cat_ingresos_id": created_cats["Ingresos Netos"],
        "cat_necesidades_id": created_cats["Necesidades Básicas"],
        "cat_deseos_id": created_cats["Deseos"],
        "cat_ahorro_id": created_cats["Ahorro e Inversión"],
        "sub_emergencia_id": sub_emergencia.id,
        "sub_alquiler_id": sub_alquiler.id,
        "sub_ocio_id": sub_ocio.id,
        "sub_salario_id": sub_salario.id,
    }
