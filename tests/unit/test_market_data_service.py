"""
Pruebas unitarias para el Servicio de Datos Macroeconómicos (Spec 001 - Fase 2).
Prueba cálculos financieros, fórmula de prima de riesgo, parseo de datos del BCE, mocks de yfinance y degradación elegante.
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from backend.domain.schemas.market import MacroIndicator, MacroOverviewResponse
from backend.services.market_data import (
    _extract_ticker_data,
    _fetch_ecb_series,
    fetch_sovereign_bonds_and_risk_premium,
    get_macro_overview,
    get_macro_overview_response,
)


def test_extract_ticker_data_success():
    """Verifica la extracción exitosa de cotizaciones de yfinance y el cálculo de variaciones."""
    mock_history = pd.DataFrame(
        {
            "Close": [11700.0, 11750.0, 11800.0, 11918.0],
        }
    )

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_history
        mock_ticker_cls.return_value = mock_ticker

        indicator = _extract_ticker_data(
            symbol="^IBEX",
            indicator_id="ibex35",
            name="IBEX 35",
            region="España",
            unit="pts",
        )

        assert indicator.id == "ibex35"
        assert indicator.name == "IBEX 35"
        assert indicator.symbol == "^IBEX"
        assert indicator.region == "España"
        assert indicator.unit == "pts"
        assert indicator.current_value == 11918.0
        # Anterior = 11800.0, Actual = 11918.0 -> diff = 118.0, change_pct = (118.0 / 11800.0) * 100 = 1.0%
        assert indicator.change_abs == 118.0
        assert indicator.change_pct == 1.0
        assert indicator.sparkline_30d == [11700.0, 11750.0, 11800.0, 11918.0]
        assert indicator.last_updated is not None


def test_extract_ticker_data_with_nans():
    """Verifica que los valores nulos (NaN) en la serie de precios sean descartados correctamente."""
    mock_history = pd.DataFrame(
        {
            "Close": [100.0, None, 105.0, 102.9],
        }
    )

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_history
        mock_ticker_cls.return_value = mock_ticker

        indicator = _extract_ticker_data(
            symbol="^TEST",
            indicator_id="test",
            name="Test Asset",
            region="Eurozona",
            unit="pts",
        )

        assert indicator.current_value == 102.9
        # Anterior = 105.0, Actual = 102.9 -> diff = -2.1, pct = (-2.1 / 105.0) * 100 = -2.0%
        assert indicator.change_abs == -2.1
        assert indicator.change_pct == -2.0
        assert indicator.sparkline_30d == [100.0, 105.0, 102.9]


def test_extract_ticker_data_fallback_on_empty_or_failure():
    """Verifica que un fallo en la API externa active la contingencia con valores base sensatos."""
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("Yahoo Finance rate limit")
        mock_ticker_cls.return_value = mock_ticker

        indicator = _extract_ticker_data(
            symbol="^IBEX",
            indicator_id="ibex35",
            name="IBEX 35",
            region="España",
            unit="pts",
        )

        assert indicator.id == "ibex35"
        assert indicator.symbol == "^IBEX"
        assert indicator.current_value == 11850.0  # Contingencia base
        assert indicator.change_pct == 0.35
        assert len(indicator.sparkline_30d) > 0


def test_fetch_ecb_series_success():
    """Verifica el parseo de observaciones en formato JSON SDMX del Banco Central Europeo."""
    mock_ecb_json = {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0": {
                        "observations": {
                            "0": [2.35, 0, None],
                            "1": [2.30, 0, None],
                            "2": [2.25, 0, None],
                        }
                    }
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_ecb_json

    with patch("requests.get", return_value=mock_resp):
        cur, diff, vals = _fetch_ecb_series("https://fake-ecb.url", default_val=2.0)

        assert cur == 2.25
        assert diff == -0.05  # 2.25 - 2.30
        assert vals == [2.35, 2.30, 2.25]


def test_fetch_ecb_series_fallback_on_network_error():
    """Verifica la respuesta de contingencia ante caída o error en la petición HTTP al BCE."""
    with patch("requests.get", side_effect=Exception("Connection timed out")):
        cur, diff, vals = _fetch_ecb_series("https://fake-ecb.url", default_val=2.25)

        assert cur == 2.25
        assert diff == 0.0
        assert len(vals) == 10
        assert vals[0] == 2.25


def test_fetch_sovereign_bonds_and_risk_premium_calculation():
    """
    Verifica que la Prima de Riesgo de España se calcule estrictamente como:
    Prima de Riesgo (pb) = (Bono_España_10A - Bund_Alemán_10A) * 100
    """
    def mock_ecb_side_effect(url, default_val):
        if "SV_C_YM.SR_10Y" in url:
            # Bund Alemán 10A
            return 2.20, -0.05, [2.30, 2.25, 2.20]
        else:
            # Bono Español 10A
            return 3.05, -0.02, [3.12, 3.07, 3.05]

    with patch("backend.services.market_data._fetch_ecb_series", side_effect=mock_ecb_side_effect):
        spain_ind, bund_ind, premium_ind = fetch_sovereign_bonds_and_risk_premium()

        # 1. Comprobación del Bund
        assert bund_ind.id == "bund_de_10y"
        assert bund_ind.symbol == "BUND10Y"
        assert bund_ind.region == "Eurozona"
        assert bund_ind.current_value == 2.20
        assert bund_ind.unit == "%"

        # 2. Comprobación del Bono Español 10A
        assert spain_ind.id == "bono_es_10y"
        assert spain_ind.symbol == "SPAIN10Y"
        assert spain_ind.region == "España"
        assert spain_ind.current_value == 3.05
        assert spain_ind.unit == "%"

        # 3. Comprobación de la Prima de Riesgo
        # Actual: (3.05 - 2.20) * 100 = 85.0 pb
        # Anterior: (3.07 - 2.25) * 100 = 82.0 pb
        # Diferencia: 85.0 - 82.0 = +3.0 pb
        assert premium_ind.id == "prima_riesgo_es"
        assert premium_ind.symbol == "SPREAD_ES_DE"
        assert premium_ind.region == "España"
        assert premium_ind.unit == "pb"
        assert premium_ind.current_value == 85.0
        assert premium_ind.change_abs == 3.0
        assert premium_ind.sparkline_30d == [82.0, 82.0, 85.0]


def test_get_macro_overview_returns_8_indicators():
    """Verifica que se devuelvan exactamente 8 indicadores priorizando España y Europa."""
    with patch("yfinance.Ticker") as mock_ticker_cls, \
         patch("requests.get") as mock_get:
        
        # Simular respuesta vacía para activar los datos base predeterminados
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        indicators = get_macro_overview()

        assert len(indicators) == 8

        ids = [ind.id for ind in indicators]
        expected_ids = [
            "ibex35",
            "stoxx50",
            "bono_es_10y",
            "bund_de_10y",
            "prima_riesgo_es",
            "sp500",
            "nasdaq100",
            "bono_us_10y",
        ]
        assert ids == expected_ids

        # Verificar priorización regional: España y Europa en primeras posiciones
        assert indicators[0].region == "España"
        assert indicators[1].region == "Eurozona"
        assert indicators[2].region == "España"
        assert indicators[3].region == "Eurozona"
        assert indicators[4].region == "España"


def test_get_macro_overview_response():
    """Verifica que get_macro_overview_response retorne un MacroOverviewResponse validado."""
    with patch("backend.services.market_data.get_macro_overview") as mock_overview:
        mock_overview.return_value = [
            MacroIndicator(
                id="ibex35",
                name="IBEX 35",
                symbol="^IBEX",
                region="España",
                current_value=11900.0,
                change_pct=0.5,
                change_abs=59.0,
                unit="pts",
                sparkline_30d=[11800.0, 11900.0],
            )
        ]

        resp = get_macro_overview_response(is_cached=True)

        assert isinstance(resp, MacroOverviewResponse)
        assert resp.is_cached is True
        assert len(resp.indicators) == 1
        assert resp.indicators[0].id == "ibex35"
        assert resp.source_notes == "Datos extraídos de Yahoo Finance y BCE"

