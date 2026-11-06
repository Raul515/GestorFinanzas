"""
Pruebas de integración para los endpoints REST del espacio conjunto (/joint) (Spec 010 - Fase 4).
Verifica los contratos HTTP, códigos de estado (200, 201, 400, 404, 409) y observabilidad.
"""

from pathlib import Path
import json
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


def test_joint_subcategories_crud_and_sync(client: TestClient, api_sync_dir: str):
    """Verifica la creación, edición y eliminación de subcategorías de necesidades comunes y sus eventos delta."""
    # 1. Configurar hogar
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Subcategorías",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )

    # 2. Consultar categorías para obtener el ID de Necesidades Básicas
    cats_resp = client.get("/joint/categories")
    assert cats_resp.status_code == 200
    cats = cats_resp.json()
    assert len(cats) >= 1
    cat_id = cats[0]["id"]

    # 3. Crear subcategoría común (POST /joint/subcategories)
    create_payload = {
        "joint_category_id": cat_id,
        "name": "Mascotas (Alimento y Salud)",
        "monthly_budget": 95.0,
    }
    create_resp = client.post("/joint/subcategories", json=create_payload)
    assert create_resp.status_code == 201
    created_sub = create_resp.json()
    assert created_sub["name"] == "Mascotas (Alimento y Salud)"
    assert created_sub["monthly_budget"] == 95.0
    sub_id = created_sub["id"]

    # 4. Verificar que se emitió evento delta SUBCATEGORY (UPSERT) en outbox
    outbox_files = list((Path(api_sync_dir) / "outbox").glob("*.json"))
    sub_events = []
    for f in outbox_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            if data.get("entity_type") == "SUBCATEGORY":
                sub_events.append(data)
    assert any(e["action"] == "UPSERT" and e["payload"]["name"] == "Mascotas (Alimento y Salud)" for e in sub_events)

    # 5. Editar subcategoría (PUT /joint/subcategories/{id})
    update_resp = client.put(f"/joint/subcategories/{sub_id}", json={"monthly_budget": 130.0})
    assert update_resp.status_code == 200
    assert update_resp.json()["monthly_budget"] == 130.0

    # 6. Eliminar subcategoría (DELETE /joint/subcategories/{id})
    del_resp = client.delete(f"/joint/subcategories/{sub_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 7. Verificar que no aparece en GET /joint/subcategories
    get_all = client.get("/joint/subcategories")
    assert get_all.status_code == 200
    assert not any(s["id"] == sub_id for s in get_all.json())


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

    # Veto patrimonial: Eliminar hucha con saldo > 0 sin destino debe ser rechazado con 400
    veto_resp = client.delete(f"/joint/sinking-funds/{fund_id}")
    assert veto_resp.status_code == 400
    assert "Debe seleccionar el destino obligatorio" in veto_resp.json()["detail"]

    # En modo pre-convivencia, liberar a tesorería general debe ser rechazado con 400
    pre_treasury_resp = client.delete(f"/joint/sinking-funds/{fund_id}?action_on_balance=RELEASE_TO_TREASURY")
    assert pre_treasury_resp.status_code == 400
    assert "no existe tesorería general" in pre_treasury_resp.json()["detail"]

    # En modo pre-convivencia, devolver a miembros (REFUND_MEMBERS) liquida el saldo y borra la hucha
    del_resp = client.delete(f"/joint/sinking-funds/{fund_id}?action_on_balance=REFUND_MEMBERS")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
    assert del_resp.json()["action_on_balance"] == "REFUND_MEMBERS"


def test_joint_sinking_fund_reallocate_and_cohabitation_release(client: TestClient):
    """Valida la reasignación de saldo a otra hucha y la liberación a tesorería en convivencia."""
    # 1. Configurar hogar en modo convivencia
    setup_resp = client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Convivencia",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )
    assert setup_resp.status_code == 201

    # Crear dos huchas
    f1 = client.post("/joint/sinking-funds", json={"name": "Hucha A", "target_amount": 500.0, "current_balance": 100.0}).json()
    f2 = client.post("/joint/sinking-funds", json={"name": "Hucha B", "target_amount": 500.0, "current_balance": 50.0}).json()

    # Reasignar saldo de Hucha A a Hucha B al eliminar
    del_realloc = client.delete(f"/joint/sinking-funds/{f1['id']}?action_on_balance=REALLOCATE&reallocate_to_fund_id={f2['id']}")
    assert del_realloc.status_code == 200

    # Hucha B debe haber incrementado su saldo a 150.0 €
    updated_f2 = client.get(f"/joint/sinking-funds").json()
    assert len(updated_f2) == 1
    assert updated_f2[0]["id"] == f2["id"]
    assert updated_f2[0]["current_balance"] == 150.0

    # En convivencia, liberar a tesorería (RELEASE_TO_TREASURY) está permitido
    del_treasury = client.delete(f"/joint/sinking-funds/{f2['id']}?action_on_balance=RELEASE_TO_TREASURY")
    assert del_treasury.status_code == 200
    assert del_treasury.json()["deleted"] is True

    # Verificar que ya no quedan huchas
    assert client.get("/joint/sinking-funds").json() == []


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
    """
    Verifica el endpoint de aportación asistida en 1 clic (/joint/contributions/asentar-asistida),
    crecimiento real de huchas (R-4), reversión por DELETE /joint/contributions/{id} (R-6)
    y eliminación en cascada desde la transacción personal (R-6).
    """
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Aportación",
            "cohabitation_stage": "COHABITATION",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "split_mode": "EQUAL_50_50",
        },
    )

    # Crear una hucha activa para probar asignación y crecimiento (R-4)
    fund_resp = client.post(
        "/joint/sinking-funds",
        json={
            "name": "Hucha Vacaciones 2027",
            "target_amount": 1200.0,
            "current_balance": 100.0,
            "monthly_target_amount": 100.0,
            "allocation_percentage": 100.0,
            "status": "ACTIVE",
            "priority": 1,
        },
    )
    assert fund_resp.status_code == 201
    fund_id = fund_resp.json()["id"]

    # 1. Aportación ordinaria mensual
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

    # Comprobar que la aportación figura en /joint/contributions con UUID (R-5)
    contribs_resp = client.get("/joint/contributions?month=2026-11")
    assert contribs_resp.status_code == 200
    contribs = contribs_resp.json()
    assert len(contribs) == 1
    assert contribs[0]["amount"] == 750.0
    assert "uuid" in contribs[0]
    first_contrib_id = contribs[0]["id"]
    first_tx_id = contribs[0]["personal_transaction_id"]

    # 2. Aportación extraordinaria directa a la hucha (R-4)
    extra_payload = {
        "month": "2026-11",
        "amount": 200.0,
        "contributor_profile": "MEMBER_A",
        "target_sinking_fund_id": fund_id,
    }
    resp_extra = client.post("/joint/contributions/asentar-asistida", json=extra_payload)
    assert resp_extra.status_code == 201

    # Verificar que el saldo de la hucha creció en 200 € directos (R-4)
    funds_list = client.get("/joint/sinking-funds").json()
    fund_check = next(f for f in funds_list if f["id"] == fund_id)
    assert fund_check["current_balance"] >= 300.0

    # 3. Eliminar aportación extraordinaria vía DELETE /joint/contributions/{id} (R-6)
    extra_contribs = client.get("/joint/contributions?month=2026-11").json()
    assert len(extra_contribs) == 2
    extra_contrib_id = next(c["id"] for c in extra_contribs if c["id"] != first_contrib_id)

    del_resp = client.delete(f"/joint/contributions/{extra_contrib_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Comprobar que el saldo de la hucha se revirtió (R-6)
    funds_list_after = client.get("/joint/sinking-funds").json()
    fund_after_del = next(f for f in funds_list_after if f["id"] == fund_id)
    assert fund_after_del["current_balance"] < fund_check["current_balance"]

    # 4. Eliminación en cascada: borrar la transacción personal en /transactions/{id} (R-6)
    assert first_tx_id is not None
    tx_del_resp = client.delete(f"/transactions/{first_tx_id}")
    assert tx_del_resp.status_code == 200

    # Verificar que la aportación conjunta vinculada fue eliminada en cascada
    contribs_final = client.get("/joint/contributions?month=2026-11").json()
    assert len(contribs_final) == 0

    # Comprobar endpoint de cálculo dinámico de cuotas (Mejora 1)
    # 4. Salvaguarda: Rechazar aportación a nombre de la pareja (MEMBER_B) desde dispositivo local (MEMBER_A)
    impersonate_payload = {
        "month": "2026-11",
        "amount": 500.0,
        "contributor_profile": "MEMBER_B",
    }
    resp_imp = client.post("/joint/contributions/asentar-asistida", json=impersonate_payload)
    assert resp_imp.status_code == 403
    assert "Solo puedes asentar aportaciones desde tu propio perfil local" in resp_imp.json()["detail"]

    calc_resp = client.get("/joint/contributions/calculation")
    assert calc_resp.status_code == 200
    calc_data = calc_resp.json()
    assert "member_a_contribution" in calc_data
    assert "member_b_contribution" in calc_data
    assert calc_data["local_profile"] == "MEMBER_A"


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


def test_joint_reset_lifecycle(client: TestClient, api_sync_dir: str):
    """Verifica el restablecimiento completo de la cuenta conjunta a Estado Cero (/joint/reset) y emisión de delta ACCOUNT (DELETE)."""
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

    # 4. Verificar que se emitió el delta ACCOUNT (DELETE) a outbox para la pareja
    outbox_files = [f for f in (Path(api_sync_dir) / "outbox").glob("*.json") if not f.name.endswith(".tmp")]
    assert len(outbox_files) > 0
    all_events = [json.loads(f.read_text(encoding="utf-8")) for f in outbox_files]
    delete_account_events = [e for e in all_events if e.get("entity_type") == "ACCOUNT" and e.get("action") == "DELETE"]
    assert len(delete_account_events) == 1
    assert delete_account_events[0]["payload"]["household_name"] == "Hogar a Purgar"


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
            "member_a_contribution_pct": 65.0,
            "member_b_contribution_pct": 35.0,
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
    assert res_inv["invitation"]["member_a_contribution_pct"] == 65.0
    assert res_inv["invitation"]["member_b_contribution_pct"] == 35.0

    # 4. Aceptar la invitación en 1 clic
    accept_resp = client.post("/joint/accept-invitation")
    assert accept_resp.status_code == 201
    acc = accept_resp.json()
    assert acc["household_name"] == "Hogar Compartido D&R"
    assert acc["member_a_name"] == "David"
    assert acc["member_b_name"] == "Raquel"
    assert acc["member_a_contribution_pct"] == 65.0
    assert acc["member_b_contribution_pct"] == 35.0
    assert acc["local_profile"] == "MEMBER_B"
    assert acc["remote_profile"] == "MEMBER_A"

    # 5. La cuenta ya existe, por lo que /joint/invitation retorna False y re-aceptar da 409
    assert client.get("/joint/invitation").json()["has_invitation"] is False
    assert client.post("/joint/accept-invitation").status_code == 409


def test_joint_export_and_sync_viewer_endpoints(client: TestClient):
    """
    Fase 7.2: Valida los endpoints REST de exportacion a Excel (.xlsx),
    inspeccion de eventos en el visor de sincronizacion y reintento de errores.
    """
    # 1. Configurar hogar
    setup_resp = client.post(
        "/joint/setup",
        json={
            "household_name": "Casa Test Export",
            "cohabitation_stage": "COHABITATION",
            "split_mode": "EQUAL_50_50",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "member_a_reference_income": 3000.0,
            "member_b_reference_income": 2000.0,
        },
    )
    assert setup_resp.status_code == 201

    # 2. Descargar Excel
    export_resp = client.get("/joint/export/excel")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=finanzas_hogar_1_" in export_resp.headers.get("content-disposition", "")
    assert len(export_resp.content) > 0

    # 3. Consultar eventos de sincronizacion
    events_resp = client.get("/joint/sync/events")
    assert events_resp.status_code == 200
    data_ev = events_resp.json()
    assert "outbox_count" in data_ev
    assert "inbox_count" in data_ev
    assert "processed_count" in data_ev
    assert "error_count" in data_ev

    # 4. Reintentar errores (sin errores pendientes devuelve 0 retried)
    retry_resp = client.post("/joint/sync/retry-errors")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["retried_count"] == 0



def test_joint_settlement_api_flow(client: TestClient):
    """Valida el flujo integral de liquidación de gastos adelantados y reembolsos vía API (Fase 7.3)."""
    # 1. Configurar hogar
    setup_resp = client.post(
        "/joint/setup",
        json={
            "household_name": "Casa Test Settlement Flow",
            "cohabitation_stage": "COHABITATION",
            "split_mode": "EQUAL_50_50",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "member_a_reference_income": 2500.0,
            "member_b_reference_income": 2200.0,
        },
    )
    assert setup_resp.status_code == 201

    subcats = client.get("/joint/subcategories").json()
    subcat_id = subcats[0]["id"]

    # 2. Registrar gasto adelantado por MEMBER_A (Reembolso de Fondo Común)
    tx1_resp = client.post(
        "/joint/transactions",
        json={
            "date": "2026-11-04",
            "amount": 100.0,
            "description": "Compra Leroy Merlin David",
            "joint_subcategory_id": subcat_id,
            "created_by_profile": "MEMBER_A",
            "paid_by": "MEMBER_A",
            "settlement_mechanism": "COMMON_REIMBURSEMENT",
        },
    )
    assert tx1_resp.status_code == 201
    tx1 = tx1_resp.json()
    assert tx1["settlement_status"] == "PENDING"
    assert tx1["paid_by"] == "MEMBER_A"

    # 3. Registrar gasto adelantado por MEMBER_B (Liquidación Directa Bizum)
    tx2_resp = client.post(
        "/joint/transactions",
        json={
            "date": "2026-11-04",
            "amount": 60.0,
            "description": "Cena compartida Raquel",
            "joint_subcategory_id": subcat_id,
            "created_by_profile": "MEMBER_B",
            "paid_by": "MEMBER_B",
            "settlement_mechanism": "DIRECT_MEMBER_SETTLEMENT",
        },
    )
    assert tx2_resp.status_code == 201
    tx2 = tx2_resp.json()
    assert tx2["settlement_status"] == "PENDING"

    # 4. Consultar resumen de liquidación
    summary_resp = client.get("/joint/settlement/summary")
    assert summary_resp.status_code == 200
    s_data = summary_resp.json()
    assert s_data["unsettled_count"] == 2
    assert s_data["common_reimbursement"]["owes_member_a"] == 100.0
    assert s_data["common_reimbursement"]["total_common_debt"] == 100.0
    assert s_data["direct_settlement"]["member_a_owes_member_b"] == 30.0
    assert s_data["direct_settlement"]["net_amount"] == 30.0
    assert s_data["direct_settlement"]["net_debtor"] == "MEMBER_A"

    # 5. Liquidar individualmente tx1
    settle1_resp = client.post(f"/joint/settlement/settle-transaction/{tx1['id']}")
    assert settle1_resp.status_code == 200
    assert settle1_resp.json()["settlement_status"] == "SETTLED"
    assert settle1_resp.json()["settled_at"] is not None

    # Consultar resumen tras liquidación de tx1
    summary_resp2 = client.get("/joint/settlement/summary")
    assert summary_resp2.status_code == 200
    s_data2 = summary_resp2.json()
    assert s_data2["unsettled_count"] == 1
    assert s_data2["common_reimbursement"]["total_common_debt"] == 0.0
    assert s_data2["direct_settlement"]["net_amount"] == 30.0

    # 6. Liquidar en bloque con settle-all
    settle_all_resp = client.post("/joint/settlement/settle-all")
    assert settle_all_resp.status_code == 200
    settled_list = settle_all_resp.json()
    assert len(settled_list) == 1
    assert settled_list[0]["id"] == tx2["id"]
    assert settled_list[0]["settlement_status"] == "SETTLED"

    # 7. Resumen final completamente a cero
    summary_resp3 = client.get("/joint/settlement/summary")
    assert summary_resp3.status_code == 200
    s_data3 = summary_resp3.json()
    assert s_data3["unsettled_count"] == 0
    assert s_data3["common_reimbursement"]["total_common_debt"] == 0.0
    assert s_data3["direct_settlement"]["net_amount"] == 0.0


def test_joint_sinking_fund_transfer_api_flow(client: TestClient):
    """Valida el flujo integral de traspaso y rebalanceo entre huchas vía API REST (Fase 7.4)."""
    # 1. Configurar hogar
    setup_resp = client.post(
        "/joint/setup",
        json={
            "household_name": "Casa Test Transfer Flow",
            "cohabitation_stage": "COHABITATION",
            "split_mode": "EQUAL_50_50",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "member_a_reference_income": 2500.0,
            "member_b_reference_income": 2200.0,
        },
    )
    assert setup_resp.status_code == 201

    # 2. Crear dos huchas
    f1_resp = client.post(
        "/joint/sinking-funds",
        json={"name": "Vacaciones Playa", "target_amount": 1000.0, "current_balance": 400.0, "status": "ACTIVE"},
    )
    assert f1_resp.status_code == 201
    f1 = f1_resp.json()

    f2_resp = client.post(
        "/joint/sinking-funds",
        json={"name": "Seguro Moto", "target_amount": 500.0, "current_balance": 100.0, "status": "ACTIVE"},
    )
    assert f2_resp.status_code == 201
    f2 = f2_resp.json()

    # 3. Traspaso exitoso de 150€ de f1 a f2
    tr_resp = client.post(
        "/joint/sinking-funds/transfer",
        json={
            "source_fund_id": f1["id"],
            "target_fund_id": f2["id"],
            "amount": 150.0,
            "notes": "Rebalanceo viaje a seguro",
        },
    )
    assert tr_resp.status_code == 201
    tr_data = tr_resp.json()
    assert tr_data["amount"] == 150.0
    assert tr_data["source_fund_name"] == "Vacaciones Playa"
    assert tr_data["target_fund_name"] == "Seguro Moto"

    # Verificar saldos actualizados de ambas huchas
    funds_after = client.get("/joint/sinking-funds").json()
    f1_after = next(f for f in funds_after if f["id"] == f1["id"])
    f2_after = next(f for f in funds_after if f["id"] == f2["id"])
    assert f1_after["current_balance"] == 250.0
    assert f2_after["current_balance"] == 250.0

    # 4. Consultar historial de traspasos
    history_resp = client.get("/joint/sinking-funds/transfers")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) == 1
    assert history[0]["notes"] == "Rebalanceo viaje a seguro"

    # 5. Intentar traspasar más saldo del disponible arroja 400 Bad Request
    fail_resp = client.post(
        "/joint/sinking-funds/transfer",
        json={
            "source_fund_id": f1["id"],
            "target_fund_id": f2["id"],
            "amount": 300.0,  # Disponible: 250€
        },
    )
    assert fail_resp.status_code == 400


def test_joint_transactions_search_endpoint(client: TestClient):
    """Valida el endpoint de búsqueda global y filtrado multicriterio GET /joint/transactions/search (Fase 7.6)."""
    # 1. Configurar cuenta conjunta
    setup_payload = {
        "household_name": "Casa Búsqueda API",
        "member_a_name": "Carlos",
        "member_b_name": "Elena",
        "cohabitation_stage": "COHABITATION",
        "contribution_strategy": "INCOME_PERCENTAGE",
        "split_mode": "EQUAL_50_50",
        "member_a_reference_income": 2200.0,
        "member_b_reference_income": 1800.0,
        "local_profile": "MEMBER_A",
    }
    client.post("/joint/setup", json=setup_payload)

    # 2. Registrar subcategoría y transacciones
    subcats = client.get("/joint/subcategories").json()
    subcat_id = subcats[0]["id"] if subcats else None

    # Transacción 1: Compra supermercado común
    tx1_resp = client.post(
        "/joint/transactions",
        json={
            "date": "2026-03-10",
            "amount": 85.50,
            "description": "Compra Carrefour Semanal",
            "joint_subcategory_id": subcat_id,
            "created_by_profile": "MEMBER_A",
            "paid_by": "COMMON",
            "settlement_status": "SETTLED",
        },
    )
    assert tx1_resp.status_code == 201

    # Transacción 2: Farmacia adelantada por MEMBER_A
    tx2_resp = client.post(
        "/joint/transactions",
        json={
            "date": "2026-04-12",
            "amount": 24.00,
            "description": "Farmacia jarabe Elena",
            "joint_subcategory_id": subcat_id,
            "created_by_profile": "MEMBER_A",
            "paid_by": "MEMBER_A",
            "settlement_mechanism": "DIRECT_MEMBER_SETTLEMENT",
            "settlement_status": "PENDING",
        },
    )
    assert tx2_resp.status_code == 201

    # 3. Búsqueda por texto (query)
    resp_text = client.get("/joint/transactions/search", params={"query": "carrefour"})
    assert resp_text.status_code == 200
    res_text = resp_text.json()
    assert len(res_text) == 1
    assert "Carrefour" in res_text[0]["description"]

    # 4. Filtrado por pagador y estado
    resp_payer = client.get(
        "/joint/transactions/search",
        params={"paid_by": "MEMBER_A", "settlement_status": "PENDING"},
    )
    assert resp_payer.status_code == 200
    res_payer = resp_payer.json()
    assert len(res_payer) == 1
    assert res_payer[0]["paid_by"] == "MEMBER_A"
    assert res_payer[0]["amount"] == 24.00

    # 5. Filtrado por rango de fechas
    resp_dates = client.get(
        "/joint/transactions/search",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    assert resp_dates.status_code == 200
    res_dates = resp_dates.json()
    assert len(res_dates) == 1
    assert res_dates[0]["description"] == "Farmacia jarabe Elena"

    # 6. Filtrado por rango de importes
    resp_amt = client.get(
        "/joint/transactions/search",
        params={"min_amount": 50.0, "max_amount": 100.0},
    )
    assert resp_amt.status_code == 200
    res_amt = resp_amt.json()
    assert len(res_amt) == 1
    assert res_amt[0]["amount"] == 85.50


def test_joint_account_global_fixed_budget_and_calculation(client: TestClient):
    """
    Verifica que la configuración de la cuenta conjunta soporte la estrategia GLOBAL_FIXED
    con custom_total_monthly_budget, y que el endpoint de cálculo devuelva las cuotas correctas.
    """
    # 1. Asegurar cuenta inicializada
    resp = client.get("/joint/account")
    if resp.status_code == 404:
        init_resp = client.post(
            "/joint/setup",
            json={
                "household_name": "Hogar Fijo Test",
                "member_a_name": "Raul",
                "member_b_name": "Evita",
                "cohabitation_stage": "COHABITATION",
                "split_mode": "EQUAL_50_50",
                "contribution_strategy": "NOMINAL_TEMPLATE",
                "member_a_reference_income": 1500.0,
                "member_b_reference_income": 1500.0,
            },
        )
        assert init_resp.status_code == 201

    # 2. Actualizar a GLOBAL_FIXED con presupuesto manual de 1400.0 €
    upd_resp = client.put(
        "/joint/account",
        json={
            "contribution_strategy": "GLOBAL_FIXED",
            "custom_total_monthly_budget": 1400.0,
            "split_mode": "EQUAL_50_50",
            "cohabitation_stage": "COHABITATION",
        },
    )
    assert upd_resp.status_code == 200
    acc_data = upd_resp.json()
    assert acc_data["contribution_strategy"] == "GLOBAL_FIXED"
    assert acc_data["custom_total_monthly_budget"] == 1400.0

    # 3. Consultar endpoint de cálculo de aportaciones
    calc_resp = client.get("/joint/contributions/calculation")
    assert calc_resp.status_code == 200
    calc_data = calc_resp.json()
    assert calc_data["contribution_strategy"] == "GLOBAL_FIXED"
    assert calc_data["total_household_budget"] == 1400.0
    assert calc_data["member_a_contribution"] == 700.0
    assert calc_data["member_b_contribution"] == 700.0


def test_remote_deletion_endpoints_and_clear_errors(client: TestClient, api_sync_dir: str):
    """Verifica los endpoints de borrado remoto (pending, reject, accept) y limpieza de errores."""
    import uuid

    # 1. Asegurar cuenta configurada
    client.post(
        "/joint/setup",
        json={
            "household_name": "Hogar Borrado Remoto",
            "member_a_name": "Raul",
            "member_b_name": "Evita",
            "cohabitation_stage": "COHABITATION",
            "split_mode": "EQUAL_50_50",
            "contribution_strategy": "NOMINAL_TEMPLATE",
            "member_a_reference_income": 2000.0,
            "member_b_reference_income": 2000.0,
        },
    )

    # 2. Sin eventos pendientes
    pend_resp = client.get("/joint/remote-deletion/pending")
    assert pend_resp.status_code == 200
    assert pend_resp.json()["pending"] is False

    # 3. Colocar un evento ACCOUNT DELETE en inbox
    inbox_dir = Path(api_sync_dir) / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    del_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "ACCOUNT",
        "action": "DELETE",
        "origin_device_id": "REMOTE_MAC",
        "timestamp_utc": "2026-11-20T12:00:00Z",
        "payload": {"household_name": "Hogar Borrado Remoto"},
    }
    with open(inbox_dir / "evt_delete.json", "w", encoding="utf-8") as f:
        json.dump(del_evt, f)

    # 4. Comprobar que pending lo detecta
    pend_resp2 = client.get("/joint/remote-deletion/pending")
    assert pend_resp2.status_code == 200
    assert pend_resp2.json()["pending"] is True
    assert pend_resp2.json()["data"]["origin_device_id"] == "REMOTE_MAC"

    # 5. Rechazar borrado
    rej_resp = client.post("/joint/remote-deletion/reject")
    assert rej_resp.status_code == 200
    assert rej_resp.json()["accepted"] is False

    # La cuenta sigue existiendo
    status_resp = client.get("/joint/status")
    assert status_resp.json()["is_configured"] is True

    # 6. Colocar otro evento ACCOUNT DELETE y ahora Aceptar
    del_evt2 = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "ACCOUNT",
        "action": "DELETE",
        "origin_device_id": "REMOTE_MAC",
        "timestamp_utc": "2026-11-20T13:00:00Z",
        "payload": {"household_name": "Hogar Borrado Remoto"},
    }
    with open(inbox_dir / "evt_delete2.json", "w", encoding="utf-8") as f:
        json.dump(del_evt2, f)

    acc_resp = client.post("/joint/remote-deletion/accept")
    assert acc_resp.status_code == 200
    assert acc_resp.json()["accepted"] is True

    # La cuenta vuelve a Estado Cero
    status_resp2 = client.get("/joint/status")
    assert status_resp2.json()["is_configured"] is False

    # 7. Probar clear-errors
    err_dir = Path(api_sync_dir) / "error"
    err_dir.mkdir(parents=True, exist_ok=True)
    with open(err_dir / "err_dummy.json", "w", encoding="utf-8") as f:
        f.write("{}")
    clear_resp = client.post("/joint/sync/clear-errors")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["deleted_count"] == 1
