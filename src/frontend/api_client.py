"""
Fachada unificada del cliente HTTP del frontend (Spec 017 - Fase 4).
Mantiene compatibilidad total de contratos, cachés @st.cache_data y mocks de tests,
delegando la implementación en los submódulos de frontend.api.*.
"""

from typing import Any, Dict, Optional

import requests
import streamlit as st

from frontend.api.ai import (
    create_copilot_session,
    delete_copilot_session,
    get_copilot_session_detail,
    get_copilot_sessions,
    run_investment_committee,
    send_copilot_chat,
)
from frontend.api.http import API_URL, _session, get_session, logger
from frontend.api.joint import (
    accept_joint_invitation,
    accept_remote_deletion,
    asentar_aportacion_asistida,
    clear_joint_sync_errors,
    create_joint_sinking_fund,
    create_joint_subcategory,
    create_joint_transaction,
    delete_joint_contribution,
    delete_joint_sinking_fund,
    delete_joint_subcategory,
    delete_joint_transaction,
    export_joint_excel,
    get_joint_account,
    get_joint_annual_summary,
    get_joint_categories,
    get_joint_contribution_calculation,
    get_joint_contributions,
    get_joint_health,
    get_joint_invitation,
    get_joint_settlement_summary,
    get_joint_sinking_fund_transfers,
    get_joint_sinking_funds,
    get_joint_status,
    get_joint_subcategories,
    get_joint_subcategory_usage,
    get_joint_sync_events_detail,
    get_joint_transactions,
    get_pending_remote_deletion,
    get_sync_status,
    reject_remote_deletion,
    resend_joint_invitation,
    reset_joint_account,
    retry_joint_sync_errors,
    search_joint_transactions,
    settle_all_joint_transactions,
    settle_joint_transaction,
    setup_joint_account,
    transfer_joint_sinking_fund,
    trigger_process_inbox,
    update_joint_account,
    update_joint_sinking_fund,
    update_joint_subcategory,
)
from frontend.api.market import (
    add_to_watchlist,
    get_deepdive_analysis,
    get_macro_indicators,
    get_market_news,
    get_screener_custom,
    get_screener_universe,
    get_screener_universes,
    get_watchlist,
    refresh_deepdive_analysis,
    refresh_market_radar,
    refresh_screener_universe,
    remove_from_watchlist,
)
from frontend.api.mobile import (
    generate_mobile_pin,
    get_cached_pairing_token,
    get_mobile_catalog,
    get_mobile_monthly_summary,
    get_mobile_pairing_token,
    get_mobile_status,
    get_mobile_version,
    process_mobile_folder,
    update_mobile_budget,
    upload_mobile_apk,
)
from frontend.api.personal import (
    apply_guideline_strategy,
    compensate_guideline_deficit,
    create_presupuesto,
    create_subcategory,
    create_transaccion,
    delete_subcategory,
    delete_transaction,
    get_annual_guidelines,
    get_annual_summary_data,
    get_categorias,
    get_monthly_guidelines,
    get_presupuestos,
    get_safety_status,
    get_subcategorias,
    get_subcategory_usage,
    get_transacciones,
    revert_guideline_strategy,
    save_presupuestos_bulk,
    sweep_month_surplus,
    update_emergency_fund_config,
    update_subcategory,
)
from frontend.api.system import (
    apply_system_update,
    check_for_updates,
    get_app_version,
    rollback_system_update,
)
from frontend.api import system as _system

create_budget = create_presupuesto
delete_transaccion = delete_transaction


# Wrappers de backup que preservan el uso de frontend.api_client.requests para mocks unitarios
def get_database_health() -> Optional[Dict[str, Any]]:
    return _system.get_database_health(http_client=requests)


def create_backup(custom_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _system.create_backup(custom_name=custom_name, http_client=requests)


def download_backup_bytes() -> Optional[tuple[bytes, str]]:
    return _system.download_backup_bytes(http_client=requests)


def list_backups() -> Dict[str, Any]:
    return _system.list_backups(http_client=requests)


def validate_backup_upload(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    return _system.validate_backup_upload(file_bytes, filename, http_client=requests)


def restore_backup_upload(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    return _system.restore_backup_upload(file_bytes, filename, http_client=requests)


def restore_backup_local(filename: str) -> Optional[Dict[str, Any]]:
    return _system.restore_backup_local(filename, http_client=requests)


def rollback_restore() -> Optional[Dict[str, Any]]:
    return _system.rollback_restore(http_client=requests)


def delete_backup_local(filename: str) -> bool:
    return _system.delete_backup_local(filename, http_client=requests)


def get_backup_schedule() -> Optional[Dict[str, Any]]:
    return _system.get_backup_schedule(http_client=requests)


def update_backup_schedule(enabled: bool, frequency_days: int, keep_max_copies: int) -> Optional[Dict[str, Any]]:
    return _system.update_backup_schedule(enabled, frequency_days, keep_max_copies, http_client=requests)


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
    """Invalida la caché del resumen anual consolidado."""
    try:
        get_annual_summary_data.clear()
    except Exception as exc:
        logger.debug("Error limpiando caché de resumen anual: %s", exc)


def clear_joint_cache() -> None:
    """Invalida la caché de entidades de cuenta conjunta."""
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
