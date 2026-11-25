import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

from backend.domain.constants import is_default_personal_subcategory

try:
    from frontend import api_client
    from frontend.services.financial_calculator import (
        calculate_503020_percentages,
        calculate_annual_metrics,
        calculate_category_totals,
    )
    from frontend.services.guidelines_view import (
        render_annual_guidelines_expander,
        render_monthly_guidelines_expander,
    )
    from frontend.utils.formatting import format_datetime_es as _shared_format_datetime_es
except ImportError:
    import api_client  # type: ignore
    from services.financial_calculator import (  # type: ignore
        calculate_503020_percentages,
        calculate_annual_metrics,
        calculate_category_totals,
    )
    from services.guidelines_view import (  # type: ignore
        render_annual_guidelines_expander,
        render_monthly_guidelines_expander,
    )
    from utils.formatting import format_datetime_es as _shared_format_datetime_es  # type: ignore

logger = logging.getLogger(__name__)

MESES_NOMBRES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _format_datetime_es(raw: Any) -> str:
    return _shared_format_datetime_es(raw, fallback="")


def render_personal_annual_view(year_selected: int, categorias: List[Dict[str, Any]], todas_subcats: List[Dict[str, Any]], colores_cabecera: Dict[str, str], ingresos_name: str, necesidades_name: str, deseos_name: str, ahorro_name: str) -> None:
    """Renderiza la pestaña de Resumen Anual personal."""
    st.header(f"Resumen Anual - Año: {year_selected}")

    if not categorias:
        st.info("La base de datos está vacía o el backend no está corriendo. Revisa que FastAPI esté funcionando.")
    else:
        # Recolectar datos de los 12 meses (RF-10: Caching en RAM TTL 120s para suprimir 24 llamadas HTTP redundantes)
        cached_annual = api_client.get_annual_summary_data(year_selected)
        anual_data = {}

        for m in range(1, 13):
            m_info = cached_annual.get(m, {})
            presupuestos_m = m_info.get("presupuestos", [])
            transacciones_m = m_info.get("transacciones", [])
            anual_data[m] = calculate_category_totals(
                categorias, todas_subcats, presupuestos_m, transacciones_m,
                ingresos_name, necesidades_name, deseos_name, ahorro_name,
            )

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
# PESTAÑA 1: GESTIÓN MENSUAL (ÁGIL EN 1 CLIC)
# ==========================================
