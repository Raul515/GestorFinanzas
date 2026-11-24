"""
Pruebas de Integración para los Endpoints REST del Companion Móvil (Spec 016 - Fase 7).
Valida seguridad por Pairing Token, /api/mobile/catalog, /api/mobile/sync,
/api/mobile/subcategory, /api/mobile/summary, /api/mobile/budget,
/api/mobile/status, /api/mobile/process-folder y montaje de la PWA.
"""

from datetime import date
import io
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

    # 3. /status es público para diagnóstico pero JAMÁS expone el token (SEC-01)
    resp_status = client.get("/api/mobile/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data.get("pairing_token") is None
    assert status_data["authenticated"] is False

    # Con cabecera de autenticación válida, /status refleja authenticated=True sin exponer el token
    token = MobileSyncService().get_or_create_pairing_token()
    resp_auth_status = client.get("/api/mobile/status", headers={"X-Mobile-Pairing-Token": token})
    assert resp_auth_status.status_code == 200
    auth_data = resp_auth_status.json()
    assert auth_data.get("pairing_token") is None
    assert auth_data["authenticated"] is True


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


def test_process_mobile_folder_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica que POST /api/mobile/process-folder procese deltas en disco y requiera token (SEC-05)."""
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

    # 1. Sin autenticación -> Rechazado 403 (SEC-05)
    resp_unauth = client.post("/api/mobile/process-folder")
    assert resp_unauth.status_code == 403

    # 2. Con autenticación -> 200 OK
    resp = client.post("/api/mobile/process-folder", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["processed_count"] == 1


def test_static_mobile_mount(client: TestClient):
    """Verifica que la ruta /mobile devuelva el archivo estático de la PWA."""
    resp = client.get("/mobile/")
    assert resp.status_code == 200
    assert "Gestor Finanzas" in resp.text


def test_mobile_ota_version_and_download_flow(client: TestClient, auth_headers: dict):
    """Verifica el flujo de comprobación de versión, subida y descarga de APK OTA (Fase 8 y SEC-02)."""
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
    # 3a. Sin autenticación -> Rechazado 403 (SEC-02)
    resp_unauth = client.post("/api/mobile/upload-apk", files=files, data=data)
    assert resp_unauth.status_code == 403

    # 3b. Con token válido -> 200 OK
    files_auth = {"apk_file": ("gestor-finanzas-v1.2.apk", apk_content, "application/vnd.android.package-archive")}
    token = MobileSyncService().get_or_create_pairing_token()
    resp_up = client.post("/api/mobile/upload-apk", headers={"X-Mobile-Pairing-Token": token}, files=files_auth, data=data)
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


def test_admin_pairing_token_security_and_loopback_restriction(client: TestClient):
    """Verifica que /api/mobile/admin/pairing-token esté restringido al host local (SEC-01)."""
    # 1. Petición desde el cliente local (TestClient/localhost)
    resp = client.get("/api/mobile/admin/pairing-token")
    assert resp.status_code == 200
    data = resp.json()
    assert "pairing_token" in data
    assert data["pairing_token"].startswith("sec_")

    # 2. Petición simulada desde IP externa en la red Wi-Fi
    from unittest.mock import patch
    with patch("fastapi.Request.client", new_callable=lambda: property(lambda self: type("Client", (), {"host": "192.168.1.105"})())):
        resp_ext = client.get("/api/mobile/admin/pairing-token")
        assert resp_ext.status_code == 403
        assert "Acceso denegado" in resp_ext.json()["detail"]


def test_delete_mobile_transaction_api_flow(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica el endpoint DELETE /api/mobile/transactions/{id} con seguridad de token (Fase 9)."""
    cat = Category(name="Deseos (30%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Cena para Borrar", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    # 1. Crear una transacción mediante sync
    evt_id = "evt_api_del_test_999"
    payload = {
        "device_id": "test-device",
        "transactions": [
            {
                "event_id": evt_id,
                "scope": "PERSONAL",
                "amount": 18.50,
                "description": "Cena para borrar",
                "date": str(date.today()),
                "subcategory_id": sub.id,
            }
        ],
    }
    sync_resp = client.post(
        "/api/mobile/sync",
        json=payload,
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["processed_count"] == 1

    # 2. Intentar eliminar sin token -> 403 Forbidden
    resp_no_token = client.delete(f"/api/mobile/transactions/{evt_id}")
    assert resp_no_token.status_code == 403

    # 3. Eliminar con token válido -> 200 OK
    resp_del = client.delete(
        f"/api/mobile/transactions/{evt_id}",
        headers=auth_headers,
    )
    assert resp_del.status_code == 200
    del_data = resp_del.json()
    assert del_data["success"] is True
    assert del_data["identifier"] == evt_id
    assert del_data["deleted_id"] is not None

    # 4. Verificar que ya no existe en la BD
    tx_check = db_session.query(Transaction).filter(Transaction.mobile_event_id == evt_id).first()
    assert tx_check is None

    # 5. Intentar eliminarlo de nuevo -> 404 Not Found
    resp_del_404 = client.delete(
        f"/api/mobile/transactions/{evt_id}",
        headers=auth_headers,
    )
    assert resp_del_404.status_code == 404


def test_search_mobile_transactions_and_cache_api(
    client: TestClient, db_session: Session, auth_headers: dict
):
    """Verifica los endpoints de búsqueda profunda y descarga de caché histórica (Fase 11)."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    assert cat.id is not None

    sub = Subcategory(name="Taller Mecánico", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()
    assert sub.id is not None

    tx = Transaction(
        date=date(2026, 11, 20),
        subcategory_id=sub.id,
        amount=145.0,
        description="Cambio de aceite y filtros",
        mobile_event_id="evt_srch_api_001",
    )
    db_session.add(tx)
    db_session.commit()

    # 1. Búsqueda sin autenticación -> 403 Forbidden
    resp_unauth = client.get("/api/mobile/transactions/search?q=aceite")
    assert resp_unauth.status_code == 403

    # 2. Búsqueda con token válido -> 200 OK con resultados
    resp_search = client.get("/api/mobile/transactions/search?q=aceite", headers=auth_headers)
    assert resp_search.status_code == 200
    s_data = resp_search.json()
    assert s_data["query"] == "aceite"
    assert s_data["total_found"] >= 1
    assert any("Cambio de aceite" in r["description"] for r in s_data["items"])

    # 3. Caché histórica sin autenticación -> 403 Forbidden
    resp_cache_unauth = client.get("/api/mobile/transactions/history-cache?months=12")
    assert resp_cache_unauth.status_code == 403

    # 4. Caché histórica con token válido -> 200 OK con lista de transacciones
    resp_cache = client.get("/api/mobile/transactions/history-cache?months=12", headers=auth_headers)
    assert resp_cache.status_code == 200
    cache_data = resp_cache.json()
    assert isinstance(cache_data, list)
    assert len(cache_data) >= 1
    assert any(r["description"] == "Cambio de aceite y filtros" for r in cache_data)


def test_mobile_receipts_api_flow(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica la subida multipart, descarga y vinculación de tickets vía REST (Fase 12)."""
    cat = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add(cat)
    db_session.commit()
    sub = Subcategory(name="Farmacia", category_id=cat.id)
    db_session.add(sub)
    db_session.commit()

    # 1. Subida multipart sin token -> 403 Forbidden
    fake_img = b"\xff\xd8\xff\xe0\x00\x10JFIFfakejpgbytes"
    files = {"receipt_file": ("receipt.jpg", io.BytesIO(fake_img), "image/jpeg")}
    data_unauth = {"event_id": "evt_api_receipt_unauth"}
    resp_unauth = client.post("/api/mobile/receipts", data=data_unauth, files=files)
    assert resp_unauth.status_code == 403

    # 2. Subida con tipo de contenido no permitido (ej. text/plain) -> 400 Bad Request
    bad_files = {"receipt_file": ("doc.txt", io.BytesIO(b"not an image"), "text/plain")}
    data_bad = {"event_id": "evt_api_receipt_bad"}
    resp_bad = client.post("/api/mobile/receipts", headers=auth_headers, data=data_bad, files=bad_files)
    assert resp_bad.status_code == 400
    assert "Tipo de archivo no permitido" in resp_bad.json()["detail"]

    # 3. Subida válida con token
    valid_files = {"receipt_file": ("receipt.jpg", io.BytesIO(fake_img), "image/jpeg")}
    data_payload = {"event_id": "evt_api_receipt_999"}
    resp_upload = client.post("/api/mobile/receipts", headers=auth_headers, data=data_payload, files=valid_files)
    assert resp_upload.status_code == 200
    up_data = resp_upload.json()
    assert up_data["success"] is True
    assert up_data["event_id"] == "evt_api_receipt_999"
    filename = up_data["receipt_filename"]
    assert filename == "receipt_evt_api_receipt_999.jpg"
    assert up_data["receipt_url"] == f"/api/mobile/receipts/{filename}"

    # 4. Descarga del ticket sin token -> 403 Forbidden
    resp_get_unauth = client.get(f"/api/mobile/receipts/{filename}")
    assert resp_get_unauth.status_code == 403

    # 5. Descarga del ticket con token (vía header y vía query param ?token=...) -> 200 OK
    resp_get = client.get(f"/api/mobile/receipts/{filename}", headers=auth_headers)
    assert resp_get.status_code == 200
    assert resp_get.content == fake_img
    assert "image/jpeg" in resp_get.headers.get("content-type", "")

    token_val = auth_headers["X-Mobile-Pairing-Token"]
    resp_get_query = client.get(f"/api/mobile/receipts/{filename}?token={token_val}")
    assert resp_get_query.status_code == 200
    assert resp_get_query.content == fake_img

    # 6. Descarga con path traversal o archivo inexistente -> 404 Not Found o 400
    resp_not_found = client.get("/api/mobile/receipts/non_existent_file.jpg", headers=auth_headers)
    assert resp_not_found.status_code == 404

    resp_traversal = client.get("/api/mobile/receipts/..%2F..%2Fsecret.txt", headers=auth_headers)
    assert resp_traversal.status_code in [400, 404]

    # 7. Sincronización normal pasando base64
    fake_b64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    sync_payload = {
        "device_id": "phone-integration-test",
        "transactions": [
            {
                "event_id": "evt_int_rec_001",
                "scope": "PERSONAL",
                "amount": 8.75,
                "description": "Medicamentos con receta",
                "date": "2026-11-22",
                "subcategory_id": sub.id,
                "receipt_base64": fake_b64,
            }
        ]
    }
    resp_sync = client.post("/api/mobile/sync", headers=auth_headers, json=sync_payload)
    assert resp_sync.status_code == 200
    sync_res = resp_sync.json()
    assert sync_res["processed_count"] == 1

    # Verificar que el ticket generado por sync se puede descargar vía API
    resp_synced_receipt = client.get("/api/mobile/receipts/receipt_evt_int_rec_001.jpg", headers=auth_headers)
    assert resp_synced_receipt.status_code == 200
    assert len(resp_synced_receipt.content) > 0


def test_mobile_income_sync_and_summary_api(client: TestClient, db_session: Session, auth_headers: dict):
    """Verifica el flujo completo de captura y consulta de ingresos vía API (Fase 13)."""
    cat_ing = Category(name="Ingresos Netos", type="income")
    cat_gas = Category(name="Necesidades Básicas (50%)", type="expense")
    db_session.add_all([cat_ing, cat_gas])
    db_session.commit()

    sub_bizum = Subcategory(name="Bizum Recibido", category_id=cat_ing.id)
    sub_comida = Subcategory(name="Supermercado", category_id=cat_gas.id)
    db_session.add_all([sub_bizum, sub_comida])
    db_session.commit()

    # 1. Catálogo expone category_type
    cat_resp = client.get("/api/mobile/catalog", headers=auth_headers)
    assert cat_resp.status_code == 200
    subs = cat_resp.json()["personal_subcategories"]
    bizum_sub = next(s for s in subs if s["name"] == "Bizum Recibido")
    assert bizum_sub["category_type"] == "income"

    # 2. Sincronizar un ingreso y un gasto simultáneamente
    sync_payload = {
        "device_id": "test-phone-income",
        "transactions": [
            {
                "event_id": "evt_api_income_001",
                "type": "INCOME",
                "amount": 100.0,
                "description": "Devolución IRPF / Bizum",
                "date": str(date.today()),
                "subcategory_id": sub_bizum.id,
            },
            {
                "event_id": "evt_api_expense_001",
                "type": "EXPENSE",
                "amount": 25.0,
                "description": "Compra súper",
                "date": str(date.today()),
                "subcategory_id": sub_comida.id,
            },
        ],
    }
    sync_resp = client.post("/api/mobile/sync", headers=auth_headers, json=sync_payload)
    assert sync_resp.status_code == 200
    assert sync_resp.json()["processed_count"] == 2

    # 3. Consultar /summary y validar balance
    today_month = date.today().strftime("%Y-%m")
    sum_resp = client.get(f"/api/mobile/summary?month={today_month}", headers=auth_headers)
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert sum_data["total_income"] == 100.0
    assert sum_data["total_spent"] == 25.0
    assert sum_data["remaining_budget"] == 75.0

    # 4. Búsqueda devuelve type='INCOME' para el ingreso
    search_resp = client.get("/api/mobile/transactions/search?q=Devoluci%C3%B3n", headers=auth_headers)
    assert search_resp.status_code == 200
    s_items = search_resp.json()["items"]
    assert len(s_items) >= 1
    assert s_items[0]["type"] == "INCOME"


def test_admin_pairing_token_access_control(client: TestClient, db_session: Session):
    """Verifica que /api/mobile/admin/pairing-token permita acceso a localhost y Docker bridge (172.16/12), y rechace IPs externas (Wi-Fi)."""
    from fastapi import HTTPException
    from starlette.requests import Request
    from backend.api.routers.mobile import get_admin_pairing_token

    # 1. Petición estándar local vía TestClient (loopback/testclient) -> 200 OK
    resp = client.get("/api/mobile/admin/pairing-token")
    assert resp.status_code == 200
    assert "pairing_token" in resp.json()
    assert len(resp.json()["pairing_token"]) > 10

    # 2. Petición simulada desde contenedor Docker (red bridge 172.18.0.3) -> Permitida
    service = MobileSyncService()
    docker_request = Request({"type": "http", "client": ("172.18.0.3", 52341)})
    docker_resp = get_admin_pairing_token(request=docker_request, service=service)
    assert docker_resp.pairing_token == service.get_or_create_pairing_token()

    # 3. Petición simulada desde dispositivo en la Wi-Fi (192.168.1.55) -> 403 Forbidden
    wifi_request = Request({"type": "http", "client": ("192.168.1.55", 43210)})
    with pytest.raises(HTTPException) as exc_info:
        get_admin_pairing_token(request=wifi_request, service=service)
    assert exc_info.value.status_code == 403
    assert "Acceso denegado" in exc_info.value.detail

    # 4. Petición simulada desde dispositivo en Hotspot de iPhone (172.20.10.1) -> 403 Forbidden
    hotspot_request = Request({"type": "http", "client": ("172.20.10.1", 54321)})
    with pytest.raises(HTTPException) as exc_info_hs:
        get_admin_pairing_token(request=hotspot_request, service=service)
    assert exc_info_hs.value.status_code == 403
    assert "Acceso denegado" in exc_info_hs.value.detail

    # 5. Petición simulada desde subred fija dedicada de Docker (172.28.199.5) -> Permitida
    dedicated_docker_request = Request({"type": "http", "client": ("172.28.199.5", 42100)})
    dedicated_resp = get_admin_pairing_token(request=dedicated_docker_request, service=service)
    assert dedicated_resp.pairing_token == service.get_or_create_pairing_token()


def test_mobile_cors_preflight_and_headers(client: TestClient):
    """Verifica que FastAPI responda a peticiones CORS preflight para soportar APK nativa (Capacitor)."""
    headers = {
        "Origin": "http://localhost",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-Mobile-Pairing-Token",
    }
    resp = client.options("/api/mobile/status", headers=headers)
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
    assert resp.headers["access-control-allow-origin"] in ("*", "http://localhost")


def test_admin_generate_pin_and_pair_device_flow(client: TestClient, db_session):
    """Verifica el flujo completo de generación de PIN administrativo y vinculación móvil (Sin Cámara)."""
    # 1. Generar PIN como administrador local
    resp_pin = client.post("/api/mobile/admin/generate-pin?ttl_seconds=300")
    assert resp_pin.status_code == 200
    pin_data = resp_pin.json()
    assert "pin" in pin_data
    pin = pin_data["pin"]
    assert len(pin) == 6
    assert pin.isdigit()

    # 2. Formato inválido (< 6 dígitos) -> 422
    resp_inv = client.post("/api/mobile/pair-pin", json={"pin": "123"})
    assert resp_inv.status_code == 422

    # 3. PIN incorrecto -> 400
    wrong_pin = "000000" if pin != "000000" else "999999"
    resp_wrong = client.post("/api/mobile/pair-pin", json={"pin": wrong_pin})
    assert resp_wrong.status_code == 400
    assert "PIN incorrecto" in resp_wrong.json()["detail"]

    # 4. PIN correcto -> 200 OK con token maestro
    resp_pair = client.post("/api/mobile/pair-pin", json={"pin": pin})
    assert resp_pair.status_code == 200
    pair_res = resp_pair.json()
    assert pair_res["success"] is True
    assert "pairing_token" in pair_res
    received_token = pair_res["pairing_token"]
    assert received_token.startswith("sec_")

    # 5. Usar el token recibido para autenticar una petición a /api/mobile/catalog -> 200 OK
    cat_resp = client.get("/api/mobile/catalog", headers={"X-Mobile-Pairing-Token": received_token})
    assert cat_resp.status_code == 200

    # 6. Intentar canjear el mismo PIN de nuevo -> 400 (ya consumido)
    resp_reuse = client.post("/api/mobile/pair-pin", json={"pin": pin})
    assert resp_reuse.status_code == 400


def test_admin_generate_pin_access_control(client: TestClient):
    """Verifica que /api/mobile/admin/generate-pin rechace IPs externas a la administración."""
    from fastapi import HTTPException
    from starlette.requests import Request
    from backend.api.routers.mobile import generate_admin_pairing_pin

    service = MobileSyncService()

    # IP de la Wi-Fi pública (192.168.1.55) -> 403 Forbidden
    wifi_request = Request({"type": "http", "client": ("192.168.1.55", 43210)})
    with pytest.raises(HTTPException) as exc_info:
        generate_admin_pairing_pin(request=wifi_request, service=service)
    assert exc_info.value.status_code == 403
    assert "Acceso denegado" in exc_info.value.detail









