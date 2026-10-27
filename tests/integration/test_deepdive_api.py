"""
Pruebas de integración para los endpoints REST de Deep Dive (Spec 003 - Fase 4).
Verifica ciclo de vida de caché (24h), refresco forzado y manejo de errores 404.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.domain.schemas.deepdive import (
    DeepDiveResponse,
    FinancialStatementYear,
    PiotroskiScore,
    QualityValueReport,
)


def _dummy_deepdive_response(ticker: str = "ITX.MC") -> DeepDiveResponse:
    """Genera una respuesta sintética de prueba para Deep Dive."""
    return DeepDiveResponse(
        ticker=ticker,
        name="Inditex S.A.",
        sector="Consumer Cyclical",
        industry="Apparel Retail",
        country="Spain",
        currency="EUR",
        description="Líder global en distribución de moda.",
        current_price=45.50,
        day_change_pct=1.2,
        market_cap=141000000000.0,
        pe_trailing=22.5,
        pe_forward=19.5,
        ev_to_ebitda=11.8,
        price_to_book=6.5,
        dividend_yield=3.4,
        beta=0.85,
        statements=[
            FinancialStatementYear(
                year=2023,
                revenue=35000000000.0,
                gross_profit=20000000000.0,
                operating_income=6500000000.0,
                net_income=5000000000.0,
                diluted_eps=1.65,
                total_assets=30000000000.0,
                current_assets=15000000000.0,
                current_liabilities=10000000000.0,
                long_term_debt=1000000000.0,
                total_debt=1500000000.0,
                cash_and_equivalents=11000000000.0,
                operating_cash_flow=7500000000.0,
                capital_expenditure=1500000000.0,
                free_cash_flow=6000000000.0,
                shares_outstanding=3116000000.0,
            )
        ],
        piotroski=PiotroskiScore(
            total_score=8,
            max_score=9,
            rating="Excelente",
        ),
        fcf_metrics={
            "fcf_yield": 4.25,
            "fcf_conversion_ratio": 1.20,
            "reinvestment_rate": 20.0,
            "roe": 28.0,
            "roic": 24.5,
            "has_moat": True,
        },
        quality_value_report=None,
        is_financial_institution=False,
        from_cache=False,
        updated_at=datetime.now(timezone.utc),
    )


def _dummy_quality_value_report() -> QualityValueReport:
    """Genera un informe sintético de tesis agéntica Quality Value."""
    return QualityValueReport(
        quadrant="Quality Value",
        summary_thesis="Negocio excepcional con alta generación de FCF.",
        six_ingredients={
            "long_term_growth": "Sostenido al 8%",
            "tailwinds": "Digital",
            "market_leadership": "Número 1",
            "moat": "Escala y logística",
            "high_returns_on_capital": "ROIC > 24%",
            "temporary_headwinds": "Costes puntuales",
        },
        business_model_and_risks={"model": "Retail"},
        bearish_risks=["Aranceles comerciales", "Contracción del consumo"],
        valuation_projections={"base": {"target": 54.0}},
        target_irr_entry_zone="38.00 € - 42.00 € (TIR exigida: 15% - 20%)",
    )


@patch("backend.api.routers.deepdive.analyze_quality_value")
@patch("backend.api.routers.deepdive.get_equity_deepdive_data")
def test_get_deepdive_analysis_caching_flow(mock_extract, mock_analyze, client: TestClient):
    """Verifica el ciclo de vida de la caché SQLite de 24 horas para diagnósticos Deep Dive."""
    dummy_data = _dummy_deepdive_response("ITX.MC")
    dummy_report = _dummy_quality_value_report()

    mock_extract.return_value = dummy_data
    mock_analyze.return_value = dummy_report

    # Primera petición: Debe consultar el servicio y guardar en caché (from_cache=False)
    res_1 = client.get("/deepdive/itx.mc")
    assert res_1.status_code == 200
    data_1 = res_1.json()
    assert data_1["ticker"] == "ITX.MC"
    assert data_1["from_cache"] is False
    assert data_1["quality_value_report"] is not None
    assert data_1["quality_value_report"]["quadrant"] == "Quality Value"
    assert mock_extract.call_count == 1
    assert mock_analyze.call_count == 1

    # Segunda petición inmediata: Debe servirse directamente desde la caché SQLite (from_cache=True)
    res_2 = client.get("/deepdive/itx.mc")
    assert res_2.status_code == 200
    data_2 = res_2.json()
    assert data_2["ticker"] == "ITX.MC"
    assert data_2["from_cache"] is True
    # Los mocks no deben haber sido llamados nuevamente
    assert mock_extract.call_count == 1
    assert mock_analyze.call_count == 1


@patch("backend.api.routers.deepdive.get_equity_deepdive_data")
def test_get_deepdive_analysis_not_found(mock_extract, client: TestClient):
    """Verifica que un ticker inexistente devuelva código HTTP 404 con mensaje explicativo."""
    mock_extract.return_value = None

    res = client.get("/deepdive/NO_EXISTE")
    assert res.status_code == 404
    assert "No se pudieron encontrar" in res.json()["detail"]


@patch("backend.api.routers.deepdive.analyze_quality_value")
@patch("backend.api.routers.deepdive.get_equity_deepdive_data")
def test_refresh_deepdive_analysis_forces_recalculation(mock_extract, mock_analyze, client: TestClient):
    """Verifica que POST /deepdive/refresh/{ticker} invalide la caché y regenere los datos."""
    dummy_data = _dummy_deepdive_response("MSFT")
    dummy_report = _dummy_quality_value_report()

    mock_extract.return_value = dummy_data
    mock_analyze.return_value = dummy_report

    # Cargar en caché inicialmente
    res_init = client.get("/deepdive/msft")
    assert res_init.status_code == 200
    assert mock_extract.call_count == 1

    # Refresco forzado: Debe invalidar la caché y re-ejecutar el análisis
    res_refresh = client.post("/deepdive/refresh/msft")
    assert res_refresh.status_code == 200
    data_refresh = res_refresh.json()
    assert data_refresh["ticker"] == "MSFT"
    assert data_refresh["from_cache"] is False
    assert mock_extract.call_count == 2
    assert mock_analyze.call_count == 2


@patch("backend.api.routers.deepdive.analyze_quality_value")
@patch("backend.api.routers.deepdive.get_equity_deepdive_data")
def test_get_deepdive_analysis_without_llm_report(mock_extract, mock_analyze, client: TestClient):
    """Verifica degradación elegante cuando el analista de IA no está disponible (devuelve None)."""
    dummy_data = _dummy_deepdive_response("SAN.MC")
    mock_extract.return_value = dummy_data
    mock_analyze.return_value = None

    res = client.get("/deepdive/san.mc")
    assert res.status_code == 200
    data = res.json()
    assert data["ticker"] == "SAN.MC"
    assert data["quality_value_report"] is None
    assert data["piotroski"]["total_score"] == 8
