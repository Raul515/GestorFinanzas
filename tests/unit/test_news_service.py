from unittest.mock import MagicMock, patch
import pytest

from backend.domain.schemas.market import NewsItem
from backend.services.news_service import (
    _clean_text,
    _generate_item_id,
    fetch_financial_news,
    fetch_rss_feed_news,
    fetch_yahoo_finance_news,
)


def test_clean_text_removes_html_and_spaces():
    raw = "<p>El <b>Ibex 35</b> sube un 1.2%&nbsp;hoy.</p>   \n   "
    clean = _clean_text(raw)
    assert clean == "El Ibex 35 sube un 1.2%&nbsp;hoy."
    assert _clean_text(None) == ""
    assert _clean_text("") == ""


def test_generate_item_id_deterministic():
    id1 = _generate_item_id("Título de Prueba", "https://ejemplo.com/noticia-1")
    id2 = _generate_item_id("Título de Prueba", "https://ejemplo.com/noticia-1")
    id3 = _generate_item_id("Otro Título", "https://ejemplo.com/noticia-2")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


@patch("backend.services.news_service.yf.Ticker")
def test_fetch_yahoo_finance_news_legacy_format(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            "title": "El Ibex 35 lidera las ganancias en Europa",
            "link": "https://finance.yahoo.com/news/ibex-lidera-123.html",
            "publisher": "Reuters España",
            "providerPublishTime": 1700000000,
        }
    ]
    mock_ticker_cls.return_value = mock_ticker

    items = fetch_yahoo_finance_news(ticker_symbol="^IBEX", limit=5)
    assert len(items) == 1
    assert items[0].title == "El Ibex 35 lidera las ganancias en Europa"
    assert items[0].link == "https://finance.yahoo.com/news/ibex-lidera-123.html"
    assert items[0].source == "Reuters España"
    assert items[0].published_at is not None


@patch("backend.services.news_service.yf.Ticker")
def test_fetch_yahoo_finance_news_new_content_format(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            "content": {
                "title": "El BCE mantiene los tipos de interés",
                "canonicalUrl": {"url": "https://finance.yahoo.com/news/bce-tipos-456.html"},
                "provider": {"displayName": "Bloomberg"},
                "pubDate": "2026-10-23T10:00:00Z",
            }
        }
    ]
    mock_ticker_cls.return_value = mock_ticker

    items = fetch_yahoo_finance_news(ticker_symbol="^IBEX", limit=5)
    assert len(items) == 1
    assert items[0].title == "El BCE mantiene los tipos de interés"
    assert items[0].source == "Bloomberg"
    assert items[0].published_at == "2026-10-23T10:00:00Z"


@patch("backend.services.news_service.yf.Ticker")
def test_fetch_yahoo_finance_news_error_graceful(mock_ticker_cls):
    mock_ticker_cls.side_effect = Exception("Conexión fallida con Yahoo")
    items = fetch_yahoo_finance_news(ticker_symbol="^IBEX")
    assert items == []


@patch("backend.services.news_service.feedparser.parse")
def test_fetch_rss_feed_news_success(mock_parse):
    entry1 = MagicMock()
    entry1.title = "La inflación en España modera su subida al 2.1%"
    entry1.link = "https://www.eleconomista.es/mercados/noticia-ipc.html"
    entry1.published = "Fri, 24 Oct 2026 09:30:00 GMT"

    parsed_result = MagicMock()
    parsed_result.entries = [entry1]
    mock_parse.return_value = parsed_result

    items = fetch_rss_feed_news(
        feed_name="elEconomista",
        feed_url="https://fake-url.com/rss",
        limit=5,
    )
    assert len(items) == 1
    assert items[0].title == "La inflación en España modera su subida al 2.1%"
    assert items[0].source == "elEconomista"
    assert items[0].published_at == "Fri, 24 Oct 2026 09:30:00 GMT"


@patch("backend.services.news_service.feedparser.parse")
def test_fetch_rss_feed_news_error_graceful(mock_parse):
    mock_parse.side_effect = Exception("Error de red al leer feed")
    items = fetch_rss_feed_news(
        feed_name="Cinco Días",
        feed_url="https://fake-url.com/rss",
    )
    assert items == []


@patch("backend.services.news_service.fetch_rss_feed_news")
@patch("backend.services.news_service.fetch_yahoo_finance_news")
def test_fetch_financial_news_aggregation_and_deduplication(mock_yahoo, mock_rss):
    item1 = NewsItem(
        id="1",
        title="El BCE baja tipos 25 pb",
        link="https://fuente1.com/1",
        source="Yahoo",
    )
    # Noticia duplicada en RSS
    item2 = NewsItem(
        id="2",
        title="el bce baja tipos 25 pb",  # Duplicado por título en minúsculas
        link="https://fuente2.com/2",
        source="elEconomista",
    )
    item3 = NewsItem(
        id="3",
        title="Telefónica presenta resultados trimestrales",
        link="https://fuente3.com/3",
        source="Cinco Días",
    )

    mock_yahoo.return_value = [item1]
    mock_rss.side_effect = [
        [item2, item3],  # Primer feed
        [],              # Segundo feed
        [],              # Tercer feed
    ]

    results = fetch_financial_news(limit=10)
    assert len(results) == 2
    assert results[0].title == "El BCE baja tipos 25 pb"
    assert results[1].title == "Telefónica presenta resultados trimestrales"
