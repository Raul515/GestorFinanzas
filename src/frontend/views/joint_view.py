"""
Vista Frontend para la Gestión de Finanzas Compartidas (Cuenta Conjunta del Hogar).
Especificación 010: Arquitectura Multi-Perfil para Parejas y Finanzas Compartidas.
"""

import logging
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import streamlit as st
import pandas as pd
import altair as alt

# Asegurar importación de api_client
try:
    import api_client
except ImportError:
    from frontend import api_client  # type: ignore

logger = logging.getLogger(__name__)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def render_joint_view(selected_year: int) -> None:
    """Punto de entrada principal para la pantalla de Economía del Hogar (Cuenta Conjunta)."""
    status = api_client.get_joint_status()
    is_configured = status.get("is_configured", False)

    if not is_configured:
        _render_zero_state_wizard()
    else:
        account = api_client.get_joint_account()
        if not account:
            st.error("⚠️ No se pudo obtener la información de la cuenta conjunta. Verifica la conexión con el servidor.")
            return
        _render_configured_joint_view(selected_year=selected_year, account=account, status=status)


# =====================================================================
# 1. ESTADO CERO (ZERO-STATE ONBOARDING WIZARD)
# =====================================================================

def _render_zero_state_wizard() -> None:
    """Asistente de bienvenida y configuración inicial de la cuenta conjunta."""
    st.header("✨ Configurar Espacio Compartido del Hogar")
    st.markdown(
        """
        Bienvenido a la gestión financiera conjunta. Este espacio permite coordinar los gastos del hogar
        y las huchas compartidas manteniendo la **total privacidad** de tus ingresos individuales,
        patrimonio propio y gastos personales (ocio, caprichos o formación).
        """
    )

    # Detección de invitación previa enviada por la pareja vía Syncthing (Opción A)
    inv_resp = api_client.get_joint_invitation()
    has_invitation = inv_resp.get("has_invitation", False)

    if has_invitation:
        inv = inv_resp.get("invitation", {})
        h_name = inv.get("household_name", "Hogar Compartido")
        creator = inv.get("member_a_name", "tu pareja")
        split_lbl = "Al 50%" if "50" in str(inv.get("split_mode", "50")) else "Proporcional a Ingresos"
        cohab_lbl = "Convivencia Inicial" if "DATING" in str(inv.get("cohabitation_stage", "")) or "PRE" in str(inv.get("cohabitation_stage", "")) else "Matrimonio / Proyecto a Largo Plazo"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #064e3b, #0f172a); border: 2px solid #10b981; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="color: #6ee7b7; margin: 0 0 8px 0;">🎉 ¡Invitación de Hogar Detectada!</h3>
                <p style="color: #f1f5f9; margin: 0 0 10px 0; font-size: 1rem;">
                    Tu pareja (<b>{creator}</b>) ya ha configurado el hogar <b>'{h_name}'</b> en su ordenador y lo ha compartido contigo a través de Syncthing.
                </p>
                <p style="color: #cbd5e1; margin: 0 0 14px 0; font-size: 0.9rem;">
                    • <b>Modo de Reparto pactado</b>: {split_lbl}<br>
                    • <b>Etapa de Convivencia</b>: {cohab_lbl}
                </p>
                <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">
                    Al unirte, este dispositivo adoptará automáticamente la configuración común sin riesgo de discrepancias ni duplicados.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("✨ Unirse a este Hogar en 1-Clic", type="primary", use_container_width=True, key="btn_accept_inv"):
            with st.spinner("Conectando con la cuenta conjunta de tu pareja..."):
                res_acc = api_client.accept_joint_invitation()
                if res_acc:
                    st.success("🎉 ¡Te has unido a la cuenta conjunta exitosamente!")
                    st.rerun()
                else:
                    st.error("❌ Ocurrió un error al aceptar la invitación.")

        st.markdown("<hr style='margin: 25px 0 15px 0; border: 0; border-top: 1px dashed #475569;'>", unsafe_allow_html=True)
        st.markdown("<p style='color: #94a3b8; font-size: 0.9rem;'>O si lo prefieres, puedes ignorar la invitación y configurar una cuenta distinta manualmente:</p>", unsafe_allow_html=True)

    with st.expander("📝 Configurar Cuenta Conjunta Manualmente", expanded=(not has_invitation)):
        with st.form("joint_onboarding_form"):
            st.subheader("1. Identificación del Hogar")
            account_name = st.text_input(
                "Nombre del Hogar o Cuenta Común",
                value="Hogar Compartido",
                help="Ejemplo: Hogar Martínez-López, Casa Nuestra, etc.",
            )

            col_a, col_b = st.columns(2)
            with col_a:
                member_a_name = st.text_input(
                    "Tu Nombre (Miembro A - Dispositivo Local)",
                    value="Raúl",
                    help="Identificador que figurará en tus aportaciones conjuntas.",
                )
                member_a_income = st.number_input(
                    "Tu Salario Neto Mensual Estimado (€)",
                    min_value=0.0,
                    value=2000.0,
                    step=50.0,
                    help="Utilizado de forma confidencial para el cálculo del semáforo y reparto proporcional.",
                )

            with col_b:
                member_b_name = st.text_input(
                    "Nombre de tu Pareja (Miembro B - Cotitular)",
                    value="Pareja",
                    help="Nombre de la otra persona del hogar.",
                )
                member_b_income = st.number_input(
                    "Salario Neto Mensual Estimado de tu Pareja (€)",
                    min_value=0.0,
                    value=2000.0,
                    step=50.0,
                    help="Utilizado para la Tasa de Esfuerzo Familiar combinada.",
                )

            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("2. Reglas de Convivencia y Reparto")
            col_c, col_d = st.columns(2)
            with col_c:
                split_mode_choice = st.selectbox(
                    "Modo de Reparto de Gastos",
                    options=["Al 50% cada uno (EQUAL_50_50)", "Proporcional a Ingresos Netos (INCOME_PROPORTIONAL)"],
                    index=0,
                    help="Define cómo se calcula la aportación mensual de cada persona a la cuenta común.",
                )
                split_mode = "EQUAL_50_50" if "50%" in split_mode_choice else "INCOME_PROPORTIONAL"

            with col_d:
                cohab_choice = st.selectbox(
                    "Etapa de Convivencia",
                    options=[
                        "Convivencia Plena / Compartiendo Hogar (COHABITATION)",
                        "Pre-Convivencia / Viviendo Separados (PRE_COHABITATION)",
                    ],
                    index=0,
                    help="En convivencia plena se gestionan facturas del hogar (alquiler, suministros, súper) + huchas. En pre-convivencia se ahorra para metas futuras sin costes de vivienda.",
                )
                cohabitation_stage = "COHABITATION" if "Convivencia Plena" in cohab_choice or "Compartiendo" in cohab_choice else "PRE_COHABITATION"

            st.info(
                "ℹ️ Al crear la cuenta conjunta, se inicializarán automáticamente las subcategorías de necesidades comunes "
                "(Alquiler/Hipoteca, Supermercado, Luz, Agua, Seguros del Hogar, etc.) y se habilitará la sincronización Syncthing."
            )

            submitted = st.form_submit_button("🚀 Iniciar y Activar Cuenta Conjunta", use_container_width=True)
            if submitted:
                if not account_name.strip() or not member_a_name.strip() or not member_b_name.strip():
                    st.error("Por favor completa los nombres requeridos.")
                    return

                payload = {
                    "household_name": account_name.strip(),
                    "member_a_name": member_a_name.strip(),
                    "member_b_name": member_b_name.strip(),
                    "split_mode": split_mode,
                    "cohabitation_stage": cohabitation_stage,
                    "contribution_strategy": "NOMINAL_TEMPLATE",
                    "member_a_reference_income": float(member_a_income),
                    "member_b_reference_income": float(member_b_income),
                    "local_profile": "MEMBER_A",
                    "remote_profile": "MEMBER_B",
                }

                with st.spinner("Configurando el espacio del hogar..."):
                    res = api_client.setup_joint_account(payload)
                    if res:
                        st.success("🎉 ¡Cuenta conjunta configurada exitosamente!")
                        st.rerun()
                    else:
                        st.error("❌ Ocurrió un error al crear la cuenta conjunta. Revisa los registros.")



# =====================================================================
# 2. PANTALLA PRINCIPAL (CONFIGURED JOINT ACCOUNT)
# =====================================================================

def _render_configured_joint_view(selected_year: int, account: Dict[str, Any], status: Dict[str, Any]) -> None:
    """Renderiza la pantalla completa e independiente de la economía del hogar."""
    # Cabecera con resumen del hogar
    sync_status = api_client.get_sync_status()
    is_synced = sync_status.get("is_synchronized", True)
    sync_badge = "🟢 Sincronizado" if is_synced else "🟡 Sincronización Pendiente"

    cohab_val = account.get("cohabitation_stage", "PRE_COHABITATION")
    cohab_text = (
        "Pre-Convivencia"
        if cohab_val in ("PRE_COHABITATION", "DATING_COHABITATION")
        else "Convivencia Plena"
    )
    split_val = account.get("split_mode", "EQUAL_50_50")
    split_text = "Reparto 50/50" if "50" in str(split_val) else "Reparto Proporcional"

    # Calcular saldo de tesorería del año
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
                        {cohab_text} | {split_text}
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

    # 4 Pestañas Principales
    tab_resumen, tab_meses, tab_huchas, tab_config = st.tabs([
        "📊 Resumen Anual del Hogar",
        "📅 12 Meses del Hogar",
        "🎯 Huchas de Amortización",
        "⚙️ Configuración del Hogar y Sincronización",
    ])

    with tab_resumen:
        _render_tab_resumen_anual(selected_year=selected_year, account=account)

    with tab_meses:
        _render_tab_12_meses(selected_year=selected_year, account=account)

    with tab_huchas:
        _render_tab_huchas(account=account)

    with tab_config:
        _render_tab_configuracion(account=account, sync_status=sync_status)


# =====================================================================
# TAB 1: RESUMEN ANUAL DEL HOGAR
# =====================================================================

def _render_tab_resumen_anual(selected_year: int, account: Dict[str, Any]) -> None:
    """
    Renderiza el Resumen Anual consolidado de la unidad familiar.
    Regla innegociable: no incluye comparativas de quién aportó más (Miembro A vs Miembro B).
    """
    st.subheader(f"Resumen Consolidado del Hogar - Año {selected_year}")

    annual_summary = api_client.get_joint_annual_summary(year=selected_year)
    if not annual_summary:
        st.info("No se pudieron cargar las métricas anuales del hogar para este año.")
        return

    needs_spent = annual_summary.get("total_needs_spent", 0.0)
    sinking_saved = annual_summary.get("total_sinking_funds_saved", 0.0)
    effort_rate = annual_summary.get("effort_rate_pct", 0.0)
    health_status = annual_summary.get("health_status", "SUSTAINABLE")

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

    # Diagnóstico del Semáforo
    if health_status == "SUSTAINABLE":
        st.success(
            f"🟢 **Hogar Sostenible**: La tasa de esfuerzo del hogar es del {effort_rate:.1f}%. "
            "La carga de gastos esenciales no asfixia la economía familiar, permitiendo dotar huchas y ahorrar."
        )
    elif health_status == "TENSION":
        st.warning(
            f"🟡 **Zona de Tensión**: Los gastos fijos del hogar absorben el {effort_rate:.1f}% "
            "de los ingresos combinados. Conviene vigilar desviaciones en facturas y suministros."
        )
    else:
        st.error(
            f"🔴 **Alerta Crítica**: La tasa de esfuerzo ({effort_rate:.1f}%) supera el umbral de seguridad del 60%. "
            "Se recomienda auditar los suministros y renegociar contratos de vivienda o seguros."
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
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Aún no hay transacciones suficientes registradas en el año para generar la gráfica comparativa.")


# =====================================================================
# TAB 2: 12 MESES DEL HOGAR
# =====================================================================

def _render_tab_12_meses(selected_year: int, account: Dict[str, Any]) -> None:
    """Pestaña mensual de tesorería, registro de gastos comunes y listado de transacciones."""
    col_sel, _ = st.columns([2, 4])
    with col_sel:
        current_m_idx = min(max(datetime.now().month - 1, 0), 11)
        selected_month_name = st.selectbox("Selecciona Mes a Gestionar", MESES_ES, index=current_m_idx)
        month_idx = MESES_ES.index(selected_month_name) + 1
        month_str = f"{selected_year}-{month_idx:02d}"

    # Cargar datos del mes
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

    st.markdown("<hr style='margin: 16px 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)

    # Formulario para registrar nuevo gasto común
    is_pre_cohabitation = account.get("cohabitation_stage") in ("PRE_COHABITATION", "DATING_COHABITATION")

    with st.expander(f"➕ Registrar Gasto Común en {selected_month_name}", expanded=False):
        subcategories = api_client.get_joint_subcategories()
        sinking_funds = api_client.get_joint_sinking_funds(status="ACTIVE")

        subcat_map = {s["id"]: s["name"] for s in subcategories} if subcategories else {}
        fund_map = {f["id"]: f["name"] for f in sinking_funds} if sinking_funds else {}

        if is_pre_cohabitation:
            charge_type = "Cargo a Hucha de Amortización"
            st.info(
                "ℹ️ **Modo Pre-Convivencia Activo**: Los gastos comunes de vivienda (alquiler, suministros, supermercado) "
                "están desactivados porque aún no compartís domicilio. Todo gasto común se imputa directamente a una "
                "Hucha de Amortización de vuestro ahorro conjunto."
            )
        else:
            # Radio selector fuera del form para reactividad instantánea en Streamlit
            charge_type = st.radio(
                "Tipo de Imputación",
                options=["Necesidad Común del Hogar", "Cargo a Hucha de Amortización"],
                horizontal=True,
                key=f"charge_type_{selected_month_name}",
                help="Define si este gasto se financia con el presupuesto mensual ordinario o si se descuenta de una hucha de ahorro acumulada.",
            )

        with st.form("new_joint_tx_form"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                tx_desc = st.text_input("Concepto / Descripción", placeholder="Ej. Billetes de avión, Factura Luz...")
                tx_amount = st.number_input("Importe (€)", min_value=0.01, value=65.0, step=5.0)
                tx_date = st.date_input("Fecha", value=date.today())

            with col_f2:
                chosen_subcat_id = None
                chosen_fund_id = None

                if charge_type == "Necesidad Común del Hogar":
                    if subcat_map:
                        chosen_subcat_id = st.selectbox(
                            "Subcategoría de Necesidades",
                            options=list(subcat_map.keys()),
                            format_func=lambda k: subcat_map[k],
                        )
                    else:
                        st.caption("No hay subcategorías disponibles.")
                else:
                    if fund_map:
                        chosen_fund_id = st.selectbox(
                            "Hucha a Cargar (se descontará de su saldo)",
                            options=list(fund_map.keys()),
                            format_func=lambda k: fund_map[k],
                        )
                    else:
                        st.warning("⚠️ No hay huchas activas creadas. Crea una en la pestaña '🎯 Huchas de Amortización' (ej. Vacaciones, Entrada de Piso).")

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
                    help="Por defecto sale del presupuesto común del hogar. Si uno de los dos adelantó el dinero de su bolsillo, indícalo aquí.",
                )
                paid_by = account.get("local_profile", "MEMBER_A") if paid_choice == "COMMON" else paid_choice

            tx_submitted = st.form_submit_button("💾 Guardar Gasto Común", use_container_width=True)
            if tx_submitted:
                if not tx_desc.strip():
                    st.error("Por favor introduce una descripción del gasto.")
                elif charge_type == "Necesidad Común del Hogar" and not chosen_subcat_id:
                    st.error("Debes seleccionar una subcategoría de necesidad común.")
                elif charge_type == "Cargo a Hucha de Amortización" and not chosen_fund_id:
                    st.error("Debes seleccionar una hucha de amortización activa para imputar el gasto.")
                else:
                    payload_tx = {
                        "description": tx_desc.strip(),
                        "amount": float(tx_amount),
                        "date": tx_date.isoformat(),
                        "joint_subcategory_id": chosen_subcat_id,
                        "joint_sinking_fund_id": chosen_fund_id,
                        "created_by_profile": paid_by,
                    }
                    res_tx = api_client.create_joint_transaction(payload_tx)
                    if res_tx:
                        st.success("✅ Gasto registrado y transmitido a la bandeja de sincronización.")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar el gasto común.")

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
                "Fecha": cb.get("contribution_date"),
                "Aportante": p_name,
                "Mes Aplicado": cb.get("month"),
                "Importe (€)": f"{cb.get('amount', 0.0):,.2f} €",
            })
        df_cb = pd.DataFrame(contrib_rows)
        st.dataframe(df_cb[["Fecha", "Aportante", "Mes Aplicado", "Importe (€)"]], use_container_width=True)

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
            paid_lbl = (
                account.get("member_a_name", "Miembro A")
                if tx.get("created_by_profile") == "MEMBER_A"
                else account.get("member_b_name", "Miembro B")
            )
            table_rows.append({
                "ID": tx.get("id"),
                "Fecha": tx.get("date"),
                "Descripción": tx.get("description"),
                "Subcategoría": subcat_lbl,
                "Hucha Imputada": fund_lbl,
                "Pagado Por": paid_lbl,
                "Importe (€)": f"{tx.get('amount', 0.0):,.2f} €",
            })

        df_tx = pd.DataFrame(table_rows)
        st.dataframe(df_tx[["Fecha", "Descripción", "Subcategoría", "Hucha Imputada", "Pagado Por", "Importe (€)"]], use_container_width=True)

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
# =====================================================================

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
        with st.form("create_sinking_fund_form"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                fund_name = st.text_input("Nombre de la Meta / Hucha", placeholder="Ej. Seguro Coche Anual")
                fund_desc = st.text_input("Descripción", placeholder="Provisión para póliza anual a todo riesgo")
                target_amount = st.number_input("Objetivo Total (€)", min_value=1.0, value=600.0, step=50.0)

            with col_f2:
                current_balance = st.number_input("Saldo Inicial Acumulado (€)", min_value=0.0, value=0.0, step=25.0)
                monthly_target = st.number_input("Aportación Mensual Sugerida (€)", min_value=0.0, value=50.0, step=10.0)
                target_date = st.date_input("Fecha Objetivo (Opcional)", value=None)

            fund_created = st.form_submit_button("🎯 Crear Hucha de Amortización", use_container_width=True)
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

            with col:
                st.markdown(
                    f"""
                    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                        <h4 style="margin: 0 0 6px 0; color: #38bdf8;">🎯 {f.get('name')}</h4>
                        <p style="font-size: 0.85rem; color: #94a3b8; margin: 0 0 8px 0;">{f.get('description') or 'Sin descripción'}</p>
                        <h3 style="margin: 0; color: #f8fafc;">{balance:,.2f} € <small style="font-size: 0.8rem; color: #64748b;">/ {target:,.2f} €</small></h3>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.progress(pct)
                st.caption(f"Progreso: {pct * 100:.1f}% | Mensual sugerido: {f.get('monthly_target_amount', 0.0):,.2f} €")

        # Acciones de edición / eliminación
        with st.expander("⚙️ Administrar o Eliminar Huchas"):
            fund_to_manage = st.selectbox(
                "Selecciona hucha para editar o eliminar",
                options=[f["id"] for f in funds],
                format_func=lambda id_val: next((f["name"] for f in funds if f["id"] == id_val), str(id_val)),
            )
            selected_f = next((f for f in funds if f["id"] == fund_to_manage), None)

            if selected_f:
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    new_f_balance = st.number_input(
                        "Ajustar Saldo Directo (€)",
                        value=float(selected_f.get("current_balance", 0.0)),
                        step=25.0,
                        key="edit_fund_bal",
                    )
                    if st.button("Guardar Saldo", key="btn_save_f_bal"):
                        api_client.update_joint_sinking_fund(selected_f["id"], {"current_balance": new_f_balance})
                        st.success("Saldo actualizado.")
                        st.rerun()

                with col_e2:
                    other_funds = [of for of in funds if of["id"] != selected_f["id"]]
                    realloc_target = None
                    if other_funds:
                        realloc_target = st.selectbox(
                            "Reasignar saldo a otra hucha al eliminar (opcional)",
                            options=[None] + [of["id"] for of in other_funds],
                            format_func=lambda k: "No reasignar" if k is None else next((of["name"] for of in other_funds if of["id"] == k), str(k)),
                        )
                    if st.button("🗑️ Eliminar Hucha", key="btn_del_fund"):
                        ok = api_client.delete_joint_sinking_fund(selected_f["id"], reallocate_to_fund_id=realloc_target)
                        if ok:
                            st.success("Hucha eliminada exitosamente.")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar la hucha.")


# =====================================================================
# TAB 4: CONFIGURACIÓN Y SINCRONIZACIÓN
# =====================================================================

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
        if st.button("🔄 Procesar Bandeja de Entrada Ahora (Inbox)", use_container_width=True):
            with st.spinner("Procesando deltas entrantes de Syncthing..."):
                res = api_client.trigger_process_inbox()
                processed = res.get("processed_count", 0)
                ignored = res.get("ignored_count", 0)
                st.success(f"Procesamiento finalizado. Eventos aplicados: {processed}, Ignorados por idempotencia: {ignored}.")
                st.rerun()
    with col_btn2:
        if st.button("📤 Reenviar Invitación a mi Pareja", use_container_width=True):
            with st.spinner("Regenerando invitación del hogar en Outbox..."):
                if api_client.resend_joint_invitation():
                    st.success("¡Invitación regenerada en Outbox! Syncthing la enviará a tu pareja.")
                    st.rerun()
                else:
                    st.error("Error al reenviar la invitación.")


    st.markdown("<hr style='margin: 20px 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)
    st.markdown("### Parámetros de la Cuenta Conjunta")

    with st.form("edit_joint_account_form"):
        new_acc_name = st.text_input("Nombre del Hogar", value=account.get("household_name") or account.get("account_name", ""))

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            new_mem_a = st.text_input("Nombre Miembro A", value=account.get("member_a_name", "Miembro A"))
            new_inc_a = st.number_input(
                "Salario de Referencia Miembro A (€)",
                min_value=0.0,
                value=float(account.get("member_a_reference_income") or account.get("member_a_estimated_income", 0.0)),
                step=50.0,
            )

        with col_p2:
            new_mem_b = st.text_input("Nombre Miembro B", value=account.get("member_b_name", "Miembro B"))
            new_inc_b = st.number_input(
                "Salario de Referencia Miembro B (€)",
                min_value=0.0,
                value=float(account.get("member_b_reference_income") or account.get("member_b_estimated_income", 0.0)),
                step=50.0,
            )

        col_p3, col_p4 = st.columns(2)
        with col_p3:
            current_split = account.get("split_mode", "EQUAL_50_50")
            split_idx = 0 if "50" in str(current_split) else 1
            new_split_choice = st.selectbox("Modo de Reparto", ["Al 50% cada uno (EQUAL_50_50)", "Proporcional a Ingresos Netos (INCOME_PROPORTIONAL)"], index=split_idx)
            new_split = "EQUAL_50_50" if "50%" in new_split_choice else "INCOME_PROPORTIONAL"

        with col_p4:
            current_cohab = account.get("cohabitation_stage", "PRE_COHABITATION")
            cohab_idx = 0 if "PRE" in str(current_cohab) or "DATING" in str(current_cohab) else 1
            new_cohab_choice = st.selectbox("Etapa de Convivencia", ["Pre-Convivencia / Viviendo Separados (PRE_COHABITATION)", "Convivencia Plena / Compartiendo Hogar (COHABITATION)"], index=cohab_idx)
            new_cohab = "PRE_COHABITATION" if "Pre" in new_cohab_choice else "COHABITATION"

        acc_saved = st.form_submit_button("💾 Guardar Cambios de Configuración", use_container_width=True)
        if acc_saved:
            payload_acc = {
                "household_name": new_acc_name.strip(),
                "member_a_name": new_mem_a.strip(),
                "member_b_name": new_mem_b.strip(),
                "member_a_reference_income": float(new_inc_a),
                "member_b_reference_income": float(new_inc_b),
                "split_mode": new_split,
                "cohabitation_stage": new_cohab,
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
            use_container_width=True,
            key="btn_danger_reset",
        ):
            with st.spinner("Purgando cuenta conjunta y limpiando sincronización..."):
                ok = api_client.reset_joint_account()
                if ok:
                    st.success("✅ Cuenta conjunta desactivada con éxito. Volviendo al estado inicial...")
                    st.rerun()
                else:
                    st.error("❌ Error al purgar la cuenta conjunta en el servidor.")
