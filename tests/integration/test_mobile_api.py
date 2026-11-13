"""
Pruebas de Integración para los Endpoints REST del Companion Móvil (Spec 016).
Valida /api/mobile/catalog, /api/mobile/sync, /api/mobile/status,
/api/mobile/process-folder y el montaje estático de la PWA en /mobile.
"""

from datetime import date
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.services.mobile_sync_service import MobileSyncService


def test_get_mobile_catalog_api(client: TestClient, db_session: Session):
    """Verifica que GET /api/mobile/catalog retorne el catálogo formateado con código HTTP 200."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Supermercado", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()

    resp = client.get("/api/mobile/catalog")
    assert resp.status_code == 200
    data = resp.json()

    assert "device_id" in data
    assert "personal_subcategories" in data
    assert len(data["personal_subcategories"]) >= 1
    assert any(s["name"] == "Supermercado" for s in data["personal_subcategories"])


def test_sync_mobile_transactions_api(client: TestClient, db_session: Session):
    """Verifica la ingesta atómica e idempotente vía POST /api/mobile/sync."""
    cat = Category(name="Deseos (30%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Café y Desayunos", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    payload = {
        "device_id": "test-phone-api",
        "transactions": [
            {
                "event_id": "api-uuid-001",
                "scope": "PERSONAL",
                "amount": 2.20,
                "description": "Café espresso",
                "date": str(date.today()),
                "subcategory_id": sub.id,
                "subcategory_name": "Café y Desayunos",
            },
            {
                "event_id": "api-uuid-002",
                "scope": "PERSONAL",
                "amount": 18.00,
                "description": "Cena tapas",
                "date": str(date.today()),
                "subcategory_id": sub.id,
                "subcategory_name": "Café y Desayunos",
            },
        ],
    }

    # 1. Primera llamada: inserción limpia
    resp = client.post("/api/mobile/sync", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["processed_count"] == 2
    assert res_data["ignored_duplicates_count"] == 0

    # 2. Reintento idéntico: debe ignorar duplicados
    resp_dup = client.post("/api/mobile/sync", json=payload)
    assert resp_dup.status_code == 200
    res_dup_data = resp_dup.json()
    assert res_dup_data["processed_count"] == 0
    assert res_dup_data["ignored_duplicates_count"] == 2

    # 3. Validar en base de datos
    tx_count = db_session.query(Transaction).filter(
        Transaction.mobile_event_id.in_(["api-uuid-001", "api-uuid-002"])
    ).count()
    assert tx_count == 2


def test_sync_mobile_transactions_validation_error(client: TestClient):
    """Verifica que peticiones con importes negativos o datos no válidos respondan HTTP 422."""
    invalid_payload = {
        "device_id": "test-phone-api",
        "transactions": [
            {
                "event_id": "api-uuid-inv",
                "scope": "PERSONAL",
                "amount": -10.00,  # Inválido: debe ser > 0
                "description": "Error",
                "date": str(date.today()),
                "subcategory_id": 1,
            }
        ],
    }
    resp = client.post("/api/mobile/sync", json=invalid_payload)
    assert resp.status_code == 422


def test_get_mobile_status_api(client: TestClient, db_session: Session):
    """Verifica que GET /api/mobile/status responda con salud y métricas de servidor."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Supermercado", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    # Registrar 1 transacción de hoy
    tx = Transaction(
        date=date.today(),
        subcategory_id=sub.id,
        amount=15.0,
        description="Compra hoy",
    )
    db_session.add(tx)
    db_session.commit()

    resp = client.get("/api/mobile/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server_online"] is True
    assert data["today_transactions_count"] >= 1


def test_process_mobile_folder_api(client: TestClient, db_session: Session):
    """Verifica que POST /api/mobile/process-folder procese deltas en disco."""
    cat = Category(name="Deseos (30%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Café", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    # Depositar archivo en inbox
    service = MobileSyncService()
    inbox_file = service.inbox_dir / "evt_mob_api_test.json"
    inbox_file.write_text(json.dumps({
        "event_id": "file-via-api-01",
        "scope": "PERSONAL",
        "amount": 3.50,
        "description": "Desayuno completo",
        "date": str(date.today()),
        "subcategory_id": sub.id,
    }), encoding="utf-8")

    resp = client.post("/api/mobile/process-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["processed_count"] == 1


def test_static_mobile_mount(client: TestClient):
    """Verifica que la ruta /mobile devuelva el archivo estático de la PWA."""
    resp = client.get("/mobile/")
    assert resp.status_code == 200
    assert "Gestor Finanzas" in resp.text
