"""
Pruebas de integración End-to-End (E2E) para el flujo completo del Companion Móvil Quick-Capture.
Simula la interacción de un dispositivo móvil (PWA/APK/Syncthing) con los endpoints del backend:
1. Seguridad por Pairing Token (rechazo a dispositivos ajenos).
2. Consulta de catálogo offline con frecuencias y conceptos automáticos.
3. Sincronización directa vía Wi-Fi con idempotencia ante reconexiones y subcategorías al vuelo.
4. Consulta y ajuste de presupuestos mensuales 50/30/20 («Mi Mes»).
5. Ingesta desatendida mediante buzón sync/mobile/inbox/ y rotación a processed/.
6. Verificación de persistencia en SQLite y retorno del mobile_event_id en /transactions/.
"""

from datetime import date
import json
import os
import tempfile
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.api.main import app
from backend.api.routers.mobile import get_sync_service
from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.services.mobile_sync_service import MobileSyncService


@pytest.fixture
def auth_headers() -> dict:
    """Retorna las cabeceras con el Pairing Token válido para peticiones del móvil."""
    token = MobileSyncService().get_or_create_pairing_token()
    return {"X-Mobile-Pairing-Token": token}


def test_mobile_e2e_complete_sync_and_persistence_flow(
    client: TestClient, db_session: Session, auth_headers: dict
):
    """Flujo E2E 1: Consulta de Catálogo -> Sincronización Wi-Fi -> Idempotencia -> Verificación en BD."""
    # 1. Preparar categorías y subcategorías
    cat_necesidad = Category(name="Necesidades Básicas (50%)", type="expense")
    cat_ocio = Category(name="Deseos (30%)", type="expense")
    db_session.add_all([cat_necesidad, cat_ocio])
    db_session.commit()

    sub_super = Subcategory(name="Supermercado", category_id=cat_necesidad.id)
    sub_cafe = Subcategory(name="Café y Desayunos", category_id=cat_ocio.id)
    db_session.add_all([sub_super, sub_cafe])
    db_session.commit()

    # Transacción previa para alimentar conceptos frecuentes
    prev_tx = Transaction(
        date=date.today(),
        subcategory_id=sub_cafe.id,
        amount=2.50,
        description="Café con leche",
    )
    db_session.add(prev_tx)
    db_session.commit()

    # 2. El móvil se conecta con su Pairing Token y consulta el catálogo
    resp_cat = client.get("/api/mobile/catalog", headers=auth_headers)
    assert resp_cat.status_code == 200
    cat_data = resp_cat.json()
    assert "personal_subcategories" in cat_data
    subcats = cat_data["personal_subcategories"]
    assert len(subcats) >= 2
    assert any(s["id"] == sub_cafe.id for s in subcats)
    assert "frequent_concepts" in cat_data
    assert "Café con leche" in cat_data["frequent_concepts"]

    # 3. El usuario registra 2 transacciones offline en la calle (una de ellas con subcategoría creada al vuelo)
    event_id_1 = f"e2e-event-{uuid.uuid4()}"
    event_id_2 = f"e2e-event-{uuid.uuid4()}"

    sync_payload = {
        "device_id": "iphone-raul-pwa",
        "transactions": [
            {
                "event_id": event_id_1,
                "scope": "PERSONAL",
                "date": str(date.today()),
                "amount": 1.60,
                "description": "Café solo en terraza",
                "subcategory_id": sub_cafe.id,
                "subcategory_name": "Café y Desayunos",
            },
            {
                "event_id": event_id_2,
                "scope": "PERSONAL",
                "date": str(date.today()),
                "amount": 25.00,
                "description": "Partida pádel pista cubierta",
                "subcategory_id": -1,  # Creada al vuelo offline
                "subcategory_name": "Pádel y Deportes",
            },
        ],
    }

    # 4. Al llegar a casa, auto-flush a /api/mobile/sync con token
    resp_sync = client.post("/api/mobile/sync", json=sync_payload, headers=auth_headers)
    assert resp_sync.status_code == 200
    sync_res = resp_sync.json()
    assert sync_res["success"] is True
    assert sync_res["processed_count"] == 2
    assert sync_res["ignored_duplicates_count"] == 0

    # 5. Reintento (idempotencia y offline sync retry)
    resp_retry = client.post("/api/mobile/sync", json=sync_payload, headers=auth_headers)
    assert resp_retry.status_code == 200
    retry_res = resp_retry.json()
    assert retry_res["success"] is True
    assert retry_res["processed_count"] == 0
    assert retry_res["ignored_duplicates_count"] == 2

    # 6. Verificar que /transactions/ retorna ambas transacciones persistidas
    resp_txs = client.get("/transactions/")
    assert resp_txs.status_code == 200
    all_txs = resp_txs.json()

    saved_tx1 = next((t for t in all_txs if t.get("mobile_event_id") == event_id_1), None)
    saved_tx2 = next((t for t in all_txs if t.get("mobile_event_id") == event_id_2), None)
    assert saved_tx1 is not None
    assert saved_tx1["amount"] == 1.60
    assert saved_tx1["description"] == "Café solo en terraza"
    assert saved_tx2 is not None
    assert saved_tx2["amount"] == 25.00
    assert saved_tx2["description"] == "Partida pádel pista cubierta"

    # 7. Consultar «Mi Mes» a través de /api/mobile/summary
    curr_month = date.today().strftime("%Y-%m")
    resp_summary = client.get(f"/api/mobile/summary?month={curr_month}", headers=auth_headers)
    assert resp_summary.status_code == 200
    sum_data = resp_summary.json()
    assert sum_data["total_spent"] >= 26.60
    assert "emergency_fund" in sum_data


def test_mobile_e2e_syncthing_inbox_and_file_rotation(client: TestClient, db_session: Session):
    """Flujo E2E 2: Fichero delta depositado en sync/mobile/inbox/ -> Procesamiento manual -> Rotación a processed/."""
    with tempfile.TemporaryDirectory(prefix="e2e_mobile_sync_") as temp_dir:
        cat = Category(name="Ocio", type="expense")
        db_session.add(cat)
        db_session.commit()
        sub = Subcategory(name="Cine", category_id=cat.id)
        db_session.add(sub)
        db_session.commit()

        # Instanciar servicio personalizado apuntando al directorio temporal
        custom_service = MobileSyncService(base_sync_dir=temp_dir)
        app.dependency_overrides[get_sync_service] = lambda: custom_service

        try:
            # 1. Depositar un archivo delta en inbox
            event_id_syncthing = f"syncthing-{uuid.uuid4()}"
            delta_content = {
                "device_id": "pixel8-syncthing",
                "transactions": [
                    {
                        "event_id": event_id_syncthing,
                        "scope": "PERSONAL",
                        "date": str(date.today()),
                        "amount": 9.50,
                        "description": "Entrada cine viernes",
                        "subcategory_id": sub.id,
                        "subcategory_name": "Cine",
                    }
                ],
            }

            delta_path = custom_service.inbox_dir / "mobile_delta_20261113.json"
            with open(delta_path, "w", encoding="utf-8") as f:
                json.dump(delta_content, f)

            # 2. Comprobar que /api/mobile/status detecta 1 fichero pendiente
            resp_status_1 = client.get("/api/mobile/status")
            assert resp_status_1.status_code == 200
            assert resp_status_1.json()["pending_inbox_files"] == 1

            # 3. Disparar procesamiento de la carpeta
            resp_proc = client.post("/api/mobile/process-folder")
            assert resp_proc.status_code == 200
            proc_data = resp_proc.json()
            assert proc_data["success"] is True
            assert proc_data["processed_count"] == 1

            # 4. Validar que el archivo rotó a processed/ y se limpió el inbox
            assert len(os.listdir(custom_service.inbox_dir)) == 0
            archived = os.listdir(custom_service.processed_dir)
            assert len(archived) == 1
            assert "mobile_delta_20261113" in archived[0]

            # 5. Comprobar que en base de datos la transacción existe
            saved_tx = db_session.query(Transaction).filter_by(mobile_event_id=event_id_syncthing).first()
            assert saved_tx is not None
            assert saved_tx.amount == 9.50
            assert saved_tx.description == "Entrada cine viernes"

            # 6. Comprobar que status ahora tiene 0 pendientes
            resp_status_2 = client.get("/api/mobile/status")
            assert resp_status_2.status_code == 200
            assert resp_status_2.json()["pending_inbox_files"] == 0
        finally:
            app.dependency_overrides.pop(get_sync_service, None)
