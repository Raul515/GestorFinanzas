import os
import tempfile
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.domain.models.base import Base
from backend.domain.models import categories as cat_models
from backend.domain.models import budgets as pres_models
from backend.domain.models import transactions as trans_models
from backend.domain.models import emergency_fund as fund_models
from backend.domain.models import market_cache as cache_models
from backend.domain.models import watchlist as watchlist_models
from backend.domain.models import copilot as copilot_models
from backend.domain.models import guidelines as guideline_models
from backend.domain.models import joint as joint_models
from backend.domain.models import backup as backup_models
from backend.database.componentes.sqlite_db import get_db
from backend.api.main import app

# Motor SQLite en memoria con StaticPool para preservar el esquema entre hilos
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Proporciona una sesión de base de datos aislada y limpia en memoria para cada prueba."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def isolate_sync_folder_for_all_tests():
    """Garantiza que ningún test del sistema escriba jamás en la carpeta real sync/."""
    with tempfile.TemporaryDirectory(prefix="safe_test_sync_") as temp_dir:
        old_env = os.environ.get("BASE_SYNC_DIR")
        os.environ["BASE_SYNC_DIR"] = temp_dir
        from backend.services.joint_sync_service import JointSyncService
        from backend.api.routers.joint import get_sync_service
        test_sync = JointSyncService(base_sync_dir=temp_dir, local_device_id="TEST_MOCK_DEVICE")
        app.dependency_overrides[get_sync_service] = lambda: test_sync
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_sync_service, None)
            if old_env is not None:
                os.environ["BASE_SYNC_DIR"] = old_env
            else:
                os.environ.pop("BASE_SYNC_DIR", None)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Cliente de pruebas TestClient conectado a la base de datos de test mediante sobreescritura de dependencias."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture(scope="function")
def seed_data(db_session: Session) -> dict[str, int]:
    """Puebla las categorías estándar del sistema 50/30/20 y subcategorías esenciales para pruebas."""
    cats = [
        {"name": "Ingresos Netos", "type": "ingreso"},
        {"name": "Necesidades Básicas", "type": "gasto"},
        {"name": "Deseos", "type": "gasto"},
        {"name": "Ahorro e Inversión", "type": "ahorro"},
    ]
    created_cats = {}
    for c in cats:
        cat_obj = cat_models.Category(name=c["name"], type=c["type"])
        db_session.add(cat_obj)
        db_session.flush()
        created_cats[c["name"]] = cat_obj.id

    # Subcategorías esenciales

    sub_emergencia = cat_models.Subcategory(
        name="Fondo de emergencia",
        category_id=created_cats["Ahorro e Inversión"]
    )
    sub_alquiler = cat_models.Subcategory(
        name="Alquiler / Hipoteca",
        category_id=created_cats["Necesidades Básicas"]
    )
    sub_ocio = cat_models.Subcategory(
        name="Ocio y Salidas",
        category_id=created_cats["Deseos"]
    )
    sub_salario = cat_models.Subcategory(
        name="Nómina",
        category_id=created_cats["Ingresos Netos"]
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
