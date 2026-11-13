"""
Pruebas Unitarias para el Motor de Sincronización y Cola Offline Móvil (Spec 016 - Fase 4).
Valida la generación de deltas offline, transiciones de estado, exportación compatible
y procesamiento de lotes acumulados al volver a la conexión Wi-Fi doméstica.
"""

from datetime import date
import json
from pathlib import Path
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileSyncRequest,
    MobileTransactionPayload,
)
from backend.services.mobile_sync_service import MobileSyncService


def test_offline_queue_flush_and_sync_simulation(db_session: Session):
    """Simula una cola de 3 gastos acumulados offline en la calle y su sincronización al llegar a casa."""
    # 1. Configurar base contable
    cat_nec = Category(name="Necesidades Básicas (50%)", type="expense")
    cat_des = Category(name="Deseos (30%)", type="expense")
    db_session.add_all([cat_nec, cat_des])
    db_session.commit()
    assert cat_nec.id is not None
    assert cat_des.id is not None

    sub_cafe = Subcategory(name="Café y Desayunos", category_id=cat_des.id)
    sub_super = Subcategory(name="Supermercado", category_id=cat_nec.id)
    sub_gas = Subcategory(name="Gasolina", category_id=cat_nec.id)
    db_session.add_all([sub_cafe, sub_super, sub_gas])
    db_session.commit()
    assert sub_cafe.id is not None
    assert sub_super.id is not None
    assert sub_gas.id is not None

    service = MobileSyncService()

    # 2. Cola offline acumulada en el móvil
    offline_queue = [
        MobileTransactionPayload(
            event_id="offline-tx-001",
            amount=1.60,
            description="Café con leche",
            date=date(2026, 11, 13),
            subcategory_id=sub_cafe.id,
            subcategory_name="Café y Desayunos",
            created_at_utc="2026-11-13T09:15:00Z",
        ),
        MobileTransactionPayload(
            event_id="offline-tx-002",
            amount=38.45,
            description="Supermercado semanal",
            date=date(2026, 11, 13),
            subcategory_id=sub_super.id,
            subcategory_name="Supermercado",
            created_at_utc="2026-11-13T12:30:00Z",
        ),
        MobileTransactionPayload(
            event_id="offline-tx-003",
            amount=45.00,
            description="Repostaje Repsol",
            date=date(2026, 11, 13),
            subcategory_id=sub_gas.id,
            subcategory_name="Gasolina",
            created_at_utc="2026-11-13T17:45:00Z",
        ),
    ]

    # 3. Al llegar a casa (conexión Wi-Fi): se dispara el volcado a la API
    sync_request = MobileSyncRequest(
        device_id="android-pixel-raul",
        transactions=offline_queue,
    )

    sync_response = service.process_mobile_sync(db_session, sync_request)
    assert sync_response.success is True
    assert sync_response.processed_count == 3
    assert sync_response.ignored_duplicates_count == 0

    # 4. Validar persistencia exacta en SQLite
    txs = (
        db_session.query(Transaction)
        .filter(Transaction.mobile_event_id.in_(["offline-tx-001", "offline-tx-002", "offline-tx-003"]))
        .all()
    )
    assert len(txs) == 3

    amounts = {t.amount for t in txs}
    assert amounts == {1.60, 38.45, 45.00}


def test_exported_json_interoperability_with_syncthing_inbox(db_session: Session, tmp_path: Path):
    """
    Verifica que el payload generado por la exportación JSON del móvil sea
    100% interoperable con el lector del buzón Syncthing en el backend.
    """
    cat = Category(name="Deseos (30%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Cena Viernes", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    service = MobileSyncService(base_sync_dir=str(tmp_path))

    # Estructura generada por exportTransactionsToJsonFile() en el cliente
    client_exported_payload = {
        "device_id": "mobile-pwa",
        "exported_at_utc": "2026-11-13T21:00:00Z",
        "transactions": [
            {
                "event_id": "exported-uuid-888",
                "scope": "PERSONAL",
                "amount": 25.50,
                "description": "Cena pizza y bebida",
                "date": "2026-11-13",
                "subcategory_id": sub.id,
                "subcategory_name": "Cena Viernes",
                "created_at_utc": "2026-11-13T20:50:00Z",
            }
        ],
    }

    # Depositar en inbox
    inbox_file = service.inbox_dir / "evt_mob_from_phone.json"
    inbox_file.write_text(json.dumps(client_exported_payload), encoding="utf-8")

    # Ingesta por el worker del backend
    count = service.process_mobile_inbox_folder(db_session)
    assert count == 1
    assert not inbox_file.exists()
    assert (service.processed_dir / "evt_mob_from_phone.json").exists()

    # Comprobar registro en BD
    tx = db_session.query(Transaction).filter(Transaction.mobile_event_id == "exported-uuid-888").first()
    assert tx is not None
    assert tx.amount == 25.50
    assert tx.description == "Cena pizza y bebida"
