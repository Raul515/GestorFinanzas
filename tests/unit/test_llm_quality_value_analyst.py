"""
Pruebas unitarias para el analista agéntico Quality Value con Google Gemini (Spec 003 - Fase 3).
"""

import json
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import pytest

from backend.domain.schemas.deepdive import (
    DeepDiveResponse,
    FinancialStatementYear,
    PiotroskiScore,
)
from backend.services.llm_quality_value_analyst import (
    analyze_quality_value,
    get_configured_deepdive_model,
)


@pytest.fixture
def sample_deepdive_response() -> DeepDiveResponse:
    """Genera una respuesta DeepDiveResponse de prueba con magnitudes cuantitativas completas."""
    stmt = FinancialStatementYear(
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
    return DeepDiveResponse(
        ticker="ITX.MC",
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
        statements=[stmt],
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


def test_get_configured_deepdive_model_precedence():
    """Verifica la precedencia de selección del modelo Gemini (override > DEEPDIVE > MODEL > default)."""
    # 1. Con override explícito
    assert get_configured_deepdive_model("gemini-custom") == "gemini-custom"

    # 2. Con GEMINI_DEEPDIVE_MODEL en entorno
    with patch.dict(os.environ, {"GEMINI_DEEPDIVE_MODEL": "gemini-3.1-flash"}):
        assert get_configured_deepdive_model() == "gemini-3.1-flash"

    # 3. Fallback a GEMINI_MODEL general
    with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash"}, clear=True):
        assert get_configured_deepdive_model() == "gemini-2.5-flash"

    # 4. Fallback por defecto si no hay variables
    with patch.dict(os.environ, {}, clear=True):
        assert get_configured_deepdive_model() == "gemini-2.5-pro"


@patch.dict(os.environ, {}, clear=True)
def test_analyze_quality_value_no_api_key(sample_deepdive_response: DeepDiveResponse):
    """Verifica degradación elegante devolviendo None cuando no hay clave API configurada."""
    report = analyze_quality_value(sample_deepdive_response, api_key=None)
    assert report is None


@patch("backend.services.llm_quality_value_analyst.genai.Client")
def test_analyze_quality_value_success(mock_client_cls, sample_deepdive_response: DeepDiveResponse):
    """Verifica generación y validación correcta del informe agéntico Quality Value."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_llm_payload = {
        "quadrant": "Quality Value",
        "summary_thesis": "Excelente negocio líder global cotizando con prima razonable.",
        "six_ingredients": {
            "long_term_growth": "Crecimiento del 7-9% sostenido.",
            "tailwinds": "Consolidación de cuota y canal digital.",
            "market_leadership": "Número 1 indiscutible en rotación.",
            "moat": "Foso logístico insuperable en radio de proximidad.",
            "high_returns_on_capital": "ROIC > 24% sin apalancamiento.",
            "temporary_headwinds": "Presión puntual en costes laborales.",
        },
        "business_model_and_risks": {
            "business_model": "Venta minorista de moda con ciclo de caja negativo.",
            "capital_dynamics": "CapEx ligero y fuerte conversión a FCF.",
        },
        "bearish_risks": [
            "Escalada de tensiones comerciales y aranceles a la importación textil.",
            "Fuerte desaceleración del consumo discrecional en la Eurozona.",
        ],
        "valuation_projections": {
            "scenario_base": {"target_price": 54.0, "exit_multiple": 20.0, "expected_irr": 0.16},
            "scenario_stress": {"target_price": 38.0, "exit_multiple": 15.0, "expected_irr": 0.05},
        },
        "target_irr_entry_zone": "38.00 € - 42.00 € (TIR exigida: 15% - 20%)",
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_llm_payload)
    mock_client.models.generate_content.return_value = mock_response

    report = analyze_quality_value(sample_deepdive_response, api_key="fake-key-test")

    assert report is not None
    assert report.quadrant == "Quality Value"
    assert "Excelente negocio" in report.summary_thesis
    assert len(report.bearish_risks) == 2
    assert "38.00 €" in report.target_irr_entry_zone
    assert report.six_ingredients["moat"] != ""


@patch("backend.services.llm_quality_value_analyst.genai.Client")
def test_analyze_quality_value_invalid_json_fallback(mock_client_cls, sample_deepdive_response: DeepDiveResponse):
    """Verifica manejo resiliente ante respuesta no JSON o JSON corrupto del modelo."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "Respuesta no estructurada de texto libre..."
    mock_client.models.generate_content.return_value = mock_response

    report = analyze_quality_value(sample_deepdive_response, api_key="fake-key-test")
    assert report is None


@patch("backend.services.llm_quality_value_analyst.genai.Client")
def test_analyze_quality_value_api_exception_fallback(mock_client_cls, sample_deepdive_response: DeepDiveResponse):
    """Verifica que fallos de red o de cuota de la API de Gemini retornen None sin levantar excepciones."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("ResourceExhausted: Quota exceeded")

    report = analyze_quality_value(sample_deepdive_response, api_key="fake-key-test")
    assert report is None


@patch("backend.services.llm_quality_value_analyst.genai.Client")
def test_analyze_quality_value_quadrant_normalization_and_min_risks(
    mock_client_cls, sample_deepdive_response: DeepDiveResponse
):
    """Verifica normalización de cuadrantes y adición preventiva de riesgos si el modelo devuelve menos de 2."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    # Cuadrante devuelto en minúsculas y solo 1 riesgo bajista
    mock_llm_payload = {
        "quadrant": "trampa de valor",
        "summary_thesis": "Riesgo de pérdida de competitividad.",
        "bearish_risks": ["Deterioro acelerado de márgenes."],
        "target_irr_entry_zone": "N/A",
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_llm_payload)
    mock_client.models.generate_content.return_value = mock_response

    report = analyze_quality_value(sample_deepdive_response, api_key="fake-key-test")

    assert report is not None
    assert report.quadrant == "Trampa de Valor"
    assert len(report.bearish_risks) >= 2
