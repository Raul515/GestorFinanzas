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


def _render_tab_resumen_anual(selected_year: int, account: Dict[str, Any]) -> None:
    """
    Renderiza el Resumen Anual consolidado de la unidad familiar.
    Regla innegociable: no incluye comparativas de quién aportó más (Miembro A vs Miembro B).
    """
    col_rh1, col_rh2 = st.columns([3, 1])
    with col_rh1:
        st.subheader(f"Resumen Consolidado del Hogar - Año {selected_year}")
    with col_rh2:
        st.download_button(
            label="📥 Exportar a Excel (.xlsx)",
            data=lambda: api_client.export_joint_excel() or b"",
            file_name=f"finanzas_hogar_{selected_year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key=f"download_excel_annual_{selected_year}",
        )

    annual_summary = api_client.get_joint_annual_summary(year=selected_year)
    if not annual_summary:
        st.info("No se pudieron cargar las métricas anuales del hogar para este año.")
        return

    needs_spent = annual_summary.get("total_needs_spent", 0.0)
    sinking_saved = annual_summary.get("total_sinking_funds_saved", 0.0)
    effort_rate = annual_summary.get("effort_rate_pct", 0.0)
    health_status = annual_summary.get("health_status", "SUSTAINABLE")

    # RF-8: Diagnóstico Inmediato de Salud Financiera y Tasa de Esfuerzo en Cabecera Superior
    if health_status == "SUSTAINABLE":
        st.success(
            f"🟢 **Hogar Sostenible (Tasa de Esfuerzo: {effort_rate:.1f}%)**: "
            "La carga de gastos esenciales no asfixia la economía familiar (≤ 50% de los ingresos combinados), permitiendo dotar huchas y ahorrar con holgura."
        )
    elif health_status == "TENSION":
        st.warning(
            f"🟡 **Zona de Tensión Moderada (Tasa de Esfuerzo: {effort_rate:.1f}%)**: "
            "Los gastos fijos del hogar absorben entre el 50% y el 60% de los ingresos combinados. Conviene vigilar desviaciones en facturas y suministros."
        )
    else:
        st.error(
            f"🔴 **Alerta Crítica de Sobreesfuerzo (Tasa de Esfuerzo: {effort_rate:.1f}%)**: "
            "La tasa de esfuerzo supera el umbral de seguridad constitucional del 60%. Se recomienda auditar los suministros y renegociar contratos de vivienda o seguros."
        )

    # Tarjetas de Métricas Principales (3 Columnas)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="Total Necesidades Comunes",
            value=f"{needs_spent:,.2f} €",
            help="Gasto total del año en vivienda, luz, agua, supermercado y seguros del hogar.",
        )

    with col2:
        st.metric(
            label="Total Ahorrado en Huchas",
            value=f"{sinking_saved:,.2f} €",
            help="Progreso acumulado en las huchas de amortización conjuntas.",
        )

    with col3:
        if health_status == "SUSTAINABLE":
            st.metric(
                label="Tasa de Esfuerzo Familiar",
                value=f"{effort_rate:.1f} %",
                delta="🟢 Saludable (≤ 50%)",
                delta_color="normal",
                help="Porcentaje de los ingresos del hogar destinados a necesidades comunes.",
            )
        elif health_status == "TENSION":
            st.metric(
                label="Tasa de Esfuerzo Familiar",
                value=f"{effort_rate:.1f} %",
                delta="🟡 Tensión Moderada (50% - 60%)",
                delta_color="inverse",
                help="Los costes fijos comprometen el ahorro individual.",
            )
        else:
            st.metric(
                label="Tasa de Esfuerzo Familiar",
                value=f"{effort_rate:.1f} %",
                delta="🔴 Alerta Crítica (> 60%)",
                delta_color="inverse",
                help="Riesgo de sobrecarga financiera estructural en el hogar.",
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📊 Evolución Mensual: Aportaciones vs Destino (Necesidades y Ahorro)")

    # Gráfica visual con Altair
    monthly_metrics = annual_summary.get("monthly_metrics", [])
    if monthly_metrics:
        records = []
        for item in monthly_metrics:
            m_key = item.get("month", "")
            try:
                m_num = int(m_key.split("-")[1])
                m_name = MESES_ES[m_num - 1][:3]
            except Exception:
                m_name = m_key
                m_num = 1

            needs_spent = float(item.get("needs_spent", 0.0))
            total_contributed = float(item.get("total_contributed", item.get("contributed", 0.0)))
            sinking_allocated = float(item.get("sinking_allocated", 0.0))
            surplus = max(0.0, round(total_contributed - needs_spent, 2))
            unassigned_amount = float(
                item.get(
                    "unassigned_amount",
                    max(0.0, round(surplus - sinking_allocated, 2)),
                )
            )

            # Columna 1: Aportaciones Recibidas
            records.append({
                "Mes": m_name,
                "Columna": "1. Aportaciones",
                "Concepto": "Aportaciones Recibidas",
                "Importe": total_contributed,
                "Mes_Num": m_num,
                "Stack_Order": 1,
            })
            # Columna 2: Destino (Necesidades Comunes + Ahorro en Huchas + Remanente Sin Asignar)
            records.append({
                "Mes": m_name,
                "Columna": "2. Destino",
                "Concepto": "Necesidades Comunes",
                "Importe": needs_spent,
                "Mes_Num": m_num,
                "Stack_Order": 1,
            })
            records.append({
                "Mes": m_name,
                "Columna": "2. Destino",
                "Concepto": "Ahorro en Huchas",
                "Importe": sinking_allocated,
                "Mes_Num": m_num,
                "Stack_Order": 2,
            })
            records.append({
                "Mes": m_name,
                "Columna": "2. Destino",
                "Concepto": "Remanente Sin Asignar",
                "Importe": unassigned_amount,
                "Mes_Num": m_num,
                "Stack_Order": 3,
            })

        df_chart = pd.DataFrame(records)
        chart = (
            alt.Chart(df_chart)
            .mark_bar()
            .encode(
                x=alt.X("Mes:N", sort=alt.SortField("Mes_Num"), title=None),
                xOffset=alt.XOffset("Columna:N", sort=["1. Aportaciones", "2. Destino"], title=None),
                y=alt.Y("Importe:Q", stack="zero", title="Euros (€)"),
                color=alt.Color(
                    "Concepto:N",
                    scale=alt.Scale(
                        domain=[
                            "Aportaciones Recibidas",
                            "Necesidades Comunes",
                            "Ahorro en Huchas",
                            "Remanente Sin Asignar",
                        ],
                        range=["#10b981", "#3b82f6", "#06b6d4", "#64748b"],
                    ),
                    legend=alt.Legend(title="Concepto", orient="top"),
                ),
                order=alt.Order("Stack_Order:Q", sort="ascending"),
                tooltip=[
                    alt.Tooltip("Mes:N", title="Mes"),
                    alt.Tooltip("Concepto:N", title="Concepto"),
                    alt.Tooltip("Importe:Q", format=",.2f", title="Importe (€)"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Aún no hay transacciones suficientes registradas en el año para generar la gráfica comparativa.")


# =====================================================================
# TAB 2: 12 MESES DEL HOGAR
# =====================================================================

def _render_tab_12_meses(selected_year: int, account: Dict[str, Any]) -> None:
    """Pestaña mensual de tesorería, registro de gastos comunes y listado de transacciones."""
    # RF-6: Navegación mensual ágil en 1 clic sincronizada
    if "joint_active_month" not in st.session_state:
        st.session_state["joint_active_month"] = MESES_ES[min(max(datetime.now().month - 1, 0), 11)]

    col_nav_prev, col_nav_sel, col_nav_next, _ = st.columns([1.2, 2.6, 1.2, 3.0])
    with col_nav_prev:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("◀ Mes Anterior", width="stretch", key="btn_joint_prev_month", help="Ir al mes anterior"):
            cur_idx = MESES_ES.index(st.session_state["joint_active_month"])
            st.session_state["joint_active_month"] = MESES_ES[(cur_idx - 1) % 12]
            st.rerun()

    with col_nav_sel:
        cur_idx = MESES_ES.index(st.session_state["joint_active_month"])
        selected_month_name = st.selectbox(
            "Mes a Gestionar",
            MESES_ES,
            index=cur_idx,
            key=f"sel_joint_month_display_{cur_idx}",
        )
        if selected_month_name != st.session_state["joint_active_month"]:
            st.session_state["joint_active_month"] = selected_month_name
            st.rerun()
        month_idx = MESES_ES.index(selected_month_name) + 1
        month_str = f"{selected_year}-{month_idx:02d}"

    with col_nav_next:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Mes Siguiente ▶", width="stretch", key="btn_joint_next_month", help="Ir al mes siguiente"):
            cur_idx = MESES_ES.index(st.session_state["joint_active_month"])
            st.session_state["joint_active_month"] = MESES_ES[(cur_idx + 1) % 12]
            st.rerun()
    transactions = api_client.get_joint_transactions(year=selected_year, month=month_str)
    contributions = api_client.get_joint_contributions(year=selected_year, month=month_str)

    total_contrib = sum(float(c.get("amount", 0.0)) for c in contributions)
    total_spent = sum(float(t.get("amount", 0.0)) for t in transactions)
    net_treasury = total_contrib - total_spent

    # Métricas del mes
    st.markdown(f"### Tesorería del Hogar - {selected_month_name} {selected_year}")
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.metric("Aportaciones Recibidas", f"{total_contrib:,.2f} €")
    with col_t2:
        st.metric("Gastos Comunes Ejecutados", f"{total_spent:,.2f} €")
    with col_t3:
        st.metric(
            "Flujo Neto del Mes",
            f"{net_treasury:,.2f} €",
            delta=f"{net_treasury:,.2f} €",
        )

    # Resumen y Liquidación de Gastos Adelantados con Tarjeta Personal (Fase 7.3)
    settlement_data = api_client.get_joint_settlement_summary()
    if settlement_data and settlement_data.get("unsettled_count", 0) > 0:
        unsettled_n = settlement_data.get("unsettled_count", 0)
        common_reimb = settlement_data.get("common_reimbursement", {})
        direct_settle = settlement_data.get("direct_settlement", {})
        total_common_debt = float(common_reimb.get("total_common_debt", 0.0))
        net_amount = float(direct_settle.get("net_amount", 0.0))

        st.markdown(
            """
            <div style="background-color: #1e293b; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 6px; margin: 14px 0 10px 0;">
                <span style="font-weight: 600; color: #fbbf24; font-size: 1.05rem;">💳 Gastos Adelantados con Tarjeta Personal Pendientes de Liquidar</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_s1, col_s2, col_s3 = st.columns([2, 2, 2])
        with col_s1:
            name_a = account.get("member_a_name", "Miembro A")
            name_b = account.get("member_b_name", "Miembro B")
            owes_a = float(common_reimb.get("owes_member_a", 0.0))
            owes_b = float(common_reimb.get("owes_member_b", 0.0))
            st.metric(
                "Fondo Común Adeuda",
                f"{total_common_debt:,.2f} €",
                help=f"Deuda de la cuenta común hacia los miembros:\n- {name_a}: {owes_a:,.2f} €\n- {name_b}: {owes_b:,.2f} €",
            )
            if total_common_debt > 0:
                st.caption(f"A devolver: {name_a}: **{owes_a:,.2f} €** | {name_b}: **{owes_b:,.2f} €**")

        with col_s2:
            if net_amount > 0:
                debtor_prof = direct_settle.get("net_debtor")
                creditor_prof = direct_settle.get("net_creditor")
                debtor_name = account.get("member_a_name" if debtor_prof == "MEMBER_A" else "member_b_name", debtor_prof)
                creditor_name = account.get("member_a_name" if creditor_prof == "MEMBER_A" else "member_b_name", creditor_prof)
                st.metric(
                    "Compensación Directa (Bizum)",
                    f"{net_amount:,.2f} €",
                    help=f"{debtor_name} debe transferir {net_amount:,.2f} € a {creditor_name} para saldar compras compartidas.",
                )
                st.caption(f"📲 **{debtor_name}** debe abonar a **{creditor_name}**")
            else:
                st.metric("Compensación Directa (Bizum)", "0,00 €")
                st.caption("Saldos directos entre miembros equilibrados")

        with col_s3:
            st.write("")
            if st.button(f"💸 Liquidar Todo ({unsettled_n} pendientes)", width="stretch", key=f"btn_settle_all_{selected_month_name}"):
                ok_settle = api_client.settle_all_joint_transactions()
                if ok_settle:
                    st.success("✅ Todos los gastos adelantados han sido liquidados y reembolsados.")
                    st.rerun()
                else:
                    st.error("No se pudo liquidar el saldo pendiente.")

    st.markdown("<hr style='margin: 16px 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)

    # RF-7: Disposición Simétrica de Acciones de Entrada (Gasto Común vs Aportación)
    col_act_gasto, col_act_aport = st.columns(2)

    with col_act_gasto:
        # Formulario para registrar nuevo gasto común
        is_pre_cohabitation = account.get("cohabitation_stage") in ("PRE_COHABITATION", "DATING_COHABITATION")
        with st.expander(f"🛒 Registrar Gasto Común ({selected_month_name})", expanded=False):
            subcategories = api_client.get_joint_subcategories()
            sinking_funds = api_client.get_joint_sinking_funds(status="ACTIVE")

            subcat_map = {s["id"]: s["name"] for s in subcategories} if subcategories else {}
            fund_map = {f["id"]: f["name"] for f in sinking_funds} if sinking_funds else {}

            if is_pre_cohabitation:
                charge_type = "Cargo a Hucha de Amortización"
                st.info(
                    "ℹ️ **Modo Pre-Convivencia Activo**: Los gastos comunes de vivienda están desactivados "
                    "porque aún no compartís domicilio. Todo gasto común se imputa a una Hucha de Amortización."
                )
            else:
                charge_type = st.radio(
                    "Tipo de Imputación",
                    options=["Necesidad Común del Hogar", "Cargo a Hucha de Amortización"],
                    horizontal=True,
                    key=f"charge_type_{selected_month_name}",
                    help="Define si este gasto se financia con el presupuesto mensual ordinario o si se descuenta de una hucha.",
                )

            # Formulario reactivo y dinámico (sin st.form para actualización inmediata de saldos y sobregastos)
            tx_desc = st.text_input(
                "Concepto / Descripción",
                placeholder="Ej. Factura Luz, Compra Semanal, Aceite...",
                key=f"tx_desc_{selected_month_name}",
            )
            col_amt, col_dt = st.columns(2)
            with col_amt:
                tx_amount = st.number_input(
                    "Importe (€)",
                    min_value=0.01,
                    value=40.0,
                    step=5.0,
                    key=f"tx_amount_{selected_month_name}",
                )
            with col_dt:
                tx_date = st.date_input(
                    "Fecha",
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key=f"tx_date_{selected_month_name}",
                )

            chosen_subcat_id = None
            chosen_fund_id = None
            selected_fund_obj = None
            confirm_overdraft = False

            if charge_type == "Necesidad Común del Hogar":
                if subcat_map:
                    chosen_subcat_id = st.selectbox(
                        "Subcategoría de Necesidades",
                        options=list(subcat_map.keys()),
                        format_func=lambda k: subcat_map[k],
                        key=f"tx_subcat_{selected_month_name}",
                    )
                else:
                    st.caption("No hay subcategorías disponibles.")
            else:
                if fund_map:
                    chosen_fund_id = st.selectbox(
                        "Hucha a Cargar (se descontará de su saldo)",
                        options=list(fund_map.keys()),
                        format_func=lambda k: fund_map[k],
                        key=f"tx_fund_{selected_month_name}",
                    )
                    selected_fund_obj = next((f for f in sinking_funds if f["id"] == chosen_fund_id), None)
                    fund_balance = float(selected_fund_obj.get("current_balance", 0.0)) if selected_fund_obj else 0.0
                    st.caption(f"Saldo disponible en esta hucha: **{fund_balance:,.2f} €**")
                    has_overdraft = (fund_balance < float(tx_amount))
                    confirm_overdraft = False
                    if has_overdraft:
                        diff_treasury = float(tx_amount) - fund_balance
                        st.warning(
                            f"⚠️ **Sobregasto Detectado**\n\n"
                            f"El importe (**{tx_amount:,.2f} €**) supera el saldo (**{fund_balance:,.2f} €**).\n"
                            f"La diferencia de **{diff_treasury:,.2f} €** será absorbida por la tesorería común."
                        )
                        confirm_overdraft = st.checkbox(
                            "Confirmo el sobregasto y autorizo que la diferencia sea absorbida por la tesorería común",
                            key=f"confirm_overdraft_{selected_month_name}",
                        )
                else:
                    st.warning("⚠️ No hay huchas activas creadas. Crea una en '🎯 Huchas de Amortización'.")

            paid_options = ["COMMON", "MEMBER_A", "MEMBER_B"]
            paid_labels = {
                "COMMON": "💳 Cuenta Bancaria Común del Hogar",
                "MEMBER_A": f"👤 {account.get('member_a_name', 'Miembro A')} (Adelantado con tarjeta personal)",
                "MEMBER_B": f"👤 {account.get('member_b_name', 'Miembro B')} (Adelantado con tarjeta personal)",
            }
            paid_choice = st.selectbox(
                "Medio de Pago / Pagado Por",
                options=paid_options,
                index=0,
                format_func=lambda k: paid_labels[k],
                key=f"tx_paid_{selected_month_name}",
                help="Por defecto sale del presupuesto común del hogar. Si uno de los dos adelantó el dinero de su bolsillo, indícalo aquí.",
            )
            settlement_mech = "COMMON_REIMBURSEMENT"
            if paid_choice in ("MEMBER_A", "MEMBER_B"):
                settlement_mech = st.selectbox(
                    "Modalidad de Liquidación / Reembolso",
                    options=["COMMON_REIMBURSEMENT", "DIRECT_MEMBER_SETTLEMENT"],
                    format_func=lambda m: (
                        "🏦 Reembolso desde Cuenta Común"
                        if m == "COMMON_REIMBURSEMENT"
                        else "🤝 Liquidación Directa entre Miembros (Bizum)"
                    ),
                    key=f"tx_settle_{selected_month_name}",
                    help="Elige cómo se compensará el gasto adelantado.",
                )

            tx_submitted = st.button("💾 Guardar Gasto Común", type="primary", width="stretch", key=f"btn_save_tx_{selected_month_name}")
            if tx_submitted:
                if not tx_desc.strip():
                    st.error("Por favor introduce una descripción del gasto.")
                elif charge_type == "Necesidad Común del Hogar" and not chosen_subcat_id:
                    st.error("Debes seleccionar una subcategoría de necesidad común.")
                elif charge_type == "Cargo a Hucha de Amortización" and not chosen_fund_id:
                    st.error("Debes seleccionar una hucha de amortización activa para imputar el gasto.")
                elif charge_type == "Cargo a Hucha de Amortización" and fund_map and (float(selected_fund_obj.get("current_balance", 0.0) if selected_fund_obj else 0.0) < float(tx_amount)) and not confirm_overdraft:
                    st.error("⚠️ Debes marcar la casilla obligatoria de confirmación de sobregasto para autorizar el cargo a la tesorería común.")
                else:
                    payload_tx = {
                        "description": tx_desc.strip(),
                        "amount": float(tx_amount),
                        "date": tx_date.isoformat(),
                        "joint_subcategory_id": chosen_subcat_id,
                        "joint_sinking_fund_id": chosen_fund_id,
                        "created_by_profile": account.get("local_profile", "MEMBER_A"),
                        "paid_by": paid_choice,
                        "settlement_mechanism": settlement_mech if paid_choice in ("MEMBER_A", "MEMBER_B") else "COMMON_REIMBURSEMENT",
                    }
                    res_tx = api_client.create_joint_transaction(payload_tx)
                    if res_tx:
                        st.success("✅ Gasto registrado y transmitido a la sincronización.")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar el gasto común.")

    with col_act_aport:
        # Formulario para asentar aportación (ordinaria mensual o extraordinaria a hucha concreta)
        with st.expander(f"💰 Asentar Aportación ({selected_month_name})", expanded=False):
            contrib_type = st.radio(
                "Modalidad de Aportación",
                options=["Aportación Ordinaria (Presupuesto Común)", "Aportación Extraordinaria (Hucha Concreta)"],
                horizontal=True,
                key=f"contrib_type_{selected_month_name}",
            )
            sinking_funds_avail = api_client.get_joint_sinking_funds(status="ACTIVE")
            fund_choice_map = {f["id"]: f["name"] for f in sinking_funds_avail} if sinking_funds_avail else {}

            with st.form(f"new_joint_contrib_form_{selected_month_name}"):
                target_fund_choice = None
                if contrib_type == "Aportación Extraordinaria (Hucha Concreta)":
                    if fund_choice_map:
                        target_fund_choice = st.selectbox(
                            "Hucha de Destino",
                            options=list(fund_choice_map.keys()),
                            format_func=lambda k: fund_choice_map[k],
                        )
                    else:
                        st.warning("No hay huchas activas. La aportación se ingresará en la tesorería general.")

                col_camt, col_cdt = st.columns(2)
                with col_camt:
                    cb_amount = st.number_input("Importe a Aportar (€)", min_value=1.0, value=100.0, step=25.0)
                with col_cdt:
                    cb_date = st.date_input("Fecha de Aportación", value=date.today(), format="DD/MM/YYYY", key=f"cb_date_{selected_month_name}")

                local_prof = account.get("local_profile", "MEMBER_A")
                local_name = account.get("member_a_name" if local_prof == "MEMBER_A" else "member_b_name", "Miembro Local")
                cb_profile = local_prof
                st.info(
                    f"👤 **Miembro Aportante**: **{local_name} (Tú)** — Esta aportación se registrará en tu cuenta personal "
                    f"y se sumará al fondo común del hogar. *(Tu pareja registrará su cuota desde su propio dispositivo).* "
                )
                st.caption(f"Mes imputado: **{month_str}**")

                cb_submitted = st.form_submit_button("💾 Confirmar Asiento de Aportación", width="stretch")
                if cb_submitted:
                    payload_cb = {
                        "month": month_str,
                        "amount": float(cb_amount),
                        "contributor_profile": cb_profile,
                        "contribution_date": cb_date.isoformat(),
                        "target_sinking_fund_id": target_fund_choice,
                    }
                    res_cb = api_client.asentar_aportacion_asistida(payload_cb)
                    if res_cb:
                        st.success("✅ Aportación asentada correctamente y sincronizada.")
                        st.rerun()
                    else:
                        st.error("❌ No se pudo asentar la aportación.")

    st.markdown("<hr style='margin: 16px 0; border: 0; border-top: 1px dashed #334155;'>", unsafe_allow_html=True)

    # 1. Historial de Aportaciones Recibidas en el Mes
    st.markdown("#### 📥 Historial de Aportaciones Recibidas")
    if not contributions:
        st.info(f"Aún no hay aportaciones asentadas en {selected_month_name} {selected_year}.")
    else:
        contrib_rows = []
        for cb in contributions:
            p_profile = cb.get("contributor_profile")
            p_name = (
                account.get("member_a_name", "Miembro A")
                if p_profile == "MEMBER_A"
                else account.get("member_b_name", "Miembro B")
            )
            contrib_rows.append({
                "ID": cb.get("id"),
                "Fecha": _format_date_es(cb.get("contribution_date")),
                "Aportante": p_name,
                "Mes Aplicado": cb.get("month"),
                "Importe (€)": f"{cb.get('amount', 0.0):,.2f} €",
            })
        df_cb = pd.DataFrame(contrib_rows)
        st.dataframe(df_cb[["Fecha", "Aportante", "Mes Aplicado", "Importe (€)"]], width="stretch")

        with st.expander("🗑️ Revertir una Aportación"):
            cb_to_delete = st.selectbox(
                "Selecciona la aportación a revertir",
                options=[r["ID"] for r in contrib_rows],
                format_func=lambda id_val: next(
                    (f"ID {r['ID']} - {r['Fecha']} | {r['Aportante']} ({r['Importe (€)']})" for r in contrib_rows if r["ID"] == id_val),
                    str(id_val),
                ),
                key=f"sel_revert_cb_{selected_month_name}",
            )
            if st.button("Confirmar Reversión", key=f"btn_revert_cb_{selected_month_name}"):
                ok = api_client.delete_joint_contribution(cb_to_delete)
                if ok:
                    st.success("Aportación revertida con éxito y sincronizada con tu pareja.")
                    st.rerun()
                else:
                    st.error("No se pudo revertir la aportación.")

    st.markdown("<hr style='margin: 16px 0; border: 0; border-top: 1px dashed #334155;'>", unsafe_allow_html=True)

    # 2. Historial de Gastos Comunes del Mes
    st.markdown("#### 📤 Historial de Gastos Comunes Ejecutados")
    if not transactions:
        st.info(f"No hay gastos comunes registrados en {selected_month_name} {selected_year}.")
    else:
        # Construir tabla de gastos con acción de borrado
        subcategories_all = api_client.get_joint_subcategories()
        subcat_dict = {s["id"]: s["name"] for s in subcategories_all}
        funds_all = api_client.get_joint_sinking_funds()
        funds_dict = {f["id"]: f["name"] for f in funds_all}

        table_rows = []
        for tx in transactions:
            subcat_lbl = subcat_dict.get(tx.get("joint_subcategory_id"), "—")
            fund_lbl = funds_dict.get(tx.get("joint_sinking_fund_id"), "—")
            
            paid_by_val = tx.get("paid_by") or "COMMON"
            if paid_by_val == "MEMBER_A":
                paid_lbl = f"👤 {account.get('member_a_name', 'Miembro A')}"
            elif paid_by_val == "MEMBER_B":
                paid_lbl = f"👤 {account.get('member_b_name', 'Miembro B')}"
            else:
                paid_lbl = "💳 Cuenta Común"

            status_val = tx.get("settlement_status")
            if paid_by_val == "COMMON":
                status_lbl = "🟢 Directo"
            elif status_val == "PENDING":
                mech_val = tx.get("settlement_mechanism")
                mech_short = "Bizum" if mech_val == "DIRECT_MEMBER_SETTLEMENT" else "Cta. Común"
                status_lbl = f"🟡 Pendiente ({mech_short})"
            else:
                status_lbl = "🟢 Reembolsado"

            table_rows.append({
                "ID": tx.get("id"),
                "Fecha": _format_date_es(tx.get("date")),
                "Descripción": tx.get("description"),
                "Subcategoría": subcat_lbl,
                "Hucha Imputada": fund_lbl,
                "Pagado Por": paid_lbl,
                "Reembolso": status_lbl,
                "Importe (€)": f"{tx.get('amount', 0.0):,.2f} €",
                "_raw": tx,
            })

        df_tx = pd.DataFrame(table_rows)
        st.dataframe(df_tx[["Fecha", "Descripción", "Subcategoría", "Hucha Imputada", "Pagado Por", "Reembolso", "Importe (€)"]], width="stretch")

        # Acciones de liquidación de gastos adelantados pendientes
        unsettled_in_table = [r for r in table_rows if r["_raw"].get("settlement_status") == "PENDING" and r["_raw"].get("paid_by") in ("MEMBER_A", "MEMBER_B")]
        if unsettled_in_table:
            with st.expander("💸 Liquidar / Reembolsar Gasto Individual"):
                tx_to_settle = st.selectbox(
                    "Selecciona el gasto adelantado a marcar como reembolsado",
                    options=[r["ID"] for r in unsettled_in_table],
                    format_func=lambda id_val: next(
                        (f"ID {r['ID']} - {r['Fecha']} | {r['Descripción']} ({r['Importe (€)']}) - {r['Pagado Por']}" for r in unsettled_in_table if r["ID"] == id_val),
                        str(id_val),
                    ),
                    key=f"sel_settle_tx_{selected_month_name}",
                )
                if st.button("✓ Confirmar Reembolso / Liquidación", key=f"btn_confirm_settle_{selected_month_name}"):
                    ok_s = api_client.settle_joint_transaction(tx_to_settle)
                    if ok_s:
                        st.success("Gasto marcado como reembolsado con éxito y sincronizado.")
                        st.rerun()
                    else:
                        st.error("No se pudo liquidar la transacción.")

        # Acciones de eliminación de transacciones
        with st.expander("🗑️ Eliminar una Transacción"):
            tx_to_delete = st.selectbox(
                "Selecciona la transacción a eliminar",
                options=[r["ID"] for r in table_rows],
                format_func=lambda id_val: next(
                    (f"ID {r['ID']} - {r['Fecha']} | {r['Descripción']} ({r['Importe (€)']})" for r in table_rows if r["ID"] == id_val),
                    str(id_val),
                ),
            )
            if st.button("Confirmar Eliminación", key="btn_del_joint_tx"):
                ok = api_client.delete_joint_transaction(tx_to_delete)
                if ok:
                    st.success("Transacción eliminada con tombstone de sincronización.")
                    st.rerun()
                else:
                    st.error("No se pudo eliminar la transacción.")


# =====================================================================
# TAB 3: HUCHAS DE AMORTIZACIÓN

def _render_personal_assisted_contribution_banner(year: int) -> None:
    """Monitor de Aportaciones Cruzadas en el Perfil Personal (Fase 7.5).

    Evalúa el estado de las aportaciones del mes actual para ambos miembros del hogar:
    - Si ambos han cumplido su cuota: auto-ocultación limpia (no muestra banner).
    - Si el usuario local está pendiente: banner con input y botón en 1-clic para asentar su parte,
      con cabecera del estado cruzado de ambos miembros.
    - Si el usuario local ya aportó pero la pareja está pendiente: banner informativo compacto de una sola línea.
    """
    today = date.today()
    curr_month_str = f"{today.year}-{today.month:02d}"
    curr_month_name = MESES_ES[today.month - 1] if 1 <= today.month <= 12 else str(today.month)

    try:
        account = api_client.get_joint_account()
        if not account:
            return

        loc_profile = account.get("local_profile", "MEMBER_A")
        remote_profile = "MEMBER_B" if loc_profile == "MEMBER_A" else "MEMBER_A"

        local_name = (
            account.get("member_a_name", "Miembro A")
            if loc_profile == "MEMBER_A"
            else account.get("member_b_name", "Miembro B")
        )
        remote_name = (
            account.get("member_b_name", "Miembro B")
            if loc_profile == "MEMBER_A"
            else account.get("member_a_name", "Miembro A")
        )

        contributions = api_client.get_joint_contributions(year=today.year, month=curr_month_str)

        # Calcular importes ya aportados en el mes
        contrib_local = sum(
            float(c.get("amount", 0.0)) for c in contributions if c.get("contributor_profile") == loc_profile
        )
        contrib_remote = sum(
            float(c.get("amount", 0.0)) for c in contributions if c.get("contributor_profile") == remote_profile
        )

        # Obtener cuotas objetivo sugeridas exclusivamente desde el backend (Principio 3)
        calc = api_client.get_joint_contribution_calculation()
        if not calc:
            return
        target_local = (
            float(calc.get("member_a_contribution", 0.0))
            if loc_profile == "MEMBER_A"
            else float(calc.get("member_b_contribution", 0.0))
        )
        target_remote = (
            float(calc.get("member_b_contribution", 0.0))
            if loc_profile == "MEMBER_A"
            else float(calc.get("member_a_contribution", 0.0))
        )

        is_local_complete = (target_local <= 0.0) or (contrib_local >= target_local)
        is_remote_complete = (target_remote <= 0.0) or (contrib_remote >= target_remote)

        # CASO 1: Ambos miembros han completado su aportación (o la cuota requerida es 0.00 €) -> Auto-ocultación limpia
        if is_local_complete and is_remote_complete:
            return

        # Texto del estado de la pareja
        if is_remote_complete:
            remote_status_txt = f"✅ {contrib_remote:,.2f} € aportados"
        else:
            rem_remote = max(0.0, target_remote - contrib_remote)
            remote_status_txt = f"⏳ {rem_remote:,.2f} € pendientes"

        # CASO 2: El usuario local ya completó su cuota pero la pareja sigue pendiente
        if is_local_complete:
            local_status_txt = f"✅ {contrib_local:,.2f} € aportados"
            st.info(
                f"ℹ️ **Economía del Hogar ({curr_month_name} {today.year})**: "
                f"Tú ({local_name}: {local_status_txt}) | "
                f"Pareja ({remote_name}: {remote_status_txt})."
            )
            return

        # CASO 3: El usuario local tiene saldo pendiente -> Banner con formulario de asiento
        rem_local = max(0.0, target_local - contrib_local)
        local_status_txt = f"⏳ {rem_local:,.2f} € pendientes"
        default_input = rem_local if rem_local > 0 else target_local

        st.info(
            f"🔔 **Aportación al Hogar ({curr_month_name} {today.year})**: "
            f"Tú ({local_name}: {local_status_txt}) | "
            f"Pareja ({remote_name}: {remote_status_txt})."
        )

        col_b1, col_b2 = st.columns([3, 1])
        with col_b1:
            contrib_amount = st.number_input(
                f"Importe aportación de {local_name} (€)",
                min_value=1.0,
                value=max(1.0, float(default_input)),
                step=25.0,
                key="assisted_contrib_input",
            )
        with col_b2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("💳 Asentar en 1-Clic", key="btn_asentar_asistida_banner", width="stretch"):
                payload = {
                    "month": curr_month_str,
                    "amount": float(contrib_amount),
                    "contributor_profile": loc_profile,
                    "contribution_date": today.isoformat(),
                }
                res = api_client.asentar_aportacion_asistida(payload)
                if res:
                    st.success("✅ Aportación transferida y registrada en tu cuenta personal y conjunta.")
                    st.rerun()
                else:
                    st.error("❌ No se pudo asentar la aportación.")
    except Exception as e:
        logger.warning("No se pudo comprobar la aportación asistida: %s", e)

