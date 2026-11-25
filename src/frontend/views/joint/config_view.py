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


def _render_tab_configuracion(account: Dict[str, Any], sync_status: Dict[str, Any]) -> None:
    """Pestaña de sincronización Syncthing descentralizada y configuración del hogar."""
    st.subheader("⚙️ Configuración del Hogar y Sincronización")

    st.markdown("### Estado de Sincronización P2P (Syncthing)")
    st.markdown(
        """
        La sincronización funciona mediante archivos delta cifrados compartidos a través de carpetas locales de **Syncthing**
        (`sync/outbox/` e `sync/inbox/`), sin necesidad de servidores centrales ni exponer bases de datos.
        """
    )

    col_s1, col_s2, col_s3 = st.columns(3)
    is_synced = sync_status.get("is_synchronized", True)
    with col_s1:
        st.metric("Estado General", "🟢 Sincronizado" if is_synced else "🟡 Pendiente")
    with col_s2:
        st.metric("Deltas en Outbox", sync_status.get("outbox_pending_count", 0))
    with col_s3:
        st.metric("Deltas en Inbox", sync_status.get("inbox_pending_count", 0))

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Procesar Bandeja de Entrada Ahora (Inbox)", width="stretch"):
            with st.spinner("Procesando deltas entrantes de Syncthing..."):
                res = api_client.trigger_process_inbox()
                processed = res.get("processed_count", 0)
                ignored = res.get("ignored_count", 0)
                st.success(f"Procesamiento finalizado. Eventos aplicados: {processed}, Ignorados por idempotencia: {ignored}.")
                st.rerun()
    with col_btn2:
        if st.button("📤 Reenviar Invitación a mi Pareja", width="stretch"):
            with st.spinner("Regenerando invitación del hogar en Outbox..."):
                if api_client.resend_joint_invitation():
                    st.success("¡Invitación regenerada en Outbox! Syncthing la enviará a tu pareja.")
                    st.rerun()
                else:
                    st.error("Error al reenviar la invitación.")


    # Visor Avanzado de Sincronización y Registro de Eventos
    with st.expander("🔍 Visor Avanzado de Sincronización y Registro de Eventos", expanded=False):
        sync_detail = api_client.get_joint_sync_events_detail()
        if sync_detail:
            col_v1, col_v2, col_v3, col_v4 = st.columns(4)
            with col_v1:
                st.metric("Outbox (Salida)", sync_detail.get("outbox_count", 0))
            with col_v2:
                st.metric("Inbox (Entrada)", sync_detail.get("inbox_count", 0))
            with col_v3:
                st.metric("Archivados (Processed)", sync_detail.get("processed_count", 0))
            with col_v4:
                err_c = sync_detail.get("error_count", 0)
                st.metric("Eventos en Error", err_c, delta="⚠️ Requiere atención" if err_c > 0 else None, delta_color="inverse")

            if st.button(
                "🔄 Sincronizar Ahora (Forzar Inbox)",
                key="btn_sync_now_viewer",
                width="stretch",
                help="Fuerza el escaneo y procesamiento inmediato de los ficheros de cambio recibidos en la bandeja de entrada (inbox/) de Syncthing, aplicando al instante los movimientos de tu pareja sin esperar al ciclo automático.",
            ):
                with st.spinner("Procesando deltas de entrada..."):
                    res_s = api_client.trigger_process_inbox()
                    st.toast("Sincronización procesada.")
                    st.rerun()

            if err_c > 0:
                col_btn_err1, col_btn_err2 = st.columns(2)
                with col_btn_err1:
                    if st.button("🔁 Reintentar Eventos en Error", key="btn_retry_errors_viewer", type="primary", width="stretch"):
                        with st.spinner("Reintentando eventos en error..."):
                            res_r = api_client.retry_joint_sync_errors()
                            cnt = res_r.get("retried_count", 0) if res_r else 0
                            st.success(f"Se han reintentado {cnt} eventos.")
                            st.rerun()
                with col_btn_err2:
                    if st.button("🗑️ Descartar y Limpiar Errores", key="btn_clear_errors_viewer", width="stretch"):
                        with st.spinner("Eliminando eventos en error..."):
                            res_c = api_client.clear_joint_sync_errors()
                            cnt_c = res_c.get("deleted_count", 0) if res_c else 0
                            st.success(f"Se han eliminado {cnt_c} eventos en error. Sincronización restaurada.")
                            st.rerun()

                st.markdown("#### ⚠️ Eventos en Error")
                for ef in sync_detail.get("error_events", []):
                    st.error(f"**Archivo**: `{ef.get('filename')}`\n\n```\n{ef.get('preview')}\n```")

            st.markdown("#### 📋 Últimos Eventos Procesados")
            proc_evs = sync_detail.get("processed_events", [])
            if proc_evs:
                entity_map = {
                    "TRANSACTION": "Gasto Común",
                    "CONTRIBUTION": "Aportación",
                    "SINKING_FUND": "Hucha de Amortización",
                    "SINKING_FUND_TRANSFER": "Traspaso entre Huchas",
                    "SUBCATEGORY": "Subcategoría",
                    "ACCOUNT": "Configuración Hogar",
                    "SETTLEMENT": "Liquidación",
                }
                action_map = {
                    "UPSERT": "Guardar / Modificar",
                    "DELETE": "Eliminar",
                }
                formatted_events = []
                for ev in proc_evs:
                    raw_ent = ev.get("entity_type", "")
                    raw_act = ev.get("action", "")
                    raw_ts = ev.get("timestamp_utc", "")
                    formatted_ts = "—"
                    if raw_ts:
                        try:
                            clean_iso = raw_ts.replace("Z", "+00:00")
                            dt_val = datetime.fromisoformat(clean_iso)
                            formatted_ts = dt_val.strftime("%d/%m/%Y %H:%M:%S")
                        except Exception:
                            formatted_ts = raw_ts[:19].replace("T", " ")
                    formatted_events.append({
                        "Tipo": entity_map.get(raw_ent, raw_ent),
                        "Acción": action_map.get(raw_act, raw_act),
                        "Fecha": formatted_ts,
                    })
                df_evs = pd.DataFrame(formatted_events)
                st.dataframe(df_evs[["Tipo", "Acción", "Fecha"]], width="stretch", hide_index=True)
            else:
                st.caption("No hay eventos archivados en processed/ aún.")

    # Exportación Consolidada del Hogar a Excel
    st.markdown("<hr style='margin: 20px 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)
    st.markdown("### 📥 Exportación Consolidada del Hogar")
    st.markdown(
        "Descarga un archivo Excel (.xlsx) estructurado con 3 pestañas conteniendo el histórico completo de "
        "gastos comunes, aportaciones de los miembros y estado de las huchas de amortización."
    )
    st.download_button(
        label="📥 Descargar Datos del Hogar en Excel (.xlsx)",
        data=lambda: api_client.export_joint_excel() or b"",
        file_name=f"finanzas_hogar_completo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="content",
        key="download_excel_config_tab",
    )

    # EXPANDER: GESTIÓN DE SUBCATEGORÍAS DEL HOGAR (SPEC-015)
    # RF-5: Si la cuenta está en Pre-Convivencia, los gastos de vivienda no aplican y el expander no se muestra.
    is_pre_cohabitation = account.get("cohabitation_stage") in ("PRE_COHABITATION", "DATING_COHABITATION")
    if not is_pre_cohabitation:
        st.markdown("<hr style='margin: 25px 0 15px 0;'>", unsafe_allow_html=True)
        with st.expander("🏷️ Administrar Subcategorías del Hogar", expanded=False):
            st.markdown("#### ➕ Añadir Nueva Subcategoría de Necesidades Comunes")
            st.caption("Crea nuevos conceptos para clasificar los gastos compartidos del piso o la familia.")

            joint_cats = api_client.get_joint_categories()
            joint_subcats = api_client.get_joint_subcategories()
            if not joint_cats:
                st.info("No hay categorías principales del hogar configuradas.")
            else:
                with st.form("form_alta_subcat_hogar", clear_on_submit=True):
                    col_jc_cat, col_jc_nom, col_jc_bud = st.columns([1.5, 2, 1.2])
                    with col_jc_cat:
                        sel_jcat = st.selectbox(
                            "Categoría del Hogar",
                            options=joint_cats,
                            format_func=lambda c: c.get("name", "Gastos Comunes"),
                            key="sel_joint_subcat_parent"
                        )
                    with col_jc_nom:
                        new_jsub_name = st.text_input(
                            "Nombre del Concepto",
                            placeholder="Ej: Artículos de limpieza, Mascotas...",
                            key="txt_new_joint_subcat_name"
                        )
                    with col_jc_bud:
                        new_jsub_budget = st.number_input(
                            "Presupuesto Mensual (€)",
                            min_value=0.0,
                            value=0.0,
                            step=10.0,
                            key="num_new_joint_subcat_budget"
                        )

                    btn_add_jsub = st.form_submit_button("💾 Guardar Subcategoría del Hogar", width="stretch")
                    if btn_add_jsub:
                        cleaned_jname = new_jsub_name.strip()
                        if not cleaned_jname:
                            st.warning("⚠️ Debes indicar un nombre para la subcategoría.")
                        else:
                            existing_jnames = [js.get("name", "").strip().lower() for js in joint_subcats]
                            if cleaned_jname.lower() in existing_jnames:
                                st.warning(f"⚠️ Ya existe una subcategoría con el nombre '{cleaned_jname}' en los gastos del hogar.")
                            else:
                                created_jsub = api_client.create_joint_subcategory(
                                    name=cleaned_jname,
                                    joint_category_id=sel_jcat["id"],
                                    monthly_budget=new_jsub_budget
                                )
                                if created_jsub:
                                    st.success(f"✅ ¡Subcategoría '{cleaned_jname}' creada exitosamente y propagada a la pareja!")
                                    st.rerun()
                                else:
                                    st.error("❌ No se pudo crear la subcategoría conjunta. Es posible que ya exista o que la pareja la haya registrado.")

            st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown("#### 📋 Subcategorías de Necesidades Registradas")
            st.caption("Puedes modificar el nombre, presupuesto mensual estimado o eliminar subcategorías libres de transacciones.")
            if not joint_subcats:
                st.info("Aún no se han configurado subcategorías para el hogar.")
            else:
                for js in joint_subcats:
                    js_id = js["id"]
                    js_name = js.get("name", "")
                    js_budget = float(js.get("monthly_budget", 0.0) or 0.0)
                    is_base = is_default_joint_subcategory(js_name)

                    col_jinfo, col_jedit, col_jdel = st.columns([3, 1, 1])
                    with col_jinfo:
                        badge_jbase = " &nbsp; <span style='background: rgba(148, 163, 184, 0.15); color: #94a3b8; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;'>Base</span>" if is_base else ""
                        st.markdown(f"**{js_name}**{badge_jbase} &nbsp; <span style='color: #64748b; font-size: 0.85rem;'>[{js_budget:.2f} €/mes]</span>", unsafe_allow_html=True)

                    with col_jedit:
                        with st.popover("✏️ Editar", key=f"pop_edit_joint_{js_id}"):
                            st.markdown(f"**Editar '{js_name}'**")
                            if is_base:
                                st.caption("🔒 El nombre de este concepto base no se puede modificar.")
                                edit_name = js_name
                            else:
                                edit_name = st.text_input("Nombre:", value=js_name, key=f"inp_edit_jname_{js_id}")
                            edit_bud = st.number_input("Presupuesto (€):", min_value=0.0, value=js_budget, step=10.0, key=f"inp_edit_jbud_{js_id}")
                            if st.button("Guardar Cambios", key=f"btn_confirm_jedit_{js_id}"):
                                if edit_name.strip():
                                    res_jupd = api_client.update_joint_subcategory(
                                        js_id,
                                        name=edit_name.strip(),
                                        monthly_budget=edit_bud
                                    )
                                    if res_jupd:
                                        st.success("✅ Subcategoría actualizada y propagada.")
                                        st.rerun()
                                    else:
                                        st.error("❌ Error al actualizar la subcategoría conjunta.")
                                else:
                                    st.warning("El nombre no puede estar vacío.")

                    if not is_base:
                        with col_jdel:
                            with st.popover("🗑️ Eliminar", key=f"pop_del_joint_{js_id}"):
                                st.markdown(f"**Eliminar '{js_name}'**")
                                st.warning("Solo se eliminará si no contiene transacciones comunes vinculadas.")
                                if st.button("Confirmar Borrado", key=f"btn_confirm_jdel_{js_id}", type="primary"):
                                    ok_jdel, msg_jdel = api_client.delete_joint_subcategory(js_id)
                                    if ok_jdel:
                                        st.success(f"✅ {msg_jdel}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {msg_jdel}")

    st.markdown("<hr style='margin: 20px 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)
    with st.expander("⚙️ Parámetros de la Cuenta Conjunta", expanded=False):
        new_acc_name = st.text_input("Nombre del Hogar", value=account.get("household_name") or account.get("account_name", ""), key="joint_cfg_acc_name")

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            new_mem_a = st.text_input("Nombre Miembro A", value=account.get("member_a_name", "Miembro A"), key="joint_cfg_mem_a")
            new_inc_a = st.number_input(
                "Salario de Referencia Miembro A (€)",
                min_value=0.0,
                value=float(account.get("member_a_reference_income") or account.get("member_a_estimated_income", 0.0)),
                step=50.0,
                key="joint_cfg_inc_a",
            )

        with col_p2:
            new_mem_b = st.text_input("Nombre Miembro B", value=account.get("member_b_name", "Miembro B"), key="joint_cfg_mem_b")
            new_inc_b = st.number_input(
                "Salario de Referencia Miembro B (€)",
                min_value=0.0,
                value=float(account.get("member_b_reference_income") or account.get("member_b_estimated_income", 0.0)),
                step=50.0,
                key="joint_cfg_inc_b",
            )

        col_p3, col_p4 = st.columns(2)
        with col_p3:
            current_split = account.get("split_mode", "EQUAL_50_50")
            split_idx = 0 if "50" in str(current_split) else 1
            new_split_choice = st.selectbox(
                "Modo de Reparto",
                ["Al 50% cada uno (EQUAL_50_50)", "Proporcional a Ingresos Netos (INCOME_PROPORTIONAL)"],
                index=split_idx,
                key="joint_cfg_split",
            )
            new_split = "EQUAL_50_50" if "50%" in new_split_choice else "INCOME_PROPORTIONAL"

        with col_p4:
            current_cohab = account.get("cohabitation_stage", "PRE_COHABITATION")
            cohab_idx = 0 if "PRE" in str(current_cohab) or "DATING" in str(current_cohab) else 1
            new_cohab_choice = st.selectbox(
                "Etapa de Convivencia",
                ["Pre-Convivencia / Viviendo Separados (PRE_COHABITATION)", "Convivencia Plena / Compartiendo Hogar (COHABITATION)"],
                index=cohab_idx,
                key="joint_cfg_cohab",
            )
            new_cohab = "PRE_COHABITATION" if "Pre" in new_cohab_choice else "COHABITATION"

        col_strat1, col_strat2 = st.columns(2)
        with col_strat1:
            current_strat = account.get("contribution_strategy", "NOMINAL_TEMPLATE")
            strat_idx = 1 if current_strat == "GLOBAL_FIXED" else 0
            strat_options = [
                "Calculado por Conceptos (Necesidades + Huchas)",
                "Presupuesto Fijo Global (Manual)",
            ]
            new_strat_choice = st.selectbox(
                "Cálculo del Presupuesto del Hogar",
                strat_options,
                index=strat_idx,
                key="joint_cfg_strat",
                help="Determina si el presupuesto mensual total del hogar se calcula sumando los conceptos o se fija un importe global.",
            )
            new_strat = "GLOBAL_FIXED" if "Global" in new_strat_choice else "NOMINAL_TEMPLATE"

        with col_strat2:
            if new_strat == "GLOBAL_FIXED":
                new_custom_budget = st.number_input(
                    "Cantidad Total a Aportar cada Mes (€)",
                    min_value=0.0,
                    value=float(account.get("custom_total_monthly_budget", 0.0) or 0.0),
                    step=50.0,
                    key="joint_cfg_custom_budget",
                    help="Importe global mensual presupuestado para el hogar. Se repartirá entre ambos miembros según el Modo de Reparto seleccionado.",
                )
            else:
                new_custom_budget = 0.0
                st.info("ℹ️ El presupuesto total se calcula sumando el presupuesto de necesidades más las cuotas de huchas activas no cumplidas.")

        acc_saved = st.button("💾 Guardar Cambios de Configuración", type="primary", width="stretch", key="btn_save_joint_cfg")
        if acc_saved:
            payload_acc = {
                "household_name": new_acc_name.strip(),
                "member_a_name": new_mem_a.strip(),
                "member_b_name": new_mem_b.strip(),
                "member_a_reference_income": float(new_inc_a),
                "member_b_reference_income": float(new_inc_b),
                "split_mode": new_split,
                "cohabitation_stage": new_cohab,
                "contribution_strategy": new_strat,
                "custom_total_monthly_budget": float(new_custom_budget),
            }
            res_upd = api_client.update_joint_account(payload_acc)
            if res_upd:
                st.success("✅ Configuración del hogar actualizada correctamente.")
                st.rerun()
            else:
                st.error("❌ Error al actualizar los parámetros de la cuenta conjunta.")

    st.markdown("<hr style='margin: 30px 0 20px 0; border: 0; border-top: 1px solid #7f1d1d;'>", unsafe_allow_html=True)
    with st.expander("🚨 Zona de Peligro: Desactivar Cuenta Conjunta y Regresar a Estado Cero"):
        st.markdown(
            """
            <div style="background: rgba(127, 29, 29, 0.2); border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <p style="color: #fca5a5; font-size: 0.95rem; margin: 0 0 8px 0; font-weight: 600;">
                    ⚠️ Acción Destructiva para el Espacio Compartido
                </p>
                <p style="color: #cbd5e1; font-size: 0.85rem; margin: 0;">
                    Esta acción purgará los datos de la cuenta conjunta, categorías compartidas, transacciones comunes,
                    huchas del hogar y vaciará las bandejas de sincronización (outbox/inbox).<br>
                    <b>Tus datos personales (transacciones individuales, categorías privadas y fondos de seguridad) permanecerán intactos y a salvo.</b>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        confirm_reset = st.checkbox(
            "Entiendo que esta acción desactivará la cuenta conjunta en este equipo y la devolverá al Estado Inicial.",
            key="chk_confirm_reset",
        )

        if st.button(
            "🗑️ Desactivar Cuenta Conjunta y Volver al Estado Cero",
            type="primary",
            disabled=not confirm_reset,
            width="stretch",
            key="btn_danger_reset",
        ):
            with st.spinner("Purgando cuenta conjunta y limpiando sincronización..."):
                ok = api_client.reset_joint_account()
                if ok:
                    api_client.clear_joint_cache()
                    api_client.clear_annual_cache()
                    st.cache_data.clear()
                    st.success("✅ Cuenta conjunta desactivada con éxito. Volviendo al estado inicial...")
                    st.rerun()
                else:
                    st.error("❌ Error al purgar la cuenta conjunta en el servidor.")


# =====================================================================
# BANNER ASISTIDO DE APORTACIONES CRUZADAS EN PERFIL PERSONAL (FASE 7.5)

