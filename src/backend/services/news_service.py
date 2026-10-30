import hashlib
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
import feedparser
import yfinance as yf

from backend.domain.schemas.latency_metrics import ExternalProviderEnum
from backend.domain.schemas.market import NewsItem
from backend.services.latency_profiler import track_external_latency

logger = logging.getLogger(__name__)

# Fuentes RSS de referencia en España y la Eurozona
RSS_FEEDS = [
    {
        "name": "elEconomista Mercados",
        "url": "https://www.eleconomista.es/rss/rss-mercados.php",
    },
    {
        "name": "Cinco Días Mercados",
        "url": "https://cincodias.elpais.com/seccion/rss/mercados/",
    },
    {
        "name": "Banco Central Europeo",
        "url": "https://www.ecb.europa.eu/rss/press.html",
    },
]


def _clean_text(raw_text: Optional[str]) -> str:
    """Elimina etiquetas HTML y espacios redundantes de títulos o descripciones."""
    if not raw_text:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_text)
    return " ".join(clean.split())


def _generate_item_id(title: str, link: str) -> str:
    """Genera un identificador determinista y único basado en título y enlace."""
    normalized = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def fetch_yahoo_finance_news(ticker_symbol: str = "^IBEX", limit: int = 5) -> List[NewsItem]:
    """Extrae noticias de Yahoo Finance para un ticker determinado (por defecto IBEX 35)."""
    items: List[NewsItem] = []
    try:
        with track_external_latency(ExternalProviderEnum.YAHOO_FINANCE, "news_feed", target=ticker_symbol) as ctx:
            ticker = yf.Ticker(ticker_symbol)
            raw_news = ticker.news or []
            ctx.status_code = 200
        for entry in raw_news[:limit]:
            title = ""
            link = ""
            source = f"Yahoo Finance ({ticker_symbol})"
            published_at = None

            # yfinance puede devolver formato antiguo (plano) o nuevo (anidado en 'content')
            if isinstance(entry, dict):
                if "content" in entry and isinstance(entry["content"], dict):
                    content = entry["content"]
                    title = _clean_text(content.get("title", ""))
                    canonical = content.get("canonicalUrl") or {}
                    link = canonical.get("url", "")
                    provider = content.get("provider") or {}
                    source = provider.get("displayName") or source
                    published_at = content.get("pubDate")
                else:
                    title = _clean_text(entry.get("title", ""))
                    link = entry.get("link", "")
                    source = entry.get("publisher") or source
                    if "providerPublishTime" in entry:
                        try:
                            ts = entry["providerPublishTime"]
                            published_at = datetime.fromtimestamp(ts).isoformat()
                        except Exception:
                            published_at = None

            if title and link:
                item_id = _generate_item_id(title, link)
                items.append(
                    NewsItem(
                        id=item_id,
                        title=title,
                        link=link,
                        source=source,
                        published_at=published_at,
                    )
                )
    except Exception as e:
        logger.warning(f"Error extrayendo noticias de Yahoo Finance ({ticker_symbol}): {e}")
    return items


def fetch_rss_feed_news(feed_name: str, feed_url: str, limit: int = 5) -> List[NewsItem]:
    """Extrae y normaliza noticias desde un canal RSS público."""
    items: List[NewsItem] = []
    is_ecb = "ecb.europa.eu" in feed_url or "banco central europeo" in feed_name.lower()
    provider = ExternalProviderEnum.ECB if is_ecb else ExternalProviderEnum.OTHER
    op_name = "ecb_rss" if is_ecb else "rss_feed"

    try:
        with track_external_latency(provider, op_name, target=feed_name) as ctx:
            parsed = feedparser.parse(feed_url)
            ctx.status_code = 200

        for entry in parsed.entries[:limit]:
            title = _clean_text(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            published_at = getattr(entry, "published", None) or getattr(entry, "updated", None)

            if title and link:
                item_id = _generate_item_id(title, link)
                items.append(
                    NewsItem(
                        id=item_id,
                        title=title,
                        link=link,
                        source=feed_name,
                        published_at=str(published_at) if published_at else None,
                    )
                )
    except Exception as e:
        logger.warning(f"Error procesando feed RSS '{feed_name}' ({feed_url}): {e}")
    return items


def fetch_financial_news(limit: int = 15) -> List[NewsItem]:
    """
    Agrega noticias financieras de Yahoo Finance y fuentes RSS de España/Eurozona,
    eliminando duplicados y acotando el resultado al límite solicitado (10-15 noticias).
    """
    aggregated_items: List[NewsItem] = []
    seen_titles: set = set()

    # 1. Extraer noticias de Yahoo Finance para el IBEX 35
    yahoo_items = fetch_yahoo_finance_news(ticker_symbol="^IBEX", limit=5)
    for item in yahoo_items:
        norm_title = item.title.strip().lower()
        if norm_title not in seen_titles:
            seen_titles.add(norm_title)
            aggregated_items.append(item)

    # 2. Extraer de los feeds RSS configurados
    for feed_cfg in RSS_FEEDS:
        feed_items = fetch_rss_feed_news(
            feed_name=feed_cfg["name"],
            feed_url=feed_cfg["url"],
            limit=5,
        )
        for item in feed_items:
            norm_title = item.title.strip().lower()
            if norm_title not in seen_titles:
                seen_titles.add(norm_title)
                aggregated_items.append(item)
            if len(aggregated_items) >= limit:
                break
        if len(aggregated_items) >= limit:
            break

    return aggregated_items[:limit]
