import streamlit as st
import pandas as pd
from datetime import date
import api_client

st.set_page_config(page_title="Gestor Finanzas", layout="wide")

# Load CSS
import os
css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
if os.path.exists(css_path):
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

st.title("Gestor de Finanzas Personales")

# Sidebar for global filters and entry
st.sidebar.header("Filtros")
mes_actual = st.sidebar.text_input("Mes (YYYY-MM)", value=date.today().strftime("%Y-%m"))

st.sidebar.header("Añadir Transacción")
todas_subcats = api_client.get_subcategorias()
if todas_subcats:
    subcat_options = {s['id']: s['nombre'] for s in todas_subcats}
    selected_subcat = st.sidebar.selectbox("Subcategoría", options=list(subcat_options.keys()), format_func=lambda x: subcat_options[x])
    cantidad = st.sidebar.number_input("Cantidad (€)", min_value=0.0, step=10.0)
    concepto = st.sidebar.text_input("Concepto")
    fecha = st.sidebar.date_input("Fecha", value=date.today())
    if st.sidebar.button("Guardar Transacción"):
        api_client.create_transaccion(fecha, selected_subcat, cantidad, concepto)
        st.sidebar.success("Transacción añadida!")
        st.rerun()
else:
    st.sidebar.warning("No hay subcategorías en la BBDD. Asegúrate de inicializar el backend.")

# Main Dashboard
st.header(f"Resumen de {mes_actual}")

# Fetch data
categorias = api_client.get_categorias()
presupuestos = api_client.get_presupuestos(mes_actual)
transacciones = api_client.get_transacciones(mes_actual)
todas_subcats = api_client.get_subcategorias()

if not categorias:
    st.info("La base de datos está vacía o el backend no está corriendo. Revisa que FastAPI esté funcionando en el puerto 8000.")
else:
    # 1. Calcular totales para la gráfica y la lógica general
    totales = {}
    for cat in categorias:
        subcats = [s for s in todas_subcats if s['categoria_id'] == cat['id']]
        total_pres = 0.0
        total_real = 0.0
        for s in subcats:
            s_id = s['id']
            # Presupuesto
            if presupuestos:
                p_row = [p for p in presupuestos if p['subcategoria_id'] == s_id]
                if p_row:
                    total_pres += p_row[0]['cantidad']
            # Real
            if transacciones:
                r_sum = sum(t['cantidad'] for t in transacciones if t['subcategoria_id'] == s_id)
                total_real += r_sum
        totales[cat['nombre']] = {
            "presupuesto": total_pres,
            "real": total_real,
            "tipo": cat['tipo'],
            "subcategorias": subcats
        }
    
    # 2. Renderizar gráficos de la Regla 50/30/20
    necesidades_name = "Necesidades Básicas"
    deseos_name = "Deseos y Estilo de vida"
    ahorro_name = "Ahorro e Inversión"
    
    pres_nec = totales.get(necesidades_name, {}).get("presupuesto", 0.0)
    real_nec = totales.get(necesidades_name, {}).get("real", 0.0)
    
    pres_des = totales.get(deseos_name, {}).get("presupuesto", 0.0)
    real_des = totales.get(deseos_name, {}).get("real", 0.0)
    
    pres_aho = totales.get(ahorro_name, {}).get("presupuesto", 0.0)
    real_aho = totales.get(ahorro_name, {}).get("real", 0.0)
    
    total_gasto_pres = pres_nec + pres_des + pres_aho
    total_gasto_real = real_nec + real_des + real_aho
    
    pct_nec_pres = (pres_nec / total_gasto_pres * 100) if total_gasto_pres > 0 else 0.0
    pct_des_pres = (pres_des / total_gasto_pres * 100) if total_gasto_pres > 0 else 0.0
    pct_aho_pres = (pres_aho / total_gasto_pres * 100) if total_gasto_pres > 0 else 0.0
    
    pct_nec_real = (real_nec / total_gasto_real * 100) if total_gasto_real > 0 else 0.0
    pct_des_real = (real_des / total_gasto_real * 100) if total_gasto_real > 0 else 0.0
    pct_aho_real = (real_aho / total_gasto_real * 100) if total_gasto_real > 0 else 0.0
    
    # Gráficos y KPI de totales
    import altair as alt
    
    chart_col, metrics_col = st.columns([2, 1])
    
    with chart_col:
        data_pct = pd.DataFrame([
            {"Categoría": "Necesidades (50%)", "Distribución": "Objetivo", "Porcentaje": 50.0},
            {"Categoría": "Deseos (30%)", "Distribución": "Objetivo", "Porcentaje": 30.0},
            {"Categoría": "Ahorro/Inv (20%)", "Distribución": "Objetivo", "Porcentaje": 20.0},
            
            {"Categoría": "Necesidades (50%)", "Distribución": "Presupuestado", "Porcentaje": pct_nec_pres},
            {"Categoría": "Deseos (30%)", "Distribución": "Presupuestado", "Porcentaje": pct_des_pres},
            {"Categoría": "Ahorro/Inv (20%)", "Distribución": "Presupuestado", "Porcentaje": pct_aho_pres},
            
            {"Categoría": "Necesidades (50%)", "Distribución": "Real", "Porcentaje": pct_nec_real},
            {"Categoría": "Deseos (30%)", "Distribución": "Real", "Porcentaje": pct_des_real},
            {"Categoría": "Ahorro/Inv (20%)", "Distribución": "Real", "Porcentaje": pct_aho_real},
        ])
        
        chart = alt.Chart(data_pct).mark_bar().encode(
            x=alt.X('Distribución:N', title=None, sort=['Objetivo', 'Presupuestado', 'Real']),
            y=alt.Y('Porcentaje:Q', title="Porcentaje (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color('Categoría:N', scale=alt.Scale(
                domain=['Necesidades (50%)', 'Deseos (30%)', 'Ahorro/Inv (20%)'],
                range=['#1565c0', '#ef6c00', '#00838f']
            )),
            tooltip=['Categoría', 'Distribución', alt.Tooltip('Porcentaje:Q', format='.1f')]
        ).properties(
            height=300,
            title="Distribución del Gasto (Regla 50/30/20)"
        )
        st.altair_chart(chart, use_container_width=True)
        
    with metrics_col:
        st.subheader("Totales del Mes")
        total_ingresos_real = totales.get("Ingresos Netos", {}).get("real", 0.0)
        total_ingresos_pres = totales.get("Ingresos Netos", {}).get("presupuesto", 0.0)
        
        st.metric(label="Ingresos Totales (Real)", value=f"{total_ingresos_real:.2f} €", delta=f"{total_ingresos_real - total_ingresos_pres:.2f} € vs Presupuesto")
        st.metric(label="Gastos Totales (Real)", value=f"{total_gasto_real:.2f} €", delta=f"{total_gasto_real - total_gasto_pres:.2f} € vs Presupuesto", delta_color="inverse")
        
        balance = total_ingresos_real - total_gasto_real
        st.metric(label="Balance Neto (Ahorro)", value=f"{balance:.2f} €", delta=f"{balance - (total_ingresos_pres - total_gasto_pres):.2f} € vs Presupuesto")

    st.markdown("---")
    
    # 3. Renderizar tablas personalizadas estilo Excel
    colores_cabecera = {
        "Ingresos Netos": "#2e7d32",
        "Necesidades Básicas": "#1565c0",
        "Deseos y Estilo de vida": "#ef6c00",
        "Ahorro e Inversión": "#00838f"
    }
    
    for cat in categorias:
        nombre_cat = cat['nombre']
        info_cat = totales.get(nombre_cat, {})
        subcats = info_cat.get("subcategorias", [])
        
        if not subcats:
            continue
            
        header_color = colores_cabecera.get(nombre_cat, "#333333")
        
        # Título de sección adaptativo al tema (Light/Dark)
        st.markdown(f"""<div style="border-left: 6px solid {header_color}; padding-left: 12px; margin-top: 30px; margin-bottom: 15px;">
<h3 style="margin: 0; color: inherit; font-family: 'Inter', sans-serif; font-weight: 700;">{nombre_cat}</h3>
</div>""", unsafe_allow_html=True)
        
        col_tabla, col_desv = st.columns([3, 1])
        
        total_pres = info_cat.get("presupuesto", 0.0)
        total_real = info_cat.get("real", 0.0)
        
        with col_tabla:
            filas_html = ""
            for s in subcats:
                s_id = s['id']
                
                pres_val = 0.0
                if presupuestos:
                    p_row = [p for p in presupuestos if p['subcategoria_id'] == s_id]
                    if p_row:
                        pres_val = p_row[0]['cantidad']
                
                real_val = 0.0
                if transacciones:
                    real_val = sum(t['cantidad'] for t in transacciones if t['subcategoria_id'] == s_id)
                
                filas_html += f"""<tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.2);">
<td style="padding: 10px; font-weight: 500; color: inherit;">{s['nombre']}</td>
<td style="padding: 10px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{pres_val:.2f} €</td>
<td style="padding: 10px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{real_val:.2f} €</td>
</tr>"""
                
            tabla_html = f"""<table style="width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; color: inherit;">
<thead>
<tr style="background-color: {header_color}; color: #ffffff !important; text-align: left; font-weight: 600;">
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); border-top-left-radius: 4px; color: #ffffff;">Concepto</th>
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); text-align: right; color: #ffffff;">Presupuesto</th>
<th style="padding: 12px; border-bottom: 2px solid rgba(0,0,0,0.1); text-align: right; border-top-right-radius: 4px; color: #ffffff;">Real</th>
</tr>
</thead>
<tbody>
{filas_html}
<tr style="font-weight: bold; background-color: rgba(128, 128, 128, 0.15);">
<td style="padding: 12px; border-bottom-left-radius: 4px; color: inherit;">TOTAL</td>
<td style="padding: 12px; text-align: right; font-variant-numeric: tabular-nums; color: inherit;">{total_pres:.2f} €</td>
<td style="padding: 12px; text-align: right; font-variant-numeric: tabular-nums; border-bottom-right-radius: 4px; color: inherit;">{total_real:.2f} €</td>
</tr>
</tbody>
</table>"""
            st.markdown(tabla_html, unsafe_allow_html=True)
            
        with col_desv:
            # Calcular desviación según tipo de categoría
            if cat['tipo'] == 'ingreso':
                desviacion = total_real - total_pres
                es_positivo = desviacion >= 0
            else:
                if nombre_cat == "Ahorro e Inversión":
                    desviacion = total_real - total_pres
                    es_positivo = desviacion >= 0
                else:
                    # Para gastos, gastar menos es positivo (verde)
                    desviacion = total_pres - total_real
                    es_positivo = desviacion >= 0
            
            # Estilo condicional de desviación (verde brillante para positivo, rojo claro para negativo)
            if es_positivo:
                bg_color = "rgba(46, 125, 50, 0.15)"
                border_color = "#2e7d32"
                text_color = "#4caf50"
                signo = "+"
            else:
                bg_color = "rgba(198, 40, 40, 0.15)"
                border_color = "#c62828"
                text_color = "#ef5350"
                signo = ""
                
            desviacion_card = f"""<div style="background-color: {bg_color}; border: 2px solid {border_color}; padding: 22px 15px; border-radius: 8px; text-align: center; margin-top: 38px;">
<span style="color: inherit; font-size: 13px; font-weight: 600; display: block; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px;">Desviación Total</span>
<span style="color: {text_color}; font-size: 24px; font-weight: 700; display: block; font-variant-numeric: tabular-nums;">{signo}{desviacion:.2f} €</span>
</div>"""
            st.markdown(desviacion_card, unsafe_allow_html=True)
