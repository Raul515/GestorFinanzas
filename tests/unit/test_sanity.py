from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from frontend import api_client


def test_sanity_db_and_seed(db_session: Session, seed_data: dict[str, int]):
    """Verifica que el motor SQLite en memoria y la fixture seed_data funcionen con normalidad."""
    assert seed_data["cat_ingresos_id"] > 0
    assert seed_data["sub_emergencia_id"] > 0


def test_sanity_api_client(client: TestClient):
    """Verifica que el TestClient se comunique con la aplicación FastAPI con inyección de dependencias sobreescrita."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Gestor Finanzas API funcionando"}


@patch("frontend.api_client.requests.get")
def test_frontend_api_client_market_methods(mock_get):
    # Test get_macro_indicators
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"indicators": []}
    mock_get.return_value = mock_resp

    res = api_client.get_macro_indicators()
    assert res == {"indicators": []}

    # Test get_market_news
    mock_resp.json.return_value = {"news": []}
    res_news = api_client.get_market_news(limit=5)
    assert res_news == {"news": []}


@patch("frontend.api_client.requests.post")
def test_frontend_api_client_refresh(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"message": "actualizado"}
    mock_post.return_value = mock_resp

    res = api_client.refresh_market_radar()
    assert res == {"message": "actualizado"}


@patch("frontend.api_client.requests.get")
def test_frontend_api_client_handles_errors_gracefully(mock_get):
    import requests
    # 1. Simular error de red (ConnectionError)
    mock_get.side_effect = requests.exceptions.ConnectionError("Backend inaccesible")
    assert api_client.get_categorias() == []
    assert api_client.get_macro_indicators() is None

    # 2. Simular respuesta HTTP 500
    mock_get.side_effect = None
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_get.return_value = mock_resp
    assert api_client.get_market_news() is None
    assert api_client.get_screener_universes() == []
    assert api_client.get_screener_universe("ibex35") is None


@patch("frontend.api_client.requests.get")
@patch("frontend.api_client.requests.post")
def test_frontend_api_client_screener_methods(mock_post, mock_get):
    """Verifica las llamadas exitosas de los métodos de screener en el cliente del frontend."""
    # Test get_screener_universes
    mock_resp_u = MagicMock()
    mock_resp_u.status_code = 200
    mock_resp_u.json.return_value = [{"id": "ibex35", "name": "IBEX 35"}]
    mock_get.return_value = mock_resp_u

    univs = api_client.get_screener_universes()
    assert len(univs) == 1
    assert univs[0]["id"] == "ibex35"

    # Test get_screener_universe
    mock_resp_scr = MagicMock()
    mock_resp_scr.status_code = 200
    mock_resp_scr.json.return_value = {"universe": "ibex35", "items": [{"ticker": "ITX.MC"}]}
    mock_get.return_value = mock_resp_scr

    data = api_client.get_screener_universe("ibex35", preset="quality", max_pe=25.0)
    assert data is not None
    assert data["universe"] == "ibex35"
    assert len(data["items"]) == 1

    # Test get_screener_custom
    mock_resp_cust = MagicMock()
    mock_resp_cust.status_code = 200
    mock_resp_cust.json.return_value = {"universe": "custom", "items": [{"ticker": "AAPL"}]}
    mock_post.return_value = mock_resp_cust

    custom_data = api_client.get_screener_custom(["AAPL"], filter_params={"search_query": "apple"})
    assert custom_data is not None
    assert custom_data["universe"] == "custom"

    # Test refresh_screener_universe
    mock_resp_ref = MagicMock()
    mock_resp_ref.status_code = 200
    mock_resp_ref.json.return_value = {"notes": "actualizado"}
    mock_post.return_value = mock_resp_ref

    ref_res = api_client.refresh_screener_universe("ibex35")
    assert ref_res == {"notes": "actualizado"}


@patch("frontend.api_client.requests.get")
@patch("frontend.api_client.requests.post")
def test_frontend_api_client_deepdive_methods(mock_post, mock_get):
    """Verifica las llamadas cliente de Deep Dive (obtención y refresco forzado)."""
    # Test get_deepdive_analysis
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ticker": "ITX.MC", "current_price": 45.5}
    mock_get.return_value = mock_resp

    data = api_client.get_deepdive_analysis("itx.mc")
    assert data is not None
    assert data["ticker"] == "ITX.MC"
    assert data["current_price"] == 45.5

    # Test refresh_deepdive_analysis
    mock_resp_ref = MagicMock()
    mock_resp_ref.status_code = 200
    mock_resp_ref.json.return_value = {"ticker": "ITX.MC", "from_cache": False}
    mock_post.return_value = mock_resp_ref

    ref_data = api_client.refresh_deepdive_analysis("itx.mc")
    assert ref_data is not None
    assert ref_data["from_cache"] is False


@patch("frontend.api_client.requests.get")
@patch("frontend.api_client.requests.post")
@patch("frontend.api_client.requests.delete")
def test_frontend_api_client_watchlist_methods(mock_del, mock_post, mock_get):
    """Verifica las operaciones CRUD del cliente para la lista de seguimiento (Watchlist)."""
    # Test get_watchlist
    mock_resp_get = MagicMock()
    mock_resp_get.status_code = 200
    mock_resp_get.json.return_value = [{"ticker": "SAN.MC", "price_at_addition": 4.5}]
    mock_get.return_value = mock_resp_get

    watchlist = api_client.get_watchlist()
    assert len(watchlist) == 1
    assert watchlist[0]["ticker"] == "SAN.MC"

    # Test add_to_watchlist
    mock_resp_post = MagicMock()
    mock_resp_post.status_code = 201
    mock_resp_post.json.return_value = {"ticker": "AAPL", "price_at_addition": 220.0}
    mock_post.return_value = mock_resp_post

    added = api_client.add_to_watchlist({"ticker": "AAPL", "price_at_addition": 220.0})
    assert added is not None
    assert added["ticker"] == "AAPL"

    # Test remove_from_watchlist
    mock_resp_del = MagicMock()
    mock_resp_del.status_code = 200
    mock_del.return_value = mock_resp_del

    deleted = api_client.remove_from_watchlist("AAPL")
    assert deleted is True




