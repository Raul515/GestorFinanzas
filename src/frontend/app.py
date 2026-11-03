import logging
import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime
import os
import sys

# Asegurar que src esté en el sys.path para resolución de módulos del frontend y backend
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import api_client
try:
    from frontend.services.financial_calculator import (
        calculate_category_totals,
        calculate_503020_percentages,
        calculate_annual_metrics,
    )
    from frontend.services.guidelines_view import (
        render_monthly_guidelines_expander,
        render_annual_guidelines_expander,
    )
    from frontend.views.joint_view import render_joint_view
    from frontend.views.backup_view import render_backup_view
    from frontend.views.updater_view import render_updater_view
except ImportError:
    from services.financial_calculator import (  # type: ignore
        calculate_category_totals,
        calculate_503020_percentages,
        calculate_annual_metrics,
    )
    from services.guidelines_view import (  # type: ignore
        render_monthly_guidelines_expander,
        render_annual_guidelines_expander,
    )
    from views.joint_view import render_joint_view  # type: ignore
    from views.backup_view import render_backup_view  # type: ignore
    from views.updater_view import render_updater_view  # type: ignore

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Gestor Finanzas", layout="wide")

# Load CSS
css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Sidebar para selección de modo de gestión
st.sidebar.header("Espacio de Trabajo")
context_mode = st.sidebar.radio(
    "Modo de Gestión",
    options=["👤 Mi Perfil Personal", "👥 Economía del Hogar (Cuenta Conjunta)"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.header("Configuración Temporal")
year_today = date.today().year
year_selected = st.sidebar.number_input("Año", min_value=2000, max_value=2100, value=year_today, step=1)

MESES_NOMBRES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def _render_personal_assisted_contribution_banner(year: int) -> None:
    """Muestra un banner si la aportación a la cuenta conjunta para el mes actual está pendiente."""
    today = date.today()
    curr_month_str = f"{today.year}-{today.month:02d}"
    curr_month_name = MESES_NOMBRES[today.month - 1] if 1 <= today.month <= 12 else str(today.month)

    try:
        account = api_client.get_joint_account()
        if not account:
            return

        loc_profile = account.get("local_profile", "MEMBER_A")
        contributions = api_client.get_joint_contributions(year=today.year, month=curr_month_str)
        already_paid = any(c.get("contributor_profile") == loc_profile for c in contributions)

        if not already_paid:
            # Obtener cálculo dinámico exacto según la estrategia del hogar (Mejora 1)
            calc = api_client.get_joint_contribution_calculation()
            if calc:
                default_amount = (
                    float(calc.get("member_a_contribution", 500.0))
                    if loc_profile == "MEMBER_A"
                    else float(calc.get("member_b_contribution", 500.0))
                )
            else:
                ref_income = (
                    float(account.get("member_a_reference_income", 2000.0))
                    if loc_profile == "MEMBER_A"
                    else float(account.get("member_b_reference_income", 2000.0))
                )
                default_amount = round(ref_income * 0.4, 2) if ref_income > 0 else 500.0

            local_name = (
                account.get("member_a_name", "Miembro A")
                if loc_profile == "MEMBER_A"
                else account.get("member_b_name", "Miembro B")
            )

            st.info(
                f"🔔 **Aportación Pendiente al Hogar ({curr_month_name} {today.year})**: "
                f"Aún no has registrado tu aportación mensual para gastos comunes."
            )
            col_b1, col_b2 = st.columns([3, 1])
            with col_b1:
                contrib_amount = st.number_input(
                    f"Importe aportación de {local_name} (€)",
                    min_value=1.0,
                    value=max(1.0, float(default_amount)),
                    step=25.0,
                    key="assisted_contrib_input",
                )
            with col_b2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("💳 Asentar en 1-Clic", key="btn_asentar_asistida_banner", use_container_width=True):
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


if context_mode == "👥 Economía del Hogar (Cuenta Conjunta)":
    st.title("Economía del Hogar (Cuenta Conjunta)")
    render_joint_view(selected_year=year_selected)
    st.stop()

st.title("Gestor de Finanzas Personales")

# Banner asistido de inicio de mes (solo si cuenta conjunta está configurada)
try:
    joint_status = api_client.get_joint_status()
    if joint_status.get("is_configured"):
        api_client.trigger_process_inbox()
        _render_personal_assisted_contribution_banner(year_selected)
except Exception as e:
    logger.warning("Error al comprobar el estado de la cuenta conjunta: %s", e)


# Pestañas de Navegación (Resumen Anual + 12 Meses + Presupuesto Base + Radar Macro + Screener + Deep Dive + Copiloto + Comité Asesor)
tabs_list = (
    ["📊 Resumen Anual"]
    + MESES_NOMBRES
    + [
        "⚙️ Presupuesto Base",
        "🌐 Radar Macro y Noticias",
        "🔍 Screener y Oportunidades",
        "🔬 Análisis Fundamental (Deep Dive)",
        "💬 Copiloto Patrimonial",
        "🏛️ Comité Asesor Multiagente",
        "💾 Base de Datos y Copias de Seguridad",
        "🚀 Actualizaciones del Sistema",
    ]
)
tabs = st.tabs(tabs_list)
tab_anual = tabs[0]
tabs_meses = tabs[1:13]
tab_base = tabs[13]
tab_radar = tabs[14]
tab_screener = tabs[15]
tab_deepdive = tabs[16]
tab_copilot = tabs[17]
tab_committee = tabs[18]
tab_backup = tabs[19]
tab_updater = tabs[20]

# Datos globales de categorías y subcategorías
categorias = api_client.get_categorias()
todas_subcats = api_client.get_subcategorias()
subcat_options = {s['id']: s['nombre'] for s in todas_subcats} if todas_subcats else {}

# Nombres estándar de las categorías
necesidades_name = "Necesidades Básicas"
deseos_name = "Deseos y Estilo de vida"
ahorro_name = "Ahorro e Inversión"
ingresos_name = "Ingresos Netos"

colores_cabecera = {
    "Ingresos Netos": "#2e7d32",
    "Necesidades Básicas": "#1565c0",
    "Deseos y Estilo de vida": "#ef6c00",
    "Ahorro e Inversión": "#00838f"
}

# ==========================================
# PESTAÑA 0: RESUMEN ANUAL
# ==========================================
with tab_anual:
    st.header(f"Resumen Anual - Año: {year_selected}")
    
    if not categorias:
        st.info("La base de datos está vacía o el backend no está corriendo. Revisa que FastAPI esté funcionando.")
    else:
        # Recolectar datos de los 12 meses
        anual_data = {m: {cat['nombre']: {"presupuesto": 0.0, "real": 0.0} for cat in categorias} for m in range(1, 13)}
        
        for m in range(1, 13):
            mes_key = f"{year_selected}-{m:02d}"
            presupuestos_m = api_client.get_presupuestos(mes_key)
            transacciones_m = api_client.get_transacciones(mes_key)
            
            for cat in categorias:
                cat_subcats = [s for s in todas_subcats if (s.get('categoria_id') if s.get('categoria_id') is not None else s.get('category_id')) == cat['id']]
                p_sum = 0.0
                r_sum = 0.0
                for s in cat_subcats:
                    s_id = s['id']
                    p_val = 0.0
                    if presupuestos_m:
                        p_match = [p for p in presupuestos_m if (p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')) == s_id]
                        if p_match:
                            p_val = p_match[0].get('cantidad') if p_match[0].get('cantidad') is not None else p_match[0].get('amount', 0.0)
                    p_sum += p_val
                    
                    t_val = 0.0
                    if transacciones_m:
                        r_match = [t.get('cantidad', t.get('amount', 0.0)) for t in transacciones_m if (t.get('subcategoria_id') if t.get('subcategoria_id') is not None else t.get('subcategory_id')) == s_id]
                        t_val = sum(r_match)
                    
                    r_sum += (p_val + t_val)
                
                anual_data[m][cat['nombre']]["presupuesto"] = p_sum
                anual_data[m][cat['nombre']]["real"] = r_sum
            
            # Derivar automáticamente presupuestos de bloques según regla 50/30/20
            p_ing_m = anual_data[m][ingresos_name]["presupuesto"]
            if necesidades_name in anual_data[m]:
                anual_data[m][necesidades_name]["presupuesto"] = p_ing_m * 0.50
            if deseos_name in anual_data[m]:
                anual_data[m][deseos_name]["presupuesto"] = p_ing_m * 0.30
            if ahorro_name in anual_data[m]:
                anual_data[m][ahorro_name]["presupuesto"] = p_ing_m * 0.20

        # Totales Consolidados Anuales
        ann_metrics = calculate_annual_metrics(
            anual_data, ingresos_name, necesidades_name, deseos_name, ahorro_name
        )
        ingresos_anual_real = ann_metrics["ingresos_anual_real"]
        nec_anual_real = ann_metrics["nec_anual_real"]
        des_anual_real = ann_metrics["des_anual_real"]
        aho_anual_real = ann_metrics["aho_anual_real"]
        gasto_corriente_real = nec_anual_real + des_anual_real
        tasa_ahorro_media = (aho_anual_real / ingresos_anual_real * 100) if ingresos_anual_real > 0 else 0.0
        ahorro_acumulado_total = ann_metrics["ahorro_acumulado_total"]
        pct_nec_real = ann_metrics["pct_nec_real"]
        pct_des_real = ann_metrics["pct_des_real"]
        pct_aho_real = ann_metrics["pct_aho_real"]
        desv_nec = ann_metrics["desv_nec"]
        desv_des = ann_metrics["desv_des"]
        desv_aho = ann_metrics["desv_aho"]

        # 1. TARJETAS KPI SUPERIORES ANUALES (5 Tarjetas en distribución 3 + 2)
        safety_status_anual = api_client.get_safety_status()
        ef_balance = safety_status_anual.get("current_balance", 0.0) if safety_status_anual else 0.0
        ef_cov = safety_status_anual.get("coverage_months", 0.0) if safety_status_anual else 0.0
        ef_complete = safety_status_anual.get("is_completed", False) if safety_status_anual else False
        ef_tag = "FONDO COMPLETO" if ef_complete else "EN CONSTRUCCIÓN"
        ef_color = "#2e7d32" if ef_complete else "#ef6c00"
        ef_bg = "rgba(46, 125, 50, 0.15)" if ef_complete else "rgba(239, 108, 0, 0.1)"

        # Fila 1: 3 Columnas
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.markdown(f"""<div style="background-color: rgba(21, 101, 192, 0.1); border: 2px solid #1565c0; border-radius: 8px; padding: 15px; text-align: center;">
                <span style="font-size: 11px; font-weight: 700; color: #1565c0; text-transform: uppercase;">INGRESOS NETOS ANUALES</span>
                <h2 style="margin: 5px 0 0 0; color: inherit; font-size: 22px;">{ingresos_anual_real:,.2f} €</h2>
            </div>""", unsafe_allow_html=True)
            
        with kpi2:
            st.markdown(f"""<div style="background-color: rgba(239, 108, 0, 0.1); border: 2px solid #ef6c00; border-radius: 8px; padding: 15px; text-align: center;">
                <span style="font-size: 11px; font-weight: 700; color: #ef6c00; text-transform: uppercase;">GASTO CORRIENTE CONSOLIDADO</span>
                <h2 style="margin: 5px 0 0 0; color: inherit; font-size: 22px;">{gasto_corriente_real:,.2f} €</h2>
            </div>""", unsafe_allow_html=True)
            
        with kpi3:
            st.markdown(f"""<div style="background-color: rgba(46, 125, 50, 0.15); border: 2px solid #2e7d32; border-radius: 8px; padding: 15px; text-align: center;">
                <span style="font-size: 11px; font-weight: 700; color: #2e7d32; text-transform: uppercase;">TASA DE AHORRO MEDIA REAL</span>
                <h2 style="margin: 5px 0 0 0; color: #2e7d32; font-size: 22px;">{tasa_ahorro_media:.2f}%</h2>
            </div>""", unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

        # Fila 2: 2 Columnas
        kpi4, kpi5 = st.columns(2)
        with kpi4:
            st.markdown(f"""<div style="background-color: rgba(0, 131, 143, 0.1); border: 2px solid #00838f; border-radius: 8px; text-align: center; padding: 15px;">
                <span style="font-size: 11px; font-weight: 700; color: #00838f; text-transform: uppercase;">AHORRO ACUMULADO TOTAL</span>
                <h2 style="margin: 5px 0 0 0; color: inherit; font-size: 22px;">{ahorro_acumulado_total:,.2f} €</h2>
            </div>""", unsafe_allow_html=True)

        with kpi5:
            st.markdown(f"""<div style="background-color: {ef_bg}; border: 2px solid {ef_color}; border-radius: 8px; text-align: center; padding: 15px;">
                <span style="font-size: 11px; font-weight: 700; color: {ef_color}; text-transform: uppercase;">FONDO DE EMERGENCIA ({ef_tag})</span>
                <h2 style="margin: 5px 0 0 0; color: inherit; font-size: 22px;">{ef_balance:,.2f} € <span style="font-size: 14px; opacity: 0.85; font-weight: 500;">({ef_cov:.1f} meses cubiertos)</span></h2>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. RESUMEN FLUJO DINÁMICO & GRÁFICOS (3 Columnas)
        c_flujo, c_donut, c_bar = st.columns([1.2, 1, 1.2])
        
        with c_flujo:
            st.markdown("##### Resumen Flujo Dinámico")
            
            flujo_html = f"""<table style="width: 100%; border-collapse: collapse; font-size: 13px; color: inherit;">
            <thead>
                <tr style="background-color: #1565c0; color: white;">
                    <th style="padding: 6px; text-align: left;">Bloque</th>
                    <th style="padding: 6px; text-align: right;">Cifra Total</th>
                    <th style="padding: 6px; text-align: right;">% Presup.</th>
                    <th style="padding: 6px; text-align: right;">% Real</th>
                    <th style="padding: 6px; text-align: right;">Desviación</th>
                </tr>
            </thead>
            <tbody>
                <tr style="border-bottom: 1px solid rgba(128,128,128,0.2);">
                    <td style="padding: 6px; font-weight: bold;">Ingresos Netos Totales</td>
                    <td style="padding: 6px; text-align: right;">{ingresos_anual_real:,.2f} €</td>
                    <td style="padding: 6px; text-align: right;">100,00%</td>
                    <td style="padding: 6px; text-align: right;">100,00%</td>
                    <td style="padding: 6px; text-align: right;">0,00%</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(128,128,128,0.2);">
                    <td style="padding: 6px;">Necesidades Básicas (50%)</td>
                    <td style="padding: 6px; text-align: right;">{nec_anual_real:,.2f} €</td>
                    <td style="padding: 6px; text-align: right;">50,00%</td>
                    <td style="padding: 6px; text-align: right;">{pct_nec_real:.2f}%</td>
                    <td style="padding: 6px; text-align: right; color: {'#ef5350' if desv_nec > 0 else '#4caf50'};">{desv_nec:+.2f}%</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(128,128,128,0.2);">
                    <td style="padding: 6px;">Deseos (30%)</td>
                    <td style="padding: 6px; text-align: right;">{des_anual_real:,.2f} €</td>
                    <td style="padding: 6px; text-align: right;">30,00%</td>
                    <td style="padding: 6px; text-align: right;">{pct_des_real:.2f}%</td>
                    <td style="padding: 6px; text-align: right; color: {'#ef5350' if desv_des > 0 else '#4caf50'};">{desv_des:+.2f}%</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(128,128,128,0.2);">
                    <td style="padding: 6px;">Ahorro e Inversión (20%)</td>
                    <td style="padding: 6px; text-align: right;">{aho_anual_real:,.2f} €</td>
                    <td style="padding: 6px; text-align: right;">20,00%</td>
                    <td style="padding: 6px; text-align: right;">{pct_aho_real:.2f}%</td>
                    <td style="padding: 6px; text-align: right; color: {'#4caf50' if desv_aho >= 0 else '#ef5350'};">{desv_aho:+.2f}%</td>
                </tr>
            </tbody>
            </table>"""
            st.markdown(flujo_html, unsafe_allow_html=True)
            
        with c_donut:
            st.markdown("<p style='text-align: center; font-weight: bold; font-size: 13px; margin: 0;'>Porcentaje Real a cada bloque</p>", unsafe_allow_html=True)
            donut_df = pd.DataFrame([
                {"Bloque": "Necesidades (50%)", "Valor": nec_anual_real},
                {"Bloque": "Deseos (30%)", "Valor": des_anual_real},
                {"Bloque": "Ahorro (20%)", "Valor": aho_anual_real},
            ])
            donut_chart = alt.Chart(donut_df).mark_arc(innerRadius=40).encode(
                theta=alt.Theta(field="Valor", type="quantitative"),
                color=alt.Color(field="Bloque", type="nominal", scale=alt.Scale(
                    domain=['Necesidades (50%)', 'Deseos (30%)', 'Ahorro (20%)'],
                    range=['#1565c0', '#ef6c00', '#2e7d32']
                )),
                tooltip=['Bloque', alt.Tooltip('Valor:Q', format=',.2f')]
            ).properties(height=200)
            st.altair_chart(donut_chart, width="stretch")
            
        with c_bar:
            st.markdown("<p style='text-align: center; font-weight: bold; font-size: 13px; margin: 0;'>Gasto vs Ahorro mensual</p>", unsafe_allow_html=True)
            mensual_list = []
            for m in range(1, 13):
                m_nombre = MESES_NOMBRES[m-1][:3]
                mensual_list.append({"Mes": m_nombre, "Bloque": "Necesidades", "Monto": anual_data[m][necesidades_name]["real"], "Orden": m})
                mensual_list.append({"Mes": m_nombre, "Bloque": "Deseos", "Monto": anual_data[m][deseos_name]["real"], "Orden": m})
                mensual_list.append({"Mes": m_nombre, "Bloque": "Ahorro", "Monto": anual_data[m][ahorro_name]["real"], "Orden": m})
            
            bar_df = pd.DataFrame(mensual_list)
            bar_chart = alt.Chart(bar_df).mark_bar().encode(
                x=alt.X('Mes:N', sort=alt.SortField("Orden"), title=None),
                y=alt.Y('Monto:Q', title="Euros (€)"),
                color=alt.Color('Bloque:N', scale=alt.Scale(
                    domain=['Necesidades', 'Deseos', 'Ahorro'],
                    range=['#1565c0', '#ef6c00', '#ffca28']
                )),
                tooltip=['Mes', 'Bloque', alt.Tooltip('Monto:Q', format=',.2f')]
            ).properties(height=200)
            st.altair_chart(bar_chart, width="stretch")

        st.markdown("<br>", unsafe_allow_html=True)

        # Spec 008: Diagnóstico Estructural y Pautas Anuales
        annual_guideline_report = api_client.get_annual_guidelines(ann_metrics)
        if annual_guideline_report:
            render_annual_guidelines_expander(annual_guideline_report, expanded=False)

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. GRÁFICO DE AHORRO ACUMULADO (LÍNEA)
        st.markdown("##### Ahorro Acumulado")
        ahorro_acum_list = []
        acumulado = 0.0
        for m in range(1, 13):
            m_nombre = MESES_NOMBRES[m-1]
            acumulado += anual_data[m][ahorro_name]["real"]
            ahorro_acum_list.append({"Mes": m_nombre, "Ahorro Acumulado": acumulado, "Orden": m})
            
        line_df = pd.DataFrame(ahorro_acum_list)
        line_chart = alt.Chart(line_df).mark_line(point=True, color='#00838f', strokeWidth=3).encode(
            x=alt.X('Mes:N', sort=alt.SortField("Orden"), title=None),
            y=alt.Y('Ahorro Acumulado:Q', title="Euros (€)"),
            tooltip=['Mes', alt.Tooltip('Ahorro Acumulado:Q', format=',.2f')]
        ).properties(height=220)
        st.altair_chart(line_chart, width="stretch")

        # 4. TABLA MATRIZ MENSUAL CONSOLIDADA (Enero a Diciembre + Total)
        st.markdown("##### Detalle Mensual Consolidado")
        
        columnas_meses = "".join([f"<th style='padding: 8px; text-align: right;'>{MESES_NOMBRES[m-1][:3]}</th>" for m in range(1, 13)])
        
        def render_row(nombre_bloque, key_name):
            vals = [anual_data[m][key_name]["real"] for m in range(1, 13)]
            tot = sum(vals)
            cells = "".join([f"<td style='padding: 8px; text-align: right;'>{v:,.2f} €</td>" for v in vals])
            return f"""<tr style="border-bottom: 1px solid rgba(128,128,128,0.2);">
                <td style="padding: 8px; font-weight: 500;">{nombre_bloque}</td>
                {cells}
                <td style="padding: 8px; text-align: right; font-weight: bold;">{tot:,.2f} €</td>
            </tr>"""

        acum_vals = []
        ac = 0.0
        for m in range(1, 13):
            ac += anual_data[m][ahorro_name]["real"]
            acum_vals.append(ac)
        cells_acum = "".join([f"<td style='padding: 8px; text-align: right;'>{v:,.2f} €</td>" for v in acum_vals])
        row_acum = f"""<tr style="border-bottom: 1px solid rgba(128,128,128,0.2); font-weight: bold; background-color: rgba(0, 131, 143, 0.1);">
            <td style="padding: 8px;">Ahorro Acumulado</td>
            {cells_acum}
            <td style="padding: 8px; text-align: right;">{acum_vals[-1]:,.2f} €</td>
        </tr>"""

        matriz_html = f"""<div style="overflow-x: auto;"><table style="width: 100%; border-collapse: collapse; font-size: 12px; color: inherit; white-space: nowrap;">
        <thead>
            <tr style="background-color: #1565c0; color: white;">
                <th style="padding: 8px; text-align: left;">Meses</th>
                {columnas_meses}
                <th style="padding: 8px; text-align: right;">Total Anual Real</th>
            </tr>
        </thead>
        <tbody>
            {render_row("Ingresos", ingresos_name)}
            {render_row("Necesidades (50%)", necesidades_name)}
            {render_row("Deseos (30%)", deseos_name)}
            {render_row("Ahorro (20%)", ahorro_name)}
            {row_acum}
        </tbody>
        </table></div>"""
        
        st.markdown(matriz_html, unsafe_allow_html=True)


# ==========================================
# PESTAÑAS 1 a 12: MESES INDIVIDUALES
# ==========================================
for idx, tab in enumerate(tabs_meses, start=1):
    with tab:
        mes_key = f"{year_selected}-{idx:02d}"
        nombre_mes = MESES_NOMBRES[idx-1]
        
        st.header(f"Gestión de Finanzas - {nombre_mes} {year_selected}")
        
        # Cargar datos del mes
        presupuestos_m = api_client.get_presupuestos(mes_key)
        transacciones_m = api_client.get_transacciones(mes_key)
        
        if not categorias:
            st.info("La base de datos está vacía o el backend no está corriendo.")
            continue

        # Totales del mes
        totales_m = calculate_category_totals(
            categorias, todas_subcats, presupuestos_m, transacciones_m,
            ingresos_name, necesidades_name, deseos_name, ahorro_name
        )

        # 1. RESUMEN KPI DEL MES
        real_ing = totales_m.get(ingresos_name, {}).get("real", 0.0)
        pres_ing = totales_m.get(ingresos_name, {}).get("presupuesto", 0.0)
        
        real_nec_m = totales_m.get(necesidades_name, {}).get("real", 0.0)
        pres_nec_m = totales_m.get(necesidades_name, {}).get("presupuesto", 0.0)
        
        real_des_m = totales_m.get(deseos_name, {}).get("real", 0.0)
        pres_des_m = totales_m.get(deseos_name, {}).get("presupuesto", 0.0)
        
        real_aho_m = totales_m.get(ahorro_name, {}).get("real", 0.0)
        pres_aho_m = totales_m.get(ahorro_name, {}).get("presupuesto", 0.0)
        
        total_gasto_real_m = real_nec_m + real_des_m + real_aho_m
        total_gasto_pres_m = pres_nec_m + pres_des_m + pres_aho_m
        
        m_kpi1, m_kpi2, m_kpi3 = st.columns(3)
        with m_kpi1:
            st.metric(label="Ingresos Totales (Real)", value=f"{real_ing:,.2f} €", delta=f"{real_ing - pres_ing:,.2f} € vs Presupuesto")
        with m_kpi2:
            st.metric(label="Gastos Totales (Real)", value=f"{total_gasto_real_m:,.2f} €", delta=f"{total_gasto_real_m - total_gasto_pres_m:,.2f} € vs Presupuesto", delta_color="inverse")
        with m_kpi3:
            bal_m = real_ing - total_gasto_real_m
            st.metric(label="Balance Neto (Ahorro)", value=f"{bal_m:,.2f} €", delta=f"{bal_m - (pres_ing - total_gasto_pres_m):,.2f} € vs Presupuesto")

        st.markdown("<br>", unsafe_allow_html=True)

        # 2. GRÁFICOS COMPARATIVOS PRESUPUESTO VS REAL POR CATEGORÍA (Estilo Excel)
        with st.expander("📊 Gráficos Comparativos (Presupuesto vs Real)", expanded=True):
            g_col1, g_col2 = st.columns(2)
            
            for index_cat, cat in enumerate(categorias):
                n_cat = cat['nombre']
                info_c = totales_m.get(n_cat, {})
                subcats_c = info_c.get("subcategorias", [])
                if not subcats_c:
                    continue
                
                chart_data_cat = []
                for s in subcats_c:
                    s_id = s['id']
                    pval = 0.0
                    if presupuestos_m:
                        pm = [p for p in presupuestos_m if (p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')) == s_id]
                        if pm:
                            pval = pm[0].get('cantidad') if pm[0].get('cantidad') is not None else pm[0].get('amount', 0.0)
                    rval_trans = 0.0
                    if transacciones_m:
                        rval_trans = sum(t.get('cantidad', t.get('amount', 0.0)) for t in transacciones_m if (t.get('subcategoria_id') if t.get('subcategoria_id') is not None else t.get('subcategory_id')) == s_id)
                    rval_total = pval + rval_trans
                    
                    chart_data_cat.append({"Concepto": s['nombre'], "Tipo": "Presupuesto", "Monto": pval})
                    chart_data_cat.append({"Concepto": s['nombre'], "Tipo": "Real", "Monto": rval_total})
                
                # Añadir Total al gráfico
                t_pres_c = info_c.get("presupuesto", 0.0)
                t_real_c = info_c.get("real", 0.0)
                chart_data_cat.append({"Concepto": "Total", "Tipo": "Presupuesto", "Monto": t_pres_c})
                chart_data_cat.append({"Concepto": "Total", "Tipo": "Real", "Monto": t_real_c})
                
                df_chart = pd.DataFrame(chart_data_cat)
                
                target_col = g_col1 if (index_cat % 2 == 0) else g_col2
                with target_col:
                    chart_bars = alt.Chart(df_chart).mark_bar().encode(
                        x=alt.X('Concepto:N', title=None, sort=None),
                        y=alt.Y('Monto:Q', title="Euros (€)"),
                        color=alt.Color('Tipo:N', scale=alt.Scale(
                            domain=['Presupuesto', 'Real'],
                            range=['#d4e157', '#ec407a']
                        )),
                        xOffset='Tipo:N',
                        tooltip=['Concepto', 'Tipo', alt.Tooltip('Monto:Q', format=',.2f')]
                    ).properties(height=220, title=f"{n_cat}")
                    st.altair_chart(chart_bars, width="stretch")

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. FORMULARIO CON CATEGORÍA Y SUBCATEGORÍA FILTRADA PARA AÑADIR TRANSACCIÓN
        st.markdown("##### ➕ Añadir Nueva Transacción")

        # Reset selectivo de campos tras inserción (Cantidad y Concepto a blanco; Fecha, Categoría y Subcategoría se mantienen)
        if st.session_state.get(f"reset_tx_{mes_key}"):
            st.session_state[f"txt_{mes_key}"] = ""
            st.session_state[f"num_{mes_key}"] = 0.0
            st.session_state[f"reset_tx_{mes_key}"] = False

        f_col1, f_col2, f_col3, f_col4, f_col5, f_col6 = st.columns([1.8, 2, 2, 2.5, 1.5, 1.2])
        
        with f_col1:
            fecha_val = st.date_input(
                "Fecha",
                value=date(year_selected, idx, min(date.today().day, 28)),
                key=f"dt_{mes_key}",
                format="DD/MM/YYYY",
            )
            
        with f_col2:
            cat_options = {c['id']: c['nombre'] for c in categorias}
            cat_sel_id = st.selectbox("Categoría", options=list(cat_options.keys()), format_func=lambda x: cat_options[x], key=f"cat_sb_{mes_key}")
            
        with f_col3:
            subcats_filtradas = [s for s in todas_subcats if (s.get('categoria_id') if s.get('categoria_id') is not None else s.get('category_id')) == cat_sel_id]
            subcat_opts = {s['id']: s['nombre'] for s in subcats_filtradas}
            subcat_sel_id = st.selectbox("Subcategoría", options=list(subcat_opts.keys()), format_func=lambda x: subcat_opts[x], key=f"subcat_sb_{mes_key}") if subcat_opts else None
            
        with f_col4:
            conc_val = st.text_input("Concepto / Causa", key=f"txt_{mes_key}")
            
        with f_col5:
            cant_val = st.number_input("Cantidad (€)", min_value=0.0, step=10.0, key=f"num_{mes_key}")
            
        with f_col6:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            btn_add = st.button("Guardar", key=f"btn_add_{mes_key}", width="stretch")
            
        if btn_add:
            if subcat_sel_id and cant_val > 0:
                api_client.create_transaccion(fecha_val, subcat_sel_id, cant_val, conc_val)
                st.session_state[f"reset_tx_{mes_key}"] = True
                st.toast("¡Transacción guardada correctamente!", icon="✅")
                st.rerun()
            else:
                st.error("Por favor, selecciona una subcategoría y una cantidad mayor a 0.")

        # Historial de Transacciones del Mes (Spec 006)
        with st.expander(f"📋 Historial de Transacciones de {nombre_mes}"):
            if not transacciones_m:
                st.info("No hay transacciones registradas en este mes.")
            else:
                st.caption(f"Listado de transacciones registradas para {nombre_mes}. Pulsa en 🗑️ para eliminar un apunte.")
                h_col1, h_col2, h_col3, h_col4, h_col5, h_col6 = st.columns([1.5, 2.2, 2.2, 1.8, 2.8, 1.2])
                with h_col1:
                    st.markdown("**Fecha**")
                with h_col2:
                    st.markdown("**Concepto / Subcat.**")
                with h_col3:
                    st.markdown("**Categoría**")
                with h_col4:
                    st.markdown("**Importe**")
                with h_col5:
                    st.markdown("**Descripción**")
                with h_col6:
                    st.markdown("**Acción**")
                st.markdown("<hr style='margin: 4px 0 10px 0;'>", unsafe_allow_html=True)

                subcat_map = {s['id']: s for s in todas_subcats}
                cat_map = {c['id']: c for c in categorias}

                sorted_transacciones = sorted(
                    transacciones_m,
                    key=lambda x: str(x.get('fecha') or x.get('date') or ''),
                    reverse=True,
                )

                for tx in sorted_transacciones:
                    tx_id = tx.get("id")
                    tx_sub_id = tx.get("subcategoria_id") if tx.get("subcategoria_id") is not None else tx.get("subcategory_id")
                    tx_sub = subcat_map.get(tx_sub_id)
                    sub_nombre = tx_sub["nombre"] if tx_sub else f"Subcategoría #{tx_sub_id}"

                    cat_id = (tx_sub.get("categoria_id") if tx_sub.get("categoria_id") is not None else tx_sub.get("category_id")) if tx_sub else None
                    cat_obj = cat_map.get(cat_id) if cat_id else None
                    cat_nombre = cat_obj["nombre"] if cat_obj else "—"

                    raw_fecha = str(tx.get("fecha") or tx.get("date") or "—")
                    try:
                        if raw_fecha and raw_fecha != "—":
                            dt_parts = raw_fecha.split("T")[0].split("-")
                            if len(dt_parts) == 3:
                                tx_fecha = f"{dt_parts[2]}/{dt_parts[1]}/{dt_parts[0]}"
                            else:
                                tx_fecha = raw_fecha
                        else:
                            tx_fecha = "—"
                    except Exception:
                        tx_fecha = raw_fecha

                    tx_monto = float(tx.get("cantidad") if tx.get("cantidad") is not None else tx.get("amount", 0.0))
                    tx_desc = tx.get("concepto") or tx.get("description") or "—"

                    r_col1, r_col2, r_col3, r_col4, r_col5, r_col6 = st.columns([1.5, 2.2, 2.2, 1.8, 2.8, 1.2])
                    with r_col1:
                        st.write(tx_fecha)
                    with r_col2:
                        st.write(sub_nombre)
                    with r_col3:
                        st.write(cat_nombre)
                    with r_col4:
                        st.write(f"{tx_monto:,.2f} €")
                    with r_col5:
                        st.write(tx_desc)
                    with r_col6:
                        with st.popover("🗑️", help="Eliminar transacción"):
                            st.markdown(f"¿Eliminar apunte de **{tx_monto:,.2f} €**?")
                            st.caption(f"{sub_nombre} ({tx_fecha})")
                            is_pauta_tx = bool(tx.get("applied_strategy_id") or str(tx_desc).startswith("[Pauta "))
                            if is_pauta_tx:
                                st.warning("⚠️ **Estrategia Vinculada**: Al eliminar esta transacción, se anulará la estrategia completa y se revertirán también sus transacciones hermanas.")
                            if st.button("Confirmar", key=f"btn_del_tx_{mes_key}_{tx_id}", type="primary", width="stretch"):
                                if api_client.delete_transaction(tx_id):
                                    msg = "Estrategia y transacciones revertidas correctamente" if is_pauta_tx else "Transacción eliminada correctamente"
                                    st.toast(msg, icon="🗑️")
                                    st.rerun()
                                else:
                                    st.error("Error al intentar eliminar la transacción.")

        # Personalizar Presupuesto del Mes (Opcional)
        with st.expander(f"✏️ Personalizar Presupuesto de {nombre_mes} (Opcional)"):
            st.caption("Si este mes tiene un gasto o ingreso presupuestado excepcional, puedes modificarlo aquí. De lo contrario, usará los valores por defecto de tu Presupuesto Base.")
            with st.form(key=f"form_pres_mes_{mes_key}"):
                mes_pres_nuevos = []
                p_mes_map = {(p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')): (p.get('cantidad') if p.get('cantidad') is not None else p.get('amount', 0.0)) for p in presupuestos_m} if presupuestos_m else {}
                
                for cat in categorias:
                    n_cat = cat['nombre']
                    subcats_c = [s for s in todas_subcats if (s.get('categoria_id') if s.get('categoria_id') is not None else s.get('category_id')) == cat['id']]
                    if not subcats_c:
                        continue
                    st.markdown(f"**{n_cat}**")
                    cols_m = st.columns(2)
                    for i_s, s in enumerate(subcats_c):
                        v_actual = p_mes_map.get(s['id'], 0.0)
                        with cols_m[i_s % 2]:
                            nv = st.number_input(
                                label=f"{s['nombre']} (€)",
                                min_value=0.0,
                                value=float(v_actual),
                                step=10.0,
                                key=f"pm_in_{mes_key}_{s['id']}"
                            )
                            mes_pres_nuevos.append({
                                "mes": mes_key,
                                "subcategoria_id": s['id'],
                                "cantidad": nv
                            })
                
                btn_save_m = st.form_submit_button(f"💾 Guardar Presupuesto de {nombre_mes}", width="stretch")
                if btn_save_m:
                    res_m = api_client.save_presupuestos_bulk(mes_pres_nuevos)
                    if res_m is not None:
                        st.success(f"¡Presupuesto de {nombre_mes} actualizado!")
                        st.rerun()

        st.markdown("---")

        # 3. TABLAS POR CATEGORÍA DEL MES
        for cat in categorias:
            n_cat = cat['nombre']
            info_c = totales_m.get(n_cat, {})
            subcats_c = info_c.get("subcategorias", [])
            
            if not subcats_c:
                continue
                
            h_color = colores_cabecera.get(n_cat, "#333333")
            
            st.markdown(f"""<div style="border-left: 6px solid {h_color}; padding-left: 12px; margin-top: 25px; margin-bottom: 12px;">
<h3 style="margin: 0; color: inherit; font-family: 'Inter', sans-serif; font-weight: 700;">{n_cat}</h3>
</div>""", unsafe_allow_html=True)
            
            c_tb, c_ds = st.columns([3, 1])
            
            t_pres_c = info_c.get("presupuesto", 0.0)
            t_real_c = info_c.get("real", 0.0)
            
            with c_tb:
                f_html = ""
                for s in subcats_c:
                    s_id = s['id']
                    
                    pval = 0.0
                    if presupuestos_m:
                        pm = [p for p in presupuestos_m if (p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')) == s_id]
                        if pm:
                            pval = pm[0].get('cantidad') if pm[0].get('cantidad') is not None else pm[0].get('amount', 0.0)
                    
                    rval_trans = 0.0
                    if transacciones_m:
                        rval_trans = sum(t.get('cantidad', t.get('amount', 0.0)) for t in transacciones_m if (t.get('subcategoria_id') if t.get('subcategoria_id') is not None else t.get('subcategory_id')) == s_id)
                    
                    rval_total = pval + rval_trans
                    
                    f_html += f"""<tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.2);">
<td style="padding: 10px; font-weight: 500; color: inherit;">{s['nombre']}</td>
<td style="padding: 10px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{pval:,.2f} €</td>
<td style="padding: 10px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{rval_total:,.2f} €</td>
</tr>"""
                
                t_html = f"""<table style="width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; color: inherit;">
<thead>
<tr style="background-color: {h_color}; color: #ffffff !important; text-align: left; font-weight: 600;">
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); border-top-left-radius: 4px; color: #ffffff;">Concepto</th>
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); text-align: right; color: #ffffff;">Presupuesto</th>
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); text-align: right; border-top-right-radius: 4px; color: #ffffff;">Real</th>
</tr>
</thead>
<tbody>
{f_html}
<tr style="font-weight: bold; background-color: rgba(128, 128, 128, 0.15);">
<td style="padding: 12px; border-bottom-left-radius: 4px; color: inherit;">TOTAL</td>
<td style="padding: 12px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{t_pres_c:,.2f} €</td>
<td style="padding: 12px; text-align: right; font-variant-numeric: tabular-nums; border-bottom-right-radius: 4px; color: inherit;">{t_real_c:,.2f} €</td>
</tr>
</tbody>
</table>"""
                st.markdown(t_html, unsafe_allow_html=True)
                
            with c_ds:
                if cat['tipo'] == 'ingreso':
                    desv = t_real_c - t_pres_c
                    pos = desv >= 0
                else:
                    if n_cat == "Ahorro e Inversión":
                        desv = t_real_c - t_pres_c
                        pos = desv >= 0
                    else:
                        desv = t_pres_c - t_real_c
                        pos = desv >= 0
                
                if pos:
                    bg_c = "rgba(46, 125, 50, 0.15)"
                    brd_c = "#2e7d32"
                    txt_c = "#4caf50"
                    sg = "+"
                else:
                    bg_c = "rgba(198, 40, 40, 0.15)"
                    brd_c = "#c62828"
                    txt_c = "#ef5350"
                    sg = ""
                    
                ds_card = f"""<div style="background-color: {bg_c}; border: 2px solid {brd_c}; padding: 22px 15px; border-radius: 8px; text-align: center; margin-top: 38px;">
<span style="color: inherit; font-size: 13px; font-weight: 600; display: block; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px;">Desviación Total</span>
<span style="color: {txt_c}; font-size: 24px; font-weight: 700; display: block; font-variant-numeric: tabular-nums;">{sg}{desv:,.2f} €</span>
</div>"""
                st.markdown(ds_card, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 4. EXPANDIBLE CON GRÁFICO CIRCULAR DE PORCENTAJES REALES (Cumplimiento 50/30/20)
        with st.expander("🍰 Porcentajes Reales de los Bloques (Cumplimiento 50/30/20)", expanded=True):
            pct_nec, pct_des, pct_aho, pct_sin, real_sin_asignar = calculate_503020_percentages(
                real_ing, real_nec_m, real_des_m, real_aho_m
            )
            
            df_pie_m = pd.DataFrame([
                {"Bloque": "Necesidades Totales", "Porcentaje": pct_nec, "Monto": real_nec_m},
                {"Bloque": "Deseos Totales", "Porcentaje": pct_des, "Monto": real_des_m},
                {"Bloque": "Ahorros Totales", "Porcentaje": pct_aho, "Monto": real_aho_m},
                {"Bloque": "Sin Asignar", "Porcentaje": pct_sin, "Monto": real_sin_asignar}
            ])
            
            p_col1, p_col2 = st.columns([1.5, 1])
            with p_col1:
                pie_chart = alt.Chart(df_pie_m).mark_arc(innerRadius=0, outerRadius=140).encode(
                    theta=alt.Theta(field="Porcentaje", type="quantitative"),
                    color=alt.Color(field="Bloque", type="nominal", scale=alt.Scale(
                        domain=["Necesidades Totales", "Deseos Totales", "Ahorros Totales", "Sin Asignar"],
                        range=["#1b6289", "#f27231", "#1b7332", "#78909c"]
                    ), title=None),
                    tooltip=["Bloque", alt.Tooltip("Porcentaje:Q", format=".1f", title="Porcentaje (%)"), alt.Tooltip("Monto:Q", format=",.2f", title="Monto Real (€)")]
                ).properties(height=340, title="Porcentajes Reales de los Bloques")
                
                st.altair_chart(pie_chart, width="stretch")
                
            with p_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("##### 🎯 Metas 50/30/20")
                
                st.markdown(f"""
                <div style="background: rgba(27, 98, 137, 0.15); border-left: 5px solid #1b6289; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                    <span style="font-weight: 600; font-size: 13px;">Necesidades: <strong>{pct_nec:.1f}%</strong></span> <span style="font-size: 12px; opacity: 0.8;">(Meta: 50%)</span><br>
                    <span style="font-size: 14px; font-weight: 700; color: {'#4caf50' if pct_nec <= 50 else '#ef5350'};">{real_nec_m:,.2f} €</span>
                </div>
                
                <div style="background: rgba(242, 114, 49, 0.15); border-left: 5px solid #f27231; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                    <span style="font-weight: 600; font-size: 13px;">Deseos: <strong>{pct_des:.1f}%</strong></span> <span style="font-size: 12px; opacity: 0.8;">(Meta: 30%)</span><br>
                    <span style="font-size: 14px; font-weight: 700; color: {'#4caf50' if pct_des <= 30 else '#ef5350'};">{real_des_m:,.2f} €</span>
                </div>
                
                <div style="background: rgba(27, 115, 50, 0.15); border-left: 5px solid #1b7332; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                    <span style="font-weight: 600; font-size: 13px;">Ahorro: <strong>{pct_aho:.1f}%</strong></span> <span style="font-size: 12px; opacity: 0.8;">(Meta: 20%)</span><br>
                    <span style="font-size: 14px; font-weight: 700; color: {'#4caf50' if pct_aho >= 20 else '#ef5350'};">{real_aho_m:,.2f} €</span>
                </div>
                
                <div style="background: rgba(120, 144, 156, 0.15); border-left: 5px solid #78909c; padding: 10px 14px; border-radius: 6px;">
                    <span style="font-weight: 600; font-size: 13px;">Sin Asignar: <strong>{pct_sin:.1f}%</strong></span><br>
                    <span style="font-size: 14px; font-weight: 700; color: #78909c;">{real_sin_asignar:,.2f} €</span>
                </div>
                """, unsafe_allow_html=True)

        # Spec 008: Pautas Deterministas de Gestión y Compensación Presupuestaria
        safety_status_m = api_client.get_safety_status(mes_key)
        monthly_guideline_report = api_client.get_monthly_guidelines(
            month_key=mes_key,
            month_name=nombre_mes,
            real_income=real_ing,
            budget_income=pres_ing,
            real_needs=real_nec_m,
            real_wants=real_des_m,
            real_savings=real_aho_m,
            safety_status=safety_status_m,
        )
        if monthly_guideline_report:
            st.markdown("<br>", unsafe_allow_html=True)
            render_monthly_guidelines_expander(
                monthly_guideline_report,
                expanded=False,
                subcategories=todas_subcats,
                categories=categorias,
                api_client=api_client,
            )

        # 5. TARJETA RESUMEN DEL FONDO DE EMERGENCIA (SAFETY GUARD)
        if safety_status_m:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.container():
                st.markdown("##### 🛡️ Estado del Fondo de Emergencia (Safety Guard)")
                col_sg1, col_sg2, col_sg3 = st.columns([1, 1, 2])
                with col_sg1:
                    st.metric("Saldo Acumulado", f"{safety_status_m['current_balance']:,.2f} €")
                with col_sg2:
                    st.metric("Meta Objetivo", f"{safety_status_m['target_amount']:,.2f} €", f"{safety_status_m['coverage_months']:.1f} / {safety_status_m['target_months']} meses")
                with col_sg3:
                    if safety_status_m['is_completed']:
                        st.success(f"**Fondo Completo ({safety_status_m['coverage_months']:.1f} meses cubiertos)**: Capacidad de inversión autorizada.")
                    else:
                        st.warning(f"**En Construcción ({safety_status_m['coverage_months']:.1f} / {safety_status_m['target_months']} meses)**: Faltan {safety_status_m['gap']:,.2f} €. Se prioriza la aportación a 'Fondo de emergencia' antes de invertir.")


# ==========================================
# PESTAÑA: CONFIGURACIÓN DEL PRESUPUESTO BASE
# ==========================================
with tab_base:
    st.header("⚙️ Configuración del Presupuesto Base (Plantilla)")
    st.caption("Establece las cantidades presupuestadas habituales para tus ingresos y gastos. Todos los meses utilizarán por defecto estos valores si no tienen una excepción propia.")
    
    if not categorias:
        st.info("La base de datos está vacía.")
    else:
        presupuestos_base = api_client.get_presupuestos("BASE")
        base_map = {(p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')): (p.get('cantidad') if p.get('cantidad') is not None else p.get('amount', 0.0)) for p in presupuestos_base} if presupuestos_base else {}
        
        with st.form("form_presupuesto_base"):
            nuevos_presupuestos = []
            
            for cat in categorias:
                n_cat = cat['nombre']
                subcats_c = [s for s in todas_subcats if (s.get('categoria_id') if s.get('categoria_id') is not None else s.get('category_id')) == cat['id']]
                if not subcats_c:
                    continue
                    
                h_color = colores_cabecera.get(n_cat, "#333333")
                st.markdown(f"""<div style="border-left: 6px solid {h_color}; padding-left: 12px; margin-top: 25px; margin-bottom: 10px;">
<h4 style="margin: 0; color: inherit; font-family: 'Inter', sans-serif;">{n_cat}</h4>
</div>""", unsafe_allow_html=True)
                
                cols = st.columns(2)
                for i_s, s in enumerate(subcats_c):
                    val_actual = base_map.get(s['id'], 0.0)
                    with cols[i_s % 2]:
                        nuevo_val = st.number_input(
                            label=f"{s['nombre']} (€)",
                            min_value=0.0,
                            value=float(val_actual),
                            step=10.0,
                            key=f"base_input_{s['id']}"
                        )
                        nuevos_presupuestos.append({
                            "mes": "BASE",
                            "subcategoria_id": s['id'],
                            "cantidad": nuevo_val
                        })
            
            st.markdown("<br>", unsafe_allow_html=True)
            btn_save_base = st.form_submit_button("💾 Guardar Presupuesto Base", width="stretch")
            if btn_save_base:
                res = api_client.save_presupuestos_bulk(nuevos_presupuestos)
                if res is not None:
                    st.success("¡Presupuesto Base guardado correctamente! Todos los meses sin presupuesto específico adoptarán estos valores.")
                    st.rerun()
                else:
                    st.error("Error al guardar el presupuesto base.")

        # SECCIÓN CONFIGURACIÓN FONDO DE EMERGENCIA (SAFETY GUARD)
        st.markdown("<br><hr>", unsafe_allow_html=True)
        st.subheader("🛡️ Fondo de Emergencia (Safety Guard)")
        st.caption("Gestiona tu reserva patrimonial mínima de seguridad. Por mandato constitucional (Principio 5), debe cubrir al menos 3 meses de gastos esenciales antes de autorizar recomendaciones de inversión.")

        safety_status_base = api_client.get_safety_status("BASE")
        if safety_status_base:
            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                st.metric("Saldo Acumulado", f"{safety_status_base['current_balance']:,.2f} €")
            with col_b2:
                st.metric("Gasto Base Necesidades", f"{safety_status_base['monthly_needs_reference']:,.2f} €/mes")
            with col_b3:
                st.metric("Meta de Seguridad", f"{safety_status_base['target_amount']:,.2f} €", f"{safety_status_base['target_months']} meses")
            with col_b4:
                status_txt = "✅ Habilitada" if safety_status_base["can_invest"] else "⛔ Bloqueada"
                st.metric("Inversión de Riesgo", status_txt, f"{safety_status_base['coverage_months']:.1f} meses cubiertos")

            if safety_status_base["is_completed"]:
                st.success(safety_status_base["message"])
            else:
                st.warning(safety_status_base["message"])

            with st.expander("✏️ Ajustar Parámetros del Fondo de Emergencia", expanded=False):
                with st.form("form_emergency_fund_config"):
                    new_months = st.number_input(
                        "Meses de cobertura objetivo (mínimo 3):",
                        min_value=3,
                        max_value=24,
                        value=int(safety_status_base["target_months"]),
                        step=1,
                    )
                    new_balance = st.number_input(
                        "Ajustar saldo real acumulado en cuenta (€):",
                        min_value=0.0,
                        value=float(safety_status_base["current_balance"]),
                        step=50.0,
                    )
                    btn_save_ef = st.form_submit_button("Actualizar Fondo de Emergencia")
                    if btn_save_ef:
                        res_ef = api_client.update_emergency_fund_config(
                            target_months=new_months,
                            current_balance=new_balance,
                            mes="BASE",
                        )
                        if res_ef:
                            st.success("¡Configuración del Fondo de Emergencia actualizada con éxito!")
                            st.rerun()
                        else:
                            st.error("Error al actualizar la configuración del Fondo de Emergencia.")


# ==========================================
# PESTAÑA: RADAR MACROECONÓMICO Y NOTICIAS
# ==========================================
with tab_radar:
    col_r_title, col_r_btn = st.columns([3, 1])
    with col_r_title:
        st.header("🌐 Radar Macroeconómico y Noticias")
        st.caption("Monitor ejecutivo de mercados con foco prioritario en España y la Eurozona, y canal de noticias financieras depurado con IA.")
    with col_r_btn:
        if st.button("🔄 Actualizar Radar", width="stretch", key="btn_refresh_radar"):
            with st.spinner("Actualizando indicadores y analizando noticias financieras..."):
                refresh_res = api_client.refresh_market_radar()
                if refresh_res:
                    st.success("¡Radar actualizado con éxito!")
                    st.rerun()
                else:
                    st.error("Error al actualizar el radar de mercado. Verifica la conexión con el backend.")

    # Función auxiliar para renderizar sparklines de 30 días con Altair
    def _render_sparkline_chart(values_list, height=55):
        if not values_list or len(values_list) < 2:
            return None
        df_sp = pd.DataFrame({"dia": list(range(len(values_list))), "valor": values_list})
        is_pos = values_list[-1] >= values_list[0]
        line_color = "#2e7d32" if is_pos else "#d32f2f"
        min_v = min(values_list) * 0.998
        max_v = max(values_list) * 1.002
        return (
            alt.Chart(df_sp)
            .mark_line(color=line_color, strokeWidth=2)
            .encode(
                x=alt.X("dia:Q", axis=None),
                y=alt.Y("valor:Q", scale=alt.Scale(domain=[min_v, max_v]), axis=None),
                tooltip=[alt.Tooltip("valor:Q", format=",.2f", title="Valor")],
            )
            .properties(height=height)
            .configure_view(strokeWidth=0)
        )

    st.markdown("---")

    # 1. BLOQUE MACROECONÓMICO (Índices, Deuda Soberana y Prima de Riesgo)
    st.subheader("📊 Monitor Macroeconómico y Tipos de Interés")
    macro_data = api_client.get_macro_indicators()

    if not macro_data or not macro_data.get("indicators"):
        st.info("No se pudieron cargar los indicadores macroeconómicos. Pulsa '🔄 Actualizar Radar' para sincronizar con los proveedores.")
    else:
        cached_tag = "📦 Desde caché local (24h)" if macro_data.get("is_cached") else "⚡ Datos en vivo"
        fetch_time = macro_data.get("fetched_at", "")[:16].replace("T", " ")
        st.caption(f"{cached_tag} | Captura: {fetch_time} | {macro_data.get('source_notes', '')}")

        indicators_by_id = {ind["id"]: ind for ind in macro_data.get("indicators", [])}

        # Sub-bloque A: España y Eurozona (Prioridad Máxima)
        st.markdown("##### 🇪🇸 España y Eurozona")
        col_es_ids = ["ibex35", "bono_es_10y", "prima_riesgo_es", "bund_10y", "stoxx50"]
        cols_es = st.columns(len(col_es_ids))

        for idx_col, ind_id in enumerate(col_es_ids):
            with cols_es[idx_col]:
                ind = indicators_by_id.get(ind_id)
                if ind:
                    val = ind["current_value"]
                    unit = ind.get("unit", "")
                    val_str = f"{val:,.2f} {unit}" if unit != "pb" else f"{int(val)} pb"
                    chg_pct = ind.get("change_pct", 0.0)
                    chg_abs = ind.get("change_abs", 0.0)
                    delta_str = f"{chg_pct:+.2f}% ({chg_abs:+.2f})"

                    st.metric(label=ind["name"], value=val_str, delta=delta_str)
                    chart = _render_sparkline_chart(ind.get("sparkline_30d", []))
                    if chart:
                        st.altair_chart(chart, width="stretch")

        st.markdown("<br>", unsafe_allow_html=True)

        # Sub-bloque B: Referencias Globales (EE.UU.)
        st.markdown("##### 🌍 Referencias Globales (EE.UU.)")
        col_global_ids = ["sp500", "nasdaq100", "bono_us_10y"]
        cols_global = st.columns(3)

        for idx_col, ind_id in enumerate(col_global_ids):
            with cols_global[idx_col]:
                ind = indicators_by_id.get(ind_id)
                if ind:
                    val = ind["current_value"]
                    unit = ind.get("unit", "")
                    val_str = f"{val:,.2f} {unit}"
                    chg_pct = ind.get("change_pct", 0.0)
                    chg_abs = ind.get("change_abs", 0.0)
                    delta_str = f"{chg_pct:+.2f}% ({chg_abs:+.2f})"

                    st.metric(label=ind["name"], value=val_str, delta=delta_str)
                    chart = _render_sparkline_chart(ind.get("sparkline_30d", []))
                    if chart:
                        st.altair_chart(chart, width="stretch")

    st.markdown("---")

    # 2. BLOQUE DE NOTICIAS DEPURADAS POR IA
    st.subheader("📰 Canal de Noticias y Pulso Económico (Perspectiva España)")
    news_data = api_client.get_market_news(limit=15)

    if not news_data or not news_data.get("news"):
        st.info("No hay noticias almacenadas actualmente. Pulsa '🔄 Actualizar Radar' para descargar y analizar los titulares.")
    else:
        ai_available = news_data.get("ai_analysis_available", False)
        if ai_available:
            st.caption("✨ Síntesis y análisis de impacto generados con inteligencia artificial (Google Gemini Pro).")
        else:
            st.warning("⚠️ Análisis de IA no disponible temporalmente. Mostrando titulares públicos.")

        all_news = news_data.get("news", [])

        # Filtros interactivos de Noticias
        col_f1, col_f2 = st.columns([1, 1])
        with col_f1:
            impact_options = ["Todos", "Alto", "Medio", "Bajo"]
            impact_selected = st.selectbox("🎯 Filtrar por Impacto:", impact_options, index=0)
        with col_f2:
            existing_topics = sorted(list({n.get("topic") for n in all_news if n.get("topic")}))
            topic_options = ["Todas"] + existing_topics
            topic_selected = st.selectbox("📂 Filtrar por Temática:", topic_options, index=0)

        # Aplicar filtros
        filtered = all_news
        if impact_selected != "Todos":
            filtered = [n for n in filtered if n.get("impact") == impact_selected]
        if topic_selected != "Todas":
            filtered = [n for n in filtered if n.get("topic") == topic_selected]

        st.caption(f"Mostrando {len(filtered)} de {len(all_news)} noticias")

        if not filtered:
            st.info("No hay noticias que coincidan con los filtros seleccionados.")
        else:
            for n in filtered:
                impact = n.get("impact", "Medio")
                topic = n.get("topic", "")
                title = n.get("title", "")
                summary = n.get("summary", "")
                source = n.get("source", "Fuente pública")
                link = n.get("link", "#")
                pub = n.get("published_at")
                pub_txt = f" • {pub[:16].replace('T', ' ')}" if pub else ""

                # Tarjeta visual de la noticia
                with st.container():
                    st.markdown(
                        f"""
                        <div class="news-card">
                            <div style="margin-bottom: 0.5rem;">
                                <span class="badge-impact badge-impact-{impact.lower()}">{impact}</span>
                                <span class="badge-topic">{topic}</span>
                            </div>
                            <h4 style="margin: 0.3rem 0; font-size: 1.05rem;">{title}</h4>
                            <p style="margin: 0.4rem 0 0.8rem 0; font-size: 0.95rem; opacity: 0.9; line-height: 1.4;">
                                {summary}
                            </p>
                            <div style="font-size: 0.82rem; opacity: 0.7;">
                                <span>📰 {source}{pub_txt}</span>
                                <span style="float: right;">
                                    <a href="{link}" target="_blank" style="text-decoration: none; font-weight: 500;">Leer noticia completa ↗</a>
                                </span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


# ==========================================
# PESTAÑA 15: SCREENER Y OPORTUNIDADES
# ==========================================
with tab_screener:
    col_sc_head, col_sc_btn = st.columns([8, 3])
    with col_sc_head:
        st.header("🔍 Screener Fundamental y Oportunidades de Inversión")
        st.caption("Cribado cuantitativo de renta variable y ETFs indexados con ratios contables, presets estratégicos y caché local de 24h.")
    with col_sc_btn:
        st.write("")

    # 1. SALVAGUARDA DE SEGURIDAD (Principio 9 de la Constitución)
    safety_status = api_client.get_safety_status(mes="BASE")
    if safety_status:
        is_safe = safety_status.get("is_safe", True)
        cov_months = float(safety_status.get("coverage_months", 0.0))
        target_months = float(safety_status.get("target_months", 3.0))
        gap = float(safety_status.get("gap", 0.0))

        if not is_safe or cov_months < 3.0:
            st.warning(
                f"⚠️ **Aviso de Salvaguarda Patrimonial (Principio 9 - Constitución)**: Tu fondo de emergencia actual cubre "
                f"**{cov_months:.1f} meses** de gastos esenciales (mínimo constitucional: **{target_months:.1f} meses**; "
                f"brecha por cubrir: **{gap:,.2f} €**). La asignación de ahorro hacia instrumentos con riesgo está bloqueada "
                f"en tus presupuestos. Este screener tiene fines formativos y de seguimiento de mercado.",
                icon="⚠️",
            )
        else:
            st.info(
                f"🛡️ **Salvaguarda Patrimonial Cumplida**: Tu fondo de emergencia cubre **{cov_months:.1f} meses** de gastos esenciales. "
                f"Asignación de capital a inversión permitida.",
                icon="✅",
            )

    st.markdown("---")

    # 2. SELECTOR DE UNIVERSO Y CONTROLES DE CACHÉ
    universe_options = {
        "ibex35": "🇪🇸 IBEX 35 (35 Acciones España)",
        "eurostoxx50": "🇪🇺 EuroStoxx 50 (50 Líderes Eurozona)",
        "sp500_top50": "🇺🇸 S&P 500 Top 50 (50 Mega-caps EE.UU.)",
        "etfs_referencia": "📈 ETFs de Referencia UCITS (15 Fondos Indexados)",
        "custom": "⚙️ Tickers Personalizados (Cesta a Medida)",
    }

    col_u_sel, col_u_ref = st.columns([8, 3])
    with col_u_sel:
        selected_universe = st.selectbox(
            "Selecciona el Universo de Activos a Inspeccionar",
            options=list(universe_options.keys()),
            format_func=lambda x: universe_options[x],
            key="screener_universe_selector",
        )
    with col_u_ref:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if selected_universe != "custom":
            if st.button("🔄 Actualizar Universo", width="stretch", key="btn_refresh_screener_univ"):
                with st.spinner("Descargando datos actualizados desde Yahoo Finance..."):
                    ref_res = api_client.refresh_screener_universe(selected_universe)
                    if ref_res:
                        st.success("¡Universo actualizado con éxito!")
                        st.rerun()
                    else:
                        st.error("Error al actualizar los datos del universo.")

    custom_tickers_list = []
    if selected_universe == "custom":
        custom_input = st.text_input(
            "Introduce tickers separados por coma (ej. ITX.MC, SAN.MC, AAPL, VWCE.DE)",
            value="ITX.MC, SAN.MC, AAPL, VWCE.DE",
            key="screener_custom_tickers_input",
        )
        custom_tickers_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]

    # 3. PRESETS RÁPIDOS Y ESTRATEGIAS
    if selected_universe == "etfs_referencia":
        preset_map = {
            "all": "Todos los ETFs",
            "low_cost_etf": "🛡️ ETFs de Bajo Coste (TER ≤ 0.25%, AUM ≥ 500M)",
            "high_dividend": "💰 Alto Dividendo (Yield ≥ 3.5%)",
        }
    else:
        preset_map = {
            "all": "Todos los valores",
            "quality": "💎 Calidad y Solvencia (ROE ≥ 15%, Margen ≥ 10%, Deuda ≤ 120%)",
            "high_dividend": "💰 Alto Dividendo (Yield ≥ 3.5%, PER Fwd ≤ 18)",
            "value": "🏷️ Valoración Atractiva (PER ≤ 15, P/B ≤ 2.0)",
            "growth": "🚀 Crecimiento (Margen Op ≥ 15%, ROE ≥ 12%, Beta ≥ 0.9)",
        }

    selected_preset = st.radio(
        "Estrategia Cuantitativa Rápida (Preset)",
        options=list(preset_map.keys()),
        format_func=lambda x: preset_map[x],
        horizontal=True,
        key="screener_preset_radio",
    )

    # 4. FILTROS AVANZADOS MANUALES
    with st.expander("⚙️ Filtros Manuales Avanzados", expanded=False):
        col_f_search, col_f_empty = st.columns([6, 6])
        with col_f_search:
            search_text = st.text_input("Buscar por Ticker, Compañía o Sector", key="screener_search_query_input")

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            filter_max_pe = st.number_input("PER Máximo", min_value=1.0, max_value=200.0, value=None, step=1.0, key="sc_max_pe")
        with col_f2:
            filter_min_div = st.number_input("Dividendo Mínimo (%)", min_value=0.0, max_value=25.0, value=None, step=0.5, key="sc_min_div")
        with col_f3:
            filter_min_roe = st.number_input("ROE Mínimo (%)", min_value=0.0, max_value=100.0, value=None, step=1.0, key="sc_min_roe")
        with col_f4:
            if selected_universe == "etfs_referencia":
                filter_max_ter = st.number_input("TER Máximo (%)", min_value=0.01, max_value=2.0, value=None, step=0.05, key="sc_max_ter")
                filter_max_debt = None
            else:
                filter_max_debt = st.number_input("Deuda/Patrimonio Máx. (%)", min_value=0.0, max_value=500.0, value=None, step=10.0, key="sc_max_debt")
                filter_max_ter = None

    # 5. OBTENCIÓN Y RENDERIZADO DE DATOS
    screener_data = None
    if selected_universe == "custom":
        if custom_tickers_list:
            filter_params_dict = {
                "preset": selected_preset,
                "search_query": search_text if search_text else None,
                "max_pe": filter_max_pe,
                "min_dividend_yield": filter_min_div,
                "min_roe": filter_min_roe,
                "max_debt_to_equity": filter_max_debt,
                "max_expense_ratio": filter_max_ter,
            }
            screener_data = api_client.get_screener_custom(custom_tickers_list, filter_params=filter_params_dict)
    else:
        screener_data = api_client.get_screener_universe(
            universe_id=selected_universe,
            preset=selected_preset if selected_preset != "all" else None,
            max_pe=filter_max_pe,
            min_dividend_yield=filter_min_div,
            min_roe=filter_min_roe,
            max_debt_to_equity=filter_max_debt,
            max_expense_ratio=filter_max_ter,
            search_query=search_text if search_text else None,
        )

    if not screener_data or "items" not in screener_data:
        st.info("Cargando activos del universo... Si es la primera vez que se consulta, puede demorarse unos segundos.")
    else:
        cached_tag = "📦 Desde caché local (24h)" if screener_data.get("from_cache") else "⚡ Datos en vivo"
        fetch_time = screener_data.get("updated_at", "")[:16].replace("T", " ")
        tot_c = screener_data.get("total_count", 0)
        filt_c = screener_data.get("filtered_count", 0)

        st.caption(f"{cached_tag} | Captura: {fetch_time} | Mostrando **{filt_c}** de **{tot_c}** activos disponibles")

        items_list = screener_data.get("items", [])
        if not items_list:
            st.warning("Ningún activo cumple con los criterios de filtrado seleccionados.")
        else:
            df_screener = pd.DataFrame(items_list)
            is_etf_view = selected_universe == "etfs_referencia"

            if is_etf_view:
                col_order = [
                    "ticker", "name", "category", "currency", "price", "change_pct",
                    "expense_ratio", "dividend_yield", "total_assets", "avg_volume", "beta"
                ]
                existing_cols = [c for c in col_order if c in df_screener.columns]
                df_view = df_screener[existing_cols].copy()
                etf_rename_map = {
                    "ticker": "Ticker",
                    "name": "Nombre ETF",
                    "category": "Categoría",
                    "currency": "Divisa",
                    "price": "Precio",
                    "change_pct": "Var. Diaria",
                    "expense_ratio": "TER (Costes)",
                    "dividend_yield": "Div. Yield",
                    "total_assets": "Patrimonio (AUM)",
                    "avg_volume": "Volumen Medio",
                    "beta": "Beta",
                }
                df_view.columns = [etf_rename_map.get(str(c), str(c)) for c in df_view.columns]

                col_config = {
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "Var. Diaria": st.column_config.NumberColumn(format="%.2f %%"),
                    "TER (Costes)": st.column_config.NumberColumn(format="%.2f %%"),
                    "Div. Yield": st.column_config.NumberColumn(format="%.2f %%"),
                    "Patrimonio (AUM)": st.column_config.NumberColumn(format="%,.0f €"),
                    "Volumen Medio": st.column_config.NumberColumn(format="%,.0f"),
                    "Beta": st.column_config.NumberColumn(format="%.2f"),
                }
            else:
                col_order = [
                    "ticker", "name", "sector", "currency", "price", "change_pct",
                    "pe_trailing", "pe_forward", "pb_ratio", "ev_to_ebitda",
                    "dividend_yield", "roe", "operating_margin", "net_margin",
                    "debt_to_equity", "beta"
                ]
                existing_cols = [c for c in col_order if c in df_screener.columns]
                df_view = df_screener[existing_cols].copy()
                stock_rename_map = {
                    "ticker": "Ticker",
                    "name": "Compañía",
                    "sector": "Sector",
                    "currency": "Divisa",
                    "price": "Precio",
                    "change_pct": "Var. Diaria",
                    "pe_trailing": "PER (Hist.)",
                    "pe_forward": "PER (Adel.)",
                    "pb_ratio": "P/B",
                    "ev_to_ebitda": "EV/EBITDA",
                    "dividend_yield": "Div. Yield",
                    "roe": "ROE",
                    "operating_margin": "Margen Op.",
                    "net_margin": "Margen Neto",
                    "debt_to_equity": "Deuda/Patr.",
                    "beta": "Beta",
                }
                df_view.columns = [stock_rename_map.get(str(c), str(c)) for c in df_view.columns]

                col_config = {
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "Var. Diaria": st.column_config.NumberColumn(format="%.2f %%"),
                    "PER (Hist.)": st.column_config.NumberColumn(format="%.2f x"),
                    "PER (Adel.)": st.column_config.NumberColumn(format="%.2f x"),
                    "P/B": st.column_config.NumberColumn(format="%.2f x"),
                    "EV/EBITDA": st.column_config.NumberColumn(format="%.2f x"),
                    "Div. Yield": st.column_config.NumberColumn(format="%.2f %%"),
                    "ROE": st.column_config.NumberColumn(format="%.2f %%"),
                    "Margen Op.": st.column_config.NumberColumn(format="%.2f %%"),
                    "Margen Neto": st.column_config.NumberColumn(format="%.2f %%"),
                    "Deuda/Patr.": st.column_config.NumberColumn(format="%.2f %%"),
                    "Beta": st.column_config.NumberColumn(format="%.2f"),
                }

            st.dataframe(
                df_view,
                width="stretch",
                hide_index=True,
                column_config=col_config,
            )

            # Botón de Descarga en CSV
            csv_data = df_view.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 Exportar Resultados a CSV",
                data=csv_data,
                file_name=f"screener_{selected_universe}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="btn_download_screener_csv",
            )


# ==========================================
# PESTAÑA 16: ANÁLISIS FUNDAMENTAL (DEEP DIVE)
# ==========================================
with tab_deepdive:
    st.header("🔬 Análisis Fundamental en Profundidad (Deep Dive)")
    st.caption("Diagnóstico contable cuantitativo a 4 años, algoritmo Piotroski F-Score (0-9) y tesis agéntica Quality Value con IA.")

    # 1. SALVAGUARDA DE SEGURIDAD (Principio 9 de la Constitución)
    safety_status = api_client.get_safety_status(mes="BASE")
    if safety_status:
        is_safe = safety_status.get("is_safe", True)
        cov_months = float(safety_status.get("coverage_months", 0.0))
        target_months = float(safety_status.get("target_months", 3.0))
        gap = float(safety_status.get("gap", 0.0))

        if not is_safe or cov_months < 3.0:
            st.warning(
                f"⚠️ **Aviso de Salvaguarda Patrimonial (Principio 9 - Constitución)**: Tu fondo de emergencia actual cubre "
                f"**{cov_months:.1f} meses** de gastos esenciales (mínimo constitucional: **{target_months:.1f} meses**; "
                f"brecha: **{gap:,.2f} €**). La asignación de ahorro hacia instrumentos con riesgo está bloqueada en tus presupuestos. "
                f"Este módulo tiene fines formativos y de diagnóstico contable previo.",
                icon="⚠️",
            )
        else:
            st.info(
                f"🛡️ **Salvaguarda Patrimonial Cumplida**: Tu fondo de emergencia cubre **{cov_months:.1f} meses** de gastos esenciales. "
                f"Asignación de capital a inversión permitida.",
                icon="✅",
            )

    st.markdown("---")

    # 2. SELECTOR DE TICKER Y GESTIÓN DE WATCHLIST
    watchlist_items = api_client.get_watchlist()
    watchlist_tickers = [w["ticker"] for w in watchlist_items] if watchlist_items else []

    col_search, col_watch_sel, col_btn_analizar, col_btn_ref = st.columns([4, 4, 2, 2])

    with col_search:
        ticker_val = st.text_input(
            "Símbolo Bursátil (Ticker)",
            value=st.session_state.get("deepdive_selected_ticker", "ITX.MC"),
            help="Introduce el ticker bursátil con su sufijo de mercado (ej. ITX.MC, SAN.MC, AAPL, MSFT)",
            key="deepdive_input_ticker_field",
        )
        ticker_input = (ticker_val or "").strip().upper()

    with col_watch_sel:
        watch_options = ["-- Seleccionar de Watchlist --"] + [f"{w['ticker']} - {w['name']}" for w in watchlist_items]
        selected_watch = st.selectbox(
            "O carga un valor de tu Watchlist",
            options=watch_options,
            key="deepdive_watchlist_quick_selector",
        )
        if selected_watch != "-- Seleccionar de Watchlist --":
            chosen_ticker = selected_watch.split(" - ")[0].strip().upper()
            if chosen_ticker != ticker_input:
                ticker_input = chosen_ticker
                st.session_state["deepdive_selected_ticker"] = chosen_ticker

    with col_btn_analizar:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        analizar_clicked = st.button("🔍 Analizar", width="stretch", key="btn_deepdive_analyze")

    with col_btn_ref:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        refresh_clicked = st.button("🔄 Refrescar", width="stretch", key="btn_deepdive_refresh")

    # Ejecución o recuperación del análisis
    active_ticker = ticker_input or "ITX.MC"

    if refresh_clicked:
        with st.spinner(f"Invalidando caché y reanalizando {active_ticker}..."):
            data = api_client.refresh_deepdive_analysis(active_ticker)
            if data:
                st.session_state[f"deepdive_data_{active_ticker}"] = data
                st.success(f"¡Análisis de {active_ticker} actualizado con éxito!")
            else:
                st.error(f"No se pudieron refrescar los datos para '{active_ticker}'. Comprueba el ticker y mercado.")
    elif analizar_clicked or f"deepdive_data_{active_ticker}" not in st.session_state:
        with st.spinner(f"Cargando diagnóstico financiero para {active_ticker}..."):
            data = api_client.get_deepdive_analysis(active_ticker)
            if data:
                st.session_state[f"deepdive_data_{active_ticker}"] = data
            else:
                st.error(f"No se pudieron encontrar estados financieros para '{active_ticker}'.")

    data = st.session_state.get(f"deepdive_data_{active_ticker}")

    if data:
        # Estado de caché
        if data.get("from_cache"):
            st.caption(f"⚡ Datos servidos desde la caché local de 24h. Última actualización: {str(data.get('updated_at', ''))[:19]}")
        else:
            st.caption(f"✨ Datos actualizados en directo. Fecha de extracción: {str(data.get('updated_at', ''))[:19]}")

        # Cabecera de la empresa
        name = data.get("name") or active_ticker
        sector = data.get("sector") or "General"
        industry = data.get("industry") or ""
        country = data.get("country") or ""
        currency = data.get("currency") or "EUR"
        curr_price = float(data.get("current_price", 0.0))
        day_chg = data.get("day_change_pct")

        chg_str = f"{day_chg:+.2f}%" if day_chg is not None else ""

        col_h1, col_h2 = st.columns([9, 3])
        with col_h1:
            st.subheader(f"{name} ({active_ticker})")
            st.write(f"🏢 **Sector**: {sector} | 🏭 **Industria**: {industry} | 📍 **País**: {country} | 💱 **Divisa**: {currency}")
            if data.get("description"):
                with st.expander("📖 Descripción del Negocio", expanded=False):
                    st.write(data["description"])

        with col_h2:
            st.metric("Cotización Actual", f"{curr_price:,.2f} {currency}", delta=chg_str)

        st.markdown("---")

        # 3. FILA DE MÉTRICAS CLAVE Y MÚLTIPLOS (KPIs)
        m_cap = data.get("market_cap")
        if m_cap:
            if m_cap >= 1e9:
                m_cap_str = f"{m_cap / 1e9:,.2f} B {currency}"
            else:
                m_cap_str = f"{m_cap / 1e6:,.2f} M {currency}"
        else:
            m_cap_str = "N/D"

        pe_t = data.get("pe_trailing")
        pe_f = data.get("pe_forward")
        ev_ebitda = data.get("ev_to_ebitda")
        pb = data.get("price_to_book")
        div_y = data.get("dividend_yield")
        fcf_m = data.get("fcf_metrics") or {}
        fcf_y = fcf_m.get("fcf_yield")
        roe = fcf_m.get("roe")
        roic = fcf_m.get("roic")

        kpi_cols = st.columns(6)
        kpi_cols[0].metric("Cap. Bursátil", m_cap_str)
        kpi_cols[1].metric("PER Trailing", f"{pe_t:.1f}x" if pe_t is not None else "N/D")
        kpi_cols[2].metric("EV/EBITDA", f"{ev_ebitda:.1f}x" if ev_ebitda is not None else "N/D")
        kpi_cols[3].metric("Price / Book", f"{pb:.1f}x" if pb is not None else "N/D")
        kpi_cols[4].metric("FCF Yield", f"{fcf_y:.1f}%" if fcf_y is not None else "N/D")
        kpi_cols[5].metric("ROE / ROIC", f"{roe:.1f}% / {roic:.1f}%" if roe is not None and roic is not None else "N/D")

        st.markdown("---")

        # 4. DIAGNÓSTICO PIOTROSKI F-SCORE (0 A 9 PUNTOS)
        piotroski = data.get("piotroski") or {}
        total_p = piotroski.get("total_score", 0)
        max_p = piotroski.get("max_score", 9)
        rating_p = piotroski.get("rating", "Aceptable")

        col_piot_score, col_piot_desc = st.columns([4, 8])
        with col_piot_score:
            if rating_p == "Excelente":
                st.success(f"### Piotroski F-Score: {total_p} / {max_p}\n**Salud Contable Excelente** 🟢")
            elif rating_p == "Aceptable":
                st.warning(f"### Piotroski F-Score: {total_p} / {max_p}\n**Salud Contable Aceptable** 🟡")
            else:
                st.error(f"### Piotroski F-Score: {total_p} / {max_p}\n**Riesgo Contable / Debilidad** 🔴")

            if data.get("is_financial_institution"):
                st.caption("ℹ️ *Entidad Financiera (Banco/Seguros): Puntuación adaptada a 7 criterios al no aplicar Margen Bruto ni Ratio Corriente.*")

        with col_piot_desc:
            with st.expander("📋 Ver Desglose de los Criterios Contables Evaluados", expanded=True):
                criteria_list = piotroski.get("criteria", [])
                if criteria_list:
                    p_data = []
                    for c in criteria_list:
                        icon = "✅ Cumple (1 pto)" if c.get("points") == 1 else "❌ No cumple (0 ptos)"
                        p_data.append({
                            "Regla": c.get("code"),
                            "Categoría": c.get("category", "").capitalize(),
                            "Evaluación": icon,
                            "Descripción": c.get("description"),
                        })
                    st.dataframe(pd.DataFrame(p_data), width="stretch", hide_index=True)

        st.markdown("---")

        # 5. GRÁFICOS HISTÓRICOS Y EVOLUCIÓN CONTABLE
        statements = data.get("statements", [])
        if statements:
            st.subheader("📊 Historial Financiero Consolidado")

            df_hist = pd.DataFrame(statements)
            df_hist_sorted = df_hist.sort_values("year", ascending=True).copy()

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**Evolución de Ingresos y Beneficio Neto (€)**")
                chart_data_rev = df_hist_sorted[["year", "revenue", "net_income"]].copy()
                chart_data_rev["year"] = chart_data_rev["year"].astype(str)
                chart_rev = alt.Chart(chart_data_rev).transform_fold(
                    ["revenue", "net_income"], as_=["Métrica", "Importe"]
                ).mark_bar().encode(
                    x=alt.X("year:O", title="Año"),
                    y=alt.Y("Importe:Q", title="Importe (€)"),
                    color=alt.Color("Métrica:N", scale=alt.Scale(domain=["revenue", "net_income"], range=["#1565c0", "#2e7d32"])),
                    xOffset="Métrica:N",
                    tooltip=["year:O", "Métrica:N", alt.Tooltip("Importe:Q", format=",.0f")]
                ).properties(height=280)
                st.altair_chart(chart_rev, width="stretch")

            with col_g2:
                st.markdown("**Generación de Flujos de Caja: CFO vs CapEx vs FCF (€)**")
                chart_data_cf = df_hist_sorted[["year", "operating_cash_flow", "capital_expenditure", "free_cash_flow"]].copy()
                chart_data_cf["year"] = chart_data_cf["year"].astype(str)
                chart_cf = alt.Chart(chart_data_cf).transform_fold(
                    ["operating_cash_flow", "capital_expenditure", "free_cash_flow"], as_=["Flujo", "Importe"]
                ).mark_line(point=True).encode(
                    x=alt.X("year:O", title="Año"),
                    y=alt.Y("Importe:Q", title="Importe (€)"),
                    color=alt.Color("Flujo:N", scale=alt.Scale(domain=["operating_cash_flow", "capital_expenditure", "free_cash_flow"], range=["#00838f", "#ef6c00", "#2e7d32"])),
                    tooltip=["year:O", "Flujo:N", alt.Tooltip("Importe:Q", format=",.0f")]
                ).properties(height=280)
                st.altair_chart(chart_cf, width="stretch")

            # Tabla resumen de estados contables
            with st.expander("📑 Ver Tabla Completa de Estados Financieros Históricos"):
                disp_cols = [
                    "year", "revenue", "gross_profit", "operating_income", "net_income",
                    "operating_cash_flow", "capital_expenditure", "free_cash_flow",
                    "total_assets", "total_debt", "cash_and_equivalents"
                ]
                existing_cols = [c for c in disp_cols if c in df_hist.columns]
                df_table = df_hist[existing_cols].copy()
                table_rename_map = {
                    "year": "Año",
                    "revenue": "Ingresos",
                    "gross_profit": "Beneficio Bruto",
                    "operating_income": "EBIT / Beneficio Op.",
                    "net_income": "Beneficio Neto",
                    "operating_cash_flow": "CFO (Caja Operativa)",
                    "capital_expenditure": "CapEx",
                    "free_cash_flow": "FCF (Caja Libre)",
                    "total_assets": "Activo Total",
                    "total_debt": "Deuda Total",
                    "cash_and_equivalents": "Efectivo",
                }
                df_table.columns = [table_rename_map.get(str(c), str(c)) for c in df_table.columns]
                st.dataframe(df_table, width="stretch", hide_index=True)

        st.markdown("---")

        # 6. INFORME AGÉNTICO QUALITY VALUE (IA CON GEMINI)
        st.subheader("🤖 Tesis Agéntica de Inversión (Quality Value)")
        report = data.get("quality_value_report")

        if report:
            quadrant = report.get("quadrant", "Quality Value")
            if quadrant == "Quality Value":
                st.markdown(
                    f"<div class='quadrant-quality-value'><h3>💎 Cuadrante: {quadrant}</h3>"
                    f"<p>Excelente negocio con retornos sostenibles sobre el capital, foso defensivo y cotizando a múltiplo razonable.</p></div>",
                    unsafe_allow_html=True,
                )
            elif quadrant == "Calidad Cara":
                st.markdown(
                    f"<div class='quadrant-calidad-cara'><h3>⭐ Cuadrante: {quadrant}</h3>"
                    f"<p>Gran negocio con sólidas ventajas competitivas pero cotizando a múltiplos muy exigentes que reducen el margen de seguridad.</p></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='quadrant-trampa-valor'><h3>⚠️ Cuadrante: {quadrant}</h3>"
                    f"<p>Negocio aparentemente barato por múltiplos simples pero con deterioro estructural de foso o quema de caja.</p></div>",
                    unsafe_allow_html=True,
                )

            st.markdown(f"**Tesis Ejecutiva**: {report.get('summary_thesis')}")

            # 6 Ingredientes
            st.markdown("#### 🔍 Evaluación de los 6 Ingredientes Clave")
            ingredients = report.get("six_ingredients") or {}
            ing_cols1, ing_cols2 = st.columns(2)
            with ing_cols1:
                st.info(f"**📈 Crecimiento a Largo Plazo**: {ingredients.get('long_term_growth', 'N/D')}")
                st.info(f"**🌬️ Vientos de Cola**: {ingredients.get('tailwinds', 'N/D')}")
                st.info(f"**👑 Liderazgo de Mercado**: {ingredients.get('market_leadership', 'N/D')}")
            with ing_cols2:
                st.info(f"**🏰 Foso Defensivo (Moat)**: {ingredients.get('moat', 'N/D')}")
                st.info(f"**💰 Rentabilidad sobre Capital (ROIC/ROE)**: {ingredients.get('high_returns_on_capital', 'N/D')}")
                st.info(f"**⏳ Dificultades Temporales / Descuento**: {ingredients.get('temporary_headwinds', 'N/D')}")

            # Doble Tesis y Matriz de Riesgos
            st.markdown("#### 🛡️ Matriz de Riesgos: \"¿Qué puede salir mal y cuánto beneficio destruiría?\"")
            b_model = report.get("business_model_and_risks") or {}
            if b_model:
                st.write(f"**Dinámica de Negocio**: {b_model.get('business_model', b_model.get('cash_cycle', 'Generación recurrente de caja.'))}")

            bearish = report.get("bearish_risks") or []
            for r in bearish:
                st.error(f"🔻 **Riesgo Bajista**: {r}")

            # Valoración y Zona de Entrada por TIR
            st.markdown("#### 🎯 Valoración a 5 Años y Zona de Entrada Ideal (TIR 15% - 20%)")
            target_zone = report.get("target_irr_entry_zone", "N/D")

            # 1. Tarjeta destacada de Zona de Compra con Margen de Seguridad
            st.markdown(
                f"<div class='valuation-entry-zone-card'>"
                f"<div style='display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;'>"
                f"  <div>"
                f"    <span style='font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; color: #2e7d32;'>🎯 Zona de Compra con Margen de Seguridad</span>"
                f"    <div style='font-size: 1.45rem; font-weight: 800; margin-top: 0.2rem;'>{target_zone}</div>"
                f"  </div>"
                f"  <div style='text-align: right;'>"
                f"    <span style='font-size: 0.82rem; color: gray;'>Cotización Actual</span>"
                f"    <div style='font-size: 1.25rem; font-weight: 700;'>{curr_price:,.2f} {currency}</div>"
                f"  </div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # 2. Análisis y Comparación de Escenarios Proyectados a 5 Años
            val_proj = report.get("valuation_projections") or {}

            def _clean_val(val):
                if val is None:
                    return None
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    clean = val.replace("€", "").replace("$", "").replace("%", "").replace("x", "").replace("X", "").strip()
                    try:
                        return float(clean)
                    except ValueError:
                        return None
                return None

            base_raw = val_proj.get("scenario_base") or val_proj.get("base") or {}
            stress_raw = val_proj.get("scenario_stress") or val_proj.get("stress") or {}

            base_target = _clean_val(base_raw.get("target_price", base_raw.get("precio_objetivo")))
            base_pe = _clean_val(base_raw.get("exit_multiple", base_raw.get("multiplo_salida")))
            base_irr = _clean_val(base_raw.get("expected_irr", base_raw.get("tir_esperada", base_raw.get("irr"))))

            stress_target = _clean_val(stress_raw.get("target_price", stress_raw.get("precio_objetivo")))
            stress_pe = _clean_val(stress_raw.get("exit_multiple", stress_raw.get("multiplo_salida")))
            stress_irr = _clean_val(stress_raw.get("expected_irr", stress_raw.get("tir_esperada", stress_raw.get("irr"))))

            delta_base_str = None
            delta_stress_str = None

            if base_target is not None or stress_target is not None:
                col_sc_base, col_sc_stress = st.columns(2)

                with col_sc_base:
                    st.markdown(
                        "<div class='valuation-scenario-card valuation-scenario-card-base'>"
                        "<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;'>"
                        "  <strong style='font-size: 1.05rem;'>📈 Escenario Base (Central)</strong>"
                        "  <span class='valuation-badge-base'>Probabilidad Central</span>"
                        "</div>"
                        "<p style='font-size: 0.84rem; color: gray; margin-bottom: 0.75rem;'>"
                        "Crecimiento secular de ingresos, mantenimiento de márgenes operativos y conversión de caja sólida a 5 años."
                        "</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    m1, m2, m3 = st.columns(3)
                    delta_base = ((base_target - curr_price) / curr_price * 100.0) if (base_target and curr_price) else None
                    delta_base_str = f"{delta_base:+.1f}%" if delta_base is not None else None
                    m1.metric("Precio Obj. 5A", f"{base_target:,.2f} {currency}" if base_target else "N/D", delta=delta_base_str)
                    m2.metric("TIR Esperada", f"{base_irr:.1f}% / año" if base_irr is not None else "N/D", help="Tasa Interna de Retorno anualizada esperada a 5 años")
                    m3.metric("Múltiplo PER", f"{base_pe:.1f}x" if base_pe is not None else "N/D", help="Múltiplo de salida proyectado al año 5")

                with col_sc_stress:
                    st.markdown(
                        "<div class='valuation-scenario-card valuation-scenario-card-stress'>"
                        "<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;'>"
                        "  <strong style='font-size: 1.05rem;'>🛡️ Escenario de Estrés (Conservador)</strong>"
                        "  <span class='valuation-badge-stress'>Margen de Seguridad</span>"
                        "</div>"
                        "<p style='font-size: 0.84rem; color: gray; margin-bottom: 0.75rem;'>"
                        "Compresión de múltiplos por tipos altos, desaceleración macro o presiones competitivas transitorias."
                        "</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    s1, s2, s3 = st.columns(3)
                    delta_stress = ((stress_target - curr_price) / curr_price * 100.0) if (stress_target and curr_price) else None
                    delta_stress_str = f"{delta_stress:+.1f}%" if delta_stress is not None else None
                    s1.metric("Precio Obj. 5A", f"{stress_target:,.2f} {currency}" if stress_target else "N/D", delta=delta_stress_str)
                    s2.metric("TIR Esperada", f"{stress_irr:.1f}% / año" if stress_irr is not None else "N/D", help="Tasa Interna de Retorno anualizada en escenario de estrés")
                    s3.metric("Múltiplo PER", f"{stress_pe:.1f}x" if stress_pe is not None else "N/D", help="Múltiplo de salida comprimido al año 5")

                # Tabla Comparativa Sintética
                summary_data = [
                    {
                        "Métrica Financiera a 5 Años": "Precio Objetivo por Acción",
                        "Escenario de Estrés 🛡️": f"{stress_target:,.2f} {currency} ({delta_stress_str})" if stress_target else "N/D",
                        "Cotización Actual 📍": f"{curr_price:,.2f} {currency}",
                        "Escenario Base 📈": f"{base_target:,.2f} {currency} ({delta_base_str})" if base_target else "N/D",
                        "Zona de Entrada Óptima 🎯": target_zone,
                    },
                    {
                        "Métrica Financiera a 5 Años": "Múltiplo de Salida (PER)",
                        "Escenario de Estrés 🛡️": f"{stress_pe:.1f}x" if stress_pe else "N/D",
                        "Cotización Actual 📍": f"{pe_t:.1f}x" if pe_t is not None else "N/D",
                        "Escenario Base 📈": f"{base_pe:.1f}x" if base_pe else "N/D",
                        "Zona de Entrada Óptima 🎯": "Margen de Seguridad",
                    },
                    {
                        "Métrica Financiera a 5 Años": "Rentabilidad Anual Compuesta (TIR)",
                        "Escenario de Estrés 🛡️": f"{stress_irr:.1f}% / año" if stress_irr is not None else "N/D",
                        "Cotización Actual 📍": "—",
                        "Escenario Base 📈": f"{base_irr:.1f}% / año" if base_irr is not None else "N/D",
                        "Zona de Entrada Óptima 🎯": "15.0% - 20.0% / año",
                    },
                ]
                st.dataframe(pd.DataFrame(summary_data), width="stretch", hide_index=True)

            if val_proj:
                with st.expander("🔎 Ver JSON técnico estructurado"):
                    st.json(val_proj)
        else:
            st.info(
                "ℹ️ **Síntesis Agéntica con IA no disponible**: Los datos cuantitativos, ratios contables y Piotroski Score "
                "están calculados con precisión matemática local en Python. La generación de la tesis cualitativa requiere configurar "
                "la clave `GEMINI_API_KEY` en tu archivo `.env`.",
                icon="ℹ️",
            )

        st.markdown("---")

        # 7. GESTIÓN DE LA WATCHLIST PARA EL VALOR ACTUAL
        st.subheader("⭐ Lista de Seguimiento (Watchlist)")
        is_in_watch = active_ticker in watchlist_tickers

        col_w_info, col_w_act = st.columns([8, 4])
        with col_w_info:
            if is_in_watch:
                matched_w = [w for w in watchlist_items if w["ticker"] == active_ticker][0]
                st.write(f"📌 **Guardado en Watchlist**: Añadido a **{matched_w.get('price_at_addition', 0):,.2f} {currency}**.")
                if matched_w.get("notes"):
                    st.caption(f"📝 Notas: {matched_w['notes']}")
            else:
                st.write(f"Este activo no está en tu lista de seguimiento.")

        with col_w_act:
            if is_in_watch:
                if st.button("🗑️ Eliminar de Watchlist", key="btn_del_from_watchlist"):
                    if api_client.remove_from_watchlist(active_ticker):
                        st.success(f"¡{active_ticker} eliminado de la Watchlist!")
                        st.rerun()
                    else:
                        st.error("Error al eliminar el activo.")
            else:
                notes_input = st.text_input("Notas u objetivo de compra", key="notes_for_watchlist")
                if st.button("⭐ Añadir a Watchlist", key="btn_add_to_watchlist"):
                    add_payload = {
                        "ticker": active_ticker,
                        "name": name,
                        "sector": sector,
                        "currency": currency,
                        "price_at_addition": curr_price,
                        "notes": notes_input or None,
                    }
                    res_add = api_client.add_to_watchlist(add_payload)
                    if res_add:
                        st.success(f"¡{active_ticker} guardado en tu Watchlist!")
                        st.rerun()
                    else:
                        st.error("Error al guardar en Watchlist.")

        # 8. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
        st.markdown("---")
        st.caption(
            "⚖️ **Descargo Legal (Disclaimer)**: Esta herramienta de diagnóstico y la síntesis generada por IA "
            "tienen carácter exclusivamente formativo e informativo. No constituyen recomendación de compra o venta "
            "ni asesoramiento financiero regulado. Los rendimientos pasados no garantizan rentabilidades futuras."
        )


# ==========================================
# PESTAÑA 17: COPILOTO PATRIMONIAL (SPEC 004)
# ==========================================
with tab_copilot:
    st.header("💬 Copiloto Patrimonial")
    st.caption(
        "Asistente conversacional de inteligencia financiera con Function Calling bajo demanda y doble tesis obligatoria."
    )

    safety_info = api_client.get_safety_status()
    if safety_info:
        cov_months = float(safety_info.get("coverage_months", 0.0))
        inv_allowed = bool(safety_info.get("can_invest") if "can_invest" in safety_info else safety_info.get("investing_allowed", False))
        if not inv_allowed or cov_months < 3.0:
            st.warning(
                f"🛡️ **Salvaguarda de Seguridad Activa (Principio 9)**: Tu Fondo de Emergencia cubre "
                f"**{cov_months:.1f} meses** de necesidades básicas (mínimo constitucional: **3.0 meses**). "
                f"El Copiloto vetará cualquier recomendación de renta variable o instrumentos con riesgo hasta que el fondo esté completo."
            )
        else:
            st.info(
                f"✅ **Salvaguarda Superada**: Tu Fondo de Emergencia cubre **{cov_months:.1f} meses** "
                f"(objetivo constitucional cumplido). Puedes planificar asignaciones de inversión responsable con tu saldo 'Sin Asignar'."
            )

    st.markdown("---")

    # 2. GESTIÓN DE SESIONES DE CONVERSACIÓN
    if "copilot_session_id" not in st.session_state:
        st.session_state["copilot_session_id"] = None

    copilot_sessions = api_client.get_copilot_sessions()
    sess_col1, sess_col2, sess_col3 = st.columns([6, 3, 3])

    with sess_col1:
        if copilot_sessions:
            session_map = {
                s["id"]: f"{s.get('title', 'Conversación')} ({s.get('message_count', 0)} msgs)"
                for s in copilot_sessions
            }
            if (
                st.session_state["copilot_session_id"] not in session_map
                and len(copilot_sessions) > 0
            ):
                st.session_state["copilot_session_id"] = copilot_sessions[0]["id"]

            active_sess_id = st.session_state["copilot_session_id"]
            active_idx = (
                list(session_map.keys()).index(active_sess_id)
                if active_sess_id in session_map
                else 0
            )

            chosen_sess_id = st.selectbox(
                "Conversación activa:",
                options=list(session_map.keys()),
                index=active_idx,
                format_func=lambda sid: session_map.get(sid, str(sid)),
                key="copilot_session_selector",
            )
            st.session_state["copilot_session_id"] = chosen_sess_id
        else:
            st.write("*(No hay conversaciones guardadas)*")

    with sess_col2:
        st.write("")
        st.write("")
        if st.button("➕ Nueva conversación", key="btn_new_copilot_sess", width="stretch"):
            new_sess = api_client.create_copilot_session()
            if new_sess and "id" in new_sess:
                st.session_state["copilot_session_id"] = new_sess["id"]
                st.rerun()

    with sess_col3:
        st.write("")
        st.write("")
        if st.session_state["copilot_session_id"]:
            if st.button("🗑️ Eliminar conversación", key="btn_del_copilot_sess", width="stretch"):
                api_client.delete_copilot_session(st.session_state["copilot_session_id"])
                st.session_state["copilot_session_id"] = None
                st.rerun()

    st.markdown("---")

    # 3. RENDERIZADO DE MENSAJES HISTÓRICOS
    current_session_id = st.session_state.get("copilot_session_id")
    messages = []
    if current_session_id:
        detail_data = api_client.get_copilot_session_detail(current_session_id)
        if detail_data and "messages" in detail_data:
            messages = detail_data["messages"]

    if not messages:
        st.markdown(
            """
            <div class="copilot-welcome-card">
                <h4>👋 ¡Bienvenido a tu Copiloto Patrimonial!</h4>
                <p>Estoy aquí para ayudarte a tomar decisiones financieras prudentes, planificar tu presupuesto 50/30/20 y auditar oportunidades de inversión con máxima objetividad.</p>
                <p><strong>Ejemplos de preguntas que puedes hacerme:</strong></p>
                <ul>
                    <li><em>"¿Cómo está mi presupuesto este mes y cuánto tengo en 'Sin Asignar'?"</em></li>
                    <li><em>"¿Puedo empezar a invertir en fondos o bolsa este mes?"</em></li>
                    <li><em>"¿Qué valores tengo guardados en mi Watchlist?"</em></li>
                    <li><em>"¿Cuál es el análisis fundamental y la tesis Quality Value de ITX.MC?"</em></li>
                    <li><em>"¿Qué riesgos bajistas tiene Apple antes de plantearme comprar?"</em></li>
                    <li><em>"¿Cómo están los tipos de interés del BCE y la prima de riesgo de España?"</em></li>
                </ul>
                <p><small>🔒 <em>Tus datos contables privados residen exclusivamente en tu base de datos SQLite local y sólo son consultados cuando tu pregunta lo requiere.</em></small></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for msg in messages:
            msg_role = msg.get("role", "assistant")
            msg_content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")

            with st.chat_message(msg_role):
                st.markdown(msg_content)
                if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                    with st.expander(f"🔧 Herramientas consultadas ({len(tool_calls)})", expanded=False):
                        for tc in tool_calls:
                            tool_name = tc.get("tool", "herramienta")
                            tool_args = tc.get("args", {})
                            st.markdown(f"- **`{tool_name}`**: `{tool_args}`")

    # 4. ENTRADA INTERACTIVA DE CHAT (st.chat_input)
    if chat_input := st.chat_input("Escribe tu consulta financiera al Copiloto..."):
        # Mostrar el mensaje del usuario de inmediato en la UI
        with st.chat_message("user"):
            st.markdown(chat_input)

        with st.spinner("El Copiloto está analizando datos y razonando..."):
            chat_response = api_client.send_copilot_chat(
                message=chat_input,
                session_id=current_session_id,
            )

        if chat_response:
            st.session_state["copilot_session_id"] = chat_response["session_id"]
            st.rerun()
        else:
            st.error("No se pudo obtener respuesta del Copiloto. Comprueba que el backend FastAPI esté ejecutándose.")

    # 5. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
    st.markdown("---")
    st.caption(
        "⚖️ **Descargo de Responsabilidad Legal (Disclaimer)**: El Copiloto Patrimonial es una herramienta de asistencia formativa y de soporte analítico. "
        "No constituye asesoramiento financiero regulado (MiFID II / CNMV), recomendación vinculante de inversión ni oferta de productos financieros. "
        "Toda decisión de inversión conlleva riesgo de pérdida de capital y debe basarse en tu propio análisis prudente."
    )


# ========================================================
# PESTAÑA 18: COMITÉ ASESOR MULTIAGENTE (SPEC 005 - LANGGRAPH)
# ========================================================
with tab_committee:
    st.header("🏛️ Comité Asesor de Inversión Multiagente")
    st.caption(
        "Órgano colegiado de deliberación patrimonial orquestado con LangGraph. Coordina cinco agentes cognitivos especializados "
        "con veto constitucional vinculante (Principio 9) y auditoría obligatoria de doble tesis (Principio 12)."
    )

    # 1. SALVAGUARDA DE SEGURIDAD PATRIMONIAL (Principio 9 de la Constitución)
    safety_committee = api_client.get_safety_status()
    if safety_committee:
        cov_m = float(safety_committee.get("coverage_months", 0.0))
        inv_ok = bool(safety_committee.get("can_invest") if "can_invest" in safety_committee else safety_committee.get("investing_allowed", False))
        target_3m = float(safety_committee.get("target_amount") or safety_committee.get("target_3m", 0.0))
        curr_bal = float(safety_committee.get("current_balance", 0.0))
        unassigned_bal = float(safety_committee.get("unassigned_balance", 0.0))

        if not inv_ok or cov_m < 3.0:
            st.markdown(
                f"""
                <div class="committee-veto-banner">
                    <h4 style="margin: 0; color: #b71c1c;">⛔ Veto Constitucional Activo (Principio 9 de la Constitución)</h4>
                    <p style="margin-top: 0.5rem; margin-bottom: 0.2rem;">
                        Tu Fondo de Emergencia cubre actualmente <strong>{cov_m:.1f} meses</strong> ({curr_bal:,.2f} €) de tus gastos esenciales.
                        El mínimo constitucional obligatorio es de <strong>3.0 meses</strong> ({target_3m:,.2f} €).
                    </p>
                    <p style="margin: 0; font-size: 0.88rem; color: #c62828;">
                        <em>El Comité Asesor bloqueará de forma inmediata cualquier asignación a renta variable o activos con riesgo y emitirá un plan de acción para completar tu colchón de liquidez.</em>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            unassigned_desc = f"Dispones de <strong>{unassigned_bal:,.2f} €</strong> en saldo 'Sin Asignar' para inversión estratégica." if unassigned_bal > 0 else "Tienes capacidad autorizada para evaluar asignaciones de inversión estratégica."
            st.markdown(
                f"""
                <div class="committee-approved-banner">
                    <h4 style="margin: 0; color: #1b5e20;">🛡️ Salvaguarda Patrimonial Superada (Cobertura: {cov_m:.1f} meses)</h4>
                    <p style="margin-top: 0.5rem; margin-bottom: 0.2rem;">
                        Tu Fondo de Emergencia ({curr_bal:,.2f} €) supera el umbral constitucional de 3 meses.
                        {unassigned_desc}
                    </p>
                    <p style="margin: 0; font-size: 0.88rem; color: #2e7d32;">
                        <em>El Comité deliberará la conveniencia y tramos de entrada bajo la estricta formulación de la doble tesis (mínimo 2 riesgos bajistas obligatorios).</em>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # 2. FORMULARIO DE CONVOCATORIA DEL COMITÉ
    st.subheader("📋 Convocatoria de Deliberación")

    # Recuperar lista de seguimiento para facilitar la selección de empresas
    watch_items_com = api_client.get_watchlist()
    watch_tickers = [w["ticker"] for w in watch_items_com] if watch_items_com else []

    col_c1, col_c2 = st.columns([6, 6])
    with col_c1:
        tipo_analisis = st.radio(
            "Modalidad de deliberación:",
            options=["Activo específico (Empresa / ETF)", "Consulta patrimonial general (Sin ticker)"],
            horizontal=True,
            key="committee_tipo_analisis",
        )

        selected_ticker = None
        if tipo_analisis == "Activo específico (Empresa / ETF)":
            ticker_options = ["(Ingresar manualmente)"] + watch_tickers
            chosen_option = st.selectbox(
                "Seleccionar ticker:",
                options=ticker_options,
                help="Puedes seleccionar una empresa de tu Watchlist o escribir cualquier ticker de mercado.",
                key="committee_ticker_select",
            )
            if chosen_option == "(Ingresar manualmente)":
                manual_ticker = st.text_input(
                    "Símbolo bursátil (ej. ITX.MC, SAN.MC, AAPL, IWDA.AS):",
                    value="ITX.MC",
                    key="committee_manual_ticker",
                )
                selected_ticker = manual_ticker.strip().upper() if manual_ticker else None
            else:
                selected_ticker = chosen_option

    with col_c2:
        mes_auditar = st.selectbox(
            "Mes contable de referencia:",
            options=["BASE"] + [f"{year_selected}-{m:02d}" for m in range(1, 13)],
            index=0,
            help="Mes para evaluar la liquidez real disponible y los gastos esenciales.",
            key="committee_month_select",
        )

        user_notes = st.text_area(
            "Notas o directrices del usuario (opcional):",
            placeholder="Ejemplo: Perfil moderado, horizonte temporal a 5 años, dudas sobre el impacto de tipos del BCE...",
            max_chars=500,
            height=78,
            key="committee_user_notes",
        )

    st.write("")
    btn_deliberar = st.button(
        "🚀 Convocar Deliberación del Comité Asesor",
        type="primary",
        width="stretch",
        key="btn_run_committee",
    )

    if btn_deliberar:
        with st.spinner("🏛️ El Comité Asesor de Inversión está deliberando en LangGraph (Salvaguarda ➔ Macro ➔ Fundamental ➔ Debate de Riesgos ➔ Síntesis)..."):
            res_committee = api_client.run_investment_committee(
                ticker=selected_ticker,
                month=mes_auditar,
                initial_notes=user_notes,
            )
            if res_committee:
                st.session_state["committee_result"] = res_committee
                st.success("¡Deliberación del Comité completada con éxito!")
            else:
                st.error("No se pudo completar la deliberación. Asegúrate de que el backend FastAPI esté ejecutándose.")

    # 3. RENDERIZADO DEL INFORME Y VEREDICTO FINAL
    committee_data = st.session_state.get("committee_result")
    if committee_data:
        st.markdown("---")
        st.subheader("📑 Dictamen Oficial del Comité Asesor")

        veto_flag = committee_data.get("veto_active", False)
        veredicto_txt = committee_data.get("final_verdict", "Sin veredicto emitido.")
        action_plan_txt = committee_data.get("action_plan", "")
        ticker_reportado = committee_data.get("ticker")
        mes_reportado = committee_data.get("month", "BASE")

        # 3.1 TARJETA DEL VEREDICTO FINAL
        if veto_flag:
            st.error(veredicto_txt)
        else:
            st.markdown(
                f"""
                <div class="committee-verdict-card">
                    <h3 style="margin-top: 0; color: #1565c0;">⚖️ Veredicto Vinculante del Comité — {ticker_reportado or 'Patrimonio General'} (Mes {mes_reportado})</h3>
                    <div style="font-size: 1.05rem; line-height: 1.6; white-space: pre-wrap;">{veredicto_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3.2 PLAN DE ACCIÓN ESTRATÉGICO
        if action_plan_txt:
            st.markdown(
                f"""
                <div class="committee-action-card">
                    <h4 style="margin-top: 0; color: #0d47a1;">📋 Plan de Acción y Despliegue de Liquidez</h4>
                    <div style="white-space: pre-wrap; font-size: 0.95rem; line-height: 1.6;">{action_plan_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3.3 AUDITORÍA DE DOBLE TESIS (PRINCIPIO 12 DE LA CONSTITUCIÓN)
        if not veto_flag and ticker_reportado:
            st.subheader("⚖️ Auditoría de Doble Tesis (Principio 12)")
            col_bull, col_bear = st.columns(2)

            bull_thesis_txt = committee_data.get("bull_thesis") or "Fundamentales sólidos y ventaja competitiva contrastada."
            bear_risks_list = committee_data.get("bear_risks") or []

            with col_bull:
                st.markdown(
                    f"""
                    <div class="committee-bull-card">
                        <h4 style="margin-top: 0; color: #1b5e20;">🐂 Tesis Favorable & Moat (Bull Case)</h4>
                        <div style="white-space: pre-wrap; font-size: 0.92rem; line-height: 1.5;">{bull_thesis_txt}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_bear:
                risks_html = "".join([f"<li style='margin-bottom: 0.45rem;'><strong>{r}</strong></li>" for r in bear_risks_list])
                st.markdown(
                    f"""
                    <div class="committee-bear-card">
                        <h4 style="margin-top: 0; color: #b71c1c;">🐻 Auditoría Red Team (Bear Risks Obligatorios)</h4>
                        <p style="font-size: 0.85rem; color: #c62828; margin-bottom: 0.6rem;">
                            <em>"¿Qué puede salir mal y cuánto beneficio destruiría?"</em>
                        </p>
                        <ul style="font-size: 0.92rem; line-height: 1.45; padding-left: 1.2rem; margin: 0;">
                            {risks_html}
                        </ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # 3.4 CRONOLOGÍA Y TRAZABILIDAD DE LOS AGENTES EN LANGGRAPH
        agent_logs = committee_data.get("agent_logs") or []
        if agent_logs:
            st.markdown("---")
            st.subheader(f"🔄 Deliberación Paso a Paso de los Agentes ({len(agent_logs)} Intervenciones)")

            for idx, log in enumerate(agent_logs, start=1):
                agent_name = log.get("agent", "Agente")
                log_time = log.get("timestamp", "")
                log_msg = log.get("message", "")
                data_keys = log.get("data_keys", [])

                # Asignar badge según rol
                if "Safety" in agent_name:
                    badge_class = "badge-agent-safety"
                    agent_title = f"🛡️ Paso {idx}: Salvaguarda Patrimonial ({agent_name})"
                elif "Macro" in agent_name:
                    badge_class = "badge-agent-macro"
                    agent_title = f"🌐 Paso {idx}: Contexto Macroeconómico ({agent_name})"
                elif "Fundamental" in agent_name:
                    badge_class = "badge-agent-fundamental"
                    agent_title = f"🔬 Paso {idx}: Diagnóstico Contable ({agent_name})"
                elif "Risk" in agent_name:
                    badge_class = "badge-agent-risk"
                    agent_title = f"🐻 Paso {idx}: Red Team & Doble Tesis ({agent_name})"
                else:
                    badge_class = "badge-agent-advisor"
                    agent_title = f"⚖️ Paso {idx}: Síntesis y Veredicto Final ({agent_name})"

                with st.expander(agent_title, expanded=(idx == len(agent_logs) or "Veto" in log_msg)):
                    col_l1, col_l2 = st.columns([9, 3])
                    with col_l1:
                        st.markdown(f"**Conclusión del agente**: {log_msg}")
                    with col_l2:
                        st.caption(f"⏱️ {log_time[:19].replace('T', ' ')}")

                    if data_keys:
                        st.write("🔑 *Claves inyectadas al estado compartido:*")
                        st.code(", ".join(data_keys), language="text")

        # 3.5 DIAGNÓSTICOS CUANTITATIVOS AUXILIARES
        macro_sum = committee_data.get("macro_summary")
        fund_sum = committee_data.get("fundamental_summary")
        if macro_sum or fund_sum:
            st.markdown("---")
            st.subheader("📊 Datos Cuantitativos de Soporte")
            tab_diag_m, tab_diag_f = st.tabs(["🌐 Indicadores Macro", "📈 Auditoría Contable"])

            with tab_diag_m:
                if macro_sum and "indicators" in macro_sum:
                    df_macro = pd.DataFrame(macro_sum["indicators"])
                    st.dataframe(df_macro, width="stretch")
                else:
                    st.info("Sin datos macroeconómicos requeridos en esta consulta.")

            with tab_diag_f:
                if fund_sum:
                    st.json(fund_sum)
                else:
                    st.info("Sin datos contables de empresa individual requeridos en esta consulta.")

    # 4. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
    st.markdown("---")
    st.caption(
        "⚖️ **Descargo de Responsabilidad Legal (Disclaimer)**: Las deliberaciones y dictámenes del Comité Asesor de Inversión Multiagente "
        "tienen propósito exclusivamente pedagógico e informativo. No constituyen recomendación de inversión personalizada ni asesoramiento financiero "
        "regulado (MiFID II). La asignación de activos de riesgo debe realizarse bajo el estricto criterio y responsabilidad del usuario."
    )


# ==========================================
# PESTAÑA 19: BASE DE DATOS Y COPIAS DE SEGURIDAD
# ==========================================
with tab_backup:
    render_backup_view()


# ==========================================
# PESTAÑA 20: ACTUALIZACIONES DEL SISTEMA
# ==========================================
with tab_updater:
    render_updater_view()





