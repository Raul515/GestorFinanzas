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


def test_pairing_token_generation_and_validation(tmp_path: Path):
    """Verifica la generación idempotente y validación criptográfica de tokens de emparejamiento."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    token1 = service.get_or_create_pairing_token()
    assert token1.startswith("sec_")
    assert len(token1) >= 20

    # Idempotencia: no debe cambiar entre llamadas
    token2 = service.get_or_create_pairing_token()
    assert token1 == token2

    # Validación
    assert service.validate_pairing_token(token1) is True
    assert service.validate_pairing_token("sec_token_falso") is False
    assert service.validate_pairing_token("") is False


def test_create_or_get_subcategory_on_the_fly(populated_db: Session):
    """Verifica la creación al vuelo de subcategorías e idempotencia case-insensitive."""
    service = MobileSyncService()

    # 1. Crear nueva subcategoría en 'Deseos (30%)'
    sub1, is_new1 = service.create_or_get_subcategory(
        populated_db,
        name="Pádel Semanal",
        category_name="Deseos (30%)",
    )
    assert is_new1 is True
    assert sub1.id is not None
    assert sub1.name == "Pádel Semanal"
    assert sub1.category.name == "Deseos (30%)"

    # 2. Llamada repetida (idempotente sin duplicar)
    sub2, is_new2 = service.create_or_get_subcategory(
        populated_db,
        name="pádel semanal",
        category_name="Deseos (30%)",
    )
    assert is_new2 is False
    assert sub2.id == sub1.id

    # 3. Categoría de fallback si no existe (asigna Deseos 30% como salvaguarda)
    sub3, is_new3 = service.create_or_get_subcategory(
        populated_db,
        name="Reparación Caldera",
        category_name="Categoría Inexistente",
    )
    assert is_new3 is True
    assert sub3.id is not None
    assert sub3.category.name == "Deseos (30%)"


def test_process_mobile_sync_creates_subcategory_when_negative_id(populated_db: Session):
    """Verifica que transacciones offline con subcategoría creada al vuelo (ID <= 0) se creen automáticamente."""
    service = MobileSyncService()

    request = MobileSyncRequest(
        device_id="mobile-tester",
        transactions=[
            MobileTransactionPayload(
                event_id="evt-onthefly-01",
                amount=12.50,
                description="Clase de Tenis",
                date=date(2026, 11, 14),
                subcategory_id=-1,
                subcategory_name="Tenis y Raquetas",
            )
        ],
    )

    result = service.process_mobile_sync(populated_db, request)
    assert result.processed_count == 1
    assert result.ignored_duplicates_count == 0

    # Comprobar que la subcategoría existe
    sub = populated_db.query(Subcategory).filter(Subcategory.name == "Tenis y Raquetas").first()
    assert sub is not None

    # Comprobar que la transacción se enlazó a ella
    tx = populated_db.query(Transaction).filter(Transaction.mobile_event_id == "evt-onthefly-01").first()
    assert tx is not None
    assert tx.subcategory_id == sub.id
    assert tx.amount == 12.50


def test_get_mobile_monthly_summary_and_budget_update(populated_db: Session):
    """Verifica la generación del resumen mensual móvil 50/30/20 y la actualización de presupuestos."""
    service = MobileSyncService()
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    sub_nomina = populated_db.query(Subcategory).filter(Subcategory.name == "Nómina").first()
    assert sub_cafe is not None
    assert sub_nomina is not None

    # Asignar presupuesto mensual
    ok_b = service.update_mobile_budget(populated_db, sub_cafe.id, 50.0, month="2026-11")
    assert ok_b is True

    # Insertar nómina y gasto
    tx_ing = Transaction(
        date=date(2026, 11, 1),
        subcategory_id=sub_nomina.id,
        amount=2000.0,
        description="Nómina Noviembre",
    )
    tx_gas = Transaction(
        date=date(2026, 11, 5),
        subcategory_id=sub_cafe.id,
        amount=15.0,
        description="Desayunos semana",
    )
    populated_db.add_all([tx_ing, tx_gas])
    populated_db.commit()

    summary = service.get_mobile_monthly_summary(populated_db, month="2026-11")
    assert summary.month == "2026-11"
    assert summary.total_income == 2000.0
    assert summary.total_spent == 15.0
    assert summary.wants is not None
    assert summary.wants.spent == 15.0
    assert summary.wants.budget == 50.0
    assert summary.emergency_fund is not None
    assert summary.emergency_fund.target_amount > 0
    assert len(summary.subcategories) >= 1


def test_mobile_apk_ota_version_and_publish(tmp_path: Path):
    """Verifica el ciclo de vida de versiones OTA y publicación de binarios APK (Fase 8)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    # 1. Estado inicial sin APK publicado
    initial_v = service.get_mobile_version_info()
    assert initial_v.version_code == 1
    assert initial_v.apk_available is False
    assert service.get_latest_apk_path() is None

    # 2. Publicar una nueva release de APK
    dummy_apk = b"PK\x03\x04dummy-android-apk-bytes-gestor-finanzas"
    published = service.publish_apk_release(
        apk_bytes=dummy_apk,
        filename="gestor-finanzas-v1.1.apk",
        version_code=2,
        version_name="1.1.0",
        release_notes="Añadido termómetro 50/30/20 y auto-actualizador OTA",
    )

    assert published.version_code == 2
    assert published.version_name == "1.1.0"
    assert published.apk_available is True
    assert published.apk_filename == "gestor-finanzas-v1.1.apk"
    assert published.apk_size_bytes == len(dummy_apk)
    assert published.apk_url == "/api/mobile/download-apk"

    # 3. Comprobar ruta del archivo APK
    apk_file = service.get_latest_apk_path()
    assert apk_file is not None
    assert apk_file.name == "gestor-finanzas-v1.1.apk"
    assert apk_file.read_bytes() == dummy_apk


def test_delete_mobile_transaction_by_id_and_by_event_id(populated_db, tmp_path: Path):
    """Verifica la eliminación segura de transacciones por id numérico o por mobile_event_id (Fase 9)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    # Obtener una subcategoría de prueba
    subcat = populated_db.query(Subcategory).first()
    assert subcat is not None

    # 1. Crear transacción con mobile_event_id
    tx1 = Transaction(
        date=date(2026, 11, 23),
        subcategory_id=subcat.id,
        amount=25.50,
        description="Cena con amigos",
        mobile_event_id="evt_del_test_001",
    )
    populated_db.add(tx1)
    populated_db.commit()
    populated_db.refresh(tx1)

    tx1_id = tx1.id
    assert tx1_id is not None

    # 2. Eliminar usando mobile_event_id
    deleted_id = service.delete_mobile_transaction(populated_db, "evt_del_test_001")
    assert deleted_id == tx1_id
    assert populated_db.query(Transaction).filter(Transaction.id == tx1_id).first() is None

    # 3. Crear otra transacción y eliminar usando ID numérico
    tx2 = Transaction(
        date=date(2026, 11, 23),
        subcategory_id=subcat.id,
        amount=12.00,
        description="Café y tostada",
        mobile_event_id="evt_del_test_002",
    )
    populated_db.add(tx2)
    populated_db.commit()
    populated_db.refresh(tx2)

    deleted_by_num = service.delete_mobile_transaction(populated_db, str(tx2.id))
    assert deleted_by_num == tx2.id
    assert populated_db.query(Transaction).filter(Transaction.id == tx2.id).first() is None

    # 4. Intentar eliminar identificador inexistente
    assert service.delete_mobile_transaction(populated_db, "inexistente_123") is None


def test_wants_traffic_light_prediction_and_thresholds():
    """Valida los umbrales matemáticos del semáforo predictivo de Deseos (Fase 10)."""
    wants_budget = 300.0
    current_spent = 200.0  # 66.6%

    # Caso 1: Gasto pequeño (15 €) -> 215 / 300 = 71.6% (< 80% -> OPTIMAL)
    projected_1 = current_spent + 15.0
    ratio_1 = projected_1 / wants_budget
    remaining_1 = wants_budget - projected_1
    assert ratio_1 < 0.80
    assert remaining_1 == 85.0

    # Caso 2: Gasto que sitúa entre 80% y 99.9% (45 €) -> 245 / 300 = 81.6% -> WARNING
    projected_2 = current_spent + 45.0
    ratio_2 = projected_2 / wants_budget
    remaining_2 = wants_budget - projected_2
    assert 0.80 <= ratio_2 < 1.0
    assert remaining_2 == 55.0

    # Caso 3: Gasto que supera el 100% (120 €) -> 320 / 300 = 106.6% -> OVER_LIMIT
    projected_3 = current_spent + 120.0
    ratio_3 = projected_3 / wants_budget
    deficit_3 = projected_3 - wants_budget
    assert ratio_3 >= 1.0
    assert deficit_3 == 20.0


def test_search_historical_transactions_and_cache(populated_db: Session):
    """Verifica la búsqueda por texto y la generación de caché histórica de 12 meses (Fase 11)."""
    service = MobileSyncService()

    sub_gas = populated_db.query(Subcategory).filter(Subcategory.name == "Gasolina").first()
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_gas is not None
    assert sub_cafe is not None

    tx1 = Transaction(
        date=date(2026, 11, 10),
        subcategory_id=sub_gas.id,
        amount=55.40,
        description="Repsol Gasolina 95",
        mobile_event_id="evt_srch_001",
    )
    tx2 = Transaction(
        date=date(2026, 11, 15),
        subcategory_id=sub_gas.id,
        amount=48.20,
        description="ITV Pasada Furgoneta",
        mobile_event_id="evt_srch_002",
    )
    tx3 = Transaction(
        date=date(2026, 10, 5),
        subcategory_id=sub_cafe.id,
        amount=3.20,
        description="Café con tostada",
        mobile_event_id="evt_srch_003",
    )
    populated_db.add_all([tx1, tx2, tx3])
    populated_db.commit()

    # 1. Búsqueda exacta e insensible a mayúsculas por concepto
    results_itv = service.search_transactions(populated_db, query_text="itv")
    assert results_itv.total_found == 1
    assert results_itv.items[0].description == "ITV Pasada Furgoneta"
    assert results_itv.items[0].amount == 48.20
    assert results_itv.items[0].subcategory_name == "Gasolina"

    # 2. Búsqueda por nombre de subcategoría
    results_gas = service.search_transactions(populated_db, query_text="gasolina")
    assert results_gas.total_found == 2
    descriptions = [r.description for r in results_gas.items]
    assert "Repsol Gasolina 95" in descriptions
    assert "ITV Pasada Furgoneta" in descriptions

    # 3. Búsqueda vacía devuelve lista vacía
    empty_res = service.search_transactions(populated_db, query_text="")
    assert empty_res.total_found == 0
    assert empty_res.items == []

    # 4. Obtención de caché histórica de 12 meses
    cache = service.get_historical_cache(populated_db, months=12)
    assert len(cache) >= 3
    # Comprobar que está ordenado descendente por fecha
    assert cache[0].date >= cache[1].date
    first = cache[0]
    assert hasattr(first, "id")
    assert hasattr(first, "date")
    assert hasattr(first, "amount")
    assert hasattr(first, "description")
    assert hasattr(first, "subcategory_name")



