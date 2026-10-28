import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_delete_transaction_success_200(client: TestClient, db_session: Session, seed_data: dict[str, int]):
    """Verifica que eliminar una transacción existente retorne HTTP 200 y el cuerpo esperado."""
    # 1. Crear transacción estándar
    create_payload = {
        "date": str(datetime.date.today()),
        "subcategory_id": seed_data["sub_alquiler_id"],
        "amount": 750.0,
        "description": "Alquiler mensual",
    }
    create_resp = client.post("/transactions/", json=create_payload)
    assert create_resp.status_code == 200
    tx_data = create_resp.json()
    tx_id = tx_data["id"]

    # 2. Eliminar la transacción
    del_resp = client.delete(f"/transactions/{tx_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {
        "status": "deleted",
        "transaction_id": tx_id,
    }

    # 3. Confirmar que ya no aparece en el listado
    list_resp = client.get("/transactions/")
    assert list_resp.status_code == 200
    remaining_ids = [t["id"] for t in list_resp.json()]
    assert tx_id not in remaining_ids


def test_delete_transaction_emergency_fund_reversal_integration(
    client: TestClient, db_session: Session, seed_data: dict[str, int]
):
    """Verifica que eliminar una transacción del fondo de emergencia revierta su saldo acumulado vía API."""
    # 1. Crear aportación de 400 € al fondo de emergencia
    create_payload = {
        "date": str(datetime.date.today()),
        "subcategory_id": seed_data["sub_emergencia_id"],
        "amount": 400.0,
        "description": "Aportación al fondo de emergencia",
    }
    create_resp = client.post("/transactions/", json=create_payload)
    assert create_resp.status_code == 200
    tx_id = create_resp.json()["id"]

    # 2. Comprobar que el saldo actual es 400 €
    status_before = client.get("/advisor/safety-status?mes=BASE")
    assert status_before.status_code == 200
    assert status_before.json()["current_balance"] == 400.0

    # 3. Eliminar la aportación vía DELETE
    del_resp = client.delete(f"/transactions/{tx_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # 4. Comprobar que el saldo del fondo se revirtió a 0 €
    status_after = client.get("/advisor/safety-status?mes=BASE")
    assert status_after.status_code == 200
    assert status_after.json()["current_balance"] == 0.0


def test_delete_transaction_not_found_404(client: TestClient):
    """Verifica que intentar eliminar una transacción con ID inexistente retorne HTTP 404."""
    del_resp = client.delete("/transactions/999999")
    assert del_resp.status_code == 404
    assert del_resp.json()["detail"] == "Transaction not found"


def test_delete_transaction_invalid_id_type_422(client: TestClient):
    """Verifica que pasar un ID no numérico retorne HTTP 422 de validación FastAPI."""
    del_resp = client.delete("/transactions/invalid-id")
    assert del_resp.status_code == 422
