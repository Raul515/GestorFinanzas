"""
Utilidades de Presentación y Renderizado para Pautas Deterministas de Gestión (Spec 008).
Genera tablas sinópticas, tarjetas de estrategia con cifras reales, controles interactivos de
asignación de capital y jerarquías de compensación compatibles con Streamlit (Light y Dark mode).
Completamente desacoplado del backend (Fase 3: Asignaciones Positivas y Barrido de Cierre).
"""

import datetime
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
    subcategories: Optional[List[Dict[str, Any]]] = None,
    categories: Optional[List[Dict[str, Any]]] = None,
    api_client: Any = None,
) -> None:
    """
    Renderiza el componente desplegable de pautas de actuación y compensación mensual en Streamlit.
    Acepta tanto diccionarios provenientes de la API como objetos serializados.
    Incorpora controles interactivos para ejecución de estrategias y barrido de fin de mes.
    """
    if not report_data:
        return

    report = _to_node(report_data)
    m_key = str(report.month_key or "curr")

    # Detección de mes vacío sin datos financieros (sin actividad contable)
    is_empty = (
        bool(getattr(report, "is_empty_month", False))
        or report.overall_status == "Mes sin Información Financiera"
        or (
            float(report.real_income or 0.0) == 0.0
            and float(report.real_needs or 0.0) == 0.0
            and float(report.real_wants or 0.0) == 0.0
            and float(report.real_savings or 0.0) == 0.0
            and not (report.guidelines and any("Optimizado" in (g.title or "") or "Colchón" in (g.title or "") for g in report.guidelines))
            and not getattr(report, "applied_strategy", None)
        )
    )

    if is_empty:
        expander_title = "ℹ️ Pautas de Actuación Presupuestaria (Mes sin Información Financiera)"
        with st.expander(expander_title, expanded=expanded):
            st.markdown(
                """<div style="background: rgba(128, 128, 128, 0.08); border-left: 5px solid #757575; padding: 12px 16px; border-radius: 6px; margin: 4px 0 10px 0;">
<span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: #757575;">ℹ️ Mes sin Información Financiera</span><br>
<span style="font-size: 13px; opacity: 0.9;">No se han registrado ingresos ni gastos en este mes. Las pautas deterministas y los cálculos 50/30/20 se activarán automáticamente en cuanto introduzcas datos presupuestarios o transacciones.</span>
</div>""",
                unsafe_allow_html=True,
            )
        return

    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    overall_status = report.overall_status or "Evaluación Presupuestaria"
    expander_title = (
        f"{icon} Pautas de Actuación y Compensación Presupuestaria ({overall_status})"
    )

    # Identificar subcategorías de Ahorro y Deseos
    savings_subcats: List[Dict[str, Any]] = []
    wants_subcats: List[Dict[str, Any]] = []
    emergency_subcat_id: Optional[int] = None

    if subcategories and categories:
        cat_map = {c.get("id"): c for c in categories}
        for s in subcategories:
            c_id = s.get("categoria_id") if s.get("categoria_id") is not None else s.get("category_id")
            cat = cat_map.get(c_id, {})
            cat_type = str(cat.get("tipo") or cat.get("type", "")).lower()
            cat_name = str(cat.get("nombre") or cat.get("name", "")).lower()
            s_name = str(s.get("nombre") or s.get("name", "")).lower()

            if cat_type == "ahorro" or "ahorro" in cat_name:
                savings_subcats.append(s)
                if "emergencia" in s_name:
                    emergency_subcat_id = s.get("id")
            elif "deseos" in cat_name or (cat_type == "gasto" and "deseos" in cat_name):
                wants_subcats.append(s)

    with st.expander(expander_title, expanded=expanded):
        # 1. Resumen ejecutivo de cabecera
        st.markdown(
            f"""<div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px;">
<span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">{icon} Diagnóstico del Mes: {overall_status}</span><br>
<span style="font-size: 13px; opacity: 0.9;">Ingresos Reales: <strong>{float(report.real_income or 0.0):,.2f} €</strong> | Necesidades (50% meta): <strong>{float(report.real_needs or 0.0):,.2f} €</strong> | Deseos (30% meta): <strong>{float(report.real_wants or 0.0):,.2f} €</strong> | Ahorro Real: <strong>{float(report.real_savings or 0.0):,.2f} € ({float(report.savings_rate or 0.0):.1f}%)</strong></span>
</div>""",
            unsafe_allow_html=True,
        )

        # 2. Tabla Sinóptica de Decisión Rápida (Formato HTML compacto inmune a sangrías CommonMark)
        synoptic_table = report.synoptic_table or []
        if synoptic_table:
            st.markdown("##### 📋 Tabla Sinóptica de Compensación Rápida")
            table_rows_html = ""
            for row in synoptic_table:
                touch_ef = str(row.touch_emergency_fund or "")
                ef_color = "#ef5350" if "NUNCA" in touch_ef or "NO" in touch_ef else "#2e7d32"
                table_rows_html += (
                    f'<tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.2);">'
                    f'<td style="padding: 8px 10px; font-weight: 600; color: inherit;">{row.scenario_name}</td>'
                    f'<td style="padding: 8px 10px; color: inherit;">{row.funding_source}</td>'
                    f'<td style="padding: 8px 10px; text-align: center; font-weight: bold; color: {ef_color};">{touch_ef}</td>'
                    f'<td style="padding: 8px 10px; color: inherit;">{row.budget_action}</td>'
                    f'</tr>'
                )

            clean_table_html = (
                '<div style="overflow-x: auto; margin-bottom: 1.25rem;">'
                '<table style="width: 100%; border-collapse: collapse; font-size: 12.5px; color: inherit;">'
                '<thead><tr style="background-color: #1565c0; color: #ffffff;">'
                '<th style="padding: 8px 10px; text-align: left; border-top-left-radius: 4px;">Tipo de Situación</th>'
                '<th style="padding: 8px 10px; text-align: left;">¿De dónde se saca el dinero?</th>'
                '<th style="padding: 8px 10px; text-align: center;">¿Se toca el Fondo de Emergencia?</th>'
                '<th style="padding: 8px 10px; text-align: left; border-top-right-radius: 4px;">Acción Presupuestaria</th>'
                f'</tr></thead><tbody>{table_rows_html}</tbody></table></div>'
            )
            st.markdown(clean_table_html, unsafe_allow_html=True)

        # 3. Detalle de Pautas y Estrategias Activas
        today = datetime.date.today()
        current_ym = today.strftime("%Y-%m")
        is_month_end_window = (today.day >= 26 and m_key == current_ym) or (m_key < current_ym)
        unassigned_cash = float(report.unassigned_amount or 0.0)
        is_sweep_active = is_month_end_window and unassigned_cash > 5.0 and bool(savings_subcats)

        guidelines = report.guidelines or []
        visible_guidelines = []
        for g in guidelines:
            raw_scen = getattr(g.scenario_type, "value", g.scenario_type)
            scen_type = str(raw_scen or "")
            if "." in scen_type:
                scen_type = scen_type.split(".")[-1]

            if is_sweep_active:
                # A fin de mes, suprimir recomendaciones de excedente no aplicado y avisos de dinero sin asignar / óptimo
                if scen_type in ("HIGH_UNASSIGNED", "OPTIMAL"):
                    continue
                if scen_type == "NEEDS_SURPLUS" and not ("Optimizado" in (g.title or "") or "Colchón Prudencial" in (g.title or "")):
                    continue
                if scen_type == "EXTRAORDINARY_INCOME" and not ("Asignado" in (g.title or "")):
                    continue

            visible_guidelines.append(g)

        if visible_guidelines:
            st.markdown("##### 🔍 Pautas Operativas y Asignación con Cifras Reales")

        is_ef_completed = bool(report.is_emergency_fund_completed)
        ef_target = float(report.emergency_fund_target_months or 3.0)
        ef_coverage = float(report.emergency_fund_coverage_months or 0.0)

        for g_idx, g in enumerate(visible_guidelines):
            g_border, g_bg, g_icon = _get_severity_colors(g.severity)
            if "Optimizado" in (g.title or "") or "Asignado" in (g.title or ""):
                g_icon = "✅"
            raw_scen = getattr(g.scenario_type, "value", g.scenario_type)
            scen_type = str(raw_scen or "")
            if "." in scen_type:
                scen_type = scen_type.split(".")[-1]

            clean_title = (g.title or "").strip()
            # Si el título ya contiene un emoji al inicio, no duplicarlo
            if clean_title.startswith(("💡", "✅", "⚠️", "🚨", "🛡️", "🔍")):
                display_title = clean_title
            else:
                display_title = f"{g_icon} {clean_title}"

            st.markdown(
                f"""<div style="background: {g_bg}; border: 1px solid {g_border}; border-left: 6px solid {g_border}; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px;">
<h4 style="margin: 0 0 6px 0; color: inherit; font-size: 16px; font-weight: 700;">{display_title}</h4>
<p style="margin: 0 0 10px 0; font-size: 13.5px; line-height: 1.45; color: inherit;">{g.summary_headline}</p>
<div style="background: rgba(0, 0, 0, 0.05); padding: 8px 12px; border-radius: 6px; font-size: 12.5px;"><strong>🛡️ Regla sobre el Fondo de Emergencia:</strong> {g.emergency_fund_rule}</div>
</div>""",
                unsafe_allow_html=True,
            )

            # Botón "↩️ Deshacer Estrategia" si el estado ya está optimizado, en colchón o asignado (centrado con popover de confirmación)
            if "Optimizado" in g.title or "Colchón Prudencial" in g.title or "Asignado" in g.title:
                st.markdown("<div style='margin-top: -6px; margin-bottom: 8px;'></div>", unsafe_allow_html=True)
                _, rev_center, _ = st.columns([1.2, 1.6, 1.2])
                with rev_center:
                    with st.popover("↩️ Deshacer Estrategia", help="Revierte la estrategia aplicada eliminando transacciones vinculadas y restaurando saldos", use_container_width=True):
                        st.markdown("##### ⚠️ ¿Deshacer Estrategia?")
                        st.warning(
                            "¿Estás seguro de que deseas deshacer la estrategia aplicada? "
                            "Se revertirán las transacciones generadas y el saldo del Fondo de Emergencia volverá a su estado anterior."
                        )
                        if st.button("Sí, deshacer estrategia", key=f"btn_revert_strat_confirm_{m_key}_{g_idx}", type="primary", use_container_width=True):
                            if api_client:
                                res = api_client.revert_guideline_strategy(month_key=m_key, scenario_type=scen_type)
                                if res and res.get("success"):
                                    st.toast("Estrategia deshecha exitosamente. El capital vuelve a estar disponible.", icon="↩️")
                                    st.rerun()
                                else:
                                    st.error("No se pudo revertir la estrategia en el backend.")

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
                        f"""<div style="padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; background: rgba(128,128,128,0.08); border-left: 4px solid {border_step}; font-size: 13px;">
<span style="font-weight: 700;">Línea {step.priority} ({step.source_block}):</span> <strong style="color: {amt_color};">{amt:,.2f} €</strong> — {step.action_text} <span style="font-size: 11px; float: right; opacity: 0.8; font-weight: 600;">{ef_tag}</span>
</div>""",
                        unsafe_allow_html=True,
                    )

            # Amortiguación interactiva de Necesidades desde Deseos (Fase 4: NEEDS_DEFICIT)
            if scen_type == "NEEDS_DEFICIT" and wants_subcats:
                excess_amt = float(g.delta_amount or 0.0)
                st.markdown(
                    f"""<div style="background: rgba(239, 108, 0, 0.08); border: 1px solid #ef6c00; border-left: 6px solid #ef6c00; border-radius: 8px; padding: 12px 16px; margin: 10px 0 12px 0;">
<h5 style="margin: 0 0 4px 0; color: inherit; font-size: 14.5px; font-weight: 700;">⚡ Amortiguar con Deseos del Mes (Protección del Fondo de Emergencia)</h5>
<p style="margin: 0; font-size: 13px; opacity: 0.95;">Absorbe el déficit de <strong>{excess_amt:,.2f} €</strong> reduciendo el presupuesto de Deseos de este mes (<strong>{m_key}</strong>) para evitar tocar tu Fondo de Emergencia.</p>
</div>""",
                    unsafe_allow_html=True,
                )
                abs_col1, abs_col2 = st.columns([2, 1])
                with abs_col1:
                    sub_opts_wants = {s["id"]: s["nombre"] for s in wants_subcats}
                    target_abs_id = st.selectbox(
                        "Subcategoría de Deseos a Reducir:",
                        options=list(sub_opts_wants.keys()),
                        format_func=lambda x: sub_opts_wants.get(x, f"Subcat {x}"),
                        key=f"needs_absorb_sub_{m_key}_{g_idx}",
                    )
                with abs_col2:
                    st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
                    if st.button(f"⚡ Amortiguar ({excess_amt:,.2f} €)", key=f"btn_absorb_{m_key}_{g_idx}", type="primary"):
                        if api_client:
                            res = api_client.compensate_guideline_deficit(
                                month_key=m_key,
                                action_type="NEEDS_ABSORPTION_CURRENT_WANTS",
                                amount=excess_amt,
                                target_subcategory_id=target_abs_id,
                            )
                            if res and res.get("success"):
                                st.toast(f"¡Amortiguación aplicada! Presupuesto reducido en {excess_amt:,.2f} €.", icon="⚡")
                                st.rerun()
                            else:
                                st.error("No se pudo aplicar la amortiguación en el backend.")

            # B. Estrategias de Asignación de Capital (NEEDS_SURPLUS y EXTRAORDINARY_INCOME)
            strategies = g.strategies or []
            if strategies:
                st.markdown("**Estrategias de Asignación con Cifras Reales:**")

                # Selector de modalidad para Excedente en Necesidades
                is_partial = False
                factor = 1.0
                if scen_type == "NEEDS_SURPLUS":
                    mode_col1, mode_col2 = st.columns([1.8, 1])
                    with mode_col1:
                        mode_sel = st.radio(
                            "Modalidad de Traspaso del Excedente:",
                            ["Traspaso Total (100%)", "Traspaso con Colchón Prudencial (50% en Necesidades)"],
                            index=1,
                            horizontal=True,
                            key=f"mode_surplus_{m_key}_{g_idx}",
                        )
                        is_partial = "50%" in mode_sel
                        factor = 0.5 if is_partial else 1.0
                    with mode_col2:
                        surplus_val = float(g.delta_amount or 0.0)
                        if is_partial:
                            st.info(f"💡 Traspasas {surplus_val * 0.5:,.2f} € y reservas {surplus_val * 0.5:,.2f} € internamente en Necesidades.")
                        else:
                            st.info(f"💡 Traspasas el 100% ({surplus_val:,.2f} €) a las partidas elegidas.")

                cols = st.columns(len(strategies))
                for s_idx, strat in enumerate(strategies):
                    with cols[s_idx]:
                        raw_items = strat.breakdown_items or []
                        items_html = "".join([f"<li style='margin-bottom: 5px;'>{it}</li>" for it in raw_items])
                        st.markdown(
                            f"""<div style="background: rgba(128,128,128,0.06); border: 1px solid rgba(128,128,128,0.2); border-radius: 8px; padding: 12px; margin-bottom: 10px;">
<span style="background: #1565c0; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase;">{strat.badge}</span>
<h5 style="margin: 8px 0 4px 0; font-size: 14px; font-weight: 700; color: inherit;">{strat.name}</h5>
<p style="font-size: 12px; opacity: 0.9; margin-bottom: 8px;">{strat.description}</p>
<ul style="padding-left: 18px; margin: 0; font-size: 12px; line-height: 1.4;">{items_html}</ul>
</div>""",
                            unsafe_allow_html=True,
                        )

                        # Controles interactivos y botón "⚡ Aplicar" (Fase 3)
                        surplus_base = float(strat.allocation_amount or g.delta_amount or 0.0)
                        eff_amount = surplus_base * factor

                        # --- ESTRATEGIA 1: FIRE (100% Ahorro) ---
                        if s_idx == 0 and scen_type == "NEEDS_SURPLUS":
                            if not is_ef_completed:
                                st.caption("🔒 **Fondo de Emergencia Incompleto**: Destino asignado forzosamente al fondo por salvaguarda patrimonial.")
                                target_sub_id = emergency_subcat_id or (savings_subcats[0]["id"] if savings_subcats else 1)
                            else:
                                sub_opts = {s["id"]: s["nombre"] for s in savings_subcats}
                                target_sub_id = st.selectbox(
                                    "Subcategoría Destino (Ahorro/Inversión):",
                                    options=list(sub_opts.keys()),
                                    format_func=lambda x: sub_opts.get(x, f"Subcat {x}"),
                                    key=f"fire_sub_{m_key}_{g_idx}",
                                )

                            if st.button(f"⚡ Aplicar FIRE ({eff_amount:,.2f} €)", key=f"btn_fire_{m_key}_{g_idx}", type="primary"):
                                if api_client:
                                    payload = {
                                        "month_key": m_key,
                                        "strategy_type": "FIRE",
                                        "is_partial": is_partial,
                                        "savings_allocations": [{"subcategory_id": target_sub_id, "amount": eff_amount}],
                                        "wants_allocations": [],
                                    }
                                    res = api_client.apply_guideline_strategy(payload)
                                    if res and res.get("success"):
                                        st.toast(f"¡Acelerador FIRE aplicado exitosamente ({eff_amount:,.2f} €)!", icon="🚀")
                                        st.rerun()
                                    else:
                                        st.error("No se pudo aplicar la estrategia en el backend.")

                        # --- ESTRATEGIA 2: SINKING FUND (50% Medio Plazo + 50% Largo Plazo) ---
                        elif s_idx == 1 and scen_type == "NEEDS_SURPLUS":
                            half_amt = eff_amount * 0.5
                            sub_opts = {s["id"]: s["nombre"] for s in savings_subcats}
                            sub_keys = list(sub_opts.keys())

                            sub_med_id = st.selectbox(
                                f"Destino Medio Plazo (50% = {half_amt:,.2f} €):",
                                options=sub_keys,
                                index=0 if sub_keys else 0,
                                format_func=lambda x: sub_opts.get(x, f"Subcat {x}"),
                                key=f"sinking_med_{m_key}_{g_idx}",
                            )
                            sub_long_id = st.selectbox(
                                f"Destino Largo Plazo (50% = {half_amt:,.2f} €):",
                                options=sub_keys,
                                index=min(1, len(sub_keys) - 1) if sub_keys else 0,
                                format_func=lambda x: sub_opts.get(x, f"Subcat {x}"),
                                key=f"sinking_long_{m_key}_{g_idx}",
                            )

                            if st.button(f"⚡ Aplicar Sinking Fund ({eff_amount:,.2f} €)", key=f"btn_sinking_{m_key}_{g_idx}"):
                                if api_client:
                                    payload = {
                                        "month_key": m_key,
                                        "strategy_type": "SINKING_FUND",
                                        "is_partial": is_partial,
                                        "savings_allocations": [
                                            {"subcategory_id": sub_med_id, "amount": half_amt},
                                            {"subcategory_id": sub_long_id, "amount": half_amt},
                                        ],
                                        "wants_allocations": [],
                                    }
                                    res = api_client.apply_guideline_strategy(payload)
                                    if res and res.get("success"):
                                        st.toast("¡Sinking Fund aplicado exitosamente!", icon="🎯")
                                        st.rerun()
                                    else:
                                        st.error("No se pudo aplicar la estrategia en el backend.")

                        # --- ESTRATEGIA 3: REGLA 80/20 (80% Ahorro + 20% Deseos) ---
                        elif s_idx == 2 and scen_type == "NEEDS_SURPLUS":
                            amt_80 = eff_amount * 0.8
                            amt_20 = eff_amount * 0.2

                            # Destino Ahorro (80%)
                            if not is_ef_completed:
                                st.caption(f"🔒 **80% ({amt_80:,.2f} €)** al Fondo de Emergencia (en construcción).")
                                sub_80_id = emergency_subcat_id or (savings_subcats[0]["id"] if savings_subcats else 1)
                            else:
                                sub_opts_sav = {s["id"]: s["nombre"] for s in savings_subcats}
                                sub_80_id = st.selectbox(
                                    f"Destino Ahorro (80% = {amt_80:,.2f} €):",
                                    options=list(sub_opts_sav.keys()),
                                    format_func=lambda x: sub_opts_sav.get(x, f"Subcat {x}"),
                                    key=f"sub_80_{m_key}_{g_idx}",
                                )

                            # Destino Deseos (20%)
                            sub_opts_wants = {s["id"]: s["nombre"] for s in wants_subcats}
                            split_wants = st.checkbox(
                                f"Dividir el 20% ({amt_20:,.2f} €) en varios deseos",
                                value=False,
                                key=f"chk_split_{m_key}_{g_idx}",
                            )

                            wants_allocations: List[Dict[str, Any]] = []
                            is_split_valid = True

                            if not split_wants:
                                sub_20_id = st.selectbox(
                                    f"Subcategoría de Deseos (+{amt_20:,.2f} € asignación real):",
                                    options=list(sub_opts_wants.keys()),
                                    format_func=lambda x: sub_opts_wants.get(x, f"Subcat {x}"),
                                    key=f"wants_single_{m_key}_{g_idx}",
                                )
                                wants_allocations.append({"subcategory_id": sub_20_id, "amount": amt_20, "percentage": 20.0})
                            else:
                                num_splits = st.selectbox(
                                    "Número de divisiones (máximo 4):",
                                    options=[2, 3, 4],
                                    index=0,
                                    key=f"num_splits_{m_key}_{g_idx}",
                                )
                                sum_pct = 0.0
                                for sp_i in range(num_splits):
                                    sp_col1, sp_col2 = st.columns([1.5, 1])
                                    with sp_col1:
                                        sp_sub_id = st.selectbox(
                                            f"Deseo {sp_i+1}:",
                                            options=list(sub_opts_wants.keys()),
                                            index=min(sp_i, max(0, len(sub_opts_wants)-1)),
                                            format_func=lambda x: sub_opts_wants.get(x, f"Subcat {x}"),
                                            key=f"split_sub_{num_splits}_{sp_i}_{m_key}_{g_idx}",
                                        )
                                    with sp_col2:
                                        if num_splits == 2:
                                            default_pct = 10.0
                                        elif num_splits == 3:
                                            default_pct = 10.0 if sp_i == 0 else 5.0
                                        else:
                                            default_pct = 5.0

                                        sp_pct = st.number_input(
                                            f"% Partición {sp_i+1}:",
                                            min_value=5.0,
                                            max_value=20.0,
                                            step=5.0,
                                            value=default_pct,
                                            key=f"split_pct_{num_splits}_{sp_i}_{m_key}_{g_idx}",
                                        )
                                    sum_pct += sp_pct
                                    part_amt = eff_amount * (sp_pct / 100.0)
                                    wants_allocations.append({"subcategory_id": sp_sub_id, "amount": part_amt, "percentage": sp_pct})

                                if abs(sum_pct - 20.0) < 0.01:
                                    st.success("✅ Reparto completado: 20.0%")
                                    is_split_valid = True
                                else:
                                    st.warning(f"⚠️ La suma debe ser 20.0% (actual: {sum_pct:.1f}%)")
                                    is_split_valid = False

                            if st.button(
                                f"⚡ Aplicar 80/20 ({eff_amount:,.2f} €)",
                                disabled=not is_split_valid,
                                key=f"btn_8020_{m_key}_{g_idx}",
                            ):
                                if api_client:
                                    payload = {
                                        "month_key": m_key,
                                        "strategy_type": "HYBRID_80_20",
                                        "is_partial": is_partial,
                                        "savings_allocations": [{"subcategory_id": sub_80_id, "amount": amt_80}],
                                        "wants_allocations": wants_allocations,
                                    }
                                    res = api_client.apply_guideline_strategy(payload)
                                    if res and res.get("success"):
                                        st.toast("¡Estrategia 80/20 aplicada con éxito!", icon="✨")
                                        st.rerun()
                                    else:
                                        st.error("No se pudo aplicar la estrategia en el backend.")

                        # --- ESTRATEGIAS DE BONUS / PAGA EXTRA ---
                        elif scen_type == "EXTRAORDINARY_INCOME":
                            sub_opts_sav = {s["id"]: s["nombre"] for s in savings_subcats}
                            sub_opts_wants = {s["id"]: s["nombre"] for s in wants_subcats}

                            if not is_ef_completed:
                                st.caption("🔒 **Inyección a Fondo de Emergencia**: El extra se canaliza al fondo para completar los 3 meses.")
                                target_bonus_sub = emergency_subcat_id or (savings_subcats[0]["id"] if savings_subcats else 1)
                                if st.button(f"⚡ Inyectar al Fondo ({eff_amount:,.2f} €)", key=f"btn_bonus_ef_{m_key}_{g_idx}", type="primary"):
                                    if api_client:
                                        payload = {
                                            "month_key": m_key,
                                            "strategy_type": "EXTRAORDINARY_INCOME",
                                            "is_partial": False,
                                            "savings_allocations": [{"subcategory_id": target_bonus_sub, "amount": eff_amount}],
                                            "wants_allocations": [],
                                        }
                                        res = api_client.apply_guideline_strategy(payload)
                                        if res and res.get("success"):
                                            st.toast("¡Fondo de Emergencia fortalecido con éxito!", icon="🛡️")
                                            st.rerun()
                            else:
                                st.caption("🎉 **Regla de Bonus (80/20)**: 80% a inversión y 20% a ocio para celebrarlo.")
                                target_inv_id = st.selectbox(
                                    f"Inversión (80% = {eff_amount * 0.8:,.2f} €):",
                                    options=list(sub_opts_sav.keys()),
                                    format_func=lambda x: sub_opts_sav.get(x, f"Subcat {x}"),
                                    key=f"bonus_inv_{m_key}_{g_idx}",
                                )
                                target_wants_id = st.selectbox(
                                    f"Presupuesto Deseos (20% = {eff_amount * 0.2:,.2f} €):",
                                    options=list(sub_opts_wants.keys()),
                                    format_func=lambda x: sub_opts_wants.get(x, f"Subcat {x}"),
                                    key=f"bonus_wants_{m_key}_{g_idx}",
                                )
                                if st.button(f"⚡ Aplicar Distribución de Bonus ({eff_amount:,.2f} €)", key=f"btn_bonus_split_{m_key}_{g_idx}"):
                                    if api_client:
                                        payload = {
                                            "month_key": m_key,
                                            "strategy_type": "EXTRAORDINARY_INCOME",
                                            "is_partial": False,
                                            "savings_allocations": [{"subcategory_id": target_inv_id, "amount": eff_amount * 0.8}],
                                            "wants_allocations": [{"subcategory_id": target_wants_id, "amount": eff_amount * 0.2}],
                                        }
                                        res = api_client.apply_guideline_strategy(payload)
                                        if res and res.get("success"):
                                            st.toast("¡Bonus distribuido con éxito!", icon="🎉")
                                            st.rerun()

            # Ajuste compensatorio para exceso en Deseos (Fase 4: WANTS_DEFICIT)
            if scen_type == "WANTS_DEFICIT" and wants_subcats:
                excess_amt = float(g.delta_amount or 0.0)
                try:
                    parts = m_key.split("-")
                    y, m = int(parts[0]), int(parts[1])
                    next_m_key = f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"
                except Exception:
                    next_m_key = m_key

                st.markdown(
                    f"""<div style="background: rgba(198, 40, 40, 0.08); border: 1px solid #c62828; border-left: 6px solid #c62828; border-radius: 8px; padding: 12px 16px; margin: 12px 0;">
<h5 style="margin: 0 0 4px 0; color: inherit; font-size: 14.5px; font-weight: 700;">⚡ Opción A: Programar Ajuste Compensatorio al Próximo Mes ({next_m_key})</h5>
<p style="margin: 0; font-size: 13px; opacity: 0.95;">Restaura la disciplina patrimonial reduciendo en <strong>{excess_amt:,.2f} €</strong> el presupuesto de Deseos del mes siguiente (<strong>{next_m_key}</strong>) para devolver al ahorro lo restado este mes.</p>
</div>""",
                    unsafe_allow_html=True,
                )
                w_col1, w_col2 = st.columns([2, 1])
                with w_col1:
                    sub_opts_wants = {s["id"]: s["nombre"] for s in wants_subcats}
                    target_next_id = st.selectbox(
                        f"Subcategoría de Deseos a Reducir en {next_m_key}:",
                        options=list(sub_opts_wants.keys()),
                        format_func=lambda x: sub_opts_wants.get(x, f"Subcat {x}"),
                        key=f"wants_comp_sub_{m_key}_{g_idx}",
                    )
                with w_col2:
                    st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
                    if st.button(f"⚡ Programar Recorte ({excess_amt:,.2f} €)", key=f"btn_wants_comp_{m_key}_{g_idx}", type="primary"):
                        if api_client:
                            res = api_client.compensate_guideline_deficit(
                                month_key=m_key,
                                action_type="WANTS_COMPENSATION_NEXT_MONTH",
                                amount=excess_amt,
                                target_subcategory_id=target_next_id,
                            )
                            if res and res.get("success"):
                                st.toast(f"¡Ajuste compensatorio programado para {next_m_key} (-{excess_amt:,.2f} €)!", icon="⚡")
                                st.rerun()
                            else:
                                st.error("No se pudo programar el ajuste compensatorio en el backend.")

            # Congelación de ocio ante caída de ingresos (Fase 4: INCOME_SHORTFALL)
            if scen_type == "INCOME_SHORTFALL" and wants_subcats:
                st.markdown(
                    f"""<div style="background: rgba(2, 119, 189, 0.08); border: 1px solid #0277bd; border-left: 6px solid #0277bd; border-radius: 8px; padding: 12px 16px; margin: 12px 0;">
<h5 style="margin: 0 0 4px 0; color: inherit; font-size: 14.5px; font-weight: 700;">❄️ Protocolo de Contingencia: Congelar Deseos del Mes ({m_key})</h5>
<p style="margin: 0; font-size: 13px; opacity: 0.95;">Ante la caída imprevista de ingresos en <strong>{m_key}</strong>, reduce temporalmente a 0.00 € las partidas de Deseos para garantizar el pago de Necesidades Básicas.</p>
</div>""",
                    unsafe_allow_html=True,
                )
                if st.button(f"❄️ Congelar Deseos de Este Mes ({m_key})", key=f"btn_freeze_{m_key}_{g_idx}", type="primary"):
                    if api_client:
                        res = api_client.compensate_guideline_deficit(
                            month_key=m_key,
                            action_type="FREEZE_WANTS",
                            target_subcategory_ids=[s["id"] for s in wants_subcats],
                        )
                        if res and res.get("success"):
                            st.toast("¡Partidas de Deseos congeladas a 0 € con éxito!", icon="❄️")
                            st.rerun()
                        else:
                            st.error("No se pudo congelar las partidas de Deseos en el backend.")

            # Recomendación operativa: SÓLO mostrar en Dinero Sin Asignar (HIGH_UNASSIGNED)
            if scen_type == "HIGH_UNASSIGNED" and g.key_recommendation:
                st.markdown(
                    f'<div style="padding-left: 24px; margin-top: -4px; margin-bottom: 12px; font-size: 13.5px; opacity: 0.9;">'
                    f'💡 <strong>Recomendación Operativa:</strong> {g.key_recommendation}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # 4. Acción de Barrido de Fin de Mes (Cierre Contable a partir del día 26)
        if is_sweep_active:
            if visible_guidelines:
                st.markdown("---")

            # Detectar si hay un colchón prudencial activo de una estrategia previa
            applied = getattr(report, "applied_strategy", None)
            has_active_cushion = False
            cushion_amt = 0.0
            strat_label = ""
            split_cfg = None

            if applied:
                is_partial = bool(applied.get("is_partial", False))
                cushion_amt = float(applied.get("cushion_amount", 0.0))
                if is_partial and cushion_amt > 0:
                    has_active_cushion = True
                    raw_type = applied.get("strategy_type", "")
                    strat_name_map = {
                        "FIRE": "El Acelerador FIRE (100% Ahorro)",
                        "SINKING_FUND": "Sinking Fund",
                        "HYBRID_80_20": "El Enfoque Híbrido (Regla 80/20)",
                        "EIGHTY_TWENTY": "El Enfoque Híbrido (Regla 80/20)",
                    }
                    strat_label = strat_name_map.get(raw_type, f"Estrategia {raw_type}")
                    split_cfg = applied.get("split_config")

            if has_active_cushion:
                st.markdown(
                    f"""<div style="background: rgba(21, 101, 192, 0.08); border: 1px solid #1565c0; border-left: 6px solid #1565c0; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
<h5 style="margin: 0 0 4px 0; color: inherit; font-size: 15px; font-weight: 700;">🧹 Barrido de Fin de Mes (Liquidación de Colchón y Remanente)</h5>
<p style="margin: 0; font-size: 13px; opacity: 0.95;">Has alcanzado el cierre del mes con un remanente en cuenta corriente de <strong>{unassigned_cash:,.2f} €</strong> (mantienes un colchón prudencial de <strong>{cushion_amt:,.2f} €</strong> no consumido en Necesidades Básicas tras ejecutar <em>{strat_label}</em>).</p>
</div>""",
                    unsafe_allow_html=True,
                )

                sweep_mode = st.radio(
                    "Modalidad de Liquidación del Remanente:",
                    options=["INHERIT_STRATEGY", "DEFAULT_SAVINGS"],
                    format_func=lambda x: (
                        f"✨ Completar estrategia del mes ({strat_label})"
                        if x == "INHERIT_STRATEGY"
                        else "🏦 Barrer 100% a Ahorro tradicional"
                    ),
                    key=f"sweep_mode_{m_key}",
                    horizontal=True,
                )

                if sweep_mode == "INHERIT_STRATEGY":
                    # Vista previa proporcional
                    if split_cfg:
                        orig_s = split_cfg.get("savings", [])
                        orig_w = split_cfg.get("wants", [])
                        tot_orig = sum(float(x.get("amount", 0.0)) for x in orig_s + orig_w)
                        if tot_orig > 0:
                            sub_names = {s["id"]: s["nombre"] for s in (savings_subcats + (wants_subcats or []))}
                            items_preview = []
                            for x in orig_s:
                                sh = float(x.get("amount", 0.0)) / tot_orig
                                nm = x.get("name") or sub_names.get(x.get("subcategory_id"), f"Subcat {x.get('subcategory_id')}")
                                items_preview.append(f"🔒 Ahorro ({nm}): **{unassigned_cash * sh:,.2f} €** ({sh*100:.0f}%)")
                            for x in orig_w:
                                sh = float(x.get("amount", 0.0)) / tot_orig
                                nm = x.get("name") or sub_names.get(x.get("subcategory_id"), f"Subcat {x.get('subcategory_id')}")
                                items_preview.append(f"🎯 Deseos ({nm}): **{unassigned_cash * sh:,.2f} €** ({sh*100:.0f}%)")
                            st.caption("Distribución proporcional según la pauta del mes: " + " · ".join(items_preview))

                    if st.button(
                        f"⚡ Liquidar y Completar Estrategia ({unassigned_cash:,.2f} €)",
                        key=f"btn_sweep_inherit_{m_key}",
                        type="primary",
                    ):
                        if api_client:
                            res = api_client.sweep_month_surplus(
                                month_key=m_key,
                                amount=unassigned_cash,
                                mode="INHERIT_STRATEGY",
                            )
                            if res and res.get("success"):
                                st.toast(f"¡Estrategia completada! Barrido proporcional de {unassigned_cash:,.2f} € ejecutado.", icon="✨")
                                st.rerun()
                            else:
                                st.error("No se pudo ejecutar el barrido proporcional en el backend.")
                else:
                    # Modo DEFAULT_SAVINGS con colchón
                    sweep_col1, sweep_col2 = st.columns([2, 1])
                    with sweep_col1:
                        sub_opts_sav = {s["id"]: s["nombre"] for s in savings_subcats}
                        default_target = emergency_subcat_id if (not is_ef_completed and emergency_subcat_id) else list(sub_opts_sav.keys())[0]
                        target_sweep_id = st.selectbox(
                            "Subcategoría Destino del Barrido:",
                            options=list(sub_opts_sav.keys()),
                            index=list(sub_opts_sav.keys()).index(default_target) if default_target in sub_opts_sav else 0,
                            format_func=lambda x: sub_opts_sav.get(x, f"Subcat {x}"),
                            key=f"sweep_target_{m_key}",
                        )
                    with sweep_col2:
                        st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
                        if st.button(f"⚡ Barrer 100% a Ahorro ({unassigned_cash:,.2f} €)", key=f"btn_sweep_def_{m_key}", type="primary"):
                            if api_client:
                                res = api_client.sweep_month_surplus(
                                    month_key=m_key,
                                    amount=unassigned_cash,
                                    target_subcategory_id=target_sweep_id,
                                    mode="DEFAULT_SAVINGS",
                                )
                                if res and res.get("success"):
                                    st.toast(f"¡Barrido a ahorro ejecutado ({unassigned_cash:,.2f} €)!", icon="🧹")
                                    st.rerun()
                                else:
                                    st.error("No se pudo ejecutar el barrido en el backend.")
            else:
                # Comportamiento tradicional sin colchón activo
                st.markdown(
                    f"""<div style="background: rgba(21, 101, 192, 0.08); border: 1px solid #1565c0; border-left: 6px solid #1565c0; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
<h5 style="margin: 0 0 4px 0; color: inherit; font-size: 15px; font-weight: 700;">🧹 Barrido de Fin de Mes (Cierre Contable)</h5>
<p style="margin: 0; font-size: 13px; opacity: 0.95;">Has alcanzado el cierre del mes con un remanente no gastado de <strong>{unassigned_cash:,.2f} €</strong>. Transfiérelo al ahorro para cerrar el mes con tasa de ahorro maximizada.</p>
</div>""",
                    unsafe_allow_html=True,
                )
                sweep_col1, sweep_col2 = st.columns([2, 1])
                with sweep_col1:
                    sub_opts_sav = {s["id"]: s["nombre"] for s in savings_subcats}
                    default_target = emergency_subcat_id if (not is_ef_completed and emergency_subcat_id) else list(sub_opts_sav.keys())[0]
                    target_sweep_id = st.selectbox(
                        "Subcategoría Destino del Barrido:",
                        options=list(sub_opts_sav.keys()),
                        index=list(sub_opts_sav.keys()).index(default_target) if default_target in sub_opts_sav else 0,
                        format_func=lambda x: sub_opts_sav.get(x, f"Subcat {x}"),
                        key=f"sweep_target_{m_key}",
                    )
                with sweep_col2:
                    st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
                    if st.button(f"⚡ Ejecutar Barrido ({unassigned_cash:,.2f} €)", key=f"btn_sweep_{m_key}", type="primary"):
                        if api_client:
                            res = api_client.sweep_month_surplus(m_key, unassigned_cash, target_sweep_id, mode="DEFAULT_SAVINGS")
                            if res and res.get("success"):
                                st.toast(f"¡Barrido de fin de mes ejecutado ({unassigned_cash:,.2f} €)!", icon="🧹")
                                st.rerun()
                            else:
                                st.error("No se pudo ejecutar el barrido en el backend.")


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
    is_empty_year = (
        report.overall_health == "Año sin Información Financiera"
        or (
            not report.guidelines
            and float(report.average_savings_rate or 0.0) == 0.0
            and "sin Información" in str(report.overall_health or "")
        )
    )

    if is_empty_year:
        expander_title = "ℹ️ Diagnóstico Estructural y Pautas Anuales (Año sin Información Financiera)"
        with st.expander(expander_title, expanded=expanded):
            st.markdown(
                """<div style="background: rgba(128, 128, 128, 0.08); border-left: 5px solid #757575; padding: 12px 16px; border-radius: 6px; margin: 4px 0 10px 0;">
<span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: #757575;">ℹ️ Año sin Información Financiera</span><br>
<span style="font-size: 13.5px; opacity: 0.95;">No se han registrado transacciones ni presupuesto en este ejercicio. El diagnóstico estructural y la detección de riesgos se activarán automáticamente cuando haya actividad financiera.</span>
</div>""",
                unsafe_allow_html=True,
            )
        return

    border_color, bg_color, icon = _get_severity_colors(report.status_severity)

    overall_health = report.overall_health or "Consolidado Anual"
    expander_title = (
        f"{icon} Diagnóstico Estructural y Pautas Anuales ({overall_health})"
    )

    with st.expander(expander_title, expanded=expanded):
        avg_savings = float(report.average_savings_rate or 0.0)
        summary = report.summary_text or ""
        st.markdown(
            f"""<div style="background: {bg_color}; border-left: 5px solid {border_color}; padding: 12px 16px; border-radius: 6px; margin-bottom: 14px;">
<span style="font-weight: 700; font-size: 14px; text-transform: uppercase; color: {border_color};">{icon} Estado Anual Consolidado: {overall_health}</span><br>
<span style="font-size: 13.5px; opacity: 0.95;">Tasa de Ahorro Media Anual: <strong>{avg_savings:.2f}%</strong> (Meta mínima: 20.00%) — {summary}</span>
</div>""",
            unsafe_allow_html=True,
        )

        guidelines = report.guidelines or []
        if guidelines:
            st.markdown("##### 🔬 Análisis de Factores Estructurales")
            for g in guidelines:
                g_border, g_bg, g_icon = _get_severity_colors(g.severity)
                st.markdown(
                    f"""<div style="background: {g_bg}; border: 1px solid {g_border}; border-left: 5px solid {g_border}; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
<h5 style="margin: 0; font-size: 15px; font-weight: 700; color: inherit;">{g_icon} {g.title}</h5>
<span style="background: {g_border}; color: white; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 4px;">{g.metric_value_text}</span>
</div>
<p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.45; color: inherit;">{g.description}</p>
<div style="background: rgba(0,0,0,0.05); padding: 8px 12px; border-radius: 6px; font-size: 12.5px;"><strong>🛠️ Plan de Calibración:</strong> {g.action_plan}</div>
</div>""",
                    unsafe_allow_html=True,
                )


__all__ = [
    "GuidelineSeverity",
    "render_monthly_guidelines_expander",
    "render_annual_guidelines_expander",
]
