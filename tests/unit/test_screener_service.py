"""
Pruebas unitarias para el Servicio de Screener Fundamental (Spec 002 - Fase 2).
Prueba extracción de acciones y ETFs, normalización de porcentajes, resiliencia ante datos nulos y motor de presets.
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.domain.schemas.screener import (
    ETFScreenerItem,
    ScreenerFilterParams,
    ScreenerPresetEnum,
    StockScreenerItem,
)
from backend.services.screener_service import (
    _clean_percentage,
    apply_screener_filters,
    fetch_custom_tickers,
    fetch_etf_item,
    fetch_stock_item,
    fetch_universe_data,
    IBEX_35_TICKERS,
    UNIVERSES_METADATA,
)


def test_clean_percentage_utility():
    """Verifica la normalización matemática de ratios decimales y porcentajes."""
    assert _clean_percentage(0.045) == 4.5
    assert _clean_percentage(0.185) == 18.5
    assert _clean_percentage(12.5) == 12.5
    assert _clean_percentage(None) is None
    assert _clean_percentage("invalid") is None


def test_fetch_stock_item_complete_mock():
    """Verifica la extracción y mapeo completo de una acción con datos enriquecidos."""
    mock_info = {
        "shortName": "Inditex",
        "sector": "Consumer Cyclical",
        "country": "Spain",
        "currency": "EUR",
        "currentPrice": 46.20,
        "previousClose": 45.50,
        "regularMarketChangePercent": 0.0154,  # Ratio 1.54%
        "marketCap": 144000000000,
        "trailingPE": 22.5,
        "forwardPE": 19.8,
        "priceToBook": 6.4,
        "enterpriseToEbitda": 11.2,
        "dividendYield": 0.032,  # 3.2%
        "returnOnEquity": 0.285,  # 28.5%
        "operatingMargins": 0.182,  # 18.2%
        "profitMargins": 0.141,  # 14.1%
        "debtToEquity": 32.5,  # 32.5%
        "currentRatio": 1.45,
        "beta": 0.88,
    }

    item = fetch_stock_item("ITX.MC", info_dict=mock_info)
    assert item is not None
    assert item.ticker == "ITX.MC"
    assert item.name == "Inditex"
    assert item.price == 46.20
    assert item.dividend_yield == 3.2
    assert item.roe == 28.5
    assert item.operating_margin == 18.2
    assert item.net_margin == 14.1
    assert item.debt_to_equity == 32.5
    assert item.asset_type == "stock"


def test_fetch_stock_item_resilient_missing_bank_ratios():
    """Verifica que un banco sin EBITDA tradicional o ratio de endeudamiento no quiebre la extracción."""
    mock_info = {
        "shortName": "Banco Santander",
        "sector": "Financial Services",
        "currency": "EUR",
        "currentPrice": 4.55,
        "previousClose": 4.50,
        "regularMarketChangePercent": 1.11,
        "trailingPE": 6.8,
        "priceToBook": 0.72,
        "returnOnEquity": 0.13,
        "dividendYield": 0.048,
        # EBITDA y debtToEquity ausentes en bancos
    }

    item = fetch_stock_item("SAN.MC", info_dict=mock_info)
    assert item is not None
    assert item.ticker == "SAN.MC"
    assert item.price == 4.55
    assert item.pe_trailing == 6.8
    assert item.ev_to_ebitda is None
    assert item.debt_to_equity is None
    assert item.dividend_yield == 4.8


def test_fetch_stock_item_zero_price_or_error_returns_none():
    """Verifica que un ticker sin precio o con error de API devuelva None con logging sin caerse."""
    assert fetch_stock_item("INVALID", info_dict={}) is None
    assert fetch_stock_item("ZERO", info_dict={"currentPrice": 0.0}) is None


def test_fetch_etf_item_complete_mock():
    """Verifica la extracción y normalización de métricas de un ETF UCITS."""
    mock_info = {
        "shortName": "Vanguard FTSE All-World",
        "category": "Global Equity",
        "currency": "EUR",
        "navPrice": 124.50,
        "previousClose": 124.00,
        "annualReportExpenseRatio": 0.0022,  # 0.22%
        "yield": 0.016,  # 1.6%
        "totalAssets": 15000000000,
        "averageVolume": 180000,
        "beta": 1.02,
    }

    item = fetch_etf_item("VWCE.DE", info_dict=mock_info)
    assert item is not None
    assert item.ticker == "VWCE.DE"
    assert item.asset_type == "etf"
    assert item.price == 124.50
    assert item.expense_ratio == 0.22
    assert item.dividend_yield == 1.6
    assert item.total_assets == 15000000000.0


def test_fetch_universe_data_mocked():
    """Verifica la invocación por lotes para un universo predefinido."""
    dummy_stock = StockScreenerItem(ticker="ITX.MC", name="Inditex", price=45.0, change_pct=1.0)

    with patch("backend.services.screener_service.fetch_stock_item", return_value=dummy_stock):
        items = fetch_universe_data("ibex35")
        assert len(items) == len(IBEX_35_TICKERS)
        assert items[0].ticker == "ITX.MC"

    # Universo inexistente
    assert fetch_universe_data("universo_desconocido") == []


def test_fetch_custom_tickers_auto_detection():
    """Verifica que una lista de tickers distinga entre ETFs y acciones según quoteType."""
    mock_stock_info = {"quoteType": "EQUITY", "currentPrice": 100.0, "shortName": "Apple"}
    mock_etf_info = {"quoteType": "ETF", "navPrice": 50.0, "shortName": "iShares Core"}

    def fake_ticker(symbol):
        mock_obj = MagicMock()
        if symbol == "AAPL":
            mock_obj.info = mock_stock_info
        else:
            mock_obj.info = mock_etf_info
        return mock_obj

    with patch("yfinance.Ticker", side_effect=fake_ticker):
        items = fetch_custom_tickers(["AAPL", "CSPX.AS"])
        assert len(items) == 2
        assert items[0].asset_type == "stock"
        assert items[0].ticker == "AAPL"
        assert items[1].asset_type == "etf"
        assert items[1].ticker == "CSPX.AS"


def test_apply_screener_filters_preset_quality():
    """Verifica el filtrado por preset 'Calidad y Solvencia' (ROE >= 15, Margen >= 10, Deuda <= 120)."""
    stock_quality = StockScreenerItem(
        ticker="AAA", name="Empresa Calidad", price=10.0, change_pct=0.0,
        roe=18.0, net_margin=15.0, debt_to_equity=50.0,
    )
    stock_bad_roe = StockScreenerItem(
        ticker="BBB", name="Empresa Bajo ROE", price=10.0, change_pct=0.0,
        roe=8.0, net_margin=15.0, debt_to_equity=50.0,
    )
    stock_high_debt = StockScreenerItem(
        ticker="CCC", name="Empresa Endeudada", price=10.0, change_pct=0.0,
        roe=20.0, net_margin=12.0, debt_to_equity=160.0,
    )

    items = [stock_quality, stock_bad_roe, stock_high_debt]
    params = ScreenerFilterParams(preset=ScreenerPresetEnum.QUALITY)

    res = apply_screener_filters(items, params)
    assert len(res) == 1
    assert res[0].ticker == "AAA"


def test_apply_screener_filters_preset_high_dividend():
    """Verifica el filtrado por preset 'Alto Dividendo' (Yield >= 3.5%, PER Forward <= 18, Deuda <= 150)."""
    stock_div = StockScreenerItem(
        ticker="DIV1", name="Empresa Dividendo", price=20.0, change_pct=0.0,
        dividend_yield=4.5, pe_forward=14.0, debt_to_equity=90.0,
    )
    stock_low_div = StockScreenerItem(
        ticker="DIV2", name="Empresa Crecimiento", price=20.0, change_pct=0.0,
        dividend_yield=1.2, pe_forward=14.0, debt_to_equity=90.0,
    )
    etf_div = ETFScreenerItem(
        ticker="ETFDIV", name="Vanguard High Dividend", price=50.0, change_pct=0.0,
        dividend_yield=3.8, expense_ratio=0.29,
    )

    items = [stock_div, stock_low_div, etf_div]
    params = ScreenerFilterParams(preset=ScreenerPresetEnum.HIGH_DIVIDEND)

    res = apply_screener_filters(items, params)
    assert len(res) == 2
    tickers = [i.ticker for i in res]
    assert "DIV1" in tickers
    assert "ETFDIV" in tickers
    assert "DIV2" not in tickers


def test_apply_screener_filters_preset_value():
    """Verifica el filtrado por preset 'Value' (PER <= 15, P/B <= 2.0, Div Yield >= 2.0%)."""
    stock_value = StockScreenerItem(
        ticker="VAL1", name="Empresa Barata", price=30.0, change_pct=0.0,
        pe_trailing=11.0, pb_ratio=1.4, dividend_yield=3.0,
    )
    stock_expensive = StockScreenerItem(
        ticker="VAL2", name="Empresa Cara", price=30.0, change_pct=0.0,
        pe_trailing=28.0, pb_ratio=4.5, dividend_yield=1.0,
    )

    items = [stock_value, stock_expensive]
    params = ScreenerFilterParams(preset=ScreenerPresetEnum.VALUE)

    res = apply_screener_filters(items, params)
    assert len(res) == 1
    assert res[0].ticker == "VAL1"


def test_apply_screener_filters_preset_growth():
    """Verifica el filtrado por preset 'Crecimiento' (Op Margin >= 15%, ROE >= 12%, Beta >= 0.9)."""
    stock_growth = StockScreenerItem(
        ticker="GRO1", name="Empresa Crecimiento", price=150.0, change_pct=1.0,
        operating_margin=22.0, roe=19.0, beta=1.15,
    )
    stock_defensive = StockScreenerItem(
        ticker="GRO2", name="Empresa Lenta", price=150.0, change_pct=1.0,
        operating_margin=8.0, roe=7.0, beta=0.5,
    )

    items = [stock_growth, stock_defensive]
    params = ScreenerFilterParams(preset=ScreenerPresetEnum.GROWTH)

    res = apply_screener_filters(items, params)
    assert len(res) == 1
    assert res[0].ticker == "GRO1"


def test_apply_screener_filters_preset_low_cost_etf():
    """Verifica el filtrado por preset 'ETFs de Bajo Coste' (TER <= 0.25%, AUM >= 500M)."""
    etf_cheap = ETFScreenerItem(
        ticker="E1", name="ETF Barato", price=100.0, change_pct=0.0,
        expense_ratio=0.12, total_assets=2000000000.0,
    )
    etf_expensive = ETFScreenerItem(
        ticker="E2", name="ETF Caro", price=100.0, change_pct=0.0,
        expense_ratio=0.65, total_assets=100000000.0,
    )

    items = [etf_cheap, etf_expensive]
    params = ScreenerFilterParams(preset=ScreenerPresetEnum.LOW_COST_ETF)

    res = apply_screener_filters(items, params)
    assert len(res) == 1
    assert res[0].ticker == "E1"


def test_apply_screener_filters_search_query_and_numeric_ranges():
    """Verifica la combinación de búsqueda textual por nombre/ticker y rangos numéricos."""
    stock1 = StockScreenerItem(
        ticker="SAN.MC", name="Banco Santander", sector="Financial Services",
        price=4.5, change_pct=0.5, pe_trailing=7.0, dividend_yield=4.5, roe=13.0,
    )
    stock2 = StockScreenerItem(
        ticker="BBVA.MC", name="BBVA", sector="Financial Services",
        price=9.2, change_pct=0.8, pe_trailing=8.0, dividend_yield=5.5, roe=16.0,
    )
    stock3 = StockScreenerItem(
        ticker="ITX.MC", name="Inditex", sector="Consumer Cyclical",
        price=45.0, change_pct=-0.2, pe_trailing=22.0, dividend_yield=3.2, roe=28.0,
    )

    items = [stock1, stock2, stock3]

    # Búsqueda por query "banco"
    res_query = apply_screener_filters(items, ScreenerFilterParams(search_query="banco"))
    assert len(res_query) == 1
    assert res_query[0].ticker == "SAN.MC"

    # Rango numérico: max_pe=10.0, min_roe=14.0
    res_ranges = apply_screener_filters(
        items,
        ScreenerFilterParams(max_pe=10.0, min_roe=14.0),
    )
    assert len(res_ranges) == 1
    assert res_ranges[0].ticker == "BBVA.MC"
