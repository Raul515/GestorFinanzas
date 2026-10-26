import logging
import os
import requests

logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


def get_categorias():
    """Obtiene el listado de categorías, normalizando claves para compatibilidad."""
    url = f"{API_URL}/categories/"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for c in raw:
                if "name" in c and "nombre" not in c:
                    c["nombre"] = c["name"]
                if "type" in c and "tipo" not in c:
                    c["tipo"] = c["type"]
            return raw
        logger.warning("Respuesta no exitosa al consultar categorías (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar categorías en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_categorias(): %s", e)
    return []


def get_subcategorias(categoria_id=None):
    """Obtiene subcategorías, normalizando claves para compatibilidad."""
    url = f"{API_URL}/categories/subcategories/"
    params = {}
    if categoria_id:
        params["category_id"] = categoria_id
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for s in raw:
                if "name" in s and "nombre" not in s:
                    s["nombre"] = s["name"]
            return raw
        logger.warning("Respuesta no exitosa al consultar subcategorías (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar subcategorías en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_subcategorias(): %s", e)
    return []


def get_presupuestos(mes):
    """Obtiene presupuestos de un mes, normalizando claves para compatibilidad."""
    url = f"{API_URL}/budgets/{mes}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for p in raw:
                if "month" in p and "mes" not in p:
                    p["mes"] = p["month"]
                if "amount" in p and "cantidad" not in p:
                    p["cantidad"] = p["amount"]
            return raw
        logger.warning("Respuesta no exitosa al consultar presupuestos de %s (%s): %s", mes, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar presupuestos en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_presupuestos(%s): %s", mes, e)
    return []


def get_transacciones(mes=None):
    """Obtiene transacciones de un mes, normalizando claves para compatibilidad."""
    url = f"{API_URL}/transactions/"
    params = {}
    if mes:
        params["month"] = mes
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            raw = response.json()
            for t in raw:
                if "date" in t and "fecha" not in t:
                    t["fecha"] = t["date"]
                if "amount" in t and "cantidad" not in t:
                    t["cantidad"] = t["amount"]
                if "description" in t and "concepto" not in t:
                    t["concepto"] = t["description"]
            return raw
        logger.warning("Respuesta no exitosa al consultar transacciones (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar transacciones en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_transacciones(): %s", e)
    return []


def create_transaccion(fecha, subcategoria_id, cantidad, concepto):
    url = f"{API_URL}/transactions/"
    data = {
        "date": fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
        "subcategory_id": subcategoria_id,
        "amount": cantidad,
        "description": concepto,
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            res = response.json()
            if "date" in res and "fecha" not in res:
                res["fecha"] = res["date"]
            if "amount" in res and "cantidad" not in res:
                res["cantidad"] = res["amount"]
            return res
        logger.warning("Error al crear transacción (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al crear transacción en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en create_transaccion(): %s", e)
    return None


def save_presupuestos_bulk(presupuestos_list):
    url = f"{API_URL}/budgets/bulk"
    payload = []
    for p in presupuestos_list:
        m = p.get("month") or p.get("mes")
        s = p.get("subcategory_id")
        a = p.get("amount") if p.get("amount") is not None else p.get("cantidad", 0.0)
        payload.append({"month": m, "subcategory_id": s, "amount": a})
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
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
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
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
        response = requests.post(url, params=params, json=data, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Error al actualizar configuración del fondo de emergencia (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al actualizar fondo de emergencia en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en update_emergency_fund_config(): %s", e)
    return None


def get_macro_indicators():
    """Obtiene los indicadores macroeconómicos y deuda soberana desde el backend."""
    url = f"{API_URL}/market/macro-indicators"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al obtener indicadores macro (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al obtener macro-indicators en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_macro_indicators(): %s", e)
    return None


def get_market_news(limit=15):
    """Obtiene las noticias financieras depuradas con análisis de IA desde el backend."""
    url = f"{API_URL}/market/news"
    try:
        response = requests.get(url, params={"limit": limit}, timeout=35)
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
        response = requests.post(url, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al refrescar el radar de mercado (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al refrescar el radar en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en refresh_market_radar(): %s", e)
    return None


def get_screener_universes():
    """Obtiene la lista de universos predefinidos para el screener."""
    url = f"{API_URL}/screener/universes"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al consultar universos de screener (%s): %s", response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red o conexión al consultar universos en %s: %s", url, e)
    except Exception as e:
        logger.error("Error inesperado en get_screener_universes(): %s", e)
    return []


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
        response = requests.get(url, params=params, timeout=30)
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
        response = requests.post(url, json=payload, timeout=35)
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
        response = requests.post(url, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.warning("Respuesta no exitosa al refrescar universo '%s' (%s): %s", universe_id, response.status_code, response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al refrescar screener universo '%s' en %s: %s", universe_id, url, e)
    except Exception as e:
        logger.error("Error inesperado en refresh_screener_universe('%s'): %s", universe_id, e)
    return None
