"""
Pruebas de Integración para los Endpoints REST del Companion Móvil (Spec 016 - Fase 7).
Valida seguridad por Pairing Token, /api/mobile/catalog, /api/mobile/sync,
/api/mobile/subcategory, /api/mobile/summary, /api/mobile/budget,
/api/mobile/status, /api/mobile/process-folder y montaje de la PWA.
"""

from datetime import date
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.services.mobile_sync_service import MobileSyncService


@pytest.fixture
def auth_headers() -> dict:
    """Retorna las cabeceras con el Pairing Token válido para peticiones del móvil."""
    token = MobileSyncService().get_or_create_pairing_token()
    return {"X-Mobile-Pairing-Token": token}


def test_pairing_token_security_rejection(client: TestClient):
    """Verifica que llamadas sin token o con token erróneo sean rechazadas con HTTP 403 Forbidden."""
    # 1. Sin cabecera
    resp_no_token = client.get("/api/mobile/catalog")
    assert resp_no_token.status_code == 403
    assert "Token de emparejamiento móvil no válido" in resp_no_token.json()["detail"]

    # 2. Con token falso / dispositivo ajeno en la Wi-Fi
    resp_fake_token = client.get(
        "/api/mobile/catalog",
        headers={"X-Mobile-Pairing-Token": "sec_token_ajeno_invalido"},
    )
    assert resp_fake_token.status_code == 403

    # 3. /status es público para diagnóstico pero devuelve si está emparejado
    resp_status = client.get("/api/mobile/status")
    assert resp_status.status_code == 200
    assert "pairing_token" in resp_status.json()


def test_get_mobile_catalog_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica que GET /api/mobile/catalog retorne el catálogo formateado con código HTTP 200 al usar el token."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Supermercado", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()

    resp = client.get("/api/mobile/catalog", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "device_id" in data
    assert "personal_subcategories" in data
    assert len(data["personal_subcategories"]) >= 1
    assert any(s["name"] == "Supermercado" for s in data["personal_subcategories"])


def test_sync_mobile_transactions_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica la ingesta atómica e idempotente vía POST /api/mobile/sync con token."""
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
    resp = client.post("/api/mobile/sync", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["processed_count"] == 2
    assert res_data["ignored_duplicates_count"] == 0

    # 2. Reintento idéntico: debe ignorar duplicados
    resp_dup = client.post("/api/mobile/sync", json=payload, headers=auth_headers)
    assert resp_dup.status_code == 200
    res_dup_data = resp_dup.json()
    assert res_dup_data["processed_count"] == 0
    assert res_dup_data["ignored_duplicates_count"] == 2

    # 3. Validar en base de datos
    tx_count = db_session.query(Transaction).filter(
        Transaction.mobile_event_id.in_(["api-uuid-001", "api-uuid-002"])
    ).count()
    assert tx_count == 2


def test_sync_mobile_transactions_validation_error(client: TestClient, auth_headers: dict):
    """Verifica que peticiones con importes negativos respondan HTTP 422."""
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
    resp = client.post("/api/mobile/sync", json=invalid_payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_subcategory_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica POST /api/mobile/subcategory para alta rápida de categorías."""
    cat = Category(name="Deseos (30%)", type="expense")
    db_session.add(cat)
    db_session.commit()

    payload = {
        "name": "Pádel con amigos",
        "category_name": "Deseos (30%)",
    }
    resp = client.post("/api/mobile/subcategory", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Pádel con amigos"
    assert data["category_name"] == "Deseos (30%)"
    assert data["id"] > 0

    # Idempotencia
    resp2 = client.post("/api/mobile/subcategory", json=payload, headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == data["id"]


def test_get_monthly_summary_and_update_budget_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica GET /api/mobile/summary y POST /api/mobile/budget."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Supermercado", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    # 1. Actualizar presupuesto
    budget_payload = {
        "subcategory_id": sub.id,
        "allocated_amount": 300.0,
        "month": "2026-11",
    }
    resp_b = client.post("/api/mobile/budget", json=budget_payload, headers=auth_headers)
    assert resp_b.status_code == 200
    assert resp_b.json()["success"] is True

    # 2. Consultar resumen
    resp_s = client.get("/api/mobile/summary?month=2026-11", headers=auth_headers)
    assert resp_s.status_code == 200
    s_data = resp_s.json()
    assert s_data["month"] == "2026-11"
    assert s_data["needs"]["budget"] == 300.0
    assert any(item["subcategory_name"] == "Supermercado" for item in s_data["subcategories"])


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


def test_mobile_ota_version_and_download_flow(client: TestClient):
    """Verifica el flujo de comprobación de versión, subida y descarga de APK OTA (Fase 8)."""
    # 1. Consulta inicial de versión
    resp_v1 = client.get("/api/mobile/version")
    assert resp_v1.status_code == 200
    v1_data = resp_v1.json()
    assert "version_code" in v1_data
    assert "apk_available" in v1_data

    # 2. Si no hay APK disponible, /download-apk responde 404
    if not v1_data.get("apk_available"):
        resp_down_404 = client.get("/api/mobile/download-apk")
        assert resp_down_404.status_code == 404

    # 3. Publicar una nueva versión APK vía /upload-apk
    apk_content = b"PK\x03\x04test-android-apk-binary-content"
    files = {"apk_file": ("gestor-finanzas-v1.2.apk", apk_content, "application/vnd.android.package-archive")}
    data = {
        "version_code": "3",
        "version_name": "1.2.0",
        "release_notes": "Prueba de actualización in-app OTA",
    }
    resp_up = client.post("/api/mobile/upload-apk", files=files, data=data)
    assert resp_up.status_code == 200
    up_data = resp_up.json()
    assert up_data["version_code"] == 3
    assert up_data["version_name"] == "1.2.0"
    assert up_data["apk_available"] is True
    assert up_data["apk_filename"] == "gestor-finanzas-v1.2.apk"

    # 4. Descargar el APK publicado
    resp_down = client.get("/api/mobile/download-apk")
    assert resp_down.status_code == 200
    assert resp_down.headers.get("content-type") == "application/vnd.android.package-archive"
    assert resp_down.content == apk_content
