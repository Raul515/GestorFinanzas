"""
Pruebas unitarias para el motor contable de Deep Dive, Piotroski F-Score y métricas FCF.
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from backend.domain.schemas.deepdive import FinancialStatementYear
from backend.services.equity_deepdive import (
    _get_row_value,
    _safe_float,
    calculate_fcf_metrics,
    calculate_piotroski_score,
    fetch_historical_financials,
    get_equity_deepdive_data,
)


@pytest.fixture
def mock_statements_excellent() -> list[FinancialStatementYear]:
    """Genera dos ejercicios contables de una empresa con salud contable excelente (Piotroski 9/9)."""
    t = FinancialStatementYear(
        year=2023,
        revenue=10000.0,
        gross_profit=6000.0,  # Margen bruto 60%
        operating_income=2500.0,
        net_income=2000.0,  # ROA: 2000 / 10000 = 20%
        diluted_eps=2.0,
        total_assets=10000.0,
        current_assets=5000.0,
        current_liabilities=2000.0,  # Current ratio: 2.5
        long_term_debt=1000.0,  # Apalancamiento: 10%
        total_debt=1000.0,
        cash_and_equivalents=3000.0,
        operating_cash_flow=2500.0,  # CFO > Net Income (devengo positivo)
        capital_expenditure=500.0,
        free_cash_flow=2000.0,
        shares_outstanding=1000.0,  # Mismo número de acciones
    )
    t_prev = FinancialStatementYear(
        year=2022,
        revenue=9000.0,
        gross_profit=5000.0,  # Margen bruto 55.5% (< 60%)
        operating_income=2000.0,
        net_income=1500.0,  # ROA: 1500 / 10000 = 15% (< 20%)
        diluted_eps=1.5,
        total_assets=10000.0,
        current_assets=4000.0,
        current_liabilities=2000.0,  # Current ratio: 2.0 (< 2.5)
        long_term_debt=1500.0,  # Apalancamiento: 15% (> 10%)
        total_debt=1500.0,
        cash_and_equivalents=2000.0,
        operating_cash_flow=1800.0,
        capital_expenditure=600.0,
        free_cash_flow=1200.0,
        shares_outstanding=1000.0,
    )
    return [t, t_prev]


@pytest.fixture
def mock_statements_distressed() -> list[FinancialStatementYear]:
    """Genera dos ejercicios contables de una empresa con deterioro severo (Piotroski 0-1/9)."""
    t = FinancialStatementYear(
        year=2023,
        revenue=8000.0,
        gross_profit=3000.0,  # Margen bruto 37.5% (< 45%)
        operating_income=-500.0,
        net_income=-1000.0,  # ROA negativo
        diluted_eps=-1.0,
        total_assets=12000.0,
        current_assets=2000.0,
        current_liabilities=3000.0,  # Current ratio: 0.67 (< 1.2)
        long_term_debt=6000.0,  # Apalancamiento: 50% (> 30%)
        total_debt=6000.0,
        cash_and_equivalents=500.0,
        operating_cash_flow=-1200.0,  # CFO negativo
        capital_expenditure=400.0,
        free_cash_flow=-1600.0,
        shares_outstanding=1500.0,  # Dilución (+50%)
    )
    t_prev = FinancialStatementYear(
        year=2022,
        revenue=10000.0,
        gross_profit=4500.0,
        operating_income=500.0,
        net_income=200.0,
        diluted_eps=0.2,
        total_assets=10000.0,
        current_assets=3600.0,
        current_liabilities=3000.0,
        long_term_debt=3000.0,
        total_debt=3000.0,
        cash_and_equivalents=1000.0,
        operating_cash_flow=400.0,
        capital_expenditure=300.0,
        free_cash_flow=100.0,
        shares_outstanding=1000.0,
    )
    return [t, t_prev]


@pytest.fixture
def mock_bank_statements() -> list[FinancialStatementYear]:
    """Genera ejercicios contables para un banco sin margen bruto ni ratio corriente."""
    t = FinancialStatementYear(
        year=2023,
        revenue=20000.0,
        gross_profit=None,
        operating_income=None,
        net_income=4000.0,  # ROA positivo
        diluted_eps=0.5,
        total_assets=200000.0,
        current_assets=None,
        current_liabilities=None,
        long_term_debt=20000.0,
        total_debt=30000.0,
        cash_and_equivalents=25000.0,
        operating_cash_flow=5000.0,  # CFO > Net Income
        capital_expenditure=800.0,
        free_cash_flow=4200.0,
        shares_outstanding=8000.0,
    )
    t_prev = FinancialStatementYear(
        year=2022,
        revenue=18000.0,
        gross_profit=None,
        operating_income=None,
        net_income=3000.0,
        diluted_eps=0.38,
        total_assets=190000.0,
        current_assets=None,
        current_liabilities=None,
        long_term_debt=22000.0,
        total_debt=32000.0,
        cash_and_equivalents=20000.0,
        operating_cash_flow=3500.0,
        capital_expenditure=700.0,
        free_cash_flow=2800.0,
        shares_outstanding=8000.0,
    )
    return [t, t_prev]


def test_safe_float_and_get_row_value():
    """Verifica las funciones utilitarias de conversión numérica y lectura de filas en DataFrames."""
    assert _safe_float(45.567) == 45.57
    assert _safe_float("123.4") == 123.4
    assert _safe_float(None) is None
    assert _safe_float(float("nan")) is None
    assert _safe_float("invalido") is None

    df = pd.DataFrame(
        {"2023": [100.0, 200.0]},
        index=["Total Revenue", "Operating Income"],
    )
    val = _get_row_value(df, ["Operating Revenue", "Total Revenue"], "2023")
    assert val == 100.0

    missing_val = _get_row_value(df, ["Nonexistent"], "2023")
    assert missing_val is None


def test_calculate_piotroski_score_perfect(mock_statements_excellent: list[FinancialStatementYear]):
    """Verifica la puntuación máxima de 9 puntos en Piotroski con semáforo Excelente."""
    score = calculate_piotroski_score(mock_statements_excellent, is_bank=False)

    assert score.total_score == 9
    assert score.max_score == 9
    assert score.rating == "Excelente"
    assert len(score.criteria) == 9

    codes = [c.code for c in score.criteria]
    assert "ROA" in codes
    assert "CFO" in codes
    assert "DELTA_ROA" in codes
    assert "ACCRUAL" in codes
    assert "DELTA_LEVER" in codes
    assert "DELTA_LIQUID" in codes
    assert "EQ_OFFER" in codes
    assert "DELTA_MARGIN" in codes
    assert "DELTA_TURN" in codes

    for c in score.criteria:
        assert c.points == 1


def test_calculate_piotroski_score_distressed(mock_statements_distressed: list[FinancialStatementYear]):
    """Verifica la puntuación baja en empresa deteriorada con semáforo Riesgo Contable."""
    score = calculate_piotroski_score(mock_statements_distressed, is_bank=False)

    assert score.total_score <= 1
    assert score.max_score == 9
    assert score.rating == "Riesgo Contable"


def test_calculate_piotroski_score_financial_institution(mock_bank_statements: list[FinancialStatementYear]):
    """Verifica la adaptación de Piotroski para bancos (max_score=7, sin margen bruto ni ratio corriente)."""
    score = calculate_piotroski_score(mock_bank_statements, is_bank=True)

    assert score.max_score == 7
    codes = [c.code for c in score.criteria]
    assert "DELTA_LIQUID" not in codes
    assert "DELTA_MARGIN" not in codes
    assert score.total_score >= 5
    assert score.rating == "Excelente"


def test_calculate_piotroski_score_single_year(mock_statements_excellent: list[FinancialStatementYear]):
    """Verifica la resiliencia cuando solo se dispone de un único ejercicio contable (sin deltas anuales)."""
    single_year = [mock_statements_excellent[0]]
    score = calculate_piotroski_score(single_year, is_bank=False)

    assert score.total_score >= 2  # Al menos ROA y CFO positivos
    assert score.max_score == 9


def test_calculate_piotroski_score_empty():
    """Verifica el manejo de lista vacía de estados contables sin caídas en ejecución."""
    score = calculate_piotroski_score([], is_bank=False)
    assert score.total_score == 0
    assert score.rating == "Riesgo Contable"
    assert len(score.criteria) == 0


def test_calculate_fcf_metrics_complete(mock_statements_excellent: list[FinancialStatementYear]):
    """Verifica el cálculo de múltiplos de caja, tasa de conversión y detección de foso defensivo."""
    market_cap = 50000.0
    info = {"returnOnEquity": 0.22}  # 22% ROE

    metrics = calculate_fcf_metrics(mock_statements_excellent, market_cap=market_cap, info=info)

    # FCF Yield = (2000 / 50000) * 100 = 4.0%
    assert metrics["fcf_yield"] == 4.0
    # Conversión FCF = 2000 / 2000 = 1.0
    assert metrics["fcf_conversion_ratio"] == 1.0
    # Reinversión CapEx = (500 / 2500) * 100 = 20.0%
    assert metrics["reinvestment_rate"] == 20.0
    # Moat presente por ROE >= 15%
    assert metrics["has_moat"] is True
    assert metrics["roe"] == 22.0
    assert len(metrics["fcf_history"]) == 2


def test_calculate_fcf_metrics_empty():
    """Verifica que sin estados contables se devuelva una estructura segura por defecto."""
    metrics = calculate_fcf_metrics([])
    assert metrics["fcf_yield"] is None
    assert metrics["has_moat"] is False
    assert metrics["fcf_history"] == []


@patch("backend.services.equity_deepdive.yf.Ticker")
def test_fetch_historical_financials_mocked(mock_ticker_class):
    """Verifica la extracción contable y modelado histórico mediante mocks de yfinance."""
    col_2023 = pd.Timestamp("2023-12-31")
    col_2022 = pd.Timestamp("2022-12-31")

    mock_inst = MagicMock()
    mock_inst.info = {
        "sector": "Consumer Cyclical",
        "currentPrice": 45.5,
        "marketCap": 140000000000.0,
    }
    mock_inst.financials = pd.DataFrame(
        {
            col_2023: [35000.0, 20000.0, 6000.0, 5000.0, 1.6],
            col_2022: [32000.0, 18000.0, 5000.0, 4000.0, 1.3],
        },
        index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income", "Diluted EPS"],
    )
    mock_inst.balance_sheet = pd.DataFrame(
        {
            col_2023: [30000.0, 15000.0, 10000.0, 1000.0, 1000.0, 5000.0, 3100.0],
            col_2022: [28000.0, 14000.0, 9000.0, 1200.0, 1200.0, 4500.0, 3100.0],
        },
        index=[
            "Total Assets",
            "Current Assets",
            "Current Liabilities",
            "Long Term Debt",
            "Total Debt",
            "Cash And Cash Equivalents",
            "Ordinary Shares Number",
        ],
    )
    mock_inst.cashflow = pd.DataFrame(
        {
            col_2023: [7000.0, -1500.0, 5500.0],
            col_2022: [6000.0, -1400.0, 4600.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
    )
    mock_ticker_class.return_value = mock_inst

    info, statements, is_bank = fetch_historical_financials("ITX.MC")

    assert is_bank is False
    assert len(statements) == 2
    assert statements[0].year == 2023
    assert statements[0].revenue == 35000.0
    assert statements[0].free_cash_flow == 5500.0
    assert statements[0].capital_expenditure == 1500.0


@patch("backend.services.equity_deepdive.fetch_historical_financials")
def test_get_equity_deepdive_data_orchestration(mock_fetch):
    """Verifica la orquestación completa de Deep Dive retornando DeepDiveResponse."""
    mock_info = {
        "shortName": "Inditex",
        "sector": "Consumer Cyclical",
        "currentPrice": 45.5,
        "marketCap": 140000000000.0,
        "returnOnEquity": 0.25,
        "trailingPE": 22.5,
    }
    stmt = FinancialStatementYear(
        year=2023,
        revenue=35000.0,
        net_income=5000.0,
        total_assets=30000.0,
        operating_cash_flow=7000.0,
        capital_expenditure=1500.0,
        free_cash_flow=5500.0,
    )
    mock_fetch.return_value = (mock_info, [stmt], False)

    response = get_equity_deepdive_data("ITX.MC")

    assert response is not None
    assert response.ticker == "ITX.MC"
    assert response.current_price == 45.5
    assert response.market_cap == 140000000000.0
    assert response.piotroski.total_score >= 2
    assert response.fcf_metrics["has_moat"] is True
    assert response.quality_value_report is None
    assert response.from_cache is False
