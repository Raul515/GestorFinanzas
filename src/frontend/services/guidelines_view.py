"""
Utilidades de Presentación y Renderizado para Pautas Deterministas de Gestión (Spec 008).
Genera tablas sinópticas, tarjetas de estrategia con cifras reales y jerarquías de compensación
compatibles con Streamlit (Light y Dark mode), completamente desacopladas del backend.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import streamlit as st


class GuidelineSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"


class _DataNode:
    """Adaptador ligero que permite acceder tanto por clave como por atributo a datos estructurados."""

    def __init__(self, data: Any):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if isinstance(self._data, dict):
            val = self._data.get(name)
        else:
            val = getattr(self._data, name, None)

        if isinstance(val, dict):
            return _DataNode(val)
        if isinstance(val, list):
            return [_DataNode(x) if isinstance(x, (dict, list)) else x for x in val]
        return val

    def __getitem__(self, item: Any) -> Any:
        if isinstance(self._data, dict):
            val = self._data[item]
        else:
            val = getattr(self._data, str(item))
        if isinstance(val, dict):
            return _DataNode(val)
        return val

    def __bool__(self) -> bool:
        return bool(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self._data, dict):
            val = self._data.get(key, default)
        else:
            val = getattr(self._data, key, default)
        if isinstance(val, dict):
            return _DataNode(val)
        return val


def _to_node(data: Any) -> Any:
    if data is None or isinstance(data, _DataNode):
        return data
    return _DataNode(data)


def _get_severity_colors(severity: Any) -> Tuple[str, str, str]:
    """Retorna tupla de (color_borde, color_fondo, icono) según la severidad."""
    sev_str = str(getattr(severity, "value", severity)).lower()
    if sev_str == "alert":
        return "#c62828", "rgba(198, 40, 40, 0.08)", "🚨"
    if sev_str == "warning":
        return "#ef6c00", "rgba(239, 108, 0, 0.08)", "⚠️"
    return "#1565c0", "rgba(21, 101, 192, 0.08)", "💡"


def render_monthly_guidelines_expander(
    report_data: Any,
    expanded: bool = False,
) -> None:
    """
    Renderiza el componente desplegable de pautas de actuación y compensación mensual en Streamlit.
    Acepta tanto diccionarios provenientes de la API como objetos serializados.
    """
    if not report_data:
        return

    report = _to_node(report_data)
    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    overall_status = report.overall_status or "Evaluación Presupuestaria"
    expander_title = (
        f"{icon} Pautas de Actuación y Compensación Presupuestaria ({overall_status})"
    )

    with st.expander(expander_title, expanded=expanded):
        # 1. Resumen ejecutivo de cabecera
        st.markdown(
            f"""
            <div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px;">
                <span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">
                    {icon} Diagnóstico del Mes: {overall_status}
                </span><br>
                <span style="font-size: 13px; opacity: 0.9;">
                    Ingresos Reales: <strong>{float(report.real_income or 0.0):,.2f} €</strong> | 
                    Necesidades (50% meta): <strong>{float(report.real_needs or 0.0):,.2f} €</strong> | 
                    Deseos (30% meta): <strong>{float(report.real_wants or 0.0):,.2f} €</strong> | 
                    Ahorro Real: <strong>{float(report.real_savings or 0.0):,.2f} € ({float(report.savings_rate or 0.0):.1f}%)</strong>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 2. Tabla Sinóptica de Decisión Rápida
        synoptic_table = report.synoptic_table or []
        if synoptic_table:
            st.markdown("##### 📋 Tabla Sinóptica de Compensación Rápida")
            table_rows_html = ""
            for row in synoptic_table:
                touch_ef = str(row.touch_emergency_fund or "")
                ef_color = "#ef5350" if "NUNCA" in touch_ef or "NO" in touch_ef else "#2e7d32"
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.2);">
                    <td style="padding: 8px 10px; font-weight: 600; color: inherit;">{row.scenario_name}</td>
                    <td style="padding: 8px 10px; color: inherit;">{row.funding_source}</td>
                    <td style="padding: 8px 10px; text-align: center; font-weight: bold; color: {ef_color};">
                        {touch_ef}
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
        guidelines = report.guidelines or []
        st.markdown("##### 🔍 Pautas Operativas y Asignación con Cifras Reales")

        for g in guidelines:
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
            comp_steps = g.compensation_hierarchy or []
            if comp_steps:
                st.markdown("**Jerarquía de Compensación Presupuestaria:**")
                for step in comp_steps:
                    can_touch = bool(step.can_touch_emergency_fund)
                    ef_tag = "⚠️ REQUIERE FUERZA MAYOR" if can_touch else "🔒 GASTO CORRIENTE"
                    amt = float(step.amount or 0.0)
                    amt_color = "#ef5350" if amt > 0 else "inherit"
                    border_step = "#ef5350" if can_touch else "#1565c0"
                    st.markdown(
                        f"""
                        <div style="padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; background: rgba(128,128,128,0.08); border-left: 4px solid {border_step}; font-size: 13px;">
                            <span style="font-weight: 700;">Línea {step.priority} ({step.source_block}):</span> 
                            <strong style="color: {amt_color};">{amt:,.2f} €</strong> — {step.action_text} 
                            <span style="font-size: 11px; float: right; opacity: 0.8; font-weight: 600;">{ef_tag}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # B. Estrategias de Asignación (si aplica: excedente o bonus)
            strategies = g.strategies or []
            if strategies:
                st.markdown("**Estrategias de Asignación con Cifras Reales:**")
                cols = st.columns(len(strategies))
                for s_idx, strat in enumerate(strategies):
                    with cols[s_idx]:
                        raw_items = strat.breakdown_items or []
                        items_html = "".join([f"<li style='margin-bottom: 5px;'>{it}</li>" for it in raw_items])
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
            if g.key_recommendation:
                st.caption(f"💡 **Recomendación Operativa:** {g.key_recommendation}")


def render_annual_guidelines_expander(
    report_data: Any,
    expanded: bool = False,
) -> None:
    """
    Renderiza el componente de diagnóstico y pautas anuales en la Pestaña 0 de Streamlit.
    Acepta tanto diccionarios de la API como objetos serializados.
    """
    if not report_data:
        return

    report = _to_node(report_data)
    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    overall_health = report.overall_health or "Consolidado Anual"
    expander_title = (
        f"{icon} Diagnóstico Estructural y Pautas Anuales ({overall_health})"
    )

    with st.expander(expander_title, expanded=expanded):
        avg_savings = float(report.average_savings_rate or 0.0)
        summary = report.summary_text or ""
        st.markdown(
            f"""
            <div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 12px 16px; border-radius: 6px; margin-bottom: 14px;">
                <span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">
                    {icon} Estado Anual Consolidado: {overall_health}
                </span><br>
                <span style="font-size: 13.5px; opacity: 0.95;">
                    Tasa de Ahorro Media Anual: <strong>{avg_savings:.2f}%</strong> (Meta mínima: 20.00%) — {summary}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        guidelines = report.guidelines or []
        if guidelines:
            st.markdown("##### 🔬 Análisis de Factores Estructurales")
            for g in guidelines:
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


__all__ = [
    "GuidelineSeverity",
    "render_monthly_guidelines_expander",
    "render_annual_guidelines_expander",
]
