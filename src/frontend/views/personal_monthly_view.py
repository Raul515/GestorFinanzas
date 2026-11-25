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


def render_personal_monthly_view(year_selected: int, categorias: List[Dict[str, Any]], todas_subcats: List[Dict[str, Any]], subcat_options: Dict[int, str], colores_cabecera: Dict[str, str], ingresos_name: str, necesidades_name: str, deseos_name: str, ahorro_name: str) -> None:
    """Renderiza la pestaña de Gestión Mensual personal."""
    if "personal_active_month_idx" not in st.session_state:
        st.session_state["personal_active_month_idx"] = min(max(datetime.now().month - 1, 0), 11)

    col_nav_prev, col_nav_sel, col_nav_next, _ = st.columns([1.2, 2.6, 1.2, 3.0])
    with col_nav_prev:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("◀ Mes Anterior", width="stretch", key="btn_personal_prev_month", help="Ir al mes anterior"):
            st.session_state["personal_active_month_idx"] = (st.session_state["personal_active_month_idx"] - 1) % 12
            st.rerun()

    with col_nav_sel:
        cur_idx = st.session_state["personal_active_month_idx"] % 12
        selected_month_name = st.selectbox(
            "Selecciona Mes a Gestionar",
            MESES_NOMBRES,
            index=cur_idx,
            key=f"sel_personal_month_display_{cur_idx}",
        )
        if selected_month_name != MESES_NOMBRES[st.session_state["personal_active_month_idx"]]:
            st.session_state["personal_active_month_idx"] = MESES_NOMBRES.index(selected_month_name)
            st.rerun()
        idx = st.session_state["personal_active_month_idx"] + 1
        mes_key = f"{year_selected}-{idx:02d}"
        nombre_mes = selected_month_name

    with col_nav_next:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Mes Siguiente ▶", width="stretch", key="btn_personal_next_month", help="Ir al mes siguiente"):
            st.session_state["personal_active_month_idx"] = (st.session_state["personal_active_month_idx"] + 1) % 12
            st.rerun()

    st.header(f"Gestión de Finanzas - {nombre_mes} {year_selected}")


    # Cargar datos del mes
    presupuestos_m = api_client.get_presupuestos(mes_key)
    transacciones_m = api_client.get_transacciones(mes_key)

    if not categorias:
        st.info("La base de datos está vacía o el backend no está corriendo.")
        pass

    # Detección defensiva de subcategorías recién creadas en transacciones
    known_subcat_ids = {s['id'] for s in todas_subcats}
    tx_unknown = any(
        (t.get('subcategoria_id') if t.get('subcategoria_id') is not None else t.get('subcategory_id')) not in known_subcat_ids
        for t in (transacciones_m or [])
        if (t.get('subcategoria_id') if t.get('subcategoria_id') is not None else t.get('subcategory_id')) is not None
    )
    if tx_unknown:
        api_client.clear_categories_cache()
        st.cache_data.clear()
        todas_subcats = api_client.get_subcategorias()
        categorias = api_client.get_categorias()
        subcat_options = {s['id']: s.get('nombre') or s.get('name') for s in todas_subcats} if todas_subcats else {}

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
                if not tx_sub and tx_sub_id:
                    api_client.clear_categories_cache()
                    st.cache_data.clear()
                    fresh_subcats = api_client.get_subcategorias()
                    fresh_cats = api_client.get_categorias()
                    if fresh_subcats:
                        subcat_map = {s['id']: s for s in fresh_subcats}
                        tx_sub = subcat_map.get(tx_sub_id)
                    if fresh_cats:
                        cat_map = {c['id']: c for c in fresh_cats}
                sub_nombre = (tx_sub.get("nombre") or tx_sub.get("name")) if tx_sub else f"Subcategoría #{tx_sub_id}"

                cat_id = (tx_sub.get("categoria_id") if tx_sub.get("categoria_id") is not None else tx_sub.get("category_id")) if tx_sub else None
                cat_obj = cat_map.get(cat_id) if cat_id else None
                cat_nombre = (cat_obj.get("nombre") or cat_obj.get("name")) if cat_obj else "—"

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




