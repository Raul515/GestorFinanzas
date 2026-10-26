from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from backend.domain.schemas.screener import (
    ETFScreenerItem,
    ScreenerFilterParams,
    ScreenerPresetEnum,
    ScreenerResponse,
    StockScreenerItem,
    UniverseInfo,
)


def test_stock_screener_item_creation_and_defaults():
    """Verifica la instanciación completa de un activo de renta variable con valores opcionales."""
    item = StockScreenerItem(
        ticker="ITX.MC",
        name="Inditex",
        sector="Consumer Cyclical",
        country="Spain",
        currency="EUR",
        price=45.50,
        change_pct=1.25,
        market_cap=140000000000.0,
        pe_trailing=22.4,
        pe_forward=19.8,
        pb_ratio=6.2,
        ev_to_ebitda=11.5,
        dividend_yield=3.2,
        roe=28.4,
        operating_margin=18.5,
        net_margin=14.2,
        debt_to_equity=35.0,
        current_ratio=1.45,
        beta=0.85,
    )

    assert item.ticker == "ITX.MC"
    assert item.asset_type == "stock"
    assert item.price == 45.50
    assert item.roe == 28.4
    assert item.pe_trailing == 22.4


def test_stock_screener_item_minimal_missing_ratios():
    """Verifica que empresas sin EBITDA (bancos) o sin dividendos acepten None de forma resiliente."""
    item = StockScreenerItem(
        ticker="SAN.MC",
        name="Banco Santander",
        price=4.60,
        change_pct=-0.5,
    )

    assert item.ticker == "SAN.MC"
    assert item.currency == "EUR"
    assert item.asset_type == "stock"
    assert item.pe_trailing is None
    assert item.ev_to_ebitda is None
    assert item.debt_to_equity is None
    assert item.dividend_yield is None


def test_etf_screener_item_creation():
    """Verifica la instanciación de un ETF indexado con métricas de costes y patrimonio."""
    etf = ETFScreenerItem(
        ticker="VWCE.DE",
        name="Vanguard FTSE All-World UCITS ETF",
        category="Global Large-Cap Blend Equity",
        currency="EUR",
        price=125.80,
        change_pct=0.45,
        expense_ratio=0.22,
        dividend_yield=1.45,
        total_assets=15000000000.0,
        avg_volume=250000.0,
        beta=1.0,
    )

    assert etf.ticker == "VWCE.DE"
    assert etf.asset_type == "etf"
    assert etf.expense_ratio == 0.22
    assert etf.total_assets == 15000000000.0


def test_universe_info_creation():
    """Verifica el esquema de metadatos de universos disponibles."""
    info = UniverseInfo(
        id="ibex35",
        name="IBEX 35",
        description="Las 35 empresas más líquidas cotizadas en las bolsas españolas",
        asset_type="stock",
        ticker_count=35,
    )

    assert info.id == "ibex35"
    assert info.asset_type == "stock"
    assert info.ticker_count == 35


def test_screener_filter_params_defaults_and_custom():
    """Verifica los parámetros de filtrado y el valor por defecto del preset."""
    defaults = ScreenerFilterParams()
    assert defaults.preset == ScreenerPresetEnum.ALL
    assert defaults.max_pe is None
    assert defaults.search_query is None

    custom = ScreenerFilterParams(
        preset=ScreenerPresetEnum.QUALITY,
        max_pe=20.0,
        min_roe=15.0,
        min_dividend_yield=2.5,
        search_query="Inditex",
    )
    assert custom.preset == ScreenerPresetEnum.QUALITY
    assert custom.max_pe == 20.0
    assert custom.min_roe == 15.0
    assert custom.search_query == "Inditex"


def test_screener_response_polymorphic_items():
    """Verifica que la respuesta agregada maneje tanto acciones como ETFs en la misma colección."""
    stock = StockScreenerItem(
        ticker="ITX.MC",
        name="Inditex",
        price=45.50,
        change_pct=1.0,
    )
    etf = ETFScreenerItem(
        ticker="VWCE.DE",
        name="Vanguard All-World",
        price=125.0,
        change_pct=0.5,
        expense_ratio=0.22,
    )

    now = datetime.now(timezone.utc)
    response = ScreenerResponse(
        universe="custom",
        asset_type="mixed",
        updated_at=now,
        from_cache=False,
        total_count=2,
        filtered_count=2,
        items=[stock, etf],
    )

    assert response.total_count == 2
    assert len(response.items) == 2
    assert response.items[0].asset_type == "stock"
    assert response.items[1].asset_type == "etf"
    assert response.items[1].ticker == "VWCE.DE"


def test_invalid_data_validation_error():
    """Verifica que campos obligatorios faltantes lancen ValidationError."""
    with pytest.raises(ValidationError):
        # Falta price y change_pct
        StockScreenerItem(ticker="ITX.MC", name="Inditex")  # type: ignore
