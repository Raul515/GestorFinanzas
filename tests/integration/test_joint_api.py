"""
Pruebas de integración para los endpoints REST del espacio conjunto (/joint) (Spec 010 - Fase 4).
Verifica los contratos HTTP, códigos de estado (200, 201, 400, 404, 409) y observabilidad.
"""

from pathlib import Path
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routers.joint import get_sync_service
from backend.services.joint_sync_service import JointSyncService


@pytest.fixture
def api_sync_dir():
    """Directorio temporal aislado para sincronización en pruebas de API."""
    temp_dir = tempfile.mkdtemp(prefix="test_api_sync_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def override_sync_service(api_sync_dir: str):
    """Sobreescribe el servicio de sincronización para que use el directorio temporal."""
    sync_service = JointSyncService(base_sync_dir=api_sync_dir, local_device_id="TEST_DEVICE_A")
    app.dependency_overrides[get_sync_service] = lambda: sync_service
    yield
    app.dependency_overrides.pop(get_sync_service, None)


def test_joint_status_and_onboarding_lifecycle(client: TestClient):
    """Verifica el Estado Cero inicial y la ejecución del onboarding."""
    # 1. Estado Cero: no configurado
    status_resp = client.get("/joint/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_configured"] is False

    # 2. Consultar cuenta devuelve 404 antes de configurar
    account_resp = client.get("/joint/account")
    assert account_resp.status_code == 404

    # 3. Onboarding exitoso (POST /joint/setup)
    setup_payload = {
        "household_name": "Nuestro Piso",
        "cohabitation_stage": "PRE_COHABITATION",
        "contribution_strategy": "NOMINAL_TEMPLATE",
        "split_mode": "EQUAL_50_50",
        "member_a_reference_income": 2600.0,
        "member_b_reference_income": 2200.0,
        "member_a_contribution_pct": 50.0,
        "member_b_contribution_pct": 50.0,
        "local_profile": "MEMBER_A",
        "remote_profile": "MEMBER_B",
    }
    create_resp = client.post("/joint/setup", json=setup_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["id"] == 1
    assert created_data["household_name"] == "Nuestro Piso"

    # 4. Verificar que se sembraron las subcategorías por defecto (4 subcategorías)
    subcats_resp = client.get("/joint/subcategories")
    assert subcats_resp.status_code == 200
    subcats = subcats_resp.json()
    assert len(subcats) == 4
    names = [s["name"] for s in subcats]
    assert "Vivienda (Alquiler / Hipoteca)" in names

    # 5. Intentar crear una segunda cuenta devuelve 409 Conflict
    conflict_resp = client.post("/joint/setup", json=setup_payload)
    assert conflict_resp.status_code == 409

    # 6. Estado tras onboarding
    status_after = client.get("/joint/status")
    assert status_after.status_code == 200
    assert status_after.json()["is_configured"] is True
    assert status_after.json()["household_name"] == "Nuestro Piso"


def test_joint_account_update_endpoint(client: TestClient):
    """Verifica la actualización de parámetros del hogar (PUT /joint/account)."""
    # Configurar cuenta
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Inicial",
            "cohabitation_stage": "PRE_COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
            "member_a_reference_income": 2000.0,
            "member_b_reference_income": 2000.0,
        },
    )

    # Actualizar a convivencia plena y cambiar ingresos
    update_payload = {
        "cohabitation_stage": "COHABITATION",
        "member_a_reference_income": 2500.0,
        "household_name": "Hogar Renovado",
    }
    put_resp = client.put("/joint/account", json=update_payload)
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["cohabitation_stage"] == "COHABITATION"
    assert updated["member_a_reference_income"] == 2500.0
    assert updated["household_name"] == "Hogar Renovado"


def test_joint_sinking_funds_endpoints(client: TestClient):
    """Verifica el catálogo y gestión de Huchas de Amortización (/joint/sinking-funds)."""
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Metas",
            "cohabitation_stage": "PRE_COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )

    # Inicialmente lista vacía
    get_init = client.get("/joint/sinking-funds")
    assert get_init.status_code == 200
    assert get_init.json() == []

    # Crear hucha
    fund_payload = {
        "name": "Entrada de Piso",
        "target_amount": 30000.0,
        "current_balance": 5000.0,
        "monthly_target_amount": 500.0,
        "allocation_percentage": 50.0,
        "status": "ACTIVE",
        "priority": 1,
    }
    create_resp = client.post("/joint/sinking-funds", json=fund_payload)
    assert create_resp.status_code == 201
    fund_data = create_resp.json()
    assert fund_data["id"] is not None
    assert fund_data["name"] == "Entrada de Piso"
    fund_id = fund_data["id"]

    # Editar hucha
    update_resp = client.put(f"/joint/sinking-funds/{fund_id}", json={"current_balance": 6000.0})
    assert update_resp.status_code == 200
    assert update_resp.json()["current_balance"] == 6000.0

    # Eliminar hucha
    del_resp = client.delete(f"/joint/sinking-funds/{fund_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_joint_transactions_endpoints(client: TestClient):
    """Verifica el registro y eliminación de gastos comunes (/joint/transactions)."""
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Gastos",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )
    subcats = client.get("/joint/subcategories").json()
    subcat_id = subcats[0]["id"]

    # Registrar gasto
    tx_payload = {
        "date": "2026-11-03",
        "amount": 85.0,
        "description": "Compra semanal",
        "joint_subcategory_id": subcat_id,
        "created_by_profile": "MEMBER_A",
    }
    post_resp = client.post("/joint/transactions", json=tx_payload)
    assert post_resp.status_code == 201
    tx_data = post_resp.json()
    assert tx_data["id"] is not None
    assert tx_data["uuid"] is not None
    tx_id = tx_data["id"]

    # Listar transacciones
    get_resp = client.get("/joint/transactions?year=2026")
    assert get_resp.status_code == 200
    assert len(get_resp.json()) == 1

    # Eliminar transacción (emite tombstone)
    del_resp = client.delete(f"/joint/transactions/{tx_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


def test_assisted_contribution_flow(client: TestClient):
    """Verifica el endpoint de aportación asistida en 1 clic (/joint/contributions/asentar-asistida)."""
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Aportación",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )

    asentar_payload = {
        "month": "2026-11",
        "amount": 750.0,
        "contributor_profile": "MEMBER_A",
    }
    resp = client.post("/joint/contributions/asentar-asistida", json=asentar_payload)
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["amount"] == 750.0

    # Comprobar que la aportación figura en /joint/contributions
    contribs_resp = client.get("/joint/contributions?month=2026-11")
    assert contribs_resp.status_code == 200
    assert len(contribs_resp.json()) == 1
    assert contribs_resp.json()[0]["amount"] == 750.0


def test_joint_health_and_annual_summary_endpoints(client: TestClient):
    """Verifica /joint/health y /joint/annual-summary sin marcadores A vs B."""
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Salud",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
            "member_a_reference_income": 2500.0,
            "member_b_reference_income": 2000.0,
        },
    )

    # 1. Semáforo de salud
    health_resp = client.get("/joint/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert "effort_rate_pct" in health_data
    assert "status" in health_data

    # 2. Resumen Anual consolidado
    annual_resp = client.get("/joint/annual-summary?year=2026")
    assert annual_resp.status_code == 200
    summary = annual_resp.json()
    assert summary["year"] == 2026
    assert "total_needs_spent" in summary
    assert "total_sinking_funds_saved" in summary
    assert "effort_rate_pct" in summary
    assert "health_status" in summary
    assert len(summary["monthly_metrics"]) == 12

    # Prohibición de marcadores A vs B
    dump_str = str(summary).lower()
    assert "member_a_contributed" not in dump_str
    assert "member_b_contributed" not in dump_str


def test_joint_sync_endpoints(client: TestClient, api_sync_dir: str):
    """Verifica los endpoints de control y estado de sincronización (/joint/sync/*)."""
    # 1. Estado de sincronización
    status_resp = client.get("/joint/sync/status")
    assert status_resp.status_code == 200
    assert "is_synchronized" in status_resp.json()

    # 2. Trigger para procesar inbox
    process_resp = client.post("/joint/sync/process-inbox")
    assert process_resp.status_code == 200
    assert process_resp.json()["status"] == "ok"


def test_joint_reset_lifecycle(client: TestClient):
    """Verifica el restablecimiento completo de la cuenta conjunta a Estado Cero (/joint/reset)."""
    # 1. Configurar cuenta y datos
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar a Purgar",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
            "member_a_reference_income": 2000.0,
            "member_b_reference_income": 2000.0,
        },
    )
    # Crear una hucha
    client.post(
        "/joint/sinking-funds",
        json={"name": "Hucha Temporal", "target_amount": 500.0, "current_balance": 100.0},
    )
    assert client.get("/joint/status").json()["is_configured"] is True
    assert len(client.get("/joint/sinking-funds").json()) == 1

    # 2. Resetear cuenta conjunta
    reset_resp = client.post("/joint/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "success"

    # 3. Comprobar que regresó al Estado Cero
    assert client.get("/joint/status").json()["is_configured"] is False
    assert client.get("/joint/account").status_code == 404
    assert client.get("/joint/sinking-funds").json() == []
    assert client.get("/joint/transactions").json() == []


def test_joint_invitation_detection_and_acceptance(client: TestClient, api_sync_dir: str):
    """Verifica la detección automática de invitación y adopción en 1 clic (Opción A)."""
    import json

    # 1. Inicialmente no hay invitaciones ni cuenta configurada
    inv_init = client.get("/joint/invitation")
    assert inv_init.status_code == 200
    assert inv_init.json()["has_invitation"] is False

    # 2. Simular que la pareja deposita un delta ACCOUNT en sync/inbox/
    inbox_dir = Path(api_sync_dir) / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    invitation_payload = {
        "event_id": "evt-inv-001",
        "origin_device_id": "REMOTE_PARTNER_MAC",
        "entity_type": "ACCOUNT",
        "action": "UPSERT",
        "payload": {
            "household_name": "Hogar Compartido D&R",
            "cohabitation_stage": "PRE_COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
            "member_a_reference_income": 2500.0,
            "member_b_reference_income": 2100.0,
            "member_a_name": "David",
            "member_b_name": "Raquel",
        },
    }
    with open(inbox_dir / "account_delta.json", "w", encoding="utf-8") as f:
        json.dump(invitation_payload, f)

    # 3. Detección de la invitación
    inv_detected = client.get("/joint/invitation")
    assert inv_detected.status_code == 200
    res_inv = inv_detected.json()
    assert res_inv["has_invitation"] is True
    assert res_inv["invitation"]["household_name"] == "Hogar Compartido D&R"
    assert res_inv["invitation"]["member_a_name"] == "David"

    # 4. Aceptar la invitación en 1 clic
    accept_resp = client.post("/joint/accept-invitation")
    assert accept_resp.status_code == 201
    acc = accept_resp.json()
    assert acc["household_name"] == "Hogar Compartido D&R"
    assert acc["local_profile"] == "MEMBER_B"
    assert acc["remote_profile"] == "MEMBER_A"

    # 5. La cuenta ya existe, por lo que /joint/invitation retorna False y re-aceptar da 409
    assert client.get("/joint/invitation").json()["has_invitation"] is False
    assert client.post("/joint/accept-invitation").status_code == 409

