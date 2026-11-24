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


def test_mobile_receipt_saving_and_sync(populated_db: Session, tmp_path: Path):
    """Verifica el guardado en disco de comprobantes (base64 y binario) y su vinculación con transacciones (Fase 12)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    # 1. Guardado de receipt via base64
    fake_base64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    filename_b64 = service.save_receipt_base64("evt_rec_001", fake_base64)
    assert filename_b64 == "receipt_evt_rec_001.jpg"
    rec_path = service.get_receipt_path(filename_b64)
    assert rec_path is not None
    assert rec_path.exists()
    assert rec_path.is_file()

    # 2. Guardado de receipt via binario directo
    bin_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFfakejpgdata"
    filename_bin = service.save_receipt_file("evt_rec_002", bin_bytes)
    assert filename_bin == "receipt_evt_rec_002.jpg"
    rec_path_bin = service.get_receipt_path(filename_bin)
    assert rec_path_bin is not None
    assert rec_path_bin.exists()
    assert rec_path_bin.read_bytes() == bin_bytes

    # 3. Protección contra path traversal
    assert service.get_receipt_path("../../../etc/passwd") is None
    assert service.get_receipt_path("sub/folder/file.jpg") is None

    # 4. Sincronización con payload conteniendo base64
    req = MobileSyncRequest(
        device_id="pixel-phone",
        transactions=[
            MobileTransactionPayload(
                event_id="evt_sync_with_receipt",
                amount=12.50,
                description="Almuerzo de trabajo con ticket",
                date=date(2026, 11, 21),
                subcategory_id=sub_cafe.id,
                receipt_base64=fake_base64,
            )
        ],
    )
    res = service.process_mobile_sync(populated_db, req)
    assert res.processed_count == 1

    tx = populated_db.query(Transaction).filter(Transaction.mobile_event_id == "evt_sync_with_receipt").first()
    assert tx is not None
    assert tx.receipt_filename == "receipt_evt_sync_with_receipt.jpg"

    # 5. Búsqueda histórica incluye los campos receipt_filename y receipt_url
    search_res = service.search_transactions(populated_db, query_text="Almuerzo de trabajo")
    assert search_res.total_found >= 1
    found_item = search_res.items[0]
    assert found_item.receipt_filename == "receipt_evt_sync_with_receipt.jpg"
    assert found_item.receipt_url == "/api/mobile/receipts/receipt_evt_sync_with_receipt.jpg"


def test_mobile_income_transaction_capture_and_summary(populated_db: Session):
    """Verifica la captura de ingresos extraordinarios / bizums y su impacto en el resumen mensual (Fase 13)."""
    service = MobileSyncService()

    # 1. Comprobar que el catálogo clasifica las subcategorías por category_type ('income' vs 'expense')
    catalog = service.get_mobile_catalog(populated_db)
    sub_income = next(s for s in catalog.personal_subcategories if s.name == "Nómina")
    assert sub_income.category_type == "income"
    sub_cafe = next(s for s in catalog.personal_subcategories if s.name == "Café y Desayunos")
    assert sub_cafe.category_type == "expense"

    # 2. Sincronizar un ingreso (ej. Bizum recibido de 45.00 €)
    req = MobileSyncRequest(
        device_id="pixel-phone",
        transactions=[
            MobileTransactionPayload(
                event_id="evt_bizum_recibido_01",
                type="INCOME",
                amount=45.0,
                description="Bizum cena compartida",
                date=date(2026, 11, 22),
                subcategory_id=sub_income.id,
            )
        ],
    )
    res = service.process_mobile_sync(populated_db, req)
    assert res.processed_count == 1

    # 3. Consultar resumen mensual y verificar que el ingreso suma al total_income y recalcula remaining_budget
    summary = service.get_mobile_monthly_summary(populated_db, month_key="2026-11")
    assert summary.total_income == 45.0
    assert summary.total_spent == 0.0
    assert summary.remaining_budget == 45.0

    # 4. Comprobar que en la búsqueda y caché histórica el tipo queda marcado como INCOME
    search_res = service.search_transactions(populated_db, query_text="Bizum cena")
    assert search_res.total_found == 1
    assert search_res.items[0].type == "INCOME"
    assert search_res.items[0].amount == 45.0

    cache = service.get_historical_cache(populated_db, months=12)
    cached_bizum = next(c for c in cache if c.description == "Bizum cena compartida")
    assert cached_bizum.type == "INCOME"

    # 5. Creación al vuelo de una subcategoría de ingresos
    sub_extra, is_new = service.create_or_get_subcategory(
        populated_db,
        name="Ventas Wallapop",
        category_name="Ingresos Netos",
    )
    assert is_new is True
    assert service.is_income_category(sub_extra.category) is True


def test_mobile_performance_optimizations_and_sql_aggregation(populated_db: Session):
    """Verifica las optimizaciones de rendimiento de la Fase 15 (SQL aggregation y joinedload)."""
    service = MobileSyncService()

    # 1. Insertar transacciones para probar agregación en SQL
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    for i in range(5):
        populated_db.add(
            Transaction(
                date=date.today(),
                subcategory_id=sub_cafe.id,
                amount=1.50,
                description="Café matutino",
                mobile_event_id=f"evt_perf_cafe_{i}",
            )
        )
    populated_db.commit()

    # 2. Catálogo generado mediante SQL GROUP BY
    catalog = service.get_mobile_catalog(populated_db)
    top_cafe = next((s for s in catalog.personal_subcategories if s.id == sub_cafe.id), None)
    assert top_cafe is not None
    assert top_cafe.is_frequent is True
    assert "Café matutino" in catalog.frequent_concepts

    # 3. Caché histórica con joinedload (comprobar que resuelve categoría y subcategoría sin fallos)
    cache = service.get_historical_cache(populated_db, months=1)
    assert len(cache) >= 5
    first_item = cache[0]
    assert first_item.subcategory_name != ""
    assert first_item.category_name != ""

    # 4. Búsqueda con joinedload
    search_res = service.search_transactions(populated_db, query_text="Café matutino")
    assert search_res.total_found >= 5
    assert search_res.items[0].subcategory_name == "Café y Desayunos"


def test_sync_status_does_not_leak_pairing_token(populated_db, tmp_path: Path):
    """Verifica que get_sync_status nunca devuelva el pairing_token (SEC-01)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    service.get_or_create_pairing_token()

    status = service.get_sync_status(populated_db, authenticated=True)
    assert status.pairing_token is None


def test_save_receipt_with_non_alphanumeric_event_id(tmp_path: Path):
    """Verifica que el saneamiento de safe_id evite inyección de nombres de archivo."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    saved_fn = service.save_receipt_base64("../../../exploit_evt", dummy_b64)
    assert saved_fn is not None
    assert ".." not in saved_fn
    assert "/" not in saved_fn
    assert "\\" not in saved_fn
    assert saved_fn == "receipt_exploit_evt.jpg"


def test_mobile_sync_income_subcategory_auto_assigned_to_income(populated_db, tmp_path: Path):
    """Verifica que una subcategoría creada al vuelo para INCOME se asigne a Ingresos Netos (Fase 18)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    req = MobileSyncRequest(
        device_id="mobile-test-income",
        transactions=[
            MobileTransactionPayload(
                event_id="evt-income-vuelo-1",
                amount=120.0,
                description="Devolución Hacienda IRPF",
                date=date(2026, 11, 10),
                subcategory_name="Devoluciones IRPF",
                type="INCOME",
            )
        ],
    )
    res = service.process_mobile_sync(populated_db, req)
    assert res.success is True
    assert res.processed_count == 1

    created_sub = populated_db.query(Subcategory).filter(Subcategory.name == "Devoluciones IRPF").first()
    assert created_sub is not None
    assert service.is_income_category(created_sub.category) is True


def test_delete_transaction_removes_physical_receipt_file(populated_db, tmp_path: Path, monkeypatch):
    """Verifica que al eliminar una transacción se borre físicamente el comprobante del disco (Fase 18)."""
    monkeypatch.setenv("BASE_SYNC_DIR", str(tmp_path))
    service = MobileSyncService(base_sync_dir=str(tmp_path))
    dummy_bytes = b"dummy-receipt-image-content"
    filename = service.save_receipt_file("evt-delete-physical", dummy_bytes)
    assert filename is not None
    physical_path = service.get_receipt_path(filename)
    assert physical_path is not None
    assert physical_path.exists() is True

    subcat = populated_db.query(Subcategory).first()
    tx = Transaction(
        date=date.today(),
        subcategory_id=subcat.id,
        amount=45.0,
        description="Compra ferretería con ticket",
        mobile_event_id="evt-delete-physical",
        receipt_filename=filename,
    )
    populated_db.add(tx)
    populated_db.commit()
    populated_db.refresh(tx)

    deleted_id = service.delete_mobile_transaction(populated_db, "evt-delete-physical")
    assert deleted_id == tx.id
    assert physical_path.exists() is False


def test_get_mobile_monthly_summary_with_null_subcategory(populated_db, tmp_path: Path, monkeypatch):
    """Verifica que transacciones huérfanas sin subcategoría se computen en total_spent (Fase 18)."""
    import types
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    fake_orphan = types.SimpleNamespace(
        id=999,
        date=date(2026, 11, 12),
        subcategory_id=None,
        amount=65.50,
        description="Gasto no categorizado móvil",
    )

    orig_query = populated_db.query
    def mock_query(model, *args, **kwargs):
        q = orig_query(model, *args, **kwargs)
        if model == Transaction:
            orig_all = q.all
            def mock_all():
                items = orig_all()
                return list(items) + [fake_orphan]
            q.all = mock_all
        return q

    monkeypatch.setattr(populated_db, "query", mock_query)

    summary = service.get_mobile_monthly_summary(populated_db, month="2026-11")
    assert summary.total_spent >= 65.50
    orphan_item = next((s for s in summary.subcategories if s.get("subcategory_id") == -1), None)
    assert orphan_item is not None
    assert orphan_item["spent"] == 65.50
    assert orphan_item["subcategory_name"] == "Sin Subcategoría"


def test_pairing_pin_generation_and_ttl_expiration(tmp_path: Path):
    """Verifica la generación de PIN de 6 dígitos y su expiración por tiempo."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    # 1. Generar PIN con 2 segundos de TTL
    pin_data = service.generate_pairing_pin(ttl_seconds=2)
    assert len(pin_data["pin"]) == 6
    assert pin_data["pin"].isdigit()
    assert pin_data["expires_in_seconds"] == 2
    assert service.pin_file.exists()

    # 2. Simular expiración manipulando el timestamp
    import time
    with open(service.pin_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["expires_at_timestamp"] = time.time() - 10
    with open(service.pin_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # 3. Intentar emparejar con PIN caducado
    success, token, msg = service.pair_with_pin(pin_data["pin"])
    assert success is False
    assert token is None
    assert "caducado" in msg.lower()
    assert service.pin_file.exists() is False


def test_pairing_pin_successful_pairing_and_single_use(tmp_path: Path):
    """Verifica que el emparejamiento con PIN entregue el token y consuma el PIN (un solo uso)."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    pin_data = service.generate_pairing_pin(ttl_seconds=600)
    pin = pin_data["pin"]

    # 1. Canjear PIN exitosamente
    success, token, msg = service.pair_with_pin(pin)
    assert success is True
    assert token is not None
    assert service.validate_pairing_token(token) is True
    assert "éxito" in msg.lower()

    # 2. El PIN ya no existe (consumido)
    assert service.pin_file.exists() is False
    success_retry, token_retry, msg_retry = service.pair_with_pin(pin)
    assert success_retry is False
    assert token_retry is None
    assert "no hay ningún pin" in msg_retry.lower()


def test_pairing_pin_brute_force_rate_limiting(tmp_path: Path):
    """Verifica que tras 5 intentos fallidos el PIN se invalide permanentemente."""
    service = MobileSyncService(base_sync_dir=str(tmp_path))

    pin_data = service.generate_pairing_pin(ttl_seconds=600)
    real_pin = pin_data["pin"]
    wrong_pin = "000000" if real_pin != "000000" else "111111"

    # Intentos 1 a 4 fallidos con conteo regresivo
    for attempt in range(1, 5):
        success, token, msg = service.pair_with_pin(wrong_pin)
        assert success is False
        assert token is None
        assert f"quedan {5 - attempt} intentos" in msg

    # Intento 5: se bloquea e invalida
    success_final, token_final, msg_final = service.pair_with_pin(wrong_pin)
    assert success_final is False
    assert token_final is None
    assert "superado el límite" in msg_final.lower()
    assert service.pin_file.exists() is False










