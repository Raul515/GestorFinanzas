"""
Pruebas Unitarias para el Servicio de Sincronización Móvil Quick-Capture (Spec 016).
Valida contratos Pydantic v2, catálogo móvil, deduplicación e idempotencia,
resolución por nombre y procesamiento de buzón de ficheros.
"""

from datetime import date
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileCatalogResponse,
    MobileSyncRequest,
    MobileTransactionPayload,
)
from backend.services.mobile_sync_service import MobileSyncService


@pytest.fixture
def populated_db(db_session: Session) -> Session:
    """Prepara categorías y subcategorías estándar de prueba."""
    cat_nec = Category(name="Necesidades Básicas (50%)", type="expense")
    cat_des = Category(name="Deseos (30%)", type="expense")
    cat_aho = Category(name="Ahorro e Inversión (20%)", type="expense")
    cat_ing = Category(name="Ingresos Netos", type="income")
    db_session.add_all([cat_nec, cat_des, cat_aho, cat_ing])
    db_session.commit()

    assert cat_nec.id is not None
    assert cat_des.id is not None
    assert cat_ing.id is not None

    sub_cafe = Subcategory(name="Café y Desayunos", category_id=cat_des.id)
    sub_super = Subcategory(name="Supermercado", category_id=cat_nec.id)
    sub_rest = Subcategory(name="Restaurante", category_id=cat_des.id)
    sub_gas = Subcategory(name="Gasolina", category_id=cat_nec.id)
    sub_salario = Subcategory(name="Nómina", category_id=cat_ing.id)

    db_session.add_all([sub_cafe, sub_super, sub_rest, sub_gas, sub_salario])
    db_session.commit()
    return db_session


def test_mobile_payload_schema_validations():
    """Verifica las restricciones defensivas del esquema MobileTransactionPayload."""
    # Válido
    payload = MobileTransactionPayload(
        event_id="evt-1234",
        amount=2.50,
        description="Café con leche",
        date=date(2026, 11, 13),
        subcategory_id=1,
    )
    assert payload.amount == 2.50
    assert payload.scope == "PERSONAL"

    # Rechazo si el importe es <= 0
    with pytest.raises(ValidationError):
        MobileTransactionPayload(
            event_id="evt-1234",
            amount=0.0,
            description="Café",
            date=date(2026, 11, 13),
            subcategory_id=1,
        )

    with pytest.raises(ValidationError):
        MobileTransactionPayload(
            event_id="evt-1234",
            amount=-5.0,
            description="Café",
            date=date(2026, 11, 13),
            subcategory_id=1,
        )

    # Rechazo si el concepto está vacío
    with pytest.raises(ValidationError):
        MobileTransactionPayload(
            event_id="evt-1234",
            amount=3.0,
            description="",
            date=date(2026, 11, 13),
            subcategory_id=1,
        )


def test_get_mobile_catalog_structure_and_frequency(populated_db: Session):
    """Verifica la generación del catálogo y la detección de subcategorías frecuentes."""
    service = MobileSyncService()

    # Catálogo inicial sin transacciones previas
    catalog = service.get_mobile_catalog(populated_db, local_device_id="test-host")
    assert isinstance(catalog, MobileCatalogResponse)
    assert catalog.device_id == "test-host"
    assert len(catalog.personal_subcategories) == 5

    # Insertar transacciones para simular uso recurrente de Café y Supermercado
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    sub_super = populated_db.query(Subcategory).filter(Subcategory.name == "Supermercado").first()
    assert sub_cafe is not None
    assert sub_super is not None

    for _ in range(5):
        populated_db.add(Transaction(
            date=date.today(),
            subcategory_id=sub_cafe.id,
            amount=1.50,
            description="Café solo",
        ))
    for _ in range(3):
        populated_db.add(Transaction(
            date=date.today(),
            subcategory_id=sub_super.id,
            amount=22.30,
            description="Compra Mercadona",
        ))
    populated_db.commit()

    # Recalcular catálogo
    updated_catalog = service.get_mobile_catalog(populated_db)
    frequent_subs = [s for s in updated_catalog.personal_subcategories if s.is_frequent]
    frequent_names = [s.name for s in frequent_subs]

    assert "Café y Desayunos" in frequent_names
    assert "Supermercado" in frequent_names
    assert "Café solo" in updated_catalog.frequent_concepts
    assert "Compra Mercadona" in updated_catalog.frequent_concepts


def test_process_mobile_sync_insertion(populated_db: Session):
    """Valida la inserción atómica de un lote de transacciones móviles."""
    service = MobileSyncService()
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    request = MobileSyncRequest(
        device_id="pixel-phone",
        transactions=[
            MobileTransactionPayload(
                event_id="uuid-mobile-001",
                amount=2.40,
                description="Café con tostada",
                date=date(2026, 11, 13),
                subcategory_id=sub_cafe.id,
                subcategory_name=sub_cafe.name,
            ),
            MobileTransactionPayload(
                event_id="uuid-mobile-002",
                amount=14.50,
                description="Almuerzo rápido",
                date=date(2026, 11, 13),
                subcategory_id=sub_cafe.id,
                subcategory_name=sub_cafe.name,
            ),
        ],
    )

    response = service.process_mobile_sync(populated_db, request)
    assert response.success is True
    assert response.processed_count == 2
    assert response.ignored_duplicates_count == 0

    # Comprobar en base de datos
    txs = populated_db.query(Transaction).filter(Transaction.mobile_event_id.in_(["uuid-mobile-001", "uuid-mobile-002"])).all()
    assert len(txs) == 2
    assert any(t.description == "Café con tostada" and t.amount == 2.40 for t in txs)
    assert any(t.description == "Almuerzo rápido" and t.amount == 14.50 for t in txs)


def test_process_mobile_sync_idempotency_and_duplicates(populated_db: Session):
    """Verifica que el reintento del mismo lote o mismo UUID ignora duplicados (idempotencia)."""
    service = MobileSyncService()
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    request = MobileSyncRequest(
        device_id="pixel-phone",
        transactions=[
            MobileTransactionPayload(
                event_id="uuid-dup-test",
                amount=3.20,
                description="Café de especialidad",
                date=date(2026, 11, 13),
                subcategory_id=sub_cafe.id,
            )
        ],
    )

    # 1. Primera sincronización
    res1 = service.process_mobile_sync(populated_db, request)
    assert res1.processed_count == 1
    assert res1.ignored_duplicates_count == 0

    # 2. Reintento idéntico (misma petición de red)
    res2 = service.process_mobile_sync(populated_db, request)
    assert res2.processed_count == 0
    assert res2.ignored_duplicates_count == 1

    # 3. Verificar que solo existe 1 registro en base de datos
    count = populated_db.query(Transaction).filter(Transaction.mobile_event_id == "uuid-dup-test").count()
    assert count == 1


def test_process_mobile_sync_fallback_by_name(populated_db: Session):
    """Verifica la resolución por nombre de subcategoría si el ID no existe en el destino."""
    service = MobileSyncService()

    # ID inexistente 9999 pero nombre coincide con 'Supermercado'
    request = MobileSyncRequest(
        device_id="pixel-phone",
        transactions=[
            MobileTransactionPayload(
                event_id="uuid-fallback-01",
                amount=45.10,
                description="Compra fin de semana",
                date=date(2026, 11, 13),
                subcategory_id=9999,
                subcategory_name="Supermercado",
            )
        ],
    )

    res = service.process_mobile_sync(populated_db, request)
    assert res.processed_count == 1

    tx = populated_db.query(Transaction).filter(Transaction.mobile_event_id == "uuid-fallback-01").first()
    assert tx is not None
    assert tx.subcategory is not None
    assert tx.subcategory.name == "Supermercado"


def test_process_inbox_folder_and_file_rotation(populated_db: Session, tmp_path: Path):
    """Valida la ingesta de ficheros JSON en sync/mobile/inbox/ y su archivado a processed."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    # Crear fichero delta en el inbox
    inbox_file = service.inbox_dir / "evt_mob_test_001.json"
    delta_payload = {
        "event_id": "file-uuid-777",
        "scope": "PERSONAL",
        "amount": 1.80,
        "description": "Café para llevar",
        "date": "2026-11-13",
        "subcategory_id": sub_cafe.id,
        "subcategory_name": "Café y Desayunos",
        "created_at_utc": "2026-11-13T10:00:00Z",
    }
    inbox_file.write_text(json.dumps(delta_payload), encoding="utf-8")

    # Procesar buzón
    processed_count = service.process_mobile_inbox_folder(populated_db)
    assert processed_count == 1
    assert not inbox_file.exists()
    assert (service.processed_dir / "evt_mob_test_001.json").exists()

    # Comprobar en base de datos
    tx = populated_db.query(Transaction).filter(Transaction.mobile_event_id == "file-uuid-777").first()
    assert tx is not None
    assert tx.amount == 1.80


def test_export_catalog_file(populated_db: Session, tmp_path: Path):
    """Verifica que export_catalog_file genera un archivo JSON válido en disco."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    catalog_path = service.export_catalog_file(populated_db)

    assert catalog_path.exists()
    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "personal_subcategories" in data
    assert len(data["personal_subcategories"]) == 5
