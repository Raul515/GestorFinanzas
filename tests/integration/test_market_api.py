from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.domain.schemas.market import (
    AnalyzedNewsItem,
    ImpactLevel,
    MacroIndicator,
    MacroOverviewResponse,
    MarketNewsResponse,
    NewsTopic,
)


def _dummy_macro_response(is_cached: bool = False) -> MacroOverviewResponse:
    return MacroOverviewResponse(
        indicators=[
            MacroIndicator(
                id="ibex35",
                name="IBEX 35",
                symbol="^IBEX",
                region="España",
                current_value=11500.0,
                change_pct=0.85,
                change_abs=97.0,
                unit="pts",
                sparkline_30d=[11400.0, 11500.0],
            )
        ],
        fetched_at=datetime.now(timezone.utc),
        is_cached=is_cached,
        source_notes="Datos mockeados",
    )


def _dummy_news_response(is_cached: bool = False) -> MarketNewsResponse:
    return MarketNewsResponse(
        news=[
            AnalyzedNewsItem(
                id="news1",
                title="El BCE mantiene tipos rectores",
                link="https://noticias.com/1",
                source="BCE",
                published_at="2026-10-26T08:00:00Z",
                impact=ImpactLevel.HIGH.value,
                topic=NewsTopic.MONETARY_POLICY.value,
                summary="El Consejo de Gobierno mantiene estables los tipos oficiales.",
            )
        ],
        fetched_at=datetime.now(timezone.utc),
        is_cached=is_cached,
        ai_analysis_available=True,
        notes="Análisis mock",
    )


def test_get_macro_indicators_cache_flow(client: TestClient):
    """
    Verifica que la primera llamada a /market/macro-indicators consulta la fuente
    y la segunda llamada recupera el resultado desde la caché SQLite de 24 horas.
    """
    with patch(
        "backend.api.routers.market.get_macro_overview_response"
    ) as mock_service:
        mock_service.return_value = _dummy_macro_response(is_cached=False)

        # 1. Primera llamada (Cache Miss)
        res1 = client.get("/market/macro-indicators")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["is_cached"] is False
        assert len(data1["indicators"]) == 1
        assert data1["indicators"][0]["name"] == "IBEX 35"
        assert mock_service.call_count == 1

        # 2. Segunda llamada (Cache Hit)
        res2 = client.get("/market/macro-indicators")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["is_cached"] is True
        assert len(data2["indicators"]) == 1
        assert data2["indicators"][0]["name"] == "IBEX 35"
        # El servicio externo NO debe ser llamado de nuevo
        assert mock_service.call_count == 1


def test_get_market_news_cache_flow(client: TestClient):
    """
    Verifica que la primera llamada a /market/news procesa las noticias con IA
    y la segunda llamada sirve la respuesta directamente desde la caché local.
    """
    with patch(
        "backend.api.routers.market.get_analyzed_market_news"
    ) as mock_service:
        mock_service.return_value = _dummy_news_response(is_cached=False)

        # 1. Primera llamada (Cache Miss)
        res1 = client.get("/market/news?limit=10")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["is_cached"] is False
        assert len(data1["news"]) == 1
        assert data1["news"][0]["impact"] == "Alto"
        assert mock_service.call_count == 1

        # 2. Segunda llamada (Cache Hit)
        res2 = client.get("/market/news?limit=10")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["is_cached"] is True
        assert len(data2["news"]) == 1
        # No se repite la llamada al servicio externo ni a Gemini
        assert mock_service.call_count == 1


def test_refresh_market_radar(client: TestClient):
    """
    Verifica que POST /market/refresh fuerza la recarga de indicadores y noticias,
    actualizando ambas claves en la caché de SQLite.
    """
    with patch(
        "backend.api.routers.market.get_macro_overview_response"
    ) as mock_macro, patch(
        "backend.api.routers.market.get_analyzed_market_news"
    ) as mock_news:
        mock_macro.return_value = _dummy_macro_response(is_cached=False)
        mock_news.return_value = _dummy_news_response(is_cached=False)

        response = client.post("/market/refresh")
        assert response.status_code == 200
        data = response.json()

        assert "actualizado con éxito" in data["message"]
        assert len(data["macro_indicators"]["indicators"]) == 1
        assert len(data["news"]["news"]) == 1
        assert mock_macro.call_count == 1
        assert mock_news.call_count == 1

        # Comprobar que tras el refresco, una llamada GET a noticias llega desde la caché
        res_cached = client.get("/market/news")
        assert res_cached.status_code == 200
        assert res_cached.json()["is_cached"] is True
        assert mock_news.call_count == 1
