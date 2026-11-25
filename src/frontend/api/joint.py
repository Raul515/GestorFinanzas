"""Cliente HTTP para Cuenta Conjunta, Huchas, Liquidaciones y Sincronización P2P."""

from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

from frontend.api import http


def get_joint_status() -> Dict[str, Any]:
    """Consulta si la cuenta conjunta está configurada o si nos encontramos en Estado Cero."""
    return http.request("GET", "/joint/status", default={"is_configured": False}, log_context="get_joint_status")


def setup_joint_account(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta el onboarding inicial para crear la cuenta conjunta."""
    res = http.request(
        "POST",
        "/joint/setup",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="setup_joint_account",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
    return res


def get_joint_account() -> Optional[Dict[str, Any]]:
    """Obtiene la configuración activa de la cuenta conjunta."""
    return http.request("GET", "/joint/account", default=None, log_context="get_joint_account")


def update_joint_account(payload: dict) -> Optional[Dict[str, Any]]:
    """Actualiza los parámetros del hogar e invalida cachés conjuntas."""
    res = http.request("PUT", "/joint/account", json=payload, default=None, log_context="update_joint_account")
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
    return res


@st.cache_data(ttl=600, show_spinner=False)
def get_joint_categories() -> List[Dict[str, Any]]:
    """Obtiene el catálogo de categorías del hogar."""
    return http.request("GET", "/joint/categories", default=[], log_context="get_joint_categories")


@st.cache_data(ttl=600, show_spinner=False)
def get_joint_subcategories(category_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Obtiene las subcategorías de necesidades comunes."""
    params = {"category_id": category_id} if category_id else None
    return http.request("GET", "/joint/subcategories", params=params, default=[], log_context="get_joint_subcategories")


def create_joint_subcategory(name: str, joint_category_id: int, monthly_budget: float = 0.0) -> Optional[Dict[str, Any]]:
    """Crea una subcategoría de necesidades comunes del hogar e invalida caché."""
    cleaned_name = name.strip() if name else ""
    if not cleaned_name:
        http.logger.warning("Intento de crear subcategoría del hogar con nombre vacío")
        return None

    res = http.request(
        "POST",
        "/joint/subcategories",
        json={
            "name": cleaned_name,
            "joint_category_id": joint_category_id,
            "monthly_budget": float(monthly_budget or 0.0),
        },
        expected_statuses=(200, 201),
        default=None,
        log_context="create_joint_subcategory",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.logger.info("Subcategoría del hogar '%s' creada con éxito", cleaned_name)
    return res


def update_joint_subcategory(
    subcategory_id: int,
    name: Optional[str] = None,
    monthly_budget: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Actualiza el nombre o presupuesto mensual de una subcategoría común del hogar."""
    payload: Dict[str, Any] = {}
    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name:
            http.logger.warning("Intento de actualizar subcategoría del hogar %s con nombre vacío", subcategory_id)
            return None
        payload["name"] = cleaned_name
    if monthly_budget is not None:
        payload["monthly_budget"] = float(monthly_budget)

    if not payload:
        http.logger.warning("update_joint_subcategory invocado sin campos a actualizar")
        return None

    res = http.request(
        "PUT",
        f"/joint/subcategories/{subcategory_id}",
        json=payload,
        default=None,
        log_context=f"update_joint_subcategory({subcategory_id})",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.logger.info("Subcategoría del hogar %s actualizada con éxito: %s", subcategory_id, payload)
    return res


def get_joint_subcategory_usage(subcategory_id: int) -> Optional[Dict[str, Any]]:
    """Consulta la auditoría contable de uso de una subcategoría común del hogar."""
    return http.request(
        "GET",
        f"/joint/subcategories/{subcategory_id}/usage",
        default=None,
        log_context=f"get_joint_subcategory_usage({subcategory_id})",
    )


def delete_joint_subcategory(subcategory_id: int) -> Tuple[bool, str]:
    """Elimina físicamente una subcategoría del hogar si no tiene transacciones asociadas."""
    url = f"{http.API_URL}/joint/subcategories/{subcategory_id}"
    try:
        response = http._session.delete(url, timeout=10)
        if response.status_code == 200:
            http.clear_cache_hook("clear_joint_cache")
            http.logger.info("Subcategoría del hogar %s eliminada con éxito", subcategory_id)
            return True, "Subcategoría conjunta eliminada con éxito."
        if response.status_code == 409:
            err_msg = http.safe_error_detail(
                response, "La subcategoría contiene transacciones del hogar y no puede eliminarse."
            )
            http.logger.warning("Borrado bloqueado por dependencias en subcategoría del hogar %s: %s", subcategory_id, err_msg)
            return False, err_msg
        err_msg = http.safe_error_detail(response)
        http.logger.warning("Error al eliminar subcategoría del hogar %s (%s): %s", subcategory_id, response.status_code, err_msg)
        return False, f"Error del servidor ({response.status_code}): {err_msg}"
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en delete_joint_subcategory en %s: %s", url, exc)
        return False, f"Error de red o conexión: {exc}"
    except Exception as exc:
        http.logger.error("Error inesperado en delete_joint_subcategory(): %s", exc)
        return False, f"Error inesperado: {exc}"


@st.cache_data(ttl=60, show_spinner=False)
def get_joint_sinking_funds(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene las metas de ahorro / huchas de amortización del hogar."""
    params = {"status": status} if status else None
    return http.request("GET", "/joint/sinking-funds", params=params, default=[], log_context="get_joint_sinking_funds")


def create_joint_sinking_fund(payload: dict) -> Optional[Dict[str, Any]]:
    """Crea una nueva hucha de amortización e invalida cachés."""
    res = http.request(
        "POST",
        "/joint/sinking-funds",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="create_joint_sinking_fund",
    )
    if res is not None:
        try:
            get_joint_sinking_funds.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de huchas: %s", exc)
        http.clear_cache_hook("clear_joint_cache")
    return res


def update_joint_sinking_fund(fund_id: int, payload: dict) -> Optional[Dict[str, Any]]:
    """Edita una hucha de amortización existente e invalida cachés."""
    res = http.request(
        "PUT",
        f"/joint/sinking-funds/{fund_id}",
        json=payload,
        default=None,
        log_context=f"update_joint_sinking_fund({fund_id})",
    )
    if res is not None:
        try:
            get_joint_sinking_funds.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de huchas: %s", exc)
        http.clear_cache_hook("clear_joint_cache")
    return res


def delete_joint_sinking_fund(
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = None,
    action_on_balance: Optional[str] = None,
    refund_personal_entry: bool = True,
) -> bool:
    """Elimina una hucha de amortización, definiendo el destino de su saldo remanente."""
    params: Dict[str, Any] = {"refund_personal_entry": str(refund_personal_entry).lower()}
    if reallocate_to_fund_id:
        params["reallocate_to_fund_id"] = reallocate_to_fund_id
    if action_on_balance:
        params["action_on_balance"] = action_on_balance

    res = http.request(
        "DELETE",
        f"/joint/sinking-funds/{fund_id}",
        params=params,
        default=None,
        log_context=f"delete_joint_sinking_fund({fund_id})",
    )
    if res is not None:
        try:
            get_joint_sinking_funds.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de huchas: %s", exc)
        http.clear_cache_hook("clear_categories_cache")
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
        return True
    return False


def transfer_joint_sinking_fund(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta un rebalanceo o traspaso directo de saldo entre huchas del hogar."""
    res = http.request(
        "POST",
        "/joint/sinking-funds/transfer",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="transfer_joint_sinking_fund",
    )
    if res is not None:
        try:
            get_joint_sinking_funds.clear()
        except Exception as exc:
            http.logger.debug("Error limpiando caché de huchas: %s", exc)
        http.clear_cache_hook("clear_joint_cache")
    return res


def get_joint_sinking_fund_transfers(limit: int = 100) -> List[Dict[str, Any]]:
    """Obtiene el historial de traspasos y rebalanceos entre huchas de amortización."""
    return http.request(
        "GET",
        "/joint/sinking-funds/transfers",
        params={"limit": limit},
        default=[],
        log_context="get_joint_sinking_fund_transfers",
    )


def get_joint_transactions(year: Optional[int] = None, month: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene los gastos del hogar registrados."""
    params: Dict[str, Any] = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    return http.request("GET", "/joint/transactions", params=params, default=[], log_context="get_joint_transactions")


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

    return http.request("GET", "/joint/transactions/search", params=params, default=[], log_context="search_joint_transactions")


def create_joint_transaction(payload: dict) -> Optional[Dict[str, Any]]:
    """Registra un nuevo gasto común del hogar."""
    res = http.request(
        "POST",
        "/joint/transactions",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="create_joint_transaction",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
    return res


def delete_joint_transaction(tx_id: int) -> bool:
    """Elimina una transacción conjunta."""
    res = http.request("DELETE", f"/joint/transactions/{tx_id}", default=None, log_context=f"delete_joint_transaction({tx_id})")
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        return True
    return False


def get_joint_settlement_summary() -> Optional[Dict[str, Any]]:
    """Obtiene el resumen consolidado de liquidación y reembolsos de gastos adelantados."""
    return http.request("GET", "/joint/settlement/summary", default=None, log_context="get_joint_settlement_summary")


def settle_joint_transaction(tx_id: int) -> bool:
    """Marca una transacción conjunta pendiente como liquidada/reembolsada."""
    res = http.request(
        "POST",
        f"/joint/settlement/settle-transaction/{tx_id}",
        default=None,
        log_context=f"settle_joint_transaction({tx_id})",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        return True
    return False


def settle_all_joint_transactions() -> bool:
    """Marca todas las transacciones conjuntas pendientes como liquidadas/reembolsadas."""
    res = http.request("POST", "/joint/settlement/settle-all", default=None, log_context="settle_all_joint_transactions")
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        return True
    return False


def get_joint_contributions(year: Optional[int] = None, month: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene el historial de aportaciones a la cuenta común."""
    params: Dict[str, Any] = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    return http.request("GET", "/joint/contributions", params=params, default=[], log_context="get_joint_contributions")


def get_joint_contribution_calculation() -> Optional[Dict[str, Any]]:
    """Consulta el cálculo dinámico de las cuotas mensuales del hogar."""
    return http.request("GET", "/joint/contributions/calculation", default=None, log_context="get_joint_contribution_calculation")


def asentar_aportacion_asistida(payload: dict) -> Optional[Dict[str, Any]]:
    """Ejecuta el asiento asistido en 1 clic de inicio de mes."""
    res = http.request(
        "POST",
        "/joint/contributions/asentar-asistida",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="asentar_aportacion_asistida",
    )
    if res is not None:
        http.clear_cache_hook("clear_categories_cache")
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
    return res


def delete_joint_contribution(contribution_id: int) -> bool:
    """Elimina físicamente una aportación a la cuenta común."""
    res = http.request(
        "DELETE",
        f"/joint/contributions/{contribution_id}",
        default=None,
        log_context=f"delete_joint_contribution({contribution_id})",
    )
    if res is not None:
        http.clear_cache_hook("clear_categories_cache")
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
        return True
    return False


def get_joint_health() -> Optional[Dict[str, Any]]:
    """Consulta la Tasa de Esfuerzo Familiar y el semáforo determinista."""
    return http.request("GET", "/joint/health", default=None, log_context="get_joint_health")


def get_joint_annual_summary(year: int) -> Optional[Dict[str, Any]]:
    """Consulta el Resumen Anual consolidado del hogar."""
    return http.request(
        "GET",
        "/joint/annual-summary",
        params={"year": year},
        default=None,
        log_context=f"get_joint_annual_summary({year})",
    )


def trigger_process_inbox() -> Dict[str, Any]:
    """Dispara el procesamiento de los deltas de Syncthing en sync/inbox/."""
    res = http.request("POST", "/joint/sync/process-inbox", default={"status": "error"}, log_context="trigger_process_inbox")
    if isinstance(res, dict) and res.get("status") != "error":
        http.clear_cache_hook("clear_joint_cache")
    return res


def get_sync_status() -> Dict[str, Any]:
    """Obtiene el estado de sincronización y métricas de deltas pendientes."""
    return http.request(
        "GET",
        "/joint/sync/status",
        default={"is_synchronized": False, "outbox_pending_count": 0, "inbox_pending_count": 0},
        log_context="get_sync_status",
    )


def reset_joint_account() -> bool:
    """Purga la cuenta conjunta completa y vacía los buzones de sincronización."""
    res = http.request("POST", "/joint/reset", default=None, log_context="reset_joint_account")
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
        return True
    return False


def get_joint_invitation() -> Dict[str, Any]:
    """Comprueba si hay una invitación de hogar pendiente enviada por la pareja."""
    return http.request(
        "GET",
        "/joint/invitation",
        default={"has_invitation": False, "invitation": None},
        log_context="get_joint_invitation",
    )


def accept_joint_invitation() -> Optional[Dict[str, Any]]:
    """Acepta la invitación de hogar detectada en 1 clic."""
    res = http.request(
        "POST",
        "/joint/accept-invitation",
        expected_statuses=(200, 201),
        default=None,
        log_context="accept_joint_invitation",
    )
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
    return res


def resend_joint_invitation() -> bool:
    """Solicita al backend que vuelva a emitir la invitación para la pareja en outbox/."""
    res = http.request("POST", "/joint/resend-invitation", default=None, log_context="resend_joint_invitation")
    return res is not None


@st.cache_data(ttl=300, show_spinner=False)
def export_joint_excel() -> Optional[bytes]:
    """Descarga el archivo Excel estructurado (.xlsx) con los datos consolidados del hogar."""
    response = http.request("GET", "/joint/export/excel", timeout=15, raw_response=True, default=None, log_context="export_joint_excel")
    if response is not None and response.status_code == 200:
        return response.content
    return None


def get_joint_sync_events_detail(max_processed: int = 30) -> Optional[Dict[str, Any]]:
    """Consulta la inspección detallada de deltas en outbox, inbox, processed y error."""
    return http.request(
        "GET",
        "/joint/sync/events",
        params={"max_processed": max_processed},
        default=None,
        log_context="get_joint_sync_events_detail",
    )


def retry_joint_sync_errors() -> Optional[Dict[str, Any]]:
    """Solicita al backend mover los eventos de sync/error/ a sync/inbox/ y reprocesarlos."""
    return http.request("POST", "/joint/sync/retry-errors", timeout=15, default=None, log_context="retry_joint_sync_errors")


def clear_joint_sync_errors() -> Optional[Dict[str, Any]]:
    """Solicita al backend purgar todos los eventos delta fallidos de sync/error/."""
    return http.request("POST", "/joint/sync/clear-errors", timeout=15, default=None, log_context="clear_joint_sync_errors")


def get_pending_remote_deletion() -> Optional[Dict[str, Any]]:
    """Consulta si hay una solicitud de borrado remoto pendiente emitida por la pareja."""
    res_data = http.request("GET", "/joint/remote-deletion/pending", default=None, log_context="get_pending_remote_deletion")
    if isinstance(res_data, dict) and res_data.get("pending"):
        return res_data.get("data")
    return None


def accept_remote_deletion() -> bool:
    """Acepta la solicitud de borrado remoto del hogar y purga las cachés locales."""
    res = http.request("POST", "/joint/remote-deletion/accept", timeout=15, default=None, log_context="accept_remote_deletion")
    if res is not None:
        http.clear_cache_hook("clear_joint_cache")
        http.clear_cache_hook("clear_annual_cache")
        return True
    return False


def reject_remote_deletion() -> bool:
    """Rechaza la solicitud de borrado remoto del hogar, conservando los datos locales."""
    res = http.request("POST", "/joint/remote-deletion/reject", timeout=15, default=None, log_context="reject_remote_deletion")
    return res is not None
