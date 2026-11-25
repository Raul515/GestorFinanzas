import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import sys

import altair as alt
import pandas as pd
import streamlit as st

from backend.domain.constants import is_default_joint_subcategory

try:
    import api_client as _default_api_client
except ImportError:
    from frontend import api_client as _default_api_client  # type: ignore

try:
    from utils.formatting import format_date_es as _shared_format_date_es  # type: ignore
except ImportError:
    from frontend.utils.formatting import format_date_es as _shared_format_date_es  # type: ignore

logger = logging.getLogger(__name__)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _format_date_es(d_val: Any) -> str:
    return _shared_format_date_es(d_val, fallback="—")


class _ApiProxy:
    def __getattr__(self, name: str) -> Any:
        jv = sys.modules.get("frontend.views.joint_view") or sys.modules.get("views.joint_view")
        client = getattr(jv, "api_client", _default_api_client) if jv else _default_api_client
        return getattr(client, name)


api_client = _ApiProxy()


def _render_tab_huchas(account: Dict[str, Any]) -> None:
    """Pestaña de metas de ahorro compartido y huchas de amortización anuales/periódicas."""
    st.subheader("🎯 Huchas de Amortización y Ahorro Compartido")
    st.markdown(
        """
        Las huchas permiten aprovisionar periódicamente para gastos que **no ocurren todos los meses**
        (ej. seguro del coche, IBI, vacaciones, reparaciones del hogar) o para proyectos de ahorro conjunto.
        """
    )

    funds = api_client.get_joint_sinking_funds()

    # Formulario para crear una nueva hucha
    with st.expander("➕ Crear Nueva Hucha de Amortización", expanded=(len(funds) == 0)):
        with st.form("create_sinking_fund_form", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                fund_name = st.text_input("Nombre de la Meta / Hucha", placeholder="Ej. Seguro Coche Anual")
                fund_desc = st.text_input("Descripción", placeholder="Provisión para póliza anual a todo riesgo")
                target_amount = st.number_input("Objetivo Total (€)", min_value=1.0, value=600.0, step=50.0)

            with col_f2:
                current_balance = st.number_input("Saldo Inicial Acumulado (€)", min_value=0.0, value=0.0, step=25.0)
                monthly_target = st.number_input("Aportación Mensual Sugerida (€)", min_value=0.0, value=50.0, step=10.0)
                target_date = st.date_input("Fecha Objetivo (Opcional)", value=None, format="DD/MM/YYYY")

            fund_created = st.form_submit_button("🎯 Crear Hucha de Amortización", width="stretch")
            if fund_created:
                if not fund_name.strip():
                    st.error("Por favor introduce un nombre para la hucha.")
                else:
                    payload_fund = {
                        "name": fund_name.strip(),
                        "description": fund_desc.strip() if fund_desc else None,
                        "target_amount": float(target_amount),
                        "current_balance": float(current_balance),
                        "monthly_target_amount": float(monthly_target),
                        "target_date": target_date.isoformat() if target_date else None,
                        "status": "ACTIVE",
                    }
                    res_fund = api_client.create_joint_sinking_fund(payload_fund)
                    if res_fund:
                        st.success("🎉 Hucha creada exitosamente.")
                        st.rerun()
                    else:
                        st.error("❌ No se pudo crear la hucha. Verifica que el nombre no esté duplicado.")

    # Traspaso directo / Rebalanceo entre huchas (Fase 7.4)
    eligible_sources = [f for f in funds if float(f.get("current_balance", 0.0)) > 0]
    active_targets = [f for f in funds if f.get("status") == "ACTIVE"]

    with st.expander("↔️ Traspasar Saldo entre Huchas (Rebalanceo)", expanded=False):
        if not eligible_sources:
            st.info("ℹ️ No hay huchas con saldo acumulado disponible para traspasar.")
        elif len(funds) < 2:
            st.info("ℹ️ Necesitas tener al menos dos huchas creadas para realizar un traspaso entre ellas.")
        else:
            # Selector reactivo de origen fuera del form para refrescar destinos dinámicamente
            col_sel_src, col_sel_dest_info = st.columns(2)
            with col_sel_src:
                src_id = st.selectbox(
                    "Hucha de Origen (desde donde sale el saldo)",
                    options=[f["id"] for f in eligible_sources],
                    format_func=lambda fid: next(
                        (f"{f['name']} (Disponible: {float(f.get('current_balance', 0.0)):,.2f} €)" for f in eligible_sources if f["id"] == fid),
                        str(fid),
                    ),
                    key="sel_src_fund_transfer",
                )
            selected_src = next((f for f in eligible_sources if f["id"] == src_id), None)
            max_avail = float(selected_src.get("current_balance", 0.0)) if selected_src else 0.0
            dest_candidates = [f for f in active_targets if f["id"] != src_id]

            with col_sel_dest_info:
                if not dest_candidates:
                    st.warning("No hay otra hucha activa disponible como destino.")
                else:
                    st.caption("Selecciona el importe y la hucha receptora a continuación.")

            if dest_candidates:
                with st.form("transfer_sinking_fund_form", clear_on_submit=True):
                    col_tr1, col_tr2 = st.columns(2)
                    with col_tr1:
                        tr_amount = st.number_input(
                            f"Importe a Traspasar (€, máx {max_avail:,.2f} €)",
                            min_value=0.01,
                            max_value=max(max_avail, 0.01),
                            value=min(50.0, max(max_avail, 0.01)),
                            step=10.0,
                            key="num_amount_fund_transfer",
                        )
                    with col_tr2:
                        dest_id = st.selectbox(
                            "Hucha de Destino (hacia donde entra el saldo)",
                            options=[f["id"] for f in dest_candidates],
                            format_func=lambda fid: next(
                                (f"{f['name']} (Saldo actual: {float(f.get('current_balance', 0.0)):,.2f} €)" for f in dest_candidates if f["id"] == fid),
                                str(fid),
                            ),
                            key="sel_dest_fund_transfer",
                        )
                    tr_notes = st.text_input("Motivo / Notas del Traspaso (Opcional)", placeholder="Ej. Reasignación de viaje cancelado a revisión coche")

                    tr_submitted = st.form_submit_button("↔️ Confirmar Traspaso de Saldo", width="stretch")
                    if tr_submitted:
                        if not dest_id or dest_id == src_id:
                            st.error("⚠️ La hucha de origen y la de destino deben ser distintas.")
                        elif tr_amount <= 0 or tr_amount > max_avail:
                            st.error(f"El importe debe ser mayor a 0 y no superar los {max_avail:,.2f} € disponibles.")
                        else:
                            payload_tr = {
                                "source_fund_id": src_id,
                                "target_fund_id": dest_id,
                                "amount": float(tr_amount),
                                "notes": tr_notes.strip() if tr_notes else None,
                                "created_by_profile": account.get("local_profile", "MEMBER_A"),
                            }
                            res_tr = api_client.transfer_joint_sinking_fund(payload_tr)
                            if res_tr:
                                st.success(f"✅ Se han traspasado {tr_amount:,.2f} € con éxito y se han emitido los deltas de sincronización.")
                                st.rerun()
                            else:
                                st.error("❌ No se pudo completar el traspaso de saldo.")

    st.markdown("### Mis Huchas Activas")
    if not funds:
        st.info("No tienes huchas de amortización activas todavía.")
    else:
        # Renderizar tarjetas visuales de progreso
        cols = st.columns(min(len(funds), 3))
        for idx, f in enumerate(funds):
            col = cols[idx % len(cols)]
            target = max(float(f.get("target_amount", 1.0)), 1.0)
            balance = float(f.get("current_balance", 0.0))
            pct = min(balance / target, 1.0)

            is_completed = (target > 0 and balance >= target)
            with col:
                badge_completed = (
                    " &nbsp; <span style='background: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: 600; font-size: 0.75rem; padding: 2px 8px; border-radius: 4px;'>✅ Completada</span>"
                    if is_completed else ""
                )
                card_border = "#10b981" if is_completed else "#334155"
                st.markdown(
                    f"""
                    <div style="background: #1e293b; border: 1px solid {card_border}; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                        <h4 style="margin: 0 0 6px 0; color: #38bdf8;">🎯 {f.get('name')}{badge_completed}</h4>
                        <p style="font-size: 0.85rem; color: #94a3b8; margin: 0 0 8px 0;">{f.get('description') or 'Sin descripción'}</p>
                        <h3 style="margin: 0; color: #f8fafc;">{balance:,.2f} € <small style="font-size: 0.8rem; color: #64748b;">/ {target:,.2f} €</small></h3>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if is_completed:
                    st.markdown(
                        """
                        <div style="background-color: #334155; border-radius: 6px; height: 10px; width: 100%; overflow: hidden; margin: 6px 0;">
                            <div style="background-color: #10b981; height: 100%; width: 100%;"></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.caption("Progreso: 100.0% | 🎉 ¡Meta cumplida! (0,00 €/mes requeridos)")
                else:
                    st.progress(pct)
                    st.caption(f"Progreso: {pct * 100:.1f}% | Mensual sugerido: {f.get('monthly_target_amount', 0.0):,.2f} €")

        # Acciones de edición / eliminación
        with st.expander("⚙️ Administrar Huchas"):
            fund_to_manage = st.selectbox(
                "Selecciona hucha para editar o eliminar",
                options=[f["id"] for f in funds],
                format_func=lambda id_val: next((f["name"] for f in funds if f["id"] == id_val), str(id_val)),
            )
            selected_f = next((f for f in funds if f["id"] == fund_to_manage), None)

            if selected_f:
                other_funds = [of for of in funds if of["id"] != selected_f["id"]]
                cur_bal = float(selected_f.get("current_balance", 0.0))
                is_pre = (account.get("cohabitation_stage") == "PRE_COHABITATION")

                st.markdown("##### ✏️ Modificar Parámetros de la Hucha")
                col_e1, col_e2 = st.columns(2, gap="medium")
                with col_e1:
                    new_f_balance = st.number_input(
                        "Ajustar Saldo Directo (€)",
                        value=cur_bal,
                        step=25.0,
                        key=f"edit_fund_bal_{selected_f['id']}",
                    )
                with col_e2:
                    st.write("")
                    st.write("")
                    if st.button("💾 Guardar Saldo Actualizado", key=f"btn_save_f_bal_{selected_f['id']}", width="stretch"):
                        api_client.update_joint_sinking_fund(selected_f["id"], {"current_balance": new_f_balance})
                        st.success("Saldo actualizado exitosamente.")
                        st.rerun()

                st.markdown("---")
                st.markdown("##### 🗑️ Eliminar Hucha de Amortización")

                if cur_bal <= 0.0:
                    st.info("ℹ️ Esta hucha tiene un saldo de **0,00 €**. Puedes eliminarla de forma directa y segura.")
                    if st.button("🗑️ Eliminar Hucha Definitivamente", key=f"btn_del_fund_{selected_f['id']}", type="secondary", width="stretch"):
                        ok = api_client.delete_joint_sinking_fund(selected_f["id"])
                        if ok:
                            st.cache_data.clear()
                            st.success("Hucha eliminada exitosamente.")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar la hucha.")
                else:
                    st.warning(
                        f"⚠️ **Saldo Remanente Detectado: {cur_bal:,.2f} €**\n\n"
                        "Para proteger el patrimonio común, queda estrictamente prohibida la eliminación sin definir "
                        "el destino de estos fondos. Selecciona una de las siguientes opciones obligatorias:"
                    )

                    # Cálculo de cuotas para miembros
                    name_a = account.get("member_a_name", "Miembro A")
                    name_b = account.get("member_b_name", "Miembro B")
                    split_mode = account.get("split_mode", "EQUAL_50_50")
                    pct_a = float(account.get("member_a_contribution_pct", 50.0))
                    if split_mode == "EQUAL_50_50":
                        share_a = round(cur_bal * 0.5, 2)
                        share_b = round(cur_bal - share_a, 2)
                    else:
                        share_a = round(cur_bal * (pct_a / 100.0), 2)
                        share_b = round(cur_bal - share_a, 2)

                    # Determinación de opciones según la etapa de convivencia
                    actions_available = []
                    actions_labels = {}

                    if is_pre:
                        # Modo Pre-Convivencia: No hay tesorería general; por defecto devolver a miembros
                        actions_available.append("REFUND_MEMBERS")
                        actions_labels["REFUND_MEMBERS"] = f"💰 Devolver a los Miembros según reparto pactado ({name_a}: {share_a:,.2f} € | {name_b}: {share_b:,.2f} €) [Recomendado]"
                        if other_funds:
                            actions_available.append("REALLOCATE")
                            actions_labels["REALLOCATE"] = "↔️ Reasignar todo el saldo a otra hucha activa"
                    else:
                        # Modo Convivencia: Por defecto liberar a tesorería general del hogar
                        actions_available.append("RELEASE_TO_TREASURY")
                        actions_labels["RELEASE_TO_TREASURY"] = "🏦 Liberar a la Tesorería General del Hogar (Colchón No Asignado para compras comunes) [Recomendado]"
                        if other_funds:
                            actions_available.append("REALLOCATE")
                            actions_labels["REALLOCATE"] = "↔️ Reasignar todo el saldo a otra hucha activa"
                        actions_available.append("REFUND_MEMBERS")
                        actions_labels["REFUND_MEMBERS"] = f"💰 Devolver y Liquidar a los Miembros ({name_a}: {share_a:,.2f} € | {name_b}: {share_b:,.2f} €)"

                    chosen_action = st.radio(
                        "Selecciona el destino del saldo remanente:",
                        options=actions_available,
                        format_func=lambda k: actions_labels[k],
                        key=f"radio_del_action_{selected_f['id']}",
                    )

                    realloc_dest_id = None
                    if chosen_action == "REALLOCATE":
                        realloc_dest_id = st.selectbox(
                            "Selecciona la hucha de destino que recibirá los fondos:",
                            options=[of["id"] for of in other_funds],
                            format_func=lambda fid: next((f"{of['name']} (Saldo actual: {float(of.get('current_balance', 0.0)):,.2f} €)" for of in other_funds if of["id"] == fid), str(fid)),
                            key=f"sel_realloc_dest_{selected_f['id']}",
                        )

                    refund_cb = True
                    if chosen_action == "REFUND_MEMBERS":
                        local_prof = account.get("local_profile", "MEMBER_A")
                        local_share = share_a if local_prof == "MEMBER_A" else share_b
                        refund_cb = st.checkbox(
                            f"Anotar automáticamente un ingreso de reintegro ({local_share:,.2f} €) en mi cuenta personal",
                            value=True,
                            key=f"cb_refund_personal_{selected_f['id']}",
                        )

                    if st.button("🗑️ Confirmar Destino y Eliminar Hucha", key=f"btn_del_fund_confirm_{selected_f['id']}", type="primary", width="stretch"):
                        ok = api_client.delete_joint_sinking_fund(
                            selected_f["id"],
                            reallocate_to_fund_id=realloc_dest_id if chosen_action == "REALLOCATE" else None,
                            action_on_balance=chosen_action,
                            refund_personal_entry=refund_cb if chosen_action == "REFUND_MEMBERS" else False,
                        )
                        if ok:
                            st.cache_data.clear()
                            st.success("Hucha eliminada y saldo remanente reasignado exitosamente.")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar la hucha. Consulta los registros para más información.")

        # Historial de Rebalanceos y Traspasos entre Huchas (Fase 7.4)
        transfers_history = api_client.get_joint_sinking_fund_transfers(limit=50)
        if transfers_history:
            with st.expander(f"📜 Historial de Rebalanceos entre Huchas ({len(transfers_history)})", expanded=False):
                tr_rows = []
                for tr in transfers_history:
                    p_profile = tr.get("created_by_profile")
                    p_name = account.get("member_a_name", "Miembro A") if p_profile == "MEMBER_A" else account.get("member_b_name", "Miembro B")
                    tr_rows.append({
                        "Fecha": _format_date_es(tr.get("date")),
                        "Origen": tr.get("source_fund_name") or f"Hucha #{tr.get('source_fund_id')}",
                        "Destino": tr.get("target_fund_name") or f"Hucha #{tr.get('target_fund_id')}",
                        "Importe (€)": f"{float(tr.get('amount', 0.0)):,.2f} €",
                        "Motivo / Notas": tr.get("notes") or "—",
                        "Registrado Por": p_name,
                    })
                df_tr = pd.DataFrame(tr_rows)
                st.dataframe(df_tr, width="stretch")


# =====================================================================
# TAB 4: BUSCADOR GLOBAL Y FILTRO MULTICRITERIO DE GASTOS COMUNES

