"""
Utilidades de Presentación y Renderizado para Pautas Deterministas de Gestión (Spec 008).
Genera tablas sinópticas, tarjetas de estrategia con cifras reales y jerarquías de compensación
compatibles con Streamlit (Light y Dark mode).
"""

import os
import sys
from typing import Optional

# Garantizar que src esté en sys.path
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import streamlit as st
from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
    GuidelineSeverity,
    MonthlyGuidelineReport,
    MonthlyScenarioType,
)
from backend.services.guidelines_service import (
    evaluate_monthly_guidelines,
    evaluate_annual_guidelines,
)

__all__ = [
    "evaluate_monthly_guidelines",
    "evaluate_annual_guidelines",
    "render_monthly_guidelines_expander",
    "render_annual_guidelines_expander",
]


def _get_severity_colors(severity: GuidelineSeverity) -> tuple:
    """Retorna tupla de (color_borde, color_fondo, icono) según la severidad."""
    if severity == GuidelineSeverity.ALERT:
        return "#c62828", "rgba(198, 40, 40, 0.08)", "🚨"
    if severity == GuidelineSeverity.WARNING:
        return "#ef6c00", "rgba(239, 108, 0, 0.08)", "⚠️"
    return "#1565c0", "rgba(21, 101, 192, 0.08)", "💡"


def render_monthly_guidelines_expander(
    report: MonthlyGuidelineReport,
    expanded: bool = False,
) -> None:
    """Renderiza el componente desplegable de pautas de actuación y compensación mensual en Streamlit."""
    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    expander_title = (
        f"{icon} Pautas de Actuación y Compensación Presupuestaria ({report.overall_status})"
    )

    with st.expander(expander_title, expanded=expanded):
        # 1. Resumen ejecutivo de cabecera
        st.markdown(
            f"""
            <div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px;">
                <span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">
                    {icon} Diagnóstico del Mes: {report.overall_status}
                </span><br>
                <span style="font-size: 13px; opacity: 0.9;">
                    Ingresos Reales: <strong>{report.real_income:,.2f} €</strong> | 
                    Necesidades (50% meta): <strong>{report.real_needs:,.2f} €</strong> | 
                    Deseos (30% meta): <strong>{report.real_wants:,.2f} €</strong> | 
                    Ahorro Real: <strong>{report.real_savings:,.2f} € ({report.savings_rate:.1f}%)</strong>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 2. Tabla Sinóptica de Decisión Rápida
        if report.synoptic_table:
            st.markdown("##### 📋 Tabla Sinóptica de Compensación Rápida")
            table_rows_html = ""
            for row in report.synoptic_table:
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.2);">
                    <td style="padding: 8px 10px; font-weight: 600; color: inherit;">{row.scenario_name}</td>
                    <td style="padding: 8px 10px; color: inherit;">{row.funding_source}</td>
                    <td style="padding: 8px 10px; text-align: center; font-weight: bold; color: {'#ef5350' if 'NUNCA' in row.touch_emergency_fund or 'NO' in row.touch_emergency_fund else '#2e7d32'};">
                        {row.touch_emergency_fund}
                    </td>
                    <td style="padding: 8px 10px; color: inherit;">{row.budget_action}</td>
                </tr>
                """

            st.markdown(
                f"""
                <div style="overflow-x: auto; margin-bottom: 1.25rem;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12.5px; color: inherit;">
                        <thead>
                            <tr style="background-color: #1565c0; color: #ffffff;">
                                <th style="padding: 8px 10px; text-align: left; border-top-left-radius: 4px;">Tipo de Situación</th>
                                <th style="padding: 8px 10px; text-align: left;">¿De dónde se saca el dinero?</th>
                                <th style="padding: 8px 10px; text-align: center;">¿Se toca el Fondo de Emergencia?</th>
                                <th style="padding: 8px 10px; text-align: left; border-top-right-radius: 4px;">Acción Presupuestaria</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows_html}
                        </tbody>
                    </table>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3. Detalle de Pautas y Estrategias Activas
        st.markdown("##### 🔍 Pautas Operativas y Asignación con Cifras Reales")

        for idx, g in enumerate(report.guidelines):
            g_border, g_bg, g_icon = _get_severity_colors(g.severity)

            st.markdown(
                f"""
                <div style="background: {g_bg}; border: 1px solid {g_border}; border-left: 6px solid {g_border}; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px;">
                    <h4 style="margin: 0 0 6px 0; color: inherit; font-size: 16px; font-weight: 700;">
                        {g_icon} {g.title}
                    </h4>
                    <p style="margin: 0 0 10px 0; font-size: 13.5px; line-height: 1.45; color: inherit;">
                        {g.summary_headline}
                    </p>
                    <div style="background: rgba(0, 0, 0, 0.05); padding: 8px 12px; border-radius: 6px; font-size: 12.5px;">
                        <strong>🛡️ Regla sobre el Fondo de Emergencia:</strong> {g.emergency_fund_rule}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # A. Jerarquía de Compensación (si aplica: déficit)
            if g.compensation_hierarchy:
                st.markdown("**Jerarquía de Compensación Presupuestaria:**")
                for step in g.compensation_hierarchy:
                    ef_tag = "⚠️ REQUIERE FUERZA MAYOR" if step.can_touch_emergency_fund else "🔒 GASTO CORRIENTE"
                    st.markdown(
                        f"""
                        <div style="padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; background: rgba(128,128,128,0.08); border-left: 4px solid {'#ef5350' if step.can_touch_emergency_fund else '#1565c0'}; font-size: 13px;">
                            <span style="font-weight: 700;">Línea {step.priority} ({step.source_block}):</span> 
                            <strong style="color: {'#ef5350' if step.amount > 0 else 'inherit'};">{step.amount:,.2f} €</strong> — {step.action_text} 
                            <span style="font-size: 11px; float: right; opacity: 0.8; font-weight: 600;">{ef_tag}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # B. Estrategias de Asignación (si aplica: excedente o bonus)
            if g.strategies:
                st.markdown("**Estrategias de Asignación con Cifras Reales:**")
                cols = st.columns(len(g.strategies))
                for s_idx, strat in enumerate(g.strategies):
                    with cols[s_idx]:
                        items_html = "".join([f"<li style='margin-bottom: 5px;'>{it}</li>" for it in strat.breakdown_items])
                        st.markdown(
                            f"""
                            <div style="background: rgba(128,128,128,0.06); border: 1px solid rgba(128,128,128,0.2); border-radius: 8px; padding: 12px; height: 100%;">
                                <span style="background: #1565c0; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase;">
                                    {strat.badge}
                                </span>
                                <h5 style="margin: 8px 0 4px 0; font-size: 14px; font-weight: 700; color: inherit;">{strat.name}</h5>
                                <p style="font-size: 12px; opacity: 0.9; margin-bottom: 8px;">{strat.description}</p>
                                <ul style="padding-left: 18px; margin: 0; font-size: 12px; line-height: 1.4;">
                                    {items_html}
                                </ul>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # Recomendación clave
            st.caption(f"💡 **Recomendación Operativa:** {g.key_recommendation}")


def render_annual_guidelines_expander(
    report: AnnualGuidelineReport,
    expanded: bool = False,
) -> None:
    """Renderiza el componente de diagnóstico y pautas anuales en la Pestaña 0 de Streamlit."""
    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    expander_title = (
        f"{icon} Diagnóstico Estructural y Pautas Anuales ({report.overall_health})"
    )

    with st.expander(expander_title, expanded=expanded):
        st.markdown(
            f"""
            <div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 12px 16px; border-radius: 6px; margin-bottom: 14px;">
                <span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">
                    {icon} Estado Anual Consolidado: {report.overall_health}
                </span><br>
                <span style="font-size: 13.5px; opacity: 0.95;">
                    Tasa de Ahorro Media Anual: <strong>{report.average_savings_rate:.2f}%</strong> (Meta mínima: 20.00%) — {report.summary_text}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("##### 🔬 Análisis de Factores Estructurales")
        for g in report.guidelines:
            g_border, g_bg, g_icon = _get_severity_colors(g.severity)
            st.markdown(
                f"""
                <div style="background: {g_bg}; border: 1px solid {g_border}; border-left: 5px solid {g_border}; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <h5 style="margin: 0; font-size: 15px; font-weight: 700; color: inherit;">
                            {g_icon} {g.title}
                        </h5>
                        <span style="background: {g_border}; color: white; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">
                            {g.metric_value_text}
                        </span>
                    </div>
                    <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.45; color: inherit;">
                        {g.description}
                    </p>
                    <div style="background: rgba(0,0,0,0.05); padding: 8px 12px; border-radius: 6px; font-size: 12.5px;">
                        <strong>🛠️ Plan de Calibración:</strong> {g.action_plan}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
