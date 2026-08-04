import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime
import os
import api_client
from services.financial_calculator import (
    calculate_category_totals,
    calculate_503020_percentages,
    calculate_annual_metrics
)

st.set_page_config(page_title="Gestor Finanzas", layout="wide")

# Load CSS
css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

st.title("Gestor de Finanzas Personales")

# Sidebar para selección de año
st.sidebar.header("Configuración")
year_today = date.today().year
year_selected = st.sidebar.number_input("Año", min_value=2000, max_value=2100, value=year_today, step=1)

MESES_NOMBRES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# Pestañas de Navegación (Resumen Anual + 12 Meses + Presupuesto Base)
tabs_list = ["📊 Resumen Anual"] + MESES_NOMBRES + ["⚙️ Presupuesto Base"]
tabs = st.tabs(tabs_list)

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
with tabs[0]:
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
                cat_subcats = [s for s in todas_subcats if s['categoria_id'] == cat['id']]
                p_sum = 0.0
                r_sum = 0.0
                for s in cat_subcats:
                    s_id = s['id']
                    p_val = 0.0
                    if presupuestos_m:
                        p_match = [p for p in presupuestos_m if p['subcategoria_id'] == s_id]
                        if p_match:
                            p_val = p_match[0]['cantidad']
                    p_sum += p_val
                    
                    t_val = 0.0
                    if transacciones_m:
                        r_match = [t['cantidad'] for t in transacciones_m if t['subcategoria_id'] == s_id]
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

        # 1. TARJETAS KPI SUPERIORES ANUALES (4 Columnas)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
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
            
        with kpi4:
            st.markdown(f"""<div style="background-color: rgba(0, 131, 143, 0.1); border: 2px solid #00838f; border-radius: 8px; text-align: center; padding: 15px;">
                <span style="font-size: 11px; font-weight: 700; color: #00838f; text-transform: uppercase;">AHORRO ACUMULADO TOTAL</span>
                <h2 style="margin: 5px 0 0 0; color: inherit; font-size: 22px;">{ahorro_acumulado_total:,.2f} €</h2>
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
            st.altair_chart(donut_chart, use_container_width=True)
            
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
            st.altair_chart(bar_chart, use_container_width=True)

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
        st.altair_chart(line_chart, use_container_width=True)

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
for idx, tab in enumerate(tabs[1:-1], start=1):
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
                        pm = [p for p in presupuestos_m if p['subcategoria_id'] == s_id]
                        if pm:
                            pval = pm[0]['cantidad']
                    rval_trans = 0.0
                    if transacciones_m:
                        rval_trans = sum(t['cantidad'] for t in transacciones_m if t['subcategoria_id'] == s_id)
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
                    st.altair_chart(chart_bars, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. FORMULARIO CON CATEGORÍA Y SUBCATEGORÍA FILTRADA PARA AÑADIR TRANSACCIÓN
        st.markdown("##### ➕ Añadir Nueva Transacción")
        f_col1, f_col2, f_col3, f_col4, f_col5, f_col6 = st.columns([1.8, 2, 2, 2.5, 1.5, 1.2])
        
        with f_col1:
            fecha_val = st.date_input("Fecha", value=date(year_selected, idx, min(date.today().day, 28)), key=f"dt_{mes_key}")
            
        with f_col2:
            cat_options = {c['id']: c['nombre'] for c in categorias}
            cat_sel_id = st.selectbox("Categoría", options=list(cat_options.keys()), format_func=lambda x: cat_options[x], key=f"cat_sb_{mes_key}")
            
        with f_col3:
            subcats_filtradas = [s for s in todas_subcats if s['categoria_id'] == cat_sel_id]
            subcat_opts = {s['id']: s['nombre'] for s in subcats_filtradas}
            subcat_sel_id = st.selectbox("Subcategoría", options=list(subcat_opts.keys()), format_func=lambda x: subcat_opts[x], key=f"subcat_sb_{mes_key}") if subcat_opts else None
            
        with f_col4:
            conc_val = st.text_input("Concepto / Causa", key=f"txt_{mes_key}")
            
        with f_col5:
            cant_val = st.number_input("Cantidad (€)", min_value=0.0, step=10.0, key=f"num_{mes_key}")
            
        with f_col6:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            btn_add = st.button("Guardar", key=f"btn_add_{mes_key}", use_container_width=True)
            
        if btn_add:
            if subcat_sel_id and cant_val > 0:
                api_client.create_transaccion(fecha_val, subcat_sel_id, cant_val, conc_val)
                st.success("¡Transacción guardada correctamente!")
                st.rerun()
            else:
                st.error("Por favor, selecciona una subcategoría y una cantidad mayor a 0.")

        # Personalizar Presupuesto del Mes (Opcional)
        with st.expander(f"✏️ Personalizar Presupuesto de {nombre_mes} (Opcional)"):
            st.caption("Si este mes tiene un gasto o ingreso presupuestado excepcional, puedes modificarlo aquí. De lo contrario, usará los valores por defecto de tu Presupuesto Base.")
            with st.form(key=f"form_pres_mes_{mes_key}"):
                mes_pres_nuevos = []
                p_mes_map = {p['subcategoria_id']: p['cantidad'] for p in presupuestos_m} if presupuestos_m else {}
                
                for cat in categorias:
                    n_cat = cat['nombre']
                    subcats_c = [s for s in todas_subcats if s['categoria_id'] == cat['id']]
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
                
                btn_save_m = st.form_submit_button(f"💾 Guardar Presupuesto de {nombre_mes}", use_container_width=True)
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
                        pm = [p for p in presupuestos_m if p['subcategoria_id'] == s_id]
                        if pm:
                            pval = pm[0]['cantidad']
                    
                    rval_trans = 0.0
                    if transacciones_m:
                        rval_trans = sum(t['cantidad'] for t in transacciones_m if t['subcategoria_id'] == s_id)
                    
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
                
                st.altair_chart(pie_chart, use_container_width=True)
                
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


# ==========================================
# PESTAÑA FINAL: CONFIGURACIÓN DEL PRESUPUESTO BASE
# ==========================================
with tabs[-1]:
    st.header("⚙️ Configuración del Presupuesto Base (Plantilla)")
    st.caption("Establece las cantidades presupuestadas habituales para tus ingresos y gastos. Todos los meses utilizarán por defecto estos valores si no tienen una excepción propia.")
    
    if not categorias:
        st.info("La base de datos está vacía.")
    else:
        presupuestos_base = api_client.get_presupuestos("BASE")
        base_map = {p['subcategoria_id']: p['cantidad'] for p in presupuestos_base} if presupuestos_base else {}
        
        with st.form("form_presupuesto_base"):
            nuevos_presupuestos = []
            
            for cat in categorias:
                n_cat = cat['nombre']
                subcats_c = [s for s in todas_subcats if s['categoria_id'] == cat['id']]
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
            btn_save_base = st.form_submit_button("💾 Guardar Presupuesto Base", use_container_width=True)
            if btn_save_base:
                res = api_client.save_presupuestos_bulk(nuevos_presupuestos)
                if res is not None:
                    st.success("¡Presupuesto Base guardado correctamente! Todos los meses sin presupuesto específico adoptarán estos valores.")
                    st.rerun()
                else:
                    st.error("Error al guardar el presupuesto base.")
