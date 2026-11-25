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


def render_base_budget_settings_view(categorias: List[Dict[str, Any]], todas_subcats: List[Dict[str, Any]], colores_cabecera: Dict[str, str]) -> None:
    """Renderiza la pestaña de Plantilla BASE y Subcategorías."""
    st.header("⚙️ Configuración del Presupuesto Base (Plantilla)")
    st.caption("Establece las cantidades presupuestadas habituales para tus ingresos y gastos. Todos los meses utilizarán por defecto estos valores si no tienen una excepción propia.")

    if not categorias:
        st.info("La base de datos está vacía.")
    else:
        presupuestos_base = api_client.get_presupuestos("BASE")
        base_map = {(p.get('subcategoria_id') if p.get('subcategoria_id') is not None else p.get('subcategory_id')): (p.get('cantidad') if p.get('cantidad') is not None else p.get('amount', 0.0)) for p in presupuestos_base} if presupuestos_base else {}
    
        # 1. EXPANDER: FORMULARIO DE CONFIGURACIÓN DEL PRESUPUESTO BASE (ARRIBA)
        with st.expander("⚙️ Formulario de Configuración del Presupuesto Base", expanded=False):
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

        # SEPARADOR Y EXPLICACIÓN DEL ADMINISTRADOR DE SUBCATEGORÍAS
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("Personaliza y organiza los conceptos de gasto y ahorro de tu presupuesto. Añade nuevas subcategorías a tu medida o renombra y elimina aquellas personalizadas que hayas creado y ya no utilices.")

        # 2. EXPANDER: GESTIÓN DE SUBCATEGORÍAS PERSONALIZADAS (DEBAJO)
        with st.expander("🏷️ Administrar Subcategorías Personalizadas", expanded=False):
            st.markdown("#### ➕ Añadir Nueva Subcategoría")
            st.caption("Crea conceptos personalizados para adaptar el presupuesto a tu estilo de vida.")

            cats_disponibles = [c for c in categorias if c.get("tipo") in ("gasto", "ahorro") or c.get("type") in ("gasto", "ahorro")]
            if not cats_disponibles:
                st.info("No se encontraron categorías de gastos o ahorro disponibles.")
            else:
                saved_cat_id = st.session_state.get("last_selected_personal_cat_id")
                default_cat_idx = 0
                if saved_cat_id is not None:
                    for idx_c, c_opt in enumerate(cats_disponibles):
                        if c_opt.get("id") == saved_cat_id:
                            default_cat_idx = idx_c
                            break

                with st.form("form_alta_subcat_personal", clear_on_submit=True):
                    col_cat_sel, col_sub_nom, col_sub_pres, col_sub_mes = st.columns([1.4, 1.8, 1.1, 1.3])
                    with col_cat_sel:
                        selected_cat = st.selectbox(
                            "Categoría Principal",
                            options=cats_disponibles,
                            index=default_cat_idx,
                            format_func=lambda c: c.get("nombre") or c.get("name", ""),
                            key="sel_new_subcat_parent"
                        )
                    with col_sub_nom:
                        new_sub_name = st.text_input(
                            "Nombre de la Subcategoría",
                            placeholder="Ej: Veterinario, Cursos, etc.",
                            key="txt_new_subcat_name"
                        )
                    with col_sub_pres:
                        new_sub_budget = st.number_input(
                            "Presupuesto (€, opc.)",
                            min_value=0.0,
                            value=0.0,
                            step=10.0,
                            key="num_new_subcat_budget"
                        )
                    today_dt = date.today()
                    curr_natural_year = today_dt.year
                    default_month_idx = max(0, min(11, today_dt.month - 1))
                    with col_sub_mes:
                        start_month_name = st.selectbox(
                            f"A partir de ({curr_natural_year})",
                            options=MESES_NOMBRES,
                            index=default_month_idx,
                            key="sel_new_subcat_start_month",
                            help=f"El presupuesto mensual se aplicará desde este mes hasta diciembre de {curr_natural_year}. Los meses anteriores tendrán 0,00 €."
                        )

                    btn_add_subcat = st.form_submit_button("💾 Guardar Nueva Subcategoría", width="stretch")
                    if btn_add_subcat:
                        st.session_state["last_selected_personal_cat_id"] = selected_cat["id"]
                        cleaned_name = new_sub_name.strip()
                        if not cleaned_name:
                            st.warning("⚠️ Debes indicar un nombre para la subcategoría.")
                        else:
                            existing_names = [
                                (s.get("nombre") or s.get("name", "")).strip().lower()
                                for s in todas_subcats
                                if (s.get("categoria_id") if s.get("categoria_id") is not None else s.get("category_id")) == selected_cat["id"]
                            ]
                            if cleaned_name.lower() in existing_names:
                                st.warning(f"⚠️ Ya existe una subcategoría con el nombre '{cleaned_name}' en {selected_cat.get('nombre') or selected_cat.get('name')}.")
                            else:
                                created_sub = api_client.create_subcategory(
                                    category_id=selected_cat["id"],
                                    name=cleaned_name
                                )
                                if created_sub:
                                    if new_sub_budget > 0:
                                        start_month_num = (MESES_NOMBRES.index(start_month_name) + 1) if start_month_name in MESES_NOMBRES else today_dt.month
                                        bulk_presupuestos = [
                                            {"mes": "BASE", "subcategoria_id": created_sub["id"], "cantidad": new_sub_budget}
                                        ]
                                        # Meses anteriores del año natural: 0.00 € explícito para blindar el histórico
                                        for m in range(1, start_month_num):
                                            bulk_presupuestos.append({
                                                "mes": f"{curr_natural_year}-{m:02d}",
                                                "subcategoria_id": created_sub["id"],
                                                "cantidad": 0.0
                                            })
                                        # Mes de inicio y posteriores del año natural: nuevo presupuesto
                                        for m in range(start_month_num, 13):
                                            bulk_presupuestos.append({
                                                "mes": f"{curr_natural_year}-{m:02d}",
                                                "subcategoria_id": created_sub["id"],
                                                "cantidad": new_sub_budget
                                            })
                                        api_client.save_presupuestos_bulk(bulk_presupuestos)
                                    st.success(f"✅ ¡Subcategoría '{cleaned_name}' creada exitosamente!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ No se pudo crear la subcategoría '{cleaned_name}'. Verifica si ya existe o contacta con el administrador.")

            st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown("#### 📋 Catálogo y Edición de Subcategorías")
            st.caption("Solo se pueden renombrar o eliminar las subcategorías personalizadas creadas por ti que no tengan transacciones vinculadas. Las subcategorías base del sistema están protegidas.")

            for cat in cats_disponibles:
                n_cat = cat.get("nombre") or cat.get("name", "")
                subcats_c = [
                    s for s in todas_subcats 
                    if (s.get("categoria_id") if s.get("categoria_id") is not None else s.get("category_id")) == cat["id"]
                ]
                if not subcats_c:
                    continue

                h_color = colores_cabecera.get(n_cat, "#333333")
                st.markdown(f"""<div style="border-left: 5px solid {h_color}; padding-left: 10px; margin-top: 15px; margin-bottom: 8px;">
<h5 style="margin: 0; color: inherit; font-family: 'Inter', sans-serif;">{n_cat}</h5>
</div>""", unsafe_allow_html=True)

                for s in subcats_c:
                    s_id = s["id"]
                    s_name = s.get("nombre") or s.get("name", "")
                    b_val = base_map.get(s_id, 0.0)
                    is_base = is_default_personal_subcategory(s_name)

                    col_info, col_ren, col_del = st.columns([3, 1, 1])
                    with col_info:
                        badge_base = " &nbsp; <span style='background: rgba(148, 163, 184, 0.15); color: #94a3b8; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;'>Base</span>" if is_base else ""
                        st.markdown(f"**{s_name}**{badge_base} &nbsp; <span style='color: #64748b; font-size: 0.85rem;'>[Base: {b_val:.2f} €/mes]</span>", unsafe_allow_html=True)

                    if not is_base:
                        with col_ren:
                            with st.popover("✏️ Renombrar", key=f"pop_ren_{s_id}"):
                                st.markdown(f"**Renombrar '{s_name}'**")
                                ren_name = st.text_input("Nuevo nombre:", value=s_name, key=f"ren_input_{s_id}")
                                if st.button("Guardar Nombre", key=f"btn_confirm_ren_{s_id}"):
                                    if ren_name.strip() and ren_name.strip() != s_name:
                                        res_ren = api_client.update_subcategory(s_id, ren_name.strip())
                                        if res_ren:
                                            st.success("✅ Nombre actualizado.")
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar nombre.")
                                    elif not ren_name.strip():
                                        st.warning("El nombre no puede estar vacío.")

                        with col_del:
                            with st.popover("🗑️ Eliminar", key=f"pop_del_{s_id}"):
                                st.markdown(f"**Eliminar '{s_name}'**")
                                st.warning("Solo se eliminará si no contiene transacciones vinculadas.")
                                if st.button("Confirmar Borrado", key=f"btn_confirm_del_{s_id}", type="primary"):
                                    ok_del, msg_del = api_client.delete_subcategory(s_id)
                                    if ok_del:
                                        st.success(f"✅ {msg_del}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {msg_del}")

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
# PESTAÑA 19: BASE DE DATOS Y COPIAS DE SEGURIDAD
# ==========================================
