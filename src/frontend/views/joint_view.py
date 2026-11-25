"""
Fachada de Vista Frontend para la Gestión de Finanzas Compartidas (Cuenta Conjunta del Hogar).
Especificación 010 / Spec 017 (Fase 5): Delega en los submódulos de frontend.views.joint.*.
"""

import logging
from typing import Any, Dict

import streamlit as st

try:
    import api_client
except ImportError:
    from frontend import api_client  # type: ignore

try:
    from utils.formatting import format_date_es as _shared_format_date_es  # type: ignore
    from views.joint.config_view import _render_tab_configuracion  # type: ignore
    from views.joint.dashboard_view import (  # type: ignore
        _render_personal_assisted_contribution_banner,
        _render_tab_12_meses,
        _render_tab_resumen_anual,
    )
    from views.joint.search_view import _render_tab_buscador_gastos  # type: ignore
    from views.joint.setup_view import _render_zero_state_wizard  # type: ignore
    from views.joint.sinking_funds_view import _render_tab_huchas  # type: ignore
except ImportError:
    from frontend.utils.formatting import format_date_es as _shared_format_date_es  # type: ignore
    from frontend.views.joint.config_view import _render_tab_configuracion  # type: ignore
    from frontend.views.joint.dashboard_view import (  # type: ignore
        _render_personal_assisted_contribution_banner,
        _render_tab_12_meses,
        _render_tab_resumen_anual,
    )
    from frontend.views.joint.search_view import _render_tab_buscador_gastos  # type: ignore
    from frontend.views.joint.setup_view import _render_zero_state_wizard  # type: ignore
    from frontend.views.joint.sinking_funds_view import _render_tab_huchas  # type: ignore

logger = logging.getLogger(__name__)


def _format_date_es(d_val: Any) -> str:
    """Formatea cualquier fecha a estándar español DD/MM/AAAA."""
    return _shared_format_date_es(d_val, fallback="—")


def render_joint_view(selected_year: int) -> None:
    """Punto de entrada principal para la pantalla de Economía del Hogar (Cuenta Conjunta)."""
    status = api_client.get_joint_status()
    is_configured = status.get("is_configured", False)

    if not is_configured:
        _render_zero_state_wizard()
        return

    account = api_client.get_joint_account()
    if not account:
        st.error("No se pudo recuperar la configuración del hogar desde el backend.")
        return

    _render_configured_joint_view(selected_year=selected_year, account=account, status=status)


def _render_configured_joint_view(selected_year: int, account: Dict[str, Any], status: Dict[str, Any]) -> None:
    """Renderiza la pantalla completa e independiente de la economía del hogar."""
    sync_status = api_client.get_sync_status()
    if sync_status.get("inbox_pending_count", 0) > 0:
        api_client.trigger_process_inbox()
        sync_status = api_client.get_sync_status()

    pending_del = api_client.get_pending_remote_deletion()
    if pending_del:
        partner_name = pending_del.get("partner_name", "Tu pareja")
        hh_name = pending_del.get("household_name", "el hogar")
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #7f1d1d, #450a0a); border: 2px solid #ef4444; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="color: #fca5a5; margin: 0 0 8px 0;">⚠️ Solicitud de Desactivación del Hogar Detectada</h3>
                <p style="color: #fef2f2; margin: 0 0 10px 0; font-size: 1rem;">
                    Tu pareja (<b>{partner_name}</b>) ha desactivado la cuenta conjunta de <b>'{hh_name}'</b> en su dispositivo.
                </p>
                <p style="color: #fecaca; margin: 0 0 14px 0; font-size: 0.9rem;">
                    ¿Qué deseas hacer en este dispositivo? Puedes aceptar el borrado para volver al Estado Cero, o rechazarlo para conservar tus datos locales intactos.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_acc, col_rej = st.columns(2)
        with col_acc:
            if st.button("🗑️ Aceptar Borrado y Volver al Estado Cero", type="primary", width="stretch", key="btn_accept_remote_del"):
                with st.spinner("Restableciendo cuenta conjunta al Estado Cero..."):
                    if api_client.accept_remote_deletion():
                        api_client.clear_joint_cache()
                        api_client.clear_annual_cache()
                        st.cache_data.clear()
                        st.success("✅ Cuenta conjunta restablecida al Estado Cero.")
                        st.rerun()
                    else:
                        st.error("❌ Error al procesar el restablecimiento.")
        with col_rej:
            if st.button("🛡️ Rechazar y Conservar Mis Datos Locales", width="stretch", key="btn_reject_remote_del"):
                with st.spinner("Conservando datos locales..."):
                    if api_client.reject_remote_deletion():
                        st.info("🛡️ Solicitud de borrado descartada. Tus datos locales se mantienen intactos.")
                        st.rerun()
                    else:
                        st.error("❌ Error al descartar la solicitud.")
        st.markdown("<hr style='margin: 20px 0; border: 0; border-top: 1px dashed #ef4444;'>", unsafe_allow_html=True)

    is_synced = sync_status.get("is_synchronized", True)
    inbox_cnt = sync_status.get("inbox_pending_count", 0)
    sync_badge = "🟢 Sincronizado" if is_synced else f"🟡 {inbox_cnt} Delta(s) Pendiente(s)"

    cohab_val = account.get("cohabitation_stage", "PRE_COHABITATION")
    cohab_text = (
        "Pre-Convivencia"
        if cohab_val in ("PRE_COHABITATION", "DATING_COHABITATION")
        else "Convivencia Plena"
    )
    split_val = account.get("split_mode", "EQUAL_50_50")
    split_text = "Reparto 50/50" if "50" in str(split_val) else "Reparto Proporcional"
    strat_val = account.get("contribution_strategy", "NOMINAL_TEMPLATE")
    custom_budget_val = float(account.get("custom_total_monthly_budget", 0.0) or 0.0)
    strat_text = f"Presupuesto Fijo ({custom_budget_val:,.2f} €/mes)" if strat_val == "GLOBAL_FIXED" else "Por Conceptos"

    tx_all = api_client.get_joint_transactions(year=selected_year)
    contrib_all = api_client.get_joint_contributions(year=selected_year)
    total_contrib = sum(float(c.get("amount", 0.0)) for c in contrib_all)
    total_spent = sum(float(t.get("amount", 0.0)) for t in tx_all)
    current_treasury = total_contrib - total_spent

    household_title = account.get("household_name") or account.get("account_name", "Hogar Compartido")
    member_a_display = account.get("member_a_name", "Miembro A")
    member_b_display = account.get("member_b_name", "Miembro B")

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 18px 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <h2 style="color: #f8fafc; margin: 0; font-size: 1.5rem;">👥 {household_title}</h2>
                    <p style="color: #94a3b8; margin: 4px 0 0 0; font-size: 0.9rem;">
                        Miembros: <b>{member_a_display}</b> y <b>{member_b_display}</b> |
                        {cohab_text} | {split_text} | {strat_text}
                    </p>
                </div>
                <div style="text-align: right; margin-top: 8px;">
                    <span style="font-size: 0.85rem; color: #cbd5e1; background: #334155; padding: 4px 10px; border-radius: 6px;">
                        {sync_badge}
                    </span>
                    <h3 style="color: #38bdf8; margin: 6px 0 0 0; font-size: 1.3rem;">
                        {current_treasury:,.2f} € <small style="font-size: 0.75rem; color: #94a3b8;">(Saldo Tesorería)</small>
                    </h3>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # RF-10: Pestaña espaciadora invisible (#joint-tabs-marker) para fijar Configuración a la derecha (margin-left: auto !important;)
    tab_resumen, tab_meses, tab_huchas, tab_buscador, tab_espacio, tab_config = st.tabs([
        "📊 Resumen Anual del Hogar",
        "📅 12 Meses del Hogar",
        "🎯 Huchas de Amortización",
        "🔍 Buscador de Gastos",
        "ㅤ",
        "⚙️ Configuración del Hogar y Sincronización",
    ])

    with tab_espacio:
        st.empty()

    with tab_resumen:
        _render_tab_resumen_anual(selected_year=selected_year, account=account)

    with tab_meses:
        _render_tab_12_meses(selected_year=selected_year, account=account)

    with tab_huchas:
        _render_tab_huchas(account=account)

    with tab_buscador:
        _render_tab_buscador_gastos(account=account, selected_year=selected_year)

    with tab_config:
        _render_tab_configuracion(account=account, sync_status=sync_status)


render_personal_assisted_contribution_banner = _render_personal_assisted_contribution_banner
