"""Pruebas unitarias de instrumentación de proveedores externos (Yahoo Finance, BCE, Gemini).

Verifica que las llamadas salientes en los servicios de negocio invoquen defensivamente
el LatencyTracker con sus respectivos proveedores, operaciones y targets.
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from backend.domain.schemas.latency_metrics import ExternalProviderEnum, LatencyStatusEnum
from backend.services.equity_deepdive import fetch_historical_financials
from backend.services.latency_profiler import get_latency_tracker, reset_latency_tracker
from backend.services.llm_copilot_advisor import run_copilot_turn
from backend.services.llm_news_analyst import analyze_news_batch
from backend.services.llm_quality_value_analyst import analyze_quality_value
from backend.services.market_data import _extract_ticker_data, _fetch_ecb_series
from backend.services.news_service import fetch_financial_news, fetch_rss_feed_news, fetch_yahoo_finance_news
from backend.services.screener_service import fetch_stock_item


def test_market_data_yahoo_instrumentation():
    """Verifica que _extract_ticker_data registre la métrica de Yahoo Finance."""
    reset_latency_tracker()

    mock_history = pd.DataFrame({"Close": [100.0, 102.5]})
    mock_ticker_instance = MagicMock()
    mock_ticker_instance.history.return_value = mock_history

    with patch("backend.services.market_data.yf.Ticker", return_value=mock_ticker_instance):
        ind = _extract_ticker_data("^IBEX", "ibex35", "IBEX 35", "España")

    assert ind.current_value == 102.5
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()

    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.YAHOO_FINANCE
    assert call.operation == "ticker_history"
    assert call.target == "^IBEX"
    assert call.status == LatencyStatusEnum.OK


def test_market_data_ecb_instrumentation():
    """Verifica que _fetch_ecb_series registre la métrica del BCE."""
    reset_latency_tracker()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "dataSets": [
            {
                "series": {
                    "0": {
                        "observations": {
                            "0": [2.20],
                            "1": [2.25],
                        }
                    }
                }
            }
        ]
    }

    bund_url = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=25"
    with patch("backend.services.market_data.requests.get", return_value=mock_response):
        cur, diff, vals = _fetch_ecb_series(bund_url, default_val=2.0)

    assert cur == 2.25
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()

    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.ECB
    assert call.operation == "yield_series"
    assert call.target == "bund_10y"
    assert call.status_code == 200


def test_news_service_yahoo_and_ecb_instrumentation():
    """Verifica que las noticias de Yahoo Finance y el feed RSS del BCE registren sus métricas."""
    reset_latency_tracker()

    # 1. Yahoo News
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {"title": "Noticia IBEX", "link": "https://example.com/1", "publisher": "Reuters"}
    ]
    with patch("backend.services.news_service.yf.Ticker", return_value=mock_ticker):
        items = fetch_yahoo_finance_news("^IBEX", limit=1)
    assert len(items) == 1

    # 2. ECB RSS Feed
    mock_parsed = MagicMock()
    mock_entry = MagicMock()
    mock_entry.title = "Comunicado BCE"
    mock_entry.link = "https://ecb.europa.eu/press/1"
    mock_entry.published = "2026-10-30"
    mock_parsed.entries = [mock_entry]

    with patch("backend.services.news_service.feedparser.parse", return_value=mock_parsed):
        rss_items = fetch_rss_feed_news("Banco Central Europeo", "https://www.ecb.europa.eu/rss/press.html")
    assert len(rss_items) == 1

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 2

    providers = [c.provider for c in report.recent_calls]
    assert ExternalProviderEnum.YAHOO_FINANCE in providers
    assert ExternalProviderEnum.ECB in providers


def test_equity_deepdive_instrumentation():
    """Verifica que fetch_historical_financials registre la consulta a Yahoo Finance."""
    reset_latency_tracker()

    mock_ticker = MagicMock()
    mock_ticker.info = {"sector": "Technology", "industry": "Software"}
    mock_df = pd.DataFrame({"2025": [100.0], "2024": [90.0]}, index=["Total Revenue"])
    mock_ticker.financials = mock_df
    mock_ticker.balance_sheet = mock_df
    mock_ticker.cashflow = mock_df

    with patch("backend.services.equity_deepdive.yf.Ticker", return_value=mock_ticker):
        info, statements, is_bank = fetch_historical_financials("ITX.MC")

    assert not is_bank
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()

    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.YAHOO_FINANCE
    assert call.operation == "deepdive_financials"
    assert call.target == "ITX.MC"


def test_screener_service_instrumentation():
    """Verifica que fetch_stock_item registre la consulta individual en Yahoo Finance."""
    reset_latency_tracker()

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 45.0,
        "regularMarketChangePercent": 1.2,
        "trailingPE": 18.5,
        "shortName": "Inditex",
    }

    with patch("backend.services.screener_service.yf.Ticker", return_value=mock_ticker):
        item = fetch_stock_item("ITX.MC")

    assert item is not None
    assert item.price == 45.0
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()

    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.YAHOO_FINANCE
    assert call.operation == "screener_stock_info"
    assert call.target == "ITX.MC"


def test_gemini_quality_value_analyst_instrumentation():
    """Verifica que generate_quality_value_report registre la métrica de inferencia de Gemini."""
    reset_latency_tracker()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"quadrant": "Quality Value", "summary_thesis": "Excelente foso", "bearish_risks": ["Riesgo 1", "Riesgo 2"]}'
    mock_client.models.generate_content.return_value = mock_response

    mock_deepdive = MagicMock()
    mock_deepdive.ticker = "ITX.MC"
    mock_deepdive.name = "Inditex"
    mock_deepdive.sector = "Consumo Cíclico"
    mock_deepdive.industry = "Textil"
    mock_deepdive.country = "España"
    mock_deepdive.currency = "EUR"
    mock_deepdive.current_price = 45.0
    mock_deepdive.market_cap = 140000000000.0
    mock_deepdive.pe_trailing = 22.0
    mock_deepdive.pe_forward = 20.0
    mock_deepdive.ev_to_ebitda = 12.0
    mock_deepdive.price_to_book = 6.0
    mock_deepdive.dividend_yield = 3.5
    mock_deepdive.beta = 0.85
    mock_deepdive.piotroski = MagicMock(total_score=8, max_score=9, rating="Excelente")
    mock_deepdive.fcf_metrics = {"fcf_to_net_income": 1.1, "fcf_margin_pct": 15.0, "fcf_yield_pct": 5.5}
    mock_deepdive.historical_years = []
    mock_deepdive.is_financial_institution = False

    with patch("backend.services.llm_quality_value_analyst._get_gemini_client", return_value=mock_client):
        report_res = analyze_quality_value(mock_deepdive, api_key="fake_key")

    assert report_res is not None
    assert report_res.quadrant == "Quality Value"

    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.GEMINI
    assert call.operation == "quality_value_report"
    assert call.status == LatencyStatusEnum.OK


def test_gemini_news_analyst_instrumentation():
    """Verifica que analyze_market_news registre la inferencia de Gemini."""
    reset_latency_tracker()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"id": "item1", "impact": "Medio", "topic": "Macroeconomía España y Eurozona", "summary": "Inflación moderada."}]'
    mock_client.models.generate_content.return_value = mock_response

    mock_item = MagicMock()
    mock_item.id = "item1"
    mock_item.title = "Titular de prueba"
    mock_item.link = "https://example.com"
    mock_item.source = "Test"
    mock_item.published_at = None

    with patch("backend.services.llm_news_analyst._get_gemini_client", return_value=mock_client):
        analyzed, ok = analyze_news_batch([mock_item], api_key="fake_key")

    assert ok is True
    assert len(analyzed) == 1
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.GEMINI
    assert call.operation == "news_sentiment_analysis"


def test_gemini_copilot_advisor_instrumentation():
    """Verifica que chat_with_copilot registre la llamada de Gemini."""
    reset_latency_tracker()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Respuesta del asesor patrimonial"
    mock_response.function_calls = None
    mock_client.models.generate_content.return_value = mock_response

    mock_repo = MagicMock()

    with patch("backend.services.llm_copilot_advisor.genai.Client", return_value=mock_client):
        turn_result = run_copilot_turn(
            user_message="¿Cómo calcular el interés compuesto?",
            conversation_history=[],
            repo=mock_repo,
            api_key="fake_key",
        )

    assert "Respuesta del asesor patrimonial" in turn_result["reply_text"]
    tracker = get_latency_tracker()
    report = tracker.get_metrics_report()
    assert report.total_calls_recorded == 1
    call = report.recent_calls[0]
    assert call.provider == ExternalProviderEnum.GEMINI
    assert call.operation == "copilot_chat"
