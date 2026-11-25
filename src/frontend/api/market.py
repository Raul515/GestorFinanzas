"""Cliente HTTP para Radar de Mercado, Screener, Deep Dive y Watchlist."""

from typing import Any, Dict, List, Optional

import streamlit as st

from frontend.api import http


@st.cache_data(ttl=300, show_spinner=False)
def get_macro_indicators() -> Optional[Dict[str, Any]]:
    """Obtiene los indicadores macroeconómicos y deuda soberana desde el backend."""
    return http.request("GET", "/market/macro-indicators", timeout=15, default=None, log_context="get_macro_indicators")


@st.cache_data(ttl=300, show_spinner=False)
def get_market_news(limit: int = 15) -> Optional[Dict[str, Any]]:
    """Obtiene las noticias financieras depuradas con análisis de IA desde el backend."""
    return http.request("GET", "/market/news", params={"limit": limit}, timeout=35, default=None, log_context="get_market_news")


def refresh_market_radar() -> Optional[Dict[str, Any]]:
    """Fuerza la invalidación y recarga manual del Radar de Mercado y Noticias."""
    res = http.request("POST", "/market/refresh", timeout=60, default=None, log_context="refresh_market_radar")
    if res is not None:
        http.clear_cache_hook("clear_market_cache")
    return res


@st.cache_data(ttl=3600, show_spinner=False)
def get_screener_universes() -> List[Dict[str, Any]]:
    """Obtiene la lista de universos predefinidos para el screener."""
    return http.request("GET", "/screener/universes", default=[], log_context="get_screener_universes")


@st.cache_data(ttl=1800, show_spinner=False)
def get_screener_universe(
    universe_id: str,
    preset: Any = None,
    max_pe: Any = None,
    min_dividend_yield: Any = None,
    min_roe: Any = None,
    max_debt_to_equity: Any = None,
    max_expense_ratio: Any = None,
    search_query: Any = None,
) -> Optional[Dict[str, Any]]:
    """Consulta los activos de un universo aplicando filtros cuantitativos y de preset."""
    params: Dict[str, Any] = {}
    if preset:
        params["preset"] = preset
    if max_pe is not None:
        params["max_pe"] = max_pe
    if min_dividend_yield is not None:
        params["min_dividend_yield"] = min_dividend_yield
    if min_roe is not None:
        params["min_roe"] = min_roe
    if max_debt_to_equity is not None:
        params["max_debt_to_equity"] = max_debt_to_equity
    if max_expense_ratio is not None:
        params["max_expense_ratio"] = max_expense_ratio
    if search_query:
        params["search_query"] = search_query

    return http.request(
        "GET",
        f"/screener/universe/{universe_id}",
        params=params,
        timeout=30,
        default=None,
        log_context=f"get_screener_universe({universe_id})",
    )


def get_screener_custom(tickers: List[str], filter_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Consulta y filtra una lista personalizada de tickers."""
    return http.request(
        "POST",
        "/screener/custom",
        json={"tickers": tickers, "filter_params": filter_params},
        timeout=35,
        default=None,
        log_context="get_screener_custom",
    )


def refresh_screener_universe(universe_id: str) -> Optional[Dict[str, Any]]:
    """Fuerza la invalidación de la caché en SQLite y descarga datos frescos de Yahoo Finance."""
    res = http.request(
        "POST",
        f"/screener/refresh/{universe_id}",
        timeout=60,
        default=None,
        log_context=f"refresh_screener_universe({universe_id})",
    )
    if res is not None:
        try:
            get_screener_universe.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de screener: %s", exc)
    return res


@st.cache_data(ttl=1800, show_spinner=False)
def get_deepdive_analysis(ticker: str) -> Optional[Dict[str, Any]]:
    """Consulta el diagnóstico contable en profundidad (Deep Dive)."""
    clean_ticker = ticker.strip().upper()
    return http.request(
        "GET",
        f"/deepdive/{clean_ticker}",
        timeout=40,
        default=None,
        log_context=f"get_deepdive_analysis({clean_ticker})",
    )


def refresh_deepdive_analysis(ticker: str) -> Optional[Dict[str, Any]]:
    """Fuerza la invalidación de caché y regenera el análisis Deep Dive para un ticker."""
    clean_ticker = ticker.strip().upper()
    res = http.request(
        "POST",
        f"/deepdive/refresh/{clean_ticker}",
        timeout=60,
        default=None,
        log_context=f"refresh_deepdive_analysis({clean_ticker})",
    )
    if res is not None:
        try:
            get_deepdive_analysis.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de deepdive: %s", exc)
    return res


def get_watchlist() -> List[Dict[str, Any]]:
    """Recupera la lista de activos en seguimiento guardados en la base de datos local."""
    return http.request("GET", "/watchlist", default=[], log_context="get_watchlist")


def add_to_watchlist(item: dict) -> Optional[Dict[str, Any]]:
    """Añade o actualiza un activo con sus notas en la lista de seguimiento local."""
    return http.request(
        "POST",
        "/watchlist",
        json=item,
        expected_statuses=(200, 201),
        default=None,
        log_context="add_to_watchlist",
    )


def remove_from_watchlist(ticker: str) -> bool:
    """Elimina un activo de la lista de seguimiento local."""
    clean_ticker = ticker.strip().upper()
    res = http.request(
        "DELETE",
        f"/watchlist/{clean_ticker}",
        default=None,
        log_context=f"remove_from_watchlist({clean_ticker})",
    )
    return res is not None
