"""
Pruebas de integración para los endpoints REST de la Lista de Seguimiento (Watchlist - Spec 003 - Fase 4).
"""

from fastapi.testclient import TestClient


def test_get_watchlist_initially_empty(client: TestClient):
    """Verifica que la lista de seguimiento devuelva un array vacío inicialmente."""
    response = client.get("/watchlist")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_watchlist_item(client: TestClient):
    """Verifica la adición y recuperación de una compañía en la lista de seguimiento."""
    payload = {
        "ticker": "ITX.MC",
        "name": "Inditex S.A.",
        "sector": "Consumer Cyclical",
        "currency": "EUR",
        "price_at_addition": 45.50,
        "notes": "Comprar en retroceso a 40€ con TIR > 15%",
    }
    post_res = client.post("/watchlist", json=payload)
    assert post_res.status_code == 201
    created = post_res.json()
    assert created["ticker"] == "ITX.MC"
    assert created["name"] == "Inditex S.A."
    assert created["price_at_addition"] == 45.50
    assert "created_at" in created

    # Obtener listado
    get_res = client.get("/watchlist")
    assert get_res.status_code == 200
    items = get_res.json()
    assert len(items) == 1
    assert items[0]["ticker"] == "ITX.MC"


def test_create_existing_ticker_updates_record(client: TestClient):
    """Verifica que añadir un ticker ya existente actualice los datos sin duplicar registros."""
    client.post(
        "/watchlist",
        json={
            "ticker": "SAN.MC",
            "name": "Santander",
            "currency": "EUR",
            "price_at_addition": 4.20,
            "notes": "Nota inicial",
        },
    )

    update_res = client.post(
        "/watchlist",
        json={
            "ticker": "san.mc",
            "name": "Banco Santander S.A.",
            "sector": "Financial Services",
            "currency": "EUR",
            "price_at_addition": 4.60,
            "notes": "Precio actualizado tras resultados",
        },
    )
    assert update_res.status_code == 201
    updated = update_res.json()
    assert updated["ticker"] == "SAN.MC"
    assert updated["price_at_addition"] == 4.60
    assert updated["notes"] == "Precio actualizado tras resultados"

    # La lista sigue teniendo 1 único registro
    get_res = client.get("/watchlist")
    assert len(get_res.json()) == 1


def test_delete_watchlist_item_success_and_404(client: TestClient):
    """Verifica la eliminación correcta y el error 404 si el ticker no existe en la lista."""
    client.post(
        "/watchlist",
        json={
            "ticker": "IBE.MC",
            "name": "Iberdrola",
            "price_at_addition": 13.20,
        },
    )

    # Eliminar con éxito (case-insensitive)
    del_res = client.delete("/watchlist/ibe.mc")
    assert del_res.status_code == 200
    assert del_res.json() == {"status": "deleted", "ticker": "IBE.MC"}

    # Comprobar que ya no está
    get_res = client.get("/watchlist")
    assert len(get_res.json()) == 0

    # Intentar eliminar ticker inexistente
    del_missing = client.delete("/watchlist/NO_EXISTE")
    assert del_missing.status_code == 404
    assert "no se encuentra" in del_missing.json()["detail"]


def test_create_watchlist_item_validation_error(client: TestClient):
    """Verifica que un payload inválido (precio negativo o ticker vacío) devuelva código 422."""
    res_neg = client.post(
        "/watchlist",
        json={
            "ticker": "AAPL",
            "name": "Apple",
            "price_at_addition": -10.0,
        },
    )
    assert res_neg.status_code == 422

    res_empty = client.post(
        "/watchlist",
        json={
            "ticker": "",
            "name": "Apple",
            "price_at_addition": 220.0,
        },
    )
    assert res_empty.status_code == 422
