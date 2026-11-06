import streamlit as st
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Asegurar que src esté en el sys.path si se invoca directamente desde el frontend
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from backend.utils.logging_config import setup_logging

frontend_log_file = os.getenv("FRONTEND_LOG_FILE", "logs/frontend.log")
setup_logging(frontend_log_file)
logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# Pool de conexiones persistentes HTTP con Keep-Alive para eliminar sobrecarga de sockets
_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=30,
    max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504]),
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def get_session() -> requests.Session:
    """Retorna la sesión HTTP persistente compartida."""
    return _session


@st.cache_data(ttl=600, show_spinner=False)
def get_categorias():
    """Obtiene el listado de categorías, normalizando claves para compatibilidad bidireccional."""
    url = f"{API_URL}/categories/"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for c in raw:
                if "name" in c and "nombre" not in c:
                    c["nombre"] = c["name"]
                if "nombre" in c and "name" not in c:
                    c["name"] = c["nombre"]
                if "type" in c and "tipo" not in c:
                    c["tipo"] = c["type"]
                if "tipo" in c and "type" not in c:
                    c["type"] = c["tipo"]
                for s in c.get("subcategories", []):
                    if "name" in s and "nombre" not in s:
                        s["nombre"] = s["name"]
                    if "nombre" in s and "name" not in s:
                        s["name"] = s["nombre"]
                    if "category_id" in s and "categoria_id" not in s:
                        s["categoria_id"] = s["category_id"]
                    if "categoria_id" in s and "category_id" not in s:
                        s["category_id"] = s["categoria_id"]
            return raw
        logger.warning("Respuesta no exitosa al consultar categorías (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar categorías en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_categorias(): %s", e)
    return []


@st.cache_data(ttl=600, show_spinner=False)
def get_subcategorias(categoria_id=None):
    """Obtiene subcategorías, normalizando claves para compatibilidad bidireccional."""
    url = f"{API_URL}/categories/subcategories/"
    params = {}
    if categoria_id:
        params["category_id"] = categoria_id
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for s in raw:
                if "name" in s and "nombre" not in s:
                    s["nombre"] = s["name"]
                if "nombre" in s and "name" not in s:
                    s["name"] = s["nombre"]
                if "category_id" in s and "categoria_id" not in s:
                    s["categoria_id"] = s["category_id"]
                if "categoria_id" in s and "category_id" not in s:
                    s["category_id"] = s["categoria_id"]
            return raw
        logger.warning("Respuesta no exitosa al consultar subcategorías (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar subcategorías en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_subcategorias(): %s", e)
    return []

def create_subcategory(category_id: int, name: str) -> Optional[Dict[str, Any]]:
    """
    Crea una nueva subcategoría personal vinculada a una categoría padre.
    Invalida reactivamente la caché de categorías y el resumen anual.
    """
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        logger.warning("Intento de crear subcategoría personal con nombre vacío")
        return None

    url = f"{API_URL}/categories/subcategories/"
    payload = {"category_id": category_id, "name": cleaned_name}
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_categories_cache()
            clear_annual_cache()
            logger.info("Subcategoría personal '%s' creada con éxito", cleaned_name)
            return response.json()
        logger.warning("Fallo al crear subcategoría personal (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en create_subcategory en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_subcategory(): %s", e)
    return None


def update_subcategory(subcategory_id: int, name: str) -> Optional[Dict[str, Any]]:
    """
    Actualiza el nombre de una subcategoría personal existente.
    Invalida reactivamente la caché de categorías y el resumen anual.
    """
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        logger.warning("Intento de actualizar subcategoría %s con nombre vacío", subcategory_id)
        return None

    url = f"{API_URL}/categories/subcategories/{subcategory_id}"
    payload = {"name": cleaned_name}
    try:
        response = _session.put(url, json=payload, timeout=10)
        if response.status_code == 200:
            clear_categories_cache()
            clear_annual_cache()
            logger.info("Subcategoría personal %s renombrada a '%s'", subcategory_id, cleaned_name)
            return response.json()
        logger.warning("Fallo al actualizar subcategoría personal %s (%s): %s", subcategory_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en update_subcategory en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_subcategory(): %s", e)
    return None


def get_subcategory_usage(subcategory_id: int) -> Optional[Dict[str, Any]]:
    """
    Consulta la auditoría contable de uso de una subcategoría personal (número de transacciones y presupuestos).
    """
    url = f"{API_URL}/categories/subcategories/{subcategory_id}/usage"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al consultar uso de subcategoría %s (%s): %s", subcategory_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_subcategory_usage en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_subcategory_usage(): %s", e)
    return None


def delete_subcategory(subcategory_id: int) -> Tuple[bool, str]:
    """
    Elimina físicamente una subcategoría personal si no tiene histórico contable asociado.
    Retorna (True, mensaje) si se eliminó, o (False, detalle_error) si está bloqueada o falla.
    """
    url = f"{API_URL}/categories/subcategories/{subcategory_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            clear_categories_cache()
            clear_annual_cache()
            logger.info("Subcategoría personal %s eliminada con éxito", subcategory_id)
            return True, "Subcategoría eliminada con éxito."
        elif response.status_code == 409:
            err_msg = response.json().get("detail", "La subcategoría contiene registros vinculados y no puede eliminarse.")
            logger.warning("Borrado bloqueado por dependencias en subcategoría %s: %s", subcategory_id, err_msg)
            return False, err_msg
        else:
            err_msg = response.json().get("detail", response.text) if response.headers.get("content-type") == "application/json" else response.text
            logger.warning("Error al eliminar subcategoría %s (%s): %s", subcategory_id, response.status_code, err_msg)
            return False, f"Error del servidor ({response.status_code}): {err_msg}"
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_subcategory en %s: %s", url, e)
        return False, f"Error de red o conexión: {e}"
    except Exception as e:
        logger.error("Error inesperado en delete_subcategory(): %s", e)
        return False, f"Error inesperado: {e}"



def get_presupuestos(mes):
    """Obtiene presupuestos de un mes, normalizando claves para compatibilidad bidireccional."""
    url = f"{API_URL}/budgets/{mes}"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for p in raw:
                if "month" in p and "mes" not in p:
                    p["mes"] = p["month"]
                if "mes" in p and "month" not in p:
                    p["month"] = p["mes"]
                if "amount" in p and "cantidad" not in p:
                    p["cantidad"] = p["amount"]
                if "cantidad" in p and "amount" not in p:
                    p["amount"] = p["cantidad"]
                if "subcategory_id" in p and "subcategoria_id" not in p:
                    p["subcategoria_id"] = p["subcategory_id"]
                if "subcategoria_id" in p and "subcategory_id" not in p:
                    p["subcategory_id"] = p["subcategoria_id"]
            return raw
        logger.warning("Respuesta no exitosa al consultar presupuestos de %s (%s): %s", mes, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar presupuestos en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_presupuestos(%s): %s", mes, e)
    return []


def create_presupuesto(mes: str, subcategoria_id: int, cantidad: float) -> Optional[Dict[str, Any]]:
    """
    Crea o actualiza una asignación presupuestaria individual para un mes o plantilla BASE.
    Invalida reactivamente la caché del resumen anual consolidado.
    """
    url = f"{API_URL}/budgets/"
    payload = {
        "month": mes,
        "subcategory_id": subcategoria_id,
        "amount": float(cantidad or 0.0),
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_annual_cache()
            raw = response.json()
            if isinstance(raw, dict):
                if "month" in raw and "mes" not in raw:
                    raw["mes"] = raw["month"]
                if "amount" in raw and "cantidad" not in raw:
                    raw["cantidad"] = raw["amount"]
                if "subcategory_id" in raw and "subcategoria_id" not in raw:
                    raw["subcategoria_id"] = raw["subcategory_id"]
            return raw
        logger.warning("Error al crear presupuesto individual (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al crear presupuesto en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_presupuesto(): %s", e)
    return None

create_budget = create_presupuesto


def get_transacciones(mes=None):
    """Obtiene transacciones de un mes, normalizando claves para compatibilidad bidireccional."""
    url = f"{API_URL}/transactions/"
    params = {}
    if mes:
        params["month"] = mes
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for t in raw:
                if "date" in t and "fecha" not in t:
                    t["fecha"] = t["date"]
                if "fecha" in t and "date" not in t:
                    t["date"] = t["fecha"]
                if "amount" in t and "cantidad" not in t:
                    t["cantidad"] = t["amount"]
                if "cantidad" in t and "amount" not in t:
                    t["amount"] = t["cantidad"]
                if "description" in t and "concepto" not in t:
                    t["concepto"] = t["description"]
                if "concepto" in t and "description" not in t:
                    t["description"] = t["concepto"]
                if "subcategory_id" in t and "subcategoria_id" not in t:
                    t["subcategoria_id"] = t["subcategory_id"]
                if "subcategoria_id" in t and "subcategory_id" not in t:
                    t["subcategory_id"] = t["subcategoria_id"]
            return raw
        logger.warning("Respuesta no exitosa al consultar transacciones (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar transacciones en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_transacciones(): %s", e)
    return []

@st.cache_data(ttl=120, show_spinner=False)
def get_annual_summary_data(year: int) -> Dict[int, Dict[str, Any]]:
    """
    RF-10: Recolecta y cachea en memoria RAM (TTL 120s) los presupuestos y transacciones
    de los 12 meses del año para el Resumen Anual, eliminando 24 llamadas HTTP redundantes en cada rerun.
    """
    annual_data: Dict[int, Dict[str, Any]] = {}
    for m in range(1, 13):
        mes_key = f"{year}-{m:02d}"
        presupuestos_m = get_presupuestos(mes_key)
        transacciones_m = get_transacciones(mes_key)
        annual_data[m] = {
            "presupuestos": presupuestos_m or [],
            "transacciones": transacciones_m or [],
        }
    return annual_data


def create_transaccion(fecha, subcategoria_id, cantidad, concepto):
    url = f"{API_URL}/transactions/"
    data = {
        "date": fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
        "subcategory_id": subcategoria_id,
        "amount": cantidad,
        "description": concepto,
    }
    try:
        response = _session.post(url, json=data, timeout=10)
        if response.status_code == 200:
            clear_annual_cache()
            res = response.json()
            if "date" in res and "fecha" not in res:
                res["fecha"] = res["date"]
            if "amount" in res and "cantidad" not in res:
                res["cantidad"] = res["amount"]
            if "subcategory_id" in res and "subcategoria_id" not in res:
                res["subcategoria_id"] = res["subcategory_id"]
            if "description" in res and "concepto" not in res:
                res["concepto"] = res["description"]
            return res
        logger.warning("Error al crear transacción (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al crear transacción en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_transaccion(): %s", e)
    return None


def delete_transaction(transaction_id: int) -> bool:
    """
    Elimina una transacción por su identificador en el backend.
    Registra cualquier fallo de red o error HTTP en el logger (Principio 13).
    """
    url = f"{API_URL}/transactions/{transaction_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            clear_annual_cache()
            logger.info("Transacción %s eliminada exitosamente en el backend", transaction_id)
            return True
        logger.error(
            "Error al eliminar transacción %s en %s (HTTP %s): %s",
            transaction_id,
            url,
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al eliminar transacción en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_transaction(%s): %s", transaction_id, e)
    return False


delete_transaccion = delete_transaction


def save_presupuestos_bulk(presupuestos_list):
    url = f"{API_URL}/budgets/bulk"
    payload = []
    for p in presupuestos_list:
        m = p.get("month") or p.get("mes")
        s = p.get("subcategory_id") if p.get("subcategory_id") is not None else p.get("subcategoria_id")
        a = p.get("amount") if p.get("amount") is not None else p.get("cantidad", 0.0)
        payload.append({"month": m, "subcategory_id": s, "amount": a})
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            clear_annual_cache()
            res = response.json()
            if isinstance(res, list):
                for p in res:
                    if "month" in p and "mes" not in p:
                        p["mes"] = p["month"]
                    if "amount" in p and "cantidad" not in p:
                        p["cantidad"] = p["amount"]
                    if "subcategory_id" in p and "subcategoria_id" not in p:
                        p["subcategoria_id"] = p["subcategory_id"]
            return res
        logger.warning("Error al guardar presupuestos en bloque (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al guardar presupuestos en bloque en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en save_presupuestos_bulk(): %s", e)
    return None


def get_safety_status(mes=None):
    url = f"{API_URL}/advisor/safety-status"
    params = {}
    if mes:
        params["mes"] = mes
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            try:
                get_macro_indicators.clear()
                get_market_news.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Respuesta no exitosa al consultar safety-status (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar safety-status en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_safety_status(): %s", e)
    return None


def update_emergency_fund_config(target_months=None, current_balance=None, mes=None):
    url = f"{API_URL}/advisor/emergency-fund/config"
    params = {}
    if mes:
        params["mes"] = mes
    data = {}
    if target_months is not None:
        data["target_months"] = target_months
    if current_balance is not None:
        data["current_balance"] = current_balance
    try:
        response = _session.post(url, params=params, json=data, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Error al actualizar configuración del fondo de emergencia (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al actualizar fondo de emergencia en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_emergency_fund_config(): %s", e)
    return None


@st.cache_data(ttl=300, show_spinner=False)
def get_macro_indicators():
    """Obtiene los indicadores macroeconómicos y deuda soberana desde el backend."""
    url = f"{API_URL}/market/macro-indicators"
    try:
        response = _session.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al obtener indicadores macro (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al obtener macro-indicators en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_macro_indicators(): %s", e)
    return None


@st.cache_data(ttl=300, show_spinner=False)
def get_market_news(limit=15):
    """Obtiene las noticias financieras depuradas con análisis de IA desde el backend."""
    url = f"{API_URL}/market/news"
    try:
        response = _session.get(url, params={"limit": limit}, timeout=35)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al obtener noticias de mercado (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al obtener noticias en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_market_news(): %s", e)
    return None


def refresh_market_radar():
    """Fuerza la invalidación y recarga manual del Radar de Mercado y Noticias."""
    url = f"{API_URL}/market/refresh"
    try:
        response = _session.post(url, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al refrescar el radar de mercado (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al refrescar el radar en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en refresh_market_radar(): %s", e)
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_screener_universes():
    """Obtiene la lista de universos predefinidos para el screener."""
    url = f"{API_URL}/screener/universes"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar universos de screener (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar universos en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_screener_universes(): %s", e)
    return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_screener_universe(
    universe_id: str,
    preset=None,
    max_pe=None,
    min_dividend_yield=None,
    min_roe=None,
    max_debt_to_equity=None,
    max_expense_ratio=None,
    search_query=None,
):
    """Consulta los activos de un universo aplicando filtros cuantitativos y de preset."""
    url = f"{API_URL}/screener/universe/{universe_id}"
    params = {}
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

    try:
        response = _session.get(url, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar universo '%s' (%s): %s", universe_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar screener universo '%s' en %s: %s", universe_id, url, e)
    except Exception as e:
        logger.error("Error inesperado en get_screener_universe('%s'): %s", universe_id, e)
    return None


def get_screener_custom(tickers, filter_params=None):
    """Consulta y filtra una lista personalizada de tickers (hasta 50)."""
    url = f"{API_URL}/screener/custom"
    payload = {"tickers": tickers, "filter_params": filter_params}
    try:
        response = _session.post(url, json=payload, timeout=35)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar tickers custom (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar tickers custom en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_screener_custom(): %s", e)
    return None


def refresh_screener_universe(universe_id: str):
    """Fuerza la invalidación de la caché en SQLite y descarga datos frescos de Yahoo Finance."""
    url = f"{API_URL}/screener/refresh/{universe_id}"
    try:
        response = _session.post(url, timeout=60)
        if response.status_code == 200:
            try:
                get_screener_universe.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Respuesta no exitosa al refrescar universo '%s' (%s): %s", universe_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al refrescar screener universo '%s' en %s: %s", universe_id, url, e)
    except Exception as e:
        logger.error("Error inesperado en refresh_screener_universe('%s'): %s", universe_id, e)
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_deepdive_analysis(ticker: str):
    """Consulta el diagnóstico contable en profundidad (Deep Dive) con caché SQLite de 24 horas."""
    clean_ticker = ticker.strip().upper()
    url = f"{API_URL}/deepdive/{clean_ticker}"
    try:
        response = _session.get(url, timeout=40)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar Deep Dive para '%s' (%s): %s", clean_ticker, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar Deep Dive para '%s' en %s: %s", clean_ticker, url, e)
    except Exception as e:
        logger.error("Error inesperado en get_deepdive_analysis('%s'): %s", clean_ticker, e)
    return None


def refresh_deepdive_analysis(ticker: str):
    """Fuerza la invalidación de caché y regenera el análisis Deep Dive para un ticker."""
    clean_ticker = ticker.strip().upper()
    url = f"{API_URL}/deepdive/refresh/{clean_ticker}"
    try:
        response = _session.post(url, timeout=60)
        if response.status_code == 200:
            try:
                get_deepdive_analysis.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Respuesta no exitosa al refrescar Deep Dive para '%s' (%s): %s", clean_ticker, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al refrescar Deep Dive para '%s' en %s: %s", clean_ticker, url, e)
    except Exception as e:
        logger.error("Error inesperado en refresh_deepdive_analysis('%s'): %s", clean_ticker, e)
    return None


def get_watchlist():
    """Recupera la lista de activos en seguimiento guardados en la base de datos local SQLite."""
    url = f"{API_URL}/watchlist"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar la watchlist (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar la watchlist en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_watchlist(): %s", e)
    return []


def add_to_watchlist(item: dict):
    """Añade o actualiza un activo con sus notas en la lista de seguimiento local."""
    url = f"{API_URL}/watchlist"
    try:
        response = _session.post(url, json=item, timeout=10)
        if response.status_code in (200, 201):
            return response.json()
        logger.warning("Respuesta no exitosa al guardar en watchlist (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al guardar en watchlist en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en add_to_watchlist(): %s", e)
    return None


def remove_from_watchlist(ticker: str) -> bool:
    """Elimina un activo de la lista de seguimiento local."""
    clean_ticker = ticker.strip().upper()
    url = f"{API_URL}/watchlist/{clean_ticker}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Respuesta no exitosa al eliminar de watchlist '%s' (%s): %s", clean_ticker, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al eliminar de watchlist '%s' en %s: %s", clean_ticker, url, e)
    except Exception as e:
        logger.error("Error inesperado en remove_from_watchlist('%s'): %s", clean_ticker, e)
    return False


# ==========================================
# 7. COPILOTO PATRIMONIAL (SPEC 004)
# ==========================================

def get_copilot_sessions():
    """Obtiene el listado de sesiones históricas del Copiloto Patrimonial."""
    url = f"{API_URL}/copilot/sessions"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al listar sesiones del copiloto (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar sesiones del copiloto en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_copilot_sessions(): %s", e)
    return []


def create_copilot_session(title=None):
    """Crea una nueva sesión de conversación para el Copiloto."""
    url = f"{API_URL}/copilot/sessions"
    payload = {"title": title} if title else {}
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            return response.json()
        logger.warning("Respuesta no exitosa al crear sesión del copiloto (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al crear sesión del copiloto en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_copilot_session(): %s", e)
    return None


def get_copilot_session_detail(session_id: int):
    """Obtiene el detalle de una sesión con todos sus mensajes e historial."""
    url = f"{API_URL}/copilot/sessions/{session_id}"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar sesión %d (%s): %s", session_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar sesión %d en %s: %s", session_id, url, e)
    except Exception as e:
        logger.error("Error inesperado en get_copilot_session_detail(%d): %s", session_id, e)
    return None


def delete_copilot_session(session_id: int) -> bool:
    """Elimina una sesión de conversación y todos sus mensajes."""
    url = f"{API_URL}/copilot/sessions/{session_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Respuesta no exitosa al eliminar sesión %d (%s): %s", session_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al eliminar sesión %d en %s: %s", session_id, url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_copilot_session(%d): %s", session_id, e)
    return False


def send_copilot_chat(message: str, session_id=None):
    """
    Envía un mensaje al Copiloto Patrimonial ejecutando el turno con Function Calling.
    Timeout extendido a 60s para acomodar llamadas a LLM y herramientas.
    """
    url = f"{API_URL}/copilot/chat"
    payload = {"message": message, "session_id": session_id}
    try:
        response = _session.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al enviar chat al copiloto (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al enviar chat al copiloto en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en send_copilot_chat(): %s", e)
    return None


# ==========================================
# 8. COMITÉ ASESOR MULTIAGENTE (SPEC 005)
# ==========================================

def run_investment_committee(ticker=None, month=None, initial_notes=None):
    """
    Convoca la deliberación del Comité Asesor de Inversión Multiagente (LangGraph).
    Retorna el dictamen unificado, estado de salvaguarda, doble tesis y bitácora de los agentes.
    Timeout extendido a 90s para permitir la ejecución de los agentes y llamadas LLM.
    """
    url = f"{API_URL}/committee/analyze"
    payload = {
        "ticker": ticker.strip().upper() if ticker and isinstance(ticker, str) and ticker.strip() else None,
        "month": month.strip() if month and isinstance(month, str) and month.strip() else None,
        "initial_notes": initial_notes.strip() if initial_notes and isinstance(initial_notes, str) and initial_notes.strip() else None,
    }
    try:
        response = _session.post(url, json=payload, timeout=90)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al convocar Comité Asesor (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al convocar Comité Asesor en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en run_investment_committee(): %s", e)
    return None


# ==========================================
# 9. PAUTAS DETERMINISTAS DE GESTIÓN (SPEC 008)
# ==========================================

def get_monthly_guidelines(
    month_key: str,
    month_name: str,
    real_income: float,
    budget_income: float,
    real_needs: float,
    real_wants: float,
    real_savings: float,
    safety_status=None,
):
    """
    Solicita al backend la evaluación determinista de pautas y compensación para un mes.
    Retorna el informe tipado serializado a diccionario, o None si ocurre un fallo.
    """
    url = f"{API_URL}/guidelines/monthly"
    payload = {
        "month_key": month_key,
        "month_name": month_name,
        "real_income": float(real_income or 0.0),
        "budget_income": float(budget_income or 0.0),
        "real_needs": float(real_needs or 0.0),
        "real_wants": float(real_wants or 0.0),
        "real_savings": float(real_savings or 0.0),
        "safety_status": safety_status,
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al consultar pautas mensuales (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar pautas mensuales en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_monthly_guidelines(): %s", e)
    return None


def get_annual_guidelines(metrics):
    """
    Solicita al backend el diagnóstico estructural y pautas anuales consolidadas.
    Retorna el informe tipado serializado a diccionario, o None si ocurre un fallo.
    """
    url = f"{API_URL}/guidelines/annual"
    payload = {"metrics": metrics}
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al consultar pautas anuales (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar pautas anuales en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_annual_guidelines(): %s", e)
    return None


def apply_guideline_strategy(payload: dict):
    """
    Ejecuta una estrategia de asignación de capital de forma atómica en el backend.
    Crea transacciones de ahorro e incrementa presupuestos de deseos según corresponda.
    """
    url = f"{API_URL}/guidelines/apply-strategy"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al aplicar estrategia (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al aplicar estrategia en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en apply_guideline_strategy(): %s", e)
    return None


def sweep_month_surplus(
    month_key: str,
    amount: float,
    target_subcategory_id: Optional[int] = None,
    mode: str = "DEFAULT_SAVINGS",
):
    """
    Ejecuta el barrido de fin de mes en el backend para liquidar el excedente restante hacia el ahorro
    o completando proporcionalmente la estrategia activa del mes.
    """
    url = f"{API_URL}/guidelines/sweep"
    payload = {
        "month_key": month_key,
        "amount": float(amount or 0.0),
        "target_subcategory_id": target_subcategory_id,
        "mode": mode,
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al ejecutar barrido de fin de mes (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al ejecutar barrido en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en sweep_month_surplus(): %s", e)
    return None


def compensate_guideline_deficit(
    month_key: str,
    action_type: str,
    amount: float = 0.0,
    target_subcategory_id: Optional[int] = None,
    target_subcategory_ids: Optional[List[int]] = None,
):
    """
    Ejecuta una acción de compensación o contención presupuestaria de forma atómica en el backend:
    - Ajuste compensatorio de sobregasto en Deseos al mes siguiente (WANTS_COMPENSATION_NEXT_MONTH).
    - Amortiguación de déficit de Necesidades desde Deseos del mes (NEEDS_ABSORPTION_CURRENT_WANTS).
    - Congelación de partidas de Deseos a 0.0 € ante caída de ingresos (FREEZE_WANTS).
    """
    url = f"{API_URL}/guidelines/compensate-deficit"
    payload = {
        "month_key": month_key,
        "action_type": action_type,
        "amount": float(amount or 0.0),
        "target_subcategory_id": target_subcategory_id,
        "target_subcategory_ids": target_subcategory_ids,
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al ejecutar compensación de déficit (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al ejecutar compensación de déficit en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en compensate_guideline_deficit(): %s", e)
    return None


def revert_guideline_strategy(month_key: str, scenario_type: str = "NEEDS_SURPLUS"):
    """
    Revierte atómicamente una estrategia de asignación aplicada en el mes indicado.
    Elimina las transacciones generadas, revierte el saldo aportado al fondo de emergencia
    y restablece el estado para que el excedente vuelva a estar disponible.
    """
    url = f"{API_URL}/guidelines/revert-strategy"
    payload = {
        "month_key": month_key,
        "scenario_type": scenario_type,
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Respuesta no exitosa al revertir estrategia (%s): %s",
            response.status_code,
            response.text,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al revertir estrategia en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en revert_guideline_strategy(): %s", e)
    return None


# ==========================================
# ESPACIO CONJUNTO / HOGAR (SPEC 010)
# ==========================================

def get_joint_status() -> Dict[str, Any]:
    """Consulta si la cuenta conjunta está configurada o si nos encontramos en Estado Cero."""
    url = f"{API_URL}/joint/status"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa en get_joint_status (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de conexión al consultar /joint/status en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_status(): %s", e)
    return {"is_configured": False}


def setup_joint_account(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta el onboarding inicial para crear la cuenta conjunta."""
    url = f"{API_URL}/joint/setup"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_joint_cache()
            clear_annual_cache()
            return response.json()
        logger.warning("Fallo en setup_joint_account (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en setup_joint_account en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en setup_joint_account(): %s", e)
    return None


def get_joint_account() -> Optional[Dict[str, Any]]:
    """Obtiene la configuración activa de la cuenta conjunta."""
    url = f"{API_URL}/joint/account"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_account (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_account en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_account(): %s", e)
    return None


def update_joint_account(payload: dict) -> Optional[Dict[str, Any]]:
    """Actualiza los parámetros del hogar."""
    url = f"{API_URL}/joint/account"
    try:
        response = _session.put(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en update_joint_account (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en update_joint_account en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_joint_account(): %s", e)
    return None


@st.cache_data(ttl=600, show_spinner=False)
def get_joint_categories() -> List[Dict[str, Any]]:
    """Obtiene el catálogo de categorías del hogar."""
    url = f"{API_URL}/joint/categories"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_categories (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_categories en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_categories(): %s", e)
    return []


@st.cache_data(ttl=600, show_spinner=False)
def get_joint_subcategories(category_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Obtiene las subcategorías de necesidades comunes."""
    url = f"{API_URL}/joint/subcategories"
    params = {}
    if category_id:
        params["category_id"] = category_id
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_subcategories (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_subcategories en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_subcategories(): %s", e)
    return []

def create_joint_subcategory(name: str, joint_category_id: int, monthly_budget: float = 0.0) -> Optional[Dict[str, Any]]:
    """
    Crea una nueva subcategoría de necesidades comunes del hogar y emite evento delta P2P.
    Invalida reactivamente la caché de cuenta conjunta.
    """
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        logger.warning("Intento de crear subcategoría del hogar con nombre vacío")
        return None

    url = f"{API_URL}/joint/subcategories"
    payload = {
        "name": cleaned_name,
        "joint_category_id": joint_category_id,
        "monthly_budget": float(monthly_budget or 0.0),
    }
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_joint_cache()
            logger.info("Subcategoría del hogar '%s' creada con éxito", cleaned_name)
            return response.json()
        logger.warning("Fallo al crear subcategoría del hogar (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en create_joint_subcategory en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_joint_subcategory(): %s", e)
    return None


def update_joint_subcategory(
    subcategory_id: int,
    name: Optional[str] = None,
    monthly_budget: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Actualiza el nombre o presupuesto mensual de una subcategoría común del hogar y propaga el cambio.
    Invalida reactivamente la caché de cuenta conjunta.
    """
    url = f"{API_URL}/joint/subcategories/{subcategory_id}"
    payload: Dict[str, Any] = {}
    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name:
            logger.warning("Intento de actualizar subcategoría del hogar %s con nombre vacío", subcategory_id)
            return None
        payload["name"] = cleaned_name
    if monthly_budget is not None:
        payload["monthly_budget"] = float(monthly_budget)

    if not payload:
        logger.warning("update_joint_subcategory invocado sin campos a actualizar")
        return None

    try:
        response = _session.put(url, json=payload, timeout=10)
        if response.status_code == 200:
            clear_joint_cache()
            logger.info("Subcategoría del hogar %s actualizada con éxito: %s", subcategory_id, payload)
            return response.json()
        logger.warning("Fallo al actualizar subcategoría del hogar %s (%s): %s", subcategory_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en update_joint_subcategory en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_joint_subcategory(): %s", e)
    return None


def get_joint_subcategory_usage(subcategory_id: int) -> Optional[Dict[str, Any]]:
    """
    Consulta la auditoría contable de uso de una subcategoría común del hogar (transacciones vinculadas).
    """
    url = f"{API_URL}/joint/subcategories/{subcategory_id}/usage"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al consultar uso de subcategoría del hogar %s (%s): %s", subcategory_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_subcategory_usage en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_subcategory_usage(): %s", e)
    return None


def delete_joint_subcategory(subcategory_id: int) -> Tuple[bool, str]:
    """
    Elimina físicamente una subcategoría del hogar y emite evento tombstone si no tiene transacciones asociadas.
    Retorna (True, mensaje) si se eliminó, o (False, detalle_error) si está bloqueada o falla.
    """
    url = f"{API_URL}/joint/subcategories/{subcategory_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            clear_joint_cache()
            logger.info("Subcategoría del hogar %s eliminada con éxito", subcategory_id)
            return True, "Subcategoría conjunta eliminada con éxito."
        elif response.status_code == 409:
            err_msg = response.json().get("detail", "La subcategoría contiene transacciones del hogar y no puede eliminarse.")
            logger.warning("Borrado bloqueado por dependencias en subcategoría del hogar %s: %s", subcategory_id, err_msg)
            return False, err_msg
        else:
            err_msg = response.json().get("detail", response.text) if response.headers.get("content-type") == "application/json" else response.text
            logger.warning("Error al eliminar subcategoría del hogar %s (%s): %s", subcategory_id, response.status_code, err_msg)
            return False, f"Error del servidor ({response.status_code}): {err_msg}"
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_joint_subcategory en %s: %s", url, e)
        return False, f"Error de red o conexión: {e}"
    except Exception as e:
        logger.error("Error inesperado en delete_joint_subcategory(): %s", e)
        return False, f"Error inesperado: {e}"



@st.cache_data(ttl=60, show_spinner=False)
def get_joint_sinking_funds(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene las metas de ahorro / huchas de amortización del hogar."""
    url = f"{API_URL}/joint/sinking-funds"
    params = {}
    if status:
        params["status"] = status
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_sinking_funds (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_sinking_funds en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_sinking_funds(): %s", e)
    return []


def create_joint_sinking_fund(payload: dict) -> Optional[Dict[str, Any]]:
    """Crea una nueva hucha de amortización."""
    url = f"{API_URL}/joint/sinking-funds"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            try:
                get_joint_sinking_funds.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Fallo en create_joint_sinking_fund (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en create_joint_sinking_fund en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_joint_sinking_fund(): %s", e)
    return None


def update_joint_sinking_fund(fund_id: int, payload: dict) -> Optional[Dict[str, Any]]:
    """Edita una hucha de amortización existente."""
    url = f"{API_URL}/joint/sinking-funds/{fund_id}"
    try:
        response = _session.put(url, json=payload, timeout=10)
        if response.status_code == 200:
            try:
                get_joint_sinking_funds.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Fallo en update_joint_sinking_fund (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en update_joint_sinking_fund en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_joint_sinking_fund(): %s", e)
    return None


def delete_joint_sinking_fund(
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = None,
    action_on_balance: Optional[str] = None,
    refund_personal_entry: bool = True,
) -> bool:
    """Elimina una hucha de amortización, definiendo el destino de su saldo remanente si corresponde."""
    url = f"{API_URL}/joint/sinking-funds/{fund_id}"
    params: Dict[str, Any] = {}
    if reallocate_to_fund_id:
        params["reallocate_to_fund_id"] = reallocate_to_fund_id
    if action_on_balance:
        params["action_on_balance"] = action_on_balance
    params["refund_personal_entry"] = str(refund_personal_entry).lower()
    try:
        response = _session.delete(url, params=params, timeout=10)
        if response.status_code == 200:
            try:
                get_joint_sinking_funds.clear()
            except Exception:
                pass
            clear_joint_cache()
            clear_annual_cache()
            return True
        logger.warning("Fallo en delete_joint_sinking_fund (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_joint_sinking_fund en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_joint_sinking_fund(): %s", e)
    return False


def transfer_joint_sinking_fund(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta un rebalanceo o traspaso directo de saldo entre huchas del hogar."""
    url = f"{API_URL}/joint/sinking-funds/transfer"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            try:
                get_joint_sinking_funds.clear()
            except Exception:
                pass
            return response.json()
        logger.warning("Fallo en transfer_joint_sinking_fund (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en transfer_joint_sinking_fund en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en transfer_joint_sinking_fund(): %s", e)
    return None


def get_joint_sinking_fund_transfers(limit: int = 100) -> List[Dict[str, Any]]:
    """Obtiene el historial de traspasos y rebalanceos entre huchas de amortización."""
    url = f"{API_URL}/joint/sinking-funds/transfers"
    try:
        response = _session.get(url, params={"limit": limit}, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_sinking_fund_transfers (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_sinking_fund_transfers en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_sinking_fund_transfers(): %s", e)
    return []


def get_joint_transactions(year: Optional[int] = None, month: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene los gastos del hogar registrados."""
    url = f"{API_URL}/joint/transactions"
    params = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_transactions (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_transactions en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_transactions(): %s", e)
    return []


def search_joint_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    query: Optional[str] = None,
    joint_subcategory_id: Optional[int] = None,
    paid_by: Optional[str] = None,
    settlement_status: Optional[str] = None,
    is_sinking_fund: Optional[bool] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Busca y filtra transacciones del hogar por criterios múltiples."""
    url = f"{API_URL}/joint/transactions/search"
    params: Dict[str, Any] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if query:
        params["query"] = query
    if joint_subcategory_id is not None:
        params["joint_subcategory_id"] = joint_subcategory_id
    if paid_by and paid_by != "ALL":
        params["paid_by"] = paid_by
    if settlement_status and settlement_status != "ALL":
        params["settlement_status"] = settlement_status
    if is_sinking_fund is not None:
        params["is_sinking_fund"] = is_sinking_fund
    if min_amount is not None:
        params["min_amount"] = min_amount
    if max_amount is not None:
        params["max_amount"] = max_amount

    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en search_joint_transactions (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en search_joint_transactions en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en search_joint_transactions(): %s", e)
    return []


def create_joint_transaction(payload: dict) -> Optional[Dict[str, Any]]:
    """Registra un nuevo gasto común del hogar."""
    url = f"{API_URL}/joint/transactions"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_joint_cache()
            return response.json()
        logger.warning("Fallo en create_joint_transaction (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en create_joint_transaction en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_joint_transaction(): %s", e)
    return None


def delete_joint_transaction(tx_id: int) -> bool:
    """Elimina una transacción conjunta."""
    url = f"{API_URL}/joint/transactions/{tx_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            clear_joint_cache()
            return True
        logger.warning("Fallo en delete_joint_transaction (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_joint_transaction en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_joint_transaction(): %s", e)
    return False


def get_joint_settlement_summary() -> Optional[Dict[str, Any]]:
    """Obtiene el resumen consolidado de liquidación y reembolsos de gastos adelantados."""
    url = f"{API_URL}/joint/settlement/summary"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_settlement_summary (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_settlement_summary en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_settlement_summary(): %s", e)
    return None


def settle_joint_transaction(tx_id: int) -> bool:
    """Marca una transacción conjunta pendiente como liquidada/reembolsada."""
    url = f"{API_URL}/joint/settlement/settle-transaction/{tx_id}"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Fallo en settle_joint_transaction (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en settle_joint_transaction en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en settle_joint_transaction(): %s", e)
    return False


def settle_all_joint_transactions() -> bool:
    """Marca todas las transacciones conjuntas pendientes como liquidadas/reembolsadas."""
    url = f"{API_URL}/joint/settlement/settle-all"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Fallo en settle_all_joint_transactions (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en settle_all_joint_transactions en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en settle_all_joint_transactions(): %s", e)
    return False


def get_joint_contributions(year: Optional[int] = None, month: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene el historial de aportaciones a la cuenta común."""
    url = f"{API_URL}/joint/contributions"
    params = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_contributions (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_contributions en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_contributions(): %s", e)
    return []


def get_joint_contribution_calculation() -> Optional[Dict[str, Any]]:
    """Consulta el cálculo dinámico de las cuotas mensuales del hogar (Mejora 1)."""
    url = f"{API_URL}/joint/contributions/calculation"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_contribution_calculation (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_contribution_calculation en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_contribution_calculation(): %s", e)
    return None


def asentar_aportacion_asistida(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta el asiento asistido en 1 clic de inicio de mes."""
    url = f"{API_URL}/joint/contributions/asentar-asistida"
    try:
        response = _session.post(url, json=payload, timeout=10)
        if response.status_code in (200, 201):
            clear_joint_cache()
            return response.json()
        logger.warning("Fallo en asentar_aportacion_asistida (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en asentar_aportacion_asistida en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en asentar_aportacion_asistida(): %s", e)
    return None


def delete_joint_contribution(contribution_id: int) -> bool:
    """Elimina físicamente una aportación a la cuenta común."""
    url = f"{API_URL}/joint/contributions/{contribution_id}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            clear_joint_cache()
            return True
        logger.warning("Fallo en delete_joint_contribution (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_joint_contribution en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_joint_contribution(): %s", e)
    return False


def get_joint_health() -> Optional[Dict[str, Any]]:
    """Consulta la Tasa de Esfuerzo Familiar y el semáforo determinista."""
    url = f"{API_URL}/joint/health"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_health (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_health en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_health(): %s", e)
    return None


def get_joint_annual_summary(year: int) -> Optional[Dict[str, Any]]:
    """Consulta el Resumen Anual consolidado del hogar (sin comparativas A vs B)."""
    url = f"{API_URL}/joint/annual-summary"
    params = {"year": year}
    try:
        response = _session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_annual_summary (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_annual_summary en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_annual_summary(): %s", e)
    return None


def trigger_process_inbox() -> Dict[str, Any]:
    """Dispara el procesamiento de los deltas de Syncthing en sync/inbox/."""
    url = f"{API_URL}/joint/sync/process-inbox"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en trigger_process_inbox (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en trigger_process_inbox en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en trigger_process_inbox(): %s", e)
    return {"status": "error"}


def get_sync_status() -> Dict[str, Any]:
    """Obtiene el estado de sincronización y métricas de deltas pendientes."""
    url = f"{API_URL}/joint/sync/status"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_sync_status (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_sync_status en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_sync_status(): %s", e)
    return {"is_synchronized": False, "outbox_pending_count": 0, "inbox_pending_count": 0}


def reset_joint_account() -> bool:
    """Purga la cuenta conjunta completa y vacía los buzones de sincronización (regreso a Estado Cero)."""
    url = f"{API_URL}/joint/reset"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code == 200:
            clear_joint_cache()
            clear_annual_cache()
            return True
        logger.warning("Fallo en reset_joint_account (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en reset_joint_account en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en reset_joint_account(): %s", e)
    return False


def get_joint_invitation() -> Dict[str, Any]:
    """Comprueba si hay una invitación de hogar pendiente enviada por la pareja."""
    url = f"{API_URL}/joint/invitation"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_invitation (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_invitation en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_invitation(): %s", e)
    return {"has_invitation": False, "invitation": None}


def accept_joint_invitation() -> Optional[Dict[str, Any]]:
    """Acepta la invitación de hogar detectada en 1 clic (Opción A)."""
    url = f"{API_URL}/joint/accept-invitation"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code in (200, 201):
            clear_joint_cache()
            clear_annual_cache()
            return response.json()
        logger.warning("Fallo en accept_joint_invitation (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en accept_joint_invitation en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en accept_joint_invitation(): %s", e)
    return None


def resend_joint_invitation() -> bool:

    """Solicita al backend que vuelva a emitir la invitación para la pareja en outbox/."""
    url = f"{API_URL}/joint/resend-invitation"
    try:
        response = _session.post(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Fallo en resend_joint_invitation (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en resend_joint_invitation en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en resend_joint_invitation(): %s", e)
    return False


@st.cache_data(ttl=300, show_spinner=False)
def export_joint_excel() -> Optional[bytes]:
    """Descarga el archivo Excel estructurado (.xlsx) con los datos consolidados del hogar."""
    url = f"{API_URL}/joint/export/excel"
    try:
        response = _session.get(url, timeout=15)
        if response.status_code == 200:
            return response.content
        logger.warning("Fallo en export_joint_excel (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en export_joint_excel en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en export_joint_excel(): %s", e)
    return None


def get_joint_sync_events_detail(max_processed: int = 30) -> Optional[Dict[str, Any]]:
    """Consulta la inspección detallada de deltas en outbox, inbox, processed y error."""
    url = f"{API_URL}/joint/sync/events"
    try:
        response = _session.get(url, params={"max_processed": max_processed}, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_joint_sync_events_detail (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_joint_sync_events_detail en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_joint_sync_events_detail(): %s", e)
    return None


def retry_joint_sync_errors() -> Optional[Dict[str, Any]]:
    """Solicita al backend mover los eventos de sync/error/ a sync/inbox/ y reprocesarlos."""
    url = f"{API_URL}/joint/sync/retry-errors"
    try:
        response = _session.post(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en retry_joint_sync_errors (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en retry_joint_sync_errors en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en retry_joint_sync_errors(): %s", e)
    return None


def clear_joint_sync_errors() -> Optional[Dict[str, Any]]:
    """Solicita al backend purgar todos los eventos delta fallidos de sync/error/."""
    url = f"{API_URL}/joint/sync/clear-errors"
    try:
        response = _session.post(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en clear_joint_sync_errors (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en clear_joint_sync_errors en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en clear_joint_sync_errors(): %s", e)
    return None


def get_pending_remote_deletion() -> Optional[Dict[str, Any]]:
    """Consulta si hay una solicitud de borrado remoto pendiente emitida por la pareja."""
    url = f"{API_URL}/joint/remote-deletion/pending"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("pending"):
                return res_data.get("data")
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_pending_remote_deletion en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_pending_remote_deletion(): %s", e)
    return None


def accept_remote_deletion() -> bool:
    """Acepta la solicitud de borrado remoto del hogar y purga las cachés locales."""
    url = f"{API_URL}/joint/remote-deletion/accept"
    try:
        response = _session.post(url, timeout=15)
        if response.status_code == 200:
            clear_joint_cache()
            clear_annual_cache()
            return True
        logger.warning("Fallo en accept_remote_deletion (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en accept_remote_deletion en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en accept_remote_deletion(): %s", e)
    return False


def reject_remote_deletion() -> bool:
    """Rechaza la solicitud de borrado remoto del hogar, conservando los datos locales."""
    url = f"{API_URL}/joint/remote-deletion/reject"
    try:
        response = _session.post(url, timeout=15)
        if response.status_code == 200:
            return True
        logger.warning("Fallo en reject_remote_deletion (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en reject_remote_deletion en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en reject_remote_deletion(): %s", e)
    return False




# ==============================================================================
# MÉTODOS DE COPIAS DE SEGURIDAD Y RESTAURACIÓN (SPEC 011 - BACKUP & RESTORE)
# ==============================================================================

def get_database_health() -> Optional[Dict[str, Any]]:
    """Consulta el diagnóstico de salud, integridad y advertencia de respaldos."""
    url = f"{API_URL}/backup/health"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_database_health (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de conexión al consultar salud de base de datos en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_database_health(): %s", e)
    return None


def create_backup(custom_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Genera una copia de seguridad caliente en el servidor."""
    url = f"{API_URL}/backup/create"
    params = {"custom_name": custom_name} if custom_name else {}
    try:
        response = _session.post(url, params=params, timeout=30)
        if response.status_code in (200, 201):
            return response.json()
        logger.warning("Fallo en create_backup (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de conexión al crear backup en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_backup(): %s", e)
    return None


def download_backup_bytes() -> Optional[tuple[bytes, str]]:
    """Descarga los bytes binarios de la base de datos consistente y retorna (bytes, filename)."""
    url = f"{API_URL}/backup/download"
    try:
        response = _session.get(url, timeout=45)
        if response.status_code == 200:
            # Obtener nombre del header Content-Disposition si existe
            filename = "finanzas_backup.db"
            cd = response.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip('"')
            return response.content, filename
        logger.warning("Fallo al descargar copia de seguridad (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al descargar backup en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en download_backup_bytes(): %s", e)
    return None


def list_backups() -> Dict[str, Any]:
    """Obtiene el catálogo de copias de seguridad locales disponibles."""
    url = f"{API_URL}/backup/list"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en list_backups (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en list_backups en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en list_backups(): %s", e)
    return {"backups": [], "total_count": 0, "latest_safety_snapshot": None}


def validate_backup_upload(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """Inspecciona y valida un archivo de copia subido sin aplicarlo a la base activa."""
    url = f"{API_URL}/backup/validate"
    files = {"file": (filename, file_bytes, "application/x-sqlite3")}
    try:
        response = _session.post(url, files=files, timeout=30)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en validate_backup_upload (%s): %s", response.status_code, response.text)
        return {"is_valid": False, "error_message": response.json().get("detail", response.text)}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en validate_backup_upload en %s: %s", url, e)
        return {"is_valid": False, "error_message": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error("Error inesperado en validate_backup_upload(): %s", e)
        return {"is_valid": False, "error_message": f"Error inesperado: {str(e)}"}


def restore_backup_upload(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """Sube y aplica un archivo .db de restauración validando previamente su integridad."""
    url = f"{API_URL}/backup/restore/upload"
    files = {"file": (filename, file_bytes, "application/x-sqlite3")}
    try:
        response = _session.post(url, files=files, timeout=45)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en restore_backup_upload (%s): %s", response.status_code, response.text)
        return {"success": False, "message": response.json().get("detail", response.text)}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en restore_backup_upload en %s: %s", url, e)
        return {"success": False, "message": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error("Error inesperado en restore_backup_upload(): %s", e)
        return {"success": False, "message": f"Error inesperado: {str(e)}"}


def restore_backup_local(filename: str) -> Optional[Dict[str, Any]]:
    """Restaura una instantánea del catálogo local en backups/."""
    url = f"{API_URL}/backup/restore/local/{filename}"
    try:
        response = _session.post(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en restore_backup_local (%s): %s", response.status_code, response.text)
        return {"success": False, "message": response.json().get("detail", response.text)}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en restore_backup_local en %s: %s", url, e)
        return {"success": False, "message": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error("Error inesperado en restore_backup_local(): %s", e)
        return {"success": False, "message": f"Error inesperado: {str(e)}"}


def rollback_restore() -> Optional[Dict[str, Any]]:
    """Deshace en 1 clic la última restauración aplicando el snapshot previo de seguridad."""
    url = f"{API_URL}/backup/restore/rollback"
    try:
        response = _session.post(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en rollback_restore (%s): %s", response.status_code, response.text)
        return {"success": False, "message": response.json().get("detail", response.text)}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en rollback_restore en %s: %s", url, e)
        return {"success": False, "message": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error("Error inesperado en rollback_restore(): %s", e)
        return {"success": False, "message": f"Error inesperado: {str(e)}"}


def delete_backup_local(filename: str) -> bool:
    """Elimina permanentemente una copia de seguridad local del servidor."""
    url = f"{API_URL}/backup/local/{filename}"
    try:
        response = _session.delete(url, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning("Fallo en delete_backup_local (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en delete_backup_local en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en delete_backup_local(): %s", e)
    return False


def get_backup_schedule() -> Optional[Dict[str, Any]]:
    """Consulta la configuración de programación de copias automáticas."""
    url = f"{API_URL}/backup/schedule"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en get_backup_schedule (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en get_backup_schedule en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_backup_schedule(): %s", e)
    return None


def update_backup_schedule(enabled: bool, frequency_days: int, keep_max_copies: int) -> Optional[Dict[str, Any]]:
    """Actualiza la programación de copias periódicas automáticas."""
    url = f"{API_URL}/backup/schedule"
    payload = {
        "enabled": enabled,
        "frequency_days": frequency_days,
        "keep_max_copies": keep_max_copies,
    }
    try:
        response = _session.put(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo en update_backup_schedule (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en update_backup_schedule en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_backup_schedule(): %s", e)
    return None












# ==============================================================================
# SECCIÓN: ACTUALIZADOR EN 1 CLIC (IN-APP OTA UPDATER)
# ==============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_app_version() -> Optional[Dict[str, Any]]:
    """Obtiene la versión del sistema instalada localmente, rama y disponibilidad de rollback."""
    url = f"{API_URL}/api/updater/version"
    try:
        response = _session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al obtener versión (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al consultar versión en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_app_version(): %s", e)
    return None


def check_for_updates(force: bool = False, branch: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Comprueba en GitHub API si existen nuevas versiones disponibles con soporte de caché."""
    url = f"{API_URL}/api/updater/check"
    params: Dict[str, Any] = {"force": force}
    if branch:
        params["branch"] = branch
    try:
        response = _session.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al comprobar actualizaciones (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al comprobar actualizaciones en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en check_for_updates(): %s", e)
    return None


def apply_system_update(branch: Optional[str] = None, remote_commit: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Ejecuta la actualización del sistema en staging, backups y reemplazo atómico."""
    url = f"{API_URL}/api/updater/apply"
    payload: Dict[str, Any] = {}
    if branch:
        payload["branch"] = branch
    if remote_commit:
        payload["remote_commit"] = remote_commit
    try:
        response = _session.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al aplicar actualización (%s): %s", response.status_code, response.text)
        try:
            return response.json()
        except Exception:
            return {"success": False, "message": f"Error del servidor ({response.status_code}): {response.text}"}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al aplicar actualización en %s: %s", url, e)
        return {"success": False, "message": f"Error de conexión con el servidor backend: {e}"}
    except Exception as e:
        logger.error("Error inesperado en apply_system_update(): %s", e)
        return {"success": False, "message": f"Error inesperado: {e}"}


def rollback_system_update() -> Optional[Dict[str, Any]]:
    """Restaura la versión previa de código y dependencias desde la instantánea comprimida."""
    url = f"{API_URL}/api/updater/rollback"
    try:
        response = _session.post(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        logger.warning("Fallo al revertir código (%s): %s", response.status_code, response.text)
        try:
            return response.json()
        except Exception:
            return {"success": False, "message": f"Error del servidor ({response.status_code}): {response.text}"}
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al revertir código en %s: %s", url, e)
        return {"success": False, "message": f"Error de conexión con el backend: {e}"}
    except Exception as e:
        logger.error("Error inesperado en rollback_system_update(): %s", e)
        return {"success": False, "message": f"Error inesperado: {e}"}


# ==============================================================================
# FUNCIONES DE GESTIÓN E INVALIDACIÓN DE CACHÉ DE FRONTEND (SPEC 014)
# ==============================================================================

def clear_categories_cache() -> None:
    """Invalida la caché de categorías y subcategorías."""
    try:
        get_categorias.clear()
        get_subcategorias.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché de categorías: %s", exc)


def clear_market_cache() -> None:
    """Invalida la caché de indicadores macro, noticias, screener y deepdive."""
    try:
        get_macro_indicators.clear()
        get_market_news.clear()
        get_screener_universe.clear()
        get_deepdive_analysis.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché de mercado: %s", exc)


def clear_annual_cache() -> None:
    """RF-10: Invalida la caché del resumen anual consolidado."""
    try:
        get_annual_summary_data.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché de resumen anual: %s", exc)


def clear_joint_cache() -> None:
    """Invalida la caché de entidades de cuenta conjunta (huchas, subcategorías y exportación Excel)."""
    try:
        get_joint_categories.clear()
        get_joint_subcategories.clear()
        get_joint_sinking_funds.clear()
        export_joint_excel.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché de cuenta conjunta: %s", exc)


def clear_all_frontend_cache() -> None:
    """Limpia la totalidad de la caché de datos de Streamlit."""
    try:
        st.cache_data.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché global de frontend: %s", exc)
