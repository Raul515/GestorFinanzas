import json
import os
from unittest.mock import MagicMock, patch
import pytest

from backend.domain.schemas.market import (
    ImpactLevel,
    NewsItem,
    NewsTopic,
)
from backend.services.llm_news_analyst import (
    analyze_news_batch,
    get_analyzed_market_news,
)


@pytest.fixture
def sample_news_items():
    return [
        NewsItem(
            id="item1",
            title="El BCE decide una bajada de tipos de 25 puntos básicos",
            link="https://fuente.com/1",
            source="elEconomista",
        ),
        NewsItem(
            id="item2",
            title="Inditex bate récords de facturación en el tercer trimestre",
            link="https://fuente.com/2",
            source="Cinco Días",
        ),
    ]


def test_analyze_news_batch_empty_list():
    items, ai_available = analyze_news_batch([])
    assert items == []
    assert ai_available is True


@patch.dict(os.environ, {}, clear=True)
def test_analyze_news_batch_no_api_key(sample_news_items):
    # Sin clave GEMINI_API_KEY en entorno ni argumento
    items, ai_available = analyze_news_batch(sample_news_items, api_key=None)
    assert ai_available is False
    assert len(items) == 2
    assert "no configurada" in items[0].summary
    assert items[0].impact == ImpactLevel.MEDIUM.value
    assert items[0].topic == NewsTopic.MACROECONOMY.value


@patch("backend.services.llm_news_analyst.genai.Client")
def test_analyze_news_batch_success(mock_client_cls, sample_news_items):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = json.dumps(
        [
            {
                "id": "item1",
                "impact": "Alto",
                "topic": "Política Monetaria BCE / Tipos e Hipotecas",
                "summary": "El BCE abarata el crédito hipotecario al reducir los tipos rectores.",
            },
            {
                "id": "item2",
                "impact": "Medio",
                "topic": "Resultados Empresariales",
                "summary": "Inditex consolida su liderazgo bursátil con márgenes sólidos.",
            },
        ]
    )
    mock_client.models.generate_content.return_value = mock_response

    items, ai_available = analyze_news_batch(
        sample_news_items,
        api_key="fake-test-key",
        model_name="gemini-pro-test",
    )

    assert ai_available is True
    assert len(items) == 2
    assert items[0].id == "item1"
    assert items[0].impact == "Alto"
    assert items[0].topic == "Política Monetaria BCE / Tipos e Hipotecas"
    assert "abarata el crédito" in items[0].summary

    assert items[1].id == "item2"
    assert items[1].impact == "Medio"
    assert items[1].topic == "Resultados Empresariales"

    # Verificar que el modelo solicitado se pasó a la llamada
    call_args, call_kwargs = mock_client.models.generate_content.call_args
    assert call_kwargs.get("model") == "gemini-pro-test"


@patch("backend.services.llm_news_analyst.genai.Client")
def test_analyze_news_batch_invalid_json_fallback(mock_client_cls, sample_news_items):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    # Respuesta no parseable como JSON
    mock_response = MagicMock()
    mock_response.text = "Respuesta en texto libre sin formato JSON"
    mock_client.models.generate_content.return_value = mock_response

    items, ai_available = analyze_news_batch(
        sample_news_items,
        api_key="fake-key",
    )

    assert ai_available is False
    assert len(items) == 2
    assert "no disponible temporalmente" in items[0].summary


@patch("backend.services.llm_news_analyst.genai.Client")
def test_analyze_news_batch_api_exception_fallback(mock_client_cls, sample_news_items):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    # Simular caída de red o límite de cuota
    mock_client.models.generate_content.side_effect = Exception("Quota exceeded 429")

    items, ai_available = analyze_news_batch(
        sample_news_items,
        api_key="fake-key",
    )

    assert ai_available is False
    assert len(items) == 2
    assert items[0].impact == ImpactLevel.MEDIUM.value
    assert "no disponible temporalmente" in items[0].summary


@patch("backend.services.llm_news_analyst.analyze_news_batch")
@patch("backend.services.llm_news_analyst.fetch_financial_news")
def test_get_analyzed_market_news_orchestration(mock_fetch, mock_analyze, sample_news_items):
    mock_fetch.return_value = sample_news_items
    from backend.domain.schemas.market import AnalyzedNewsItem
    analyzed_samples = [
        AnalyzedNewsItem(
            id="item1",
            title="Noticia 1",
            link="https://fuente.com/1",
            source="Fuente 1",
            summary="Resumen 1",
        ),
        AnalyzedNewsItem(
            id="item2",
            title="Noticia 2",
            link="https://fuente.com/2",
            source="Fuente 2",
            summary="Resumen 2",
        ),
    ]
    mock_analyze.return_value = (analyzed_samples, True)

    response = get_analyzed_market_news(limit=5, api_key="fake-key")

    assert response.is_cached is False
    assert response.ai_analysis_available is True
    assert len(response.news) == 2
    assert response.notes is not None and "Google Gemini" in response.notes
