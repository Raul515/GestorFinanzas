"""Cliente HTTP para finanzas personales, presupuestos, salvaguarda y pautas."""

from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

from frontend.api import http

_CATEGORY_KEY_PAIRS = (("name", "nombre"), ("type", "tipo"))
_SUBCATEGORY_KEY_PAIRS = (("name", "nombre"), ("category_id", "categoria_id"))
_BUDGET_KEY_PAIRS = (("month", "mes"), ("amount", "cantidad"), ("subcategory_id", "subcategoria_id"))
_TX_KEY_PAIRS = (
    ("date", "fecha"),
    ("amount", "cantidad"),
    ("description", "concepto"),
    ("subcategory_id", "subcategoria_id"),
)


@st.cache_data(ttl=600, show_spinner=False)
def get_categorias() -> List[Dict[str, Any]]:
    """Obtiene el listado de categorías, normalizando claves en la frontera."""
    raw = http.request("GET", "/categories/", default=[], log_context="get_categorias")
    for cat in raw:
        http.normalize_bidirectional(cat, _CATEGORY_KEY_PAIRS)
        for sub in cat.get("subcategories", []):
            http.normalize_bidirectional(sub, _SUBCATEGORY_KEY_PAIRS)
    return raw


@st.cache_data(ttl=600, show_spinner=False)
def get_subcategorias(categoria_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Obtiene subcategorías, normalizando claves en la frontera."""
    params = {"category_id": categoria_id} if categoria_id else None
    raw = http.request("GET", "/categories/subcategories/", params=params, default=[], log_context="get_subcategorias")
    for sub in raw:
        http.normalize_bidirectional(sub, _SUBCATEGORY_KEY_PAIRS)
    return raw


def create_subcategory(category_id: int, name: str) -> Optional[Dict[str, Any]]:
    """Crea una subcategoría personal e invalida cachés de categorías y resumen anual."""
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        http.logger.warning("Intento de crear subcategoría personal con nombre vacío")
        return None

    res = http.request(
        "POST",
        "/categories/subcategories/",
        json={"category_id": category_id, "name": cleaned_name},
        expected_statuses=(200, 201),
        default=None,
        log_context="create_subcategory",
    )
    if res is not None:
        http.clear_cache_hook("clear_categories_cache")
        http.clear_cache_hook("clear_annual_cache")
        http.logger.info("Subcategoría personal '%s' creada con éxito", cleaned_name)
    return res


def update_subcategory(subcategory_id: int, name: str) -> Optional[Dict[str, Any]]:
    """Actualiza el nombre de una subcategoría personal e invalida cachés."""
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        http.logger.warning("Intento de actualizar subcategoría %s con nombre vacío", subcategory_id)
        return None

    res = http.request(
        "PUT",
        f"/categories/subcategories/{subcategory_id}",
        json={"name": cleaned_name},
        default=None,
        log_context=f"update_subcategory({subcategory_id})",
    )
    if res is not None:
        http.clear_cache_hook("clear_categories_cache")
        http.clear_cache_hook("clear_annual_cache")
        http.logger.info("Subcategoría personal %s renombrada a '%s'", subcategory_id, cleaned_name)
    return res


def get_subcategory_usage(subcategory_id: int) -> Optional[Dict[str, Any]]:
    """Consulta la auditoría contable de uso de una subcategoría personal."""
    return http.request(
        "GET",
        f"/categories/subcategories/{subcategory_id}/usage",
        default=None,
        log_context=f"get_subcategory_usage({subcategory_id})",
    )


def delete_subcategory(subcategory_id: int) -> Tuple[bool, str]:
    """Elimina físicamente una subcategoría personal si no tiene histórico contable."""
    url = f"{http.API_URL}/categories/subcategories/{subcategory_id}"
    try:
        response = http._session.delete(url, timeout=10)
        if response.status_code == 200:
            http.clear_cache_hook("clear_categories_cache")
            http.clear_cache_hook("clear_annual_cache")
            http.logger.info("Subcategoría personal %s eliminada con éxito", subcategory_id)
            return True, "Subcategoría eliminada con éxito."
        if response.status_code == 409:
            err_msg = http.safe_error_detail(
                response, "La subcategoría contiene registros vinculados y no puede eliminarse."
            )
            http.logger.warning("Borrado bloqueado por dependencias en subcategoría %s: %s", subcategory_id, err_msg)
            return False, err_msg
        err_msg = http.safe_error_detail(response)
        http.logger.warning("Error al eliminar subcategoría %s (%s): %s", subcategory_id, response.status_code, err_msg)
        return False, f"Error del servidor ({response.status_code}): {err_msg}"
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en delete_subcategory en %s: %s", url, exc)
        return False, f"Error de red o conexión: {exc}"
    except Exception as exc:
        http.logger.error("Error inesperado en delete_subcategory(): %s", exc)
        return False, f"Error inesperado: {exc}"


def get_presupuestos(mes: str) -> List[Dict[str, Any]]:
    """Obtiene presupuestos de un mes, normalizando claves en la frontera."""
    raw = http.request("GET", f"/budgets/{mes}", default=[], log_context=f"get_presupuestos({mes})")
    for p in raw:
        http.normalize_bidirectional(p, _BUDGET_KEY_PAIRS)
    return raw


def create_presupuesto(mes: str, subcategoria_id: int, cantidad: float) -> Optional[Dict[str, Any]]:
    """Crea o actualiza una asignación presupuestaria individual."""
    res = http.request(
        "POST",
        "/budgets/",
        json={"month": mes, "subcategory_id": subcategoria_id, "amount": float(cantidad or 0.0)},
        expected_statuses=(200, 201),
        default=None,
        log_context="create_presupuesto",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
        if isinstance(res, dict):
            http.normalize_bidirectional(res, _BUDGET_KEY_PAIRS)
    return res


def get_transacciones(mes: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene transacciones de un mes, normalizando claves en la frontera."""
    params = {"month": mes} if mes else None
    raw = http.request("GET", "/transactions/", params=params, default=[], log_context="get_transacciones")
    for tx in raw:
        http.normalize_bidirectional(tx, _TX_KEY_PAIRS)
    return raw


@st.cache_data(ttl=120, show_spinner=False)
def get_annual_summary_data(year: int) -> Dict[int, Dict[str, Any]]:
    """Recolecta y cachea los presupuestos y transacciones de los 12 meses del año."""
    import sys

    facade = sys.modules.get("frontend.api_client") or sys.modules.get("api_client")
    fetch_budgets = getattr(facade, "get_presupuestos", get_presupuestos) if facade else get_presupuestos
    fetch_txs = getattr(facade, "get_transacciones", get_transacciones) if facade else get_transacciones

    annual_data: Dict[int, Dict[str, Any]] = {}
    for m in range(1, 13):
        mes_key = f"{year}-{m:02d}"
        annual_data[m] = {
            "presupuestos": fetch_budgets(mes_key) or [],
            "transacciones": fetch_txs(mes_key) or [],
        }
    return annual_data


def create_transaccion(fecha: Any, subcategoria_id: int, cantidad: float, concepto: str) -> Optional[Dict[str, Any]]:
    """Registra una nueva transacción personal e invalida la caché anual."""
    res = http.request(
        "POST",
        "/transactions/",
        json={
            "date": fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
            "subcategory_id": subcategoria_id,
            "amount": cantidad,
            "description": concepto,
        },
        default=None,
        log_context="create_transaccion",
    )
    if isinstance(res, dict):
        http.clear_cache_hook("clear_annual_cache")
        http.normalize_bidirectional(res, _TX_KEY_PAIRS)
    return res


def delete_transaction(transaction_id: int) -> bool:
    """Elimina una transacción por su identificador en el backend."""
    res = http.request(
        "DELETE",
        f"/transactions/{transaction_id}",
        default=None,
        log_context=f"delete_transaction({transaction_id})",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
        http.logger.info("Transacción %s eliminada exitosamente en el backend", transaction_id)
        return True
    return False


def save_presupuestos_bulk(presupuestos_list: List[Dict[str, Any]]) -> Any:
    """Guarda presupuestos en bloque e invalida la caché anual."""
    payload = []
    for p in presupuestos_list:
        m = p.get("month") or p.get("mes")
        s = p.get("subcategory_id") if p.get("subcategory_id") is not None else p.get("subcategoria_id")
        a = p.get("amount") if p.get("amount") is not None else p.get("cantidad", 0.0)
        payload.append({"month": m, "subcategory_id": s, "amount": a})

    res = http.request(
        "POST",
        "/budgets/bulk",
        json=payload,
        default=None,
        log_context="save_presupuestos_bulk",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
        if isinstance(res, list):
            for item in res:
                http.normalize_bidirectional(item, _BUDGET_KEY_PAIRS)
    return res


def get_safety_status(mes: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Consulta el estado del fondo de emergencia sin invalidar cachés de mercado."""
    params = {"mes": mes} if mes else None
    return http.request("GET", "/advisor/safety-status", params=params, default=None, log_context="get_safety_status")


def update_emergency_fund_config(
    target_months: Optional[int] = None,
    current_balance: Optional[float] = None,
    mes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Actualiza la configuración del fondo de emergencia."""
    params = {"mes": mes} if mes else None
    data: Dict[str, Any] = {}
    if target_months is not None:
        data["target_months"] = target_months
    if current_balance is not None:
        data["current_balance"] = current_balance
    return http.request(
        "POST",
        "/advisor/emergency-fund/config",
        params=params,
        json=data,
        default=None,
        log_context="update_emergency_fund_config",
    )


def get_monthly_guidelines(
    month_key: str,
    month_name: str,
    real_income: float,
    budget_income: float,
    real_needs: float,
    real_wants: float,
    real_savings: float,
    safety_status: Any = None,
) -> Optional[Dict[str, Any]]:
    """Solicita al backend la evaluación determinista de pautas mensuales."""
    return http.request(
        "POST",
        "/guidelines/monthly",
        json={
            "month_key": month_key,
            "month_name": month_name,
            "real_income": float(real_income or 0.0),
            "budget_income": float(budget_income or 0.0),
            "real_needs": float(real_needs or 0.0),
            "real_wants": float(real_wants or 0.0),
            "real_savings": float(real_savings or 0.0),
            "safety_status": safety_status,
        },
        default=None,
        log_context="get_monthly_guidelines",
    )


def get_annual_guidelines(metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Solicita al backend el diagnóstico estructural y pautas anuales consolidadas."""
    return http.request(
        "POST",
        "/guidelines/annual",
        json={"metrics": metrics},
        default=None,
        log_context="get_annual_guidelines",
    )


def apply_guideline_strategy(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta una estrategia de asignación de capital e invalida la caché anual."""
    res = http.request(
        "POST",
        "/guidelines/apply-strategy",
        json=payload,
        default=None,
        log_context="apply_guideline_strategy",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
    return res


def sweep_month_surplus(
    month_key: str,
    amount: float,
    target_subcategory_id: Optional[int] = None,
    mode: str = "DEFAULT_SAVINGS",
) -> Optional[Dict[str, Any]]:
    """Ejecuta el barrido de fin de mes e invalida la caché anual."""
    res = http.request(
        "POST",
        "/guidelines/sweep",
        json={
            "month_key": month_key,
            "amount": float(amount or 0.0),
            "target_subcategory_id": target_subcategory_id,
            "mode": mode,
        },
        default=None,
        log_context="sweep_month_surplus",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
    return res


def compensate_guideline_deficit(
    month_key: str,
    action_type: str,
    amount: float = 0.0,
    target_subcategory_id: Optional[int] = None,
    target_subcategory_ids: Optional[List[int]] = None,
) -> Optional[Dict[str, Any]]:
    """Ejecuta una acción de compensación o contención presupuestaria e invalida la caché anual."""
    res = http.request(
        "POST",
        "/guidelines/compensate-deficit",
        json={
            "month_key": month_key,
            "action_type": action_type,
            "amount": float(amount or 0.0),
            "target_subcategory_id": target_subcategory_id,
            "target_subcategory_ids": target_subcategory_ids,
        },
        default=None,
        log_context="compensate_guideline_deficit",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
    return res


def revert_guideline_strategy(month_key: str, scenario_type: str = "NEEDS_SURPLUS") -> Optional[Dict[str, Any]]:
    """Revierte atómicamente una estrategia aplicada e invalida la caché anual."""
    res = http.request(
        "POST",
        "/guidelines/revert-strategy",
        json={"month_key": month_key, "scenario_type": scenario_type},
        default=None,
        log_context="revert_guideline_strategy",
    )
    if res is not None:
        http.clear_cache_hook("clear_annual_cache")
    return res
