"""
Pruebas de integración para los endpoints REST del Screener Fundamental (Spec 002 - Fase 3).
Verifica listado de universos, ciclo de vida de caché (24h), filtros, tickers personalizados y refresco forzado.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.domain.schemas.screener import (
    ETFScreenerItem,
    StockScreenerItem,
)


def _dummy_stock_items():
    return [
        StockScreenerItem(
            ticker="ITX.MC",
            name="Inditex",
            sector="Consumer Cyclical",
            price=46.0,
            change_pct=1.5,
            pe_trailing=22.0,
            pe_forward=19.0,
            pb_ratio=6.0,
            dividend_yield=3.2,
            roe=28.0,
            operating_margin=18.0,
            net_margin=14.0,
            debt_to_equity=30.0,
            beta=0.85,
        ),
        StockScreenerItem(
            ticker="SAN.MC",
            name="Banco Santander",
            sector="Financial Services",
            price=4.6,
            change_pct=-0.5,
            pe_trailing=6.5,
            dividend_yield=5.2,
            roe=13.0,
            net_margin=18.0,
        ),
    ]


def _dummy_etf_items():
    return [
        ETFScreenerItem(
            ticker="VWCE.DE",
            name="Vanguard FTSE All-World",
            category="Global Equity",
            price=125.0,
            change_pct=0.4,
            expense_ratio=0.22,
            dividend_yield=1.5,
            total_assets=15000000000.0,
        ),
        ETFScreenerItem(
            ticker="CSPX.AS",
            name="iShares Core S&P 500",
            category="US Large-Cap Blend",
            price=540.0,
            change_pct=0.8,
            expense_ratio=0.07,
            dividend_yield=1.2,
            total_assets=75000000000.0,
        ),
    ]


def test_get_universes_list(client: TestClient):
    """Verifica que el endpoint /screener/universes devuelva los 5 universos configurados."""
    response = client.get("/screener/universes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5

    universe_ids = [u["id"] for u in data]
    assert "ibex35" in universe_ids
    assert "eurostoxx50" in universe_ids
    assert "sp500_top50" in universe_ids
    assert "etfs_referencia" in universe_ids
    assert "custom" in universe_ids


def test_get_universe_screener_caching_flow(client: TestClient):
    """
    Verifica que la primera llamada extraiga datos y la segunda consuma la caché SQLite de 24h.
    """
    dummy_items = _dummy_stock_items()

    with patch("backend.api.routers.screener.fetch_universe_data", return_value=dummy_items) as mock_fetch:
        # 1. Primera llamada: sin caché previa
        res1 = client.get("/screener/universe/ibex35")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["universe"] == "ibex35"
        assert data1["from_cache"] is False
        assert data1["total_count"] == 2
        assert len(data1["items"]) == 2
        assert mock_fetch.call_count == 1

        # 2. Segunda llamada: debe servirse desde la caché de SQLite
        res2 = client.get("/screener/universe/ibex35")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["universe"] == "ibex35"
        assert data2["from_cache"] is True
        assert data2["total_count"] == 2
        # fetch_universe_data NO debe haber sido llamado nuevamente
        assert mock_fetch.call_count == 1


def test_get_universe_screener_with_filters(client: TestClient):
    """Verifica la aplicación de filtros por query params (ej. preset calidad)."""
    dummy_items = _dummy_stock_items()

    with patch("backend.api.routers.screener.fetch_universe_data", return_value=dummy_items):
        # Filtro de preset QUALITY: ROE >= 15%, Net Margin >= 10%, Debt/Equity <= 120%
        # Inditex (ROE=28%, Net=14%, Debt=30%) cumple.
        # Santander (ROE=13%) no cumple.
        res = client.get("/screener/universe/ibex35?preset=quality")
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] == 2
        assert data["filtered_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["ticker"] == "ITX.MC"


def test_get_universe_screener_404_on_invalid_universe(client: TestClient):
    """Verifica error 404 al solicitar un universo inexistente."""
    res = client.get("/screener/universe/universo_ficticio")
    assert res.status_code == 404
    assert "no encontrado" in res.json()["detail"].lower()


def test_post_custom_screener(client: TestClient):
    """Verifica el endpoint POST /screener/custom para cribado de tickers arbitrarios."""
    dummy_custom = [
        StockScreenerItem(ticker="AAPL", name="Apple Inc.", price=220.0, change_pct=1.2),
        ETFScreenerItem(ticker="VWCE.DE", name="Vanguard All-World", price=125.0, change_pct=0.5, expense_ratio=0.22),
    ]

    with patch("backend.api.routers.screener.fetch_custom_tickers", return_value=dummy_custom):
        payload = {
            "tickers": ["AAPL", "VWCE.DE"],
            "filter_params": {
                "search_query": "apple"
            }
        }
        res = client.post("/screener/custom", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["universe"] == "custom"
        assert data["total_count"] == 2
        assert data["filtered_count"] == 1
        assert data["items"][0]["ticker"] == "AAPL"


def test_refresh_universe_screener(client: TestClient):
    """Verifica que POST /screener/refresh/{universe_id} invalide la caché y devuelva datos frescos."""
    dummy_items = _dummy_stock_items()

    with patch("backend.api.routers.screener.fetch_universe_data", return_value=dummy_items) as mock_fetch:
        res = client.post("/screener/refresh/ibex35")
        assert res.status_code == 200
        data = res.json()
        assert data["from_cache"] is False
        assert data["notes"] is not None
        assert mock_fetch.call_count == 1
